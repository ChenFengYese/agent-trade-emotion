"""Public Binance USD-M observations, RSS headlines, and technical measures."""

from __future__ import annotations

import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .common import TheoryPaperError, digest_json, iso_utc


JsonGetter = Callable[[str, Mapping[str, Any]], Any]
EQUITY_PERPETUALS = frozenset({"SNDKUSDT", "MUUSDT"})


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _last(values: Sequence[float], default: float | None = None) -> float | None:
    return values[-1] if values else default


def sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    output = [current]
    for value in values[period:]:
        current = alpha * value + (1.0 - alpha) * current
        output.append(current)
    return output


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = ((period - 1) * average_gain + gain) / period
        average_loss = ((period - 1) * average_loss + loss) / period
    if average_loss == 0:
        return 100.0
    relative = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative)


def atr(bars: Sequence[Mapping[str, float]], period: int = 14) -> float | None:
    if len(bars) <= period:
        return None
    ranges: list[float] = []
    for index in range(1, len(bars)):
        previous = bars[index - 1]["close"]
        bar = bars[index]
        ranges.append(
            max(
                bar["high"] - bar["low"],
                abs(bar["high"] - previous),
                abs(bar["low"] - previous),
            )
        )
    current = sum(ranges[:period]) / period
    for value in ranges[period:]:
        current = ((period - 1) * current + value) / period
    return current


def adx(bars: Sequence[Mapping[str, float]], period: int = 14) -> float | None:
    if len(bars) < period * 2 + 1:
        return None
    true_ranges: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for index in range(1, len(bars)):
        current, previous = bars[index], bars[index - 1]
        up = current["high"] - previous["high"]
        down = previous["low"] - current["low"]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        true_ranges.append(
            max(
                current["high"] - current["low"],
                abs(current["high"] - previous["close"]),
                abs(current["low"] - previous["close"]),
            )
        )
    dx_values: list[float] = []
    for end in range(period, len(true_ranges) + 1):
        tr = sum(true_ranges[end - period : end])
        if tr <= 0:
            continue
        plus = 100.0 * sum(plus_dm[end - period : end]) / tr
        minus = 100.0 * sum(minus_dm[end - period : end]) / tr
        denominator = plus + minus
        dx_values.append(0.0 if denominator == 0 else 100.0 * abs(plus - minus) / denominator)
    return sma(dx_values, period)


def efficiency_ratio(values: Sequence[float], period: int = 10) -> float | None:
    if len(values) <= period:
        return None
    direction = abs(values[-1] - values[-period - 1])
    volatility = sum(abs(values[index] - values[index - 1]) for index in range(len(values) - period, len(values)))
    return 0.0 if volatility == 0 else direction / volatility


def _macd(values: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    fast = ema_series(values, 12)
    slow = ema_series(values, 26)
    if not fast or not slow:
        return None, None, None
    offset = len(fast) - len(slow)
    line = [fast[index + offset] - slow[index] for index in range(len(slow))]
    signal_values = ema_series(line, 9)
    if not signal_values:
        return line[-1], None, None
    return line[-1], signal_values[-1], line[-1] - signal_values[-1]


def _round(value: float | None, digits: int = 8) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, digits)


def equity_reference_context(symbol: str, observed_at: datetime) -> dict[str, str]:
    """Describe the US-equity reference session without claiming a cash-equity quote.

    This intentionally does not attempt to infer exchange holidays.  A weekday
    marked as a regular session is therefore a schedule estimate, not proof the
    Nasdaq reference market was open.
    """
    if symbol not in EQUITY_PERPETUALS:
        return {
            "instrument_kind": "CRYPTO_PERPETUAL",
            "underlying_session": "NOT_APPLICABLE",
            "reference_mode": "CRYPTO_DERIVATIVE",
        }
    local = observed_at.astimezone(ZoneInfo("America/New_York"))
    minute = local.hour * 60 + local.minute
    if local.weekday() >= 5:
        session = "CLOSED_OR_HOLIDAY_UNVERIFIED"
    elif 4 * 60 <= minute < 9 * 60 + 30:
        session = "PRE_MARKET_SCHEDULE_ESTIMATE"
    elif 9 * 60 + 30 <= minute < 16 * 60:
        session = "REGULAR_SCHEDULE_ESTIMATE"
    elif 16 * 60 <= minute < 20 * 60:
        session = "AFTER_HOURS_SCHEDULE_ESTIMATE"
    else:
        session = "CLOSED_OR_HOLIDAY_UNVERIFIED"
    return {
        "instrument_kind": "TRADIFI_EQUITY_PERPETUAL_DERIVATIVE",
        "underlying_session": session,
        "reference_mode": (
            "EQUITY_REFERENCE_SCHEDULE_ACTIVE"
            if session in {"PRE_MARKET_SCHEDULE_ESTIMATE", "REGULAR_SCHEDULE_ESTIMATE", "AFTER_HOURS_SCHEDULE_ESTIMATE"}
            else "DERIVATIVE_ORDERBOOK_REFERENCE_EXPECTED"
        ),
    }


class BinancePublicClient:
    """Credential-free USD-M REST client with bounded retries."""

    base_url = "https://fapi.binance.com"

    def __init__(self, timeout_seconds: float = 12.0, retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def get_json(self, path: str, params: Mapping[str, Any]) -> Any:
        query = urllib.parse.urlencode([(key, value) for key, value in params.items() if value is not None])
        url = self.base_url + path + ("?" + query if query else "")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "agent-trade-emotion-theory-paper/1.0"},
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    import json

                    return json.loads(response.read().decode("utf-8"))
            except (OSError, urllib.error.URLError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (attempt + 1))
        raise TheoryPaperError(f"public market request failed: {path}") from last_error


def _safe_get(getter: JsonGetter, path: str, params: Mapping[str, Any]) -> tuple[Any, str | None]:
    try:
        return getter(path, params), None
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"


def _closed_bars(raw: Any, observed_ms: int) -> list[dict[str, float]]:
    output: list[dict[str, float]] = []
    if not isinstance(raw, list):
        return output
    for row in raw:
        if not isinstance(row, list) or len(row) < 7:
            continue
        close_time = int(row[6])
        values = [_finite(row[index]) for index in (1, 2, 3, 4, 5)]
        if close_time > observed_ms or any(value is None for value in values):
            continue
        output.append(
            {
                "open_time": float(row[0]),
                "open": values[0],
                "high": values[1],
                "low": values[2],
                "close": values[3],
                "volume": values[4],
                "close_time": float(close_time),
            }
        )
    return output


def _book_measures(depth: Any, reference_price: float, notional: float = 1000.0) -> dict[str, Any]:
    if not isinstance(depth, dict):
        return {"status": "UNKNOWN"}
    bids = sorted(
        ((float(price), float(qty)) for price, qty in depth.get("bids", []) if float(qty) > 0),
        key=lambda row: row[0],
        reverse=True,
    )
    asks = sorted(
        ((float(price), float(qty)) for price, qty in depth.get("asks", []) if float(qty) > 0),
        key=lambda row: row[0],
    )
    if not bids or not asks:
        return {"status": "UNKNOWN"}
    if bids[0][0] >= asks[0][0]:
        return {
            "status": "UNKNOWN_CROSSED_OR_LOCKED_SNAPSHOT",
            "strict_resilience_available": False,
            "strict_resilience_reason": "INVALID_TOP_OF_BOOK_FOR_STATIC_IMPACT",
        }
    bid_value = sum(price * qty for price, qty in bids[:20])
    ask_value = sum(price * qty for price, qty in asks[:20])
    total = bid_value + ask_value

    midpoint = (bids[0][0] + asks[0][0]) / 2.0

    def impact(levels: Iterable[tuple[float, float]], side: str) -> float | None:
        remaining = notional
        acquired = 0.0
        spent = 0.0
        for price, qty in levels:
            available = price * qty
            used = min(available, remaining)
            acquired += used / price
            spent += used
            remaining -= used
            if remaining <= 1e-9:
                break
        if remaining > 1e-6 or acquired <= 0:
            return None
        average = spent / acquired
        adverse = (
            average / midpoint - 1.0
            if side == "BUY"
            else 1.0 - average / midpoint
        )
        return max(0.0, 10000.0 * adverse)

    return {
        "status": "OBSERVED_SNAPSHOT_PROXY",
        "best_bid": bids[0][0],
        "best_ask": asks[0][0],
        "midpoint": midpoint,
        "spread_bps": _round(10000.0 * (asks[0][0] - bids[0][0]) / midpoint, 4),
        "top20_bid_notional": _round(bid_value, 2),
        "top20_ask_notional": _round(ask_value, 2),
        "top20_imbalance": _round(0.0 if total == 0 else (bid_value - ask_value) / total, 6),
        "buy_1000_impact_bps": _round(impact(asks, "BUY"), 4),
        "sell_1000_impact_bps": _round(impact(bids, "SELL"), 4),
        "impact_reference": "VALID_TOP_OF_BOOK_MIDPOINT",
        "impact_semantics": "NONNEGATIVE_ADVERSE_STATIC_WALK_IMPACT",
        "external_reference_price": _round(reference_price, 8),
        "strict_resilience_available": False,
        "strict_resilience_reason": "ONE_SNAPSHOT_HAS_NO_POST_PRESSURE_REPLENISHMENT_SEQUENCE",
    }


def _trade_measures(trades: Any) -> dict[str, Any]:
    if not isinstance(trades, list) or not trades:
        return {"status": "UNKNOWN"}
    buy = sell = 0.0
    prices: list[float] = []
    total_quantity = 0.0
    weighted = 0.0
    for row in trades:
        if not isinstance(row, dict):
            continue
        price = _finite(row.get("p"))
        quantity = _finite(row.get("q"))
        if price is None or quantity is None:
            continue
        quote = price * quantity
        if row.get("m") is True:
            sell += quote
        else:
            buy += quote
        prices.append(price)
        total_quantity += quantity
        weighted += quote
    total = buy + sell
    return {
        "status": "OBSERVED_RECENT_WINDOW",
        "trade_count": len(prices),
        "taker_buy_notional": _round(buy, 2),
        "taker_sell_notional": _round(sell, 2),
        "signed_taker_imbalance": _round(0.0 if total == 0 else (buy - sell) / total, 6),
        "vwap": _round(None if total_quantity == 0 else weighted / total_quantity, 8),
        "first_price": _round(prices[0] if prices else None, 8),
        "last_price": _round(prices[-1] if prices else None, 8),
    }


def _timeframe_measures(bars: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    if len(bars) < 30:
        return {"status": "UNKNOWN", "bar_count": len(bars)}
    closes = [bar["close"] for bar in bars]
    volumes = [bar["volume"] for bar in bars]
    ema20 = _last(ema_series(closes, 20))
    ema50 = _last(ema_series(closes, 50))
    ema200 = _last(ema_series(closes, 200))
    atr14 = atr(bars)
    adx14 = adx(bars)
    macd_line, macd_signal, macd_hist = _macd(closes)
    volume_mean = sma(volumes[:-1], min(20, max(1, len(volumes) - 1)))
    rvol = None if not volume_mean else volumes[-1] / volume_mean
    mean20 = sma(closes, 20)
    std20 = statistics.pstdev(closes[-20:]) if len(closes) >= 20 else None
    price = closes[-1]
    bollinger_upper = None if mean20 is None or std20 is None else mean20 + 2.0 * std20
    bollinger_lower = None if mean20 is None or std20 is None else mean20 - 2.0 * std20
    bollinger_width = (
        None
        if bollinger_upper is None or bollinger_lower is None
        else bollinger_upper - bollinger_lower
    )
    if ema20 is not None and ema50 is not None and price > ema20 > ema50 and (adx14 or 0) >= 20:
        trend = "UP"
    elif ema20 is not None and ema50 is not None and price < ema20 < ema50 and (adx14 or 0) >= 20:
        trend = "DOWN"
    elif (adx14 or 0) < 18:
        trend = "RANGE"
    else:
        trend = "TRANSITION"
    pivots_low = [
        bars[index]["low"]
        for index in range(max(2, len(bars) - 60), len(bars) - 2)
        if bars[index]["low"] <= min(bars[index - 2]["low"], bars[index - 1]["low"], bars[index + 1]["low"], bars[index + 2]["low"])
    ]
    pivots_high = [
        bars[index]["high"]
        for index in range(max(2, len(bars) - 60), len(bars) - 2)
        if bars[index]["high"] >= max(bars[index - 2]["high"], bars[index - 1]["high"], bars[index + 1]["high"], bars[index + 2]["high"])
    ]
    supports = sorted({round(value, 8) for value in pivots_low if value < price}, reverse=True)[:3]
    resistances = sorted({round(value, 8) for value in pivots_high if value > price})[:3]
    return {
        "status": "OBSERVED_CLOSED_BARS",
        "bar_count": len(bars),
        "price": _round(price),
        "change_1_bar_pct": _round(100.0 * (price / closes[-2] - 1.0), 5),
        "change_6_bar_pct": _round(100.0 * (price / closes[-7] - 1.0), 5) if len(closes) >= 7 else None,
        "ema20": _round(ema20),
        "ema50": _round(ema50),
        "ema200": _round(ema200),
        "rsi14": _round(rsi(closes), 4),
        "atr14": _round(atr14),
        "atr_pct": _round(None if not atr14 else 100.0 * atr14 / price, 5),
        "adx14": _round(adx14, 4),
        "efficiency_ratio10": _round(efficiency_ratio(closes), 5),
        "macd": _round(macd_line),
        "macd_signal": _round(macd_signal),
        "macd_histogram": _round(macd_hist),
        "bollinger_middle": _round(mean20),
        "bollinger_upper": _round(bollinger_upper),
        "bollinger_lower": _round(bollinger_lower),
        "bollinger_bandwidth": _round(
            None if not mean20 or bollinger_width is None else bollinger_width / mean20,
            8,
        ),
        "bollinger_percent_b": _round(
            None
            if bollinger_lower is None or not bollinger_width
            else (price - bollinger_lower) / bollinger_width,
            8,
        ),
        "relative_volume20": _round(rvol, 4),
        "trend_state": trend,
        "supports": supports,
        "resistances": resistances,
        "last_closed_bar": dict(bars[-1]),
    }


def fetch_symbol_snapshot(
    symbol: str,
    getter: JsonGetter,
    *,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    observed = observed_at or datetime.now(timezone.utc)
    observed_ms = int(observed.timestamp() * 1000)
    errors: dict[str, str] = {}

    def request(name: str, path: str, params: Mapping[str, Any]) -> Any:
        value, error = _safe_get(getter, path, params)
        if error:
            errors[name] = error
        return value

    ticker = request("ticker24h", "/fapi/v1/ticker/24hr", {"symbol": symbol})
    premium = request("premium", "/fapi/v1/premiumIndex", {"symbol": symbol})
    open_interest = request("open_interest", "/fapi/v1/openInterest", {"symbol": symbol})
    oi_history = request("oi_history", "/futures/data/openInterestHist", {"symbol": symbol, "period": "1h", "limit": 4})
    funding = request("funding", "/fapi/v1/fundingRate", {"symbol": symbol, "limit": 4})
    global_ratio = request("global_ratio", "/futures/data/globalLongShortAccountRatio", {"symbol": symbol, "period": "1h", "limit": 4})
    top_ratio = request("top_ratio", "/futures/data/topLongShortPositionRatio", {"symbol": symbol, "period": "1h", "limit": 4})
    taker_ratio = request("taker_ratio", "/futures/data/takerlongshortRatio", {"symbol": symbol, "period": "1h", "limit": 4})
    depth = request("depth", "/fapi/v1/depth", {"symbol": symbol, "limit": 100})
    trades = request("agg_trades", "/fapi/v1/aggTrades", {"symbol": symbol, "limit": 500})
    liquidations = request("liquidations", "/fapi/v1/allForceOrders", {"symbol": symbol, "limit": 100})
    raw_klines: dict[str, Any] = {}
    for interval, limit in (("15m", 240), ("1h", 240), ("4h", 240), ("1d", 240), ("1w", 120)):
        raw_klines[interval] = request(
            f"klines_{interval}",
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )

    price = _finite((premium or {}).get("markPrice") if isinstance(premium, dict) else None)
    if price is None and isinstance(ticker, dict):
        price = _finite(ticker.get("lastPrice"))
    if price is None:
        raise TheoryPaperError(f"{symbol} has no observable public price")

    timeframes = {
        interval: _timeframe_measures(_closed_bars(raw, observed_ms))
        for interval, raw in raw_klines.items()
    }
    oi_rows = oi_history if isinstance(oi_history, list) else []
    oi_values = [
        _finite(row.get("sumOpenInterestValue"))
        for row in oi_rows
        if isinstance(row, dict)
    ]
    oi_values = [value for value in oi_values if value is not None]
    oi_change = None if len(oi_values) < 2 or oi_values[-2] == 0 else (oi_values[-1] / oi_values[-2] - 1.0)
    index_price = _finite((premium or {}).get("indexPrice") if isinstance(premium, dict) else None)
    basis_bps = None if not index_price else 10000.0 * (price / index_price - 1.0)
    liquidation_rows = liquidations if isinstance(liquidations, list) else []
    liquidation_notional = 0.0
    for row in liquidation_rows:
        if not isinstance(row, dict):
            continue
        liquidation_notional += (_finite(row.get("price")) or 0.0) * (_finite(row.get("origQty")) or 0.0)

    def latest(rows: Any, key: str) -> float | None:
        if not isinstance(rows, list) or not rows or not isinstance(rows[-1], dict):
            return None
        return _finite(rows[-1].get(key))

    measures = {
        "price": price,
        "ticker_24h": {
            "change_pct": _finite(ticker.get("priceChangePercent")) if isinstance(ticker, dict) else None,
            "high": _finite(ticker.get("highPrice")) if isinstance(ticker, dict) else None,
            "low": _finite(ticker.get("lowPrice")) if isinstance(ticker, dict) else None,
            "quote_volume": _finite(ticker.get("quoteVolume")) if isinstance(ticker, dict) else None,
            "trade_count": ticker.get("count") if isinstance(ticker, dict) else None,
        },
        "directional_pressure_D": {
            "recent_trades": _trade_measures(trades),
            "hourly_taker_buy_sell_ratio": latest(taker_ratio, "buySellRatio"),
            "interpretation_boundary": "FLOW_PRESSURE_PROXY_NOT_PARTICIPANT_IDENTITY",
        },
        "leverage_L": {
            "open_interest_contracts": _finite(open_interest.get("openInterest")) if isinstance(open_interest, dict) else None,
            "open_interest_value_1h_change_pct": _round(None if oi_change is None else 100.0 * oi_change, 6),
            "interpretation_boundary": "OI_CHANGE_HAS_NO_DIRECTIONAL_TRUTH_ALONE",
        },
        "crowding_C": {
            "funding_rate": latest(funding, "fundingRate"),
            "basis_bps": _round(basis_bps, 5),
            "global_account_long_short_ratio": latest(global_ratio, "longShortRatio"),
            "top_position_long_short_ratio": latest(top_ratio, "longShortRatio"),
            "interpretation_boundary": "MULTI_PROXY_VECTOR_NOT_SINGLE_EMOTION_SCORE",
        },
        "forced_deleveraging_F": {
            "status": "OBSERVED_RECENT_API_WINDOW" if isinstance(liquidations, list) else "UNKNOWN",
            "event_count": len(liquidation_rows),
            "notional": _round(liquidation_notional, 2),
            "missing_is_zero": False,
        },
        "liquidity_resilience_R": _book_measures(depth, price),
        "timeframes": timeframes,
    }
    quality = {
        "required_components": 15,
        "error_count": len(errors),
        "coverage_ratio": round(max(0.0, (15 - len(errors)) / 15.0), 4),
        "errors": errors,
        "strict_R_available": False,
        "liquidation_zero_certainty": False,
    }
    raw = {
        "ticker": ticker,
        "premium": premium,
        "open_interest": open_interest,
        "oi_history": oi_history,
        "funding": funding,
        "global_ratio": global_ratio,
        "top_ratio": top_ratio,
        "taker_ratio": taker_ratio,
        "depth": depth,
        "agg_trades": trades,
        "liquidations": liquidations,
        "klines": raw_klines,
    }
    return {
        "symbol": symbol,
        "venue": "BINANCE_USDM_PUBLIC",
        **equity_reference_context(symbol, observed),
        "observed_at": iso_utc(observed),
        "measures": measures,
        "data_quality": quality,
        "raw_digest": digest_json(raw),
        "raw": raw,
    }


def fetch_market_snapshot(
    symbols: Sequence[str],
    *,
    client: BinancePublicClient | None = None,
    getter: JsonGetter | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    if not symbols or len(set(symbols)) != len(symbols):
        raise TheoryPaperError("symbols must be a nonempty unique sequence")
    source = getter or (client or BinancePublicClient()).get_json
    observed = observed_at or datetime.now(timezone.utc)
    results: dict[str, Any] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as pool:
        futures = {
            pool.submit(fetch_symbol_snapshot, symbol, source, observed_at=observed): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception as exc:
                failures[symbol] = f"{type(exc).__name__}:{exc}"
    if not results:
        raise TheoryPaperError("all public market snapshots failed")
    return {
        "schema_version": "theory-paper-market-snapshot.v1",
        "observed_at": iso_utc(observed),
        "symbols": [results[symbol] for symbol in symbols if symbol in results],
        "failures": failures,
        "point_in_time_rule": "ONLY_RESPONSES_AVAILABLE_BY_OBSERVED_AT_AND_CLOSED_BARS",
        "market_snapshot_digest": digest_json(
            {
                "observed_at": iso_utc(observed),
                "symbols": [results[symbol]["raw_digest"] for symbol in symbols if symbol in results],
                "failures": failures,
            }
        ),
    }


def fetch_news_headlines(
    queries: Mapping[str, str],
    *,
    limit_per_query: int = 8,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Fetch headline metadata only; article bodies and inferred sentiment are excluded."""
    output: dict[str, Any] = {}
    for key, query in queries.items():
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": query + " when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"}
        )
        items: list[dict[str, Any]] = []
        error: str | None = None
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "agent-trade-emotion-theory-paper/1.0"},
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                root = ET.fromstring(response.read())
            for item in root.findall("./channel/item")[:limit_per_query]:
                source = item.find("source")
                items.append(
                    {
                        "title": (item.findtext("title") or "").strip(),
                        "url": (item.findtext("link") or "").strip(),
                        "published_at": (item.findtext("pubDate") or "").strip(),
                        "source": (source.text or "").strip() if source is not None else "",
                    }
                )
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
        output[key] = {
            "query": query,
            "source": "GOOGLE_NEWS_RSS_DISCOVERY_METADATA_ONLY",
            "items": items,
            "error": error,
        }
    return {
        "schema_version": "theory-paper-news-metadata.v1",
        "observed_at": iso_utc(),
        "queries": output,
        "interpretation_boundary": "HEADLINES_ARE_CONTEXT_FACTS_NOT_CAUSAL_OR_SENTIMENT_TRUTH",
    }
