"""Normalization and deterministic quality gates for frozen hourly data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ...domain.contracts.canonical import canonical_decimal, canonical_digest
from .model import (
    AvailabilityBasis,
    AvailabilityStatus,
    CollectedPublicResponses,
    DatasetQualityReceipt,
    DerivedMarketBar,
    FieldStatus,
    HistoricalReplayAdmissibilityReceipt,
    HourlyDecisionSlot,
    InterfaceField,
    NormalizedHourlyBar,
    OutcomeBinding,
    PublicRequestCapture,
    QualityCheck,
    QualityStatus,
)


_HOUR_MS = 3_600_000
_CONTEMPORANEOUS_UNKNOWN = "ARCHIVE_CAPTURE_AFTER_HISTORICAL_DECISION"
FORMAL_EXPERIMENT_CONTRACT_DIGEST = (
    "92a3ef3cfb150e6f17bbc0ded71bdb5674531effab05990084e366397344ec3a"
)
FORMAL_CLOSED_BAR_COUNT = 256
FORMAL_WARMUP_BAR_COUNT = 96
FORMAL_DECISION_INDEX_START = 96
FORMAL_DECISION_INDEX_END = 191
FORMAL_OUTCOME_HORIZONS = (1, 4, 8, 24)
BINANCE_PROVIDER_ID = "BINANCE_USDM_OFFICIAL_PUBLIC_API"
OKX_PROVIDER_ID = "OKX_OFFICIAL_PUBLIC_API"
_BINANCE_BASE_URL = "https://fapi.binance.com"
_OKX_BASE_URL = "https://www.okx.com"


class FreshMarketQualityError(ValueError):
    """Malformed inputs that cannot safely enter a quality receipt."""


def _decode_json_any(raw: bytes) -> object:
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FreshMarketQualityError("JSON_UTF8_INVALID") from exc

    def reject_float(_: str) -> None:
        raise FreshMarketQualityError("BINARY_FLOAT_FORBIDDEN")

    def reject_constant(_: str) -> None:
        raise FreshMarketQualityError("NONFINITE_NUMBER_FORBIDDEN")

    def unique_object(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise FreshMarketQualityError("JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        return json.loads(
            source,
            object_pairs_hook=unique_object,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except FreshMarketQualityError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise FreshMarketQualityError("JSON_INVALID") from exc


def _utc_from_ms(value: int) -> datetime:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        milliseconds=value
    )


def _decimal(raw: object, *, nonnegative: bool = False) -> tuple[Decimal, str]:
    if not isinstance(raw, str) or not raw:
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID") from exc
    if not value.is_finite() or (nonnegative and value < 0):
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    return value, canonical_decimal(value)


def _record_digest(capture: PublicRequestCapture) -> str:
    payload = capture.to_dict()
    payload.pop("record_digest")
    return canonical_digest(payload)


def _request_identity(capture: PublicRequestCapture) -> str:
    return canonical_digest(
        {
            "method": capture.method,
            "base_url": capture.base_url,
            "path": capture.path,
            "query": [
                {"name": name, "value": value}
                for name, value in capture.query
            ],
        }
    )


def _bar_content_payload(
    *,
    open_time_ms: int,
    close_time_ms: int,
    open_value: str,
    high_value: str,
    low_value: str,
    close_value: str,
    volume: str,
    quote_volume: str,
    trade_count: int | None,
    taker_base: str | None,
    taker_quote: str | None,
    ignored: str,
) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "open_time_ms": open_time_ms,
        "close_time_ms": close_time_ms,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "volume": volume,
        "quote_asset_volume": quote_volume,
        "trade_count": trade_count,
        "taker_buy_base_volume": taker_base,
        "taker_buy_quote_volume": taker_quote,
        "provider_ignored_field": ignored,
    }


def _normalize_bar(
    row: object,
    *,
    capture: PublicRequestCapture,
    provider_id: str,
) -> NormalizedHourlyBar:
    if provider_id == BINANCE_PROVIDER_ID:
        if not isinstance(row, list) or len(row) != 12:
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
        open_time_ms, close_time_ms = row[0], row[6]
        trade_count = row[8]
        if (
            not isinstance(open_time_ms, int)
            or isinstance(open_time_ms, bool)
            or not isinstance(close_time_ms, int)
            or isinstance(close_time_ms, bool)
            or not isinstance(trade_count, int)
            or isinstance(trade_count, bool)
            or trade_count < 0
        ):
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
        volume_raw = row[5]
        quote_volume_raw = row[7]
        taker_base_raw = row[9]
        taker_quote_raw = row[10]
        _, ignored = _decimal(row[11])
    elif provider_id == OKX_PROVIDER_ID:
        if (
            not isinstance(row, list)
            or len(row) != 9
            or not all(isinstance(value, str) for value in row)
            or row[8] != "1"
        ):
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
        try:
            open_time_ms = int(row[0])
        except ValueError as exc:
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID") from exc
        close_time_ms = open_time_ms + _HOUR_MS - 1
        trade_count = None
        # For OKX derivatives, volCcy is base-currency volume and
        # volCcyQuote is quote-currency volume. Raw ``vol`` is contracts.
        _decimal(row[5], nonnegative=True)
        volume_raw = row[6]
        quote_volume_raw = row[7]
        taker_base_raw = None
        taker_quote_raw = None
        ignored = row[8]
    else:
        raise FreshMarketQualityError("EVIDENCE_SOURCE_UNREGISTERED")
    if (
        close_time_ms - open_time_ms != _HOUR_MS - 1
        or open_time_ms % _HOUR_MS != 0
    ):
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    open_decimal, open_value = _decimal(row[1], nonnegative=True)
    high_decimal, high_value = _decimal(row[2], nonnegative=True)
    low_decimal, low_value = _decimal(row[3], nonnegative=True)
    close_decimal, close_value = _decimal(row[4], nonnegative=True)
    volume_decimal, volume = _decimal(volume_raw, nonnegative=True)
    quote_decimal, quote_volume = _decimal(
        quote_volume_raw, nonnegative=True
    )
    if taker_base_raw is None or taker_quote_raw is None:
        taker_base_decimal = None
        taker_quote_decimal = None
        taker_base = None
        taker_quote = None
    else:
        taker_base_decimal, taker_base = _decimal(
            taker_base_raw, nonnegative=True
        )
        taker_quote_decimal, taker_quote = _decimal(
            taker_quote_raw, nonnegative=True
        )
    if (
        min(open_decimal, high_decimal, low_decimal, close_decimal) <= 0
        or high_decimal < max(open_decimal, close_decimal, low_decimal)
        or low_decimal > min(open_decimal, close_decimal, high_decimal)
        or (
            taker_base_decimal is not None
            and taker_base_decimal > volume_decimal
        )
        or (
            taker_quote_decimal is not None
            and taker_quote_decimal > quote_decimal
        )
    ):
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    observed_at = _utc_from_ms(close_time_ms)
    available_at = _utc_from_ms(close_time_ms + 1)
    content = _bar_content_payload(
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open_value=open_value,
        high_value=high_value,
        low_value=low_value,
        close_value=close_value,
        volume=volume,
        quote_volume=quote_volume,
        trade_count=trade_count,
        taker_base=taker_base,
        taker_quote=taker_quote,
        ignored=ignored,
    )
    return NormalizedHourlyBar(
        bar_id=f"BTCUSDT-1h-{open_time_ms}",
        symbol="BTCUSDT",
        interval="1h",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=volume,
        quote_asset_volume=quote_volume,
        trade_count=trade_count,
        taker_buy_base_volume=taker_base,
        taker_buy_quote_volume=taker_quote,
        provider_ignored_field=ignored,
        observed_at=observed_at,
        available_at=available_at,
        captured_at=capture.response_received_at,
        availability_status=AvailabilityStatus.DERIVED,
        availability_basis=AvailabilityBasis.PROVIDER_CLOSED_BAR_PROTOCOL,
        source_request_id=capture.request_id,
        source_raw_body_sha256=capture.raw_body_sha256,
        usage_scope="COUNTERFACTUAL_MARKET_REPLAY",
        decision_contemporaneous_status=QualityStatus.UNKNOWN,
        decision_contemporaneous_reason=_CONTEMPORANEOUS_UNKNOWN,
        bar_digest=canonical_digest(content),
    )


def _unknown_fields() -> tuple[InterfaceField, ...]:
    return (
        InterfaceField(
            field_name="funding_rate",
            status=FieldStatus.UNKNOWN,
            value=None,
            unit="rate",
            reason_code="UNKNOWN_NOT_REQUESTED",
        ),
        InterfaceField(
            field_name="open_interest",
            status=FieldStatus.UNKNOWN,
            value=None,
            unit="contracts",
            reason_code="UNKNOWN_NOT_REQUESTED",
        ),
        InterfaceField(
            field_name="order_book",
            status=FieldStatus.UNKNOWN,
            value=None,
            unit=None,
            reason_code="UNKNOWN_NOT_REQUESTED",
        ),
        InterfaceField(
            field_name="liquidation_flow",
            status=FieldStatus.UNKNOWN,
            value=None,
            unit="USDT",
            reason_code="UNKNOWN_NOT_REQUESTED",
        ),
        InterfaceField(
            field_name="participant_psychology",
            status=FieldStatus.UNKNOWN,
            value=None,
            unit=None,
            reason_code="UNKNOWN_UNIDENTIFIABLE_FROM_PUBLIC_AGGREGATES",
        ),
    )


def _slot_fields(bar: NormalizedHourlyBar) -> tuple[InterfaceField, ...]:
    observed: tuple[InterfaceField, ...] = (
        InterfaceField(
            field_name="close",
            status=FieldStatus.OBSERVED,
            value=bar.close,
            unit="USDT",
            reason_code=None,
        ),
        InterfaceField(
            field_name="base_volume",
            status=FieldStatus.OBSERVED,
            value=bar.volume,
            unit="BTC",
            reason_code=None,
        ),
    )
    trade_count = (
        InterfaceField(
            field_name="trade_count",
            status=FieldStatus.UNKNOWN,
            value=None,
            unit="trades",
            reason_code="UNKNOWN_NOT_PROVIDED_BY_SOURCE",
        )
        if bar.trade_count is None
        else InterfaceField(
            field_name="trade_count",
            status=FieldStatus.OBSERVED,
            value=str(bar.trade_count),
            unit="trades",
            reason_code=None,
        )
    )
    return observed + (trade_count,) + _unknown_fields()


def _build_slots(
    bars: Sequence[NormalizedHourlyBar],
) -> tuple[HourlyDecisionSlot, ...]:
    if (
        len(bars) <= FORMAL_DECISION_INDEX_END
        or len({bar.bar_id for bar in bars}) != len(bars)
    ):
        return ()
    slots: list[HourlyDecisionSlot] = []
    for slot_index, bar_index in enumerate(
        range(
            FORMAL_DECISION_INDEX_START,
            FORMAL_DECISION_INDEX_END + 1,
        )
    ):
        decision_bar = bars[bar_index]
        visible = tuple(item.bar_id for item in bars[: bar_index + 1])
        payload = {
            "slot_id": f"BTCUSDT-1h-decision-{decision_bar.open_time_ms}",
            "slot_index": slot_index,
            "decision_at": decision_bar.available_at.isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
            "visible_bar_ids": list(visible),
            "visible_through_bar_id": decision_bar.bar_id,
            "source_request_id": decision_bar.source_request_id,
            "source_raw_body_sha256": (
                decision_bar.source_raw_body_sha256
            ),
            "interface_fields": [
                field.to_dict() for field in _slot_fields(decision_bar)
            ],
            "usage_scope": "COUNTERFACTUAL_MARKET_REPLAY",
            "contemporaneous_agent_input_status": "UNKNOWN",
            "contemporaneous_agent_input_reason": (
                _CONTEMPORANEOUS_UNKNOWN
            ),
        }
        slots.append(
            HourlyDecisionSlot(
                slot_id=str(payload["slot_id"]),
                slot_index=slot_index,
                decision_at=decision_bar.available_at,
                visible_bar_ids=visible,
                visible_through_bar_id=decision_bar.bar_id,
                source_request_id=decision_bar.source_request_id,
                source_raw_body_sha256=(
                    decision_bar.source_raw_body_sha256
                ),
                interface_fields=_slot_fields(decision_bar),
                usage_scope="COUNTERFACTUAL_MARKET_REPLAY",
                contemporaneous_agent_input_status=QualityStatus.UNKNOWN,
                contemporaneous_agent_input_reason=(
                    _CONTEMPORANEOUS_UNKNOWN
                ),
                slot_digest=canonical_digest(payload),
            )
        )
    return tuple(slots)


def _build_outcomes(
    bars: Sequence[NormalizedHourlyBar],
    slots: Sequence[HourlyDecisionSlot],
) -> tuple[OutcomeBinding, ...]:
    if len(bars) < FORMAL_CLOSED_BAR_COUNT or len(slots) != 96:
        return ()
    bindings: list[OutcomeBinding] = []
    for offset, slot in enumerate(slots):
        decision_index = FORMAL_DECISION_INDEX_START + offset
        for horizon in FORMAL_OUTCOME_HORIZONS:
            outcome = bars[decision_index + horizon]
            payload = {
                "binding_id": (
                    f"{slot.slot_id}-outcome-{horizon}h"
                ),
                "decision_slot_id": slot.slot_id,
                "decision_bar_index": decision_index,
                "horizon_hours": horizon,
                "outcome_bar_id": outcome.bar_id,
                "outcome_available_at": outcome.available_at.isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z"),
                "role_visible": False,
            }
            bindings.append(
                OutcomeBinding(
                    binding_id=str(payload["binding_id"]),
                    decision_slot_id=slot.slot_id,
                    decision_bar_index=decision_index,
                    horizon_hours=horizon,
                    outcome_bar_id=outcome.bar_id,
                    outcome_available_at=outcome.available_at,
                    role_visible=False,
                    binding_digest=canonical_digest(payload),
                )
            )
    return tuple(bindings)


def _derive_bars(
    bars: Sequence[NormalizedHourlyBar],
    *,
    interval: str,
    hours: int,
) -> tuple[DerivedMarketBar, ...]:
    by_open = {bar.open_time_ms: bar for bar in bars}
    if not bars:
        return ()
    first_boundary = (
        (bars[0].open_time_ms + hours * _HOUR_MS - 1)
        // (hours * _HOUR_MS)
    ) * (hours * _HOUR_MS)
    last_open = bars[-1].open_time_ms
    result: list[DerivedMarketBar] = []
    group_open = first_boundary
    while group_open + (hours - 1) * _HOUR_MS <= last_open:
        members = tuple(
            by_open.get(group_open + offset * _HOUR_MS)
            for offset in range(hours)
        )
        if all(member is not None for member in members):
            complete = tuple(
                member for member in members if member is not None
            )
            high = canonical_decimal(
                max(Decimal(member.high) for member in complete)
            )
            low = canonical_decimal(
                min(Decimal(member.low) for member in complete)
            )
            volume = canonical_decimal(
                sum(Decimal(member.volume) for member in complete)
            )
            close_time_ms = (
                group_open + hours * _HOUR_MS - 1
            )
            payload = {
                "derived_bar_id": (
                    f"BTCUSDT-{interval}-{group_open}"
                ),
                "symbol": "BTCUSDT",
                "interval": interval,
                "open_time_ms": group_open,
                "close_time_ms": close_time_ms,
                "open": complete[0].open,
                "high": high,
                "low": low,
                "close": complete[-1].close,
                "volume": volume,
                "source_bar_ids": [
                    member.bar_id for member in complete
                ],
                "available_at": complete[-1].available_at.isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z"),
                "derivation_status": "DERIVED_FROM_FROZEN_1H",
            }
            result.append(
                DerivedMarketBar(
                    derived_bar_id=str(payload["derived_bar_id"]),
                    interval=interval,
                    open_time_ms=group_open,
                    close_time_ms=close_time_ms,
                    open=complete[0].open,
                    high=high,
                    low=low,
                    close=complete[-1].close,
                    volume=volume,
                    source_bar_ids=tuple(
                        member.bar_id for member in complete
                    ),
                    available_at=complete[-1].available_at,
                    derivation_status="DERIVED_FROM_FROZEN_1H",
                    derived_bar_digest=canonical_digest(payload),
                )
            )
        group_open += hours * _HOUR_MS
    return tuple(result)


def _instrument_legality(
    exchange_payload: object, *, provider_id: str
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(exchange_payload, dict):
        return False, ("EXCHANGE_INFO_ROOT_INVALID",)
    if provider_id == OKX_PROVIDER_ID:
        if (
            exchange_payload.get("code") != "0"
            or exchange_payload.get("msg") != ""
            or not isinstance(exchange_payload.get("data"), list)
        ):
            return False, ("OKX_INSTRUMENT_ROOT_INVALID",)
        matches = [
            item
            for item in exchange_payload["data"]
            if isinstance(item, dict)
            and item.get("instId") == "BTC-USDT-SWAP"
        ]
        if len(matches) != 1:
            return False, ("BTC_USDT_SWAP_INSTRUMENT_NOT_UNIQUE",)
        instrument = matches[0]
        failures: list[str] = []
        expected = {
            "instType": "SWAP",
            "state": "live",
            "ctType": "linear",
            "settleCcy": "USDT",
            "ctValCcy": "BTC",
        }
        for field, expected_value in expected.items():
            if instrument.get(field) != expected_value:
                failures.append(f"BTC_USDT_SWAP_{field.upper()}_INVALID")
        for field in ("tickSz", "lotSz", "ctVal"):
            try:
                value, _ = _decimal(
                    instrument.get(field), nonnegative=True
                )
            except FreshMarketQualityError:
                value = Decimal(0)
            if value <= 0:
                failures.append(
                    f"BTC_USDT_SWAP_{field.upper()}_INVALID"
                )
        return not failures, tuple(failures or ["PASS"])
    if provider_id != BINANCE_PROVIDER_ID:
        return False, ("EVIDENCE_SOURCE_UNREGISTERED",)
    symbols = exchange_payload.get("symbols")
    if not isinstance(symbols, list):
        return False, ("EXCHANGE_INFO_SYMBOLS_MISSING",)
    matches = [
        item
        for item in symbols
        if isinstance(item, dict) and item.get("symbol") == "BTCUSDT"
    ]
    if len(matches) != 1:
        return False, ("BTCUSDT_SYMBOL_NOT_UNIQUE",)
    symbol = matches[0]
    failures: list[str] = []
    expected = {
        "status": "TRADING",
        "contractType": "PERPETUAL",
        "quoteAsset": "USDT",
        "baseAsset": "BTC",
    }
    for field, value in expected.items():
        if symbol.get(field) != value:
            failures.append(f"BTCUSDT_{field.upper()}_INVALID")
    filters = symbol.get("filters")
    if not isinstance(filters, list):
        failures.append("BTCUSDT_FILTERS_MISSING")
    else:
        by_type = {
            item.get("filterType"): item
            for item in filters
            if isinstance(item, dict)
            and isinstance(item.get("filterType"), str)
        }
        for filter_type, field in (
            ("PRICE_FILTER", "tickSize"),
            ("LOT_SIZE", "stepSize"),
        ):
            current = by_type.get(filter_type)
            if not isinstance(current, dict):
                failures.append(f"BTCUSDT_{filter_type}_MISSING")
                continue
            try:
                value, _ = _decimal(current.get(field), nonnegative=True)
            except FreshMarketQualityError:
                value = Decimal(0)
            if value <= 0:
                failures.append(
                    f"BTCUSDT_{filter_type}_{field.upper()}_INVALID"
                )
    return not failures, tuple(failures or ["PASS"])


def _check(
    *,
    check_id: str,
    passed: bool | None,
    hard_gate: bool,
    reasons: tuple[str, ...],
    observed: int | None = None,
    required: int | None = None,
) -> QualityCheck:
    if passed is True:
        status = QualityStatus.PASS
        reason_codes = ("PASS",)
    elif passed is False:
        status = QualityStatus.FAIL
        reason_codes = reasons
    else:
        status = QualityStatus.UNKNOWN
        reason_codes = reasons
    return QualityCheck(
        check_id=check_id,
        status=status,
        hard_gate=hard_gate,
        observed_count=observed,
        required_count=required,
        reason_codes=reason_codes,
    )


@dataclass(frozen=True, slots=True)
class PreparedFreshMarketDataset:
    experiment_contract_digest: str
    provider_id: str
    symbol: str
    interval: str
    server_time_ms: int
    requested_closed_bar_count: int
    decision_index_start: int
    decision_index_end: int
    outcome_horizons_hours: tuple[int, ...]
    forming_or_future_rows_excluded: int
    bars: tuple[NormalizedHourlyBar, ...]
    derived_4h_bars: tuple[DerivedMarketBar, ...]
    derived_1d_bars: tuple[DerivedMarketBar, ...]
    decision_slots: tuple[HourlyDecisionSlot, ...]
    outcome_bindings: tuple[OutcomeBinding, ...]
    requests: tuple[PublicRequestCapture, ...]
    quality: DatasetQualityReceipt
    replay_admissibility: HistoricalReplayAdmissibilityReceipt

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_type": "HISTORICAL_COUNTERFACTUAL_REPLAY",
            "experiment_contract_digest": self.experiment_contract_digest,
            "provider_id": self.provider_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "server_time_ms": self.server_time_ms,
            "requested_closed_bar_count": self.requested_closed_bar_count,
            "decision_indices_inclusive": [
                self.decision_index_start,
                self.decision_index_end,
            ],
            "outcome_horizons_hours": list(
                self.outcome_horizons_hours
            ),
            "forming_or_future_rows_excluded": (
                self.forming_or_future_rows_excluded
            ),
            "bars": [bar.to_dict() for bar in self.bars],
            "derived_4h_bars": [
                bar.to_dict() for bar in self.derived_4h_bars
            ],
            "derived_1d_bars": [
                bar.to_dict() for bar in self.derived_1d_bars
            ],
            "decision_slots": [
                slot.to_dict() for slot in self.decision_slots
            ],
            "outcome_bindings": [
                item.to_dict() for item in self.outcome_bindings
            ],
            "request_ids": [item.request_id for item in self.requests],
            "quality_receipt_id": self.quality.receipt_id,
            "quality_receipt_digest": self.quality.receipt_digest,
            "replay_admissibility_receipt_id": (
                self.replay_admissibility.receipt_id
            ),
            "replay_admissibility_receipt_digest": (
                self.replay_admissibility.receipt_digest
            ),
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": (
                EXTERNAL_EXECUTION_AUTHORITY
            ),
            "executable": False,
        }


def _response_provider_id(
    responses: CollectedPublicResponses,
) -> str:
    base_urls = {
        responses.server_time.base_url,
        responses.exchange_info.base_url,
        responses.klines.base_url,
    }
    if base_urls == {_BINANCE_BASE_URL}:
        return BINANCE_PROVIDER_ID
    if base_urls == {_OKX_BASE_URL}:
        return OKX_PROVIDER_ID
    raise FreshMarketQualityError("EVIDENCE_SOURCE_UNREGISTERED")


def _server_time_ms(payload: object, *, provider_id: str) -> int:
    if provider_id == BINANCE_PROVIDER_ID:
        if (
            not isinstance(payload, dict)
            or set(payload) != {"serverTime"}
            or not isinstance(payload["serverTime"], int)
            or isinstance(payload["serverTime"], bool)
        ):
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
        result = payload["serverTime"]
    elif provider_id == OKX_PROVIDER_ID:
        if (
            not isinstance(payload, dict)
            or payload.get("code") != "0"
            or payload.get("msg") != ""
            or not isinstance(payload.get("data"), list)
            or len(payload["data"]) != 1
            or not isinstance(payload["data"][0], dict)
            or not isinstance(payload["data"][0].get("ts"), str)
        ):
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
        try:
            result = int(payload["data"][0]["ts"])
        except ValueError as exc:
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID") from exc
    else:  # pragma: no cover - guarded by _response_provider_id
        raise FreshMarketQualityError("EVIDENCE_SOURCE_UNREGISTERED")
    if result <= 0:
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    return result


def _kline_rows(payload: object, *, provider_id: str) -> list[object]:
    if provider_id == BINANCE_PROVIDER_ID:
        if not isinstance(payload, list):
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
        return payload
    if provider_id == OKX_PROVIDER_ID:
        if (
            not isinstance(payload, dict)
            or payload.get("code") != "0"
            or payload.get("msg") != ""
            or not isinstance(payload.get("data"), list)
        ):
            raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
        return payload["data"]
    raise FreshMarketQualityError("EVIDENCE_SOURCE_UNREGISTERED")


def prepare_fresh_market_dataset(
    responses: CollectedPublicResponses,
    *,
    prior_bar_digests: Mapping[str, str] | None = None,
    experiment_contract_digest: str = FORMAL_EXPERIMENT_CONTRACT_DIGEST,
) -> PreparedFreshMarketDataset:
    """Normalize one capture and produce all fail-closed quality checks."""

    if (
        not isinstance(experiment_contract_digest, str)
        or len(experiment_contract_digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in experiment_contract_digest
        )
    ):
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    request_tuple = (
        responses.server_time,
        responses.exchange_info,
        responses.klines,
    )
    if len({item.request_id for item in request_tuple}) != 3:
        raise FreshMarketQualityError("EVIDENCE_LINEAGE_INVALID")
    provider_id = _response_provider_id(responses)
    server_payload = _decode_json_any(
        responses.raw_body_by_request_id.get(
            responses.server_time.request_id, b""
        )
    )
    exchange_payload = _decode_json_any(
        responses.raw_body_by_request_id.get(
            responses.exchange_info.request_id, b""
        )
    )
    kline_payload = _decode_json_any(
        responses.raw_body_by_request_id.get(
            responses.klines.request_id, b""
        )
    )
    server_time_ms = _server_time_ms(
        server_payload, provider_id=provider_id
    )
    normalized_rows = sorted(
        (
            _normalize_bar(
                row,
                capture=responses.klines,
                provider_id=provider_id,
            )
            for row in _kline_rows(
                kline_payload, provider_id=provider_id
            )
        ),
        key=lambda item: item.open_time_ms,
    )
    closed_bars = tuple(
        row
        for row in normalized_rows
        if row.available_at <= _utc_from_ms(server_time_ms)
    )
    excluded = len(normalized_rows) - len(closed_bars)
    slots = _build_slots(closed_bars)
    outcome_bindings = _build_outcomes(closed_bars, slots)
    derived_4h = _derive_bars(
        closed_bars, interval="4h", hours=4
    )
    derived_1d = _derive_bars(
        closed_bars, interval="1d", hours=24
    )

    checks: list[QualityCheck] = []
    required_bar_count = FORMAL_CLOSED_BAR_COUNT
    checks.append(
        _check(
            check_id="closed_bar_completeness",
            passed=len(closed_bars) == required_bar_count,
            hard_gate=True,
            reasons=("INSUFFICIENT_CLOSED_BARS",),
            observed=len(closed_bars),
            required=required_bar_count,
        )
    )
    unique_bar_ids = {item.bar_id for item in closed_bars}
    checks.append(
        _check(
            check_id="bar_uniqueness",
            passed=len(unique_bar_ids) == len(closed_bars),
            hard_gate=True,
            reasons=("DUPLICATE_BAR_ID",),
            observed=len(unique_bar_ids),
            required=len(closed_bars),
        )
    )
    continuity = all(
        right.open_time_ms - left.open_time_ms == _HOUR_MS
        for left, right in zip(closed_bars, closed_bars[1:])
    )
    checks.append(
        _check(
            check_id="hourly_continuity",
            passed=continuity,
            hard_gate=True,
            reasons=("HOURLY_BAR_GAP_OR_REORDER",),
            observed=len(closed_bars),
            required=required_bar_count,
        )
    )
    legal, legal_reasons = _instrument_legality(
        exchange_payload, provider_id=provider_id
    )
    checks.append(
        _check(
            check_id="instrument_legality",
            passed=legal,
            hard_gate=True,
            reasons=legal_reasons,
            observed=1 if legal else 0,
            required=1,
        )
    )
    required_decision_slots = (
        FORMAL_DECISION_INDEX_END - FORMAL_DECISION_INDEX_START + 1
    )
    slot_complete = len(slots) == required_decision_slots
    checks.append(
        _check(
            check_id="minimum_decision_slots",
            passed=slot_complete,
            hard_gate=True,
            reasons=("INSUFFICIENT_DECISION_SLOTS",),
            observed=len(slots),
            required=required_decision_slots,
        )
    )
    bars_by_id = {item.bar_id: item for item in closed_bars}
    no_future = all(
        all(
            visible in bars_by_id
            and bars_by_id[visible].available_at <= slot.decision_at
            for visible in slot.visible_bar_ids
        )
        for slot in slots
    )
    checks.append(
        _check(
            check_id="pit_future_visibility",
            passed=no_future,
            hard_gate=True,
            reasons=("PIT_FUTURE_AVAILABLE",),
            observed=sum(len(item.visible_bar_ids) for item in slots),
            required=None,
        )
    )
    expected_outcome_count = (
        required_decision_slots * len(FORMAL_OUTCOME_HORIZONS)
    )
    outcome_ids = {item.outcome_bar_id for item in outcome_bindings}
    outcome_separated = (
        len(outcome_bindings) == expected_outcome_count
        and all(not item.role_visible for item in outcome_bindings)
        and all(
            item.outcome_bar_id not in slots[
                item.decision_bar_index - FORMAL_DECISION_INDEX_START
            ].visible_bar_ids
            for item in outcome_bindings
        )
        and outcome_ids.issubset(set(bars_by_id))
    )
    checks.append(
        _check(
            check_id="outcome_horizon_separation",
            passed=outcome_separated,
            hard_gate=True,
            reasons=("PIT_FUTURE_AVAILABLE",),
            observed=len(outcome_bindings),
            required=expected_outcome_count,
        )
    )
    request_lineage = all(
        responses.raw_body_by_request_id.get(item.request_id) is not None
        and hashlib.sha256(
            responses.raw_body_by_request_id[item.request_id]
        ).hexdigest()
        == item.raw_body_sha256
        and len(responses.raw_body_by_request_id[item.request_id])
        == item.raw_body_byte_length
        and _record_digest(item) == item.record_digest
        and _request_identity(item) == item.request_identity_digest
        for item in request_tuple
    )
    checks.append(
        _check(
            check_id="request_and_raw_lineage",
            passed=request_lineage,
            hard_gate=True,
            reasons=("EVIDENCE_LINEAGE_INVALID",),
            observed=sum(1 for _ in request_tuple) if request_lineage else 0,
            required=3,
        )
    )
    expected_hour_open = (server_time_ms // _HOUR_MS) * _HOUR_MS
    expected_end = expected_hour_open - 1
    expected_start = (
        expected_hour_open - FORMAL_CLOSED_BAR_COUNT * _HOUR_MS
    )
    expected_binance_kline_query = (
        ("endTime", str(expected_end)),
        ("interval", "1h"),
        ("limit", str(FORMAL_CLOSED_BAR_COUNT)),
        ("startTime", str(expected_start)),
        ("symbol", "BTCUSDT"),
    )
    expected_okx_kline_query = (
        ("after", str(expected_hour_open)),
        ("bar", "1H"),
        ("instId", "BTC-USDT-SWAP"),
        ("limit", str(FORMAL_CLOSED_BAR_COUNT)),
    )
    if provider_id == BINANCE_PROVIDER_ID:
        request_window_contract = (
            responses.server_time.path == "/fapi/v1/time"
            and responses.server_time.query == ()
            and responses.exchange_info.path == "/fapi/v1/exchangeInfo"
            and responses.exchange_info.query == ()
            and responses.klines.path == "/fapi/v1/klines"
            and responses.klines.query == expected_binance_kline_query
        )
    else:
        request_window_contract = (
            responses.server_time.path == "/api/v5/public/time"
            and responses.server_time.query == ()
            and responses.exchange_info.path
            == "/api/v5/public/instruments"
            and responses.exchange_info.query
            == (("instId", "BTC-USDT-SWAP"), ("instType", "SWAP"))
            and responses.klines.path == "/api/v5/market/history-candles"
            and responses.klines.query == expected_okx_kline_query
        )
    request_window_contract = (
        request_window_contract
        and bool(closed_bars)
        and closed_bars[0].open_time_ms == expected_start
        and closed_bars[-1].close_time_ms == expected_end
    )
    checks.append(
        _check(
            check_id="official_request_window_contract",
            passed=request_window_contract,
            hard_gate=True,
            reasons=("OFFICIAL_END_TIME_OR_WINDOW_MISMATCH",),
            observed=len(closed_bars),
            required=FORMAL_CLOSED_BAR_COUNT,
        )
    )
    derived_source_ids = {
        source_id
        for derived in (*derived_4h, *derived_1d)
        for source_id in derived.source_bar_ids
    }
    derived_consistent = (
        bool(derived_4h)
        and bool(derived_1d)
        and derived_source_ids.issubset(set(bars_by_id))
        and all(
            item.available_at
            == bars_by_id[item.source_bar_ids[-1]].available_at
            for item in (*derived_4h, *derived_1d)
        )
    )
    checks.append(
        _check(
            check_id="cross_timeframe_consistency",
            passed=derived_consistent,
            hard_gate=True,
            reasons=("DERIVED_TIMEFRAME_INCONSISTENT",),
            observed=len(derived_4h) + len(derived_1d),
            required=1,
        )
    )
    server_dt = _utc_from_ms(server_time_ms)
    # Five minutes covers normal public-request and host-clock skew while still
    # rejecting stale/future authority captures.
    freshness = (
        responses.server_time.request_started_at - timedelta(minutes=5)
        <= server_dt
        <= responses.server_time.response_received_at + timedelta(minutes=5)
    )
    checks.append(
        _check(
            check_id="server_time_freshness",
            passed=freshness,
            hard_gate=True,
            reasons=("SERVER_TIME_OUTSIDE_CAPTURE_WINDOW",),
        )
    )
    replay_scoped = (
        all(
            bar.usage_scope == "COUNTERFACTUAL_MARKET_REPLAY"
            and bar.availability_status is AvailabilityStatus.DERIVED
            and bar.availability_basis
            is AvailabilityBasis.PROVIDER_CLOSED_BAR_PROTOCOL
            and bar.decision_contemporaneous_status
            is QualityStatus.UNKNOWN
            for bar in closed_bars
        )
        and all(
            slot.usage_scope == "COUNTERFACTUAL_MARKET_REPLAY"
            and slot.contemporaneous_agent_input_status
            is QualityStatus.UNKNOWN
            for slot in slots
        )
    )
    checks.append(
        _check(
            check_id="historical_replay_scope_admissibility",
            passed=replay_scoped,
            hard_gate=True,
            reasons=("HISTORICAL_REPLAY_SCOPE_MISSTATED",),
        )
    )
    typed_unknowns = all(
        field.value is None and bool(field.reason_code)
        for slot in slots
        for field in slot.interface_fields
        if field.status is FieldStatus.UNKNOWN
    )
    checks.append(
        _check(
            check_id="typed_unknown_integrity",
            passed=typed_unknowns,
            hard_gate=True,
            reasons=("UNKNOWN_FIELD_IMPUTED_OR_UNTYPED",),
        )
    )
    if prior_bar_digests is None:
        checks.append(
            _check(
                check_id="cross_cycle_consistency",
                passed=None,
                hard_gate=False,
                reasons=("UNKNOWN_NO_PRIOR_BUNDLE",),
            )
        )
    else:
        overlap = {
            item.bar_id: item.bar_digest
            for item in closed_bars
            if item.bar_id in prior_bar_digests
        }
        same = bool(overlap) and all(
            prior_bar_digests[bar_id] == digest
            for bar_id, digest in overlap.items()
        )
        checks.append(
            _check(
                check_id="cross_cycle_consistency",
                passed=same,
                hard_gate=True,
                reasons=(
                    ("CROSS_CYCLE_BAR_REVISION",)
                    if overlap
                    else ("CROSS_CYCLE_NO_OVERLAP",)
                ),
                observed=len(overlap),
                required=1,
            )
        )
    hard_failures = tuple(
        item.check_id
        for item in checks
        if item.hard_gate and item.status is QualityStatus.FAIL
    )
    hard_unknowns = tuple(
        item.check_id
        for item in checks
        if item.hard_gate and item.status is QualityStatus.UNKNOWN
    )
    unknowns = tuple(
        item.check_id
        for item in checks
        if item.status is QualityStatus.UNKNOWN
    )
    if hard_failures:
        overall = QualityStatus.FAIL
    elif hard_unknowns:
        overall = QualityStatus.UNKNOWN
    else:
        overall = QualityStatus.PASS
    receipt_prefix = (
        "binance-usdm-btcusdt"
        if provider_id == BINANCE_PROVIDER_ID
        else "okx-btc-usdt-swap"
    )
    receipt = DatasetQualityReceipt(
        receipt_id=f"{receipt_prefix}-1h-quality",
        checks=tuple(checks),
        overall_status=overall,
        hard_failures=hard_failures,
        unknowns=unknowns,
        system_mode=SYSTEM_MODE,
        external_execution_authority=EXTERNAL_EXECUTION_AUTHORITY,
        executable=False,
        receipt_digest="0" * 64,
    )
    payload = receipt.to_dict()
    payload.pop("receipt_digest")
    receipt = replace(
        receipt, receipt_digest=canonical_digest(payload)
    )
    admissibility = HistoricalReplayAdmissibilityReceipt(
        receipt_id=f"{receipt_prefix}-1h-replay-admissibility",
        status=QualityStatus.PASS,
        permitted_usage_scope="HISTORICAL_COUNTERFACTUAL_REPLAY",
        availability_status=AvailabilityStatus.DERIVED,
        contemporaneous_agent_input_status=QualityStatus.UNKNOWN,
        forbidden_claims=(
            "NOT_CONTEMPORANEOUS_AGENT_INPUT",
            "NOT_PHYSICALLY_CAPTURED_AT_HISTORICAL_DECISION_TIME",
            "NOT_LIVE_OR_PAPER_TRADING_AUTHORIZATION",
            "NOT_PREDICTIVE_OR_PROFITABILITY_PROOF",
        ),
        system_mode=SYSTEM_MODE,
        external_execution_authority=EXTERNAL_EXECUTION_AUTHORITY,
        executable=False,
        receipt_digest="0" * 64,
    )
    admissibility_payload = admissibility.to_dict()
    admissibility_payload.pop("receipt_digest")
    admissibility = replace(
        admissibility,
        receipt_digest=canonical_digest(admissibility_payload),
    )
    return PreparedFreshMarketDataset(
        experiment_contract_digest=experiment_contract_digest,
        provider_id=provider_id,
        symbol="BTCUSDT",
        interval="1h",
        server_time_ms=server_time_ms,
        requested_closed_bar_count=FORMAL_CLOSED_BAR_COUNT,
        decision_index_start=FORMAL_DECISION_INDEX_START,
        decision_index_end=FORMAL_DECISION_INDEX_END,
        outcome_horizons_hours=FORMAL_OUTCOME_HORIZONS,
        forming_or_future_rows_excluded=excluded,
        bars=closed_bars,
        derived_4h_bars=derived_4h,
        derived_1d_bars=derived_1d,
        decision_slots=slots,
        outcome_bindings=outcome_bindings,
        requests=request_tuple,
        quality=receipt,
        replay_admissibility=admissibility,
    )


__all__ = [
    "FreshMarketQualityError",
    "PreparedFreshMarketDataset",
    "prepare_fresh_market_dataset",
]
