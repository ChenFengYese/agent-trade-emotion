from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trade_system.theory_paper.common import (
    TheoryPaperError,
    digest_json,
    read_json,
    verify_ledger,
    write_atomic_json,
)
from trade_system.theory_paper.experiment import (
    _hypothesis_assessments,
    finalize_experiment,
    initialize_experiment,
    inject_manual_emotion_trade,
    run_hourly_cycle,
    run_review,
    status_report,
    submit_agent_decision,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "theory_paper_experiment.v1.json"
SYMBOL_PRICES = {
    "SNDKUSDT": 1110.0,
    "MUUSDT": 790.0,
    "BTCUSDT": 64500.0,
    "ETHUSDT": 1925.0,
    "SOLUSDT": 75.5,
    "HYPEUSDT": 55.2,
}


def _timeframe(price: float, close_time_ms: int) -> dict[str, Any]:
    return {
        "status": "OBSERVED_CLOSED_BARS",
        "bar_count": 240,
        "price": price,
        "change_1_bar_pct": 0.25,
        "change_6_bar_pct": 1.1,
        "ema20": price * 0.99,
        "ema50": price * 0.98,
        "ema200": price * 0.95,
        "rsi14": 57.0,
        "atr14": price * 0.01,
        "atr_pct": 1.0,
        "adx14": 24.0,
        "efficiency_ratio10": 0.42,
        "macd": price * 0.002,
        "macd_signal": price * 0.0015,
        "macd_histogram": price * 0.0005,
        "bollinger_upper": price * 1.03,
        "bollinger_lower": price * 0.97,
        "relative_volume20": 1.15,
        "trend_state": "UP",
        "supports": [price * 0.98],
        "resistances": [price * 1.03],
        # Deliberately spans every legacy limit level, but is historical.  A
        # correct run must not convert it into a paper fill.
        "last_closed_bar": {
            "open_time": close_time_ms - 3_599_999,
            "open": price,
            "high": 100_000.0,
            "low": 1.0,
            "close": price,
            "volume": 1_000.0,
            "close_time": close_time_ms,
        },
    }


def _market_snapshot(observed_at: datetime, activated_at: datetime) -> dict[str, Any]:
    historical_close = int((activated_at - timedelta(milliseconds=1)).timestamp() * 1000)
    symbols: list[dict[str, Any]] = []
    for symbol, price in SYMBOL_PRICES.items():
        timeframes = {
            interval: _timeframe(price, historical_close)
            for interval in ("15m", "1h", "4h", "1d", "1w")
        }
        symbols.append(
            {
                "symbol": symbol,
                "venue": "BINANCE_USDM_PUBLIC",
                "instrument_kind": (
                    "TRADIFI_EQUITY_PERPETUAL_DERIVATIVE"
                    if symbol in {"SNDKUSDT", "MUUSDT"}
                    else "CRYPTO_PERPETUAL_DERIVATIVE"
                ),
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "measures": {
                    "price": price,
                    "ticker_24h": {
                        "change_pct": 1.2,
                        "high": price * 1.03,
                        "low": price * 0.97,
                        "quote_volume": 10_000_000.0,
                        "trade_count": 50_000,
                    },
                    "directional_pressure_D": {
                        "recent_trades": {
                            "status": "OBSERVED_RECENT_WINDOW",
                            "trade_count": 100,
                            "taker_buy_notional": 550_000.0,
                            "taker_sell_notional": 450_000.0,
                            "signed_taker_imbalance": 0.1,
                            "vwap": price,
                            "first_price": price * 0.999,
                            "last_price": price,
                        },
                        "hourly_taker_buy_sell_ratio": 1.1,
                        "interpretation_boundary": (
                            "FLOW_PRESSURE_PROXY_NOT_PARTICIPANT_IDENTITY"
                        ),
                    },
                    "leverage_L": {
                        "open_interest_contracts": 1_000_000.0,
                        "open_interest_value_1h_change_pct": 0.5,
                        "interpretation_boundary": (
                            "OI_CHANGE_HAS_NO_DIRECTIONAL_TRUTH_ALONE"
                        ),
                    },
                    "crowding_C": {
                        "funding_rate": 0.0001,
                        "basis_bps": 2.0,
                        "global_account_long_short_ratio": 1.05,
                        "top_position_long_short_ratio": 1.1,
                        "interpretation_boundary": (
                            "MULTI_PROXY_VECTOR_NOT_SINGLE_EMOTION_SCORE"
                        ),
                    },
                    "forced_deleveraging_F": {
                        "status": "OBSERVED_RECENT_API_WINDOW",
                        "event_count": 0,
                        "notional": 0.0,
                        "missing_is_zero": False,
                    },
                    "liquidity_resilience_R": {
                        "status": "OBSERVED_SINGLE_BOOK_SNAPSHOT",
                        "spread_bps": 1.5,
                        "book_imbalance": 0.08,
                        "buy_impact_bps_for_1000_usdt": 0.8,
                        "sell_impact_bps_for_1000_usdt": 0.9,
                        "strict_resilience_available": False,
                    },
                    "timeframes": timeframes,
                },
                "data_quality": {
                    "required_components": 15,
                    "error_count": 0,
                    "coverage_ratio": 1.0,
                    "errors": {},
                    "strict_R_available": False,
                    "liquidation_zero_certainty": False,
                },
                "raw_digest": digest_json({"symbol": symbol, "price": price}),
                "raw": {},
            }
        )
    snapshot = {
        "schema_version": "theory-paper-market-snapshot.v1",
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "symbols": symbols,
        "failures": {},
        "point_in_time_rule": (
            "ONLY_RESPONSES_AVAILABLE_BY_OBSERVED_AT_AND_CLOSED_BARS"
        ),
    }
    snapshot["market_snapshot_digest"] = digest_json(snapshot)
    return snapshot


def _news_snapshot(observed_at: datetime) -> dict[str, Any]:
    queries = {
        symbol: {
            "query": f"{symbol} synthetic test context",
            "source": "OFFLINE_TEST_FIXTURE",
            "items": [
                {
                    "title": f"{symbol} public context headline",
                    "url": f"https://example.invalid/{symbol.lower()}",
                    "published_at": "Wed, 30 Jul 2026 00:30:00 GMT",
                    "source": "Synthetic primary-source placeholder",
                }
            ],
            "error": None,
        }
        for symbol in SYMBOL_PRICES
    }
    return {
        "schema_version": "theory-paper-news-metadata.v1",
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "queries": queries,
        "interpretation_boundary": (
            "HEADLINES_ARE_CONTEXT_FACTS_NOT_CAUSAL_OR_SENTIMENT_TRUTH"
        ),
    }


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    forbidden = {
        "api_key",
        "api_secret",
        "secret_key",
        "private_key",
        "credential",
        "credentials",
        "account_id",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key).lower() in forbidden:
                found.append(child)
            found.extend(_find_forbidden_keys(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_forbidden_keys(item, f"{path}[{index}]"))
    return found


def _complete_abstention_template(
    template: dict[str, Any],
    *,
    expiry_at: datetime,
    portfolio: dict[str, Any],
    triage_initial_risk: bool,
) -> dict[str, Any]:
    """Fill the skeleton and complete the first-cycle legacy-risk triage."""

    expiry = expiry_at.isoformat().replace("+00:00", "Z")
    template.update(
        {
            "executive_summary_zh": "离线生命周期夹具只检验审计和状态转换。",
            "portfolio_rationale_zh": "首轮保护遗留仓位，后续周期不新增风险。",
            "news_evidence": [],
            "method_observations": ["离线固定数据不能支持真实消息因果结论。"],
            "agent_identity": {
                "agent_role": "OFFLINE_TEST_AGENT",
                "model_identity": "DETERMINISTIC_UNIT_TEST",
                "prompt_binding_sha256": template["agent_identity"][
                    "prompt_binding_sha256"
                ],
            },
        }
    )
    if isinstance(template.get("active_method_delta"), dict):
        template["method_delta_execution"] = {
            "method_delta_id": template["active_method_delta"]["id"],
            "execution_steps": [
                "Apply the frozen future-only method delta to this cycle."
            ],
            "acceptance_criteria": [
                "Record whether the named issue recurs in the next review window."
            ],
            "falsification_observation": (
                "The issue recurs at or above its frozen baseline count."
            ),
        }
    for action in template["symbol_decisions"]:
        phi_ids = action["allowed_phi_ids"]
        fact_refs = json.loads(json.dumps(action["available_fact_refs"][:2]))
        inference_refs = json.loads(
            json.dumps(action["available_inference_refs"][:2])
        )
        action.update(
            {
                "action": "ABSTAIN",
                "execution_intent": "NO_NEW_RISK",
                "selected_phi_id": phi_ids[0],
                "alternative_phi_ids": phi_ids[1:2],
                "analysis_narrative_zh": "离线夹具保留完整分析记录，但不作方向预测。",
                "behavior_hypotheses_zh": "成交代理不能识别具体参与者或机构身份。",
                "future_force_path_zh": "下一闭合周期仅用于验证生命周期和否证字段。",
                "thesis": (
                    "Offline lifecycle fixture abstains; it tests the audit path, "
                    "not a directional market claim."
                ),
                "fact_refs": fact_refs,
                "inference_refs": inference_refs,
                "hard_falsifier": (
                    "The fixture expires at the declared UTC time without being "
                    "promoted into a trade."
                ),
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
                "next_observations": ["下一根已闭合的一小时测试 K 线"],
                "expiry_at": expiry,
                "geometry_candidate_id": "UNKNOWN",
                "order": {
                    "order_type": "UNKNOWN",
                    "side": "UNKNOWN",
                    "limit_price": "UNKNOWN",
                    "notional_usdt": "UNKNOWN",
                    "stop_loss": "UNKNOWN",
                    "take_profit": "UNKNOWN",
                },
                "abstention_reason_code": "OFFLINE_LIFECYCLE_FIXTURE",
                "market_actionability": "RISK_VETO",
                "active_probe_plan": False,
            }
        )
    if not triage_initial_risk:
        template["portfolio_actions"].append(
            {
                "type": "HOLD",
                "reason": "NO_NEW_LOW_LEVEL_PORTFOLIO_ACTION_IN_OFFLINE_FIXTURE",
            }
        )
        return template
    for lot in portfolio["lots"]:
        if lot["status"] != "OPEN":
            continue
        mark = SYMBOL_PRICES[lot["symbol"]]
        template["portfolio_actions"].append(
            {
                "type": "UPDATE_PROTECTION",
                "symbol": lot["symbol"],
                "lot_id": lot["lot_id"],
                "stop_price": mark * 0.98,
                "target_price": mark * 1.04,
                "reason": "FIRST_CYCLE_INITIAL_POSITION_PROTECTION",
            }
        )
    for order in portfolio["orders"]:
        if order["state"] != "REVIEW_REQUIRED":
            continue
        template["portfolio_actions"].append(
            {
                "type": "CANCEL_ORDER",
                "order_id": order["order_id"],
                "reason": "OFFLINE_FIXTURE_CANCELS_UNREVIEWED_LEGACY_ORDER",
            }
        )
    return template


class TheoryPaperExperimentEndToEndTests(unittest.TestCase):
    def test_offline_lifecycle_is_auditable_idempotent_and_paper_only(self) -> None:
        started_at = datetime(2026, 7, 30, 0, 0, tzinfo=timezone.utc)
        cycle_at = started_at + timedelta(hours=1, minutes=15)

        def network_must_not_be_called(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.fail("injected offline snapshots must prevent every network fetch")

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            config_path = Path(temporary) / "simulated-config.json"
            simulated_config = json.loads(CONFIG.read_text(encoding="utf-8"))
            simulated_config["clock_policy"]["mode"] = "SIMULATED_CLOCK_TEST_ONLY"
            config_path.write_text(
                json.dumps(simulated_config),
                encoding="utf-8",
            )
            initialized = initialize_experiment(
                config_path,
                run_dir,
                started_at=started_at,
            )
            self.assertTrue(initialized["initialized"])
            self.assertTrue(initialized["paper_only"])
            self.assertEqual(set(initialized["symbols"]), set(SYMBOL_PRICES))

            cycle = run_hourly_cycle(
                run_dir,
                decision_at=cycle_at,
                market_snapshot=_market_snapshot(cycle_at, started_at),
                news_snapshot=_news_snapshot(cycle_at),
                market_fetcher=network_must_not_be_called,
                news_fetcher=network_must_not_be_called,
            )
            self.assertTrue(cycle["created"])
            self.assertEqual(cycle["cycle_id"], "cycle-0001")
            self.assertEqual(set(cycle["symbols_observed"]), set(SYMBOL_PRICES))

            market_execution = read_json(
                run_dir / "cycles" / "cycle-0001" / "market-execution.json"
            )
            self.assertEqual(market_execution["fills"], [])
            self.assertEqual(
                {item["reason"] for item in market_execution["skipped"]},
                {"BAR_NOT_AFTER_PORTFOLIO_ACTIVATION"},
            )
            state_before_submit = read_json(run_dir / "state.json")
            self.assertEqual(state_before_submit["portfolio"]["fills"], [])
            self.assertTrue(
                all(
                    order["state"] == "REVIEW_REQUIRED"
                    for order in state_before_submit["portfolio"]["orders"]
                )
            )

            sealed = read_json(run_dir / ".sealed-chaos.json")
            analysis_path = run_dir / "cycles" / "cycle-0001" / "analysis.json"
            analysis = read_json(analysis_path)
            analysis_text = analysis_path.read_text(encoding="utf-8")
            self.assertNotIn(sealed["seed"], analysis_text)
            for event in sealed["events"]:
                self.assertNotIn(event["due_at"], analysis_text)
            self.assertNotIn("chaos", analysis.get("portfolio_context", {}))

            template = read_json(
                run_dir / "cycles" / "cycle-0001" / "decision-template.json"
            )
            template = _complete_abstention_template(
                template,
                expiry_at=cycle_at + timedelta(hours=4),
                portfolio=state_before_submit["portfolio"],
                triage_initial_risk=True,
            )
            receipt = submit_agent_decision(
                run_dir,
                template,
                decided_at=cycle_at + timedelta(minutes=5),
            )
            self.assertTrue(receipt["paper_only"])
            self.assertEqual(receipt["cycle_id"], "cycle-0001")
            self.assertNotIn(
                "REJECTED",
                {item["status"] for item in receipt["execution"]["results"]},
            )
            self.assertEqual(
                receipt["portfolio_metrics"]["unprotected_lot_ids"],
                [],
            )
            state_after_submit = read_json(run_dir / "state.json")
            self.assertTrue(
                all(
                    order["state"] == "CANCELED"
                    for order in state_after_submit["portfolio"]["orders"]
                )
            )
            state_before_bad_chaos = read_json(run_dir / "state.json")
            with self.assertRaises(TheoryPaperError):
                inject_manual_emotion_trade(
                    run_dir,
                    idempotency_key="manual-too-small",
                    symbol="MUUSDT",
                    side="BUY",
                    notional_usdt=99.0,
                    reason="BOUNDARY_TEST",
                    injected_at=cycle_at + timedelta(minutes=10),
                )
            self.assertEqual(
                read_json(run_dir / "state.json"),
                state_before_bad_chaos,
            )
            manual = inject_manual_emotion_trade(
                run_dir,
                idempotency_key="manual-accepted-100",
                symbol="MUUSDT",
                side="BUY",
                notional_usdt=100.0,
                reason="EXPLICIT_EMOTION_DISTURBANCE_TEST",
                injected_at=cycle_at + timedelta(minutes=10),
            )
            duplicate_manual = inject_manual_emotion_trade(
                run_dir,
                idempotency_key="manual-accepted-100",
                symbol="MUUSDT",
                side="BUY",
                notional_usdt=100.0,
                reason="EXPLICIT_EMOTION_DISTURBANCE_TEST",
                injected_at=cycle_at + timedelta(minutes=11),
            )
            self.assertEqual(manual, duplicate_manual)
            with self.assertRaises(TheoryPaperError):
                inject_manual_emotion_trade(
                    run_dir,
                    idempotency_key="manual-accepted-100",
                    symbol="MUUSDT",
                    side="SELL",
                    notional_usdt=100.0,
                    reason="DIFFERENT_PAYLOAD",
                    injected_at=cycle_at + timedelta(minutes=12),
                )

            same_hour = run_hourly_cycle(
                run_dir,
                decision_at=cycle_at + timedelta(minutes=30),
                market_snapshot=_market_snapshot(cycle_at, started_at),
                news_snapshot=_news_snapshot(cycle_at),
                market_fetcher=network_must_not_be_called,
                news_fetcher=network_must_not_be_called,
            )
            self.assertFalse(same_hour["created"])
            self.assertEqual(
                same_hour["reason"],
                "IDEMPOTENT_HOUR_ALREADY_CREATED",
            )
            self.assertEqual(read_json(run_dir / "state.json")["cycle_count"], 1)

            for hour in range(2, 9):
                next_cycle_at = started_at + timedelta(hours=hour, minutes=15)
                hourly_market = _market_snapshot(next_cycle_at, started_at)
                if hour == 2:
                    hourly_market["failures"] = {
                        "synthetic_component": "OFFLINE_DATA_QUALITY_TEST"
                    }
                    hourly_market["market_snapshot_digest"] = digest_json(
                        {
                            key: value
                            for key, value in hourly_market.items()
                            if key != "market_snapshot_digest"
                        }
                    )
                next_cycle = run_hourly_cycle(
                    run_dir,
                    decision_at=next_cycle_at,
                    market_snapshot=hourly_market,
                    news_snapshot=_news_snapshot(next_cycle_at),
                    market_fetcher=network_must_not_be_called,
                    news_fetcher=network_must_not_be_called,
                )
                self.assertTrue(next_cycle["created"])
                next_template = read_json(
                    run_dir
                    / "cycles"
                    / f"cycle-{hour:04d}"
                    / "decision-template.json"
                )
                current_state = read_json(run_dir / "state.json")
                next_template = _complete_abstention_template(
                    next_template,
                    expiry_at=next_cycle_at + timedelta(hours=4),
                    portfolio=current_state["portfolio"],
                    triage_initial_risk=False,
                )
                next_receipt = submit_agent_decision(
                    run_dir,
                    next_template,
                    decided_at=next_cycle_at + timedelta(minutes=5),
                )
                self.assertNotIn(
                    "REJECTED",
                    {
                        item["status"]
                        for item in next_receipt["execution"]["results"]
                    },
                )

            review = run_review(
                run_dir,
                reviewed_at=started_at + timedelta(hours=8, minutes=30),
                force=True,
            )
            self.assertTrue(review["created"])
            self.assertEqual(review["cycle_range"], [1, 8])
            self.assertEqual(
                review["score_boundary"],
                "PNL_DOES_NOT_CHANGE_THEORY_OR_METHOD_SCORE",
            )
            lifecycle_statuses = {
                item["status"]
                for item in review["hypothesis_lifecycle_updates"]
            }
            self.assertIn("SUPPORTED_AT_EXPIRY", lifecycle_statuses)
            self.assertNotIn("FALSIFIED", lifecycle_statuses)
            self.assertEqual(
                review["hypothesis_outcome_diagnostics"]["score"],
                100.0,
            )
            self.assertTrue(review["primary_delta_for_future_cycles"])

            ninth_at = started_at + timedelta(hours=9, minutes=15)
            ninth = run_hourly_cycle(
                run_dir,
                decision_at=ninth_at,
                market_snapshot=_market_snapshot(ninth_at, started_at),
                news_snapshot=_news_snapshot(ninth_at),
                market_fetcher=network_must_not_be_called,
                news_fetcher=network_must_not_be_called,
            )
            self.assertTrue(ninth["created"])
            ninth_analysis = read_json(
                run_dir / "cycles" / "cycle-0009" / "analysis.json"
            )
            self.assertIsInstance(ninth_analysis["active_method_delta"], dict)
            ninth_template = _complete_abstention_template(
                read_json(
                    run_dir / "cycles" / "cycle-0009" / "decision-template.json"
                ),
                expiry_at=ninth_at + timedelta(hours=4),
                portfolio=read_json(run_dir / "state.json")["portfolio"],
                triage_initial_risk=False,
            )
            submit_agent_decision(
                run_dir,
                ninth_template,
                decided_at=ninth_at + timedelta(minutes=5),
            )

            active_status = status_report(run_dir)
            self.assertEqual(active_status["status"], "ACTIVE")
            self.assertEqual(active_status["cycle_count"], 9)
            self.assertEqual(active_status["review_count"], 1)
            self.assertTrue(active_status["ledger"]["valid"])

            final = finalize_experiment(
                run_dir,
                finalized_at=started_at + timedelta(hours=72),
                force=True,
            )
            self.assertEqual(
                final["result_status"],
                "INCOMPLETE_RECOVERY_PAPER_PRACTICE",
            )
            self.assertTrue(final["ledger_after_final"]["valid"])
            self.assertEqual(status_report(run_dir)["status"], "FINALIZED")

            for path in run_dir.rglob("*.json"):
                self.assertEqual(
                    _find_forbidden_keys(json.loads(path.read_text(encoding="utf-8"))),
                    [],
                    msg=f"credential-shaped key leaked into {path.relative_to(run_dir)}",
                )
            self.assertTrue(verify_ledger(run_dir)["valid"])

    def test_live_clock_and_transaction_anchor_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            future_run = Path(temporary) / "future"
            with self.assertRaises(TheoryPaperError):
                initialize_experiment(
                    CONFIG,
                    future_run,
                    started_at=datetime(2040, 1, 1, tzinfo=timezone.utc),
                )

            config_path = Path(temporary) / "simulated-config.json"
            simulated_config = json.loads(CONFIG.read_text(encoding="utf-8"))
            simulated_config["clock_policy"]["mode"] = "SIMULATED_CLOCK_TEST_ONLY"
            config_path.write_text(json.dumps(simulated_config), encoding="utf-8")
            secret_config_path = Path(temporary) / "secret-config.json"
            secret_config = json.loads(json.dumps(simulated_config))
            secret_config["unsafe_nested"] = {"api_key": "credential-canary"}
            secret_config_path.write_text(
                json.dumps(secret_config),
                encoding="utf-8",
            )
            with self.assertRaises(TheoryPaperError):
                initialize_experiment(
                    secret_config_path,
                    Path(temporary) / "secret-run",
                    started_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
                )
            run_dir = Path(temporary) / "anchored"
            initialize_experiment(
                config_path,
                run_dir,
                started_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            )
            status = status_report(run_dir)
            self.assertEqual(
                status["transaction_state"]["latest_transaction_id"],
                "experiment-initialize",
            )
            state = read_json(run_dir / "state.json")
            state["portfolio"]["cash_balance_usdt"] += 1.0
            write_atomic_json(run_dir / "state.json", state)
            with self.assertRaises(TheoryPaperError):
                status_report(run_dir)

    def test_supported_hypothesis_remains_open_and_can_later_be_falsified(self) -> None:
        start = datetime(2026, 7, 30, tzinfo=timezone.utc)
        decision = {
            "symbol": "BTCUSDT",
            "selected_phi_id": "PHI-TREND-CONTINUATION",
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
            "expiry_at": (start + timedelta(hours=20))
            .isoformat()
            .replace("+00:00", "Z"),
        }

        def analysis(at: datetime, direction: str) -> dict[str, Any]:
            return {
                "analysis_digest": digest_json(
                    {"at": at.isoformat(), "direction": direction}
                ),
                "decision_at": at.isoformat().replace("+00:00", "Z"),
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "measurement_snapshot": {},
                        "structural_position": {},
                        "multi_scale_state_belief": {
                            "role_states": [
                                {
                                    "timeframe": "4h",
                                    "direction_state": direction,
                                }
                            ]
                        },
                    }
                ],
            }

        first = _hypothesis_assessments(
            [decision],
            [analysis(start + timedelta(hours=4), "UP")],
            start + timedelta(hours=8),
            start.isoformat().replace("+00:00", "Z"),
        )
        self.assertEqual(first[0]["status"], "SUPPORTED_ACTIVE")
        later = _hypothesis_assessments(
            [decision],
            [
                analysis(start + timedelta(hours=4), "UP"),
                analysis(start + timedelta(hours=12), "DOWN"),
            ],
            start + timedelta(hours=16),
            start.isoformat().replace("+00:00", "Z"),
        )
        self.assertEqual(later[0]["status"], "FALSIFIED")

    def test_uncommitted_decision_and_final_artifacts_are_not_idempotent_success(self) -> None:
        start = datetime(2026, 7, 30, tzinfo=timezone.utc)
        cycle_at = start + timedelta(minutes=15)
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "simulated-config.json"
            simulated_config = json.loads(CONFIG.read_text(encoding="utf-8"))
            simulated_config["clock_policy"]["mode"] = "SIMULATED_CLOCK_TEST_ONLY"
            config_path.write_text(json.dumps(simulated_config), encoding="utf-8")
            run_dir = Path(temporary) / "run"
            initialize_experiment(config_path, run_dir, started_at=start)
            run_hourly_cycle(
                run_dir,
                decision_at=cycle_at,
                market_snapshot=_market_snapshot(cycle_at, start),
                news_snapshot=_news_snapshot(cycle_at),
            )
            write_atomic_json(
                run_dir / "cycles" / "cycle-0001" / "decision.json",
                {"forged": True},
            )
            with self.assertRaises(TheoryPaperError):
                submit_agent_decision(
                    run_dir,
                    decided_at=cycle_at + timedelta(minutes=1),
                )
            write_atomic_json(
                run_dir / "final" / "report.json",
                {"forged": True},
            )
            with self.assertRaises(TheoryPaperError):
                finalize_experiment(
                    run_dir,
                    finalized_at=start + timedelta(hours=72),
                    force=True,
                )


if __name__ == "__main__":
    unittest.main()
