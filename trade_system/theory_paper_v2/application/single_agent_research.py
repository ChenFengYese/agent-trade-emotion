"""Minimal single-Strategy-Agent research loop.

The module deliberately does not generate market paths, candidate actions, or a
deterministic trading policy.  It prepares point-in-time evidence, validates a
Strategy Agent's own analysis and actions against hard boundaries, replays
registered barriers, and persists a local non-executable state chain.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import statistics
import tempfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trade_system.theory_paper.common import (
    digest_json,
    parse_utc,
    sha256_file,
    verify_ledger,
)
from trade_system.theory_paper.experiment import _verify_latest_transaction_state
from trade_system.theory_paper.market import _closed_bars, _timeframe_measures

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_decimal,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ..domain.position import LotRole
from ..infrastructure.legacy_v1 import legacy_tree_digest
from ..infrastructure.authority.current_research import (
    assert_current_research_start_authorized,
)
from ..infrastructure.offline_portfolio import (
    Attribution,
    FillRecord,
    LotSide,
    OfflineLot,
    PortfolioState,
    close_lot,
    mark_portfolio,
    open_lot,
)


EVIDENCE_CLASS = "SEEN_V1_DIAGNOSTIC_REPLAY"
AGENT_JUDGMENT_EVIDENCE_LABEL = "PRACTICAL_SINGLE_AGENT_JUDGMENT"
AGENT_DECISION_SCHEMA_VERSION = "1.3.0"
FUNDING_PROXY_STATUS = (
    "MODELED_OKX_REALIZED_RATE_WITH_CLOSED_15M_TRADE_PRICE_PROXY_ACCRUAL"
)
SYSTEM_MODE = "LOCAL_PAPER_RESEARCH_NON_EXECUTABLE"
EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
PNL_RECONCILIATION_TOLERANCE_USDT = Decimal("0.000000000001")
SYMBOLS = (
    "SNDKUSDT",
    "MUUSDT",
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "HYPEUSDT",
)
REQUIRED_PATH_CLASSES = frozenset(
    {
        "TREND_CONTINUATION",
        "NORMAL_PULLBACK",
        "EXHAUSTION_OR_FAILURE",
        "RANGE_REFORMATION",
        "OTHER_OR_UNKNOWN",
    }
)
OPTIONAL_PATH_CLASSES = frozenset(
    {
        "LIQUIDITY_STRESS",
        "EVENT_REPRICING",
        "DATA_ARTIFACT",
    }
)
PATH_CLASSES = REQUIRED_PATH_CLASSES | OPTIONAL_PATH_CLASSES
PATH_CLASS_ORDER = (
    "TREND_CONTINUATION",
    "NORMAL_PULLBACK",
    "EXHAUSTION_OR_FAILURE",
    "RANGE_REFORMATION",
    "LIQUIDITY_STRESS",
    "EVENT_REPRICING",
    "DATA_ARTIFACT",
    "OTHER_OR_UNKNOWN",
)
MECHANISM_IDS = frozenset(
    {
        "CONTINUATION",
        "ABSORPTION_REVERSAL",
        "RANGE",
        "LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM",
        "EVENT_REPRICING",
        "ARTIFACT",
        "OTHER",
    }
)
SUPPORT_LEVELS = frozenset(
    {"DOMINANT", "SUPPORTED", "PLAUSIBLE", "WEAK", "INVALIDATED", "UNKNOWN"}
)
EVIDENCE_PERSPECTIVES = frozenset(
    {
        "PRICE_STRUCTURE",
        "ORDER_FLOW",
        "LIQUIDITY",
        "LEVERAGE_CROWDING",
        "VOLATILITY",
        "PUBLIC_EVENT",
        "CROSS_MARKET",
        "DATA_QUALITY",
        "EXECUTION",
    }
)
EVIDENCE_DIRECTIONS = frozenset(
    {"SUPPORT", "SOFT_CONTRADICTION", "HARD_FALSIFIER"}
)
ORDINAL_STRENGTHS = frozenset({"WEAK", "MODERATE", "STRONG"})
PATH_CONFIDENCE_LEVELS = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})
EPISTEMIC_TYPES = frozenset(
    {"OBSERVATION", "DERIVED_MEASURE", "INFERENCE", "HYPOTHESIS", "FORECAST", "POLICY"}
)
STRATEGIC_STATUSES = frozenset({"ACTIVE", "CHALLENGED", "INVALIDATED", "CLOSED", "NONE"})
EPISODE_OPERATIONS = frozenset(
    {"OPEN", "UPDATE", "CHALLENGE", "INVALIDATE", "CLOSE", "REPLACE", "NONE"}
)
ACTION_TYPES = frozenset(
    {
        "HOLD",
        "WAIT",
        "SET_PROTECTION",
        "MOVE_STOP",
        "TRAIL_CORE",
        "OPEN_CORE",
        "OPEN_TACTICAL",
        "ADD_CORE",
        "ADD_TACTICAL",
        "REDUCE_CORE",
        "REDUCE_TACTICAL",
        "PARTIAL_TAKE_PROFIT",
        "EXIT_TACTICAL",
        "EXIT_WITH_REENTRY",
        "EXIT_STRATEGIC",
        "REENTER_CORE",
        "REENTER_TACTICAL",
        "CANCEL_ORDER",
        "ACTIVATE_ORDER",
    }
)
NEW_RISK_ACTIONS = frozenset(
    {
        "OPEN_CORE",
        "OPEN_TACTICAL",
        "ADD_CORE",
        "ADD_TACTICAL",
        "REENTER_CORE",
        "REENTER_TACTICAL",
    }
)
REDUCTION_ACTIONS = frozenset(
    {
        "REDUCE_CORE",
        "REDUCE_TACTICAL",
        "PARTIAL_TAKE_PROFIT",
        "EXIT_TACTICAL",
        "EXIT_WITH_REENTRY",
        "EXIT_STRATEGIC",
    }
)
COMPARISON_CLASSES = frozenset(
    {
        "HOLD",
        "OPEN",
        "ADD",
        "REDUCE",
        "PARTIAL_TAKE_PROFIT",
        "EXIT",
        "REENTER",
        "WAIT",
    }
)
OBSERVATION_REQUEST_STATUSES = frozenset(
    {"PENDING", "FULFILLED", "UNAVAILABLE", "DROPPED_NO_INCREMENTAL_VALUE"}
)
OBSERVATION_SOURCE_PREFERENCES = frozenset(
    {
        "CURRENT_CONTEXT",
        "FROZEN_RAW_DERIVATION",
        "PUBLIC_PRIMARY_SOURCE",
        "PUBLIC_ALTERNATIVE_SOURCE",
        "LABELED_PROXY",
    }
)
ZERO = Decimal("0")
ONE = Decimal("1")


class SingleAgentResearchError(ValueError):
    """Fail-closed research-loop error."""


def _d(value: Any, code: str) -> Decimal:
    if isinstance(value, bool):
        raise SingleAgentResearchError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise SingleAgentResearchError(code) from exc
    if not result.is_finite():
        raise SingleAgentResearchError(code)
    return result


def _ts(value: str | datetime) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else parse_utc(str(value))
    except Exception as exc:
        raise SingleAgentResearchError("CLOCK_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise SingleAgentResearchError("CLOCK_TIME_INVALID")
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _iso_ms(value: int) -> str:
    return _iso(datetime.fromtimestamp(value / 1000, tz=UTC))


def _load_json_float(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SingleAgentResearchError(f"SOURCE_JSON_INVALID:{path}") from exc
    if not isinstance(value, dict):
        raise SingleAgentResearchError(f"SOURCE_JSON_ROOT_INVALID:{path}")
    return value


def _canonical_source_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return canonical_decimal(Decimal(str(value)))
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_source_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_source_value(item) for item in value]
    raise SingleAgentResearchError(f"SOURCE_VALUE_TYPE_UNSUPPORTED:{type(value).__name__}")


def _write_atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _decision_at_from_analysis_bytes(path: Path) -> str:
    raw = Path(path).read_bytes()
    matches = re.findall(rb'"decision_at":"([^"\\]+)"', raw)
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise SingleAgentResearchError("SOURCE_ANALYSIS_DECISION_AT_AMBIGUOUS")
    try:
        value = unique[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise SingleAgentResearchError("SOURCE_ANALYSIS_DECISION_AT_INVALID") from exc
    _ts(value)
    return value


def _fill_document(fill: FillRecord) -> dict[str, Any]:
    return {
        "fill_id": fill.fill_id,
        "lot_id": fill.lot_id,
        "instrument_id": fill.instrument_id,
        "side": fill.side,
        "quantity": canonical_decimal(fill.quantity),
        "fill_price": canonical_decimal(fill.fill_price),
        "notional": canonical_decimal(fill.notional),
        "fee": canonical_decimal(fill.fee),
        "realized_pnl_before_fee": canonical_decimal(fill.realized_pnl_before_fee),
        "occurred_at": _iso(fill.occurred_at),
        "reason": fill.reason,
        "attribution": fill.attribution.value,
    }


def _lot_document(lot: OfflineLot) -> dict[str, Any]:
    return {
        "lot_id": lot.lot_id,
        "instrument_id": lot.instrument_id,
        "side": lot.side.value,
        "role": lot.role.value,
        "attribution": lot.attribution.value,
        "quantity": canonical_decimal(lot.quantity),
        "remaining_quantity": canonical_decimal(lot.remaining_quantity),
        "entry_price": canonical_decimal(lot.entry_price),
        "stop_price": None if lot.stop_price is None else canonical_decimal(lot.stop_price),
        "target_price": None if lot.target_price is None else canonical_decimal(lot.target_price),
        "opened_at": _iso(lot.opened_at),
        "episode_id": lot.episode_id,
        "stage_id": lot.stage_id,
        "geometry_id": lot.geometry_id,
        "contract_multiplier": canonical_decimal(lot.contract_multiplier),
    }


def _portfolio_document(state: PortfolioState) -> dict[str, Any]:
    return {
        "portfolio_id": state.portfolio_id,
        "revision": state.revision,
        "initial_equity": canonical_decimal(state.initial_equity),
        "realized_pnl_before_cost": canonical_decimal(state.realized_pnl_before_cost),
        "total_fees": canonical_decimal(state.total_fees),
        "lots": [_lot_document(lot) for lot in state.lots],
        "fills": [_fill_document(fill) for fill in state.fills],
    }


def _portfolio_from_document(value: Mapping[str, Any]) -> PortfolioState:
    try:
        lots = tuple(
            OfflineLot(
                lot_id=str(row["lot_id"]),
                instrument_id=str(row["instrument_id"]),
                side=LotSide(str(row["side"])),
                role=LotRole(str(row["role"])),
                attribution=Attribution(str(row["attribution"])),
                quantity=_d(row["quantity"], "PORTFOLIO_LOT_INVALID"),
                remaining_quantity=_d(row["remaining_quantity"], "PORTFOLIO_LOT_INVALID"),
                entry_price=_d(row["entry_price"], "PORTFOLIO_LOT_INVALID"),
                stop_price=(
                    None
                    if row.get("stop_price") is None
                    else _d(row["stop_price"], "PORTFOLIO_LOT_INVALID")
                ),
                target_price=(
                    None
                    if row.get("target_price") is None
                    else _d(row["target_price"], "PORTFOLIO_LOT_INVALID")
                ),
                opened_at=_ts(row["opened_at"]),
                episode_id=row.get("episode_id"),
                stage_id=row.get("stage_id"),
                geometry_id=row.get("geometry_id"),
                contract_multiplier=_d(row["contract_multiplier"], "PORTFOLIO_LOT_INVALID"),
            )
            for row in value["lots"]
        )
        fills = tuple(
            FillRecord(
                fill_id=str(row["fill_id"]),
                lot_id=str(row["lot_id"]),
                instrument_id=str(row["instrument_id"]),
                side=str(row["side"]),
                quantity=_d(row["quantity"], "PORTFOLIO_FILL_INVALID"),
                fill_price=_d(row["fill_price"], "PORTFOLIO_FILL_INVALID"),
                notional=_d(row["notional"], "PORTFOLIO_FILL_INVALID"),
                fee=_d(row["fee"], "PORTFOLIO_FILL_INVALID"),
                realized_pnl_before_fee=_d(
                    row["realized_pnl_before_fee"], "PORTFOLIO_FILL_INVALID"
                ),
                occurred_at=_ts(row["occurred_at"]),
                reason=str(row["reason"]),
                attribution=Attribution(str(row["attribution"])),
            )
            for row in value["fills"]
        )
        return PortfolioState(
            portfolio_id=str(value["portfolio_id"]),
            revision=int(value["revision"]),
            initial_equity=_d(value["initial_equity"], "PORTFOLIO_STATE_INVALID"),
            realized_pnl_before_cost=_d(
                value["realized_pnl_before_cost"], "PORTFOLIO_STATE_INVALID"
            ),
            total_fees=_d(value["total_fees"], "PORTFOLIO_STATE_INVALID"),
            lots=lots,
            fills=fills,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, SingleAgentResearchError):
            raise
        raise SingleAgentResearchError("PORTFOLIO_STATE_INVALID") from exc


def _open_lots(portfolio: PortfolioState, symbol: str | None = None) -> tuple[OfflineLot, ...]:
    return tuple(
        lot
        for lot in portfolio.lots
        if lot.remaining_quantity > ZERO
        and (symbol is None or lot.instrument_id == symbol)
    )


def _rolling_vwap(bars: Sequence[Mapping[str, float]], window: int) -> Decimal | None:
    selected = bars[-window:]
    total_volume = sum(_d(row["volume"], "BAR_VALUE_INVALID") for row in selected)
    if not selected or total_volume <= ZERO:
        return None
    value = sum(
        _d(row["close"], "BAR_VALUE_INVALID")
        * _d(row["volume"], "BAR_VALUE_INVALID")
        for row in selected
    ) / total_volume
    return value


def _realized_volatility(bars: Sequence[Mapping[str, float]], window: int) -> Decimal | None:
    selected = bars[-(window + 1) :]
    if len(selected) < 3:
        return None
    returns = [
        math.log(float(selected[index]["close"]) / float(selected[index - 1]["close"]))
        for index in range(1, len(selected))
        if float(selected[index - 1]["close"]) > 0
    ]
    if len(returns) < 2:
        return None
    return Decimal(str(statistics.pstdev(returns) * math.sqrt(len(returns))))


def _normalized_bar(symbol: str, timeframe: str, row: Mapping[str, float]) -> dict[str, Any]:
    open_ms = int(float(row["open_time"]))
    close_ms = int(float(row["close_time"]))
    return {
        "bar_id": f"{symbol}:{timeframe}:{open_ms}",
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time_ms": open_ms,
        "close_time_ms": close_ms,
        "open_time": _iso_ms(open_ms),
        "available_at": _iso_ms(close_ms),
        "open": canonical_decimal(_d(row["open"], "BAR_VALUE_INVALID")),
        "high": canonical_decimal(_d(row["high"], "BAR_VALUE_INVALID")),
        "low": canonical_decimal(_d(row["low"], "BAR_VALUE_INVALID")),
        "close": canonical_decimal(_d(row["close"], "BAR_VALUE_INVALID")),
        "volume": canonical_decimal(_d(row["volume"], "BAR_VALUE_INVALID")),
    }


def _evidence_rows(
    symbol: str,
    *,
    observed_at: str,
    technical: Mapping[str, Mapping[str, Any]],
    measures: Mapping[str, Any],
    news: Sequence[Mapping[str, Any]],
    source_version: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(
        identifier: str,
        value: Any,
        source: str,
        limitation: str,
        dependency_group: str,
        version: str | None = None,
    ) -> None:
        rows.append(
            {
                "evidence_ref": f"{symbol}:{identifier}",
                "value": _canonical_source_value(value),
                "available_at": observed_at,
                "source": source,
                "source_version": version or f"{source}:{source_version}",
                "dependency_group": dependency_group,
                "limitation": limitation,
            }
        )

    add(
        "mark",
        measures.get("price"),
        "PUBLIC_MARK_SNAPSHOT",
        "POINT_SNAPSHOT",
        f"{symbol}:mark:{observed_at}",
    )
    for timeframe, values in technical.items():
        last_closed = values.get("last_closed_bar")
        technical_version = (
            str(last_closed.get("close_time"))
            if isinstance(last_closed, Mapping) and last_closed.get("close_time")
            else "UNKNOWN_NO_CLOSED_BAR"
        )
        for key, value in values.items():
            if key in {"last_closed_bar", "status", "supports", "resistances"}:
                continue
            add(
                f"{timeframe}:{key}",
                value,
                f"CLOSED_BARS_{timeframe}",
                "DERIVED_OBSERVATION_NOT_MECHANICAL_SIGNAL",
                f"{symbol}:closed-bars:{timeframe}:{technical_version}",
            )
        for key in ("supports", "resistances"):
            add(
                f"{timeframe}:{key}",
                values.get(key),
                f"CLOSED_BARS_{timeframe}",
                "PIVOT_CANDIDATES_NOT_ORDER_LEVELS",
                f"{symbol}:closed-bars:{timeframe}:{technical_version}",
            )
    mapping = {
        "flow": measures.get("directional_pressure_D", {}),
        "leverage": measures.get("leverage_L", {}),
        "crowding": measures.get("crowding_C", {}),
        "forced_deleveraging": measures.get("forced_deleveraging_F", {}),
        "liquidity": measures.get("liquidity_resilience_R", {}),
        "ticker_24h": measures.get("ticker_24h", {}),
    }
    for group, values in mapping.items():
        if not isinstance(values, Mapping):
            continue
        for key, value in values.items():
            if isinstance(value, Mapping):
                for nested_key, nested_value in value.items():
                    add(
                        f"{group}:{key}:{nested_key}",
                        nested_value,
                        "PUBLIC_MARKET_SNAPSHOT",
                        "PROXY_OR_WINDOWED_OBSERVATION",
                        f"{symbol}:{group}:{key}:{observed_at}",
                    )
            elif key != "interpretation_boundary":
                add(
                    f"{group}:{key}",
                    value,
                    "PUBLIC_MARKET_SNAPSHOT",
                    "PROXY_OR_WINDOWED_OBSERVATION",
                    f"{symbol}:{group}:{key}:{observed_at}",
                )
    for item in news:
        add(
            f"news:{item['news_id']}",
            item["title"],
            "PUBLIC_NEWS_DISCOVERY_METADATA",
            "HEADLINE_METADATA_NOT_CAUSAL_OR_SENTIMENT_TRUTH",
            f"{symbol}:news:{item['news_id']}",
            f"PUBLIC_NEWS_DISCOVERY_METADATA:{item['news_id']}",
        )
    return rows


def _timeframe_role_profile(symbol: str, underlying_session: str) -> dict[str, Any]:
    if symbol in {"SNDKUSDT", "MUUSDT"}:
        roles = {
            "1w": "REFERENCE_EQUITY_TAIL_BACKGROUND_ONLY_WHEN_HISTORY_IS_ADEQUATE",
            "1d": "REFERENCE_EQUITY_STRATEGIC_STRUCTURE_WITH_SESSION_GAP_CAVEAT",
            "4h": "DERIVATIVE_REGIME_AND_REFERENCE_SESSION_TRANSITION",
            "1h": "SETUP_AND_DYNAMIC_GEOMETRY",
            "15m": "EXECUTION_PRESSURE_AND_FROZEN_BARRIER_REPLAY",
        }
        profile_kind = "EQUITY_REFERENCE_CONTINUOUS_DERIVATIVE"
    else:
        roles = {
            "1w": "SYMBOL_SPECIFIC_TAIL_RISK_BACKGROUND",
            "1d": "SYMBOL_SPECIFIC_STRATEGIC_STRUCTURE",
            "4h": "SYMBOL_SPECIFIC_OPERATIONAL_REGIME",
            "1h": "SYMBOL_SPECIFIC_SETUP_AND_DYNAMIC_GEOMETRY",
            "15m": "SYMBOL_SPECIFIC_EXECUTION_PRESSURE_AND_BARRIER_REPLAY",
        }
        profile_kind = "CONTINUOUS_CRYPTO_DERIVATIVE"
    return {
        "profile_id": f"{symbol}:{profile_kind}:V1",
        "symbol": symbol,
        "profile_kind": profile_kind,
        "underlying_session": underlying_session,
        "ordered_high_to_low": ["1w", "1d", "4h", "1h", "15m"],
        "roles": roles,
        "information_flow": "HIGHER_ROLE_CONSTRAINS_LOWER_ROLE;NO_MAJORITY_VOTE",
        "boundary": "SYMBOL_AND_MARKET_SPECIFIC_PROFILE_NOT_UNIVERSAL_BTC_ROLE_REUSE",
    }


def _news_rows(news: Mapping[str, Any], symbol: str, decision_at: str) -> list[dict[str, Any]]:
    queries = news.get("queries")
    query = queries.get(symbol, {}) if isinstance(queries, Mapping) else {}
    items = query.get("items", []) if isinstance(query, Mapping) else []
    output: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        published_value = str(item.get("published_at") or "")
        try:
            published_at = _ts(published_value)
        except SingleAgentResearchError:
            try:
                published_at = parsedate_to_datetime(published_value)
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=UTC)
                published_at = published_at.astimezone(UTC)
            except (TypeError, ValueError, OverflowError):
                continue
        if published_at > _ts(decision_at):
            continue
        source = str(item.get("source") or "UNKNOWN")
        title = str(item.get("title") or "")
        identity = canonical_digest(
            {"published_at": _iso(published_at), "source": source, "title": title}
        )[:20]
        output.append(
            {
                "news_id": f"NEWS-{identity}",
                "published_at": _iso(published_at),
                "source": source,
                "title": title,
                "url": str(item.get("url") or ""),
                "boundary": "HEADLINE_METADATA_NOT_CAUSAL_OR_SENTIMENT_TRUTH",
            }
        )
    return sorted(output, key=lambda row: row["published_at"])[-5:]


def _symbol_context(
    source: Mapping[str, Any],
    *,
    market_observed_at: str,
    decision_at: str,
    news: Mapping[str, Any],
) -> dict[str, Any]:
    symbol = str(source.get("symbol", ""))
    if symbol not in SYMBOLS:
        raise SingleAgentResearchError("SOURCE_SYMBOL_SET_INVALID")
    observed_at = str(source.get("observed_at") or market_observed_at)
    if _ts(observed_at) > _ts(decision_at):
        raise SingleAgentResearchError("PIT_AVAILABLE_AT_VIOLATION")
    raw = source.get("raw")
    stored_measures = source.get("measures")
    if not isinstance(raw, Mapping) or not isinstance(stored_measures, Mapping):
        raise SingleAgentResearchError("SOURCE_MARKET_SYMBOL_INVALID")
    raw_klines = raw.get("klines")
    if not isinstance(raw_klines, Mapping):
        raise SingleAgentResearchError("SOURCE_KLINES_MISSING")
    observed_ms = int(_ts(observed_at).timestamp() * 1000)
    technical: dict[str, dict[str, Any]] = {}
    recent_bars: dict[str, list[dict[str, Any]]] = {}
    execution_bars: list[dict[str, Any]] = []
    for timeframe, keep in (("15m", 16), ("1h", 24), ("4h", 16), ("1d", 16), ("1w", 12)):
        raw_rows = raw_klines.get(timeframe)
        bars = _closed_bars(raw_rows, observed_ms)
        if not bars:
            if timeframe == "15m":
                raise SingleAgentResearchError("SOURCE_CLOSED_BARS_EMPTY")
            values = _timeframe_measures([])
            values["rolling_vwap_24"] = None
            values["realized_volatility_20"] = None
            values["availability"] = "UNKNOWN_NOT_DIRECTLY_OBSERVED_OR_DERIVABLE"
            technical[timeframe] = _canonical_source_value(values)
            recent_bars[timeframe] = []
            continue
        if any(
            int(bars[index]["close_time"]) <= int(bars[index - 1]["close_time"])
            for index in range(1, len(bars))
        ):
            raise SingleAgentResearchError("SOURCE_KLINE_ORDER_INVALID")
        values = _timeframe_measures(bars)
        values["rolling_vwap_24"] = _rolling_vwap(bars, 24)
        values["realized_volatility_20"] = _realized_volatility(bars, 20)
        technical[timeframe] = _canonical_source_value(values)
        normalized = [_normalized_bar(symbol, timeframe, row) for row in bars[-keep:]]
        recent_bars[timeframe] = normalized
        if timeframe == "15m":
            execution_bars = [_normalized_bar(symbol, timeframe, row) for row in bars]
    headlines = _news_rows(news, symbol, decision_at)
    measures = copy.deepcopy(dict(stored_measures))
    measures["timeframes"] = technical
    source_version = str(source.get("raw_digest") or canonical_digest(raw))
    evidence = _evidence_rows(
        symbol,
        observed_at=observed_at,
        technical=technical,
        measures=measures,
        news=headlines,
        source_version=source_version,
    )
    underlying_session = str(source.get("underlying_session") or "UNKNOWN")
    return {
        "symbol": symbol,
        "venue": str(source.get("venue") or "UNKNOWN"),
        "instrument_kind": str(source.get("instrument_kind") or "UNKNOWN"),
        "underlying_session": underlying_session,
        "timeframe_role_profile": _timeframe_role_profile(symbol, underlying_session),
        "reference_mode": str(source.get("reference_mode") or "UNKNOWN"),
        "observed_at": observed_at,
        "mark": canonical_decimal(_d(stored_measures.get("price"), "SOURCE_MARK_INVALID")),
        "data_quality": _canonical_source_value(source.get("data_quality")),
        "technical": technical,
        "market_proxies": _canonical_source_value(
            {
                key: value
                for key, value in stored_measures.items()
                if key != "timeframes"
            }
        ),
        "recent_closed_bars": recent_bars,
        "execution_bars_15m": execution_bars,
        "news_metadata": headlines,
        "evidence_catalog": evidence,
        "funding_events": _canonical_source_value(source.get("funding_events", [])),
        "instrument_rules": _canonical_source_value(source.get("instrument_rules", {})),
        "source_raw_digest": source_version,
    }


def _cross_market_context(symbols: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        technical = symbols[symbol]["technical"]
        one_hour = technical["1h"]
        one_day = technical["1d"]
        rows.append(
            {
                "symbol": symbol,
                "change_1h_pct": one_hour.get("change_1_bar_pct"),
                "change_6h_pct": one_hour.get("change_6_bar_pct"),
                "change_1d_pct": one_day.get("change_1_bar_pct"),
                "relative_volume_1h": one_hour.get("relative_volume20"),
                "funding_rate": symbols[symbol]["market_proxies"]
                .get("crowding_C", {})
                .get("funding_rate"),
                "oi_change_1h_pct": symbols[symbol]["market_proxies"]
                .get("leverage_L", {})
                .get("open_interest_value_1h_change_pct"),
            }
        )
    ranked = sorted(
        rows,
        key=lambda row: _d(row["change_6h_pct"] or "-999999", "CROSS_MARKET_VALUE_INVALID"),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["six_hour_strength_rank"] = rank
    ordered_rows = sorted(ranked, key=lambda row: SYMBOLS.index(str(row["symbol"])))
    return {
        "evidence_ref": "cross_market:six-symbol:relative-strength",
        "available_at": _iso(
            max(_ts(str(symbols[symbol]["observed_at"])) for symbol in SYMBOLS)
        ),
        "dependency_group": "cross-market:six-symbol:relative-strength",
        "source_version": f"CROSS_MARKET_RELATIVE_STRENGTH_V1:{canonical_digest(ordered_rows)}",
        "rows": ordered_rows,
        "boundary": "RELATIVE_STRENGTH_IS_CROSS_SECTIONAL_OBSERVATION_NOT_CAUSAL_SIGNAL",
    }


def normalize_seen_v1_cycle(
    market: Mapping[str, Any],
    news: Mapping[str, Any],
    *,
    cycle_index: int,
    decision_at: str,
) -> dict[str, Any]:
    market_observed_at = str(market.get("observed_at") or "")
    news_observed_at = str(news.get("observed_at") or "")
    if (
        not market_observed_at
        or not news_observed_at
        or _ts(market_observed_at) > _ts(decision_at)
        or _ts(news_observed_at) > _ts(decision_at)
    ):
        raise SingleAgentResearchError("PIT_AVAILABLE_AT_VIOLATION")
    source_rows = market.get("symbols")
    if not isinstance(source_rows, list):
        raise SingleAgentResearchError("SOURCE_MARKET_SYMBOLS_INVALID")
    normalized_rows = [
        _symbol_context(
            row,
            market_observed_at=market_observed_at,
            decision_at=decision_at,
            news=news,
        )
        for row in source_rows
        if isinstance(row, Mapping)
    ]
    symbols = {str(row["symbol"]): row for row in normalized_rows}
    if tuple(sorted(symbols)) != tuple(sorted(SYMBOLS)):
        raise SingleAgentResearchError("SOURCE_SYMBOL_SET_INVALID")
    value = {
        "schema_id": "single_agent_market_context",
        "schema_version": "1.0.0",
        "cycle_index": cycle_index,
        "cycle_id": f"cycle-{cycle_index:04d}",
        "decision_at": decision_at,
        "market_observed_at": market_observed_at,
        "news_observed_at": news_observed_at,
        "symbols": symbols,
        "cross_market": _cross_market_context(symbols),
        "point_in_time_rule": "AVAILABLE_AT_LTE_DECISION_AT_CLOSED_BARS_ONLY",
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    return self_digest(value, "context_digest")


def _initial_state(
    *,
    run_id: str,
    source_config: Mapping[str, Any],
    activated_at: str,
    first_context: Mapping[str, Any],
) -> dict[str, Any]:
    initial = source_config.get("initial_portfolio")
    if not isinstance(initial, Mapping):
        raise SingleAgentResearchError("SOURCE_INITIAL_PORTFOLIO_INVALID")
    equity = _d(initial.get("initial_cash_usdt"), "SOURCE_INITIAL_EQUITY_INVALID")
    lots: list[OfflineLot] = []
    lot_contracts: dict[str, dict[str, Any]] = {}
    episodes: dict[str, dict[str, Any] | None] = {symbol: None for symbol in SYMBOLS}
    for index, row in enumerate(initial.get("positions", []), start=1):
        if not isinstance(row, Mapping):
            raise SingleAgentResearchError("SOURCE_INITIAL_POSITION_INVALID")
        symbol = str(row.get("symbol"))
        if symbol not in SYMBOLS or str(row.get("side")) != LotSide.LONG.value:
            raise SingleAgentResearchError("SOURCE_INITIAL_POSITION_INVALID")
        entry = _d(row.get("entry_price"), "SOURCE_INITIAL_POSITION_INVALID")
        if row.get("quantity") is not None:
            quantity = _d(row.get("quantity"), "SOURCE_INITIAL_POSITION_INVALID")
        else:
            notional = _d(row.get("notional_usdt"), "SOURCE_INITIAL_POSITION_INVALID")
            quantity = notional / entry
        if entry <= ZERO or quantity <= ZERO:
            raise SingleAgentResearchError("SOURCE_INITIAL_POSITION_INVALID")
        lot_id = f"{run_id}:exogenous:{index:02d}"
        episode_id = f"{run_id}:{symbol}:episode-001"
        initial_stop = (
            None
            if row.get("initial_stop_price") is None
            else _d(row.get("initial_stop_price"), "SOURCE_INITIAL_POSITION_INVALID")
        )
        management_checkpoint = (
            None
            if row.get("management_checkpoint") is None
            else _d(row.get("management_checkpoint"), "SOURCE_INITIAL_POSITION_INVALID")
        )
        if initial_stop is not None and not (
            ZERO < initial_stop < entry
            and management_checkpoint is not None
            and management_checkpoint > entry
            and row.get("risk_budget_usdt") is not None
            and row.get("max_horizon_at") is not None
        ):
            raise SingleAgentResearchError("SOURCE_INITIAL_CONTRACT_INCOMPLETE")
        geometry_id = str(
            row.get("geometry_id") or f"{episode_id}:geometry-unset"
        )
        lot = OfflineLot(
            lot_id=lot_id,
            instrument_id=symbol,
            side=LotSide.LONG,
            role=LotRole.CORE,
            attribution=Attribution.EXOGENOUS,
            quantity=quantity,
            remaining_quantity=quantity,
            entry_price=entry,
            stop_price=initial_stop,
            target_price=None,
            opened_at=_ts(activated_at),
            episode_id=episode_id,
            stage_id=f"{episode_id}:genesis",
            geometry_id=geometry_id,
        )
        lots.append(lot)
        lot_contracts[lot_id] = {
            "lot_id": lot_id,
            "episode_id": episode_id,
            "role": "CORE",
            "exit_intent": str(
                row.get("exit_intent") or "EXOGENOUS_RECONCILIATION_REQUIRED"
            ),
            "risk_budget_usdt": row.get("risk_budget_usdt"),
            "management_checkpoint": (
                None
                if management_checkpoint is None
                else canonical_decimal(management_checkpoint)
            ),
            "management_checkpoint_id": row.get("management_checkpoint_id"),
            "max_horizon_at": row.get("max_horizon_at"),
            "protection_active_from": (
                activated_at if initial_stop is not None else None
            ),
            "geometry_id": lot.geometry_id,
            "checkpoint_event_ids": [],
        }
        episodes[symbol] = {
            "episode_id": episode_id,
            "revision": 0,
            "previous_episode_digest": None,
            "strategic_status": "CHALLENGED",
            "exposure_status": "EXPOSED_CORE",
            "primary_direction": "LONG",
            "primary_horizon": "UNDECLARED_GENESIS",
            "market_regime": "UNKNOWN_REQUIRES_GENESIS_REVIEW",
            "origin_hypothesis": "EXOGENOUS_INITIAL_POSITION_THESIS_UNDECLARED",
            "paths": [],
            "evidence_ledger": [],
            "evidence_aggregation": {},
            "consumed_evidence_keys": [],
            "operational_lead_path_id": None,
            "runner_up_path_id": None,
            "competition_set_status": "UNKNOWN_NO_VALID_COMPETITION_SET",
            "active_primitive_mechanism_ids": ["OTHER"],
            "hard_invalidators": [],
            "pending_observations": ["GENESIS_REVIEW_REQUIRED"],
            "review_by": str(first_context["decision_at"]),
            "geometry": (
                None
                if initial_stop is None
                else {
                    "geometry_id": geometry_id,
                    "status": "EXOGENOUS_GENESIS_PROTECTION_ONLY",
                    "hard_stop": canonical_decimal(initial_stop),
                    "management_checkpoint": canonical_decimal(
                        management_checkpoint
                    ),
                    "valid_until": str(row["max_horizon_at"]),
                    "basis": "FROZEN_GENESIS_1H_ATR_NOT_A_MARKET_PATH_SIGNAL",
                }
            ),
            "exit_reason": None,
            "reentry_contract": None,
        }
        episodes[symbol] = self_digest(episodes[symbol], "episode_digest")
    portfolio = PortfolioState(
        portfolio_id=f"{run_id}:portfolio",
        revision=0,
        initial_equity=equity,
        realized_pnl_before_cost=ZERO,
        total_fees=ZERO,
        lots=tuple(lots),
        fills=(),
    )
    orders: list[dict[str, Any]] = []
    for index, row in enumerate(initial.get("orders", []), start=1):
        if not isinstance(row, Mapping):
            raise SingleAgentResearchError("SOURCE_INITIAL_ORDER_INVALID")
        orders.append(
            {
                "order_id": f"V1-ORDER-{index:03d}",
                "symbol": str(row.get("symbol")),
                "side": str(row.get("side")),
                "limit_price": canonical_decimal(_d(row.get("limit_price"), "SOURCE_INITIAL_ORDER_INVALID")),
                "notional_usdt": canonical_decimal(_d(row.get("notional_usdt"), "SOURCE_INITIAL_ORDER_INVALID")),
                "status": "REVIEW_REQUIRED",
                "role": None,
                "episode_id": None,
                "stop_price": None,
                "target_price": None,
                "management_checkpoint": None,
                "max_horizon_at": None,
                "geometry_id": None,
                "active_from": None,
            }
        )
    processed = {}
    activated_ms = int(_ts(activated_at).timestamp() * 1000)
    for symbol in SYMBOLS:
        bars = first_context["symbols"][symbol]["execution_bars_15m"]
        eligible = [int(row["close_time_ms"]) for row in bars if int(row["close_time_ms"]) <= activated_ms]
        processed[symbol] = max(eligible, default=0)
    funding_policy = source_config.get("funding_policy")
    funding_observed = (
        isinstance(funding_policy, Mapping)
        and funding_policy.get("status")
        == FUNDING_PROXY_STATUS
    )
    value = {
        "schema_id": "single_agent_accepted_state",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "revision": 0,
        "previous_state_digest": None,
        "accepted_at": activated_at,
        "state_stage": "GENESIS",
        "portfolio": _portfolio_document(portfolio),
        "lot_contracts": lot_contracts,
        "episodes": episodes,
        "orders": orders,
        "processed_15m_close_time_ms": processed,
        "peak_equity_usdt": canonical_decimal(equity),
        "equity_curve": [],
        "target_events": [],
        "reentry_delays_hours": [],
        "action_fidelity_failures": [],
        "state_continuity_failures": [],
        "funding_status": (
            FUNDING_PROXY_STATUS
            if funding_observed
            else "UNKNOWN_NOT_IN_V1_PNL"
        ),
        "funding_usdt": "0" if funding_observed else None,
        "processed_funding_event_ids": [],
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    return self_digest(value, "state_digest")


def prepare_seen_v1_research(
    *,
    project_root: Path,
    source_root: Path,
    runtime_root: Path,
    contract_path: Path,
    run_id: str,
    prepared_at: datetime | None = None,
) -> dict[str, Any]:
    """Freeze point-in-time Agent contexts without reading recorded decisions."""

    project = Path(project_root).resolve(strict=True)
    assert_current_research_start_authorized(
        project_root=project,
        operation="PREPARE_SEEN_V1",
        run_id=run_id,
        template_path=contract_path,
    )
    source = Path(source_root).resolve(strict=True)
    contract = load_json_strict(contract_path)
    if contract.get("evidence_class") != EVIDENCE_CLASS:
        raise SingleAgentResearchError("CONTRACT_EVIDENCE_CLASS_INVALID")
    if contract.get("source_run_id") != "msta-paper-20260729T212716Z-87cc29bb":
        raise SingleAgentResearchError("SOURCE_RUN_ID_MISMATCH")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{5,95}", run_id):
        raise SingleAgentResearchError("RUN_ID_INVALID")
    implementation_bindings = contract.get("implementation_bindings")
    if not isinstance(implementation_bindings, list) or not implementation_bindings:
        raise SingleAgentResearchError("IMPLEMENTATION_BINDING_MISSING")
    for row in implementation_bindings:
        if not isinstance(row, Mapping):
            raise SingleAgentResearchError("IMPLEMENTATION_BINDING_INVALID")
        path = project / str(row.get("path") or "")
        if not path.is_file() or sha256_file(path) != str(row.get("physical_sha256")):
            raise SingleAgentResearchError(f"IMPLEMENTATION_BINDING_DRIFT:{path}")
    playbook_binding = contract.get("strategy_playbook")
    if not isinstance(playbook_binding, Mapping):
        raise SingleAgentResearchError("STRATEGY_PLAYBOOK_BINDING_MISSING")
    playbook_relative_path = str(playbook_binding.get("path") or "")
    try:
        playbook_path = (project / playbook_relative_path).resolve(strict=True)
        playbook_path.relative_to(project)
        playbook_text = playbook_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise SingleAgentResearchError("STRATEGY_PLAYBOOK_INVALID") from exc
    playbook_sha256 = sha256_file(playbook_path)
    if (
        not playbook_text.strip()
        or playbook_sha256 != str(playbook_binding.get("physical_sha256") or "")
    ):
        raise SingleAgentResearchError("STRATEGY_PLAYBOOK_BINDING_DRIFT")
    before = legacy_tree_digest(source)
    if before != str(contract.get("source_tree_digest")):
        raise SingleAgentResearchError("SOURCE_TREE_DIGEST_MISMATCH")
    try:
        ledger = verify_ledger(source)
        transactions = _verify_latest_transaction_state(source)
    except Exception as exc:
        raise SingleAgentResearchError("V1_LEDGER_OR_TRANSACTION_CHAIN_INVALID") from exc
    if ledger.get("valid") is not True or transactions.get("valid") is not True:
        raise SingleAgentResearchError("V1_LEDGER_OR_TRANSACTION_CHAIN_INVALID")
    source_manifest = _load_json_float(source / "manifest.json")
    source_config_raw = _load_json_float(source / "config.json")
    if source_manifest.get("run_id") != contract["source_run_id"]:
        raise SingleAgentResearchError("SOURCE_RUN_ID_MISMATCH")
    activated_at = str(source_manifest.get("started_at") or "")
    _ts(activated_at)
    run_root = Path(runtime_root).resolve() / run_id
    if run_root.exists():
        raise SingleAgentResearchError("RUN_ROOT_ALREADY_EXISTS")
    contexts: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    for cycle_index in range(1, 26):
        cycle_id = f"cycle-{cycle_index:04d}"
        cycle_root = source / "cycles" / cycle_id
        market_path = cycle_root / "market.json"
        news_path = cycle_root / "news.json"
        analysis_path = cycle_root / "analysis.json"
        decision_at = _decision_at_from_analysis_bytes(analysis_path)
        context = normalize_seen_v1_cycle(
            _load_json_float(market_path),
            _load_json_float(news_path),
            cycle_index=cycle_index,
            decision_at=decision_at,
        )
        contexts.append(context)
        source_rows.append(
            {
                "cycle_index": cycle_index,
                "market_path": market_path.relative_to(source).as_posix(),
                "market_sha256": sha256_file(market_path),
                "news_path": news_path.relative_to(source).as_posix(),
                "news_sha256": sha256_file(news_path),
                "analysis_cutoff_path": analysis_path.relative_to(source).as_posix(),
                "analysis_cutoff_sha256": sha256_file(analysis_path),
                "context_digest": context["context_digest"],
            }
        )
    after = legacy_tree_digest(source)
    if after != before:
        raise SingleAgentResearchError("LEGACY_WRITE_ATTEMPT_FORBIDDEN")
    run_root.mkdir(parents=True, exist_ok=False)
    for context in contexts:
        write_once_json(
            run_root / "market-contexts" / f"cycle-{int(context['cycle_index']):04d}.json",
            context,
        )
    source_config = _canonical_source_value(source_config_raw)
    genesis = _initial_state(
        run_id=run_id,
        source_config=source_config,
        activated_at=activated_at,
        first_context=contexts[0],
    )
    write_once_json(run_root / "states" / "state-0000-genesis.json", genesis)
    manifest = self_digest(
        {
            "schema_id": "single_agent_research_manifest",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "prepared_at": _iso((prepared_at or datetime.now(UTC)).astimezone(UTC)),
            "evidence_class": EVIDENCE_CLASS,
            "contract_digest": canonical_digest(contract),
            "research_contract": contract,
            "strategy_playbook": {
                "path": playbook_relative_path,
                "physical_sha256": playbook_sha256,
                "content": playbook_text,
            },
            "source_run_id": contract["source_run_id"],
            "source_root": str(source),
            "source_tree_digest_before": before,
            "source_tree_digest_after": after,
            "source_chain": {
                "ledger_event_count": ledger.get("event_count"),
                "ledger_tip_digest": ledger.get("tip_digest"),
                "transaction_count": transactions.get("transaction_count"),
                "latest_transaction_id": transactions.get("latest_transaction_id"),
            },
            "source_config": source_config,
            "contexts": source_rows,
            "decision_cycles": 24,
            "terminal_observation_cycle": 25,
            "strategy_agent_count": 1,
            "critic_enabled": False,
            "recorded_v1_decisions_opened": False,
            "recorded_v1_outcomes_opened": False,
            "funding_status": "UNKNOWN_NOT_IN_V1_PNL",
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


def _load_verified(path: Path, digest_field: str) -> dict[str, Any]:
    value = load_json_strict(path)
    try:
        verify_self_digest(value, digest_field)
    except Exception as exc:
        raise SingleAgentResearchError(f"DIGEST_INVALID:{path}") from exc
    return value


def _run_documents(run_root: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = Path(run_root).resolve(strict=True)
    manifest = _load_verified(root / "manifest.json", "manifest_digest")
    checkpoint = load_json_strict(root / "checkpoint.json")
    if checkpoint.get("run_id") != manifest.get("run_id"):
        raise SingleAgentResearchError("CHECKPOINT_RUN_MISMATCH")
    if checkpoint.get("manifest_digest") != manifest.get("manifest_digest"):
        raise SingleAgentResearchError("CHECKPOINT_MANIFEST_MISMATCH")
    return root, manifest, checkpoint


def _risk_policy(manifest: Mapping[str, Any]) -> dict[str, Decimal]:
    source_config = manifest.get("source_config")
    source = source_config.get("risk_policy") if isinstance(source_config, Mapping) else None
    if not isinstance(source, Mapping):
        raise SingleAgentResearchError("RISK_POLICY_MISSING")
    return {
        "standard_risk_fraction": _d(source.get("standard_thesis_risk_fraction"), "RISK_POLICY_INVALID"),
        "probe_risk_fraction": _d(source.get("exploration_probe_risk_fraction"), "RISK_POLICY_INVALID"),
        "symbol_risk_fraction": _d(source.get("per_instrument_open_pending_risk_fraction"), "RISK_POLICY_INVALID"),
        "portfolio_risk_fraction": _d(source.get("portfolio_open_pending_risk_fraction"), "RISK_POLICY_INVALID"),
        "gross_multiple": _d(source.get("gross_notional_equity_multiple"), "RISK_POLICY_INVALID"),
        "drawdown_fraction": _d(source.get("drawdown_no_new_risk_fraction"), "RISK_POLICY_INVALID"),
        "minimum_reward_risk": _d(source.get("minimum_reward_risk"), "RISK_POLICY_INVALID"),
        "taker_fee_rate": _d(source.get("default_taker_fee_rate"), "RISK_POLICY_INVALID"),
        "maker_fee_rate": _d(source.get("default_maker_fee_rate"), "RISK_POLICY_INVALID"),
        "market_slippage_bps": _d(source.get("default_market_slippage_bps"), "RISK_POLICY_INVALID"),
        "stop_slippage_bps": _d(source.get("default_stop_slippage_bps"), "RISK_POLICY_INVALID"),
        "symbol_notional_fraction": Decimal("0.35"),
        "minimum_notional_usdt": Decimal("50"),
        "maximum_notional_usdt": Decimal("1500"),
    }


def _marks(context: Mapping[str, Any]) -> dict[str, Decimal]:
    symbols = context.get("symbols")
    if not isinstance(symbols, Mapping):
        raise SingleAgentResearchError("CONTEXT_SYMBOLS_INVALID")
    return {
        symbol: _d(symbols[symbol]["mark"], "CONTEXT_MARK_INVALID")
        for symbol in SYMBOLS
    }


def _snapshot_document(
    snapshot: Any,
    *,
    funding_usdt: Decimal | None = None,
    cost_aware_open_risk_usdt: Decimal | None = None,
) -> dict[str, Any]:
    adjusted_net = None if funding_usdt is None else snapshot.net_pnl + funding_usdt
    adjusted_equity = None if funding_usdt is None else snapshot.equity + funding_usdt
    return {
        "marked_at": _iso(snapshot.marked_at),
        "marks": {key: canonical_decimal(value) for key, value in snapshot.marks},
        "realized_pnl_before_cost_usdt": canonical_decimal(snapshot.realized_pnl_before_cost),
        "unrealized_pnl_usdt": canonical_decimal(snapshot.unrealized_pnl),
        "fees_usdt": canonical_decimal(snapshot.total_fees),
        "funding_usdt": None if funding_usdt is None else canonical_decimal(funding_usdt),
        "funding_status": (
            "UNKNOWN_NOT_IN_V1_PNL"
            if funding_usdt is None
            else FUNDING_PROXY_STATUS
        ),
        "funding_model_boundary": (
            "MISSING_NOT_ZERO"
            if funding_usdt is None
            else "REALIZED_PUBLIC_RATE_TIMES_OPEN_QUANTITY_TIMES_LATEST_CLOSED_15M_TRADE_PRICE_PROXY;NOT_TRUE_SETTLEMENT_MARK"
        ),
        "net_pnl_before_unknown_funding_usdt": canonical_decimal(snapshot.net_pnl),
        "equity_before_unknown_funding_usdt": canonical_decimal(snapshot.equity),
        "net_pnl_after_observed_funding_usdt": (
            None if adjusted_net is None else canonical_decimal(adjusted_net)
        ),
        "equity_after_observed_funding_usdt": (
            None if adjusted_equity is None else canonical_decimal(adjusted_equity)
        ),
        "gross_notional_usdt": canonical_decimal(snapshot.gross_notional),
        "open_risk_to_stop_usdt": (
            None
            if snapshot.open_risk_to_stop is None
            else canonical_decimal(
                snapshot.open_risk_to_stop
                if cost_aware_open_risk_usdt is None
                else cost_aware_open_risk_usdt
            )
        ),
        "open_risk_semantics": (
            "ENTRY_TO_REGISTERED_STOP_WITHOUT_EXECUTION_COST_LEGACY"
            if cost_aware_open_risk_usdt is None
            else "CURRENT_MARK_TO_SLIPPAGE_ADJUSTED_STOP_PLUS_EXIT_FEE"
        ),
        "unprotected_lot_ids": list(snapshot.unprotected_lot_ids),
    }


def _fill_fee(quantity: Decimal, price: Decimal, fee_rate: Decimal) -> Decimal:
    return quantity * price * fee_rate


def _market_fill(mark: Decimal, side: LotSide, *, opening: bool, bps: Decimal) -> Decimal:
    direction = ONE if side is LotSide.LONG else -ONE
    if not opening:
        direction = -direction
    return mark * (ONE + direction * bps / Decimal("10000"))


def _stop_fill(stop: Decimal, side: LotSide, bps: Decimal) -> Decimal:
    direction = -ONE if side is LotSide.LONG else ONE
    return stop * (ONE + direction * bps / Decimal("10000"))


def _close_quantity(
    portfolio: PortfolioState,
    *,
    lot: OfflineLot,
    quantity: Decimal,
    price: Decimal,
    fee_rate: Decimal,
    occurred_at: datetime,
    reason: str,
    fill_id: str,
) -> PortfolioState:
    return close_lot(
        portfolio,
        lot_id=lot.lot_id,
        quantity=quantity,
        fill_price=price,
        fee=_fill_fee(quantity, price, fee_rate),
        occurred_at=occurred_at,
        reason=reason,
        fill_id=fill_id,
    )


def _new_reentry_obligation(
    *,
    episode: Mapping[str, Any],
    symbol: str,
    exit_time: str,
    exit_price: Decimal,
    reason: str,
    next_review_at: str,
) -> dict[str, Any]:
    return self_digest(
        {
            "contract_id": f"{episode['episode_id']}:reentry:{exit_time}",
            "episode_id": episode["episode_id"],
            "symbol": symbol,
            "status": "PENDING_AGENT_REVIEW",
            "created_at": exit_time,
            "exit_price": canonical_decimal(exit_price),
            "exit_reason": reason,
            "thesis_status_at_exit": episode["strategic_status"],
            "required_review_at": next_review_at,
            "evidence_to_reenter": [],
            "evidence_to_cancel": list(episode.get("hard_invalidators", [])),
            "last_review_at": None,
            "resolution": None,
        },
        "reentry_digest",
    )


def _bar_touches_stop(lot: OfflineLot, low: Decimal, high: Decimal) -> bool:
    if lot.stop_price is None:
        return False
    return low <= lot.stop_price if lot.side is LotSide.LONG else high >= lot.stop_price


def _bar_touches_target(lot: OfflineLot, low: Decimal, high: Decimal) -> bool:
    if lot.target_price is None:
        return False
    return high >= lot.target_price if lot.side is LotSide.LONG else low <= lot.target_price


def _bar_touches_checkpoint(lot: OfflineLot, checkpoint: Decimal, low: Decimal, high: Decimal) -> bool:
    return high >= checkpoint if lot.side is LotSide.LONG else low <= checkpoint


def _next_review_at(context: Mapping[str, Any]) -> str:
    return _iso(_ts(str(context["decision_at"])) + timedelta(hours=1))


def _apply_due_funding(
    portfolio: PortfolioState,
    *,
    symbol: str,
    funding_events: Sequence[Mapping[str, Any]],
    through: datetime,
    decision_at: datetime,
    processed_ids: set[str],
    cumulative_funding: Decimal | None,
) -> tuple[Decimal | None, list[dict[str, Any]]]:
    """Apply newly visible settlements to lots open at the settlement instant."""

    emitted: list[dict[str, Any]] = []
    for event in sorted(funding_events, key=lambda item: int(item["funding_time_ms"])):
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in processed_ids:
            continue
        event_time = _ts(str(event.get("funding_time")))
        available_at = _ts(str(event.get("available_at")))
        if event_time > through or available_at > decision_at:
            continue
        rate = _d(event.get("funding_rate"), "FUNDING_EVENT_INVALID")
        mark = _d(
            event.get("settlement_price_proxy", event.get("settlement_mark_proxy")),
            "FUNDING_EVENT_INVALID",
        )
        if cumulative_funding is None:
            raise SingleAgentResearchError("FUNDING_STATUS_CONFLICT")
        event_amount = ZERO
        lot_rows: list[dict[str, Any]] = []
        for lot in sorted(_open_lots(portfolio, symbol), key=lambda item: item.lot_id):
            if lot.opened_at > event_time:
                continue
            direction = ONE if lot.side is LotSide.LONG else -ONE
            amount = -direction * lot.remaining_quantity * lot.contract_multiplier * mark * rate
            event_amount += amount
            lot_rows.append(
                {
                    "lot_id": lot.lot_id,
                    "side": lot.side.value,
                    "quantity": canonical_decimal(lot.remaining_quantity),
                    "funding_usdt": canonical_decimal(amount),
                }
            )
        cumulative_funding += event_amount
        processed_ids.add(event_id)
        emitted.append(
            {
                "event_type": "FUNDING_PROXY_ACCRUAL_APPLIED",
                "event_id": event_id,
                "symbol": symbol,
                "occurred_at": _iso(event_time),
                "available_at": _iso(available_at),
                "funding_rate": canonical_decimal(rate),
                "settlement_price_proxy": canonical_decimal(mark),
                "funding_usdt": canonical_decimal(event_amount),
                "lots": lot_rows,
                "source": event.get("source"),
                "price_proxy_basis": event.get(
                    "settlement_price_basis", event.get("settlement_mark_basis")
                ),
                "model_boundary": "NOT_TRUE_VENUE_SETTLEMENT_MARK_OR_ACCOUNT_CASHFLOW",
            }
        )
    return cumulative_funding, emitted


def _process_bars(
    state: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    policy: Mapping[str, Decimal],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replay every newly closed 15-minute bar; stop wins same-bar ambiguity."""

    current = copy.deepcopy(dict(state))
    portfolio = _portfolio_from_document(current["portfolio"])
    lot_contracts = copy.deepcopy(dict(current["lot_contracts"]))
    episodes = copy.deepcopy(dict(current["episodes"]))
    orders = copy.deepcopy(list(current["orders"]))
    processed = copy.deepcopy(dict(current["processed_15m_close_time_ms"]))
    target_events = copy.deepcopy(list(current["target_events"]))
    processed_funding_ids = set(current.get("processed_funding_event_ids", []))
    cumulative_funding = (
        None
        if current.get("funding_usdt") is None
        else _d(current.get("funding_usdt"), "STATE_FUNDING_INVALID")
    )
    events: list[dict[str, Any]] = []
    decision_at = _ts(str(context["decision_at"]))

    for symbol in SYMBOLS:
        cutoff = int(processed.get(symbol, 0))
        rows = context["symbols"][symbol]["execution_bars_15m"]
        funding_rows = context["symbols"][symbol].get("funding_events", [])
        if not isinstance(funding_rows, list):
            raise SingleAgentResearchError("FUNDING_EVENTS_INVALID")
        bars = sorted(
            (
                row
                for row in rows
                if int(row["close_time_ms"]) > cutoff
                and _ts(str(row["available_at"])) <= decision_at
            ),
            key=lambda row: int(row["close_time_ms"]),
        )
        for bar in bars:
            bar_open = _ts(str(bar["open_time"]))
            bar_close = _ts(str(bar["available_at"]))
            if cumulative_funding is not None:
                cumulative_funding, funding_events = _apply_due_funding(
                    portfolio,
                    symbol=symbol,
                    funding_events=funding_rows,
                    through=bar_close,
                    decision_at=decision_at,
                    processed_ids=processed_funding_ids,
                    cumulative_funding=cumulative_funding,
                )
                events.extend(funding_events)
            low = _d(bar["low"], "BAR_VALUE_INVALID")
            high = _d(bar["high"], "BAR_VALUE_INVALID")
            open_price = _d(bar["open"], "BAR_VALUE_INVALID")

            for lot in sorted(_open_lots(portfolio, symbol), key=lambda item: item.lot_id):
                contract = lot_contracts.get(lot.lot_id, {})
                active_from_value = contract.get("protection_active_from")
                if not active_from_value or bar_open < _ts(str(active_from_value)):
                    continue
                if _bar_touches_stop(lot, low, high):
                    stop = lot.stop_price
                    assert stop is not None
                    reference = (
                        min(stop, open_price) if lot.side is LotSide.LONG else max(stop, open_price)
                    )
                    price = _stop_fill(reference, lot.side, policy["stop_slippage_bps"])
                    portfolio = _close_quantity(
                        portfolio,
                        lot=lot,
                        quantity=lot.remaining_quantity,
                        price=price,
                        fee_rate=policy["taker_fee_rate"],
                        occurred_at=bar_close,
                        reason="PROTECTIVE_STOP_15M_STOP_FIRST",
                        fill_id=f"{bar['bar_id']}:{lot.lot_id}:stop",
                    )
                    events.append(
                        {
                            "event_type": "PROTECTIVE_STOP_FILLED",
                            "symbol": symbol,
                            "lot_id": lot.lot_id,
                            "bar_id": bar["bar_id"],
                            "occurred_at": _iso(bar_close),
                            "fill_price": canonical_decimal(price),
                            "same_bar_priority": "STOP_FIRST",
                        }
                    )
                    episode = episodes.get(symbol)
                    if (
                        lot.role is LotRole.CORE
                        and isinstance(episode, Mapping)
                        and episode.get("strategic_status") in {"ACTIVE", "CHALLENGED"}
                        and not any(item.role is LotRole.CORE for item in _open_lots(portfolio, symbol))
                    ):
                        updated = copy.deepcopy(dict(episode))
                        updated["reentry_contract"] = _new_reentry_obligation(
                            episode=episode,
                            symbol=symbol,
                            exit_time=_iso(bar_close),
                            exit_price=price,
                            reason="PROTECTIVE_STOP_FILLED_STRATEGIC_THESIS_NOT_INVALIDATED",
                            next_review_at=_next_review_at(context),
                        )
                        updated["exposure_status"] = "FLAT_REENTRY_PENDING"
                        updated["revision"] = int(updated["revision"]) + 1
                        updated["previous_episode_digest"] = episode["episode_digest"]
                        updated.pop("episode_digest", None)
                        episodes[symbol] = self_digest(updated, "episode_digest")
                    continue
                if lot.role is LotRole.TACTICAL and _bar_touches_target(lot, low, high):
                    target = lot.target_price
                    assert target is not None
                    portfolio = _close_quantity(
                        portfolio,
                        lot=lot,
                        quantity=lot.remaining_quantity,
                        price=target,
                        fee_rate=policy["maker_fee_rate"],
                        occurred_at=bar_close,
                        reason="TACTICAL_TARGET_LIMIT_15M",
                        fill_id=f"{bar['bar_id']}:{lot.lot_id}:target",
                    )
                    events.append(
                        {
                            "event_type": "TACTICAL_TARGET_FILLED",
                            "symbol": symbol,
                            "lot_id": lot.lot_id,
                            "bar_id": bar["bar_id"],
                            "occurred_at": _iso(bar_close),
                            "fill_price": canonical_decimal(target),
                        }
                    )
                    continue
                checkpoint_value = contract.get("management_checkpoint")
                checkpoint_id = contract.get("management_checkpoint_id")
                emitted = set(contract.get("checkpoint_event_ids", []))
                if (
                    lot.role is LotRole.CORE
                    and checkpoint_value is not None
                    and checkpoint_id
                    and checkpoint_id not in emitted
                    and _bar_touches_checkpoint(
                        lot, _d(checkpoint_value, "LOT_CONTRACT_INVALID"), low, high
                    )
                ):
                    event_id = f"{bar['bar_id']}:{lot.lot_id}:{checkpoint_id}"
                    event = {
                        "event_id": event_id,
                        "event_type": "CORE_MANAGEMENT_CHECKPOINT_REACHED",
                        "symbol": symbol,
                        "lot_id": lot.lot_id,
                        "episode_id": lot.episode_id,
                        "management_checkpoint_id": checkpoint_id,
                        "management_checkpoint": checkpoint_value,
                        "occurred_at": _iso(bar_close),
                        "bar_id": bar["bar_id"],
                        "automatic_exit": False,
                    }
                    target_events.append(event)
                    events.append(event)
                    contract.setdefault("checkpoint_event_ids", []).append(checkpoint_id)
                    lot_contracts[lot.lot_id] = contract

            for order in sorted(orders, key=lambda item: item["order_id"]):
                if order["symbol"] != symbol or order["status"] != "ACTIVE":
                    continue
                if not order.get("active_from") or bar_open < _ts(str(order["active_from"])):
                    continue
                limit = _d(order["limit_price"], "ORDER_INVALID")
                touched = low <= limit if order["side"] == "BUY" else high >= limit
                if not touched:
                    continue
                if order["side"] == "BUY":
                    role = LotRole(str(order["role"]))
                    notional = _d(order["notional_usdt"], "ORDER_INVALID")
                    lot_id = f"{state['run_id']}:order-fill:{order['order_id']}"
                    target = (
                        _d(order["target_price"], "ORDER_INVALID")
                        if role is LotRole.TACTICAL
                        else None
                    )
                    lot = OfflineLot(
                        lot_id=lot_id,
                        instrument_id=symbol,
                        side=LotSide.LONG,
                        role=role,
                        attribution=Attribution.STRATEGY,
                        quantity=notional / limit,
                        remaining_quantity=notional / limit,
                        entry_price=limit,
                        stop_price=_d(order["stop_price"], "ORDER_INVALID"),
                        target_price=target,
                        opened_at=bar_close,
                        episode_id=str(order["episode_id"]),
                        stage_id=f"{order['episode_id']}:order:{order['order_id']}",
                        geometry_id=str(order["geometry_id"]),
                    )
                    portfolio = open_lot(
                        portfolio,
                        lot=lot,
                        fee_rate=policy["maker_fee_rate"],
                        fill_id=f"{bar['bar_id']}:{order['order_id']}:entry",
                        charge_entry_fee=True,
                    )
                    lot_contracts[lot_id] = {
                        "lot_id": lot_id,
                        "episode_id": lot.episode_id,
                        "role": role.value,
                        "exit_intent": "TACTICAL_TARGET" if role is LotRole.TACTICAL else "CORE_DYNAMIC_MANAGEMENT",
                        "risk_budget_usdt": order.get("risk_budget_usdt"),
                        "management_checkpoint": order.get("management_checkpoint"),
                        "management_checkpoint_id": order.get("management_checkpoint_id"),
                        "max_horizon_at": order.get("max_horizon_at"),
                        "protection_active_from": _iso(bar_close),
                        "geometry_id": lot.geometry_id,
                        "checkpoint_event_ids": [],
                    }
                else:
                    remaining = _d(order["notional_usdt"], "ORDER_INVALID")
                    for lot in sorted(_open_lots(portfolio, symbol), key=lambda item: item.lot_id):
                        quantity = min(lot.remaining_quantity, remaining / limit)
                        if quantity <= ZERO:
                            continue
                        portfolio = _close_quantity(
                            portfolio,
                            lot=lot,
                            quantity=quantity,
                            price=limit,
                            fee_rate=policy["maker_fee_rate"],
                            occurred_at=bar_close,
                            reason="ACTIVATED_REDUCE_LIMIT",
                            fill_id=f"{bar['bar_id']}:{order['order_id']}:{lot.lot_id}",
                        )
                        remaining -= quantity * limit
                        if remaining <= ZERO:
                            break
                order["status"] = "FILLED"
                order["filled_at"] = _iso(bar_close)
                events.append(
                    {
                        "event_type": "ACTIVATED_ORDER_FILLED",
                        "order_id": order["order_id"],
                        "symbol": symbol,
                        "occurred_at": _iso(bar_close),
                        "fill_price": canonical_decimal(limit),
                    }
                )
            processed[symbol] = int(bar["close_time_ms"])
        if cumulative_funding is not None:
            cumulative_funding, funding_events = _apply_due_funding(
                portfolio,
                symbol=symbol,
                funding_events=funding_rows,
                through=decision_at,
                decision_at=decision_at,
                processed_ids=processed_funding_ids,
                cumulative_funding=cumulative_funding,
            )
            events.extend(funding_events)

        ticker_proxy = (
            context["symbols"][symbol]
            .get("market_proxies", {})
            .get("ticker_24h", {})
        )
        decision_trade_value = (
            ticker_proxy.get("last") if isinstance(ticker_proxy, Mapping) else None
        )
        if decision_trade_value is not None:
            decision_trade = _d(
                decision_trade_value, "DECISION_TRADE_PRICE_INVALID"
            )
            for lot in sorted(
                _open_lots(portfolio, symbol), key=lambda item: item.lot_id
            ):
                contract = lot_contracts.get(lot.lot_id, {})
                active_from_value = contract.get("protection_active_from")
                if (
                    not active_from_value
                    or _ts(str(active_from_value)) > decision_at
                ):
                    continue
                stop_crossed = lot.stop_price is not None and (
                    decision_trade <= lot.stop_price
                    if lot.side is LotSide.LONG
                    else decision_trade >= lot.stop_price
                )
                if stop_crossed:
                    assert lot.stop_price is not None
                    reference = (
                        min(lot.stop_price, decision_trade)
                        if lot.side is LotSide.LONG
                        else max(lot.stop_price, decision_trade)
                    )
                    price = _stop_fill(
                        reference, lot.side, policy["stop_slippage_bps"]
                    )
                    portfolio = _close_quantity(
                        portfolio,
                        lot=lot,
                        quantity=lot.remaining_quantity,
                        price=price,
                        fee_rate=policy["taker_fee_rate"],
                        occurred_at=decision_at,
                        reason="PROTECTIVE_STOP_VISIBLE_LAST_TRADE",
                        fill_id=f"decision:{context['cycle_index']}:{lot.lot_id}:stop",
                    )
                    events.append(
                        {
                            "event_type": "PROTECTIVE_STOP_FILLED",
                            "symbol": symbol,
                            "lot_id": lot.lot_id,
                            "occurred_at": _iso(decision_at),
                            "fill_price": canonical_decimal(price),
                            "trigger_source": "VISIBLE_PUBLIC_LAST_TRADE_AT_DECISION",
                        }
                    )
                    episode = episodes.get(symbol)
                    if (
                        lot.role is LotRole.CORE
                        and isinstance(episode, Mapping)
                        and episode.get("strategic_status")
                        in {"ACTIVE", "CHALLENGED"}
                        and not any(
                            item.role is LotRole.CORE
                            for item in _open_lots(portfolio, symbol)
                        )
                    ):
                        updated = copy.deepcopy(dict(episode))
                        updated["reentry_contract"] = _new_reentry_obligation(
                            episode=episode,
                            symbol=symbol,
                            exit_time=_iso(decision_at),
                            exit_price=price,
                            reason="PROTECTIVE_STOP_FILLED_STRATEGIC_THESIS_NOT_INVALIDATED",
                            next_review_at=_next_review_at(context),
                        )
                        updated["revision"] = int(updated["revision"]) + 1
                        updated["previous_episode_digest"] = episode[
                            "episode_digest"
                        ]
                        updated.pop("episode_digest", None)
                        episodes[symbol] = self_digest(
                            updated, "episode_digest"
                        )
                    continue
                target_crossed = (
                    lot.role is LotRole.TACTICAL
                    and lot.target_price is not None
                    and (
                        decision_trade >= lot.target_price
                        if lot.side is LotSide.LONG
                        else decision_trade <= lot.target_price
                    )
                )
                if target_crossed:
                    assert lot.target_price is not None
                    portfolio = _close_quantity(
                        portfolio,
                        lot=lot,
                        quantity=lot.remaining_quantity,
                        price=lot.target_price,
                        fee_rate=policy["maker_fee_rate"],
                        occurred_at=decision_at,
                        reason="TACTICAL_TARGET_VISIBLE_LAST_TRADE",
                        fill_id=f"decision:{context['cycle_index']}:{lot.lot_id}:target",
                    )
                    events.append(
                        {
                            "event_type": "TACTICAL_TARGET_FILLED",
                            "symbol": symbol,
                            "lot_id": lot.lot_id,
                            "occurred_at": _iso(decision_at),
                            "fill_price": canonical_decimal(lot.target_price),
                            "trigger_source": "VISIBLE_PUBLIC_LAST_TRADE_AT_DECISION",
                            "market_exit_after_trigger_forbidden": True,
                        }
                    )
                    continue
                checkpoint_value = contract.get("management_checkpoint")
                checkpoint_id = contract.get("management_checkpoint_id")
                emitted = set(contract.get("checkpoint_event_ids", []))
                if (
                    lot.role is LotRole.CORE
                    and checkpoint_value is not None
                    and checkpoint_id
                    and checkpoint_id not in emitted
                    and (
                        decision_trade
                        >= _d(checkpoint_value, "LOT_CONTRACT_INVALID")
                        if lot.side is LotSide.LONG
                        else decision_trade
                        <= _d(checkpoint_value, "LOT_CONTRACT_INVALID")
                    )
                ):
                    event = {
                        "event_id": f"decision:{context['cycle_index']}:{lot.lot_id}:{checkpoint_id}",
                        "event_type": "CORE_MANAGEMENT_CHECKPOINT_REACHED",
                        "symbol": symbol,
                        "lot_id": lot.lot_id,
                        "episode_id": lot.episode_id,
                        "management_checkpoint_id": checkpoint_id,
                        "management_checkpoint": checkpoint_value,
                        "occurred_at": _iso(decision_at),
                        "trigger_source": "VISIBLE_PUBLIC_LAST_TRADE_AT_DECISION",
                        "automatic_exit": False,
                    }
                    target_events.append(event)
                    events.append(event)
                    contract.setdefault("checkpoint_event_ids", []).append(
                        checkpoint_id
                    )
                    lot_contracts[lot.lot_id] = contract

    for symbol, episode in episodes.items():
        if isinstance(episode, Mapping):
            episodes[symbol] = _resolve_episode_exposure(
                episode,
                portfolio=portfolio,
                symbol=symbol,
                decision_at=str(context["decision_at"]),
                wait_actions=(),
            )

    current["portfolio"] = _portfolio_document(portfolio)
    current["lot_contracts"] = lot_contracts
    current["episodes"] = episodes
    current["orders"] = orders
    current["processed_15m_close_time_ms"] = processed
    current["target_events"] = target_events
    current["processed_funding_event_ids"] = sorted(processed_funding_ids)
    if cumulative_funding is not None:
        current["funding_usdt"] = canonical_decimal(cumulative_funding)
    current.pop("state_digest", None)
    return current, events


def _compact_market_for_agent(context: Mapping[str, Any]) -> dict[str, Any]:
    compact = copy.deepcopy(dict(context))
    for symbol in SYMBOLS:
        row = compact["symbols"][symbol]
        row.pop("execution_bars_15m", None)
        row["evidence_catalog"] = [
            {
                "evidence_ref": evidence["evidence_ref"],
                "available_at": evidence["available_at"],
                "source": evidence["source"],
                "source_version": evidence["source_version"],
                "dependency_group": evidence["dependency_group"],
                "limitation": evidence["limitation"],
            }
            for evidence in row["evidence_catalog"]
        ]
        row["evidence_catalog_boundary"] = (
            "METADATA_BINDS_TO_THE_FULL_FROZEN_CONTEXT; DEPENDENCY_GROUP_IS_AUTHORITATIVE_FOR_DEDUP; "
            "TECHNICALS_ARE_DERIVED_OBSERVATIONS, MARKET_FIELDS_ARE_SNAPSHOTS_OR_PROXIES, "
            "AND_NEWS_IS_HEADLINE_METADATA"
        )
        keep_by_timeframe = {"15m": 12, "1h": 12, "4h": 8, "1d": 8, "1w": 6}
        row["recent_closed_bars"] = {
            timeframe: bars[-keep_by_timeframe[timeframe] :]
            for timeframe, bars in row["recent_closed_bars"].items()
        }
    compact.pop("context_digest", None)
    return compact


def _risk_summary(
    portfolio: PortfolioState,
    *,
    marks: Mapping[str, Decimal],
    marked_at: datetime,
    state: Mapping[str, Any],
    policy: Mapping[str, Decimal],
) -> dict[str, Any]:
    snapshot = mark_portfolio(portfolio, marks=dict(marks), marked_at=marked_at)
    funding = (
        None
        if state.get("funding_usdt") is None
        else _d(state.get("funding_usdt"), "STATE_FUNDING_INVALID")
    )
    effective_equity = snapshot.equity if funding is None else snapshot.equity + funding
    risk_cap_equity = min(effective_equity, portfolio.initial_equity)
    peak = _d(state["peak_equity_usdt"], "STATE_EQUITY_INVALID")
    drawdown = ZERO if peak <= ZERO else max(ZERO, (peak - effective_equity) / peak)
    portfolio_risk, symbol_risk = _current_open_risk(
        portfolio, marks=marks, policy=policy
    )
    return {
        "snapshot": _snapshot_document(
            snapshot,
            funding_usdt=funding,
            cost_aware_open_risk_usdt=portfolio_risk,
        ),
        "risk_cap_equity_usdt": canonical_decimal(risk_cap_equity),
        "drawdown_fraction": canonical_decimal(drawdown),
        "new_risk_allowed_by_drawdown": drawdown < policy["drawdown_fraction"],
        "unprotected_lot_ids": list(snapshot.unprotected_lot_ids),
        "portfolio_open_risk_usdt": canonical_decimal(portfolio_risk),
        "portfolio_risk_cap_usdt": canonical_decimal(risk_cap_equity * policy["portfolio_risk_fraction"]),
        "symbol_open_risk_usdt": {
            symbol: canonical_decimal(symbol_risk[symbol]) for symbol in SYMBOLS
        },
        "symbol_risk_cap_usdt": canonical_decimal(risk_cap_equity * policy["symbol_risk_fraction"]),
        "gross_cap_usdt": canonical_decimal(effective_equity * policy["gross_multiple"]),
        "symbol_notional_cap_usdt": canonical_decimal(effective_equity * policy["symbol_notional_fraction"]),
        "open_risk_semantics": "CURRENT_MARK_TO_SLIPPAGE_ADJUSTED_STOP_PLUS_EXIT_FEE",
        "boundary": "RISK_KERNEL_MAY_VETO_BUT_DOES_NOT_PRESELECT_OR_DELETE_ACTIONS",
    }


def _action_position_truth(
    agent_context: Mapping[str, Any], *, symbol: str
) -> dict[str, Any]:
    """Build the only authoritative position facts used by action counterfactuals."""

    accepted = agent_context.get("accepted_strategy_state")
    market = agent_context.get("market")
    if not isinstance(accepted, Mapping) or not isinstance(market, Mapping):
        raise SingleAgentResearchError("ACTION_POSITION_TRUTH_CONTEXT_INVALID")
    portfolio = accepted.get("portfolio")
    risk = accepted.get("risk")
    market_symbols = market.get("symbols")
    if (
        not isinstance(portfolio, Mapping)
        or not isinstance(risk, Mapping)
        or not isinstance(market_symbols, Mapping)
        or not isinstance(market_symbols.get(symbol), Mapping)
    ):
        raise SingleAgentResearchError("ACTION_POSITION_TRUTH_CONTEXT_INVALID")
    mark = _d(market_symbols[symbol].get("mark"), "ACTION_POSITION_TRUTH_MARK_INVALID")
    if mark <= ZERO:
        raise SingleAgentResearchError("ACTION_POSITION_TRUTH_MARK_INVALID")
    lots = portfolio.get("lots")
    if not isinstance(lots, list):
        raise SingleAgentResearchError("ACTION_POSITION_TRUTH_LOTS_INVALID")
    open_lots: list[dict[str, Any]] = []
    gross_quantity = ZERO
    mark_notional = ZERO
    for raw_lot in lots:
        if not isinstance(raw_lot, Mapping) or raw_lot.get("instrument_id") != symbol:
            continue
        remaining = _d(
            raw_lot.get("remaining_quantity"), "ACTION_POSITION_TRUTH_LOTS_INVALID"
        )
        if remaining <= ZERO:
            continue
        multiplier = _d(
            raw_lot.get("contract_multiplier", "1"),
            "ACTION_POSITION_TRUTH_LOTS_INVALID",
        )
        if multiplier <= ZERO:
            raise SingleAgentResearchError("ACTION_POSITION_TRUTH_LOTS_INVALID")
        lot_notional = remaining * multiplier * mark
        gross_quantity += remaining
        mark_notional += lot_notional
        open_lots.append(
            {
                "lot_id": str(raw_lot.get("lot_id") or ""),
                "role": str(raw_lot.get("role") or ""),
                "side": str(raw_lot.get("side") or ""),
                "remaining_quantity": canonical_decimal(remaining),
                "contract_multiplier": canonical_decimal(multiplier),
                "mark_notional_usdt": canonical_decimal(lot_notional),
                "stop_price": raw_lot.get("stop_price"),
            }
        )
    symbol_risk = risk.get("symbol_open_risk_usdt")
    if not isinstance(symbol_risk, Mapping) or symbol not in symbol_risk:
        raise SingleAgentResearchError("ACTION_POSITION_TRUTH_RISK_INVALID")
    open_risk = _d(
        symbol_risk[symbol], "ACTION_POSITION_TRUTH_RISK_INVALID"
    )
    if open_risk < ZERO:
        raise SingleAgentResearchError("ACTION_POSITION_TRUTH_RISK_INVALID")
    truth = {
        "schema_id": "action_position_truth",
        "schema_version": "1.0.0",
        "cycle_index": int(agent_context.get("cycle_index", 0)),
        "pre_decision_state_digest": str(
            agent_context.get("pre_decision_state_digest") or ""
        ),
        "symbol": symbol,
        "mark_price": canonical_decimal(mark),
        "open_lots": sorted(open_lots, key=lambda row: row["lot_id"]),
        "gross_remaining_quantity": canonical_decimal(gross_quantity),
        "mark_notional_usdt": canonical_decimal(mark_notional),
        "mark_to_stop_open_risk_usdt": canonical_decimal(open_risk),
        "truth_boundary": "DETERMINISTIC_PRE_DECISION_STATE_PLUS_CURRENT_MARK;NARRATIVE_MUST_NOT_DUPLICATE_NUMERIC_POSITION_FACTS",
    }
    return self_digest(truth, "position_truth_digest")


def _reject_unstructured_position_truth(*narratives: str) -> None:
    joined = " ".join(narratives)
    position_metric_claims = (
        r"mark\s*名义\s*[=:：]?\s*[+-]?\d",
        r"mark[ _-]*notional\s*[=:：]?\s*[+-]?\d",
        r"open[ _-]*risk\s*[=:：]?\s*[+-]?\d",
        r"remaining[ _-]*quantity\s*[=:：]?\s*[+-]?\d",
        r"(?:CORE|TACTICAL|HEDGE)\s*[=:：]?\s*[+-]?\d",
    )
    if any(re.search(pattern, joined, flags=re.IGNORECASE) for pattern in position_metric_claims):
        raise SingleAgentResearchError(
            "ACTION_COUNTERFACTUAL_UNSTRUCTURED_POSITION_TRUTH"
        )


def _agent_decision_contract() -> dict[str, Any]:
    return {
        "top_level": {
            "required_fields": [
                "schema_id",
                "schema_version",
                "run_id",
                "cycle_index",
                "decision_at",
                "agent_context_digest",
                "pre_decision_state_digest",
                "strategy_playbook_sha256",
                "evidence_label",
                "symbol_decisions",
                "portfolio_rationale",
                "agent_attestation",
            ],
            "schema_id": "single_strategy_agent_decision",
            "schema_version": AGENT_DECISION_SCHEMA_VERSION,
        },
        "episode_transition": {
            "allowed_operations": [
                "OPEN",
                "UPDATE",
                "CHALLENGE",
                "INVALIDATE",
                "CLOSE",
                "REPLACE",
            ],
            "allowed_strategic_statuses": [
                "ACTIVE",
                "CHALLENGED",
                "INVALIDATED",
                "CLOSED",
            ],
            "genesis_without_previous_episode": "Use OPEN with a new episode_id; OPEN is required even for a flat watch episode.",
            "existing_episode": "Keep the same episode_id and use UPDATE, CHALLENGE, INVALIDATE, or CLOSE.",
            "replacement": "Use REPLACE with a new episode_id only after the prior episode is INVALIDATED or CLOSED.",
            "operation_status_pairs": {
                "OPEN": ["ACTIVE", "CHALLENGED"],
                "UPDATE": ["ACTIVE", "CHALLENGED", "INVALIDATED", "CLOSED"],
                "CHALLENGE": ["CHALLENGED"],
                "INVALIDATE": ["INVALIDATED"],
                "CLOSE": ["CLOSED"],
                "REPLACE": ["ACTIVE", "CHALLENGED"],
            },
            "literal_boundary": "CREATE_IS_NOT_A_VALID_OPERATION_LITERAL",
        },
        "path_card": {
            "required_fields": [
                "path_id",
                "path_class",
                "mechanism_ids",
                "support_level",
                "confidence",
                "theory_source_refs",
                "thesis",
                "horizon",
                "observed_prefix",
                "evidence_for_refs",
                "evidence_against_refs",
                "next_support_observations",
                "soft_contradictions",
                "hard_falsifiers",
                "expiry_at",
                "favorable_path",
                "adverse_path",
                "normal_path_variation",
                "data_gaps",
                "what_changed",
                "limitations",
            ],
            "required_classes": [
                item for item in PATH_CLASS_ORDER if item in REQUIRED_PATH_CLASSES
            ],
            "optional_classes": [
                item for item in PATH_CLASS_ORDER if item in OPTIONAL_PATH_CLASSES
            ],
            "allowed_mechanism_ids": sorted(MECHANISM_IDS),
            "identity_rule": "Retain the prior path_id for every surviving path_class.",
            "support_rule": "Primitive mechanisms may coexist. support_level is ordinal and must never be normalized or interpreted as a mixture weight.",
            "numeric_probability_rule": "probability_pct, sum-to-100, top-path probability, margin, entropy, and EV are forbidden because this contract has no registered partition proof or calibration authority.",
        },
        "evidence_ledger": {
            "location": "symbol_decision.strategic_assessment.evidence_ledger",
            "exact_fields": [
                "evidence_id",
                "available_at",
                "perspective_id",
                "dependency_group",
                "target_ids",
                "direction",
                "ordinal_strength",
                "quality",
                "source_version",
            ],
            "allowed_perspectives": sorted(EVIDENCE_PERSPECTIVES),
            "allowed_directions": sorted(EVIDENCE_DIRECTIONS),
            "allowed_strengths": sorted(ORDINAL_STRENGTHS),
            "quality": "VALID",
            "aggregation": "FOR_EACH_TARGET_AND_DEPENDENCY_GROUP_KEEP_MAX_ABSOLUTE_STRENGTH_WITH_STABLE_EVIDENCE_ID_TIE_BREAK",
        },
        "analysis_trace": {
            "location": "symbol_decision.analysis_trace",
            "required_epistemic_types": [
                "OBSERVATION_OR_DERIVED_MEASURE",
                "INFERENCE",
                "HYPOTHESIS",
                "POLICY",
            ],
            "required_fields": [
                "trace_id",
                "epistemic_type",
                "statement",
                "evidence_refs",
                "theory_source_refs",
                "limitation",
            ],
            "allowed_epistemic_types": sorted(EPISTEMIC_TYPES),
        },
        "dynamic_update": {
            "required_field": "dynamic_update_from_cycle_index",
            "binding_rule": "Must equal current cycle_index minus one. The free-text summary may only use that prior-cycle label; prefer '上一 accepted cycle' wording.",
        },
        "strategic_selection": {
            "required_fields": [
                "operational_lead_path_id",
                "runner_up_path_id",
                "path_selection_rationale",
                "ranking_uncertainty",
                "support_boundary",
                "competition_set_status",
                "active_primitive_mechanism_ids",
                "switch_conditions",
            ],
            "competition_set_status": "UNKNOWN_NO_VALID_COMPETITION_SET",
            "lead_boundary": "Operational lead and runner-up are action-ordering judgments, not normalized path probabilities or calibrated top-path claims.",
            "invalidation_rule": "INVALIDATE additionally requires invalidation_basis.matched_prior_hard_invalidator, invalidated_prior_premise, and current evidence_refs.",
            "genesis_rule": "An undeclared exogenous thesis is a governance gap, not a hard falsifier.",
        },
        "observation_request": {
            "location": "symbol_decision.evidence_update.observation_requests",
            "required_fields": [
                "request_id",
                "observation",
                "purpose_path_ids",
                "timeframe",
                "premise",
                "source_preference",
                "cost_tier",
                "status",
                "evidence_refs",
                "resolution_note",
                "limitation",
            ],
            "statuses": sorted(OBSERVATION_REQUEST_STATUSES),
            "source_preferences": sorted(OBSERVATION_SOURCE_PREFERENCES),
            "pending_rule": "Every prior PENDING request must be carried forward until fulfilled, unavailable, or explicitly dropped for no incremental value.",
        },
        "action_comparison": {
            "required_classes": sorted(COMPARISON_CLASSES),
            "required_fields": [
                "action_class",
                "feasible",
                "relative_utility",
                "reason",
                "path_conditioned_outcomes",
                "hard_vetoes",
            ],
            "path_conditioned_outcome_fields": [
                "path_id",
                "position_effect",
                "compatibility",
                "position_truth_digest",
                "path_realization",
                "failure_process",
                "opportunity_cost",
                "cost_and_risk",
            ],
            "coverage_rule": "Every action compares the operational lead, runner-up, and OTHER_OR_UNKNOWN residual with action-specific counterfactual text.",
            "position_truth_rule": "Every outcome must reference the exact deterministic per-symbol position_truth_digest. Numeric lot quantity, mark notional, and open-risk claims are forbidden in narrative fields so stale prose cannot conflict with pre-state truth.",
        },
        "allowed_action_types": sorted(ACTION_TYPES),
        "required_evidence_label": AGENT_JUDGMENT_EVIDENCE_LABEL,
        "boundary": "OUTPUT_INTERFACE_ONLY_DOES_NOT_PRESELECT_ANALYSIS_PATH_OR_ACTION",
    }


def open_research_cycle(*, run_root: Path, cycle_index: int) -> dict[str, Any]:
    root, manifest, checkpoint = _run_documents(run_root)
    if checkpoint.get("status") not in {"PREPARED_OUTCOMES_SEALED", "RUNNING_OUTCOMES_SEALED"}:
        raise SingleAgentResearchError("RUN_NOT_OPENABLE")
    if int(checkpoint.get("next_cycle_index", 0)) != cycle_index or not 1 <= cycle_index <= 24:
        raise SingleAgentResearchError("CYCLE_ORDER_INVALID")
    if checkpoint.get("pending_agent_context_path") is not None:
        raise SingleAgentResearchError("PENDING_CYCLE_ALREADY_OPEN")
    state_path = root / str(checkpoint["accepted_state_path"])
    state = _load_verified(state_path, "state_digest")
    if state["state_digest"] != checkpoint["accepted_state_digest"]:
        raise SingleAgentResearchError("CHECKPOINT_STATE_MISMATCH")
    context = _load_verified(
        root / "market-contexts" / f"cycle-{cycle_index:04d}.json", "context_digest"
    )
    policy = _risk_policy(manifest)
    pre, events = _process_bars(state, context, policy=policy)
    portfolio = _portfolio_from_document(pre["portfolio"])
    marks = _marks(context)
    risk = _risk_summary(
        portfolio,
        marks=marks,
        marked_at=_ts(str(context["decision_at"])),
        state=pre,
        policy=policy,
    )
    pre["revision"] = int(state["revision"]) + 1
    pre["previous_state_digest"] = state["state_digest"]
    pre["accepted_at"] = str(context["decision_at"])
    pre["state_stage"] = "PRE_DECISION_AFTER_BAR_REPLAY"
    pre["cycle_index"] = cycle_index
    pre["bar_replay_events"] = events
    pre["risk_snapshot"] = risk
    pre = self_digest(pre, "state_digest")
    pre_path = root / "pre-decision-states" / f"cycle-{cycle_index:04d}.json"
    write_once_json(pre_path, pre)
    agent_context_document = {
            "schema_id": "single_strategy_agent_context",
            "schema_version": AGENT_DECISION_SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "cycle_index": cycle_index,
            "decision_at": context["decision_at"],
            "prior_accepted_state_digest": state["state_digest"],
            "pre_decision_state_digest": pre["state_digest"],
            "market_context_digest": context["context_digest"],
            "market": _compact_market_for_agent(context),
            "accepted_strategy_state": {
                "episodes": pre["episodes"],
                "portfolio": pre["portfolio"],
                "lot_contracts": pre["lot_contracts"],
                "orders": pre["orders"],
                "target_events": pre["target_events"],
                "bar_replay_events": events,
                "risk": risk,
            },
            "strategy_playbook": manifest["strategy_playbook"],
            "agent_task": {
                "objective": "Update the prior strategic state using only new point-in-time evidence, analyze market emotion and all competing paths, compare all feasible position actions, then choose actions without treating flat exposure as free.",
                "required_path_classes": [
                    item for item in PATH_CLASS_ORDER if item in REQUIRED_PATH_CLASSES
                ],
                "optional_path_classes": [
                    item for item in PATH_CLASS_ORDER if item in OPTIONAL_PATH_CLASSES
                ],
                "allowed_mechanism_ids": sorted(MECHANISM_IDS),
                "required_action_comparison_classes": sorted(COMPARISON_CLASSES),
                "required_sentiment_dimensions": [
                    "price_and_flow_emotion",
                    "leverage_and_crowding",
                    "public_event_narrative",
                    "cross_market_risk_appetite",
                ],
                "theory_source_catalog": [
                    {
                        "source_ref": "CORE_V2_1:2.1-2.3_EPISTEMIC_AND_PIT",
                        "document": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
                        "sections": ["2.1 强制标签", "2.2 唯一合法的推理链", "2.3 点时信息集"],
                    },
                    {
                        "source_ref": "CORE_V2_1:4_OBSERVABILITY_BOUNDARIES",
                        "document": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
                        "sections": ["4. 可观测性与不可识别边界"],
                    },
                    {
                        "source_ref": "CORE_V2_1:5_DLCFRK_STATE",
                        "document": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
                        "sections": ["5. 五因子状态条件理论"],
                    },
                    {
                        "source_ref": "CORE_V2_1:6-8_EPISODE_EV_POSITION",
                        "document": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
                        "sections": ["6. 时间、空间与 episode", "7. 状态演化", "8. 预测目标、EV 与行动"],
                    },
                    {
                        "source_ref": "CORE_V2_1:16_DYNAMIC_COMPETING_PATHS",
                        "document": "archive/authority/CORE_TRADING_THEORY_v2_1.md",
                        "sections": ["16. 通用多视角竞争机制—动态路径方法论"],
                    },
                    {
                        "source_ref": "FORMALIZATION_AUDIT:3.1-3.11_CONTINUITY",
                        "document": "archive/docs/reviews/THEORY_AGENT_V2_THEORY_FORMALIZATION_AUDIT_v0_1.md",
                        "sections": ["3.1 趋势延续", "3.3 target 事件", "3.4 role", "3.7 reentry", "3.9 动态几何", "3.10 多路径", "3.11 ABSTAIN"],
                    },
                    {
                        "source_ref": "BOUND_SINGLE_AGENT_PLAYBOOK:OPERATIONAL_FLOW",
                        "document": manifest["strategy_playbook"]["path"],
                        "sections": [
                            "标的专属周期职责",
                            "Evidence ledger 与依赖去重",
                            "有限机制和动态路径",
                            "八动作的真实路径反事实",
                            "仓位、barrier、重入和成本",
                        ],
                    },
                ],
                "evidence_label": AGENT_JUDGMENT_EVIDENCE_LABEL,
                "competition_boundary": "Primitive mechanisms may coexist and use ordinal support. This run has no registered partition proof or calibration authority, so probability_pct, sum-to-100, top-path probability, margin, entropy, and EV are forbidden. Report UNKNOWN_NO_VALID_COMPETITION_SET plus an operational lead and runner-up for action ordering.",
                "dependency_rule": "Copy the authoritative dependency_group/source_version/available_at from evidence_catalog; for one target and dependency group only the maximum absolute ordinal increment counts, with stable evidence_id tie break.",
                "unknown_rule": "Missing evidence remains UNKNOWN; inference must be labeled as inference.",
                "wait_rule": "WAIT requires a specific evidence gap, risk veto, or relative-utility reason plus a review obligation.",
                "core_rule": "A CORE management checkpoint is an Agent review event, never an automatic full exit.",
                "reentry_rule": "A valid strategic thesis after CORE liquidation must preserve or resolve an explicit reentry contract; a prior tactical exit is restored with REENTER_TACTICAL or reviewed with an explicit WAIT obligation.",
                "diagnostic_learning_boundary": (
                    "Known V1 failure classes and the frozen playbook are authorized guidance; this prospective cycle may use only public observations received by decision_at, prior accepted state, and already occurred fills. Later market observations remain unavailable until their scheduled cycle."
                    if manifest.get("evidence_class") == "PROSPECTIVE_24H_PUBLIC_PAPER"
                    else "Known V1 failure classes and the frozen playbook are authorized diagnostic guidance; current-cycle future prices, recorded V1 decisions, fills, and outcomes remain sealed until terminal."
                ),
            },
            "decision_contract": _agent_decision_contract(),
            "hard_boundaries": {
                "point_in_time": "available_at <= decision_at",
                "long_and_short_research_allowed": True,
                "new_risk_requires_stop_and_reward_checkpoint": True,
                "minimum_net_reward_risk": canonical_decimal(policy["minimum_reward_risk"]),
                "standard_trade_risk_fraction": canonical_decimal(policy["standard_risk_fraction"]),
                "probe_trade_risk_fraction": canonical_decimal(policy["probe_risk_fraction"]),
                "symbol_risk_fraction": canonical_decimal(policy["symbol_risk_fraction"]),
                "portfolio_risk_fraction": canonical_decimal(policy["portfolio_risk_fraction"]),
                "gross_multiple": canonical_decimal(policy["gross_multiple"]),
                "drawdown_no_new_risk_fraction": canonical_decimal(policy["drawdown_fraction"]),
                "external_execution_authority": EXECUTION_AUTHORITY,
                "executable": False,
            },
            "recorded_v1_decisions_visible": False,
            "recorded_v1_outcomes_visible": False,
        }
    agent_context_document["accepted_strategy_state"]["position_truth"] = {
        symbol: _action_position_truth(agent_context_document, symbol=symbol)
        for symbol in SYMBOLS
    }
    agent_context = self_digest(agent_context_document, "agent_context_digest")
    agent_path = root / "agent-contexts" / f"cycle-{cycle_index:04d}.json"
    write_once_json(agent_path, agent_context)
    checkpoint["status"] = "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED"
    checkpoint["pending_agent_context_path"] = agent_path.relative_to(root).as_posix()
    checkpoint["pending_pre_decision_state_path"] = pre_path.relative_to(root).as_posix()
    _write_atomic_json(root / "checkpoint.json", checkpoint)
    return agent_context


def _string_list(value: Any, code: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise SingleAgentResearchError(code)
    if not allow_empty and not value:
        raise SingleAgentResearchError(code)
    return list(value)


def _review_time(value: Any, decision_at: str) -> str:
    if not isinstance(value, str) or _ts(value) <= _ts(decision_at):
        raise SingleAgentResearchError("REVIEW_OBLIGATION_INVALID")
    return value


def _validate_evidence_refs(refs: Any, valid: set[str], code: str) -> list[str]:
    rows = _string_list(refs, code)
    if any(item not in valid for item in rows):
        raise SingleAgentResearchError(code)
    return rows


def _validate_path_set(
    paths: Any,
    *,
    valid_evidence: set[str],
    valid_theory_sources: set[str],
    previous_episode: Mapping[str, Any] | None,
    decision_at: str,
) -> list[dict[str, Any]]:
    if (
        not isinstance(paths, list)
        or len(paths) < len(REQUIRED_PATH_CLASSES)
        or len(paths) > len(PATH_CLASSES)
    ):
        raise SingleAgentResearchError("COMPETING_PATH_SET_INCOMPLETE")
    output: list[dict[str, Any]] = []
    classes: set[str] = set()
    identifiers: set[str] = set()
    old_by_class = {
        str(row.get("path_class")): str(row.get("path_id"))
        for row in (previous_episode or {}).get("paths", [])
        if isinstance(row, Mapping)
    }
    for row in paths:
        if not isinstance(row, Mapping):
            raise SingleAgentResearchError("COMPETING_PATH_INVALID")
        path_class = str(row.get("path_class") or "")
        path_id = str(row.get("path_id") or "")
        support = str(row.get("support_level") or "")
        confidence = str(row.get("confidence") or "")
        if "probability_pct" in row:
            raise SingleAgentResearchError("PATH_NUMERIC_PROBABILITY_UNAUTHORIZED")
        if path_class not in PATH_CLASSES or path_class in classes:
            raise SingleAgentResearchError("COMPETING_PATH_SET_INCOMPLETE")
        if (
            not path_id
            or path_id in identifiers
            or support not in SUPPORT_LEVELS
            or confidence not in PATH_CONFIDENCE_LEVELS
        ):
            raise SingleAgentResearchError("COMPETING_PATH_INVALID")
        if path_class in old_by_class and old_by_class[path_class] != path_id:
            raise SingleAgentResearchError("PATH_ID_CONTINUITY_VIOLATION")
        thesis = str(row.get("thesis") or "").strip()
        horizon = str(row.get("horizon") or "").strip()
        observed_prefix = str(row.get("observed_prefix") or "").strip()
        favorable_path = str(row.get("favorable_path") or "").strip()
        adverse_path = str(row.get("adverse_path") or "").strip()
        normal_path_variation = str(row.get("normal_path_variation") or "").strip()
        what_changed = str(row.get("what_changed") or "").strip()
        mechanism_ids = _string_list(
            row.get("mechanism_ids", []), "PATH_MECHANISM_INVALID", allow_empty=False
        )
        if (
            not thesis
            or not horizon
            or not observed_prefix
            or not favorable_path
            or not adverse_path
            or not normal_path_variation
            or not what_changed
            or len(set(mechanism_ids)) != len(mechanism_ids)
            or any(item not in MECHANISM_IDS for item in mechanism_ids)
        ):
            raise SingleAgentResearchError("COMPETING_PATH_INVALID")
        if path_class == "DATA_ARTIFACT":
            if "ARTIFACT" not in mechanism_ids:
                raise SingleAgentResearchError("PATH_MECHANISM_INVALID")
        elif "ARTIFACT" in mechanism_ids:
            raise SingleAgentResearchError("PATH_MECHANISM_INVALID")
        if path_class == "OTHER_OR_UNKNOWN":
            if "OTHER" not in mechanism_ids:
                raise SingleAgentResearchError("PATH_MECHANISM_INVALID")
        elif "OTHER" in mechanism_ids:
            raise SingleAgentResearchError("PATH_MECHANISM_INVALID")
        theory_source_refs = _string_list(
            row.get("theory_source_refs", []),
            "PATH_THEORY_SOURCE_INVALID",
            allow_empty=False,
        )
        if any(item not in valid_theory_sources for item in theory_source_refs):
            raise SingleAgentResearchError("PATH_THEORY_SOURCE_INVALID")
        normalized = {
            "path_id": path_id,
            "path_class": path_class,
            "mechanism_ids": mechanism_ids,
            "support_level": support,
            "confidence": confidence,
            "theory_source_refs": theory_source_refs,
            "thesis": thesis,
            "horizon": horizon,
            "observed_prefix": observed_prefix,
            "evidence_for_refs": _validate_evidence_refs(
                row.get("evidence_for_refs", []), valid_evidence, "PATH_EVIDENCE_REF_INVALID"
            ),
            "evidence_against_refs": _validate_evidence_refs(
                row.get("evidence_against_refs", []), valid_evidence, "PATH_EVIDENCE_REF_INVALID"
            ),
            "next_support_observations": _string_list(
                row.get("next_support_observations", []),
                "PATH_NEXT_SUPPORT_INVALID",
                allow_empty=False,
            ),
            "soft_contradictions": _string_list(
                row.get("soft_contradictions", []),
                "PATH_SOFT_CONTRADICTION_INVALID",
                allow_empty=False,
            ),
            "hard_falsifiers": _string_list(
                row.get("hard_falsifiers", []),
                "PATH_INVALIDATOR_INVALID",
                allow_empty=False,
            ),
            "expiry_at": _review_time(row.get("expiry_at"), decision_at),
            "favorable_path": favorable_path,
            "adverse_path": adverse_path,
            "normal_path_variation": normal_path_variation,
            "data_gaps": _string_list(row.get("data_gaps", []), "PATH_DATA_GAP_INVALID"),
            "what_changed": what_changed,
            "limitations": _string_list(
                row.get("limitations", []), "PATH_LIMITATION_INVALID", allow_empty=False
            ),
        }
        classes.add(path_class)
        identifiers.add(path_id)
        output.append(normalized)
    if not REQUIRED_PATH_CLASSES.issubset(classes):
        raise SingleAgentResearchError("COMPETING_PATH_SET_INCOMPLETE")
    if old_by_class and not set(old_by_class).issubset(classes):
        raise SingleAgentResearchError("PATH_ID_CONTINUITY_VIOLATION")
    return sorted(output, key=lambda row: PATH_CLASS_ORDER.index(row["path_class"]))


def _validate_evidence_ledger(
    ledger: Any,
    *,
    evidence_metadata: Mapping[str, Mapping[str, Any]],
    valid_path_ids: set[str],
    decision_at: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(ledger, list) or not ledger:
        raise SingleAgentResearchError("EVIDENCE_LEDGER_MISSING")
    exact_fields = {
        "evidence_id",
        "available_at",
        "perspective_id",
        "dependency_group",
        "target_ids",
        "direction",
        "ordinal_strength",
        "quality",
        "source_version",
    }
    normalized: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    for item in ledger:
        if not isinstance(item, Mapping) or set(item) != exact_fields:
            raise SingleAgentResearchError("EVIDENCE_LEDGER_SCHEMA_INVALID")
        evidence_id = str(item.get("evidence_id") or "")
        perspective_id = str(item.get("perspective_id") or "")
        dependency_group = str(item.get("dependency_group") or "")
        direction = str(item.get("direction") or "")
        ordinal_strength = str(item.get("ordinal_strength") or "")
        quality = str(item.get("quality") or "")
        source_version = str(item.get("source_version") or "")
        target_ids = item.get("target_ids")
        if (
            not evidence_id
            or evidence_id in evidence_ids
            or evidence_id not in evidence_metadata
            or perspective_id not in EVIDENCE_PERSPECTIVES
            or not dependency_group
            or direction not in EVIDENCE_DIRECTIONS
            or ordinal_strength not in ORDINAL_STRENGTHS
            or quality != "VALID"
            or not source_version
            or not isinstance(target_ids, list)
            or not target_ids
            or target_ids != sorted(set(target_ids))
            or any(not isinstance(target, str) or target not in valid_path_ids for target in target_ids)
        ):
            raise SingleAgentResearchError("EVIDENCE_LEDGER_VALUE_INVALID")
        metadata = evidence_metadata[evidence_id]
        available_at = str(item.get("available_at") or "")
        if (
            available_at != str(metadata.get("available_at") or "")
            or dependency_group != str(metadata.get("dependency_group") or "")
            or source_version != str(metadata.get("source_version") or "")
            or _ts(available_at) > _ts(decision_at)
        ):
            raise SingleAgentResearchError("EVIDENCE_LEDGER_LINEAGE_INVALID")
        normalized.append(
            {
                "evidence_id": evidence_id,
                "available_at": available_at,
                "perspective_id": perspective_id,
                "dependency_group": dependency_group,
                "target_ids": list(target_ids),
                "direction": direction,
                "ordinal_strength": ordinal_strength,
                "quality": quality,
                "source_version": source_version,
            }
        )
        evidence_ids.add(evidence_id)

    strength_value = {"WEAK": 1, "MODERATE": 2, "STRONG": 3}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in normalized:
        for target_id in item["target_ids"]:
            grouped.setdefault((target_id, item["dependency_group"]), []).append(item)
    selected: dict[str, list[dict[str, Any]]] = {target: [] for target in valid_path_ids}
    for (target_id, _), candidates in sorted(grouped.items()):
        def priority(candidate: Mapping[str, Any]) -> tuple[int, str]:
            magnitude = 4 if candidate["direction"] == "HARD_FALSIFIER" else strength_value[candidate["ordinal_strength"]]
            return (-magnitude, str(candidate["evidence_id"]))

        selected[target_id].append(sorted(candidates, key=priority)[0])
    aggregation: dict[str, dict[str, Any]] = {}
    for target_id in sorted(valid_path_ids):
        winners = sorted(selected[target_id], key=lambda item: (item["dependency_group"], item["evidence_id"]))
        net_delta = 0
        hard_ids: list[str] = []
        for winner in winners:
            if winner["direction"] == "HARD_FALSIFIER":
                net_delta -= 4
                hard_ids.append(winner["evidence_id"])
            elif winner["direction"] == "SOFT_CONTRADICTION":
                net_delta -= strength_value[winner["ordinal_strength"]]
            else:
                net_delta += strength_value[winner["ordinal_strength"]]
        aggregation[target_id] = {
            "aggregator": "MAX_ABSOLUTE_STRENGTH_THEN_EVIDENCE_ID",
            "dependency_group_count": len(winners),
            "selected_evidence_ids": [winner["evidence_id"] for winner in winners],
            "hard_falsifier_evidence_ids": hard_ids,
            "net_ordinal_delta": net_delta,
        }
    return sorted(normalized, key=lambda item: item["evidence_id"]), aggregation


def _validate_observation_requests(
    requests: Any,
    *,
    valid_evidence: set[str],
    valid_path_ids: set[str],
    previous_episode: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(requests, list):
        raise SingleAgentResearchError("OBSERVATION_REQUESTS_INVALID")
    output: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for row in requests:
        if not isinstance(row, Mapping):
            raise SingleAgentResearchError("OBSERVATION_REQUEST_INVALID")
        request_id = str(row.get("request_id") or "").strip()
        observation = str(row.get("observation") or "").strip()
        timeframe = str(row.get("timeframe") or "").strip()
        premise = str(row.get("premise") or "").strip()
        limitation = str(row.get("limitation") or "").strip()
        resolution_note = str(row.get("resolution_note") or "").strip()
        status = str(row.get("status") or "")
        source_preference = str(row.get("source_preference") or "")
        cost_tier = str(row.get("cost_tier") or "")
        if (
            not request_id
            or request_id in identifiers
            or not observation
            or not timeframe
            or not premise
            or not limitation
            or not resolution_note
            or status not in OBSERVATION_REQUEST_STATUSES
            or source_preference not in OBSERVATION_SOURCE_PREFERENCES
            or cost_tier not in {"LOW", "MEDIUM", "HIGH"}
        ):
            raise SingleAgentResearchError("OBSERVATION_REQUEST_INVALID")
        purpose_path_ids = _string_list(
            row.get("purpose_path_ids", []),
            "OBSERVATION_REQUEST_PATH_INVALID",
            allow_empty=False,
        )
        if any(item not in valid_path_ids for item in purpose_path_ids):
            raise SingleAgentResearchError("OBSERVATION_REQUEST_PATH_INVALID")
        evidence_refs = _validate_evidence_refs(
            row.get("evidence_refs", []),
            valid_evidence,
            "OBSERVATION_REQUEST_EVIDENCE_INVALID",
        )
        if status == "FULFILLED" and not evidence_refs:
            raise SingleAgentResearchError("OBSERVATION_REQUEST_EVIDENCE_INVALID")
        identifiers.add(request_id)
        output.append(
            {
                "request_id": request_id,
                "observation": observation,
                "purpose_path_ids": purpose_path_ids,
                "timeframe": timeframe,
                "premise": premise,
                "source_preference": source_preference,
                "cost_tier": cost_tier,
                "status": status,
                "evidence_refs": evidence_refs,
                "resolution_note": resolution_note,
                "limitation": limitation,
            }
        )
    prior_pending = {
        str(row.get("request_id"))
        for row in (previous_episode or {}).get("observation_requests", [])
        if isinstance(row, Mapping) and row.get("status") == "PENDING"
    }
    if not prior_pending.issubset(identifiers):
        raise SingleAgentResearchError("PENDING_OBSERVATION_REQUEST_DROPPED")
    return sorted(output, key=lambda row: row["request_id"])


def _validate_symbol_decision(
    row: Any,
    *,
    symbol: str,
    agent_context: Mapping[str, Any],
    previous_episode: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise SingleAgentResearchError("SYMBOL_DECISION_INVALID")
    position_truth = _action_position_truth(agent_context, symbol=symbol)
    stored_position_truth = (
        agent_context.get("accepted_strategy_state", {})
        .get("position_truth", {})
        .get(symbol)
    )
    if stored_position_truth is not None and stored_position_truth != position_truth:
        raise SingleAgentResearchError("ACTION_POSITION_TRUTH_CONTEXT_MISMATCH")
    evidence_catalog = agent_context["market"]["symbols"][symbol]["evidence_catalog"]
    evidence_metadata = {
        str(item["evidence_ref"]): item
        for item in evidence_catalog
        if isinstance(item, Mapping) and item.get("evidence_ref")
    }
    valid_evidence = set(evidence_metadata)
    cross_market = agent_context["market"].get("cross_market", {})
    cross_market_ref = (
        cross_market.get("evidence_ref") if isinstance(cross_market, Mapping) else None
    )
    if isinstance(cross_market_ref, str) and cross_market_ref:
        valid_evidence.add(cross_market_ref)
        evidence_metadata[cross_market_ref] = {
            "available_at": cross_market.get("available_at"),
            "dependency_group": cross_market.get("dependency_group"),
            "source_version": cross_market.get("source_version"),
        }
    if not valid_evidence or any(
        not metadata.get("available_at")
        or not metadata.get("dependency_group")
        or not metadata.get("source_version")
        for metadata in evidence_metadata.values()
    ):
        raise SingleAgentResearchError("EVIDENCE_CATALOG_LINEAGE_MISSING")
    theory_catalog = agent_context["agent_task"].get("theory_source_catalog", [])
    valid_theory_sources = {
        str(item.get("source_ref"))
        for item in theory_catalog
        if isinstance(item, Mapping) and item.get("source_ref")
    }
    if not valid_theory_sources:
        raise SingleAgentResearchError("THEORY_SOURCE_CATALOG_MISSING")

    analysis_trace = row.get("analysis_trace")
    if not isinstance(analysis_trace, list) or len(analysis_trace) < 4:
        raise SingleAgentResearchError("ANALYSIS_TRACE_INCOMPLETE")
    normalized_trace: list[dict[str, Any]] = []
    trace_ids: set[str] = set()
    epistemic_types: set[str] = set()
    for item in analysis_trace:
        if not isinstance(item, Mapping):
            raise SingleAgentResearchError("ANALYSIS_TRACE_INVALID")
        trace_id = str(item.get("trace_id") or "").strip()
        epistemic_type = str(item.get("epistemic_type") or "")
        statement = str(item.get("statement") or "").strip()
        limitation = str(item.get("limitation") or "").strip()
        if (
            not trace_id
            or trace_id in trace_ids
            or epistemic_type not in EPISTEMIC_TYPES
            or not statement
            or not limitation
        ):
            raise SingleAgentResearchError("ANALYSIS_TRACE_INVALID")
        source_refs = _string_list(
            item.get("theory_source_refs", []),
            "ANALYSIS_TRACE_THEORY_INVALID",
            allow_empty=False,
        )
        if any(source not in valid_theory_sources for source in source_refs):
            raise SingleAgentResearchError("ANALYSIS_TRACE_THEORY_INVALID")
        evidence_refs = _validate_evidence_refs(
            item.get("evidence_refs", []),
            valid_evidence,
            "ANALYSIS_TRACE_EVIDENCE_INVALID",
        )
        if epistemic_type in {"OBSERVATION", "DERIVED_MEASURE", "INFERENCE"} and not evidence_refs:
            raise SingleAgentResearchError("ANALYSIS_TRACE_EVIDENCE_INVALID")
        normalized_trace.append(
            {
                "trace_id": trace_id,
                "epistemic_type": epistemic_type,
                "statement": statement,
                "evidence_refs": evidence_refs,
                "theory_source_refs": source_refs,
                "limitation": limitation,
            }
        )
        trace_ids.add(trace_id)
        epistemic_types.add(epistemic_type)
    if not {
        "INFERENCE",
        "HYPOTHESIS",
        "POLICY",
    }.issubset(epistemic_types) or not epistemic_types.intersection(
        {"OBSERVATION", "DERIVED_MEASURE"}
    ):
        raise SingleAgentResearchError("ANALYSIS_TRACE_INCOMPLETE")
    sentiment = row.get("sentiment_assessment")
    if not isinstance(sentiment, Mapping):
        raise SingleAgentResearchError("SENTIMENT_ASSESSMENT_MISSING")
    dimensions = sentiment.get("dimensions")
    required_dimensions = set(agent_context["agent_task"]["required_sentiment_dimensions"])
    if not isinstance(dimensions, Mapping) or set(dimensions) != required_dimensions:
        raise SingleAgentResearchError("SENTIMENT_DIMENSIONS_INCOMPLETE")
    normalized_dimensions: dict[str, Any] = {}
    for name in sorted(required_dimensions):
        value = dimensions[name]
        if not isinstance(value, Mapping):
            raise SingleAgentResearchError("SENTIMENT_DIMENSION_INVALID")
        state = str(value.get("state") or "")
        interpretation = str(value.get("interpretation") or "").strip()
        if state not in {"RISK_SEEKING", "RISK_AVERSE", "MIXED", "NEUTRAL", "UNKNOWN"} or not interpretation:
            raise SingleAgentResearchError("SENTIMENT_DIMENSION_INVALID")
        normalized_dimensions[name] = {
            "state": state,
            "interpretation": interpretation,
            "evidence_refs": _validate_evidence_refs(
                value.get("evidence_refs", []), valid_evidence, "SENTIMENT_EVIDENCE_REF_INVALID"
            ),
            "inference_label": str(value.get("inference_label") or "INFERENCE_NOT_OBSERVATION"),
            "limitations": _string_list(value.get("limitations", []), "SENTIMENT_LIMITATION_INVALID"),
        }
    sentiment_summary = str(sentiment.get("summary") or "").strip()
    if not sentiment_summary:
        raise SingleAgentResearchError("SENTIMENT_ASSESSMENT_MISSING")

    assessment = row.get("strategic_assessment")
    if not isinstance(assessment, Mapping):
        raise SingleAgentResearchError("STRATEGIC_ASSESSMENT_MISSING")
    operation = str(assessment.get("episode_operation") or "")
    status = str(assessment.get("strategic_status") or "")
    if operation not in EPISODE_OPERATIONS or status not in STRATEGIC_STATUSES - {"NONE"}:
        raise SingleAgentResearchError("EPISODE_TRANSITION_INVALID")
    episode_id = str(assessment.get("episode_id") or "")
    if previous_episode is None:
        if operation != "OPEN" or not episode_id:
            raise SingleAgentResearchError("EPISODE_GENESIS_REQUIRED")
    else:
        previous_status = str(previous_episode.get("strategic_status"))
        if operation == "OPEN":
            raise SingleAgentResearchError("EPISODE_DUPLICATE_OPEN")
        if operation != "REPLACE" and episode_id != previous_episode.get("episode_id"):
            raise SingleAgentResearchError("EPISODE_ID_CONTINUITY_VIOLATION")
        if operation == "REPLACE" and previous_status not in {"INVALIDATED", "CLOSED"}:
            raise SingleAgentResearchError("EPISODE_REPLACE_BEFORE_CLOSE")
        if (
            operation == "INVALIDATE"
            and previous_episode.get("origin_hypothesis")
            == "EXOGENOUS_INITIAL_POSITION_THESIS_UNDECLARED"
        ):
            raise SingleAgentResearchError("GENESIS_UNDECLARED_THESIS_NOT_HARD_FALSIFIER")
    status_by_operation = {
        "CHALLENGE": {"CHALLENGED"},
        "INVALIDATE": {"INVALIDATED"},
        "CLOSE": {"CLOSED"},
        "OPEN": {"ACTIVE", "CHALLENGED"},
        "UPDATE": {"ACTIVE", "CHALLENGED"},
        "REPLACE": {"ACTIVE", "CHALLENGED"},
        "NONE": set(),
    }
    if status not in status_by_operation[operation]:
        raise SingleAgentResearchError("EPISODE_TRANSITION_INVALID")
    paths = _validate_path_set(
        assessment.get("paths"),
        valid_evidence=valid_evidence,
        valid_theory_sources=valid_theory_sources,
        previous_episode=(None if operation == "REPLACE" else previous_episode),
        decision_at=str(agent_context["decision_at"]),
    )
    valid_path_ids = {item["path_id"] for item in paths}
    evidence_ledger, evidence_aggregation = _validate_evidence_ledger(
        assessment.get("evidence_ledger"),
        evidence_metadata=evidence_metadata,
        valid_path_ids=valid_path_ids,
        decision_at=str(agent_context["decision_at"]),
    )
    current_evidence_keys = {
        f"{item['evidence_id']}|{item['dependency_group']}|{target_id}"
        for item in evidence_ledger
        for target_id in item["target_ids"]
    }
    prior_evidence_keys = set(
        (previous_episode or {}).get("consumed_evidence_keys", [])
    )
    if current_evidence_keys.intersection(prior_evidence_keys):
        raise SingleAgentResearchError("EVIDENCE_INCREMENT_REUSED")
    consumed_evidence_keys = sorted(prior_evidence_keys | current_evidence_keys)
    ledger_by_evidence = {item["evidence_id"]: item for item in evidence_ledger}
    for path in paths:
        for evidence_ref in path["evidence_for_refs"]:
            ledger_row = ledger_by_evidence.get(evidence_ref)
            if (
                ledger_row is None
                or path["path_id"] not in ledger_row["target_ids"]
                or ledger_row["direction"] != "SUPPORT"
            ):
                raise SingleAgentResearchError("PATH_EVIDENCE_LEDGER_MISMATCH")
        for evidence_ref in path["evidence_against_refs"]:
            ledger_row = ledger_by_evidence.get(evidence_ref)
            if (
                ledger_row is None
                or path["path_id"] not in ledger_row["target_ids"]
                or ledger_row["direction"] == "SUPPORT"
            ):
                raise SingleAgentResearchError("PATH_EVIDENCE_LEDGER_MISMATCH")
    if any(
        key in assessment
        for key in {
            "primary_path_id",
            "probability_boundary",
            "top_path_probability",
            "margin",
            "entropy",
        }
    ):
        raise SingleAgentResearchError("PATH_NUMERIC_COMPETITION_UNAUTHORIZED")
    operational_lead_path_id = str(assessment.get("operational_lead_path_id") or "")
    runner_up_path_id = str(assessment.get("runner_up_path_id") or "")
    path_class_by_id = {item["path_id"]: item["path_class"] for item in paths}
    if (
        operational_lead_path_id not in valid_path_ids
        or runner_up_path_id not in valid_path_ids
        or runner_up_path_id == operational_lead_path_id
        or path_class_by_id[operational_lead_path_id] in {"OTHER_OR_UNKNOWN", "DATA_ARTIFACT"}
        or path_class_by_id[runner_up_path_id] in {"OTHER_OR_UNKNOWN", "DATA_ARTIFACT"}
    ):
        raise SingleAgentResearchError("OPERATIONAL_PATH_ORDER_INVALID")
    residual_path_id = next(
        item["path_id"] for item in paths if item["path_class"] == "OTHER_OR_UNKNOWN"
    )
    competition_set_status = str(assessment.get("competition_set_status") or "")
    if competition_set_status != "UNKNOWN_NO_VALID_COMPETITION_SET":
        raise SingleAgentResearchError("COMPETITION_SET_STATUS_INVALID")
    active_primitive_mechanism_ids = _string_list(
        assessment.get("active_primitive_mechanism_ids", []),
        "ACTIVE_MECHANISM_SET_INVALID",
        allow_empty=False,
    )
    declared_mechanisms = {
        mechanism for path in paths for mechanism in path["mechanism_ids"]
    }
    if (
        active_primitive_mechanism_ids != sorted(set(active_primitive_mechanism_ids))
        or any(
            mechanism not in MECHANISM_IDS or mechanism not in declared_mechanisms
            for mechanism in active_primitive_mechanism_ids
        )
    ):
        raise SingleAgentResearchError("ACTIVE_MECHANISM_SET_INVALID")
    path_selection_rationale = str(assessment.get("path_selection_rationale") or "").strip()
    ranking_uncertainty = str(assessment.get("ranking_uncertainty") or "").strip()
    switch_conditions = _string_list(
        assessment.get("switch_conditions", []),
        "PATH_SWITCH_CONDITION_INVALID",
        allow_empty=False,
    )
    support_boundary = str(assessment.get("support_boundary") or "").strip()
    if not path_selection_rationale or not ranking_uncertainty or not support_boundary:
        raise SingleAgentResearchError("PATH_SELECTION_RATIONALE_MISSING")
    primary_direction = str(assessment.get("primary_direction") or "")
    if primary_direction not in {"LONG", "SHORT", "NEUTRAL"}:
        raise SingleAgentResearchError("PRIMARY_DIRECTION_INVALID")
    review_by = _review_time(assessment.get("review_by"), str(agent_context["decision_at"]))
    invalidation_basis = None
    if operation == "INVALIDATE":
        value = assessment.get("invalidation_basis")
        if not isinstance(value, Mapping) or previous_episode is None:
            raise SingleAgentResearchError("STRATEGIC_INVALIDATION_BASIS_INVALID")
        matched = str(value.get("matched_prior_hard_invalidator") or "").strip()
        prior_premise = str(value.get("invalidated_prior_premise") or "").strip()
        evidence_refs = _validate_evidence_refs(
            value.get("evidence_refs", []),
            valid_evidence,
            "STRATEGIC_INVALIDATION_EVIDENCE_INVALID",
        )
        if (
            not matched
            or matched not in set(previous_episode.get("hard_invalidators", []))
            or not prior_premise
            or not evidence_refs
        ):
            raise SingleAgentResearchError("STRATEGIC_INVALIDATION_BASIS_INVALID")
        invalidation_basis = {
            "matched_prior_hard_invalidator": matched,
            "invalidated_prior_premise": prior_premise,
            "evidence_refs": evidence_refs,
        }
    elif assessment.get("invalidation_basis") is not None:
        raise SingleAgentResearchError("STRATEGIC_INVALIDATION_BASIS_INVALID")
    geometry = assessment.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, Mapping) or not str(geometry.get("geometry_id") or ""):
            raise SingleAgentResearchError("DYNAMIC_GEOMETRY_INVALID")
        geometry = {
            "geometry_id": str(geometry["geometry_id"]),
            "status": str(geometry.get("status") or "OBSERVATION_ONLY"),
            "entry_zone_lower": geometry.get("entry_zone_lower"),
            "entry_zone_upper": geometry.get("entry_zone_upper"),
            "hard_stop": geometry.get("hard_stop"),
            "tactical_target": geometry.get("tactical_target"),
            "management_checkpoint": geometry.get("management_checkpoint"),
            "valid_until": _review_time(geometry.get("valid_until"), str(agent_context["decision_at"])),
            "basis_evidence_refs": _validate_evidence_refs(
                geometry.get("basis_evidence_refs", []), valid_evidence, "GEOMETRY_EVIDENCE_REF_INVALID"
            ),
            "limitations": _string_list(geometry.get("limitations", []), "GEOMETRY_LIMITATION_INVALID"),
        }

    evidence_update = row.get("evidence_update")
    if not isinstance(evidence_update, Mapping):
        raise SingleAgentResearchError("EVIDENCE_UPDATE_MISSING")
    normalized_update = {
        "added_refs": _validate_evidence_refs(
            evidence_update.get("added_refs", []), valid_evidence, "EVIDENCE_UPDATE_REF_INVALID"
        ),
        "changed_premises": _string_list(
            evidence_update.get("changed_premises", []), "EVIDENCE_PREMISE_INVALID"
        ),
        "removed_or_weakened_premises": _string_list(
            evidence_update.get("removed_or_weakened_premises", []), "EVIDENCE_PREMISE_INVALID"
        ),
        "unknowns": _string_list(evidence_update.get("unknowns", []), "EVIDENCE_UNKNOWN_INVALID"),
        "observation_requests": _validate_observation_requests(
            evidence_update.get("observation_requests", []),
            valid_evidence=valid_evidence,
            valid_path_ids=valid_path_ids,
            previous_episode=previous_episode,
        ),
    }

    comparisons = row.get("action_comparison")
    if not isinstance(comparisons, list) or len(comparisons) != len(COMPARISON_CLASSES):
        raise SingleAgentResearchError("ACTION_COMPARISON_INCOMPLETE")
    comparison_rows: list[dict[str, Any]] = []
    seen_classes: set[str] = set()
    narrative_signatures: set[tuple[str, str, str, str]] = set()
    position_effect_by_class = {
        "HOLD": "MAINTAIN_EXPOSURE",
        "OPEN": "INCREASE_EXPOSURE",
        "ADD": "INCREASE_EXPOSURE",
        "REDUCE": "DECREASE_EXPOSURE",
        "PARTIAL_TAKE_PROFIT": "DECREASE_EXPOSURE",
        "EXIT": "EXIT_SCOPE_EXPOSURE",
        "REENTER": "RESTORE_EXPOSURE",
        "WAIT": "NO_EXPOSURE_CHANGE",
    }
    open_lots = [
        lot
        for lot in agent_context["accepted_strategy_state"]["portfolio"].get("lots", [])
        if isinstance(lot, Mapping)
        and lot.get("instrument_id") == symbol
        and _d(lot.get("remaining_quantity"), "ACTION_COMPARISON_POSITION_INVALID") > ZERO
    ]
    has_open_exposure = bool(open_lots)
    comparison_path_ids = {
        operational_lead_path_id,
        runner_up_path_id,
        residual_path_id,
    }
    for item in comparisons:
        if not isinstance(item, Mapping):
            raise SingleAgentResearchError("ACTION_COMPARISON_INVALID")
        action_class = str(item.get("action_class") or "")
        reason = str(item.get("reason") or "").strip()
        relative_utility = str(item.get("relative_utility") or "").strip()
        feasible = item.get("feasible")
        hard_vetoes = _string_list(
            item.get("hard_vetoes", []), "ACTION_COMPARISON_VETO_INVALID"
        )
        if (
            action_class not in COMPARISON_CLASSES
            or action_class in seen_classes
            or not isinstance(feasible, bool)
            or not reason
            or not relative_utility
            or (not feasible and not hard_vetoes)
            or (feasible and hard_vetoes)
        ):
            raise SingleAgentResearchError("ACTION_COMPARISON_INVALID")
        if action_class in {"HOLD", "REDUCE", "PARTIAL_TAKE_PROFIT", "EXIT"} and feasible != has_open_exposure:
            raise SingleAgentResearchError("ACTION_COMPARISON_POSITION_INCONSISTENT")
        if action_class == "ADD" and feasible and not has_open_exposure:
            raise SingleAgentResearchError("ACTION_COMPARISON_POSITION_INCONSISTENT")
        if action_class == "OPEN" and feasible and has_open_exposure:
            raise SingleAgentResearchError("ACTION_COMPARISON_POSITION_INCONSISTENT")
        conditioned = item.get("path_conditioned_outcomes")
        if not isinstance(conditioned, list) or len(conditioned) != 3:
            raise SingleAgentResearchError("ACTION_PATH_COUNTERFACTUAL_INCOMPLETE")
        normalized_outcomes: list[dict[str, Any]] = []
        seen_path_ids: set[str] = set()
        for outcome in conditioned:
            if not isinstance(outcome, Mapping):
                raise SingleAgentResearchError("ACTION_PATH_COUNTERFACTUAL_INVALID")
            path_id = str(outcome.get("path_id") or "")
            position_effect = str(outcome.get("position_effect") or "")
            compatibility = str(outcome.get("compatibility") or "")
            position_truth_digest = str(
                outcome.get("position_truth_digest") or ""
            )
            path_realization = str(outcome.get("path_realization") or "").strip()
            failure_process = str(outcome.get("failure_process") or "").strip()
            opportunity_cost = str(outcome.get("opportunity_cost") or "").strip()
            cost_and_risk = str(outcome.get("cost_and_risk") or "").strip()
            if (
                path_id not in comparison_path_ids
                or path_id in seen_path_ids
                or position_effect != position_effect_by_class[action_class]
                or compatibility
                not in {"FAVORS_ACTION", "HARMS_ACTION", "CONDITIONAL", "NEUTRAL"}
                or position_truth_digest != position_truth["position_truth_digest"]
                or not path_realization
                or not failure_process
                or not opportunity_cost
                or not cost_and_risk
            ):
                raise SingleAgentResearchError("ACTION_PATH_COUNTERFACTUAL_INVALID")
            _reject_unstructured_position_truth(
                path_realization,
                failure_process,
                opportunity_cost,
                cost_and_risk,
            )
            if (
                has_open_exposure
                and primary_direction == "LONG"
                and action_class == "EXIT"
                and path_class_by_id[path_id] == "TREND_CONTINUATION"
                and compatibility == "FAVORS_ACTION"
            ):
                raise SingleAgentResearchError("ACTION_PATH_SEMANTIC_INVERSION")
            if (
                primary_direction == "LONG"
                and action_class in {"OPEN", "ADD", "REENTER"}
                and path_class_by_id[path_id] == "EXHAUSTION_OR_FAILURE"
                and compatibility == "FAVORS_ACTION"
            ):
                raise SingleAgentResearchError("ACTION_PATH_SEMANTIC_INVERSION")
            signature = (
                path_realization,
                failure_process,
                opportunity_cost,
                cost_and_risk,
            )
            if signature in narrative_signatures:
                raise SingleAgentResearchError("ACTION_COUNTERFACTUAL_TEMPLATE_REUSE")
            narrative_signatures.add(signature)
            normalized_outcomes.append(
                {
                    "path_id": path_id,
                    "position_effect": position_effect,
                    "compatibility": compatibility,
                    "position_truth_digest": position_truth_digest,
                    "path_realization": path_realization,
                    "failure_process": failure_process,
                    "opportunity_cost": opportunity_cost,
                    "cost_and_risk": cost_and_risk,
                }
            )
            seen_path_ids.add(path_id)
        if seen_path_ids != comparison_path_ids:
            raise SingleAgentResearchError("ACTION_PATH_COUNTERFACTUAL_INCOMPLETE")
        comparison_rows.append(
            {
                "action_class": action_class,
                "feasible": feasible,
                "relative_utility": relative_utility,
                "reason": reason,
                "path_conditioned_outcomes": sorted(
                    normalized_outcomes,
                    key=lambda outcome: (
                        0
                        if outcome["path_id"] == operational_lead_path_id
                        else 1
                        if outcome["path_id"] == runner_up_path_id
                        else 2
                    ),
                ),
                "hard_vetoes": hard_vetoes,
            }
        )
        seen_classes.add(action_class)
    if seen_classes != COMPARISON_CLASSES:
        raise SingleAgentResearchError("ACTION_COMPARISON_INCOMPLETE")

    selected = row.get("selected_actions")
    if not isinstance(selected, list) or not selected:
        raise SingleAgentResearchError("SELECTED_ACTION_MISSING")
    actions: list[dict[str, Any]] = []
    action_ids: set[str] = set()
    for item in selected:
        if not isinstance(item, Mapping):
            raise SingleAgentResearchError("ACTION_INVALID")
        action = copy.deepcopy(dict(item))
        action_id = str(action.get("action_id") or "")
        action_type = str(action.get("action_type") or "")
        path_id = str(action.get("path_id") or "")
        reason = str(action.get("reason") or "").strip()
        if (
            not action_id
            or action_id in action_ids
            or action_type not in ACTION_TYPES
            or path_id not in {item["path_id"] for item in paths}
            or not reason
        ):
            raise SingleAgentResearchError("ACTION_INVALID")
        if (
            action_type in NEW_RISK_ACTIONS
            and path_class_by_id[path_id] in {"DATA_ARTIFACT", "OTHER_OR_UNKNOWN"}
        ):
            raise SingleAgentResearchError("NEW_RISK_REQUIRES_MARKET_PATH")
        action["evidence_refs"] = _validate_evidence_refs(
            action.get("evidence_refs", []), valid_evidence, "ACTION_EVIDENCE_REF_INVALID"
        )
        action["action_id"] = action_id
        action["action_type"] = action_type
        action["path_id"] = path_id
        action["reason"] = reason
        action_ids.add(action_id)
        actions.append(action)
    for item in (row for row in actions if row["action_type"] == "WAIT"):
        _review_time(item.get("review_by"), str(agent_context["decision_at"]))
        if not str(item.get("wait_basis") or "") in {"DATA_GAP", "RISK_VETO", "RELATIVE_UTILITY"}:
            raise SingleAgentResearchError("WAIT_BASIS_INVALID")
        _string_list(item.get("required_observations", []), "WAIT_OBLIGATION_INVALID", allow_empty=False)
    comparison_by_class = {
        item["action_class"]: item["feasible"] for item in comparison_rows
    }
    action_to_class = {
        "HOLD": "HOLD",
        "WAIT": "WAIT",
        "OPEN_CORE": "OPEN",
        "OPEN_TACTICAL": "OPEN",
        "ADD_CORE": "ADD",
        "ADD_TACTICAL": "ADD",
        "REDUCE_CORE": "REDUCE",
        "REDUCE_TACTICAL": "REDUCE",
        "PARTIAL_TAKE_PROFIT": "PARTIAL_TAKE_PROFIT",
        "EXIT_TACTICAL": "EXIT",
        "EXIT_WITH_REENTRY": "EXIT",
        "EXIT_STRATEGIC": "EXIT",
        "REENTER_CORE": "REENTER",
        "REENTER_TACTICAL": "REENTER",
    }
    if any(
        action_to_class.get(action["action_type"]) is not None
        and not comparison_by_class[action_to_class[action["action_type"]]]
        for action in actions
    ):
        raise SingleAgentResearchError("SELECTED_ACTION_DECLARED_INFEASIBLE")

    market_conclusion = str(row.get("market_conclusion") or "").strip()
    dynamic_update_summary = str(row.get("dynamic_update_summary") or "").strip()
    if not market_conclusion or not dynamic_update_summary:
        raise SingleAgentResearchError("MARKET_CONCLUSION_MISSING")
    expected_prior_cycle = int(agent_context.get("cycle_index", 0)) - 1
    prior_cycle = row.get("dynamic_update_from_cycle_index")
    if isinstance(prior_cycle, bool) or prior_cycle != expected_prior_cycle:
        raise SingleAgentResearchError("DYNAMIC_UPDATE_PRIOR_CYCLE_INVALID")
    narrative_cycle_refs = {
        int(value)
        for pattern in (r"\bcycle\s*[-#:]?\s*(\d+)\b", r"第\s*(\d+)\s*轮")
        for value in re.findall(pattern, dynamic_update_summary, flags=re.IGNORECASE)
    }
    if narrative_cycle_refs and narrative_cycle_refs != {expected_prior_cycle}:
        raise SingleAgentResearchError("DYNAMIC_UPDATE_PRIOR_CYCLE_LABEL_CONFLICT")
    return {
        "symbol": symbol,
        "market_conclusion": market_conclusion,
        "dynamic_update_from_cycle_index": expected_prior_cycle,
        "dynamic_update_summary": dynamic_update_summary,
        "position_truth": position_truth,
        "analysis_trace": normalized_trace,
        "sentiment_assessment": {
            "summary": sentiment_summary,
            "dimensions": normalized_dimensions,
            "confidence": str(sentiment.get("confidence") or "UNKNOWN"),
            "limitations": _string_list(sentiment.get("limitations", []), "SENTIMENT_LIMITATION_INVALID"),
        },
        "evidence_update": normalized_update,
        "strategic_assessment": {
            "episode_operation": operation,
            "episode_id": episode_id,
            "strategic_status": status,
            "primary_direction": primary_direction,
            "primary_horizon": str(assessment.get("primary_horizon") or "UNSPECIFIED"),
            "market_regime": str(assessment.get("market_regime") or "UNKNOWN"),
            "origin_hypothesis": str(assessment.get("origin_hypothesis") or "UNSPECIFIED"),
            "paths": paths,
            "evidence_ledger": evidence_ledger,
            "evidence_aggregation": evidence_aggregation,
            "consumed_evidence_keys": consumed_evidence_keys,
            "operational_lead_path_id": operational_lead_path_id,
            "runner_up_path_id": runner_up_path_id,
            "path_selection_rationale": path_selection_rationale,
            "ranking_uncertainty": ranking_uncertainty,
            "support_boundary": support_boundary,
            "competition_set_status": competition_set_status,
            "active_primitive_mechanism_ids": active_primitive_mechanism_ids,
            "switch_conditions": switch_conditions,
            "hard_invalidators": _string_list(assessment.get("hard_invalidators", []), "EPISODE_INVALIDATOR_INVALID"),
            "soft_challenges": _string_list(assessment.get("soft_challenges", []), "EPISODE_CHALLENGE_INVALID"),
            "pending_observations": _string_list(assessment.get("pending_observations", []), "EPISODE_PENDING_INVALID"),
            "review_by": review_by,
            "geometry": geometry,
            "exit_reason": assessment.get("exit_reason"),
            "reentry_contract_update": assessment.get("reentry_contract_update"),
            "invalidation_basis": invalidation_basis,
        },
        "action_comparison": sorted(comparison_rows, key=lambda item: item["action_class"]),
        "selected_actions": actions,
    }


def _normalize_agent_decision(
    decision: Mapping[str, Any],
    *,
    agent_context: Mapping[str, Any],
    pre_state: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        decision.get("schema_id") != "single_strategy_agent_decision"
        or decision.get("schema_version") != AGENT_DECISION_SCHEMA_VERSION
        or decision.get("evidence_label") != AGENT_JUDGMENT_EVIDENCE_LABEL
    ):
        raise SingleAgentResearchError("DECISION_SCHEMA_INVALID")
    for key, expected in (
        ("run_id", agent_context["run_id"]),
        ("cycle_index", agent_context["cycle_index"]),
        ("decision_at", agent_context["decision_at"]),
        ("agent_context_digest", agent_context["agent_context_digest"]),
        ("pre_decision_state_digest", pre_state["state_digest"]),
        (
            "strategy_playbook_sha256",
            agent_context["strategy_playbook"]["physical_sha256"],
        ),
    ):
        if decision.get(key) != expected:
            raise SingleAgentResearchError(f"DECISION_BINDING_INVALID:{key}")
    rows = decision.get("symbol_decisions")
    if not isinstance(rows, Mapping) or set(rows) != set(SYMBOLS):
        raise SingleAgentResearchError("DECISION_SYMBOL_SET_INVALID")
    normalized = {
        "schema_id": "single_strategy_agent_decision",
        "schema_version": AGENT_DECISION_SCHEMA_VERSION,
        "run_id": agent_context["run_id"],
        "cycle_index": agent_context["cycle_index"],
        "decision_at": agent_context["decision_at"],
        "agent_context_digest": agent_context["agent_context_digest"],
        "pre_decision_state_digest": pre_state["state_digest"],
        "strategy_playbook_sha256": agent_context["strategy_playbook"][
            "physical_sha256"
        ],
        "evidence_label": AGENT_JUDGMENT_EVIDENCE_LABEL,
        "symbol_decisions": {
            symbol: _validate_symbol_decision(
                rows[symbol],
                symbol=symbol,
                agent_context=agent_context,
                previous_episode=(
                    pre_state["episodes"].get(symbol)
                    if isinstance(pre_state["episodes"].get(symbol), Mapping)
                    else None
                ),
            )
            for symbol in SYMBOLS
        },
        "portfolio_rationale": str(decision.get("portfolio_rationale") or "").strip(),
        "agent_attestation": str(decision.get("agent_attestation") or "").strip(),
    }
    if not normalized["portfolio_rationale"] or not normalized["agent_attestation"]:
        raise SingleAgentResearchError("DECISION_RATIONALE_OR_ATTESTATION_MISSING")
    return self_digest(normalized, "decision_digest")


def _episode_from_assessment(
    assessment: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    sentiment: Mapping[str, Any],
    evidence_update: Mapping[str, Any],
) -> dict[str, Any]:
    replace_episode = assessment["episode_operation"] == "REPLACE"
    revision = 0 if previous is None or replace_episode else int(previous["revision"]) + 1
    reentry = None if previous is None or replace_episode else copy.deepcopy(previous.get("reentry_contract"))
    value = {
        "episode_id": assessment["episode_id"],
        "revision": revision,
        "previous_episode_digest": None if previous is None else previous["episode_digest"],
        "strategic_status": assessment["strategic_status"],
        "exposure_status": "PENDING_ACTION_APPLICATION",
        "primary_direction": assessment["primary_direction"],
        "primary_horizon": assessment["primary_horizon"],
        "market_regime": assessment["market_regime"],
        "origin_hypothesis": assessment["origin_hypothesis"],
        "paths": assessment["paths"],
        "evidence_ledger": assessment["evidence_ledger"],
        "evidence_aggregation": assessment["evidence_aggregation"],
        "consumed_evidence_keys": assessment["consumed_evidence_keys"],
        "operational_lead_path_id": assessment["operational_lead_path_id"],
        "runner_up_path_id": assessment["runner_up_path_id"],
        "path_selection_rationale": assessment["path_selection_rationale"],
        "ranking_uncertainty": assessment["ranking_uncertainty"],
        "support_boundary": assessment["support_boundary"],
        "competition_set_status": assessment["competition_set_status"],
        "active_primitive_mechanism_ids": assessment[
            "active_primitive_mechanism_ids"
        ],
        "switch_conditions": assessment["switch_conditions"],
        "hard_invalidators": assessment["hard_invalidators"],
        "soft_challenges": assessment["soft_challenges"],
        "pending_observations": assessment["pending_observations"],
        "review_by": assessment["review_by"],
        "geometry": assessment["geometry"],
        "exit_reason": assessment["exit_reason"],
        "invalidation_basis": assessment["invalidation_basis"],
        "reentry_contract": reentry,
        "observation_requests": evidence_update["observation_requests"],
        "sentiment_assessment": sentiment,
        "last_evidence_update": evidence_update,
    }
    return self_digest(value, "episode_digest")


def _replace_portfolio_lot(
    portfolio: PortfolioState, lot_id: str, **changes: Any
) -> PortfolioState:
    if not any(lot.lot_id == lot_id and lot.remaining_quantity > ZERO for lot in portfolio.lots):
        raise SingleAgentResearchError("LOT_NOT_OPEN")
    lots = tuple(
        replace(lot, **changes) if lot.lot_id == lot_id else lot
        for lot in portfolio.lots
    )
    return replace(portfolio, revision=portfolio.revision + 1, lots=lots)


def _active_pending_metrics(
    orders: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Decimal],
) -> tuple[Decimal, dict[str, Decimal], dict[str, Decimal]]:
    gross = ZERO
    risks = {symbol: ZERO for symbol in SYMBOLS}
    notionals = {symbol: ZERO for symbol in SYMBOLS}
    for order in orders:
        if order.get("status") != "ACTIVE" or order.get("side") != "BUY":
            continue
        symbol = str(order["symbol"])
        notional = _d(order["notional_usdt"], "ORDER_INVALID")
        entry = _d(order["limit_price"], "ORDER_INVALID")
        stop = _d(order["stop_price"], "ORDER_INVALID")
        budget = order.get("risk_budget_usdt")
        if budget is not None:
            risk = _d(budget, "ORDER_INVALID")
        else:
            quantity = notional / entry
            stop_fill = _stop_fill(
                stop, LotSide.LONG, policy["stop_slippage_bps"]
            )
            risk = (
                abs(entry - stop_fill) * quantity
                + notional * policy["maker_fee_rate"]
                + quantity * stop_fill * policy["taker_fee_rate"]
            )
        gross += notional
        notionals[symbol] += notional
        risks[symbol] += risk
    return gross, risks, notionals


def _current_open_risk(
    portfolio: PortfolioState,
    *,
    marks: Mapping[str, Decimal],
    policy: Mapping[str, Decimal],
) -> tuple[Decimal, dict[str, Decimal]]:
    total = ZERO
    rows = {symbol: ZERO for symbol in SYMBOLS}
    for lot in _open_lots(portfolio):
        if lot.stop_price is None:
            continue
        mark = marks[lot.instrument_id]
        stop_fill = _stop_fill(
            lot.stop_price, lot.side, policy["stop_slippage_bps"]
        )
        adverse_from_current_equity = (
            max(mark - stop_fill, ZERO)
            if lot.side is LotSide.LONG
            else max(stop_fill - mark, ZERO)
        )
        quantity_multiplier = lot.remaining_quantity * lot.contract_multiplier
        risk = (
            adverse_from_current_equity * quantity_multiplier
            + stop_fill * quantity_multiplier * policy["taker_fee_rate"]
        )
        total += risk
        rows[lot.instrument_id] += risk
    return total, rows


def _entry_geometry(
    *,
    side: LotSide,
    reference: Decimal,
    notional: Decimal,
    stop: Decimal,
    reward_checkpoint: Decimal,
    policy: Mapping[str, Decimal],
    maker_entry: bool = False,
) -> dict[str, Decimal]:
    entry = (
        reference
        if maker_entry
        else _market_fill(reference, side, opening=True, bps=policy["market_slippage_bps"])
    )
    if side is LotSide.LONG:
        valid = stop < entry < reward_checkpoint
    else:
        valid = reward_checkpoint < entry < stop
    if not valid:
        raise SingleAgentResearchError("ACTION_GEOMETRY_DIRECTION_INVALID")
    quantity = notional / entry
    stop_price = _stop_fill(stop, side, policy["stop_slippage_bps"])
    entry_fee_rate = policy["maker_fee_rate"] if maker_entry else policy["taker_fee_rate"]
    entry_fee = notional * entry_fee_rate
    stop_fee = quantity * stop_price * policy["taker_fee_rate"]
    reward_fee = quantity * reward_checkpoint * policy["taker_fee_rate"]
    gross_loss = abs(entry - stop_price) * quantity
    gross_reward = abs(reward_checkpoint - entry) * quantity
    net_loss = gross_loss + entry_fee + stop_fee
    net_reward = gross_reward - entry_fee - reward_fee
    net_rr = ZERO if net_loss <= ZERO else net_reward / net_loss
    return {
        "entry": entry,
        "quantity": quantity,
        "stop_fill": stop_price,
        "entry_fee": entry_fee,
        "net_loss": net_loss,
        "net_reward": net_reward,
        "net_reward_risk": net_rr,
    }


def _new_risk_vetoes(
    *,
    portfolio: PortfolioState,
    orders: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    marks: Mapping[str, Decimal],
    marked_at: datetime,
    symbol: str,
    notional: Decimal,
    geometry: Mapping[str, Decimal],
    risk_class: str,
    policy: Mapping[str, Decimal],
) -> list[str]:
    vetoes: list[str] = []
    if notional < policy["minimum_notional_usdt"] or notional > policy["maximum_notional_usdt"]:
        vetoes.append("NOTIONAL_OUTSIDE_FROZEN_RANGE")
    snapshot = mark_portfolio(portfolio, marks=dict(marks), marked_at=marked_at)
    funding = (
        ZERO
        if state.get("funding_usdt") is None
        else _d(state.get("funding_usdt"), "STATE_FUNDING_INVALID")
    )
    effective_equity = snapshot.equity + funding
    risk_cap_equity = min(effective_equity, portfolio.initial_equity)
    peak = _d(state["peak_equity_usdt"], "STATE_EQUITY_INVALID")
    drawdown = ZERO if peak <= ZERO else max(ZERO, (peak - effective_equity) / peak)
    if drawdown >= policy["drawdown_fraction"]:
        vetoes.append("DRAWDOWN_NO_NEW_RISK")
    if snapshot.unprotected_lot_ids:
        vetoes.append("UNPROTECTED_EXISTING_LOT")
    if geometry["net_reward"] <= ZERO or geometry["net_reward_risk"] < policy["minimum_reward_risk"]:
        vetoes.append("NET_REWARD_RISK_BELOW_MINIMUM")
    trade_fraction = (
        policy["probe_risk_fraction"] if risk_class == "PROBE" else policy["standard_risk_fraction"]
    )
    if risk_class not in {"PROBE", "STANDARD"}:
        vetoes.append("RISK_CLASS_INVALID")
    if geometry["net_loss"] > risk_cap_equity * trade_fraction:
        vetoes.append("TRADE_RISK_CAP_EXCEEDED")
    current_risk, symbol_risk = _current_open_risk(
        portfolio, marks=marks, policy=policy
    )
    pending_gross, pending_risk, pending_notional = _active_pending_metrics(
        orders, policy=policy
    )
    if current_risk + sum(pending_risk.values(), ZERO) + geometry["net_loss"] > risk_cap_equity * policy["portfolio_risk_fraction"]:
        vetoes.append("PORTFOLIO_RISK_CAP_EXCEEDED")
    if symbol_risk[symbol] + pending_risk[symbol] + geometry["net_loss"] > risk_cap_equity * policy["symbol_risk_fraction"]:
        vetoes.append("SYMBOL_RISK_CAP_EXCEEDED")
    if snapshot.gross_notional + pending_gross + notional > effective_equity * policy["gross_multiple"]:
        vetoes.append("GROSS_NOTIONAL_CAP_EXCEEDED")
    symbol_open_notional = sum(
        lot.remaining_quantity * marks[symbol] * lot.contract_multiplier
        for lot in _open_lots(portfolio, symbol)
    )
    if symbol_open_notional + pending_notional[symbol] + notional > effective_equity * policy["symbol_notional_fraction"]:
        vetoes.append("SYMBOL_NOTIONAL_CAP_EXCEEDED")
    return sorted(set(vetoes))


def _eligible_action_lots(
    portfolio: PortfolioState,
    *,
    symbol: str,
    action: Mapping[str, Any],
    required_role: LotRole | None = None,
) -> tuple[OfflineLot, ...]:
    lots = _open_lots(portfolio, symbol)
    lot_id = action.get("lot_id")
    if lot_id:
        lots = tuple(lot for lot in lots if lot.lot_id == lot_id)
    role_value = action.get("role")
    if role_value:
        try:
            role = LotRole(str(role_value))
        except ValueError as exc:
            raise SingleAgentResearchError("ACTION_ROLE_INVALID") from exc
        lots = tuple(lot for lot in lots if lot.role is role)
    if required_role is not None:
        lots = tuple(lot for lot in lots if lot.role is required_role)
    if not lots:
        raise SingleAgentResearchError("ACTION_HAS_NO_ELIGIBLE_LOT")
    return tuple(sorted(lots, key=lambda lot: lot.lot_id))


def _apply_protection_action(
    portfolio: PortfolioState,
    lot_contracts: dict[str, dict[str, Any]],
    *,
    symbol: str,
    action: Mapping[str, Any],
    mark: Decimal,
    decision_at: str,
) -> PortfolioState:
    action_type = str(action["action_type"])
    required = LotRole.CORE if action_type == "TRAIL_CORE" else None
    lots = _eligible_action_lots(
        portfolio, symbol=symbol, action=action, required_role=required
    )
    if len(lots) != 1:
        raise SingleAgentResearchError("PROTECTION_ACTION_REQUIRES_ONE_LOT")
    lot = lots[0]
    stop = _d(action.get("stop_price"), "PROTECTION_STOP_INVALID")
    if (lot.side is LotSide.LONG and stop >= mark) or (lot.side is LotSide.SHORT and stop <= mark):
        raise SingleAgentResearchError("PROTECTION_STOP_MARK_INVALID")
    if lot.stop_price is not None:
        if lot.side is LotSide.LONG and stop < lot.stop_price:
            raise SingleAgentResearchError("PROTECTION_STOP_MONOTONICITY_VIOLATION")
        if lot.side is LotSide.SHORT and stop > lot.stop_price:
            raise SingleAgentResearchError("PROTECTION_STOP_MONOTONICITY_VIOLATION")
    changes: dict[str, Any] = {"stop_price": stop}
    contract = copy.deepcopy(lot_contracts.get(lot.lot_id, {}))
    checkpoint_value = action.get("management_checkpoint")
    if lot.role is LotRole.CORE:
        if action_type == "SET_PROTECTION" and checkpoint_value is None and contract.get("management_checkpoint") is None:
            raise SingleAgentResearchError("CORE_MANAGEMENT_CHECKPOINT_REQUIRED")
        if checkpoint_value is not None:
            checkpoint = _d(checkpoint_value, "CORE_MANAGEMENT_CHECKPOINT_INVALID")
            if (lot.side is LotSide.LONG and checkpoint <= mark) or (
                lot.side is LotSide.SHORT and checkpoint >= mark
            ):
                raise SingleAgentResearchError("CORE_MANAGEMENT_CHECKPOINT_INVALID")
            contract["management_checkpoint"] = canonical_decimal(checkpoint)
            contract["management_checkpoint_id"] = str(
                action.get("management_checkpoint_id")
                or f"{action['action_id']}:checkpoint"
            )
            contract["checkpoint_event_ids"] = []
    elif action_type == "SET_PROTECTION":
        target_value = action.get("tactical_target")
        if target_value is None:
            raise SingleAgentResearchError("TACTICAL_TARGET_REQUIRED")
        target = _d(target_value, "TACTICAL_TARGET_INVALID")
        if (lot.side is LotSide.LONG and target <= mark) or (
            lot.side is LotSide.SHORT and target >= mark
        ):
            raise SingleAgentResearchError("TACTICAL_TARGET_INVALID")
        changes["target_price"] = target
    contract["protection_active_from"] = decision_at
    contract["max_horizon_at"] = action.get("max_horizon_at") or contract.get("max_horizon_at")
    lot_contracts[lot.lot_id] = contract
    return _replace_portfolio_lot(portfolio, lot.lot_id, **changes)


def _apply_new_risk_action(
    portfolio: PortfolioState,
    lot_contracts: dict[str, dict[str, Any]],
    orders: Sequence[Mapping[str, Any]],
    *,
    state: Mapping[str, Any],
    episode: Mapping[str, Any],
    symbol: str,
    action: Mapping[str, Any],
    mark: Decimal,
    marks: Mapping[str, Decimal],
    decision_at: str,
    policy: Mapping[str, Decimal],
) -> tuple[PortfolioState, dict[str, Any], list[str]]:
    action_type = str(action["action_type"])
    role = LotRole.CORE if action_type in {"OPEN_CORE", "ADD_CORE", "REENTER_CORE"} else LotRole.TACTICAL
    try:
        side = LotSide(str(action.get("side") or episode["primary_direction"]))
    except ValueError as exc:
        raise SingleAgentResearchError("ACTION_SIDE_INVALID") from exc
    notional = _d(action.get("notional_usdt"), "ACTION_NOTIONAL_INVALID")
    stop = _d(action.get("stop_price"), "ACTION_STOP_INVALID")
    reward = _d(action.get("reward_checkpoint"), "ACTION_REWARD_CHECKPOINT_INVALID")
    geometry = _entry_geometry(
        side=side,
        reference=mark,
        notional=notional,
        stop=stop,
        reward_checkpoint=reward,
        policy=policy,
    )
    vetoes = _new_risk_vetoes(
        portfolio=portfolio,
        orders=orders,
        state=state,
        marks=marks,
        marked_at=_ts(decision_at),
        symbol=symbol,
        notional=notional,
        geometry=geometry,
        risk_class=str(action.get("risk_class") or "STANDARD"),
        policy=policy,
    )
    result = {
        "entry_price": canonical_decimal(geometry["entry"]),
        "quantity": canonical_decimal(geometry["quantity"]),
        "planned_net_loss_usdt": canonical_decimal(geometry["net_loss"]),
        "planned_net_reward_usdt": canonical_decimal(geometry["net_reward"]),
        "planned_net_reward_risk": canonical_decimal(geometry["net_reward_risk"]),
        "risk_vetoes": vetoes,
    }
    if vetoes:
        return portfolio, result, vetoes
    lot_id = f"{state['run_id']}:cycle-{int(state['cycle_index']):04d}:{action['action_id']}"
    geometry_id = str(action.get("geometry_id") or "")
    if not geometry_id:
        raise SingleAgentResearchError("ACTION_GEOMETRY_ID_REQUIRED")
    lot = OfflineLot(
        lot_id=lot_id,
        instrument_id=symbol,
        side=side,
        role=role,
        attribution=Attribution.STRATEGY,
        quantity=geometry["quantity"],
        remaining_quantity=geometry["quantity"],
        entry_price=geometry["entry"],
        stop_price=stop,
        target_price=reward if role is LotRole.TACTICAL else None,
        opened_at=_ts(decision_at),
        episode_id=str(episode["episode_id"]),
        stage_id=f"{episode['episode_id']}:cycle-{int(state['cycle_index']):04d}",
        geometry_id=geometry_id,
    )
    portfolio = open_lot(
        portfolio,
        lot=lot,
        fee_rate=policy["taker_fee_rate"],
        fill_id=f"{lot_id}:entry",
        charge_entry_fee=True,
    )
    lot_contracts[lot_id] = {
        "lot_id": lot_id,
        "episode_id": episode["episode_id"],
        "role": role.value,
        "exit_intent": "TACTICAL_TARGET" if role is LotRole.TACTICAL else "CORE_DYNAMIC_MANAGEMENT",
        "risk_budget_usdt": canonical_decimal(geometry["net_loss"]),
        "management_checkpoint": canonical_decimal(reward) if role is LotRole.CORE else None,
        "management_checkpoint_id": (
            str(action.get("management_checkpoint_id") or f"{action['action_id']}:checkpoint")
            if role is LotRole.CORE
            else None
        ),
        "max_horizon_at": action.get("max_horizon_at"),
        "protection_active_from": decision_at,
        "geometry_id": geometry_id,
        "checkpoint_event_ids": [],
    }
    result["lot_id"] = lot_id
    return portfolio, result, []


def _apply_order_action(
    portfolio: PortfolioState,
    orders: list[dict[str, Any]],
    *,
    state: Mapping[str, Any],
    episode: Mapping[str, Any],
    symbol: str,
    action: Mapping[str, Any],
    marks: Mapping[str, Decimal],
    decision_at: str,
    policy: Mapping[str, Decimal],
) -> tuple[PortfolioState, dict[str, Any], list[str]]:
    order_id = str(action.get("order_id") or "")
    matches = [row for row in orders if row["order_id"] == order_id and row["symbol"] == symbol]
    if len(matches) != 1 or matches[0]["status"] != "REVIEW_REQUIRED":
        raise SingleAgentResearchError("ORDER_REVIEW_ACTION_INVALID")
    order = matches[0]
    if action["action_type"] == "CANCEL_ORDER":
        order["status"] = "CANCELLED_BY_SINGLE_AGENT_REVIEW"
        order["resolved_at"] = decision_at
        order["resolution_reason"] = action["reason"]
        return portfolio, {"order_id": order_id, "order_status": order["status"]}, []
    if action["action_type"] != "ACTIVATE_ORDER":
        raise SingleAgentResearchError("ORDER_REVIEW_ACTION_INVALID")
    geometry_id = str(action.get("geometry_id") or "")
    if not geometry_id:
        raise SingleAgentResearchError("ACTION_GEOMETRY_ID_REQUIRED")
    order["episode_id"] = episode["episode_id"]
    order["geometry_id"] = geometry_id
    order["active_from"] = decision_at
    if order["side"] == "BUY":
        try:
            role = LotRole(str(action.get("role") or ""))
        except ValueError as exc:
            raise SingleAgentResearchError("ACTION_ROLE_INVALID") from exc
        if role not in {LotRole.CORE, LotRole.TACTICAL}:
            raise SingleAgentResearchError("ACTION_ROLE_INVALID")
        stop = _d(action.get("stop_price"), "ACTION_STOP_INVALID")
        reward = _d(action.get("reward_checkpoint"), "ACTION_REWARD_CHECKPOINT_INVALID")
        notional = _d(order["notional_usdt"], "ORDER_INVALID")
        limit = _d(order["limit_price"], "ORDER_INVALID")
        geometry = _entry_geometry(
            side=LotSide.LONG,
            reference=limit,
            notional=notional,
            stop=stop,
            reward_checkpoint=reward,
            policy=policy,
            maker_entry=True,
        )
        vetoes = _new_risk_vetoes(
            portfolio=portfolio,
            orders=orders,
            state=state,
            marks=marks,
            marked_at=_ts(decision_at),
            symbol=symbol,
            notional=notional,
            geometry=geometry,
            risk_class=str(action.get("risk_class") or "STANDARD"),
            policy=policy,
        )
        result = {
            "order_id": order_id,
            "planned_net_loss_usdt": canonical_decimal(geometry["net_loss"]),
            "planned_net_reward_usdt": canonical_decimal(geometry["net_reward"]),
            "planned_net_reward_risk": canonical_decimal(geometry["net_reward_risk"]),
            "risk_vetoes": vetoes,
        }
        if vetoes:
            order["episode_id"] = None
            order["geometry_id"] = None
            order["active_from"] = None
            return portfolio, result, vetoes
        order["role"] = role.value
        order["stop_price"] = canonical_decimal(stop)
        order["target_price"] = canonical_decimal(reward) if role is LotRole.TACTICAL else None
        order["management_checkpoint"] = canonical_decimal(reward) if role is LotRole.CORE else None
        order["management_checkpoint_id"] = (
            str(action.get("management_checkpoint_id") or f"{action['action_id']}:checkpoint")
            if role is LotRole.CORE
            else None
        )
        order["risk_budget_usdt"] = canonical_decimal(geometry["net_loss"])
        order["max_horizon_at"] = action.get("max_horizon_at")
        order["status"] = "ACTIVE"
        result["order_status"] = "ACTIVE"
        return portfolio, result, []
    if order["side"] == "SELL":
        if not _open_lots(portfolio, symbol):
            raise SingleAgentResearchError("REDUCE_ORDER_WITHOUT_POSITION")
        order["role"] = str(action.get("role") or "ALL")
        order["status"] = "ACTIVE"
        order["risk_budget_usdt"] = "0"
        return portfolio, {"order_id": order_id, "order_status": "ACTIVE"}, []
    raise SingleAgentResearchError("ORDER_SIDE_INVALID")


def _reentry_contract_from_action(
    action: Mapping[str, Any],
    *,
    episode: Mapping[str, Any],
    symbol: str,
    decision_at: str,
    exit_price: Decimal,
) -> dict[str, Any]:
    plan = action.get("reentry_plan")
    if not isinstance(plan, Mapping):
        raise SingleAgentResearchError("REENTRY_CONTRACT_REQUIRED")
    review_by = _review_time(plan.get("review_by"), decision_at)
    required = _string_list(
        plan.get("required_observations", []), "REENTRY_CONTRACT_INVALID", allow_empty=False
    )
    invalidators = _string_list(
        plan.get("cancel_invalidators", []), "REENTRY_CONTRACT_INVALID", allow_empty=False
    )
    return self_digest(
        {
            "contract_id": str(plan.get("contract_id") or f"{episode['episode_id']}:reentry:{decision_at}"),
            "episode_id": episode["episode_id"],
            "symbol": symbol,
            "status": "PENDING_AGENT_REVIEW",
            "created_at": decision_at,
            "exit_price": canonical_decimal(exit_price),
            "exit_reason": action["reason"],
            "thesis_status_at_exit": episode["strategic_status"],
            "required_review_at": review_by,
            "evidence_to_reenter": required,
            "evidence_to_cancel": invalidators,
            "last_review_at": None,
            "resolution": None,
        },
        "reentry_digest",
    )


def _apply_reduction_action(
    portfolio: PortfolioState,
    *,
    episode: Mapping[str, Any],
    symbol: str,
    action: Mapping[str, Any],
    mark: Decimal,
    decision_at: str,
    policy: Mapping[str, Decimal],
) -> tuple[PortfolioState, dict[str, Any], dict[str, Any] | None]:
    action_type = str(action["action_type"])
    required_role = None
    if action_type == "REDUCE_CORE":
        required_role = LotRole.CORE
    elif action_type in {"REDUCE_TACTICAL", "EXIT_TACTICAL"}:
        required_role = LotRole.TACTICAL
    lots = _eligible_action_lots(
        portfolio, symbol=symbol, action=action, required_role=required_role
    )
    fraction = _d(action.get("fraction", "1"), "ACTION_FRACTION_INVALID")
    if fraction <= ZERO or fraction > ONE:
        raise SingleAgentResearchError("ACTION_FRACTION_INVALID")
    if action_type in {"REDUCE_CORE", "REDUCE_TACTICAL", "PARTIAL_TAKE_PROFIT"} and fraction >= ONE:
        raise SingleAgentResearchError("PARTIAL_ACTION_CANNOT_FULL_EXIT")
    if action_type in {"EXIT_TACTICAL", "EXIT_WITH_REENTRY", "EXIT_STRATEGIC"} and fraction != ONE:
        raise SingleAgentResearchError("EXIT_ACTION_REQUIRES_FULL_FRACTION")
    if action_type == "EXIT_STRATEGIC" and episode["strategic_status"] not in {"INVALIDATED", "CLOSED"}:
        raise SingleAgentResearchError("STRATEGIC_EXIT_WITHOUT_INVALIDATION")
    closed: list[dict[str, Any]] = []
    current = portfolio
    for original in lots:
        lot = next(item for item in current.lots if item.lot_id == original.lot_id)
        quantity = lot.remaining_quantity * fraction
        price = _market_fill(mark, lot.side, opening=False, bps=policy["market_slippage_bps"])
        current = _close_quantity(
            current,
            lot=lot,
            quantity=quantity,
            price=price,
            fee_rate=policy["taker_fee_rate"],
            occurred_at=_ts(decision_at),
            reason=f"SINGLE_AGENT_{action_type}",
            fill_id=f"{action['action_id']}:{lot.lot_id}:exit",
        )
        closed.append(
            {
                "lot_id": lot.lot_id,
                "role": lot.role.value,
                "quantity": canonical_decimal(quantity),
                "fill_price": canonical_decimal(price),
            }
        )
    reentry = None
    if action_type == "EXIT_WITH_REENTRY":
        reentry = _reentry_contract_from_action(
            action,
            episode=episode,
            symbol=symbol,
            decision_at=decision_at,
            exit_price=mark,
        )
    return current, {"closed": closed}, reentry


def _resolve_episode_exposure(
    episode: Mapping[str, Any],
    *,
    portfolio: PortfolioState,
    symbol: str,
    decision_at: str,
    wait_actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    current = copy.deepcopy(dict(episode))
    current.pop("episode_digest", None)
    open_lots = _open_lots(portfolio, symbol)
    core = [lot for lot in open_lots if lot.role is LotRole.CORE]
    tactical = [lot for lot in open_lots if lot.role is LotRole.TACTICAL]
    reentry = current.get("reentry_contract")
    if current["strategic_status"] in {"INVALIDATED", "CLOSED"}:
        current["exposure_status"] = "CLOSED" if not open_lots else "EXIT_IN_PROGRESS"
        if isinstance(reentry, Mapping) and reentry.get("status") == "PENDING_AGENT_REVIEW":
            updated = copy.deepcopy(dict(reentry))
            updated.pop("reentry_digest", None)
            updated["status"] = "CANCELLED_BY_STRATEGIC_INVALIDATION"
            updated["last_review_at"] = decision_at
            updated["resolution"] = current["strategic_status"]
            current["reentry_contract"] = self_digest(updated, "reentry_digest")
    elif core:
        current["exposure_status"] = "EXPOSED_CORE"
    elif tactical:
        current["exposure_status"] = "EXPOSED_TACTICAL_ONLY"
    elif isinstance(reentry, Mapping) and reentry.get("status") == "PENDING_AGENT_REVIEW":
        current["exposure_status"] = "FLAT_REENTRY_PENDING"
        if wait_actions:
            wait = wait_actions[-1]
            updated = copy.deepcopy(dict(reentry))
            updated.pop("reentry_digest", None)
            updated["last_review_at"] = decision_at
            updated["required_review_at"] = _review_time(wait.get("review_by"), decision_at)
            updated["evidence_to_reenter"] = _string_list(
                wait.get("required_observations", []), "WAIT_OBLIGATION_INVALID", allow_empty=False
            )
            current["reentry_contract"] = self_digest(updated, "reentry_digest")
    else:
        current["exposure_status"] = "FLAT_WATCH"
    return self_digest(current, "episode_digest")


def _ordered_selected_actions(
    decision: Mapping[str, Any],
) -> list[tuple[str, Mapping[str, Any]]]:
    """Apply portfolio protection before any other action in one decision.

    A multi-symbol decision is atomic at one decision timestamp.  New-risk
    checks must therefore see protection established elsewhere in that same
    decision, rather than depend on SYMBOLS iteration order.  Relative order is
    retained inside the protection phase and inside the remaining phase.
    """

    protection_types = {"SET_PROTECTION", "MOVE_STOP", "TRAIL_CORE"}
    protection: list[tuple[str, Mapping[str, Any]]] = []
    remaining: list[tuple[str, Mapping[str, Any]]] = []
    for symbol in SYMBOLS:
        for action in decision["symbol_decisions"][symbol]["selected_actions"]:
            row = (symbol, action)
            if action["action_type"] in protection_types:
                protection.append(row)
            else:
                remaining.append(row)
    return protection + remaining


def _tactical_reentry_exit_time(
    portfolio: PortfolioState,
    *,
    symbol: str,
    episode_id: str,
) -> datetime:
    if any(
        lot.role is LotRole.TACTICAL for lot in _open_lots(portfolio, symbol)
    ):
        raise SingleAgentResearchError("TACTICAL_REENTRY_WHILE_TACTICAL_OPEN")
    closed_tactical_ids = {
        lot.lot_id
        for lot in portfolio.lots
        if lot.instrument_id == symbol
        and lot.episode_id == episode_id
        and lot.role is LotRole.TACTICAL
        and lot.remaining_quantity <= ZERO
    }
    exit_times = [
        fill.occurred_at
        for fill in portfolio.fills
        if fill.lot_id in closed_tactical_ids and fill.side == "SELL"
    ]
    if not exit_times:
        raise SingleAgentResearchError(
            "REENTER_TACTICAL_WITHOUT_PRIOR_TACTICAL_EXIT"
        )
    return max(exit_times)


def _apply_agent_decision(
    pre_state: Mapping[str, Any],
    decision: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = copy.deepcopy(dict(pre_state))
    portfolio = _portfolio_from_document(state["portfolio"])
    lot_contracts = copy.deepcopy(dict(state["lot_contracts"]))
    orders = copy.deepcopy(list(state["orders"]))
    previous_episodes = copy.deepcopy(dict(state["episodes"]))
    episodes: dict[str, dict[str, Any]] = {}
    action_results: list[dict[str, Any]] = []
    policy = _risk_policy(manifest)
    marks = _marks(context)
    decision_at = str(decision["decision_at"])
    reentry_delays = copy.deepcopy(list(state["reentry_delays_hours"]))

    for symbol in SYMBOLS:
        symbol_decision = decision["symbol_decisions"][symbol]
        previous = previous_episodes.get(symbol)
        episodes[symbol] = _episode_from_assessment(
            symbol_decision["strategic_assessment"],
            previous=previous if isinstance(previous, Mapping) else None,
            sentiment=symbol_decision["sentiment_assessment"],
            evidence_update=symbol_decision["evidence_update"],
        )

    for symbol, action in _ordered_selected_actions(decision):
        episode = episodes[symbol]
        action_type = action["action_type"]
        result: dict[str, Any] = {
            "symbol": symbol,
            "action_id": action["action_id"],
            "action_type": action_type,
            "selected_by_agent": True,
            "status": "APPLIED",
            "risk_vetoes": [],
        }
        if action_type in {"HOLD", "WAIT"}:
            result["effect"] = "NO_POSITION_MUTATION"
        elif action_type in {"SET_PROTECTION", "MOVE_STOP", "TRAIL_CORE"}:
            portfolio = _apply_protection_action(
                portfolio,
                lot_contracts,
                symbol=symbol,
                action=action,
                mark=marks[symbol],
                decision_at=decision_at,
            )
        elif action_type in NEW_RISK_ACTIONS:
            if episode["strategic_status"] not in {"ACTIVE", "CHALLENGED"}:
                raise SingleAgentResearchError("NEW_RISK_WITHOUT_ACTIVE_EPISODE")
            prior_contract = episode.get("reentry_contract")
            tactical_exit_at: datetime | None = None
            if action_type == "REENTER_TACTICAL":
                tactical_exit_at = _tactical_reentry_exit_time(
                    portfolio,
                    symbol=symbol,
                    episode_id=str(episode["episode_id"]),
                )
            portfolio, detail, vetoes = _apply_new_risk_action(
                portfolio,
                lot_contracts,
                orders,
                state=state,
                episode=episode,
                symbol=symbol,
                action=action,
                mark=marks[symbol],
                marks=marks,
                decision_at=decision_at,
                policy=policy,
            )
            result.update(detail)
            if vetoes:
                result["status"] = "REJECTED_BY_RISK_KERNEL"
                result["risk_vetoes"] = vetoes
            elif action_type == "REENTER_CORE":
                if not isinstance(prior_contract, Mapping) or prior_contract.get("status") != "PENDING_AGENT_REVIEW":
                    raise SingleAgentResearchError("REENTER_WITHOUT_PENDING_CONTRACT")
                updated = copy.deepcopy(dict(prior_contract))
                updated.pop("reentry_digest", None)
                updated["status"] = "FULFILLED"
                updated["last_review_at"] = decision_at
                updated["resolution"] = action["action_id"]
                episode = copy.deepcopy(dict(episode))
                episode.pop("episode_digest", None)
                episode["reentry_contract"] = self_digest(updated, "reentry_digest")
                episode = self_digest(episode, "episode_digest")
                episodes[symbol] = episode
                delay = (_ts(decision_at) - _ts(str(prior_contract["created_at"]))).total_seconds() / 3600
                reentry_delays.append(canonical_decimal(Decimal(str(delay))))
            elif action_type == "REENTER_TACTICAL":
                assert tactical_exit_at is not None
                delay = (
                    _ts(decision_at) - tactical_exit_at
                ).total_seconds() / 3600
                reentry_delays.append(canonical_decimal(Decimal(str(delay))))
                result["reentry_role"] = "TACTICAL"
                result["reentry_delay_hours"] = canonical_decimal(
                    Decimal(str(delay))
                )
                if (
                    isinstance(prior_contract, Mapping)
                    and prior_contract.get("status") == "PENDING_AGENT_REVIEW"
                ):
                    updated = copy.deepcopy(dict(prior_contract))
                    updated.pop("reentry_digest", None)
                    updated["last_review_at"] = decision_at
                    updated["resolution"] = (
                        f"PARTIAL_TACTICAL_RESTORATION:{action['action_id']}"
                    )
                    episode = copy.deepcopy(dict(episode))
                    episode.pop("episode_digest", None)
                    episode["reentry_contract"] = self_digest(
                        updated, "reentry_digest"
                    )
                    episode = self_digest(episode, "episode_digest")
                    episodes[symbol] = episode
        elif action_type in REDUCTION_ACTIONS:
            portfolio, detail, reentry = _apply_reduction_action(
                portfolio,
                episode=episode,
                symbol=symbol,
                action=action,
                mark=marks[symbol],
                decision_at=decision_at,
                policy=policy,
            )
            result.update(detail)
            if reentry is not None:
                episode = copy.deepcopy(dict(episode))
                episode.pop("episode_digest", None)
                episode["reentry_contract"] = reentry
                episode = self_digest(episode, "episode_digest")
                episodes[symbol] = episode
        elif action_type in {"CANCEL_ORDER", "ACTIVATE_ORDER"}:
            portfolio, detail, vetoes = _apply_order_action(
                portfolio,
                orders,
                state=state,
                episode=episode,
                symbol=symbol,
                action=action,
                marks=marks,
                decision_at=decision_at,
                policy=policy,
            )
            result.update(detail)
            if vetoes:
                result["status"] = "REJECTED_BY_RISK_KERNEL"
                result["risk_vetoes"] = vetoes
        else:
            raise SingleAgentResearchError("ACTION_TYPE_UNREACHABLE")
        action_results.append(result)

    if int(decision["cycle_index"]) == 1:
        unresolved = [row["order_id"] for row in orders if row["status"] == "REVIEW_REQUIRED"]
        if unresolved:
            raise SingleAgentResearchError("INITIAL_ORDER_REVIEW_INCOMPLETE")
        unprotected = [lot.lot_id for lot in _open_lots(portfolio) if lot.stop_price is None]
        if unprotected:
            raise SingleAgentResearchError("INITIAL_POSITION_PROTECTION_INCOMPLETE")

    for symbol in SYMBOLS:
        symbol_actions = decision["symbol_decisions"][symbol]["selected_actions"]
        wait_actions = [item for item in symbol_actions if item["action_type"] == "WAIT"]
        prior_had_core = any(
            lot.instrument_id == symbol
            and lot.role is LotRole.CORE
            and lot.remaining_quantity > ZERO
            for lot in _portfolio_from_document(pre_state["portfolio"]).lots
        )
        now_has_core = any(lot.role is LotRole.CORE for lot in _open_lots(portfolio, symbol))
        episode = episodes[symbol]
        if (
            prior_had_core
            and not now_has_core
            and episode["strategic_status"] in {"ACTIVE", "CHALLENGED"}
            and not isinstance(episode.get("reentry_contract"), Mapping)
        ):
            raise SingleAgentResearchError("CORE_EXIT_WITHOUT_REENTRY_OBLIGATION")
        episodes[symbol] = _resolve_episode_exposure(
            episode,
            portfolio=portfolio,
            symbol=symbol,
            decision_at=decision_at,
            wait_actions=wait_actions,
        )

    for lot in _open_lots(portfolio):
        contract = lot_contracts.get(lot.lot_id)
        if not isinstance(contract, dict):
            raise SingleAgentResearchError("OPEN_LOT_CONTRACT_MISSING")
        if lot.stop_price is None:
            contract["risk_budget_usdt"] = None
        else:
            adverse = (
                max(lot.entry_price - lot.stop_price, ZERO)
                if lot.side is LotSide.LONG
                else max(lot.stop_price - lot.entry_price, ZERO)
            ) * lot.remaining_quantity * lot.contract_multiplier
            contract["risk_budget_usdt"] = canonical_decimal(adverse)
            if (
                lot.role is LotRole.CORE
                and contract.get("exit_intent") == "EXOGENOUS_RECONCILIATION_REQUIRED"
            ):
                contract["exit_intent"] = "CORE_DYNAMIC_MANAGEMENT"

    snapshot = mark_portfolio(
        portfolio, marks=marks, marked_at=_ts(decision_at)
    )
    funding = (
        None
        if state.get("funding_usdt") is None
        else _d(state.get("funding_usdt"), "STATE_FUNDING_INVALID")
    )
    effective_equity = snapshot.equity if funding is None else snapshot.equity + funding
    effective_net_pnl = snapshot.net_pnl if funding is None else snapshot.net_pnl + funding
    old_peak = _d(state["peak_equity_usdt"], "STATE_EQUITY_INVALID")
    peak = max(old_peak, effective_equity)
    curve = copy.deepcopy(list(state["equity_curve"]))
    curve.append(
        {
            "cycle_index": int(decision["cycle_index"]),
            "marked_at": decision_at,
            "equity_before_unknown_funding_usdt": canonical_decimal(snapshot.equity),
            "net_pnl_before_unknown_funding_usdt": canonical_decimal(snapshot.net_pnl),
            "equity_after_observed_funding_usdt": (
                None if funding is None else canonical_decimal(effective_equity)
            ),
            "net_pnl_after_observed_funding_usdt": (
                None if funding is None else canonical_decimal(effective_net_pnl)
            ),
            "funding_usdt": None if funding is None else canonical_decimal(funding),
            "gross_notional_usdt": canonical_decimal(snapshot.gross_notional),
        }
    )
    state["revision"] = int(pre_state["revision"]) + 1
    state["previous_state_digest"] = pre_state["state_digest"]
    state["accepted_at"] = decision_at
    state["state_stage"] = "ACCEPTED_AFTER_SINGLE_AGENT_DECISION"
    state["portfolio"] = _portfolio_document(portfolio)
    state["lot_contracts"] = lot_contracts
    state["orders"] = orders
    state["episodes"] = episodes
    state["peak_equity_usdt"] = canonical_decimal(peak)
    state["equity_curve"] = curve
    state["reentry_delays_hours"] = reentry_delays
    state["last_decision_digest"] = decision["decision_digest"]
    state["last_action_results"] = action_results
    cost_aware_open_risk, _ = _current_open_risk(
        portfolio, marks=marks, policy=policy
    )
    state["post_decision_snapshot"] = _snapshot_document(
        snapshot,
        funding_usdt=funding,
        cost_aware_open_risk_usdt=cost_aware_open_risk,
    )
    state["risk_snapshot"] = _risk_summary(
        portfolio,
        marks=marks,
        marked_at=_ts(decision_at),
        state=state,
        policy=policy,
    )
    state.pop("state_digest", None)
    return self_digest(state, "state_digest"), action_results


def accept_research_decision(
    *,
    run_root: Path,
    decision_path: Path,
) -> dict[str, Any]:
    root, manifest, checkpoint = _run_documents(run_root)
    if checkpoint.get("status") != "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED":
        raise SingleAgentResearchError("RUN_NOT_AWAITING_DECISION")
    cycle_index = int(checkpoint["next_cycle_index"])
    agent_context = _load_verified(
        root / str(checkpoint["pending_agent_context_path"]), "agent_context_digest"
    )
    pre_state = _load_verified(
        root / str(checkpoint["pending_pre_decision_state_path"]), "state_digest"
    )
    raw_decision = load_json_strict(decision_path)
    decision = _normalize_agent_decision(
        raw_decision, agent_context=agent_context, pre_state=pre_state
    )
    context = _load_verified(
        root / "market-contexts" / f"cycle-{cycle_index:04d}.json", "context_digest"
    )
    accepted_state, action_results = _apply_agent_decision(
        pre_state, decision, context, manifest=manifest
    )
    decision_target = root / "agent-decisions" / f"cycle-{cycle_index:04d}.json"
    state_target = root / "states" / f"state-{cycle_index:04d}-accepted.json"
    write_once_json(decision_target, decision)
    write_once_json(state_target, accepted_state)
    receipt = self_digest(
        {
            "schema_id": "single_agent_cycle_receipt",
            "schema_version": "1.0.0",
            "run_id": manifest["run_id"],
            "cycle_index": cycle_index,
            "decision_at": decision["decision_at"],
            "agent_context_digest": agent_context["agent_context_digest"],
            "pre_decision_state_digest": pre_state["state_digest"],
            "decision_digest": decision["decision_digest"],
            "accepted_state_digest": accepted_state["state_digest"],
            "action_results": action_results,
            "funding_status": accepted_state.get("funding_status"),
            "funding_usdt": accepted_state.get("funding_usdt"),
            "recorded_v1_decisions_opened": False,
            "recorded_v1_outcomes_opened": False,
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "receipt_digest",
    )
    receipt_target = root / "receipts" / f"cycle-{cycle_index:04d}.json"
    write_once_json(receipt_target, receipt)
    checkpoint["status"] = "RUNNING_OUTCOMES_SEALED"
    checkpoint["completed_cycles"] = cycle_index
    checkpoint["next_cycle_index"] = cycle_index + 1
    checkpoint["accepted_state_path"] = state_target.relative_to(root).as_posix()
    checkpoint["accepted_state_digest"] = accepted_state["state_digest"]
    checkpoint["pending_agent_context_path"] = None
    checkpoint["pending_pre_decision_state_path"] = None
    _write_atomic_json(root / "checkpoint.json", checkpoint)
    return receipt


def finalize_research_run(*, run_root: Path) -> dict[str, Any]:
    root, manifest, checkpoint = _run_documents(run_root)
    if checkpoint.get("status") != "RUNNING_OUTCOMES_SEALED":
        raise SingleAgentResearchError("RUN_NOT_FINALIZABLE")
    if int(checkpoint.get("completed_cycles", 0)) != 24 or int(checkpoint.get("next_cycle_index", 0)) != 25:
        raise SingleAgentResearchError("RUN_NOT_FINALIZABLE")
    state = _load_verified(root / str(checkpoint["accepted_state_path"]), "state_digest")
    context = _load_verified(root / "market-contexts" / "cycle-0025.json", "context_digest")
    policy = _risk_policy(manifest)
    terminal, events = _process_bars(state, context, policy=policy)
    portfolio = _portfolio_from_document(terminal["portfolio"])
    marks = _marks(context)
    snapshot = mark_portfolio(
        portfolio, marks=marks, marked_at=_ts(str(context["decision_at"]))
    )
    funding = (
        None
        if terminal.get("funding_usdt") is None
        else _d(terminal.get("funding_usdt"), "STATE_FUNDING_INVALID")
    )
    effective_equity = snapshot.equity if funding is None else snapshot.equity + funding
    effective_net_pnl = snapshot.net_pnl if funding is None else snapshot.net_pnl + funding
    curve = copy.deepcopy(list(terminal["equity_curve"]))
    curve.append(
        {
            "cycle_index": 25,
            "marked_at": context["decision_at"],
            "equity_before_unknown_funding_usdt": canonical_decimal(snapshot.equity),
            "net_pnl_before_unknown_funding_usdt": canonical_decimal(snapshot.net_pnl),
            "equity_after_observed_funding_usdt": (
                None if funding is None else canonical_decimal(effective_equity)
            ),
            "net_pnl_after_observed_funding_usdt": (
                None if funding is None else canonical_decimal(effective_net_pnl)
            ),
            "funding_usdt": None if funding is None else canonical_decimal(funding),
            "gross_notional_usdt": canonical_decimal(snapshot.gross_notional),
            "terminal_observation": True,
        }
    )
    terminal["revision"] = int(state["revision"]) + 1
    terminal["previous_state_digest"] = state["state_digest"]
    terminal["accepted_at"] = str(context["decision_at"])
    terminal["state_stage"] = "TERMINAL_AFTER_FINAL_BAR_REPLAY"
    terminal["cycle_index"] = 25
    terminal["terminal_bar_replay_events"] = events
    terminal["peak_equity_usdt"] = canonical_decimal(
        max(_d(state["peak_equity_usdt"], "STATE_EQUITY_INVALID"), effective_equity)
    )
    terminal["equity_curve"] = curve
    cost_aware_open_risk, _ = _current_open_risk(
        portfolio, marks=marks, policy=policy
    )
    terminal["terminal_snapshot"] = _snapshot_document(
        snapshot,
        funding_usdt=funding,
        cost_aware_open_risk_usdt=cost_aware_open_risk,
    )
    terminal.pop("state_digest", None)
    terminal = self_digest(terminal, "state_digest")
    terminal_path = root / "states" / "state-0025-terminal.json"
    write_once_json(terminal_path, terminal)
    receipt = self_digest(
        {
            "schema_id": "single_agent_terminal_receipt",
            "schema_version": "1.0.0",
            "run_id": manifest["run_id"],
            "completed_decision_cycles": 24,
            "terminal_observation_cycle": 25,
            "terminal_at": context["decision_at"],
            "prior_accepted_state_digest": state["state_digest"],
            "terminal_market_context_digest": context["context_digest"],
            "terminal_state_digest": terminal["state_digest"],
            "terminal_bar_replay_events": events,
            "recorded_v1_decisions_opened": False,
            "recorded_v1_outcomes_opened": False,
            "funding_status": terminal.get("funding_status"),
            "funding_usdt": terminal.get("funding_usdt"),
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        },
        "terminal_receipt_digest",
    )
    receipt_path = root / "receipts" / "terminal.json"
    write_once_json(receipt_path, receipt)
    checkpoint["status"] = "TERMINAL_OUTCOMES_SEALED"
    checkpoint["next_cycle_index"] = 25
    checkpoint["accepted_state_path"] = terminal_path.relative_to(root).as_posix()
    checkpoint["accepted_state_digest"] = terminal["state_digest"]
    checkpoint["terminal_receipt_path"] = receipt_path.relative_to(root).as_posix()
    _write_atomic_json(root / "checkpoint.json", checkpoint)
    return receipt


def _maximum_drawdown(
    curve: Sequence[Mapping[str, Any]], *, initial_equity: Decimal
) -> Decimal:
    peak = initial_equity
    maximum = ZERO
    for row in curve:
        equity = _d(row["equity_before_unknown_funding_usdt"], "EQUITY_CURVE_INVALID")
        peak = max(peak, equity)
        if peak > ZERO:
            maximum = max(maximum, (peak - equity) / peak)
    return maximum


def _flat_exposure_metrics(states: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for symbol in SYMBOLS:
        total_hours = ZERO
        longest = ZERO
        current_start: datetime | None = None
        previous_time: datetime | None = None
        for state in states:
            now = _ts(str(state["accepted_at"]))
            portfolio = _portfolio_from_document(state["portfolio"])
            exposed = bool(_open_lots(portfolio, symbol))
            if not exposed and current_start is None:
                current_start = now
            if exposed and current_start is not None:
                duration = Decimal(str((now - current_start).total_seconds() / 3600))
                total_hours += duration
                longest = max(longest, duration)
                current_start = None
            previous_time = now
        if current_start is not None and previous_time is not None:
            duration = Decimal(str((previous_time - current_start).total_seconds() / 3600))
            total_hours += duration
            longest = max(longest, duration)
        by_symbol[symbol] = {
            "flat_hours": canonical_decimal(total_hours),
            "longest_flat_hours": canonical_decimal(longest),
        }
    return by_symbol


def _path_capture_metrics(
    states: Sequence[Mapping[str, Any]],
    contexts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    correct = 0
    captured = 0
    total = 0
    neutral = 0
    neutral_positive = 0
    neutral_negative = 0
    neutral_positive_sum = ZERO
    neutral_negative_sum = ZERO
    flat_positive = 0
    flat_negative = 0
    flat_positive_sum = ZERO
    flat_negative_sum = ZERO
    by_symbol: dict[str, dict[str, Any]] = {
        symbol: {
            "directional_opportunities": 0,
            "captured_with_aligned_exposure": 0,
            "neutral_primary_cycles": 0,
            "neutral_positive_cycles": 0,
            "neutral_negative_cycles": 0,
            "neutral_positive_return_sum_pct": "0",
            "neutral_negative_return_sum_pct": "0",
            "flat_positive_cycles": 0,
            "flat_negative_cycles": 0,
            "flat_positive_return_sum_pct": "0",
            "flat_negative_return_sum_pct": "0",
        }
        for symbol in SYMBOLS
    }
    for index in range(min(len(states), len(contexts) - 1)):
        state = states[index]
        current_context = contexts[index]
        next_context = contexts[index + 1]
        portfolio = _portfolio_from_document(state["portfolio"])
        for symbol in SYMBOLS:
            episode = state["episodes"].get(symbol)
            if not isinstance(episode, Mapping):
                continue
            direction = str(episode.get("primary_direction"))
            current_mark = _d(current_context["symbols"][symbol]["mark"], "CONTEXT_MARK_INVALID")
            next_mark = _d(next_context["symbols"][symbol]["mark"], "CONTEXT_MARK_INVALID")
            market_return = (next_mark - current_mark) / current_mark
            open_lots = _open_lots(portfolio, symbol)
            if not open_lots:
                if market_return > ZERO:
                    flat_positive += 1
                    flat_positive_sum += market_return
                    by_symbol[symbol]["flat_positive_cycles"] += 1
                    by_symbol[symbol]["flat_positive_return_sum_pct"] = canonical_decimal(
                        _d(by_symbol[symbol]["flat_positive_return_sum_pct"], "PATH_CAPTURE_INVALID")
                        + market_return * Decimal("100")
                    )
                elif market_return < ZERO:
                    flat_negative += 1
                    flat_negative_sum += market_return
                    by_symbol[symbol]["flat_negative_cycles"] += 1
                    by_symbol[symbol]["flat_negative_return_sum_pct"] = canonical_decimal(
                        _d(by_symbol[symbol]["flat_negative_return_sum_pct"], "PATH_CAPTURE_INVALID")
                        + market_return * Decimal("100")
                    )
            if direction not in {"LONG", "SHORT"}:
                neutral += 1
                by_symbol[symbol]["neutral_primary_cycles"] += 1
                if market_return > ZERO:
                    neutral_positive += 1
                    neutral_positive_sum += market_return
                    by_symbol[symbol]["neutral_positive_cycles"] += 1
                    by_symbol[symbol]["neutral_positive_return_sum_pct"] = canonical_decimal(
                        _d(
                            by_symbol[symbol]["neutral_positive_return_sum_pct"],
                            "PATH_CAPTURE_INVALID",
                        )
                        + market_return * Decimal("100")
                    )
                elif market_return < ZERO:
                    neutral_negative += 1
                    neutral_negative_sum += market_return
                    by_symbol[symbol]["neutral_negative_cycles"] += 1
                    by_symbol[symbol]["neutral_negative_return_sum_pct"] = canonical_decimal(
                        _d(
                            by_symbol[symbol]["neutral_negative_return_sum_pct"],
                            "PATH_CAPTURE_INVALID",
                        )
                        + market_return * Decimal("100")
                    )
                continue
            actual_direction = "LONG" if next_mark > current_mark else "SHORT" if next_mark < current_mark else "FLAT"
            total += 1
            if actual_direction != direction:
                continue
            correct += 1
            by_symbol[symbol]["directional_opportunities"] += 1
            aligned = any(
                (lot.side is LotSide.LONG and direction == "LONG")
                or (lot.side is LotSide.SHORT and direction == "SHORT")
                for lot in open_lots
            )
            if aligned:
                captured += 1
                by_symbol[symbol]["captured_with_aligned_exposure"] += 1
    return {
        "assessed_directional_cycles": total,
        "correct_direction_cycles": correct,
        "correct_direction_rate": None if total == 0 else canonical_decimal(Decimal(correct) / Decimal(total)),
        "aligned_exposure_capture_count": captured,
        "aligned_exposure_capture_ratio_given_correct_direction": (
            None if correct == 0 else canonical_decimal(Decimal(captured) / Decimal(correct))
        ),
        "neutral_primary_cycles": neutral,
        "neutral_positive_cycles": neutral_positive,
        "neutral_negative_cycles": neutral_negative,
        "neutral_positive_return_sum_pct": canonical_decimal(
            neutral_positive_sum * Decimal("100")
        ),
        "neutral_negative_return_sum_pct": canonical_decimal(
            neutral_negative_sum * Decimal("100")
        ),
        "flat_positive_cycles": flat_positive,
        "flat_negative_cycles": flat_negative,
        "flat_positive_return_sum_pct": canonical_decimal(flat_positive_sum * Decimal("100")),
        "flat_negative_return_sum_pct": canonical_decimal(flat_negative_sum * Decimal("100")),
        "by_symbol": by_symbol,
        "boundary": "DESCRIPTIVE_ONE_STEP_PATH_AND_FLAT_OPPORTUNITY_ACCOUNTING_NOT_CAUSAL_OR_PREDICTIVE_PROOF",
    }


def _candidate_attribution(
    portfolio: PortfolioState,
    *,
    terminal_marks: Mapping[str, Decimal],
) -> dict[str, Any]:
    def empty_row() -> dict[str, Any]:
        return {
            "realized_pnl_before_cost_usdt": ZERO,
            "unrealized_pnl_usdt": ZERO,
            "fees_usdt": ZERO,
            "fill_count": 0,
            "entry_fill_count": 0,
            "exit_fill_count": 0,
        }

    by_attribution = {item.value: empty_row() for item in Attribution}
    by_symbol = {symbol: empty_row() for symbol in SYMBOLS}
    for fill in portfolio.fills:
        attribution_row = by_attribution[fill.attribution.value]
        symbol_row = by_symbol[fill.instrument_id]
        is_entry = fill.reason in {
            "COUNTERFACTUAL_STAGE_ENTRY",
            "EXOGENOUS_INITIAL_POSITION_NO_ENTRY_FILL",
        }
        for row in (attribution_row, symbol_row):
            row["realized_pnl_before_cost_usdt"] += fill.realized_pnl_before_fee
            row["fees_usdt"] += fill.fee
            row["fill_count"] += 1
            row["entry_fill_count" if is_entry else "exit_fill_count"] += 1
    for lot in _open_lots(portfolio):
        mark = terminal_marks[lot.instrument_id]
        direction = ONE if lot.side is LotSide.LONG else -ONE
        unrealized = (
            (mark - lot.entry_price)
            * lot.remaining_quantity
            * lot.contract_multiplier
            * direction
        )
        by_attribution[lot.attribution.value]["unrealized_pnl_usdt"] += unrealized
        by_symbol[lot.instrument_id]["unrealized_pnl_usdt"] += unrealized

    def finalize(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, row in rows.items():
            realized = _d(row["realized_pnl_before_cost_usdt"], "ATTRIBUTION_INVALID")
            unrealized = _d(row["unrealized_pnl_usdt"], "ATTRIBUTION_INVALID")
            fees = _d(row["fees_usdt"], "ATTRIBUTION_INVALID")
            output[key] = {
                "realized_pnl_before_cost_usdt": canonical_decimal(realized),
                "unrealized_pnl_usdt": canonical_decimal(unrealized),
                "fees_usdt": canonical_decimal(fees),
                "net_pnl_before_unknown_funding_usdt": canonical_decimal(
                    realized + unrealized - fees
                ),
                "fill_count": int(row["fill_count"]),
                "entry_fill_count": int(row["entry_fill_count"]),
                "exit_fill_count": int(row["exit_fill_count"]),
            }
        return output

    return {
        "by_attribution": finalize(by_attribution),
        "by_symbol": finalize(by_symbol),
        "funding_status": "UNKNOWN_NOT_IN_V1_PNL",
        "boundary": "FILL_AND_TERMINAL_MARK_ATTRIBUTION_WITH_FEES_SLIPPAGE_EMBEDDED_IN_FILL_PRICE",
    }


def _pnl_reconciles(left: Decimal, right: Decimal) -> bool:
    """Allow only sub-picodollar Decimal aggregation noise."""

    return abs(left - right) <= PNL_RECONCILIATION_TOLERANCE_USDT


def _reentry_history(states: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    contracts: dict[str, dict[str, Any]] = {}
    for state in states:
        observed_at = str(state["accepted_at"])
        for symbol, episode in state["episodes"].items():
            if not isinstance(episode, Mapping):
                continue
            contract = episode.get("reentry_contract")
            if not isinstance(contract, Mapping):
                continue
            contract_id = str(contract.get("contract_id") or "")
            if not contract_id:
                raise SingleAgentResearchError("REENTRY_CONTRACT_ID_MISSING")
            status = str(contract.get("status") or "UNKNOWN")
            row = contracts.setdefault(
                contract_id,
                {
                    "contract_id": contract_id,
                    "symbol": symbol,
                    "episode_id": contract.get("episode_id"),
                    "created_at": contract.get("created_at"),
                    "exit_price": contract.get("exit_price"),
                    "exit_reason": contract.get("exit_reason"),
                    "evidence_to_reenter": contract.get("evidence_to_reenter", []),
                    "evidence_to_cancel": contract.get("evidence_to_cancel", []),
                    "status_history": [],
                },
            )
            history = row["status_history"]
            if not history or history[-1]["status"] != status:
                history.append({"observed_at": observed_at, "status": status})
            row["final_status"] = status
            row["last_review_at"] = contract.get("last_review_at")
            row["resolution"] = contract.get("resolution")
    rows = [contracts[key] for key in sorted(contracts)]
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["final_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "contracts_created": len(rows),
        "final_status_counts": dict(sorted(status_counts.items())),
        "contracts": rows,
        "boundary": "FULL_ACCEPTED_STATE_HISTORY_NOT_ONLY_TERMINAL_PENDING_CONTRACTS",
    }


def _news_visibility(contexts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    unique_ids: set[str] = set()
    item_observations = 0
    symbol_cycles_with_metadata = 0
    by_symbol: dict[str, dict[str, Any]] = {}
    for symbol in SYMBOLS:
        symbol_ids: set[str] = set()
        symbol_observations = 0
        symbol_cycles = 0
        for context in contexts:
            rows = context["symbols"][symbol].get("news_metadata", [])
            if not isinstance(rows, list):
                raise SingleAgentResearchError("CONTEXT_NEWS_METADATA_INVALID")
            if rows:
                symbol_cycles += 1
                symbol_cycles_with_metadata += 1
            for item in rows:
                if not isinstance(item, Mapping) or not item.get("news_id"):
                    raise SingleAgentResearchError("CONTEXT_NEWS_METADATA_INVALID")
                news_id = str(item["news_id"])
                symbol_ids.add(news_id)
                unique_ids.add(news_id)
                symbol_observations += 1
                item_observations += 1
        by_symbol[symbol] = {
            "symbol_cycles_with_metadata": symbol_cycles,
            "item_observations_including_repeats": symbol_observations,
            "unique_news_items": len(symbol_ids),
        }
    return {
        "symbol_cycles_total": len(contexts) * len(SYMBOLS),
        "symbol_cycles_with_metadata": symbol_cycles_with_metadata,
        "item_observations_including_repeats": item_observations,
        "unique_news_items": len(unique_ids),
        "by_symbol": by_symbol,
        "boundary": "PIT_FILTERED_PUBLIC_HEADLINE_METADATA_VISIBILITY_NOT_SENTIMENT_TRUTH",
    }


def _multi_horizon_metrics(
    states: Sequence[Mapping[str, Any]],
    contexts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(states) != len(contexts):
        raise SingleAgentResearchError("MULTI_HORIZON_ALIGNMENT_INVALID")
    equity = [
        _d(
            state["equity_curve"][-1]["equity_before_unknown_funding_usdt"],
            "EQUITY_CURVE_INVALID",
        )
        for state in states
    ]
    rows: dict[str, Any] = {}
    for hours in (1, 4, 8, 24):
        pnl_changes: list[Decimal] = []
        assessed = 0
        correct = 0
        aligned_when_correct = 0
        neutral_cycles = 0
        flat_positive_cycles = 0
        flat_negative_cycles = 0
        for index in range(len(contexts) - 1):
            start_at = _ts(str(contexts[index]["decision_at"]))
            target_at = start_at + timedelta(hours=hours)
            future_index = next(
                (
                    candidate
                    for candidate in range(index + 1, len(contexts))
                    if _ts(str(contexts[candidate]["decision_at"])) >= target_at
                ),
                None,
            )
            if future_index is None:
                continue
            pnl_changes.append(equity[future_index] - equity[index])
            portfolio = _portfolio_from_document(states[index]["portfolio"])
            for symbol in SYMBOLS:
                current_mark = _d(
                    contexts[index]["symbols"][symbol]["mark"], "CONTEXT_MARK_INVALID"
                )
                future_mark = _d(
                    contexts[future_index]["symbols"][symbol]["mark"],
                    "CONTEXT_MARK_INVALID",
                )
                market_return = future_mark - current_mark
                open_lots = _open_lots(portfolio, symbol)
                if not open_lots:
                    if market_return > ZERO:
                        flat_positive_cycles += 1
                    elif market_return < ZERO:
                        flat_negative_cycles += 1
                episode = states[index]["episodes"].get(symbol)
                direction = (
                    str(episode.get("primary_direction"))
                    if isinstance(episode, Mapping)
                    else "NEUTRAL"
                )
                if direction not in {"LONG", "SHORT"}:
                    neutral_cycles += 1
                    continue
                assessed += 1
                direction_correct = (direction == "LONG" and market_return > ZERO) or (
                    direction == "SHORT" and market_return < ZERO
                )
                if not direction_correct:
                    continue
                correct += 1
                if any(
                    (lot.side is LotSide.LONG and direction == "LONG")
                    or (lot.side is LotSide.SHORT and direction == "SHORT")
                    for lot in open_lots
                ):
                    aligned_when_correct += 1
        rows[f"{hours}h"] = {
            "eligible_start_cycles": len(pnl_changes),
            "overlapping_actual_sequence_equity_change_mean_usdt": (
                None
                if not pnl_changes
                else canonical_decimal(sum(pnl_changes, ZERO) / Decimal(len(pnl_changes)))
            ),
            "overlapping_actual_sequence_equity_change_median_usdt": (
                None if not pnl_changes else canonical_decimal(statistics.median(pnl_changes))
            ),
            "overlapping_actual_sequence_equity_change_min_usdt": (
                None if not pnl_changes else canonical_decimal(min(pnl_changes))
            ),
            "overlapping_actual_sequence_equity_change_max_usdt": (
                None if not pnl_changes else canonical_decimal(max(pnl_changes))
            ),
            "positive_sequence_count": sum(value > ZERO for value in pnl_changes),
            "negative_sequence_count": sum(value < ZERO for value in pnl_changes),
            "assessed_directional_symbol_cycles": assessed,
            "correct_direction_symbol_cycles": correct,
            "correct_direction_rate": (
                None if assessed == 0 else canonical_decimal(Decimal(correct) / Decimal(assessed))
            ),
            "aligned_exposure_when_direction_correct": aligned_when_correct,
            "neutral_primary_symbol_cycles": neutral_cycles,
            "flat_positive_symbol_cycles": flat_positive_cycles,
            "flat_negative_symbol_cycles": flat_negative_cycles,
        }
    return {
        "horizons": rows,
        "boundary": "DESCRIPTIVE_OVERLAPPING_ACTUAL_POLICY_SEQUENCE_AND_START_STATE_PATH_ACCOUNTING_NOT_INDEPENDENT_SAMPLES_OR_CAUSAL_PROOF",
    }


def _buy_hold_benchmark(
    manifest: Mapping[str, Any],
    terminal_context: Mapping[str, Any],
    *,
    policy: Mapping[str, Decimal],
) -> dict[str, Any]:
    initial = manifest["source_config"]["initial_portfolio"]
    total_before_cost = ZERO
    total_after_liquidation = ZERO
    rows: dict[str, Any] = {}
    for item in initial["positions"]:
        symbol = str(item["symbol"])
        side = LotSide(str(item.get("side") or "LONG"))
        entry = _d(item["entry_price"], "SOURCE_INITIAL_POSITION_INVALID")
        notional = _d(item["notional_usdt"], "SOURCE_INITIAL_POSITION_INVALID")
        terminal = _d(terminal_context["symbols"][symbol]["mark"], "CONTEXT_MARK_INVALID")
        quantity = notional / entry
        direction = ONE if side is LotSide.LONG else -ONE
        pnl = quantity * (terminal - entry) * direction
        liquidation_fill = _market_fill(
            terminal,
            side,
            opening=False,
            bps=policy["market_slippage_bps"],
        )
        liquidation_pnl = quantity * (liquidation_fill - entry) * direction
        liquidation_fee = quantity * liquidation_fill * policy["taker_fee_rate"]
        after_liquidation = liquidation_pnl - liquidation_fee
        total_before_cost += pnl
        total_after_liquidation += after_liquidation
        rows[symbol] = {
            "side": side.value,
            "entry_price": canonical_decimal(entry),
            "terminal_mark": canonical_decimal(terminal),
            "initial_notional_usdt": canonical_decimal(notional),
            "mark_to_market_pnl_before_cost_usdt": canonical_decimal(pnl),
            "terminal_liquidation_fill": canonical_decimal(liquidation_fill),
            "terminal_liquidation_fee_usdt": canonical_decimal(liquidation_fee),
            "pnl_after_terminal_liquidation_cost_usdt": canonical_decimal(
                after_liquidation
            ),
        }
    return {
        "initial_portfolio_hold_pnl_before_cost_usdt": canonical_decimal(total_before_cost),
        "initial_portfolio_hold_pnl_after_terminal_liquidation_cost_usdt": canonical_decimal(
            total_after_liquidation
        ),
        "by_symbol": rows,
        "boundary": "STATIC_INITIAL_POSITION_HOLD_NO_REBALANCING_WITH_SEPARATE_COSTED_TERMINAL_LIQUIDATION_VIEW",
    }


def _v1_baseline(source: Path, *, initial_equity: Decimal) -> dict[str, Any]:
    decision = _load_json_float(source / "cycles" / "cycle-0024" / "decision.json")
    metrics = decision.get("portfolio_metrics")
    if not isinstance(metrics, Mapping):
        raise SingleAgentResearchError("V1_BASELINE_METRICS_MISSING")
    equity_curve: list[dict[str, Any]] = []
    for index in range(1, 25):
        cycle = _load_json_float(source / "cycles" / f"cycle-{index:04d}" / "decision.json")
        cycle_metrics = cycle.get("portfolio_metrics")
        if not isinstance(cycle_metrics, Mapping):
            raise SingleAgentResearchError("V1_BASELINE_METRICS_MISSING")
        equity_curve.append(
            {
                "cycle_index": index,
                "equity_before_unknown_funding_usdt": cycle_metrics.get("equity_usdt"),
            }
        )
    attribution = metrics.get("attribution")
    chaos_present = isinstance(attribution, Mapping) and "CHAOS_AUTO" in attribution
    return _canonical_source_value(
        {
            "terminal_cycle": 24,
            "net_realized_pnl_usdt": metrics.get("net_realized_pnl_usdt"),
            "total_net_pnl_usdt": metrics.get("total_net_pnl_usdt"),
            "maximum_drawdown_fraction": _maximum_drawdown(
                equity_curve, initial_equity=initial_equity
            ),
            "recorded_terminal_current_drawdown_fraction": metrics.get(
                "drawdown_fraction"
            ),
            "gross_notional_usdt": metrics.get("gross_notional_usdt"),
            "funding_status": metrics.get("funding_accrual_status"),
            "attribution": attribution,
            "chaos_auto_attribution_present": chaos_present,
            "comparator_content_difference": (
                "V1_INCLUDES_CHAOS_AUTO_EXOGENOUS_EMOTION_INJECTION_CANDIDATE_DOES_NOT"
                if chaos_present
                else "NONE_OBSERVED"
            ),
            "closed_trade_count": metrics.get("closed_trade_count"),
            "win_rate": metrics.get("win_rate"),
            "profit_factor": metrics.get("profit_factor"),
            "boundary": "RECORDED_V1_RESULT_OPENED_ONLY_AFTER_CANDIDATE_TERMINAL_RECEIPT_GENESIS_INCLUDED_IN_MAX_DRAWDOWN",
        }
    )


def _sndk_core_retention_sensitivity(
    source: Path,
    terminal_context: Mapping[str, Any],
    *,
    policy: Mapping[str, Decimal],
) -> dict[str, Any]:
    cycle = _load_json_float(source / "cycles" / "cycle-0016" / "decision.json")
    results = cycle.get("execution", {}).get("results", [])
    source_fill: Mapping[str, Any] | None = None
    for row in results if isinstance(results, list) else []:
        fill = row.get("fill") if isinstance(row, Mapping) else None
        closed = fill.get("closed_lots", []) if isinstance(fill, Mapping) else []
        if any(isinstance(item, Mapping) and item.get("lot_id") == "lot-000007" for item in closed):
            source_fill = fill
            break
    if source_fill is None:
        raise SingleAgentResearchError("V1_SNDK_REFERENCE_FILL_MISSING")
    quantity = _d(source_fill["quantity"], "V1_SENSITIVITY_SOURCE_INVALID")
    actual_exit = _d(source_fill["price"], "V1_SENSITIVITY_SOURCE_INVALID")
    terminal_mark = _d(terminal_context["symbols"]["SNDKUSDT"]["mark"], "CONTEXT_MARK_INVALID")
    terminal_exit = terminal_mark * (ONE - policy["market_slippage_bps"] / Decimal("10000"))
    incremental_per_unit = (
        terminal_exit * (ONE - policy["taker_fee_rate"])
        - actual_exit * (ONE - policy["taker_fee_rate"])
    )
    rows = []
    for retained in (Decimal("0.25"), Decimal("0.5"), Decimal("0.75"), Decimal("1")):
        increment = quantity * retained * incremental_per_unit
        rows.append(
            {
                "retained_core_fraction": canonical_decimal(retained),
                "incremental_net_pnl_vs_actual_full_exit_usdt": canonical_decimal(increment),
                "terminal_exit_assumption": canonical_decimal(terminal_exit),
            }
        )
    return {
        "reference_lot_id": "lot-000007",
        "actual_exit_price": canonical_decimal(actual_exit),
        "terminal_mark": canonical_decimal(terminal_mark),
        "rows": rows,
        "boundary": "OUTCOME_CONDITIONED_SENSITIVITY_ONLY_NOT_A_POLICY_SELECTION_OR_EX_ANTE_OPTIMUM",
    }


def evaluate_seen_v1_research(
    *,
    run_root: Path,
    artifact_root: Path | None = None,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    root, manifest, checkpoint = _run_documents(run_root)
    if checkpoint.get("status") not in {"TERMINAL_OUTCOMES_SEALED", "EVALUATED_SEEN_DIAGNOSTIC"}:
        raise SingleAgentResearchError("OUTCOME_ACCESS_BEFORE_TERMINAL_FORBIDDEN")
    terminal_receipt = _load_verified(root / str(checkpoint["terminal_receipt_path"]), "terminal_receipt_digest")
    terminal_state = _load_verified(root / str(checkpoint["accepted_state_path"]), "state_digest")
    if terminal_receipt["terminal_state_digest"] != terminal_state["state_digest"]:
        raise SingleAgentResearchError("TERMINAL_RECEIPT_STATE_MISMATCH")
    source = Path(str(manifest["source_root"])).resolve(strict=True)
    if legacy_tree_digest(source) != manifest["source_tree_digest_before"]:
        raise SingleAgentResearchError("SOURCE_TREE_DIGEST_MISMATCH")
    states = [
        _load_verified(root / "states" / f"state-{index:04d}-accepted.json", "state_digest")
        for index in range(1, 25)
    ]
    contexts = [
        _load_verified(root / "market-contexts" / f"cycle-{index:04d}.json", "context_digest")
        for index in range(1, 26)
    ]
    decisions = [
        _load_verified(root / "agent-decisions" / f"cycle-{index:04d}.json", "decision_digest")
        for index in range(1, 25)
    ]
    receipts = [
        _load_verified(root / "receipts" / f"cycle-{index:04d}.json", "receipt_digest")
        for index in range(1, 25)
    ]
    if any(
        states[index]["previous_state_digest"]
        != _load_verified(
            root / "pre-decision-states" / f"cycle-{index + 1:04d}.json", "state_digest"
        )["state_digest"]
        for index in range(24)
    ):
        raise SingleAgentResearchError("STATE_CHAIN_INVALID")
    action_results = [item for receipt in receipts for item in receipt["action_results"]]
    selected = len(action_results)
    applied = sum(item["status"] == "APPLIED" for item in action_results)
    rejected = sum(item["status"] == "REJECTED_BY_RISK_KERNEL" for item in action_results)
    new_risk_applied = sum(
        item["status"] == "APPLIED" and item["action_type"] in NEW_RISK_ACTIONS
        for item in action_results
    )
    competing_path_assessments = sum(
        len(symbol_decision["strategic_assessment"]["paths"])
        for decision in decisions
        for symbol_decision in decision["symbol_decisions"].values()
    )
    observation_request_status_counts: dict[str, int] = {}
    for decision in decisions:
        for symbol_decision in decision["symbol_decisions"].values():
            for request in symbol_decision["evidence_update"]["observation_requests"]:
                status = str(request["status"])
                observation_request_status_counts[status] = (
                    observation_request_status_counts.get(status, 0) + 1
                )
    portfolio = _portfolio_from_document(terminal_state["portfolio"])
    terminal_context = contexts[-1]
    terminal_marks = _marks(terminal_context)
    terminal_snapshot = mark_portfolio(
        portfolio,
        marks=terminal_marks,
        marked_at=_ts(str(terminal_context["decision_at"])),
    )
    policy = _risk_policy(manifest)
    buy_hold = _buy_hold_benchmark(
        manifest,
        terminal_context,
        policy=policy,
    )
    candidate_net = terminal_snapshot.net_pnl
    attribution = _candidate_attribution(portfolio, terminal_marks=terminal_marks)
    attribution_total = sum(
        (
            _d(row["net_pnl_before_unknown_funding_usdt"], "ATTRIBUTION_INVALID")
            for row in attribution["by_attribution"].values()
        ),
        ZERO,
    )
    if not _pnl_reconciles(attribution_total, candidate_net):
        raise SingleAgentResearchError("CANDIDATE_ATTRIBUTION_RECONCILIATION_FAILED")
    all_states = [*states, terminal_state]
    fill_reason_counts: dict[str, int] = {}
    for fill in portfolio.fills:
        fill_reason_counts[fill.reason] = fill_reason_counts.get(fill.reason, 0) + 1
    raw = self_digest(
        {
            "schema_id": "single_agent_seen_v1_raw_evaluation",
            "schema_version": "1.1.0",
            "run_id": manifest["run_id"],
            "evaluated_at": _iso((evaluated_at or datetime.now(UTC)).astimezone(UTC)),
            "evidence_class": EVIDENCE_CLASS,
            "sequence": {
                "genesis_complete": True,
                "decision_cycles_completed": 24,
                "terminal_observation_cycle": 25,
                "terminal_receipt_digest": terminal_receipt["terminal_receipt_digest"],
                "state_chain_complete": True,
                "point_in_time_contexts": 25,
                "recorded_v1_outcomes_opened_after_terminal": True,
            },
            "candidate_result": {
                "realized_pnl_before_cost_usdt": canonical_decimal(portfolio.realized_pnl_before_cost),
                "unrealized_pnl_usdt": canonical_decimal(terminal_snapshot.unrealized_pnl),
                "fees_usdt": canonical_decimal(portfolio.total_fees),
                "funding_usdt": None,
                "funding_status": "UNKNOWN_NOT_IN_V1_PNL",
                "net_pnl_before_unknown_funding_usdt": canonical_decimal(candidate_net),
                "terminal_equity_before_unknown_funding_usdt": canonical_decimal(terminal_snapshot.equity),
                "maximum_drawdown_fraction": canonical_decimal(
                    _maximum_drawdown(
                        terminal_state["equity_curve"],
                        initial_equity=portfolio.initial_equity,
                    )
                ),
                "open_lot_count": len(_open_lots(portfolio)),
                "gross_notional_usdt": canonical_decimal(terminal_snapshot.gross_notional),
                "attribution": attribution,
            },
            "v1_recorded_baseline": _v1_baseline(
                source,
                initial_equity=portfolio.initial_equity,
            ),
            "initial_portfolio_hold_benchmark": buy_hold,
            "opportunity_difference": {
                "candidate_minus_initial_hold_before_unknown_funding_usdt": canonical_decimal(
                    candidate_net - _d(buy_hold["initial_portfolio_hold_pnl_before_cost_usdt"], "BENCHMARK_INVALID")
                ),
                "candidate_minus_initial_hold_after_terminal_liquidation_cost_usdt": canonical_decimal(
                    candidate_net
                    - _d(
                        buy_hold[
                            "initial_portfolio_hold_pnl_after_terminal_liquidation_cost_usdt"
                        ],
                        "BENCHMARK_INVALID",
                    )
                ),
                "candidate_minus_zero_pnl_cash_usdt": canonical_decimal(candidate_net),
                "boundary": "CASH_AND_FLAT_EXPOSURE_HAVE_OPPORTUNITY_COST_HOLD_IS_SHOWN_BEFORE_AND_AFTER_TERMINAL_LIQUIDATION_COST",
            },
            "cost_and_execution_accounting": {
                "taker_fee_rate": canonical_decimal(policy["taker_fee_rate"]),
                "maker_fee_rate": canonical_decimal(policy["maker_fee_rate"]),
                "market_slippage_bps": canonical_decimal(
                    policy["market_slippage_bps"]
                ),
                "stop_slippage_bps": canonical_decimal(policy["stop_slippage_bps"]),
                "slippage_status": "EMBEDDED_IN_EXECUTED_FILL_PRICE_NOT_ADDED_AS_A_SECOND_PNL_LINE",
                "funding_status": "UNKNOWN_NOT_IN_V1_PNL",
                "fill_reason_counts": dict(sorted(fill_reason_counts.items())),
            },
            "action_fidelity": {
                "selected_actions": selected,
                "applied_actions": applied,
                "risk_rejected_actions": rejected,
                "application_ratio": None if selected == 0 else canonical_decimal(Decimal(applied) / Decimal(selected)),
                "new_risk_actions_applied": new_risk_applied,
            },
            "flat_exposure": _flat_exposure_metrics(all_states),
            "reentry": {
                "recorded_delay_hours": terminal_state["reentry_delays_hours"],
                "history": _reentry_history(all_states),
                "pending_contracts": [
                    episode["reentry_contract"]
                    for episode in terminal_state["episodes"].values()
                    if isinstance(episode, Mapping)
                    and isinstance(episode.get("reentry_contract"), Mapping)
                    and episode["reentry_contract"].get("status") == "PENDING_AGENT_REVIEW"
                ],
            },
            "path_capture": _path_capture_metrics(states, contexts),
            "multi_horizon_outcomes": _multi_horizon_metrics(all_states, contexts),
            "public_news_visibility": _news_visibility(contexts),
            "core_management_checkpoint_events": terminal_state["target_events"],
            "sndk_core_retention_sensitivity": _sndk_core_retention_sensitivity(
                source, terminal_context, policy=policy
            ),
            "decision_counts": {
                "symbols_analyzed": len(decisions) * len(SYMBOLS),
                "sentiment_assessments": len(decisions) * len(SYMBOLS),
                "competing_path_assessments": competing_path_assessments,
                "observation_request_status_counts": dict(
                    sorted(observation_request_status_counts.items())
                ),
            },
            "claims_boundary": {
                "market_validity": "SEEN_HISTORICAL_DIAGNOSTIC_ONLY",
                "predictive_validity": "NOT_ESTABLISHED",
                "profitability": "NOT_ESTABLISHED",
                "latest_paper_readiness": "REQUIRES_SEPARATE_PRE_OUTCOME_FREEZE_AND_NEW_WINDOW",
                "external_execution_authority": EXECUTION_AUTHORITY,
                "executable": False,
            },
        },
        "evaluation_digest",
    )
    evaluation_path = root / "evaluation" / "raw-evaluation.json"
    write_once_json(evaluation_path, raw)
    if artifact_root is not None:
        artifact = Path(artifact_root).resolve() / manifest["run_id"] / "raw-evaluation.json"
        write_once_json(artifact, raw)
    checkpoint["status"] = "EVALUATED_SEEN_DIAGNOSTIC"
    checkpoint["recorded_v1_decisions_opened"] = True
    checkpoint["recorded_v1_outcomes_opened"] = True
    checkpoint["evaluation_path"] = evaluation_path.relative_to(root).as_posix()
    checkpoint["evaluation_digest"] = raw["evaluation_digest"]
    _write_atomic_json(root / "checkpoint.json", checkpoint)
    if legacy_tree_digest(source) != manifest["source_tree_digest_before"]:
        raise SingleAgentResearchError("LEGACY_WRITE_ATTEMPT_FORBIDDEN")
    return raw


def research_status(*, run_root: Path) -> dict[str, Any]:
    root, manifest, checkpoint = _run_documents(run_root)
    value = {
        "run_id": manifest["run_id"],
        "evidence_class": manifest["evidence_class"],
        "status": checkpoint["status"],
        "completed_cycles": checkpoint["completed_cycles"],
        "next_cycle_index": checkpoint["next_cycle_index"],
        "accepted_state_digest": checkpoint["accepted_state_digest"],
        "pending_agent_context_path": checkpoint["pending_agent_context_path"],
        "recorded_v1_decisions_opened": checkpoint["recorded_v1_decisions_opened"],
        "recorded_v1_outcomes_opened": checkpoint["recorded_v1_outcomes_opened"],
        "terminal_receipt_path": checkpoint["terminal_receipt_path"],
        "interruption_receipt_path": checkpoint.get("interruption_receipt_path"),
        "interruption_digest": checkpoint.get("interruption_digest"),
        "evaluation_path": checkpoint.get("evaluation_path"),
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    return value
