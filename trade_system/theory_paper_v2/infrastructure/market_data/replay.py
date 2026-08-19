"""Read-only replay helpers over the sole existing raw-capture store."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ...domain.market_cycle.contracts import ArtifactRef
from ...domain.market_cycle.data import CaptureRefV1
from .okx_transport import (
    CapturedPublicResponse,
    OkxPublicTransport,
    OkxPublicTransportError,
)
from .raw_capture import FileRawCaptureStore, LoadedRawCapture
from .source_catalog import SourceCatalogV1


class RawReplayError(ValueError):
    """Sealed raw cannot be replayed without changing its meaning."""


@dataclass(frozen=True, slots=True)
class SealedCaptureSetV1:
    """Integrity-verified raw bundles plus an independent completeness result."""

    cycle_id: str
    loaded: Mapping[str, LoadedRawCapture]
    raw_refs: tuple[ArtifactRef, ...]
    missing_required_capture_ids: tuple[str, ...]
    route_policy_id: str | None

    @property
    def status(self) -> str:
        return (
            "INCOMPLETE"
            if self.missing_required_capture_ids
            else "RAW_COMPLETE"
        )


class _NoNetworkReplayOpener:
    """Carries the sealed route identity and fails if any network path is used."""

    def __init__(self, route_policy_id: str) -> None:
        self.route_policy_id = route_policy_id

    def open(self, request, timeout):  # noqa: ANN001, ANN201
        raise RawReplayError("V332_OFFLINE_REPLAY_NETWORK_FORBIDDEN")


def _no_replay_clock() -> str:
    raise RawReplayError("V332_OFFLINE_REPLAY_CLOCK_READ_FORBIDDEN")


class SealedOnlyOkxTransport:
    """Expose ``get_once`` semantics while performing only verified raw reads."""

    def __init__(
        self,
        *,
        raw_store: FileRawCaptureStore,
        route_policy_id: str,
    ) -> None:
        if not isinstance(raw_store, FileRawCaptureStore):
            raise RawReplayError("V332_REPLAY_RAW_STORE_INVALID")
        if not isinstance(route_policy_id, str) or not route_policy_id:
            raise RawReplayError("V332_REPLAY_ROUTE_POLICY_INVALID")
        self._transport = OkxPublicTransport(
            raw_sink=raw_store,
            clock=_no_replay_clock,
            opener=_NoNetworkReplayOpener(route_policy_id),
        )

    def get_once(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        component_id: str,
        path: str,
        query: Mapping[str, str],
    ) -> CapturedPublicResponse:
        response = self._transport.load_sealed(
            cycle_id=cycle_id,
            capture_id=capture_id,
            component_id=component_id,
            path=path,
            query=query,
        )
        if response is None:
            raise OkxPublicTransportError(
                "PUBLIC_PREVIOUS_ATTEMPT_INDETERMINATE",
                coverage_eligible=True,
            )
        return response


def inspect_sealed_capture_set(
    *,
    raw_store: FileRawCaptureStore,
    cycle_id: str,
    required_capture_ids: Sequence[str],
    optional_capture_ids: Sequence[str] = (),
) -> SealedCaptureSetV1:
    """Verify every present bundle and report missing core raw as INCOMPLETE."""

    if not isinstance(raw_store, FileRawCaptureStore):
        raise RawReplayError("V332_REPLAY_RAW_STORE_INVALID")
    required = tuple(required_capture_ids)
    optional = tuple(optional_capture_ids)
    if (
        not isinstance(cycle_id, str)
        or not cycle_id
        or not required
        or any(not isinstance(item, str) or not item for item in required + optional)
        or len(set(required + optional)) != len(required + optional)
    ):
        raise RawReplayError("V332_REPLAY_CAPTURE_SET_REQUEST_INVALID")

    loaded: dict[str, LoadedRawCapture] = {}
    raw_refs: list[ArtifactRef] = []
    route_policies: set[str] = set()
    for capture_id in required + optional:
        item = raw_store.load_response(cycle_id=cycle_id, capture_id=capture_id)
        if item is None:
            continue
        if not isinstance(item, LoadedRawCapture):
            raise RawReplayError("V332_REPLAY_LOADED_CAPTURE_INVALID")
        policy = item.summary.get("route_policy_id")
        if not isinstance(policy, str) or not policy:
            raise RawReplayError(
                f"V332_REPLAY_ROUTE_POLICY_MISSING:{capture_id}"
            )
        route_policies.add(policy)
        try:
            raw_ref = ArtifactRef.from_dict(item.raw_ref)
        except ValueError as exc:
            raise RawReplayError(
                f"V332_REPLAY_RAW_REFERENCE_INVALID:{capture_id}"
            ) from exc
        loaded[capture_id] = item
        raw_refs.append(raw_ref)
    if len(route_policies) > 1:
        raise RawReplayError("V332_REPLAY_ROUTE_POLICY_MISMATCH")
    missing = tuple(item for item in required if item not in loaded)
    return SealedCaptureSetV1(
        cycle_id=cycle_id,
        loaded=MappingProxyType(loaded),
        raw_refs=tuple(raw_refs),
        missing_required_capture_ids=missing,
        route_policy_id=(next(iter(route_policies)) if route_policies else None),
    )


def capture_refs_from_sealed_set(
    capture_set: SealedCaptureSetV1,
    *,
    catalog: SourceCatalogV1,
) -> tuple[CaptureRefV1, ...]:
    """Bind parsed source/timing metadata to existing raw ArtifactRefs."""

    if not isinstance(capture_set, SealedCaptureSetV1):
        raise RawReplayError("V332_REPLAY_CAPTURE_SET_INVALID")
    if not isinstance(catalog, SourceCatalogV1):
        raise RawReplayError("V332_REPLAY_SOURCE_CATALOG_INVALID")
    refs: list[CaptureRefV1] = []
    for capture_id, loaded in capture_set.loaded.items():
        route = catalog.for_capture(capture_id)
        summary = loaded.summary
        query = summary.get("query")
        if not isinstance(query, Mapping):
            raise RawReplayError(
                f"V332_REPLAY_REQUEST_QUERY_INVALID:{capture_id}"
            )
        request_binding: dict[str, Any] = {
            "component_id": summary.get("component_id"),
            "method": summary.get("method"),
            "path": summary.get("path"),
            "query": dict(query),
            "route_policy_id": summary.get("route_policy_id"),
            "attempt_number": summary.get("attempt_number"),
            "retry_allowed": summary.get("retry_allowed"),
        }
        try:
            raw_ref = ArtifactRef.from_dict(loaded.raw_ref)
            refs.append(
                CaptureRefV1(
                    capture_id=capture_id,
                    source_id=route.source_id,
                    request_binding=request_binding,
                    request_started_at=summary.get("request_started_at"),
                    response_received_at=summary.get("response_received_at"),
                    captured_at=summary.get("capture_completed_at"),
                    raw_ref=raw_ref,
                    parser_version=route.parser_version,
                )
            )
        except (TypeError, ValueError) as exc:
            raise RawReplayError(
                f"V332_REPLAY_CAPTURE_BINDING_INVALID:{capture_id}"
            ) from exc
    return tuple(refs)


__all__ = [
    "RawReplayError",
    "SealedCaptureSetV1",
    "SealedOnlyOkxTransport",
    "capture_refs_from_sealed_set",
    "inspect_sealed_capture_set",
]
