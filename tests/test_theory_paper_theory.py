from __future__ import annotations

import copy
import unittest

from trade_system.theory_paper.theory import (
    PHI_IDS,
    _measurement_snapshot,
    build_cycle_analysis,
    build_decision_template,
    build_method_candidates,
    score_method_practice,
    score_theory_integrity,
    validate_decision,
)


OBSERVED_AT = "2026-07-30T00:00:00Z"


def technical_frame(
    trend: str,
    *,
    price: float = 100.0,
    support: float = 96.0,
    resistance: float = 110.0,
) -> dict:
    return {
        "status": "OBSERVED_CLOSED_BARS",
        "price": price,
        "change_1_bar_pct": 0.7,
        "change_6_bar_pct": 2.1,
        "ema20": 99.0,
        "ema50": 97.0,
        "ema200": 90.0,
        "rsi14": 61.0,
        "atr14": 2.0,
        "atr_pct": 2.0,
        "adx14": 27.0,
        "efficiency_ratio10": 0.6,
        "macd_histogram": 0.4,
        "bollinger_middle": 99.0,
        "bollinger_upper": 104.0,
        "bollinger_lower": 94.0,
        "bollinger_bandwidth": 0.1010101,
        "bollinger_percent_b": 0.6,
        "relative_volume20": 1.1,
        "trend_state": trend,
        "supports": [support, support - 5.0],
        "resistances": [resistance, resistance + 5.0],
    }


def market_snapshot(*, sparse: bool = False) -> dict:
    if sparse:
        measures = {"price": 100.0, "timeframes": {}}
        quality = {
            "coverage_ratio": 0.1,
            "error_count": 14,
            "errors": {"depth": "unavailable"},
            "strict_R_available": False,
            "liquidation_zero_certainty": False,
        }
    else:
        measures = {
            "price": 100.0,
            "directional_pressure_D": {
                "recent_trades": {
                    "status": "OBSERVED_RECENT_WINDOW",
                    "signed_taker_imbalance": 0.22,
                    "vwap": 99.5,
                },
                "hourly_taker_buy_sell_ratio": 1.3,
            },
            "leverage_L": {
                "open_interest_contracts": 12345.0,
                "open_interest_value_1h_change_pct": 1.2,
            },
            "crowding_C": {
                "funding_rate": 0.0001,
                "basis_bps": 2.0,
                "global_account_long_short_ratio": 1.2,
                "top_position_long_short_ratio": 1.1,
            },
            "forced_deleveraging_F": {
                "status": "OBSERVED_RECENT_API_WINDOW",
                "event_count": 2,
                "notional": 5000.0,
            },
            "liquidity_resilience_R": {
                "status": "OBSERVED_SNAPSHOT_PROXY",
                "spread_bps": 1.0,
                "top20_imbalance": 0.1,
                "buy_1000_impact_bps": 1.2,
                "sell_1000_impact_bps": 1.3,
                "strict_resilience_available": False,
            },
            "timeframes": {
                "1w": technical_frame("UP"),
                "1d": technical_frame("UP"),
                "4h": technical_frame("UP"),
                "1h": technical_frame("UP"),
                "15m": technical_frame("UP"),
            },
        }
        quality = {
            "coverage_ratio": 1.0,
            "error_count": 0,
            "errors": {},
            "strict_R_available": False,
            "liquidation_zero_certainty": False,
        }
    symbol = {
        "symbol": "BTCUSDT",
        "venue": "BINANCE_USDM_PUBLIC",
        "observed_at": OBSERVED_AT,
        "measures": measures,
        "data_quality": quality,
        "raw_digest": "a" * 64,
    }
    return {
        "schema_version": "theory-paper-market-snapshot.v1",
        "observed_at": OBSERVED_AT,
        "symbols": [symbol],
        "failures": {},
        "market_snapshot_digest": "b" * 64,
    }


def completed_decision(analysis: dict) -> dict:
    decision = build_decision_template(analysis)
    decision.update(
        {
            "executive_summary_zh": "测试周期只验证纸面决策契约与审计边界。",
            "portfolio_rationale_zh": "不新增真实风险，只保留可证伪的纸面观察。",
            "news_evidence": [],
            "method_observations": ["本轮使用离线固定数据，不作市场因果声明。"],
            "agent_identity": {
                "agent_role": "PAPER_RESEARCH_DECISION_AGENT",
                "model_identity": "OFFLINE_UNIT_TEST_MODEL",
                "prompt_binding_sha256": analysis["decision_authority"][
                    "automation_prompt_sha256"
                ],
            },
        }
    )
    row = decision["symbol_decisions"][0]
    fact_refs = copy.deepcopy(row["available_fact_refs"][:2])
    inference_refs = copy.deepcopy(row["available_inference_refs"][:2])
    row.update(
        {
            "action": "ABSTAIN",
            "selected_phi_id": "PHI_UPWARD_CONTINUATION",
            "alternative_phi_ids": ["PHI_RANGE", "PHI_OTHER_UNKNOWN"],
            "analysis_narrative_zh": "多周期结构用于验证决策字段，不代表实盘预测。",
            "behavior_hypotheses_zh": "主动成交仅作为行为代理，不识别具体参与者。",
            "future_force_path_zh": "若结构延续则观察买方跟随，否则等待否证。",
            "thesis": "Continuation remains a testable paper hypothesis.",
            "fact_refs": fact_refs,
            "inference_refs": inference_refs,
            "hard_falsifier": "A closed 4h down structure after the decision.",
            "support_predicate": {
                "observable_id": "4H_DIRECTION",
                "operator": "EQ",
                "value": "UP",
            },
            "falsifier_predicate": {
                "observable_id": "4H_DIRECTION",
                "operator": "EQ",
                "value": "DOWN",
            },
            "next_observations": ["next closed 1h and 4h structure"],
            "expiry_at": "2026-07-30T08:00:00Z",
            "geometry_candidate_id": "UNKNOWN",
            "abstention_reason_code": "WAIT_FOR_ENTRY_GEOMETRY",
            "market_actionability": "ACTIONABLE",
            "active_probe_plan": False,
        }
    )
    return decision


def news_snapshot() -> dict:
    return {
        "schema_version": "theory-paper-news-metadata.v1",
        "observed_at": OBSERVED_AT,
        "queries": {
            "BTCUSDT": {
                "query": "BTC test context",
                "source": "OFFLINE_TEST_FIXTURE",
                "items": [
                    {
                        "title": "Frozen public discovery headline",
                        "url": "https://news.example.invalid/frozen-btc",
                        "published_at": "Wed, 29 Jul 2026 23:30:00 GMT",
                        "source": "Synthetic discovery source",
                    }
                ],
                "error": None,
            }
        },
        "interpretation_boundary": (
            "HEADLINES_ARE_CONTEXT_FACTS_NOT_CAUSAL_OR_SENTIMENT_TRUTH"
        ),
    }


def configure_open_long(
    decision: dict,
    analysis: dict,
    *,
    execution_intent: str = "EXECUTE_NOW",
    include_low_level: bool = True,
    probe: bool = False,
    notional_usdt: float = 100.0,
) -> dict:
    geometry = next(
        item
        for item in analysis["symbols"][0]["action_geometry_candidates"]
        if item["status"] == "RESEARCH_READY" and item["side"] == "LONG"
    )
    entry = (geometry["entry_zone"]["low"] + geometry["entry_zone"]["high"]) / 2.0
    high = decision["symbol_decisions"][0]
    high.update(
        {
            "action": "OPEN_LONG",
            "execution_intent": execution_intent,
            "geometry_candidate_id": geometry["geometry_candidate_id"],
            "order": {
                "order_type": "LIMIT",
                "side": "BUY",
                "limit_price": entry,
                "notional_usdt": notional_usdt,
                "stop_loss": geometry["stop_loss"],
                "take_profit": geometry["take_profit"],
            },
            "abstention_reason_code": "UNKNOWN",
            "market_actionability": "ACTIONABLE",
            "active_probe_plan": probe,
        }
    )
    low = {
        "type": "PLACE_LIMIT",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "notional_usdt": notional_usdt,
        "limit_price": entry,
        "stop_price": geometry["stop_loss"],
        "target_price": geometry["take_profit"],
        "geometry_candidate_id": geometry["geometry_candidate_id"],
        "hypothesis_id": "PHI_UPWARD_CONTINUATION",
        "risk_authorization": {
            "approved": True,
            "authority": "AGENT_DECISION",
            "reason": "bounded paper theory action",
        },
        "probe": probe,
    }
    if include_low_level:
        decision["portfolio_actions"].append(copy.deepcopy(low))
    return low


class TheoryPaperTheoryTests(unittest.TestCase):
    def test_existing_bollinger_and_recent_vwap_are_visible_to_analysis(self) -> None:
        snapshot = _measurement_snapshot(market_snapshot()["symbols"][0])
        self.assertEqual(
            snapshot["axes"]["D"]["observations"]["recent_window_vwap"],
            99.5,
        )
        technical = snapshot["axes"]["K"]["timeframes"]["1h"]["observations"]
        self.assertEqual(technical["bollinger_middle"], 99.0)
        self.assertEqual(technical["bollinger_bandwidth"], 0.1010101)
        self.assertEqual(technical["bollinger_percent_b"], 0.6)

    def test_complete_chain_is_experimental_paper_only_and_non_probability(self) -> None:
        analysis = build_cycle_analysis(
            market_snapshot(),
            portfolio_state={
                "valid_hours_without_strategy_fill": 7,
                "lots": [
                    {
                        "lot_id": "lot-1",
                        "status": "OPEN",
                        "stop_price": None,
                        "target_price": None,
                    }
                ],
                "orders": [{"order_id": "order-1", "state": "REVIEW_REQUIRED"}],
                "chaos": {"schedule": [{"secret": "must-not-copy"}]},
            },
            cycle_id="cycle-001",
        )
        self.assertEqual("EXPERIMENTAL", analysis["method_status"])
        self.assertEqual("PAPER_ONLY", analysis["execution_scope"])
        symbol = analysis["symbols"][0]
        self.assertEqual(
            {"D", "L", "C", "F", "R", "K"},
            set(symbol["measurement_snapshot"]["axes"]),
        )
        self.assertEqual(
            list(PHI_IDS),
            symbol["phi_competition"]["finite_registry"],
        )
        self.assertEqual(
            "QUALITATIVE_ORDINAL_NON_NORMALIZED",
            symbol["phi_competition"]["competition_mode"],
        )
        for hypothesis in symbol["phi_competition"]["hypotheses"]:
            self.assertFalse(hypothesis["is_probability"])
            self.assertEqual(
                "UNAVAILABLE_NOT_CALIBRATED",
                hypothesis["probability_status"],
            )
            self.assertTrue(hypothesis["hard_falsifiers"])
        for actor in symbol["actor_behavior_hypotheses"]["items"]:
            self.assertEqual("NOT_IDENTIFIED", actor["identity_status"])
        self.assertTrue(
            any(
                item["status"] == "RESEARCH_READY"
                for item in symbol["action_geometry_candidates"]
            )
        )
        self.assertTrue(analysis["theory_integrity_score"]["passing"])
        self.assertFalse(analysis["theory_integrity_score"]["pnl_in_score"])
        self.assertEqual(7, analysis["portfolio_context"]["valid_hours_without_strategy_fill"])
        self.assertEqual(["lot-1"], analysis["portfolio_context"]["unprotected_lot_ids"])
        self.assertEqual(["order-1"], analysis["portfolio_context"]["review_required_order_ids"])
        self.assertNotIn("chaos", analysis["portfolio_context"])

    def test_unknown_inputs_remain_unknown_and_do_not_create_geometry(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(sparse=True), cycle_id="cycle-unknown")
        symbol = analysis["symbols"][0]
        measurement = symbol["measurement_snapshot"]
        for axis in ("D", "L", "C", "F", "R"):
            self.assertEqual("UNKNOWN", measurement["axes"][axis]["status"])
        for role in symbol["multi_scale_state_belief"]["role_states"]:
            self.assertEqual("UNKNOWN", role["direction_state"])
            self.assertEqual("UNKNOWN", role["momentum_state"])
        self.assertEqual("UNKNOWN", symbol["structural_position"]["location_stage"])
        self.assertEqual(
            "REJECTED_OR_UNKNOWN_GEOMETRY",
            symbol["action_geometry_candidates"][0]["status"],
        )
        phis = {
            item["phi_id"]: item["support_ordinal"]
            for item in symbol["phi_competition"]["hypotheses"]
        }
        self.assertEqual("UNKNOWN", phis["PHI_UPWARD_CONTINUATION"])
        self.assertNotEqual("STRONG", phis["PHI_ABSORPTION_REVERSAL"])
        self.assertEqual("UNKNOWN", symbol["actor_behavior_hypotheses"]["status"])
        self.assertFalse(analysis["theory_integrity_score"]["passing"])
        self.assertLess(analysis["theory_integrity_score"]["score"], 80)
        self.assertTrue(
            any(
                "COVERAGE_PARTIAL" in item
                for item in analysis["theory_integrity_score"]["deductions"]
            )
        )

    def test_decision_validator_separates_symbol_reasoning_and_portfolio_actions(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(), cycle_id="cycle-decision")
        decision = completed_decision(analysis)
        geometry = next(
            item
            for item in analysis["symbols"][0]["action_geometry_candidates"]
            if item["status"] == "RESEARCH_READY" and item["side"] == "LONG"
        )
        entry = (
            geometry["entry_zone"]["low"] + geometry["entry_zone"]["high"]
        ) / 2.0
        decision["symbol_decisions"][0].update(
            {
                "action": "OPEN_LONG",
                "execution_intent": "EXECUTE_NOW",
                "geometry_candidate_id": geometry["geometry_candidate_id"],
                "order": {
                    "order_type": "LIMIT",
                    "side": "BUY",
                    "limit_price": entry,
                    "notional_usdt": 100.0,
                    "stop_loss": geometry["stop_loss"],
                    "take_profit": geometry["take_profit"],
                },
                "abstention_reason_code": "UNKNOWN",
                "market_actionability": "ACTIONABLE",
                "active_probe_plan": False,
            }
        )
        decision["portfolio_actions"] = [
            {
                "type": "UPDATE_PROTECTION",
                "symbol": "BTCUSDT",
                "lot_id": "lot-1",
                "stop_price": 95.0,
                "target_price": 110.0,
            },
            {
                "type": "MARKET",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "notional_usdt": 100.0,
                "limit_price": entry,
                "stop_price": geometry["stop_loss"],
                "target_price": geometry["take_profit"],
                "geometry_candidate_id": geometry["geometry_candidate_id"],
                "hypothesis_id": "PHI_UPWARD_CONTINUATION",
                "risk_authorization": {
                    "approved": True,
                    "authority": "AGENT_DECISION",
                    "reason": "bounded paper probe",
                },
            },
        ]
        decision["portfolio_actions"][1]["type"] = "PLACE_LIMIT"
        result = validate_decision(decision, analysis)
        self.assertTrue(result["valid"], result)
        normalized = result["normalized_decision"]
        self.assertEqual(2, len(normalized["actions"]))
        self.assertEqual("PLACE_LIMIT", normalized["actions"][1]["type"])
        self.assertEqual(1, len(normalized["symbol_decisions"]))

        invalid = copy.deepcopy(decision)
        invalid["portfolio_actions"][1]["live"] = True
        invalid["portfolio_actions"][1]["risk_authorization"]["approved"] = False
        rejected = validate_decision(invalid, analysis)
        self.assertFalse(rejected["valid"])
        self.assertTrue(
            any("LIVE_OR_CREDENTIAL_FIELD_FORBIDDEN" in error for error in rejected["errors"])
        )
        self.assertTrue(
            any("EXPLICIT_RISK_AUTHORIZATION_REQUIRED" in error for error in rejected["errors"])
        )

        bypass = completed_decision(analysis)
        bypass["portfolio_actions"] = [copy.deepcopy(decision["portfolio_actions"][1])]
        rejected_bypass = validate_decision(bypass, analysis)
        self.assertFalse(rejected_bypass["valid"])
        self.assertTrue(
            any(
                "NEW_RISK_CONTRADICTS_SYMBOL_ACTION" in error
                for error in rejected_bypass["errors"]
            )
        )

    def test_decision_at_is_required_bound_and_normalized_from_analysis(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(), cycle_id="cycle-time")
        valid = validate_decision(completed_decision(analysis), analysis)
        self.assertTrue(valid["valid"], valid)
        self.assertEqual(
            analysis["decision_at"],
            valid["normalized_decision"]["decision_at"],
        )

        missing = completed_decision(analysis)
        missing.pop("decision_at")
        missing_result = validate_decision(missing, analysis)
        self.assertIn("DECISION_AT_REQUIRED", missing_result["errors"])

        mismatch = completed_decision(analysis)
        mismatch["decision_at"] = "2026-07-30T00:01:00Z"
        mismatch_result = validate_decision(mismatch, analysis)
        self.assertIn("DECISION_AT_MISMATCH", mismatch_result["errors"])

        invalid_analysis = copy.deepcopy(analysis)
        invalid_analysis.pop("decision_at")
        invalid_result = validate_decision(
            completed_decision(analysis),
            invalid_analysis,
        )
        self.assertIn("ANALYSIS_DECISION_AT_INVALID", invalid_result["errors"])

    def test_agent_identity_is_bound_to_frozen_automation_prompt(self) -> None:
        authority = {
            "automation_prompt_sha256": "1" * 64,
            "path": "automation/theory-paper-hourly-v1",
            "theory_authority_digest": "2" * 64,
        }
        analysis = build_cycle_analysis(
            market_snapshot(),
            config={"decision_authority": authority},
            cycle_id="cycle-agent-identity",
        )
        self.assertEqual(authority, analysis["decision_authority"])
        template = build_decision_template(analysis)
        self.assertEqual(
            authority["automation_prompt_sha256"],
            template["agent_identity"]["prompt_binding_sha256"],
        )
        decision = completed_decision(analysis)
        self.assertTrue(validate_decision(decision, analysis)["valid"])

        wrong_prompt = copy.deepcopy(decision)
        wrong_prompt["agent_identity"]["prompt_binding_sha256"] = "3" * 64
        self.assertIn(
            "AGENT_PROMPT_BINDING_MISMATCH",
            validate_decision(wrong_prompt, analysis)["errors"],
        )
        missing_model = copy.deepcopy(decision)
        missing_model["agent_identity"]["model_identity"] = ""
        self.assertIn(
            "AGENT_IDENTITY_REQUIRED",
            validate_decision(missing_model, analysis)["errors"],
        )

    def test_news_evidence_is_temporal_typed_and_bound_to_frozen_discovery(self) -> None:
        analysis = build_cycle_analysis(
            market_snapshot(),
            news_snapshot(),
            cycle_id="cycle-news",
        )
        frozen = analysis["symbols"][0]["news_context"]["headline_metadata"][0]
        decision = completed_decision(analysis)
        public_evidence = {
            "symbol": "BTCUSDT",
            "source_url": frozen["url"],
            "published_at": frozen["published_at"],
            "claim_zh": "该标题只作为冻结的公开发现元数据，不证明因果。",
            "authority": "PUBLIC_DISCOVERY_METADATA",
            "causal_status": "CONTEXT_ONLY",
            "evidence_origin": "FROZEN_PUBLIC_DISCOVERY",
            "title": frozen["title"],
            "retrieved_at": frozen["retrieved_at"],
            "content_hash": frozen["metadata_content_hash"],
            "frozen_news_item_id": frozen["news_item_id"],
        }
        decision["news_evidence"] = [public_evidence]
        valid = validate_decision(decision, analysis)
        self.assertTrue(valid["valid"], valid)

        official = completed_decision(analysis)
        official["news_evidence"] = [
            {
                "symbol": "BTCUSDT",
                "source_url": "https://www.federalreserve.gov/example",
                "published_at": "2026-07-29T22:00:00Z",
                "claim_zh": "外部核验的官方材料也仅作为上下文。",
                "authority": "OFFICIAL_PRIMARY",
                "causal_status": "TEMPORAL_HYPOTHESIS_NOT_CAUSAL_PROOF",
                "evidence_origin": "EXTERNAL_OFFICIAL_VERIFICATION",
                "title": "Official primary-source test fixture",
                "retrieved_at": OBSERVED_AT,
                "content_hash": "c" * 64,
            }
        ]
        self.assertTrue(validate_decision(official, analysis)["valid"])
        arbitrary_official = copy.deepcopy(official)
        arbitrary_official["news_evidence"][0]["source_url"] = (
            "https://unverified.example/claim"
        )
        self.assertTrue(
            any(
                "OFFICIAL_SOURCE_DOMAIN_NOT_ALLOWED" in error
                for error in validate_decision(
                    arbitrary_official,
                    analysis,
                )["errors"]
            )
        )

        illegal_symbol = copy.deepcopy(decision)
        illegal_symbol["news_evidence"][0]["symbol"] = "DOGEUSDT"
        self.assertTrue(
            any(
                "INVALID_TYPED_EVIDENCE" in error
                for error in validate_decision(illegal_symbol, analysis)["errors"]
            )
        )

        future = copy.deepcopy(decision)
        future["news_evidence"][0]["published_at"] = "2026-07-30T00:00:01Z"
        self.assertTrue(
            any(
                "PUBLISHED_AFTER_DECISION" in error
                for error in validate_decision(future, analysis)["errors"]
            )
        )

        mismatched_title = copy.deepcopy(decision)
        mismatched_title["news_evidence"][0]["title"] = "Rewritten headline"
        self.assertTrue(
            any(
                "FROZEN_DISCOVERY_BINDING_MISMATCH" in error
                for error in validate_decision(mismatched_title, analysis)["errors"]
            )
        )

        fake_authority = copy.deepcopy(decision)
        fake_item = fake_authority["news_evidence"][0]
        fake_item["authority"] = "OFFICIAL_PRIMARY"
        fake_item["evidence_origin"] = "EXTERNAL_OFFICIAL_VERIFICATION"
        fake_item.pop("frozen_news_item_id")
        self.assertTrue(
            any(
                "OFFICIAL_AUTHORITY_CANNOT_RECLASSIFY_DISCOVERY" in error
                for error in validate_decision(fake_authority, analysis)["errors"]
            )
        )

    def test_new_risk_requires_exactly_one_low_level_action_or_plan_only(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(), cycle_id="cycle-bidirectional")

        missing = completed_decision(analysis)
        configure_open_long(missing, analysis, include_low_level=False)
        missing_result = validate_decision(missing, analysis)
        self.assertTrue(
            any(
                "EXECUTE_NOW_REQUIRES_EXACTLY_ONE_LOW_LEVEL_ACTION" in error
                for error in missing_result["errors"]
            )
        )

        plan_only = completed_decision(analysis)
        low = configure_open_long(
            plan_only,
            analysis,
            execution_intent="PLAN_ONLY",
            include_low_level=False,
        )
        plan_result = validate_decision(plan_only, analysis)
        self.assertTrue(plan_result["valid"], plan_result)
        self.assertEqual([], plan_result["normalized_decision"]["actions"])

        plan_with_action = copy.deepcopy(plan_only)
        plan_with_action["portfolio_actions"] = [low]
        plan_with_action_result = validate_decision(plan_with_action, analysis)
        self.assertTrue(
            any(
                "PLAN_ONLY_FORBIDS_LOW_LEVEL_ACTION" in error
                for error in plan_with_action_result["errors"]
            )
        )

        duplicate = completed_decision(analysis)
        configure_open_long(duplicate, analysis)
        duplicate["portfolio_actions"].append(
            copy.deepcopy(duplicate["portfolio_actions"][0])
        )
        duplicate_result = validate_decision(duplicate, analysis)
        self.assertTrue(
            any(
                "EXECUTE_NOW_REQUIRES_EXACTLY_ONE_LOW_LEVEL_ACTION" in error
                for error in duplicate_result["errors"]
            )
        )

    def test_gross_one_point_five_geometry_fails_cost_aware_decision_gate(self) -> None:
        analysis = build_cycle_analysis(
            market_snapshot(),
            cycle_id="cycle-net-rr",
        )
        geometry = next(
            item
            for item in analysis["symbols"][0]["action_geometry_candidates"]
            if item["status"] == "RESEARCH_READY" and item["side"] == "LONG"
        )
        entry = (
            geometry["entry_zone"]["low"] + geometry["entry_zone"]["high"]
        ) / 2.0
        geometry["stop_loss"] = entry - 5.0
        geometry["take_profit"] = entry + 7.5
        decision = completed_decision(analysis)
        configure_open_long(decision, analysis)
        result = validate_decision(decision, analysis)
        self.assertTrue(
            any(
                "MINIMUM_NET_REWARD_RISK_NOT_MET" in error
                for error in result["errors"]
            )
        )

    def test_activity_gate_uses_frozen_fields_not_probe_language(self) -> None:
        analysis = build_cycle_analysis(
            market_snapshot(),
            portfolio_state={
                "valid_hours_without_strategy_fill": 7,
                "lots": [],
                "orders": [],
            },
            cycle_id="cycle-probe-gate",
        )
        settings = {
            "activity_policy": {
                "valid_hours_without_strategy_fill_before_probe": 6,
                "probe_notional_min_usdt": 100.0,
                "probe_notional_max_usdt": 250.0,
            }
        }
        evasion = completed_decision(analysis)
        evasion["portfolio_rationale_zh"] = (
            "文字声称已经执行 probe，但没有任何低层动作。"
        )
        blocked = validate_decision(evasion, analysis, settings)
        self.assertFalse(blocked["valid"])
        self.assertEqual(
            "BLOCKED_ACTIONABLE_INACTIVITY",
            blocked["orchestration_gate"]["status"],
        )
        self.assertFalse(blocked["orchestration_gate"]["satisfied"])

        veto = completed_decision(analysis)
        veto["symbol_decisions"][0]["market_actionability"] = "RISK_VETO"
        veto_result = validate_decision(veto, analysis, settings)
        self.assertTrue(veto_result["valid"], veto_result)
        self.assertEqual(
            "SATISFIED_BY_TYPED_SAFETY_VETO",
            veto_result["orchestration_gate"]["status"],
        )

        probe = completed_decision(analysis)
        configure_open_long(probe, analysis, probe=True)
        probe_result = validate_decision(probe, analysis, settings)
        self.assertTrue(probe_result["valid"], probe_result)
        self.assertEqual(
            "SATISFIED_BY_EXECUTED_NEW_RISK",
            probe_result["orchestration_gate"]["status"],
        )
        self.assertEqual(
            ["BTCUSDT"],
            probe_result["orchestration_gate"]["executed_probe_symbols"],
        )

        invalid_enum = completed_decision(analysis)
        invalid_enum["symbol_decisions"][0]["market_actionability"] = (
            "ACTIONABLE because the narrative says so"
        )
        invalid_enum["symbol_decisions"][0]["active_probe_plan"] = "true"
        enum_result = validate_decision(invalid_enum, analysis, settings)
        self.assertTrue(
            any("INVALID_MARKET_ACTIONABILITY" in error for error in enum_result["errors"])
        )
        self.assertTrue(
            any(
                "ACTIVE_PROBE_PLAN_MUST_BE_BOOLEAN" in error
                for error in enum_result["errors"]
            )
        )

    def test_recursive_secret_prefixes_are_rejected_in_keys_and_free_text(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(), cycle_id="cycle-secret")
        secret_key = completed_decision(analysis)
        secret_key["nested"] = {"apiSecretBackup": "redacted-looking-value"}
        key_result = validate_decision(secret_key, analysis)
        self.assertIn("LIVE_OR_CREDENTIAL_FIELD_FORBIDDEN", key_result["errors"])

        secret_text = completed_decision(analysis)
        secret_text["portfolio_rationale_zh"] = (
            "accidental secret sk-proj-abcdefghijklmnop must never be persisted"
        )
        text_result = validate_decision(secret_text, analysis)
        self.assertIn("LIVE_OR_CREDENTIAL_FIELD_FORBIDDEN", text_result["errors"])

    def test_active_method_delta_is_frozen_and_requires_execution_acceptance_plan(self) -> None:
        method_delta = {
            "id": "METHOD-DELTA-001",
            "version": "v1",
            "effective_cycle": "cycle-method-delta",
            "proposed_method_delta": "Require a retest before breakout entry.",
            "falsification_test": "Reject if retest filtering worsens unseen geometry.",
        }
        analysis = build_cycle_analysis(
            market_snapshot(),
            config={"active_method_delta": method_delta},
            cycle_id="cycle-method-delta",
        )
        self.assertEqual(method_delta, analysis["active_method_delta"])
        template = build_decision_template(analysis)
        self.assertEqual(method_delta, template["active_method_delta"])
        self.assertIn("execution_steps", template["method_delta_execution"])
        self.assertIn("acceptance_criteria", template["method_delta_execution"])

        decision = completed_decision(analysis)
        decision["method_delta_execution"] = {
            "method_delta_id": method_delta["id"],
            "execution_steps": ["等待突破后回踩确认再构造纸面入场。"],
            "acceptance_criteria": ["记录回踩是否降低无效突破比例。"],
            "falsification_observation": "若新样本遗漏直接延续行情则记录否证。",
        }
        valid = validate_decision(decision, analysis)
        self.assertTrue(valid["valid"], valid)

        mismatch = copy.deepcopy(decision)
        mismatch["active_method_delta"]["version"] = "v2"
        mismatch_result = validate_decision(mismatch, analysis)
        self.assertIn("ACTIVE_METHOD_DELTA_MISMATCH", mismatch_result["errors"])

    def test_integrity_hard_failures_and_pnl_exclusion(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(), cycle_id="cycle-score")
        baseline = score_theory_integrity(analysis)
        with_pnl = copy.deepcopy(analysis)
        with_pnl["paper_performance"] = {"pnl_usdt": 999999.0, "win_rate": 1.0}
        self.assertEqual(baseline, score_theory_integrity(with_pnl))

        tampered = copy.deepcopy(analysis)
        competition = tampered["symbols"][0]["phi_competition"]
        competition["hypotheses"][0]["probability"] = 0.8
        competition["hypotheses"] = [
            item
            for item in competition["hypotheses"]
            if item["phi_id"] != "PHI_OTHER_UNKNOWN"
        ]
        score = score_theory_integrity(tampered)
        self.assertFalse(score["passing"])
        self.assertLessEqual(score["score"], 49)
        self.assertTrue(
            any("ORDINAL_TREATED_AS_PROBABILITY" in item for item in score["hard_failures"])
        )
        self.assertTrue(
            any("OTHER_UNKNOWN_MISSING" in item for item in score["hard_failures"])
        )

    def test_method_score_and_eight_hour_candidates_are_process_only(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(), cycle_id="cycle-method")
        decision = completed_decision(analysis)
        validation = validate_decision(decision, analysis)
        self.assertTrue(validation["valid"], validation)
        record = {
            "cycle_id": "cycle-method",
            "analysis": analysis,
            "decision": validation["normalized_decision"],
            "review": {
                "hypothesis_status": "FALSIFIED",
                "evidence_refs": ["next-hour-closed-bar"],
                "method_issue_codes": ["ACTION_GEOMETRY", "FALSIFICATION"],
                "lesson": "The invalidation condition was too broad.",
                "posthoc_thesis_changed": False,
            },
            "paper_performance": {"pnl_usdt": -500.0},
        }
        first = score_method_practice([record])
        profitable = copy.deepcopy(record)
        profitable["paper_performance"]["pnl_usdt"] = 5000.0
        self.assertEqual(first, score_method_practice([profitable]))
        self.assertFalse(first["pnl_in_score"])
        supported = copy.deepcopy(record)
        supported["review"]["hypothesis_status"] = "SUPPORTED_AT_EXPIRY"
        self.assertEqual(first, score_method_practice([supported]))

        candidates = build_method_candidates([record], "review-001", window_hours=8)
        self.assertEqual(
            ["ACTION_GEOMETRY", "FALSIFICATION"],
            [item["issue_code"] for item in candidates],
        )
        self.assertTrue(all(item["status"] == "PROPOSED_NOT_ADOPTED" for item in candidates))
        self.assertTrue(all(item["automatic_core_edit"] is False for item in candidates))
        self.assertEqual(candidates, build_method_candidates([record], "review-001", 8))

    def test_actionable_inactivity_requires_an_active_probe_plan(self) -> None:
        analysis = build_cycle_analysis(market_snapshot(), cycle_id="cycle-idle")
        base = completed_decision(analysis)
        base["symbol_decisions"][0]["active_probe_plan"] = False
        validation = validate_decision(base, analysis)
        self.assertTrue(validation["valid"], validation)
        records = [
            {
                "analysis": analysis,
                "decision": validation["normalized_decision"],
                "review": {
                    "hypothesis_status": "UNRESOLVED_UNKNOWN",
                    "evidence_refs": [],
                    "method_issue_codes": [],
                    "lesson": "No bounded probe was planned.",
                    "posthoc_thesis_changed": False,
                },
            }
            for _ in range(4)
        ]
        score = score_method_practice(records)
        self.assertIn("UNDERTRADING_WITHOUT_ACTIVE_PROBE_PLAN", score["hard_failures"])
        self.assertLessEqual(score["score"], 49)


if __name__ == "__main__":
    unittest.main()
