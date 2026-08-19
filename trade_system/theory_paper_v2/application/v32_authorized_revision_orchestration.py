"""Application orchestration for the authorized 2026-08-08 V3.2 revisions.

The use cases coordinate pure Domain contracts and an injected durability port.
They do not know filesystem paths, call networks, invoke Agents, or create
authority/qualification/run state.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Protocol, Sequence

from ..domain.contracts.canonical import canonical_bytes, canonical_digest, self_digest, verify_self_digest
from ..domain.v32_authorized_revision_common import (
    SCHEMA_VERSION,
    V32AuthorizedRevisionContractError,
    binding,
    boundary,
    digest,
    integer,
    moment,
    text,
    time,
    verify_boundary,
)
from ..domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD,
    MANIFEST_SCHEMA_ID,
    POLICY_DIGEST_FIELD as CONTEXT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as CONTEXT_POLICY_SCHEMA_ID,
    SELECTION_DIGEST_FIELD,
    SELECTION_SCHEMA_ID,
    SHARD_DIGEST_FIELD as CONTEXT_SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID as CONTEXT_SHARD_SCHEMA_ID,
    build_v32_context_compaction_bundle_v1,
    build_v32_context_shard_selection_v1,
    verify_v32_context_compaction_bundle_v1,
    verify_v32_context_compaction_policy_v1,
    verify_v32_context_shard_selection_v1,
)
from ..domain.v32_cycle_audit_narrative import (
    POLICY_DIGEST_FIELD as AUDIT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as AUDIT_POLICY_SCHEMA_ID,
    build_v32_cycle_audit_narrative_bundle_v1,
    verify_v32_cycle_audit_policy_v1,
)
from ..domain.v32_cycle_source_admission import (
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
)
from ..domain.v32_data_gap_escalation import (
    ESCALATION_DIGEST_FIELD,
    ESCALATION_SCHEMA_ID,
    MANUAL_REVISION_DIGEST_FIELD,
    MANUAL_REVISION_SCHEMA_ID,
    POLICY_DIGEST_FIELD as DATA_GAP_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as DATA_GAP_POLICY_SCHEMA_ID,
    build_v32_data_gap_escalation_v1,
    build_v32_manual_public_evidence_revision_v1,
    verify_v32_data_gap_escalation_v1,
    verify_v32_data_gap_manual_policy_v1,
    verify_v32_manual_public_evidence_revision_v1,
)
from ..domain.v32_environment_capability import (
    CAPABILITY_CATEGORIES,
    DIGEST_FIELD as ENVIRONMENT_DIGEST_FIELD,
    SCHEMA_ID as ENVIRONMENT_SCHEMA_ID,
    build_v32_environment_capability_profile_v1,
    verify_v32_environment_capability_profile_v1,
)
from ..domain.v32_recovery_supervision import (
    DISPOSITIONS,
    OBSERVATION_DIGEST_FIELD,
    OBSERVATION_SCHEMA_ID,
    POLICY_DIGEST_FIELD as RECOVERY_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as RECOVERY_POLICY_SCHEMA_ID,
    RECOVERY_DIGEST_FIELD,
    RECOVERY_SCHEMA_ID,
    verify_v32_deterministic_recovery_receipt_v1,
    verify_v32_recovery_supervision_policy_v1,
    verify_v32_supervisor_observation_v1,
)
from ..domain.v32_unknown_assessment import (
    ASSESSMENT_DIGEST_FIELD,
    ASSESSMENT_SCHEMA_ID,
    EVIDENCE_REGISTRY_DIGEST_FIELD,
    EVIDENCE_REGISTRY_SCHEMA_ID,
    OBJECTIVE_DIGEST_FIELD,
    OBJECTIVE_SCHEMA_ID,
    PIT_AVAILABILITY_DIGEST_FIELD,
    PIT_AVAILABILITY_SCHEMA_ID,
    POLICY_DIGEST_FIELD as UNKNOWN_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as UNKNOWN_POLICY_SCHEMA_ID,
    build_v32_objective_unknown_v1,
    build_v32_unknown_assessment_evidence_registry_v1,
    build_v32_unknown_subjective_assessment_v1,
    verify_v32_objective_unknown_v1,
    verify_v32_unknown_assessment_evidence_registry_v1,
    verify_v32_unknown_subjective_assessment_v1,
    verify_v32_unknown_subjective_policy_v1,
)
from ..domain.v32_dynamic_research import SUBJECTIVE_PLAUSIBILITY_TIERS


SUPPORT_BUNDLE_SCHEMA_ID = "theory_paper_v32_authorized_revision_support_bundle_v1"
SUPPORT_BUNDLE_DIGEST_FIELD = "authorized_revision_support_bundle_digest"
CYCLE_REGISTRY_SCHEMA_ID = "theory_paper_v32_authorized_revision_cycle_registry_v1"
CYCLE_REGISTRY_DIGEST_FIELD = "authorized_revision_cycle_registry_digest"
CYCLE_REGISTRY_SCHEMA_VERSION_V1 = SCHEMA_VERSION
CYCLE_REGISTRY_SCHEMA_VERSION_V2 = "2.0.0"
REVISION_INPUT_STATE_SCHEMA_ID = "theory_paper_v32_revision_input_state_v1"
REVISION_INPUT_STATE_DIGEST_FIELD = "revision_input_state_digest"
REVISION_INPUT_STATES = frozenset(
    {"PRESENT", "NO_REVISION_INPUT", "UNKNOWN_READER_UNAVAILABLE"}
)
_REVISION_READER_BINDING_FIELDS = frozenset(
    {"reader_id", "reader_version", "reader_kind", "configuration_digest"}
)


class V32AuthorizedRevisionOrchestrationError(ValueError):
    """An aggregate admitted an unverified, misbound, or cross-cycle artifact."""


def _revision_reader_binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _REVISION_READER_BINDING_FIELDS:
        raise V32AuthorizedRevisionOrchestrationError(code)
    normalized = {
        "reader_id": text(value["reader_id"], code),
        "reader_version": text(value["reader_version"], code),
        "reader_kind": text(value["reader_kind"], code),
        "configuration_digest": digest(value["configuration_digest"], code),
    }
    if normalized["reader_version"] != SCHEMA_VERSION:
        raise V32AuthorizedRevisionOrchestrationError(code)
    return normalized


def build_v32_revision_input_state_v1(
    *,
    run_id: str,
    cycle_index: int,
    state: str,
    observed_at: str,
    reason: str,
    reader_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the explicit result of one local revision-material read.

    This state distinguishes an observed absence from an unavailable reader.
    It is not a revision item and cannot zero-impute a missing observation.
    """

    status = text(state, "V32_REVISION_INPUT_STATE_STATUS_INVALID")
    if status not in REVISION_INPUT_STATES:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_INPUT_STATE_STATUS_INVALID"
        )
    document = {
        "schema_id": REVISION_INPUT_STATE_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": text(run_id, "V32_REVISION_INPUT_STATE_RUN_INVALID"),
        "cycle_index": integer(
            cycle_index,
            "V32_REVISION_INPUT_STATE_CYCLE_INVALID",
            minimum=1,
            maximum=16,
        ),
        "state": status,
        "observed_at": time(
            observed_at, "V32_REVISION_INPUT_STATE_OBSERVED_AT_INVALID"
        ),
        "reason": text(reason, "V32_REVISION_INPUT_STATE_REASON_INVALID"),
        "zero_imputed": False,
        "reader_binding": _revision_reader_binding(
            reader_binding, "V32_REVISION_INPUT_STATE_READER_BINDING_INVALID"
        ),
        **boundary(),
    }
    return self_digest(document, REVISION_INPUT_STATE_DIGEST_FIELD)


_REVISION_INPUT_STATE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "state",
        "observed_at",
        "reason",
        "zero_imputed",
        "reader_binding",
        *boundary().keys(),
        REVISION_INPUT_STATE_DIGEST_FIELD,
    }
)


def verify_v32_revision_input_state_v1(
    document: Mapping[str, Any],
    *,
    expected_run_id: str | None = None,
    expected_cycle_index: int | None = None,
    expected_observed_at: str | None = None,
    expected_reader_binding: Mapping[str, Any] | None = None,
) -> str:
    code = "V32_REVISION_INPUT_STATE_INVALID"
    try:
        if not isinstance(document, Mapping) or set(document) != _REVISION_INPUT_STATE_FIELDS:
            raise V32AuthorizedRevisionOrchestrationError(code)
        supplied = verify_self_digest(document, REVISION_INPUT_STATE_DIGEST_FIELD)
        verify_boundary(document, code)
        run = text(document["run_id"], code)
        cycle = integer(document["cycle_index"], code, minimum=1, maximum=16)
        observed = time(document["observed_at"], code)
        status = text(document["state"], code)
        reader = _revision_reader_binding(document["reader_binding"], code)
        text(document["reason"], code)
        if (
            document["schema_id"] != REVISION_INPUT_STATE_SCHEMA_ID
            or document["schema_version"] != SCHEMA_VERSION
            or status not in REVISION_INPUT_STATES
            or document["zero_imputed"] is not False
            or (expected_run_id is not None and run != expected_run_id)
            or (expected_cycle_index is not None and cycle != expected_cycle_index)
            or (expected_observed_at is not None and observed != time(expected_observed_at, code))
            or (
                expected_reader_binding is not None
                and reader != _revision_reader_binding(expected_reader_binding, code)
            )
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizedRevisionOrchestrationError):
            raise
        raise V32AuthorizedRevisionOrchestrationError(code) from exc
    return supplied


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _checked_binding(
    document: Mapping[str, Any],
    value: Mapping[str, Any],
    *,
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
    code: str,
) -> dict[str, str]:
    try:
        normalized = binding(value, code)
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(code) from exc
    if (
        normalized["schema_id"] != schema_id
        or normalized["digest_field"] != digest_field
        or normalized["semantic_digest"] != semantic_digest
        or normalized["physical_sha256"] != _physical(document)
    ):
        raise V32AuthorizedRevisionOrchestrationError(code)
    return normalized


def _not_after(value: Any, ceiling: str, code: str) -> None:
    try:
        if moment(value, code) > moment(ceiling, code):
            raise V32AuthorizedRevisionOrchestrationError(code)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizedRevisionOrchestrationError):
            raise
        raise V32AuthorizedRevisionOrchestrationError(code) from exc


class V32AuthorizedRevisionStorePort(Protocol):
    def persist_document(
        self, *, role: str, document: Mapping[str, Any]
    ) -> Mapping[str, str]: ...

    def persist_context_bundle(
        self,
        *,
        manifest: Mapping[str, Any],
        shards: Sequence[Mapping[str, Any]],
        original_documents: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...

    def persist_audit_bundle(
        self,
        *,
        directory: Mapping[str, Any],
        shards: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...


def compact_and_select_v32_agent_context_v1(
    *,
    store: V32AuthorizedRevisionStorePort,
    run_id: str,
    cycle_index: int,
    created_at: str,
    selected_at: str,
    source_artifacts: Sequence[Mapping[str, Any]],
    original_documents: Sequence[Mapping[str, Any]],
    caller_required_member_ids: Sequence[str],
    max_shard_canonical_bytes: int,
    max_manifest_canonical_bytes: int,
    max_agent_context_canonical_bytes: int,
) -> Mapping[str, Any]:
    bundle = build_v32_context_compaction_bundle_v1(
        run_id=run_id,
        cycle_index=cycle_index,
        created_at=created_at,
        source_artifacts=source_artifacts,
        original_documents=original_documents,
        max_shard_canonical_bytes=max_shard_canonical_bytes,
        max_manifest_canonical_bytes=max_manifest_canonical_bytes,
    )
    persisted = store.persist_context_bundle(
        manifest=bundle["manifest"],
        shards=bundle["shards"],
        original_documents=original_documents,
    )
    selection = build_v32_context_shard_selection_v1(
        manifest=bundle["manifest"],
        manifest_binding=persisted["manifest_binding"],
        shards=bundle["shards"],
        original_documents=original_documents,
        caller_required_member_ids=caller_required_member_ids,
        selected_at=selected_at,
        max_agent_context_canonical_bytes=max_agent_context_canonical_bytes,
        shard_bindings=persisted["shard_bindings"],
    )
    selection_binding = store.persist_document(
        role="context_shard_selection", document=selection
    )
    return {
        **bundle,
        **dict(persisted),
        "original_documents": [dict(document) for document in original_documents],
        "selection": selection,
        "selection_binding": dict(selection_binding),
    }


def compose_v32_unknown_dual_track_v1(
    *,
    store: V32AuthorizedRevisionStorePort,
    objective_unknown_args: Mapping[str, Any],
    pit_evidence_registry: Mapping[str, Any],
    pit_evidence_registry_binding: Mapping[str, Any],
    pit_evidence_availability_registry: Mapping[str, Any],
    pit_evidence_availability_registry_binding: Mapping[str, Any],
    registry_id: str,
    registered_mechanisms: Sequence[Mapping[str, Any]],
    registered_opposite_branches: Sequence[Mapping[str, Any]],
    registry_created_at: str,
    assessment_args: Mapping[str, Any],
) -> Mapping[str, Any]:
    objective = build_v32_objective_unknown_v1(**dict(objective_unknown_args))
    objective_binding = store.persist_document(
        role="objective_unknown", document=objective
    )
    registry = build_v32_unknown_assessment_evidence_registry_v1(
        registry_id=registry_id,
        pit_evidence_registry=pit_evidence_registry,
        pit_evidence_registry_binding=pit_evidence_registry_binding,
        pit_evidence_availability_registry=pit_evidence_availability_registry,
        pit_evidence_availability_registry_binding=(
            pit_evidence_availability_registry_binding
        ),
        registered_mechanisms=registered_mechanisms,
        registered_opposite_branches=registered_opposite_branches,
        created_at=registry_created_at,
    )
    registry_binding = store.persist_document(
        role="unknown_evidence_registry", document=registry
    )
    assessment = build_v32_unknown_subjective_assessment_v1(
        objective_unknown=objective,
        objective_unknown_binding=objective_binding,
        evidence_registry=registry,
        evidence_registry_binding=registry_binding,
        **dict(assessment_args),
    )
    assessment_binding = store.persist_document(
        role="unknown_subjective_assessment", document=assessment
    )
    return {
        "objective_unknown": objective,
        "objective_unknown_binding": dict(objective_binding),
        "evidence_registry": registry,
        "evidence_registry_binding": dict(registry_binding),
        "subjective_assessment": assessment,
        "subjective_assessment_binding": dict(assessment_binding),
    }


def compose_v32_data_gap_escalation_v1(
    *, store: V32AuthorizedRevisionStorePort, escalation_args: Mapping[str, Any]
) -> Mapping[str, Any]:
    escalation = build_v32_data_gap_escalation_v1(**dict(escalation_args))
    escalation_binding = store.persist_document(
        role="data_gap_escalation", document=escalation
    )
    return {
        "data_gap_escalation": escalation,
        "data_gap_escalation_binding": dict(escalation_binding),
    }


def admit_v32_manual_public_evidence_revision_v1(
    *,
    store: V32AuthorizedRevisionStorePort,
    escalation: Mapping[str, Any],
    escalation_binding: Mapping[str, Any],
    revision_args: Mapping[str, Any],
) -> Mapping[str, Any]:
    revision = build_v32_manual_public_evidence_revision_v1(
        escalation=escalation,
        escalation_binding=escalation_binding,
        **dict(revision_args),
    )
    revision_binding = store.persist_document(
        role="manual_public_evidence_revision", document=revision
    )
    return {
        "manual_public_evidence_revision": revision,
        "manual_public_evidence_revision_binding": dict(revision_binding),
    }


def freeze_v32_environment_capability_profile_v1(
    *, store: V32AuthorizedRevisionStorePort, profile_args: Mapping[str, Any]
) -> Mapping[str, Any]:
    profile = build_v32_environment_capability_profile_v1(**dict(profile_args))
    profile_binding = store.persist_document(
        role="environment_capability_profile", document=profile
    )
    return {
        "environment_capability_profile": profile,
        "environment_capability_profile_binding": dict(profile_binding),
    }


def compose_v32_cycle_audit_narrative_v1(
    *, store: V32AuthorizedRevisionStorePort, narrative_args: Mapping[str, Any]
) -> Mapping[str, Any]:
    bundle = build_v32_cycle_audit_narrative_bundle_v1(**dict(narrative_args))
    persisted = store.persist_audit_bundle(
        directory=bundle["directory"], shards=bundle["shards"]
    )
    return {**bundle, **dict(persisted)}


def build_v32_authorized_revision_support_bundle_v1(
    *,
    support_bundle_id: str,
    run_scope_id: str,
    frozen_at: str,
    context_compaction_policy: Mapping[str, Any],
    context_compaction_policy_binding: Mapping[str, Any],
    unknown_subjective_policy: Mapping[str, Any],
    unknown_subjective_policy_binding: Mapping[str, Any],
    data_gap_manual_policy: Mapping[str, Any],
    data_gap_manual_policy_binding: Mapping[str, Any],
    cycle_audit_policy: Mapping[str, Any],
    cycle_audit_policy_binding: Mapping[str, Any],
    environment_capability_profile: Mapping[str, Any],
    environment_capability_profile_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the one digest that binds all authorized revision support rules."""

    try:
        support_scope = text(
            run_scope_id, "V32_REVISION_SUPPORT_RUN_SCOPE_INVALID"
        )
        support_time = time(frozen_at, "V32_REVISION_SUPPORT_TIME_INVALID")
        component_specs = (
            (
                "context_compaction_policy",
                context_compaction_policy,
                context_compaction_policy_binding,
                CONTEXT_POLICY_SCHEMA_ID,
                CONTEXT_POLICY_DIGEST_FIELD,
                verify_v32_context_compaction_policy_v1(
                    context_compaction_policy
                ),
            ),
            (
                "unknown_subjective_policy",
                unknown_subjective_policy,
                unknown_subjective_policy_binding,
                UNKNOWN_POLICY_SCHEMA_ID,
                UNKNOWN_POLICY_DIGEST_FIELD,
                verify_v32_unknown_subjective_policy_v1(
                    unknown_subjective_policy
                ),
            ),
            (
                "data_gap_manual_policy",
                data_gap_manual_policy,
                data_gap_manual_policy_binding,
                DATA_GAP_POLICY_SCHEMA_ID,
                DATA_GAP_POLICY_DIGEST_FIELD,
                verify_v32_data_gap_manual_policy_v1(data_gap_manual_policy),
            ),
            (
                "cycle_audit_policy",
                cycle_audit_policy,
                cycle_audit_policy_binding,
                AUDIT_POLICY_SCHEMA_ID,
                AUDIT_POLICY_DIGEST_FIELD,
                verify_v32_cycle_audit_policy_v1(cycle_audit_policy),
            ),
            (
                "environment_capability_profile",
                environment_capability_profile,
                environment_capability_profile_binding,
                ENVIRONMENT_SCHEMA_ID,
                ENVIRONMENT_DIGEST_FIELD,
                verify_v32_environment_capability_profile_v1(
                    environment_capability_profile
                ),
            ),
        )
        components: list[dict[str, Any]] = []
        for role, document, supplied_binding, schema_id, digest_field, value_digest in component_specs:
            if document.get("run_scope_id") != support_scope:
                raise V32AuthorizedRevisionOrchestrationError(
                    "V32_REVISION_SUPPORT_SCOPE_MISMATCH"
                )
            _not_after(
                document.get("frozen_at"),
                support_time,
                "V32_REVISION_SUPPORT_TIME_MISMATCH",
            )
            components.append(
                {
                    "role": role,
                    "binding": _checked_binding(
                        document,
                        supplied_binding,
                        schema_id=schema_id,
                        digest_field=digest_field,
                        semantic_digest=value_digest,
                        code="V32_REVISION_SUPPORT_BINDING_INVALID",
                    ),
                }
            )
        document = {
            "schema_id": SUPPORT_BUNDLE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "support_bundle_id": text(
                support_bundle_id, "V32_REVISION_SUPPORT_ID_INVALID"
            ),
            "run_scope_id": support_scope,
            "frozen_at": support_time,
            "components": components,
            "component_count": 5,
            "component_semantic_digests": [
                row["binding"]["semantic_digest"] for row in components
            ],
            "all_components_verified_by_owning_contract": True,
            "single_support_digest_for_contract_and_q_gate": True,
            "recovery_and_workspace_policies_included": False,
            "recovery_and_workspace_policy_owner": "OUTSIDE_THIS_SUPPORT_BUNDLE",
            "support_bundle_is_authority": False,
            "support_bundle_is_qualification": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizedRevisionOrchestrationError):
            raise
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_SUPPORT_INPUT_INVALID"
        ) from exc
    return self_digest(document, SUPPORT_BUNDLE_DIGEST_FIELD)


def verify_v32_authorized_revision_support_bundle_v1(
    document: Mapping[str, Any],
    *,
    context_compaction_policy: Mapping[str, Any],
    unknown_subjective_policy: Mapping[str, Any],
    data_gap_manual_policy: Mapping[str, Any],
    cycle_audit_policy: Mapping[str, Any],
    environment_capability_profile: Mapping[str, Any],
) -> str:
    try:
        supplied = verify_self_digest(document, SUPPORT_BUNDLE_DIGEST_FIELD)
        verify_boundary(document, "V32_REVISION_SUPPORT_BOUNDARY_INVALID")
        component_rows = document["components"]
        if not isinstance(component_rows, list) or len(component_rows) != 5:
            raise V32AuthorizedRevisionOrchestrationError(
                "V32_REVISION_SUPPORT_COMPONENT_SET_INVALID"
            )
        by_role = {
            row["role"]: row["binding"]
            for row in component_rows
            if isinstance(row, Mapping) and set(row) == {"role", "binding"}
        }
        if len(by_role) != 5:
            raise V32AuthorizedRevisionOrchestrationError(
                "V32_REVISION_SUPPORT_COMPONENT_SET_INVALID"
            )
        rebuilt = build_v32_authorized_revision_support_bundle_v1(
            support_bundle_id=document["support_bundle_id"],
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
            context_compaction_policy=context_compaction_policy,
            context_compaction_policy_binding=by_role[
                "context_compaction_policy"
            ],
            unknown_subjective_policy=unknown_subjective_policy,
            unknown_subjective_policy_binding=by_role[
                "unknown_subjective_policy"
            ],
            data_gap_manual_policy=data_gap_manual_policy,
            data_gap_manual_policy_binding=by_role["data_gap_manual_policy"],
            cycle_audit_policy=cycle_audit_policy,
            cycle_audit_policy_binding=by_role["cycle_audit_policy"],
            environment_capability_profile=environment_capability_profile,
            environment_capability_profile_binding=by_role[
                "environment_capability_profile"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizedRevisionOrchestrationError):
            raise
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_SUPPORT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[SUPPORT_BUNDLE_DIGEST_FIELD]:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_SUPPORT_REPLAY_MISMATCH"
        )
    return supplied


def _package_sequence(value: Any, code: str, *, maximum: int = 512) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32AuthorizedRevisionOrchestrationError(code)
    rows = list(value)
    if len(rows) > maximum:
        raise V32AuthorizedRevisionOrchestrationError(code)
    return rows


def _context_registry_entry(
    *,
    phase: str,
    package: Mapping[str, Any] | None,
    run_id: str,
    cycle_index: int,
    registry_time: str,
) -> dict[str, Any] | None:
    if package is None:
        return None
    expected = {
        "manifest",
        "shards",
        "original_documents",
        "selection",
        "manifest_binding",
        "shard_bindings",
        "selection_binding",
    }
    if not isinstance(package, Mapping) or set(package) != expected:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_CONTEXT_PACKAGE_INVALID"
        )
    manifest = package["manifest"]
    shards = _package_sequence(
        package["shards"], "V32_REVISION_CYCLE_CONTEXT_SHARDS_INVALID"
    )
    originals = _package_sequence(
        package["original_documents"],
        "V32_REVISION_CYCLE_CONTEXT_ORIGINALS_INVALID",
        maximum=64,
    )
    shard_bindings = _package_sequence(
        package["shard_bindings"],
        "V32_REVISION_CYCLE_CONTEXT_SHARD_BINDINGS_INVALID",
    )
    try:
        manifest_digest = verify_v32_context_compaction_bundle_v1(
            manifest, shards, original_documents=originals
        )
        selection = package["selection"]
        selection_digest = verify_v32_context_shard_selection_v1(
            selection,
            manifest=manifest,
            shards=shards,
            original_documents=originals,
        )
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_CONTEXT_REPLAY_INVALID"
        ) from exc
    if (
        manifest.get("run_id") != run_id
        or manifest.get("cycle_index") != cycle_index
        or selection.get("run_id") != run_id
        or selection.get("cycle_index") != cycle_index
    ):
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_CONTEXT_SCOPE_INVALID"
        )
    _not_after(
        manifest.get("created_at"),
        registry_time,
        "V32_REVISION_CYCLE_CONTEXT_TIME_INVALID",
    )
    _not_after(
        selection.get("selected_at"),
        registry_time,
        "V32_REVISION_CYCLE_CONTEXT_TIME_INVALID",
    )
    manifest_ref = _checked_binding(
        manifest,
        package["manifest_binding"],
        schema_id=MANIFEST_SCHEMA_ID,
        digest_field=MANIFEST_DIGEST_FIELD,
        semantic_digest=manifest_digest,
        code="V32_REVISION_CYCLE_CONTEXT_BINDING_INVALID",
    )
    selection_ref = _checked_binding(
        selection,
        package["selection_binding"],
        schema_id=SELECTION_SCHEMA_ID,
        digest_field=SELECTION_DIGEST_FIELD,
        semantic_digest=selection_digest,
        code="V32_REVISION_CYCLE_CONTEXT_BINDING_INVALID",
    )
    if len(shard_bindings) != len(shards):
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_CONTEXT_SHARD_BINDINGS_INVALID"
        )
    normalized_shard_bindings = [
        _checked_binding(
            shard,
            supplied_binding,
            schema_id=CONTEXT_SHARD_SCHEMA_ID,
            digest_field=CONTEXT_SHARD_DIGEST_FIELD,
            semantic_digest=shard[CONTEXT_SHARD_DIGEST_FIELD],
            code="V32_REVISION_CYCLE_CONTEXT_SHARD_BINDINGS_INVALID",
        )
        for shard, supplied_binding in zip(shards, shard_bindings, strict=True)
    ]
    selected_refs = selection["selected_shard_bindings"]
    if len(selected_refs) != len(normalized_shard_bindings) or any(
        any(
            left[field] != right[field]
            for field in (
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
            )
        )
        for left, right in zip(
            normalized_shard_bindings, selected_refs, strict=True
        )
    ):
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_CONTEXT_SHARD_BINDINGS_INVALID"
        )
    normalized_shard_bindings.sort(
        key=lambda row: (
            row["schema_id"], row["semantic_digest"], row["relative_ref"]
        )
    )
    original_artifact_bindings = [
        row["artifact_binding"] for row in manifest["source_artifacts"]
    ]
    original_artifact_bindings.sort(
        key=lambda row: (
            row["schema_id"], row["semantic_digest"], row["relative_ref"]
        )
    )
    return {
        "phase": phase,
        "manifest_binding": manifest_ref,
        "shard_bindings": normalized_shard_bindings,
        "selection_binding": selection_ref,
        "original_artifact_bindings": original_artifact_bindings,
        "manifest_status": manifest["status"],
        "selection_status": selection["selection_status"],
        "member_count": manifest["member_count"],
        "shard_count": manifest["shard_count"],
        "selected_member_count": selection["selected_member_count"],
        "complete_original_replay_verified": True,
        "complete_dependency_closure_verified": True,
        "truncation_performed": False,
    }


def _unknown_registry_entry(
    package: Mapping[str, Any], *, run_id: str, cycle_index: int, registry_time: str
) -> dict[str, Any]:
    expected = {
        "objective_unknown",
        "objective_unknown_binding",
        "evidence_registry",
        "evidence_registry_binding",
        "subjective_assessment",
        "subjective_assessment_binding",
        "pit_evidence_registry",
        "pit_evidence_availability_registry",
    }
    if not isinstance(package, Mapping) or set(package) != expected:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_UNKNOWN_PACKAGE_INVALID"
        )
    objective = package["objective_unknown"]
    registry = package["evidence_registry"]
    assessment = package["subjective_assessment"]
    try:
        objective_digest = verify_v32_objective_unknown_v1(objective)
        registry_digest = verify_v32_unknown_assessment_evidence_registry_v1(
            registry,
            pit_evidence_registry=package["pit_evidence_registry"],
            pit_evidence_availability_registry=package[
                "pit_evidence_availability_registry"
            ],
        )
        assessment_digest = verify_v32_unknown_subjective_assessment_v1(
            assessment,
            objective_unknown=objective,
            evidence_registry=registry,
        )
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_UNKNOWN_REPLAY_INVALID"
        ) from exc
    if any(
        document.get("run_id") != run_id
        or document.get("cycle_index") != cycle_index
        for document in (objective, registry, assessment)
    ):
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_UNKNOWN_SCOPE_INVALID"
        )
    for value in (
        objective.get("detected_at"),
        registry.get("created_at"),
        assessment.get("assessed_at"),
    ):
        _not_after(value, registry_time, "V32_REVISION_CYCLE_UNKNOWN_TIME_INVALID")
    return {
        "unknown_id": objective["unknown_id"],
        "assessment_id": assessment["assessment_id"],
        "objective_unknown_binding": _checked_binding(
            objective,
            package["objective_unknown_binding"],
            schema_id=OBJECTIVE_SCHEMA_ID,
            digest_field=OBJECTIVE_DIGEST_FIELD,
            semantic_digest=objective_digest,
            code="V32_REVISION_CYCLE_UNKNOWN_BINDING_INVALID",
        ),
        "evidence_registry_binding": _checked_binding(
            registry,
            package["evidence_registry_binding"],
            schema_id=EVIDENCE_REGISTRY_SCHEMA_ID,
            digest_field=EVIDENCE_REGISTRY_DIGEST_FIELD,
            semantic_digest=registry_digest,
            code="V32_REVISION_CYCLE_UNKNOWN_BINDING_INVALID",
        ),
        "subjective_assessment_binding": _checked_binding(
            assessment,
            package["subjective_assessment_binding"],
            schema_id=ASSESSMENT_SCHEMA_ID,
            digest_field=ASSESSMENT_DIGEST_FIELD,
            semantic_digest=assessment_digest,
            code="V32_REVISION_CYCLE_UNKNOWN_BINDING_INVALID",
        ),
        "pit_evidence_registry_binding": registry[
            "pit_evidence_registry_binding"
        ],
        "pit_evidence_availability_registry_binding": registry[
            "pit_evidence_availability_registry_binding"
        ],
        "objective_status": "UNKNOWN",
        "assessment_status": assessment["assessment_status"],
        "directional_view": assessment["directional_view"],
        "subjective_plausibility_tier": assessment[
            "subjective_plausibility_tier"
        ],
        "objective_unknown_preserved": True,
    }


def _data_gap_registry_entry(
    package: Mapping[str, Any], *, run_id: str, cycle_index: int, registry_time: str
) -> dict[str, Any]:
    if not isinstance(package, Mapping) or set(package) != {
        "escalation",
        "escalation_binding",
    }:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_DATA_GAP_PACKAGE_INVALID"
        )
    escalation = package["escalation"]
    try:
        escalation_digest = verify_v32_data_gap_escalation_v1(escalation)
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_DATA_GAP_REPLAY_INVALID"
        ) from exc
    if (
        escalation.get("run_id") != run_id
        or escalation.get("cycle_index") != cycle_index
    ):
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_DATA_GAP_SCOPE_INVALID"
        )
    _not_after(
        escalation.get("failed_at"),
        registry_time,
        "V32_REVISION_CYCLE_DATA_GAP_TIME_INVALID",
    )
    return {
        "gap_id": escalation["gap_id"],
        "escalation_binding": _checked_binding(
            escalation,
            package["escalation_binding"],
            schema_id=ESCALATION_SCHEMA_ID,
            digest_field=ESCALATION_DIGEST_FIELD,
            semantic_digest=escalation_digest,
            code="V32_REVISION_CYCLE_DATA_GAP_BINDING_INVALID",
        ),
        "objective_status": "UNKNOWN",
        "manual_plan_status": escalation["manual_plan_status"],
        "claim_ceiling": escalation["claim_ceiling"],
    }


def _manual_revision_registry_entry(
    package: Mapping[str, Any], *, run_id: str, cycle_index: int, registry_time: str
) -> dict[str, Any]:
    if not isinstance(package, Mapping) or set(package) != {
        "escalation",
        "revision",
        "revision_binding",
    }:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_MANUAL_PACKAGE_INVALID"
        )
    escalation = package["escalation"]
    revision = package["revision"]
    try:
        revision_digest = verify_v32_manual_public_evidence_revision_v1(
            revision, escalation=escalation
        )
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_MANUAL_REPLAY_INVALID"
        ) from exc
    if (
        revision.get("run_id") != run_id
        or revision.get("future_cycle_index") != cycle_index
    ):
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_MANUAL_SCOPE_INVALID"
        )
    _not_after(
        revision.get("verified_at"),
        registry_time,
        "V32_REVISION_CYCLE_MANUAL_TIME_INVALID",
    )
    return {
        "revision_id": revision["revision_id"],
        "source_cycle_index": revision["source_cycle_index"],
        "future_cycle_index": revision["future_cycle_index"],
        "escalation_binding": revision["escalation_binding"],
        "revision_binding": _checked_binding(
            revision,
            package["revision_binding"],
            schema_id=MANUAL_REVISION_SCHEMA_ID,
            digest_field=MANUAL_REVISION_DIGEST_FIELD,
            semantic_digest=revision_digest,
            code="V32_REVISION_CYCLE_MANUAL_BINDING_INVALID",
        ),
        "raw_evidence_binding": revision["raw_evidence_binding"],
        "capture_evidence_binding": revision["capture_evidence_binding"],
        "admission_status": revision["admission_status"],
        "historical_backfill_performed": False,
    }


def _environment_registry_entry(
    package: Mapping[str, Any] | None, *, registry_time: str
) -> dict[str, Any] | None:
    if package is None:
        return None
    if not isinstance(package, Mapping) or set(package) != {"profile", "profile_binding"}:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_ENVIRONMENT_PACKAGE_INVALID"
        )
    profile = package["profile"]
    try:
        profile_digest = verify_v32_environment_capability_profile_v1(profile)
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_ENVIRONMENT_REPLAY_INVALID"
        ) from exc
    _not_after(
        profile.get("frozen_at"),
        registry_time,
        "V32_REVISION_CYCLE_ENVIRONMENT_TIME_INVALID",
    )
    native = all(row["status"] == "AVAILABLE" for row in profile["capabilities"])
    return {
        "profile_binding": _checked_binding(
            profile,
            package["profile_binding"],
            schema_id=ENVIRONMENT_SCHEMA_ID,
            digest_field=ENVIRONMENT_DIGEST_FIELD,
            semantic_digest=profile_digest,
            code="V32_REVISION_CYCLE_ENVIRONMENT_BINDING_INVALID",
        ),
        "run_scope_id": profile["run_scope_id"],
        "conformance_status": (
            "CONFORMANT_NATIVE"
            if native and not profile["localization_adapters"]
            else "CONFORMANT_WITH_DECLARED_LIMITS"
        ),
        "capability_statuses": [
            {"category": row["category"], "status": row["status"]}
            for row in profile["capabilities"]
        ],
        "localization_adapter_count": len(profile["localization_adapters"]),
        "core_theory_evaluation_timing_authority_unchanged": True,
    }


def _recovery_registry_entry(
    package: Mapping[str, Any], *, run_id: str, cycle_index: int, registry_time: str
) -> dict[str, Any]:
    expected = {
        "policy",
        "policy_binding",
        "observation",
        "observation_binding",
        "recovery_receipt",
        "recovery_receipt_binding",
    }
    if not isinstance(package, Mapping) or set(package) != expected:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_RECOVERY_PACKAGE_INVALID"
        )
    policy = package["policy"]
    observation = package["observation"]
    receipt = package["recovery_receipt"]
    receipt_binding = package["recovery_receipt_binding"]
    try:
        policy_digest = verify_v32_recovery_supervision_policy_v1(policy)
        observation_digest = verify_v32_supervisor_observation_v1(
            observation, policy=policy
        )
        receipt_digest = (
            None
            if receipt is None
            else verify_v32_deterministic_recovery_receipt_v1(
                receipt, policy=policy, observation=observation
            )
        )
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_RECOVERY_REPLAY_INVALID"
        ) from exc
    if (
        observation.get("run_id") != run_id
        or observation.get("cycle_index") != cycle_index
        or (receipt is not None and receipt.get("run_id") != run_id)
        or (receipt is not None and receipt.get("cycle_index") != cycle_index)
        or (receipt is None) != (receipt_binding is None)
    ):
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_RECOVERY_SCOPE_INVALID"
        )
    _not_after(
        observation.get("observed_at"),
        registry_time,
        "V32_REVISION_CYCLE_RECOVERY_TIME_INVALID",
    )
    if receipt is not None:
        _not_after(
            receipt.get("completed_at"),
            registry_time,
            "V32_REVISION_CYCLE_RECOVERY_TIME_INVALID",
        )
    return {
        "policy_binding": _checked_binding(
            policy,
            package["policy_binding"],
            schema_id=RECOVERY_POLICY_SCHEMA_ID,
            digest_field=RECOVERY_POLICY_DIGEST_FIELD,
            semantic_digest=policy_digest,
            code="V32_REVISION_CYCLE_RECOVERY_BINDING_INVALID",
        ),
        "observation_binding": _checked_binding(
            observation,
            package["observation_binding"],
            schema_id=OBSERVATION_SCHEMA_ID,
            digest_field=OBSERVATION_DIGEST_FIELD,
            semantic_digest=observation_digest,
            code="V32_REVISION_CYCLE_RECOVERY_BINDING_INVALID",
        ),
        "recovery_receipt_binding": (
            None
            if receipt is None
            else _checked_binding(
                receipt,
                receipt_binding,
                schema_id=RECOVERY_SCHEMA_ID,
                digest_field=RECOVERY_DIGEST_FIELD,
                semantic_digest=receipt_digest,
                code="V32_REVISION_CYCLE_RECOVERY_BINDING_INVALID",
            )
        ),
        "disposition": observation["disposition"],
        "recovery_result": None if receipt is None else receipt["result"],
        "network_request_count": 0,
        "agent_attempt_count": 0,
        "outcome_read_count": 0,
    }


def _semantic_digests(value: Any) -> list[str]:
    found: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            if set(item) == {
                "relative_ref",
                "schema_id",
                "digest_field",
                "semantic_digest",
                "physical_sha256",
            }:
                found.add(str(item["semantic_digest"]))
                return
            for nested in item.values():
                visit(nested)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            for nested in item:
                visit(nested)

    visit(value)
    return sorted(found)


def _sorted_unique_entries(
    rows: Sequence[dict[str, Any]], *, key: str, code: str
) -> list[dict[str, Any]]:
    normalized = sorted(rows, key=lambda row: (str(row[key]), canonical_digest(row)))
    if len({str(row[key]) for row in normalized}) != len(normalized):
        raise V32AuthorizedRevisionOrchestrationError(code)
    return normalized


def build_v32_authorized_revision_cycle_registry_v1(
    *,
    registry_id: str,
    run_id: str,
    cycle_index: int,
    created_at: str,
    proposal_context: Mapping[str, Any] | None,
    selection_context: Mapping[str, Any] | None,
    unknown_tracks: Sequence[Mapping[str, Any]],
    data_gap_entries: Sequence[Mapping[str, Any]],
    manual_evidence_entries: Sequence[Mapping[str, Any]],
    environment_conformance: Mapping[str, Any] | None,
    recovery_traces: Sequence[Mapping[str, Any]],
    revision_input_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate one cycle while replaying every owned nested contract.

    Omitting ``revision_input_state`` preserves the exact historical 1.0.0
    artifact.  New production callers supply it and emit strict 2.0.0.
    """

    try:
        run = text(run_id, "V32_REVISION_CYCLE_REGISTRY_RUN_INVALID")
        cycle = integer(
            cycle_index,
            "V32_REVISION_CYCLE_REGISTRY_CYCLE_INVALID",
            minimum=1,
            maximum=16,
        )
        created = time(
            created_at, "V32_REVISION_CYCLE_REGISTRY_TIME_INVALID"
        )
        proposal = _context_registry_entry(
            phase="PROPOSAL",
            package=proposal_context,
            run_id=run,
            cycle_index=cycle,
            registry_time=created,
        )
        selection = _context_registry_entry(
            phase="SELECTION",
            package=selection_context,
            run_id=run,
            cycle_index=cycle,
            registry_time=created,
        )
        unknown_rows = _sorted_unique_entries(
            [
                _unknown_registry_entry(
                    row,
                    run_id=run,
                    cycle_index=cycle,
                    registry_time=created,
                )
                for row in _package_sequence(
                    unknown_tracks, "V32_REVISION_CYCLE_UNKNOWN_SET_INVALID"
                )
            ],
            key="assessment_id",
            code="V32_REVISION_CYCLE_UNKNOWN_DUPLICATE",
        )
        gap_rows = _sorted_unique_entries(
            [
                _data_gap_registry_entry(
                    row,
                    run_id=run,
                    cycle_index=cycle,
                    registry_time=created,
                )
                for row in _package_sequence(
                    data_gap_entries, "V32_REVISION_CYCLE_DATA_GAP_SET_INVALID"
                )
            ],
            key="gap_id",
            code="V32_REVISION_CYCLE_DATA_GAP_DUPLICATE",
        )
        manual_rows = _sorted_unique_entries(
            [
                _manual_revision_registry_entry(
                    row,
                    run_id=run,
                    cycle_index=cycle,
                    registry_time=created,
                )
                for row in _package_sequence(
                    manual_evidence_entries,
                    "V32_REVISION_CYCLE_MANUAL_SET_INVALID",
                )
            ],
            key="revision_id",
            code="V32_REVISION_CYCLE_MANUAL_DUPLICATE",
        )
        environment = _environment_registry_entry(
            environment_conformance, registry_time=created
        )
        recovery_rows = [
            _recovery_registry_entry(
                row,
                run_id=run,
                cycle_index=cycle,
                registry_time=created,
            )
            for row in _package_sequence(
                recovery_traces, "V32_REVISION_CYCLE_RECOVERY_SET_INVALID"
            )
        ]
        recovery_rows.sort(
            key=lambda row: row["observation_binding"]["semantic_digest"]
        )
        if len(
            {
                row["observation_binding"]["semantic_digest"]
                for row in recovery_rows
            }
        ) != len(recovery_rows):
            raise V32AuthorizedRevisionOrchestrationError(
                "V32_REVISION_CYCLE_RECOVERY_DUPLICATE"
            )
        normalized_revision_input_state = None
        if revision_input_state is not None:
            normalized_revision_input_state = dict(revision_input_state)
            verify_v32_revision_input_state_v1(
                normalized_revision_input_state,
                expected_run_id=run,
                expected_cycle_index=cycle,
            )
            _not_after(
                normalized_revision_input_state["observed_at"],
                created,
                "V32_REVISION_CYCLE_INPUT_STATE_AFTER_REGISTRY",
            )
            reader_item_count = len(unknown_rows) + len(manual_rows) + len(recovery_rows)
            if (
                normalized_revision_input_state["state"] == "PRESENT"
                and reader_item_count == 0
            ) or (
                normalized_revision_input_state["state"] != "PRESENT"
                and reader_item_count != 0
            ):
                raise V32AuthorizedRevisionOrchestrationError(
                    "V32_REVISION_CYCLE_INPUT_STATE_MATERIAL_MISMATCH"
                )
        component_view = {
            "proposal_context": proposal,
            "selection_context": selection,
            "unknown_tracks": unknown_rows,
            "data_gap_entries": gap_rows,
            "manual_evidence_entries": manual_rows,
            "environment_conformance": environment,
            "recovery_traces": recovery_rows,
        }
        if normalized_revision_input_state is not None:
            component_view["revision_input_state"] = normalized_revision_input_state
        component_digests = _semantic_digests(component_view)
        document = {
            "schema_id": CYCLE_REGISTRY_SCHEMA_ID,
            "schema_version": (
                CYCLE_REGISTRY_SCHEMA_VERSION_V1
                if normalized_revision_input_state is None
                else CYCLE_REGISTRY_SCHEMA_VERSION_V2
            ),
            "registry_id": text(
                registry_id, "V32_REVISION_CYCLE_REGISTRY_ID_INVALID"
            ),
            "run_id": run,
            "cycle_index": cycle,
            "created_at": created,
            **component_view,
            "unknown_track_count": len(unknown_rows),
            "data_gap_count": len(gap_rows),
            "manual_evidence_revision_count": len(manual_rows),
            "recovery_trace_count": len(recovery_rows),
            "component_semantic_digests": component_digests,
            "component_semantic_digest_index_digest": canonical_digest(
                component_digests
            ),
            "zero_item_registries_are_explicit": True,
            "nested_artifacts_verified_by_owning_contracts": True,
            "full_nested_replay_requires_external_packages": True,
            "receipt_integrity_verifier_replays_nested_artifacts": False,
            "cycle_audit_narrative_included": False,
            "cycle_audit_narrative_stage": (
                "POST_CORRESPONDING_TYPED_BOUNDARY_OUTSIDE_CYCLE_REGISTRY"
            ),
            "registry_is_authority": False,
            "registry_is_acceptance": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizedRevisionOrchestrationError):
            raise
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_REGISTRY_INPUT_INVALID"
        ) from exc
    return self_digest(document, CYCLE_REGISTRY_DIGEST_FIELD)


_CYCLE_REGISTRY_FIELDS_V1 = frozenset(
    {
        "schema_id",
        "schema_version",
        "registry_id",
        "run_id",
        "cycle_index",
        "created_at",
        "proposal_context",
        "selection_context",
        "unknown_tracks",
        "data_gap_entries",
        "manual_evidence_entries",
        "environment_conformance",
        "recovery_traces",
        "unknown_track_count",
        "data_gap_count",
        "manual_evidence_revision_count",
        "recovery_trace_count",
        "component_semantic_digests",
        "component_semantic_digest_index_digest",
        "zero_item_registries_are_explicit",
        "nested_artifacts_verified_by_owning_contracts",
        "full_nested_replay_requires_external_packages",
        "receipt_integrity_verifier_replays_nested_artifacts",
        "cycle_audit_narrative_included",
        "cycle_audit_narrative_stage",
        "registry_is_authority",
        "registry_is_acceptance",
        *boundary().keys(),
        CYCLE_REGISTRY_DIGEST_FIELD,
    }
)
_CYCLE_REGISTRY_FIELDS_V2 = frozenset(
    {*_CYCLE_REGISTRY_FIELDS_V1, "revision_input_state"}
)
_CONTEXT_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "phase",
        "manifest_binding",
        "shard_bindings",
        "selection_binding",
        "original_artifact_bindings",
        "manifest_status",
        "selection_status",
        "member_count",
        "shard_count",
        "selected_member_count",
        "complete_original_replay_verified",
        "complete_dependency_closure_verified",
        "truncation_performed",
    }
)
_UNKNOWN_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "unknown_id",
        "assessment_id",
        "objective_unknown_binding",
        "evidence_registry_binding",
        "subjective_assessment_binding",
        "pit_evidence_registry_binding",
        "pit_evidence_availability_registry_binding",
        "objective_status",
        "assessment_status",
        "directional_view",
        "subjective_plausibility_tier",
        "objective_unknown_preserved",
    }
)
_DATA_GAP_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "gap_id",
        "escalation_binding",
        "objective_status",
        "manual_plan_status",
        "claim_ceiling",
    }
)
_MANUAL_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "revision_id",
        "source_cycle_index",
        "future_cycle_index",
        "escalation_binding",
        "revision_binding",
        "raw_evidence_binding",
        "capture_evidence_binding",
        "admission_status",
        "historical_backfill_performed",
    }
)
_ENVIRONMENT_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "profile_binding",
        "run_scope_id",
        "conformance_status",
        "capability_statuses",
        "localization_adapter_count",
        "core_theory_evaluation_timing_authority_unchanged",
    }
)
_RECOVERY_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "policy_binding",
        "observation_binding",
        "recovery_receipt_binding",
        "disposition",
        "recovery_result",
        "network_request_count",
        "agent_attempt_count",
        "outcome_read_count",
    }
)


def _receipt_binding(
    value: Any,
    *,
    code: str,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    try:
        normalized = binding(value, code)
    except (TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionOrchestrationError(code) from exc
    if (
        (schema_id is not None and normalized["schema_id"] != schema_id)
        or (
            digest_field is not None
            and normalized["digest_field"] != digest_field
        )
    ):
        raise V32AuthorizedRevisionOrchestrationError(code)
    return normalized


def _receipt_binding_list(
    value: Any,
    *,
    code: str,
    allow_empty: bool,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> list[dict[str, str]]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise V32AuthorizedRevisionOrchestrationError(code)
    rows = [
        _receipt_binding(
            row,
            code=code,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        for row in value
    ]
    if (
        rows
        != sorted(
            rows,
            key=lambda row: (
                row["schema_id"], row["semantic_digest"], row["relative_ref"]
            ),
        )
        or len(
            {
                (row["schema_id"], row["semantic_digest"], row["physical_sha256"])
                for row in rows
            }
        )
        != len(rows)
    ):
        raise V32AuthorizedRevisionOrchestrationError(code)
    return rows


def _verify_context_registry_receipt(value: Any, *, phase: str) -> None:
    if value is None:
        return
    code = "V32_REVISION_CYCLE_REGISTRY_CONTEXT_RECEIPT_INVALID"
    if not isinstance(value, Mapping) or set(value) != _CONTEXT_REGISTRY_ENTRY_FIELDS:
        raise V32AuthorizedRevisionOrchestrationError(code)
    _receipt_binding(
        value["manifest_binding"],
        code=code,
        schema_id=MANIFEST_SCHEMA_ID,
        digest_field=MANIFEST_DIGEST_FIELD,
    )
    shards = _receipt_binding_list(
        value["shard_bindings"],
        code=code,
        allow_empty=True,
        schema_id=CONTEXT_SHARD_SCHEMA_ID,
        digest_field=CONTEXT_SHARD_DIGEST_FIELD,
    )
    _receipt_binding(
        value["selection_binding"],
        code=code,
        schema_id=SELECTION_SCHEMA_ID,
        digest_field=SELECTION_DIGEST_FIELD,
    )
    _receipt_binding_list(
        value["original_artifact_bindings"], code=code, allow_empty=False
    )
    member_count = integer(value["member_count"], code, minimum=1, maximum=16_384)
    shard_count = integer(value["shard_count"], code, minimum=0, maximum=512)
    selected_count = integer(
        value["selected_member_count"], code, minimum=0, maximum=member_count
    )
    del selected_count
    if (
        value["phase"] != phase
        or value["manifest_status"] != "READY_LOSSLESS_SHARDED"
        or value["selection_status"]
        not in {
            "READY_FORCED_ALL_SHARDS_SEQUENTIAL",
            "CONTEXT_CAPACITY_UNRESOLVED",
        }
        or shard_count != len(shards)
        or shard_count == 0
        or (
            value["selection_status"]
            == "READY_FORCED_ALL_SHARDS_SEQUENTIAL"
            and value["selected_member_count"] != member_count
        )
        or value["complete_original_replay_verified"] is not True
        or value["complete_dependency_closure_verified"] is not True
        or value["truncation_performed"] is not False
    ):
        raise V32AuthorizedRevisionOrchestrationError(code)


def _verify_unknown_registry_receipts(value: Any) -> None:
    code = "V32_REVISION_CYCLE_REGISTRY_UNKNOWN_RECEIPT_INVALID"
    if not isinstance(value, list) or len(value) > 512:
        raise V32AuthorizedRevisionOrchestrationError(code)
    identities: list[str] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != _UNKNOWN_REGISTRY_ENTRY_FIELDS:
            raise V32AuthorizedRevisionOrchestrationError(code)
        identities.append(text(row["assessment_id"], code))
        text(row["unknown_id"], code)
        _receipt_binding(
            row["objective_unknown_binding"],
            code=code,
            schema_id=OBJECTIVE_SCHEMA_ID,
            digest_field=OBJECTIVE_DIGEST_FIELD,
        )
        _receipt_binding(
            row["evidence_registry_binding"],
            code=code,
            schema_id=EVIDENCE_REGISTRY_SCHEMA_ID,
            digest_field=EVIDENCE_REGISTRY_DIGEST_FIELD,
        )
        _receipt_binding(
            row["subjective_assessment_binding"],
            code=code,
            schema_id=ASSESSMENT_SCHEMA_ID,
            digest_field=ASSESSMENT_DIGEST_FIELD,
        )
        _receipt_binding(
            row["pit_evidence_registry_binding"],
            code=code,
            schema_id=PIT_REGISTRY_SCHEMA_ID,
            digest_field=PIT_REGISTRY_DIGEST_FIELD,
        )
        _receipt_binding(
            row["pit_evidence_availability_registry_binding"],
            code=code,
            schema_id=PIT_AVAILABILITY_SCHEMA_ID,
            digest_field=PIT_AVAILABILITY_DIGEST_FIELD,
        )
        tier = text(row["subjective_plausibility_tier"], code)
        if (
            tier not in SUBJECTIVE_PLAUSIBILITY_TIERS
            or
            row["objective_status"] != "UNKNOWN"
            or row["assessment_status"]
            not in {
                "EVIDENCE_BOUND_SUBJECTIVE_ASSESSMENT",
                "NO_EVIDENCE_REMAINS_UNKNOWN_EXTREME_UNCERTAINTY",
            }
            or row["directional_view"]
            not in {"LONG", "SHORT", "NEUTRAL", "MIXED", "UNKNOWN"}
            or row["objective_unknown_preserved"] is not True
            or (
                row["assessment_status"]
                == "NO_EVIDENCE_REMAINS_UNKNOWN_EXTREME_UNCERTAINTY"
                and (
                    row["directional_view"] != "UNKNOWN"
                    or tier != "EXTREME_UNCERTAINTY"
                )
            )
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
    expected_order = sorted(
        value, key=lambda row: (row["assessment_id"], canonical_digest(row))
    )
    if list(value) != expected_order or len(identities) != len(set(identities)):
        raise V32AuthorizedRevisionOrchestrationError(code)


def _verify_data_gap_registry_receipts(value: Any) -> None:
    code = "V32_REVISION_CYCLE_REGISTRY_DATA_GAP_RECEIPT_INVALID"
    if not isinstance(value, list) or len(value) > 512:
        raise V32AuthorizedRevisionOrchestrationError(code)
    identities: list[str] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != _DATA_GAP_REGISTRY_ENTRY_FIELDS:
            raise V32AuthorizedRevisionOrchestrationError(code)
        identities.append(text(row["gap_id"], code))
        text(row["claim_ceiling"], code)
        _receipt_binding(
            row["escalation_binding"],
            code=code,
            schema_id=ESCALATION_SCHEMA_ID,
            digest_field=ESCALATION_DIGEST_FIELD,
        )
        if (
            row["objective_status"] != "UNKNOWN"
            or row["manual_plan_status"]
            != "OPEN_MANUAL_PUBLIC_EVIDENCE_PLAN"
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
    if (
        list(value)
        != sorted(value, key=lambda row: (row["gap_id"], canonical_digest(row)))
        or len(identities) != len(set(identities))
    ):
        raise V32AuthorizedRevisionOrchestrationError(code)


def _verify_manual_registry_receipts(value: Any, *, cycle_index: int) -> None:
    code = "V32_REVISION_CYCLE_REGISTRY_MANUAL_RECEIPT_INVALID"
    if not isinstance(value, list) or len(value) > 512:
        raise V32AuthorizedRevisionOrchestrationError(code)
    identities: list[str] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != _MANUAL_REGISTRY_ENTRY_FIELDS:
            raise V32AuthorizedRevisionOrchestrationError(code)
        identities.append(text(row["revision_id"], code))
        source_cycle = integer(
            row["source_cycle_index"], code, minimum=1, maximum=16
        )
        future_cycle = integer(
            row["future_cycle_index"], code, minimum=1, maximum=16
        )
        _receipt_binding(
            row["escalation_binding"],
            code=code,
            schema_id=ESCALATION_SCHEMA_ID,
            digest_field=ESCALATION_DIGEST_FIELD,
        )
        _receipt_binding(
            row["revision_binding"],
            code=code,
            schema_id=MANUAL_REVISION_SCHEMA_ID,
            digest_field=MANUAL_REVISION_DIGEST_FIELD,
        )
        _receipt_binding(row["raw_evidence_binding"], code=code)
        _receipt_binding(row["capture_evidence_binding"], code=code)
        if (
            source_cycle >= future_cycle
            or future_cycle != cycle_index
            or row["admission_status"] != "VERIFIED_FOR_FUTURE_CYCLE_ONLY"
            or row["historical_backfill_performed"] is not False
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
    if (
        list(value)
        != sorted(value, key=lambda row: (row["revision_id"], canonical_digest(row)))
        or len(identities) != len(set(identities))
    ):
        raise V32AuthorizedRevisionOrchestrationError(code)


def _verify_environment_registry_receipt(value: Any) -> None:
    if value is None:
        return
    code = "V32_REVISION_CYCLE_REGISTRY_ENVIRONMENT_RECEIPT_INVALID"
    if not isinstance(value, Mapping) or set(value) != _ENVIRONMENT_REGISTRY_ENTRY_FIELDS:
        raise V32AuthorizedRevisionOrchestrationError(code)
    _receipt_binding(
        value["profile_binding"],
        code=code,
        schema_id=ENVIRONMENT_SCHEMA_ID,
        digest_field=ENVIRONMENT_DIGEST_FIELD,
    )
    text(value["run_scope_id"], code)
    rows = value["capability_statuses"]
    adapter_count = integer(
        value["localization_adapter_count"], code, minimum=0, maximum=64
    )
    native = (
        isinstance(rows, list)
        and all(
            isinstance(row, Mapping) and row.get("status") == "AVAILABLE"
            for row in rows
        )
        and adapter_count == 0
    )
    if (
        not isinstance(rows, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"category", "status"}
            or row["status"]
            not in {"AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN"}
            for row in rows
        )
        or [row["category"] for row in rows] != list(CAPABILITY_CATEGORIES)
        or value["conformance_status"]
        != (
            "CONFORMANT_NATIVE"
            if native
            else "CONFORMANT_WITH_DECLARED_LIMITS"
        )
        or value["core_theory_evaluation_timing_authority_unchanged"] is not True
    ):
        raise V32AuthorizedRevisionOrchestrationError(code)


def _verify_recovery_registry_receipts(value: Any) -> None:
    code = "V32_REVISION_CYCLE_REGISTRY_RECOVERY_RECEIPT_INVALID"
    if not isinstance(value, list) or len(value) > 512:
        raise V32AuthorizedRevisionOrchestrationError(code)
    identities: list[str] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != _RECOVERY_REGISTRY_ENTRY_FIELDS:
            raise V32AuthorizedRevisionOrchestrationError(code)
        _receipt_binding(
            row["policy_binding"],
            code=code,
            schema_id=RECOVERY_POLICY_SCHEMA_ID,
            digest_field=RECOVERY_POLICY_DIGEST_FIELD,
        )
        observation = _receipt_binding(
            row["observation_binding"],
            code=code,
            schema_id=OBSERVATION_SCHEMA_ID,
            digest_field=OBSERVATION_DIGEST_FIELD,
        )
        identities.append(observation["semantic_digest"])
        if row["recovery_receipt_binding"] is not None:
            _receipt_binding(
                row["recovery_receipt_binding"],
                code=code,
                schema_id=RECOVERY_SCHEMA_ID,
                digest_field=RECOVERY_DIGEST_FIELD,
            )
        if (row["recovery_receipt_binding"] is None) != (
            row["recovery_result"] is None
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
        for field in (
            "network_request_count",
            "agent_attempt_count",
            "outcome_read_count",
        ):
            if row[field] != 0:
                raise V32AuthorizedRevisionOrchestrationError(code)
        if text(row["disposition"], code) not in DISPOSITIONS:
            raise V32AuthorizedRevisionOrchestrationError(code)
        if row["recovery_result"] is not None:
            text(row["recovery_result"], code)
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise V32AuthorizedRevisionOrchestrationError(code)


def verify_v32_authorized_revision_cycle_registry_receipt_v1(
    document: Mapping[str, Any],
) -> str:
    """Verify registry receipt integrity without claiming nested original replay.

    Acceptance/store callers that only hold the registry and its binding can use
    this closed-shape verifier.  The package-aware full verifier remains the only
    verifier that replays original documents and every owning Domain contract.
    """

    code = "V32_REVISION_CYCLE_REGISTRY_RECEIPT_INVALID"
    try:
        if not isinstance(document, Mapping):
            raise V32AuthorizedRevisionOrchestrationError(code)
        schema_version = document.get("schema_version")
        expected_fields = {
            CYCLE_REGISTRY_SCHEMA_VERSION_V1: _CYCLE_REGISTRY_FIELDS_V1,
            CYCLE_REGISTRY_SCHEMA_VERSION_V2: _CYCLE_REGISTRY_FIELDS_V2,
        }.get(schema_version)
        if expected_fields is None or set(document) != expected_fields:
            raise V32AuthorizedRevisionOrchestrationError(code)
        supplied = verify_self_digest(document, CYCLE_REGISTRY_DIGEST_FIELD)
        verify_boundary(document, code)
        if (
            document["schema_id"] != CYCLE_REGISTRY_SCHEMA_ID
            or schema_version
            not in {
                CYCLE_REGISTRY_SCHEMA_VERSION_V1,
                CYCLE_REGISTRY_SCHEMA_VERSION_V2,
            }
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
        text(document["registry_id"], code)
        text(document["run_id"], code)
        cycle = integer(document["cycle_index"], code, minimum=1, maximum=16)
        time(document["created_at"], code)
        _verify_context_registry_receipt(
            document["proposal_context"], phase="PROPOSAL"
        )
        _verify_context_registry_receipt(
            document["selection_context"], phase="SELECTION"
        )
        _verify_unknown_registry_receipts(document["unknown_tracks"])
        _verify_data_gap_registry_receipts(document["data_gap_entries"])
        _verify_manual_registry_receipts(
            document["manual_evidence_entries"], cycle_index=cycle
        )
        _verify_environment_registry_receipt(document["environment_conformance"])
        _verify_recovery_registry_receipts(document["recovery_traces"])
        if schema_version == CYCLE_REGISTRY_SCHEMA_VERSION_V2:
            verify_v32_revision_input_state_v1(
                document["revision_input_state"],
                expected_run_id=document["run_id"],
                expected_cycle_index=cycle,
            )
            _not_after(
                document["revision_input_state"]["observed_at"],
                document["created_at"],
                code,
            )
            reader_item_count = (
                len(document["unknown_tracks"])
                + len(document["manual_evidence_entries"])
                + len(document["recovery_traces"])
            )
            if (
                document["revision_input_state"]["state"] == "PRESENT"
                and reader_item_count == 0
            ) or (
                document["revision_input_state"]["state"] != "PRESENT"
                and reader_item_count != 0
            ):
                raise V32AuthorizedRevisionOrchestrationError(code)
        if (
            document["unknown_track_count"] != len(document["unknown_tracks"])
            or document["data_gap_count"] != len(document["data_gap_entries"])
            or document["manual_evidence_revision_count"]
            != len(document["manual_evidence_entries"])
            or document["recovery_trace_count"] != len(document["recovery_traces"])
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
        component_view = {
            "proposal_context": document["proposal_context"],
            "selection_context": document["selection_context"],
            "unknown_tracks": document["unknown_tracks"],
            "data_gap_entries": document["data_gap_entries"],
            "manual_evidence_entries": document["manual_evidence_entries"],
            "environment_conformance": document["environment_conformance"],
            "recovery_traces": document["recovery_traces"],
        }
        if schema_version == CYCLE_REGISTRY_SCHEMA_VERSION_V2:
            component_view["revision_input_state"] = document[
                "revision_input_state"
            ]
        component_digests = document["component_semantic_digests"]
        if (
            not isinstance(component_digests, list)
            or component_digests != sorted(set(component_digests))
            or any(digest(value, code) != value for value in component_digests)
            or component_digests != _semantic_digests(component_view)
            or document["component_semantic_digest_index_digest"]
            != canonical_digest(component_digests)
            or document["zero_item_registries_are_explicit"] is not True
            or document["nested_artifacts_verified_by_owning_contracts"] is not True
            or document["full_nested_replay_requires_external_packages"] is not True
            or document["receipt_integrity_verifier_replays_nested_artifacts"] is not False
            or document["cycle_audit_narrative_included"] is not False
            or document["cycle_audit_narrative_stage"]
            != "POST_CORRESPONDING_TYPED_BOUNDARY_OUTSIDE_CYCLE_REGISTRY"
            or document["registry_is_authority"] is not False
            or document["registry_is_acceptance"] is not False
        ):
            raise V32AuthorizedRevisionOrchestrationError(code)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizedRevisionOrchestrationError):
            raise
        raise V32AuthorizedRevisionOrchestrationError(code) from exc
    return supplied


def verify_v32_authorized_revision_cycle_registry_v1(
    document: Mapping[str, Any],
    *,
    proposal_context: Mapping[str, Any] | None,
    selection_context: Mapping[str, Any] | None,
    unknown_tracks: Sequence[Mapping[str, Any]],
    data_gap_entries: Sequence[Mapping[str, Any]],
    manual_evidence_entries: Sequence[Mapping[str, Any]],
    environment_conformance: Mapping[str, Any] | None,
    recovery_traces: Sequence[Mapping[str, Any]],
    revision_input_state: Mapping[str, Any] | None = None,
) -> str:
    try:
        supplied = verify_v32_authorized_revision_cycle_registry_receipt_v1(
            document
        )
        rebuilt = build_v32_authorized_revision_cycle_registry_v1(
            registry_id=document["registry_id"],
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            created_at=document["created_at"],
            proposal_context=proposal_context,
            selection_context=selection_context,
            unknown_tracks=unknown_tracks,
            data_gap_entries=data_gap_entries,
            manual_evidence_entries=manual_evidence_entries,
            environment_conformance=environment_conformance,
            recovery_traces=recovery_traces,
            revision_input_state=revision_input_state,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorizedRevisionOrchestrationError):
            raise
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_REGISTRY_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[CYCLE_REGISTRY_DIGEST_FIELD]:
        raise V32AuthorizedRevisionOrchestrationError(
            "V32_REVISION_CYCLE_REGISTRY_REPLAY_MISMATCH"
        )
    return supplied


def freeze_v32_authorized_revision_support_bundle_v1(
    *, store: V32AuthorizedRevisionStorePort, support_bundle_args: Mapping[str, Any]
) -> Mapping[str, Any]:
    document = build_v32_authorized_revision_support_bundle_v1(
        **dict(support_bundle_args)
    )
    document_binding = store.persist_document(
        role="authorized_revision_support_bundle", document=document
    )
    return {"support_bundle": document, "support_bundle_binding": dict(document_binding)}


def compose_v32_authorized_revision_cycle_registry_v1(
    *, store: V32AuthorizedRevisionStorePort, registry_args: Mapping[str, Any]
) -> Mapping[str, Any]:
    document = build_v32_authorized_revision_cycle_registry_v1(
        **dict(registry_args)
    )
    document_binding = store.persist_document(
        role="authorized_revision_cycle_registry", document=document
    )
    return {"cycle_registry": document, "cycle_registry_binding": dict(document_binding)}


__all__ = [
    "CYCLE_REGISTRY_DIGEST_FIELD",
    "CYCLE_REGISTRY_SCHEMA_ID",
    "CYCLE_REGISTRY_SCHEMA_VERSION_V1",
    "CYCLE_REGISTRY_SCHEMA_VERSION_V2",
    "REVISION_INPUT_STATE_DIGEST_FIELD",
    "REVISION_INPUT_STATE_SCHEMA_ID",
    "REVISION_INPUT_STATES",
    "SUPPORT_BUNDLE_DIGEST_FIELD",
    "SUPPORT_BUNDLE_SCHEMA_ID",
    "V32AuthorizedRevisionStorePort",
    "V32AuthorizedRevisionOrchestrationError",
    "admit_v32_manual_public_evidence_revision_v1",
    "build_v32_authorized_revision_cycle_registry_v1",
    "build_v32_authorized_revision_support_bundle_v1",
    "build_v32_revision_input_state_v1",
    "compact_and_select_v32_agent_context_v1",
    "compose_v32_authorized_revision_cycle_registry_v1",
    "compose_v32_cycle_audit_narrative_v1",
    "compose_v32_data_gap_escalation_v1",
    "compose_v32_unknown_dual_track_v1",
    "freeze_v32_environment_capability_profile_v1",
    "freeze_v32_authorized_revision_support_bundle_v1",
    "verify_v32_authorized_revision_cycle_registry_v1",
    "verify_v32_authorized_revision_cycle_registry_receipt_v1",
    "verify_v32_authorized_revision_support_bundle_v1",
    "verify_v32_revision_input_state_v1",
]
