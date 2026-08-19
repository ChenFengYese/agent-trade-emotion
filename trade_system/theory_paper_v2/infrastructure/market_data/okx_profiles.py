"""Explicit OKX asset profiles and the offline HYPE admission adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from ...application.market_cycle.data_profiles import (
    AssetDataProfileError,
    AssetDataProfileService,
    AssetDataProfileV1,
    AssetDataReplayResultV1,
)
from ...application.market_cycle.ports import MarketCaptureRequest
from ...domain.contracts.canonical import canonical_digest
from ...domain.market_cycle.contracts import ArtifactRef
from ...domain.market_cycle.data import (
    AssetDataSliceV1,
    InstrumentIdentityV1,
    TypedUnknownV1,
)
from .okx_snapshot import OkxBaselineMarketData
from .optional_context import (
    OKX_PUBLIC_OPTIONAL_PROFILE,
    OkxOptionalContextMarketData,
)
from .raw_capture import FileRawCaptureStore
from .okx_transport import OkxPublicTransport
from .replay import (
    SealedOnlyOkxTransport,
    capture_refs_from_sealed_set,
    inspect_sealed_capture_set,
)
from .source_catalog import (
    OKX_CORE_CAPTURE_IDS,
    OKX_OPTIONAL_CAPTURE_IDS,
    OKX_SOURCE_CATALOG,
    SourceCatalogError,
    SourceCatalogV1,
)


HYPE_OKX_PROFILE_ID = "V332_HYPE_OKX_HTTP_V1"
HYPE_OKX_INSTRUMENT_ID = "HYPE-USDT-SWAP"
HYPE_OKX_CONTRACT_IDENTITY = "OKX:HYPE-USDT-SWAP:linear"


class OkxAssetProfileError(ValueError):
    """Sealed OKX bytes do not satisfy the selected asset profile."""


class HypeOkxPublicCollector:
    """Collect one bounded HYPE slice through the existing primary raw sink."""

    def __init__(self, *, transport: OkxPublicTransport) -> None:
        if not isinstance(transport, OkxPublicTransport):
            raise OkxAssetProfileError("V332_HYPE_PUBLIC_TRANSPORT_INVALID")
        self._market_data = OkxOptionalContextMarketData(
            core=OkxBaselineMarketData(
                transport=transport, include_candle_volume=True
            ),
            transport=transport,
        )

    def collect(
        self, profile: AssetDataProfileV1, *, request: MarketCaptureRequest
    ) -> None:
        _require_hype_profile(profile)
        if (
            request.venue_id != profile.venue_id
            or request.instrument_id != profile.instrument_id
            or request.contract_type != profile.contract_identity
            or request.data_profile != profile.market_data_profile
        ):
            raise OkxAssetProfileError("V332_HYPE_COLLECTION_IDENTITY_MISMATCH")
        self._market_data.capture(request)


def _moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OkxAssetProfileError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OkxAssetProfileError(code) from exc
    if parsed.tzinfo is None:
        raise OkxAssetProfileError(code)
    return parsed.astimezone(UTC)


def _time_text(value: object, *, code: str) -> str:
    return _moment(value, code=code).isoformat().replace("+00:00", "Z")


HYPE_OKX_DATA_PROFILE = AssetDataProfileV1(
    profile_id=HYPE_OKX_PROFILE_ID,
    asset_id="HYPE",
    venue_id="OKX",
    instrument_id=HYPE_OKX_INSTRUMENT_ID,
    market_type="SWAP",
    contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
    expected_base_asset="HYPE",
    expected_quote_asset="USDT",
    expected_settle_asset="USDT",
    expected_contract_family="linear",
    market_data_profile=OKX_PUBLIC_OPTIONAL_PROFILE,
    required_source_ids=tuple(
        item.source_id for item in OKX_SOURCE_CATALOG.core_routes
    ),
    optional_source_ids=tuple(
        item.source_id for item in OKX_SOURCE_CATALOG.optional_routes
    ),
)
HYPE_OKX_PROFILE = HYPE_OKX_DATA_PROFILE


_CORE_OBSERVATION_COMPONENTS = {
    "server_time": "SERVER_TIME",
    "instrument": "INSTRUMENT",
    "mark_price": "MARK_PRICE",
    "closed_15m_bars": "CLOSED_CANDLES_15M",
}
_OPTIONAL_OBSERVATION_COMPONENTS = {
    "okx_order_book": "ORDER_BOOK",
    "okx_recent_trades": "RECENT_TRADES",
    "okx_open_interest": "OPEN_INTEREST",
    "okx_funding_rate_history": "FUNDING_RATE_HISTORY",
}
_OBSERVATION_METADATA = {
    "server_time": (
        "OKX_PUBLIC_SERVER_CLOCK",
        "POINT_IN_TIME",
        "UNIX_MS",
    ),
    "instrument": (
        "ONE_EXPLICIT_OKX_LIVE_SWAP",
        "CURRENT_PROVIDER_METADATA",
        "CONTRACT_METADATA",
    ),
    "mark_price": (
        "ONE_EXPLICIT_OKX_SWAP_MARK",
        "POINT_IN_TIME",
        "USDT_PER_HYPE",
    ),
    "closed_15m_bars": (
        "CONFIRMED_CONTIGUOUS_OKX_BARS",
        "UP_TO_96_X_15M",
        "USDT_PER_HYPE",
    ),
    "okx_order_book": (
        "VISIBLE_OKX_DEPTH_20",
        "ONE_REST_SNAPSHOT",
        "USDT_PER_HYPE_AND_CONTRACTS",
    ),
    "okx_recent_trades": (
        "UP_TO_100_RECENT_OKX_TRADES",
        "PROVIDER_RECENT_WINDOW",
        "USDT_PER_HYPE_AND_CONTRACTS",
    ),
    "okx_open_interest": (
        "ONE_OKX_SWAP_OPEN_INTEREST_LEVEL",
        "POINT_IN_TIME",
        "CONTRACTS_COIN_AND_OPTIONAL_USD",
    ),
    "okx_funding_rate_history": (
        "UP_TO_10_OKX_FUNDING_RECORDS",
        "PROVIDER_REALIZED_HISTORY",
        "DECIMAL_RATE",
    ),
}


def build_hype_okx_profile() -> AssetDataProfileV1:
    """Return the sole Phase-1 HYPE profile; no instrument default is accepted."""

    return HYPE_OKX_DATA_PROFILE


def profile_for_asset(asset_id: str) -> AssetDataProfileV1:
    """Resolve an exact asset id and fail instead of falling back to BTC."""

    if asset_id != "HYPE":
        raise AssetDataProfileError(f"V332_DATA_PROFILE_NOT_REGISTERED:{asset_id}")
    return HYPE_OKX_DATA_PROFILE


def _require_hype_profile(profile: AssetDataProfileV1) -> None:
    if not isinstance(profile, AssetDataProfileV1) or profile != HYPE_OKX_DATA_PROFILE:
        raise OkxAssetProfileError("V332_HYPE_PROFILE_IDENTITY_MISMATCH")


def _observed_at(name: str, observation: Mapping[str, Any]) -> str:
    if name == "server_time":
        value = observation.get("observed_at")
    elif name == "instrument":
        inner = observation.get("value")
        value = inner.get("observed_at") if isinstance(inner, Mapping) else None
    elif name == "mark_price":
        value = observation.get("observed_at")
    elif name == "closed_15m_bars":
        value = observation.get("last_closed_at")
    else:
        value = observation.get("observed_at")
        if value is None:
            inner = observation.get("value")
            if isinstance(inner, Mapping):
                value = inner.get("provider_as_of")
            elif isinstance(inner, (list, tuple)) and inner:
                times = [
                    item.get("provider_as_of")
                    for item in inner
                    if isinstance(item, Mapping)
                ]
                value = max(
                    times,
                    key=lambda item: _moment(
                        item, code="V332_HYPE_OPTIONAL_EVENT_TIME_INVALID"
                    ),
                ) if len(times) == len(inner) else None
            else:
                value = None
    return _time_text(value, code=f"V332_HYPE_{name.upper()}_EVENT_TIME_INVALID")


def _enrich_observation(
    name: str,
    observation: Mapping[str, Any],
    *,
    component_id: str,
    catalog: SourceCatalogV1,
    raw_refs: tuple[ArtifactRef, ...],
) -> dict[str, Any]:
    route = catalog.for_component(component_id)
    population, window, unit = _OBSERVATION_METADATA[name]
    matches = [
        item
        for item in raw_refs
        if item.path == f"raw/{route.capture_id}/body.bin"
        and item.sha256 == observation.get("raw_sha256")
    ]
    if len(matches) != 1:
        raise OkxAssetProfileError("V332_HYPE_OBSERVATION_RAW_BINDING_INVALID")
    raw_ref = matches[0]
    return {
        **dict(observation),
        "raw_ref": raw_ref.to_dict(),
        "source_id": route.source_id,
        "venue": "OKX",
        "market_type": "SWAP",
        "population": population,
        "window": window,
        "unit": unit,
        "claim_ceiling": route.contract.claim_ceiling,
        "observed_at": _observed_at(name, observation),
    }


def _instrument_identity(
    instrument_observation: Mapping[str, Any],
    *,
    profile: AssetDataProfileV1,
    raw_refs: tuple[ArtifactRef, ...],
) -> InstrumentIdentityV1:
    value = instrument_observation.get("value")
    if not isinstance(value, Mapping):
        raise OkxAssetProfileError("V332_HYPE_INSTRUMENT_VALUE_INVALID")
    expected = (
        value.get("instrument_id") == profile.instrument_id
        and value.get("instrument_type") == profile.market_type
        and value.get("contract_family") == profile.expected_contract_family
        and value.get("base_currency") == profile.expected_base_asset
        and value.get("quote_currency") == profile.expected_quote_asset
        and value.get("settlement_currency") == profile.expected_settle_asset
        and value.get("contract_value_currency") == profile.expected_base_asset
    )
    if not expected:
        raise OkxAssetProfileError("V332_HYPE_INSTRUMENT_IDENTITY_MISMATCH")
    raw_value = instrument_observation.get("raw_ref")
    if not isinstance(raw_value, Mapping):
        raise OkxAssetProfileError("V332_HYPE_INSTRUMENT_RAW_REF_INVALID")
    try:
        raw_ref = ArtifactRef.from_dict(raw_value)
    except ValueError as exc:
        raise OkxAssetProfileError(
            "V332_HYPE_INSTRUMENT_RAW_REF_INVALID"
        ) from exc
    if raw_ref not in raw_refs:
        raise OkxAssetProfileError("V332_HYPE_INSTRUMENT_RAW_NOT_BOUND")
    effective_at = _time_text(
        value.get("observed_at"), code="V332_HYPE_INSTRUMENT_EFFECTIVE_AT_INVALID"
    )
    discovered_at = _time_text(
        instrument_observation.get("available_at"),
        code="V332_HYPE_INSTRUMENT_DISCOVERED_AT_INVALID",
    )
    return InstrumentIdentityV1(
        instrument_key=(
            f"{profile.venue_id}:{profile.instrument_id}:"
            f"{profile.market_type}:{profile.expected_contract_family}"
        ),
        venue=profile.venue_id,
        market_type=profile.market_type,
        venue_symbol=profile.instrument_id,
        base_asset=profile.expected_base_asset,
        quote_asset=profile.expected_quote_asset,
        settle_asset=profile.expected_settle_asset,
        underlying_identity=f"CRYPTO_ASSET:{profile.expected_base_asset}",
        product_identity=f"OKX_SWAP:{profile.instrument_id}",
        contract_semantics="LINEAR_PERPETUAL_SWAP",
        quantity_basis=(
            f"{value.get('contract_value')} {value.get('contract_value_currency')} "
            f"PER_CONTRACT X {value.get('contract_multiplier')}"
        ),
        session_semantics="CONTINUOUS_24X7_PROVIDER_SESSION",
        status="ACTIVE",
        discovered_at=discovered_at,
        effective_at=effective_at,
        source_ref=raw_ref,
    )


def _typed_unknowns(
    supplied: tuple[Mapping[str, Any], ...],
    *,
    raw_refs: tuple[ArtifactRef, ...],
    catalog: SourceCatalogV1,
) -> tuple[TypedUnknownV1, ...]:
    result: list[TypedUnknownV1] = []
    for item in supplied:
        if not isinstance(item, Mapping):
            raise OkxAssetProfileError("V332_HYPE_TYPED_UNKNOWN_INVALID")
        component_id = item.get("component_id")
        reason = item.get("missing_reason")
        if (
            not isinstance(component_id, str)
            or not component_id
            or not isinstance(reason, str)
            or not reason
            or item.get("status") != "UNKNOWN"
            or item.get("missing_is_zero") is not False
        ):
            raise OkxAssetProfileError("V332_HYPE_TYPED_UNKNOWN_INVALID")
        try:
            route = catalog.for_component(component_id)
            source_id = route.source_id
            claim_ceiling = route.contract.claim_ceiling
        except SourceCatalogError:
            source_id = f"profile.{component_id.casefold()}"
            claim_ceiling = "UNKNOWN; no observation may be inferred"
        raw_value = item.get("raw_ref")
        raw_ref = None
        if raw_value is not None:
            try:
                candidate = ArtifactRef.from_dict(raw_value)
            except ValueError as exc:
                raise OkxAssetProfileError(
                    "V332_HYPE_TYPED_UNKNOWN_RAW_REF_INVALID"
                ) from exc
            if candidate not in raw_refs:
                raise OkxAssetProfileError(
                    "V332_HYPE_TYPED_UNKNOWN_RAW_NOT_BOUND"
                )
            raw_ref = candidate
        result.append(
            TypedUnknownV1(
                component_id=component_id,
                source_id=source_id,
                missing_reason=reason,
                claim_ceiling=claim_ceiling,
                available_at=item.get("available_at"),
                raw_ref=raw_ref,
            )
        )
    result.append(
        TypedUnknownV1(
            component_id="SHARED_CONTEXT",
            source_id="shared_context.offline_phase1",
            missing_reason="NOT_PROVIDED_OFFLINE_PHASE1",
            claim_ceiling="asset-local HYPE facts only",
        )
    )
    if len({item.component_id for item in result}) != len(result):
        raise OkxAssetProfileError("V332_HYPE_TYPED_UNKNOWN_DUPLICATE")
    return tuple(result)


def _source_health(
    values: tuple[Mapping[str, Any], ...], *, catalog: SourceCatalogV1
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise OkxAssetProfileError("V332_HYPE_SOURCE_HEALTH_INVALID")
        candidate = dict(item)
        component_id = candidate.get("component_id")
        try:
            route = catalog.for_component(component_id)
            candidate["source_id"] = route.source_id
            candidate["claim_ceiling"] = route.contract.claim_ceiling
        except SourceCatalogError:
            candidate["source_id"] = f"profile.{str(component_id).casefold()}"
            candidate["claim_ceiling"] = "UNKNOWN_ONLY"
        result.append(candidate)
    return tuple(result)


def _validate_cutoff_and_staleness(
    *,
    cutoff_at: str,
    core: Mapping[str, Mapping[str, Any]],
    optional: Mapping[str, Mapping[str, Any]],
    catalog: SourceCatalogV1,
) -> dict[str, Any]:
    cutoff = _moment(cutoff_at, code="V332_HYPE_CUTOFF_INVALID")
    ages: dict[str, Any] = {}
    for name, observation in {**core, **optional}.items():
        available = _moment(
            observation.get("available_at"),
            code=f"V332_HYPE_{name.upper()}_AVAILABLE_AT_INVALID",
        )
        if available > cutoff:
            raise OkxAssetProfileError(f"V332_HYPE_PIT_VIOLATION:{name}")
        component = (
            _CORE_OBSERVATION_COMPONENTS.get(name)
            or _OPTIONAL_OBSERVATION_COMPONENTS.get(name)
        )
        if component is None:
            raise OkxAssetProfileError(
                f"V332_HYPE_OBSERVATION_COMPONENT_UNKNOWN:{name}"
            )
        route = catalog.for_component(component)
        age_ms = int((cutoff - available).total_seconds() * 1000)
        ages[route.source_id] = {
            "availability_age_milliseconds": age_ms,
            "max_staleness_seconds": route.contract.max_staleness_seconds,
            "status": (
                "FRESH"
                if age_ms <= route.contract.max_staleness_seconds * 1000
                else "STALE"
            ),
        }
        if route.required_for_core and age_ms > (
            route.contract.max_staleness_seconds * 1000
        ):
            raise OkxAssetProfileError(f"V332_HYPE_CORE_STALE:{component}")
    return ages


class OkxAssetProfileReplay:
    """Replay HYPE from ``FileRawCaptureStore`` through existing OKX parsers."""

    def __init__(
        self,
        *,
        raw_store: FileRawCaptureStore,
        catalog: SourceCatalogV1 = OKX_SOURCE_CATALOG,
    ) -> None:
        if not isinstance(raw_store, FileRawCaptureStore):
            raise OkxAssetProfileError("V332_HYPE_RAW_STORE_INVALID")
        if not isinstance(catalog, SourceCatalogV1):
            raise OkxAssetProfileError("V332_HYPE_SOURCE_CATALOG_INVALID")
        self._raw_store = raw_store
        self._catalog = catalog

    def replay(
        self,
        profile: AssetDataProfileV1,
        *,
        cycle_id: str,
        cutoff_at: str | None = None,
        requested_at: str | None = None,
    ) -> AssetDataReplayResultV1:
        _require_hype_profile(profile)
        capture_set = inspect_sealed_capture_set(
            raw_store=self._raw_store,
            cycle_id=cycle_id,
            required_capture_ids=OKX_CORE_CAPTURE_IDS,
            optional_capture_ids=OKX_OPTIONAL_CAPTURE_IDS,
        )
        if capture_set.missing_required_capture_ids:
            return AssetDataReplayResultV1(
                status="INCOMPLETE",
                profile_id=profile.profile_id,
                cycle_id=cycle_id,
                data_slice=None,
                raw_refs=capture_set.raw_refs,
                missing_capture_ids=capture_set.missing_required_capture_ids,
                reason="RAW_CAPTURE_SET_INCOMPLETE",
            )
        if capture_set.route_policy_id is None:
            raise OkxAssetProfileError("V332_HYPE_ROUTE_POLICY_MISSING")

        transport = SealedOnlyOkxTransport(
            raw_store=self._raw_store,
            route_policy_id=capture_set.route_policy_id,
        )
        parser = OkxOptionalContextMarketData(
            core=OkxBaselineMarketData(
                transport=transport, include_candle_volume=True
            ),
            transport=transport,
        )
        server_summary = capture_set.loaded["server-time"].summary
        replay_requested_at = requested_at or server_summary.get(
            "request_started_at"
        )
        observation = parser.capture(
            MarketCaptureRequest(
                cycle_id=cycle_id,
                venue_id=profile.venue_id,
                instrument_id=profile.instrument_id,
                contract_type=profile.contract_identity,
                requested_at=replay_requested_at,
                analysis_profile="COLD",
                data_profile=profile.market_data_profile,
            )
        )
        chosen_cutoff = _time_text(
            cutoff_at or observation.cutoff_at,
            code="V332_HYPE_CUTOFF_INVALID",
        )
        raw_refs = tuple(ArtifactRef.from_dict(item) for item in observation.raw_refs)
        if set(raw_refs) != set(capture_set.raw_refs):
            raise OkxAssetProfileError("V332_HYPE_REPLAY_RAW_SET_MISMATCH")

        core = {
            name: _enrich_observation(
                name,
                item,
                component_id=_CORE_OBSERVATION_COMPONENTS[name],
                catalog=self._catalog,
                raw_refs=raw_refs,
            )
            for name, item in observation.core_observations.items()
        }
        optional = {
            name: _enrich_observation(
                name,
                item,
                component_id=_OPTIONAL_OBSERVATION_COMPONENTS[name],
                catalog=self._catalog,
                raw_refs=raw_refs,
            )
            for name, item in observation.optional_observations.items()
        }
        staleness = _validate_cutoff_and_staleness(
            cutoff_at=chosen_cutoff,
            core=core,
            optional=optional,
            catalog=self._catalog,
        )
        identity = _instrument_identity(
            core["instrument"], profile=profile, raw_refs=raw_refs
        )
        unknowns = _typed_unknowns(
            tuple(observation.unknowns),
            raw_refs=raw_refs,
            catalog=self._catalog,
        )
        capture_refs = capture_refs_from_sealed_set(
            capture_set, catalog=self._catalog
        )
        candle_rows = core["closed_15m_bars"].get("value")
        if not isinstance(candle_rows, (list, tuple)) or not candle_rows:
            raise OkxAssetProfileError("V332_HYPE_CANDLE_WINDOW_INVALID")
        first = candle_rows[0]
        if not isinstance(first, Mapping):
            raise OkxAssetProfileError("V332_HYPE_CANDLE_WINDOW_INVALID")
        slice_start = _time_text(
            first.get("opened_at"), code="V332_HYPE_SLICE_START_INVALID"
        )
        data_cursor = canonical_digest(
            {
                "asset_profile_id": profile.profile_id,
                "instrument_key": identity.instrument_key,
                "cutoff_at": chosen_cutoff,
                "raw_refs": [item.to_dict() for item in raw_refs],
            }
        )
        admitted_optional = len(optional)
        data_slice = AssetDataSliceV1(
            asset_profile_id=profile.profile_id,
            instrument_identity=identity,
            cutoff_at=chosen_cutoff,
            slice_start_at=slice_start,
            slice_end_at=chosen_cutoff,
            data_cursor=data_cursor,
            core_observations=core,
            optional_observations=optional,
            shared_context_ref=None,
            source_health=_source_health(
                tuple(observation.source_health), catalog=self._catalog
            ),
            coverage={
                "status": "CORE_ADMITTED_OPTIONAL_BOUNDED",
                "required_core_count": len(OKX_CORE_CAPTURE_IDS),
                "admitted_core_count": len(core),
                "optional_expected_count": len(OKX_OPTIONAL_CAPTURE_IDS),
                "optional_admitted_count": admitted_optional,
                "optional_unknown_count": len(OKX_OPTIONAL_CAPTURE_IDS)
                - admitted_optional,
                "raw_capture_count": len(raw_refs),
            },
            staleness=staleness,
            typed_unknowns=unknowns,
            raw_refs=raw_refs,
            capture_refs=capture_refs,
            sealed_at=chosen_cutoff,
        )
        return AssetDataReplayResultV1(
            status="ADMITTED",
            profile_id=profile.profile_id,
            cycle_id=cycle_id,
            data_slice=data_slice,
            raw_refs=raw_refs,
        )


def build_hype_data_profile_service(
    *, raw_store: FileRawCaptureStore
) -> AssetDataProfileService:
    """Compose the application service over the one existing raw store."""

    return AssetDataProfileService(
        profiles=(HYPE_OKX_DATA_PROFILE,),
        replay=OkxAssetProfileReplay(raw_store=raw_store),
    )


__all__ = [
    "HYPE_OKX_CONTRACT_IDENTITY",
    "HYPE_OKX_DATA_PROFILE",
    "HYPE_OKX_INSTRUMENT_ID",
    "HYPE_OKX_PROFILE",
    "HYPE_OKX_PROFILE_ID",
    "HypeOkxPublicCollector",
    "OkxAssetProfileError",
    "OkxAssetProfileReplay",
    "build_hype_data_profile_service",
    "build_hype_okx_profile",
    "profile_for_asset",
]
