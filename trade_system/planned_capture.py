"""Application workflow for one immutable, predeclared public capture slot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .capture_plan import ForwardCapturePlan
from .collection_sealing import seal_collection
from .event_store import EventStore
from .replay import DeterministicReplay
from .source_registry import SourceRegistry
from .software_identity import collector_software_binding
from .types import utc_now


@dataclass(frozen=True)
class PlannedCaptureRequest:
    capture_plan_path: Path
    capture_slot: str
    data_root: Path
    source_registry_path: Path
    duration_seconds: Optional[float] = None
    snapshot_limit: int = 1000
    oi_poll_seconds: float = 5.0
    metadata_poll_seconds: float = 300.0
    live_feature_output: str = ""
    episode_policy: str = ""


@dataclass(frozen=True)
class PublicCaptureRequest:
    data_dir: str
    connection_id: str
    instrument: str
    duration_seconds: float
    snapshot_limit: int
    oi_poll_seconds: float
    metadata_poll_seconds: float
    source_registry: str
    capture_plan: str
    capture_slot: str
    live_feature_output: str
    episode_policy: str


Collector = Callable[[PublicCaptureRequest], Tuple[Dict[str, Any], int]]


def public_configured_streams(instrument: str) -> list:
    normalized = instrument.lower()
    return [
        normalized + "@depth@100ms",
        normalized + "@aggTrade",
        normalized + "@markPrice@1s",
        normalized + "@forceOrder",
        "openInterest",
        "snapshot",
        "exchangeInfo",
    ]


def run_planned_capture(
    request: PlannedCaptureRequest,
    *,
    collector: Collector,
    now: Optional[datetime] = None,
) -> Tuple[Dict[str, Any], int]:
    """Reserve, collect, terminate, seal and audit exactly one slot."""
    plan = ForwardCapturePlan.load(request.capture_plan_path)
    slot = next((item for item in plan.slots if item.slot_id == request.capture_slot), None)
    if slot is None:
        raise ValueError("capture slot is not declared in plan")
    duration = slot.min_duration_seconds if request.duration_seconds is None else request.duration_seconds
    registry = SourceRegistry.load(request.source_registry_path)
    software_binding = collector_software_binding()
    observed_now = now or utc_now()
    capture_plan_binding = plan.bind_slot(
        slot_id=slot.slot_id,
        now=observed_now,
        requested_duration_seconds=duration,
        instrument=plan.instrument,
        registry_id=registry.registry_id,
        registry_sha256=registry.sha256,
        collector_software_sha256=software_binding["package_source_sha256"],
    )
    target = request.data_root / plan.plan_id / slot.slot_id
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise ValueError("planned slot evidence directory already exists: %s" % target) from exc
    connection_id = "%s-%s" % (plan.plan_id, slot.slot_id)
    capture_request = PublicCaptureRequest(
        data_dir=str(target),
        connection_id=connection_id,
        instrument=plan.instrument,
        duration_seconds=duration,
        snapshot_limit=request.snapshot_limit,
        oi_poll_seconds=request.oi_poll_seconds,
        metadata_poll_seconds=request.metadata_poll_seconds,
        source_registry=str(request.source_registry_path),
        capture_plan=str(request.capture_plan_path),
        capture_slot=slot.slot_id,
        live_feature_output=request.live_feature_output,
        episode_policy=request.episode_policy,
    )
    try:
        summary, result = collector(capture_request)
    except Exception as exc:
        # Reservation is irreversible by design. Persist an explicit terminal
        # failure so an empty-looking directory can never be mistaken for a
        # future retry candidate.
        store = EventStore(target)
        audit_valid, audit_issues, audit_digest = store.audit()
        manifest = store.write_collection_manifest(connection_id, {
            "schema_version": "collection-manifest-v1",
            "instrument": plan.instrument,
            "venue": "BINANCE_USDM",
            "configured_streams": public_configured_streams(plan.instrument),
            "source_registry": registry.manifest_binding(plan.instrument, public_configured_streams(plan.instrument)),
            "capture_plan": capture_plan_binding,
            "collector_software": software_binding,
            "duration_seconds": duration,
            "collection_result": "UNQUALIFIED",
            "raw_captured": 0,
            "availability_written": 0,
            "parse_errors": 0,
            "book_gaps": 0,
            "reconnects": {},
            "errors": ["planned collector setup failure: %s: %s" % (type(exc).__name__, exc)],
            "audit_valid": audit_valid,
            "audit_issues": audit_issues,
            "audit_digest": audit_digest,
            "replay_digest": DeterministicReplay(store).digest(),
        })
        return ({
            "status": "UNQUALIFIED_NOT_SEALED",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.digest,
            "slot_id": slot.slot_id,
            "connection_id": connection_id,
            "data_dir": str(target),
            "collection_manifest": str(manifest),
        }, 1)
    report: Dict[str, Any] = {
        "plan_id": plan.plan_id,
        "plan_sha256": plan.digest,
        "slot_id": slot.slot_id,
        "connection_id": connection_id,
        "data_dir": str(target),
        "collection": summary,
    }
    if result != 0:
        report["status"] = "UNQUALIFIED_NOT_SEALED"
        return report, result
    store = EventStore(target)
    try:
        report["sealing"] = seal_collection(store, connection_id)
    except ValueError as exc:
        report.update({"status": "QUALIFIED_SMOKE_NOT_SEALED", "sealing_error": str(exc)})
        return report, 1
    audit_valid, audit_issues, audit_digest = store.audit()
    report.update({
        "status": "QUALIFIED_SMOKE_SEALED" if audit_valid else "QUALIFIED_SMOKE_AUDIT_FAILED",
        "audit_valid": audit_valid,
        "audit_issues": audit_issues,
        "audit_digest": audit_digest,
    })
    return report, (0 if audit_valid else 1)
