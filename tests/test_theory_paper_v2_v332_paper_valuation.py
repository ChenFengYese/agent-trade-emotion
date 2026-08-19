from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from trade_system.theory_paper_v2.application.market_cycle.paper_valuation import (
    PaperValuationError,
    project_paper_valuation,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    InstrumentSpecV1,
    PaperAccountVersionV1,
    PaperContractError,
    PaperMarketSliceV1,
    PaperPositionV1,
)


def _account(
    *,
    mode: str = "LINEAR_PERP",
    cash: str = "100",
    quantity: str = "1",
    entry: str = "100",
    margin: str = "20",
    carry_coverage_status: str = "UNKNOWN",
    modeled_liquidation_risk: bool = False,
) -> PaperAccountVersionV1:
    symbol = "HYPE-USDT-SWAP"
    return PaperAccountVersionV1(
        account_id="hype-paper",
        version=1,
        account_mode=mode,
        owner_logical_agent_id="hype-trader",
        base_currency="USDT",
        permitted_symbol=symbol,
        max_leverage="5",
        instrument_spec=InstrumentSpecV1(
            instrument_spec_id="okx-hype-linear-v1",
            symbol=symbol,
            account_mode=mode,
            quote_currency="USDT",
            contract_multiplier="1",
            quantity_basis="BASE_UNITS",
            maintenance_margin_rate="0.1" if modeled_liquidation_risk else None,
            maintenance_margin_deduction="2" if modeled_liquidation_risk else None,
            liquidation_fee_reserve="1" if modeled_liquidation_risk else None,
            risk_parameter_status=(
                "MODELED_EXPLICIT_PARAMETERS"
                if modeled_liquidation_risk
                else "UNKNOWN"
            ),
            risk_parameter_set_id=(
                "paper-risk-parameters-v1" if modeled_liquidation_risk else None
            ),
            parameter_status="OBSERVED_RAW_BOUND",
            parameter_source_sha256="0" * 64,
        ),
        owner_agent_generation=1,
        initial_balance="100",
        cash_balance=cash,
        reserved_margin=margin,
        realized_pnl="0",
        fees_paid="0",
        funding_paid="0",
        borrow_paid="0",
        carry_coverage_status=carry_coverage_status,
        funding_coverage_status=(
            "NOT_APPLICABLE"
            if mode == "CASH_SPOT"
            else carry_coverage_status
        ),
        borrow_coverage_status="NOT_APPLICABLE",
        funding_coverage_start_at=(
            "2026-08-12T11:00:00+00:00"
            if mode == "LINEAR_PERP"
            and carry_coverage_status in {"COMPLETE", "PARTIAL"}
            else None
        ),
        funding_coverage_end_at=(
            "2026-08-12T13:00:00+00:00"
            if mode == "LINEAR_PERP"
            and carry_coverage_status in {"COMPLETE", "PARTIAL"}
            else None
        ),
        borrow_coverage_start_at=None,
        borrow_coverage_end_at=None,
        positions=(
            PaperPositionV1(
                symbol=symbol,
                quantity=quantity,
                average_entry_price=entry,
                margin_allocated=margin,
                realized_pnl="0",
            ),
        ),
        orders=(),
        applied_command_ids=(),
        last_event_id="event-1",
        last_fact_at="2026-08-12T12:00:00+00:00",
        last_market_observed_at=None,
        last_market_available_at=None,
        last_market_source_sha256=None,
    )


def _mark(
    minute: int,
    value: str | None,
    *,
    path_status: str = "ORDERED",
    digest_character: str = "0",
) -> PaperMarketSliceV1:
    timestamp = f"2026-08-12T12:{minute:02d}:00+00:00"
    return PaperMarketSliceV1(
        symbol="HYPE-USDT-SWAP",
        observed_at=timestamp,
        available_at=timestamp,
        source_sha256=digest_character * 64,
        granularity="MARK" if value is not None else "QUOTE",
        path_status=path_status,
        bid=None if value is not None else "99",
        ask=None if value is not None else "101",
        mark=value,
    )


class V332PaperValuationTests(unittest.TestCase):
    def test_linear_projection_replays_known_marks_and_keeps_unknown_carry_open(self) -> None:
        account = _account(modeled_liquidation_risk=True)
        marks = (_mark(2, "108", digest_character="2"), _mark(0, "100"), _mark(1, "120", digest_character="1"))

        result = project_paper_valuation(
            account,
            marks,
            carry_coverage_status="UNKNOWN",
        )
        replay = project_paper_valuation(
            account,
            tuple(reversed(marks)),
            carry_coverage_status="UNKNOWN",
        )

        self.assertEqual(result.to_dict(), replay.to_dict())
        self.assertEqual(result.status, "PARTIAL_UNKNOWN_CARRY_COSTS")
        self.assertEqual(result.mark, "108")
        self.assertEqual(result.unrealized_pnl, "8")
        self.assertEqual(result.equity_before_unknown_costs, "108")
        self.assertIsNone(result.complete_equity)
        self.assertEqual(result.gross_exposure, "108")
        self.assertEqual(result.effective_leverage, "1")
        self.assertEqual(result.peak_equity, "120")
        self.assertEqual(result.current_drawdown, "0.1")
        self.assertEqual(result.observed_max_drawdown, "0.1")
        self.assertEqual(result.drawdown_unit, "FRACTION")
        self.assertIsNone(result.liquidation_buffer)
        self.assertEqual(
            result.liquidation_buffer_status, "UNKNOWN_CARRY_COSTS"
        )
        self.assertEqual(
            result.drawdown_status, "OBSERVED_BEFORE_UNKNOWN_CARRY_COSTS"
        )
        self.assertEqual(result.actual_cost_effect_status, "UNKNOWN_NOT_EVALUATED")

    def test_complete_carry_exposes_complete_equity_without_double_deduction(self) -> None:
        result = project_paper_valuation(
            _account(
                carry_coverage_status="COMPLETE",
                modeled_liquidation_risk=True,
            ),
            (_mark(2, "108"),),
            carry_coverage_status="COMPLETE",
        )

        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.equity_before_unknown_costs, "108")
        self.assertEqual(result.complete_equity, "108")
        self.assertEqual(result.liquidation_buffer, "98.2")
        self.assertEqual(
            result.liquidation_buffer_status, "MODELED_EXPLICIT_PARAMETERS"
        )
        breached = project_paper_valuation(
            _account(
                cash="5",
                carry_coverage_status="COMPLETE",
                modeled_liquidation_risk=True,
            ),
            (_mark(2, "1"),),
        )
        self.assertLess(Decimal(breached.liquidation_buffer), 0)
        self.assertEqual(
            breached.liquidation_buffer_status,
            "BREACHED_MODELED_EXPLICIT_PARAMETERS",
        )

    def test_cash_spot_equity_is_cash_plus_marked_inventory(self) -> None:
        result = project_paper_valuation(
            _account(
                mode="CASH_SPOT",
                cash="50",
                entry="50",
                margin="0",
                carry_coverage_status="NOT_APPLICABLE",
                modeled_liquidation_risk=True,
            ),
            (_mark(0, "50"),),
            carry_coverage_status="NOT_APPLICABLE",
        )

        self.assertEqual(result.unrealized_pnl, "0")
        self.assertEqual(result.equity_before_unknown_costs, "100")
        self.assertEqual(result.complete_equity, "100")
        self.assertEqual(result.gross_exposure, "50")
        self.assertEqual(result.effective_leverage, "0.5")
        self.assertEqual(
            result.liquidation_buffer_status, "NOT_APPLICABLE_CASH_SPOT"
        )
        self.assertIsNone(result.liquidation_buffer)

    def test_signed_short_pnl_and_absolute_gross_exposure_are_separate(self) -> None:
        result = project_paper_valuation(
            _account(quantity="-1"),
            (_mark(0, "90"),),
            carry_coverage_status="UNKNOWN",
        )

        self.assertEqual(result.unrealized_pnl, "10")
        self.assertEqual(result.equity_before_unknown_costs, "110")
        self.assertEqual(result.gross_exposure, "90")
        self.assertEqual(
            Decimal(result.effective_leverage), Decimal("90") / Decimal("110")
        )

    def test_missing_mark_returns_typed_unknown_instead_of_using_last_or_mid(self) -> None:
        result = project_paper_valuation(
            _account(),
            (_mark(0, None),),
            carry_coverage_status="UNKNOWN",
        )

        self.assertEqual(result.status, "UNKNOWN_NO_EXPLICIT_MARK")
        self.assertIsNone(result.mark)
        self.assertIsNone(result.unrealized_pnl)
        self.assertIsNone(result.equity_before_unknown_costs)
        self.assertIsNone(result.gross_exposure)
        self.assertEqual(
            result.drawdown_status, "UNKNOWN_NO_KNOWN_VALUATION_POINT"
        )

    def test_unordered_or_conflicting_path_never_creates_favorable_drawdown(self) -> None:
        unordered = project_paper_valuation(
            _account(),
            (_mark(0, "100"), _mark(1, "90", path_status="UNORDERED")),
            carry_coverage_status="UNKNOWN",
        )
        self.assertEqual(unordered.mark, "90")
        self.assertIsNone(unordered.current_drawdown)
        self.assertIsNone(unordered.observed_max_drawdown)
        self.assertEqual(unordered.drawdown_status, "UNKNOWN_UNORDERED_MARK_PATH")

        conflict = (
            _mark(0, "100"),
            _mark(0, "101", digest_character="1"),
        )
        with self.assertRaisesRegex(PaperValuationError, "conflicting MARK"):
            project_paper_valuation(
                _account(), conflict, carry_coverage_status="UNKNOWN"
            )

    def test_invalid_partial_liquidation_or_carry_parameters_fail_closed(self) -> None:
        with self.assertRaisesRegex(PaperContractError, "must not exceed one"):
            InstrumentSpecV1(
                instrument_spec_id="invalid-risk-parameters-v1",
                symbol="HYPE-USDT-SWAP",
                account_mode="LINEAR_PERP",
                quote_currency="USDT",
                contract_multiplier="0.1",
                quantity_basis="CONTRACTS",
                maintenance_margin_rate="1.1",
                maintenance_margin_deduction="0",
                liquidation_fee_reserve="0",
                risk_parameter_status="MODELED_EXPLICIT_PARAMETERS",
                risk_parameter_set_id="invalid-risk-set-v1",
                parameter_status="OBSERVED_RAW_BOUND",
                parameter_source_sha256="0" * 64,
            )
        with self.assertRaisesRegex(PaperValuationError, "carry_coverage_status"):
            project_paper_valuation(
                _account(), (_mark(0, "100"),), carry_coverage_status="ASSUMED_ZERO"
            )
        with self.assertRaisesRegex(PaperValuationError, "must match"):
            project_paper_valuation(
                _account(), (_mark(0, "100"),), carry_coverage_status="COMPLETE"
            )

    def test_account_history_prevents_future_position_from_leaking_into_prior_drawdown(self) -> None:
        current = replace(
            _account(carry_coverage_status="COMPLETE"),
            version=9,
            last_event_id="event-9",
            last_fact_at="2026-08-12T12:02:00+00:00",
        )
        flat = replace(
            current,
            version=1,
            reserved_margin="0",
            positions=(
                PaperPositionV1(
                    symbol="HYPE-USDT-SWAP",
                    quantity="0",
                    average_entry_price="0",
                    margin_allocated="0",
                    realized_pnl="0",
                ),
            ),
            last_event_id="event-1",
            last_fact_at="2026-08-12T12:00:00+00:00",
        )
        marks = (_mark(1, "80"), _mark(3, "90", digest_character="3"))

        replayed = project_paper_valuation(
            current,
            marks,
            account_history=(flat, current),
        )

        self.assertEqual(replayed.equity_before_unknown_costs, "90")
        self.assertEqual(replayed.peak_equity, "100")
        self.assertEqual(replayed.observed_max_drawdown, "0.1")
        self.assertEqual(
            replayed.drawdown_status, "OBSERVED_REPLAYED_ACCOUNT_MARK_POINTS"
        )

    def test_complete_carry_label_does_not_cover_a_later_mark_without_window_evidence(self) -> None:
        account = replace(
            _account(carry_coverage_status="COMPLETE"),
            funding_coverage_end_at="2026-08-12T12:01:00+00:00",
        )

        result = project_paper_valuation(account, (_mark(2, "108"),))

        self.assertEqual(result.carry_coverage_status, "COMPLETE")
        self.assertEqual(
            result.carry_coverage_at_mark_status, "INCOMPLETE_AT_MARK"
        )
        self.assertIsNone(result.complete_equity)
        self.assertEqual(result.status, "PARTIAL_UNKNOWN_CARRY_COSTS")

    def test_drawdown_requires_account_history_after_the_open_version(self) -> None:
        account = replace(
            _account(),
            version=7,
            last_event_id="event-7",
        )

        result = project_paper_valuation(
            account,
            (_mark(1, "120"), _mark(2, "108")),
        )

        self.assertIsNone(result.peak_equity)
        self.assertIsNone(result.current_drawdown)
        self.assertIsNone(result.observed_max_drawdown)
        self.assertEqual(
            result.drawdown_status, "UNKNOWN_ACCOUNT_HISTORY_REQUIRED"
        )


if __name__ == "__main__":
    unittest.main()
