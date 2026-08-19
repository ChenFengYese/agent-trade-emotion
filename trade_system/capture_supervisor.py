"""Cheap, read-only selection of the next frozen forward-capture slot."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .capture_plan import ForwardCapturePlan


@dataclass(frozen=True)
class CaptureSupervisorDecision:
    action: str
    plan_id: str
    plan_sha256: str
    decided_at: datetime
    slot_id: Optional[str]
    reason_codes: Tuple[str, ...]
    pending_slots: int
    reserved_slots: int
    missed_slots: int
    resource_guard: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_type": "capture_supervisor_decision",
            "action": self.action,
            "plan_id": self.plan_id,
            "plan_sha256": self.plan_sha256,
            "decided_at": self.decided_at.isoformat(),
            "slot_id": self.slot_id,
            "reason_codes": list(self.reason_codes),
            "pending_slots": self.pending_slots,
            "reserved_slots": self.reserved_slots,
            "missed_slots": self.missed_slots,
            "resource_guard": self.resource_guard,
        }


def _nearest_existing(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists():
        if candidate.parent == candidate:
            raise ValueError("cannot locate an existing filesystem ancestor for data root")
        candidate = candidate.parent
    return candidate


def _tree_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except OSError as exc:
        raise ValueError("cannot measure capture-plan storage") from exc
    return total


def _resource_guard(plan: ForwardCapturePlan, data_root: Path) -> Dict[str, Any]:
    budget = plan.resource_budget
    if budget is None:
        return {"enabled": False, "passed": True}
    usage = shutil.disk_usage(_nearest_existing(data_root))
    plan_bytes = _tree_bytes(data_root / plan.plan_id)
    reasons = []
    if usage.free < budget.min_free_bytes:
        reasons.append("FREE_BYTES_BELOW_FROZEN_MINIMUM")
    if plan_bytes >= budget.max_plan_bytes:
        reasons.append("PLAN_BYTES_AT_OR_ABOVE_FROZEN_MAXIMUM")
    return {
        "enabled": True,
        "passed": not reasons,
        "free_bytes": usage.free,
        "plan_bytes": plan_bytes,
        "min_free_bytes": budget.min_free_bytes,
        "max_plan_bytes": budget.max_plan_bytes,
        "reason_codes": reasons,
    }


def decide_capture_slot(plan: ForwardCapturePlan, *, data_root: Path, now: datetime) -> CaptureSupervisorDecision:
    """Choose at most one due slot without auditing or mutating evidence."""
    ready = []
    pending = reserved = missed = 0
    for slot in plan.slots:
        target = Path(data_root) / plan.plan_id / slot.slot_id
        if target.exists():
            reserved += 1
            continue
        latest_start = slot.end - timedelta(seconds=slot.min_duration_seconds)
        if now < slot.start:
            pending += 1
        elif now <= latest_start:
            ready.append(slot)
        else:
            missed += 1
    if len(ready) > 1:
        raise ValueError("capture plan exposed more than one runnable non-overlapping slot")
    resource = _resource_guard(plan, Path(data_root))
    if not resource["passed"]:
        reasons = tuple(resource.get("reason_codes", ()))
        return CaptureSupervisorDecision(
            "RESOURCE_BLOCKED", plan.plan_id, plan.digest, now, None, reasons,
            pending, reserved, missed, resource,
        )
    if ready:
        reasons = ["DUE_SLOT_AVAILABLE"]
        if missed:
            reasons.append("MISSED_SLOTS_PRESENT")
        return CaptureSupervisorDecision(
            "RUN_SLOT", plan.plan_id, plan.digest, now, ready[0].slot_id, tuple(reasons),
            pending, reserved, missed, resource,
        )
    if pending:
        reasons = ["FUTURE_SLOT_PENDING"]
        if missed:
            reasons.append("MISSED_SLOTS_PRESENT")
        return CaptureSupervisorDecision(
            "WAIT", plan.plan_id, plan.digest, now, None, tuple(reasons),
            pending, reserved, missed, resource,
        )
    if reserved == len(plan.slots):
        return CaptureSupervisorDecision(
            "PLAN_RESERVED", plan.plan_id, plan.digest, now, None,
            ("ALL_SLOTS_RESERVED_REQUIRES_STATUS_AUDIT",), pending, reserved, missed, resource,
        )
    return CaptureSupervisorDecision(
        "PLAN_EXHAUSTED", plan.plan_id, plan.digest, now, None,
        ("NO_FUTURE_OR_RUNNABLE_SLOTS", "MISSED_SLOTS_PRESENT"), pending, reserved, missed, resource,
    )
