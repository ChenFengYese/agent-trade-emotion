from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from trade_system.theory_paper.market import _book_measures

from trade_system.theory_paper_v2.application.prospective_single_agent import (
    PROSPECTIVE_EVIDENCE_CLASS,
    ProspectiveResearchError,
    SYMBOLS,
    _aggregate_candle_rows,
    _capture_request,
    _prospective_source_config,
    _request_routes,
    _request_specs,
    _trade_measures,
    _validate_successor_recovery_contract,
    collect_next_prospective_cycle,
    interrupt_prospective_research,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from trade_system.theory_paper_v2.application.single_agent_research import (
    _initial_state,
    _symbol_context,
)


class ProspectiveSingleAgentTests(unittest.TestCase):
    def template(self) -> dict:
        return {
            "initial_equity_usdt": "10000",
            "initial_market_notional_usdt": {
                "SNDKUSDT": "500",
                "ETHUSDT": "1000",
                "SOLUSDT": "800",
                "BTCUSDT": "1000",
                "HYPEUSDT": "800",
            },
            "source_config": {"risk_policy": {"minimum_reward_risk": "1.5"}},
        }

    def context(self) -> dict:
        return {
            "decision_at": "2026-08-03T08:00:00Z",
            "symbols": {
                symbol: {
                    "mark": str(100 + index * 10),
                    "technical": {"1h": {"atr14": "2"}},
                }
                for index, symbol in enumerate(SYMBOLS)
            }
        }

    def test_initial_cost_is_102_percent_but_quantity_preserves_market_notional(self) -> None:
        config = _prospective_source_config(self.template(), self.context())
        positions = {
            row["symbol"]: row for row in config["initial_portfolio"]["positions"]
        }
        row = positions["SNDKUSDT"]
        self.assertEqual("102", row["entry_price"])
        self.assertEqual(Decimal("5"), Decimal(row["quantity"]))
        self.assertEqual("500", row["market_notional_at_genesis_usdt"])
        self.assertEqual("96", row["initial_stop_price"])
        self.assertEqual("114", row["management_checkpoint"])
        self.assertIsNotNone(row["risk_budget_usdt"])
        self.assertEqual(
            "CORE_DYNAMIC_MANAGEMENT_NOT_FIXED_TARGET", row["exit_intent"]
        )
        self.assertNotIn("MUUSDT", positions)
        self.assertEqual([], config["initial_portfolio"]["orders"])

    def test_genesis_agent_input_has_complete_initial_lot_contracts(self) -> None:
        context = self.context()
        for symbol in SYMBOLS:
            context["symbols"][symbol]["execution_bars_15m"] = []
        config = _prospective_source_config(self.template(), context)
        state = _initial_state(
            run_id="genesis-contract-test",
            source_config=config,
            activated_at=context["decision_at"],
            first_context=context,
        )
        self.assertEqual(5, len(state["portfolio"]["lots"]))
        for lot in state["portfolio"]["lots"]:
            contract = state["lot_contracts"][lot["lot_id"]]
            self.assertIsNotNone(lot["stop_price"])
            self.assertEqual("CORE", contract["role"])
            self.assertIsNotNone(contract["risk_budget_usdt"])
            self.assertIsNotNone(contract["management_checkpoint"])
            self.assertIsNotNone(contract["management_checkpoint_id"])
            self.assertIsNotNone(contract["protection_active_from"])
            self.assertIsNotNone(contract["max_horizon_at"])

    def test_slow_sentiment_routes_are_four_hour_and_terminal_only(self) -> None:
        hourly = {spec.name for spec in _request_specs(2)}
        review = {spec.name for spec in _request_specs(4)}
        terminal = {spec.name for spec in _request_specs(25)}
        for name in {"long_short", "taker_volume", "liquidations"}:
            self.assertNotIn(name, hourly)
            self.assertIn(name, review)
            self.assertIn(name, terminal)
        for name in {"mark", "funding_history", "oi_history", "book", "trades"}:
            self.assertIn(name, hourly)

    def test_candles_use_300_rows_and_official_current_route_fallback(self) -> None:
        spec = next(
            value
            for value in _request_specs(1)
            if value.symbol == "SNDKUSDT" and value.name == "candles_1h"
        )
        self.assertEqual("300", dict(spec.query)["limit"])
        self.assertEqual(
            ["/api/v5/market/history-candles", "/api/v5/market/candles"],
            [value.path for value in _request_routes(spec)],
        )

    def test_complete_lower_bars_aggregate_into_fixed_utc_bucket(self) -> None:
        hour_ms = 60 * 60 * 1000
        quarter_ms = 15 * 60 * 1000
        rows = [
            [
                index * quarter_ms,
                str(100 + index),
                str(102 + index),
                str(99 + index),
                str(101 + index),
                "10",
                (index + 1) * quarter_ms - 1,
                "1000",
            ]
            for index in range(8)
        ]
        aggregated = _aggregate_candle_rows(
            rows,
            source_duration_ms=quarter_ms,
            target_duration_ms=hour_ms,
            source_timeframe="15m",
        )
        self.assertEqual(2, len(aggregated))
        self.assertEqual("100", aggregated[0][1])
        self.assertEqual("105", aggregated[0][2])
        self.assertEqual("99", aggregated[0][3])
        self.assertEqual("104", aggregated[0][4])
        self.assertEqual("40", aggregated[0][5])
        self.assertEqual("4000", aggregated[0][7])
        self.assertIn("DERIVED_15M", aggregated[0][11])
        self.assertEqual(
            1,
            len(
                _aggregate_candle_rows(
                    rows[:-1],
                    source_duration_ms=quarter_ms,
                    target_duration_ms=hour_ms,
                    source_timeframe="15m",
                )
            ),
        )

    def test_failed_primary_route_and_successful_fallback_are_receipted(self) -> None:
        spec = next(
            value
            for value in _request_specs(1)
            if value.symbol == "SNDKUSDT" and value.name == "candles_1h"
        )
        now = datetime(2026, 8, 3, 7, tzinfo=UTC)
        raw = json.dumps(
            {
                "code": "0",
                "msg": "",
                "data": [["1", "1", "2", "0.5", "1.5", "10", "10", "15", "1"]],
            },
            separators=(",", ":"),
        ).encode()

        class FlakyCollector:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def _get(self, *, request_id: str, path: str, query_items: dict):
                self.calls.append(path)
                if len(self.calls) == 1:
                    raise ValueError("synthetic TLS failure")
                capture = SimpleNamespace(
                    request_started_at=now,
                    response_received_at=now + timedelta(seconds=1),
                    http_status=200,
                    raw_body_sha256=hashlib.sha256(raw).hexdigest(),
                    raw_body_byte_length=len(raw),
                    request_identity_digest="a" * 64,
                )
                return capture, raw

        collector = FlakyCollector()
        with tempfile.TemporaryDirectory() as directory:
            result = _capture_request(
                collector,
                spec,
                receipt_root=Path(directory),
            )
            self.assertEqual("SUCCESS", result["status"])
            self.assertEqual("/api/v5/market/candles", result["used_spec"].path)
            receipt = load_json_strict(
                Path(directory) / "SNDKUSDT" / "candles_1h.json"
            )
            verify_self_digest(receipt, "receipt_digest")
            self.assertEqual(2, len(receipt["attempts"]))
            self.assertEqual("FAILED_UNKNOWN", receipt["attempts"][0]["status"])
            self.assertEqual("SUCCESS", receipt["attempts"][1]["status"])

    def test_missing_higher_timeframes_remain_explicit_unknown(self) -> None:
        observed = datetime(2026, 8, 3, 7, tzinfo=UTC)
        observed_ms = int(observed.timestamp() * 1000)

        def rows(duration_ms: int) -> list[list[str | int]]:
            return [
                [
                    observed_ms - (30 - index) * duration_ms,
                    "100",
                    "102",
                    "99",
                    str(100 + index / 10),
                    "10",
                    observed_ms - (29 - index) * duration_ms,
                ]
                for index in range(30)
            ]

        source = {
            "symbol": "MUUSDT",
            "observed_at": observed.isoformat().replace("+00:00", "Z"),
            "raw": {
                "klines": {
                    "15m": rows(15 * 60 * 1000),
                    "1h": [],
                    "4h": [],
                    "1d": [],
                    "1w": [],
                }
            },
            "measures": {"price": "100"},
        }
        context = _symbol_context(
            source,
            market_observed_at=source["observed_at"],
            decision_at=source["observed_at"],
            news={"queries": {}},
        )
        for timeframe in ("1h", "4h", "1d", "1w"):
            self.assertEqual("UNKNOWN", context["technical"][timeframe]["status"])
            self.assertEqual(0, context["technical"][timeframe]["bar_count"])
            self.assertEqual([], context["recent_closed_bars"][timeframe])

    def test_recent_trades_disclose_variable_time_window(self) -> None:
        rows = [
            {"px": "100", "sz": "2", "side": "buy", "ts": "1785743999000"},
            {"px": "101", "sz": "1", "side": "sell", "ts": "1785743990000"},
        ]
        result = _trade_measures(
            rows,
            contract_value=Decimal("0.1"),
            decision_at="2026-08-03T08:00:00Z",
        )
        self.assertEqual("9", result["window_span_seconds"])
        self.assertEqual("LATEST_N_TRADES_NOT_FIXED_TIME_WINDOW", result["window_semantics"])
        self.assertFalse(result["cross_cycle_comparable"])
        self.assertEqual(100, result["requested_count"])

    def test_static_book_impact_uses_midpoint_and_nonnegative_adverse_legs(self) -> None:
        result = _book_measures(
            {
                "bids": [["99", "20"], ["98", "20"]],
                "asks": [["101", "20"], ["102", "20"]],
            },
            reference_price=110,
            notional=1000,
        )
        self.assertEqual("VALID_TOP_OF_BOOK_MIDPOINT", result["impact_reference"])
        self.assertGreaterEqual(result["buy_1000_impact_bps"], 0)
        self.assertGreaterEqual(result["sell_1000_impact_bps"], 0)
        self.assertAlmostEqual(
            result["buy_1000_impact_bps"], result["sell_1000_impact_bps"]
        )

    def test_interruption_receipt_is_idempotent_and_blocks_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "prospective-run"
            manifest = self_digest(
                {
                    "run_id": "prospective-run",
                    "evidence_class": PROSPECTIVE_EVIDENCE_CLASS,
                },
                "manifest_digest",
            )
            state = self_digest(
                {"run_id": "prospective-run", "revision": 14}, "state_digest"
            )
            receipt = self_digest(
                {
                    "run_id": "prospective-run",
                    "cycle_index": 14,
                    "decision_digest": "d" * 64,
                },
                "receipt_digest",
            )
            write_once_json(root / "manifest.json", manifest)
            write_once_json(root / "states" / "state-0014.json", state)
            write_once_json(root / "receipts" / "cycle-0014.json", receipt)
            write_once_json(
                root / "checkpoint.json",
                {
                    "run_id": "prospective-run",
                    "manifest_digest": manifest["manifest_digest"],
                    "status": "RUNNING_OUTCOMES_SEALED",
                    "completed_cycles": 14,
                    "next_cycle_index": 15,
                    "accepted_state_path": "states/state-0014.json",
                    "accepted_state_digest": state["state_digest"],
                    "pending_agent_context_path": None,
                    "pending_pre_decision_state_path": None,
                    "terminal_receipt_path": None,
                    "recorded_v1_decisions_opened": False,
                    "recorded_v1_outcomes_opened": False,
                },
            )
            first = interrupt_prospective_research(
                run_root=root,
                reason_code="USER_REPORTED_NETWORK_INTERRUPTION",
                recorded_at=datetime(2026, 8, 4, 0, tzinfo=UTC),
            )
            second = interrupt_prospective_research(
                run_root=root,
                reason_code="IGNORED_IDEMPOTENT_RETRY",
                recorded_at=datetime(2026, 8, 4, 1, tzinfo=UTC),
            )
            self.assertEqual(first["interruption_digest"], second["interruption_digest"])
            self.assertEqual(state["state_digest"], first["last_accepted_state_digest"])
            self.assertEqual(
                "INTERRUPTED_OUTCOMES_SEALED",
                load_json_strict(root / "checkpoint.json")["status"],
            )
            with self.assertRaisesRegex(ProspectiveResearchError, "RUN_NOT_COLLECTABLE"):
                collect_next_prospective_cycle(run_root=root, cycle_index=15)

    def test_successor_recovery_requires_exact_sealed_predecessor_binding(self) -> None:
        predecessor_manifest = {
            "run_id": "predecessor-run",
            "manifest_digest": "a" * 64,
        }
        checkpoint = {"status": "INTERRUPTED_OUTCOMES_SEALED"}
        interruption = {
            "resume_allowed": False,
            "interruption_digest": "b" * 64,
            "reason_code": "ACCEPTED_TRUTH_CONFLICT",
        }
        recovery = {
            "mode": "SEALED_PREDECESSOR_TO_FRESH_SUCCESSOR",
            "predecessor_run_id": "predecessor-run",
            "predecessor_manifest_digest": "a" * 64,
            "predecessor_interruption_digest": "b" * 64,
            "predecessor_reason_code": "ACCEPTED_TRUTH_CONFLICT",
            "resume_predecessor": False,
            "reuse_predecessor_state_or_context": False,
            "post_accept_truth_conflict": "SEAL_AND_START_NEW_CHRONOLOGY",
            "bounded_pre_accept_repair_attempts": 2,
        }
        result = _validate_successor_recovery_contract(
            template={"automatic_recovery": recovery},
            predecessor_manifest=predecessor_manifest,
            predecessor_checkpoint=checkpoint,
            interruption=interruption,
        )
        self.assertEqual(2, result["bounded_pre_accept_repair_attempts"])

        recovery["reuse_predecessor_state_or_context"] = True
        with self.assertRaisesRegex(
            ProspectiveResearchError,
            "AUTOMATIC_RECOVERY_BINDING_INVALID:reuse_predecessor_state_or_context",
        ):
            _validate_successor_recovery_contract(
                template={"automatic_recovery": recovery},
                predecessor_manifest=predecessor_manifest,
                predecessor_checkpoint=checkpoint,
                interruption=interruption,
            )

    def test_user_theory_review_suspension_forbids_automatic_successor(self) -> None:
        predecessor_manifest = {
            "run_id": "predecessor-run",
            "manifest_digest": "a" * 64,
        }
        checkpoint = {"status": "INTERRUPTED_OUTCOMES_SEALED"}
        interruption = {
            "resume_allowed": False,
            "successor_creation_authorized": False,
            "interruption_digest": "b" * 64,
            "reason_code": "USER_PAUSED_FOR_THEORY_ROOT_CAUSE_REDESIGN",
        }
        with self.assertRaisesRegex(
            ProspectiveResearchError, "SUCCESSOR_NOT_AUTHORIZED"
        ):
            _validate_successor_recovery_contract(
                template={"automatic_recovery": {}},
                predecessor_manifest=predecessor_manifest,
                predecessor_checkpoint=checkpoint,
                interruption=interruption,
            )


if __name__ == "__main__":
    unittest.main()
