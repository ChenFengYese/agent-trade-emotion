"""Prospective 24-hour public-market research for one Strategy Agent.

This module is deliberately a thin vertical slice around the existing
``single_agent_research`` state, risk, ledger, and matching code.  It collects
credential-free OKX public observations for the six V1 markets, records every
request, builds one point-in-time context per hour, and appends it to the same
write-once single-Agent state chain.  It has no account or order capability.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlencode

from trade_system.theory_paper.common import digest_json, sha256_file
from trade_system.theory_paper.market import _book_measures, fetch_news_headlines

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_decimal,
    canonical_digest,
    load_json_strict,
    self_digest,
    write_once_json,
)
from ..infrastructure.fresh_market.okx_public import (
    OKX_PUBLIC_BASE_URL,
    OkxCurlPublicHttpTransport,
    OkxPublicFreshCollector,
    _decode_json,
)
from ..infrastructure.authority.current_research import (
    assert_current_research_start_authorized,
)
from .single_agent_research import (
    FUNDING_PROXY_STATUS,
    EXECUTION_AUTHORITY,
    SYMBOLS,
    SYSTEM_MODE,
    SingleAgentResearchError,
    _initial_state,
    _iso,
    _load_verified,
    _portfolio_from_document,
    _run_documents,
    _ts,
    _write_atomic_json,
    normalize_seen_v1_cycle,
)


PROSPECTIVE_EVIDENCE_CLASS = "PROSPECTIVE_24H_PUBLIC_PAPER"
PROSPECTIVE_SCHEMA_VERSION = "1.0.0"
DECISION_CYCLES = 24
TERMINAL_CYCLE = 25
MAXIMUM_CYCLE_LATENESS = timedelta(minutes=90)
ZERO = Decimal("0")
ONE = Decimal("1")

INSTRUMENT_IDS = {
    "SNDKUSDT": "SNDK-USDT-SWAP",
    "MUUSDT": "MU-USDT-SWAP",
    "BTCUSDT": "BTC-USDT-SWAP",
    "ETHUSDT": "ETH-USDT-SWAP",
    "SOLUSDT": "SOL-USDT-SWAP",
    "HYPEUSDT": "HYPE-USDT-SWAP",
}
INDEX_IDS = {symbol: instrument.removesuffix("-SWAP") for symbol, instrument in INSTRUMENT_IDS.items()}
BASE_CURRENCIES = {symbol: instrument.split("-", 1)[0] for symbol, instrument in INSTRUMENT_IDS.items()}
TIMEFRAME_REQUESTS = {
    "15m": ("15m", 15 * 60 * 1000),
    "1h": ("1H", 60 * 60 * 1000),
    "4h": ("4H", 4 * 60 * 60 * 1000),
    "1d": ("1Dutc", 24 * 60 * 60 * 1000),
    "1w": ("1Wutc", 7 * 24 * 60 * 60 * 1000),
}
NEWS_QUERIES = {
    "SNDKUSDT": "Sandisk SNDK earnings SEC investor relations stock",
    "MUUSDT": "Micron MU earnings SEC investor relations stock semiconductors",
    "BTCUSDT": "Bitcoin BTC macro regulation ETF market",
    "ETHUSDT": "Ethereum ETH foundation upgrade market",
    "SOLUSDT": "Solana SOL network ecosystem market",
    "HYPEUSDT": "Hyperliquid HYPE protocol market",
}


class ProspectiveResearchError(ValueError):
    """A prospective collection, freeze, schedule, or lineage boundary failed."""


@dataclass(frozen=True, slots=True)
class _RequestSpec:
    symbol: str
    name: str
    path: str
    query: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ProspectiveCollection:
    context: Mapping[str, Any]
    acquisition: Mapping[str, Any]
    market_snapshot: Mapping[str, Any]
    news_snapshot: Mapping[str, Any]


def _d(value: Any, code: str) -> Decimal:
    if isinstance(value, bool):
        raise ProspectiveResearchError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ProspectiveResearchError(code) from exc
    if not result.is_finite():
        raise ProspectiveResearchError(code)
    return result


def _now() -> datetime:
    return datetime.now(UTC)


def _write_once_bytes(path: Path, payload: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != payload:
            raise ProspectiveResearchError(f"WRITE_ONCE_CONFLICT:{target}")
        return
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _okx_root(raw: bytes, code: str) -> dict[str, Any]:
    root = _decode_json(raw)
    if (
        not isinstance(root, dict)
        or root.get("code") != "0"
        or root.get("msg") != ""
        or not isinstance(root.get("data"), list)
    ):
        raise ProspectiveResearchError(code)
    return root


def _request_specs(cycle_index: int) -> list[_RequestSpec]:
    specs: list[_RequestSpec] = []
    for symbol in SYMBOLS:
        instrument = INSTRUMENT_IDS[symbol]
        ccy = BASE_CURRENCIES[symbol]

        def add(name: str, path: str, query: Mapping[str, str | int]) -> None:
            specs.append(
                _RequestSpec(
                    symbol=symbol,
                    name=name,
                    path=path,
                    query=tuple(sorted((str(key), str(value)) for key, value in query.items())),
                )
            )

        add("instrument", "/api/v5/public/instruments", {"instType": "SWAP", "instId": instrument})
        add("ticker", "/api/v5/market/ticker", {"instId": instrument})
        add("mark", "/api/v5/public/mark-price", {"instType": "SWAP", "instId": instrument})
        add("index", "/api/v5/market/index-tickers", {"instId": INDEX_IDS[symbol]})
        add("open_interest", "/api/v5/public/open-interest", {"instType": "SWAP", "instId": instrument})
        add("funding", "/api/v5/public/funding-rate", {"instId": instrument})
        add("funding_history", "/api/v5/public/funding-rate-history", {"instId": instrument, "limit": 100})
        add("book", "/api/v5/market/books", {"instId": instrument, "sz": 20})
        add("trades", "/api/v5/market/trades", {"instId": instrument, "limit": 100})
        add(
            "liquidations",
            "/api/v5/public/liquidation-orders",
            {"instType": "SWAP", "uly": INDEX_IDS[symbol], "state": "filled", "limit": 100},
        )
        add(
            "oi_history",
            "/api/v5/rubik/stat/contracts/open-interest-history",
            {"instId": instrument, "period": "1H", "limit": 100},
        )
        add(
            "long_short",
            "/api/v5/rubik/stat/contracts/long-short-account-ratio",
            {"ccy": ccy, "period": "1H"},
        )
        add(
            "taker_volume",
            "/api/v5/rubik/stat/taker-volume",
            {"ccy": ccy, "instType": "CONTRACTS", "period": "1H"},
        )
        for timeframe, (bar, _) in TIMEFRAME_REQUESTS.items():
            add(
                f"candles_{timeframe}",
                "/api/v5/market/history-candles",
                {"instId": instrument, "bar": bar, "limit": 300},
            )
    slow_review_observations = {"long_short", "taker_volume", "liquidations"}
    if cycle_index in {1, TERMINAL_CYCLE} or cycle_index % 4 == 0:
        return specs
    return [spec for spec in specs if spec.name not in slow_review_observations]


def _request_routes(spec: _RequestSpec) -> tuple[_RequestSpec, ...]:
    """Return the bounded official-public route order for one observation."""

    if not spec.name.startswith("candles_"):
        return (spec,)
    fallback = _RequestSpec(
        symbol=spec.symbol,
        name=spec.name,
        path="/api/v5/market/candles",
        query=spec.query,
    )
    return (spec, fallback)


def _attempt_specs(spec: _RequestSpec) -> tuple[_RequestSpec, ...]:
    routes = _request_routes(spec)
    if spec.name in {"instrument", "mark"}:
        return (spec, spec, spec, spec)
    if spec.name == "candles_15m":
        return routes + routes
    if spec.name.startswith("candles_"):
        return routes
    return (spec,)


def _request_url(spec: _RequestSpec) -> str:
    value = f"{OKX_PUBLIC_BASE_URL}{spec.path}"
    if spec.query:
        value += "?" + urlencode(spec.query)
    return value


def _rows(root: Mapping[str, Any] | None) -> list[Any]:
    value = root.get("data") if isinstance(root, Mapping) else None
    return list(value) if isinstance(value, list) else []


def _latest_ms(rows: Sequence[Any]) -> int | None:
    values: list[int] = []
    for row in rows:
        raw: Any = None
        if isinstance(row, Mapping):
            raw = row.get("ts") or row.get("time") or row.get("fundingTime")
            if raw is None and isinstance(row.get("details"), list):
                for detail in row["details"]:
                    if isinstance(detail, Mapping):
                        candidate = detail.get("ts") or detail.get("time")
                        try:
                            values.append(int(str(candidate)))
                        except (TypeError, ValueError):
                            pass
        elif isinstance(row, list) and row:
            raw = row[0]
        try:
            if raw is not None:
                values.append(int(str(raw)))
        except (TypeError, ValueError):
            pass
    return max(values, default=None)


def _freshness_limit(name: str) -> int:
    if name.startswith("candles_"):
        timeframe = name.removeprefix("candles_")
        return int(TIMEFRAME_REQUESTS[timeframe][1] / 1000 * 2)
    if name in {"funding", "funding_history"}:
        return 10 * 60 * 60
    if name in {"oi_history", "long_short", "taker_volume"}:
        return 3 * 60 * 60
    if name == "liquidations":
        return 24 * 60 * 60
    return 5 * 60


def _capture_request(
    collector: OkxPublicFreshCollector,
    spec: _RequestSpec,
    *,
    receipt_root: Path | None = None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    first_attempted_at = _now()

    def finish(value: dict[str, Any]) -> dict[str, Any]:
        if receipt_root is not None:
            receipt = self_digest(
                {
                    "schema_id": "prospective_public_request_attempt_receipt",
                    "schema_version": PROSPECTIVE_SCHEMA_VERSION,
                    "symbol": spec.symbol,
                    "observation": spec.name,
                    "final_status": value["status"],
                    "selected_route": (
                        None
                        if value.get("used_spec") is None
                        else value["used_spec"].path
                    ),
                    "attempts": attempts,
                    "authority": "PUBLIC_READ_ONLY_NO_CREDENTIALS_NO_ACCOUNT_NO_ORDERS",
                },
                "receipt_digest",
            )
            write_once_json(
                Path(receipt_root) / spec.symbol / f"{spec.name}.json", receipt
            )
            value["attempt_receipt_digest"] = receipt["receipt_digest"]
        else:
            value["attempt_receipt_digest"] = None
        return value

    planned = _attempt_specs(spec)
    for attempt_index, routed_spec in enumerate(planned, start=1):
        attempted_at = _now()
        try:
            capture, raw = collector._get(  # one bounded public transport; no account surface
                request_id=(
                    f"okx-{spec.symbol.lower()}-{spec.name.replace('_', '-')}"
                    f"-attempt-{attempt_index}"
                ),
                path=routed_spec.path,
                query_items=dict(routed_spec.query),
            )
            root = _okx_root(raw, f"OKX_PAYLOAD_INVALID:{spec.symbol}:{spec.name}")
            attempts.append(
                {
                    "attempt": attempt_index,
                    "route": routed_spec.path,
                    "url": _request_url(routed_spec),
                    "request_started_at": _iso(capture.request_started_at),
                    "response_received_at": _iso(capture.response_received_at),
                    "status": "SUCCESS",
                    "http_status": capture.http_status,
                    "rows": len(_rows(root)),
                    "raw_sha256": capture.raw_body_sha256,
                    "raw_bytes": capture.raw_body_byte_length,
                    "error": None,
                }
            )
            return finish({
                "spec": spec,
                "used_spec": routed_spec,
                "status": "SUCCESS",
                "capture": capture,
                "raw": raw,
                "root": root,
                "attempted_at": first_attempted_at,
                "attempt_count": attempt_index,
                "prior_attempt_errors": [
                    row for row in attempts[:-1] if row["status"] != "SUCCESS"
                ],
                "error": None,
            })
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt_index,
                    "route": routed_spec.path,
                    "url": _request_url(routed_spec),
                    "attempted_at": _iso(attempted_at),
                    "response_received_at": None,
                    "status": "FAILED_UNKNOWN",
                    "http_status": None,
                    "rows": None,
                    "raw_sha256": None,
                    "raw_bytes": None,
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
            if attempt_index < len(planned):
                time.sleep(min(2.0, 0.35 * attempt_index))
    return finish({
        "spec": spec,
        "used_spec": None,
        "status": "FAILED_UNKNOWN",
        "capture": None,
        "raw": None,
        "root": None,
        "attempted_at": first_attempted_at,
        "attempt_count": len(planned),
        "prior_attempt_errors": attempts,
        "error": attempts[-1]["error"],
    })


def _candle_rows(root: Mapping[str, Any], *, duration_ms: int) -> list[list[Any]]:
    output: list[list[Any]] = []
    for row in _rows(root):
        if not isinstance(row, list) or len(row) < 9 or str(row[8]) != "1":
            continue
        try:
            open_ms = int(str(row[0]))
        except (TypeError, ValueError) as exc:
            raise ProspectiveResearchError("OKX_CANDLE_TIME_INVALID") from exc
        output.append(
            [
                open_ms,
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                str(row[6]),
                open_ms + duration_ms - 1,
                str(row[7]),
                None,
                None,
                None,
                "OKX_CONFIRM_1",
            ]
        )
    output.sort(key=lambda item: int(item[0]))
    if not output:
        raise ProspectiveResearchError("OKX_CLOSED_CANDLES_EMPTY")
    return output


def _utc_bucket_open(open_ms: int, duration_ms: int) -> int:
    if duration_ms == 7 * 24 * 60 * 60 * 1000:
        monday_offset_ms = 4 * 24 * 60 * 60 * 1000
        return (
            (open_ms - monday_offset_ms) // duration_ms * duration_ms
            + monday_offset_ms
        )
    return open_ms // duration_ms * duration_ms


def _aggregate_candle_rows(
    rows: Sequence[Sequence[Any]],
    *,
    source_duration_ms: int,
    target_duration_ms: int,
    source_timeframe: str,
) -> list[list[Any]]:
    """Aggregate only complete fixed UTC buckets from already closed lower bars."""

    if (
        source_duration_ms <= 0
        or target_duration_ms <= source_duration_ms
        or target_duration_ms % source_duration_ms != 0
    ):
        raise ProspectiveResearchError("CANDLE_AGGREGATION_DURATION_INVALID")
    ratio = target_duration_ms // source_duration_ms
    grouped: dict[int, list[Sequence[Any]]] = {}
    for row in rows:
        if len(row) < 7:
            continue
        try:
            open_ms = int(str(row[0]))
        except (TypeError, ValueError):
            continue
        bucket = _utc_bucket_open(open_ms, target_duration_ms)
        grouped.setdefault(bucket, []).append(row)

    output: list[list[Any]] = []
    for bucket, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda row: int(str(row[0])))
        expected = [
            bucket + index * source_duration_ms for index in range(ratio)
        ]
        observed = [int(str(row[0])) for row in ordered]
        if observed != expected:
            continue
        open_price = _d(ordered[0][1], "CANDLE_AGGREGATION_VALUE_INVALID")
        high = max(_d(row[2], "CANDLE_AGGREGATION_VALUE_INVALID") for row in ordered)
        low = min(_d(row[3], "CANDLE_AGGREGATION_VALUE_INVALID") for row in ordered)
        close = _d(ordered[-1][4], "CANDLE_AGGREGATION_VALUE_INVALID")
        volume = sum(
            (_d(row[5], "CANDLE_AGGREGATION_VALUE_INVALID") for row in ordered),
            ZERO,
        )
        quote_values = [row[7] for row in ordered if len(row) > 7]
        quote_volume = (
            sum(
                (
                    _d(value, "CANDLE_AGGREGATION_VALUE_INVALID")
                    for value in quote_values
                ),
                ZERO,
            )
            if len(quote_values) == len(ordered)
            and all(value is not None for value in quote_values)
            else None
        )
        output.append(
            [
                bucket,
                canonical_decimal(open_price),
                canonical_decimal(high),
                canonical_decimal(low),
                canonical_decimal(close),
                canonical_decimal(volume),
                bucket + target_duration_ms - 1,
                None if quote_volume is None else canonical_decimal(quote_volume),
                None,
                None,
                None,
                f"DERIVED_{source_timeframe.upper()}_UTC_COMPLETE_BUCKET",
            ]
        )
    return output


def _latest_row(rows: Sequence[Any]) -> Any:
    if not rows:
        return None

    def key(row: Any) -> int:
        if isinstance(row, list) and row:
            try:
                return int(str(row[0]))
            except (TypeError, ValueError):
                return -1
        if isinstance(row, Mapping):
            try:
                return int(str(row.get("ts") or row.get("fundingTime") or -1))
            except (TypeError, ValueError):
                return -1
        return -1

    return max(rows, key=key)


def _trade_measures(
    rows: Sequence[Any],
    *,
    contract_value: Decimal,
    decision_at: str,
    requested_count: int = 100,
) -> dict[str, Any]:
    buy_base = ZERO
    sell_base = ZERO
    buy_quote = ZERO
    sell_quote = ZERO
    buy_count = 0
    sell_count = 0
    trade_times_ms: list[int] = []
    decision_ms = int(_ts(decision_at).timestamp() * 1000)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            price = _d(row.get("px"), "OKX_TRADE_INVALID")
            base = _d(row.get("sz"), "OKX_TRADE_INVALID") * contract_value
            trade_ms = int(str(row.get("ts")))
        except (ProspectiveResearchError, TypeError, ValueError):
            continue
        if trade_ms > decision_ms:
            continue
        trade_times_ms.append(trade_ms)
        if row.get("side") == "buy":
            buy_base += base
            buy_quote += base * price
            buy_count += 1
        elif row.get("side") == "sell":
            sell_base += base
            sell_quote += base * price
            sell_count += 1
    total_quote = buy_quote + sell_quote
    earliest_ms = min(trade_times_ms) if trade_times_ms else None
    latest_ms = max(trade_times_ms) if trade_times_ms else None
    return {
        "status": "OBSERVED_RECENT_TRADES" if buy_count + sell_count else "UNKNOWN_EMPTY",
        "trade_count": buy_count + sell_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "taker_buy_base_volume": canonical_decimal(buy_base),
        "taker_sell_base_volume": canonical_decimal(sell_base),
        "taker_buy_quote_volume": canonical_decimal(buy_quote),
        "taker_sell_quote_volume": canonical_decimal(sell_quote),
        "taker_buy_quote_share": (
            None if total_quote <= ZERO else canonical_decimal(buy_quote / total_quote)
        ),
        "requested_count": requested_count,
        "raw_row_count": len(rows),
        "timestamped_trade_count": len(trade_times_ms),
        "window_start": (
            None
            if earliest_ms is None
            else _iso(datetime.fromtimestamp(earliest_ms / 1000, UTC))
        ),
        "window_end": (
            None
            if latest_ms is None
            else _iso(datetime.fromtimestamp(latest_ms / 1000, UTC))
        ),
        "window_span_seconds": (
            None
            if earliest_ms is None or latest_ms is None
            else canonical_decimal(
                Decimal(latest_ms - earliest_ms) / Decimal("1000")
            )
        ),
        "window_semantics": "LATEST_N_TRADES_NOT_FIXED_TIME_WINDOW",
        "cross_cycle_comparable": False,
        "interpretation_boundary": "RECENT_AGGRESSOR_SIDE_PROXY_NOT_PARTICIPANT_IDENTITY",
    }


def _funding_events(
    symbol: str,
    funding_rows: Sequence[Any],
    *,
    candles_15m: Sequence[list[Any]],
    available_at: str,
    decision_at: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    decision_ms = int(_ts(decision_at).timestamp() * 1000)
    for row in funding_rows:
        if not isinstance(row, Mapping):
            continue
        try:
            funding_ms = int(str(row.get("fundingTime")))
            rate = _d(
                row.get("realizedRate") if row.get("realizedRate") not in {None, ""} else row.get("fundingRate"),
                "OKX_FUNDING_RATE_INVALID",
            )
        except (ProspectiveResearchError, TypeError, ValueError):
            continue
        if funding_ms > decision_ms:
            continue
        preceding = [bar for bar in candles_15m if int(bar[6]) < funding_ms]
        if not preceding:
            continue
        mark_proxy = str(preceding[-1][4])
        value = {
            "event_id": f"{symbol}:funding:{funding_ms}",
            "symbol": symbol,
            "funding_time_ms": funding_ms,
            "funding_time": _iso(datetime.fromtimestamp(funding_ms / 1000, UTC)),
            "available_at": available_at,
            "funding_rate": canonical_decimal(rate),
            "settlement_price_proxy": mark_proxy,
            "settlement_price_basis": "LATEST_CLOSED_15M_TRADE_CANDLE_CLOSE_BEFORE_SETTLEMENT",
            "source": "OKX_PUBLIC_REALIZED_FUNDING_HISTORY",
            "model_boundary": "REALIZED_RATE_WITH_TRADE_PRICE_PROXY_NOT_TRUE_SETTLEMENT_MARK_OR_ACCOUNT_CASHFLOW",
        }
        output.append(self_digest(value, "event_digest"))
    return sorted(output, key=lambda item: int(item["funding_time_ms"]))


def _symbol_snapshot(
    symbol: str,
    successful: Mapping[str, Mapping[str, Any]],
    failures: Mapping[str, str],
    *,
    market_observed_at: str,
    decision_at: str,
) -> dict[str, Any]:
    required = {
        "instrument",
        "mark",
        "candles_15m",
    }
    missing_required = sorted(required - set(successful))
    if missing_required:
        raise ProspectiveResearchError(
            f"REQUIRED_OKX_OBSERVATION_MISSING:{symbol}:{','.join(missing_required)}"
        )
    payload = {name: row["root"] for name, row in successful.items()}
    instrument_rows = _rows(payload["instrument"])
    instrument = instrument_rows[0] if instrument_rows and isinstance(instrument_rows[0], Mapping) else {}
    if instrument.get("instId") != INSTRUMENT_IDS[symbol] or instrument.get("state") != "live":
        raise ProspectiveResearchError(f"OKX_INSTRUMENT_NOT_LIVE:{symbol}")
    contract_value = _d(instrument.get("ctVal"), "OKX_CONTRACT_VALUE_INVALID")
    if contract_value <= ZERO:
        raise ProspectiveResearchError("OKX_CONTRACT_VALUE_INVALID")

    mark_row = _latest_row(_rows(payload["mark"]))
    if not isinstance(mark_row, Mapping):
        raise ProspectiveResearchError(f"OKX_MARK_MISSING:{symbol}")
    mark = _d(mark_row.get("markPx"), "OKX_MARK_INVALID")
    if mark <= ZERO:
        raise ProspectiveResearchError("OKX_MARK_INVALID")

    raw_klines: dict[str, list[list[Any]]] = {}
    kline_lineage: dict[str, dict[str, Any]] = {}
    lower_timeframe = {"1h": "15m", "4h": "1h", "1d": "4h", "1w": "1d"}
    for timeframe, (_, duration_ms) in TIMEFRAME_REQUESTS.items():
        source = payload.get(f"candles_{timeframe}")
        direct_rows: list[list[Any]] = []
        direct_error: str | None = None
        if source is not None:
            try:
                direct_rows = _candle_rows(source, duration_ms=duration_ms)
            except ProspectiveResearchError as exc:
                direct_error = str(exc)
        if direct_rows:
            raw_klines[timeframe] = direct_rows
            request = successful[f"candles_{timeframe}"]
            used_spec: _RequestSpec = request["used_spec"]
            kline_lineage[timeframe] = {
                "status": "DIRECT_OKX_CLOSED_BARS",
                "route": used_spec.path,
                "row_count": len(direct_rows),
                "source_body_sha256": request["capture"].raw_body_sha256,
                "derived_digest": None,
                "limitation": "OKX_CONFIRM_1_PROVIDER_CLOSED_BAR_PROTOCOL",
            }
            continue
        if timeframe == "15m":
            raise ProspectiveResearchError(
                f"REQUIRED_OKX_OBSERVATION_MISSING:{symbol}:candles_15m"
            )
        source_timeframe = lower_timeframe[timeframe]
        source_duration_ms = TIMEFRAME_REQUESTS[source_timeframe][1]
        derived = _aggregate_candle_rows(
            raw_klines[source_timeframe],
            source_duration_ms=source_duration_ms,
            target_duration_ms=duration_ms,
            source_timeframe=source_timeframe,
        )
        raw_klines[timeframe] = derived
        kline_lineage[timeframe] = {
            "status": (
                "DERIVED_FROM_COMPLETE_LOWER_UTC_BUCKETS" if derived else "UNKNOWN"
            ),
            "route": None,
            "source_timeframe": source_timeframe,
            "row_count": len(derived),
            "source_row_count": len(raw_klines[source_timeframe]),
            "source_rows_digest": canonical_digest(raw_klines[source_timeframe]),
            "derived_digest": canonical_digest(derived),
            "direct_collection_error": (
                direct_error
                or failures.get(f"candles_{timeframe}")
                or "DIRECT_OBSERVATION_UNAVAILABLE"
            ),
            "formula": "FIXED_UTC_BUCKET_OPEN_FIRST_HIGH_MAX_LOW_MIN_CLOSE_LAST_VOLUME_SUM_COMPLETE_BUCKETS_ONLY",
            "limitation": (
                "NO_COMPLETE_DERIVED_BUCKET_AVAILABLE" if not derived else None
            ),
        }

    ticker = _latest_row(_rows(payload.get("ticker")))
    index = _latest_row(_rows(payload.get("index")))
    oi = _latest_row(_rows(payload.get("open_interest")))
    funding = _latest_row(_rows(payload.get("funding")))
    oi_history = sorted(
        [row for row in _rows(payload.get("oi_history")) if isinstance(row, list) and len(row) >= 4],
        key=lambda row: int(str(row[0])),
    )
    oi_change = None
    if len(oi_history) >= 2:
        prior = _d(oi_history[-2][3], "OKX_OI_HISTORY_INVALID")
        latest = _d(oi_history[-1][3], "OKX_OI_HISTORY_INVALID")
        if prior != ZERO:
            oi_change = (latest / prior - ONE) * Decimal("100")

    index_price = (
        _d(index.get("idxPx"), "OKX_INDEX_INVALID")
        if isinstance(index, Mapping) and index.get("idxPx") not in {None, ""}
        else None
    )
    basis_bps = None if index_price in {None, ZERO} else (mark / index_price - ONE) * Decimal("10000")

    book_row = _latest_row(_rows(payload.get("book")))
    book = {"bids": [], "asks": []}
    if isinstance(book_row, Mapping):
        for side in ("bids", "asks"):
            for level in book_row.get(side, []):
                if not isinstance(level, list) or len(level) < 2:
                    continue
                try:
                    base_quantity = _d(level[1], "OKX_BOOK_INVALID") * contract_value
                except ProspectiveResearchError:
                    continue
                book[side].append([str(level[0]), canonical_decimal(base_quantity)])
    liquidity = _book_measures(book, float(mark))
    liquidity["strict_resilience_status"] = "UNKNOWN_SNAPSHOT_ONLY"
    liquidity["quantity_conversion"] = "CONTRACT_SIZE_TIMES_CTVAL_TO_BASE_PROXY"

    trade_measure = _trade_measures(
        _rows(payload.get("trades")),
        contract_value=contract_value,
        decision_at=decision_at,
    )
    long_short = _latest_row(_rows(payload.get("long_short")))
    taker_volume = _latest_row(_rows(payload.get("taker_volume")))

    liquidation_details: list[Mapping[str, Any]] = []
    for group in _rows(payload.get("liquidations")):
        if not isinstance(group, Mapping) or group.get("instId") != INSTRUMENT_IDS[symbol]:
            continue
        liquidation_details.extend(
            detail for detail in group.get("details", []) if isinstance(detail, Mapping)
        )
    long_size = ZERO
    short_size = ZERO
    for detail in liquidation_details:
        try:
            base = _d(detail.get("sz"), "OKX_LIQUIDATION_INVALID") * contract_value
        except ProspectiveResearchError:
            continue
        if detail.get("posSide") == "long":
            long_size += base
        elif detail.get("posSide") == "short":
            short_size += base

    ticker_change = None
    if isinstance(ticker, Mapping):
        open_24h = _d(ticker.get("open24h"), "OKX_TICKER_INVALID")
        last = _d(ticker.get("last"), "OKX_TICKER_INVALID")
        ticker_change = None if open_24h == ZERO else (last / open_24h - ONE) * Decimal("100")

    funding_rate = None
    settled_rate = None
    if isinstance(funding, Mapping):
        if funding.get("fundingRate") not in {None, ""}:
            funding_rate = canonical_decimal(_d(funding["fundingRate"], "OKX_FUNDING_INVALID"))
        if funding.get("settFundingRate") not in {None, ""}:
            settled_rate = canonical_decimal(_d(funding["settFundingRate"], "OKX_FUNDING_INVALID"))

    long_short_ratio = None
    if isinstance(long_short, list) and len(long_short) >= 2:
        long_short_ratio = str(long_short[1])
    buy_sell_ratio = None
    if isinstance(taker_volume, list) and len(taker_volume) >= 3:
        buy = _d(taker_volume[1], "OKX_TAKER_VOLUME_INVALID")
        sell = _d(taker_volume[2], "OKX_TAKER_VOLUME_INVALID")
        buy_sell_ratio = None if sell == ZERO else canonical_decimal(buy / sell)

    succeeded = len(successful)
    total = succeeded + len(failures)
    measures = {
        "price": canonical_decimal(mark),
        "ticker_24h": {
            "last": ticker.get("last") if isinstance(ticker, Mapping) else None,
            "change_pct": None if ticker_change is None else canonical_decimal(ticker_change),
            "high": ticker.get("high24h") if isinstance(ticker, Mapping) else None,
            "low": ticker.get("low24h") if isinstance(ticker, Mapping) else None,
            "quote_volume": ticker.get("volCcy24h") if isinstance(ticker, Mapping) else None,
            "trade_count": None,
        },
        "directional_pressure_D": {
            "recent_trades": trade_measure,
            "hourly_taker_buy_sell_ratio": buy_sell_ratio,
            "interpretation_boundary": "FLOW_PRESSURE_PROXY_NOT_PARTICIPANT_IDENTITY",
        },
        "leverage_L": {
            "open_interest_contracts": oi.get("oi") if isinstance(oi, Mapping) else None,
            "open_interest_base": oi.get("oiCcy") if isinstance(oi, Mapping) else None,
            "open_interest_usd": oi.get("oiUsd") if isinstance(oi, Mapping) else None,
            "open_interest_value_1h_change_pct": (
                None if oi_change is None else canonical_decimal(oi_change)
            ),
            "interpretation_boundary": "OI_CHANGE_HAS_NO_DIRECTIONAL_TRUTH_ALONE",
        },
        "crowding_C": {
            "funding_rate": funding_rate,
            "settled_funding_rate": settled_rate,
            "basis_bps": None if basis_bps is None else canonical_decimal(basis_bps),
            "global_account_long_short_ratio": long_short_ratio,
            "top_position_long_short_ratio": None,
            "interpretation_boundary": "MULTI_PROXY_VECTOR_NOT_SINGLE_EMOTION_SCORE",
        },
        "forced_deleveraging_F": {
            "status": "OBSERVED_RECENT_API_WINDOW" if "liquidations" in successful else "UNKNOWN",
            "event_count": len(liquidation_details) if "liquidations" in successful else None,
            "long_liquidation_base_size": canonical_decimal(long_size) if "liquidations" in successful else None,
            "short_liquidation_base_size": canonical_decimal(short_size) if "liquidations" in successful else None,
            "history_completeness": "UNKNOWN_RECENT_ROWS_ONLY",
            "missing_is_zero": False,
        },
        "liquidity_resilience_R": liquidity,
        "timeframes": {},
    }
    funding_capture = successful.get("funding_history", {}).get("capture")
    funding_available_at = (
        _iso(funding_capture.response_received_at)
        if funding_capture is not None
        else market_observed_at
    )
    funding_events = _funding_events(
        symbol,
        _rows(payload.get("funding_history")),
        candles_15m=raw_klines["15m"],
        available_at=funding_available_at,
        decision_at=decision_at,
    )
    return {
        "symbol": symbol,
        "venue": "OKX_OFFICIAL_PUBLIC",
        "instrument_kind": "USDT_LINEAR_SWAP",
        "underlying_session": "CONTINUOUS_DERIVATIVE_WITH_EQUITY_REFERENCE_LIMITATION" if symbol in {"SNDKUSDT", "MUUSDT"} else "CONTINUOUS_CRYPTO_DERIVATIVE",
        "reference_mode": "DERIVATIVE_MARK_WITH_PUBLIC_INDEX",
        "observed_at": market_observed_at,
        "measures": measures,
        "data_quality": {
            "requested_components": total,
            "hard_required_components": ["instrument", "mark", "candles_15m"],
            "success_count": succeeded,
            "error_count": len(failures),
            "coverage_ratio": canonical_decimal(Decimal(succeeded) / Decimal(total)) if total else None,
            "errors": dict(sorted(failures.items())),
            "timeframe_lineage": kline_lineage,
            "strict_R_available": False,
            "liquidation_history_complete": False,
        },
        "funding_events": funding_events,
        "instrument_rules": {
            "inst_id": INSTRUMENT_IDS[symbol],
            "contract_value": canonical_decimal(contract_value),
            "contract_value_currency": instrument.get("ctValCcy"),
            "lot_size_contracts": instrument.get("lotSz"),
            "tick_size": instrument.get("tickSz"),
        },
        "raw_digest": canonical_digest(
            {
                "request_bodies": {
                name: row["capture"].raw_body_sha256
                for name, row in sorted(successful.items())
                },
                "kline_lineage": kline_lineage,
            }
        ),
        "raw": {
            "klines": raw_klines,
            "kline_lineage": kline_lineage,
            "request_body_digests": {
                name: row["capture"].raw_body_sha256
                for name, row in sorted(successful.items())
            },
        },
    }


def collect_okx_six_context(
    *,
    run_root: Path,
    cycle_index: int,
    collector: OkxPublicFreshCollector | None = None,
    news_fetcher: Callable[..., dict[str, Any]] = fetch_news_headlines,
) -> ProspectiveCollection:
    """Collect and persist one complete PIT market/news packet."""

    if not 1 <= cycle_index <= TERMINAL_CYCLE:
        raise ProspectiveResearchError("CYCLE_INDEX_INVALID")
    root = Path(run_root)
    raw_root = root / "raw" / f"cycle-{cycle_index:04d}"
    if raw_root.exists():
        raise ProspectiveResearchError("CYCLE_RAW_ROOT_ALREADY_EXISTS")
    active_collector = collector or OkxPublicFreshCollector(
        transport=OkxCurlPublicHttpTransport(), timeout=30.0
    )
    time_errors: list[str] = []
    time_attempt_rows: list[dict[str, Any]] = []
    time_capture = None
    time_raw = None
    for time_attempt in (1, 2, 3, 4):
        attempted_at = _now()
        try:
            time_capture, time_raw = active_collector._get(
                request_id=(
                    f"okx-cycle-{cycle_index:04d}-server-time-attempt-{time_attempt}"
                ),
                path="/api/v5/public/time",
            )
            time_attempt_rows.append(
                {
                    "attempt": time_attempt,
                    "request_started_at": _iso(time_capture.request_started_at),
                    "response_received_at": _iso(time_capture.response_received_at),
                    "status": "SUCCESS",
                    "http_status": time_capture.http_status,
                    "raw_sha256": time_capture.raw_body_sha256,
                    "raw_bytes": time_capture.raw_body_byte_length,
                    "error": None,
                }
            )
            break
        except Exception as exc:
            error = f"attempt-{time_attempt}:{type(exc).__name__}:{exc}"
            time_errors.append(error)
            time_attempt_rows.append(
                {
                    "attempt": time_attempt,
                    "request_started_at": _iso(attempted_at),
                    "response_received_at": None,
                    "status": "FAILED_UNKNOWN",
                    "http_status": None,
                    "raw_sha256": None,
                    "raw_bytes": None,
                    "error": error,
                }
            )
            if time_attempt < 4:
                time.sleep(min(2.0, 0.35 * time_attempt))
    time_attempt_receipt = self_digest(
        {
            "schema_id": "prospective_server_time_attempt_receipt",
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "cycle_index": cycle_index,
            "final_status": "SUCCESS" if time_capture is not None else "FAILED_UNKNOWN",
            "attempts": time_attempt_rows,
            "authority": "PUBLIC_READ_ONLY_NO_CREDENTIALS_NO_ACCOUNT_NO_ORDERS",
        },
        "receipt_digest",
    )
    write_once_json(raw_root / "request-receipts" / "venue-time.json", time_attempt_receipt)
    if time_capture is None or time_raw is None:
        raise ProspectiveResearchError(
            "OKX_SERVER_TIME_UNAVAILABLE:" + "|".join(time_errors)
        )
    time_root = _okx_root(time_raw, "OKX_SERVER_TIME_INVALID")
    try:
        venue_ms = int(str(time_root["data"][0]["ts"]))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProspectiveResearchError("OKX_SERVER_TIME_INVALID") from exc
    local_ms = int(time_capture.response_received_at.timestamp() * 1000)
    if abs(local_ms - venue_ms) > 120_000:
        raise ProspectiveResearchError("CLOCK_DRIFT_EXCEEDS_120_SECONDS")
    _write_once_bytes(raw_root / "venue-time.json", time_raw)

    results: list[dict[str, Any]] = []
    specs = _request_specs(cycle_index)
    specs_by_symbol = {
        symbol: [spec for spec in specs if spec.symbol == symbol]
        for symbol in SYMBOLS
    }

    def collect_symbol(symbol: str) -> list[dict[str, Any]]:
        priority = {
            "instrument": 0,
            "mark": 1,
            "candles_15m": 2,
            "candles_1h": 3,
            "candles_4h": 4,
            "candles_1d": 5,
            "candles_1w": 6,
        }
        ordered = sorted(
            specs_by_symbol[symbol],
            key=lambda spec: (priority.get(spec.name, 100), spec.name),
        )
        return [
            _capture_request(
                active_collector,
                spec,
                receipt_root=raw_root / "request-receipts",
            )
            for spec in ordered
        ]

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_symbol, symbol): symbol for symbol in SYMBOLS}
        for future in as_completed(futures):
            results.extend(future.result())
    results.sort(key=lambda row: (SYMBOLS.index(row["spec"].symbol), row["spec"].name))

    successful_by_symbol: dict[str, dict[str, dict[str, Any]]] = {symbol: {} for symbol in SYMBOLS}
    failures_by_symbol: dict[str, dict[str, str]] = {symbol: {} for symbol in SYMBOLS}
    acquisition_rows: list[dict[str, Any]] = []
    received_times = [time_capture.response_received_at]
    for result in results:
        spec: _RequestSpec = result["spec"]
        used_spec: _RequestSpec | None = result.get("used_spec")
        request_url = _request_url(used_spec or spec)
        if result["status"] == "SUCCESS":
            capture = result["capture"]
            raw = result["raw"]
            row_root = result["root"]
            raw_path = raw_root / "okx" / spec.symbol / f"{spec.name}.json"
            _write_once_bytes(raw_path, raw)
            received_times.append(capture.response_received_at)
            successful_by_symbol[spec.symbol][spec.name] = result
            latest_ms = _latest_ms(_rows(row_root))
            age_seconds = (
                None
                if latest_ms is None
                else max(0, int((capture.response_received_at.timestamp() * 1000 - latest_ms) / 1000))
            )
            freshness_limit = _freshness_limit(spec.name)
            acquisition_rows.append(
                {
                    "symbol": spec.symbol,
                    "observation": spec.name,
                    "status": "SUCCESS",
                    "method": "GET",
                    "url": request_url,
                    "request_started_at": _iso(capture.request_started_at),
                    "response_received_at": _iso(capture.response_received_at),
                    "http_status": capture.http_status,
                    "rows": len(_rows(row_root)),
                    "latest_observation_at": (
                        None if latest_ms is None else _iso(datetime.fromtimestamp(latest_ms / 1000, UTC))
                    ),
                    "age_seconds_at_receipt": age_seconds,
                    "freshness_limit_seconds": freshness_limit,
                    "freshness": (
                        "UNKNOWN_NO_SOURCE_TIMESTAMP"
                        if age_seconds is None
                        else "CURRENT"
                        if age_seconds <= freshness_limit
                        else "STALE_OR_SPARSE"
                    ),
                    "raw_path": raw_path.relative_to(root).as_posix(),
                    "raw_sha256": capture.raw_body_sha256,
                    "raw_bytes": capture.raw_body_byte_length,
                    "request_identity_digest": capture.request_identity_digest,
                    "attempt_count": result["attempt_count"],
                    "prior_attempt_errors": result["prior_attempt_errors"],
                    "selected_route": used_spec.path if used_spec is not None else None,
                    "attempt_receipt_digest": result["attempt_receipt_digest"],
                }
            )
        else:
            failures_by_symbol[spec.symbol][spec.name] = str(result["error"])
            acquisition_rows.append(
                {
                    "symbol": spec.symbol,
                    "observation": spec.name,
                    "status": "FAILED_UNKNOWN",
                    "method": "GET",
                    "url": request_url,
                    "request_started_at": _iso(result["attempted_at"]),
                    "response_received_at": None,
                    "http_status": None,
                    "rows": None,
                    "latest_observation_at": None,
                    "freshness": "UNKNOWN_COLLECTION_FAILED",
                    "raw_path": None,
                    "raw_sha256": None,
                    "raw_bytes": None,
                    "error": result["error"],
                    "attempt_count": result["attempt_count"],
                    "attempt_errors": result["prior_attempt_errors"],
                    "selected_route": None,
                    "attempt_receipt_digest": result["attempt_receipt_digest"],
                }
            )

    market_observed_at = _iso(max(received_times))
    news = news_fetcher(NEWS_QUERIES, limit_per_query=8, timeout_seconds=12.0)
    news = copy.deepcopy(dict(news))
    news_observed_at = _iso(_ts(str(news.get("observed_at") or _iso(_now()))))
    news["observed_at"] = news_observed_at
    decision_at = _iso(
        max(_ts(market_observed_at), _ts(news_observed_at), _now())
        + timedelta(milliseconds=1)
    )
    _write_once_bytes(
        raw_root / "news-metadata.json", canonical_bytes(news) + b"\n"
    )
    news_rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        value = news.get("queries", {}).get(symbol, {})
        items = value.get("items", []) if isinstance(value, Mapping) else []
        news_rows.append(
            {
                "symbol": symbol,
                "source": "GOOGLE_NEWS_RSS_DISCOVERY_METADATA_ONLY",
                "query": NEWS_QUERIES[symbol],
                "request_observed_at": news_observed_at,
                "status": "SUCCESS" if not value.get("error") else "FAILED_UNKNOWN",
                "rows": len(items) if isinstance(items, list) else 0,
                "error": value.get("error") if isinstance(value, Mapping) else "NEWS_RESULT_INVALID",
                "boundary": "HEADLINE_METADATA_ONLY_NO_ARTICLE_BODY_NO_CAUSAL_TRUTH",
            }
        )

    acquisition_attempts = self_digest(
        {
            "schema_id": "prospective_public_data_acquisition_attempts",
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "venue_time_attempt_receipt_digest": time_attempt_receipt["receipt_digest"],
            "market_requests": acquisition_rows,
            "news_requests": news_rows,
            "summary": {
                "market_request_count": len(acquisition_rows),
                "market_success_count": sum(
                    row["status"] == "SUCCESS" for row in acquisition_rows
                ),
                "market_failure_count": sum(
                    row["status"] != "SUCCESS" for row in acquisition_rows
                ),
                "news_query_count": len(news_rows),
                "news_success_count": sum(
                    row["status"] == "SUCCESS" for row in news_rows
                ),
            },
            "normalization_status": "PENDING",
            "authority": "PUBLIC_READ_ONLY_NO_CREDENTIALS_NO_ACCOUNT_NO_ORDERS",
        },
        "attempts_digest",
    )
    write_once_json(raw_root / "acquisition-attempts.json", acquisition_attempts)

    symbols = [
        _symbol_snapshot(
            symbol,
            successful_by_symbol[symbol],
            failures_by_symbol[symbol],
            market_observed_at=market_observed_at,
            decision_at=decision_at,
        )
        for symbol in SYMBOLS
    ]
    market = {
        "schema_version": "theory-paper-okx-six-market-snapshot.v1",
        "observed_at": market_observed_at,
        "symbols": symbols,
        "failures": failures_by_symbol,
        "point_in_time_rule": "ONLY_PUBLIC_RESPONSES_RECEIVED_BY_DECISION_AT_AND_CONFIRM_1_CLOSED_BARS",
        "market_snapshot_digest": digest_json(
            {
                "observed_at": market_observed_at,
                "symbols": [row["raw_digest"] for row in symbols],
                "failures": failures_by_symbol,
            }
        ),
    }
    acquisition = self_digest(
        {
            "schema_id": "prospective_public_data_acquisition",
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "venue_time": _iso(datetime.fromtimestamp(venue_ms / 1000, UTC)),
            "venue_time_request": time_capture.to_dict(),
            "venue_time_attempt_count": len(time_errors) + 1,
            "venue_time_prior_errors": time_errors,
            "market_requests": acquisition_rows,
            "news_requests": news_rows,
            "summary": {
                "market_request_count": len(acquisition_rows),
                "market_success_count": sum(row["status"] == "SUCCESS" for row in acquisition_rows),
                "market_failure_count": sum(row["status"] != "SUCCESS" for row in acquisition_rows),
                "news_query_count": len(news_rows),
                "news_success_count": sum(row["status"] == "SUCCESS" for row in news_rows),
                "strict_orderbook_resilience": "UNKNOWN_HOURLY_SNAPSHOT_ONLY",
                "liquidation_history_completeness": "UNKNOWN_RECENT_PUBLIC_ROWS_ONLY",
                "opennews_status": "NOT_USED_REQUIRES_BEARER_TOKEN_OUTSIDE_NO_CREDENTIAL_BOUNDARY",
            },
            "authority": "PUBLIC_READ_ONLY_NO_CREDENTIALS_NO_ACCOUNT_NO_ORDERS",
        },
        "acquisition_digest",
    )
    write_once_json(raw_root / "acquisition.json", acquisition)
    context = normalize_seen_v1_cycle(
        market,
        news,
        cycle_index=cycle_index,
        decision_at=decision_at,
    )
    context = dict(context)
    context.pop("context_digest", None)
    context["data_acquisition"] = acquisition
    context["source_mode"] = "PROSPECTIVE_OKX_PUBLIC_PLUS_GOOGLE_NEWS_RSS"
    context["evidence_class"] = PROSPECTIVE_EVIDENCE_CLASS
    context = self_digest(context, "context_digest")
    return ProspectiveCollection(
        context=context,
        acquisition=acquisition,
        market_snapshot=market,
        news_snapshot=news,
    )


def _verify_bindings(project: Path, template: Mapping[str, Any]) -> None:
    rows = template.get("implementation_bindings")
    if not isinstance(rows, list) or not rows:
        raise ProspectiveResearchError("IMPLEMENTATION_BINDING_MISSING")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ProspectiveResearchError("IMPLEMENTATION_BINDING_INVALID")
        path = project / str(row.get("path") or "")
        if not path.is_file() or sha256_file(path) != str(row.get("physical_sha256") or ""):
            raise ProspectiveResearchError(f"IMPLEMENTATION_BINDING_DRIFT:{path}")


def _prospective_source_config(
    template: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    config = copy.deepcopy(dict(template.get("source_config") or {}))
    if not isinstance(config.get("risk_policy"), Mapping):
        raise ProspectiveResearchError("RISK_POLICY_MISSING")
    notionals = template.get("initial_market_notional_usdt")
    if not isinstance(notionals, Mapping):
        raise ProspectiveResearchError("INITIAL_NOTIONALS_MISSING")
    positions: list[dict[str, Any]] = []
    genesis_decision_at = str(context.get("decision_at") or "")
    if not genesis_decision_at:
        raise ProspectiveResearchError("GENESIS_DECISION_TIME_MISSING")
    maximum_horizon_at = _iso(_ts(genesis_decision_at) + timedelta(hours=24))
    taker_fee_rate = _d(
        config["risk_policy"].get("default_taker_fee_rate", "0.0005"),
        "RISK_POLICY_INVALID",
    )
    for symbol in SYMBOLS:
        if symbol not in notionals:
            continue
        notional = _d(notionals[symbol], "INITIAL_NOTIONAL_INVALID")
        mark = _d(context["symbols"][symbol]["mark"], "INITIAL_MARK_INVALID")
        entry = mark * Decimal("1.02")
        technical = context["symbols"][symbol].get("technical", {})
        one_hour = technical.get("1h", {}) if isinstance(technical, Mapping) else {}
        atr_value = one_hour.get("atr14") if isinstance(one_hour, Mapping) else None
        if atr_value is None:
            raise ProspectiveResearchError(
                f"INITIAL_PROTECTION_NOT_EVALUABLE_NO_1H_ATR:{symbol}"
            )
        atr = _d(atr_value, "INITIAL_ATR_INVALID")
        stop = mark - Decimal("2") * atr
        if atr <= ZERO or stop <= ZERO or stop >= entry:
            raise ProspectiveResearchError(f"INITIAL_PROTECTION_INVALID:{symbol}")
        quantity = notional / mark
        risk_budget = quantity * (entry - stop) + quantity * stop * taker_fee_rate
        management_checkpoint = entry + Decimal("2") * (entry - stop)
        geometry_id = f"{symbol}:genesis-1h-atr-protection-v1"
        positions.append(
            {
                "symbol": symbol,
                "side": "LONG",
                "origin": "EXOGENOUS_INITIAL_POSITION",
                "entry_price": canonical_decimal(entry),
                "quantity": canonical_decimal(quantity),
                "market_notional_at_genesis_usdt": canonical_decimal(notional),
                "entry_notional_usdt": canonical_decimal(notional * Decimal("1.02")),
                "initial_mark_price": canonical_decimal(mark),
                "cost_basis_rule": "GENESIS_OKX_MARK_MULTIPLIED_BY_1.02",
                "initial_stop_price": canonical_decimal(stop),
                "management_checkpoint": canonical_decimal(management_checkpoint),
                "management_checkpoint_id": f"{symbol}:genesis-core-checkpoint-v1",
                "risk_budget_usdt": canonical_decimal(risk_budget),
                "max_horizon_at": maximum_horizon_at,
                "exit_intent": "CORE_DYNAMIC_MANAGEMENT_NOT_FIXED_TARGET",
                "geometry_id": geometry_id,
                "geometry_basis": "GENESIS_MARK_MINUS_2_TIMES_1H_ATR14_PROTECTION;CHECKPOINT_IS_REVIEW_EVENT_NOT_AUTO_EXIT",
            }
        )
    config["initial_portfolio"] = {
        "initial_cash_usdt": str(template.get("initial_equity_usdt")),
        "positions": positions,
        "orders": [],
        "initial_order_state": "NONE_NO_STALE_V1_GEOMETRY_CARRIED_FORWARD",
        "position_notional_semantics": "MARKET_NOTIONAL_AT_GENESIS_WITH_102_PERCENT_COST_BASIS",
    }
    config["funding_policy"] = {
        "status": FUNDING_PROXY_STATUS,
        "position_basis": "OPEN_LOTS_AT_SETTLEMENT_TIME",
        "price_basis": "LATEST_CLOSED_15M_TRADE_CANDLE_CLOSE_BEFORE_SETTLEMENT_PROXY",
        "truth_boundary": "MODELED_ACCRUAL_NOT_TRUE_SETTLEMENT_MARK_OR_ACCOUNT_CASHFLOW",
        "missing": "UNKNOWN_NOT_ZERO",
    }
    return config


def prepare_prospective_research(
    *,
    project_root: Path,
    runtime_root: Path,
    template_path: Path,
    run_id: str,
    prepared_at: datetime | None = None,
) -> dict[str, Any]:
    """Collect genesis, freeze the final contract, and create a write-once run."""

    project = Path(project_root).resolve(strict=True)
    assert_current_research_start_authorized(
        project_root=project,
        operation="PREPARE_PROSPECTIVE",
        run_id=run_id,
        template_path=template_path,
    )
    runtime = Path(runtime_root).resolve()
    template = load_json_strict(template_path)
    if template.get("evidence_class") != PROSPECTIVE_EVIDENCE_CLASS:
        raise ProspectiveResearchError("CONTRACT_EVIDENCE_CLASS_INVALID")
    if template.get("start_authorized") is not True:
        raise ProspectiveResearchError("PROSPECTIVE_START_NOT_AUTHORIZED")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{5,95}", run_id):
        raise ProspectiveResearchError("RUN_ID_INVALID")
    _verify_bindings(project, template)
    playbook_binding = template.get("strategy_playbook")
    if not isinstance(playbook_binding, Mapping):
        raise ProspectiveResearchError("STRATEGY_PLAYBOOK_BINDING_MISSING")
    playbook_path = (project / str(playbook_binding.get("path") or "")).resolve(strict=True)
    playbook_path.relative_to(project)
    playbook_text = playbook_path.read_text(encoding="utf-8")
    playbook_sha = sha256_file(playbook_path)
    if playbook_sha != str(playbook_binding.get("physical_sha256") or ""):
        raise ProspectiveResearchError("STRATEGY_PLAYBOOK_BINDING_DRIFT")

    run_root = runtime / run_id
    if run_root.exists():
        raise ProspectiveResearchError("RUN_ROOT_ALREADY_EXISTS")
    run_root.mkdir(parents=True, exist_ok=False)
    collection = collect_okx_six_context(run_root=run_root, cycle_index=1)
    context = collection.context
    source_config = _prospective_source_config(template, context)
    activated_at = str(context["decision_at"])
    genesis = _initial_state(
        run_id=run_id,
        source_config=source_config,
        activated_at=activated_at,
        first_context=context,
    )
    write_once_json(run_root / "market-contexts" / "cycle-0001.json", context)
    write_once_json(run_root / "states" / "state-0000-genesis.json", genesis)

    final_contract = copy.deepcopy(dict(template))
    comparator_geometry: dict[str, dict[str, Any]] = {}
    for position in source_config["initial_portfolio"]["positions"]:
        symbol = str(position["symbol"])
        mark = _d(context["symbols"][symbol]["mark"], "COMPARATOR_MARK_INVALID")
        atr_value = context["symbols"][symbol]["technical"]["1h"].get("atr14")
        if atr_value is None:
            comparator_geometry[symbol] = {
                "status": "NOT_EVALUABLE_NO_1H_ATR",
                "genesis_mark": canonical_decimal(mark),
                "atr14_1h": None,
                "initial_stop": None,
                "one_r_from_genesis_mark": None,
                "static_full_target_2r": None,
                "deterministic_partial_1r": None,
                "deterministic_partial_2r": None,
                "same_bar_policy": "STOP_FIRST",
            }
            continue
        atr = _d(atr_value, "COMPARATOR_ATR_INVALID")
        if atr <= ZERO or mark - Decimal("2") * atr <= ZERO:
            raise ProspectiveResearchError(f"COMPARATOR_GEOMETRY_INVALID:{symbol}")
        stop = mark - Decimal("2") * atr
        one_r = mark - stop
        comparator_geometry[symbol] = {
            "status": "EVALUABLE",
            "genesis_mark": canonical_decimal(mark),
            "atr14_1h": canonical_decimal(atr),
            "initial_stop": canonical_decimal(stop),
            "one_r_from_genesis_mark": canonical_decimal(one_r),
            "static_full_target_2r": canonical_decimal(mark + Decimal("2") * one_r),
            "deterministic_partial_1r": canonical_decimal(mark + one_r),
            "deterministic_partial_2r": canonical_decimal(mark + Decimal("2") * one_r),
            "same_bar_policy": "STOP_FIRST",
        }
    final_contract["template_physical_sha256"] = sha256_file(Path(template_path))
    final_contract["run_id"] = run_id
    final_contract["genesis"] = {
        "decision_at": activated_at,
        "market_context_digest": context["context_digest"],
        "acquisition_digest": collection.acquisition["acquisition_digest"],
        "initial_positions": source_config["initial_portfolio"]["positions"],
        "comparator_geometry": comparator_geometry,
        "first_due_at": activated_at,
        "terminal_due_at": _iso(_ts(activated_at) + timedelta(hours=24)),
    }
    final_contract = self_digest(final_contract, "contract_digest")
    write_once_json(run_root / "frozen-contract.json", final_contract)
    manifest = self_digest(
        {
            "schema_id": "prospective_single_agent_research_manifest",
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "run_id": run_id,
            "prepared_at": _iso((prepared_at or _now()).astimezone(UTC)),
            "evidence_class": PROSPECTIVE_EVIDENCE_CLASS,
            "contract_digest": final_contract["contract_digest"],
            "research_contract": final_contract,
            "strategy_playbook": {
                "path": str(playbook_binding["path"]),
                "physical_sha256": playbook_sha,
                "content": playbook_text,
            },
            "source_config": source_config,
            "contexts": [
                {
                    "cycle_index": 1,
                    "decision_at": activated_at,
                    "context_digest": context["context_digest"],
                    "acquisition_digest": collection.acquisition["acquisition_digest"],
                }
            ],
            "schedule": {
                "genesis_decision_at": activated_at,
                "decision_interval_minutes": 60,
                "review_interval_hours": 4,
                "decision_cycles": DECISION_CYCLES,
                "terminal_observation_cycle": TERMINAL_CYCLE,
                "maximum_cycle_lateness_minutes": int(MAXIMUM_CYCLE_LATENESS.total_seconds() / 60),
            },
            "decision_cycles": DECISION_CYCLES,
            "terminal_observation_cycle": TERMINAL_CYCLE,
            "strategy_agent_count": 1,
            "critic_enabled": False,
            "recorded_v1_decisions_opened": False,
            "recorded_v1_outcomes_opened": False,
            "funding_status": FUNDING_PROXY_STATUS,
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "manifest_digest",
    )
    write_once_json(run_root / "manifest.json", manifest)
    checkpoint = {
        "schema_id": "single_agent_research_checkpoint",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "manifest_digest": manifest["manifest_digest"],
        "status": "PREPARED_OUTCOMES_SEALED",
        "next_cycle_index": 1,
        "completed_cycles": 0,
        "accepted_state_path": "states/state-0000-genesis.json",
        "accepted_state_digest": genesis["state_digest"],
        "pending_agent_context_path": None,
        "pending_pre_decision_state_path": None,
        "terminal_receipt_path": None,
        "recorded_v1_decisions_opened": False,
        "recorded_v1_outcomes_opened": False,
    }
    _write_atomic_json(run_root / "checkpoint.json", checkpoint)
    return manifest


def collect_next_prospective_cycle(
    *, run_root: Path, cycle_index: int
) -> dict[str, Any]:
    """Collect the next due context without opening or deciding it."""

    root, manifest, checkpoint = _run_documents(run_root)
    if manifest.get("evidence_class") != PROSPECTIVE_EVIDENCE_CLASS:
        raise ProspectiveResearchError("NOT_PROSPECTIVE_RUN")
    if checkpoint.get("status") not in {
        "PREPARED_OUTCOMES_SEALED",
        "RUNNING_OUTCOMES_SEALED",
    }:
        raise ProspectiveResearchError("RUN_NOT_COLLECTABLE")
    if cycle_index == 1:
        raise ProspectiveResearchError("GENESIS_CONTEXT_ALREADY_FROZEN")
    if int(checkpoint.get("next_cycle_index", 0)) != cycle_index:
        raise ProspectiveResearchError("CYCLE_ORDER_INVALID")
    if checkpoint.get("pending_agent_context_path") is not None:
        raise ProspectiveResearchError("PENDING_CYCLE_ALREADY_OPEN")
    if cycle_index <= DECISION_CYCLES and int(checkpoint.get("completed_cycles", 0)) != cycle_index - 1:
        raise ProspectiveResearchError("PRIOR_CYCLE_NOT_ACCEPTED")
    if cycle_index == TERMINAL_CYCLE and int(checkpoint.get("completed_cycles", 0)) != DECISION_CYCLES:
        raise ProspectiveResearchError("TERMINAL_BEFORE_DECISIONS_COMPLETE")
    context_path = root / "market-contexts" / f"cycle-{cycle_index:04d}.json"
    if context_path.exists():
        raise ProspectiveResearchError("CYCLE_CONTEXT_ALREADY_EXISTS")
    genesis_at = _ts(str(manifest["schedule"]["genesis_decision_at"]))
    due_at = genesis_at + timedelta(hours=cycle_index - 1)
    if _now() < due_at:
        raise ProspectiveResearchError(f"CYCLE_NOT_DUE:{_iso(due_at)}")
    collection = collect_okx_six_context(run_root=root, cycle_index=cycle_index)
    observed_at = _ts(str(collection.context["decision_at"]))
    lateness = observed_at - due_at
    if lateness > MAXIMUM_CYCLE_LATENESS:
        raise ProspectiveResearchError(
            f"CYCLE_LATENESS_EXCEEDED:{int(lateness.total_seconds())}"
        )
    context = dict(collection.context)
    context.pop("context_digest", None)
    context["schedule"] = {
        "due_at": _iso(due_at),
        "collected_decision_at": _iso(observed_at),
        "lateness_seconds": max(0, int(lateness.total_seconds())),
        "review_cycle": cycle_index % 4 == 0,
        "terminal_observation": cycle_index == TERMINAL_CYCLE,
    }
    context = self_digest(context, "context_digest")
    write_once_json(context_path, context)
    receipt = self_digest(
        {
            "schema_id": "prospective_context_collection_receipt",
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "cycle_index": cycle_index,
            "due_at": _iso(due_at),
            "decision_at": context["decision_at"],
            "lateness_seconds": max(0, int(lateness.total_seconds())),
            "context_digest": context["context_digest"],
            "acquisition_digest": collection.acquisition["acquisition_digest"],
            "authority": "PUBLIC_READ_ONLY_NO_CREDENTIALS_NO_ACCOUNT_NO_ORDERS",
        },
        "receipt_digest",
    )
    write_once_json(
        root / "collection-receipts" / f"cycle-{cycle_index:04d}.json", receipt
    )
    return receipt


def interrupt_prospective_research(
    *,
    run_root: Path,
    reason_code: str,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Failure-close an incomplete prospective run without collecting outcomes."""

    root, manifest, checkpoint = _run_documents(run_root)
    if manifest.get("evidence_class") != PROSPECTIVE_EVIDENCE_CLASS:
        raise ProspectiveResearchError("NOT_PROSPECTIVE_RUN")
    receipt_path = root / "receipts" / "interruption.json"
    if receipt_path.exists():
        receipt = _load_verified(receipt_path, "interruption_digest")
        if checkpoint.get("status") != "INTERRUPTED_OUTCOMES_SEALED":
            checkpoint["status"] = "INTERRUPTED_OUTCOMES_SEALED"
            checkpoint["interruption_receipt_path"] = (
                receipt_path.relative_to(root).as_posix()
            )
            checkpoint["interruption_digest"] = receipt["interruption_digest"]
            _write_atomic_json(root / "checkpoint.json", checkpoint)
        return receipt
    if checkpoint.get("status") not in {
        "PREPARED_OUTCOMES_SEALED",
        "RUNNING_OUTCOMES_SEALED",
    }:
        raise ProspectiveResearchError("RUN_NOT_INTERRUPTIBLE")
    if checkpoint.get("pending_agent_context_path") is not None:
        raise ProspectiveResearchError("PENDING_CYCLE_REQUIRES_SEPARATE_FAILURE_REVIEW")
    completed = int(checkpoint.get("completed_cycles", -1))
    next_cycle = int(checkpoint.get("next_cycle_index", -1))
    if completed < 0 or completed >= DECISION_CYCLES or next_cycle != completed + 1:
        raise ProspectiveResearchError("INTERRUPTION_BOUNDARY_INVALID")
    if (root / "market-contexts" / f"cycle-{next_cycle:04d}.json").exists():
        raise ProspectiveResearchError("UNACCEPTED_FUTURE_CONTEXT_PRESENT")
    accepted_state = _load_verified(
        root / str(checkpoint["accepted_state_path"]), "state_digest"
    )
    if accepted_state["state_digest"] != checkpoint["accepted_state_digest"]:
        raise ProspectiveResearchError("CHECKPOINT_STATE_MISMATCH")
    last_receipt_digest = None
    last_decision_digest = None
    if completed:
        last_receipt = _load_verified(
            root / "receipts" / f"cycle-{completed:04d}.json", "receipt_digest"
        )
        last_receipt_digest = last_receipt["receipt_digest"]
        last_decision_digest = last_receipt.get("decision_digest")
    reason = str(reason_code or "").strip()
    if not reason:
        raise ProspectiveResearchError("INTERRUPTION_REASON_MISSING")
    user_review_suspension = reason == "USER_PAUSED_FOR_THEORY_ROOT_CAUSE_REDESIGN"
    receipt = self_digest(
        {
            "schema_id": "prospective_run_interruption_receipt",
            "schema_version": "1.1.0",
            "run_id": manifest["run_id"],
            "manifest_digest": manifest["manifest_digest"],
            "recorded_at": _iso((recorded_at or _now()).astimezone(UTC)),
            "failure_at": None,
            "failure_time_status": "CONTROLLER_RECORDED_AT_ONLY;FAILURE_ORIGIN_TIME_NOT_ASSERTED",
            "reason_code": reason,
            "failure_stage": (
                "USER_AUTHORIZED_RESEARCH_SUSPENSION"
                if user_review_suspension
                else (
                    "POST_ACCEPT_WRITE_ONCE_TRUTH_CONFLICT"
                    if reason.startswith("ACCEPTED_")
                    else "UNCLASSIFIED_FAIL_CLOSED"
                )
            ),
            "status": "INTERRUPTED_OUTCOMES_SEALED",
            "completed_cycles": completed,
            "next_uncompleted_cycle": next_cycle,
            "last_accepted_state_path": checkpoint["accepted_state_path"],
            "last_accepted_state_digest": checkpoint["accepted_state_digest"],
            "last_accepted_decision_digest": last_decision_digest,
            "last_cycle_receipt_digest": last_receipt_digest,
            "uncompleted_decision_cycles": list(
                range(next_cycle, DECISION_CYCLES + 1)
            ),
            "terminal_cycle_uncollected": TERMINAL_CYCLE,
            "pending_agent_context_path": None,
            "future_context_or_outcome_collected_by_close": False,
            "resume_allowed": False,
            "successor_creation_authorized": not user_review_suspension,
            "required_successor": (
                "NONE_UNTIL_EXPLICIT_USER_REAUTHORIZATION_AFTER_THEORY_REVIEW"
                if user_review_suspension
                else "NEW_RUN_NEW_CHRONOLOGY_NEW_FROZEN_CONTRACT"
            ),
            "automatic_recovery_disposition": (
                "DISABLED_USER_REVIEW_REQUIRED"
                if user_review_suspension
                else "SEAL_PREDECESSOR_THEN_PREPARE_BOUND_FRESH_SUCCESSOR"
            ),
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "interruption_digest",
    )
    write_once_json(receipt_path, receipt)
    checkpoint["status"] = "INTERRUPTED_OUTCOMES_SEALED"
    checkpoint["interruption_receipt_path"] = receipt_path.relative_to(root).as_posix()
    checkpoint["interruption_digest"] = receipt["interruption_digest"]
    _write_atomic_json(root / "checkpoint.json", checkpoint)
    return receipt


def _validate_successor_recovery_contract(
    *,
    template: Mapping[str, Any],
    predecessor_manifest: Mapping[str, Any],
    predecessor_checkpoint: Mapping[str, Any],
    interruption: Mapping[str, Any],
) -> dict[str, Any]:
    if predecessor_checkpoint.get("status") != "INTERRUPTED_OUTCOMES_SEALED":
        raise ProspectiveResearchError("PREDECESSOR_NOT_INTERRUPTED")
    if interruption.get("resume_allowed") is not False:
        raise ProspectiveResearchError("PREDECESSOR_RESUME_BOUNDARY_INVALID")
    if interruption.get("successor_creation_authorized") is False:
        raise ProspectiveResearchError("SUCCESSOR_NOT_AUTHORIZED")
    recovery = template.get("automatic_recovery")
    if not isinstance(recovery, Mapping):
        raise ProspectiveResearchError("AUTOMATIC_RECOVERY_CONTRACT_MISSING")
    required = {
        "mode": "SEALED_PREDECESSOR_TO_FRESH_SUCCESSOR",
        "predecessor_run_id": predecessor_manifest.get("run_id"),
        "predecessor_manifest_digest": predecessor_manifest.get("manifest_digest"),
        "predecessor_interruption_digest": interruption.get("interruption_digest"),
        "predecessor_reason_code": interruption.get("reason_code"),
        "resume_predecessor": False,
        "reuse_predecessor_state_or_context": False,
        "post_accept_truth_conflict": "SEAL_AND_START_NEW_CHRONOLOGY",
    }
    for key, expected in required.items():
        if recovery.get(key) != expected:
            raise ProspectiveResearchError(
                f"AUTOMATIC_RECOVERY_BINDING_INVALID:{key}"
            )
    bounded_attempts = recovery.get("bounded_pre_accept_repair_attempts")
    if (
        isinstance(bounded_attempts, bool)
        or not isinstance(bounded_attempts, int)
        or not 1 <= bounded_attempts <= 2
    ):
        raise ProspectiveResearchError("AUTOMATIC_RECOVERY_RETRY_BOUND_INVALID")
    return dict(recovery)


def prepare_prospective_successor(
    *,
    project_root: Path,
    runtime_root: Path,
    predecessor_run_root: Path,
    template_path: Path,
    run_id: str,
    prepared_at: datetime | None = None,
) -> dict[str, Any]:
    """Prepare a fresh successor without ever reopening an interrupted chronology."""

    predecessor_root, predecessor_manifest, predecessor_checkpoint = _run_documents(
        predecessor_run_root
    )
    interruption_path = predecessor_root / str(
        predecessor_checkpoint.get("interruption_receipt_path") or ""
    )
    if not interruption_path.is_file():
        raise ProspectiveResearchError("PREDECESSOR_INTERRUPTION_RECEIPT_MISSING")
    interruption = _load_verified(interruption_path, "interruption_digest")
    template = load_json_strict(template_path)
    recovery = _validate_successor_recovery_contract(
        template=template,
        predecessor_manifest=predecessor_manifest,
        predecessor_checkpoint=predecessor_checkpoint,
        interruption=interruption,
    )
    runtime = Path(runtime_root).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    target = runtime / run_id
    if target.exists():
        raise ProspectiveResearchError("RUN_ROOT_ALREADY_EXISTS")
    with TemporaryDirectory(prefix=f".{run_id}-staging-", dir=runtime) as staging:
        manifest = prepare_prospective_research(
            project_root=project_root,
            runtime_root=Path(staging),
            template_path=template_path,
            run_id=run_id,
            prepared_at=prepared_at,
        )
        staged_root = Path(staging) / run_id
        lineage = self_digest(
            {
                "schema_id": "prospective_successor_recovery_receipt",
                "schema_version": "1.0.0",
                "predecessor_run_id": predecessor_manifest["run_id"],
                "predecessor_manifest_digest": predecessor_manifest[
                    "manifest_digest"
                ],
                "predecessor_interruption_digest": interruption[
                    "interruption_digest"
                ],
                "predecessor_completed_cycles": predecessor_checkpoint[
                    "completed_cycles"
                ],
                "predecessor_resume_allowed": False,
                "successor_run_id": manifest["run_id"],
                "successor_manifest_digest": manifest["manifest_digest"],
                "recovery_mode": recovery["mode"],
                "state_or_context_reused": False,
                "prepared_at": _iso((prepared_at or _now()).astimezone(UTC)),
                "system_mode": SYSTEM_MODE,
                "external_execution_authority": EXECUTION_AUTHORITY,
                "executable": False,
            },
            "recovery_digest",
        )
        write_once_json(staged_root / "receipts" / "recovery-lineage.json", lineage)
        os.replace(staged_root, target)
    return {
        "status": "FRESH_SUCCESSOR_PREPARED",
        "run_id": manifest["run_id"],
        "run_root": str(target),
        "manifest_digest": manifest["manifest_digest"],
        "predecessor_run_id": predecessor_manifest["run_id"],
        "predecessor_interruption_digest": interruption["interruption_digest"],
        "recovery_digest": lineage["recovery_digest"],
        "next_cycle_index": 1,
        "state_or_context_reused": False,
    }


def _comparator_position(
    *,
    symbol: str,
    quantity: Decimal,
    entry: Decimal,
    stop: Decimal | None,
    one_r: Decimal | None,
    mark: Decimal,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "quantity": quantity,
        "original_quantity": quantity,
        "entry_price": entry,
        "remaining_quantity": quantity,
        "stop_price": stop,
        "partial_1r": None if one_r is None else mark + one_r,
        "partial_2r": None if one_r is None else mark + Decimal("2") * one_r,
        "partial_1r_done": False,
        "partial_2r_done": False,
        "high_water": mark,
        "reentry_count": 0,
    }


def _close_comparator(
    arm: dict[str, Any],
    position: dict[str, Any],
    *,
    quantity: Decimal,
    price: Decimal,
    fee_rate: Decimal,
    reason: str,
    occurred_at: str,
) -> None:
    quantity = min(quantity, position["remaining_quantity"])
    if quantity <= ZERO:
        return
    realized = quantity * (price - position["entry_price"])
    fee = quantity * price * fee_rate
    position["remaining_quantity"] -= quantity
    arm["realized_pnl_before_cost"] += realized
    arm["fees"] += fee
    arm["events"].append(
        {
            "event_type": reason,
            "symbol": position["symbol"],
            "occurred_at": occurred_at,
            "quantity": canonical_decimal(quantity),
            "fill_price": canonical_decimal(price),
            "realized_pnl_before_cost": canonical_decimal(realized),
            "fee": canonical_decimal(fee),
        }
    )


def _comparator_snapshot(
    arm: Mapping[str, Any], marks: Mapping[str, Decimal], *, cycle_index: int, marked_at: str
) -> dict[str, Any]:
    unrealized = ZERO
    gross = ZERO
    positions: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        position = arm["positions"].get(symbol)
        if not isinstance(position, Mapping) or position["remaining_quantity"] <= ZERO:
            continue
        mark = marks[symbol]
        quantity = position["remaining_quantity"]
        unrealized += quantity * (mark - position["entry_price"])
        gross += quantity * mark
        positions.append(
            {
                "symbol": symbol,
                "quantity": canonical_decimal(quantity),
                "entry_price": canonical_decimal(position["entry_price"]),
                "mark": canonical_decimal(mark),
                "stop_price": (
                    None
                    if position.get("stop_price") is None
                    else canonical_decimal(position["stop_price"])
                ),
                "unrealized_pnl_usdt": canonical_decimal(
                    quantity * (mark - position["entry_price"])
                ),
            }
        )
    net = arm["realized_pnl_before_cost"] + unrealized - arm["fees"] + arm["funding"]
    return {
        "cycle_index": cycle_index,
        "marked_at": marked_at,
        "realized_pnl_before_cost_usdt": canonical_decimal(arm["realized_pnl_before_cost"]),
        "unrealized_pnl_usdt": canonical_decimal(unrealized),
        "fees_usdt": canonical_decimal(arm["fees"]),
        "funding_usdt": canonical_decimal(arm["funding"]),
        "net_pnl_after_cost_and_funding_usdt": canonical_decimal(net),
        "equity_after_cost_and_funding_usdt": canonical_decimal(Decimal("10000") + net),
        "gross_notional_usdt": canonical_decimal(gross),
        "open_positions": positions,
    }


def _apply_comparator_funding(
    arm: dict[str, Any], event: Mapping[str, Any]
) -> None:
    event_id = str(event["event_id"])
    if event_id in arm["processed_funding"]:
        return
    symbol = str(event["symbol"])
    position = arm["positions"].get(symbol)
    amount = ZERO
    if (
        isinstance(position, Mapping)
        and position["remaining_quantity"] > ZERO
        and _ts(str(event["funding_time"])) >= _ts(str(arm["genesis_at"]))
    ):
        amount = -(
            position["remaining_quantity"]
            * _d(
                event.get(
                    "settlement_price_proxy", event.get("settlement_mark_proxy")
                ),
                "COMPARATOR_FUNDING_INVALID",
            )
            * _d(event["funding_rate"], "COMPARATOR_FUNDING_INVALID")
        )
    arm["funding"] += amount
    arm["processed_funding"].add(event_id)
    arm["events"].append(
        {
            "event_type": "FUNDING_SETTLEMENT",
            "event_id": event_id,
            "symbol": symbol,
            "occurred_at": event["funding_time"],
            "funding_usdt": canonical_decimal(amount),
        }
    )


def _maximum_drawdown_from_comparator(curve: Sequence[Mapping[str, Any]]) -> Decimal:
    peak = Decimal("10000")
    maximum = ZERO
    for row in curve:
        equity = _d(row["equity_after_cost_and_funding_usdt"], "COMPARATOR_CURVE_INVALID")
        peak = max(peak, equity)
        if peak > ZERO:
            maximum = max(maximum, (peak - equity) / peak)
    return maximum


def comparator_results(
    *, run_root: Path, through_cycle: int | None = None
) -> dict[str, Any]:
    """Replay the two frozen deterministic comparators through available PIT contexts."""

    root, manifest, checkpoint = _run_documents(run_root)
    if manifest.get("evidence_class") != PROSPECTIVE_EVIDENCE_CLASS:
        raise ProspectiveResearchError("NOT_PROSPECTIVE_RUN")
    maximum_available = TERMINAL_CYCLE if (root / "market-contexts" / "cycle-0025.json").is_file() else int(checkpoint.get("completed_cycles", 0))
    if maximum_available < 1:
        maximum_available = 1
    final_cycle = through_cycle or maximum_available
    if not 1 <= final_cycle <= maximum_available:
        raise ProspectiveResearchError("COMPARATOR_CYCLE_UNAVAILABLE")
    contexts = [
        _load_verified(root / "market-contexts" / f"cycle-{index:04d}.json", "context_digest")
        for index in range(1, final_cycle + 1)
    ]
    contract = manifest["research_contract"]
    geometry = contract["genesis"]["comparator_geometry"]
    positions = manifest["source_config"]["initial_portfolio"]["positions"]
    position_by_symbol = {row["symbol"]: row for row in positions}
    static_positions: dict[str, dict[str, Any]] = {}
    continuous_positions: dict[str, dict[str, Any]] = {}
    hold_positions: dict[str, dict[str, Any]] = {}
    comparator_unavailable_symbols: set[str] = set()
    for symbol, row in position_by_symbol.items():
        entry = _d(row["entry_price"], "COMPARATOR_POSITION_INVALID")
        quantity = _d(row["quantity"], "COMPARATOR_POSITION_INVALID")
        mark = _d(row["initial_mark_price"], "COMPARATOR_POSITION_INVALID")
        hold_positions[symbol] = _comparator_position(
            symbol=symbol, quantity=quantity, entry=entry, stop=None, one_r=None, mark=mark
        )
        geometry_row = geometry.get(symbol)
        if (
            not isinstance(geometry_row, Mapping)
            or geometry_row.get("status", "EVALUABLE") != "EVALUABLE"
        ):
            comparator_unavailable_symbols.add(symbol)
            continue
        stop = _d(geometry_row["initial_stop"], "COMPARATOR_GEOMETRY_INVALID")
        one_r = _d(
            geometry_row["one_r_from_genesis_mark"], "COMPARATOR_GEOMETRY_INVALID"
        )
        static = _comparator_position(
            symbol=symbol, quantity=quantity, entry=entry, stop=stop, one_r=one_r, mark=mark
        )
        static["partial_2r"] = _d(
            geometry_row["static_full_target_2r"], "COMPARATOR_GEOMETRY_INVALID"
        )
        static_positions[symbol] = static
        continuous_positions[symbol] = _comparator_position(
            symbol=symbol, quantity=quantity, entry=entry, stop=stop, one_r=one_r, mark=mark
        )
    genesis_at = str(contract["genesis"]["decision_at"])

    def arm(arm_id: str, positions_value: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return {
            "arm_id": arm_id,
            "positions": positions_value,
            "realized_pnl_before_cost": ZERO,
            "fees": ZERO,
            "funding": ZERO,
            "events": [],
            "processed_funding": set(),
            "processed_bar_close_ms": {
                symbol: max(
                    (
                        int(bar["close_time_ms"])
                        for bar in contexts[0]["symbols"][symbol]["execution_bars_15m"]
                        if _ts(str(bar["available_at"])) <= _ts(genesis_at)
                    ),
                    default=0,
                )
                for symbol in SYMBOLS
            },
            "genesis_at": genesis_at,
            "curve": [],
            "reentry_count": {symbol: 0 for symbol in SYMBOLS},
        }

    static_arm = arm("STATIC_V1", static_positions)
    continuous_arm = arm("DETERMINISTIC_CONTINUOUS", continuous_positions)
    hold_arm = arm("INITIAL_STATIC_HOLD", hold_positions)
    for symbol in sorted(comparator_unavailable_symbols):
        for arm_value in (static_arm, continuous_arm):
            arm_value["events"].append(
                {
                    "event_type": "COMPARATOR_SYMBOL_NOT_EVALUABLE_NO_GENESIS_1H_ATR",
                    "symbol": symbol,
                    "occurred_at": genesis_at,
                }
            )
    arms = (static_arm, continuous_arm, hold_arm)
    maker_fee = _d(manifest["source_config"]["risk_policy"]["default_maker_fee_rate"], "COMPARATOR_COST_INVALID")
    taker_fee = _d(manifest["source_config"]["risk_policy"]["default_taker_fee_rate"], "COMPARATOR_COST_INVALID")
    market_bps = _d(manifest["source_config"]["risk_policy"]["default_market_slippage_bps"], "COMPARATOR_COST_INVALID")
    stop_bps = _d(manifest["source_config"]["risk_policy"]["default_stop_slippage_bps"], "COMPARATOR_COST_INVALID")
    previous_context: Mapping[str, Any] | None = None
    for context in contexts:
        decision_at = str(context["decision_at"])
        for symbol in SYMBOLS:
            bars_by_arm = {
                arm_value["arm_id"]: sorted(
                    [
                        bar
                        for bar in context["symbols"][symbol]["execution_bars_15m"]
                        if int(bar["close_time_ms"])
                        > int(arm_value["processed_bar_close_ms"][symbol])
                        and _ts(str(bar["available_at"])) <= _ts(decision_at)
                    ],
                    key=lambda bar: int(bar["close_time_ms"]),
                )
                for arm_value in arms
            }
            funding_events = context["symbols"][symbol].get("funding_events", [])
            for arm_value in arms:
                for event in funding_events:
                    if _ts(str(event["available_at"])) <= _ts(decision_at):
                        _apply_comparator_funding(arm_value, event)
                if arm_value is hold_arm:
                    if bars_by_arm[arm_value["arm_id"]]:
                        arm_value["processed_bar_close_ms"][symbol] = int(
                            bars_by_arm[arm_value["arm_id"]][-1]["close_time_ms"]
                        )
                    continue
                for bar in bars_by_arm[arm_value["arm_id"]]:
                    position = arm_value["positions"].get(symbol)
                    if isinstance(position, Mapping) and position["remaining_quantity"] > ZERO:
                        low = _d(bar["low"], "COMPARATOR_BAR_INVALID")
                        high = _d(bar["high"], "COMPARATOR_BAR_INVALID")
                        open_price = _d(bar["open"], "COMPARATOR_BAR_INVALID")
                        stop = position.get("stop_price")
                        if stop is not None and low <= stop:
                            reference = min(stop, open_price)
                            fill = reference * (ONE - stop_bps / Decimal("10000"))
                            _close_comparator(
                                arm_value,
                                position,
                                quantity=position["remaining_quantity"],
                                price=fill,
                                fee_rate=taker_fee,
                                reason="FIXED_OR_TRAILING_STOP",
                                occurred_at=str(bar["available_at"]),
                            )
                        elif arm_value is static_arm:
                            target = position.get("partial_2r")
                            if target is not None and high >= target:
                                _close_comparator(
                                    arm_value,
                                    position,
                                    quantity=position["remaining_quantity"],
                                    price=target,
                                    fee_rate=maker_fee,
                                    reason="STATIC_V1_FIXED_FULL_TARGET",
                                    occurred_at=str(bar["available_at"]),
                                )
                        else:
                            for key, fraction, reason in (
                                ("partial_1r", Decimal("0.25"), "DETERMINISTIC_PARTIAL_1R"),
                                ("partial_2r", Decimal("0.25"), "DETERMINISTIC_PARTIAL_2R"),
                            ):
                                threshold = position.get(key)
                                done_key = f"{key}_done"
                                if (
                                    threshold is not None
                                    and not position[done_key]
                                    and high >= threshold
                                    and position["remaining_quantity"] > ZERO
                                ):
                                    _close_comparator(
                                        arm_value,
                                        position,
                                        quantity=position["original_quantity"] * fraction,
                                        price=threshold,
                                        fee_rate=maker_fee,
                                        reason=reason,
                                        occurred_at=str(bar["available_at"]),
                                    )
                                    position[done_key] = True
                    arm_value["processed_bar_close_ms"][symbol] = int(bar["close_time_ms"])

            if symbol in comparator_unavailable_symbols:
                continue
            position = continuous_arm["positions"].get(symbol)
            technical = context["symbols"][symbol]["technical"]
            mark = _d(context["symbols"][symbol]["mark"], "COMPARATOR_MARK_INVALID")
            atr_value = technical["1h"].get("atr14")
            if atr_value is None:
                continuous_arm["events"].append(
                    {
                        "event_type": "COMPARATOR_ACTION_SKIPPED_MISSING_1H_ATR",
                        "symbol": symbol,
                        "occurred_at": decision_at,
                    }
                )
                continue
            atr = _d(atr_value, "COMPARATOR_ATR_INVALID")
            if isinstance(position, Mapping) and position["remaining_quantity"] > ZERO:
                if previous_context is not None:
                    previous_bar = previous_context["symbols"][symbol]["technical"]["1h"].get(
                        "last_closed_bar"
                    )
                    previous_close_time = (
                        -1
                        if not isinstance(previous_bar, Mapping)
                        else int(previous_bar["close_time"])
                    )
                    new_one_hour_bars = [
                        bar
                        for bar in context["symbols"][symbol]["recent_closed_bars"]["1h"]
                        if int(bar["close_time_ms"]) > previous_close_time
                    ]
                    if new_one_hour_bars:
                        latest_high = max(
                            _d(bar["high"], "COMPARATOR_BAR_INVALID")
                            for bar in new_one_hour_bars
                        )
                        position["high_water"] = max(position["high_water"], latest_high)
                candidate_stop = position["high_water"] - Decimal("2") * atr
                if candidate_stop < mark:
                    position["stop_price"] = max(position["stop_price"], candidate_stop)
                else:
                    continuous_arm["events"].append(
                        {
                            "event_type": "TRAIL_UPDATE_SKIPPED_NOT_BELOW_CURRENT_MARK",
                            "symbol": symbol,
                            "occurred_at": decision_at,
                            "candidate_stop": canonical_decimal(candidate_stop),
                            "mark": canonical_decimal(mark),
                        }
                    )
            elif continuous_arm["reentry_count"][symbol] < 1 and previous_context is not None:
                previous_technical = previous_context["symbols"][symbol]["technical"]
                inputs = {
                    "current_vwap": technical["1h"].get("rolling_vwap_24"),
                    "previous_vwap": previous_technical["1h"].get("rolling_vwap_24"),
                    "current_bar": technical["1h"].get("last_closed_bar"),
                    "previous_bar": previous_technical["1h"].get("last_closed_bar"),
                    "four_hour_change": technical["4h"].get("change_1_bar_pct"),
                }
                if any(value is None for value in inputs.values()):
                    continuous_arm["events"].append(
                        {
                            "event_type": "COMPARATOR_REENTRY_SKIPPED_MISSING_MEASURE",
                            "symbol": symbol,
                            "occurred_at": decision_at,
                            "missing": sorted(
                                key for key, value in inputs.items() if value is None
                            ),
                        }
                    )
                    continue
                current_vwap = _d(inputs["current_vwap"], "COMPARATOR_VWAP_INVALID")
                previous_vwap = _d(inputs["previous_vwap"], "COMPARATOR_VWAP_INVALID")
                current_close = _d(
                    inputs["current_bar"]["close"], "COMPARATOR_CLOSE_INVALID"
                )
                previous_close = _d(
                    inputs["previous_bar"]["close"], "COMPARATOR_CLOSE_INVALID"
                )
                four_hour_change = _d(
                    inputs["four_hour_change"], "COMPARATOR_TREND_INVALID"
                )
                if previous_close <= previous_vwap and current_close > current_vwap and four_hour_change > ZERO:
                    base_notional = _d(
                        contract["comparator_policies"]["deterministic_continuous"]["mu_probe_notional_usdt"]
                        if symbol == "MUUSDT"
                        else position_by_symbol[symbol]["market_notional_at_genesis_usdt"],
                        "COMPARATOR_NOTIONAL_INVALID",
                    )
                    fill = mark * (ONE + market_bps / Decimal("10000"))
                    stop = fill - Decimal("2") * atr
                    risk_quantity = Decimal("50") / (fill - stop)
                    quantity = min(base_notional * Decimal("0.5") / fill, risk_quantity)
                    opened = _comparator_position(
                        symbol=symbol,
                        quantity=quantity,
                        entry=fill,
                        stop=stop,
                        one_r=fill - stop,
                        mark=fill,
                    )
                    opened["reentry_count"] = 1
                    continuous_arm["positions"][symbol] = opened
                    continuous_arm["reentry_count"][symbol] += 1
                    continuous_arm["fees"] += quantity * fill * taker_fee
                    continuous_arm["events"].append(
                        {
                            "event_type": "DETERMINISTIC_REENTRY_OR_MU_PROBE",
                            "symbol": symbol,
                            "occurred_at": decision_at,
                            "quantity": canonical_decimal(quantity),
                            "fill_price": canonical_decimal(fill),
                            "stop_price": canonical_decimal(stop),
                        }
                    )

        marks = {
            symbol: _d(context["symbols"][symbol]["mark"], "COMPARATOR_MARK_INVALID")
            for symbol in SYMBOLS
        }
        for arm_value in arms:
            arm_value["curve"].append(
                _comparator_snapshot(
                    arm_value,
                    marks,
                    cycle_index=int(context["cycle_index"]),
                    marked_at=decision_at,
                )
            )
        previous_context = context

    output_arms: dict[str, Any] = {}
    for arm_value in arms:
        terminal = arm_value["curve"][-1]
        output_arms[arm_value["arm_id"]] = {
            "terminal": terminal,
            "maximum_drawdown_fraction": canonical_decimal(
                _maximum_drawdown_from_comparator(arm_value["curve"])
            ),
            "curve": arm_value["curve"],
            "events": arm_value["events"],
        }
    value = {
        "schema_id": "prospective_frozen_comparator_results",
        "schema_version": PROSPECTIVE_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "through_cycle": final_cycle,
        "arms": output_arms,
        "cost_policy": contract["cost_policy"],
        "comparator_policies": contract["comparator_policies"],
        "boundary": "DETERMINISTIC_COMPARATORS_USE_ONLY_FROZEN_CONTEXTS_AND_PREDECLARED_RULES",
    }
    return self_digest(value, "result_digest")


def evaluate_prospective_research(*, run_root: Path) -> dict[str, Any]:
    """Materialize the frozen terminal comparison after all 24 decisions."""

    root, manifest, checkpoint = _run_documents(run_root)
    if manifest.get("evidence_class") != PROSPECTIVE_EVIDENCE_CLASS:
        raise ProspectiveResearchError("NOT_PROSPECTIVE_RUN")
    if checkpoint.get("status") != "TERMINAL_OUTCOMES_SEALED":
        raise ProspectiveResearchError("TERMINAL_REQUIRED_BEFORE_EVALUATION")
    terminal = _load_verified(root / str(checkpoint["accepted_state_path"]), "state_digest")
    comparator = comparator_results(run_root=root, through_cycle=TERMINAL_CYCLE)
    candidate_snapshot = terminal["terminal_snapshot"]
    curve = terminal["equity_curve"]
    effective_curve = [
        {
            "equity_after_cost_and_funding_usdt": (
                row.get("equity_after_observed_funding_usdt")
                or row["equity_before_unknown_funding_usdt"]
            )
        }
        for row in curve
    ]
    value = self_digest(
        {
            "schema_id": "prospective_24h_raw_evaluation",
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "evidence_class": PROSPECTIVE_EVIDENCE_CLASS,
            "decision_cycles": DECISION_CYCLES,
            "terminal_cycle": TERMINAL_CYCLE,
            "single_strategy_agent": {
                "terminal_snapshot": candidate_snapshot,
                "maximum_drawdown_fraction": canonical_decimal(
                    _maximum_drawdown_from_comparator(effective_curve)
                ),
                "funding_status": terminal.get("funding_status"),
                "funding_usdt": terminal.get("funding_usdt"),
                "fills": terminal["portfolio"]["fills"],
                "open_lots": [
                    lot
                    for lot in terminal["portfolio"]["lots"]
                    if _d(lot["remaining_quantity"], "TERMINAL_LOT_INVALID") > ZERO
                ],
                "reentry_delays_hours": terminal.get("reentry_delays_hours", []),
            },
            "comparators": comparator,
            "claims_boundary": {
                "engineering_completion": "SEPARATE_FROM_MARKET_RESULT",
                "predictive_validity": "NOT_ESTABLISHED_BY_ONE_24H_WINDOW",
                "stable_profitability": "NOT_ESTABLISHED",
                "real_trading_authority": "NONE",
            },
        },
        "evaluation_digest",
    )
    write_once_json(root / "evaluation" / "raw-evaluation.json", value)
    return value


__all__ = [
    "PROSPECTIVE_EVIDENCE_CLASS",
    "ProspectiveCollection",
    "ProspectiveResearchError",
    "collect_next_prospective_cycle",
    "collect_okx_six_context",
    "comparator_results",
    "evaluate_prospective_research",
    "interrupt_prospective_research",
    "prepare_prospective_research",
    "prepare_prospective_successor",
]
