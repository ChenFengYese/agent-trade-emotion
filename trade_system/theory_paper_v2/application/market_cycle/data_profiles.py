"""Application use case for explicit per-asset data-profile replay."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from ...domain.market_cycle.contracts import ArtifactRef
from ...domain.market_cycle.data import AssetDataSliceV1
from .ports import MarketCaptureRequest, MarketDataObservation


class AssetDataProfileError(ValueError):
    """An asset profile is absent, ambiguous, or cannot produce a slice."""


@dataclass(frozen=True, slots=True)
class AssetDataProfileV1:
    """Frozen asset/product expectations and the sources allowed to serve it."""

    profile_id: str
    asset_id: str
    venue_id: str
    instrument_id: str
    market_type: str
    contract_identity: str
    expected_base_asset: str
    expected_quote_asset: str
    expected_settle_asset: str
    expected_contract_family: str
    market_data_profile: str
    required_source_ids: tuple[str, ...]
    optional_source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "profile_id",
            "asset_id",
            "venue_id",
            "instrument_id",
            "market_type",
            "contract_identity",
            "expected_base_asset",
            "expected_quote_asset",
            "expected_settle_asset",
            "expected_contract_family",
            "market_data_profile",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise AssetDataProfileError(
                    f"V332_DATA_PROFILE_{field_name.upper()}_INVALID"
                )
        required = tuple(self.required_source_ids)
        optional = tuple(self.optional_source_ids)
        if (
            not required
            or any(not isinstance(item, str) or not item for item in required + optional)
            or len(set(required)) != len(required)
            or len(set(optional)) != len(optional)
            or set(required) & set(optional)
        ):
            raise AssetDataProfileError("V332_DATA_PROFILE_SOURCE_SET_INVALID")
        object.__setattr__(self, "required_source_ids", required)
        object.__setattr__(self, "optional_source_ids", optional)


@dataclass(frozen=True, slots=True)
class AssetDataReplayResultV1:
    """Separate raw integrity/completeness from semantic admission."""

    status: str
    profile_id: str
    cycle_id: str
    data_slice: AssetDataSliceV1 | None
    raw_refs: Sequence[ArtifactRef]
    missing_capture_ids: Sequence[str] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ADMITTED", "INCOMPLETE"}:
            raise AssetDataProfileError("V332_DATA_REPLAY_STATUS_INVALID")
        for field_name in ("profile_id", "cycle_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise AssetDataProfileError(
                    f"V332_DATA_REPLAY_{field_name.upper()}_INVALID"
                )
        raw_refs = tuple(self.raw_refs)
        if not all(isinstance(item, ArtifactRef) for item in raw_refs):
            raise AssetDataProfileError("V332_DATA_REPLAY_RAW_REFS_INVALID")
        missing = tuple(self.missing_capture_ids)
        if any(not isinstance(item, str) or not item for item in missing):
            raise AssetDataProfileError(
                "V332_DATA_REPLAY_MISSING_CAPTURE_IDS_INVALID"
            )
        if self.status == "ADMITTED":
            if (
                not isinstance(self.data_slice, AssetDataSliceV1)
                or missing
                or self.reason is not None
                or tuple(self.data_slice.raw_refs) != raw_refs
            ):
                raise AssetDataProfileError(
                    "V332_DATA_REPLAY_ADMITTED_RESULT_INVALID"
                )
        elif (
            self.data_slice is not None
            or not missing
            or self.reason != "RAW_CAPTURE_SET_INCOMPLETE"
        ):
            raise AssetDataProfileError(
                "V332_DATA_REPLAY_INCOMPLETE_RESULT_INVALID"
            )
        object.__setattr__(self, "raw_refs", raw_refs)
        object.__setattr__(self, "missing_capture_ids", missing)

    @property
    def slice(self) -> AssetDataSliceV1 | None:
        return self.data_slice

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "profile_id": self.profile_id,
            "cycle_id": self.cycle_id,
            "data_slice": (
                None if self.data_slice is None else self.data_slice.to_dict()
            ),
            "raw_refs": [item.to_dict() for item in self.raw_refs],
            "missing_capture_ids": list(self.missing_capture_ids),
            "reason": self.reason,
        }


class AssetDataReplayPort(Protocol):
    def replay(
        self,
        profile: AssetDataProfileV1,
        *,
        cycle_id: str,
        cutoff_at: str | None = None,
        requested_at: str | None = None,
    ) -> AssetDataReplayResultV1: ...


class AssetDataCollectorPort(Protocol):
    """Explicit opt-in collector that writes only through the primary raw owner."""

    def collect(
        self, profile: AssetDataProfileV1, *, request: MarketCaptureRequest
    ) -> None: ...


class AssetDataProfileService:
    """Select one explicit profile and ask the injected replay port for it."""

    def __init__(
        self,
        *,
        profiles: Sequence[AssetDataProfileV1],
        replay: AssetDataReplayPort,
    ) -> None:
        supplied = tuple(profiles)
        if not supplied or not all(
            isinstance(item, AssetDataProfileV1) for item in supplied
        ):
            raise AssetDataProfileError("V332_DATA_PROFILES_INVALID")
        by_id = {item.profile_id: item for item in supplied}
        if len(by_id) != len(supplied):
            raise AssetDataProfileError("V332_DATA_PROFILE_ID_DUPLICATE")
        if not callable(getattr(replay, "replay", None)):
            raise AssetDataProfileError("V332_DATA_REPLAY_PORT_INVALID")
        self._profiles = MappingProxyType(by_id)
        self._replay = replay

    def require_profile(self, profile_id: str) -> AssetDataProfileV1:
        try:
            return self._profiles[profile_id]
        except (KeyError, TypeError) as exc:
            raise AssetDataProfileError(
                f"V332_DATA_PROFILE_NOT_REGISTERED:{profile_id}"
            ) from exc

    def replay(
        self,
        profile_id: str,
        *,
        cycle_id: str,
        cutoff_at: str | None = None,
        requested_at: str | None = None,
    ) -> AssetDataReplayResultV1:
        profile = self.require_profile(profile_id)
        result = self._replay.replay(
            profile,
            cycle_id=cycle_id,
            cutoff_at=cutoff_at,
            requested_at=requested_at,
        )
        if not isinstance(result, AssetDataReplayResultV1):
            raise AssetDataProfileError("V332_DATA_REPLAY_RESULT_INVALID")
        if result.profile_id != profile.profile_id or result.cycle_id != cycle_id:
            raise AssetDataProfileError("V332_DATA_REPLAY_RESULT_IDENTITY_MISMATCH")
        return result


def project_market_data_observation(
    data_slice: AssetDataSliceV1,
) -> MarketDataObservation:
    """Purely project an admitted slice onto the unchanged market-data port."""

    if not isinstance(data_slice, AssetDataSliceV1):
        raise AssetDataProfileError("V332_DATA_SLICE_REQUIRED")
    document = data_slice.to_dict()
    return MarketDataObservation(
        captured_at=data_slice.sealed_at,
        cutoff_at=data_slice.cutoff_at,
        core_observations=document["core_observations"],
        optional_observations=document["optional_observations"],
        unknowns=tuple(document["typed_unknowns"]),
        raw_refs=tuple(document["raw_refs"]),
        source_health=tuple(document["source_health"]),
    )


asset_data_slice_to_market_data_observation = project_market_data_observation


class AssetDataProfileMarketDataAdapter:
    """Thin ``MarketDataPort`` adapter for one explicitly selected profile.

    The default remains replay-only.  A caller must explicitly inject a
    collector before an incomplete raw set may cause public acquisition.
    """

    def __init__(
        self,
        *,
        service: AssetDataProfileService,
        profile_id: str,
        collector: AssetDataCollectorPort | None = None,
    ) -> None:
        if not isinstance(service, AssetDataProfileService):
            raise AssetDataProfileError("V332_DATA_PROFILE_SERVICE_INVALID")
        self._service = service
        self._profile = service.require_profile(profile_id)
        if collector is not None and not callable(getattr(collector, "collect", None)):
            raise AssetDataProfileError("V332_DATA_COLLECTOR_PORT_INVALID")
        self._collector = collector

    def capture(self, request: MarketCaptureRequest) -> MarketDataObservation:
        if not isinstance(request, MarketCaptureRequest):
            raise AssetDataProfileError("V332_MARKET_CAPTURE_REQUEST_INVALID")
        profile = self._profile
        if (
            request.venue_id != profile.venue_id
            or request.instrument_id != profile.instrument_id
            or request.contract_type != profile.contract_identity
            or request.data_profile != profile.market_data_profile
        ):
            raise AssetDataProfileError(
                "V332_MARKET_CAPTURE_PROFILE_IDENTITY_MISMATCH"
            )
        result = self._service.replay(
            profile.profile_id,
            cycle_id=request.cycle_id,
            requested_at=request.requested_at,
        )
        if result.status == "INCOMPLETE" and self._collector is not None:
            self._collector.collect(profile, request=request)
            result = self._service.replay(
                profile.profile_id,
                cycle_id=request.cycle_id,
                requested_at=request.requested_at,
            )
        if result.status != "ADMITTED" or result.data_slice is None:
            missing = ",".join(result.missing_capture_ids)
            raise AssetDataProfileError(
                f"V332_MARKET_CAPTURE_RAW_INCOMPLETE:{missing}"
            )
        return project_market_data_observation(result.data_slice)


__all__ = [
    "AssetDataProfileError",
    "AssetDataCollectorPort",
    "AssetDataProfileMarketDataAdapter",
    "AssetDataProfileService",
    "AssetDataProfileV1",
    "AssetDataReplayPort",
    "AssetDataReplayResultV1",
    "asset_data_slice_to_market_data_observation",
    "project_market_data_observation",
]
