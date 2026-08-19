from __future__ import annotations

from dataclasses import replace
import unittest

from trade_system.theory_paper_v2.application.market_cycle.position import (
    PositionPathEvaluationError,
    evaluate_static_no_transition_path,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    InstrumentSpecV1,
    PaperBracketV1,
    PaperCommandV1,
    PaperCostModelV1,
    PaperExecutionIntentV1,
    StaticNoTransitionComparatorV1,
)


def _command(
    command_id: str,
    *,
    command_type: str,
    side: str,
    quantity: str,
    limit_price: str | None = None,
    trigger_price: str | None = None,
    reduce_only: bool = False,
    expires_at: str = "2026-08-13T09:00:00Z",
) -> PaperCommandV1:
    return PaperCommandV1(
        command_id=command_id,
        account_id="position-path-paper",
        logical_agent_id="POSITION_AGENT",
        agent_generation=1,
        decision_cycle_id="position-path-decision-1",
        decision_sha256="1" * 64,
        expected_account_version=1,
        symbol="HYPE-USDT-SWAP",
        command_type=command_type,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        trigger_price=trigger_price,
        target_order_id=None,
        reduce_only=reduce_only,
        time_in_force="GTC",
        submitted_at="2026-08-13T08:01:00Z",
        expires_at=expires_at,
        cost_model_id="static-cost-v1",
    )


def _comparator(
    *, entry_expires_at: str = "2026-08-13T09:00:00Z"
) -> StaticNoTransitionComparatorV1:
    entry = _command(
        "position-entry",
        command_type="LIMIT",
        side="BUY",
        quantity="2",
        limit_price="100",
        expires_at=entry_expires_at,
    )
    stop = _command(
        "position-stop",
        command_type="STOP_LOSS",
        side="SELL",
        quantity="2",
        trigger_price="95",
        reduce_only=True,
    )
    target_one = _command(
        "position-tp-1",
        command_type="TAKE_PROFIT",
        side="SELL",
        quantity="1",
        trigger_price="105",
        reduce_only=True,
    )
    target_two = replace(
        target_one,
        command_id="position-tp-2",
        trigger_price="110",
    )
    bracket = PaperBracketV1(
        bracket_id=entry.command_id,
        entry=entry,
        protective_stop=stop,
        take_profits=(target_one, target_two),
    )
    intent = PaperExecutionIntentV1(
        intent_id=entry.command_id,
        execution_intent_request_sha256="2" * 64,
        decision_request_sha256="3" * 64,
        paper_context_sha256="4" * 64,
        ledger_head_record_sha256="5" * 64,
        decision_cycle_id=entry.decision_cycle_id,
        decision_sha256=entry.decision_sha256,
        account_id=entry.account_id,
        logical_agent_id=entry.logical_agent_id,
        agent_generation=entry.agent_generation,
        expected_account_version=entry.expected_account_version,
        symbol=entry.symbol,
        authored_at=entry.submitted_at,
        valid_until="2026-08-13T09:00:00Z",
        action="OPEN",
        episode_id="position-episode-1",
        transition_id="position-transition-1",
        tranche_id="position-core-1",
        role="CORE",
        pre_state={"status": "FLAT", "signed_quantity": "0"},
        target_state={"status": "ACTIVE", "signed_quantity": "2"},
        position_delta={"action": "OPEN", "signed_quantity_change": "2"},
        evidence_delta="The Agent-authored entry condition is active.",
        activation="Submit this exact protected local-paper bracket.",
        hard_invalidation="The protective stop remains fixed at 95.",
        risk_budget={
            "maximum_loss": "20",
            "notional_cap": "500",
            "max_observed_drawdown": "50",
        },
        command=entry,
        bracket=bracket,
    )
    return StaticNoTransitionComparatorV1.create(
        execution_intent=intent,
        preregistered_at="2026-08-13T08:01:30Z",
        account_pre_version=1,
        account_pre_head_record_sha256="5" * 64,
        instrument_spec=InstrumentSpecV1(
            instrument_spec_id="hype-base-v1",
            symbol="HYPE-USDT-SWAP",
            account_mode="CASH_SPOT",
            quote_currency="USDT",
            contract_multiplier="1",
            quantity_basis="BASE_UNITS",
        ),
        cost_model=PaperCostModelV1(
            model_id="static-cost-v1",
            maker_fee_bps="2",
            taker_fee_bps="5",
            market_impact_bps="3",
            funding_status="UNKNOWN",
            borrow_status="NOT_APPLICABLE",
        ),
    )


def _path(*, first_low: str = "99", first_high: str = "103", status: str = "ORDERED"):
    values = (
        ("2026-08-13T08:15:00Z", "2026-08-13T08:30:00Z", "101", first_high, first_low, "102"),
        ("2026-08-13T08:30:00Z", "2026-08-13T08:45:00Z", "102", "106", "100", "104"),
        ("2026-08-13T08:45:00Z", "2026-08-13T09:00:00Z", "104", "107", "101", "106"),
    )
    points = [
        {
            "sequence_index": index,
            "opened_at": opened,
            "closed_at": closed,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "confirmed_closed": True,
            "available_at": "2026-08-13T09:00:01Z",
            "raw_sha256": "6" * 64,
        }
        for index, (opened, closed, open_price, high, low, close) in enumerate(values)
    ]
    return {
        "schema_id": "agent_trade_emotion_v332_ordered_outcome_path",
        "schema_version": "1.0.0",
        "status": status,
        "path_start_at": "2026-08-13T08:01:00Z",
        "path_end_at": "2026-08-13T09:00:00Z",
        "interval": "15m",
        "intrabar_order": "UNRESOLVED_WITHIN_BAR",
        "points": points if status == "ORDERED" else [],
        "coverage": {
            "expected_point_count": len(points),
            "observed_point_count": len(points) if status == "ORDERED" else 0,
            "gap_count": 0 if status == "ORDERED" else len(points),
            "covers_all_closed_intervals": status == "ORDERED",
        },
        "missing_reason": None if status == "ORDERED" else "PATH_CAPTURE_FAILED",
    }


class V332StaticPositionPathTests(unittest.TestCase):
    def test_ordered_path_produces_bar_envelope_first_touch_and_static_endpoint(self) -> None:
        comparator = _comparator()
        result = evaluate_static_no_transition_path(comparator, _path()).to_dict()

        self.assertEqual("OBSERVED", result["status"])
        self.assertEqual("IDEALIZED_STATIC_REFERENCE", result["reference_kind"])
        self.assertEqual("NOT_COMPARABLE", result["comparison_status"])
        self.assertEqual(
            "NO_MATCHED_ACTUAL_SAME_FILL_COST_ARM",
            result["comparison_reason"],
        )
        self.assertEqual("BAR_TOUCH_REFERENCE", result["entry"]["status"])
        # The bar that first touches entry is not a valid post-entry envelope:
        # OHLC cannot order the pre-entry and post-entry portions of that bar.
        self.assertEqual("0", result["mae"]["price_excursion"])
        self.assertEqual("7", result["mfe"]["price_excursion"])
        self.assertEqual("TAKE_PROFIT_SET", result["first_touch"]["kind"])
        self.assertEqual(["position-tp-1"], result["first_touch"]["order_ids"])
        self.assertEqual("12", result["static_endpoint"]["gross_pnl"])
        self.assertEqual("1.2", result["static_endpoint"]["gross_r_multiple"])
        self.assertEqual(
            "IDEALIZED_STATIC_REFERENCE", result["static_endpoint"]["status"]
        )
        self.assertEqual("UNKNOWN", result["costs"]["funding_status"])
        self.assertEqual("UNKNOWN", result["costs"]["net_pnl_status"])
        self.assertIsNone(result["costs"]["net_pnl"])

    def test_same_post_entry_bar_stop_and_target_never_guesses_order(self) -> None:
        path = _path()
        path["points"][1]["low"] = "94"
        result = evaluate_static_no_transition_path(_comparator(), path).to_dict()

        self.assertEqual("UNRESOLVED_WITHIN_BAR", result["status"])
        self.assertEqual("UNRESOLVED_WITHIN_BAR", result["first_touch"]["status"])
        self.assertEqual("STOP_AND_TAKE_PROFIT", result["first_touch"]["kind"])
        self.assertCountEqual(
            ["position-stop", "position-tp-1"],
            result["first_touch"]["order_ids"],
        )

    def test_entry_and_exit_touch_in_entry_bar_is_unresolved(self) -> None:
        result = evaluate_static_no_transition_path(
            _comparator(), _path(first_high="106")
        ).to_dict()

        self.assertEqual("UNRESOLVED_WITHIN_BAR", result["status"])
        self.assertEqual("ENTRY_EXIT_ORDER_UNKNOWN", result["reason"])
        self.assertEqual(
            "ENTRY_AND_TAKE_PROFIT_SET", result["first_touch"]["kind"]
        )
        self.assertCountEqual(
            ["position-entry", "position-tp-1"],
            result["first_touch"]["order_ids"],
        )
        self.assertEqual("NOT_EVALUATED", result["static_endpoint"]["status"])
        self.assertEqual("NOT_COMPARABLE", result["comparison_status"])

    def test_entry_touch_in_expiry_crossing_bar_is_unresolved(self) -> None:
        result = evaluate_static_no_transition_path(
            _comparator(entry_expires_at="2026-08-13T08:20:00Z"),
            _path(),
        ).to_dict()

        self.assertEqual("UNRESOLVED_WITHIN_BAR", result["status"])
        self.assertEqual("ENTRY_TOUCH_TIME_VS_EXPIRY_UNKNOWN", result["reason"])
        self.assertEqual("ENTRY_VS_EXPIRY", result["first_touch"]["kind"])
        self.assertEqual("UNRESOLVED_WITHIN_BAR", result["entry"]["status"])
        self.assertEqual("NOT_COMPARABLE", result["comparison_status"])

    def test_missing_path_is_censored_and_semantic_tamper_raises(self) -> None:
        censored = evaluate_static_no_transition_path(
            _comparator(), _path(status="CENSORED")
        ).to_dict()
        self.assertEqual("CENSORED", censored["status"])
        self.assertEqual("PATH_CAPTURE_FAILED", censored["reason"])

        tampered = _path()
        tampered["points"][1]["low"] = "108"
        with self.assertRaisesRegex(PositionPathEvaluationError, "geometry"):
            evaluate_static_no_transition_path(_comparator(), tampered)


if __name__ == "__main__":
    unittest.main()
