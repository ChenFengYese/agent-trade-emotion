"""Local write-once store for V3.2 dynamic research-cycle artifacts.

The store owns filesystem durability only.  It accepts a finite allow-list of
versioned V3.2 semantic artifacts, writes canonical JSON once, binds both the
semantic self-digest and physical SHA-256, and advances one compare-and-swap
research checkpoint under thread and process locks.

It has no network, Agent invocation, account, order, fill, portfolio, or PnL
capability.  If a sealed two-stage commit is durable but the checkpoint update
was interrupted, the only recovery path copies the already embedded final
action plan and outcome schedule and advances the deterministic tail.  That
path cannot invoke an Agent or make a network request.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
import re
import threading
from types import MappingProxyType
from typing import Any, Mapping

from ..application.v32_action_plan_continuity import (
    DIGEST_FIELD as ACTION_CONTINUITY_DIGEST_FIELD,
    SCHEMA_ID as ACTION_CONTINUITY_SCHEMA_ID,
)
from ..application.v32_authorized_revision_orchestration import (
    CYCLE_REGISTRY_DIGEST_FIELD,
    CYCLE_REGISTRY_SCHEMA_ID,
)
from ..application.v32_agent_semantic_compiler import (
    PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD,
    PROPOSAL_COMPILE_RECEIPT_SCHEMA_ID,
    PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD,
    PROPOSAL_SEMANTIC_OUTPUT_SCHEMA_ID,
    SELECTION_COMPILE_RECEIPT_DIGEST_FIELD,
    SELECTION_COMPILE_RECEIPT_SCHEMA_ID,
    SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD,
    SELECTION_SEMANTIC_OUTPUT_SCHEMA_ID,
)
from ..application.v32_cycle_acceptance import (
    COMPONENT_SPECS as ACCEPTANCE_COMPONENT_SPECS,
    DIGEST_FIELD as ACCEPTANCE_DIGEST_FIELD,
    SCHEMA_ID as ACCEPTANCE_SCHEMA_ID,
    build_v32_analysis_cycle_acceptance_receipt_v1,
    verify_v32_analysis_cycle_acceptance_receipt_v1,
)
from ..application.v32_dynamic_state_continuity import (
    PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
    PIT_AVAILABILITY_REGISTRY_SCHEMA_ID,
    RECEIPT_DIGEST_FIELD as STATE_CONTINUITY_DIGEST_FIELD,
    RECEIPT_SCHEMA_ID as STATE_CONTINUITY_SCHEMA_ID,
)
from ..application.v32_durable_source_replay import (
    RECEIPT_DIGEST_FIELD as SOURCE_REPLAY_DIGEST_FIELD,
    RECEIPT_SCHEMA_ID as SOURCE_REPLAY_SCHEMA_ID,
    verify_v32_durable_source_replay_receipt,
)
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ..v32_durable_json import (
    atomic_replace_json,
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_DIGEST_FIELD,
    SCHEMA_ID as EXPERIMENT_SCHEMA_ID,
)
from ..domain.v32_agent_lifecycle import (
    ACTION_EVALUATION_DIGEST_FIELD,
    ACTION_EVALUATION_SCHEMA_ID,
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONSUMPTION_SCHEMA_ID,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_DELIVERY_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    COMMIT_ENVELOPE_DIGEST_FIELD,
    COMMIT_ENVELOPE_SCHEMA_ID,
    GRAPH_REGISTRY_DIGEST_FIELD,
    GRAPH_REGISTRY_SCHEMA_ID,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    PROPOSAL_PACKET_DIGEST_FIELD,
    PROPOSAL_PACKET_SCHEMA_ID,
    SELECTION_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_SCHEMA_ID,
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    THEORY_DOCUMENT_DIGEST_FIELD,
    THEORY_DOCUMENT_SCHEMA_ID,
    resolve_v32_agent_canonical_packet_v1,
    verify_v32_agent_input_context_v1,
    verify_v32_two_stage_commit_envelope_v1,
)
from ..domain.v32_agent_market_graph_view import (
    DIGEST_FIELD as AGENT_MARKET_VIEW_DIGEST_FIELD,
    SCHEMA_ID as AGENT_MARKET_VIEW_SCHEMA_ID,
)
from ..domain.v32_association_preregistration import (
    DIGEST_FIELD as ASSOCIATION_DIGEST_FIELD,
    SCHEMA_ID as ASSOCIATION_SCHEMA_ID,
)
from ..domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD as SOURCE_AUTHORITY_DIGEST_FIELD,
    AUTHORITY_PROJECTION_SCHEMA_ID as SOURCE_AUTHORITY_SCHEMA_ID,
    CAPTURE_DIGEST_FIELD as SOURCE_CAPTURE_DIGEST_FIELD,
    CAPTURE_SCHEMA_ID as SOURCE_CAPTURE_SCHEMA_ID,
    FULL_LOADER_DIGEST_FIELD as SOURCE_FULL_LOADER_DIGEST_FIELD,
    FULL_LOADER_SCHEMA_ID as SOURCE_FULL_LOADER_SCHEMA_ID,
    QUALIFICATION_DIGEST_FIELD as SOURCE_QUALIFICATION_DIGEST_FIELD,
    QUALIFICATION_SCHEMA_ID as SOURCE_QUALIFICATION_SCHEMA_ID,
    SNAPSHOT_DIGEST_FIELD as SOURCE_SNAPSHOT_DIGEST_FIELD,
    SNAPSHOT_SCHEMA_ID as SOURCE_SNAPSHOT_SCHEMA_ID,
)
from ..domain.v32_dynamic_action_plan import (
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    SCHEMA_ID as ACTION_PLAN_SCHEMA_ID,
)
from ..domain.v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    SCHEMA_ID as DYNAMIC_STATE_SCHEMA_ID,
)
from ..domain.v32_evaluation_contract import (
    DIGEST_FIELD as EVALUATION_DIGEST_FIELD,
    SCHEMA_ID as EVALUATION_SCHEMA_ID,
)
from ..domain.v32_outcome_tick import (
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
)
from ..domain.v32_shadow_evaluation import (
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    SHADOW_DECISION_BUNDLE_SCHEMA_ID,
)
from ..domain.v32_runtime_support_contracts import (
    CLOCK_DIGEST_FIELD,
    CLOCK_SCHEMA_ID,
    OUTCOME_ADAPTER_DIGEST_FIELD,
    OUTCOME_ADAPTER_SCHEMA_ID,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    CHECKPOINT_SCHEMA_ID as SUPERVISOR_CHECKPOINT_SCHEMA_ID,
    FAILURE_DIGEST_FIELD as SUPERVISOR_FAILURE_DIGEST_FIELD,
    FAILURE_SCHEMA_ID as SUPERVISOR_FAILURE_SCHEMA_ID,
    PERMIT_DIGEST_FIELD as SUPERVISOR_PERMIT_DIGEST_FIELD,
    PERMIT_SCHEMA_ID as SUPERVISOR_PERMIT_SCHEMA_ID,
)
from ..domain.v32_timeframe_cache import (
    DIGEST_FIELD as TIMEFRAME_DIGEST_FIELD,
    SCHEMA_ID as TIMEFRAME_SCHEMA_ID,
)
from .v32_public_market_graph_projection import (
    GRAPH_PROJECTION_DIGEST_FIELD,
    GRAPH_PROJECTION_SCHEMA_ID,
    verify_v32_public_market_graph_projection_v1,
    verify_v32_verified_graph_dependency_registry_v1,
)
from .v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    ANALYSIS_BUNDLE_SCHEMA_ID,
    verify_v32_public_market_analysis_bundle,
)
from .v32_public_evidence_verifier import V32InfrastructurePublicEvidenceVerifier
from .v32_shadow_decision_verifier import V32InfrastructureShadowDecisionVerifier
from .v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
    STORE_ROOT as MAILBOX_STORE_ROOT,
    V32CurrentRootAgentMailboxStoreError,
)


class V32DynamicStoreError(ValueError):
    """A V3.2 durable research-store invariant failed closed."""


STORE_ROOT = "v32-dynamic-cycle-v1"
CHECKPOINT_SCHEMA_ID = "theory_paper_v32_dynamic_research_checkpoint_v1"
CHECKPOINT_SCHEMA_VERSION = "1.0.0"
CHECKPOINT_DIGEST_FIELD = "dynamic_research_checkpoint_digest"
STORE_FAILURE_SCHEMA_ID = "theory_paper_v32_dynamic_store_failure_v1"
STORE_FAILURE_DIGEST_FIELD = "dynamic_store_failure_digest"

TOTAL_ANALYSIS_CYCLES = 16
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
STATUSES = ("READY", "OPEN", "OUTCOME_TAIL", "TERMINAL", "FAILED")

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}

# The allow-list is intentionally role-specific.  Sharing a schema between the
# proposal and selection stages does not make those roles interchangeable.
ARTIFACT_ROLE_SPECS = MappingProxyType(
    {
        "theory": (THEORY_DOCUMENT_SCHEMA_ID, THEORY_DOCUMENT_DIGEST_FIELD),
        "support_experiment": (EXPERIMENT_SCHEMA_ID, EXPERIMENT_DIGEST_FIELD),
        "support_association": (ASSOCIATION_SCHEMA_ID, ASSOCIATION_DIGEST_FIELD),
        "support_evaluation": (EVALUATION_SCHEMA_ID, EVALUATION_DIGEST_FIELD),
        "support_clock_policy": (CLOCK_SCHEMA_ID, CLOCK_DIGEST_FIELD),
        "support_outcome_adapter": (
            OUTCOME_ADAPTER_SCHEMA_ID,
            OUTCOME_ADAPTER_DIGEST_FIELD,
        ),
        "support_pit_registry": (PIT_REGISTRY_SCHEMA_ID, PIT_REGISTRY_DIGEST_FIELD),
        "support_graph_registry": (
            GRAPH_REGISTRY_SCHEMA_ID,
            GRAPH_REGISTRY_DIGEST_FIELD,
        ),
        "public_market_analysis_bundle": (
            ANALYSIS_BUNDLE_SCHEMA_ID,
            ANALYSIS_BUNDLE_DIGEST_FIELD,
        ),
        "public_market_graph_projection": (
            GRAPH_PROJECTION_SCHEMA_ID,
            GRAPH_PROJECTION_DIGEST_FIELD,
        ),
        "durable_source_replay": (
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
        "support_twelve_axis_source_registry": (
            "theory_paper_v2_v31_native_sentiment_source_registry",
            "registry_digest",
        ),
        "support_twelve_axis_projection": (
            "theory_paper_v2_v31_native_sentiment_projection",
            "projection_digest",
        ),
        "source_authority_projection": (
            SOURCE_AUTHORITY_SCHEMA_ID,
            SOURCE_AUTHORITY_DIGEST_FIELD,
        ),
        "active_authority_projection": (
            SOURCE_AUTHORITY_SCHEMA_ID,
            SOURCE_AUTHORITY_DIGEST_FIELD,
        ),
        "source_capture": (SOURCE_CAPTURE_SCHEMA_ID, SOURCE_CAPTURE_DIGEST_FIELD),
        "source_snapshot": (
            SOURCE_SNAPSHOT_SCHEMA_ID,
            SOURCE_SNAPSHOT_DIGEST_FIELD,
        ),
        "source_qualification": (
            SOURCE_QUALIFICATION_SCHEMA_ID,
            SOURCE_QUALIFICATION_DIGEST_FIELD,
        ),
        "source_full_loader": (
            SOURCE_FULL_LOADER_SCHEMA_ID,
            SOURCE_FULL_LOADER_DIGEST_FIELD,
        ),
        "cycle_source_admission": (
            SOURCE_ADMISSION_SCHEMA_ID,
            SOURCE_ADMISSION_DIGEST_FIELD,
        ),
        "timeframe_context": (TIMEFRAME_SCHEMA_ID, TIMEFRAME_DIGEST_FIELD),
        "proposal_packet": (PROPOSAL_PACKET_SCHEMA_ID, PROPOSAL_PACKET_DIGEST_FIELD),
        "proposal_input": (
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        ),
        "proposal_delivery": (AGENT_DELIVERY_SCHEMA_ID, AGENT_DELIVERY_DIGEST_FIELD),
        "proposal_consumption": (
            AGENT_CONSUMPTION_SCHEMA_ID,
            AGENT_CONSUMPTION_DIGEST_FIELD,
        ),
        "proposal_semantic_output": (
            PROPOSAL_SEMANTIC_OUTPUT_SCHEMA_ID,
            PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD,
        ),
        "proposal_compile_receipt": (
            PROPOSAL_COMPILE_RECEIPT_SCHEMA_ID,
            PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD,
        ),
        "dynamic_state": (DYNAMIC_STATE_SCHEMA_ID, DYNAMIC_STATE_DIGEST_FIELD),
        "action_evaluation": (
            ACTION_EVALUATION_SCHEMA_ID,
            ACTION_EVALUATION_DIGEST_FIELD,
        ),
        "shadow_decision_bundle": (
            SHADOW_DECISION_BUNDLE_SCHEMA_ID,
            SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
        ),
        "dynamic_state_continuity": (
            STATE_CONTINUITY_SCHEMA_ID,
            STATE_CONTINUITY_DIGEST_FIELD,
        ),
        "selection_packet": (
            SELECTION_PACKET_SCHEMA_ID,
            SELECTION_PACKET_DIGEST_FIELD,
        ),
        "selection_input": (
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        ),
        "selection_delivery": (AGENT_DELIVERY_SCHEMA_ID, AGENT_DELIVERY_DIGEST_FIELD),
        "selection_consumption": (
            AGENT_CONSUMPTION_SCHEMA_ID,
            AGENT_CONSUMPTION_DIGEST_FIELD,
        ),
        "selection_semantic_output": (
            SELECTION_SEMANTIC_OUTPUT_SCHEMA_ID,
            SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD,
        ),
        "selection_compile_receipt": (
            SELECTION_COMPILE_RECEIPT_SCHEMA_ID,
            SELECTION_COMPILE_RECEIPT_DIGEST_FIELD,
        ),
        "action_plan": (ACTION_PLAN_SCHEMA_ID, ACTION_PLAN_DIGEST_FIELD),
        "action_plan_continuity": (
            ACTION_CONTINUITY_SCHEMA_ID,
            ACTION_CONTINUITY_DIGEST_FIELD,
        ),
        "authorized_revision_cycle_registry": (
            CYCLE_REGISTRY_SCHEMA_ID,
            CYCLE_REGISTRY_DIGEST_FIELD,
        ),
        "commit_envelope": (COMMIT_ENVELOPE_SCHEMA_ID, COMMIT_ENVELOPE_DIGEST_FIELD),
        "outcome_schedule": (SCHEDULE_SET_SCHEMA_ID, SCHEDULE_SET_DIGEST_FIELD),
        "analysis_acceptance": (ACCEPTANCE_SCHEMA_ID, ACCEPTANCE_DIGEST_FIELD),
        "supervisor_checkpoint": (
            SUPERVISOR_CHECKPOINT_SCHEMA_ID,
            SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
        ),
        "supervisor_permit": (
            SUPERVISOR_PERMIT_SCHEMA_ID,
            SUPERVISOR_PERMIT_DIGEST_FIELD,
        ),
        "supervisor_failure": (
            SUPERVISOR_FAILURE_SCHEMA_ID,
            SUPERVISOR_FAILURE_DIGEST_FIELD,
        ),
        "research_failure": (STORE_FAILURE_SCHEMA_ID, STORE_FAILURE_DIGEST_FIELD),
    }
)

_GLOBAL_ROLES = frozenset(
    {
        "theory",
        "support_experiment",
        "support_association",
        "support_evaluation",
        "support_clock_policy",
        "support_outcome_adapter",
        "support_twelve_axis_source_registry",
        "source_authority_projection",
        "research_failure",
    }
)
_REQUIRED_ACCEPTANCE_ROLES = (
    "supervisor_checkpoint",
    "supervisor_permit",
    "active_authority_projection",
    "public_market_analysis_bundle",
    "public_market_graph_projection",
    "durable_source_replay",
    "support_pit_registry",
    "support_graph_registry",
    "cycle_source_admission",
    "verified_pit_evidence_availability_registry",
    "agent_market_graph_view",
    "timeframe_context",
    "proposal_packet",
    "proposal_input",
    "proposal_delivery",
    "proposal_consumption",
    "proposal_semantic_output",
    "proposal_compile_receipt",
    "dynamic_state",
    "action_evaluation",
    "shadow_decision_bundle",
    "dynamic_state_continuity",
    "selection_packet",
    "selection_input",
    "selection_delivery",
    "selection_consumption",
    "selection_semantic_output",
    "selection_compile_receipt",
    "action_plan",
    "action_plan_continuity",
    "authorized_revision_cycle_registry",
    "commit_envelope",
    "outcome_schedule",
)

# This is the single production order in ``LocalV32AnalysisLane``.  It is
# intentionally explicit rather than inferred from files on disk: an
# uncheckpointed file may be adopted only when every predecessor is already
# bound and no successor is bound.  That makes a process-crash tail
# distinguishable from an injected or out-of-order artifact.
_ANALYSIS_LANE_CYCLE_ROLE_ORDER = (
    "supervisor_checkpoint",
    "supervisor_permit",
    "active_authority_projection",
    "source_capture",
    "source_snapshot",
    "source_qualification",
    "source_full_loader",
    "cycle_source_admission",
    "public_market_analysis_bundle",
    "support_pit_registry",
    "durable_source_replay",
    "public_market_graph_projection",
    "support_graph_registry",
    "verified_pit_evidence_availability_registry",
    "agent_market_graph_view",
    "timeframe_context",
    "proposal_packet",
    "proposal_input",
    "proposal_delivery",
    "proposal_consumption",
    "proposal_semantic_output",
    "proposal_compile_receipt",
    "dynamic_state",
    "action_evaluation",
    "dynamic_state_continuity",
    "selection_packet",
    "selection_input",
    "selection_delivery",
    "selection_consumption",
    "selection_semantic_output",
    "selection_compile_receipt",
    "action_plan",
    "action_plan_continuity",
    "authorized_revision_cycle_registry",
    "outcome_schedule",
    "shadow_decision_bundle",
    "commit_envelope",
    "analysis_acceptance",
)

_BINDING_FIELDS = frozenset(
    {
        "role",
        "cycle_index",
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_ACCEPTED_BINDING_FIELDS = frozenset(
    {
        "cycle_index",
        "accepted_at",
        "artifact_binding_digests",
        "acceptance_binding_digest",
        "recovery_mode",
        "tail_recovery_agent_invocations",
        "tail_recovery_network_requests",
        "accepted_state_is_fill_or_profit_claim",
        "external_execution_authority",
        "executable",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "experiment_contract_digest",
        "active_authority_digest",
        "revision",
        "predecessor_checkpoint_digest",
        "status",
        "total_analysis_cycles",
        "accepted_analysis_cycles",
        "next_analysis_cycle_index",
        "open_cycle_index",
        "artifact_bindings",
        "accepted_cycle_bindings",
        "current_dynamic_state_binding",
        "current_action_evaluation_binding",
        "current_action_plan_binding",
        "current_timeframe_cache_binding",
        "current_source_binding",
        "current_commit_binding",
        "terminal_outcome_checkpoint_digest",
        "failure_binding",
        "created_at",
        "updated_at",
        "tail_recovery_policy",
        "tail_recovery_agent_invocations_allowed",
        "tail_recovery_network_requests_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        "resume_allowed",
        CHECKPOINT_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32DynamicStoreError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32DynamicStoreError(code) from exc
    if parsed.tzinfo is None:
        raise V32DynamicStoreError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V32DynamicStoreError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32DynamicStoreError(code)
    return value


def _cycle(value: Any, code: str, *, allow_global: bool = False) -> int:
    minimum = 0 if allow_global else 1
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= TOTAL_ANALYSIS_CYCLES
    ):
        raise V32DynamicStoreError(code)
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    atomic_replace_json(
        path,
        document,
        short_write_error="V32_DYNAMIC_CHECKPOINT_SHORT_WRITE",
    )


def _binding_digest(binding: Mapping[str, Any]) -> str:
    return canonical_digest(dict(binding))


_ACCEPTANCE_COMPONENT_ROLE_MAP = MappingProxyType(
    {
        "analysis_tick_permit": "supervisor_permit",
        "active_authority_projection": "active_authority_projection",
        "cycle_source_admission": "cycle_source_admission",
        "public_market_analysis_bundle": "public_market_analysis_bundle",
        "public_market_graph_projection": "public_market_graph_projection",
        "pit_evidence_registry": "support_pit_registry",
        "verified_graph_dependency_registry": "support_graph_registry",
        "durable_source_replay_receipt": "durable_source_replay",
        "verified_pit_evidence_availability_registry": (
            "verified_pit_evidence_availability_registry"
        ),
        "agent_market_graph_view": "agent_market_graph_view",
        "current_timeframe_context_state": "timeframe_context",
        "proposal_input_context": "proposal_input",
        "proposal_delivery": "proposal_delivery",
        "proposal_consumption": "proposal_consumption",
        "proposal_semantic_compile_receipt": "proposal_compile_receipt",
        "compiled_dynamic_research_state": "dynamic_state",
        "sealed_action_evaluation": "action_evaluation",
        "replayable_shadow_decision_bundle": "shadow_decision_bundle",
        "dynamic_state_continuity_receipt": "dynamic_state_continuity",
        "selection_input_context": "selection_input",
        "selection_delivery": "selection_delivery",
        "selection_consumption": "selection_consumption",
        "selection_semantic_compile_receipt": "selection_compile_receipt",
        "final_dynamic_action_plan": "action_plan",
        "action_plan_continuity_receipt": "action_plan_continuity",
        "authorized_revision_cycle_registry": (
            "authorized_revision_cycle_registry"
        ),
        "two_stage_commit_envelope": "commit_envelope",
        "outcome_schedule_set": "outcome_schedule",
    }
)
if any(
    tuple(ARTIFACT_ROLE_SPECS[role]) != tuple(ACCEPTANCE_COMPONENT_SPECS[component])
    for component, role in _ACCEPTANCE_COMPONENT_ROLE_MAP.items()
):
    raise RuntimeError("V32_DYNAMIC_STORE_ACCEPTANCE_ROLE_SPEC_DRIFT")


def _acceptance_binding(binding: Mapping[str, Any]) -> dict[str, str]:
    """Project a store-owned binding into the acceptance public contract."""

    return {
        "relative_ref": str(binding["relative_ref"]),
        "schema_id": str(binding["schema_id"]),
        "digest_field": str(binding["digest_field"]),
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }


def _same_artifact_identity(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> bool:
    """Match immutable bytes even when two durable stores use different refs."""

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


def _validate_non_execution_boundary(document: Mapping[str, Any], *, role: str) -> None:
    if document.get("external_execution_authority") not in {
        None,
        EXTERNAL_EXECUTION_AUTHORITY,
    }:
        raise V32DynamicStoreError("V32_DYNAMIC_STORE_EXECUTION_BOUNDARY_INVALID")
    for field in ("executable", "account_access", "order_submission"):
        if document.get(field) is True:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_EXECUTION_BOUNDARY_INVALID")
    allowed_fill = {None, False, "NONE", "NONE_NO_FILL_MODEL"}
    allowed_pnl = {None, False, "NONE", "NONE_NO_PNL_MODEL"}
    if document.get("fill_claim") not in allowed_fill or document.get(
        "pnl_claim"
    ) not in allowed_pnl:
        raise V32DynamicStoreError("V32_DYNAMIC_STORE_MARKET_CLAIM_INVALID")
    if role == "analysis_acceptance" and (
        document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
        or document.get("claim")
        != "PROCESS_ACCEPTANCE_ONLY_NO_OUTCOME_EXECUTION_OR_PROFIT_CLAIM"
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
        raise V32DynamicStoreError("V32_DYNAMIC_STORE_ACCEPTANCE_CLAIM_INVALID")


class _LocalV32AnalysisLaneArtifactWriter:
    """Opaque, store-bound write capability issued once to the formal lane."""

    __slots__ = ("__store", "__capability")

    def __init__(self, store: "LocalV32DynamicStore", capability: object) -> None:
        self.__store = store
        self.__capability = capability

    def persist_verified_artifact(
        self,
        *,
        run_id: str,
        cycle_index: int,
        role: str,
        relative_ref: str,
        document: Mapping[str, Any],
        expected_checkpoint_digest: str,
        recorded_at: str,
    ) -> Mapping[str, Any]:
        return self.__store._persist_artifact_with_lane_capability(
            capability=self.__capability,
            run_id=run_id,
            cycle_index=cycle_index,
            role=role,
            relative_ref=relative_ref,
            document=document,
            expected_checkpoint_digest=expected_checkpoint_digest,
            recorded_at=recorded_at,
        )

    def recover_next_verified_orphan_artifact(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any] | None:
        """Adopt at most one exact process-crash tail without a new clock."""

        return self.__store._recover_next_unbound_artifact_with_lane_capability(
            capability=self.__capability,
            run_id=run_id,
            cycle_index=cycle_index,
            expected_checkpoint_digest=expected_checkpoint_digest,
        )


class LocalV32DynamicStore:
    """Durable owner for one local V3.2 research checkpoint and its artifacts."""

    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root).absolute()
        if supplied.exists() and supplied.is_symlink():
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ROOT_SYMLINK_FORBIDDEN")
        ensure_directory_tree(supplied)
        if supplied.is_symlink() or not supplied.is_dir():
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ROOT_INVALID")
        self.run_root = supplied
        self._physical_root = supplied.resolve(strict=True)
        self.checkpoint_path = self._safe_path(f"{STORE_ROOT}/checkpoint.json")
        # Runtime verification cache only.  It is neither authority nor
        # research evidence and is intentionally lost on process restart.
        # Every entry is keyed by the immutable binding digest and guarded by
        # a filesystem identity tuple including ctime, so ordinary tampering
        # invalidates the cache before bytes are trusted again.
        self._artifact_read_cache: dict[
            str, tuple[tuple[int, int, int, int, int], dict[str, Any]]
        ] = {}
        self._accepted_prefix_replay_cache: dict[str, str] = {}
        # The formal analysis lane receives the only raw artifact writer once.
        # This is component capability isolation for the trusted local process,
        # not a claim of resistance to malicious Python memory introspection.
        self.__lane_artifact_capability = object()
        self.__lane_artifact_writer_claimed = False
        self.__lane_artifact_claim_lock = threading.Lock()

    def _claim_local_analysis_lane_artifact_writer(
        self,
        *,
        owner: object,
    ) -> _LocalV32AnalysisLaneArtifactWriter:
        """Issue the sole store-bound writer; a second lane cannot acquire it."""

        # Runtime import avoids a module cycle while requiring the exact formal
        # lane type, this Store, and the Lane module's temporary post-validation
        # constructor marker.  Merely allocating the type with ``object.__new__``
        # cannot satisfy that marker.
        from .v32_local_analysis_lane import (
            LocalV32AnalysisLane,
            _is_formally_constructing_local_v32_analysis_lane,
        )

        if (
            type(owner) is not LocalV32AnalysisLane
            or getattr(owner, "_dynamic", None) is not self
            or not _is_formally_constructing_local_v32_analysis_lane(
                owner=owner, store=self
            )
        ):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_LANE_WRITER_OWNER_INVALID"
            )
        with self.__lane_artifact_claim_lock:
            if self.__lane_artifact_writer_claimed:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_LANE_WRITER_ALREADY_CLAIMED"
                )
            self.__lane_artifact_writer_claimed = True
            return _LocalV32AnalysisLaneArtifactWriter(
                self, self.__lane_artifact_capability
            )

    def _assert_root(self) -> None:
        if (
            not self.run_root.is_dir()
            or self.run_root.is_symlink()
            or self.run_root.resolve(strict=True) != self._physical_root
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ROOT_CHANGED")

    def _safe_path(self, relative_ref: str) -> Path:
        self._assert_root()
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_PATH_INVALID")
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or len(lexical.parts) < 2
            or lexical.parts[0] != STORE_ROOT
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_PATH_INVALID")
        current = self.run_root
        try:
            for part in lexical.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_SYMLINK_FORBIDDEN"
                    )
            current.resolve(strict=False).relative_to(self._physical_root)
        except V32DynamicStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_PATH_INVALID") from exc
        return current

    @contextmanager
    def _lock(self):
        lock_path = self._safe_path(f"{STORE_ROOT}/.locks/store.lock")
        ensure_directory_tree(lock_path.parent)
        lock_path = self._safe_path(f"{STORE_ROOT}/.locks/store.lock")
        key = str(lock_path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            with exclusive_lock_file(lock_path):
                yield

    def initialize_checkpoint(
        self,
        *,
        run_id: str,
        experiment_contract_digest: str,
        active_authority_digest: str,
        created_at: str,
    ) -> Mapping[str, Any]:
        run = _text(run_id, "V32_DYNAMIC_STORE_RUN_ID_INVALID")
        contract = _digest(
            experiment_contract_digest, "V32_DYNAMIC_STORE_CONTRACT_DIGEST_INVALID"
        )
        authority = _digest(
            active_authority_digest, "V32_DYNAMIC_STORE_AUTHORITY_DIGEST_INVALID"
        )
        created = _time(created_at, "V32_DYNAMIC_STORE_TIME_INVALID")
        with self._lock():
            if self.checkpoint_path.exists():
                checkpoint = self.load_checkpoint(run_id=run, _already_locked=True)
                if (
                    checkpoint["experiment_contract_digest"] != contract
                    or checkpoint["active_authority_digest"] != authority
                ):
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_INITIALIZATION_CONFLICT"
                    )
                confirm_existing_json(self.checkpoint_path, checkpoint)
                return checkpoint
            checkpoint = self_digest(
                {
                    "schema_id": CHECKPOINT_SCHEMA_ID,
                    "schema_version": CHECKPOINT_SCHEMA_VERSION,
                    "run_id": run,
                    "experiment_contract_digest": contract,
                    "active_authority_digest": authority,
                    "revision": 0,
                    "predecessor_checkpoint_digest": None,
                    "status": "READY",
                    "total_analysis_cycles": TOTAL_ANALYSIS_CYCLES,
                    "accepted_analysis_cycles": 0,
                    "next_analysis_cycle_index": 1,
                    "open_cycle_index": None,
                    "artifact_bindings": [],
                    "accepted_cycle_bindings": [],
                    "current_dynamic_state_binding": None,
                    "current_action_evaluation_binding": None,
                    "current_action_plan_binding": None,
                    "current_timeframe_cache_binding": None,
                    "current_source_binding": None,
                    "current_commit_binding": None,
                    "terminal_outcome_checkpoint_digest": None,
                    "failure_binding": None,
                    "created_at": created,
                    "updated_at": created,
                    "tail_recovery_policy": (
                        "DETERMINISTIC_PERSISTED_COMMIT_TAIL_ONLY"
                    ),
                    "tail_recovery_agent_invocations_allowed": 0,
                    "tail_recovery_network_requests_allowed": 0,
                    "source_scope": SOURCE_SCOPE,
                    "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                    "executable": False,
                    "account_access": False,
                    "order_submission": False,
                    "fill_claim": "NONE_NO_FILL_MODEL",
                    "pnl_claim": "NONE_NO_PNL_MODEL",
                    "resume_allowed": True,
                },
                CHECKPOINT_DIGEST_FIELD,
            )
            self._validate_checkpoint(checkpoint, run_id=run)
            ensure_directory_tree(self.checkpoint_path.parent)
            self._safe_path(f"{STORE_ROOT}/checkpoint.json")
            _atomic_json(self.checkpoint_path, checkpoint)
            return checkpoint

    def load_checkpoint(
        self, *, run_id: str, _already_locked: bool = False
    ) -> Mapping[str, Any]:
        if not _already_locked:
            with self._lock():
                return self.load_checkpoint(run_id=run_id, _already_locked=True)
        path = self._safe_path(f"{STORE_ROOT}/checkpoint.json")
        if not path.is_file() or path.is_symlink():
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CHECKPOINT_MISSING")
        try:
            checkpoint = load_json_strict(path)
        except (OSError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_CHECKPOINT_INVALID"
            ) from exc
        self._validate_checkpoint(checkpoint, run_id=run_id)
        try:
            confirm_existing_json(path, checkpoint)
        except (OSError, TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_CHECKPOINT_INVALID"
            ) from exc
        return checkpoint

    def _validate_checkpoint(self, checkpoint: Mapping[str, Any], *, run_id: str) -> None:
        try:
            verify_self_digest(checkpoint, CHECKPOINT_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_CHECKPOINT_DIGEST_INVALID"
            ) from exc
        if (
            not isinstance(checkpoint, Mapping)
            or set(checkpoint) != _CHECKPOINT_FIELDS
            or checkpoint.get("schema_id") != CHECKPOINT_SCHEMA_ID
            or checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION
            or checkpoint.get("run_id") != run_id
            or checkpoint.get("status") not in STATUSES
            or checkpoint.get("total_analysis_cycles") != TOTAL_ANALYSIS_CYCLES
            or isinstance(checkpoint.get("revision"), bool)
            or not isinstance(checkpoint.get("revision"), int)
            or checkpoint.get("revision") < 0
            or not isinstance(checkpoint.get("artifact_bindings"), list)
            or not isinstance(checkpoint.get("accepted_cycle_bindings"), list)
            or checkpoint.get("tail_recovery_policy")
            != "DETERMINISTIC_PERSISTED_COMMIT_TAIL_ONLY"
            or checkpoint.get("tail_recovery_agent_invocations_allowed") != 0
            or checkpoint.get("tail_recovery_network_requests_allowed") != 0
            or checkpoint.get("source_scope") != SOURCE_SCOPE
            or checkpoint.get("external_execution_authority")
            != EXTERNAL_EXECUTION_AUTHORITY
            or checkpoint.get("executable") is not False
            or checkpoint.get("account_access") is not False
            or checkpoint.get("order_submission") is not False
            or checkpoint.get("fill_claim") != "NONE_NO_FILL_MODEL"
            or checkpoint.get("pnl_claim") != "NONE_NO_PNL_MODEL"
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CHECKPOINT_INVALID")
        _digest(
            checkpoint.get("experiment_contract_digest"),
            "V32_DYNAMIC_STORE_CHECKPOINT_INVALID",
        )
        _digest(
            checkpoint.get("active_authority_digest"),
            "V32_DYNAMIC_STORE_CHECKPOINT_INVALID",
        )
        predecessor = _digest(
            checkpoint.get("predecessor_checkpoint_digest"),
            "V32_DYNAMIC_STORE_CHECKPOINT_INVALID",
            nullable=True,
        )
        if (checkpoint["revision"] == 0) != (predecessor is None):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CHECKPOINT_INVALID")
        created = _moment(checkpoint["created_at"], "V32_DYNAMIC_STORE_TIME_INVALID")
        updated = _moment(checkpoint["updated_at"], "V32_DYNAMIC_STORE_TIME_INVALID")
        if updated < created:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_TIME_ROLLBACK")

        accepted = checkpoint.get("accepted_analysis_cycles")
        next_cycle = checkpoint.get("next_analysis_cycle_index")
        open_cycle = checkpoint.get("open_cycle_index")
        if (
            isinstance(accepted, bool)
            or not isinstance(accepted, int)
            or not 0 <= accepted <= TOTAL_ANALYSIS_CYCLES
            or isinstance(next_cycle, bool)
            or not isinstance(next_cycle, int)
            or next_cycle != accepted + 1
            or not 1 <= next_cycle <= TOTAL_ANALYSIS_CYCLES + 1
            or (
                open_cycle is not None
                and (
                    isinstance(open_cycle, bool)
                    or not isinstance(open_cycle, int)
                    or open_cycle != next_cycle
                    or not 1 <= open_cycle <= TOTAL_ANALYSIS_CYCLES
                )
            )
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_COUNTER_INVALID")
        status = checkpoint["status"]
        if (
            (status == "READY" and (open_cycle is not None or accepted >= 16))
            or (status == "OPEN" and open_cycle is None)
            or (
                status in {"OUTCOME_TAIL", "TERMINAL"}
                and (accepted != 16 or next_cycle != 17 or open_cycle is not None)
            )
            or (status == "TERMINAL")
            != (checkpoint["terminal_outcome_checkpoint_digest"] is not None)
            or (status == "FAILED") != (checkpoint["failure_binding"] is not None)
            or checkpoint["resume_allowed"] is not (status not in {"TERMINAL", "FAILED"})
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_STATUS_INVALID")
        if checkpoint["terminal_outcome_checkpoint_digest"] is not None:
            _digest(
                checkpoint["terminal_outcome_checkpoint_digest"],
                "V32_DYNAMIC_STORE_STATUS_INVALID",
            )

        bindings = checkpoint["artifact_bindings"]
        verified_bindings: list[Mapping[str, Any]] = []
        identities: set[tuple[int, str]] = set()
        refs: set[str] = set()
        for binding in bindings:
            document = self._read_binding(binding)
            identity = (binding["cycle_index"], binding["role"])
            if identity in identities or binding["relative_ref"] in refs:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ARTIFACT_IDENTITY_DUPLICATE"
                )
            identities.add(identity)
            refs.add(binding["relative_ref"])
            if document.get("run_id") not in {None, run_id}:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_RUN_BINDING_INVALID")
            verified_bindings.append(binding)

        accepted_bindings = checkpoint["accepted_cycle_bindings"]
        if len(accepted_bindings) != accepted:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ACCEPTED_PREFIX_INVALID")
        binding_digests = {_binding_digest(binding): binding for binding in bindings}
        prior_accepted_at = created
        for index, entry in enumerate(accepted_bindings, start=1):
            if (
                not isinstance(entry, Mapping)
                or set(entry) != _ACCEPTED_BINDING_FIELDS
                or entry.get("cycle_index") != index
                or entry.get("recovery_mode")
                not in {"NORMAL_COMMIT", "DETERMINISTIC_COMMIT_TAIL_RECOVERY"}
                or entry.get("tail_recovery_agent_invocations") != 0
                or entry.get("tail_recovery_network_requests") != 0
                or entry.get("accepted_state_is_fill_or_profit_claim") is not False
                or entry.get("external_execution_authority")
                != EXTERNAL_EXECUTION_AUTHORITY
                or entry.get("executable") is not False
                or not isinstance(entry.get("artifact_binding_digests"), Mapping)
                or set(entry["artifact_binding_digests"])
                != set(_REQUIRED_ACCEPTANCE_ROLES)
            ):
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ACCEPTED_BINDING_INVALID"
                )
            accepted_at = _moment(
                entry["accepted_at"], "V32_DYNAMIC_STORE_TIME_INVALID"
            )
            if accepted_at < prior_accepted_at or accepted_at > updated:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_TIME_ORDER_INVALID")
            prior_accepted_at = accepted_at
            for role, digest in entry["artifact_binding_digests"].items():
                _digest(digest, "V32_DYNAMIC_STORE_ACCEPTED_BINDING_INVALID")
                binding = binding_digests.get(digest)
                if (
                    binding is None
                    or binding["role"] != role
                    or binding["cycle_index"] != index
                ):
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_ACCEPTED_BINDING_INVALID"
                    )
            acceptance_digest = entry["acceptance_binding_digest"]
            _digest(
                acceptance_digest, "V32_DYNAMIC_STORE_ACCEPTED_BINDING_INVALID"
            )
            acceptance_binding = binding_digests.get(acceptance_digest)
            if (
                acceptance_binding is None
                or acceptance_binding["role"] != "analysis_acceptance"
                or acceptance_binding["cycle_index"] != index
            ):
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ACCEPTED_BINDING_INVALID"
                )
            required = self._required_acceptance_bindings(
                checkpoint, cycle_index=index
            )
            acceptance_document = self._read_binding(acceptance_binding)
            if self._verify_acceptance(
                checkpoint,
                cycle_index=index,
                required=required,
                acceptance=acceptance_document,
                allow_verified_prefix_cache=True,
            ) != acceptance_binding["semantic_digest"]:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ACCEPTED_BINDING_INVALID"
                )

        head_specs = {
            "current_dynamic_state_binding": "dynamic_state",
            "current_action_evaluation_binding": "action_evaluation",
            "current_action_plan_binding": "action_plan",
            "current_timeframe_cache_binding": "timeframe_context",
            "current_source_binding": "cycle_source_admission",
            "current_commit_binding": "commit_envelope",
        }
        for field, role in head_specs.items():
            head = checkpoint[field]
            if accepted == 0:
                if head is not None:
                    raise V32DynamicStoreError("V32_DYNAMIC_STORE_HEAD_INVALID")
                continue
            if (
                not isinstance(head, Mapping)
                or _binding_digest(head) not in binding_digests
                or head.get("role") != role
                or head.get("cycle_index") != accepted
            ):
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_HEAD_INVALID")
        failure = checkpoint["failure_binding"]
        if failure is not None and (
            not isinstance(failure, Mapping)
            or _binding_digest(failure) not in binding_digests
            or failure.get("role") not in {"research_failure", "supervisor_failure"}
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_FAILURE_BINDING_INVALID")

    def _replace_checkpoint(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        candidate: Mapping[str, Any],
        updated_at: str,
    ) -> Mapping[str, Any]:
        current = self.load_checkpoint(run_id=run_id, _already_locked=True)
        expected = _digest(
            expected_checkpoint_digest, "V32_DYNAMIC_STORE_CAS_DIGEST_INVALID"
        )
        if current[CHECKPOINT_DIGEST_FIELD] != expected:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CAS_CONFLICT")
        update_time = _time(updated_at, "V32_DYNAMIC_STORE_TIME_INVALID")
        if _moment(update_time, "V32_DYNAMIC_STORE_TIME_INVALID") < _moment(
            current["updated_at"], "V32_DYNAMIC_STORE_TIME_INVALID"
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_TIME_ROLLBACK")
        payload = dict(candidate)
        payload.pop(CHECKPOINT_DIGEST_FIELD, None)
        payload["revision"] = current["revision"] + 1
        payload["predecessor_checkpoint_digest"] = current[
            CHECKPOINT_DIGEST_FIELD
        ]
        payload["updated_at"] = update_time
        next_checkpoint = self_digest(payload, CHECKPOINT_DIGEST_FIELD)
        self._validate_checkpoint(next_checkpoint, run_id=run_id)
        _atomic_json(self.checkpoint_path, next_checkpoint)
        return next_checkpoint

    def _validate_artifact_request(
        self,
        *,
        run_id: str,
        cycle_index: int,
        role: str,
        relative_ref: str,
        document: Mapping[str, Any],
    ) -> tuple[str, str, str]:
        run = _text(run_id, "V32_DYNAMIC_STORE_RUN_ID_INVALID")
        cycle = _cycle(
            cycle_index, "V32_DYNAMIC_STORE_CYCLE_INVALID", allow_global=True
        )
        role_text = _text(role, "V32_DYNAMIC_STORE_ROLE_INVALID")
        spec = ARTIFACT_ROLE_SPECS.get(role_text)
        if spec is None:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ROLE_NOT_ALLOWED")
        if (cycle == 0) != (role_text in _GLOBAL_ROLES):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ROLE_SCOPE_INVALID")
        path = self._safe_path(relative_ref)
        expected_prefix = (
            f"{STORE_ROOT}/shared/"
            if cycle == 0
            else f"{STORE_ROOT}/cycles/{cycle:04d}/"
        )
        if not relative_ref.startswith(expected_prefix) or path == self.run_root:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ROLE_PATH_INVALID")
        if not isinstance(document, Mapping):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_DOCUMENT_INVALID")
        schema_id, digest_field = spec
        if document.get("schema_id") != schema_id:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_SCHEMA_NOT_ALLOWED")
        try:
            verify_self_digest(document, digest_field)
        except (TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_DOCUMENT_DIGEST_INVALID"
            ) from exc
        if document.get("run_id") not in {None, run}:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_RUN_BINDING_INVALID")
        if document.get("cycle_index") not in {None, cycle}:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CYCLE_BINDING_INVALID")
        if role_text.startswith("proposal_") and role_text != "proposal_packet":
            if document.get("agent_stage") not in {None, "PROPOSAL"}:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_STAGE_BINDING_INVALID")
        if role_text.startswith("selection_") and role_text != "selection_packet":
            if document.get("agent_stage") not in {None, "SELECTION"}:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_STAGE_BINDING_INVALID")
        _validate_non_execution_boundary(document, role=role_text)
        return schema_id, digest_field, run

    def _write_artifact_file(
        self,
        *,
        cycle_index: int,
        role: str,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
    ) -> dict[str, Any]:
        path = self._safe_path(relative_ref)
        ensure_directory_tree(path.parent)
        path = self._safe_path(relative_ref)
        try:
            write_once_json(path, document)
            readback = load_json_strict(path)
            semantic = verify_self_digest(readback, digest_field)
        except (OSError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_WRITE_OR_READBACK_INVALID"
            ) from exc
        if readback != dict(document) or readback.get("schema_id") != schema_id:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_READBACK_MISMATCH")
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_WRITE_OR_READBACK_INVALID"
            ) from exc
        return {
            "role": role,
            "cycle_index": cycle_index,
            "relative_ref": relative_ref,
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": semantic,
            "physical_sha256": hashlib.sha256(
                canonical_bytes(dict(document)) + b"\n"
            ).hexdigest(),
        }

    def _read_binding(self, binding: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(binding, Mapping) or set(binding) != _BINDING_FIELDS:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_INVALID")
        role = binding.get("role")
        spec = ARTIFACT_ROLE_SPECS.get(role)
        if spec is None or tuple(spec) != (
            binding.get("schema_id"),
            binding.get("digest_field"),
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_INVALID")
        cycle = _cycle(
            binding.get("cycle_index"),
            "V32_DYNAMIC_STORE_BINDING_INVALID",
            allow_global=True,
        )
        if (cycle == 0) != (role in _GLOBAL_ROLES):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_INVALID")
        ref = _text(binding.get("relative_ref"), "V32_DYNAMIC_STORE_BINDING_INVALID")
        expected_prefix = (
            f"{STORE_ROOT}/shared/"
            if cycle == 0
            else f"{STORE_ROOT}/cycles/{cycle:04d}/"
        )
        if not ref.startswith(expected_prefix):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_INVALID")
        path = self._safe_path(ref)
        if not path.is_file() or path.is_symlink():
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_FILE_INVALID")
        try:
            stat = path.stat(follow_symlinks=False)
            stat_identity = (
                int(stat.st_dev),
                int(stat.st_ino),
                int(stat.st_size),
                int(stat.st_mtime_ns),
                int(stat.st_ctime_ns),
            )
        except OSError as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_BINDING_FILE_INVALID"
            ) from exc
        cache_key = _binding_digest(binding)
        cached = self._artifact_read_cache.get(cache_key)
        if cached is not None and cached[0] == stat_identity:
            try:
                confirm_existing_json(path, cached[1])
            except (OSError, TypeError, ValueError) as exc:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_BINDING_FILE_INVALID"
                ) from exc
            return deepcopy(cached[1])
        try:
            document = load_json_strict(path)
            semantic = verify_self_digest(document, binding["digest_field"])
        except (OSError, ValueError) as exc:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_FILE_INVALID") from exc
        if (
            document.get("schema_id") != binding["schema_id"]
            or semantic
            != _digest(
                binding.get("semantic_digest"),
                "V32_DYNAMIC_STORE_BINDING_INVALID",
            )
            or _file_sha256(path)
            != _digest(
                binding.get("physical_sha256"),
                "V32_DYNAMIC_STORE_BINDING_INVALID",
            )
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_MISMATCH")
        _validate_non_execution_boundary(document, role=role)
        try:
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_BINDING_FILE_INVALID"
            ) from exc
        cached_document = deepcopy(dict(document))
        self._artifact_read_cache[cache_key] = (stat_identity, cached_document)
        return deepcopy(cached_document)

    def load_artifact(self, binding: Mapping[str, Any]) -> Mapping[str, Any]:
        with self._lock():
            return self._read_binding(binding)

    def open_cycle(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
        opened_at: str,
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index, "V32_DYNAMIC_STORE_CYCLE_INVALID")
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_CAS_CONFLICT")
            if (
                current["status"] != "READY"
                or current["next_analysis_cycle_index"] != cycle
            ):
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_OPEN_SEQUENCE_INVALID")
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=expected_checkpoint_digest,
                candidate={**current, "status": "OPEN", "open_cycle_index": cycle},
                updated_at=opened_at,
            )

    def _persist_artifact_locked(
        self,
        *,
        run_id: str,
        cycle_index: int,
        role: str,
        relative_ref: str,
        document: Mapping[str, Any],
        expected_checkpoint_digest: str,
        recorded_at: str,
    ) -> Mapping[str, Any]:
        schema_id, digest_field, run = self._validate_artifact_request(
            run_id=run_id,
            cycle_index=cycle_index,
            role=role,
            relative_ref=relative_ref,
            document=document,
        )
        record_time = _time(recorded_at, "V32_DYNAMIC_STORE_TIME_INVALID")
        current = self.load_checkpoint(run_id=run, _already_locked=True)
        if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CAS_CONFLICT")
        existing = [
            binding
            for binding in current["artifact_bindings"]
            if binding["cycle_index"] == cycle_index and binding["role"] == role
        ]
        if existing:
            durable = self._read_binding(existing[0])
            if durable != dict(document) or existing[0]["relative_ref"] != relative_ref:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_WRITE_ONCE_CONFLICT"
                )
            confirm_existing_json(self._safe_path(relative_ref), document)
            return current
        if current["status"] in {"TERMINAL", "FAILED"}:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_TERMINAL_WRITE_FORBIDDEN")
        if cycle_index == 0:
            if current["status"] not in {"READY", "OPEN"}:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_GLOBAL_WRITE_INVALID")
        elif (
            current["status"] != "OPEN"
            or current["open_cycle_index"] != cycle_index
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CYCLE_NOT_OPEN")
        binding = self._write_artifact_file(
            cycle_index=cycle_index,
            role=role,
            relative_ref=relative_ref,
            document=document,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        return self._replace_checkpoint(
            run_id=run,
            expected_checkpoint_digest=expected_checkpoint_digest,
            candidate={
                **current,
                "artifact_bindings": [*current["artifact_bindings"], binding],
            },
            updated_at=record_time,
        )

    def _persist_artifact_with_lane_capability(
        self,
        *,
        capability: object,
        run_id: str,
        cycle_index: int,
        role: str,
        relative_ref: str,
        document: Mapping[str, Any],
        expected_checkpoint_digest: str,
        recorded_at: str,
    ) -> Mapping[str, Any]:
        """Persist at the sole production edge after capability identity check.

        Ordinary store holders do not possess the opaque identity.  The writer
        issued once to ``LocalV32AnalysisLane`` is the only production caller.
        """
        if (
            capability is not self.__lane_artifact_capability
            or not self.__lane_artifact_writer_claimed
        ):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_LANE_WRITE_CAPABILITY_INVALID"
            )
        with self._lock():
            return self._persist_artifact_locked(
                run_id=run_id,
                cycle_index=cycle_index,
                role=role,
                relative_ref=relative_ref,
                document=document,
                expected_checkpoint_digest=expected_checkpoint_digest,
                recorded_at=recorded_at,
            )

    @staticmethod
    def _find_binding(
        checkpoint: Mapping[str, Any], *, cycle_index: int, role: str
    ) -> Mapping[str, Any] | None:
        matches = [
            binding
            for binding in checkpoint["artifact_bindings"]
            if binding["cycle_index"] == cycle_index and binding["role"] == role
        ]
        if len(matches) > 1:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_BINDING_AMBIGUOUS")
        return matches[0] if matches else None

    @staticmethod
    def _production_cycle_artifact_ref(*, cycle_index: int, role: str) -> str:
        if role == "analysis_acceptance":
            return (
                f"{STORE_ROOT}/cycles/{cycle_index:04d}/final/"
                "analysis-acceptance.json"
            )
        return (
            f"{STORE_ROOT}/cycles/{cycle_index:04d}/analysis-lane/"
            f"{role}.json"
        )

    def _verify_recovered_orphan_dependencies(
        self,
        checkpoint: Mapping[str, Any],
        *,
        cycle_index: int,
        role: str,
        document: Mapping[str, Any],
    ) -> None:
        """Replay cross-document contracts for the two critical tail classes."""

        if role in {"proposal_input", "selection_input"}:
            packet_role = (
                "proposal_packet" if role == "proposal_input" else "selection_packet"
            )
            packet_binding = self._find_binding(
                checkpoint, cycle_index=cycle_index, role=packet_role
            )
            if packet_binding is None:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_PREDECESSOR_INVALID"
                )
            # The qualified production mailbox is INLINE-only.  A sharded
            # request has no durable mailbox package before enqueue and cannot
            # be reconstructed safely from an unbound file alone.
            if document.get("context_delivery_mode") != "INLINE":
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_CONTEXT_UNRECOVERABLE"
                )
            try:
                verify_v32_agent_input_context_v1(document)
                packet = resolve_v32_agent_canonical_packet_v1(document)
            except (KeyError, TypeError, ValueError) as exc:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_CONTEXT_INVALID"
                ) from exc
            if packet != self._read_binding(packet_binding):
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_CONTEXT_INVALID"
                )
            return

        if role == "commit_envelope":
            stage_roles = (
                "proposal_packet",
                "proposal_input",
                "proposal_delivery",
                "proposal_consumption",
                "selection_packet",
                "selection_input",
                "selection_delivery",
                "selection_consumption",
            )
            bindings: dict[str, Mapping[str, Any]] = {}
            for stage_role in stage_roles:
                binding = self._find_binding(
                    checkpoint, cycle_index=cycle_index, role=stage_role
                )
                if binding is None:
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_ORPHAN_PREDECESSOR_INVALID"
                    )
                bindings[stage_role] = binding
            documents = {
                stage_role: self._read_binding(binding)
                for stage_role, binding in bindings.items()
            }
            packages = self._acceptance_context_packages(
                checkpoint,
                cycle_index=cycle_index,
                required=bindings,
                documents=documents,
            )
            try:
                verify_v32_two_stage_commit_envelope_v1(
                    document,
                    proposal_input_context=documents["proposal_input"],
                    proposal_delivery=documents["proposal_delivery"],
                    proposal_consumption=documents["proposal_consumption"],
                    selection_input_context=documents["selection_input"],
                    selection_delivery=documents["selection_delivery"],
                    selection_consumption=documents["selection_consumption"],
                    proposal_lossless_context_package=packages[
                        "proposal_lossless_context_package"
                    ],
                    selection_lossless_context_package=packages[
                        "selection_lossless_context_package"
                    ],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_COMMIT_INVALID"
                ) from exc
            prior = checkpoint.get("current_commit_binding")
            expected_previous = (
                None if cycle_index == 1 else prior["semantic_digest"]
                if isinstance(prior, Mapping)
                else None
            )
            if document.get("previous_commit_envelope_digest") != expected_previous:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_COMMIT_INVALID"
                )
            return

        if role == "analysis_acceptance":
            required = self._required_acceptance_bindings(
                checkpoint, cycle_index=cycle_index
            )
            digest = self._verify_acceptance(
                checkpoint,
                cycle_index=cycle_index,
                required=required,
                acceptance=document,
            )
            if digest != document.get(ACCEPTANCE_DIGEST_FIELD):
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_ACCEPTANCE_INVALID"
                )

    def _recover_next_unbound_artifact_locked(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any] | None:
        """Attach one exact durable artifact tail to its predecessor checkpoint."""

        run = _text(run_id, "V32_DYNAMIC_STORE_RUN_ID_INVALID")
        cycle = _cycle(cycle_index, "V32_DYNAMIC_STORE_CYCLE_INVALID")
        current = self.load_checkpoint(run_id=run, _already_locked=True)
        if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CAS_CONFLICT")
        if current["status"] != "OPEN" or current["open_cycle_index"] != cycle:
            return None

        bound_roles = {
            str(binding["role"])
            for binding in current["artifact_bindings"]
            if binding["cycle_index"] == cycle
        }
        orphan_candidates: list[tuple[str, str, Path]] = []
        for role in _ANALYSIS_LANE_CYCLE_ROLE_ORDER:
            if role in bound_roles:
                continue
            relative_ref = self._production_cycle_artifact_ref(
                cycle_index=cycle, role=role
            )
            path = self._safe_path(relative_ref)
            if path.is_symlink():
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ORPHAN_PATH_INVALID"
                )
            if path.exists():
                if not path.is_file():
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_ORPHAN_PATH_INVALID"
                    )
                orphan_candidates.append((role, relative_ref, path))
        if not orphan_candidates:
            return None
        if len(orphan_candidates) != 1:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ORPHAN_AMBIGUOUS")

        role, relative_ref, path = orphan_candidates[0]
        role_index = _ANALYSIS_LANE_CYCLE_ROLE_ORDER.index(role)
        if any(
            predecessor not in bound_roles
            for predecessor in _ANALYSIS_LANE_CYCLE_ROLE_ORDER[:role_index]
        ) or any(
            successor in bound_roles
            for successor in _ANALYSIS_LANE_CYCLE_ROLE_ORDER[role_index + 1 :]
        ):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ORPHAN_PREDECESSOR_INVALID"
            )
        try:
            document = load_json_strict(path)
            schema_id, digest_field, validated_run = self._validate_artifact_request(
                run_id=run,
                cycle_index=cycle,
                role=role,
                relative_ref=relative_ref,
                document=document,
            )
            confirm_existing_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            if isinstance(exc, V32DynamicStoreError):
                raise
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ORPHAN_ARTIFACT_INVALID"
            ) from exc
        if validated_run != run:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ORPHAN_ARTIFACT_INVALID"
            )
        self._verify_recovered_orphan_dependencies(
            current,
            cycle_index=cycle,
            role=role,
            document=document,
        )
        # Reuse the standard exact readback/binding constructor.  Because the
        # bytes already exist, this performs an identical-winner confirmation;
        # it never overwrites or synthesizes a replacement document.
        binding = self._write_artifact_file(
            cycle_index=cycle,
            role=role,
            relative_ref=relative_ref,
            document=document,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        checkpoint = self._replace_checkpoint(
            run_id=run,
            expected_checkpoint_digest=expected_checkpoint_digest,
            candidate={
                **current,
                "artifact_bindings": [*current["artifact_bindings"], binding],
            },
            # Recovery has no clock capability.  Preserve the predecessor's
            # already durable time while recording only the new CAS revision.
            updated_at=str(current["updated_at"]),
        )
        return {
            "checkpoint": checkpoint,
            "binding": binding,
            "document": deepcopy(dict(document)),
            "recovered_role": role,
            "agent_invocations": 0,
            "network_requests": 0,
            "clock_reads": 0,
        }

    def _recover_next_unbound_artifact_with_lane_capability(
        self,
        *,
        capability: object,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
    ) -> Mapping[str, Any] | None:
        if (
            capability is not self.__lane_artifact_capability
            or not self.__lane_artifact_writer_claimed
        ):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_LANE_WRITE_CAPABILITY_INVALID"
            )
        with self._lock():
            return self._recover_next_unbound_artifact_locked(
                run_id=run_id,
                cycle_index=cycle_index,
                expected_checkpoint_digest=expected_checkpoint_digest,
            )

    def _required_acceptance_bindings(
        self, checkpoint: Mapping[str, Any], *, cycle_index: int
    ) -> dict[str, Mapping[str, Any]]:
        required: dict[str, Mapping[str, Any]] = {}
        for role in _REQUIRED_ACCEPTANCE_ROLES:
            binding = self._find_binding(
                checkpoint, cycle_index=cycle_index, role=role
            )
            if binding is None:
                raise V32DynamicStoreError(
                    f"V32_DYNAMIC_STORE_REQUIRED_ARTIFACT_MISSING:{role}"
                )
            required[role] = binding
        return required

    def _acceptance_context_packages(
        self,
        checkpoint: Mapping[str, Any],
        *,
        cycle_index: int,
        required: Mapping[str, Mapping[str, Any]],
        documents: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Mapping[str, Any] | None]:
        """Replay lossless Agent input material from the owning mailbox.

        Inline contexts remain self-contained.  A sharded context is never
        reconstructed from a caller-supplied locator: the write-once mailbox
        must replay its complete consumed stage and return the exact manifest,
        selection, every shard, and original canonical packet.
        """

        if checkpoint.get("run_id") is None:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CONTEXT_REPLAY_INVALID")
        packages: dict[str, Mapping[str, Any] | None] = {}
        stage_specs = (
            (
                "PROPOSAL",
                "proposal_input",
                "proposal_packet",
                "proposal_delivery",
                "proposal_consumption",
                "proposal_lossless_context_package",
            ),
            (
                "SELECTION",
                "selection_input",
                "selection_packet",
                "selection_delivery",
                "selection_consumption",
                "selection_lossless_context_package",
            ),
        )
        mailbox: LocalV32CurrentRootAgentMailbox | None = None
        for (
            stage,
            input_role,
            packet_role,
            delivery_role,
            consumption_role,
            package_key,
        ) in stage_specs:
            context = documents[input_role]
            mode = context.get("context_delivery_mode")
            if mode == "INLINE":
                try:
                    verify_v32_agent_input_context_v1(context)
                    packet = resolve_v32_agent_canonical_packet_v1(context)
                except (KeyError, TypeError, ValueError) as exc:
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_CONTEXT_REPLAY_INVALID"
                    ) from exc
                if packet != documents[packet_role]:
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_CONTEXT_PACKET_MISMATCH"
                    )
                packages[package_key] = None
                continue
            if mode != "LOSSLESS_SHARDED":
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_CONTEXT_DELIVERY_MODE_INVALID"
                )
            try:
                if mailbox is None:
                    mailbox = LocalV32CurrentRootAgentMailbox(self.run_root)
                chain = mailbox.load_stage_chain(
                    run_id=checkpoint["run_id"],
                    cycle_index=cycle_index,
                    stage=stage,
                )
                package = chain.get("lossless_context_package")
                request = chain.get("request")
                if (
                    chain.get("stage_status") != "CONSUMED"
                    or not isinstance(package, Mapping)
                    or not isinstance(request, Mapping)
                    or request.get("agent_input_context") != context
                    or chain.get("canonical_packet_original")
                    != documents[packet_role]
                    or chain.get("agent_delivery") != documents[delivery_role]
                    or chain.get("agent_consumption")
                    != documents[consumption_role]
                ):
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_MAILBOX_CONTEXT_CHAIN_MISMATCH"
                    )
                verify_v32_agent_input_context_v1(
                    context, lossless_context_package=package
                )
                packet = resolve_v32_agent_canonical_packet_v1(
                    context, lossless_context_package=package
                )
            except (
                KeyError,
                TypeError,
                ValueError,
                V32CurrentRootAgentMailboxStoreError,
            ) as exc:
                if isinstance(exc, V32DynamicStoreError):
                    raise
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_CONTEXT_REPLAY_INVALID"
                ) from exc
            if packet != documents[packet_role]:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_CONTEXT_PACKET_MISMATCH"
                )
            packages[package_key] = package
        return packages

    def _acceptance_replay_material(
        self,
        checkpoint: Mapping[str, Any],
        *,
        cycle_index: int,
        required: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        documents = {
            role: self._read_binding(binding)
            for role, binding in required.items()
        }
        context_packages = self._acceptance_context_packages(
            checkpoint,
            cycle_index=cycle_index,
            required=required,
            documents=documents,
        )
        previous_projection = None
        previous_projection_binding = None
        if cycle_index > 1:
            previous_projection_binding = self._find_binding(
                checkpoint,
                cycle_index=cycle_index - 1,
                role="public_market_graph_projection",
            )
            if previous_projection_binding is None:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_PREVIOUS_GRAPH_PROJECTION_MISSING"
                )
            previous_projection = self._read_binding(
                previous_projection_binding
            )
        try:
            bundle_digest = verify_v32_public_market_analysis_bundle(
                documents["public_market_analysis_bundle"]
            )
            projection_digest = verify_v32_public_market_graph_projection_v1(
                documents["public_market_graph_projection"],
                analysis_bundle=documents["public_market_analysis_bundle"],
                previous_projection=previous_projection,
            )
            registry_digest = verify_v32_verified_graph_dependency_registry_v1(
                documents["support_graph_registry"],
                graph_projection=documents["public_market_graph_projection"],
                analysis_bundle=documents["public_market_analysis_bundle"],
                previous_projection=previous_projection,
            )
            source_replay_digest = verify_v32_durable_source_replay_receipt(
                documents["durable_source_replay"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_PUBLIC_GRAPH_REPLAY_INVALID"
            ) from exc
        if (
            bundle_digest
            != required["public_market_analysis_bundle"]["semantic_digest"]
            or projection_digest
            != required["public_market_graph_projection"]["semantic_digest"]
            or registry_digest
            != required["support_graph_registry"]["semantic_digest"]
            or source_replay_digest
            != required["durable_source_replay"]["semantic_digest"]
        ):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_PUBLIC_GRAPH_BINDING_INVALID"
            )
        components = {
            component: documents[role]
            for component, role in _ACCEPTANCE_COMPONENT_ROLE_MAP.items()
        }
        component_bindings = {
            component: _acceptance_binding(required[role])
            for component, role in _ACCEPTANCE_COMPONENT_ROLE_MAP.items()
        }
        proposal_payload = canonical_bytes(
            dict(documents["proposal_semantic_output"])
        ).decode("utf-8")
        selection_payload = canonical_bytes(
            dict(documents["selection_semantic_output"])
        ).decode("utf-8")
        if (
            documents["proposal_delivery"].get("payload_utf8")
            != proposal_payload
            or documents["selection_delivery"].get("payload_utf8")
            != selection_payload
            or documents["proposal_compile_receipt"].get(
                "proposal_semantic_output_digest"
            )
            != required["proposal_semantic_output"]["semantic_digest"]
            or documents["selection_compile_receipt"].get(
                "selection_semantic_output_digest"
            )
            != required["selection_semantic_output"]["semantic_digest"]
            or documents["proposal_packet"].get("support_documents", {}).get(
                "active_authority_projection"
            )
            != documents["active_authority_projection"]
            or not _same_artifact_identity(
                documents["proposal_packet"].get("support_bindings", {}).get(
                    "active_authority_projection"
                ),
                _acceptance_binding(required["active_authority_projection"]),
            )
            or documents["proposal_packet"].get("support_documents", {}).get(
                "agent_market_graph_view"
            )
            != documents["agent_market_graph_view"]
            or not _same_artifact_identity(
                documents["proposal_packet"].get("support_bindings", {}).get(
                    "agent_market_graph_view"
                ),
                _acceptance_binding(required["agent_market_graph_view"]),
            )
            or not _same_artifact_identity(
                documents["durable_source_replay"].get(
                    "market_analysis_bundle_binding"
                ),
                _acceptance_binding(required["public_market_analysis_bundle"]),
            )
            or not _same_artifact_identity(
                documents["durable_source_replay"].get(
                    "source_pit_registry_binding"
                ),
                _acceptance_binding(required["support_pit_registry"]),
            )
            or not _same_artifact_identity(
                documents["durable_source_replay"].get(
                    "cycle_source_admission_binding"
                ),
                _acceptance_binding(required["cycle_source_admission"]),
            )
        ):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_SEMANTIC_ARTIFACT_BINDING_INVALID"
            )

        prior_schedule_bindings = sorted(
            (
                binding
                for binding in checkpoint["artifact_bindings"]
                if binding["role"] == "outcome_schedule"
                and binding["cycle_index"] < cycle_index
            ),
            key=lambda row: row["cycle_index"],
        )
        prior_schedule_sets = [
            self._read_binding(binding) for binding in prior_schedule_bindings
        ]
        previous_timeframe = None
        previous_timeframe_binding = None
        previous_acceptance = None
        previous_acceptance_binding = None
        previous_availability = None
        previous_availability_binding = None
        if cycle_index > 1:
            timeframe_binding = self._find_binding(
                checkpoint,
                cycle_index=cycle_index - 1,
                role="timeframe_context",
            )
            acceptance_binding = self._find_binding(
                checkpoint,
                cycle_index=cycle_index - 1,
                role="analysis_acceptance",
            )
            availability_binding = self._find_binding(
                checkpoint,
                cycle_index=cycle_index - 1,
                role="verified_pit_evidence_availability_registry",
            )
            if (
                timeframe_binding is None
                or acceptance_binding is None
                or availability_binding is None
            ):
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_PREVIOUS_ACCEPTANCE_CHAIN_MISSING"
                )
            previous_timeframe = self._read_binding(timeframe_binding)
            previous_timeframe_binding = _acceptance_binding(timeframe_binding)
            previous_acceptance = self._read_binding(acceptance_binding)
            previous_acceptance_binding = _acceptance_binding(acceptance_binding)
            previous_availability = self._read_binding(availability_binding)
            previous_availability_binding = _acceptance_binding(
                availability_binding
            )

        return {
            "public_evidence_verifier": V32InfrastructurePublicEvidenceVerifier(),
            "shadow_decision_verifier": V32InfrastructureShadowDecisionVerifier(),
            "components": components,
            "component_bindings": component_bindings,
            "permit_checkpoint": documents["supervisor_checkpoint"],
            "permit_checkpoint_binding": _acceptance_binding(
                required["supervisor_checkpoint"]
            ),
            "prior_outcome_schedule_sets": prior_schedule_sets,
            "prior_outcome_schedule_set_bindings": [
                _acceptance_binding(binding)
                for binding in prior_schedule_bindings
            ],
            "previous_timeframe_context_state": previous_timeframe,
            "previous_timeframe_context_state_binding": (
                previous_timeframe_binding
            ),
            "previous_public_market_graph_projection": previous_projection,
            "previous_public_market_graph_projection_binding": (
                None
                if previous_projection_binding is None
                else _acceptance_binding(previous_projection_binding)
            ),
            "previous_pit_evidence_availability_registry": (
                previous_availability
            ),
            "previous_pit_evidence_availability_registry_binding": (
                previous_availability_binding
            ),
            "previous_accepted_receipt": previous_acceptance,
            "previous_accepted_receipt_binding": previous_acceptance_binding,
            **context_packages,
        }

    def _verify_acceptance(
        self,
        checkpoint: Mapping[str, Any],
        *,
        cycle_index: int,
        required: Mapping[str, Mapping[str, Any]],
        acceptance: Mapping[str, Any],
        allow_verified_prefix_cache: bool = False,
    ) -> str:
        # A previously accepted prefix is immutable.  Replaying its full
        # semantic closure on every append-only checkpoint revision is both
        # redundant and quadratic.  The cache is process-local, and the
        # surrounding checkpoint validation has already revalidated every
        # referenced file identity/physical binding.  Explicit public replay
        # and the current acceptance transition never use this shortcut.
        prior_schedule_bindings = [
            binding
            for binding in checkpoint["artifact_bindings"]
            if binding["role"] == "outcome_schedule"
            and binding["cycle_index"] < cycle_index
        ]
        prior_schedule_binding_digests = sorted(
            _binding_digest(binding) for binding in prior_schedule_bindings
        )
        previous_dependency_bindings = [
            binding
            for binding in checkpoint["artifact_bindings"]
            if binding["cycle_index"] == cycle_index - 1
            and binding["role"]
            in {
                "analysis_acceptance",
                "public_market_graph_projection",
                "timeframe_context",
                "verified_pit_evidence_availability_registry",
            }
        ]
        previous_dependency_binding_digests = sorted(
            _binding_digest(binding)
            for binding in previous_dependency_bindings
        )
        acceptance_binding = self._find_binding(
            checkpoint,
            cycle_index=cycle_index,
            role="analysis_acceptance",
        )
        closure_bindings = [
            *required.values(),
            *prior_schedule_bindings,
            *previous_dependency_bindings,
            *([] if acceptance_binding is None else [acceptance_binding]),
        ]
        closure_stat_identities: dict[str, list[str]] = {}
        for binding in closure_bindings:
            binding_digest = _binding_digest(binding)
            if binding_digest in closure_stat_identities:
                continue
            # Re-read through the stat-guarded artifact cache.  A metadata or
            # byte change therefore invalidates both cache layers; altered
            # bytes fail their semantic/physical binding before a prefix hit.
            self._read_binding(binding)
            cached = self._artifact_read_cache.get(binding_digest)
            if cached is None:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ACCEPTANCE_CACHE_IDENTITY_MISSING"
                )
            closure_stat_identities[binding_digest] = [
                str(value) for value in cached[0]
            ]
        mailbox_stat_identity_digest = self._mailbox_stat_identity_digest(
            cycle_index=cycle_index
        )
        replay_cache_key = canonical_digest(
            {
                "schema_id": "theory_paper_v32_verified_accepted_prefix_cache_key_v1",
                "run_id": checkpoint["run_id"],
                "cycle_index": cycle_index,
                "experiment_contract_digest": checkpoint[
                    "experiment_contract_digest"
                ],
                "active_authority_digest": checkpoint["active_authority_digest"],
                "acceptance_digest": acceptance.get(ACCEPTANCE_DIGEST_FIELD),
                "required_binding_digests": {
                    role: _binding_digest(required[role])
                    for role in sorted(required)
                },
                "prior_schedule_binding_digests": prior_schedule_binding_digests,
                "previous_dependency_binding_digests": (
                    previous_dependency_binding_digests
                ),
                "mailbox_stat_identity_digest": mailbox_stat_identity_digest,
                "closure_stat_identities": closure_stat_identities,
            }
        )
        if allow_verified_prefix_cache:
            cached_digest = self._accepted_prefix_replay_cache.get(
                replay_cache_key
            )
            if cached_digest is not None:
                return cached_digest
        replay = self._acceptance_replay_material(
            checkpoint, cycle_index=cycle_index, required=required
        )
        try:
            digest = verify_v32_analysis_cycle_acceptance_receipt_v1(
                acceptance, **replay
            )
        except (TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ACCEPTANCE_REPLAY_INVALID"
            ) from exc
        permit = replay["components"]["analysis_tick_permit"]
        if (
            acceptance.get("run_id") != checkpoint["run_id"]
            or acceptance.get("cycle_index") != cycle_index
            or permit.get("experiment_contract_digest")
            != checkpoint["experiment_contract_digest"]
            or permit.get("active_authority_digest")
            != checkpoint["active_authority_digest"]
        ):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ACCEPTANCE_CHECKPOINT_BINDING_INVALID"
            )
        self._accepted_prefix_replay_cache[replay_cache_key] = digest
        return digest

    def _mailbox_stat_identity_digest(self, *, cycle_index: int) -> str:
        """Fingerprint accepted-cycle mailbox files without parsing them.

        Lossless Agent contexts are replayed from a separate write-once
        mailbox.  A prefix-cache hit must therefore depend on that mailbox's
        filesystem identity as well as the dynamic-store bindings.  Any file
        creation, deletion, replacement, metadata change, or symlink changes
        this digest (or fails closed) and forces the full semantic replay.
        """

        cycle = _cycle(cycle_index, "V32_DYNAMIC_STORE_CYCLE_INVALID")
        relative_root = PurePosixPath(
            MAILBOX_STORE_ROOT, "cycles", f"{cycle:04d}"
        )
        mailbox_root = self.run_root.joinpath(*relative_root.parts)
        try:
            mailbox_root.resolve(strict=False).relative_to(self._physical_root)
        except (OSError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_MAILBOX_CACHE_IDENTITY_INVALID"
            ) from exc
        if not mailbox_root.exists():
            return canonical_digest(
                {
                    "schema_id": "theory_paper_v32_mailbox_stat_identity_v1",
                    "cycle_index": cycle,
                    "state": "ABSENT",
                    "files": [],
                }
            )
        if mailbox_root.is_symlink() or not mailbox_root.is_dir():
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_MAILBOX_CACHE_IDENTITY_INVALID"
            )
        identities: list[dict[str, Any]] = []
        try:
            paths = sorted(
                mailbox_root.rglob("*"),
                key=lambda path: path.relative_to(mailbox_root).as_posix(),
            )
            for path in paths:
                relative = path.relative_to(mailbox_root).as_posix()
                if path.is_symlink():
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_MAILBOX_CACHE_SYMLINK_FORBIDDEN"
                    )
                stat = path.stat(follow_symlinks=False)
                identities.append(
                    {
                        "relative_ref": relative,
                        "kind": "DIRECTORY" if path.is_dir() else "FILE",
                        "device": str(stat.st_dev),
                        "inode": str(stat.st_ino),
                        "size": str(stat.st_size),
                        "mtime_ns": str(stat.st_mtime_ns),
                        "ctime_ns": str(stat.st_ctime_ns),
                    }
                )
        except V32DynamicStoreError:
            raise
        except OSError as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_MAILBOX_CACHE_IDENTITY_INVALID"
            ) from exc
        return canonical_digest(
            {
                "schema_id": "theory_paper_v32_mailbox_stat_identity_v1",
                "cycle_index": cycle,
                "state": "PRESENT",
                "files": identities,
            }
        )

    def replay_cycle_acceptance(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any]:
        """Read and fully replay one durable cycle acceptance without writes."""

        cycle = _cycle(cycle_index, "V32_DYNAMIC_STORE_CYCLE_INVALID")
        with self._lock():
            checkpoint = self.load_checkpoint(
                run_id=run_id, _already_locked=True
            )
            required = self._required_acceptance_bindings(
                checkpoint, cycle_index=cycle
            )
            binding = self._find_binding(
                checkpoint, cycle_index=cycle, role="analysis_acceptance"
            )
            if binding is None:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_REQUIRED_ARTIFACT_MISSING:analysis_acceptance"
                )
            acceptance = self._read_binding(binding)
            digest = self._verify_acceptance(
                checkpoint,
                cycle_index=cycle,
                required=required,
                acceptance=acceptance,
            )
            if digest != binding["semantic_digest"]:
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_ACCEPTANCE_BINDING_INVALID"
                )
            return {
                "acceptance": deepcopy(dict(acceptance)),
                "binding": deepcopy(dict(binding)),
                "required_bindings": {
                    role: deepcopy(dict(required[role]))
                    for role in _REQUIRED_ACCEPTANCE_ROLES
                },
            }

    def _build_acceptance(
        self,
        checkpoint: Mapping[str, Any],
        *,
        cycle_index: int,
        required: Mapping[str, Mapping[str, Any]],
        accepted_at: str,
    ) -> dict[str, Any]:
        replay = self._acceptance_replay_material(
            checkpoint, cycle_index=cycle_index, required=required
        )
        try:
            acceptance = build_v32_analysis_cycle_acceptance_receipt_v1(
                **replay,
                accepted_at=accepted_at,
            )
            verify_v32_analysis_cycle_acceptance_receipt_v1(
                acceptance, **replay
            )
        except (TypeError, ValueError) as exc:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ACCEPTANCE_BUILD_INVALID"
            ) from exc
        return acceptance

    def _accept_cycle_locked(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
        accepted_at: str,
        recovery_mode: str,
    ) -> Mapping[str, Any]:
        current = self.load_checkpoint(run_id=run_id, _already_locked=True)
        if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CAS_CONFLICT")
        if (
            current["status"] != "OPEN"
            or current["open_cycle_index"] != cycle_index
            or current["next_analysis_cycle_index"] != cycle_index
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_ACCEPT_SEQUENCE_INVALID")
        required = self._required_acceptance_bindings(
            current, cycle_index=cycle_index
        )
        acceptance_binding = self._find_binding(
            current, cycle_index=cycle_index, role="analysis_acceptance"
        )
        if acceptance_binding is None:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_REQUIRED_ARTIFACT_MISSING:analysis_acceptance"
            )
        acceptance = self._read_binding(acceptance_binding)
        acceptance_digest = self._verify_acceptance(
            current,
            cycle_index=cycle_index,
            required=required,
            acceptance=acceptance,
        )
        if acceptance_binding["semantic_digest"] != acceptance_digest:
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ACCEPTANCE_BINDING_INVALID"
            )
        transition_time = _time(
            accepted_at, "V32_DYNAMIC_STORE_TIME_INVALID"
        )
        acceptance_time = _time(
            acceptance.get("accepted_at"), "V32_DYNAMIC_STORE_TIME_INVALID"
        )
        if (
            recovery_mode == "NORMAL_COMMIT"
            and transition_time != acceptance_time
        ) or _moment(
            transition_time, "V32_DYNAMIC_STORE_TIME_INVALID"
        ) < _moment(acceptance_time, "V32_DYNAMIC_STORE_TIME_INVALID"):
            raise V32DynamicStoreError(
                "V32_DYNAMIC_STORE_ACCEPTANCE_TIME_INVALID"
            )
        commit = self._read_binding(required["commit_envelope"])
        action = self._read_binding(required["action_plan"])
        schedule = self._read_binding(required["outcome_schedule"])
        proposal_packet = self._read_binding(required["proposal_packet"])
        proposal_input = self._read_binding(required["proposal_input"])
        proposal_delivery = self._read_binding(required["proposal_delivery"])
        proposal_consumption = self._read_binding(required["proposal_consumption"])
        dynamic_state = self._read_binding(required["dynamic_state"])
        action_evaluation = self._read_binding(required["action_evaluation"])
        selection_packet = self._read_binding(required["selection_packet"])
        selection_input = self._read_binding(required["selection_input"])
        selection_delivery = self._read_binding(required["selection_delivery"])
        selection_consumption = self._read_binding(required["selection_consumption"])
        source_admission = self._read_binding(required["cycle_source_admission"])
        timeframe_context = self._read_binding(required["timeframe_context"])
        context_packages = self._acceptance_context_packages(
            current,
            cycle_index=cycle_index,
            required=required,
            documents={
                "proposal_packet": proposal_packet,
                "proposal_input": proposal_input,
                "proposal_delivery": proposal_delivery,
                "proposal_consumption": proposal_consumption,
                "selection_packet": selection_packet,
                "selection_input": selection_input,
                "selection_delivery": selection_delivery,
                "selection_consumption": selection_consumption,
            },
        )
        proposal_packet_from_context = resolve_v32_agent_canonical_packet_v1(
            proposal_input,
            lossless_context_package=context_packages[
                "proposal_lossless_context_package"
            ],
        )
        selection_packet_from_context = resolve_v32_agent_canonical_packet_v1(
            selection_input,
            lossless_context_package=context_packages[
                "selection_lossless_context_package"
            ],
        )
        if (
            commit.get("run_id") != run_id
            or commit.get("cycle_index") != cycle_index
            or commit.get("commit_status")
            != "SEALED_NON_EXECUTABLE_RESEARCH_DECISION"
            or commit.get("final_dynamic_action_plan") != dict(action)
            or commit.get("outcome_schedule_set") != dict(schedule)
            or commit.get("final_dynamic_action_plan_digest")
            != required["action_plan"]["semantic_digest"]
            or commit.get("outcome_schedule_set_digest")
            != required["outcome_schedule"]["semantic_digest"]
            or commit.get("fill_claim") != "NONE_NO_FILL_MODEL"
            or commit.get("pnl_claim") != "NONE_NO_PNL_MODEL"
            or commit.get("proposal_input_context_digest")
            != required["proposal_input"]["semantic_digest"]
            or commit.get("proposal_delivery_digest")
            != required["proposal_delivery"]["semantic_digest"]
            or commit.get("proposal_consumption_digest")
            != required["proposal_consumption"]["semantic_digest"]
            or commit.get("selection_input_context_digest")
            != required["selection_input"]["semantic_digest"]
            or commit.get("selection_delivery_digest")
            != required["selection_delivery"]["semantic_digest"]
            or commit.get("selection_consumption_digest")
            != required["selection_consumption"]["semantic_digest"]
            or commit.get("compiled_dynamic_research_state_digest")
            != required["dynamic_state"]["semantic_digest"]
            or proposal_packet_from_context != dict(proposal_packet)
            or selection_packet_from_context != dict(selection_packet)
            or proposal_delivery.get("agent_input_context_digest")
            != required["proposal_input"]["semantic_digest"]
            or proposal_consumption.get("agent_input_context_digest")
            != required["proposal_input"]["semantic_digest"]
            or proposal_consumption.get("agent_delivery_digest")
            != required["proposal_delivery"]["semantic_digest"]
            or selection_delivery.get("agent_input_context_digest")
            != required["selection_input"]["semantic_digest"]
            or selection_consumption.get("agent_input_context_digest")
            != required["selection_input"]["semantic_digest"]
            or selection_consumption.get("agent_delivery_digest")
            != required["selection_delivery"]["semantic_digest"]
            or selection_packet.get("compiled_dynamic_research_state")
            != dict(dynamic_state)
            or selection_packet.get("sealed_action_evaluation")
            != dict(action_evaluation)
            or proposal_packet.get("support_documents", {}).get(
                "cycle_source_admission"
            )
            != dict(source_admission)
            or proposal_packet.get("support_documents", {}).get(
                "timeframe_context_state"
            )
            != dict(timeframe_context)
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_COMMIT_TAIL_INVALID")
        previous_commit = current["current_commit_binding"]
        if (
            cycle_index == 1
            and commit.get("previous_commit_envelope_digest") is not None
        ) or (
            cycle_index > 1
            and (
                previous_commit is None
                or commit.get("previous_commit_envelope_digest")
                != previous_commit["semantic_digest"]
            )
        ):
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_COMMIT_CHAIN_INVALID")
        accepted_entry = {
            "cycle_index": cycle_index,
            "accepted_at": acceptance_time,
            "artifact_binding_digests": {
                role: _binding_digest(required[role])
                for role in _REQUIRED_ACCEPTANCE_ROLES
            },
            "acceptance_binding_digest": _binding_digest(acceptance_binding),
            "recovery_mode": recovery_mode,
            "tail_recovery_agent_invocations": 0,
            "tail_recovery_network_requests": 0,
            "accepted_state_is_fill_or_profit_claim": False,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        }
        accepted_count = current["accepted_analysis_cycles"] + 1
        next_status = "OUTCOME_TAIL" if accepted_count == 16 else "READY"
        return self._replace_checkpoint(
            run_id=run_id,
            expected_checkpoint_digest=expected_checkpoint_digest,
            candidate={
                **current,
                "status": next_status,
                "accepted_analysis_cycles": accepted_count,
                "next_analysis_cycle_index": accepted_count + 1,
                "open_cycle_index": None,
                "accepted_cycle_bindings": [
                    *current["accepted_cycle_bindings"],
                    accepted_entry,
                ],
                "current_dynamic_state_binding": required["dynamic_state"],
                "current_action_evaluation_binding": required["action_evaluation"],
                "current_action_plan_binding": required["action_plan"],
                "current_timeframe_cache_binding": required["timeframe_context"],
                "current_source_binding": required["cycle_source_admission"],
                "current_commit_binding": required["commit_envelope"],
            },
            updated_at=transition_time,
        )

    def accept_cycle(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
        accepted_at: str,
    ) -> Mapping[str, Any]:
        cycle = _cycle(cycle_index, "V32_DYNAMIC_STORE_CYCLE_INVALID")
        with self._lock():
            return self._accept_cycle_locked(
                run_id=run_id,
                cycle_index=cycle,
                expected_checkpoint_digest=expected_checkpoint_digest,
                accepted_at=accepted_at,
                recovery_mode="NORMAL_COMMIT",
            )

    def recover_persisted_commit_tail(
        self,
        *,
        run_id: str,
        cycle_index: int,
        expected_checkpoint_digest: str,
        recovered_at: str,
    ) -> Mapping[str, Any]:
        """Finish only the durable commit tail; never invoke Agent or network."""

        cycle = _cycle(cycle_index, "V32_DYNAMIC_STORE_CYCLE_INVALID")
        recovery_time = _time(recovered_at, "V32_DYNAMIC_STORE_TIME_INVALID")
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_CAS_CONFLICT")
            if current["status"] != "OPEN" or current["open_cycle_index"] != cycle:
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_RECOVERY_STATE_INVALID")
            try:
                commit_binding = self._find_binding(
                    current, cycle_index=cycle, role="commit_envelope"
                )
                if commit_binding is None:
                    raise V32DynamicStoreError(
                        "V32_DYNAMIC_STORE_RECOVERY_COMMIT_MISSING"
                    )
                commit = self._read_binding(commit_binding)
                for role, field, filename in (
                    (
                        "action_plan",
                        "final_dynamic_action_plan",
                        "action-plan.json",
                    ),
                    (
                        "outcome_schedule",
                        "outcome_schedule_set",
                        "outcome-schedule.json",
                    ),
                ):
                    existing = self._find_binding(
                        current, cycle_index=cycle, role=role
                    )
                    if existing is None:
                        embedded = commit.get(field)
                        if not isinstance(embedded, Mapping):
                            raise V32DynamicStoreError(
                                "V32_DYNAMIC_STORE_RECOVERY_EMBEDDED_ARTIFACT_INVALID"
                            )
                        current = self._persist_artifact_locked(
                            run_id=run_id,
                            cycle_index=cycle,
                            role=role,
                            relative_ref=(
                                f"{STORE_ROOT}/cycles/{cycle:04d}/final/{filename}"
                            ),
                            document=embedded,
                            expected_checkpoint_digest=current[
                                CHECKPOINT_DIGEST_FIELD
                            ],
                            recorded_at=recovery_time,
                        )
                    else:
                        durable = self._read_binding(existing)
                        if durable != commit.get(field):
                            raise V32DynamicStoreError(
                                "V32_DYNAMIC_STORE_RECOVERY_WRITE_ONCE_CONFLICT"
                            )
                required = self._required_acceptance_bindings(
                    current, cycle_index=cycle
                )
                acceptance_binding = self._find_binding(
                    current, cycle_index=cycle, role="analysis_acceptance"
                )
                if acceptance_binding is None:
                    acceptance = self._build_acceptance(
                        current,
                        cycle_index=cycle,
                        required=required,
                        accepted_at=recovery_time,
                    )
                    current = self._persist_artifact_locked(
                        run_id=run_id,
                        cycle_index=cycle,
                        role="analysis_acceptance",
                        relative_ref=(
                            f"{STORE_ROOT}/cycles/{cycle:04d}/final/"
                            "analysis-acceptance.json"
                        ),
                        document=acceptance,
                        expected_checkpoint_digest=current[
                            CHECKPOINT_DIGEST_FIELD
                        ],
                        recorded_at=recovery_time,
                    )
                return self._accept_cycle_locked(
                    run_id=run_id,
                    cycle_index=cycle,
                    expected_checkpoint_digest=current[CHECKPOINT_DIGEST_FIELD],
                    accepted_at=recovery_time,
                    recovery_mode="DETERMINISTIC_COMMIT_TAIL_RECOVERY",
                )
            except (KeyError, TypeError, ValueError) as exc:
                latest = self.load_checkpoint(
                    run_id=run_id, _already_locked=True
                )
                if latest["status"] == "OPEN":
                    evidence = canonical_digest(
                        {
                            "schema_id": (
                                "theory_paper_v32_dynamic_tail_recovery_"
                                "failure_evidence_v1"
                            ),
                            "run_id": run_id,
                            "cycle_index": cycle,
                            "checkpoint_digest": latest[
                                CHECKPOINT_DIGEST_FIELD
                            ],
                            "failure_code": str(exc),
                        }
                    )
                    self._fail_closed_locked(
                        run_id=run_id,
                        expected_checkpoint_digest=latest[
                            CHECKPOINT_DIGEST_FIELD
                        ],
                        failure_code="COMMIT_STATE_CONFLICT",
                        failure_summary=(
                            "deterministic commit tail could not rebuild and "
                            "replay the exact analysis acceptance"
                        ),
                        failure_evidence_digest=evidence,
                        failed_at=recovery_time,
                    )
                raise V32DynamicStoreError(
                    "V32_DYNAMIC_STORE_RECOVERY_FAILED_CLOSED"
                ) from exc

    def mark_terminal(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        terminal_outcome_checkpoint_digest: str,
        completed_at: str,
    ) -> Mapping[str, Any]:
        outcome_digest = _digest(
            terminal_outcome_checkpoint_digest,
            "V32_DYNAMIC_STORE_OUTCOME_CHECKPOINT_INVALID",
        )
        with self._lock():
            current = self.load_checkpoint(run_id=run_id, _already_locked=True)
            if (
                current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest
                or current["status"] != "OUTCOME_TAIL"
            ):
                raise V32DynamicStoreError("V32_DYNAMIC_STORE_TERMINAL_SEQUENCE_INVALID")
            return self._replace_checkpoint(
                run_id=run_id,
                expected_checkpoint_digest=expected_checkpoint_digest,
                candidate={
                    **current,
                    "status": "TERMINAL",
                    "terminal_outcome_checkpoint_digest": outcome_digest,
                    "resume_allowed": False,
                },
                updated_at=completed_at,
            )

    def _fail_closed_locked(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        failure_code: str,
        failure_summary: str,
        failure_evidence_digest: str,
        failed_at: str,
    ) -> Mapping[str, Any]:
        code = _text(failure_code, "V32_DYNAMIC_STORE_FAILURE_CODE_INVALID")
        summary = _text(
            failure_summary, "V32_DYNAMIC_STORE_FAILURE_SUMMARY_INVALID"
        )
        evidence = _digest(
            failure_evidence_digest,
            "V32_DYNAMIC_STORE_FAILURE_EVIDENCE_INVALID",
        )
        failure_time = _time(failed_at, "V32_DYNAMIC_STORE_TIME_INVALID")
        current = self.load_checkpoint(run_id=run_id, _already_locked=True)
        if current[CHECKPOINT_DIGEST_FIELD] != expected_checkpoint_digest:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_CAS_CONFLICT")
        if current["status"] in {"TERMINAL", "FAILED"}:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_FAILURE_SEQUENCE_INVALID")
        failure = self_digest(
            {
                "schema_id": STORE_FAILURE_SCHEMA_ID,
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "run_id": run_id,
                "failed_at": failure_time,
                "failure_code": code,
                "failure_summary": summary,
                "failure_evidence_digest": evidence,
                "checkpoint_before_failure_digest": current[
                    CHECKPOINT_DIGEST_FIELD
                ],
                "accepted_analysis_cycles": current[
                    "accepted_analysis_cycles"
                ],
                "retry_allowed": False,
                "resume_allowed": False,
                "source_scope": SOURCE_SCOPE,
                "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
                "executable": False,
                "account_access": False,
                "order_submission": False,
                "fill_claim": "NONE_NO_FILL_MODEL",
                "pnl_claim": "NONE_NO_PNL_MODEL",
            },
            STORE_FAILURE_DIGEST_FIELD,
        )
        current = self._persist_artifact_locked(
            run_id=run_id,
            cycle_index=0,
            role="research_failure",
            relative_ref=f"{STORE_ROOT}/shared/failures/research-failure.json",
            document=failure,
            expected_checkpoint_digest=current[CHECKPOINT_DIGEST_FIELD],
            recorded_at=failure_time,
        )
        failure_binding = self._find_binding(
            current, cycle_index=0, role="research_failure"
        )
        if failure_binding is None:
            raise V32DynamicStoreError("V32_DYNAMIC_STORE_FAILURE_BINDING_INVALID")
        return self._replace_checkpoint(
            run_id=run_id,
            expected_checkpoint_digest=current[CHECKPOINT_DIGEST_FIELD],
            candidate={
                **current,
                "status": "FAILED",
                "open_cycle_index": None,
                "failure_binding": failure_binding,
                "resume_allowed": False,
            },
            updated_at=failure_time,
        )

    def fail_closed(
        self,
        *,
        run_id: str,
        expected_checkpoint_digest: str,
        failure_code: str,
        failure_summary: str,
        failure_evidence_digest: str,
        failed_at: str,
    ) -> Mapping[str, Any]:
        with self._lock():
            return self._fail_closed_locked(
                run_id=run_id,
                expected_checkpoint_digest=expected_checkpoint_digest,
                failure_code=failure_code,
                failure_summary=failure_summary,
                failure_evidence_digest=failure_evidence_digest,
                failed_at=failed_at,
            )


__all__ = [
    "ACCEPTANCE_DIGEST_FIELD",
    "ACCEPTANCE_SCHEMA_ID",
    "ARTIFACT_ROLE_SPECS",
    "CHECKPOINT_DIGEST_FIELD",
    "CHECKPOINT_SCHEMA_ID",
    "CHECKPOINT_SCHEMA_VERSION",
    "EXTERNAL_EXECUTION_AUTHORITY",
    "LocalV32DynamicStore",
    "STATUSES",
    "STORE_FAILURE_DIGEST_FIELD",
    "STORE_FAILURE_SCHEMA_ID",
    "STORE_ROOT",
    "TOTAL_ANALYSIS_CYCLES",
    "V32DynamicStoreError",
]
