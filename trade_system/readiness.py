"""Read-only P0 research-readiness summary.

This module evaluates an already-frozen G1 policy and reports quantitative
collection deficits. It never freezes parameters or grants trading capability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from .collection_inventory import inventory_collections
from .event_store import EventStore
from .g1_acceptance import G1AcceptancePolicy, G1PolicyError, validate_g1_stores
from .protocol import ProtocolError, ResearchProtocol


def _g1_policy_status(path: Path) -> Dict[str, Any]:
    try:
        policy = G1AcceptancePolicy.load(path)
    except G1PolicyError as exc:
        return {"path": str(path), "valid": False, "frozen": False, "error": str(exc)}
    return {
        "path": str(path),
        "valid": True,
        "policy_id": policy.policy_id,
        "status": policy.status,
        "frozen": policy.is_frozen,
        "sha256": policy.digest,
    }


def _research_protocol_status(path: Path) -> Dict[str, Any]:
    try:
        protocol = ResearchProtocol.load(path)
    except ProtocolError as exc:
        return {"path": str(path), "valid": False, "frozen": False, "error": str(exc)}
    return {
        "path": str(path),
        "valid": True,
        "protocol_id": protocol.protocol_id,
        "status": protocol.status,
        "frozen": protocol.is_frozen_for_research,
    }


def build_research_readiness(
    roots: Iterable[Path],
    *,
    g1_policy_path: Path,
    research_protocol_path: Path,
) -> Dict[str, Any]:
    """Report the next hard gate and exact evidence deficits without mutation."""
    inventory = inventory_collections(tuple(Path(item) for item in roots))
    policy = _g1_policy_status(Path(g1_policy_path))
    protocol = _research_protocol_status(Path(research_protocol_path))
    blockers = []
    if inventory["summary"]["sealed_current_collections"] == 0:
        blockers.append("NO_SEALED_CURRENT_FORWARD_COLLECTION")
    if not policy["valid"]:
        blockers.append("INVALID_G1_POLICY")
    elif not policy["frozen"]:
        blockers.append("G1_POLICY_NOT_FROZEN")
    g1_evaluation = None
    if policy.get("frozen"):
        selected_roots = sorted({
            row["data_dir"]
            for row in inventory["collections"]
            if row.get("status") == "SEALED_CURRENT" and row.get("data_dir")
        })
        if selected_roots:
            frozen_policy = G1AcceptancePolicy.load(Path(g1_policy_path))
            g1_evaluation = validate_g1_stores(
                tuple(EventStore(Path(root), create=False) for root in selected_roots),
                frozen_policy,
            )
            if not g1_evaluation["passed"]:
                blockers.append("G1_EVIDENCE_BELOW_FROZEN_POLICY")
        else:
            frozen_policy = G1AcceptancePolicy.load(Path(g1_policy_path))
            g1_evaluation = {
                "passed": False,
                "status": "WAIT_DATA",
                "policy_id": frozen_policy.policy_id,
                "policy_sha256": frozen_policy.digest,
                "qualified_collections": 0,
                "total_collections": 0,
                "total_observed_seconds": 0.0,
                "distinct_utc_dates": [],
                "distinct_utc_hour_buckets": [],
                "deficits": {
                    "qualified_collections": frozen_policy.min_qualified_collections,
                    "observed_seconds": frozen_policy.min_total_observed_seconds,
                    "distinct_utc_days": frozen_policy.min_distinct_utc_days,
                    "distinct_utc_hour_buckets": frozen_policy.min_distinct_utc_hour_buckets,
                },
                "collection_failure_counts": {},
                "reasons": ["no sealed current evidence is available"],
            }
            blockers.append("G1_EVIDENCE_BELOW_FROZEN_POLICY")
    if not protocol["valid"]:
        blockers.append("INVALID_RESEARCH_PROTOCOL")
    elif not protocol["frozen"]:
        blockers.append("RESEARCH_PROTOCOL_NOT_FROZEN")
    # A frozen protocol itself requires a passed G1 report binding. This
    # command does not accept an arbitrary report as a shortcut.
    if g1_evaluation and g1_evaluation.get("passed") and not protocol.get("frozen"):
        blockers.append("WRITE_IMMUTABLE_G1_PASS_REPORT_THEN_FINALIZE_PROTOCOL")
    if g1_evaluation and g1_evaluation.get("passed") and protocol.get("frozen"):
        blockers.append("VERIFY_G1_PASS_REPORT_AND_BUILD_G1_BUNDLE")
    if g1_evaluation and not g1_evaluation.get("passed"):
        state = "COLLECTING"
        next_action = "Continue only predeclared forward slots; inspect collection rejection counts and frozen deficits."
    elif policy.get("frozen") and g1_evaluation and g1_evaluation.get("passed"):
        state = "G1_EVALUATION_PASS_PENDING_IMMUTABLE_BINDING"
        next_action = "Write a new immutable PASS G1 report, then finalize the preregistered research protocol against its exact SHA-256."
    else:
        state = "POLICY_PREREGISTRATION_REQUIRED"
        next_action = "Freeze G1 acceptance before collecting evidence intended for that gate."
    return {
        "record_type": "p0_research_readiness",
        "forward_evidence": inventory["summary"],
        "g1_policy": policy,
        "g1_evaluation": g1_evaluation,
        "research_protocol": protocol,
        "blockers": blockers,
        "readiness": state,
        "next_action": next_action,
        "limitation": "This is a read-only navigation and frozen-G1 evaluation. It does not persist a PASS report, finalize a protocol, build features or labels, fit a model, evaluate paper execution, or authorize trading.",
    }
