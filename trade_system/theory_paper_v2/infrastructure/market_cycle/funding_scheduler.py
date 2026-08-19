"""Bounded funding scheduler for one admitted HYPE paper interval.

This adapter does not predict funding or create a second ledger.  It converts
one already-admitted, after-window OKX slice into a fully validated transaction
of point accruals plus one non-cash coverage advance.  The application service
then commits that transaction with one ledger CAS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from ...application.market_cycle.paper import (
    PaperLedgerPort,
    PaperTradingService,
    replay_paper_account,
)
from ...domain.contracts.canonical import canonical_decimal, canonical_digest
from ...domain.market_cycle.data import AssetDataSliceV1
from ...domain.market_cycle.paper import (
    CarryAccrualV1,
    FundingCoverageAdvanceV1,
    FundingSettlementModelV1,
    PaperPositionV1,
)


class FundingSchedulerError(RuntimeError):
    """The supplied account, model, or admitted slice is inconsistent."""


@dataclass(frozen=True, slots=True)
class FundingScheduleResultV1:
    status: str
    reason: str
    observed_event_count: int | None
    advance_id: str | None
    account_version: int

    def __post_init__(self) -> None:
        if self.status not in {"COMPLETE", "PARTIAL", "UNKNOWN"}:
            raise FundingSchedulerError("PAPER_FUNDING_RESULT_STATUS_INVALID")
        if not isinstance(self.reason, str) or not self.reason:
            raise FundingSchedulerError("PAPER_FUNDING_RESULT_REASON_INVALID")
        if self.observed_event_count is not None and (
            type(self.observed_event_count) is not int
            or self.observed_event_count < 0
        ):
            raise FundingSchedulerError("PAPER_FUNDING_RESULT_COUNT_INVALID")


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise FundingSchedulerError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FundingSchedulerError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FundingSchedulerError(code)
    return parsed


def _raw_digest(value: Mapping[str, Any], *, code: str) -> str:
    digest = value.get("raw_sha256")
    raw_ref = value.get("raw_ref")
    if (
        not isinstance(digest, str)
        or not isinstance(raw_ref, Mapping)
        or raw_ref.get("sha256") != digest
    ):
        raise FundingSchedulerError(code)
    return digest


def _position(positions: tuple[PaperPositionV1, ...], symbol: str) -> PaperPositionV1:
    return next(
        (item for item in positions if item.symbol == symbol),
        PaperPositionV1(
            symbol=symbol,
            quantity="0",
            average_entry_price="0",
            margin_allocated="0",
            realized_pnl="0",
        ),
    )


class AdmittedSliceFundingScheduler:
    """Book and cover one explicit account window from one immutable slice."""

    def __init__(
        self,
        *,
        ledger: PaperLedgerPort,
        service: PaperTradingService,
    ) -> None:
        if not callable(getattr(ledger, "load_records", None)):
            raise FundingSchedulerError("PAPER_FUNDING_LEDGER_INVALID")
        if not isinstance(service, PaperTradingService):
            raise FundingSchedulerError("PAPER_FUNDING_SERVICE_INVALID")
        self._ledger = ledger
        self._service = service

    def run(
        self,
        *,
        account_id: str,
        coverage_end_at: str,
        data_slice: AssetDataSliceV1,
        settlement_model: FundingSettlementModelV1,
    ) -> FundingScheduleResultV1:
        if not isinstance(data_slice, AssetDataSliceV1):
            raise FundingSchedulerError("PAPER_FUNDING_ADMITTED_SLICE_REQUIRED")
        if not isinstance(settlement_model, FundingSettlementModelV1):
            raise FundingSchedulerError("PAPER_FUNDING_MODEL_REQUIRED")
        records = self._ledger.load_records(account_id)
        state = replay_paper_account(records)
        preexisting_complete = next(
            (
                record
                for record in records
                if record.event_type == "FUNDING_COVERAGE_ADVANCED"
                and isinstance(record.payload.get("advance"), Mapping)
                and record.payload["advance"].get("coverage_end_at")
                == coverage_end_at
                and record.payload["advance"].get("settlement_model")
                == settlement_model.to_dict()
            ),
            None,
        )
        if preexisting_complete is not None:
            return FundingScheduleResultV1(
                status="COMPLETE",
                reason="IDEMPOTENT_REPLAY_OF_COMPLETE_WINDOW",
                observed_event_count=len(
                    preexisting_complete.payload["advance"].get(
                        "event_effective_ats", ()
                    )
                ),
                advance_id=preexisting_complete.event_id,
                account_version=state.version,
            )
        if (
            state.account_mode != "LINEAR_PERP"
            or state.borrow_coverage_status != "NOT_APPLICABLE"
            or data_slice.instrument_identity.venue_symbol
            != state.permitted_symbol
        ):
            raise FundingSchedulerError("PAPER_FUNDING_SCOPE_MISMATCH")
        account_opened_at = records[0].occurred_at
        if state.funding_coverage_status == "COMPLETE":
            if state.funding_coverage_end_at is None:
                raise FundingSchedulerError(
                    "PAPER_FUNDING_DURABLE_CURSOR_MISSING"
                )
            start_at = state.funding_coverage_end_at
        elif (
            state.funding_coverage_status == "UNKNOWN"
            and state.funding_coverage_end_at is None
        ):
            start_at = account_opened_at
        else:
            return FundingScheduleResultV1(
                status="PARTIAL",
                reason="DURABLE_FUNDING_CURSOR_INCOMPLETE",
                observed_event_count=None,
                advance_id=None,
                account_version=state.version,
            )
        start = _moment(start_at, code="PAPER_FUNDING_WINDOW_START_INVALID")
        end = _moment(coverage_end_at, code="PAPER_FUNDING_WINDOW_END_INVALID")
        if not start < end:
            raise FundingSchedulerError("PAPER_FUNDING_WINDOW_NOT_FORWARD")
        if not (
            _moment(
                settlement_model.effective_from,
                code="PAPER_FUNDING_MODEL_START_INVALID",
            )
            <= start
            and end
            <= _moment(
                settlement_model.effective_to,
                code="PAPER_FUNDING_MODEL_END_INVALID",
            )
        ):
            raise FundingSchedulerError("PAPER_FUNDING_MODEL_WINDOW_MISMATCH")

        funding = data_slice.optional_observations.get(
            "okx_funding_rate_history"
        )
        if funding is None:
            return FundingScheduleResultV1(
                status="UNKNOWN",
                reason="OFFICIAL_FUNDING_HISTORY_UNAVAILABLE",
                observed_event_count=None,
                advance_id=None,
                account_version=state.version,
            )
        bars = data_slice.core_observations["closed_15m_bars"]
        funding_available = _moment(
            funding.get("available_at"), code="PAPER_FUNDING_AVAILABLE_AT_INVALID"
        )
        bars_available = _moment(
            bars.get("available_at"), code="PAPER_FUNDING_BARS_AVAILABLE_AT_INVALID"
        )
        sealed_at = _moment(
            data_slice.sealed_at, code="PAPER_FUNDING_SLICE_SEALED_AT_INVALID"
        )
        if min(funding_available, sealed_at) <= end:
            return FundingScheduleResultV1(
                status="PARTIAL",
                reason="AFTER_WINDOW_EVIDENCE_NOT_YET_AVAILABLE",
                observed_event_count=None,
                advance_id=None,
                account_version=state.version,
            )
        raw_rows = funding.get("value")
        if not isinstance(raw_rows, (tuple, list)) or not raw_rows:
            return FundingScheduleResultV1(
                status="UNKNOWN",
                reason="OFFICIAL_FUNDING_HISTORY_INVALID",
                observed_event_count=None,
                advance_id=None,
                account_version=state.version,
            )
        rows: list[Mapping[str, Any]] = []
        times: set[str] = set()
        for item in raw_rows:
            if not isinstance(item, Mapping):
                return FundingScheduleResultV1(
                    "UNKNOWN",
                    "OFFICIAL_FUNDING_HISTORY_INVALID",
                    None,
                    None,
                    state.version,
                )
            effective_at = item.get("provider_as_of")
            if (
                item.get("instrument_id") != state.permitted_symbol
                or not isinstance(effective_at, str)
                or effective_at in times
            ):
                return FundingScheduleResultV1(
                    "UNKNOWN",
                    "OFFICIAL_FUNDING_HISTORY_DUPLICATE_OR_MISMATCHED",
                    None,
                    None,
                    state.version,
                )
            times.add(effective_at)
            rows.append(item)
        before = [item for item in rows if _moment(item["provider_as_of"], code="PAPER_FUNDING_EVENT_TIME_INVALID") < start]
        after = [item for item in rows if _moment(item["provider_as_of"], code="PAPER_FUNDING_EVENT_TIME_INVALID") > end]
        inside = sorted(
            (
                item
                for item in rows
                if start
                <= _moment(item["provider_as_of"], code="PAPER_FUNDING_EVENT_TIME_INVALID")
                <= end
            ),
            key=lambda item: _moment(
                item["provider_as_of"], code="PAPER_FUNDING_EVENT_TIME_INVALID"
            ),
        )
        if not before or not after:
            return FundingScheduleResultV1(
                status="PARTIAL",
                reason="TEN_ROW_HISTORY_DOES_NOT_BRACKET_WINDOW",
                observed_event_count=len(inside),
                advance_id=None,
                account_version=state.version,
            )
        nearest_before = max(
            before,
            key=lambda item: _moment(
                item["provider_as_of"], code="PAPER_FUNDING_EVENT_TIME_INVALID"
            ),
        )["provider_as_of"]
        nearest_after = min(
            after,
            key=lambda item: _moment(
                item["provider_as_of"], code="PAPER_FUNDING_EVENT_TIME_INVALID"
            ),
        )["provider_as_of"]
        if _moment(nearest_after, code="PAPER_FUNDING_BOUNDARY_INVALID") > funding_available:
            return FundingScheduleResultV1(
                "PARTIAL",
                "AFTER_BOUNDARY_NOT_YET_AVAILABLE",
                len(inside),
                None,
                state.version,
            )

        bar_rows = bars.get("value")
        if not isinstance(bar_rows, (tuple, list)) or not bar_rows:
            return FundingScheduleResultV1(
                "UNKNOWN",
                "PRICE_PROXY_HISTORY_UNAVAILABLE",
                len(inside),
                None,
                state.version,
            )
        closed = tuple(item for item in bar_rows if isinstance(item, Mapping))
        if len(closed) != len(bar_rows):
            return FundingScheduleResultV1(
                "UNKNOWN",
                "PRICE_PROXY_HISTORY_INVALID",
                len(inside),
                None,
                state.version,
            )
        funding_sha256 = _raw_digest(
            funding, code="PAPER_FUNDING_RAW_BINDING_INVALID"
        )
        bars_sha256 = _raw_digest(
            bars, code="PAPER_FUNDING_BARS_RAW_BINDING_INVALID"
        )
        available_at = max(
            (
                funding.get("available_at"),
                bars.get("available_at"),
                data_slice.sealed_at,
                state.last_fact_at,
            ),
            key=lambda value: _moment(
                value, code="PAPER_FUNDING_FACT_TIME_INVALID"
            ),
        )

        accruals: list[CarryAccrualV1] = []
        for row in inside:
            effective_at = str(row["provider_as_of"])
            eligible = [
                item
                for item in closed
                if isinstance(item.get("closed_at"), str)
                and _moment(item["closed_at"], code="PAPER_FUNDING_BAR_TIME_INVALID")
                <= _moment(effective_at, code="PAPER_FUNDING_EVENT_TIME_INVALID")
            ]
            if not eligible:
                return FundingScheduleResultV1(
                    "PARTIAL",
                    "PRICE_PROXY_MISSING_FOR_SETTLEMENT_EVENT",
                    len(inside),
                    None,
                    state.version,
                )
            proxy = max(
                eligible,
                key=lambda item: _moment(
                    item["closed_at"], code="PAPER_FUNDING_BAR_TIME_INVALID"
                ),
            )
            rate = row.get("realized_rate", row.get("funding_rate"))
            reference_price = proxy.get("close")
            if not isinstance(rate, str) or not isinstance(reference_price, str):
                return FundingScheduleResultV1(
                    "UNKNOWN",
                    "SETTLEMENT_RATE_OR_PRICE_INVALID",
                    len(inside),
                    None,
                    state.version,
                )
            effective_records = tuple(
                record
                for record in records
                if _moment(record.occurred_at, code="PAPER_FUNDING_LEDGER_TIME_INVALID")
                <= _moment(effective_at, code="PAPER_FUNDING_EVENT_TIME_INVALID")
            )
            if not effective_records:
                raise FundingSchedulerError("PAPER_FUNDING_EFFECTIVE_STATE_UNKNOWN")
            effective_state = replay_paper_account(effective_records)
            quantity = _position(
                effective_state.positions, state.permitted_symbol
            ).quantity
            amount = canonical_decimal(
                Decimal(quantity)
                * Decimal(effective_state.instrument_spec.contract_multiplier)
                * Decimal(reference_price)
                * Decimal(rate)
            )
            identity = {
                "account_id": account_id,
                "symbol": state.permitted_symbol,
                "effective_at": effective_at,
                "model_digest": settlement_model.model_digest,
                "rate_source_sha256": funding_sha256,
                "price_source_sha256": bars_sha256,
            }
            accruals.append(
                CarryAccrualV1(
                    accrual_id=f"funding-{canonical_digest(identity)[:32]}",
                    account_id=account_id,
                    symbol=state.permitted_symbol,
                    kind="FUNDING",
                    status="OBSERVED",
                    amount=amount,
                    rate=rate,
                    reference_price=reference_price,
                    position_quantity=quantity,
                    effective_at=effective_at,
                    available_at=available_at,
                    rate_source_sha256=funding_sha256,
                    price_source_sha256=bars_sha256,
                    reason=(
                        "Official realized funding; price proxy is the last "
                        "confirmed 15m close not after effective_at."
                    ),
                    coverage_status="PARTIAL",
                    coverage_start_at=effective_at,
                    coverage_end_at=effective_at,
                    settlement_model=settlement_model,
                    price_proxy_observed_at=str(proxy["closed_at"]),
                )
            )

        advance_payload = {
            "account_id": account_id,
            "symbol": state.permitted_symbol,
            "coverage_start_at": start_at,
            "coverage_end_at": coverage_end_at,
            "available_at": available_at,
            "settlement_model": settlement_model.to_dict(),
            "funding_history_source_sha256": funding_sha256,
            "price_proxy_source_sha256": bars_sha256,
            "history_boundary_before_at": nearest_before,
            "history_boundary_after_at": nearest_after,
            "event_effective_ats": [item.effective_at for item in accruals],
            "event_accrual_sha256s": [
                canonical_digest(item.to_dict()) for item in accruals
            ],
        }
        advance = FundingCoverageAdvanceV1(
            advance_id=f"funding-coverage-{canonical_digest(advance_payload)[:32]}",
            **advance_payload,
        )
        state = self._service.settle_funding_window(
            account_id=account_id,
            expected_account_version=state.version,
            accruals=tuple(accruals),
            advance=advance,
        )
        return FundingScheduleResultV1(
            status="COMPLETE",
            reason="ALL_ENUMERATED_SETTLEMENTS_BOOKED_AND_WINDOW_BRACKETED",
            observed_event_count=len(accruals),
            advance_id=advance.advance_id,
            account_version=state.version,
        )


__all__ = [
    "AdmittedSliceFundingScheduler",
    "FundingScheduleResultV1",
    "FundingSchedulerError",
]
