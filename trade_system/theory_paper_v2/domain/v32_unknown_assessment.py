"""Objective UNKNOWN plus registry-resolved subjective assessment."""

from __future__ import annotations

from datetime import timedelta
import hashlib
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_bytes, self_digest, verify_self_digest
from .v32_authorized_revision_common import (
    EXTERNAL_EXECUTION_AUTHORITY,
    SCHEMA_VERSION,
    SOURCE_SCOPE,
    V32AuthorizedRevisionContractError,
    binding,
    boundary,
    digest,
    integer,
    moment,
    sorted_unique_texts,
    text,
    time,
    verify_boundary,
)
from .v32_cycle_source_admission import verify_v32_pit_evidence_registry
from .v32_dynamic_research import SUBJECTIVE_PLAUSIBILITY_TIERS


OBJECTIVE_SCHEMA_ID = "theory_paper_v32_objective_unknown_v1"
OBJECTIVE_DIGEST_FIELD = "objective_unknown_digest"
EVIDENCE_REGISTRY_SCHEMA_ID = "theory_paper_v32_unknown_assessment_evidence_registry_v1"
EVIDENCE_REGISTRY_DIGEST_FIELD = "unknown_assessment_evidence_registry_digest"
ASSESSMENT_SCHEMA_ID = "theory_paper_v32_unknown_subjective_assessment_v1"
ASSESSMENT_DIGEST_FIELD = "unknown_subjective_assessment_digest"
POLICY_SCHEMA_ID = "theory_paper_v32_unknown_subjective_policy_v1"
POLICY_DIGEST_FIELD = "unknown_subjective_policy_digest"
PIT_AVAILABILITY_SCHEMA_ID = (
    "theory_paper_v32_pit_evidence_availability_registry_v1"
)
PIT_AVAILABILITY_DIGEST_FIELD = "pit_evidence_availability_registry_digest"
MAX_SUBJECTIVE_ASSESSMENT_TTL_SECONDS = 86_400
DIRECTIONAL_VIEWS = frozenset({"LONG", "SHORT", "NEUTRAL", "MIXED", "UNKNOWN"})


class V32UnknownAssessmentError(ValueError):
    """An objective UNKNOWN changed or a subjective assessment was ungrounded."""


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def build_v32_objective_unknown_v1(
    *,
    unknown_id: str,
    run_id: str,
    cycle_index: int,
    field_path: str,
    as_of: str,
    detected_at: str,
    missingness_reason: str,
    source_request_refs: Sequence[str],
    impact: str,
    claim_ceiling: str,
) -> dict[str, Any]:
    try:
        observed = time(as_of, "V32_OBJECTIVE_UNKNOWN_TIME_INVALID")
        detected = time(detected_at, "V32_OBJECTIVE_UNKNOWN_TIME_INVALID")
        if moment(detected, "V32_OBJECTIVE_UNKNOWN_TIME_INVALID") < moment(
            observed, "V32_OBJECTIVE_UNKNOWN_TIME_INVALID"
        ):
            raise V32UnknownAssessmentError("V32_OBJECTIVE_UNKNOWN_TIME_INVALID")
        document = {
            "schema_id": OBJECTIVE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "unknown_id": text(unknown_id, "V32_OBJECTIVE_UNKNOWN_ID_INVALID"),
            "run_id": text(run_id, "V32_OBJECTIVE_UNKNOWN_RUN_INVALID"),
            "cycle_index": integer(
                cycle_index,
                "V32_OBJECTIVE_UNKNOWN_CYCLE_INVALID",
                minimum=1,
                maximum=16,
            ),
            "field_path": text(field_path, "V32_OBJECTIVE_UNKNOWN_FIELD_INVALID"),
            "objective_status": "UNKNOWN",
            "objective_value": None,
            "as_of": observed,
            "detected_at": detected,
            "missingness_reason": text(
                missingness_reason, "V32_OBJECTIVE_UNKNOWN_REASON_INVALID"
            ),
            "source_request_refs": sorted_unique_texts(
                source_request_refs,
                "V32_OBJECTIVE_UNKNOWN_SOURCE_REFS_INVALID",
                allow_empty=True,
                maximum=64,
            ),
            "impact": text(impact, "V32_OBJECTIVE_UNKNOWN_IMPACT_INVALID"),
            "claim_ceiling": text(
                claim_ceiling, "V32_OBJECTIVE_UNKNOWN_CLAIM_CEILING_INVALID"
            ),
            "zero_imputed": False,
            "historical_backfill_allowed": False,
            "agent_may_change_objective_status": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        if isinstance(exc, V32UnknownAssessmentError):
            raise
        raise V32UnknownAssessmentError("V32_OBJECTIVE_UNKNOWN_INPUT_INVALID") from exc
    return self_digest(document, OBJECTIVE_DIGEST_FIELD)


def verify_v32_objective_unknown_v1(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, OBJECTIVE_DIGEST_FIELD)
        verify_boundary(document, "V32_OBJECTIVE_UNKNOWN_BOUNDARY_INVALID")
        rebuilt = build_v32_objective_unknown_v1(
            unknown_id=document["unknown_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            field_path=document["field_path"],
            as_of=document["as_of"],
            detected_at=document["detected_at"],
            missingness_reason=document["missingness_reason"],
            source_request_refs=document["source_request_refs"],
            impact=document["impact"],
            claim_ceiling=document["claim_ceiling"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32UnknownAssessmentError):
            raise
        raise V32UnknownAssessmentError("V32_OBJECTIVE_UNKNOWN_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[OBJECTIVE_DIGEST_FIELD]:
        raise V32UnknownAssessmentError("V32_OBJECTIVE_UNKNOWN_REPLAY_MISMATCH")
    return supplied


def _availability_registry(document: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    try:
        supplied = verify_self_digest(document, PIT_AVAILABILITY_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID") from exc
    entries = document.get("entries")
    if (
        document.get("schema_id") != PIT_AVAILABILITY_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or not isinstance(entries, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"evidence_ref", "available_at"}
            for row in entries
        )
        or len(entries) != len({row["evidence_ref"] for row in entries})
    ):
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID")
    by_ref: dict[str, str] = {}
    for row in entries:
        reference = digest(row["evidence_ref"], "V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID")
        available = time(
            row["available_at"], "V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID"
        )
        if moment(available, "V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID") > moment(
            document["as_of"], "V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID"
        ):
            raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID")
        by_ref[reference] = available
    # This registry is owned by the existing continuity layer.  Its frozen
    # schema deliberately has the three boundary fields below, rather than the
    # wider revision boundary.  Requiring fields that the owning schema never
    # emitted would reject every legitimate registry.
    if (
        document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
    ):
        raise V32UnknownAssessmentError(
            "V32_UNKNOWN_EVIDENCE_AVAILABILITY_INVALID"
        )
    return supplied, by_ref


def build_v32_unknown_subjective_policy_v1(
    *, policy_id: str, run_scope_id: str, frozen_at: str
) -> dict[str, Any]:
    """Freeze the separation between missing facts and bounded judgement."""

    try:
        document = {
            "schema_id": POLICY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "policy_id": text(policy_id, "V32_UNKNOWN_POLICY_ID_INVALID"),
            "run_scope_id": text(
                run_scope_id, "V32_UNKNOWN_POLICY_RUN_SCOPE_INVALID"
            ),
            "frozen_at": time(frozen_at, "V32_UNKNOWN_POLICY_TIME_INVALID"),
            "objective_missing_value_status": "UNKNOWN",
            "objective_zero_imputation_allowed": False,
            "subjective_assessment_may_replace_objective_unknown": False,
            "current_pit_registry_resolution_required": True,
            "evidence_available_before_assessment_required": True,
            "directional_assessment_requires_opposite_branch": True,
            "falsifier_and_expiry_required": True,
            "dependency_group_required": True,
            "no_evidence_rule": (
                "UNKNOWN_DIRECTION_EXTREME_UNCERTAINTY_ZERO_RISK"
            ),
            "subjective_tier_scale": (
                "EXTREME_UNCERTAINTY_LOW_HIGH_UNCALIBRATED_ORDINAL"
            ),
            "max_subjective_assessment_ttl_seconds": (
                MAX_SUBJECTIVE_ASSESSMENT_TTL_SECONDS
            ),
            "probability_calibration_claim_allowed": False,
            "causal_fact_claim_allowed": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        raise V32UnknownAssessmentError("V32_UNKNOWN_POLICY_INPUT_INVALID") from exc
    return self_digest(document, POLICY_DIGEST_FIELD)


def verify_v32_unknown_subjective_policy_v1(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, POLICY_DIGEST_FIELD)
        verify_boundary(document, "V32_UNKNOWN_POLICY_BOUNDARY_INVALID")
        rebuilt = build_v32_unknown_subjective_policy_v1(
            policy_id=document["policy_id"],
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32UnknownAssessmentError):
            raise
        raise V32UnknownAssessmentError("V32_UNKNOWN_POLICY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[POLICY_DIGEST_FIELD]:
        raise V32UnknownAssessmentError("V32_UNKNOWN_POLICY_REPLAY_MISMATCH")
    return supplied


def _registry_rows(value: Any, *, branch: bool) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID")
    if len(value) > 256:
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID")
    expected = {
        "reference_id",
        "semantic_digest",
        "available_at",
        "dependency_group",
        "direction",
    }
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != expected:
            raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID")
        direction = text(item["direction"], "V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID")
        allowed = {"LONG", "SHORT", "NEUTRAL", "MIXED"} if branch else DIRECTIONAL_VIEWS
        if direction not in allowed:
            raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID")
        rows.append(
            {
                "reference_id": text(
                    item["reference_id"], "V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID"
                ),
                "semantic_digest": digest(
                    item["semantic_digest"],
                    "V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID",
                ),
                "available_at": time(
                    item["available_at"], "V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID"
                ),
                "dependency_group": text(
                    item["dependency_group"],
                    "V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_INVALID",
                ),
                "direction": direction,
            }
        )
    rows.sort(key=lambda row: row["reference_id"])
    if len({row["reference_id"] for row in rows}) != len(rows):
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_ROW_DUPLICATE")
    return rows


def build_v32_unknown_assessment_evidence_registry_v1(
    *,
    registry_id: str,
    pit_evidence_registry: Mapping[str, Any],
    pit_evidence_registry_binding: Mapping[str, Any],
    pit_evidence_availability_registry: Mapping[str, Any],
    pit_evidence_availability_registry_binding: Mapping[str, Any],
    registered_mechanisms: Sequence[Mapping[str, Any]],
    registered_opposite_branches: Sequence[Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    pit_digest = verify_v32_pit_evidence_registry(pit_evidence_registry)
    availability_digest, available_by_ref = _availability_registry(
        pit_evidence_availability_registry
    )
    try:
        pit_ref = binding(
            pit_evidence_registry_binding, "V32_UNKNOWN_EVIDENCE_PIT_BINDING_INVALID"
        )
        availability_ref = binding(
            pit_evidence_availability_registry_binding,
            "V32_UNKNOWN_EVIDENCE_AVAILABILITY_BINDING_INVALID",
        )
        if (
            pit_ref["semantic_digest"] != pit_digest
            or pit_ref["physical_sha256"] != _physical(pit_evidence_registry)
            or availability_ref["semantic_digest"] != availability_digest
            or availability_ref["physical_sha256"]
            != _physical(pit_evidence_availability_registry)
            or pit_evidence_availability_registry.get("pit_evidence_registry_digest")
            != pit_digest
            or pit_evidence_availability_registry.get("run_id")
            != pit_evidence_registry.get("run_id")
            or pit_evidence_availability_registry.get("cycle_index")
            != pit_evidence_registry.get("cycle_index")
            or set(available_by_ref) != set(pit_evidence_registry.get("members", ()))
        ):
            raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_PIT_CROSS_BINDING_INVALID")
        mechanisms = _registry_rows(registered_mechanisms, branch=False)
        branches = _registry_rows(registered_opposite_branches, branch=True)
        as_of = time(pit_evidence_registry["as_of"], "V32_UNKNOWN_EVIDENCE_TIME_INVALID")
        created = time(created_at, "V32_UNKNOWN_EVIDENCE_TIME_INVALID")
        if moment(created, "V32_UNKNOWN_EVIDENCE_TIME_INVALID") < moment(
            as_of, "V32_UNKNOWN_EVIDENCE_TIME_INVALID"
        ) or any(
            moment(row["available_at"], "V32_UNKNOWN_EVIDENCE_TIME_INVALID")
            > moment(as_of, "V32_UNKNOWN_EVIDENCE_TIME_INVALID")
            for row in [*mechanisms, *branches]
        ):
            raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_TIME_INVALID")
        pit_rows = [
            {
                "reference_id": reference,
                "semantic_digest": reference,
                "available_at": available_by_ref[reference],
                "dependency_group": f"pit:{reference}",
                "direction": "UNKNOWN",
            }
            for reference in sorted(available_by_ref)
        ]
        document = {
            "schema_id": EVIDENCE_REGISTRY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "registry_id": text(registry_id, "V32_UNKNOWN_EVIDENCE_REGISTRY_ID_INVALID"),
            "run_id": pit_evidence_registry["run_id"],
            "cycle_index": pit_evidence_registry["cycle_index"],
            "as_of": as_of,
            "created_at": created,
            "pit_evidence_registry_binding": pit_ref,
            "pit_evidence_availability_registry_binding": availability_ref,
            "pit_facts": pit_rows,
            "registered_mechanisms": mechanisms,
            "registered_opposite_branches": branches,
            "current_cycle_only": True,
            "available_at_not_after_as_of": True,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32UnknownAssessmentError):
            raise
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_INPUT_INVALID") from exc
    return self_digest(document, EVIDENCE_REGISTRY_DIGEST_FIELD)


def verify_v32_unknown_assessment_evidence_registry_v1(
    document: Mapping[str, Any],
    *,
    pit_evidence_registry: Mapping[str, Any],
    pit_evidence_availability_registry: Mapping[str, Any],
) -> str:
    try:
        supplied = verify_self_digest(document, EVIDENCE_REGISTRY_DIGEST_FIELD)
        verify_boundary(document, "V32_UNKNOWN_EVIDENCE_REGISTRY_BOUNDARY_INVALID")
        rebuilt = build_v32_unknown_assessment_evidence_registry_v1(
            registry_id=document["registry_id"],
            pit_evidence_registry=pit_evidence_registry,
            pit_evidence_registry_binding=document["pit_evidence_registry_binding"],
            pit_evidence_availability_registry=pit_evidence_availability_registry,
            pit_evidence_availability_registry_binding=document[
                "pit_evidence_availability_registry_binding"
            ],
            registered_mechanisms=document["registered_mechanisms"],
            registered_opposite_branches=document["registered_opposite_branches"],
            created_at=document["created_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32UnknownAssessmentError):
            raise
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[EVIDENCE_REGISTRY_DIGEST_FIELD]:
        raise V32UnknownAssessmentError("V32_UNKNOWN_EVIDENCE_REGISTRY_REPLAY_MISMATCH")
    return supplied


def _opposes(direction: str, branch_direction: str) -> bool:
    if direction == "LONG":
        return branch_direction == "SHORT"
    if direction == "SHORT":
        return branch_direction == "LONG"
    return branch_direction in {"LONG", "SHORT"}


def build_v32_unknown_subjective_assessment_v1(
    *,
    assessment_id: str,
    objective_unknown: Mapping[str, Any],
    objective_unknown_binding: Mapping[str, Any],
    evidence_registry: Mapping[str, Any],
    evidence_registry_binding: Mapping[str, Any],
    assessed_at: str,
    expires_at: str,
    evidence_reference_ids: Sequence[str],
    rationale: str,
    opposite_branch_id: str | None,
    opposite_interpretation: str,
    falsifier: str,
    dependency_group: str,
    directional_view: str,
    subjective_plausibility_tier: str,
) -> dict[str, Any]:
    objective_digest = verify_v32_objective_unknown_v1(objective_unknown)
    try:
        objective_ref = binding(
            objective_unknown_binding, "V32_UNKNOWN_ASSESSMENT_OBJECTIVE_BINDING_INVALID"
        )
        registry_ref = binding(
            evidence_registry_binding, "V32_UNKNOWN_ASSESSMENT_REGISTRY_BINDING_INVALID"
        )
        registry_digest = verify_self_digest(
            evidence_registry, EVIDENCE_REGISTRY_DIGEST_FIELD
        )
        if (
            objective_ref["semantic_digest"] != objective_digest
            or objective_ref["physical_sha256"] != _physical(objective_unknown)
            or registry_ref["semantic_digest"] != registry_digest
            or registry_ref["physical_sha256"] != _physical(evidence_registry)
            or evidence_registry.get("run_id") != objective_unknown["run_id"]
            or evidence_registry.get("cycle_index") != objective_unknown["cycle_index"]
        ):
            raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_CROSS_BINDING_INVALID")
        assessed = time(assessed_at, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
        expires = time(expires_at, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
        if (
            moment(assessed, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            < moment(objective_unknown["detected_at"], "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            or moment(assessed, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            < moment(evidence_registry["as_of"], "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            or moment(expires, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            <= moment(assessed, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            or moment(expires, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            - moment(assessed, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            > timedelta(seconds=MAX_SUBJECTIVE_ASSESSMENT_TTL_SECONDS)
        ):
            raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
        reference_ids = sorted_unique_texts(
            evidence_reference_ids,
            "V32_UNKNOWN_ASSESSMENT_REFERENCE_SET_INVALID",
            allow_empty=True,
            maximum=64,
        )
        pit = {f"PIT:{row['reference_id']}": row for row in evidence_registry["pit_facts"]}
        mechanisms = {
            f"MECHANISM:{row['reference_id']}": row
            for row in evidence_registry["registered_mechanisms"]
        }
        lookup = {**pit, **mechanisms}
        if any(reference_id not in lookup for reference_id in reference_ids):
            raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_REFERENCE_NOT_REGISTERED")
        resolved = [
            {
                "reference_id": reference_id,
                "reference_type": (
                    "CURRENT_PIT_FACT"
                    if reference_id.startswith("PIT:")
                    else "REGISTERED_MECHANISM"
                ),
                **lookup[reference_id],
            }
            for reference_id in reference_ids
        ]
        if any(
            moment(row["available_at"], "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            > moment(assessed, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
            for row in resolved
        ):
            raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_FUTURE_REFERENCE")
        direction = text(directional_view, "V32_UNKNOWN_ASSESSMENT_DIRECTION_INVALID")
        if direction not in DIRECTIONAL_VIEWS:
            raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_DIRECTION_INVALID")
        tier = text(
            subjective_plausibility_tier,
            "V32_UNKNOWN_ASSESSMENT_TIER_INVALID",
        )
        if tier not in SUBJECTIVE_PLAUSIBILITY_TIERS:
            raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_TIER_INVALID")
        evidence_bound = bool(resolved)
        branches = {
            row["reference_id"]: row
            for row in evidence_registry["registered_opposite_branches"]
        }
        opposite = None if opposite_branch_id is None else branches.get(opposite_branch_id)
        dependency = text(
            dependency_group, "V32_UNKNOWN_ASSESSMENT_DEPENDENCY_INVALID"
        )
        if evidence_bound:
            if (
                opposite is None
                or not _opposes(direction, opposite["direction"])
                or moment(opposite["available_at"], "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
                > moment(assessed, "V32_UNKNOWN_ASSESSMENT_TIME_INVALID")
                or dependency
                not in {row["dependency_group"] for row in [*resolved, opposite]}
            ):
                raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_OPPOSITE_BRANCH_INVALID")
        elif (
            tier != "EXTREME_UNCERTAINTY"
            or direction != "UNKNOWN"
            or opposite_branch_id is not None
        ):
            raise V32UnknownAssessmentError(
                "V32_UNKNOWN_ASSESSMENT_UNSUPPORTED_DIRECTION_FORBIDDEN"
            )
        document = {
            "schema_id": ASSESSMENT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "assessment_id": text(assessment_id, "V32_UNKNOWN_ASSESSMENT_ID_INVALID"),
            "run_id": objective_unknown["run_id"],
            "cycle_index": objective_unknown["cycle_index"],
            "objective_unknown_binding": objective_ref,
            "evidence_registry_binding": registry_ref,
            "objective_status_before_assessment": "UNKNOWN",
            "objective_status_after_assessment": "UNKNOWN",
            "objective_value_after_assessment": None,
            "assessment_status": (
                "EVIDENCE_BOUND_SUBJECTIVE_ASSESSMENT"
                if evidence_bound
                else "NO_EVIDENCE_REMAINS_UNKNOWN_EXTREME_UNCERTAINTY"
            ),
            "assessed_at": assessed,
            "expires_at": expires,
            "max_ttl_seconds": MAX_SUBJECTIVE_ASSESSMENT_TTL_SECONDS,
            "evidence_reference_ids": reference_ids,
            "resolved_evidence_references": resolved,
            "rationale": text(rationale, "V32_UNKNOWN_ASSESSMENT_RATIONALE_INVALID"),
            "opposite_branch": opposite,
            "opposite_interpretation": text(
                opposite_interpretation, "V32_UNKNOWN_ASSESSMENT_OPPOSITE_INVALID"
            ),
            "falsifier": text(falsifier, "V32_UNKNOWN_ASSESSMENT_FALSIFIER_INVALID"),
            "dependency_group": dependency,
            "directional_view": direction,
            "subjective_plausibility_tier": tier,
            "subjective_plausibility_tier_type": (
                "SUBJECTIVE_UNCALIBRATED_ORDINAL_THREE_TIER"
            ),
            "observed_value_claim": False,
            "calibrated_probability_claim": False,
            "causal_fact_claim": False,
            "may_replace_objective_unknown": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32UnknownAssessmentError):
            raise
        raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_INPUT_INVALID") from exc
    return self_digest(document, ASSESSMENT_DIGEST_FIELD)


def verify_v32_unknown_subjective_assessment_v1(
    document: Mapping[str, Any],
    *,
    objective_unknown: Mapping[str, Any],
    evidence_registry: Mapping[str, Any],
) -> str:
    try:
        supplied = verify_self_digest(document, ASSESSMENT_DIGEST_FIELD)
        verify_boundary(document, "V32_UNKNOWN_ASSESSMENT_BOUNDARY_INVALID")
        rebuilt = build_v32_unknown_subjective_assessment_v1(
            assessment_id=document["assessment_id"],
            objective_unknown=objective_unknown,
            objective_unknown_binding=document["objective_unknown_binding"],
            evidence_registry=evidence_registry,
            evidence_registry_binding=document["evidence_registry_binding"],
            assessed_at=document["assessed_at"],
            expires_at=document["expires_at"],
            evidence_reference_ids=document["evidence_reference_ids"],
            rationale=document["rationale"],
            opposite_branch_id=(
                None
                if document["opposite_branch"] is None
                else document["opposite_branch"]["reference_id"]
            ),
            opposite_interpretation=document["opposite_interpretation"],
            falsifier=document["falsifier"],
            dependency_group=document["dependency_group"],
            directional_view=document["directional_view"],
            subjective_plausibility_tier=document["subjective_plausibility_tier"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32UnknownAssessmentError):
            raise
        raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[ASSESSMENT_DIGEST_FIELD]:
        raise V32UnknownAssessmentError("V32_UNKNOWN_ASSESSMENT_REPLAY_MISMATCH")
    return supplied


__all__ = [
    "ASSESSMENT_DIGEST_FIELD",
    "ASSESSMENT_SCHEMA_ID",
    "DIRECTIONAL_VIEWS",
    "EVIDENCE_REGISTRY_DIGEST_FIELD",
    "EVIDENCE_REGISTRY_SCHEMA_ID",
    "MAX_SUBJECTIVE_ASSESSMENT_TTL_SECONDS",
    "OBJECTIVE_DIGEST_FIELD",
    "OBJECTIVE_SCHEMA_ID",
    "POLICY_DIGEST_FIELD",
    "POLICY_SCHEMA_ID",
    "V32UnknownAssessmentError",
    "build_v32_objective_unknown_v1",
    "build_v32_unknown_subjective_policy_v1",
    "build_v32_unknown_assessment_evidence_registry_v1",
    "build_v32_unknown_subjective_assessment_v1",
    "verify_v32_objective_unknown_v1",
    "verify_v32_unknown_subjective_policy_v1",
    "verify_v32_unknown_assessment_evidence_registry_v1",
    "verify_v32_unknown_subjective_assessment_v1",
]
