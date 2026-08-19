"""Official-public OKX snapshot adapter for the native Codex market pilot.

The adapter keeps raw responses separate from normalized facts.  Required
requests fail closed; optional public fields become explicit UNKNOWN facts.
It never imports account, order, credential, or execution interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_decimal,
    self_digest,
    verify_self_digest,
)
from ..domain.dynamic_research import build_market_information_snapshot
from .fresh_market.model import PublicRequestCapture, timestamp
from .fresh_market.okx_public import (
    OKX_INSTRUMENT_ID,
    OkxPublicCollectionError,
    OkxPublicFreshCollector,
    _decode_json,
)


class NativeMarketCollectionError(ValueError):
    """The public snapshot cannot support a point-in-time market cycle."""


@dataclass(frozen=True, slots=True)
class NativeMarketCollection:
    snapshot: Mapping[str, Any]
    raw_body_by_request_id: Mapping[str, bytes]


def _root(raw: bytes) -> list[Mapping[str, Any]]:
    value = _decode_json(raw)
    if (
        not isinstance(value, Mapping)
        or value.get("code") != "0"
        or value.get("msg") not in {"", None}
        or not isinstance(value.get("data"), list)
        or any(not isinstance(row, Mapping) for row in value["data"])
    ):
        raise NativeMarketCollectionError("NATIVE_MARKET_SOURCE_PAYLOAD_INVALID")
    return list(value["data"])


def _decimal(
    value: object,
    reason: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
) -> Decimal:
    if not isinstance(value, str):
        raise NativeMarketCollectionError(reason)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise NativeMarketCollectionError(reason) from exc
    if (
        not parsed.is_finite()
        or (nonnegative and parsed < 0)
        or (positive and parsed <= 0)
    ):
        raise NativeMarketCollectionError(reason)
    return parsed


def _required_row(raw: bytes, reason: str) -> Mapping[str, Any]:
    rows = _root(raw)
    if not rows:
        raise NativeMarketCollectionError(reason)
    return rows[0]


def _fact(
    *,
    fact_id: str,
    value: str,
    unit: str,
    source: PublicRequestCapture,
    observed_at: str | None = None,
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "status": "OBSERVED",
        "value": value,
        "unit": unit,
        "source_request_id": source.request_id,
        "source_raw_body_sha256": source.raw_body_sha256,
        "available_at": timestamp(source.response_received_at),
        "observed_at": observed_at,
        "unknown_reason": None,
    }


def _unknown(*, fact_id: str, reason: str) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "status": "UNKNOWN",
        "value": None,
        "unit": None,
        "source_request_id": None,
        "source_raw_body_sha256": None,
        "available_at": None,
        "observed_at": None,
        "unknown_reason": reason,
    }


def _verified_prior_open_interest(
    *,
    run_id: str,
    cycle_index: int,
    prior_market_snapshot: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if cycle_index == 1:
        if prior_market_snapshot is not None:
            raise NativeMarketCollectionError(
                "NATIVE_MARKET_FIRST_CYCLE_PRIOR_SNAPSHOT_FORBIDDEN"
            )
        return None
    if prior_market_snapshot is None:
        raise NativeMarketCollectionError(
            "NATIVE_MARKET_PRIOR_SNAPSHOT_REQUIRED"
        )
    try:
        verify_self_digest(
            prior_market_snapshot, "native_market_snapshot_digest"
        )
    except ValueError as exc:
        raise NativeMarketCollectionError(
            "NATIVE_MARKET_PRIOR_SNAPSHOT_DIGEST_INVALID"
        ) from exc
    information = prior_market_snapshot.get("market_information_snapshot")
    if not isinstance(information, Mapping):
        raise NativeMarketCollectionError(
            "NATIVE_MARKET_PRIOR_INFORMATION_MISSING"
        )
    try:
        verify_self_digest(information, "market_information_snapshot_digest")
    except ValueError as exc:
        raise NativeMarketCollectionError(
            "NATIVE_MARKET_PRIOR_INFORMATION_DIGEST_INVALID"
        ) from exc
    if (
        prior_market_snapshot.get("run_id") != run_id
        or prior_market_snapshot.get("cycle_index") != cycle_index - 1
        or information.get("run_id") != run_id
        or information.get("cycle_index") != cycle_index - 1
    ):
        raise NativeMarketCollectionError(
            "NATIVE_MARKET_PRIOR_SNAPSHOT_IDENTITY_INVALID"
        )
    rows = [
        row
        for row in information.get("facts", [])
        if isinstance(row, Mapping)
        and row.get("fact_id") == "open-interest-btc"
    ]
    if len(rows) != 1:
        raise NativeMarketCollectionError(
            "NATIVE_MARKET_PRIOR_OPEN_INTEREST_INVALID"
        )
    return rows[0]


def _cross_cycle_open_interest_fact(
    *,
    cycle_index: int,
    current_fact: Mapping[str, Any],
    prior_open_interest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if cycle_index == 1:
        return _unknown(
            fact_id="open-interest-change-pct",
            reason="FIRST_CYCLE_HAS_NO_PRIOR_OPEN_INTEREST",
        )
    if prior_open_interest is None:
        raise NativeMarketCollectionError(
            "NATIVE_MARKET_PRIOR_OPEN_INTEREST_INVALID"
        )
    if current_fact.get("value") is None:
        return _unknown(
            fact_id="open-interest-change-pct",
            reason="CURRENT_CYCLE_OPEN_INTEREST_UNKNOWN",
        )
    if prior_open_interest.get("value") is None:
        return _unknown(
            fact_id="open-interest-change-pct",
            reason="PRIOR_CYCLE_OPEN_INTEREST_UNKNOWN",
        )
    current = _decimal(
        current_fact.get("value"),
        "NATIVE_MARKET_OPEN_INTEREST_CHANGE_INVALID",
        nonnegative=True,
    )
    prior = _decimal(
        prior_open_interest.get("value"),
        "NATIVE_MARKET_OPEN_INTEREST_CHANGE_INVALID",
        nonnegative=True,
    )
    if current <= 0 or prior <= 0:
        return _unknown(
            fact_id="open-interest-change-pct",
            reason="NONPOSITIVE_OPEN_INTEREST_CANNOT_FORM_CHANGE",
        )
    change = (current / prior - Decimal("1")) * Decimal("100")
    return {
        "fact_id": "open-interest-change-pct",
        "status": "OBSERVED",
        "value": canonical_decimal(change),
        "unit": "PERCENT",
        "source_request_id": current_fact.get("source_request_id"),
        "source_raw_body_sha256": current_fact.get(
            "source_raw_body_sha256"
        ),
        "available_at": current_fact.get("available_at"),
        "observed_at": current_fact.get("observed_at"),
        "unknown_reason": None,
    }


def _millisecond_time(value: object, fallback: str) -> str:
    try:
        milliseconds = int(str(value))
    except (TypeError, ValueError):
        return fallback
    return datetime.fromtimestamp(
        milliseconds / 1000, tz=timezone.utc
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dynamic_category(fact_id: str) -> str:
    if fact_id in {
        "server-time-ms",
        "instrument-live",
        "instrument-contract-multiplier",
        "instrument-okx-ct-mult",
        "instrument-quantity-step-contracts",
        "instrument-minimum-quantity-contracts",
        "instrument-price-tick-usdt",
    }:
        return "INSTRUMENT_AND_DATA_QUALITY"
    if fact_id.startswith("candle-") and "range-pct" in fact_id:
        return "TREND_VOLATILITY_AND_STRUCTURE"
    if fact_id.startswith("candle-") and "volume-vs" in fact_id:
        return "VOLUME_AND_ACTIVE_FLOW"
    if fact_id.startswith("candle-") or fact_id.startswith("ticker-") or fact_id == "mark-price":
        return "PRICE_AND_RETURNS"
    if fact_id.startswith("open-interest"):
        return "OPEN_INTEREST_AND_LEVERAGE"
    if fact_id in {"funding-rate", "crowding-positioning"}:
        return "FUNDING_BASIS_AND_POSITIONING"
    if fact_id.startswith("book-"):
        return "ORDER_BOOK_AND_LIQUIDITY"
    if fact_id.startswith("recent-trade"):
        return "VOLUME_AND_ACTIVE_FLOW"
    if fact_id == "liquidation-stress":
        return "LIQUIDATION"
    if fact_id == "news-cross-market":
        return "NEWS_EVENTS_AND_REACTION"
    if fact_id == "cross-market-risk-appetite":
        return "CROSS_MARKET_AND_MACRO"
    raise NativeMarketCollectionError("NATIVE_MARKET_DYNAMIC_CATEGORY_MISSING")


def _dependency_group(fact_id: str) -> str:
    if fact_id.startswith("candle-"):
        parts = fact_id.split("-")
        return f"CANDLE_{parts[1].upper()}"
    return {
        "server-time-ms": "SERVER_TIME",
        "instrument-live": "INSTRUMENT_STATUS",
        "instrument-contract-multiplier": "INSTRUMENT_CONTRACT_SPECIFICATION",
        "instrument-okx-ct-mult": "INSTRUMENT_CONTRACT_SPECIFICATION",
        "instrument-quantity-step-contracts": "INSTRUMENT_QUANTITY_CONSTRAINTS",
        "instrument-minimum-quantity-contracts": "INSTRUMENT_QUANTITY_CONSTRAINTS",
        "instrument-price-tick-usdt": "INSTRUMENT_PRICE_CONSTRAINTS",
        "mark-price": "MARK_PRICE",
        "ticker-last": "TICKER_PRICE",
        "ticker-best-bid": "TICKER_SPREAD",
        "ticker-best-ask": "TICKER_SPREAD_ASK",
        "ticker-volume-24h-contracts": "TICKER_VOLUME_24H",
        "ticker-volume-24h-btc": "TICKER_VOLUME_24H_BTC",
        "open-interest-btc": "OPEN_INTEREST",
        "prior-cycle-open-interest-btc": "PRIOR_OPEN_INTEREST",
        "open-interest-change-pct": "OPEN_INTEREST_CHANGE",
        "funding-rate": "FUNDING_RATE",
        "book-top5-imbalance": "BOOK_SNAPSHOT",
        "recent-trade-side-imbalance": "TRADES_SNAPSHOT",
        "crowding-positioning": "POSITIONING_SOURCE",
        "liquidation-stress": "LIQUIDATION_SOURCE",
        "news-cross-market": "NEWS_SOURCE",
        "cross-market-risk-appetite": "CROSS_MARKET_SOURCE",
    }[fact_id]


def _timeframe_and_window(fact_id: str) -> tuple[str, str]:
    if fact_id == "open-interest-change-pct":
        return "CROSS_CYCLE", "PREVIOUS_ACCEPTED_CYCLE_TO_CURRENT_CAPTURE"
    if fact_id == "prior-cycle-open-interest-btc":
        return "PRIOR_CYCLE", "PREVIOUS_ACCEPTED_CYCLE"
    if fact_id.startswith("candle-"):
        timeframe = fact_id.split("-")[1]
        return timeframe, "LATEST_CLOSED_AND_20_BAR_CONTEXT"
    if fact_id in {"book-top5-imbalance", "recent-trade-side-imbalance"}:
        return "SNAPSHOT", "SINGLE_REST_CAPTURE"
    if fact_id.startswith("ticker-"):
        return "24H_OR_LATEST", "TICKER_SNAPSHOT"
    return "SNAPSHOT", "CURRENT_CAPTURE"


def _build_dynamic_market_snapshot(
    *,
    run_id: str,
    cycle_index: int,
    captured_through: str,
    facts: list[Mapping[str, Any]],
    prior_open_interest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    enriched = list(facts) + [
        _unknown(
            fact_id="cross-market-risk-appetite",
            reason="CROSS_MARKET_SOURCE_NOT_AUTHORIZED_FOR_INITIAL_STABILITY_PILOT",
        )
    ]
    dynamic_facts: list[dict[str, Any]] = []
    if prior_open_interest is not None:
        dynamic_facts.append(
            {
                **dict(prior_open_interest),
                "fact_id": "prior-cycle-open-interest-btc",
                "metric": "prior-cycle-open-interest-btc",
                "timeframe": "PRIOR_CYCLE",
                "window": "PREVIOUS_ACCEPTED_CYCLE",
                "dependency_group": "PRIOR_OPEN_INTEREST",
                "limitations": (
                    "Source-bound open interest copied from the previous "
                    "completed cycle solely for deterministic cross-cycle comparison."
                ),
            }
        )
    for row in enriched:
        fact_id = str(row["fact_id"])
        timeframe, window = _timeframe_and_window(fact_id)
        available = str(row.get("available_at") or captured_through)
        observed = _millisecond_time(row.get("observed_at"), available)
        if datetime.fromisoformat(observed.replace("Z", "+00:00")) > datetime.fromisoformat(
            available.replace("Z", "+00:00")
        ):
            observed = available
        source_request = row.get("source_request_id")
        is_cross_cycle_open_interest = fact_id == "open-interest-change-pct"
        is_derived = (
            "return-pct" in fact_id
            or "range-pct" in fact_id
            or "volume-vs" in fact_id
            or fact_id in {"book-top5-imbalance", "recent-trade-side-imbalance"}
            or is_cross_cycle_open_interest
        )
        dynamic_facts.append(
            {
                "fact_id": fact_id,
                "kind": "DERIVED_FEATURE" if is_derived and row["value"] is not None else "RAW_FACT",
                "category": _dynamic_category(fact_id),
                "metric": fact_id,
                "value": row["value"],
                "unit": str(row.get("unit") or "UNAVAILABLE"),
                "symbol": OKX_INSTRUMENT_ID,
                "timeframe": timeframe,
                "window": window,
                "source_ref": str(source_request or "NO_AUTHORIZED_SOURCE"),
                "raw_ref": (
                    f"cycles/{cycle_index:04d}/market/raw/{source_request}.body"
                    if source_request
                    else "UNAVAILABLE"
                ),
                "raw_sha256": row["source_raw_body_sha256"],
                "observed_at": observed,
                "available_at": available,
                "quality": "GOOD" if row["value"] is not None else "UNKNOWN",
                "coverage": "1" if row["value"] is not None else "0",
                "dependency_group": _dependency_group(fact_id),
                "lineage": [],
                "transform": None,
                "limitations": str(
                    row.get("unknown_reason")
                    or (
                        "Deterministic same-source change from the previous completed-cycle open interest to the current capture; one step has no historical calibration."
                        if is_cross_cycle_open_interest
                        else "One official public point-in-time observation; interpretation requires the Agent to preserve dependency and sampling limits."
                    )
                ),
                "missing_reason": row["unknown_reason"],
            }
        )
        if is_cross_cycle_open_interest and row["value"] is not None:
            if prior_open_interest is None:
                raise NativeMarketCollectionError(
                    "NATIVE_MARKET_PRIOR_OPEN_INTEREST_INVALID"
                )
            dynamic_facts[-1]["lineage"] = [
                "open-interest-btc",
                "prior-cycle-open-interest-btc",
            ]
            dynamic_facts[-1]["transform"] = (
                "DETERMINISTIC_PERCENT_CHANGE_CURRENT_VS_PREVIOUS_COMPLETED_CYCLE"
            )
        elif is_derived and row["value"] is not None:
            # The source response is the immutable raw authority.  The existing
            # fact id is retained as the lineage anchor to avoid invented data.
            anchor_id = f"source-anchor-{source_request}"
            if not any(item["fact_id"] == anchor_id for item in dynamic_facts):
                dynamic_facts.append(
                    {
                        "fact_id": anchor_id,
                        "kind": "RAW_FACT",
                        "category": _dynamic_category(fact_id),
                        "metric": "SOURCE_RESPONSE_SHA256",
                        "value": row["source_raw_body_sha256"],
                        "unit": "SHA256",
                        "symbol": OKX_INSTRUMENT_ID,
                        "timeframe": timeframe,
                        "window": window,
                        "source_ref": str(source_request),
                        "raw_ref": f"cycles/{cycle_index:04d}/market/raw/{source_request}.body",
                        "raw_sha256": row["source_raw_body_sha256"],
                        "observed_at": observed,
                        "available_at": available,
                        "quality": "GOOD",
                        "coverage": "1",
                        "dependency_group": f"SOURCE_ANCHOR_{source_request}",
                        "lineage": [],
                        "transform": None,
                        "limitations": "Raw-response authority anchor; not a directional contributor.",
                        "missing_reason": None,
                    }
                )
            dynamic_facts[-2 if dynamic_facts[-1]["fact_id"] == anchor_id else -1]["lineage"] = [anchor_id]
            dynamic_facts[-2 if dynamic_facts[-1]["fact_id"] == anchor_id else -1]["transform"] = "DETERMINISTIC_DECIMAL_FEATURE_FROM_FROZEN_OKX_RESPONSE"
    return build_market_information_snapshot(
        run_id=run_id,
        cycle_index=cycle_index,
        symbol=OKX_INSTRUMENT_ID,
        as_of=captured_through,
        facts=dynamic_facts,
    )


def _candle_metrics(
    *, raw: bytes, capture: PublicRequestCapture, label: str
) -> list[dict[str, Any]]:
    closed: list[tuple[int, Decimal, Decimal, Decimal, Decimal, Decimal]] = []
    decoded = _decode_json(raw)
    data = decoded.get("data") if isinstance(decoded, Mapping) else None
    if not isinstance(data, list):
        raise NativeMarketCollectionError("NATIVE_MARKET_CANDLES_INVALID")
    for row in data:
        if not isinstance(row, list) or len(row) < 9 or row[8] != "1":
            continue
        try:
            ts_ms = int(row[0])
        except (TypeError, ValueError) as exc:
            raise NativeMarketCollectionError("NATIVE_MARKET_CANDLES_INVALID") from exc
        closed.append(
            (
                ts_ms,
                _decimal(row[1], "NATIVE_MARKET_CANDLES_INVALID"),
                _decimal(row[2], "NATIVE_MARKET_CANDLES_INVALID"),
                _decimal(row[3], "NATIVE_MARKET_CANDLES_INVALID"),
                _decimal(row[4], "NATIVE_MARKET_CANDLES_INVALID"),
                _decimal(row[5], "NATIVE_MARKET_CANDLES_INVALID", nonnegative=True),
            )
        )
    closed.sort(key=lambda item: item[0])
    if len(closed) < 20 or len({item[0] for item in closed}) != len(closed):
        raise NativeMarketCollectionError("NATIVE_MARKET_CLOSED_CANDLE_COVERAGE_FAILED")
    previous = closed[-2]
    latest = closed[-1]
    if previous[4] <= 0 or latest[4] <= 0:
        raise NativeMarketCollectionError("NATIVE_MARKET_CANDLES_INVALID")
    return_pct = (latest[4] / previous[4] - Decimal("1")) * Decimal("100")
    range_pct = (latest[2] - latest[3]) / latest[4] * Decimal("100")
    volumes = sorted(item[5] for item in closed[-20:])
    midpoint = len(volumes) // 2
    median_volume = (
        volumes[midpoint]
        if len(volumes) % 2
        else (volumes[midpoint - 1] + volumes[midpoint]) / Decimal("2")
    )
    volume_ratio = (
        latest[5] / median_volume if median_volume > 0 else Decimal("0")
    )
    observed_at = str(latest[0])
    return [
        _fact(
            fact_id=f"candle-{label}-close",
            value=canonical_decimal(latest[4]),
            unit="USDT_PER_BTC",
            source=capture,
            observed_at=observed_at,
        ),
        _fact(
            fact_id=f"candle-{label}-return-pct",
            value=canonical_decimal(return_pct),
            unit="PERCENT",
            source=capture,
            observed_at=observed_at,
        ),
        _fact(
            fact_id=f"candle-{label}-range-pct",
            value=canonical_decimal(range_pct),
            unit="PERCENT",
            source=capture,
            observed_at=observed_at,
        ),
        _fact(
            fact_id=f"candle-{label}-volume-vs-20bar-median",
            value=canonical_decimal(volume_ratio),
            unit="RATIO",
            source=capture,
            observed_at=observed_at,
        ),
    ]


class OkxNativeMarketCollector:
    """Collect one BTC-USDT-SWAP public snapshot with explicit coverage."""

    _CANDLES = (("15m", "15m", 96), ("1h", "1H", 168), ("4h", "4H", 90), ("1d", "1Dutc", 60))

    def __init__(self, *, collector: OkxPublicFreshCollector) -> None:
        self._collector = collector

    def _request(
        self,
        *,
        captures: dict[str, PublicRequestCapture],
        raws: dict[str, bytes],
        request_id: str,
        path: str,
        query: Mapping[str, str | int] | None = None,
    ) -> tuple[PublicRequestCapture, bytes]:
        capture, raw = self._collector._get(  # infrastructure-internal reuse
            request_id=request_id,
            path=path,
            query_items=query,
        )
        captures[request_id] = capture
        raws[request_id] = raw
        return capture, raw

    def collect(
        self,
        *,
        run_id: str,
        cycle_index: int,
        prior_market_snapshot: Mapping[str, Any] | None = None,
    ) -> NativeMarketCollection:
        prior_open_interest = _verified_prior_open_interest(
            run_id=run_id,
            cycle_index=cycle_index,
            prior_market_snapshot=prior_market_snapshot,
        )
        captures: dict[str, PublicRequestCapture] = {}
        raws: dict[str, bytes] = {}
        time_capture, time_raw = self._request(
            captures=captures,
            raws=raws,
            request_id="okx-native-server-time",
            path="/api/v5/public/time",
        )
        time_row = _required_row(time_raw, "NATIVE_MARKET_SERVER_TIME_INVALID")
        try:
            server_time_ms = int(str(time_row["ts"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise NativeMarketCollectionError("NATIVE_MARKET_SERVER_TIME_INVALID") from exc
        instrument_capture, instrument_raw = self._request(
            captures=captures,
            raws=raws,
            request_id="okx-native-instrument",
            path="/api/v5/public/instruments",
            query={"instId": OKX_INSTRUMENT_ID, "instType": "SWAP"},
        )
        instrument = _required_row(
            instrument_raw, "NATIVE_MARKET_INSTRUMENT_INVALID"
        )
        if instrument.get("instId") != OKX_INSTRUMENT_ID or instrument.get("state") != "live":
            raise NativeMarketCollectionError("NATIVE_MARKET_INSTRUMENT_NOT_LIVE")
        contract_multiplier = _decimal(
            instrument.get("ctVal"),
            "NATIVE_MARKET_CONTRACT_MULTIPLIER_INVALID",
            positive=True,
        )
        okx_ct_mult = _decimal(
            instrument.get("ctMult"),
            "NATIVE_MARKET_OKX_CT_MULT_INVALID",
            positive=True,
        )
        quantity_step = _decimal(
            instrument.get("lotSz"),
            "NATIVE_MARKET_QUANTITY_STEP_INVALID",
            positive=True,
        )
        minimum_quantity = _decimal(
            instrument.get("minSz"),
            "NATIVE_MARKET_MINIMUM_QUANTITY_INVALID",
            positive=True,
        )
        price_tick = _decimal(
            instrument.get("tickSz"),
            "NATIVE_MARKET_PRICE_TICK_INVALID",
            positive=True,
        )
        if (
            instrument.get("ctValCcy") != "BTC"
            or instrument.get("ctType") != "linear"
            or instrument.get("settleCcy") != "USDT"
        ):
            raise NativeMarketCollectionError(
                "NATIVE_MARKET_CONTRACT_SPECIFICATION_INVALID"
            )
        if minimum_quantity % quantity_step != 0:
            raise NativeMarketCollectionError(
                "NATIVE_MARKET_QUANTITY_CONSTRAINTS_INVALID"
            )
        contract_specification = {
            "instrument_id": OKX_INSTRUMENT_ID,
            "contract_multiplier": canonical_decimal(contract_multiplier),
            "contract_multiplier_unit": "BTC_PER_CONTRACT",
            "contract_multiplier_source_field": "ctVal",
            "okx_ct_val": canonical_decimal(contract_multiplier),
            "okx_ct_mult": canonical_decimal(okx_ct_mult),
            "contract_value_currency": "BTC",
            "contract_type": "linear",
            "settlement_currency": "USDT",
            "quantity_step_contracts": canonical_decimal(quantity_step),
            "minimum_quantity_contracts": canonical_decimal(minimum_quantity),
            "price_tick_usdt": canonical_decimal(price_tick),
            "source_request_id": instrument_capture.request_id,
            "source_raw_body_sha256": instrument_capture.raw_body_sha256,
            "available_at": timestamp(instrument_capture.response_received_at),
        }
        ticker_capture, ticker_raw = self._request(
            captures=captures,
            raws=raws,
            request_id="okx-native-ticker",
            path="/api/v5/market/ticker",
            query={"instId": OKX_INSTRUMENT_ID},
        )
        ticker = _required_row(ticker_raw, "NATIVE_MARKET_TICKER_INVALID")
        mark_capture, mark_raw = self._request(
            captures=captures,
            raws=raws,
            request_id="okx-native-mark-price",
            path="/api/v5/public/mark-price",
            query={"instId": OKX_INSTRUMENT_ID, "instType": "SWAP"},
        )
        mark = _required_row(mark_raw, "NATIVE_MARKET_MARK_INVALID")
        mark_price = canonical_decimal(
            _decimal(mark.get("markPx"), "NATIVE_MARKET_MARK_INVALID")
        )
        facts = [
            _fact(
                fact_id="server-time-ms",
                value=str(server_time_ms),
                unit="UNIX_MS",
                source=time_capture,
                observed_at=str(server_time_ms),
            ),
            _fact(
                fact_id="instrument-live",
                value="true",
                unit="BOOLEAN",
                source=instrument_capture,
            ),
            _fact(
                fact_id="instrument-contract-multiplier",
                value=canonical_decimal(contract_multiplier),
                unit="BTC_PER_CONTRACT",
                source=instrument_capture,
            ),
            _fact(
                fact_id="instrument-okx-ct-mult",
                value=canonical_decimal(okx_ct_mult),
                unit="OKX_CT_MULT",
                source=instrument_capture,
            ),
            _fact(
                fact_id="instrument-quantity-step-contracts",
                value=canonical_decimal(quantity_step),
                unit="CONTRACTS",
                source=instrument_capture,
            ),
            _fact(
                fact_id="instrument-minimum-quantity-contracts",
                value=canonical_decimal(minimum_quantity),
                unit="CONTRACTS",
                source=instrument_capture,
            ),
            _fact(
                fact_id="instrument-price-tick-usdt",
                value=canonical_decimal(price_tick),
                unit="USDT_PER_BTC",
                source=instrument_capture,
            ),
            _fact(
                fact_id="mark-price",
                value=mark_price,
                unit="USDT_PER_BTC",
                source=mark_capture,
                observed_at=str(mark.get("ts") or server_time_ms),
            ),
        ]
        for field, fact_id, unit in (
            ("last", "ticker-last", "USDT_PER_BTC"),
            ("bidPx", "ticker-best-bid", "USDT_PER_BTC"),
            ("askPx", "ticker-best-ask", "USDT_PER_BTC"),
            ("vol24h", "ticker-volume-24h-contracts", "CONTRACTS"),
            ("volCcy24h", "ticker-volume-24h-btc", "BTC"),
        ):
            facts.append(
                _fact(
                    fact_id=fact_id,
                    value=canonical_decimal(
                        _decimal(ticker.get(field), "NATIVE_MARKET_TICKER_INVALID")
                    ),
                    unit=unit,
                    source=ticker_capture,
                    observed_at=str(ticker.get("ts") or server_time_ms),
                )
            )

        current_bucket = {
            "15m": (server_time_ms // 900_000) * 900_000,
            "1h": (server_time_ms // 3_600_000) * 3_600_000,
            "4h": (server_time_ms // 14_400_000) * 14_400_000,
            "1d": (server_time_ms // 86_400_000) * 86_400_000,
        }
        for label, bar, limit in self._CANDLES:
            capture, raw = self._request(
                captures=captures,
                raws=raws,
                request_id=f"okx-native-candles-{label}",
                path="/api/v5/market/history-candles",
                query={
                    "after": current_bucket[label],
                    "bar": bar,
                    "instId": OKX_INSTRUMENT_ID,
                    "limit": limit,
                },
            )
            facts.extend(_candle_metrics(raw=raw, capture=capture, label=label))

        optional_failures: dict[str, str] = {}
        optional_specs = (
            (
                "open-interest",
                "/api/v5/public/open-interest",
                {"instId": OKX_INSTRUMENT_ID, "instType": "SWAP"},
            ),
            (
                "funding-rate",
                "/api/v5/public/funding-rate",
                {"instId": OKX_INSTRUMENT_ID},
            ),
            (
                "books",
                "/api/v5/market/books",
                {"instId": OKX_INSTRUMENT_ID, "sz": 50},
            ),
            (
                "trades",
                "/api/v5/market/trades",
                {"instId": OKX_INSTRUMENT_ID, "limit": 100},
            ),
        )
        optional_rows: dict[str, tuple[PublicRequestCapture, bytes]] = {}
        for key, path, query in optional_specs:
            try:
                optional_rows[key] = self._request(
                    captures=captures,
                    raws=raws,
                    request_id=f"okx-native-{key}",
                    path=path,
                    query=query,
                )
            except (OkxPublicCollectionError, NativeMarketCollectionError) as exc:
                optional_failures[key] = str(exc)

        if "open-interest" in optional_rows:
            capture, raw = optional_rows["open-interest"]
            row = _required_row(raw, "NATIVE_MARKET_OPEN_INTEREST_INVALID")
            current_open_interest = _fact(
                fact_id="open-interest-btc",
                value=canonical_decimal(
                    _decimal(row.get("oiCcy"), "NATIVE_MARKET_OPEN_INTEREST_INVALID")
                ),
                unit="BTC",
                source=capture,
                observed_at=str(row.get("ts") or server_time_ms),
            )
        else:
            current_open_interest = _unknown(
                fact_id="open-interest-btc",
                reason=optional_failures.get("open-interest", "SOURCE_UNAVAILABLE"),
            )
        facts.append(current_open_interest)
        facts.append(
            _cross_cycle_open_interest_fact(
                cycle_index=cycle_index,
                current_fact=current_open_interest,
                prior_open_interest=prior_open_interest,
            )
        )
        if "funding-rate" in optional_rows:
            capture, raw = optional_rows["funding-rate"]
            row = _required_row(raw, "NATIVE_MARKET_FUNDING_INVALID")
            facts.append(
                _fact(
                    fact_id="funding-rate",
                    value=canonical_decimal(
                        _decimal(row.get("fundingRate"), "NATIVE_MARKET_FUNDING_INVALID")
                    ),
                    unit="RATE",
                    source=capture,
                    observed_at=str(server_time_ms),
                )
            )
        else:
            facts.append(
                _unknown(
                    fact_id="funding-rate",
                    reason=optional_failures.get("funding-rate", "SOURCE_UNAVAILABLE"),
                )
            )
        if "books" in optional_rows:
            capture, raw = optional_rows["books"]
            row = _required_row(raw, "NATIVE_MARKET_BOOK_INVALID")
            bids, asks = row.get("bids"), row.get("asks")
            if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
                raise NativeMarketCollectionError("NATIVE_MARKET_BOOK_INVALID")
            bid_size = sum(
                (_decimal(item[1], "NATIVE_MARKET_BOOK_INVALID") for item in bids[:5]),
                Decimal("0"),
            )
            ask_size = sum(
                (_decimal(item[1], "NATIVE_MARKET_BOOK_INVALID") for item in asks[:5]),
                Decimal("0"),
            )
            denominator = bid_size + ask_size
            imbalance = (bid_size - ask_size) / denominator if denominator > 0 else Decimal("0")
            facts.append(
                _fact(
                    fact_id="book-top5-imbalance",
                    value=canonical_decimal(imbalance),
                    unit="RATIO_NEG1_TO_1",
                    source=capture,
                    observed_at=str(row.get("ts") or server_time_ms),
                )
            )
        else:
            facts.append(
                _unknown(
                    fact_id="book-top5-imbalance",
                    reason=optional_failures.get("books", "SOURCE_UNAVAILABLE"),
                )
            )
        if "trades" in optional_rows:
            capture, raw = optional_rows["trades"]
            rows = _root(raw)
            buy = sum(
                (
                    _decimal(row.get("sz"), "NATIVE_MARKET_TRADES_INVALID")
                    for row in rows
                    if row.get("side") == "buy"
                ),
                Decimal("0"),
            )
            sell = sum(
                (
                    _decimal(row.get("sz"), "NATIVE_MARKET_TRADES_INVALID")
                    for row in rows
                    if row.get("side") == "sell"
                ),
                Decimal("0"),
            )
            total = buy + sell
            imbalance = (buy - sell) / total if total > 0 else Decimal("0")
            facts.append(
                _fact(
                    fact_id="recent-trade-side-imbalance",
                    value=canonical_decimal(imbalance),
                    unit="RATIO_NEG1_TO_1",
                    source=capture,
                    observed_at=str(server_time_ms),
                )
            )
        else:
            facts.append(
                _unknown(
                    fact_id="recent-trade-side-imbalance",
                    reason=optional_failures.get("trades", "SOURCE_UNAVAILABLE"),
                )
            )
        facts.extend(
            [
                _unknown(
                    fact_id="crowding-positioning",
                    reason="NO_FROZEN_RELIABLE_PUBLIC_POSITIONING_SOURCE_IN_PILOT",
                ),
                _unknown(
                    fact_id="liquidation-stress",
                    reason="NO_FROZEN_RELIABLE_PUBLIC_LIQUIDATION_SOURCE_IN_PILOT",
                ),
                _unknown(
                    fact_id="news-cross-market",
                    reason="NEWS_SOURCE_NOT_AUTHORIZED_FOR_INITIAL_STABILITY_PILOT",
                ),
            ]
        )
        fact_ids = [str(item["fact_id"]) for item in facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise NativeMarketCollectionError("NATIVE_MARKET_FACT_ID_DUPLICATE")
        captured_through = max(
            timestamp(item.response_received_at) for item in captures.values()
        )
        market_information_snapshot = _build_dynamic_market_snapshot(
            run_id=run_id,
            cycle_index=cycle_index,
            captured_through=captured_through,
            facts=facts,
            prior_open_interest=prior_open_interest,
        )
        snapshot = self_digest(
            {
                "schema_id": "native_btc_public_market_snapshot",
                "schema_version": "1.1.0",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "instrument_id": OKX_INSTRUMENT_ID,
                "server_time_ms": server_time_ms,
                "captured_through": captured_through,
                "mark_price": mark_price,
                "contract_specification": contract_specification,
                "facts": facts,
                "market_information_snapshot": market_information_snapshot,
                "prior_market_snapshot_digest": (
                    prior_market_snapshot.get("native_market_snapshot_digest")
                    if prior_market_snapshot is not None
                    else None
                ),
                "source_captures": [
                    captures[key].to_dict() for key in sorted(captures)
                ],
                "required_request_ids": [
                    "okx-native-server-time",
                    "okx-native-instrument",
                    "okx-native-ticker",
                    "okx-native-mark-price",
                    "okx-native-candles-15m",
                    "okx-native-candles-1h",
                    "okx-native-candles-4h",
                    "okx-native-candles-1d",
                ],
                "optional_failures": optional_failures,
                "data_scope": "OFFICIAL_PUBLIC_MARKET_ONLY",
                "point_in_time": True,
                "missing_is_zero": False,
                "account_data_accessed": False,
                "order_data_accessed": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
            },
            "native_market_snapshot_digest",
        )
        return NativeMarketCollection(
            snapshot=snapshot,
            raw_body_by_request_id=raws,
        )


__all__ = [
    "NativeMarketCollection",
    "NativeMarketCollectionError",
    "OkxNativeMarketCollector",
]
