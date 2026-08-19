"""Offline/live feature comparison for shadow-stability evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List

from .types import parse_utc


@dataclass(frozen=True)
class ShadowPolicy:
    absolute_tolerance: Decimal = Decimal("0.00000001")
    relative_tolerance: Decimal = Decimal("0.0001")


@dataclass(frozen=True)
class ShadowComparison:
    matched_rows: int
    missing_online: List[str]
    missing_offline: List[str]
    version_mismatches: List[str]
    context_mismatches: List[str]
    value_mismatches: List[str]

    @property
    def passed(self) -> bool:
        return not (self.missing_online or self.missing_offline or self.version_mismatches or self.context_mismatches or self.value_mismatches)


@dataclass(frozen=True)
class DecisionShadowComparison:
    matched_rows: int
    missing_online: List[str]
    missing_offline: List[str]
    version_mismatches: List[str]
    decision_mismatches: List[str]
    value_mismatches: List[str]

    @property
    def passed(self) -> bool:
        return not (
            self.missing_online
            or self.missing_offline
            or self.version_mismatches
            or self.decision_mismatches
            or self.value_mismatches
        )


def _load_rows(path: Path) -> Dict[str, Dict[str, object]]:
    rows: Dict[str, Dict[str, object]] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                event_id = str(row["event_id"])
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("invalid feature row at %s:%d" % (path, line_number)) from exc
            if event_id in rows:
                raise ValueError("duplicate feature event_id: %s" % event_id)
            rows[event_id] = row
    return rows


def load_feature_rows(path: Path) -> Dict[str, Dict[str, object]]:
    """Read a feature artifact into its event-ID keyed comparison domain."""
    return _load_rows(Path(path))


def _load_decision_rows(path: Path) -> Dict[str, Dict[str, object]]:
    """Load explicit shadow decisions without inferring missing versions."""
    rows = _load_rows(path)
    required_identity = ("decision_at", "feature_version", "model_version", "policy_version", "risk_profile_digest")
    for event_id, row in rows.items():
        for field in required_identity:
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError("decision row %s lacks %s" % (event_id, field))
        try:
            parse_utc(str(row["decision_at"]))
        except ValueError as exc:
            raise ValueError("decision row %s has invalid decision_at" % event_id) from exc
        decision = row.get("decision")
        if not isinstance(decision, dict):
            raise ValueError("decision row %s lacks decision object" % event_id)
        if not isinstance(decision.get("trade"), bool):
            raise ValueError("decision row %s decision.trade must be boolean" % event_id)
        if not isinstance(decision.get("reason"), str) or not decision["reason"]:
            raise ValueError("decision row %s decision.reason must be non-empty" % event_id)
        for field in ("ev_fill", "ev_submit"):
            try:
                Decimal(str(decision[field]))
            except (KeyError, ValueError, ArithmeticError) as exc:
                raise ValueError("decision row %s has invalid decision.%s" % (event_id, field)) from exc
    return rows


def load_decision_rows(path: Path) -> Dict[str, Dict[str, object]]:
    """Read a decision artifact after enforcing its required row schema."""
    return _load_decision_rows(Path(path))


def _equal(left: Decimal, right: Decimal, policy: ShadowPolicy) -> bool:
    difference = abs(left - right)
    scale = max(abs(left), abs(right), Decimal("1"))
    return difference <= policy.absolute_tolerance or difference / scale <= policy.relative_tolerance


def compare_feature_row_maps(
    offline: Dict[str, Dict[str, object]],
    online: Dict[str, Dict[str, object]],
    policy: ShadowPolicy = ShadowPolicy(),
) -> ShadowComparison:
    missing_online = sorted(set(offline) - set(online))
    missing_offline = sorted(set(online) - set(offline))
    version_mismatches: List[str] = []
    context_mismatches: List[str] = []
    value_mismatches: List[str] = []
    for event_id in sorted(set(offline).intersection(online)):
        left, right = offline[event_id], online[event_id]
        if left.get("feature_version") != right.get("feature_version"):
            version_mismatches.append(event_id)
            continue
        for field in ("available_at", "availability_kind", "episode_id", "episode_state", "episode_policy_id", "episode_policy_sha256", "quality_flags"):
            if left.get(field) != right.get(field):
                context_mismatches.append(event_id + ":" + field)
                break
        if context_mismatches and context_mismatches[-1].startswith(event_id + ":"):
            continue
        left_values, right_values = left.get("values", {}), right.get("values", {})
        if set(left_values) != set(right_values):
            value_mismatches.append(event_id + ":feature_set")
            continue
        for feature in sorted(left_values):
            try:
                if not _equal(Decimal(str(left_values[feature])), Decimal(str(right_values[feature])), policy):
                    value_mismatches.append(event_id + ":" + feature)
                    break
            except Exception as exc:
                raise ValueError("invalid feature value for %s:%s" % (event_id, feature)) from exc
    return ShadowComparison(
        matched_rows=len(set(offline).intersection(online)),
        missing_online=missing_online,
        missing_offline=missing_offline,
        version_mismatches=version_mismatches,
        context_mismatches=context_mismatches,
        value_mismatches=value_mismatches,
    )


def compare_feature_artifacts(offline_path: Path, online_path: Path, policy: ShadowPolicy = ShadowPolicy()) -> ShadowComparison:
    return compare_feature_row_maps(_load_rows(offline_path), _load_rows(online_path), policy)


def compare_decision_artifacts(
    offline_path: Path,
    online_path: Path,
    policy: ShadowPolicy = ShadowPolicy(),
) -> DecisionShadowComparison:
    """Compare point-in-time decision artifacts after feature shadow passes.

    A matching trade boolean alone is insufficient: the feature/model/policy/
    risk profile binding, decision timestamp, reason, and both EV values must
    also agree. This command reports mismatches; it never opens an order.
    """
    offline, online = _load_decision_rows(offline_path), _load_decision_rows(online_path)
    missing_online = sorted(set(offline) - set(online))
    missing_offline = sorted(set(online) - set(offline))
    version_mismatches: List[str] = []
    decision_mismatches: List[str] = []
    value_mismatches: List[str] = []
    identity_fields = ("decision_at", "feature_version", "model_version", "policy_version", "risk_profile_digest")
    for event_id in sorted(set(offline).intersection(online)):
        left, right = offline[event_id], online[event_id]
        mismatched_identity = [field for field in identity_fields if left[field] != right[field]]
        if mismatched_identity:
            version_mismatches.append(event_id + ":" + ",".join(mismatched_identity))
            continue
        left_decision, right_decision = left["decision"], right["decision"]
        if left_decision["trade"] != right_decision["trade"]:
            decision_mismatches.append(event_id + ":trade")
            continue
        if left_decision["reason"] != right_decision["reason"]:
            decision_mismatches.append(event_id + ":reason")
            continue
        for field in ("ev_fill", "ev_submit"):
            if not _equal(Decimal(str(left_decision[field])), Decimal(str(right_decision[field])), policy):
                value_mismatches.append(event_id + ":" + field)
                break
    return DecisionShadowComparison(
        matched_rows=len(set(offline).intersection(online)),
        missing_online=missing_online,
        missing_offline=missing_offline,
        version_mismatches=version_mismatches,
        decision_mismatches=decision_mismatches,
        value_mismatches=value_mismatches,
    )
