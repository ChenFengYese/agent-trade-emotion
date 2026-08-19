"""Versioned paper-only contract for reason-level risk-gate resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Tuple

from .types import GateLevel


FROZEN_PAPER_RISK_GATE_PROFILE = "FROZEN_PAPER_RISK_GATE_PROFILE"
_STAGES = {"WATCH", "ENTER_PROBE", "ADD_POSITION_CONFIRMED"}
_RESOLVER_ORDER = ("HALT_AND_RECONCILE", "NO_NEW_RISK", "OPEN")


class RiskGateProfileError(ValueError):
    pass


def _non_empty(raw: Dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise RiskGateProfileError("%s must be a non-empty string" % field)
    return value


def _non_negative_seconds(raw: Dict[str, Any], field: str) -> timedelta:
    try:
        seconds = float(raw.get(field))
    except (TypeError, ValueError) as exc:
        raise RiskGateProfileError("%s must be numeric" % field) from exc
    if seconds < 0:
        raise RiskGateProfileError("%s must be non-negative" % field)
    return timedelta(seconds=seconds)


@dataclass(frozen=True)
class GateReasonPolicy:
    reason_code: str
    level: GateLevel
    source_contract: str
    freshness_contract: str
    threshold_contract: str
    activation_duration: timedelta
    recovery_hysteresis: timedelta
    manual_clear_required: bool
    stage_actions: Dict[str, str]


@dataclass(frozen=True)
class RiskGateProfile:
    profile_id: str
    status: str
    frozen_at: str
    policies: Tuple[GateReasonPolicy, ...]
    digest: str

    @classmethod
    def load(cls, path: Path) -> "RiskGateProfile":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RiskGateProfileError("cannot load risk gate profile") from exc
        if not isinstance(raw, dict):
            raise RiskGateProfileError("risk gate profile must be an object")
        profile_id = _non_empty(raw, "profile_id")
        status = _non_empty(raw, "status")
        if status != FROZEN_PAPER_RISK_GATE_PROFILE:
            raise RiskGateProfileError("risk gate profile must be frozen for paper")
        frozen_at = _non_empty(raw, "frozen_at")
        try:
            timestamp = frozen_at.replace("Z", "+00:00")
            if datetime.fromisoformat(timestamp).tzinfo is None:
                raise ValueError("timezone missing")
        except ValueError as exc:
            raise RiskGateProfileError("frozen_at must be ISO-8601 with timezone") from exc
        if raw.get("resolver_order") != list(_RESOLVER_ORDER):
            raise RiskGateProfileError("resolver_order must be HALT_AND_RECONCILE, NO_NEW_RISK, OPEN")
        policies_raw = raw.get("reason_policies")
        if not isinstance(policies_raw, list) or not policies_raw:
            raise RiskGateProfileError("reason_policies must be a non-empty list")
        policies = []
        seen = set()
        for item in policies_raw:
            if not isinstance(item, dict):
                raise RiskGateProfileError("reason policy must be an object")
            reason = _non_empty(item, "reason_code")
            if reason in seen:
                raise RiskGateProfileError("reason_code must be unique")
            seen.add(reason)
            try:
                level = GateLevel[_non_empty(item, "gate_level")]
            except KeyError as exc:
                raise RiskGateProfileError("gate_level is unsupported") from exc
            if level == GateLevel.OPEN:
                raise RiskGateProfileError("reason policies must be restrictive; OPEN is the resolver default")
            manual = item.get("manual_clear_required")
            if not isinstance(manual, bool):
                raise RiskGateProfileError("manual_clear_required must be boolean")
            actions = item.get("stage_actions")
            if not isinstance(actions, dict) or set(actions) != _STAGES or not all(isinstance(value, str) and value for value in actions.values()):
                raise RiskGateProfileError("stage_actions must define WATCH, ENTER_PROBE and ADD_POSITION_CONFIRMED")
            policies.append(GateReasonPolicy(
                reason_code=reason,
                level=level,
                source_contract=_non_empty(item, "source_contract"),
                freshness_contract=_non_empty(item, "freshness_contract"),
                threshold_contract=_non_empty(item, "threshold_contract"),
                activation_duration=_non_negative_seconds(item, "activation_duration_seconds"),
                recovery_hysteresis=_non_negative_seconds(item, "recovery_hysteresis_seconds"),
                manual_clear_required=manual,
                stage_actions=dict(actions),
            ))
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        import hashlib
        return cls(profile_id, status, frozen_at, tuple(policies), hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    def policy_for(self, reason_code: str) -> GateReasonPolicy:
        for policy in self.policies:
            if policy.reason_code == reason_code:
                return policy
        raise RiskGateProfileError("reason is not declared by frozen profile: %s" % reason_code)

    def summary(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "status": self.status,
            "frozen_at": self.frozen_at,
            "digest": self.digest,
            "resolver_order": list(_RESOLVER_ORDER),
            "reason_codes": [policy.reason_code for policy in self.policies],
        }
