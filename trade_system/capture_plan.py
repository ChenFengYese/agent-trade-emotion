"""Pre-registered forward-capture plans for auditable data collection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .types import parse_utc


FROZEN_CAPTURE_PLAN_STATUS = "FROZEN_FORWARD_CAPTURE_PLAN"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class CapturePlanError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _non_empty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CapturePlanError("%s must be a non-empty string" % name)
    return value


def _identifier(value: Any, name: str) -> str:
    result = _non_empty(value, name)
    if not _IDENTIFIER.fullmatch(result):
        raise CapturePlanError("%s contains unsupported characters" % name)
    return result


def _positive_seconds(value: Any, name: str) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise CapturePlanError("%s must be numeric" % name) from exc
    if seconds <= 0:
        raise CapturePlanError("%s must be positive" % name)
    return seconds


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise CapturePlanError("%s must be a positive integer" % name)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CapturePlanError("%s must be a positive integer" % name) from exc
    if number <= 0 or number != value:
        raise CapturePlanError("%s must be a positive integer" % name)
    return number


@dataclass(frozen=True)
class CaptureSlot:
    slot_id: str
    start: datetime
    end: datetime
    min_duration_seconds: float
    coverage_intent: Tuple[str, ...]


@dataclass(frozen=True)
class CaptureResourceBudget:
    """Frozen local resource limits; crossing either limit stops new slots."""

    min_free_bytes: int
    max_plan_bytes: int


@dataclass(frozen=True)
class ForwardCapturePlan:
    plan_id: str
    frozen_at: datetime
    instrument: str
    source_registry_id: str
    source_registry_sha256: str
    collector_software_sha256: str
    slots: Tuple[CaptureSlot, ...]
    resource_budget: Optional[CaptureResourceBudget]
    digest: str

    @classmethod
    def load(cls, path: Path) -> "ForwardCapturePlan":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CapturePlanError("cannot load forward capture plan") from exc
        if not isinstance(raw, dict):
            raise CapturePlanError("forward capture plan must be an object")
        if raw.get("status") != FROZEN_CAPTURE_PLAN_STATUS:
            raise CapturePlanError("forward capture plan requires status %s" % FROZEN_CAPTURE_PLAN_STATUS)
        _non_empty(raw.get("frozen_at"), "frozen_at")
        try:
            frozen_at = parse_utc(raw["frozen_at"])
        except ValueError as exc:
            raise CapturePlanError("frozen_at must be UTC ISO-8601") from exc
        registry = raw.get("source_registry")
        if not isinstance(registry, dict):
            raise CapturePlanError("source_registry must be an object")
        registry_id = _non_empty(registry.get("registry_id"), "source_registry.registry_id")
        registry_sha = _non_empty(registry.get("sha256"), "source_registry.sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", registry_sha):
            raise CapturePlanError("source_registry.sha256 must be lowercase SHA-256")
        software_sha = str(raw.get("collector_software_sha256", ""))
        if software_sha and not re.fullmatch(r"[0-9a-f]{64}", software_sha):
            raise CapturePlanError("collector_software_sha256 must be lowercase SHA-256")
        slot_values = raw.get("slots")
        if not isinstance(slot_values, list) or not slot_values:
            raise CapturePlanError("slots must be a non-empty list")
        slots = []
        identifiers = set()
        for index, value in enumerate(slot_values):
            if not isinstance(value, dict):
                raise CapturePlanError("slots[%d] must be an object" % index)
            slot_id = _identifier(value.get("slot_id"), "slots[%d].slot_id" % index)
            if slot_id in identifiers:
                raise CapturePlanError("slot IDs must be unique")
            identifiers.add(slot_id)
            try:
                start, end = parse_utc(value["start"]), parse_utc(value["end"])
            except (KeyError, ValueError) as exc:
                raise CapturePlanError("slots[%d] start/end must be UTC ISO-8601" % index) from exc
            if end <= start:
                raise CapturePlanError("slots[%d] end must follow start" % index)
            if start < frozen_at:
                raise CapturePlanError("slots[%d] starts before the plan was frozen" % index)
            duration = _positive_seconds(value.get("min_duration_seconds"), "slots[%d].min_duration_seconds" % index)
            if timedelta(seconds=duration) > end - start:
                raise CapturePlanError("slots[%d] minimum duration exceeds its window" % index)
            intent = value.get("coverage_intent")
            if not isinstance(intent, list) or not intent or not all(isinstance(item, str) and item for item in intent):
                raise CapturePlanError("slots[%d].coverage_intent must be a non-empty string list" % index)
            slots.append(CaptureSlot(slot_id, start, end, duration, tuple(intent)))
        ordered = sorted(slots, key=lambda item: item.start)
        if any(right.start < left.end for left, right in zip(ordered, ordered[1:])):
            raise CapturePlanError("slots must not overlap")
        resource_budget = None
        budget_raw = raw.get("resource_budget")
        if budget_raw is not None:
            if not isinstance(budget_raw, dict):
                raise CapturePlanError("resource_budget must be an object")
            if set(budget_raw) != {"min_free_bytes", "max_plan_bytes"}:
                raise CapturePlanError("resource_budget must contain exactly min_free_bytes and max_plan_bytes")
            resource_budget = CaptureResourceBudget(
                min_free_bytes=_positive_integer(budget_raw["min_free_bytes"], "resource_budget.min_free_bytes"),
                max_plan_bytes=_positive_integer(budget_raw["max_plan_bytes"], "resource_budget.max_plan_bytes"),
            )
        return cls(
            plan_id=_identifier(raw.get("plan_id"), "plan_id"),
            frozen_at=frozen_at,
            instrument=_non_empty(raw.get("instrument"), "instrument").upper(),
            source_registry_id=registry_id,
            source_registry_sha256=registry_sha,
            collector_software_sha256=software_sha,
            slots=tuple(ordered),
            resource_budget=resource_budget,
            digest=hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest(),
        )

    def bind_slot(self, *, slot_id: str, now: datetime, requested_duration_seconds: float, instrument: str, registry_id: str, registry_sha256: str, collector_software_sha256: str = "") -> Dict[str, Any]:
        if now < self.frozen_at:
            raise CapturePlanError("capture cannot start before the plan is frozen")
        if instrument.upper() != self.instrument:
            raise CapturePlanError("capture instrument does not match plan")
        if registry_id != self.source_registry_id or registry_sha256 != self.source_registry_sha256:
            raise CapturePlanError("capture source registry does not match plan")
        if self.collector_software_sha256 and collector_software_sha256 != self.collector_software_sha256:
            raise CapturePlanError("collector software digest does not match plan")
        slot = next((item for item in self.slots if item.slot_id == slot_id), None)
        if slot is None:
            raise CapturePlanError("capture slot is not declared in plan")
        if now < slot.start or now >= slot.end:
            raise CapturePlanError("capture start is outside its frozen slot")
        if requested_duration_seconds < slot.min_duration_seconds:
            raise CapturePlanError("capture duration is below frozen slot minimum")
        if now + timedelta(seconds=requested_duration_seconds) > slot.end:
            raise CapturePlanError("capture duration would exceed frozen slot window")
        return {
            "plan_id": self.plan_id,
            "plan_sha256": self.digest,
            "plan_frozen_at": self.frozen_at.isoformat(),
            "slot_id": slot.slot_id,
            "slot_start": slot.start.isoformat(),
            "slot_end": slot.end.isoformat(),
            "coverage_intent": slot.coverage_intent,
            "collector_software_sha256": self.collector_software_sha256 or None,
        }
