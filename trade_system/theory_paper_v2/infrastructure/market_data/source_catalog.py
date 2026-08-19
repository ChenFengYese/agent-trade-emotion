"""Frozen public OKX source contracts for the first V3.3.2 data slice."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from ...domain.market_cycle.data import SourceContractV1
from .okx_transport import (
    CLOSED_CANDLES_15M_PATH,
    FUNDING_RATE_HISTORY_PATH,
    INSTRUMENT_PATH,
    MARK_PRICE_PATH,
    OKX_PUBLIC_BASE_URL,
    OPEN_INTEREST_PATH,
    ORDER_BOOK_PATH,
    RECENT_TRADES_PATH,
    SERVER_TIME_PATH,
)


OKX_TERMS_REF = "https://www.okx.com/en-us/help/okx-api-agreement"
OKX_SERVER_TIME_SOURCE_ID = "okx.public.server_time"
OKX_INSTRUMENT_SOURCE_ID = "okx.public.swap_instrument"
OKX_MARK_PRICE_SOURCE_ID = "okx.public.mark_price"
OKX_CLOSED_CANDLES_SOURCE_ID = "okx.market.closed_candles_15m"
OKX_ORDER_BOOK_SOURCE_ID = "okx.market.order_book_depth_20"
OKX_RECENT_TRADES_SOURCE_ID = "okx.market.recent_trades_100"
OKX_OPEN_INTEREST_SOURCE_ID = "okx.public.open_interest"
OKX_FUNDING_HISTORY_SOURCE_ID = "okx.public.funding_history_10"


class SourceCatalogError(ValueError):
    """A caller requested an unregistered or ambiguous public source."""


@dataclass(frozen=True, slots=True)
class SourceRouteV1:
    """Infrastructure route bound to one domain source contract."""

    contract: SourceContractV1
    capture_id: str
    component_id: str
    path: str
    required_for_core: bool
    parser_version: str

    def __post_init__(self) -> None:
        for field_name in ("capture_id", "component_id", "path", "parser_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise SourceCatalogError(
                    f"V332_SOURCE_ROUTE_{field_name.upper()}_INVALID"
                )
        if not self.path.startswith("/"):
            raise SourceCatalogError("V332_SOURCE_ROUTE_PATH_INVALID")
        if type(self.required_for_core) is not bool:
            raise SourceCatalogError("V332_SOURCE_ROUTE_CORE_FLAG_INVALID")

    @property
    def source_id(self) -> str:
        return self.contract.source_id


class SourceCatalogV1:
    """Small explicit registry; lookup never supplies a default instrument."""

    def __init__(self, routes: Sequence[SourceRouteV1]) -> None:
        supplied = tuple(routes)
        if not supplied or not all(isinstance(item, SourceRouteV1) for item in supplied):
            raise SourceCatalogError("V332_SOURCE_CATALOG_ROUTES_INVALID")
        by_source = {item.source_id: item for item in supplied}
        by_capture = {item.capture_id: item for item in supplied}
        by_component = {item.component_id: item for item in supplied}
        if not (
            len(by_source)
            == len(by_capture)
            == len(by_component)
            == len(supplied)
        ):
            raise SourceCatalogError("V332_SOURCE_CATALOG_IDENTITY_DUPLICATE")
        self._routes = supplied
        self._by_source = MappingProxyType(by_source)
        self._by_capture = MappingProxyType(by_capture)
        self._by_component = MappingProxyType(by_component)

    @property
    def routes(self) -> tuple[SourceRouteV1, ...]:
        return self._routes

    @property
    def core_routes(self) -> tuple[SourceRouteV1, ...]:
        return tuple(item for item in self._routes if item.required_for_core)

    @property
    def optional_routes(self) -> tuple[SourceRouteV1, ...]:
        return tuple(item for item in self._routes if not item.required_for_core)

    def require(self, source_id: str) -> SourceRouteV1:
        try:
            return self._by_source[source_id]
        except (KeyError, TypeError) as exc:
            raise SourceCatalogError(
                f"V332_SOURCE_NOT_REGISTERED:{source_id}"
            ) from exc

    def for_capture(self, capture_id: str) -> SourceRouteV1:
        try:
            return self._by_capture[capture_id]
        except (KeyError, TypeError) as exc:
            raise SourceCatalogError(
                f"V332_CAPTURE_NOT_REGISTERED:{capture_id}"
            ) from exc

    def for_component(self, component_id: str) -> SourceRouteV1:
        try:
            return self._by_component[component_id]
        except (KeyError, TypeError) as exc:
            raise SourceCatalogError(
                f"V332_COMPONENT_NOT_REGISTERED:{component_id}"
            ) from exc


def _contract(
    source_id: str,
    dataset: str,
    path: str,
    *,
    parameters: Mapping[str, str],
    cadence: str,
    history_window: str,
    event_time: str,
    publish_time: str,
    claim_ceiling: str,
    max_staleness_seconds: int,
) -> SourceContractV1:
    return SourceContractV1(
        source_id=source_id,
        provider="OKX",
        dataset=dataset,
        transport="HTTPS_GET",
        access_mode="NO_AUTH_PUBLIC",
        official_endpoint=OKX_PUBLIC_BASE_URL + path,
        terms_ref=OKX_TERMS_REF,
        instrument_scope="ONE_EXPLICIT_OKX_SWAP_OR_PROVIDER_CLOCK",
        cadence=cadence,
        history_window=history_window,
        event_time_semantics=event_time,
        publish_time_semantics=publish_time,
        claim_ceiling=claim_ceiling,
        required_parameters=parameters,
        rate_limit_policy="CALLER_BOUNDED_SINGLE_PROFILE",
        retry_policy="ONE_ATTEMPT_NO_RETRY_NO_FALLBACK",
        max_staleness_seconds=max_staleness_seconds,
    )


def build_okx_source_catalog() -> SourceCatalogV1:
    """Return the eight bounded REST routes used by the HYPE HTTP profile."""

    routes = (
        SourceRouteV1(
            _contract(
                OKX_SERVER_TIME_SOURCE_ID,
                "PUBLIC_SERVER_TIME",
                SERVER_TIME_PATH,
                parameters={},
                cadence="ONCE_PER_ASSET_SLICE",
                history_window="POINT_IN_TIME",
                event_time="provider ts in UNIX milliseconds",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="OKX server clock observed for this capture only",
                max_staleness_seconds=120,
            ),
            "server-time",
            "SERVER_TIME",
            SERVER_TIME_PATH,
            True,
            "okx-baseline-price-v1",
        ),
        SourceRouteV1(
            _contract(
                OKX_INSTRUMENT_SOURCE_ID,
                "PUBLIC_SWAP_INSTRUMENT",
                INSTRUMENT_PATH,
                parameters={"instId": "EXPLICIT", "instType": "SWAP"},
                cadence="ONCE_PER_ASSET_SLICE",
                history_window="CURRENT_PROVIDER_METADATA",
                event_time="response receipt time; provider supplies no row timestamp",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="current OKX product identity and contract metadata only",
                max_staleness_seconds=300,
            ),
            "instrument",
            "INSTRUMENT",
            INSTRUMENT_PATH,
            True,
            "okx-baseline-price-v1",
        ),
        SourceRouteV1(
            _contract(
                OKX_MARK_PRICE_SOURCE_ID,
                "PUBLIC_SWAP_MARK_PRICE",
                MARK_PRICE_PATH,
                parameters={"instId": "EXPLICIT", "instType": "SWAP"},
                cadence="ONCE_PER_ASSET_SLICE",
                history_window="POINT_IN_TIME",
                event_time="provider ts in UNIX milliseconds",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="one OKX mark-price observation; not cross-venue truth",
                max_staleness_seconds=120,
            ),
            "mark-price",
            "MARK_PRICE",
            MARK_PRICE_PATH,
            True,
            "okx-baseline-price-v1",
        ),
        SourceRouteV1(
            _contract(
                OKX_CLOSED_CANDLES_SOURCE_ID,
                "MARKET_HISTORY_CANDLES_15M",
                CLOSED_CANDLES_15M_PATH,
                parameters={
                    "after": "SERVER_TIME_15M_BOUNDARY",
                    "bar": "15m",
                    "instId": "EXPLICIT",
                    "limit": "96",
                },
                cadence="ONCE_PER_ASSET_SLICE",
                history_window="UP_TO_96_CONTIGUOUS_CONFIRMED_15M_BARS",
                event_time="bar open time; confirm=1 and full interval define close",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="closed OKX 15m OHLC path in the captured window only",
                max_staleness_seconds=1800,
            ),
            "closed-candles-15m",
            "CLOSED_CANDLES_15M",
            CLOSED_CANDLES_15M_PATH,
            True,
            "okx-baseline-price-v1",
        ),
        SourceRouteV1(
            _contract(
                OKX_ORDER_BOOK_SOURCE_ID,
                "MARKET_BOOK_DEPTH_20",
                ORDER_BOOK_PATH,
                parameters={"instId": "EXPLICIT", "sz": "20"},
                cadence="OPTIONAL_ONCE_PER_ASSET_SLICE",
                history_window="ONE_REST_SNAPSHOT",
                event_time="provider ts in UNIX milliseconds",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="visible OKX depth-20 snapshot; not resilience or hidden liquidity",
                max_staleness_seconds=120,
            ),
            "order-book",
            "ORDER_BOOK",
            ORDER_BOOK_PATH,
            False,
            "okx-public-microstructure-v1",
        ),
        SourceRouteV1(
            _contract(
                OKX_RECENT_TRADES_SOURCE_ID,
                "MARKET_RECENT_TRADES_100",
                RECENT_TRADES_PATH,
                parameters={"instId": "EXPLICIT", "limit": "100"},
                cadence="OPTIONAL_ONCE_PER_ASSET_SLICE",
                history_window="UP_TO_100_PROVIDER_RECENT_TRADES",
                event_time="provider trade ts in UNIX milliseconds",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="recent OKX public trades; no participant identity or intent",
                max_staleness_seconds=120,
            ),
            "recent-trades",
            "RECENT_TRADES",
            RECENT_TRADES_PATH,
            False,
            "okx-public-microstructure-v1",
        ),
        SourceRouteV1(
            _contract(
                OKX_OPEN_INTEREST_SOURCE_ID,
                "PUBLIC_OPEN_INTEREST",
                OPEN_INTEREST_PATH,
                parameters={"instId": "EXPLICIT", "instType": "SWAP"},
                cadence="OPTIONAL_ONCE_PER_ASSET_SLICE",
                history_window="POINT_IN_TIME",
                event_time="provider ts in UNIX milliseconds",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="one OKX OI level; no direction, actor, or change claim",
                max_staleness_seconds=300,
            ),
            "open-interest",
            "OPEN_INTEREST",
            OPEN_INTEREST_PATH,
            False,
            "okx-public-derivatives-v1",
        ),
        SourceRouteV1(
            _contract(
                OKX_FUNDING_HISTORY_SOURCE_ID,
                "PUBLIC_FUNDING_HISTORY_10",
                FUNDING_RATE_HISTORY_PATH,
                parameters={"instId": "EXPLICIT", "limit": "10"},
                cadence="OPTIONAL_ONCE_PER_ASSET_SLICE",
                history_window="UP_TO_10_REALIZED_FUNDING_RECORDS",
                event_time="provider fundingTime in UNIX milliseconds",
                publish_time="raw capture_completed_at is available_at",
                claim_ceiling="OKX funding records only; no position or participant identity",
                max_staleness_seconds=86400,
            ),
            "funding-rate-history",
            "FUNDING_RATE_HISTORY",
            FUNDING_RATE_HISTORY_PATH,
            False,
            "okx-public-derivatives-v1",
        ),
    )
    return SourceCatalogV1(routes)


OKX_SOURCE_CATALOG = build_okx_source_catalog()
OKX_CORE_CAPTURE_IDS = tuple(
    item.capture_id for item in OKX_SOURCE_CATALOG.core_routes
)
OKX_OPTIONAL_CAPTURE_IDS = tuple(
    item.capture_id for item in OKX_SOURCE_CATALOG.optional_routes
)


__all__ = [
    "OKX_CLOSED_CANDLES_SOURCE_ID",
    "OKX_CORE_CAPTURE_IDS",
    "OKX_FUNDING_HISTORY_SOURCE_ID",
    "OKX_INSTRUMENT_SOURCE_ID",
    "OKX_MARK_PRICE_SOURCE_ID",
    "OKX_OPEN_INTEREST_SOURCE_ID",
    "OKX_OPTIONAL_CAPTURE_IDS",
    "OKX_ORDER_BOOK_SOURCE_ID",
    "OKX_RECENT_TRADES_SOURCE_ID",
    "OKX_SERVER_TIME_SOURCE_ID",
    "OKX_SOURCE_CATALOG",
    "OKX_TERMS_REF",
    "SourceCatalogError",
    "SourceCatalogV1",
    "SourceRouteV1",
    "build_okx_source_catalog",
]
