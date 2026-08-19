"""Pure V3.2 analysis-cycle acceptance composition.

This module owns the final per-cycle acceptance receipt.  It performs no I/O,
network access, clock reads, Agent invocation, storage mutation, account access,
or execution.  Every supplied document is replayed through its owning public
verifier, and every supplied binding is checked against canonical document
bytes rather than trusted as an assertion.

The receipt is not an outcome receipt and never makes a fill, position, PnL,
prediction-quality, or profitability claim.  Persistence remains the
responsibility of a separate write-once Store.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .v32_agent_semantic_compiler import (
    PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD,
    PROPOSAL_COMPILE_RECEIPT_SCHEMA_ID,
    SELECTION_COMPILE_RECEIPT_DIGEST_FIELD,
    SELECTION_COMPILE_RECEIPT_SCHEMA_ID,
    V32AgentSemanticCompilerError,
    verify_v32_final_action_plan_exact_match_v1,
    verify_v32_proposal_semantic_compile_receipt_v1,
    verify_v32_selection_semantic_compile_receipt_v1,
)
from .v32_action_plan_continuity import (
    DIGEST_FIELD as ACTION_CONTINUITY_DIGEST_FIELD,
    SCHEMA_ID as ACTION_CONTINUITY_SCHEMA_ID,
    V32ActionPlanContinuityError,
    verify_v32_action_plan_continuity_v1,
)
from .v32_authorized_revision_orchestration import (
    CYCLE_REGISTRY_DIGEST_FIELD,
    CYCLE_REGISTRY_SCHEMA_ID,
    V32AuthorizedRevisionOrchestrationError,
    verify_v32_authorized_revision_cycle_registry_receipt_v1,
)
from .v32_dynamic_state_continuity import (
    GRAPH_REGISTRY_DIGEST_FIELD,
    GRAPH_REGISTRY_SCHEMA_ID,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
    PIT_AVAILABILITY_REGISTRY_SCHEMA_ID,
    RECEIPT_DIGEST_FIELD as STATE_CONTINUITY_DIGEST_FIELD,
    RECEIPT_SCHEMA_ID as STATE_CONTINUITY_SCHEMA_ID,
    V32DynamicStateContinuityError,
    verify_v32_dynamic_state_continuity_v1,
    verify_v32_verified_pit_evidence_availability_registry_v1,
)
from .v32_agent_market_graph_view import (
    verify_v32_agent_market_graph_view_v1,
)
from .v32_public_evidence_port import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    ANALYSIS_BUNDLE_SCHEMA_ID,
    GRAPH_PROJECTION_DIGEST_FIELD,
    GRAPH_PROJECTION_SCHEMA_ID,
    V32PublicEvidenceVerifierPort,
)
from .v32_shadow_decision_port import (
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    SHADOW_DECISION_BUNDLE_SCHEMA_ID,
    V32ShadowDecisionVerificationError,
    V32ShadowDecisionVerifierPort,
)
from .v32_durable_source_replay import (
    RECEIPT_DIGEST_FIELD as SOURCE_REPLAY_DIGEST_FIELD,
    RECEIPT_SCHEMA_ID as SOURCE_REPLAY_SCHEMA_ID,
    verify_v32_durable_source_replay_receipt,
)
from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.v32_agent_lifecycle import (
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONSUMPTION_SCHEMA_ID,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_DELIVERY_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    ACTION_EVALUATION_DIGEST_FIELD,
    ACTION_EVALUATION_SCHEMA_ID,
    COMMIT_ENVELOPE_DIGEST_FIELD,
    COMMIT_ENVELOPE_SCHEMA_ID,
    V32_TARGET_CONTEXT_PROFILE,
    V32AgentLifecycleError,
    verify_v32_agent_consumption_v1,
    verify_v32_agent_delivery_v1,
    verify_v32_agent_input_context_v1,
    resolve_v32_agent_canonical_packet_v1,
    verify_v32_action_evaluation_v1,
    verify_v32_two_stage_commit_envelope_v1,
    v32_lifecycle_verification_scope_v1,
)
from ..domain.v32_agent_market_graph_view import (
    DIGEST_FIELD as AGENT_MARKET_VIEW_DIGEST_FIELD,
    SCHEMA_ID as AGENT_MARKET_VIEW_SCHEMA_ID,
)
from ..domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION,
    SNAPSHOT_DIGEST_FIELD,
    SNAPSHOT_SCHEMA_ID,
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_VERSION,
    SOURCE_ADMISSION_SCHEMA_ID,
    AUTHORITY_PROJECTION_SCHEMA_ID,
    V32CycleSourceAdmissionError,
    verify_v32_cycle_source_admission,
    verify_v32_active_authority_projection,
    verify_v32_pit_evidence_registry,
)
from ..domain.v32_dynamic_action_plan import (
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    SCHEMA_ID as ACTION_PLAN_SCHEMA_ID,
)
from ..domain.v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    SCHEMA_ID as DYNAMIC_STATE_SCHEMA_ID,
    V32DynamicResearchError,
    verify_v32_dynamic_research_state_v1,
)
from ..domain.v32_outcome_tick import (
    HORIZON_POLICY,
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
    V32OutcomeTickError,
    verify_v32_outcome_schedule_set,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID,
    PERMIT_DIGEST_FIELD,
    PERMIT_SCHEMA_ID,
    V32TickSupervisorError,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_permit,
)
from ..domain.v32_timeframe_cache import (
    DIGEST_FIELD as TIMEFRAME_DIGEST_FIELD,
    SCHEMA_ID as TIMEFRAME_SCHEMA_ID,
    V32TimeframeCacheError,
    verify_v32_timeframe_invalidation_bindings_v1,
    verify_v32_timeframe_payload_bindings_v1,
    verify_v32_timeframe_production_policy_v1,
    verify_v32_timeframe_context_state_v1,
    verify_v32_timeframe_context_transition_v1,
)


class V32CycleAcceptanceError(ValueError):
    """One current-cycle component or durable binding failed closed."""


SCHEMA_VERSION = "1.0.0"
SCHEMA_ID = "theory_paper_v32_analysis_cycle_acceptance_receipt_v1"
DIGEST_FIELD = "analysis_cycle_acceptance_receipt_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
CLAIM = "PROCESS_ACCEPTANCE_ONLY_NO_OUTCOME_EXECUTION_OR_PROFIT_CLAIM"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)

COMPONENT_SPECS = MappingProxyType(
    {
        "analysis_tick_permit": (PERMIT_SCHEMA_ID, PERMIT_DIGEST_FIELD),
        "active_authority_projection": (
            AUTHORITY_PROJECTION_SCHEMA_ID,
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
        ),
        "cycle_source_admission": (
            SOURCE_ADMISSION_SCHEMA_ID,
            SOURCE_ADMISSION_DIGEST_FIELD,
        ),
        "public_market_analysis_bundle": (
            ANALYSIS_BUNDLE_SCHEMA_ID,
            ANALYSIS_BUNDLE_DIGEST_FIELD,
        ),
        "public_market_graph_projection": (
            GRAPH_PROJECTION_SCHEMA_ID,
            GRAPH_PROJECTION_DIGEST_FIELD,
        ),
        "pit_evidence_registry": (
            PIT_REGISTRY_SCHEMA_ID,
            PIT_REGISTRY_DIGEST_FIELD,
        ),
        "verified_graph_dependency_registry": (
            GRAPH_REGISTRY_SCHEMA_ID,
            GRAPH_REGISTRY_DIGEST_FIELD,
        ),
        "durable_source_replay_receipt": (
            SOURCE_REPLAY_SCHEMA_ID,
            SOURCE_REPLAY_DIGEST_FIELD,
        ),
        "verified_pit_evidence_availability_registry": (
            PIT_AVAILABILITY_REGISTRY_SCHEMA_ID,
            PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
        ),
        "agent_market_graph_view": (
            AGENT_MARKET_VIEW_SCHEMA_ID,
            AGENT_MARKET_VIEW_DIGEST_FIELD,
        ),
        "current_timeframe_context_state": (
            TIMEFRAME_SCHEMA_ID,
            TIMEFRAME_DIGEST_FIELD,
        ),
        "proposal_input_context": (
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        ),
        "proposal_delivery": (
            AGENT_DELIVERY_SCHEMA_ID,
            AGENT_DELIVERY_DIGEST_FIELD,
        ),
        "proposal_consumption": (
            AGENT_CONSUMPTION_SCHEMA_ID,
            AGENT_CONSUMPTION_DIGEST_FIELD,
        ),
        "proposal_semantic_compile_receipt": (
            PROPOSAL_COMPILE_RECEIPT_SCHEMA_ID,
            PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD,
        ),
        "compiled_dynamic_research_state": (
            DYNAMIC_STATE_SCHEMA_ID,
            DYNAMIC_STATE_DIGEST_FIELD,
        ),
        "sealed_action_evaluation": (
            ACTION_EVALUATION_SCHEMA_ID,
            ACTION_EVALUATION_DIGEST_FIELD,
        ),
        "replayable_shadow_decision_bundle": (
            SHADOW_DECISION_BUNDLE_SCHEMA_ID,
            SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
        ),
        "dynamic_state_continuity_receipt": (
            STATE_CONTINUITY_SCHEMA_ID,
            STATE_CONTINUITY_DIGEST_FIELD,
        ),
        "selection_input_context": (
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        ),
        "selection_delivery": (
            AGENT_DELIVERY_SCHEMA_ID,
            AGENT_DELIVERY_DIGEST_FIELD,
        ),
        "selection_consumption": (
            AGENT_CONSUMPTION_SCHEMA_ID,
            AGENT_CONSUMPTION_DIGEST_FIELD,
        ),
        "selection_semantic_compile_receipt": (
            SELECTION_COMPILE_RECEIPT_SCHEMA_ID,
            SELECTION_COMPILE_RECEIPT_DIGEST_FIELD,
        ),
        "final_dynamic_action_plan": (
            ACTION_PLAN_SCHEMA_ID,
            ACTION_PLAN_DIGEST_FIELD,
        ),
        "action_plan_continuity_receipt": (
            ACTION_CONTINUITY_SCHEMA_ID,
            ACTION_CONTINUITY_DIGEST_FIELD,
        ),
        "authorized_revision_cycle_registry": (
            CYCLE_REGISTRY_SCHEMA_ID,
            CYCLE_REGISTRY_DIGEST_FIELD,
        ),
        "two_stage_commit_envelope": (
            COMMIT_ENVELOPE_SCHEMA_ID,
            COMMIT_ENVELOPE_DIGEST_FIELD,
        ),
        "outcome_schedule_set": (
            SCHEDULE_SET_SCHEMA_ID,
            SCHEDULE_SET_DIGEST_FIELD,
        ),
    }
)

_REPLAY_SUPPORT_FIELDS = frozenset(
    {
        "permit_checkpoint_binding",
        "prior_outcome_schedule_set_bindings",
        "previous_timeframe_context_state_binding",
        "previous_public_market_graph_projection_binding",
        "previous_pit_evidence_availability_registry_binding",
        "continuity_replay_input_bindings",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_time",
        "accepted_at",
        "previous_accepted_receipt_digest",
        "previous_accepted_receipt_binding",
        "component_bindings",
        "component_bindings_digest",
        "replay_support_bindings",
        "replay_support_bindings_digest",
        "analysis_tick_permit_digest",
        "active_authority_projection_digest",
        "cycle_source_admission_digest",
        "public_market_analysis_bundle_digest",
        "public_market_graph_projection_digest",
        "pit_evidence_registry_digest",
        "verified_graph_dependency_registry_digest",
        "durable_source_replay_receipt_digest",
        "verified_pit_evidence_availability_registry_digest",
        "agent_market_graph_view_digest",
        "shadow_decision_bundle_digest",
        "accepted_market_snapshot_binding",
        "accepted_open_interest_datum_digest",
        "accepted_open_interest_status",
        "accepted_open_interest_zero_imputed",
        "timeframe_context_state_digest",
        "proposal_lifecycle_digest",
        "proposal_semantic_compile_receipt_digest",
        "dynamic_state_continuity_receipt_digest",
        "selection_lifecycle_digest",
        "selection_semantic_compile_receipt_digest",
        "accepted_dynamic_research_state_digest",
        "final_dynamic_action_plan_digest",
        "action_plan_continuity_receipt_digest",
        "authorized_revision_cycle_registry_digest",
        "two_stage_commit_envelope_digest",
        "outcome_schedule_set_digest",
        "single_source_collection_transaction",
        "proposal_attempt_count",
        "selection_attempt_count",
        "current_outcome_present",
        "account_state_present",
        "order_state_present",
        "fill_state_present",
        "pnl_state_present",
        "acceptance_status",
        "source_scope",
        "external_execution_authority",
        "executable",
        "claim",
        DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32CycleAcceptanceError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32CycleAcceptanceError(code)
    return value


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
        raise V32CycleAcceptanceError("V32_CYCLE_ACCEPTANCE_CYCLE_INVALID")
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32CycleAcceptanceError(code) from exc
    if parsed.tzinfo is None:
        raise V32CycleAcceptanceError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32CycleAcceptanceError(code)
    return canonical


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _relative_ref(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise V32CycleAcceptanceError(code)
    return text


def _physical_sha(document: Mapping[str, Any]) -> str:
    try:
        return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_CANONICAL_BYTES_INVALID"
        ) from exc


def _strict_binding(
    *,
    document: Mapping[str, Any],
    binding: Mapping[str, Any],
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
    code: str,
) -> dict[str, str]:
    if (
        not isinstance(document, Mapping)
        or not isinstance(binding, Mapping)
        or set(binding) != _BINDING_FIELDS
    ):
        raise V32CycleAcceptanceError(code)
    normalized = {
        "relative_ref": _relative_ref(binding.get("relative_ref"), code),
        "schema_id": _text(binding.get("schema_id"), code),
        "digest_field": _text(binding.get("digest_field"), code),
        "semantic_digest": str(_digest(binding.get("semantic_digest"), code)),
        "physical_sha256": str(_digest(binding.get("physical_sha256"), code)),
    }
    if (
        document.get("schema_id") != schema_id
        or normalized["schema_id"] != schema_id
        or normalized["digest_field"] != digest_field
        or normalized["semantic_digest"] != semantic_digest
        or normalized["physical_sha256"] != _physical_sha(document)
    ):
        raise V32CycleAcceptanceError(code)
    return normalized


def _same_artifact_identity(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> bool:
    """Compare immutable artifact identity while allowing store-local refs."""

    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    return all(
        left.get(field) == right.get(field)
        for field in (
            "schema_id",
            "digest_field",
            "semantic_digest",
            "physical_sha256",
        )
    )


def _validate_receipt_intrinsic(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        ) from exc
    cycle = _cycle(document.get("cycle_index"))
    component_bindings = document.get("component_bindings")
    replay_support = document.get("replay_support_bindings")
    if (
        not isinstance(component_bindings, Mapping)
        or set(component_bindings) != set(COMPONENT_SPECS)
        or canonical_digest(component_bindings)
        != document.get("component_bindings_digest")
        or not isinstance(replay_support, Mapping)
        or set(replay_support) != _REPLAY_SUPPORT_FIELDS
        or canonical_digest(replay_support)
        != document.get("replay_support_bindings_digest")
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    for role, (schema_id, digest_field) in COMPONENT_SPECS.items():
        binding = component_bindings.get(role)
        if (
            not isinstance(binding, Mapping)
            or set(binding) != _BINDING_FIELDS
            or binding.get("schema_id") != schema_id
            or binding.get("digest_field") != digest_field
        ):
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
            )
        _relative_ref(
            binding.get("relative_ref"),
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID",
        )
        _digest(
            binding.get("semantic_digest"),
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID",
        )
        _digest(
            binding.get("physical_sha256"),
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID",
        )
    previous_receipt_digest = _digest(
        document.get("previous_accepted_receipt_digest"),
        "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID",
        nullable=True,
    )
    previous_receipt_binding = document.get("previous_accepted_receipt_binding")
    if cycle == 1:
        if previous_receipt_digest is not None or previous_receipt_binding is not None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
            )
    elif (
        previous_receipt_digest is None
        or not isinstance(previous_receipt_binding, Mapping)
        or set(previous_receipt_binding) != _BINDING_FIELDS
        or previous_receipt_binding.get("schema_id") != SCHEMA_ID
        or previous_receipt_binding.get("digest_field") != DIGEST_FIELD
        or previous_receipt_binding.get("semantic_digest")
        != previous_receipt_digest
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    permit_checkpoint_binding = replay_support.get("permit_checkpoint_binding")
    if (
        not isinstance(permit_checkpoint_binding, Mapping)
        or set(permit_checkpoint_binding) != _BINDING_FIELDS
        or permit_checkpoint_binding.get("schema_id") != CHECKPOINT_SCHEMA_ID
        or permit_checkpoint_binding.get("digest_field") != CHECKPOINT_DIGEST_FIELD
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    prior_schedule_bindings = replay_support.get(
        "prior_outcome_schedule_set_bindings"
    )
    if (
        isinstance(prior_schedule_bindings, (str, bytes))
        or not isinstance(prior_schedule_bindings, Sequence)
        or any(
            not isinstance(binding, Mapping)
            or set(binding) != _BINDING_FIELDS
            or binding.get("schema_id") != SCHEDULE_SET_SCHEMA_ID
            or binding.get("digest_field") != SCHEDULE_SET_DIGEST_FIELD
            for binding in prior_schedule_bindings
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    previous_timeframe_binding = replay_support.get(
        "previous_timeframe_context_state_binding"
    )
    if (previous_timeframe_binding is None) != (cycle == 1) or (
        previous_timeframe_binding is not None
        and (
            not isinstance(previous_timeframe_binding, Mapping)
            or set(previous_timeframe_binding) != _BINDING_FIELDS
            or previous_timeframe_binding.get("schema_id") != TIMEFRAME_SCHEMA_ID
            or previous_timeframe_binding.get("digest_field")
            != TIMEFRAME_DIGEST_FIELD
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    previous_projection_binding = replay_support.get(
        "previous_public_market_graph_projection_binding"
    )
    if (previous_projection_binding is None) != (cycle == 1) or (
        previous_projection_binding is not None
        and (
            not isinstance(previous_projection_binding, Mapping)
            or set(previous_projection_binding) != _BINDING_FIELDS
            or previous_projection_binding.get("schema_id")
            != GRAPH_PROJECTION_SCHEMA_ID
            or previous_projection_binding.get("digest_field")
            != GRAPH_PROJECTION_DIGEST_FIELD
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    previous_availability_binding = replay_support.get(
        "previous_pit_evidence_availability_registry_binding"
    )
    if (previous_availability_binding is None) != (cycle == 1) or (
        previous_availability_binding is not None
        and (
            not isinstance(previous_availability_binding, Mapping)
            or set(previous_availability_binding) != _BINDING_FIELDS
            or previous_availability_binding.get("schema_id")
            != PIT_AVAILABILITY_REGISTRY_SCHEMA_ID
            or previous_availability_binding.get("digest_field")
            != PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    continuity_bindings = replay_support.get("continuity_replay_input_bindings")
    if not isinstance(continuity_bindings, Mapping) or set(
        continuity_bindings
    ) != {
        "durable_previous_dynamic_research_state_binding",
        "durable_previous_dynamic_action_plan_binding",
        "pit_evidence_registry_binding",
        "pit_evidence_availability_registry_binding",
        "graph_dependency_registry_binding",
    }:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    prior_pairs = (
        (
            continuity_bindings[
                "durable_previous_dynamic_research_state_binding"
            ],
            DYNAMIC_STATE_SCHEMA_ID,
            DYNAMIC_STATE_DIGEST_FIELD,
        ),
        (
            continuity_bindings[
                "durable_previous_dynamic_action_plan_binding"
            ],
            ACTION_PLAN_SCHEMA_ID,
            ACTION_PLAN_DIGEST_FIELD,
        ),
    )
    if any((binding is None) != (cycle == 1) for binding, _, _ in prior_pairs):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    required_replay_bindings = (
        *[pair for pair in prior_pairs if pair[0] is not None],
        (
            continuity_bindings["pit_evidence_registry_binding"],
            PIT_REGISTRY_SCHEMA_ID,
            PIT_REGISTRY_DIGEST_FIELD,
        ),
        (
            continuity_bindings["graph_dependency_registry_binding"],
            GRAPH_REGISTRY_SCHEMA_ID,
            GRAPH_REGISTRY_DIGEST_FIELD,
        ),
        (
            continuity_bindings[
                "pit_evidence_availability_registry_binding"
            ],
            PIT_AVAILABILITY_REGISTRY_SCHEMA_ID,
            PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
        ),
    )
    for binding, schema_id, digest_field in required_replay_bindings:
        if (
            not isinstance(binding, Mapping)
            or set(binding) != _BINDING_FIELDS
            or binding.get("schema_id") != schema_id
            or binding.get("digest_field") != digest_field
        ):
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
            )
    snapshot_binding = document.get("accepted_market_snapshot_binding")
    if (
        not isinstance(snapshot_binding, Mapping)
        or set(snapshot_binding) != _BINDING_FIELDS
        or snapshot_binding.get("schema_id") != SNAPSHOT_SCHEMA_ID
        or snapshot_binding.get("digest_field") != SNAPSHOT_DIGEST_FIELD
        or document.get("accepted_open_interest_status")
        not in {"OBSERVED", "UNKNOWN"}
        or document.get("accepted_open_interest_zero_imputed") is not False
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    _digest(
        document.get("accepted_open_interest_datum_digest"),
        "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID",
    )
    direct_digest_bindings = {
        "analysis_tick_permit_digest": "analysis_tick_permit",
        "active_authority_projection_digest": "active_authority_projection",
        "cycle_source_admission_digest": "cycle_source_admission",
        "public_market_analysis_bundle_digest": (
            "public_market_analysis_bundle"
        ),
        "public_market_graph_projection_digest": (
            "public_market_graph_projection"
        ),
        "pit_evidence_registry_digest": "pit_evidence_registry",
        "verified_graph_dependency_registry_digest": (
            "verified_graph_dependency_registry"
        ),
        "durable_source_replay_receipt_digest": (
            "durable_source_replay_receipt"
        ),
        "verified_pit_evidence_availability_registry_digest": (
            "verified_pit_evidence_availability_registry"
        ),
        "agent_market_graph_view_digest": "agent_market_graph_view",
        "shadow_decision_bundle_digest": (
            "replayable_shadow_decision_bundle"
        ),
        "timeframe_context_state_digest": "current_timeframe_context_state",
        "proposal_semantic_compile_receipt_digest": (
            "proposal_semantic_compile_receipt"
        ),
        "dynamic_state_continuity_receipt_digest": (
            "dynamic_state_continuity_receipt"
        ),
        "selection_semantic_compile_receipt_digest": (
            "selection_semantic_compile_receipt"
        ),
        "accepted_dynamic_research_state_digest": (
            "compiled_dynamic_research_state"
        ),
        "final_dynamic_action_plan_digest": "final_dynamic_action_plan",
        "action_plan_continuity_receipt_digest": (
            "action_plan_continuity_receipt"
        ),
        "two_stage_commit_envelope_digest": "two_stage_commit_envelope",
        "outcome_schedule_set_digest": "outcome_schedule_set",
    }
    if any(
        document.get(field) != component_bindings[role]["semantic_digest"]
        for field, role in direct_digest_bindings.items()
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    if (
        document.get("schema_id") != SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("acceptance_status")
        != "ACCEPTED_SINGLE_ANALYSIS_CYCLE_WRITE_ONCE_REQUIRED"
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
        or document.get("claim") != CLAIM
        or document.get("single_source_collection_transaction") is not True
        or document.get("proposal_attempt_count") != 1
        or document.get("selection_attempt_count") != 1
        or any(
            document.get(field) is not False
            for field in (
                "current_outcome_present",
                "account_state_present",
                "order_state_present",
                "fill_state_present",
                "pnl_state_present",
            )
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PREVIOUS_RECEIPT_INVALID"
        )
    return supplied


def _stage_lifecycle_digest(
    *, context_digest: str, delivery_digest: str, consumption_digest: str
) -> str:
    return canonical_digest(
        {
            "agent_input_context_digest": context_digest,
            "agent_delivery_digest": delivery_digest,
            "agent_consumption_digest": consumption_digest,
        }
    )


def _replay_components(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    shadow_decision_verifier: V32ShadowDecisionVerifierPort,
    components: Mapping[str, Mapping[str, Any]],
    permit_checkpoint: Mapping[str, Any],
    prior_outcome_schedule_sets: Sequence[Mapping[str, Any]],
    previous_timeframe_context_state: Mapping[str, Any] | None,
    previous_public_market_graph_projection: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry: Mapping[str, Any] | None,
    previous_accepted_receipt: Mapping[str, Any] | None,
    proposal_lossless_context_package: Mapping[str, Any] | None,
    selection_lossless_context_package: Mapping[str, Any] | None,
) -> dict[str, str]:
    if not isinstance(components, Mapping) or set(components) != set(COMPONENT_SPECS):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_COMPONENT_SET_INVALID"
        )
    try:
        checkpoint_digest = verify_v32_tick_supervisor_checkpoint(permit_checkpoint)
        prior_schedule_digests = [
            verify_v32_outcome_schedule_set(document)
            for document in prior_outcome_schedule_sets
        ]
        permit_digest = verify_v32_tick_supervisor_permit(
            components["analysis_tick_permit"],
            checkpoint=permit_checkpoint,
            schedule_sets=prior_outcome_schedule_sets,
        )
        authority_projection_digest = verify_v32_active_authority_projection(
            components["active_authority_projection"]
        )
        source_digest = verify_v32_cycle_source_admission(
            components["cycle_source_admission"]
        )
        analysis_bundle_digest = public_evidence_verifier.verify_public_market_analysis_bundle(
            components["public_market_analysis_bundle"]
        )
        graph_projection_digest = (
            public_evidence_verifier.verify_public_market_graph_projection(
                components["public_market_graph_projection"],
                analysis_bundle=components["public_market_analysis_bundle"],
                previous_projection=previous_public_market_graph_projection,
            )
        )
        pit_registry_digest = verify_v32_pit_evidence_registry(
            components["pit_evidence_registry"]
        )
        graph_registry_digest = (
            public_evidence_verifier.verify_graph_dependency_registry(
                components["verified_graph_dependency_registry"],
                graph_projection=components["public_market_graph_projection"],
                analysis_bundle=components["public_market_analysis_bundle"],
                previous_projection=previous_public_market_graph_projection,
            )
        )
        source_replay_digest = verify_v32_durable_source_replay_receipt(
            components["durable_source_replay_receipt"]
        )
        availability_digest = (
            verify_v32_verified_pit_evidence_availability_registry_v1(
                components["verified_pit_evidence_availability_registry"],
                public_evidence_verifier=public_evidence_verifier,
                public_market_analysis_bundle=components[
                    "public_market_analysis_bundle"
                ],
                pit_evidence_registry=components["pit_evidence_registry"],
            )
        )
        market_view_digest = verify_v32_agent_market_graph_view_v1(
            components["agent_market_graph_view"],
            public_evidence_verifier=public_evidence_verifier,
            public_market_analysis_bundle=components[
                "public_market_analysis_bundle"
            ],
            public_market_graph_projection=components[
                "public_market_graph_projection"
            ],
            pit_evidence_registry=components["pit_evidence_registry"],
            graph_dependency_registry=components[
                "verified_graph_dependency_registry"
            ],
            pit_evidence_availability_registry=components[
                "verified_pit_evidence_availability_registry"
            ],
            previous_public_market_graph_projection=(
                previous_public_market_graph_projection
            ),
        )
        cycle = components["analysis_tick_permit"]["analysis_cycle_index"]
        if cycle == 1:
            if previous_timeframe_context_state is not None:
                raise V32CycleAcceptanceError(
                    "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID"
                )
            timeframe_digest = verify_v32_timeframe_context_state_v1(
                components["current_timeframe_context_state"]
            )
        else:
            if previous_timeframe_context_state is None:
                raise V32CycleAcceptanceError(
                    "V32_CYCLE_ACCEPTANCE_PREVIOUS_TIMEFRAME_REQUIRED"
                )
            timeframe_digest = verify_v32_timeframe_context_transition_v1(
                previous_state=previous_timeframe_context_state,
                current_state=components["current_timeframe_context_state"],
            )
        verify_v32_timeframe_payload_bindings_v1(
            timeframe_context_state=components["current_timeframe_context_state"],
            public_market_analysis_bundle=components[
                "public_market_analysis_bundle"
            ],
        )
        verify_v32_timeframe_production_policy_v1(
            timeframe_context_state=components["current_timeframe_context_state"],
            public_market_analysis_bundle=components[
                "public_market_analysis_bundle"
            ],
        )
        verify_v32_timeframe_invalidation_bindings_v1(
            timeframe_context_state=components["current_timeframe_context_state"],
            public_market_analysis_bundle=components[
                "public_market_analysis_bundle"
            ],
            previous_state=previous_timeframe_context_state,
        )

        proposal_context_digest = verify_v32_agent_input_context_v1(
            components["proposal_input_context"],
            lossless_context_package=proposal_lossless_context_package,
        )
        proposal_delivery_digest = verify_v32_agent_delivery_v1(
            components["proposal_delivery"],
            agent_input_context=components["proposal_input_context"],
        )
        proposal_consumption_digest = verify_v32_agent_consumption_v1(
            components["proposal_consumption"],
            agent_input_context=components["proposal_input_context"],
            agent_delivery=components["proposal_delivery"],
        )
        proposal_semantic_digest = (
            verify_v32_proposal_semantic_compile_receipt_v1(
                components["proposal_semantic_compile_receipt"],
                proposal_input_context=components["proposal_input_context"],
                proposal_delivery=components["proposal_delivery"],
                proposal_consumption=components["proposal_consumption"],
                proposal_lossless_context_package=(
                    proposal_lossless_context_package
                ),
            )
        )
        current_state_digest = verify_v32_dynamic_research_state_v1(
            components["compiled_dynamic_research_state"]
        )
        action_evaluation_digest = verify_v32_action_evaluation_v1(
            components["sealed_action_evaluation"]
        )

        proposal_packet = resolve_v32_agent_canonical_packet_v1(
            components["proposal_input_context"],
            lossless_context_package=proposal_lossless_context_package,
        )
        previous_state_digest = (
            None
            if previous_accepted_receipt is None
            else previous_accepted_receipt[
                "accepted_dynamic_research_state_digest"
            ]
        )
        previous_plan_digest = (
            None
            if previous_accepted_receipt is None
            else previous_accepted_receipt["final_dynamic_action_plan_digest"]
        )
        state_continuity_digest = verify_v32_dynamic_state_continuity_v1(
            components["dynamic_state_continuity_receipt"],
            public_evidence_verifier=public_evidence_verifier,
            current_state=components["compiled_dynamic_research_state"],
            durable_previous_state=proposal_packet[
                "previous_dynamic_research_state"
            ],
            durable_previous_state_digest=previous_state_digest,
            verified_pit_evidence_registry=components["pit_evidence_registry"],
            verified_pit_evidence_registry_digest=pit_registry_digest,
            verified_public_market_analysis_bundle=components[
                "public_market_analysis_bundle"
            ],
            verified_pit_evidence_availability_registry=components[
                "verified_pit_evidence_availability_registry"
            ],
            verified_pit_evidence_availability_registry_digest=availability_digest,
            durable_previous_pit_evidence_availability_registry=(
                previous_pit_evidence_availability_registry
            ),
            durable_previous_pit_evidence_availability_registry_digest=(
                None
                if previous_pit_evidence_availability_registry is None
                else previous_pit_evidence_availability_registry[
                    PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
                ]
            ),
            verified_graph_dependency_registry=components[
                "verified_graph_dependency_registry"
            ],
            verified_graph_dependency_registry_digest=graph_registry_digest,
        )

        selection_context_digest = verify_v32_agent_input_context_v1(
            components["selection_input_context"],
            lossless_context_package=selection_lossless_context_package,
        )
        selection_delivery_digest = verify_v32_agent_delivery_v1(
            components["selection_delivery"],
            agent_input_context=components["selection_input_context"],
        )
        selection_consumption_digest = verify_v32_agent_consumption_v1(
            components["selection_consumption"],
            agent_input_context=components["selection_input_context"],
            agent_delivery=components["selection_delivery"],
        )
        selection_semantic_digest = (
            verify_v32_selection_semantic_compile_receipt_v1(
                components["selection_semantic_compile_receipt"],
                proposal_compile_receipt=components[
                    "proposal_semantic_compile_receipt"
                ],
                selection_input_context=components["selection_input_context"],
                selection_delivery=components["selection_delivery"],
                selection_consumption=components["selection_consumption"],
                selection_lossless_context_package=(
                    selection_lossless_context_package
                ),
                proposal_lossless_context_package=(
                    proposal_lossless_context_package
                ),
            )
        )
        final_plan_digest = verify_v32_final_action_plan_exact_match_v1(
            components["final_dynamic_action_plan"],
            selection_consumption_digest=selection_consumption_digest,
            proposal_compile_receipt=components[
                "proposal_semantic_compile_receipt"
            ],
            selection_compile_receipt=components[
                "selection_semantic_compile_receipt"
            ],
            selection_input_context=components["selection_input_context"],
            selection_delivery=components["selection_delivery"],
            selection_consumption=components["selection_consumption"],
            selection_lossless_context_package=(
                selection_lossless_context_package
            ),
            proposal_lossless_context_package=(
                proposal_lossless_context_package
            ),
        )
        shadow_decision_digest = (
            shadow_decision_verifier.verify_replayable_shadow_decision_bundle(
                components["replayable_shadow_decision_bundle"],
                public_market_analysis_bundle=components[
                    "public_market_analysis_bundle"
                ],
                public_market_analysis_bundle_binding=components[
                    "replayable_shadow_decision_bundle"
                ]["market_analysis_binding"],
                pit_evidence_registry=components["pit_evidence_registry"],
                pit_evidence_registry_binding=components[
                    "replayable_shadow_decision_bundle"
                ]["pit_registry_binding"],
                sealed_action_evaluation=components["sealed_action_evaluation"],
                sealed_action_evaluation_binding=components[
                    "replayable_shadow_decision_bundle"
                ]["opportunity_set_binding"],
                dynamic_research_state=components[
                    "compiled_dynamic_research_state"
                ],
                selected_plan=components["final_dynamic_action_plan"],
                selected_plan_binding=components[
                    "replayable_shadow_decision_bundle"
                ][
                    "selected_plan_binding"
                ],
            )
        )
        action_continuity_digest = verify_v32_action_plan_continuity_v1(
            components["action_plan_continuity_receipt"],
            current_dynamic_state=components["compiled_dynamic_research_state"],
            current_action_plan=components["final_dynamic_action_plan"],
            durable_previous_dynamic_state=proposal_packet[
                "previous_dynamic_research_state"
            ],
            durable_previous_dynamic_state_digest=previous_state_digest,
            durable_previous_action_plan=proposal_packet[
                "previous_dynamic_action_plan"
            ],
            durable_previous_action_plan_digest=previous_plan_digest,
        )
        authorized_revision_registry_digest = (
            verify_v32_authorized_revision_cycle_registry_receipt_v1(
                components["authorized_revision_cycle_registry"]
            )
        )
        schedule_digest = verify_v32_outcome_schedule_set(
            components["outcome_schedule_set"]
        )
        commit_digest = verify_v32_two_stage_commit_envelope_v1(
            components["two_stage_commit_envelope"],
            proposal_input_context=components["proposal_input_context"],
            proposal_delivery=components["proposal_delivery"],
            proposal_consumption=components["proposal_consumption"],
            selection_input_context=components["selection_input_context"],
            selection_delivery=components["selection_delivery"],
            selection_consumption=components["selection_consumption"],
            proposal_lossless_context_package=(
                proposal_lossless_context_package
            ),
            selection_lossless_context_package=(
                selection_lossless_context_package
            ),
        )
    except V32CycleAcceptanceError:
        raise
    except (
        V32AgentLifecycleError,
        V32AgentSemanticCompilerError,
        V32ActionPlanContinuityError,
        V32AuthorizedRevisionOrchestrationError,
        V32CycleSourceAdmissionError,
        V32DynamicResearchError,
        V32DynamicStateContinuityError,
        V32OutcomeTickError,
        V32TickSupervisorError,
        V32TimeframeCacheError,
        V32ShadowDecisionVerificationError,
        CanonicalContractError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_COMPONENT_REPLAY_INVALID"
        ) from exc
    if len(set(prior_schedule_digests)) != len(prior_schedule_digests):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PRIOR_SCHEDULE_DUPLICATE"
        )
    return {
        "permit_checkpoint": checkpoint_digest,
        "analysis_tick_permit": permit_digest,
        "active_authority_projection": authority_projection_digest,
        "cycle_source_admission": source_digest,
        "public_market_analysis_bundle": analysis_bundle_digest,
        "public_market_graph_projection": graph_projection_digest,
        "pit_evidence_registry": pit_registry_digest,
        "verified_graph_dependency_registry": graph_registry_digest,
        "durable_source_replay_receipt": source_replay_digest,
        "verified_pit_evidence_availability_registry": availability_digest,
        "agent_market_graph_view": market_view_digest,
        "current_timeframe_context_state": timeframe_digest,
        "proposal_input_context": proposal_context_digest,
        "proposal_delivery": proposal_delivery_digest,
        "proposal_consumption": proposal_consumption_digest,
        "proposal_semantic_compile_receipt": proposal_semantic_digest,
        "compiled_dynamic_research_state": current_state_digest,
        "sealed_action_evaluation": action_evaluation_digest,
        "replayable_shadow_decision_bundle": shadow_decision_digest,
        "dynamic_state_continuity_receipt": state_continuity_digest,
        "selection_input_context": selection_context_digest,
        "selection_delivery": selection_delivery_digest,
        "selection_consumption": selection_consumption_digest,
        "selection_semantic_compile_receipt": selection_semantic_digest,
        "final_dynamic_action_plan": final_plan_digest,
        "action_plan_continuity_receipt": action_continuity_digest,
        "authorized_revision_cycle_registry": (
            authorized_revision_registry_digest
        ),
        "two_stage_commit_envelope": commit_digest,
        "outcome_schedule_set": schedule_digest,
    }


def _cross_validate(
    *,
    components: Mapping[str, Mapping[str, Any]],
    digests: Mapping[str, str],
    permit_checkpoint: Mapping[str, Any],
    previous_timeframe_context_state: Mapping[str, Any] | None,
    previous_public_market_graph_projection: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry: Mapping[str, Any] | None,
    previous_accepted_receipt: Mapping[str, Any] | None,
    accepted_at: str,
    proposal_lossless_context_package: Mapping[str, Any] | None,
    selection_lossless_context_package: Mapping[str, Any] | None,
) -> tuple[str, int, str, str | None]:
    permit = components["analysis_tick_permit"]
    authority_projection = components["active_authority_projection"]
    source = components["cycle_source_admission"]
    analysis_bundle = components["public_market_analysis_bundle"]
    graph_projection = components["public_market_graph_projection"]
    pit_registry = components["pit_evidence_registry"]
    graph_registry = components["verified_graph_dependency_registry"]
    source_replay = components["durable_source_replay_receipt"]
    availability_registry = components[
        "verified_pit_evidence_availability_registry"
    ]
    market_view = components["agent_market_graph_view"]
    timeframe = components["current_timeframe_context_state"]
    proposal_context = components["proposal_input_context"]
    proposal_delivery = components["proposal_delivery"]
    proposal_consumption = components["proposal_consumption"]
    proposal_receipt = components["proposal_semantic_compile_receipt"]
    current_state = components["compiled_dynamic_research_state"]
    action_evaluation = components["sealed_action_evaluation"]
    state_continuity = components["dynamic_state_continuity_receipt"]
    selection_context = components["selection_input_context"]
    selection_delivery = components["selection_delivery"]
    selection_consumption = components["selection_consumption"]
    selection_receipt = components["selection_semantic_compile_receipt"]
    final_plan = components["final_dynamic_action_plan"]
    action_continuity = components["action_plan_continuity_receipt"]
    authorized_revision_registry = components[
        "authorized_revision_cycle_registry"
    ]
    commit = components["two_stage_commit_envelope"]
    schedule = components["outcome_schedule_set"]
    shadow_decision = components["replayable_shadow_decision_bundle"]
    proposal_packet = resolve_v32_agent_canonical_packet_v1(
        proposal_context,
        lossless_context_package=proposal_lossless_context_package,
    )
    selection_packet = resolve_v32_agent_canonical_packet_v1(
        selection_context,
        lossless_context_package=selection_lossless_context_package,
    )
    run_id = _text(permit.get("run_id"), "V32_CYCLE_ACCEPTANCE_IDENTITY_INVALID")
    cycle = _cycle(permit.get("analysis_cycle_index"))
    decision_time = _time(
        permit.get("analysis_decision_at"),
        "V32_CYCLE_ACCEPTANCE_DECISION_TIME_INVALID",
    )
    decision_sealed_at = _time(
        selection_receipt.get("compiled_at"),
        "V32_CYCLE_ACCEPTANCE_DECISION_SEALED_TIME_INVALID",
    )
    accepted = _time(accepted_at, "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
    if not (
        _moment(decision_time, "V32_CYCLE_ACCEPTANCE_DECISION_TIME_INVALID")
        <= _moment(
            decision_sealed_at,
            "V32_CYCLE_ACCEPTANCE_DECISION_SEALED_TIME_INVALID",
        )
        <= _moment(accepted, "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_DECISION_SEALED_TIME_INVALID"
        )
    source_schema_version = source.get("schema_version")
    if source_schema_version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION:
        expected_schedule_decision_time = decision_time
    elif source_schema_version == SOURCE_ADMISSION_SCHEMA_VERSION:
        if source.get("source_cutoff_at") != decision_time:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_SOURCE_CUTOFF_INVALID"
            )
        expected_schedule_decision_time = decision_sealed_at
    else:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_SOURCE_SCHEMA_VERSION_INVALID"
        )
    expected_horizons = [horizon for horizon, _ in HORIZON_POLICY]
    actual_horizons = [row.get("horizon") for row in schedule.get("schedules", ())]
    previous_digest: str | None = None
    if cycle == 1:
        if (
            previous_accepted_receipt is not None
            or previous_public_market_graph_projection is not None
            or previous_pit_evidence_availability_registry is not None
        ):
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID"
            )
    else:
        if previous_accepted_receipt is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_REQUIRED"
            )
        previous_digest = _validate_receipt_intrinsic(previous_accepted_receipt)
        previous_components = previous_accepted_receipt["component_bindings"]
        if (
            previous_accepted_receipt.get("run_id") != run_id
            or previous_accepted_receipt.get("cycle_index") != cycle - 1
            or previous_timeframe_context_state is None
            or previous_public_market_graph_projection is None
            or previous_pit_evidence_availability_registry is None
            or permit.get("timeframe_cache_digest")
            != previous_components["current_timeframe_context_state"][
                "semantic_digest"
            ]
            or permit.get("prior_dynamic_state_digest")
            != previous_accepted_receipt[
                "accepted_dynamic_research_state_digest"
            ]
            or proposal_packet["previous_dynamic_research_state_binding"]
            != previous_components["compiled_dynamic_research_state"]
            or proposal_packet["previous_dynamic_action_plan_binding"]
            != previous_components["final_dynamic_action_plan"]
            or proposal_packet["previous_timeframe_context_state_binding"]
            != previous_components["current_timeframe_context_state"]
            or proposal_packet["previous_timeframe_context_state"]
            != previous_timeframe_context_state
            or state_continuity.get("durable_previous_state_digest")
            != previous_accepted_receipt[
                "accepted_dynamic_research_state_digest"
            ]
            or action_continuity.get("previous_dynamic_state_digest")
            != previous_accepted_receipt[
                "accepted_dynamic_research_state_digest"
            ]
            or action_continuity.get("previous_action_plan_digest")
            != previous_accepted_receipt["final_dynamic_action_plan_digest"]
            or permit.get("prior_source_admission_digest")
            != previous_components["cycle_source_admission"]["semantic_digest"]
            or permit.get("prior_source_admission_physical_sha256")
            != previous_components["cycle_source_admission"]["physical_sha256"]
            or source["previous_source_context"][
                "previous_cycle_source_admission_binding"
            ]
            != previous_components["cycle_source_admission"]
            or source["previous_source_context"]["prior_snapshot_binding"]
            != previous_accepted_receipt["accepted_market_snapshot_binding"]
            or source["previous_source_context"][
                "prior_open_interest_datum_digest"
            ]
            != previous_accepted_receipt["accepted_open_interest_datum_digest"]
            or source["previous_source_context"]["prior_open_interest_status"]
            != previous_accepted_receipt["accepted_open_interest_status"]
            or source["previous_source_context"][
                "prior_open_interest_zero_imputed"
            ]
            != previous_accepted_receipt[
                "accepted_open_interest_zero_imputed"
            ]
            or timeframe.get("previous_state_digest")
            != previous_components["current_timeframe_context_state"][
                "semantic_digest"
            ]
            or commit.get("previous_commit_envelope_digest")
            != previous_components["two_stage_commit_envelope"][
                "semantic_digest"
            ]
            or graph_projection.get("previous_graph_projection_digest")
            != previous_components["public_market_graph_projection"][
                "semantic_digest"
            ]
            or previous_public_market_graph_projection.get(
                GRAPH_PROJECTION_DIGEST_FIELD
            )
            != previous_components["public_market_graph_projection"][
                "semantic_digest"
            ]
            or previous_pit_evidence_availability_registry.get(
                PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
            )
            != previous_components[
                "verified_pit_evidence_availability_registry"
            ]["semantic_digest"]
        ):
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_CHAIN_INVALID"
            )

    support_documents = proposal_packet["support_documents"]
    support_bindings = proposal_packet["support_bindings"]
    experiment_contract = support_documents["experiment_contract"]
    inactivity_policy = experiment_contract.get("inactivity_policy", {})
    watchdog = final_plan.get("inactivity_opportunity_watchdog", {})
    current_receipts = [
        row
        for row in proposal_packet["matured_outcome_receipts"]
        if row.get("cycle_index") == cycle
    ]
    if (
        permit.get("permit_kind") != "ANALYSIS_TICK"
        or permit.get("agent_stage_attempt_limits")
        != {"PROPOSAL": 1, "SELECTION": 1}
        or permit.get("source_collection_transactions_allowed") != 1
        or permit.get("single_state_change_boundary") is not True
        or permit_checkpoint.get("run_id") != run_id
        or source.get("run_id") != run_id
        or source.get("cycle_index") != cycle
        or source.get("decision_time") != decision_time
        or source.get("single_source_collection_transaction") is not True
        or source.get("attempt_count") != 1
        or source.get("retry_allowed") is not False
        or authority_projection.get("authorized_run_id") != run_id
        or source.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != digests["active_authority_projection"]
        or analysis_bundle.get("run_id") != run_id
        or analysis_bundle.get("cycle_index") != cycle
        or graph_projection.get("run_id") != run_id
        or graph_projection.get("cycle_index") != cycle
        or graph_projection.get("analysis_bundle_digest")
        != digests["public_market_analysis_bundle"]
        or pit_registry.get("run_id") != run_id
        or pit_registry.get("cycle_index") != cycle
        or digests["public_market_analysis_bundle"]
        not in pit_registry.get("members", ())
        or graph_registry.get("run_id") != run_id
        or graph_registry.get("cycle_index") != cycle
        or graph_registry.get("as_of") != decision_time
        or graph_registry.get("upstream_semantic_digest")
        != digests["public_market_graph_projection"]
        or source_replay.get("run_id") != run_id
        or source_replay.get("cycle_index") != cycle
        or source_replay.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != permit.get("active_authority_digest")
        or source_replay.get("experiment_contract_digest")
        != permit.get("experiment_contract_digest")
        or source_replay.get("physical_replay_verified") is not True
        or source_replay.get("semantic_replay_verified") is not True
        or source_replay.get("point_in_time_verified") is not True
        or source_replay.get("analysis_bundle_digest_is_pit_member") is not True
        or source_replay.get("replay_network_calls") != 0
        or availability_registry.get("run_id") != run_id
        or availability_registry.get("cycle_index") != cycle
        or availability_registry.get("pit_evidence_registry_digest")
        != digests["pit_evidence_registry"]
        or availability_registry.get("public_market_analysis_bundle_digest")
        != digests["public_market_analysis_bundle"]
        or market_view.get("run_id") != run_id
        or market_view.get("cycle_index") != cycle
        or market_view.get("upstream_digests", {}).get(
            "public_market_analysis_bundle_digest"
        )
        != digests["public_market_analysis_bundle"]
        or market_view.get("upstream_digests", {}).get(
            "public_market_graph_projection_digest"
        )
        != digests["public_market_graph_projection"]
        or market_view.get("upstream_digests", {}).get(
            "graph_dependency_registry_digest"
        )
        != digests["verified_graph_dependency_registry"]
        or market_view.get("upstream_digests", {}).get(
            "pit_evidence_availability_registry_digest"
        )
        != digests["verified_pit_evidence_availability_registry"]
        or timeframe.get("run_id") != run_id
        or timeframe.get("cycle_index") != cycle
        or timeframe.get("decision_time") != decision_time
        or proposal_context.get("run_id") != run_id
        or proposal_context.get("cycle_index") != cycle
        or proposal_context.get("context_profile") != V32_TARGET_CONTEXT_PROFILE
        or proposal_packet.get("decision_time") != decision_time
        or support_documents.get("cycle_source_admission") != source
        or support_documents.get("timeframe_context_state") != timeframe
        or support_documents.get("active_authority_projection")
        != authority_projection
        or support_documents.get("agent_market_graph_view") != market_view
        or selection_context.get("run_id") != run_id
        or selection_context.get("cycle_index") != cycle
        or selection_packet.get("compiled_dynamic_research_state")
        != current_state
        or proposal_receipt.get("compiled_dynamic_research_state")
        != current_state
        or proposal_receipt.get("compiled_dynamic_research_state_digest")
        != digests["compiled_dynamic_research_state"]
        or selection_packet.get("sealed_action_evaluation")
        != action_evaluation
        or proposal_receipt.get("sealed_action_evaluation")
        != action_evaluation
        or proposal_receipt.get("sealed_action_evaluation_digest")
        != digests["sealed_action_evaluation"]
        or state_continuity.get("current_state_digest")
        != digests["compiled_dynamic_research_state"]
        or state_continuity.get("pit_evidence_registry_digest")
        != digests["pit_evidence_registry"]
        or state_continuity.get("graph_dependency_registry_digest")
        != digests["verified_graph_dependency_registry"]
        or proposal_receipt.get("run_id") != run_id
        or proposal_receipt.get("cycle_index") != cycle
        or selection_receipt.get("run_id") != run_id
        or selection_receipt.get("cycle_index") != cycle
        or final_plan.get("run_id") != run_id
        or final_plan.get("cycle_index") != cycle
        or shadow_decision.get("run_id") != run_id
        or shadow_decision.get("cycle_index") != cycle
        or shadow_decision.get("decision_id") != schedule.get("decision_id")
        or shadow_decision.get("as_of") != decision_time
        or shadow_decision.get("outcome_values_present") is not False
        or _moment(
            shadow_decision.get("created_at"),
            "V32_CYCLE_ACCEPTANCE_TIME_INVALID",
        )
        > _moment(accepted, "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
        or action_continuity.get("current_dynamic_state_digest")
        != digests["compiled_dynamic_research_state"]
        or action_continuity.get("current_action_plan_digest")
        != digests["final_dynamic_action_plan"]
        or authorized_revision_registry.get("run_id") != run_id
        or authorized_revision_registry.get("cycle_index") != cycle
        or authorized_revision_registry.get("proposal_context") is None
        or authorized_revision_registry.get("selection_context") is None
        or authorized_revision_registry.get("environment_conformance") is None
        or authorized_revision_registry.get("cycle_audit_narrative_included")
        is not False
        or authorized_revision_registry.get("registry_is_acceptance") is not False
        or _moment(
            authorized_revision_registry.get("created_at"),
            "V32_CYCLE_ACCEPTANCE_TIME_INVALID",
        )
        > _moment(accepted, "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
        or action_continuity.get("max_wait_cycles_before_review")
        != inactivity_policy.get("review_after_consecutive_cycles")
        or action_continuity.get("max_inactivity_seconds")
        != inactivity_policy.get("review_after_seconds")
        or commit.get("run_id") != run_id
        or commit.get("cycle_index") != cycle
        or commit.get("final_dynamic_action_plan") != final_plan
        or commit.get("final_dynamic_action_plan_digest")
        != digests["final_dynamic_action_plan"]
        or commit.get("outcome_schedule_set") != schedule
        or commit.get("outcome_schedule_set_digest")
        != digests["outcome_schedule_set"]
        or schedule.get("run_id") != run_id
        or schedule.get("cycle_index") != cycle
        or schedule.get("decision_time") != expected_schedule_decision_time
        or schedule.get("sealed_decision_digest")
        != digests["final_dynamic_action_plan"]
        or watchdog.get("max_wait_cycles_before_review")
        != inactivity_policy.get("review_after_consecutive_cycles")
        or watchdog.get("max_inactivity_seconds")
        != inactivity_policy.get("review_after_seconds")
        or actual_horizons != expected_horizons
        or len(actual_horizons) != 3
        or current_receipts
        or proposal_delivery.get("attempt_number") != 1
        or proposal_delivery.get("max_attempts") != 1
        or proposal_delivery.get("retry_allowed") is not False
        or proposal_consumption.get("attempt_count") != 1
        or proposal_consumption.get("retry_count") != 0
        or selection_delivery.get("attempt_number") != 1
        or selection_delivery.get("max_attempts") != 1
        or selection_delivery.get("retry_allowed") is not False
        or selection_consumption.get("attempt_count") != 1
        or selection_consumption.get("retry_count") != 0
        or source.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != permit.get("active_authority_digest")
        or source.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != source_replay.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        or source.get("experiment_contract_digest")
        != permit.get("experiment_contract_digest")
        or _moment(accepted, "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
        < _moment(commit.get("sealed_at"), "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
        or _moment(accepted, "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
        >= min(
            _moment(row["outcome_not_before"], "V32_CYCLE_ACCEPTANCE_TIME_INVALID")
            for row in schedule["schedules"]
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_CROSS_BINDING_INVALID"
        )
    return run_id, cycle, decision_time, previous_digest


def _build_v32_analysis_cycle_acceptance_receipt_v1(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    shadow_decision_verifier: V32ShadowDecisionVerifierPort,
    components: Mapping[str, Mapping[str, Any]],
    component_bindings: Mapping[str, Mapping[str, Any]],
    permit_checkpoint: Mapping[str, Any],
    permit_checkpoint_binding: Mapping[str, Any],
    prior_outcome_schedule_sets: Sequence[Mapping[str, Any]],
    prior_outcome_schedule_set_bindings: Sequence[Mapping[str, Any]],
    previous_timeframe_context_state: Mapping[str, Any] | None,
    previous_timeframe_context_state_binding: Mapping[str, Any] | None,
    previous_public_market_graph_projection: Mapping[str, Any] | None,
    previous_public_market_graph_projection_binding: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry_binding: Mapping[str, Any] | None,
    previous_accepted_receipt: Mapping[str, Any] | None,
    previous_accepted_receipt_binding: Mapping[str, Any] | None,
    accepted_at: str,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
    selection_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay and seal one complete V3.2 analysis-cycle acceptance boundary."""

    if (
        not isinstance(components, Mapping)
        or set(components) != set(COMPONENT_SPECS)
        or not isinstance(component_bindings, Mapping)
        or set(component_bindings) != set(COMPONENT_SPECS)
        or isinstance(prior_outcome_schedule_sets, (str, bytes))
        or not isinstance(prior_outcome_schedule_sets, Sequence)
        or isinstance(prior_outcome_schedule_set_bindings, (str, bytes))
        or not isinstance(prior_outcome_schedule_set_bindings, Sequence)
        or len(prior_outcome_schedule_sets)
        != len(prior_outcome_schedule_set_bindings)
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_BINDING_SET_INVALID"
        )
    cycle = _cycle(
        components["analysis_tick_permit"].get("analysis_cycle_index")
    )
    if cycle == 1 and any(
        value is not None
        for value in (
            previous_timeframe_context_state,
            previous_timeframe_context_state_binding,
            previous_public_market_graph_projection,
            previous_public_market_graph_projection_binding,
            previous_pit_evidence_availability_registry,
            previous_pit_evidence_availability_registry_binding,
            previous_accepted_receipt,
            previous_accepted_receipt_binding,
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID"
        )
    if cycle > 1:
        if previous_accepted_receipt is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_REQUIRED"
            )
        if previous_timeframe_context_state is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_TIMEFRAME_REQUIRED"
            )
        if previous_public_market_graph_projection is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_GRAPH_PROJECTION_REQUIRED"
            )
        if previous_pit_evidence_availability_registry is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_AVAILABILITY_REQUIRED"
            )
    digests = _replay_components(
        public_evidence_verifier=public_evidence_verifier,
        shadow_decision_verifier=shadow_decision_verifier,
        components=components,
        permit_checkpoint=permit_checkpoint,
        prior_outcome_schedule_sets=prior_outcome_schedule_sets,
        previous_timeframe_context_state=previous_timeframe_context_state,
        previous_public_market_graph_projection=(
            previous_public_market_graph_projection
        ),
        previous_pit_evidence_availability_registry=(
            previous_pit_evidence_availability_registry
        ),
        previous_accepted_receipt=previous_accepted_receipt,
        proposal_lossless_context_package=proposal_lossless_context_package,
        selection_lossless_context_package=selection_lossless_context_package,
    )
    run_id, cycle, decision_time, previous_digest = _cross_validate(
        components=components,
        digests=digests,
        permit_checkpoint=permit_checkpoint,
        previous_timeframe_context_state=previous_timeframe_context_state,
        previous_public_market_graph_projection=(
            previous_public_market_graph_projection
        ),
        previous_pit_evidence_availability_registry=(
            previous_pit_evidence_availability_registry
        ),
        previous_accepted_receipt=previous_accepted_receipt,
        accepted_at=accepted_at,
        proposal_lossless_context_package=proposal_lossless_context_package,
        selection_lossless_context_package=selection_lossless_context_package,
    )

    normalized_components: dict[str, dict[str, str]] = {}
    for role, (schema_id, digest_field) in COMPONENT_SPECS.items():
        normalized_components[role] = _strict_binding(
            document=components[role],
            binding=component_bindings[role],
            schema_id=schema_id,
            digest_field=digest_field,
            semantic_digest=digests[role],
            code="V32_CYCLE_ACCEPTANCE_COMPONENT_BINDING_INVALID",
        )
    checkpoint_binding = _strict_binding(
        document=permit_checkpoint,
        binding=permit_checkpoint_binding,
        schema_id=CHECKPOINT_SCHEMA_ID,
        digest_field=CHECKPOINT_DIGEST_FIELD,
        semantic_digest=digests["permit_checkpoint"],
        code="V32_CYCLE_ACCEPTANCE_REPLAY_SUPPORT_BINDING_INVALID",
    )
    normalized_prior_schedules = [
        _strict_binding(
            document=document,
            binding=binding,
            schema_id=SCHEDULE_SET_SCHEMA_ID,
            digest_field=SCHEDULE_SET_DIGEST_FIELD,
            semantic_digest=document[SCHEDULE_SET_DIGEST_FIELD],
            code="V32_CYCLE_ACCEPTANCE_REPLAY_SUPPORT_BINDING_INVALID",
        )
        for document, binding in zip(
            prior_outcome_schedule_sets,
            prior_outcome_schedule_set_bindings,
            strict=True,
        )
    ]
    if [row["semantic_digest"] for row in normalized_prior_schedules] != list(
        permit_checkpoint["outcome_schedule_set_digests"]
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_PRIOR_SCHEDULE_ORDER_INVALID"
        )

    normalized_previous_timeframe: dict[str, str] | None = None
    if previous_timeframe_context_state is not None:
        if previous_timeframe_context_state_binding is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_TIMEFRAME_BINDING_REQUIRED"
            )
        try:
            # The exact predecessor was already checked by the current-state
            # transition replay above.  Recalculate its intrinsic digest here
            # solely for the durable physical/semantic binding.
            previous_timeframe_digest = verify_self_digest(
                previous_timeframe_context_state, TIMEFRAME_DIGEST_FIELD
            )
        except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_TIMEFRAME_BINDING_INVALID"
            ) from exc
        normalized_previous_timeframe = _strict_binding(
            document=previous_timeframe_context_state,
            binding=previous_timeframe_context_state_binding,
            schema_id=TIMEFRAME_SCHEMA_ID,
            digest_field=TIMEFRAME_DIGEST_FIELD,
            semantic_digest=previous_timeframe_digest,
            code="V32_CYCLE_ACCEPTANCE_PREVIOUS_TIMEFRAME_BINDING_INVALID",
        )
    elif previous_timeframe_context_state_binding is not None:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID"
        )

    normalized_previous_projection: dict[str, str] | None = None
    if previous_public_market_graph_projection is not None:
        if previous_public_market_graph_projection_binding is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_GRAPH_PROJECTION_BINDING_REQUIRED"
            )
        try:
            previous_projection_digest = verify_self_digest(
                previous_public_market_graph_projection,
                GRAPH_PROJECTION_DIGEST_FIELD,
            )
        except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_GRAPH_PROJECTION_BINDING_INVALID"
            ) from exc
        normalized_previous_projection = _strict_binding(
            document=previous_public_market_graph_projection,
            binding=previous_public_market_graph_projection_binding,
            schema_id=GRAPH_PROJECTION_SCHEMA_ID,
            digest_field=GRAPH_PROJECTION_DIGEST_FIELD,
            semantic_digest=previous_projection_digest,
            code=(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_GRAPH_PROJECTION_BINDING_INVALID"
            ),
        )
        if previous_accepted_receipt is None or not _same_artifact_identity(
            normalized_previous_projection,
            previous_accepted_receipt["component_bindings"][
                "public_market_graph_projection"
            ],
        ):
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_GRAPH_PROJECTION_CHAIN_INVALID"
            )
    elif previous_public_market_graph_projection_binding is not None:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID"
        )

    normalized_previous_availability: dict[str, str] | None = None
    if previous_pit_evidence_availability_registry is not None:
        if previous_pit_evidence_availability_registry_binding is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_AVAILABILITY_BINDING_REQUIRED"
            )
        try:
            previous_availability_digest = verify_self_digest(
                previous_pit_evidence_availability_registry,
                PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
            )
        except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_AVAILABILITY_BINDING_INVALID"
            ) from exc
        normalized_previous_availability = _strict_binding(
            document=previous_pit_evidence_availability_registry,
            binding=previous_pit_evidence_availability_registry_binding,
            schema_id=PIT_AVAILABILITY_REGISTRY_SCHEMA_ID,
            digest_field=PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
            semantic_digest=previous_availability_digest,
            code="V32_CYCLE_ACCEPTANCE_PREVIOUS_AVAILABILITY_BINDING_INVALID",
        )
        if previous_accepted_receipt is None or not _same_artifact_identity(
            normalized_previous_availability,
            previous_accepted_receipt["component_bindings"][
                "verified_pit_evidence_availability_registry"
            ],
        ):
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_AVAILABILITY_CHAIN_INVALID"
            )
    elif previous_pit_evidence_availability_registry_binding is not None:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID"
        )

    normalized_previous_acceptance: dict[str, str] | None = None
    if previous_accepted_receipt is not None:
        if previous_accepted_receipt_binding is None:
            raise V32CycleAcceptanceError(
                "V32_CYCLE_ACCEPTANCE_PREVIOUS_BINDING_REQUIRED"
            )
        normalized_previous_acceptance = _strict_binding(
            document=previous_accepted_receipt,
            binding=previous_accepted_receipt_binding,
            schema_id=SCHEMA_ID,
            digest_field=DIGEST_FIELD,
            semantic_digest=str(previous_digest),
            code="V32_CYCLE_ACCEPTANCE_PREVIOUS_BINDING_INVALID",
        )
    elif previous_accepted_receipt_binding is not None:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_GENESIS_PREVIOUS_INVALID"
        )

    proposal_packet = resolve_v32_agent_canonical_packet_v1(
        components["proposal_input_context"],
        lossless_context_package=proposal_lossless_context_package,
    )
    selection_packet = resolve_v32_agent_canonical_packet_v1(
        components["selection_input_context"],
        lossless_context_package=selection_lossless_context_package,
    )
    commit = components["two_stage_commit_envelope"]
    normalized_previous_dynamic: dict[str, str] | None = None
    normalized_previous_action: dict[str, str] | None = None
    if proposal_packet["previous_dynamic_research_state"] is not None:
        normalized_previous_dynamic = _strict_binding(
            document=proposal_packet["previous_dynamic_research_state"],
            binding=proposal_packet["previous_dynamic_research_state_binding"],
            schema_id=DYNAMIC_STATE_SCHEMA_ID,
            digest_field=DYNAMIC_STATE_DIGEST_FIELD,
            semantic_digest=proposal_packet["previous_dynamic_research_state"][
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            code="V32_CYCLE_ACCEPTANCE_CONTINUITY_INPUT_BINDING_INVALID",
        )
        normalized_previous_action = _strict_binding(
            document=proposal_packet["previous_dynamic_action_plan"],
            binding=proposal_packet["previous_dynamic_action_plan_binding"],
            schema_id=ACTION_PLAN_SCHEMA_ID,
            digest_field=ACTION_PLAN_DIGEST_FIELD,
            semantic_digest=proposal_packet["previous_dynamic_action_plan"][
                ACTION_PLAN_DIGEST_FIELD
            ],
            code="V32_CYCLE_ACCEPTANCE_CONTINUITY_INPUT_BINDING_INVALID",
        )
    elif (
        proposal_packet["previous_dynamic_research_state_binding"] is not None
        or proposal_packet["previous_dynamic_action_plan"] is not None
        or proposal_packet["previous_dynamic_action_plan_binding"] is not None
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_CONTINUITY_INPUT_BINDING_INVALID"
        )
    normalized_pit_registry = _strict_binding(
        document=components["pit_evidence_registry"],
        binding=component_bindings["pit_evidence_registry"],
        schema_id=PIT_REGISTRY_SCHEMA_ID,
        digest_field=PIT_REGISTRY_DIGEST_FIELD,
        semantic_digest=digests["pit_evidence_registry"],
        code="V32_CYCLE_ACCEPTANCE_CONTINUITY_INPUT_BINDING_INVALID",
    )
    normalized_graph_registry = _strict_binding(
        document=components["verified_graph_dependency_registry"],
        binding=component_bindings["verified_graph_dependency_registry"],
        schema_id=GRAPH_REGISTRY_SCHEMA_ID,
        digest_field=GRAPH_REGISTRY_DIGEST_FIELD,
        semantic_digest=digests["verified_graph_dependency_registry"],
        code="V32_CYCLE_ACCEPTANCE_CONTINUITY_INPUT_BINDING_INVALID",
    )
    normalized_availability_registry = _strict_binding(
        document=components["verified_pit_evidence_availability_registry"],
        binding=component_bindings[
            "verified_pit_evidence_availability_registry"
        ],
        schema_id=PIT_AVAILABILITY_REGISTRY_SCHEMA_ID,
        digest_field=PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
        semantic_digest=digests[
            "verified_pit_evidence_availability_registry"
        ],
        code="V32_CYCLE_ACCEPTANCE_CONTINUITY_INPUT_BINDING_INVALID",
    )
    if (
        not _same_artifact_identity(
            proposal_packet["support_bindings"]["active_authority_projection"],
            normalized_components["active_authority_projection"],
        )
        or not _same_artifact_identity(
            proposal_packet["support_bindings"]["cycle_source_admission"],
            normalized_components["cycle_source_admission"],
        )
        or not _same_artifact_identity(
            proposal_packet["support_bindings"]["timeframe_context_state"],
            normalized_components["current_timeframe_context_state"],
        )
        or not _same_artifact_identity(
            proposal_packet["support_bindings"]["agent_market_graph_view"],
            normalized_components["agent_market_graph_view"],
        )
        or not _same_artifact_identity(
            normalized_pit_registry,
            normalized_components["pit_evidence_registry"],
        )
        or not _same_artifact_identity(
            normalized_graph_registry,
            normalized_components["verified_graph_dependency_registry"],
        )
        or not _same_artifact_identity(
            components["cycle_source_admission"].get("pit_registry_binding"),
            normalized_components["pit_evidence_registry"],
        )
        or not _same_artifact_identity(
            components["durable_source_replay_receipt"].get(
                "market_analysis_bundle_binding"
            ),
            normalized_components["public_market_analysis_bundle"],
        )
        or not _same_artifact_identity(
            components["durable_source_replay_receipt"].get(
                "source_pit_registry_binding"
            ),
            normalized_components["pit_evidence_registry"],
        )
        or not _same_artifact_identity(
            components["durable_source_replay_receipt"].get(
                "cycle_source_admission_binding"
            ),
            normalized_components["cycle_source_admission"],
        )
        or not _same_artifact_identity(
            components["proposal_delivery"]["agent_input_context_binding"],
            normalized_components["proposal_input_context"],
        )
        or not _same_artifact_identity(
            components["proposal_consumption"]["agent_input_context_binding"],
            normalized_components["proposal_input_context"],
        )
        or not _same_artifact_identity(
            components["proposal_consumption"]["agent_delivery_binding"],
            normalized_components["proposal_delivery"],
        )
        or not _same_artifact_identity(
            selection_packet["proposal_input_context_binding"],
            normalized_components["proposal_input_context"],
        )
        or not _same_artifact_identity(
            selection_packet["proposal_delivery_binding"],
            normalized_components["proposal_delivery"],
        )
        or not _same_artifact_identity(
            selection_packet["proposal_consumption_binding"],
            normalized_components["proposal_consumption"],
        )
        or not _same_artifact_identity(
            components["selection_delivery"]["agent_input_context_binding"],
            normalized_components["selection_input_context"],
        )
        or not _same_artifact_identity(
            components["selection_consumption"]["agent_input_context_binding"],
            normalized_components["selection_input_context"],
        )
        or not _same_artifact_identity(
            components["selection_consumption"]["agent_delivery_binding"],
            normalized_components["selection_delivery"],
        )
        or not _same_artifact_identity(
            selection_packet["compiled_dynamic_research_state_binding"],
            normalized_components["compiled_dynamic_research_state"],
        )
        or not _same_artifact_identity(
            selection_packet["sealed_action_evaluation_binding"],
            normalized_components["sealed_action_evaluation"],
        )
        or not _same_artifact_identity(
            commit["final_dynamic_action_plan_binding"],
            normalized_components["final_dynamic_action_plan"],
        )
        or not _same_artifact_identity(
            commit["outcome_schedule_set_binding"],
            normalized_components["outcome_schedule_set"],
        )
    ):
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_DURABLE_BINDING_GRAPH_INVALID"
        )

    replay_support = {
        "permit_checkpoint_binding": checkpoint_binding,
        "prior_outcome_schedule_set_bindings": normalized_prior_schedules,
        "previous_timeframe_context_state_binding": normalized_previous_timeframe,
        "previous_public_market_graph_projection_binding": (
            normalized_previous_projection
        ),
        "previous_pit_evidence_availability_registry_binding": (
            normalized_previous_availability
        ),
        "continuity_replay_input_bindings": {
            "durable_previous_dynamic_research_state_binding": (
                normalized_previous_dynamic
            ),
            "durable_previous_dynamic_action_plan_binding": (
                normalized_previous_action
            ),
            "pit_evidence_registry_binding": normalized_pit_registry,
            "pit_evidence_availability_registry_binding": (
                normalized_availability_registry
            ),
            "graph_dependency_registry_binding": normalized_graph_registry,
        },
    }
    proposal_lifecycle_digest = _stage_lifecycle_digest(
        context_digest=digests["proposal_input_context"],
        delivery_digest=digests["proposal_delivery"],
        consumption_digest=digests["proposal_consumption"],
    )
    selection_lifecycle_digest = _stage_lifecycle_digest(
        context_digest=digests["selection_input_context"],
        delivery_digest=digests["selection_delivery"],
        consumption_digest=digests["selection_consumption"],
    )
    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle,
        "decision_time": decision_time,
        "accepted_at": _time(accepted_at, "V32_CYCLE_ACCEPTANCE_TIME_INVALID"),
        "previous_accepted_receipt_digest": previous_digest,
        "previous_accepted_receipt_binding": normalized_previous_acceptance,
        "component_bindings": normalized_components,
        "component_bindings_digest": canonical_digest(normalized_components),
        "replay_support_bindings": replay_support,
        "replay_support_bindings_digest": canonical_digest(replay_support),
        "analysis_tick_permit_digest": digests["analysis_tick_permit"],
        "active_authority_projection_digest": digests[
            "active_authority_projection"
        ],
        "cycle_source_admission_digest": digests["cycle_source_admission"],
        "public_market_analysis_bundle_digest": digests[
            "public_market_analysis_bundle"
        ],
        "public_market_graph_projection_digest": digests[
            "public_market_graph_projection"
        ],
        "pit_evidence_registry_digest": digests["pit_evidence_registry"],
        "verified_graph_dependency_registry_digest": digests[
            "verified_graph_dependency_registry"
        ],
        "durable_source_replay_receipt_digest": digests[
            "durable_source_replay_receipt"
        ],
        "verified_pit_evidence_availability_registry_digest": digests[
            "verified_pit_evidence_availability_registry"
        ],
        "agent_market_graph_view_digest": digests["agent_market_graph_view"],
        "shadow_decision_bundle_digest": digests[
            "replayable_shadow_decision_bundle"
        ],
        "accepted_market_snapshot_binding": dict(
            components["cycle_source_admission"]["current_snapshot_binding"]
        ),
        "accepted_open_interest_datum_digest": components[
            "cycle_source_admission"
        ]["current_open_interest_datum_digest"],
        "accepted_open_interest_status": components[
            "cycle_source_admission"
        ]["current_open_interest_status"],
        "accepted_open_interest_zero_imputed": components[
            "cycle_source_admission"
        ]["current_open_interest_zero_imputed"],
        "timeframe_context_state_digest": digests[
            "current_timeframe_context_state"
        ],
        "proposal_lifecycle_digest": proposal_lifecycle_digest,
        "proposal_semantic_compile_receipt_digest": digests[
            "proposal_semantic_compile_receipt"
        ],
        "dynamic_state_continuity_receipt_digest": digests[
            "dynamic_state_continuity_receipt"
        ],
        "selection_lifecycle_digest": selection_lifecycle_digest,
        "selection_semantic_compile_receipt_digest": digests[
            "selection_semantic_compile_receipt"
        ],
        "accepted_dynamic_research_state_digest": components[
            "proposal_semantic_compile_receipt"
        ]["compiled_dynamic_research_state_digest"],
        "final_dynamic_action_plan_digest": digests[
            "final_dynamic_action_plan"
        ],
        "action_plan_continuity_receipt_digest": digests[
            "action_plan_continuity_receipt"
        ],
        "authorized_revision_cycle_registry_digest": digests[
            "authorized_revision_cycle_registry"
        ],
        "two_stage_commit_envelope_digest": digests[
            "two_stage_commit_envelope"
        ],
        "outcome_schedule_set_digest": digests["outcome_schedule_set"],
        "single_source_collection_transaction": True,
        "proposal_attempt_count": 1,
        "selection_attempt_count": 1,
        "current_outcome_present": False,
        "account_state_present": False,
        "order_state_present": False,
        "fill_state_present": False,
        "pnl_state_present": False,
        "acceptance_status": "ACCEPTED_SINGLE_ANALYSIS_CYCLE_WRITE_ONCE_REQUIRED",
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "claim": CLAIM,
    }
    return self_digest(document, DIGEST_FIELD)


def build_v32_analysis_cycle_acceptance_receipt_v1(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    shadow_decision_verifier: V32ShadowDecisionVerifierPort,
    components: Mapping[str, Mapping[str, Any]],
    component_bindings: Mapping[str, Mapping[str, Any]],
    permit_checkpoint: Mapping[str, Any],
    permit_checkpoint_binding: Mapping[str, Any],
    prior_outcome_schedule_sets: Sequence[Mapping[str, Any]],
    prior_outcome_schedule_set_bindings: Sequence[Mapping[str, Any]],
    previous_timeframe_context_state: Mapping[str, Any] | None,
    previous_timeframe_context_state_binding: Mapping[str, Any] | None,
    previous_public_market_graph_projection: Mapping[str, Any] | None,
    previous_public_market_graph_projection_binding: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry_binding: Mapping[str, Any] | None,
    previous_accepted_receipt: Mapping[str, Any] | None,
    previous_accepted_receipt_binding: Mapping[str, Any] | None,
    accepted_at: str,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
    selection_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay once with owner-bound lifecycle and public-graph scopes."""

    with (
        public_evidence_verifier.verification_scope(),
        v32_lifecycle_verification_scope_v1(),
    ):
        return _build_v32_analysis_cycle_acceptance_receipt_v1(
            public_evidence_verifier=public_evidence_verifier,
            shadow_decision_verifier=shadow_decision_verifier,
            components=components,
            component_bindings=component_bindings,
            permit_checkpoint=permit_checkpoint,
            permit_checkpoint_binding=permit_checkpoint_binding,
            prior_outcome_schedule_sets=prior_outcome_schedule_sets,
            prior_outcome_schedule_set_bindings=(
                prior_outcome_schedule_set_bindings
            ),
            previous_timeframe_context_state=previous_timeframe_context_state,
            previous_timeframe_context_state_binding=(
                previous_timeframe_context_state_binding
            ),
            previous_public_market_graph_projection=(
                previous_public_market_graph_projection
            ),
            previous_public_market_graph_projection_binding=(
                previous_public_market_graph_projection_binding
            ),
            previous_pit_evidence_availability_registry=(
                previous_pit_evidence_availability_registry
            ),
            previous_pit_evidence_availability_registry_binding=(
                previous_pit_evidence_availability_registry_binding
            ),
            previous_accepted_receipt=previous_accepted_receipt,
            previous_accepted_receipt_binding=previous_accepted_receipt_binding,
            accepted_at=accepted_at,
            proposal_lossless_context_package=proposal_lossless_context_package,
            selection_lossless_context_package=selection_lossless_context_package,
        )


def verify_v32_analysis_cycle_acceptance_receipt_v1(
    document: Mapping[str, Any],
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    shadow_decision_verifier: V32ShadowDecisionVerifierPort,
    components: Mapping[str, Mapping[str, Any]],
    component_bindings: Mapping[str, Mapping[str, Any]],
    permit_checkpoint: Mapping[str, Any],
    permit_checkpoint_binding: Mapping[str, Any],
    prior_outcome_schedule_sets: Sequence[Mapping[str, Any]],
    prior_outcome_schedule_set_bindings: Sequence[Mapping[str, Any]],
    previous_timeframe_context_state: Mapping[str, Any] | None,
    previous_timeframe_context_state_binding: Mapping[str, Any] | None,
    previous_public_market_graph_projection: Mapping[str, Any] | None,
    previous_public_market_graph_projection_binding: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry: Mapping[str, Any] | None,
    previous_pit_evidence_availability_registry_binding: Mapping[str, Any] | None,
    previous_accepted_receipt: Mapping[str, Any] | None,
    previous_accepted_receipt_binding: Mapping[str, Any] | None,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
    selection_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    """Rebuild one acceptance receipt from all replayable prerequisites."""

    if not isinstance(document, Mapping) or set(document) != _RECEIPT_FIELDS:
        raise V32CycleAcceptanceError("V32_CYCLE_ACCEPTANCE_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        rebuilt = build_v32_analysis_cycle_acceptance_receipt_v1(
            public_evidence_verifier=public_evidence_verifier,
            shadow_decision_verifier=shadow_decision_verifier,
            components=components,
            component_bindings=component_bindings,
            permit_checkpoint=permit_checkpoint,
            permit_checkpoint_binding=permit_checkpoint_binding,
            prior_outcome_schedule_sets=prior_outcome_schedule_sets,
            prior_outcome_schedule_set_bindings=prior_outcome_schedule_set_bindings,
            previous_timeframe_context_state=previous_timeframe_context_state,
            previous_timeframe_context_state_binding=previous_timeframe_context_state_binding,
            previous_public_market_graph_projection=(
                previous_public_market_graph_projection
            ),
            previous_public_market_graph_projection_binding=(
                previous_public_market_graph_projection_binding
            ),
            previous_pit_evidence_availability_registry=(
                previous_pit_evidence_availability_registry
            ),
            previous_pit_evidence_availability_registry_binding=(
                previous_pit_evidence_availability_registry_binding
            ),
            previous_accepted_receipt=previous_accepted_receipt,
            previous_accepted_receipt_binding=previous_accepted_receipt_binding,
            accepted_at=document["accepted_at"],
            proposal_lossless_context_package=proposal_lossless_context_package,
            selection_lossless_context_package=selection_lossless_context_package,
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleAcceptanceError):
            raise
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_RECEIPT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32CycleAcceptanceError(
            "V32_CYCLE_ACCEPTANCE_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "CLAIM",
    "COMPONENT_SPECS",
    "DIGEST_FIELD",
    "EXTERNAL_EXECUTION_AUTHORITY",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "SOURCE_SCOPE",
    "V32CycleAcceptanceError",
    "build_v32_analysis_cycle_acceptance_receipt_v1",
    "verify_v32_analysis_cycle_acceptance_receipt_v1",
]
