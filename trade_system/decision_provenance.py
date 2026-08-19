"""Verify that an M5 decision artifact is bound to its declared local inputs.

This module deliberately validates only evidence consistency.  It does not
score a model, synthesize a decision, or submit an order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .action_policy import ResearchActionPolicy
from .model_artifact import ModelArtifact
from .research_report import sha256_file
from .risk_gate_profile import RiskGateProfile
from .shadow import load_decision_rows, load_feature_rows
from .types import AvailabilityKind, parse_utc


def verify_shadow_decision_artifact(
    *,
    decisions_path: Path,
    features_path: Path,
    model_artifact_path: Path,
    action_policy_path: Path,
    risk_gate_profile_path: Path,
) -> Dict[str, Any]:
    """Check point-in-time and version bindings for a decision artifact.

    Every decision row must refer to a feature event in the exact supplied
    artifact, use that event's feature version, and be made no earlier than
    the feature's ACTUAL availability.  The declared model, policy and risk
    fields are then checked against the supplied immutable local artifacts.
    """
    decisions = load_decision_rows(Path(decisions_path))
    features = load_feature_rows(Path(features_path))
    model = ModelArtifact.load(Path(model_artifact_path))
    policy = ResearchActionPolicy.load(Path(action_policy_path))
    risk = RiskGateProfile.load(Path(risk_gate_profile_path))
    issues: List[str] = []
    for event_id, decision in decisions.items():
        feature = features.get(event_id)
        if feature is None:
            issues.append(event_id + ":feature_event_missing")
            continue
        if feature.get("feature_version") != decision.get("feature_version"):
            issues.append(event_id + ":feature_version")
        if feature.get("availability_kind") != AvailabilityKind.ACTUAL.value:
            issues.append(event_id + ":feature_not_actual")
        available_at = feature.get("available_at")
        try:
            if not isinstance(available_at, str) or parse_utc(str(decision["decision_at"])) < parse_utc(available_at):
                issues.append(event_id + ":decision_before_feature_available")
        except ValueError:
            issues.append(event_id + ":feature_available_at_invalid")
        if decision.get("model_version") != model.model_id:
            issues.append(event_id + ":model_version")
        if decision.get("policy_version") != policy.policy_id:
            issues.append(event_id + ":policy_version")
        if decision.get("risk_profile_digest") != risk.digest:
            issues.append(event_id + ":risk_profile_digest")
    return {
        "record_type": "shadow_decision_artifact_verification",
        "valid": not issues,
        "issues": sorted(issues),
        "decision_rows": len(decisions),
        "feature_artifact": str(Path(features_path)),
        "feature_artifact_sha256": sha256_file(Path(features_path)),
        "decision_artifact": str(Path(decisions_path)),
        "decision_artifact_sha256": sha256_file(Path(decisions_path)),
        "model_id": model.model_id,
        "model_artifact_sha256": sha256_file(Path(model_artifact_path)),
        "policy_id": policy.policy_id,
        "action_policy_sha256": policy.digest,
        "risk_profile_id": risk.profile_id,
        "risk_profile_sha256": risk.digest,
        "limitation": "This verifies local feature/model/policy/risk provenance and point-in-time ordering only; it does not establish model correctness, live decision equivalence, account reconciliation, or trading authorization.",
    }
