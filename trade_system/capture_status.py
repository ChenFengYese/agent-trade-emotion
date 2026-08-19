"""Read-only operational status for frozen forward-capture plans."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from .capture_plan import ForwardCapturePlan
from .event_store import EventStore, EventStoreError


def _binding_matches(plan: ForwardCapturePlan, slot_id: str, manifest: Dict[str, Any]) -> bool:
    capture_plan = manifest.get("capture_plan")
    source_registry = manifest.get("source_registry")
    return (
        isinstance(capture_plan, dict)
        and capture_plan.get("plan_id") == plan.plan_id
        and capture_plan.get("plan_sha256") == plan.digest
        and capture_plan.get("plan_frozen_at") == plan.frozen_at.isoformat()
        and capture_plan.get("slot_id") == slot_id
        and isinstance(source_registry, dict)
        and source_registry.get("registry_id") == plan.source_registry_id
        and source_registry.get("sha256") == plan.source_registry_sha256
    )


def inspect_forward_capture_plan(plan: ForwardCapturePlan, *, data_root: Path, now: datetime) -> Dict[str, Any]:
    """Inspect one planned directory per slot without creating any files."""
    slots: List[Dict[str, Any]] = []
    for slot in plan.slots:
        target = Path(data_root) / plan.plan_id / slot.slot_id
        base = {
            "slot_id": slot.slot_id,
            "start": slot.start.isoformat(),
            "end": slot.end.isoformat(),
            "min_duration_seconds": slot.min_duration_seconds,
            "latest_start": (slot.end - timedelta(seconds=slot.min_duration_seconds)).isoformat(),
            "data_dir": str(target),
        }
        if not target.exists():
            latest_start = slot.end - timedelta(seconds=slot.min_duration_seconds)
            status = "PENDING" if now < slot.start else ("READY" if now <= latest_start else "MISSED")
            detail = dict(base, status=status, requires_operator_action=status == "MISSED")
            if status == "MISSED" and now < slot.end:
                detail["reason_code"] = "INSUFFICIENT_REMAINING_SLOT_TIME"
            slots.append(detail)
            continue
        if not target.is_dir():
            slots.append(dict(base, status="INVALID_TARGET", requires_operator_action=True))
            continue
        connection_id = "%s-%s" % (plan.plan_id, slot.slot_id)
        manifest_path = target / "manifests" / "collection" / (connection_id + ".json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or manifest.get("record_type") != "collection_manifest" or manifest.get("collection_id") != connection_id:
                raise ValueError("invalid collection manifest identity")
        except (OSError, ValueError, json.JSONDecodeError):
            slots.append(dict(base, status="INCOMPLETE", requires_operator_action=True))
            continue
        if not _binding_matches(plan, slot.slot_id, manifest):
            slots.append(dict(base, status="PLAN_BINDING_MISMATCH", requires_operator_action=True, collection_result=manifest.get("collection_result")))
            continue
        try:
            store = EventStore(target, create=False)
            audit_valid, audit_issues, audit_digest = store.audit()
            raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(connection_id + "-")]
            segments = sorted({Path(raw.raw_segment).stem for raw in raws})
            sealed = {path.stem for path in store.manifest_root.glob("*.json")}
        except (EventStoreError, OSError, ValueError, json.JSONDecodeError) as exc:
            slots.append(dict(base, status="INVALID_EVIDENCE", requires_operator_action=True, error=str(exc)))
            continue
        result = manifest.get("collection_result")
        detail = dict(
            base,
            collection_result=result,
            raw_records=len(raws),
            raw_segments=segments,
            sealed_segments=sorted(sealed),
            audit_valid=audit_valid,
            audit_issues=audit_issues,
            audit_digest=audit_digest,
        )
        if result == "QUALIFIED_SMOKE" and raws and audit_valid and all(segment in sealed for segment in segments):
            slots.append(dict(detail, status="QUALIFIED_SMOKE_SEALED", requires_operator_action=False))
        elif result == "QUALIFIED_SMOKE":
            slots.append(dict(detail, status="QUALIFIED_SMOKE_NOT_SEALED", requires_operator_action=True))
        elif result == "UNQUALIFIED":
            slots.append(dict(detail, status="UNQUALIFIED", requires_operator_action=True))
        else:
            slots.append(dict(detail, status="INVALID_COLLECTION_RESULT", requires_operator_action=True))
    statuses = [item["status"] for item in slots]
    return {
        "plan_id": plan.plan_id,
        "plan_sha256": plan.digest,
        "inspected_at": now.isoformat(),
        "data_root": str(data_root),
        "slots": slots,
        "completed_slots": sum(status == "QUALIFIED_SMOKE_SEALED" for status in statuses),
        "requires_operator_action": any(item["requires_operator_action"] for item in slots),
        "all_slots_sealed": bool(slots) and all(status == "QUALIFIED_SMOKE_SEALED" for status in statuses),
    }
