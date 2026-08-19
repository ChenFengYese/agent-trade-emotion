"""Frozen, collection-local context and label windows for v2 research roles.

This contract closes a common provenance gap: a capture plan may say that a
collection is DEVELOPMENT/HOLDOUT eligible, while still being too short to
form 4H context or to observe a 300s market-path label.  The window is frozen
before collection and is checked again against each terminal collection.  It
never permits warmup, decision, or label evidence to span collections.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from .capture_plan import ForwardCapturePlan
from .feature_context import FeatureContextPolicy
from .types import parse_utc


FROZEN_ROLE_CAPTURE_WINDOW = "FROZEN_ROLE_CAPTURE_WINDOW"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class RoleCaptureWindowError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _integer(value: Any, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise RoleCaptureWindowError("%s must be an integer" % name)
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RoleCaptureWindowError("%s must be an integer" % name) from exc
    if result < minimum or result != value:
        raise RoleCaptureWindowError("%s must be at least %d" % (name, minimum))
    return result


def _binding(raw: Any, name: str) -> Tuple[str, str]:
    if not isinstance(raw, dict):
        raise RoleCaptureWindowError("%s must be an object" % name)
    identifier, digest = raw.get("id"), raw.get("sha256")
    if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier):
        raise RoleCaptureWindowError("%s.id is invalid" % name)
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RoleCaptureWindowError("%s.sha256 is invalid" % name)
    return identifier, digest


@dataclass(frozen=True)
class RoleCaptureWindow:
    window_id: str
    frozen_at: datetime
    role: str
    capture_plan_id: str
    capture_plan_sha256: str
    context_policy_id: str
    context_policy_sha256: str
    warmup_seconds: int
    minimum_eligible_decision_seconds: int
    label_tail_seconds: int
    digest: str

    @property
    def minimum_collection_seconds(self) -> int:
        return self.warmup_seconds + self.minimum_eligible_decision_seconds + self.label_tail_seconds

    @classmethod
    def load(cls, path: Path) -> "RoleCaptureWindow":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RoleCaptureWindowError("cannot load role capture window") from exc
        if not isinstance(raw, dict) or raw.get("status") != FROZEN_ROLE_CAPTURE_WINDOW:
            raise RoleCaptureWindowError("role capture window must have status %s" % FROZEN_ROLE_CAPTURE_WINDOW)
        window_id = raw.get("window_id")
        if not isinstance(window_id, str) or not _IDENTIFIER.fullmatch(window_id):
            raise RoleCaptureWindowError("window_id is invalid")
        try:
            frozen_at = parse_utc(raw["frozen_at"])
        except (KeyError, ValueError) as exc:
            raise RoleCaptureWindowError("frozen_at must be UTC ISO-8601") from exc
        role = raw.get("role")
        if role not in {"DEVELOPMENT", "HOLDOUT"}:
            raise RoleCaptureWindowError("role must be DEVELOPMENT or HOLDOUT")
        plan_id, plan_sha = _binding(raw.get("capture_plan"), "capture_plan")
        context_id, context_sha = _binding(raw.get("context_policy"), "context_policy")
        warmup = _integer(raw.get("warmup_seconds"), "warmup_seconds")
        decision = _integer(raw.get("minimum_eligible_decision_seconds"), "minimum_eligible_decision_seconds")
        tail = _integer(raw.get("label_tail_seconds"), "label_tail_seconds")
        return cls(window_id, frozen_at, role, plan_id, plan_sha, context_id, context_sha, warmup, decision, tail,
                   hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest())

    def assert_matches(self, *, role: str, plan: ForwardCapturePlan, context_policy: FeatureContextPolicy) -> None:
        if role != self.role:
            raise RoleCaptureWindowError("role capture window role does not match requested role")
        if (self.capture_plan_id, self.capture_plan_sha256) != (plan.plan_id, plan.digest):
            raise RoleCaptureWindowError("role capture window capture-plan binding does not match")
        if (self.context_policy_id, self.context_policy_sha256) != (context_policy.context_policy_id, context_policy.digest):
            raise RoleCaptureWindowError("role capture window context-policy binding does not match")
        if self.warmup_seconds != context_policy.warmup_seconds:
            raise RoleCaptureWindowError("role capture window warmup must equal frozen context warmup")
        for slot in plan.slots:
            if slot.min_duration_seconds < self.minimum_collection_seconds:
                raise RoleCaptureWindowError("capture slot %s is shorter than context warmup + decision + label tail" % slot.slot_id)

    def assert_collection_coverage(self, availability: Iterable[Any]) -> Dict[str, str]:
        """Validate one collection's ACTUAL timestamps, without cross-splicing.

        The first and last timestamps are intentionally calculated from the
        passed collection only.  Each raw event must have one ACTUAL record;
        reconstructed and gaps fail before a feature or label can be admitted.
        """
        records = list(availability)
        if not records:
            raise RoleCaptureWindowError("collection has no availability records")
        if any(getattr(item, "availability_kind", None).value != "ACTUAL" for item in records):
            raise RoleCaptureWindowError("role window requires ACTUAL-only availability")
        times = sorted(item.available_at for item in records)
        first, last = times[0], times[-1]
        required = timedelta(seconds=self.minimum_collection_seconds)
        if last - first < required:
            raise RoleCaptureWindowError("collection is shorter than warmup + eligible decision + label tail")
        return {
            "first_actual_available_at": first.isoformat(),
            "eligible_decision_start_at": (first + timedelta(seconds=self.warmup_seconds)).isoformat(),
            "eligible_decision_end_at": (last - timedelta(seconds=self.label_tail_seconds)).isoformat(),
            "label_tail_end_at": last.isoformat(),
        }
