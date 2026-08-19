"""Explicit allowlisted source catalog; each entry is an independent Data Mod."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Any, Callable, Mapping
import urllib.parse

from ..application.ports import (
    HttpRequest,
    TransportRequest,
    TransportResponse,
    WebSocketRequest,
)
from ..domain.contracts import AccessMode, SourceDefinition, TransportKind
from .normalizers import normalize_payload
from .websocket_transport import summarize_websocket_container


_DEFAULT_HEADERS = {
    "Accept": "application/json, text/csv, application/xml, text/xml, text/plain, text/html;q=0.8",
    "User-Agent": "agent-trade-emotion-v3.3.2-public-research/1.0",
}
_INSTRUMENT = re.compile(r"[A-Z0-9]+-[A-Z0-9]+-SWAP\Z")

RequestBuilder = Callable[
    [Mapping[str, str], Mapping[str, str], datetime], TransportRequest
]


@dataclass(frozen=True, slots=True)
class SourceAdapter:
    definition: SourceDefinition
    builder: RequestBuilder | None

    def build_request(
        self,
        *,
        parameters: Mapping[str, str],
        environment: Mapping[str, str],
        now: datetime,
    ) -> TransportRequest:
        if self.builder is None:
            raise ValueError("V332_SOURCE_HAS_NO_AUTOMATIC_TRANSPORT")
        return self.builder(parameters, environment, now)

    def normalize(
        self,
        *,
        body: bytes,
        response: TransportResponse,
    ) -> Mapping[str, Any]:
        if self.definition.transport is TransportKind.WEBSOCKET:
            return summarize_websocket_container(body)
        return normalize_payload(
            source_id=self.definition.source_id,
            raw=body,
            content_type=response.headers.get("content-type"),
        )


def _url(base: str, query: Mapping[str, str]) -> str:
    encoded = urllib.parse.urlencode(tuple(sorted(query.items())))
    return base + ("?" + encoded if encoded else "")


def _http(
    *,
    url: str,
    stored_url: str | None = None,
    headers: Mapping[str, str] | None = None,
    stored_headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    max_bytes: int = 16 * 1024 * 1024,
    omit_user_agent: bool = False,
) -> HttpRequest:
    actual_headers = dict(_DEFAULT_HEADERS)
    actual_headers.update(headers or {})
    safe_headers = dict(_DEFAULT_HEADERS)
    safe_headers.update(stored_headers if stored_headers is not None else (headers or {}))
    if omit_user_agent:
        actual_headers.pop("User-Agent", None)
        safe_headers.pop("User-Agent", None)
    return HttpRequest(
        method="POST" if body is not None else "GET",
        url=url,
        stored_url=stored_url or url,
        headers=actual_headers,
        stored_headers=safe_headers,
        body=body,
        max_bytes=max_bytes,
    )


def _static_get(url: str, *, max_bytes: int = 16 * 1024 * 1024) -> RequestBuilder:
    return lambda _parameters, _environment, _now: _http(
        url=url, max_bytes=max_bytes
    )


def _fred_graph(series_id: str, *, history_years: int = 3) -> RequestBuilder:
    if not re.fullmatch(r"[A-Z0-9]{2,32}", series_id):
        raise ValueError("V332_FRED_GRAPH_SERIES_INVALID")

    def build(_parameters: Mapping[str, str], _environment: Mapping[str, str], now: datetime) -> HttpRequest:
        start = (now - timedelta(days=366 * history_years)).date().isoformat()
        return _http(
            url=_url(
                "https://fred.stlouisfed.org/graph/fredgraph.csv",
                {"cosd": start, "id": series_id},
            ),
            headers={"Accept": "text/csv"},
            omit_user_agent=True,
        )

    return build


def _instrument(parameters: Mapping[str, str]) -> str:
    value = parameters.get("instrument_id", "BTC-USDT-SWAP")
    if _INSTRUMENT.fullmatch(value) is None:
        raise ValueError("V332_OKX_INSTRUMENT_INVALID")
    return value


def _okx(path: str, query_builder: Callable[[Mapping[str, str]], Mapping[str, str]]) -> RequestBuilder:
    def build(parameters: Mapping[str, str], _environment: Mapping[str, str], _now: datetime) -> HttpRequest:
        query = dict(query_builder(parameters))
        return _http(url=_url("https://openapi.okx.com" + path, query))

    return build


def _okx_ws(channel: str, *, liquidation: bool = False) -> RequestBuilder:
    def build(parameters: Mapping[str, str], _environment: Mapping[str, str], _now: datetime) -> WebSocketRequest:
        if liquidation:
            argument = {"channel": channel, "instType": "SWAP"}
        else:
            argument = {"channel": channel, "instId": _instrument(parameters)}
        message = json.dumps(
            {"op": "subscribe", "args": [argument]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        duration = float(parameters.get("duration_seconds", "12"))
        maximum = int(parameters.get("max_messages", "12"))
        if not 1 <= duration <= 300 or not 1 <= maximum <= 10_000:
            raise ValueError("V332_WS_WINDOW_INVALID")
        route = parameters.get("route", "primary")
        routes = {
            "primary": "wss://ws.okx.com:8443/ws/v5/public",
            "aws": "wss://wsaws.okx.com:8443/ws/v5/public",
        }
        try:
            endpoint = routes[route]
        except KeyError as exc:
            raise ValueError("V332_OKX_WS_ROUTE_INVALID") from exc
        return WebSocketRequest(
            url=endpoint,
            stored_url=endpoint,
            initial_messages=(message,),
            duration_seconds=duration,
            max_messages=maximum,
            max_bytes=32 * 1024 * 1024,
        )

    return build


def _bls(parameters: Mapping[str, str], _environment: Mapping[str, str], now: datetime) -> HttpRequest:
    start = parameters.get("startyear", str(now.year - 2))
    end = parameters.get("endyear", str(now.year))
    if not (start.isdigit() and end.isdigit() and 2000 <= int(start) <= int(end) <= now.year):
        raise ValueError("V332_BLS_YEAR_RANGE_INVALID")
    body = json.dumps(
        {
            "seriesid": [
                "CUUR0000SA0",
                "CUUR0000SA0L1E",
                "CES0000000001",
                "LNS14000000",
            ],
            "startyear": start,
            "endyear": end,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _http(
        url="https://api.bls.gov/publicAPI/v1/timeseries/data/",
        headers={"Content-Type": "application/json"},
        body=body,
    )


def _treasury(_parameters: Mapping[str, str], _environment: Mapping[str, str], now: datetime) -> HttpRequest:
    return _http(
        url=_url(
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml",
            {
                "data": "daily_treasury_yield_curve",
                "field_tdr_date_value": str(now.year),
            },
        ),
        headers={"Accept": "application/xml, text/xml"},
    )


def _gdelt(parameters: Mapping[str, str], _environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    query = parameters.get("query", "bitcoin OR BTC OR crypto ETF")
    if not query.strip() or len(query) > 300:
        raise ValueError("V332_GDELT_QUERY_INVALID")
    return _http(
        url=_url(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            {
                "format": "json",
                "maxrecords": "50",
                "mode": "artlist",
                "query": query,
                "sort": "datedesc",
                "timespan": "24h",
            },
        )
    )


def _coinmetrics(_parameters: Mapping[str, str], _environment: Mapping[str, str], now: datetime) -> HttpRequest:
    start = (now.astimezone(UTC) - timedelta(days=370)).date().isoformat()
    return _http(
        url=_url(
            "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
            {
                "assets": "btc",
                "end_time": now.astimezone(UTC).date().isoformat(),
                "frequency": "1d",
                "metrics": "AdrActCnt,TxCnt,FeeTotNtv,SplyCur,HashRate,BlkCnt",
                "page_size": "10000",
                "start_time": start,
            },
        ),
        max_bytes=24 * 1024 * 1024,
    )


def _trends(parameters: Mapping[str, str], _environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    geo = parameters.get("geo", "US")
    if not re.fullmatch(r"[A-Z]{2}", geo):
        raise ValueError("V332_TRENDS_GEO_INVALID")
    return _http(url=_url("https://trends.google.com/trending/rss", {"geo": geo}))


def _bluesky_search(parameters: Mapping[str, str], _environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    query = parameters.get("query", "bitcoin OR BTC")
    if not query.strip() or len(query) > 200:
        raise ValueError("V332_BLUESKY_QUERY_INVALID")
    return _http(
        url=_url(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
            {"limit": "50", "q": query, "sort": "latest"},
        )
    )


def _bluesky_firehose(parameters: Mapping[str, str], _environment: Mapping[str, str], _now: datetime) -> WebSocketRequest:
    duration = float(parameters.get("duration_seconds", "10"))
    maximum = int(parameters.get("max_messages", "20"))
    if not 1 <= duration <= 120 or not 1 <= maximum <= 1_000:
        raise ValueError("V332_BLUESKY_FIREHOSE_WINDOW_INVALID")
    url = "wss://relay1.us-east.bsky.network/xrpc/com.atproto.sync.subscribeRepos"
    return WebSocketRequest(
        url=url,
        stored_url=url,
        initial_messages=(),
        duration_seconds=duration,
        max_messages=maximum,
        max_bytes=32 * 1024 * 1024,
    )


def _secret_query(
    *,
    base: str,
    query: Mapping[str, str],
    secret_name: str,
    secret_key: str,
    environment: Mapping[str, str],
    max_bytes: int = 16 * 1024 * 1024,
) -> HttpRequest:
    actual = dict(query)
    actual[secret_key] = environment[secret_name]
    stored = dict(query)
    stored[secret_key] = "REDACTED"
    return _http(
        url=_url(base, actual),
        stored_url=_url(base, stored),
        max_bytes=max_bytes,
    )


def _fred(parameters: Mapping[str, str], environment: Mapping[str, str], now: datetime) -> HttpRequest:
    series = parameters.get("series_id", "DGS10")
    if not re.fullmatch(r"[A-Z0-9._-]{1,64}", series):
        raise ValueError("V332_FRED_SERIES_INVALID")
    start = parameters.get(
        "observation_start", (now.astimezone(UTC) - timedelta(days=730)).date().isoformat()
    )
    query = {
        "file_type": "json",
        "observation_start": start,
        "series_id": series,
    }
    for name in ("observation_start", "observation_end", "realtime_start", "realtime_end"):
        value = parameters.get(name, query.get(name))
        if value is None:
            continue
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("V332_FRED_DATE_INVALID") from exc
        if parsed > now.astimezone(UTC).date():
            raise ValueError("V332_FRED_FUTURE_DATE_INVALID")
        query[name] = value
    if query.get("observation_end", "9999-12-31") < query["observation_start"]:
        raise ValueError("V332_FRED_OBSERVATION_RANGE_INVALID")
    if query.get("realtime_end", "9999-12-31") < query.get("realtime_start", "1776-07-04"):
        raise ValueError("V332_FRED_REALTIME_RANGE_INVALID")
    return _secret_query(
        base="https://api.stlouisfed.org/fred/series/observations",
        query=query,
        secret_name="FRED_API_KEY",
        secret_key="api_key",
        environment=environment,
    )


def _eia(_parameters: Mapping[str, str], environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    return _secret_query(
        base="https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
        query={
            "data[0]": "value",
            "frequency": "weekly",
            "length": "100",
            "offset": "0",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
        },
        secret_name="EIA_API_KEY",
        secret_key="api_key",
        environment=environment,
    )


def _bea(_parameters: Mapping[str, str], environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    return _secret_query(
        base="https://apps.bea.gov/api/data/",
        query={
            "Frequency": "Q",
            "Method": "GetData",
            "ResultFormat": "JSON",
            "TableName": "T10101",
            "Year": "X",
            "datasetname": "NIPA",
        },
        secret_name="BEA_USER_ID",
        secret_key="UserID",
        environment=environment,
    )


def _youtube(parameters: Mapping[str, str], environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    query = parameters.get("query", "bitcoin")
    if not query.strip() or len(query) > 200:
        raise ValueError("V332_YOUTUBE_QUERY_INVALID")
    return _secret_query(
        base="https://www.googleapis.com/youtube/v3/search",
        query={
            "maxResults": "25",
            "order": "date",
            "part": "snippet",
            "q": query,
            "type": "video",
        },
        secret_name="YOUTUBE_API_KEY",
        secret_key="key",
        environment=environment,
    )


def _alphavantage(parameters: Mapping[str, str], environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    symbol = parameters.get("symbol", "SPY")
    if not re.fullmatch(r"[A-Z0-9.-]{1,16}", symbol):
        raise ValueError("V332_ALPHA_VANTAGE_SYMBOL_INVALID")
    return _secret_query(
        base="https://www.alphavantage.co/query",
        query={"function": "TIME_SERIES_DAILY", "outputsize": "compact", "symbol": symbol},
        secret_name="ALPHAVANTAGE_API_KEY",
        secret_key="apikey",
        environment=environment,
    )


def _sec(parameters: Mapping[str, str], environment: Mapping[str, str], _now: datetime) -> HttpRequest:
    cik = parameters["cik"].zfill(10)
    if not (cik.isdigit() and len(cik) == 10):
        raise ValueError("V332_SEC_CIK_INVALID")
    return _http(
        url=f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers={"User-Agent": environment["SEC_USER_AGENT"]},
        stored_headers={"User-Agent": "CONFIGURED_REDACTED"},
    )


def _definition(
    source_id: str,
    family: str,
    dataset: str,
    provider: str,
    access: AccessMode,
    transport: TransportKind,
    endpoint: str,
    terms: str,
    cadence: str,
    history: str,
    time_semantics: str,
    ceiling: str,
    *,
    required_env: tuple[str, ...] = (),
    required_parameters: tuple[str, ...] = (),
    default: bool = False,
    stream: bool = False,
) -> SourceDefinition:
    return SourceDefinition(
        source_id=source_id,
        family=family,
        dataset=dataset,
        provider=provider,
        access_mode=access,
        transport=transport,
        endpoint=endpoint,
        terms_url=terms,
        cadence=cadence,
        history=history,
        time_semantics=time_semantics,
        claim_ceiling=ceiling,
        required_env=required_env,
        required_parameters=required_parameters,
        default_enabled=default,
        stream=stream,
    )


_OKX_DOCS = "https://www.okx.com/docs-v5/en/"
_OKX_TERMS = "https://www.okx.com/en-us/help/okx-api-agreement"
_CAPTURE_TIME = "available_at is conservatively the local response receipt time"


def _sources() -> tuple[SourceAdapter, ...]:
    sources: list[SourceAdapter] = []

    def add(definition: SourceDefinition, builder: RequestBuilder | None) -> None:
        sources.append(SourceAdapter(definition, builder))

    okx_specs = (
        ("okx.server_time", "Server time", "/api/v5/public/time", lambda p: {}),
        ("okx.instrument", "Instrument identity", "/api/v5/public/instruments", lambda p: {"instId": _instrument(p), "instType": "SWAP"}),
        ("okx.mark_price", "Mark price", "/api/v5/public/mark-price", lambda p: {"instId": _instrument(p), "instType": "SWAP"}),
        ("okx.candles_15m", "Closed 15m candles", "/api/v5/market/history-candles", lambda p: {"bar": "15m", "instId": _instrument(p), "limit": "100"}),
        ("okx.candles_1h", "Closed 1h candles", "/api/v5/market/history-candles", lambda p: {"bar": "1H", "instId": _instrument(p), "limit": "100"}),
        ("okx.candles_4h", "Closed 4h candles", "/api/v5/market/history-candles", lambda p: {"bar": "4H", "instId": _instrument(p), "limit": "100"}),
        ("okx.candles_1d", "Closed UTC daily candles", "/api/v5/market/history-candles", lambda p: {"bar": "1Dutc", "instId": _instrument(p), "limit": "100"}),
        ("okx.order_book", "Order-book snapshot", "/api/v5/market/books", lambda p: {"instId": _instrument(p), "sz": "400"}),
        ("okx.recent_trades", "Recent public trades", "/api/v5/market/trades", lambda p: {"instId": _instrument(p), "limit": "100"}),
        ("okx.open_interest", "Open interest", "/api/v5/public/open-interest", lambda p: {"instId": _instrument(p), "instType": "SWAP"}),
        ("okx.funding_history", "Funding-rate history", "/api/v5/public/funding-rate-history", lambda p: {"instId": _instrument(p), "limit": "100"}),
        ("okx.taker_volume", "Contract taker buy/sell volume", "/api/v5/rubik/stat/taker-volume-contract", lambda p: {"instId": _instrument(p), "period": "5m"}),
        ("okx.long_short_contract", "Contract account long/short ratio", "/api/v5/rubik/stat/contracts/long-short-account-ratio-contract", lambda p: {"instId": _instrument(p), "period": "5m"}),
        ("okx.long_short_currency", "BTC aggregate long/short ratio", "/api/v5/rubik/stat/contracts/long-short-account-ratio", lambda p: {"ccy": "BTC", "period": "5m"}),
        ("okx.block_trades", "Delayed public block trades", "/api/v5/public/block-trades", lambda p: {"instId": _instrument(p), "limit": "100"}),
    )
    for source_id, dataset, path, query in okx_specs:
        add(
            _definition(
                source_id,
                "market_microstructure" if source_id not in {"okx.server_time", "okx.instrument"} else "market_identity",
                dataset,
                "OKX",
                AccessMode.NO_AUTH,
                TransportKind.HTTP,
                "https://openapi.okx.com" + path,
                _OKX_TERMS,
                "per cycle; respect official IP rate limits",
                "provider endpoint window only; paginate only under a separately frozen request",
                _CAPTURE_TIME,
                "OKX-visible public aggregate only; no participant identity or account truth",
                default=True,
            ),
            _okx(path, query),
        )

    add(
        _definition(
            "okx.order_book_stream", "market_microstructure", "400-level incremental order book", "OKX", AccessMode.NO_AUTH, TransportKind.WEBSOCKET,
            "wss://ws.okx.com:8443/ws/v5/public", _OKX_TERMS, "finite forward capture windows", "forward only", _CAPTURE_TIME,
            "Finite raw public book frames only; sequence continuity, checksum reconstruction, hidden liquidity and unrecorded history remain unknown", stream=True,
        ),
        _okx_ws("books"),
    )
    add(
        _definition(
            "okx.liquidation_stream", "leverage", "Recent liquidation-order stream", "OKX", AccessMode.NO_AUTH, TransportKind.WEBSOCKET,
            "wss://ws.okx.com:8443/ws/v5/public", _OKX_TERMS, "finite forward capture windows", "forward only", _CAPTURE_TIME,
            "Official feed is explicitly not the complete OKX liquidation ledger", stream=True,
        ),
        _okx_ws("liquidation-orders", liquidation=True),
    )

    no_auth_http = (
        (_definition("bls.labor_snapshot", "macro", "CPI, core CPI, payrolls and unemployment", "U.S. BLS", AccessMode.NO_AUTH, TransportKind.HTTP, "https://api.bls.gov/publicAPI/v1/timeseries/data/", "https://www.bls.gov/developers/termsOfService.htm", "daily check; use official release cadence", "requested calendar years", _CAPTURE_TIME, "Published observations and revisions only; no consensus forecast", default=True), _bls),
        (_definition("treasury.yield_curve", "macro_cross_asset", "Daily Treasury par yield curve", "U.S. Treasury", AccessMode.NO_AUTH, TransportKind.HTTP, "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml", "https://home.treasury.gov/utility/policies-and-notices", "daily", "current calendar year per request", _CAPTURE_TIME, "Official published daily curve; not intraday Treasury market depth", default=True), _treasury),
        (_definition("fed.h15_current", "macro_cross_asset", "Current H.15 interest rates page", "Federal Reserve", AccessMode.NO_AUTH, TransportKind.HTTP, "https://www.federalreserve.gov/releases/h15/current/", "https://www.federalreserve.gov/website-linking-policies.htm", "daily", "current release page", _CAPTURE_TIME, "Published H.15 page; revisions/vintages require separately preserved releases", default=True), _static_get("https://www.federalreserve.gov/releases/h15/current/")),
        (_definition("fed.h10_current", "macro_cross_asset", "Current H.10 foreign exchange rates page", "Federal Reserve", AccessMode.NO_AUTH, TransportKind.HTTP, "https://www.federalreserve.gov/releases/h10/current/", "https://www.federalreserve.gov/website-linking-policies.htm", "weekly", "current release page", _CAPTURE_TIME, "Published H.10 rates; not executable FX quotes", default=True), _static_get("https://www.federalreserve.gov/releases/h10/current/")),
        (_definition("ecb.usd_eur_daily", "macro_cross_asset", "ECB USD per EUR reference rates", "ECB", AccessMode.NO_AUTH, TransportKind.HTTP, "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A", "https://data.ecb.europa.eu/help/api/overview", "daily", "latest 90 observations", _CAPTURE_TIME, "ECB reference rate, not an executable quote", default=True), _static_get("https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata&lastNObservations=90")),
        (_definition("cboe.vix_daily", "cross_asset", "VIX official daily history", "Cboe", AccessMode.NO_AUTH, TransportKind.HTTP, "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", "https://www.cboe.com/us_disclaimers/", "daily", "1990-present file", _CAPTURE_TIME, "Official daily close history; no free realtime VIX tape", default=True), _static_get("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", max_bytes=32 * 1024 * 1024)),
        (_definition("gdelt.bitcoin_news", "news_events", "Bitcoin-related news discovery", "GDELT", AccessMode.NO_AUTH, TransportKind.HTTP, "https://api.gdeltproject.org/api/v2/doc/doc", "https://www.gdeltproject.org/about.html", "15 minutes", "query window, default last 24h", _CAPTURE_TIME, "Metadata/media sample; not article-body rights, causal truth or total news coverage", default=True), _gdelt),
        (_definition("fed.press_releases", "news_events", "Federal Reserve press release RSS", "Federal Reserve", AccessMode.NO_AUTH, TransportKind.HTTP, "https://www.federalreserve.gov/feeds/press_all.xml", "https://www.federalreserve.gov/website-linking-policies.htm", "on release", "feed window", _CAPTURE_TIME, "Official public release feed only", default=True), _static_get("https://www.federalreserve.gov/feeds/press_all.xml")),
        (_definition("bls.latest_releases", "news_events", "BLS latest numbers RSS", "U.S. BLS", AccessMode.NO_AUTH, TransportKind.HTTP, "https://www.bls.gov/feed/bls_latest.rss", "https://www.bls.gov/bls/linksite.htm", "on release", "feed window", _CAPTURE_TIME, "Official public release feed only", default=True), _static_get("https://www.bls.gov/feed/bls_latest.rss")),
        (_definition("cftc.cot_current", "institutional_proxy", "Current Traders in Financial Futures COT", "CFTC", AccessMode.NO_AUTH, TransportKind.HTTP, "https://www.cftc.gov/dea/newcot/FinFutWk.txt", "https://www.cftc.gov/WebPolicies/index.htm", "weekly", "current weekly report", _CAPTURE_TIME, "Lagged category aggregates for codes 133741/133742; not trader identity or current intent", default=True), _static_get("https://www.cftc.gov/dea/newcot/FinFutWk.txt", max_bytes=24 * 1024 * 1024)),
        (_definition("nyfed.primary_dealer_latest", "institutional_proxy", "Latest primary-dealer statistics", "New York Fed", AccessMode.NO_AUTH, TransportKind.HTTP, "https://markets.newyorkfed.org/api/pd/latest/SBN2024.json", "https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics", "weekly", "current series break from July 2024", _CAPTURE_TIME, "Aggregate dealer activity; not crypto-specific institution identity", default=True), _static_get("https://markets.newyorkfed.org/api/pd/latest/SBN2024.json", max_bytes=32 * 1024 * 1024)),
        (_definition("coinmetrics.btc_daily", "onchain", "BTC community asset metrics", "Coin Metrics", AccessMode.NO_AUTH, TransportKind.HTTP, "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics", "https://docs.coinmetrics.io/api/v4/", "daily", "rolling 370 days in one request", _CAPTURE_TIME, "Community metrics AdrActCnt, TxCnt, FeeTotNtv, SplyCur, HashRate, BlkCnt only", default=True), _coinmetrics),
        (_definition("blockstream.chain_tip", "onchain", "Bitcoin chain tip height", "Blockstream Esplora", AccessMode.NO_AUTH, TransportKind.HTTP, "https://blockstream.info/api/blocks/tip/height", "https://github.com/Blockstream/esplora/blob/master/API.md", "per daily context", "current tip", _CAPTURE_TIME, "Public node observation; not chain-wide provider availability", default=True), _static_get("https://blockstream.info/api/blocks/tip/height")),
        (_definition("blockstream.mempool", "onchain", "Bitcoin mempool aggregate", "Blockstream Esplora", AccessMode.NO_AUTH, TransportKind.HTTP, "https://blockstream.info/api/mempool", "https://github.com/Blockstream/esplora/blob/master/API.md", "per daily context", "current snapshot", _CAPTURE_TIME, "One public node's mempool view, not a universal mempool truth", default=True), _static_get("https://blockstream.info/api/mempool")),
        (_definition("blockstream.fee_estimates", "onchain", "Bitcoin fee estimates", "Blockstream Esplora", AccessMode.NO_AUTH, TransportKind.HTTP, "https://blockstream.info/api/fee-estimates", "https://github.com/Blockstream/esplora/blob/master/API.md", "per daily context", "current estimate", _CAPTURE_TIME, "Provider estimate, not guaranteed execution fee", default=True), _static_get("https://blockstream.info/api/fee-estimates")),
        (_definition("defillama.chains", "onchain_cross_asset", "Chain TVL snapshot", "DefiLlama", AccessMode.NO_AUTH, TransportKind.HTTP, "https://api.llama.fi/v2/chains", "https://defillama.com/terms", "daily", "current snapshot", _CAPTURE_TIME, "Provider-defined TVL aggregate; not direct BTC-chain truth", default=True), _static_get("https://api.llama.fi/v2/chains")),
        (_definition("defillama.stablecoins", "onchain_cross_asset", "Stablecoin supply context", "DefiLlama", AccessMode.NO_AUTH, TransportKind.HTTP, "https://stablecoins.llama.fi/stablecoins", "https://defillama.com/terms", "daily", "current snapshot", _CAPTURE_TIME, "Provider-defined stablecoin aggregate; terms restrict mirroring/redistribution", default=True), _static_get("https://stablecoins.llama.fi/stablecoins?includePrices=true", max_bytes=32 * 1024 * 1024)),
        (_definition("defillama.dex_volume", "onchain_cross_asset", "DEX volume overview", "DefiLlama", AccessMode.NO_AUTH, TransportKind.HTTP, "https://api.llama.fi/overview/dexs", "https://defillama.com/terms", "daily", "endpoint-defined history/snapshot", _CAPTURE_TIME, "Provider-defined DEX aggregate; not centralized BTC venue flow", default=True), _static_get("https://api.llama.fi/overview/dexs?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true", max_bytes=32 * 1024 * 1024)),
        (_definition("defillama.open_interest", "onchain_cross_asset", "DeFi open-interest overview", "DefiLlama", AccessMode.NO_AUTH, TransportKind.HTTP, "https://api.llama.fi/overview/open-interest", "https://defillama.com/terms", "daily", "endpoint-defined history/snapshot", _CAPTURE_TIME, "Provider-defined DeFi aggregate; no trader identity", default=True), _static_get("https://api.llama.fi/overview/open-interest?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true", max_bytes=32 * 1024 * 1024)),
        (_definition("google_trends.trending_now", "search_sentiment_proxy", "Google Trending Now RSS", "Google Trends", AccessMode.NO_AUTH, TransportKind.HTTP, "https://trends.google.com/trending/rss", "https://policies.google.com/terms", "about 10 minutes", "current trending window", _CAPTURE_TIME, "Trending queries only; not arbitrary keyword history or absolute search volume", default=True), _trends),
        (_definition("bluesky.search_posts", "social_sentiment_proxy", "Public Bluesky post search", "Bluesky", AccessMode.NO_AUTH, TransportKind.HTTP, "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts", "https://bsky.social/about/support/tos", "finite query samples", "AppView search window", _CAPTURE_TIME, "Public AppView sample; not total social sentiment and endpoint reachability may vary", default=True), _bluesky_search),
    )
    for definition, builder in no_auth_http:
        add(definition, builder)

    add(
        _definition(
            "eia.bulk_manifest", "macro_cross_asset", "Public bulk-download manifest", "EIA",
            AccessMode.NO_AUTH, TransportKind.HTTP,
            "https://www.eia.gov/opendata/bulk/manifest.txt",
            "https://www.eia.gov/about/copyrights_reuse.php", "daily",
            "current manifest and official bulk access URLs", _CAPTURE_TIME,
            "Dataset metadata and download locations only; targeted EIA API observations still require a free key",
            default=True,
        ),
        _static_get("https://www.eia.gov/opendata/bulk/manifest.txt", max_bytes=4 * 1024 * 1024),
    )

    fred_graph_specs = (
        ("fred_graph.cpi", "macro", "CPI all items", "CPIAUCSL", 12),
        ("fred_graph.core_cpi", "macro", "Core CPI", "CPILFESL", 12),
        ("fred_graph.payrolls", "macro", "Total nonfarm payrolls", "PAYEMS", 12),
        ("fred_graph.unemployment", "macro", "Unemployment rate", "UNRATE", 12),
        ("fred_graph.real_gdp", "macro", "Real GDP", "GDPC1", 12),
        ("fred_graph.fed_funds", "macro_cross_asset", "Effective federal funds rate", "DFF", 3),
        ("fred_graph.treasury_2y", "macro_cross_asset", "2-year Treasury rate", "DGS2", 3),
        ("fred_graph.treasury_10y", "macro_cross_asset", "10-year Treasury rate", "DGS10", 3),
        ("fred_graph.yield_spread_10y2y", "macro_cross_asset", "10y minus 2y Treasury spread", "T10Y2Y", 3),
        ("fred_graph.usd_index", "macro_cross_asset", "Nominal broad U.S. dollar index", "DTWEXBGS", 3),
        ("fred_graph.wti", "macro_cross_asset", "WTI crude-oil spot proxy", "DCOILWTICO", 3),
        ("fred_graph.fed_balance_sheet", "macro_cross_asset", "Federal Reserve total assets", "WALCL", 5),
        ("fred_graph.nfci_leverage", "leverage_cross_asset", "NFCI leverage subindex", "NFCILEVERAGE", 5),
    )
    for source_id, family, dataset, series_id, years in fred_graph_specs:
        add(
            _definition(
                source_id, family, dataset, "FRED graph CSV", AccessMode.NO_AUTH,
                TransportKind.HTTP, "https://fred.stlouisfed.org/graph/fredgraph.csv",
                "https://fred.stlouisfed.org/legal/", "source-series cadence",
                f"rolling {years} years", _CAPTURE_TIME,
                f"Current-revision FRED series {series_id}; not an ALFRED point-in-time vintage and source-specific notes still apply",
                default=True,
            ),
            _fred_graph(series_id, history_years=years),
        )

    add(
        _definition("bluesky.firehose_raw", "social_sentiment_proxy", "AT Protocol repository firehose raw frames", "Bluesky", AccessMode.NO_AUTH, TransportKind.WEBSOCKET, "wss://relay1.us-east.bsky.network/xrpc/com.atproto.sync.subscribeRepos", "https://bsky.social/about/support/tos", "finite forward capture windows", "forward only", _CAPTURE_TIME, "Raw CBOR/CAR frames only until a separately verified decoder is admitted", stream=True),
        _bluesky_firehose,
    )

    credential_sources = (
        (_definition("sec.submissions", "institutional_filings", "EDGAR submissions by CIK", "SEC", AccessMode.CONTACT_HEADER, TransportKind.HTTP, "https://data.sec.gov/submissions/CIK##########.json", "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data", "daily or on official RSS event", "full submissions index exposed by endpoint", _CAPTURE_TIME, "Public filings are lagged disclosures, not current institution intent", required_env=("SEC_USER_AGENT",), required_parameters=("cik",)), _sec),
        (_definition("fred.series", "macro_cross_asset", "FRED observations with optional ALFRED realtime window", "Federal Reserve Bank of St. Louis", AccessMode.FREE_KEY, TransportKind.HTTP, "https://api.stlouisfed.org/fred/series/observations", "https://fred.stlouisfed.org/docs/api/terms_of_use.html", "series cadence", "requested observation/realtime window", _CAPTURE_TIME, "Current revision by default; a point-in-time claim requires explicit realtime_start/realtime_end and preserved raw response", required_env=("FRED_API_KEY",)), _fred),
        (_definition("eia.crude_stocks", "macro_cross_asset", "Weekly U.S. crude oil stocks", "EIA", AccessMode.FREE_KEY, TransportKind.HTTP, "https://api.eia.gov/v2/petroleum/stoc/wstk/data/", "https://www.eia.gov/about/copyrights_reuse.php", "weekly", "latest 100 observations", _CAPTURE_TIME, "Published EIA aggregate, not realtime executable oil data", required_env=("EIA_API_KEY",)), _eia),
        (_definition("bea.gdp", "macro", "NIPA GDP table", "BEA", AccessMode.FREE_KEY, TransportKind.HTTP, "https://apps.bea.gov/api/data/", "https://apps.bea.gov/API/docs/terms.htm", "quarterly/release cadence", "all available years requested by API", _CAPTURE_TIME, "Published/revised macro aggregate, not consensus expectation", required_env=("BEA_USER_ID",)), _bea),
        (_definition("youtube.search", "social_sentiment_proxy", "Recent public YouTube videos", "YouTube", AccessMode.FREE_KEY, TransportKind.HTTP, "https://www.googleapis.com/youtube/v3/search", "https://developers.google.com/youtube/terms/api-services-terms-of-service", "bounded query samples", "latest 25 results", _CAPTURE_TIME, "Selected public-video sample; retention and quota rules apply", required_env=("YOUTUBE_API_KEY",)), _youtube),
        (_definition("alphavantage.daily", "cross_asset", "Daily equity/ETF proxy series", "Alpha Vantage", AccessMode.FREE_KEY, TransportKind.HTTP, "https://www.alphavantage.co/query", "https://www.alphavantage.co/terms_of_service/", "daily", "free compact window", _CAPTURE_TIME, "Free daily proxy only; realtime exchange data is not included", required_env=("ALPHAVANTAGE_API_KEY",)), _alphavantage),
    )
    for definition, builder in credential_sources:
        add(definition, builder)

    manual_sources = (
        _definition("google_trends.manual_csv", "search_sentiment_proxy", "User-selected Google Trends CSV", "Google Trends", AccessMode.MANUAL_PUBLIC_EXPORT, TransportKind.MANUAL_FILE, "https://trends.google.com/trends/explore", "https://policies.google.com/terms", "user-selected", "export-selected time range", "user must record download availability time", "Normalized relative interest 0-100, not absolute query volume"),
        _definition("btc_etf.issuer_holdings_manual", "institutional_proxy", "Official issuer BTC ETF holdings export", "ETF issuer pages", AccessMode.MANUAL_PUBLIC_EXPORT, TransportKind.MANUAL_FILE, "https://www.sec.gov/edgar/search/", "https://www.sec.gov/privacy.htm", "daily where issuer publishes", "file-specific", "user must record issuer publication and download times", "Issuer-specific holdings/shares only; compiled flow remains derived"),
    )
    for definition in manual_sources:
        add(definition, None)

    unavailable = (
        _definition("google_trends.alpha_api", "search_sentiment_proxy", "Official Trends API alpha", "Google", AccessMode.APPLICATION_REQUIRED, TransportKind.UNAVAILABLE, "https://developers.google.com/search/apis/trends", "https://policies.google.com/terms", "provider-defined", "rolling provider window", "not active before approval", "Alpha approval required; not an open public API"),
        _definition("opennews.aggregator", "news_events", "6551 OpenNews aggregator", "6551", AccessMode.APPLICATION_REQUIRED, TransportKind.UNAVAILABLE, "https://6551.io/mcp", "https://6551.io/", "provider-defined", "provider-defined", "not active before token and licence review", "Bearer token and reuse terms must be confirmed"),
        _definition("opentwitter.aggregator", "social_sentiment_proxy", "6551 Twitter aggregator", "6551", AccessMode.APPLICATION_REQUIRED, TransportKind.UNAVAILABLE, "https://6551.io/mcp", "https://6551.io/", "provider-defined", "provider-defined", "not active before token and licence review", "Bearer token and X-data reuse terms must be confirmed"),
        _definition("reddit.research_api", "social_sentiment_proxy", "Reddit research data", "Reddit", AccessMode.APPLICATION_REQUIRED, TransportKind.UNAVAILABLE, "https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data", "https://www.redditinc.com/policies/data-api-terms", "approved project only", "approval-defined", "not active before approval", "Research approval and qualifying identity are required"),
        _definition("x.official_api", "social_sentiment_proxy", "X official API", "X", AccessMode.APPLICATION_REQUIRED, TransportKind.UNAVAILABLE, "https://docs.x.com/x-api/getting-started/about-x-api", "https://developer.x.com/en/developer-terms/agreement-and-policy", "plan-defined", "plan-defined", "not active before account and plan", "Not a no-account free public source"),
        _definition("execution.account_truth", "execution_truth", "Fills, fees, latency, positions and slippage", "Account-side ledger", AccessMode.SEPARATE_AUTHORITY, TransportKind.UNAVAILABLE, "https://www.okx.com/docs-v5/en/", _OKX_TERMS, "account event cadence", "account-defined", "requires separately authorized account data", "Public data cannot establish execution truth"),
        _definition("institution.current_intent", "institutional_truth", "Current institution identity and intent", "No public provider", AccessMode.UNOBSERVABLE, TransportKind.UNAVAILABLE, "https://www.sec.gov/edgar/search/", "https://www.sec.gov/privacy.htm", "not observable", "not observable", "not observable", "Public filings and large trades remain lagged proxies"),
        _definition("okx.complete_liquidation_ledger", "leverage_truth", "Complete liquidation ledger", "No public provider", AccessMode.UNOBSERVABLE, TransportKind.UNAVAILABLE, _OKX_DOCS, _OKX_TERMS, "not observable", "not observable", "not observable", "OKX public liquidation stream explicitly does not represent all liquidations"),
        _definition("sentiment.total_population", "sentiment_truth", "Complete human or market emotion", "No public provider", AccessMode.UNOBSERVABLE, TransportKind.UNAVAILABLE, "https://trends.google.com/trends/", "https://policies.google.com/terms", "not observable", "not observable", "not observable", "Search/social samples are proxies, never population emotion truth"),
    )
    for definition in unavailable:
        add(definition, None)
    return tuple(sources)


class SourceCatalog:
    def __init__(self) -> None:
        sources = _sources()
        mapping = {source.definition.source_id: source for source in sources}
        if len(mapping) != len(sources):
            raise ValueError("V332_SOURCE_CATALOG_DUPLICATE")
        self._mapping = mapping

    def list(self) -> tuple[SourceAdapter, ...]:
        return tuple(self._mapping[key] for key in sorted(self._mapping))

    def get(self, source_id: str) -> SourceAdapter:
        try:
            return self._mapping[source_id]
        except KeyError as exc:
            raise KeyError("V332_SOURCE_NOT_REGISTERED") from exc


__all__ = ["SourceAdapter", "SourceCatalog"]
