from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_system.theory_paper_v2.application.single_agent_research import (
    AGENT_JUDGMENT_EVIDENCE_LABEL,
    COMPARISON_CLASSES,
    FUNDING_PROXY_STATUS,
    REQUIRED_PATH_CLASSES,
    SYMBOLS,
    SingleAgentResearchError,
    _agent_decision_contract,
    _action_position_truth,
    _current_open_risk,
    _maximum_drawdown,
    _news_rows,
    _ordered_selected_actions,
    _entry_geometry,
    _lot_document,
    _new_risk_vetoes,
    _portfolio_document,
    _portfolio_from_document,
    _pnl_reconciles,
    _process_bars,
    _tactical_reentry_exit_time,
    _timeframe_role_profile,
    _validate_symbol_decision,
)
from trade_system.theory_paper_v2.domain.position import LotRole
from trade_system.theory_paper_v2.infrastructure.offline_portfolio import (
    Attribution,
    LotSide,
    OfflineLot,
    PortfolioState,
)


class SingleAgentResearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 30, 12, tzinfo=UTC)
        self.policy = {
            "standard_risk_fraction": Decimal("0.005"),
            "probe_risk_fraction": Decimal("0.0015"),
            "symbol_risk_fraction": Decimal("0.01"),
            "portfolio_risk_fraction": Decimal("0.03"),
            "gross_multiple": Decimal("1.5"),
            "drawdown_fraction": Decimal("0.05"),
            "minimum_reward_risk": Decimal("1.5"),
            "taker_fee_rate": Decimal("0.0005"),
            "maker_fee_rate": Decimal("0.0002"),
            "market_slippage_bps": Decimal("2"),
            "stop_slippage_bps": Decimal("3"),
            "symbol_notional_fraction": Decimal("0.35"),
            "minimum_notional_usdt": Decimal("50"),
            "maximum_notional_usdt": Decimal("1500"),
        }

    def test_multi_symbol_decision_applies_all_protection_before_new_risk(self) -> None:
        decision = {
            "symbol_decisions": {
                symbol: {"selected_actions": []}
                for symbol in SYMBOLS
            }
        }
        decision["symbol_decisions"]["SNDKUSDT"]["selected_actions"] = [
            {"action_id": "sndk-protect", "action_type": "SET_PROTECTION"},
            {"action_id": "sndk-hold", "action_type": "HOLD"},
        ]
        decision["symbol_decisions"]["MUUSDT"]["selected_actions"] = [
            {"action_id": "mu-open", "action_type": "OPEN_TACTICAL"}
        ]
        decision["symbol_decisions"]["BTCUSDT"]["selected_actions"] = [
            {"action_id": "btc-protect", "action_type": "MOVE_STOP"}
        ]
        ordered = _ordered_selected_actions(decision)
        self.assertEqual(
            [action["action_id"] for _, action in ordered],
            ["sndk-protect", "btc-protect", "sndk-hold", "mu-open"],
        )

    @staticmethod
    def iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def lot(self, role: LotRole, *, target: Decimal | None = None) -> OfflineLot:
        return OfflineLot(
            lot_id=f"lot-{role.value.lower()}",
            instrument_id="SNDKUSDT",
            side=LotSide.LONG,
            role=role,
            attribution=Attribution.STRATEGY,
            quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_price=Decimal("90"),
            target_price=target,
            opened_at=self.now - timedelta(hours=1),
            episode_id="episode-1",
            stage_id="stage-1",
            geometry_id="geometry-1",
        )

    def state_and_context(self, lots: tuple[OfflineLot, ...], *, low: str, high: str):
        portfolio = PortfolioState(
            portfolio_id="portfolio-1",
            revision=0,
            initial_equity=Decimal("10000"),
            realized_pnl_before_cost=Decimal("0"),
            total_fees=Decimal("0"),
            lots=lots,
            fills=(),
        )
        contracts = {}
        for lot in lots:
            contracts[lot.lot_id] = {
                "lot_id": lot.lot_id,
                "episode_id": lot.episode_id,
                "role": lot.role.value,
                "management_checkpoint": "110" if lot.role is LotRole.CORE else None,
                "management_checkpoint_id": "checkpoint-1" if lot.role is LotRole.CORE else None,
                "protection_active_from": self.iso(self.now - timedelta(hours=1)),
                "checkpoint_event_ids": [],
            }
        state = {
            "run_id": "research-run",
            "portfolio": _portfolio_document(portfolio),
            "lot_contracts": contracts,
            "episodes": {symbol: None for symbol in SYMBOLS},
            "orders": [],
            "processed_15m_close_time_ms": {symbol: 0 for symbol in SYMBOLS},
            "target_events": [],
        }
        close = self.now + timedelta(minutes=15)
        empty = {"execution_bars_15m": []}
        context = {
            "decision_at": self.iso(close),
            "symbols": {symbol: dict(empty) for symbol in SYMBOLS},
        }
        context["symbols"]["SNDKUSDT"] = {
            "execution_bars_15m": [
                {
                    "bar_id": "bar-1",
                    "open_time": self.iso(self.now),
                    "available_at": self.iso(close),
                    "close_time_ms": int(close.timestamp() * 1000),
                    "open": "100",
                    "high": high,
                    "low": low,
                    "close": "105",
                }
            ]
        }
        return state, context

    def test_core_checkpoint_is_event_not_automatic_exit(self) -> None:
        state, context = self.state_and_context((self.lot(LotRole.CORE),), low="99", high="112")
        updated, events = _process_bars(state, context, policy=self.policy)
        self.assertEqual("1", updated["portfolio"]["lots"][0]["remaining_quantity"])
        self.assertEqual("CORE_MANAGEMENT_CHECKPOINT_REACHED", events[0]["event_type"])
        self.assertFalse(events[0]["automatic_exit"])

    def test_tactical_target_fills_exactly_and_stop_wins_same_bar(self) -> None:
        tactical = self.lot(LotRole.TACTICAL, target=Decimal("110"))
        state, context = self.state_and_context((tactical,), low="99", high="112")
        state["episodes"]["SNDKUSDT"] = {
            "episode_id": "episode-1",
            "revision": 1,
            "strategic_status": "ACTIVE",
            "exposure_status": "EXPOSED_TACTICAL_ONLY",
            "reentry_contract": None,
            "episode_digest": "pre-bar",
        }
        updated, events = _process_bars(state, context, policy=self.policy)
        self.assertEqual("0", updated["portfolio"]["lots"][0]["remaining_quantity"])
        self.assertEqual("110", updated["portfolio"]["fills"][0]["fill_price"])
        self.assertEqual("TACTICAL_TARGET_FILLED", events[0]["event_type"])
        self.assertEqual("FLAT_WATCH", updated["episodes"]["SNDKUSDT"]["exposure_status"])

        state, context = self.state_and_context((tactical,), low="89", high="112")
        updated, events = _process_bars(state, context, policy=self.policy)
        self.assertEqual("PROTECTIVE_STOP_FILLED", events[0]["event_type"])
        self.assertEqual("89.973", updated["portfolio"]["fills"][0]["fill_price"])

    def test_visible_last_trade_crosses_registered_target_before_agent_market_exit(self) -> None:
        tactical = self.lot(LotRole.TACTICAL, target=Decimal("110"))
        state, context = self.state_and_context((tactical,), low="99", high="109")
        state["episodes"]["SNDKUSDT"] = {
            "episode_id": "episode-1",
            "revision": 1,
            "strategic_status": "ACTIVE",
            "exposure_status": "EXPOSED_TACTICAL_ONLY",
            "reentry_contract": None,
            "episode_digest": "pre-bar",
        }
        context["cycle_index"] = 2
        context["symbols"]["SNDKUSDT"]["market_proxies"] = {
            "ticker_24h": {"last": "111"}
        }
        updated, events = _process_bars(state, context, policy=self.policy)
        target_event = next(
            event for event in events if event["event_type"] == "TACTICAL_TARGET_FILLED"
        )
        self.assertEqual("110", target_event["fill_price"])
        self.assertEqual(
            "VISIBLE_PUBLIC_LAST_TRADE_AT_DECISION", target_event["trigger_source"]
        )
        self.assertEqual("0", updated["portfolio"]["lots"][0]["remaining_quantity"])
        self.assertEqual(
            self.now + timedelta(minutes=15),
            _tactical_reentry_exit_time(
                _portfolio_from_document(updated["portfolio"]),
                symbol="SNDKUSDT",
                episode_id="episode-1",
            ),
        )

    def test_observed_funding_is_applied_once_at_settlement(self) -> None:
        state, context = self.state_and_context((self.lot(LotRole.CORE),), low="99", high="101")
        state["funding_status"] = FUNDING_PROXY_STATUS
        state["funding_usdt"] = "0"
        state["processed_funding_event_ids"] = []
        context["symbols"]["SNDKUSDT"]["funding_events"] = [
            {
                "event_id": "SNDKUSDT:funding:1",
                "funding_time_ms": int(self.now.timestamp() * 1000),
                "funding_time": self.iso(self.now),
                "available_at": self.iso(self.now + timedelta(minutes=1)),
                "funding_rate": "0.001",
                "settlement_price_proxy": "100",
                "settlement_price_basis": "TEST_PROXY",
                "source": "OKX_PUBLIC_REALIZED_FUNDING_HISTORY",
            }
        ]
        updated, events = _process_bars(state, context, policy=self.policy)
        self.assertEqual("-0.1", updated["funding_usdt"])
        self.assertEqual(["SNDKUSDT:funding:1"], updated["processed_funding_event_ids"])
        self.assertEqual(
            1,
            len([event for event in events if event["event_type"] == "FUNDING_PROXY_ACCRUAL_APPLIED"]),
        )
        updated_again, events_again = _process_bars(updated, context, policy=self.policy)
        self.assertEqual("-0.1", updated_again["funding_usdt"])
        self.assertFalse(
            [event for event in events_again if event["event_type"] == "FUNDING_PROXY_ACCRUAL_APPLIED"]
        )

    def test_net_reward_risk_includes_costs(self) -> None:
        geometry = _entry_geometry(
            side=LotSide.LONG,
            reference=Decimal("100"),
            notional=Decimal("500"),
            stop=Decimal("95"),
            reward_checkpoint=Decimal("112"),
            policy=self.policy,
        )
        self.assertGreater(geometry["net_loss"], Decimal("25"))
        self.assertLess(geometry["net_reward"], Decimal("60"))
        self.assertGreater(geometry["net_reward_risk"], Decimal("1.5"))

    def test_risk_kernel_allows_bounded_probe_and_vetoes_cap_breach(self) -> None:
        portfolio = PortfolioState(
            portfolio_id="risk-test",
            revision=0,
            initial_equity=Decimal("10000"),
            realized_pnl_before_cost=Decimal("0"),
            total_fees=Decimal("0"),
            lots=(),
            fills=(),
        )
        marks = {symbol: Decimal("100") for symbol in SYMBOLS}
        state = {"peak_equity_usdt": "10000"}
        valid = _new_risk_vetoes(
            portfolio=portfolio,
            orders=(),
            state=state,
            marks=marks,
            marked_at=self.now,
            symbol="SNDKUSDT",
            notional=Decimal("100"),
            geometry={
                "net_loss": Decimal("5"),
                "net_reward": Decimal("10"),
                "net_reward_risk": Decimal("2"),
            },
            risk_class="STANDARD",
            policy=self.policy,
        )
        self.assertEqual([], valid)
        breached = _new_risk_vetoes(
            portfolio=portfolio,
            orders=(),
            state=state,
            marks=marks,
            marked_at=self.now,
            symbol="SNDKUSDT",
            notional=Decimal("100"),
            geometry={
                "net_loss": Decimal("150"),
                "net_reward": Decimal("300"),
                "net_reward_risk": Decimal("2"),
            },
            risk_class="STANDARD",
            policy=self.policy,
        )
        self.assertIn("TRADE_RISK_CAP_EXCEEDED", breached)
        self.assertIn("SYMBOL_RISK_CAP_EXCEEDED", breached)

    def test_open_risk_uses_current_mark_stop_cost_and_negative_funding_equity(self) -> None:
        lot = OfflineLot(
            lot_id="risk-current-mark",
            instrument_id="SNDKUSDT",
            side=LotSide.LONG,
            role=LotRole.CORE,
            attribution=Attribution.STRATEGY,
            quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_price=Decimal("110"),
            target_price=None,
            opened_at=self.now - timedelta(hours=1),
            episode_id="episode-risk",
            stage_id="stage-risk",
            geometry_id="geometry-risk",
        )
        portfolio = PortfolioState(
            portfolio_id="risk-current-mark",
            revision=0,
            initial_equity=Decimal("10000"),
            realized_pnl_before_cost=Decimal("0"),
            total_fees=Decimal("0"),
            lots=(lot,),
            fills=(),
        )
        marks = {symbol: Decimal("100") for symbol in SYMBOLS}
        marks["SNDKUSDT"] = Decimal("120")
        total, by_symbol = _current_open_risk(
            portfolio, marks=marks, policy=self.policy
        )
        self.assertGreater(total, Decimal("10"))
        self.assertEqual(total, by_symbol["SNDKUSDT"])

        vetoes = _new_risk_vetoes(
            portfolio=PortfolioState(
                portfolio_id="funding-risk",
                revision=0,
                initial_equity=Decimal("10000"),
                realized_pnl_before_cost=Decimal("0"),
                total_fees=Decimal("0"),
                lots=(),
                fills=(),
            ),
            orders=(),
            state={"peak_equity_usdt": "10000", "funding_usdt": "-1000"},
            marks={symbol: Decimal("100") for symbol in SYMBOLS},
            marked_at=self.now,
            symbol="SNDKUSDT",
            notional=Decimal("100"),
            geometry={
                "net_loss": Decimal("48"),
                "net_reward": Decimal("96"),
                "net_reward_risk": Decimal("2"),
            },
            risk_class="STANDARD",
            policy=self.policy,
        )
        self.assertIn("DRAWDOWN_NO_NEW_RISK", vetoes)
        self.assertIn("TRADE_RISK_CAP_EXCEEDED", vetoes)

    def test_pnl_reconciliation_allows_only_decimal_rounding_dust(self) -> None:
        candidate = Decimal("28.15827679609942350234527755")
        attribution = Decimal("28.15827679609942350234527754")
        self.assertTrue(_pnl_reconciles(candidate, attribution))
        self.assertFalse(_pnl_reconciles(candidate, candidate - Decimal("0.000000001")))

    def valid_symbol_decision(self) -> tuple[dict, dict]:
        evidence_ref = "SNDKUSDT:mark"
        evidence_meta = {
            "evidence_ref": evidence_ref,
            "available_at": self.iso(self.now),
            "source": "PUBLIC_MARK_SNAPSHOT",
            "source_version": "PUBLIC_MARK_SNAPSHOT",
            "dependency_group": "SNDKUSDT:mark:test",
            "limitation": "POINT_SNAPSHOT",
        }
        context = {
            "cycle_index": 1,
            "decision_at": self.iso(self.now),
            "pre_decision_state_digest": "a" * 64,
            "agent_task": {
                "required_sentiment_dimensions": [
                    "price_and_flow_emotion",
                    "leverage_and_crowding",
                    "public_event_narrative",
                    "cross_market_risk_appetite",
                ],
                "theory_source_catalog": [
                    {
                        "source_ref": "CORE_V2_1:16_DYNAMIC_COMPETING_PATHS",
                        "document": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
                    }
                ],
            },
            "market": {
                "symbols": {
                    "SNDKUSDT": {
                        "mark": "100",
                        "evidence_catalog": [evidence_meta],
                    }
                }
            },
            "accepted_strategy_state": {
                "portfolio": {"lots": []},
                "risk": {
                    "symbol_open_risk_usdt": {
                        symbol: "0" for symbol in SYMBOLS
                    }
                },
            },
        }
        dimensions = {
            name: {
                "state": "MIXED",
                "interpretation": "Observed evidence is mixed.",
                "evidence_refs": [evidence_ref],
                "limitations": ["proxy"],
            }
            for name in context["agent_task"]["required_sentiment_dimensions"]
        }
        paths = [
            {
                "path_id": f"episode-1:{path_class.lower()}",
                "path_class": path_class,
                "mechanism_ids": (
                    ["OTHER"]
                    if path_class == "OTHER_OR_UNKNOWN"
                    else
                    ["RANGE"]
                    if path_class == "RANGE_REFORMATION"
                    else ["ABSORPTION_REVERSAL"]
                    if path_class in {"NORMAL_PULLBACK", "EXHAUSTION_OR_FAILURE"}
                    else ["CONTINUATION"]
                ),
                "support_level": "PLAUSIBLE",
                "confidence": "LOW",
                "theory_source_refs": ["CORE_V2_1:16_DYNAMIC_COMPETING_PATHS"],
                "thesis": f"Assess {path_class}.",
                "horizon": "1H_TO_1D",
                "observed_prefix": "Current mark and closed-bar state are observed.",
                "evidence_for_refs": [evidence_ref],
                "evidence_against_refs": [],
                "next_support_observations": ["Next closed-bar confirmation."],
                "soft_contradictions": ["A mixed response would weaken this path."],
                "hard_falsifiers": ["Closed-bar structural invalidation."],
                "expiry_at": self.iso(self.now + timedelta(hours=4)),
                "favorable_path": "Price follows the stated thesis with controlled variance.",
                "adverse_path": "Price violates the structural premise.",
                "normal_path_variation": "A one-bar counter move remains normal noise.",
                "data_gaps": ["liquidations"],
                "what_changed": "Genesis path set created from current evidence.",
                "limitations": ["short window"],
            }
            for path_class in sorted(REQUIRED_PATH_CLASSES)
        ]
        row = {
            "market_conclusion": "The market remains mixed and requires conditional path management.",
            "dynamic_update_from_cycle_index": 0,
            "dynamic_update_summary": "Genesis creates the first falsifiable path set.",
            "analysis_trace": [
                {
                    "trace_id": "trace-observation",
                    "epistemic_type": "OBSERVATION",
                    "statement": "The current mark is visible at the decision boundary.",
                    "evidence_refs": [evidence_ref],
                    "theory_source_refs": ["CORE_V2_1:16_DYNAMIC_COMPETING_PATHS"],
                    "limitation": "One mark is a point snapshot.",
                },
                {
                    "trace_id": "trace-inference",
                    "epistemic_type": "INFERENCE",
                    "statement": "The evidence balance is mixed.",
                    "evidence_refs": [evidence_ref],
                    "theory_source_refs": ["CORE_V2_1:16_DYNAMIC_COMPETING_PATHS"],
                    "limitation": "The inference is not participant identity.",
                },
                {
                    "trace_id": "trace-hypothesis",
                    "epistemic_type": "HYPOTHESIS",
                    "statement": "Four competing paths remain falsifiable.",
                    "evidence_refs": [],
                    "theory_source_refs": ["CORE_V2_1:16_DYNAMIC_COMPETING_PATHS"],
                    "limitation": "Ordinal support is not a calibrated frequency.",
                },
                {
                    "trace_id": "trace-policy",
                    "epistemic_type": "POLICY",
                    "statement": "Wait with an explicit review obligation.",
                    "evidence_refs": [],
                    "theory_source_refs": ["CORE_V2_1:16_DYNAMIC_COMPETING_PATHS"],
                    "limitation": "Waiting has opportunity cost.",
                },
            ],
            "sentiment_assessment": {
                "summary": "Mixed emotion with no decisive edge.",
                "dimensions": dimensions,
                "limitations": ["proxy"],
            },
            "evidence_update": {
                "added_refs": [evidence_ref],
                "changed_premises": [],
                "removed_or_weakened_premises": [],
                "unknowns": ["liquidations"],
                "observation_requests": [],
            },
            "strategic_assessment": {
                "episode_operation": "OPEN",
                "episode_id": "episode-1",
                "strategic_status": "CHALLENGED",
                "primary_direction": "NEUTRAL",
                "primary_horizon": "1D",
                "market_regime": "MIXED",
                "origin_hypothesis": "Genesis watch",
                "paths": paths,
                "evidence_ledger": [
                    {
                        "evidence_id": evidence_ref,
                        "available_at": self.iso(self.now),
                        "perspective_id": "PRICE_STRUCTURE",
                        "dependency_group": "SNDKUSDT:mark:test",
                        "target_ids": sorted(path["path_id"] for path in paths),
                        "direction": "SUPPORT",
                        "ordinal_strength": "WEAK",
                        "quality": "VALID",
                        "source_version": "PUBLIC_MARK_SNAPSHOT",
                    }
                ],
                "operational_lead_path_id": paths[0]["path_id"],
                "runner_up_path_id": paths[1]["path_id"],
                "path_selection_rationale": "The primary path has the best current evidence balance.",
                "ranking_uncertainty": "Evidence remains ordinal and uncalibrated.",
                "support_boundary": "Primitive support is ordinal, non-normalized, and not a probability.",
                "competition_set_status": "UNKNOWN_NO_VALID_COMPETITION_SET",
                "active_primitive_mechanism_ids": [
                    "ABSORPTION_REVERSAL",
                    "CONTINUATION",
                    "OTHER",
                    "RANGE",
                ],
                "switch_conditions": ["Independent closed-bar evidence favors the runner-up."],
                "hard_invalidators": [],
                "soft_challenges": ["mixed evidence"],
                "pending_observations": ["next closed bar"],
                "review_by": self.iso(self.now + timedelta(hours=1)),
                "invalidation_basis": None,
            },
            "action_comparison": [
                {
                    "action_class": action_class,
                    "feasible": action_class == "WAIT",
                    "relative_utility": "LOW" if action_class != "WAIT" else "HIGHEST",
                    "reason": "Compared under current evidence.",
                    "path_conditioned_outcomes": [
                        {
                            "path_id": path_id,
                            "position_effect": {
                                "HOLD": "MAINTAIN_EXPOSURE",
                                "OPEN": "INCREASE_EXPOSURE",
                                "ADD": "INCREASE_EXPOSURE",
                                "REDUCE": "DECREASE_EXPOSURE",
                                "PARTIAL_TAKE_PROFIT": "DECREASE_EXPOSURE",
                                "EXIT": "EXIT_SCOPE_EXPOSURE",
                                "REENTER": "RESTORE_EXPOSURE",
                                "WAIT": "NO_EXPOSURE_CHANGE",
                            }[action_class],
                            "compatibility": "CONDITIONAL",
                            "path_realization": f"{action_class} responds to {path_id} realization.",
                            "failure_process": f"{action_class} fails if {path_id} reverses its stated prefix.",
                            "opportunity_cost": f"{action_class} forgoes the alternative to {path_id}.",
                            "cost_and_risk": f"{action_class} cost and risk are specific to {path_id}.",
                        }
                        for path_id in {
                            paths[0]["path_id"],
                            paths[1]["path_id"],
                            next(
                                path["path_id"]
                                for path in paths
                                if path["path_class"] == "OTHER_OR_UNKNOWN"
                            ),
                        }
                    ],
                    "hard_vetoes": (
                        []
                        if action_class == "WAIT"
                        else ["NO_OPEN_RISK_AUTHORITY_IN_TEST"]
                    ),
                }
                for action_class in sorted(COMPARISON_CLASSES)
            ],
            "selected_actions": [
                {
                    "action_id": "wait-1",
                    "action_type": "WAIT",
                    "path_id": paths[0]["path_id"],
                    "reason": "The relative utility of immediate risk is lower.",
                    "evidence_refs": [evidence_ref],
                    "wait_basis": "RELATIVE_UTILITY",
                    "required_observations": ["next closed bar"],
                    "review_by": self.iso(self.now + timedelta(hours=1)),
                }
            ],
        }
        self.bind_position_truth(context, row)
        return context, row

    @staticmethod
    def bind_position_truth(context: dict, row: dict) -> None:
        truth = _action_position_truth(context, symbol="SNDKUSDT")
        for card in row["action_comparison"]:
            for outcome in card["path_conditioned_outcomes"]:
                outcome["position_truth_digest"] = truth["position_truth_digest"]

    def test_wait_requires_real_obligation_and_sentiment_is_mandatory(self) -> None:
        context, row = self.valid_symbol_decision()
        result = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        self.assertEqual("WAIT", result["selected_actions"][0]["action_type"])
        row["selected_actions"][0]["required_observations"] = []
        with self.assertRaisesRegex(SingleAgentResearchError, "WAIT_OBLIGATION_INVALID"):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

    def test_action_counterfactual_rejects_stale_numeric_position_prose(self) -> None:
        context, row = self.valid_symbol_decision()
        outcome = row["action_comparison"][0]["path_conditioned_outcomes"][0]
        outcome["path_realization"] = (
            "当前为 CORE 1，mark 名义 100 USDT、open risk 10 USDT；继续比较路径。"
        )
        with self.assertRaisesRegex(
            SingleAgentResearchError,
            "ACTION_COUNTERFACTUAL_UNSTRUCTURED_POSITION_TRUTH",
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

    def test_action_counterfactual_digest_must_bind_current_pre_state(self) -> None:
        context, row = self.valid_symbol_decision()
        row["action_comparison"][0]["path_conditioned_outcomes"][0][
            "position_truth_digest"
        ] = "f" * 64
        with self.assertRaisesRegex(
            SingleAgentResearchError, "ACTION_PATH_COUNTERFACTUAL_INVALID"
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

    def test_dynamic_update_rejects_current_cycle_as_prior_label(self) -> None:
        context, row = self.valid_symbol_decision()
        context["cycle_index"] = 17
        row["dynamic_update_from_cycle_index"] = 16
        row["dynamic_update_summary"] = (
            "Cycle 17 后的新证据改变了上一 accepted state。"
        )
        self.bind_position_truth(context, row)
        with self.assertRaisesRegex(
            SingleAgentResearchError,
            "DYNAMIC_UPDATE_PRIOR_CYCLE_LABEL_CONFLICT",
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

        row["dynamic_update_summary"] = (
            "Cycle 16 后的新证据改变了上一 accepted state。"
        )
        result = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        self.assertEqual(16, result["dynamic_update_from_cycle_index"])

    def test_cross_market_observation_has_a_citable_evidence_ref(self) -> None:
        context, row = self.valid_symbol_decision()
        cross_ref = "cross_market:six-symbol:relative-strength"
        context["market"]["cross_market"] = {
            "evidence_ref": cross_ref,
            "available_at": self.iso(self.now),
            "dependency_group": "cross-market:test",
            "source_version": "CROSS_MARKET_RELATIVE_STRENGTH_V1",
            "rows": [],
        }
        row["sentiment_assessment"]["dimensions"]["cross_market_risk_appetite"][
            "evidence_refs"
        ] = [cross_ref]
        result = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        self.assertEqual(
            [cross_ref],
            result["sentiment_assessment"]["dimensions"][
                "cross_market_risk_appetite"
            ]["evidence_refs"],
        )

    def test_hold_uses_episode_review_obligation_without_fake_wait(self) -> None:
        context, row = self.valid_symbol_decision()
        context["accepted_strategy_state"]["portfolio"]["lots"] = [
            {"instrument_id": "SNDKUSDT", "remaining_quantity": "1"}
        ]
        self.bind_position_truth(context, row)
        for card in row["action_comparison"]:
            if card["action_class"] in {
                "HOLD",
                "REDUCE",
                "PARTIAL_TAKE_PROFIT",
                "EXIT",
            }:
                card["feasible"] = True
                card["hard_vetoes"] = []
        row["selected_actions"] = [
            {
                "action_id": "hold-1",
                "action_type": "HOLD",
                "path_id": row["strategic_assessment"]["operational_lead_path_id"],
                "reason": "Keep protected exposure while the episode remains active.",
                "evidence_refs": ["SNDKUSDT:mark"],
            }
        ]
        result = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        self.assertEqual("HOLD", result["selected_actions"][0]["action_type"])

    def test_rfc_news_timestamp_is_visible_only_after_publication(self) -> None:
        news = {
            "queries": {
                "SNDKUSDT": {
                    "items": [
                        {
                            "published_at": "Wed, 29 Jul 2026 15:37:26 GMT",
                            "source": "example",
                            "title": "Public headline",
                            "url": "https://example.invalid/item",
                        }
                    ]
                }
            }
        }
        before = _news_rows(news, "SNDKUSDT", "2026-07-29T15:37:25Z")
        after = _news_rows(news, "SNDKUSDT", "2026-07-29T15:37:26Z")
        self.assertEqual([], before)
        self.assertEqual(1, len(after))
        self.assertEqual("2026-07-29T15:37:26.000Z", after[0]["published_at"])

    def test_maximum_drawdown_includes_genesis_equity(self) -> None:
        curve = [
            {"equity_before_unknown_funding_usdt": "9900"},
            {"equity_before_unknown_funding_usdt": "9950"},
            {"equity_before_unknown_funding_usdt": "9925"},
        ]
        result = _maximum_drawdown(curve, initial_equity=Decimal("10000"))
        self.assertEqual(Decimal("0.01"), result)

    def test_agent_context_exposes_exact_genesis_episode_literal(self) -> None:
        contract = _agent_decision_contract()
        self.assertEqual("1.3.0", contract["top_level"]["schema_version"])
        transition = contract["episode_transition"]
        self.assertIn("OPEN", transition["allowed_operations"])
        self.assertNotIn("CREATE", transition["allowed_operations"])
        self.assertIn("OPEN", transition["genesis_without_previous_episode"])
        self.assertEqual(
            ["ACTIVE", "CHALLENGED"],
            transition["operation_status_pairs"]["OPEN"],
        )
        self.assertEqual(
            sorted(COMPARISON_CLASSES),
            contract["action_comparison"]["required_classes"],
        )
        self.assertEqual(
            AGENT_JUDGMENT_EVIDENCE_LABEL,
            contract["required_evidence_label"],
        )
        self.assertIn(
            "forbidden",
            contract["path_card"]["numeric_probability_rule"],
        )
        self.assertIn("REENTER_TACTICAL", contract["allowed_action_types"])

    def test_timeframe_role_profiles_are_symbol_and_market_specific(self) -> None:
        sndk = _timeframe_role_profile(
            "SNDKUSDT", "CONTINUOUS_DERIVATIVE_WITH_EQUITY_REFERENCE_LIMITATION"
        )
        btc = _timeframe_role_profile(
            "BTCUSDT", "CONTINUOUS_CRYPTO_DERIVATIVE"
        )
        self.assertNotEqual(sndk["profile_id"], btc["profile_id"])
        self.assertIn("SESSION_GAP_CAVEAT", sndk["roles"]["1d"])
        self.assertIn("SYMBOL_SPECIFIC", btc["roles"]["4h"])
        self.assertIn("NOT_UNIVERSAL", sndk["boundary"])

    def test_numeric_path_probability_is_rejected_without_partition_authority(self) -> None:
        context, row = self.valid_symbol_decision()
        row["strategic_assessment"]["paths"][0]["probability_pct"] = "20"
        with self.assertRaisesRegex(
            SingleAgentResearchError, "PATH_NUMERIC_PROBABILITY_UNAUTHORIZED"
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

    def test_dependency_group_uses_one_maximum_ordinal_increment(self) -> None:
        context, row = self.valid_symbol_decision()
        second_ref = "SNDKUSDT:mark-derived-wording"
        context["market"]["symbols"]["SNDKUSDT"]["evidence_catalog"].append(
            {
                "evidence_ref": second_ref,
                "available_at": self.iso(self.now),
                "source": "PUBLIC_MARK_SNAPSHOT",
                "source_version": "PUBLIC_MARK_SNAPSHOT",
                "dependency_group": "SNDKUSDT:mark:test",
                "limitation": "SAME_UNDERLYING_INCREMENT",
            }
        )
        target = row["strategic_assessment"]["operational_lead_path_id"]
        row["strategic_assessment"]["evidence_ledger"].append(
            {
                "evidence_id": second_ref,
                "available_at": self.iso(self.now),
                "perspective_id": "ORDER_FLOW",
                "dependency_group": "SNDKUSDT:mark:test",
                "target_ids": [target],
                "direction": "SUPPORT",
                "ordinal_strength": "STRONG",
                "quality": "VALID",
                "source_version": "PUBLIC_MARK_SNAPSHOT",
            }
        )
        result = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        aggregation = result["strategic_assessment"]["evidence_aggregation"][target]
        self.assertEqual(1, aggregation["dependency_group_count"])
        self.assertEqual([second_ref], aggregation["selected_evidence_ids"])
        self.assertEqual(3, aggregation["net_ordinal_delta"])

    def test_same_evidence_increment_cannot_be_counted_again_next_cycle(self) -> None:
        context, row = self.valid_symbol_decision()
        first = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        previous = {
            "episode_id": "episode-1",
            "strategic_status": "CHALLENGED",
            "origin_hypothesis": "Genesis watch",
            "hard_invalidators": [],
            "paths": first["strategic_assessment"]["paths"],
            "observation_requests": [],
            "consumed_evidence_keys": first["strategic_assessment"][
                "consumed_evidence_keys"
            ],
        }
        row["strategic_assessment"]["episode_operation"] = "UPDATE"
        with self.assertRaisesRegex(
            SingleAgentResearchError, "EVIDENCE_INCREMENT_REUSED"
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=previous,
            )

    def test_exit_cannot_call_long_continuation_favorable(self) -> None:
        context, row = self.valid_symbol_decision()
        context["accepted_strategy_state"]["portfolio"]["lots"] = [
            {
                "instrument_id": "SNDKUSDT",
                "remaining_quantity": "1",
            }
        ]
        self.bind_position_truth(context, row)
        row["strategic_assessment"]["primary_direction"] = "LONG"
        for card in row["action_comparison"]:
            if card["action_class"] in {
                "HOLD",
                "REDUCE",
                "PARTIAL_TAKE_PROFIT",
                "EXIT",
            }:
                card["feasible"] = True
                card["hard_vetoes"] = []
        prior_lead = row["strategic_assessment"]["operational_lead_path_id"]
        continuation_id = next(
            path["path_id"]
            for path in row["strategic_assessment"]["paths"]
            if path["path_class"] == "TREND_CONTINUATION"
        )
        row["strategic_assessment"]["operational_lead_path_id"] = continuation_id
        for card in row["action_comparison"]:
            for value in card["path_conditioned_outcomes"]:
                if value["path_id"] == prior_lead:
                    value["path_id"] = continuation_id
        exit_card = next(
            card for card in row["action_comparison"] if card["action_class"] == "EXIT"
        )
        outcome = next(
            value
            for value in exit_card["path_conditioned_outcomes"]
            if value["path_id"] == continuation_id
        )
        outcome["compatibility"] = "FAVORS_ACTION"
        with self.assertRaisesRegex(
            SingleAgentResearchError, "ACTION_PATH_SEMANTIC_INVERSION"
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

    def test_open_position_partial_profit_cannot_be_declared_infeasible(self) -> None:
        context, row = self.valid_symbol_decision()
        context["accepted_strategy_state"]["portfolio"]["lots"] = [
            {"instrument_id": "SNDKUSDT", "remaining_quantity": "1"}
        ]
        self.bind_position_truth(context, row)
        for card in row["action_comparison"]:
            if card["action_class"] in {
                "HOLD",
                "REDUCE",
                "PARTIAL_TAKE_PROFIT",
                "EXIT",
            }:
                card["feasible"] = True
                card["hard_vetoes"] = []
        partial = next(
            card
            for card in row["action_comparison"]
            if card["action_class"] == "PARTIAL_TAKE_PROFIT"
        )
        partial["feasible"] = False
        partial["hard_vetoes"] = ["GENERIC_CONSERVATISM"]
        with self.assertRaisesRegex(
            SingleAgentResearchError, "ACTION_COMPARISON_POSITION_INCONSISTENT"
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

    def test_required_paths_cannot_be_replaced_by_optional_story(self) -> None:
        context, row = self.valid_symbol_decision()
        row["strategic_assessment"]["paths"] = row["strategic_assessment"]["paths"][1:]
        with self.assertRaisesRegex(SingleAgentResearchError, "COMPETING_PATH_SET_INCOMPLETE"):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=None,
            )

    def test_undeclared_genesis_thesis_cannot_self_prove_invalidation(self) -> None:
        context, row = self.valid_symbol_decision()
        row["strategic_assessment"]["episode_operation"] = "INVALIDATE"
        row["strategic_assessment"]["strategic_status"] = "INVALIDATED"
        previous = {
            "episode_id": "episode-1",
            "strategic_status": "CHALLENGED",
            "origin_hypothesis": "EXOGENOUS_INITIAL_POSITION_THESIS_UNDECLARED",
            "hard_invalidators": ["GENESIS_THESIS_UNDECLARED"],
            "paths": [],
        }
        with self.assertRaisesRegex(
            SingleAgentResearchError,
            "GENESIS_UNDECLARED_THESIS_NOT_HARD_FALSIFIER",
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=previous,
            )

    def test_optional_liquidity_path_is_allowed_without_replacing_core_paths(self) -> None:
        context, row = self.valid_symbol_decision()
        extra = dict(row["strategic_assessment"]["paths"][0])
        extra.update(
            {
                "path_id": "episode-1:liquidity_stress",
                "path_class": "LIQUIDITY_STRESS",
                "mechanism_ids": ["LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM"],
                "thesis": "A liquidity stress path remains separately testable.",
            }
        )
        row["strategic_assessment"]["paths"].append(extra)
        row["strategic_assessment"]["evidence_ledger"][0]["target_ids"] = sorted(
            [
                *row["strategic_assessment"]["evidence_ledger"][0]["target_ids"],
                extra["path_id"],
            ]
        )
        row["strategic_assessment"]["active_primitive_mechanism_ids"] = sorted(
            [
                *row["strategic_assessment"]["active_primitive_mechanism_ids"],
                "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM",
            ]
        )
        result = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        self.assertIn(
            "LIQUIDITY_STRESS",
            {item["path_class"] for item in result["strategic_assessment"]["paths"]},
        )

    def test_pending_observation_request_must_be_resolved_or_carried(self) -> None:
        context, row = self.valid_symbol_decision()
        primary = row["strategic_assessment"]["operational_lead_path_id"]
        row["evidence_update"]["observation_requests"] = [
            {
                "request_id": "request-1",
                "observation": "Independent liquidation proxy",
                "purpose_path_ids": [primary],
                "timeframe": "1h",
                "premise": "Distinguish continuation from forced deleveraging.",
                "source_preference": "PUBLIC_PRIMARY_SOURCE",
                "cost_tier": "LOW",
                "status": "PENDING",
                "evidence_refs": [],
                "resolution_note": "Not present in the current frozen context.",
                "limitation": "Public coverage may remain incomplete.",
            }
        ]
        first = _validate_symbol_decision(
            row,
            symbol="SNDKUSDT",
            agent_context=context,
            previous_episode=None,
        )
        previous = {
            "episode_id": "episode-1",
            "strategic_status": "CHALLENGED",
            "origin_hypothesis": "Genesis watch",
            "hard_invalidators": [],
            "paths": first["strategic_assessment"]["paths"],
            "observation_requests": first["evidence_update"]["observation_requests"],
        }
        row["strategic_assessment"]["episode_operation"] = "UPDATE"
        row["evidence_update"]["observation_requests"] = []
        with self.assertRaisesRegex(
            SingleAgentResearchError,
            "PENDING_OBSERVATION_REQUEST_DROPPED",
        ):
            _validate_symbol_decision(
                row,
                symbol="SNDKUSDT",
                agent_context=context,
                previous_episode=previous,
            )


if __name__ == "__main__":
    unittest.main()
