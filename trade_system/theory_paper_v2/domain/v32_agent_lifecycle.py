"""Pure two-stage V3.2 current-root Agent lifecycle contracts.

The lifecycle is deliberately causal:

* ``PROPOSAL`` receives only point-in-time facts, frozen policies, durable
  predecessor state/plan, and already-matured outcome receipts.
* deterministic compilation produces a current dynamic state and a sealed
  candidate-action evaluation;
* ``SELECTION`` receives that compiled material plus the fully replayable
  proposal delivery chain, but no final plan or future outcome;
* only after terminal selection consumption may the controller seal the final
  non-executable action plan and its 15m/1h/4h outcome schedule in a commit
  envelope.

The module owns no files, clocks, network, Agent invocation, authority loading,
accounts, orders, fills, positions, portfolio mutation, or PnL.  Its receipts
prove byte/digest continuity and declared single attempts only.  They do not
prove attention, cognition, prediction quality, profitability, or execution.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
import hashlib
from pathlib import PurePosixPath
import re
import threading
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    canonical_bytes,
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_DIGEST_FIELD,
    SCHEMA_ID as EXPERIMENT_SCHEMA_ID,
    THEORY_VERSION,
    TOTAL_ANALYSIS_CYCLES,
    TOTAL_OUTCOME_SCHEDULES,
    verify_v32_experiment_contract_v1,
)
from .governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    QUALIFICATION_PROFILE,
    TARGET_PROFILE,
    THEORY_SEMANTIC_DOCUMENT_DIGEST_FIELD as THEORY_DOCUMENT_DIGEST_FIELD,
    THEORY_SEMANTIC_DOCUMENT_SCHEMA_ID as THEORY_DOCUMENT_SCHEMA_ID,
    V32AuthorizationError,
    verify_v32_authority_v1,
)
from .v32_association_preregistration import (
    DIGEST_FIELD as ASSOCIATION_PREREGISTRATION_DIGEST_FIELD,
    SCHEMA_ID as ASSOCIATION_PREREGISTRATION_SCHEMA_ID,
    verify_v32_association_preregistration,
)
from .v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    AUTHORITY_PROJECTION_SCHEMA_ID,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    verify_v32_active_authority_projection,
    verify_v32_cycle_source_admission,
)
from .v32_evaluation_contract import (
    DIGEST_FIELD as EVALUATION_CONTRACT_DIGEST_FIELD,
    SCHEMA_ID as EVALUATION_CONTRACT_SCHEMA_ID,
    verify_v32_evaluation_contract,
)
from .v32_runtime_support_contracts import (
    CLOCK_DIGEST_FIELD as CLOCK_TICK_POLICY_DIGEST_FIELD,
    CLOCK_SCHEMA_ID as CLOCK_TICK_POLICY_SCHEMA_ID,
    OUTCOME_ADAPTER_DIGEST_FIELD as OUTCOME_ADAPTER_CONTRACT_DIGEST_FIELD,
    OUTCOME_ADAPTER_SCHEMA_ID as OUTCOME_ADAPTER_CONTRACT_SCHEMA_ID,
    verify_v32_clock_and_tick_policy_v1,
    verify_v32_public_outcome_adapter_contract_v1,
)
from .v31_sentiment_native_projection_v2 import (
    verify_v31_native_sentiment_source_registry,
)
from .v32_dynamic_action_plan import (
    BLOCK_REASONS,
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    FEASIBILITY_STATES,
    SCHEMA_ID as ACTION_PLAN_SCHEMA_ID,
    legal_v32_dynamic_action_keys_v1,
    verify_v32_dynamic_action_plan_v1,
)
from .v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    SCHEMA_ID as DYNAMIC_STATE_SCHEMA_ID,
    SUBJECTIVE_TIER_RISK_CAP_UNITS,
    verify_v32_dynamic_research_state_v1,
)
from .v32_outcome_tick import (
    OUTCOME_RECEIPT_DIGEST_FIELD,
    OUTCOME_RECEIPT_SCHEMA_ID,
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
    verify_v32_outcome_schedule_set,
)
from .v32_outcome_window_expiry import (
    EXPIRY_ROW_DIGEST_FIELD,
    EXPIRY_ROW_SCHEMA_ID,
    EXPIRY_TERMINAL_DIGEST_FIELD,
    EXPIRY_TERMINAL_SCHEMA_ID,
    verify_v32_outcome_window_expiry_row,
    verify_v32_outcome_window_expiry_terminal_intrinsic,
)
from .v32_timeframe_cache import (
    DIGEST_FIELD as TIMEFRAME_DIGEST_FIELD,
    SCHEMA_ID as TIMEFRAME_SCHEMA_ID,
    verify_v32_timeframe_context_state_v1,
    verify_v32_timeframe_context_transition_v1,
)
from .v32_agent_market_graph_view import (
    DIGEST_FIELD as AGENT_MARKET_GRAPH_VIEW_DIGEST_FIELD,
    SCHEMA_ID as AGENT_MARKET_GRAPH_VIEW_SCHEMA_ID,
    verify_v32_agent_market_graph_view_intrinsic_v1,
)
from .v32_context_compaction import (
    MANIFEST_DIGEST_FIELD as CONTEXT_MANIFEST_DIGEST_FIELD,
    MANIFEST_SCHEMA_ID as CONTEXT_MANIFEST_SCHEMA_ID,
    POLICY_DIGEST_FIELD as CONTEXT_COMPACTION_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as CONTEXT_COMPACTION_POLICY_SCHEMA_ID,
    SELECTION_DIGEST_FIELD as CONTEXT_SELECTION_DIGEST_FIELD,
    SELECTION_SCHEMA_ID as CONTEXT_SELECTION_SCHEMA_ID,
    SHARD_DIGEST_FIELD as CONTEXT_SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID as CONTEXT_SHARD_SCHEMA_ID,
    verify_v32_context_compaction_bundle_v1,
    verify_v32_context_compaction_policy_v1,
    verify_v32_context_shard_selection_v1,
)
from .v32_cycle_audit_narrative import (
    POLICY_DIGEST_FIELD as CYCLE_AUDIT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as CYCLE_AUDIT_POLICY_SCHEMA_ID,
    verify_v32_cycle_audit_policy_v1,
)
from .v32_data_gap_escalation import (
    POLICY_DIGEST_FIELD as DATA_GAP_MANUAL_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as DATA_GAP_MANUAL_POLICY_SCHEMA_ID,
    verify_v32_data_gap_manual_policy_v1,
)
from .v32_environment_capability import (
    DIGEST_FIELD as ENVIRONMENT_CAPABILITY_PROFILE_DIGEST_FIELD,
    SCHEMA_ID as ENVIRONMENT_CAPABILITY_PROFILE_SCHEMA_ID,
    verify_v32_environment_capability_profile_v1,
)
from .v32_recovery_supervision import (
    POLICY_DIGEST_FIELD as RECOVERY_SUPERVISION_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as RECOVERY_SUPERVISION_POLICY_SCHEMA_ID,
    verify_v32_recovery_supervision_policy_v1,
)
from .v32_unknown_assessment import (
    POLICY_DIGEST_FIELD as UNKNOWN_SUBJECTIVE_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as UNKNOWN_SUBJECTIVE_POLICY_SCHEMA_ID,
    verify_v32_unknown_subjective_policy_v1,
)


class V32AgentLifecycleError(ValueError):
    """A V3.2 Agent input, delivery, consumption, or commit drifted."""


class _LifecycleVerificationMemo:
    __slots__ = ("owner", "results")

    def __init__(self, owner: tuple[object, object | None]) -> None:
        self.owner = owner
        self.results: dict[tuple[str, bytes], Any] = {}


_VERIFICATION_MEMO: ContextVar[_LifecycleVerificationMemo | None] = (
    ContextVar("v32_agent_lifecycle_verification_memo", default=None)
)
_MEMO_MISSING = object()
_STRICT_SNAPSHOT_UNAVAILABLE = object()


def _execution_owner() -> tuple[object, object | None]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.current_thread(), task


def _strict_builtin_json_snapshot(value: Any) -> Any:
    value_type = type(value)
    if value is None or value_type in {str, bool, int}:
        return value
    if value_type is list:
        snapshot: list[Any] = []
        try:
            for item in value:
                copied = _strict_builtin_json_snapshot(item)
                if copied is _STRICT_SNAPSHOT_UNAVAILABLE:
                    return _STRICT_SNAPSHOT_UNAVAILABLE
                snapshot.append(copied)
        except (KeyError, RuntimeError):
            return _STRICT_SNAPSHOT_UNAVAILABLE
        return snapshot
    if value_type is dict:
        snapshot_dict: dict[str, Any] = {}
        try:
            for key, item in value.items():
                if type(key) is not str:
                    return _STRICT_SNAPSHOT_UNAVAILABLE
                copied = _strict_builtin_json_snapshot(item)
                if copied is _STRICT_SNAPSHOT_UNAVAILABLE:
                    return _STRICT_SNAPSHOT_UNAVAILABLE
                snapshot_dict[key] = copied
        except (KeyError, RuntimeError):
            return _STRICT_SNAPSHOT_UNAVAILABLE
        return snapshot_dict
    return _STRICT_SNAPSHOT_UNAVAILABLE


@contextmanager
def v32_lifecycle_verification_scope_v1():
    """Deduplicate successful lifecycle replay only inside one call scope.

    Every key and its verifier consume the same recursively copied strict JSON
    snapshot of every positional and keyword argument.  The owner-bound store
    therefore cannot be promoted by an embedded Agent digest, object identity,
    or a caller mutation between key creation and validation.  Nested scopes in
    the same execution owner share the store; the outermost scope clears it.
    """

    owner = _execution_owner()
    active = _VERIFICATION_MEMO.get()
    if active is not None and active.owner == owner:
        yield
        return
    created = _LifecycleVerificationMemo(owner)
    token = _VERIFICATION_MEMO.set(created)
    try:
        yield
    finally:
        # Clear before reset so a copied ContextVar cannot retain completed
        # results after the owning scope exits.
        created.results.clear()
        _VERIFICATION_MEMO.reset(token)


def _memoized_lifecycle_verifier(tag: str):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            memo = _VERIFICATION_MEMO.get()
            if memo is None:
                return function(*args, **kwargs)
            if memo.owner != _execution_owner():
                # ContextVars are copied by asyncio.create_task.  A copied
                # mutable memo is not authority in the child execution owner.
                with v32_lifecycle_verification_scope_v1():
                    return wrapped(*args, **kwargs)
            snapshot_args: list[Any] = []
            for value in args:
                snapshot = _strict_builtin_json_snapshot(value)
                if snapshot is _STRICT_SNAPSHOT_UNAVAILABLE:
                    return function(*args, **kwargs)
                snapshot_args.append(snapshot)
            snapshot_kwargs: dict[str, Any] = {}
            for name, value in kwargs.items():
                snapshot = _strict_builtin_json_snapshot(value)
                if snapshot is _STRICT_SNAPSHOT_UNAVAILABLE:
                    return function(*args, **kwargs)
                snapshot_kwargs[name] = snapshot
            key = (
                tag,
                canonical_bytes(
                    {
                        "args": snapshot_args,
                        "kwargs": [
                            {"name": name, "value": snapshot_kwargs[name]}
                            for name in sorted(snapshot_kwargs)
                        ],
                    }
                ),
            )
            cached = memo.results.get(key, _MEMO_MISSING)
            if cached is not _MEMO_MISSING:
                return cached
            result = function(*snapshot_args, **snapshot_kwargs)
            memo.results[key] = result
            return result

        return wrapped

    return decorate


SCHEMA_VERSION = "1.0.0"

ACTION_EVALUATION_SCHEMA_ID = "theory_paper_v32_dynamic_action_evaluation_v1"
ACTION_EVALUATION_DIGEST_FIELD = "action_evaluation_digest"

PROPOSAL_PACKET_SCHEMA_ID = "theory_paper_v32_proposal_canonical_packet_v1"
PROPOSAL_PACKET_DIGEST_FIELD = "proposal_canonical_packet_digest"
SELECTION_PACKET_SCHEMA_ID = "theory_paper_v32_selection_canonical_packet_v1"
SELECTION_PACKET_DIGEST_FIELD = "selection_canonical_packet_digest"

AGENT_INPUT_CONTEXT_SCHEMA_ID = "theory_paper_v32_agent_input_context_v1"
AGENT_INPUT_CONTEXT_DIGEST_FIELD = "agent_input_context_digest"
AGENT_DELIVERY_SCHEMA_ID = "theory_paper_v32_current_root_agent_delivery_v1"
AGENT_DELIVERY_DIGEST_FIELD = "agent_delivery_digest"
AGENT_CONSUMPTION_SCHEMA_ID = "theory_paper_v32_current_root_agent_consumption_v1"
AGENT_CONSUMPTION_DIGEST_FIELD = "agent_consumption_digest"
COMMIT_ENVELOPE_SCHEMA_ID = "theory_paper_v32_two_stage_commit_envelope_v1"
COMMIT_ENVELOPE_DIGEST_FIELD = "two_stage_commit_envelope_digest"

V32_TARGET_CONTEXT_PROFILE = "V32_TARGET_16_CYCLE_PROCESS_PILOT"
V32_QUALIFICATION_CONTEXT_PROFILE = "V32_QUALIFICATION_CURRENT_ROOT_DURABILITY"
V32_CONTEXT_PROFILES = (
    V32_TARGET_CONTEXT_PROFILE,
    V32_QUALIFICATION_CONTEXT_PROFILE,
)
V32_CONTEXT_MODES = ("FULL_CONTEXT", "DELTA_CONTEXT")
V32_AGENT_STAGES = ("PROPOSAL", "SELECTION")
V32_AGENT_INPUT_DELIVERY_MODES = ("INLINE", "LOSSLESS_SHARDED")
V32_AGENT_CONTEXT_ROOT = "v32-dynamic-agent-context"
V32_CURRENT_ROOT_AGENT_ID = "CURRENT_ROOT_CODEX_V32_STRATEGY_AGENT"
V32_CURRENT_ROOT_DELIVERY_ORIGIN = "CURRENT_ROOT_CODEX_DIRECT_CANONICAL_PACKET"
V32_LIFECYCLE_CLAIM = (
    "DIRECT_UTF8_INPUT_AND_DURABLE_SINGLE_DELIVERY_ONLY_NOT_COGNITIVE_PROOF"
)

# Explicit resource ceilings.  Direct delivery is decided by the canonical
# size of the complete Agent input envelope, not by a second stage-specific
# packet cliff.  The historical proposal/selection names remain compatibility
# aliases only; they are not independent gates.  The current-Codex
# Presentation envelope owns the final aggregate delivery cap because only it
# knows the exact request/claim/package object that will actually be returned.
# No builder truncates, summarizes, or silently drops data.
MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES = 1024 * 1024
MAX_PROPOSAL_CANONICAL_PACKET_BYTES = MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES
MAX_SELECTION_CANONICAL_PACKET_BYTES = MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES
MAX_AGENT_DELIVERY_UTF8_BYTES = 256 * 1024

# Compatibility exports for callers that previously sourced the formal graph
# registry identifiers from this lifecycle module.  The lifecycle does not
# import Infrastructure merely to obtain constants.
GRAPH_REGISTRY_SCHEMA_ID = "theory_paper_v32_verified_graph_dependency_registry_v1"
GRAPH_REGISTRY_DIGEST_FIELD = "graph_dependency_registry_digest"
AUTHORIZED_REVISION_SUPPORT_BUNDLE_SCHEMA_ID = (
    "theory_paper_v32_authorized_revision_support_bundle_v1"
)
AUTHORIZED_REVISION_SUPPORT_BUNDLE_DIGEST_FIELD = (
    "authorized_revision_support_bundle_digest"
)

_PROFILE_AUTHORITY_PROFILE = MappingProxyType(
    {
        V32_TARGET_CONTEXT_PROFILE: TARGET_PROFILE,
        V32_QUALIFICATION_CONTEXT_PROFILE: QUALIFICATION_PROFILE,
    }
)

# V31 is reused only for the cycle-independent twelve-axis taxonomy.  Current
# market evidence must be the formal V3.2 raw-first analysis bundle and its
# deterministic graph projection; an all-unknown empty V31 projection is not a
# legal substitute for current evidence.
PROPOSAL_SUPPORT_SPECS = MappingProxyType(
    {
        "active_authority_projection": (
            AUTHORITY_PROJECTION_SCHEMA_ID,
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
        ),
        "experiment_contract": (EXPERIMENT_SCHEMA_ID, EXPERIMENT_DIGEST_FIELD),
        "timeframe_context_state": (TIMEFRAME_SCHEMA_ID, TIMEFRAME_DIGEST_FIELD),
        "agent_market_graph_view": (
            AGENT_MARKET_GRAPH_VIEW_SCHEMA_ID,
            AGENT_MARKET_GRAPH_VIEW_DIGEST_FIELD,
        ),
        "twelve_axis_source_registry": (
            "theory_paper_v2_v31_native_sentiment_source_registry",
            "registry_digest",
        ),
        "association_preregistration": (
            ASSOCIATION_PREREGISTRATION_SCHEMA_ID,
            ASSOCIATION_PREREGISTRATION_DIGEST_FIELD,
        ),
        "evaluation_contract": (
            EVALUATION_CONTRACT_SCHEMA_ID,
            EVALUATION_CONTRACT_DIGEST_FIELD,
        ),
        "clock_and_tick_policy": (
            CLOCK_TICK_POLICY_SCHEMA_ID,
            CLOCK_TICK_POLICY_DIGEST_FIELD,
        ),
        "outcome_adapter_contract": (
            OUTCOME_ADAPTER_CONTRACT_SCHEMA_ID,
            OUTCOME_ADAPTER_CONTRACT_DIGEST_FIELD,
        ),
        "cycle_source_admission": (
            SOURCE_ADMISSION_SCHEMA_ID,
            SOURCE_ADMISSION_DIGEST_FIELD,
        ),
        # These five frozen rules are the Agent-facing semantic components of
        # the authorized revision bundle.  Supplying the aggregate alone would
        # prove only its own bytes, not let the Strategy Agent inspect or replay
        # the actual rules it must follow.
        "context_compaction_policy": (
            CONTEXT_COMPACTION_POLICY_SCHEMA_ID,
            CONTEXT_COMPACTION_POLICY_DIGEST_FIELD,
        ),
        "unknown_subjective_policy": (
            UNKNOWN_SUBJECTIVE_POLICY_SCHEMA_ID,
            UNKNOWN_SUBJECTIVE_POLICY_DIGEST_FIELD,
        ),
        "data_gap_manual_policy": (
            DATA_GAP_MANUAL_POLICY_SCHEMA_ID,
            DATA_GAP_MANUAL_POLICY_DIGEST_FIELD,
        ),
        "cycle_audit_policy": (
            CYCLE_AUDIT_POLICY_SCHEMA_ID,
            CYCLE_AUDIT_POLICY_DIGEST_FIELD,
        ),
        "environment_capability_profile": (
            ENVIRONMENT_CAPABILITY_PROFILE_SCHEMA_ID,
            ENVIRONMENT_CAPABILITY_PROFILE_DIGEST_FIELD,
        ),
        "authorized_revision_support_bundle": (
            AUTHORIZED_REVISION_SUPPORT_BUNDLE_SCHEMA_ID,
            AUTHORIZED_REVISION_SUPPORT_BUNDLE_DIGEST_FIELD,
        ),
        # Recovery is intentionally outside the five-component aggregate, but
        # the Strategy Agent must see that the supervisor is read-only and that
        # a second network/Agent attempt is forbidden.
        "recovery_supervision_policy": (
            RECOVERY_SUPERVISION_POLICY_SCHEMA_ID,
            RECOVERY_SUPERVISION_POLICY_DIGEST_FIELD,
        ),
    }
)

# A workspace-freeze receipt remains an authorization-loader concern.  It
# proves which Git bytes were approved, while the already verified theory,
# contract and support documents below are the semantic inputs needed for
# market analysis.  Re-embedding that receipt would add no market information
# and would couple every Agent packet to a mutable workspace presentation.
_AUTHORIZED_REVISION_COMPONENT_SUPPORT_NAMES = MappingProxyType(
    {
        "context_compaction_policy": "context_compaction_policy",
        "unknown_subjective_policy": "unknown_subjective_policy",
        "data_gap_manual_policy": "data_gap_manual_policy",
        "cycle_audit_policy": "cycle_audit_policy",
        "environment_capability_profile": "environment_capability_profile",
    }
)
_AUTHORIZED_REVISION_SUPPORT_BUNDLE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "support_bundle_id",
        "run_scope_id",
        "frozen_at",
        "components",
        "component_count",
        "component_semantic_digests",
        "all_components_verified_by_owning_contract",
        "single_support_digest_for_contract_and_q_gate",
        "recovery_and_workspace_policies_included",
        "recovery_and_workspace_policy_owner",
        "support_bundle_is_authority",
        "support_bundle_is_qualification",
        "source_scope",
        "external_execution_authority",
        "account_access",
        "paper_trading",
        "live_trading",
        "order_submission",
        "credential_use",
        "funds_access",
        "portfolio_mutation",
        "fill_claim",
        "pnl_claim",
        "executable",
        AUTHORIZED_REVISION_SUPPORT_BUNDLE_DIGEST_FIELD,
    }
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {"relative_ref", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_THEORY_SOURCE_FIELDS = frozenset(
    {"path", "version", "review_status", "physical_sha256"}
)
_THEORY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "path",
        "version",
        "review_status",
        "physical_sha256",
        "content_encoding",
        "markdown_utf8",
        "source_binding",
        "semantic_role",
        "authority_granted",
        "claim",
        THEORY_DOCUMENT_DIGEST_FIELD,
    }
)
_REGISTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "members",
        "upstream_schema_id",
        "upstream_digest_field",
        "upstream_semantic_digest",
        "full_verification_receipt_digest",
        "source_scope",
        "external_execution_authority",
        "executable",
    }
)
_MATURED_OUTCOME_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "schedule_id",
        "schedule_digest",
        "schedule_set_digest",
        "decision_id",
        "cycle_index",
        "horizon",
        "outcome_not_before",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "resolved_at",
        "resolution_status",
        "coverage_loss_reason",
        "observable_ref",
        "value",
        "provider_as_of",
        "available_at",
        "quality",
        "missingness",
        "terminal",
        "attempt_count",
        "retry_allowed",
        "shared_tick_request",
        "observation_scope",
        "stop_trigger_semantics",
        "trigger_is_fill",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "source_scope",
        "external_execution_authority",
        "executable",
        OUTCOME_RECEIPT_DIGEST_FIELD,
    }
)
_ACTION_EVALUATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "evaluated_at",
        "proposal_consumption_digest",
        "compiled_dynamic_state_digest",
        "reference_context",
        "legal_action_grid",
        "legal_action_grid_digest",
        "risk_arithmetic",
        "risk_arithmetic_digest",
        "candidate_rows",
        "candidate_rows_digest",
        "evaluation_status",
        "final_selection_present",
        "future_outcome_present",
        "source_scope",
        "external_execution_authority",
        "executable",
        ACTION_EVALUATION_DIGEST_FIELD,
    }
)
_ACTION_EVALUATION_CANDIDATE_FIELDS = frozenset(
    {
        "candidate_id",
        "action_kind",
        "direction",
        "action_key",
        "feasibility",
        "block_reasons",
        "evidence_refs",
        "risk_reference_units",
        "risk_arithmetic_digest",
    }
)
_ACTION_EVALUATION_RISK_FIELDS = frozenset(
    {
        "reference_risk_upper_bound",
        "subjective_plausibility_tier",
        "residual_uncertainty_tier",
        "agent_reference_risk_ceiling",
        "calculation_policy",
    }
)
_PROPOSAL_PACKET_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "context_profile",
        "context_mode",
        "prepared_at",
        "decision_time",
        "authority_binding",
        "authority_document",
        "theory_semantic_document",
        "theory_semantic_document_binding",
        "support_documents",
        "support_bindings",
        "support_bindings_digest",
        "previous_dynamic_research_state",
        "previous_dynamic_research_state_binding",
        "previous_dynamic_action_plan",
        "previous_dynamic_action_plan_binding",
        "previous_timeframe_context_state",
        "previous_timeframe_context_state_binding",
        "matured_outcome_receipts",
        "matured_outcome_receipt_bindings",
        "matured_outcome_receipts_digest",
        "forbidden_current_objects",
        "full_theory_utf8_required",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        "executable",
        "claim",
        PROPOSAL_PACKET_DIGEST_FIELD,
    }
)
_SELECTION_PACKET_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "context_profile",
        "context_mode",
        "prepared_at",
        "decision_time",
        "proposal_input_context",
        "proposal_input_context_binding",
        "proposal_delivery",
        "proposal_delivery_binding",
        "proposal_consumption",
        "proposal_consumption_binding",
        "compiled_dynamic_research_state",
        "compiled_dynamic_research_state_binding",
        "sealed_action_evaluation",
        "sealed_action_evaluation_binding",
        "forbidden_current_objects",
        "future_outcome_visible",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        "executable",
        "claim",
        SELECTION_PACKET_DIGEST_FIELD,
    }
)
_INPUT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "context_profile",
        "context_mode",
        "decision_time",
        "evaluation_contract_digest",
        "created_at",
        "agent_id",
        "delivery_origin",
        "agent_stage",
        "context_delivery_mode",
        "canonical_packet",
        "canonical_packet_schema_id",
        "canonical_packet_digest_field",
        "canonical_packet_digest",
        "canonical_packet_binding",
        "context_compaction_manifest_binding",
        "context_shard_selection_binding",
        "selected_context_shard_bindings",
        "selected_context_shard_bindings_digest",
        "ordered_input_delivery_units",
        "ordered_input_delivery_units_digest",
        "ordered_input_delivery_unit_count",
        "full_original_packet_embedded",
        "full_original_packet_replay_required",
        "controller_must_pass_document_unchanged",
        "single_attempt_required",
        "private_chain_of_thought_requested",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        "executable",
        "claim",
        "limitations",
        AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    }
)
_DELIVERY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "context_profile",
        "agent_stage",
        "reserved_at",
        "delivered_at",
        "agent_id",
        "delivery_origin",
        "attempt_number",
        "max_attempts",
        "retry_allowed",
        "agent_input_context_digest",
        "agent_input_context_binding",
        "payload_encoding",
        "payload_utf8",
        "payload_byte_length",
        "payload_sha256",
        "terminal_status",
        "transport_attestation_level",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        "executable",
        "claim",
        "limitations",
        AGENT_DELIVERY_DIGEST_FIELD,
    }
)
_CONSUMPTION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "context_profile",
        "agent_stage",
        "consumed_at",
        "agent_id",
        "agent_input_context_digest",
        "agent_input_context_binding",
        "agent_delivery_digest",
        "agent_delivery_binding",
        "payload_sha256",
        "context_delivery_mode",
        "ordered_input_delivery_units",
        "ordered_input_delivery_units_digest",
        "ordered_input_delivery_unit_count",
        "complete_ordered_input_consumed",
        "attempt_count",
        "max_attempts",
        "retry_count",
        "terminal_delivery_verified",
        "durable_consumption_declared",
        "next_phase",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        "executable",
        "claim",
        "limitations",
        AGENT_CONSUMPTION_DIGEST_FIELD,
    }
)
_COMMIT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "context_profile",
        "sealed_at",
        "proposal_input_context_digest",
        "proposal_delivery_digest",
        "proposal_consumption_digest",
        "selection_input_context_digest",
        "selection_delivery_digest",
        "selection_consumption_digest",
        "compiled_dynamic_research_state_digest",
        "final_dynamic_action_plan",
        "final_dynamic_action_plan_binding",
        "final_dynamic_action_plan_digest",
        "outcome_schedule_set",
        "outcome_schedule_set_binding",
        "outcome_schedule_set_digest",
        "previous_commit_envelope_digest",
        "commit_status",
        "controller_write_once_required",
        "recovery_policy",
        "chat_history_is_authority",
        "source_scope",
        "external_execution_authority",
        "account_access",
        "order_submission",
        "fill_claim",
        "pnl_claim",
        "executable",
        "claim",
        "limitations",
        COMMIT_ENVELOPE_DIGEST_FIELD,
    }
)

_LIMITATIONS = [
    "DIRECT_INPUT_ARTIFACT_DOES_NOT_PROVE_ATTENTION_OR_COGNITION",
    "DURABLE_DELIVERY_DOES_NOT_PROVE_PREDICTION_OR_PROFITABILITY",
    "CURRENT_ROOT_AND_SERVICE_MODEL_IDENTITY_ARE_NOT_MACHINE_ATTESTED",
    "RESEARCH_PLAN_IS_NOT_ACCOUNT_ORDER_FILL_POSITION_OR_PNL",
]


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32AgentLifecycleError(code)
    return value


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32AgentLifecycleError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32AgentLifecycleError(code) from exc
    if parsed.tzinfo is None:
        raise V32AgentLifecycleError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V32AgentLifecycleError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(UTC)


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= TOTAL_ANALYSIS_CYCLES:
        raise V32AgentLifecycleError("V32_AGENT_CYCLE_INVALID")
    return value


def _relative_ref(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32AgentLifecycleError(code)
    return text


def _binding(
    value: Any,
    code: str,
    *,
    schema_id: str | None = None,
    digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32AgentLifecycleError(code)
    result = {
        "relative_ref": _relative_ref(value.get("relative_ref"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    if (
        (schema_id is not None and result["schema_id"] != schema_id)
        or (digest_field is not None and result["digest_field"] != digest_field)
    ):
        raise V32AgentLifecycleError(code)
    return result


def _physical_sha(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def build_v32_embedded_document_binding_v1(
    *, relative_ref: str, document: Mapping[str, Any], schema_id: str, digest_field: str
) -> dict[str, str]:
    if not isinstance(document, Mapping):
        raise V32AgentLifecycleError("V32_AGENT_DOCUMENT_BINDING_INVALID")
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32AgentLifecycleError("V32_AGENT_DOCUMENT_BINDING_INVALID") from exc
    if document.get("schema_id") != schema_id:
        raise V32AgentLifecycleError("V32_AGENT_DOCUMENT_BINDING_INVALID")
    return {
        "relative_ref": _relative_ref(relative_ref, "V32_AGENT_DOCUMENT_BINDING_REF_INVALID"),
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic,
        "physical_sha256": _physical_sha(document),
    }


def _embedded_binding(
    *,
    document: Mapping[str, Any],
    binding: Mapping[str, Any],
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
    code: str,
) -> dict[str, str]:
    result = _binding(binding, code, schema_id=schema_id, digest_field=digest_field)
    if result["semantic_digest"] != semantic_digest or result["physical_sha256"] != _physical_sha(document):
        raise V32AgentLifecycleError(code)
    return result


def _verify_authorized_revision_support_bundle(
    *,
    document: Mapping[str, Any],
    component_documents: Mapping[str, Mapping[str, Any]],
    component_bindings: Mapping[str, Mapping[str, Any]],
    component_semantics: Mapping[str, str],
) -> str:
    """Replay the aggregate without introducing a Domain -> Application edge.

    The owning aggregate builder lives in Application because it coordinates
    persistence ports.  Proposal verification remains pure Domain code: it
    verifies the aggregate's exact closed shape, self digest, semantic flags,
    component order, and every component's semantic and physical binding
    against the concrete documents embedded in this same canonical packet.
    """

    code = "V32_AGENT_REVISION_SUPPORT_BUNDLE_INVALID"
    if (
        not isinstance(document, Mapping)
        or set(document) != _AUTHORIZED_REVISION_SUPPORT_BUNDLE_FIELDS
    ):
        raise V32AgentLifecycleError(code)
    try:
        supplied = verify_self_digest(
            document, AUTHORIZED_REVISION_SUPPORT_BUNDLE_DIGEST_FIELD
        )
        _text(document.get("support_bundle_id"), code)
        run_scope_id = _text(document.get("run_scope_id"), code)
        frozen_at = _time(document.get("frozen_at"), code)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError(code) from exc
    expected_roles = list(_AUTHORIZED_REVISION_COMPONENT_SUPPORT_NAMES)
    rows = document.get("components")
    if (
        document.get("schema_id")
        != AUTHORIZED_REVISION_SUPPORT_BUNDLE_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or not isinstance(rows, list)
        or len(rows) != len(expected_roles)
        or document.get("component_count") != len(expected_roles)
        or document.get("all_components_verified_by_owning_contract") is not True
        or document.get("single_support_digest_for_contract_and_q_gate") is not True
        or document.get("recovery_and_workspace_policies_included") is not False
        or document.get("recovery_and_workspace_policy_owner")
        != "OUTSIDE_THIS_SUPPORT_BUNDLE"
        or document.get("support_bundle_is_authority") is not False
        or document.get("support_bundle_is_qualification") is not False
        or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or any(
            document.get(field) is not False
            for field in (
                "account_access",
                "paper_trading",
                "live_trading",
                "order_submission",
                "credential_use",
                "funds_access",
                "portfolio_mutation",
                "fill_claim",
                "pnl_claim",
                "executable",
            )
        )
    ):
        raise V32AgentLifecycleError(code)
    normalized_rows: list[dict[str, Any]] = []
    for expected_role, row in zip(expected_roles, rows, strict=True):
        if (
            not isinstance(row, Mapping)
            or set(row) != {"role", "binding"}
            or row.get("role") != expected_role
        ):
            raise V32AgentLifecycleError(code)
        support_name = _AUTHORIZED_REVISION_COMPONENT_SUPPORT_NAMES[expected_role]
        if (
            component_documents[support_name].get("run_scope_id")
            != run_scope_id
            or _moment(component_documents[support_name].get("frozen_at"), code)
            > _moment(frozen_at, code)
        ):
            raise V32AgentLifecycleError(code)
        schema_id, digest_field = PROPOSAL_SUPPORT_SPECS[support_name]
        normalized_binding = _embedded_binding(
            document=component_documents[support_name],
            binding=row["binding"],
            schema_id=schema_id,
            digest_field=digest_field,
            semantic_digest=component_semantics[support_name],
            code=code,
        )
        # The aggregate and the Agent packet must resolve the same physical
        # object, not merely two equal-looking copies under different refs.
        if normalized_binding != component_bindings[support_name]:
            raise V32AgentLifecycleError(code)
        normalized_rows.append(
            {"role": expected_role, "binding": normalized_binding}
        )
    if (
        list(document.get("component_semantic_digests", []))
        != [row["binding"]["semantic_digest"] for row in normalized_rows]
    ):
        raise V32AgentLifecycleError(code)
    return supplied


def _boundary(document: Mapping[str, Any], code: str) -> None:
    if (
        document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority") != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V32AgentLifecycleError(code)


def _theory_source(value: Any) -> dict[str, str]:
    code = "V32_AGENT_THEORY_SOURCE_INVALID"
    if not isinstance(value, Mapping) or set(value) != _THEORY_SOURCE_FIELDS:
        raise V32AgentLifecycleError(code)
    result = {
        "path": _relative_ref(value.get("path"), code),
        "version": _text(value.get("version"), code),
        "review_status": _text(value.get("review_status"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    if result["version"] != THEORY_VERSION or result["review_status"] not in {
        "FROZEN_APPROVED",
        "QUALIFICATION_FROZEN",
    }:
        raise V32AgentLifecycleError(code)
    return result


def build_v32_theory_semantic_document_v1(
    *, theory_source_binding: Mapping[str, Any], markdown_utf8: str
) -> dict[str, Any]:
    source = _theory_source(theory_source_binding)
    if not isinstance(markdown_utf8, str) or not markdown_utf8:
        raise V32AgentLifecycleError("V32_AGENT_THEORY_UTF8_INVALID")
    raw = markdown_utf8.encode("utf-8", errors="strict")
    if hashlib.sha256(raw).hexdigest() != source["physical_sha256"]:
        raise V32AgentLifecycleError("V32_AGENT_THEORY_BYTES_MISMATCH")
    return self_digest(
        {
            "schema_id": THEORY_DOCUMENT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "path": source["path"],
            "version": THEORY_VERSION,
            "review_status": source["review_status"],
            "physical_sha256": source["physical_sha256"],
            "content_encoding": "UTF-8",
            "markdown_utf8": markdown_utf8,
            "source_binding": source,
            "semantic_role": "COMPLETE_V32_THEORY_DIRECT_CURRENT_ROOT_INPUT",
            "authority_granted": False,
            "claim": "EXACT_UTF8_CONTENT_AND_SHA256_ONLY_NOT_THEORY_APPROVAL",
        },
        THEORY_DOCUMENT_DIGEST_FIELD,
    )


def verify_v32_theory_semantic_document_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _THEORY_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_THEORY_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, THEORY_DOCUMENT_DIGEST_FIELD)
        rebuilt = build_v32_theory_semantic_document_v1(
            theory_source_binding=document["source_binding"],
            markdown_utf8=document["markdown_utf8"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_THEORY_DOCUMENT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[THEORY_DOCUMENT_DIGEST_FIELD]:
        raise V32AgentLifecycleError("V32_AGENT_THEORY_RECONSTRUCTION_MISMATCH")
    return supplied


def _verify_registry(document: Mapping[str, Any], *, schema_id: str, digest_field: str, run_id: str, cycle_index: int) -> str:
    code = "V32_AGENT_REGISTRY_INVALID"
    if not isinstance(document, Mapping) or set(document) != _REGISTRY_FIELDS | {digest_field}:
        raise V32AgentLifecycleError(code)
    supplied = verify_self_digest(document, digest_field)
    members = document.get("members")
    if (
        document.get("schema_id") != schema_id
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("run_id") != run_id
        or document.get("cycle_index") != cycle_index
        or not isinstance(members, list)
        or not members
        or members != sorted(set(members))
    ):
        raise V32AgentLifecycleError(code)
    _time(document.get("as_of"), code)
    _text(document.get("upstream_schema_id"), code)
    _text(document.get("upstream_digest_field"), code)
    _digest(document.get("upstream_semantic_digest"), code)
    _digest(document.get("full_verification_receipt_digest"), code)
    _boundary(document, code)
    return supplied


def _verify_matured_receipts(
    *, receipts: Sequence[Mapping[str, Any]], bindings: Sequence[Mapping[str, Any]],
    run_id: str, cycle_index: int, decision_time: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    code = "V32_AGENT_MATURED_OUTCOME_INVALID"
    if (
        isinstance(receipts, (str, bytes))
        or not isinstance(receipts, Sequence)
        or isinstance(bindings, (str, bytes))
        or not isinstance(bindings, Sequence)
        or len(receipts) != len(bindings)
    ):
        raise V32AgentLifecycleError(code)
    normalized: list[tuple[dict[str, Any], dict[str, Any]]] = []
    expiry_aggregates: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    decision = _moment(decision_time, code)
    for receipt, binding in zip(receipts, bindings, strict=True):
        if not isinstance(receipt, Mapping) or not isinstance(binding, Mapping):
            raise V32AgentLifecycleError(code)
        if receipt.get("schema_id") == EXPIRY_ROW_SCHEMA_ID:
            try:
                semantic = verify_v32_outcome_window_expiry_row(receipt)
            except (KeyError, TypeError, ValueError) as exc:
                raise V32AgentLifecycleError(code) from exc
            if (
                binding.get("member_semantic_digest") != semantic
                or receipt.get("run_id") != run_id
                or not isinstance(receipt.get("cycle_index"), int)
                or not 1 <= receipt["cycle_index"] < cycle_index
                or receipt.get("terminal") is not True
                or receipt.get("attempt_count") != 0
                or receipt.get("raw_evidence_present") is not False
                or receipt.get("observation_tick_present") is not False
                or _moment(receipt.get("resolved_at"), code) > decision
            ):
                raise V32AgentLifecycleError(code)
            if binding.get("binding_kind") == "EXPIRY_AGGREGATE_MEMBER":
                if set(binding) != {
                    "binding_kind", "aggregate_document", "aggregate_binding",
                    "member_semantic_digest",
                }:
                    raise V32AgentLifecycleError(code)
                try:
                    aggregate = dict(binding["aggregate_document"])
                    aggregate_semantic = (
                        verify_v32_outcome_window_expiry_terminal_intrinsic(
                            aggregate
                        )
                    )
                    aggregate_binding = _embedded_binding(
                        document=aggregate,
                        binding=binding["aggregate_binding"],
                        schema_id=EXPIRY_TERMINAL_SCHEMA_ID,
                        digest_field=EXPIRY_TERMINAL_DIGEST_FIELD,
                        semantic_digest=aggregate_semantic,
                        code=code,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise V32AgentLifecycleError(code) from exc
                if aggregate_semantic in expiry_aggregates:
                    raise V32AgentLifecycleError(code)
                expiry_aggregates[aggregate_semantic] = (
                    aggregate,
                    aggregate_binding,
                )
                normalized_binding = {
                    "binding_kind": "EXPIRY_AGGREGATE_MEMBER",
                    "aggregate_document": aggregate,
                    "aggregate_binding": aggregate_binding,
                    "member_semantic_digest": semantic,
                }
            elif binding.get("binding_kind") == "EXPIRY_AGGREGATE_MEMBER_REF":
                if set(binding) != {
                    "binding_kind", "aggregate_semantic_digest",
                    "member_semantic_digest",
                }:
                    raise V32AgentLifecycleError(code)
                aggregate_semantic = _digest(
                    binding.get("aggregate_semantic_digest"), code
                )
                if aggregate_semantic not in expiry_aggregates:
                    raise V32AgentLifecycleError(code)
                aggregate, _ = expiry_aggregates[aggregate_semantic]
                normalized_binding = {
                    "binding_kind": "EXPIRY_AGGREGATE_MEMBER_REF",
                    "aggregate_semantic_digest": aggregate_semantic,
                    "member_semantic_digest": semantic,
                }
            else:
                raise V32AgentLifecycleError(code)
            if not any(dict(row) == dict(receipt) for row in aggregate["rows"]):
                raise V32AgentLifecycleError(code)
            normalized.append(
                (
                    dict(receipt),
                    normalized_binding,
                )
            )
            continue
        if set(receipt) != _MATURED_OUTCOME_FIELDS:
            raise V32AgentLifecycleError(code)
        try:
            semantic = verify_self_digest(receipt, OUTCOME_RECEIPT_DIGEST_FIELD)
        except (TypeError, ValueError) as exc:
            raise V32AgentLifecycleError(code) from exc
        if (
            receipt.get("schema_id") != OUTCOME_RECEIPT_SCHEMA_ID
            or receipt.get("schema_version") != SCHEMA_VERSION
            or receipt.get("run_id") != run_id
            or not isinstance(receipt.get("cycle_index"), int)
            or not 1 <= receipt["cycle_index"] < cycle_index
            or receipt.get("terminal") is not True
            or receipt.get("attempt_count") != 1
            or receipt.get("retry_allowed") is not False
            or receipt.get("trigger_is_fill") is not False
            or receipt.get("fill_claim") is not False
            or receipt.get("position_claim") is not False
            or receipt.get("pnl_claim") is not False
            or _moment(receipt.get("outcome_not_before"), code)
            > _moment(receipt.get("resolved_at"), code)
            or _moment(receipt.get("available_at"), code)
            > _moment(receipt.get("resolved_at"), code)
            or _moment(receipt.get("available_at"), code) > decision
            or _moment(receipt.get("resolved_at"), code) > decision
        ):
            raise V32AgentLifecycleError(code)
        _boundary(receipt, code)
        normalized.append(
            (
                dict(receipt),
                _embedded_binding(
                    document=receipt,
                    binding=binding,
                    schema_id=OUTCOME_RECEIPT_SCHEMA_ID,
                    digest_field=OUTCOME_RECEIPT_DIGEST_FIELD,
                    semantic_digest=semantic,
                    code=code,
                ),
            )
        )
    normalized.sort(
        key=lambda pair: (
            pair[0].get("available_at", pair[0]["resolved_at"]),
            pair[0]["schedule_id"],
        )
    )
    return [pair[0] for pair in normalized], [pair[1] for pair in normalized]


def _verify_proposal_supports(
    *,
    run_id: str,
    experiment_run_id: str,
    cycle_index: int,
    decision_time: str,
    documents: Mapping[str, Mapping[str, Any]],
    bindings: Mapping[str, Mapping[str, Any]],
    previous_timeframe_state: Mapping[str, Any] | None,
    governing_authority_document: Mapping[str, Any],
    governing_authority_binding: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]], dict[str, str]]:
    expected = set(PROPOSAL_SUPPORT_SPECS)
    if not isinstance(documents, Mapping) or set(documents) != expected or not isinstance(bindings, Mapping) or set(bindings) != expected:
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_SUPPORT_SET_INVALID")
    docs = {name: dict(documents[name]) for name in sorted(expected)}
    try:
        semantic = {
            "active_authority_projection": (
                verify_v32_active_authority_projection(
                    docs["active_authority_projection"]
                )
            ),
            "experiment_contract": verify_v32_experiment_contract_v1(docs["experiment_contract"]),
            "timeframe_context_state": (
                verify_v32_timeframe_context_state_v1(docs["timeframe_context_state"])
                if cycle_index == 1
                else verify_v32_timeframe_context_transition_v1(
                    previous_state=previous_timeframe_state,
                    current_state=docs["timeframe_context_state"],
                )
            ),
            "agent_market_graph_view": (
                verify_v32_agent_market_graph_view_intrinsic_v1(
                    docs["agent_market_graph_view"]
                )
            ),
            "twelve_axis_source_registry": verify_v31_native_sentiment_source_registry(docs["twelve_axis_source_registry"]),
            "association_preregistration": verify_v32_association_preregistration(
                docs["association_preregistration"]
            ),
            "evaluation_contract": verify_v32_evaluation_contract(
                docs["evaluation_contract"],
                docs["association_preregistration"],
            ),
            "clock_and_tick_policy": verify_v32_clock_and_tick_policy_v1(
                docs["clock_and_tick_policy"]
            ),
            "outcome_adapter_contract": (
                verify_v32_public_outcome_adapter_contract_v1(
                    docs["outcome_adapter_contract"]
                )
            ),
            "cycle_source_admission": verify_v32_cycle_source_admission(
                docs["cycle_source_admission"]
            ),
            "context_compaction_policy": (
                verify_v32_context_compaction_policy_v1(
                    docs["context_compaction_policy"]
                )
            ),
            "unknown_subjective_policy": (
                verify_v32_unknown_subjective_policy_v1(
                    docs["unknown_subjective_policy"]
                )
            ),
            "data_gap_manual_policy": verify_v32_data_gap_manual_policy_v1(
                docs["data_gap_manual_policy"]
            ),
            "cycle_audit_policy": verify_v32_cycle_audit_policy_v1(
                docs["cycle_audit_policy"]
            ),
            "environment_capability_profile": (
                verify_v32_environment_capability_profile_v1(
                    docs["environment_capability_profile"]
                )
            ),
            "recovery_supervision_policy": (
                verify_v32_recovery_supervision_policy_v1(
                    docs["recovery_supervision_policy"]
                )
            ),
        }
        semantic["authorized_revision_support_bundle"] = (
            _verify_authorized_revision_support_bundle(
                document=docs["authorized_revision_support_bundle"],
                component_documents=docs,
                component_bindings=bindings,
                component_semantics=semantic,
            )
        )
    except V32AgentLifecycleError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_SUPPORT_INVALID") from exc
    experiment = docs["experiment_contract"]
    timeframe = docs["timeframe_context_state"]
    source = docs["cycle_source_admission"]
    authority_projection = docs["active_authority_projection"]
    market_view = docs["agent_market_graph_view"]
    expected_mode = "FULL_CONTEXT" if cycle_index == 1 else "DELTA_UPDATE"
    if (
        authority_projection.get("authorized_run_id") != run_id
        or authority_projection.get("governing_authority_binding")
        != governing_authority_binding
        or authority_projection.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != governing_authority_document.get(AUTHORITY_DIGEST_FIELD)
        or authority_projection.get("experiment_contract_digest")
        != semantic["experiment_contract"]
        or experiment.get("run_id") != experiment_run_id
        or timeframe.get("run_id") != run_id
        or timeframe.get("cycle_index") != cycle_index
        or timeframe.get("decision_time") != decision_time
        or timeframe.get("state_mode") != expected_mode
        or source.get("run_id") != run_id
        or source.get("cycle_index") != cycle_index
        or source.get("decision_time") != decision_time
        or source.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != semantic["active_authority_projection"]
        or source.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != governing_authority_document.get(AUTHORITY_DIGEST_FIELD)
        or market_view.get("run_id") != run_id
        or market_view.get("cycle_index") != cycle_index
        or _moment(
            market_view.get("as_of"), "V32_AGENT_MARKET_VIEW_TIME_INVALID"
        )
        > _moment(decision_time, "V32_AGENT_MARKET_VIEW_TIME_INVALID")
        or docs["association_preregistration"].get("run_scope_id")
        != experiment_run_id
        or docs["evaluation_contract"].get("run_scope_id")
        != experiment_run_id
        or docs["clock_and_tick_policy"].get("run_scope_id")
        != experiment_run_id
        or docs["outcome_adapter_contract"].get("run_scope_id")
        != experiment_run_id
        or docs["evaluation_contract"].get("association_preregistration_digest") != semantic["association_preregistration"]
        or experiment.get("support_bindings", {}).get("association_preregistration_digest") != semantic["association_preregistration"]
        or experiment.get("support_bindings", {}).get("evaluation_contract_digest") != semantic["evaluation_contract"]
        or experiment.get("support_bindings", {}).get("clock_policy_digest") != semantic["clock_and_tick_policy"]
        or experiment.get("support_bindings", {}).get("outcome_adapter_contract_digest") != semantic["outcome_adapter_contract"]
        or experiment.get("support_bindings", {}).get("twelve_axis_source_registry_digest") != semantic["twelve_axis_source_registry"]
        or experiment.get("support_bindings", {}).get(
            "authorized_revision_support_bundle_digest"
        )
        != semantic["authorized_revision_support_bundle"]
        or experiment.get("support_bindings", {}).get(
            "recovery_supervision_policy_digest"
        )
        != semantic["recovery_supervision_policy"]
        or docs["authorized_revision_support_bundle"].get("run_scope_id")
        != experiment_run_id
        or any(
            docs[name].get("run_scope_id") != experiment_run_id
            for name in _AUTHORIZED_REVISION_COMPONENT_SUPPORT_NAMES.values()
        )
        or any(
            _moment(
                docs[name].get("frozen_at"),
                "V32_AGENT_REVISION_SUPPORT_TIME_INVALID",
            )
            > _moment(
                decision_time, "V32_AGENT_REVISION_SUPPORT_TIME_INVALID"
            )
            for name in (
                "authorized_revision_support_bundle",
                *_AUTHORIZED_REVISION_COMPONENT_SUPPORT_NAMES.values(),
                "recovery_supervision_policy",
            )
        )
    ):
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_SUPPORT_CROSS_BINDING_INVALID")
    normalized_bindings: dict[str, dict[str, str]] = {}
    for name, (schema_id, digest_field) in PROPOSAL_SUPPORT_SPECS.items():
        normalized_bindings[name] = _embedded_binding(
            document=docs[name],
            binding=bindings[name],
            schema_id=schema_id,
            digest_field=digest_field,
            semantic_digest=semantic[name],
            code="V32_AGENT_PROPOSAL_SUPPORT_BINDING_INVALID",
        )
    return docs, normalized_bindings, semantic


def build_v32_proposal_canonical_packet_v1(
    *,
    run_id: str,
    cycle_index: int,
    context_profile: str,
    context_mode: str,
    prepared_at: str,
    decision_time: str,
    authority_document: Mapping[str, Any],
    authority_binding: Mapping[str, Any],
    theory_semantic_document: Mapping[str, Any],
    theory_semantic_document_binding: Mapping[str, Any],
    support_documents: Mapping[str, Mapping[str, Any]],
    support_bindings: Mapping[str, Mapping[str, Any]],
    previous_dynamic_research_state: Mapping[str, Any] | None,
    previous_dynamic_research_state_binding: Mapping[str, Any] | None,
    previous_dynamic_action_plan: Mapping[str, Any] | None,
    previous_dynamic_action_plan_binding: Mapping[str, Any] | None,
    previous_timeframe_context_state: Mapping[str, Any] | None,
    previous_timeframe_context_state_binding: Mapping[str, Any] | None,
    matured_outcome_receipts: Sequence[Mapping[str, Any]],
    matured_outcome_receipt_bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    run = _text(run_id, "V32_AGENT_PROPOSAL_RUN_INVALID")
    cycle = _cycle(cycle_index)
    if context_profile not in V32_CONTEXT_PROFILES:
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_PROFILE_INVALID")
    expected_mode = "FULL_CONTEXT" if cycle == 1 else "DELTA_CONTEXT"
    if context_mode != expected_mode:
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_MODE_INVALID")
    prepared = _time(prepared_at, "V32_AGENT_PROPOSAL_TIME_INVALID")
    decision = _time(decision_time, "V32_AGENT_PROPOSAL_TIME_INVALID")
    if _moment(prepared, "V32_AGENT_PROPOSAL_TIME_INVALID") > _moment(decision, "V32_AGENT_PROPOSAL_TIME_INVALID"):
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_TIME_INVALID")
    try:
        authority_digest = verify_v32_authority_v1(authority_document)
    except V32AuthorizationError as exc:
        raise V32AgentLifecycleError(
            "V32_AGENT_PROPOSAL_AUTHORITY_INVALID"
        ) from exc
    expected_authority_profile = _PROFILE_AUTHORITY_PROFILE[context_profile]
    expected_operation = (
        "V32_DYNAMIC_AGGRESSIVE_PROCESS_PILOT"
        if expected_authority_profile == TARGET_PROFILE
        else "V32_ISOLATED_QUALIFICATION"
    )
    if (
        authority_document.get("profile") != expected_authority_profile
        or authority_document.get("run_id") != run
        or authority_document.get("status") != "ACTIVE"
        or authority_document.get("authorized_operation") != expected_operation
        or _moment(
            authority_document.get("recorded_at"),
            "V32_AGENT_PROPOSAL_AUTHORITY_TIME_INVALID",
        )
        > _moment(prepared, "V32_AGENT_PROPOSAL_AUTHORITY_TIME_INVALID")
        or (
            expected_authority_profile == TARGET_PROFILE
            and (
                authority_document.get("target_run_id") != run
                or authority_document.get("target_experiment_authorized")
                is not True
                or authority_document.get("analysis_cycles")
                != TOTAL_ANALYSIS_CYCLES
                or authority_document.get("outcome_schedules")
                != TOTAL_OUTCOME_SCHEDULES
            )
        )
        or (
            expected_authority_profile == QUALIFICATION_PROFILE
            and (
                authority_document.get("target_run_id") == run
                or authority_document.get("target_experiment_authorized")
                is not False
                or authority_document.get("analysis_cycles") != 1
                or authority_document.get("outcome_schedules") != 0
                or cycle != 1
            )
        )
    ):
        raise V32AgentLifecycleError(
            "V32_AGENT_PROPOSAL_AUTHORITY_SCOPE_INVALID"
        )
    authority = _embedded_binding(
        document=authority_document,
        binding=authority_binding,
        schema_id=AUTHORITY_SCHEMA_ID,
        digest_field=AUTHORITY_DIGEST_FIELD,
        semantic_digest=authority_digest,
        code="V32_AGENT_PROPOSAL_AUTHORITY_INVALID",
    )
    theory_digest = verify_v32_theory_semantic_document_v1(theory_semantic_document)
    theory_binding = _embedded_binding(
        document=theory_semantic_document,
        binding=theory_semantic_document_binding,
        schema_id=THEORY_DOCUMENT_SCHEMA_ID,
        digest_field=THEORY_DOCUMENT_DIGEST_FIELD,
        semantic_digest=theory_digest,
        code="V32_AGENT_PROPOSAL_THEORY_BINDING_INVALID",
    )
    docs, bindings, semantics = _verify_proposal_supports(
        run_id=run,
        experiment_run_id=authority_document["target_run_id"],
        cycle_index=cycle,
        decision_time=decision,
        documents=support_documents,
        bindings=support_bindings,
        previous_timeframe_state=previous_timeframe_context_state,
        governing_authority_document=authority_document,
        governing_authority_binding=authority,
    )
    previous_dynamic: dict[str, Any] | None = None
    previous_action: dict[str, Any] | None = None
    previous_timeframe: dict[str, Any] | None = None
    previous_dynamic_binding: dict[str, str] | None = None
    previous_action_binding: dict[str, str] | None = None
    previous_timeframe_binding: dict[str, str] | None = None
    if cycle == 1:
        if any(
            value is not None
            for value in (
                previous_dynamic_research_state,
                previous_dynamic_research_state_binding,
                previous_dynamic_action_plan,
                previous_dynamic_action_plan_binding,
                previous_timeframe_context_state,
                previous_timeframe_context_state_binding,
            )
        ):
            raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_GENESIS_PREVIOUS_FORBIDDEN")
    else:
        if not all(
            value is not None
            for value in (
                previous_dynamic_research_state,
                previous_dynamic_research_state_binding,
                previous_dynamic_action_plan,
                previous_dynamic_action_plan_binding,
                previous_timeframe_context_state,
                previous_timeframe_context_state_binding,
            )
        ):
            raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_PREVIOUS_REQUIRED")
        dynamic_digest = verify_v32_dynamic_research_state_v1(previous_dynamic_research_state)
        action_digest = verify_v32_dynamic_action_plan_v1(
            previous_dynamic_action_plan,
            dynamic_research_state=previous_dynamic_research_state,
        )
        timeframe_digest = verify_self_digest(previous_timeframe_context_state, TIMEFRAME_DIGEST_FIELD)
        if (
            previous_dynamic_research_state.get("run_id") != run
            or previous_dynamic_research_state.get("cycle_index") != cycle - 1
            or previous_dynamic_action_plan.get("run_id") != run
            or previous_dynamic_action_plan.get("cycle_index") != cycle - 1
            or previous_timeframe_context_state.get("run_id") != run
            or previous_timeframe_context_state.get("cycle_index") != cycle - 1
        ):
            raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_PREVIOUS_IDENTITY_INVALID")
        previous_dynamic = dict(previous_dynamic_research_state)
        previous_action = dict(previous_dynamic_action_plan)
        previous_timeframe = dict(previous_timeframe_context_state)
        previous_dynamic_binding = _embedded_binding(
            document=previous_dynamic,
            binding=previous_dynamic_research_state_binding,
            schema_id=DYNAMIC_STATE_SCHEMA_ID,
            digest_field=DYNAMIC_STATE_DIGEST_FIELD,
            semantic_digest=dynamic_digest,
            code="V32_AGENT_PROPOSAL_PREVIOUS_BINDING_INVALID",
        )
        previous_action_binding = _embedded_binding(
            document=previous_action,
            binding=previous_dynamic_action_plan_binding,
            schema_id=ACTION_PLAN_SCHEMA_ID,
            digest_field=ACTION_PLAN_DIGEST_FIELD,
            semantic_digest=action_digest,
            code="V32_AGENT_PROPOSAL_PREVIOUS_BINDING_INVALID",
        )
        previous_timeframe_binding = _embedded_binding(
            document=previous_timeframe,
            binding=previous_timeframe_context_state_binding,
            schema_id=TIMEFRAME_SCHEMA_ID,
            digest_field=TIMEFRAME_DIGEST_FIELD,
            semantic_digest=timeframe_digest,
            code="V32_AGENT_PROPOSAL_PREVIOUS_BINDING_INVALID",
        )
    receipts, receipt_bindings = _verify_matured_receipts(
        receipts=matured_outcome_receipts,
        bindings=matured_outcome_receipt_bindings,
        run_id=run,
        cycle_index=cycle,
        decision_time=decision,
    )
    experiment_theory = docs["experiment_contract"].get("theory_binding", {})
    authority_contract_binding = authority_document.get(
        "experiment_contract_binding", {}
    )
    if (
        experiment_theory.get("theory_version") != THEORY_VERSION
        or experiment_theory.get("physical_sha256") != theory_semantic_document.get("physical_sha256")
        or experiment_theory.get("semantic_digest") != theory_digest
        or (cycle > 1 and docs["timeframe_context_state"].get("previous_state_digest") != previous_timeframe_binding["semantic_digest"])
        or docs["cycle_source_admission"].get(
            GOVERNING_AUTHORITY_DIGEST_FIELD
        )
        != authority["semantic_digest"]
        or docs["cycle_source_admission"].get(
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
        )
        != semantics["active_authority_projection"]
        or docs["cycle_source_admission"].get("experiment_contract_digest")
        != semantics["experiment_contract"]
        or authority_contract_binding.get("semantic_digest")
        != semantics["experiment_contract"]
        or authority_contract_binding.get("physical_sha256")
        != bindings["experiment_contract"]["physical_sha256"]
        or _moment(
            docs["experiment_contract"].get("frozen_at"),
            "V32_AGENT_PROPOSAL_AUTHORITY_TIME_INVALID",
        )
        > _moment(
            authority_document.get("recorded_at"),
            "V32_AGENT_PROPOSAL_AUTHORITY_TIME_INVALID",
        )
        or _moment(
            authority_document.get("recorded_at"),
            "V32_AGENT_PROPOSAL_AUTHORITY_TIME_INVALID",
        )
        > _moment(
            docs["cycle_source_admission"].get("admitted_at"),
            "V32_AGENT_PROPOSAL_AUTHORITY_TIME_INVALID",
        )
        or (
            expected_authority_profile == QUALIFICATION_PROFILE and receipts
        )
    ):
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_CROSS_BINDING_INVALID")
    document = {
        "schema_id": PROPOSAL_PACKET_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run,
        "cycle_index": cycle,
        "context_profile": context_profile,
        "context_mode": context_mode,
        "prepared_at": prepared,
        "decision_time": decision,
        "authority_document": dict(authority_document),
        "authority_binding": authority,
        "theory_semantic_document": dict(theory_semantic_document),
        "theory_semantic_document_binding": theory_binding,
        "support_documents": docs,
        "support_bindings": bindings,
        "support_bindings_digest": canonical_digest(bindings),
        "previous_dynamic_research_state": previous_dynamic,
        "previous_dynamic_research_state_binding": previous_dynamic_binding,
        "previous_dynamic_action_plan": previous_action,
        "previous_dynamic_action_plan_binding": previous_action_binding,
        "previous_timeframe_context_state": previous_timeframe,
        "previous_timeframe_context_state_binding": previous_timeframe_binding,
        "matured_outcome_receipts": receipts,
        "matured_outcome_receipt_bindings": receipt_bindings,
        "matured_outcome_receipts_digest": canonical_digest(receipt_bindings),
        "forbidden_current_objects": [
            "CURRENT_DYNAMIC_RESEARCH_STATE",
            "CURRENT_FINAL_ACTION_PLAN",
            "CURRENT_OUTCOME_SCHEDULE",
            "FUTURE_OUTCOME",
        ],
        "full_theory_utf8_required": True,
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "account_access": False,
        "order_submission": False,
        "fill_claim": "NONE_NO_FILL_MODEL",
        "pnl_claim": "NONE_NO_PNL_MODEL",
        "executable": False,
        "claim": V32_LIFECYCLE_CLAIM,
    }
    # The complete packet is the write-once semantic original.  Its size does
    # not decide whether it may exist; the Agent-input builder below decides
    # between direct inline delivery and lossless sharded delivery.
    return self_digest(document, PROPOSAL_PACKET_DIGEST_FIELD)


@_memoized_lifecycle_verifier("VERIFY_PROPOSAL_CANONICAL_PACKET_V1")
def verify_v32_proposal_canonical_packet_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _PROPOSAL_PACKET_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_PACKET_INVALID")
    try:
        supplied = verify_self_digest(document, PROPOSAL_PACKET_DIGEST_FIELD)
        rebuilt = build_v32_proposal_canonical_packet_v1(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            context_profile=document["context_profile"],
            context_mode=document["context_mode"],
            prepared_at=document["prepared_at"],
            decision_time=document["decision_time"],
            authority_document=document["authority_document"],
            authority_binding=document["authority_binding"],
            theory_semantic_document=document["theory_semantic_document"],
            theory_semantic_document_binding=document["theory_semantic_document_binding"],
            support_documents=document["support_documents"],
            support_bindings=document["support_bindings"],
            previous_dynamic_research_state=document["previous_dynamic_research_state"],
            previous_dynamic_research_state_binding=document["previous_dynamic_research_state_binding"],
            previous_dynamic_action_plan=document["previous_dynamic_action_plan"],
            previous_dynamic_action_plan_binding=document["previous_dynamic_action_plan_binding"],
            previous_timeframe_context_state=document["previous_timeframe_context_state"],
            previous_timeframe_context_state_binding=document["previous_timeframe_context_state_binding"],
            matured_outcome_receipts=document["matured_outcome_receipts"],
            matured_outcome_receipt_bindings=document["matured_outcome_receipt_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_PACKET_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[PROPOSAL_PACKET_DIGEST_FIELD]:
        raise V32AgentLifecycleError("V32_AGENT_PROPOSAL_PACKET_RECONSTRUCTION_MISMATCH")
    return supplied


def _decimal_between_zero_and_one(value: Any, code: str) -> Decimal:
    if not isinstance(value, str):
        raise V32AgentLifecycleError(code)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise V32AgentLifecycleError(code) from exc
    if not number.is_finite() or not Decimal("0") <= number <= Decimal("1"):
        raise V32AgentLifecycleError(code)
    if canonical_decimal(number) != value:
        raise V32AgentLifecycleError(code)
    return number


def _risk_arithmetic(value: Any) -> dict[str, str]:
    code = "V32_AGENT_ACTION_EVALUATION_RISK_INVALID"
    if not isinstance(value, Mapping) or set(value) != _ACTION_EVALUATION_RISK_FIELDS:
        raise V32AgentLifecycleError(code)
    upper_text = value.get("reference_risk_upper_bound")
    if not isinstance(upper_text, str):
        raise V32AgentLifecycleError(code)
    try:
        upper = Decimal(upper_text)
    except InvalidOperation as exc:
        raise V32AgentLifecycleError(code) from exc
    if (
        not upper.is_finite()
        or upper != Decimal("1")
        or canonical_decimal(upper) != upper_text
    ):
        raise V32AgentLifecycleError(code)
    subjective_tier = _text(value.get("subjective_plausibility_tier"), code)
    residual_tier = _text(value.get("residual_uncertainty_tier"), code)
    if (
        subjective_tier not in SUBJECTIVE_TIER_RISK_CAP_UNITS
        or residual_tier not in SUBJECTIVE_TIER_RISK_CAP_UNITS
    ):
        raise V32AgentLifecycleError(code)
    residual_clarity_cap_units = 100 - SUBJECTIVE_TIER_RISK_CAP_UNITS[
        residual_tier
    ]
    cap_units = min(
        SUBJECTIVE_TIER_RISK_CAP_UNITS[subjective_tier],
        residual_clarity_cap_units,
    )
    ceiling = upper * Decimal(cap_units) / Decimal("100")
    if value.get("agent_reference_risk_ceiling") != canonical_decimal(ceiling):
        raise V32AgentLifecycleError(code)
    if (
        value.get("calculation_policy")
        != "AGENT_CEILING_ONLY_UPPER_BOUND_TIMES_MIN_SUBJECTIVE_TIER_CAP_AND_COMPLEMENT_OF_RESIDUAL_UNCERTAINTY_TIER_DERIVED_BY_SEALED_PLAN"
    ):
        raise V32AgentLifecycleError(code)
    return {
        "reference_risk_upper_bound": canonical_decimal(upper),
        "subjective_plausibility_tier": subjective_tier,
        "residual_uncertainty_tier": residual_tier,
        "agent_reference_risk_ceiling": canonical_decimal(ceiling),
        "calculation_policy": (
            "AGENT_CEILING_ONLY_UPPER_BOUND_TIMES_MIN_SUBJECTIVE_TIER_CAP_"
            "AND_COMPLEMENT_OF_RESIDUAL_UNCERTAINTY_TIER_DERIVED_BY_"
            "SEALED_PLAN"
        ),
    }


def _candidate_rows(
    value: Any,
    *,
    reference_context: str,
    risk_arithmetic_digest: str,
    agent_reference_risk_ceiling: Decimal,
) -> list[dict[str, Any]]:
    code = "V32_AGENT_ACTION_EVALUATION_CANDIDATES_INVALID"
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32AgentLifecycleError(code)
    expected_grid = legal_v32_dynamic_action_keys_v1(reference_context)
    expected_keys = {f"{action}:{direction}" for action, direction in expected_grid}
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != _ACTION_EVALUATION_CANDIDATE_FIELDS:
            raise V32AgentLifecycleError(code)
        action_kind = _text(row.get("action_kind"), code)
        direction = _text(row.get("direction"), code)
        action_key = f"{action_kind}:{direction}"
        feasibility = row.get("feasibility")
        reasons = row.get("block_reasons")
        evidence = row.get("evidence_refs")
        if (
            row.get("action_key") != action_key
            or feasibility not in FEASIBILITY_STATES
            or isinstance(reasons, (str, bytes))
            or not isinstance(reasons, Sequence)
            or isinstance(evidence, (str, bytes))
            or not isinstance(evidence, Sequence)
        ):
            raise V32AgentLifecycleError(code)
        normalized_reasons = [_text(item, code) for item in reasons]
        normalized_evidence = [_text(item, code) for item in evidence]
        if (
            not normalized_reasons
            or normalized_reasons != sorted(set(normalized_reasons))
            or any(reason not in BLOCK_REASONS for reason in normalized_reasons)
            or normalized_evidence != sorted(set(normalized_evidence))
            or (feasibility == "ELIGIBLE" and normalized_reasons != ["NONE"])
            or (feasibility == "BLOCKED" and "NONE" in normalized_reasons)
        ):
            raise V32AgentLifecycleError(code)
        risk_text = row.get("risk_reference_units")
        if not isinstance(risk_text, str):
            raise V32AgentLifecycleError(code)
        try:
            risk = Decimal(risk_text)
        except InvalidOperation as exc:
            raise V32AgentLifecycleError(code) from exc
        if (
            not risk.is_finite()
            or risk < 0
            or risk > agent_reference_risk_ceiling
            or canonical_decimal(risk) != risk_text
            or (feasibility == "BLOCKED" and risk != 0)
            or row.get("risk_arithmetic_digest") != risk_arithmetic_digest
        ):
            raise V32AgentLifecycleError(code)
        rows.append(
            {
                "candidate_id": _text(row.get("candidate_id"), code),
                "action_kind": action_kind,
                "direction": direction,
                "action_key": action_key,
                "feasibility": feasibility,
                "block_reasons": normalized_reasons,
                "evidence_refs": normalized_evidence,
                "risk_reference_units": canonical_decimal(risk),
                "risk_arithmetic_digest": risk_arithmetic_digest,
            }
        )
    if (
        {row["action_key"] for row in rows} != expected_keys
        or len(rows) != len(expected_keys)
        or len({row["candidate_id"] for row in rows}) != len(rows)
    ):
        raise V32AgentLifecycleError(code)
    return sorted(rows, key=lambda row: row["action_key"])


def build_v32_action_evaluation_v1(
    *,
    run_id: str,
    cycle_index: int,
    evaluated_at: str,
    proposal_consumption_digest: str,
    compiled_dynamic_state_digest: str,
    reference_context: str,
    risk_arithmetic: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        legal_grid = [
            {"action_kind": action, "direction": direction, "action_key": f"{action}:{direction}"}
            for action, direction in legal_v32_dynamic_action_keys_v1(reference_context)
        ]
    except ValueError as exc:
        raise V32AgentLifecycleError("V32_AGENT_ACTION_EVALUATION_INVALID") from exc
    normalized_risk = _risk_arithmetic(risk_arithmetic)
    risk_digest = canonical_digest(normalized_risk)
    normalized_candidates = _candidate_rows(
        candidate_rows,
        reference_context=reference_context,
        risk_arithmetic_digest=risk_digest,
        agent_reference_risk_ceiling=Decimal(
            normalized_risk["agent_reference_risk_ceiling"]
        ),
    )
    if not any(row["feasibility"] == "ELIGIBLE" for row in normalized_candidates):
        raise V32AgentLifecycleError("V32_AGENT_ACTION_EVALUATION_INVALID")
    return self_digest(
        {
            "schema_id": ACTION_EVALUATION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": _text(run_id, "V32_AGENT_ACTION_EVALUATION_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "evaluated_at": _time(evaluated_at, "V32_AGENT_ACTION_EVALUATION_INVALID"),
            "proposal_consumption_digest": _digest(proposal_consumption_digest, "V32_AGENT_ACTION_EVALUATION_INVALID"),
            "compiled_dynamic_state_digest": _digest(compiled_dynamic_state_digest, "V32_AGENT_ACTION_EVALUATION_INVALID"),
            "reference_context": reference_context,
            "legal_action_grid": legal_grid,
            "legal_action_grid_digest": canonical_digest(legal_grid),
            "risk_arithmetic": normalized_risk,
            "risk_arithmetic_digest": risk_digest,
            "candidate_rows": normalized_candidates,
            "candidate_rows_digest": canonical_digest(normalized_candidates),
            "evaluation_status": "SEALED_CANDIDATE_EVALUATION_NO_FINAL_SELECTION",
            "final_selection_present": False,
            "future_outcome_present": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        ACTION_EVALUATION_DIGEST_FIELD,
    )


@_memoized_lifecycle_verifier("VERIFY_ACTION_EVALUATION_V1")
def verify_v32_action_evaluation_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _ACTION_EVALUATION_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_ACTION_EVALUATION_INVALID")
    try:
        supplied = verify_self_digest(document, ACTION_EVALUATION_DIGEST_FIELD)
        rebuilt = build_v32_action_evaluation_v1(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            evaluated_at=document["evaluated_at"],
            proposal_consumption_digest=document["proposal_consumption_digest"],
            compiled_dynamic_state_digest=document["compiled_dynamic_state_digest"],
            reference_context=document["reference_context"],
            risk_arithmetic=document["risk_arithmetic"],
            candidate_rows=document["candidate_rows"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_ACTION_EVALUATION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[ACTION_EVALUATION_DIGEST_FIELD]:
        raise V32AgentLifecycleError("V32_AGENT_ACTION_EVALUATION_INVALID")
    return supplied


def _packet_spec(stage: str) -> tuple[str, str]:
    if stage == "PROPOSAL":
        return PROPOSAL_PACKET_SCHEMA_ID, PROPOSAL_PACKET_DIGEST_FIELD
    if stage == "SELECTION":
        return SELECTION_PACKET_SCHEMA_ID, SELECTION_PACKET_DIGEST_FIELD
    raise V32AgentLifecycleError("V32_AGENT_STAGE_INVALID")


def _verify_packet(document: Mapping[str, Any], stage: str) -> str:
    return (
        verify_v32_proposal_canonical_packet_v1(document)
        if stage == "PROPOSAL"
        else verify_v32_selection_canonical_packet_v1(document)
    )


def build_v32_selection_canonical_packet_v1(
    *,
    proposal_input_context: Mapping[str, Any],
    proposal_input_context_binding: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_delivery_binding: Mapping[str, Any],
    proposal_consumption: Mapping[str, Any],
    proposal_consumption_binding: Mapping[str, Any],
    compiled_dynamic_research_state: Mapping[str, Any],
    compiled_dynamic_research_state_binding: Mapping[str, Any],
    sealed_action_evaluation: Mapping[str, Any],
    sealed_action_evaluation_binding: Mapping[str, Any],
    prepared_at: str,
) -> dict[str, Any]:
    proposal_context_digest = verify_v32_agent_input_context_descriptor_v1(
        proposal_input_context
    )
    if proposal_input_context.get("agent_stage") != "PROPOSAL":
        raise V32AgentLifecycleError("V32_AGENT_SELECTION_PROPOSAL_STAGE_INVALID")
    delivery_digest = verify_v32_agent_delivery_v1(proposal_delivery, agent_input_context=proposal_input_context)
    consumption_digest = verify_v32_agent_consumption_v1(
        proposal_consumption,
        agent_input_context=proposal_input_context,
        agent_delivery=proposal_delivery,
    )
    proposal_context_binding = _embedded_binding(
        document=proposal_input_context,
        binding=proposal_input_context_binding,
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        semantic_digest=proposal_context_digest,
        code="V32_AGENT_SELECTION_PROPOSAL_BINDING_INVALID",
    )
    proposal_delivery_typed = _embedded_binding(
        document=proposal_delivery,
        binding=proposal_delivery_binding,
        schema_id=AGENT_DELIVERY_SCHEMA_ID,
        digest_field=AGENT_DELIVERY_DIGEST_FIELD,
        semantic_digest=delivery_digest,
        code="V32_AGENT_SELECTION_PROPOSAL_BINDING_INVALID",
    )
    proposal_consumption_typed = _embedded_binding(
        document=proposal_consumption,
        binding=proposal_consumption_binding,
        schema_id=AGENT_CONSUMPTION_SCHEMA_ID,
        digest_field=AGENT_CONSUMPTION_DIGEST_FIELD,
        semantic_digest=consumption_digest,
        code="V32_AGENT_SELECTION_PROPOSAL_BINDING_INVALID",
    )
    dynamic_digest = verify_v32_dynamic_research_state_v1(compiled_dynamic_research_state)
    dynamic_binding = _embedded_binding(
        document=compiled_dynamic_research_state,
        binding=compiled_dynamic_research_state_binding,
        schema_id=DYNAMIC_STATE_SCHEMA_ID,
        digest_field=DYNAMIC_STATE_DIGEST_FIELD,
        semantic_digest=dynamic_digest,
        code="V32_AGENT_SELECTION_COMPILED_BINDING_INVALID",
    )
    evaluation_digest = verify_v32_action_evaluation_v1(sealed_action_evaluation)
    evaluation_binding = _embedded_binding(
        document=sealed_action_evaluation,
        binding=sealed_action_evaluation_binding,
        schema_id=ACTION_EVALUATION_SCHEMA_ID,
        digest_field=ACTION_EVALUATION_DIGEST_FIELD,
        semantic_digest=evaluation_digest,
        code="V32_AGENT_SELECTION_EVALUATION_BINDING_INVALID",
    )
    run = proposal_input_context["run_id"]
    cycle = proposal_input_context["cycle_index"]
    prepared = _time(prepared_at, "V32_AGENT_SELECTION_TIME_INVALID")
    if (
        compiled_dynamic_research_state.get("run_id") != run
        or compiled_dynamic_research_state.get("cycle_index") != cycle
        or sealed_action_evaluation.get("run_id") != run
        or sealed_action_evaluation.get("cycle_index") != cycle
        or sealed_action_evaluation.get("proposal_consumption_digest") != consumption_digest
        or sealed_action_evaluation.get("compiled_dynamic_state_digest") != dynamic_digest
        or _moment(prepared, "V32_AGENT_SELECTION_TIME_INVALID") < _moment(proposal_consumption["consumed_at"], "V32_AGENT_SELECTION_TIME_INVALID")
    ):
        raise V32AgentLifecycleError("V32_AGENT_SELECTION_CROSS_BINDING_INVALID")
    document = {
        "schema_id": SELECTION_PACKET_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run,
        "cycle_index": cycle,
        "context_profile": proposal_input_context["context_profile"],
        "context_mode": proposal_input_context["context_mode"],
        "prepared_at": prepared,
        "decision_time": proposal_input_context["decision_time"],
        "proposal_input_context": dict(proposal_input_context),
        "proposal_input_context_binding": proposal_context_binding,
        "proposal_delivery": dict(proposal_delivery),
        "proposal_delivery_binding": proposal_delivery_typed,
        "proposal_consumption": dict(proposal_consumption),
        "proposal_consumption_binding": proposal_consumption_typed,
        "compiled_dynamic_research_state": dict(compiled_dynamic_research_state),
        "compiled_dynamic_research_state_binding": dynamic_binding,
        "sealed_action_evaluation": dict(sealed_action_evaluation),
        "sealed_action_evaluation_binding": evaluation_binding,
        "forbidden_current_objects": ["CURRENT_FINAL_ACTION_PLAN", "CURRENT_OUTCOME_SCHEDULE", "FUTURE_OUTCOME"],
        "future_outcome_visible": False,
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "account_access": False,
        "order_submission": False,
        "fill_claim": "NONE_NO_FILL_MODEL",
        "pnl_claim": "NONE_NO_PNL_MODEL",
        "executable": False,
        "claim": V32_LIFECYCLE_CLAIM,
    }
    return self_digest(document, SELECTION_PACKET_DIGEST_FIELD)


@_memoized_lifecycle_verifier("VERIFY_SELECTION_CANONICAL_PACKET_V1")
def verify_v32_selection_canonical_packet_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _SELECTION_PACKET_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_SELECTION_PACKET_INVALID")
    try:
        supplied = verify_self_digest(document, SELECTION_PACKET_DIGEST_FIELD)
        rebuilt = build_v32_selection_canonical_packet_v1(
            proposal_input_context=document["proposal_input_context"],
            proposal_input_context_binding=document["proposal_input_context_binding"],
            proposal_delivery=document["proposal_delivery"],
            proposal_delivery_binding=document["proposal_delivery_binding"],
            proposal_consumption=document["proposal_consumption"],
            proposal_consumption_binding=document["proposal_consumption_binding"],
            compiled_dynamic_research_state=document["compiled_dynamic_research_state"],
            compiled_dynamic_research_state_binding=document["compiled_dynamic_research_state_binding"],
            sealed_action_evaluation=document["sealed_action_evaluation"],
            sealed_action_evaluation_binding=document["sealed_action_evaluation_binding"],
            prepared_at=document["prepared_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_SELECTION_PACKET_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[SELECTION_PACKET_DIGEST_FIELD]:
        raise V32AgentLifecycleError("V32_AGENT_SELECTION_PACKET_RECONSTRUCTION_MISMATCH")
    return supplied


def agent_input_context_ref_v1(cycle_index: int, stage: str) -> str:
    _packet_spec(stage)
    return f"{V32_AGENT_CONTEXT_ROOT}/cycles/{_cycle(cycle_index):04d}/{stage.lower()}-agent-input-context.json"


def agent_delivery_ref_v1(cycle_index: int, stage: str) -> str:
    _packet_spec(stage)
    return f"{V32_AGENT_CONTEXT_ROOT}/cycles/{_cycle(cycle_index):04d}/{stage.lower()}-agent-delivery.json"


def agent_consumption_ref_v1(cycle_index: int, stage: str) -> str:
    _packet_spec(stage)
    return f"{V32_AGENT_CONTEXT_ROOT}/cycles/{_cycle(cycle_index):04d}/{stage.lower()}-agent-consumption.json"


def agent_commit_envelope_ref_v1(cycle_index: int) -> str:
    return f"{V32_AGENT_CONTEXT_ROOT}/cycles/{_cycle(cycle_index):04d}/two-stage-commit-envelope.json"


_LOSSLESS_CONTEXT_PACKAGE_FIELDS = frozenset(
    {
        "manifest",
        "shards",
        "original_documents",
        "selection",
        "manifest_binding",
        "shard_bindings",
        "selection_binding",
    }
)


def _packet_evaluation_contract_digest(
    packet: Mapping[str, Any], stage: str
) -> str:
    try:
        value = (
            packet["support_documents"]["experiment_contract"][
                "support_bindings"
            ]["evaluation_contract_digest"]
            if stage == "PROPOSAL"
            else packet["proposal_input_context"]["evaluation_contract_digest"]
        )
    except (KeyError, TypeError) as exc:
        raise V32AgentLifecycleError(
            "V32_AGENT_INPUT_EVALUATION_CONTRACT_INVALID"
        ) from exc
    return str(_digest(value, "V32_AGENT_INPUT_EVALUATION_CONTRACT_INVALID"))


def _input_unit(
    *, unit_index: int, unit_kind: str, artifact_binding: Mapping[str, Any]
) -> dict[str, Any]:
    if (
        isinstance(unit_index, bool)
        or not isinstance(unit_index, int)
        or unit_index < 0
        or unit_kind not in {"CANONICAL_PACKET", "MANIFEST", "SELECTION", "SHARD"}
    ):
        raise V32AgentLifecycleError("V32_AGENT_INPUT_UNIT_INVALID")
    return {
        "unit_index": unit_index,
        "unit_kind": unit_kind,
        "artifact_binding": _binding(
            artifact_binding, "V32_AGENT_INPUT_UNIT_BINDING_INVALID"
        ),
    }


def _verify_lossless_context_package(
    *,
    agent_stage: str,
    canonical_packet: Mapping[str, Any],
    canonical_packet_binding: Mapping[str, Any],
    lossless_context_package: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str], list[dict[str, str]]]:
    if (
        not isinstance(lossless_context_package, Mapping)
        or set(lossless_context_package) != _LOSSLESS_CONTEXT_PACKAGE_FIELDS
    ):
        raise V32AgentLifecycleError("V32_AGENT_INPUT_SHARDED_PACKAGE_INVALID")
    try:
        originals = lossless_context_package["original_documents"]
        shards = lossless_context_package["shards"]
        shard_bindings = lossless_context_package["shard_bindings"]
        if (
            isinstance(originals, (str, bytes))
            or not isinstance(originals, Sequence)
            or len(originals) != 1
            or dict(originals[0]) != dict(canonical_packet)
            or isinstance(shards, (str, bytes))
            or not isinstance(shards, Sequence)
            or isinstance(shard_bindings, (str, bytes))
            or not isinstance(shard_bindings, Sequence)
            or len(shards) != len(shard_bindings)
        ):
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_SHARDED_PACKAGE_INVALID"
            )
        manifest = lossless_context_package["manifest"]
        selection = lossless_context_package["selection"]
        manifest_digest = verify_v32_context_compaction_bundle_v1(
            manifest, shards, original_documents=originals
        )
        selection_digest = verify_v32_context_shard_selection_v1(
            selection,
            manifest=manifest,
            shards=shards,
            original_documents=originals,
        )
        packet_ref = _binding(
            canonical_packet_binding,
            "V32_AGENT_INPUT_PACKET_BINDING_INVALID",
            schema_id=_packet_spec(agent_stage)[0],
            digest_field=_packet_spec(agent_stage)[1],
        )
        if (
            manifest.get("status") != "READY_LOSSLESS_SHARDED"
            or selection.get("selection_status")
            != "READY_FORCED_ALL_SHARDS_SEQUENTIAL"
            or manifest.get("run_id") != canonical_packet.get("run_id")
            or manifest.get("cycle_index") != canonical_packet.get("cycle_index")
            or manifest.get("source_artifacts") != [
                {
                    "artifact_binding": packet_ref,
                    "canonical_bytes": len(canonical_bytes(canonical_packet)),
                }
            ]
            or selection.get("selected_member_count")
            != manifest.get("member_count")
            or selection.get("selected_member_ids_digest")
            != manifest.get("folded_member_ids_digest")
            or selection.get("selected_shard_count") != len(shards)
            or selection.get("forced_full_member_inventory") is not True
            or selection.get("forced_full_shard_inventory") is not True
            or selection.get("sequential_delivery_required") is not True
            or selection.get("truncation_performed") is not False
        ):
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_SHARDED_COMPLETENESS_INVALID"
            )
        manifest_ref = _embedded_binding(
            document=manifest,
            binding=lossless_context_package["manifest_binding"],
            schema_id=CONTEXT_MANIFEST_SCHEMA_ID,
            digest_field=CONTEXT_MANIFEST_DIGEST_FIELD,
            semantic_digest=manifest_digest,
            code="V32_AGENT_INPUT_SHARDED_BINDING_INVALID",
        )
        selection_ref = _embedded_binding(
            document=selection,
            binding=lossless_context_package["selection_binding"],
            schema_id=CONTEXT_SELECTION_SCHEMA_ID,
            digest_field=CONTEXT_SELECTION_DIGEST_FIELD,
            semantic_digest=selection_digest,
            code="V32_AGENT_INPUT_SHARDED_BINDING_INVALID",
        )
        normalized_shards = [
            _embedded_binding(
                document=shard,
                binding=supplied_binding,
                schema_id=CONTEXT_SHARD_SCHEMA_ID,
                digest_field=CONTEXT_SHARD_DIGEST_FIELD,
                semantic_digest=shard[CONTEXT_SHARD_DIGEST_FIELD],
                code="V32_AGENT_INPUT_SHARDED_BINDING_INVALID",
            )
            for shard, supplied_binding in zip(shards, shard_bindings, strict=True)
        ]
        if (
            [shard.get("shard_index") for shard in shards] != list(range(len(shards)))
            or selection.get("selected_shard_bindings") != normalized_shards
            or selection.get("selected_shard_bindings_digest")
            != canonical_digest(normalized_shards)
        ):
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_SHARDED_ORDER_INVALID"
            )
        return manifest_ref, selection_ref, normalized_shards
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError(
            "V32_AGENT_INPUT_SHARDED_PACKAGE_INVALID"
        ) from exc


def build_v32_agent_input_context_v1(
    *,
    agent_stage: str,
    canonical_packet: Mapping[str, Any],
    canonical_packet_binding: Mapping[str, Any],
    created_at: str,
    lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    schema_id, digest_field = _packet_spec(agent_stage)
    packet_digest = _verify_packet(canonical_packet, agent_stage)
    packet_binding = _embedded_binding(
        document=canonical_packet,
        binding=canonical_packet_binding,
        schema_id=schema_id,
        digest_field=digest_field,
        semantic_digest=packet_digest,
        code="V32_AGENT_INPUT_PACKET_BINDING_INVALID",
    )
    created = _time(created_at, "V32_AGENT_INPUT_TIME_INVALID")
    if _moment(created, "V32_AGENT_INPUT_TIME_INVALID") < _moment(
        canonical_packet["prepared_at"], "V32_AGENT_INPUT_TIME_INVALID"
    ):
        raise V32AgentLifecycleError("V32_AGENT_INPUT_TIME_INVALID")
    common = {
        "schema_id": AGENT_INPUT_CONTEXT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": canonical_packet["run_id"],
        "cycle_index": canonical_packet["cycle_index"],
        "context_profile": canonical_packet["context_profile"],
        "context_mode": canonical_packet["context_mode"],
        "decision_time": canonical_packet["decision_time"],
        "evaluation_contract_digest": _packet_evaluation_contract_digest(
            canonical_packet, agent_stage
        ),
        "created_at": created,
        "agent_id": V32_CURRENT_ROOT_AGENT_ID,
        "delivery_origin": V32_CURRENT_ROOT_DELIVERY_ORIGIN,
        "agent_stage": agent_stage,
        "canonical_packet_schema_id": schema_id,
        "canonical_packet_digest_field": digest_field,
        "canonical_packet_digest": packet_digest,
        "canonical_packet_binding": packet_binding,
        "controller_must_pass_document_unchanged": True,
        "single_attempt_required": True,
        "private_chain_of_thought_requested": False,
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "account_access": False,
        "order_submission": False,
        "fill_claim": "NONE_NO_FILL_MODEL",
        "pnl_claim": "NONE_NO_PNL_MODEL",
        "executable": False,
        "claim": V32_LIFECYCLE_CLAIM,
        "limitations": list(_LIMITATIONS),
    }
    inline_units = [
        _input_unit(
            unit_index=0,
            unit_kind="CANONICAL_PACKET",
            artifact_binding=packet_binding,
        )
    ]
    inline = self_digest(
        {
            **common,
            "context_delivery_mode": "INLINE",
            "canonical_packet": dict(canonical_packet),
            "context_compaction_manifest_binding": None,
            "context_shard_selection_binding": None,
            "selected_context_shard_bindings": [],
            "selected_context_shard_bindings_digest": canonical_digest([]),
            "ordered_input_delivery_units": inline_units,
            "ordered_input_delivery_units_digest": canonical_digest(inline_units),
            "ordered_input_delivery_unit_count": 1,
            "full_original_packet_embedded": True,
            "full_original_packet_replay_required": True,
        },
        AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    if len(canonical_bytes(inline)) <= MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES:
        if lossless_context_package is not None:
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_UNNEEDED_SHARDED_PACKAGE_INVALID"
            )
        return inline
    if lossless_context_package is None:
        raise V32AgentLifecycleError("CONTEXT_CAPACITY_UNRESOLVED")
    manifest_ref, selection_ref, shard_refs = _verify_lossless_context_package(
        agent_stage=agent_stage,
        canonical_packet=canonical_packet,
        canonical_packet_binding=packet_binding,
        lossless_context_package=lossless_context_package,
    )
    units = [
        _input_unit(
            unit_index=0, unit_kind="MANIFEST", artifact_binding=manifest_ref
        ),
        _input_unit(
            unit_index=1, unit_kind="SELECTION", artifact_binding=selection_ref
        ),
        *[
            _input_unit(
                unit_index=index + 2,
                unit_kind="SHARD",
                artifact_binding=shard_ref,
            )
            for index, shard_ref in enumerate(shard_refs)
        ],
    ]
    sharded = self_digest(
        {
            **common,
            "context_delivery_mode": "LOSSLESS_SHARDED",
            "canonical_packet": None,
            "context_compaction_manifest_binding": manifest_ref,
            "context_shard_selection_binding": selection_ref,
            "selected_context_shard_bindings": shard_refs,
            "selected_context_shard_bindings_digest": canonical_digest(shard_refs),
            "ordered_input_delivery_units": units,
            "ordered_input_delivery_units_digest": canonical_digest(units),
            "ordered_input_delivery_unit_count": len(units),
            "full_original_packet_embedded": False,
            "full_original_packet_replay_required": True,
        },
        AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    if len(canonical_bytes(sharded)) > MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES:
        raise V32AgentLifecycleError("CONTEXT_CAPACITY_UNRESOLVED")
    return sharded


@_memoized_lifecycle_verifier("VERIFY_AGENT_INPUT_CONTEXT_STRUCTURE_V1")
def _verify_v32_agent_input_context_structure_v1(
    document: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _INPUT_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_INPUT_INVALID")
    try:
        supplied = verify_self_digest(document, AGENT_INPUT_CONTEXT_DIGEST_FIELD)
        stage = document["agent_stage"]
        schema_id, digest_field = _packet_spec(stage)
        _cycle(document["cycle_index"])
        _time(document["created_at"], "V32_AGENT_INPUT_TIME_INVALID")
        _time(document["decision_time"], "V32_AGENT_INPUT_TIME_INVALID")
        _digest(
            document["evaluation_contract_digest"],
            "V32_AGENT_INPUT_EVALUATION_CONTRACT_INVALID",
        )
        packet_binding = _binding(
            document["canonical_packet_binding"],
            "V32_AGENT_INPUT_PACKET_BINDING_INVALID",
            schema_id=schema_id,
            digest_field=digest_field,
        )
        units = document["ordered_input_delivery_units"]
        if isinstance(units, (str, bytes)) or not isinstance(units, Sequence):
            raise V32AgentLifecycleError("V32_AGENT_INPUT_UNIT_INVALID")
        normalized_units = [
            _input_unit(
                unit_index=index,
                unit_kind=row.get("unit_kind") if isinstance(row, Mapping) else "",
                artifact_binding=(
                    row.get("artifact_binding") if isinstance(row, Mapping) else {}
                ),
            )
            for index, row in enumerate(units)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_INPUT_INVALID") from exc
    if (
        document.get("schema_id") != AGENT_INPUT_CONTEXT_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("context_profile") not in V32_CONTEXT_PROFILES
        or document.get("context_mode") not in V32_CONTEXT_MODES
        or document.get("agent_id") != V32_CURRENT_ROOT_AGENT_ID
        or document.get("delivery_origin") != V32_CURRENT_ROOT_DELIVERY_ORIGIN
        or document.get("canonical_packet_schema_id") != schema_id
        or document.get("canonical_packet_digest_field") != digest_field
        or document.get("canonical_packet_digest")
        != packet_binding["semantic_digest"]
        or document.get("ordered_input_delivery_units") != normalized_units
        or document.get("ordered_input_delivery_unit_count") != len(normalized_units)
        or document.get("ordered_input_delivery_units_digest")
        != canonical_digest(normalized_units)
        or document.get("controller_must_pass_document_unchanged") is not True
        or document.get("single_attempt_required") is not True
        or document.get("private_chain_of_thought_requested") is not False
        or document.get("chat_history_is_authority") is not False
        or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("account_access") is not False
        or document.get("order_submission") is not False
        or document.get("fill_claim") != "NONE_NO_FILL_MODEL"
        or document.get("pnl_claim") != "NONE_NO_PNL_MODEL"
        or document.get("executable") is not False
        or document.get("claim") != V32_LIFECYCLE_CLAIM
        or document.get("limitations") != list(_LIMITATIONS)
        or len(canonical_bytes(document)) > MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES
    ):
        raise V32AgentLifecycleError("V32_AGENT_INPUT_INVALID")
    mode = document.get("context_delivery_mode")
    if mode == "INLINE":
        packet = document.get("canonical_packet")
        if not isinstance(packet, Mapping):
            raise V32AgentLifecycleError("V32_AGENT_INPUT_INVALID")
        rebuilt = build_v32_agent_input_context_v1(
            agent_stage=stage,
            canonical_packet=packet,
            canonical_packet_binding=packet_binding,
            created_at=document["created_at"],
        )
        if dict(document) != rebuilt:
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_RECONSTRUCTION_MISMATCH"
            )
    elif mode == "LOSSLESS_SHARDED":
        shard_refs = document.get("selected_context_shard_bindings")
        if (
            document.get("canonical_packet") is not None
            or document.get("full_original_packet_embedded") is not False
            or document.get("full_original_packet_replay_required") is not True
            or not isinstance(shard_refs, list)
            or not shard_refs
            or len(normalized_units) < 3
            or document.get("selected_context_shard_bindings_digest")
            != canonical_digest(shard_refs)
            or normalized_units[0]["unit_kind"] != "MANIFEST"
            or normalized_units[1]["unit_kind"] != "SELECTION"
            or any(row["unit_kind"] != "SHARD" for row in normalized_units[2:])
            or [row["artifact_binding"] for row in normalized_units[2:]]
            != shard_refs
            or normalized_units[0]["artifact_binding"]
            != document.get("context_compaction_manifest_binding")
            or normalized_units[1]["artifact_binding"]
            != document.get("context_shard_selection_binding")
        ):
            raise V32AgentLifecycleError("V32_AGENT_INPUT_INVALID")
    else:
        raise V32AgentLifecycleError("V32_AGENT_INPUT_INVALID")
    return supplied


@_memoized_lifecycle_verifier("VERIFY_AGENT_INPUT_CONTEXT_DESCRIPTOR_V1")
def verify_v32_agent_input_context_descriptor_v1(
    document: Mapping[str, Any],
) -> str:
    """Verify the durable descriptor without claiming packet availability."""

    return _verify_v32_agent_input_context_structure_v1(document)


@_memoized_lifecycle_verifier("VERIFY_AGENT_INPUT_CONTEXT_V1")
def verify_v32_agent_input_context_v1(
    document: Mapping[str, Any],
    *,
    lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    supplied = verify_v32_agent_input_context_descriptor_v1(document)
    if document.get("context_delivery_mode") == "LOSSLESS_SHARDED":
        if lossless_context_package is None:
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_DURABLE_ORIGINAL_REQUIRED"
            )
        resolve_v32_agent_canonical_packet_v1(
            document, lossless_context_package=lossless_context_package
        )
    elif lossless_context_package is not None:
        raise V32AgentLifecycleError(
            "V32_AGENT_INPUT_UNNEEDED_SHARDED_PACKAGE_INVALID"
        )
    return supplied


def resolve_v32_agent_canonical_packet_v1(
    agent_input_context: Mapping[str, Any],
    *,
    lossless_context_package: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    _verify_v32_agent_input_context_structure_v1(agent_input_context)
    mode = agent_input_context["context_delivery_mode"]
    if mode == "INLINE":
        if lossless_context_package is not None:
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_UNNEEDED_SHARDED_PACKAGE_INVALID"
            )
        return agent_input_context["canonical_packet"]
    if lossless_context_package is None:
        raise V32AgentLifecycleError("V32_AGENT_INPUT_DURABLE_ORIGINAL_REQUIRED")
    try:
        originals = lossless_context_package["original_documents"]
        if (
            isinstance(originals, (str, bytes))
            or not isinstance(originals, Sequence)
            or len(originals) != 1
        ):
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_DURABLE_ORIGINAL_REQUIRED"
            )
        packet = originals[0]
        packet_digest = _verify_packet(packet, agent_input_context["agent_stage"])
        if (
            packet_digest != agent_input_context["canonical_packet_digest"]
            or packet.get("run_id") != agent_input_context["run_id"]
            or packet.get("cycle_index") != agent_input_context["cycle_index"]
            or packet.get("decision_time") != agent_input_context["decision_time"]
            or _packet_evaluation_contract_digest(
                packet, agent_input_context["agent_stage"]
            )
            != agent_input_context["evaluation_contract_digest"]
        ):
            raise V32AgentLifecycleError(
                "V32_AGENT_INPUT_DURABLE_ORIGINAL_MISMATCH"
            )
        manifest_ref, selection_ref, shard_refs = _verify_lossless_context_package(
            agent_stage=agent_input_context["agent_stage"],
            canonical_packet=packet,
            canonical_packet_binding=agent_input_context[
                "canonical_packet_binding"
            ],
            lossless_context_package=lossless_context_package,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError(
            "V32_AGENT_INPUT_DURABLE_ORIGINAL_MISMATCH"
        ) from exc
    if (
        manifest_ref
        != agent_input_context["context_compaction_manifest_binding"]
        or selection_ref != agent_input_context["context_shard_selection_binding"]
        or shard_refs != agent_input_context["selected_context_shard_bindings"]
    ):
        raise V32AgentLifecycleError("V32_AGENT_INPUT_SHARDED_BINDING_INVALID")
    return packet


def build_v32_agent_delivery_v1(
    *, agent_input_context: Mapping[str, Any], agent_input_context_binding: Mapping[str, Any], reserved_at: str, delivered_at: str, payload_utf8: str
) -> dict[str, Any]:
    context_digest = verify_v32_agent_input_context_descriptor_v1(
        agent_input_context
    )
    context_binding = _embedded_binding(
        document=agent_input_context,
        binding=agent_input_context_binding,
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        semantic_digest=context_digest,
        code="V32_AGENT_DELIVERY_CONTEXT_BINDING_INVALID",
    )
    reserved = _time(reserved_at, "V32_AGENT_DELIVERY_TIME_INVALID")
    delivered = _time(delivered_at, "V32_AGENT_DELIVERY_TIME_INVALID")
    if not isinstance(payload_utf8, str) or not payload_utf8:
        raise V32AgentLifecycleError("V32_AGENT_DELIVERY_PAYLOAD_INVALID")
    payload = payload_utf8.encode("utf-8", errors="strict")
    if len(payload) > MAX_AGENT_DELIVERY_UTF8_BYTES:
        raise V32AgentLifecycleError("V32_AGENT_DELIVERY_PAYLOAD_TOO_LARGE")
    if _moment(agent_input_context["created_at"], "V32_AGENT_DELIVERY_TIME_INVALID") > _moment(reserved, "V32_AGENT_DELIVERY_TIME_INVALID") or _moment(reserved, "V32_AGENT_DELIVERY_TIME_INVALID") > _moment(delivered, "V32_AGENT_DELIVERY_TIME_INVALID"):
        raise V32AgentLifecycleError("V32_AGENT_DELIVERY_TIME_INVALID")
    document = {
        "schema_id": AGENT_DELIVERY_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": agent_input_context["run_id"],
        "cycle_index": agent_input_context["cycle_index"],
        "context_profile": agent_input_context["context_profile"],
        "agent_stage": agent_input_context["agent_stage"],
        "reserved_at": reserved,
        "delivered_at": delivered,
        "agent_id": V32_CURRENT_ROOT_AGENT_ID,
        "delivery_origin": V32_CURRENT_ROOT_DELIVERY_ORIGIN,
        "attempt_number": 1,
        "max_attempts": 1,
        "retry_allowed": False,
        "agent_input_context_digest": context_digest,
        "agent_input_context_binding": context_binding,
        "payload_encoding": "UTF-8",
        "payload_utf8": payload_utf8,
        "payload_byte_length": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "terminal_status": "DELIVERED_TERMINAL_NO_RETRY",
        "transport_attestation_level": "PRACTICAL_CODEX_NOT_MODEL_ATTESTED",
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "account_access": False,
        "order_submission": False,
        "fill_claim": "NONE_NO_FILL_MODEL",
        "pnl_claim": "NONE_NO_PNL_MODEL",
        "executable": False,
        "claim": V32_LIFECYCLE_CLAIM,
        "limitations": list(_LIMITATIONS),
    }
    return self_digest(document, AGENT_DELIVERY_DIGEST_FIELD)


@_memoized_lifecycle_verifier("VERIFY_AGENT_DELIVERY_V1")
def verify_v32_agent_delivery_v1(document: Mapping[str, Any], *, agent_input_context: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _DELIVERY_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_DELIVERY_INVALID")
    try:
        supplied = verify_self_digest(document, AGENT_DELIVERY_DIGEST_FIELD)
        rebuilt = build_v32_agent_delivery_v1(
            agent_input_context=agent_input_context,
            agent_input_context_binding=document["agent_input_context_binding"],
            reserved_at=document["reserved_at"],
            delivered_at=document["delivered_at"],
            payload_utf8=document["payload_utf8"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_DELIVERY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[AGENT_DELIVERY_DIGEST_FIELD]:
        raise V32AgentLifecycleError("V32_AGENT_DELIVERY_RECONSTRUCTION_MISMATCH")
    return supplied


def build_v32_agent_consumption_v1(
    *, agent_input_context: Mapping[str, Any], agent_input_context_binding: Mapping[str, Any], agent_delivery: Mapping[str, Any], agent_delivery_binding: Mapping[str, Any], consumed_at: str
) -> dict[str, Any]:
    context_digest = verify_v32_agent_input_context_descriptor_v1(
        agent_input_context
    )
    delivery_digest = verify_v32_agent_delivery_v1(agent_delivery, agent_input_context=agent_input_context)
    context_binding = _embedded_binding(
        document=agent_input_context,
        binding=agent_input_context_binding,
        schema_id=AGENT_INPUT_CONTEXT_SCHEMA_ID,
        digest_field=AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        semantic_digest=context_digest,
        code="V32_AGENT_CONSUMPTION_BINDING_INVALID",
    )
    delivery_binding = _embedded_binding(
        document=agent_delivery,
        binding=agent_delivery_binding,
        schema_id=AGENT_DELIVERY_SCHEMA_ID,
        digest_field=AGENT_DELIVERY_DIGEST_FIELD,
        semantic_digest=delivery_digest,
        code="V32_AGENT_CONSUMPTION_BINDING_INVALID",
    )
    consumed = _time(consumed_at, "V32_AGENT_CONSUMPTION_TIME_INVALID")
    if _moment(consumed, "V32_AGENT_CONSUMPTION_TIME_INVALID") < _moment(agent_delivery["delivered_at"], "V32_AGENT_CONSUMPTION_TIME_INVALID"):
        raise V32AgentLifecycleError("V32_AGENT_CONSUMPTION_TIME_INVALID")
    stage = agent_input_context["agent_stage"]
    document = {
        "schema_id": AGENT_CONSUMPTION_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": agent_input_context["run_id"],
        "cycle_index": agent_input_context["cycle_index"],
        "context_profile": agent_input_context["context_profile"],
        "agent_stage": stage,
        "consumed_at": consumed,
        "agent_id": V32_CURRENT_ROOT_AGENT_ID,
        "agent_input_context_digest": context_digest,
        "agent_input_context_binding": context_binding,
        "agent_delivery_digest": delivery_digest,
        "agent_delivery_binding": delivery_binding,
        "payload_sha256": agent_delivery["payload_sha256"],
        "context_delivery_mode": agent_input_context["context_delivery_mode"],
        "ordered_input_delivery_units": list(
            agent_input_context["ordered_input_delivery_units"]
        ),
        "ordered_input_delivery_units_digest": agent_input_context[
            "ordered_input_delivery_units_digest"
        ],
        "ordered_input_delivery_unit_count": agent_input_context[
            "ordered_input_delivery_unit_count"
        ],
        "complete_ordered_input_consumed": True,
        "attempt_count": 1,
        "max_attempts": 1,
        "retry_count": 0,
        "terminal_delivery_verified": True,
        "durable_consumption_declared": True,
        "next_phase": (
            "DETERMINISTIC_COMPILE_AND_SEALED_ACTION_EVALUATION"
            if stage == "PROPOSAL"
            else "FINAL_PLAN_AND_OUTCOME_SCHEDULE_COMMIT"
        ),
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "account_access": False,
        "order_submission": False,
        "fill_claim": "NONE_NO_FILL_MODEL",
        "pnl_claim": "NONE_NO_PNL_MODEL",
        "executable": False,
        "claim": V32_LIFECYCLE_CLAIM,
        "limitations": list(_LIMITATIONS),
    }
    return self_digest(document, AGENT_CONSUMPTION_DIGEST_FIELD)


@_memoized_lifecycle_verifier("VERIFY_AGENT_CONSUMPTION_V1")
def verify_v32_agent_consumption_v1(document: Mapping[str, Any], *, agent_input_context: Mapping[str, Any], agent_delivery: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _CONSUMPTION_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_CONSUMPTION_INVALID")
    try:
        supplied = verify_self_digest(document, AGENT_CONSUMPTION_DIGEST_FIELD)
        rebuilt = build_v32_agent_consumption_v1(
            agent_input_context=agent_input_context,
            agent_input_context_binding=document["agent_input_context_binding"],
            agent_delivery=agent_delivery,
            agent_delivery_binding=document["agent_delivery_binding"],
            consumed_at=document["consumed_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_CONSUMPTION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[AGENT_CONSUMPTION_DIGEST_FIELD]:
        raise V32AgentLifecycleError("V32_AGENT_CONSUMPTION_RECONSTRUCTION_MISMATCH")
    return supplied


def _verify_stage_chain(
    *, stage: str, context: Mapping[str, Any], delivery: Mapping[str, Any], consumption: Mapping[str, Any]
) -> tuple[str, str, str]:
    context_digest = verify_v32_agent_input_context_descriptor_v1(context)
    delivery_digest = verify_v32_agent_delivery_v1(delivery, agent_input_context=context)
    consumption_digest = verify_v32_agent_consumption_v1(
        consumption, agent_input_context=context, agent_delivery=delivery
    )
    if context.get("agent_stage") != stage or delivery.get("agent_stage") != stage or consumption.get("agent_stage") != stage:
        raise V32AgentLifecycleError("V32_AGENT_COMMIT_STAGE_INVALID")
    return context_digest, delivery_digest, consumption_digest


def build_v32_two_stage_commit_envelope_v1(
    *,
    proposal_input_context: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_consumption: Mapping[str, Any],
    selection_input_context: Mapping[str, Any],
    selection_delivery: Mapping[str, Any],
    selection_consumption: Mapping[str, Any],
    final_dynamic_action_plan: Mapping[str, Any],
    final_dynamic_action_plan_binding: Mapping[str, Any],
    outcome_schedule_set: Mapping[str, Any],
    outcome_schedule_set_binding: Mapping[str, Any],
    sealed_at: str,
    previous_commit_envelope_digest: str | None,
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
    selection_lossless_context_package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    proposal_context_digest, proposal_delivery_digest, proposal_consumption_digest = _verify_stage_chain(
        stage="PROPOSAL", context=proposal_input_context, delivery=proposal_delivery, consumption=proposal_consumption
    )
    selection_context_digest, selection_delivery_digest, selection_consumption_digest = _verify_stage_chain(
        stage="SELECTION", context=selection_input_context, delivery=selection_delivery, consumption=selection_consumption
    )
    proposal_packet = resolve_v32_agent_canonical_packet_v1(
        proposal_input_context,
        lossless_context_package=proposal_lossless_context_package,
    )
    selection_packet = resolve_v32_agent_canonical_packet_v1(
        selection_input_context,
        lossless_context_package=selection_lossless_context_package,
    )
    if (
        selection_packet.get("proposal_input_context", {}).get(AGENT_INPUT_CONTEXT_DIGEST_FIELD) != proposal_context_digest
        or selection_packet.get("proposal_delivery", {}).get(AGENT_DELIVERY_DIGEST_FIELD) != proposal_delivery_digest
        or selection_packet.get("proposal_consumption", {}).get(AGENT_CONSUMPTION_DIGEST_FIELD) != proposal_consumption_digest
    ):
        raise V32AgentLifecycleError("V32_AGENT_COMMIT_STAGE_CHAIN_MISMATCH")
    compiled_state = selection_packet["compiled_dynamic_research_state"]
    compiled_digest = verify_v32_dynamic_research_state_v1(compiled_state)
    action_digest = verify_v32_dynamic_action_plan_v1(
        final_dynamic_action_plan, dynamic_research_state=compiled_state
    )
    action_binding = _embedded_binding(
        document=final_dynamic_action_plan,
        binding=final_dynamic_action_plan_binding,
        schema_id=ACTION_PLAN_SCHEMA_ID,
        digest_field=ACTION_PLAN_DIGEST_FIELD,
        semantic_digest=action_digest,
        code="V32_AGENT_COMMIT_FINAL_BINDING_INVALID",
    )
    schedule_digest = verify_v32_outcome_schedule_set(outcome_schedule_set)
    schedule_binding = _embedded_binding(
        document=outcome_schedule_set,
        binding=outcome_schedule_set_binding,
        schema_id=SCHEDULE_SET_SCHEMA_ID,
        digest_field=SCHEDULE_SET_DIGEST_FIELD,
        semantic_digest=schedule_digest,
        code="V32_AGENT_COMMIT_FINAL_BINDING_INVALID",
    )
    run = proposal_input_context["run_id"]
    cycle = proposal_input_context["cycle_index"]
    previous = _digest(previous_commit_envelope_digest, "V32_AGENT_COMMIT_PREVIOUS_INVALID", nullable=True)
    if (cycle == 1 and previous is not None) or (cycle > 1 and previous is None):
        raise V32AgentLifecycleError("V32_AGENT_COMMIT_PREVIOUS_INVALID")
    sealed = _time(sealed_at, "V32_AGENT_COMMIT_TIME_INVALID")
    schedule_decision = _time(
        outcome_schedule_set.get("decision_time"),
        "V32_AGENT_COMMIT_TIME_INVALID",
    )
    legacy_schedule_time = schedule_decision == proposal_packet["decision_time"]
    post_selection_schedule_time = (
        _moment(
            selection_consumption["consumed_at"],
            "V32_AGENT_COMMIT_TIME_INVALID",
        )
        <= _moment(schedule_decision, "V32_AGENT_COMMIT_TIME_INVALID")
        <= _moment(sealed, "V32_AGENT_COMMIT_TIME_INVALID")
    )
    if (
        selection_input_context.get("run_id") != run
        or selection_input_context.get("cycle_index") != cycle
        or final_dynamic_action_plan.get("run_id") != run
        or final_dynamic_action_plan.get("cycle_index") != cycle
        or outcome_schedule_set.get("run_id") != run
        or outcome_schedule_set.get("cycle_index") != cycle
        or not (legacy_schedule_time or post_selection_schedule_time)
        or outcome_schedule_set.get("sealed_decision_digest") != action_digest
        or outcome_schedule_set.get("evaluation_contract_digest")
        != proposal_input_context["evaluation_contract_digest"]
        or _moment(sealed, "V32_AGENT_COMMIT_TIME_INVALID") < _moment(selection_consumption["consumed_at"], "V32_AGENT_COMMIT_TIME_INVALID")
    ):
        raise V32AgentLifecycleError("V32_AGENT_COMMIT_CROSS_BINDING_INVALID")
    document = {
        "schema_id": COMMIT_ENVELOPE_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run,
        "cycle_index": cycle,
        "context_profile": proposal_input_context["context_profile"],
        "sealed_at": sealed,
        "proposal_input_context_digest": proposal_context_digest,
        "proposal_delivery_digest": proposal_delivery_digest,
        "proposal_consumption_digest": proposal_consumption_digest,
        "selection_input_context_digest": selection_context_digest,
        "selection_delivery_digest": selection_delivery_digest,
        "selection_consumption_digest": selection_consumption_digest,
        "compiled_dynamic_research_state_digest": compiled_digest,
        "final_dynamic_action_plan": dict(final_dynamic_action_plan),
        "final_dynamic_action_plan_binding": action_binding,
        "final_dynamic_action_plan_digest": action_digest,
        "outcome_schedule_set": dict(outcome_schedule_set),
        "outcome_schedule_set_binding": schedule_binding,
        "outcome_schedule_set_digest": schedule_digest,
        "previous_commit_envelope_digest": previous,
        "commit_status": "SEALED_NON_EXECUTABLE_RESEARCH_DECISION",
        "controller_write_once_required": True,
        "recovery_policy": "DETERMINISTIC_TAIL_ONLY_NO_SECOND_AGENT_NO_NETWORK",
        "chat_history_is_authority": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "account_access": False,
        "order_submission": False,
        "fill_claim": "NONE_NO_FILL_MODEL",
        "pnl_claim": "NONE_NO_PNL_MODEL",
        "executable": False,
        "claim": V32_LIFECYCLE_CLAIM,
        "limitations": list(_LIMITATIONS),
    }
    return self_digest(document, COMMIT_ENVELOPE_DIGEST_FIELD)


@_memoized_lifecycle_verifier("VERIFY_TWO_STAGE_COMMIT_ENVELOPE_V1")
def verify_v32_two_stage_commit_envelope_v1(
    document: Mapping[str, Any],
    *,
    proposal_input_context: Mapping[str, Any],
    proposal_delivery: Mapping[str, Any],
    proposal_consumption: Mapping[str, Any],
    selection_input_context: Mapping[str, Any],
    selection_delivery: Mapping[str, Any],
    selection_consumption: Mapping[str, Any],
    proposal_lossless_context_package: Mapping[str, Any] | None = None,
    selection_lossless_context_package: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _COMMIT_FIELDS:
        raise V32AgentLifecycleError("V32_AGENT_COMMIT_INVALID")
    try:
        supplied = verify_self_digest(document, COMMIT_ENVELOPE_DIGEST_FIELD)
        rebuilt = build_v32_two_stage_commit_envelope_v1(
            proposal_input_context=proposal_input_context,
            proposal_delivery=proposal_delivery,
            proposal_consumption=proposal_consumption,
            selection_input_context=selection_input_context,
            selection_delivery=selection_delivery,
            selection_consumption=selection_consumption,
            final_dynamic_action_plan=document["final_dynamic_action_plan"],
            final_dynamic_action_plan_binding=document["final_dynamic_action_plan_binding"],
            outcome_schedule_set=document["outcome_schedule_set"],
            outcome_schedule_set_binding=document["outcome_schedule_set_binding"],
            sealed_at=document["sealed_at"],
            previous_commit_envelope_digest=document["previous_commit_envelope_digest"],
            proposal_lossless_context_package=proposal_lossless_context_package,
            selection_lossless_context_package=selection_lossless_context_package,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentLifecycleError):
            raise
        raise V32AgentLifecycleError("V32_AGENT_COMMIT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[COMMIT_ENVELOPE_DIGEST_FIELD]:
        raise V32AgentLifecycleError("V32_AGENT_COMMIT_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "ACTION_EVALUATION_DIGEST_FIELD",
    "ACTION_EVALUATION_SCHEMA_ID",
    "AGENT_CONSUMPTION_DIGEST_FIELD",
    "AGENT_CONSUMPTION_SCHEMA_ID",
    "AGENT_DELIVERY_DIGEST_FIELD",
    "AGENT_DELIVERY_SCHEMA_ID",
    "AGENT_INPUT_CONTEXT_DIGEST_FIELD",
    "AGENT_INPUT_CONTEXT_SCHEMA_ID",
    "ASSOCIATION_PREREGISTRATION_DIGEST_FIELD",
    "ASSOCIATION_PREREGISTRATION_SCHEMA_ID",
    "COMMIT_ENVELOPE_DIGEST_FIELD",
    "COMMIT_ENVELOPE_SCHEMA_ID",
    "EVALUATION_CONTRACT_DIGEST_FIELD",
    "EVALUATION_CONTRACT_SCHEMA_ID",
    "GRAPH_REGISTRY_DIGEST_FIELD",
    "GRAPH_REGISTRY_SCHEMA_ID",
    "MAX_AGENT_DELIVERY_UTF8_BYTES",
    "MAX_AGENT_INPUT_CONTEXT_CANONICAL_BYTES",
    "MAX_PROPOSAL_CANONICAL_PACKET_BYTES",
    "MAX_SELECTION_CANONICAL_PACKET_BYTES",
    "PIT_REGISTRY_DIGEST_FIELD",
    "PIT_REGISTRY_SCHEMA_ID",
    "PROPOSAL_PACKET_DIGEST_FIELD",
    "PROPOSAL_PACKET_SCHEMA_ID",
    "PROPOSAL_SUPPORT_SPECS",
    "SELECTION_PACKET_DIGEST_FIELD",
    "SELECTION_PACKET_SCHEMA_ID",
    "SOURCE_ADMISSION_DIGEST_FIELD",
    "SOURCE_ADMISSION_SCHEMA_ID",
    "THEORY_DOCUMENT_DIGEST_FIELD",
    "THEORY_DOCUMENT_SCHEMA_ID",
    "V32_AGENT_CONTEXT_ROOT",
    "V32_AGENT_INPUT_DELIVERY_MODES",
    "V32_AGENT_STAGES",
    "V32_CURRENT_ROOT_AGENT_ID",
    "V32_LIFECYCLE_CLAIM",
    "V32_QUALIFICATION_CONTEXT_PROFILE",
    "V32_TARGET_CONTEXT_PROFILE",
    "V32AgentLifecycleError",
    "agent_commit_envelope_ref_v1",
    "agent_consumption_ref_v1",
    "agent_delivery_ref_v1",
    "agent_input_context_ref_v1",
    "build_v32_action_evaluation_v1",
    "build_v32_agent_consumption_v1",
    "build_v32_agent_delivery_v1",
    "build_v32_agent_input_context_v1",
    "build_v32_embedded_document_binding_v1",
    "build_v32_proposal_canonical_packet_v1",
    "build_v32_selection_canonical_packet_v1",
    "build_v32_theory_semantic_document_v1",
    "build_v32_two_stage_commit_envelope_v1",
    "verify_v32_action_evaluation_v1",
    "verify_v32_agent_consumption_v1",
    "verify_v32_agent_delivery_v1",
    "verify_v32_agent_input_context_v1",
    "verify_v32_agent_input_context_descriptor_v1",
    "resolve_v32_agent_canonical_packet_v1",
    "verify_v32_proposal_canonical_packet_v1",
    "verify_v32_selection_canonical_packet_v1",
    "verify_v32_theory_semantic_document_v1",
    "verify_v32_two_stage_commit_envelope_v1",
    "v32_lifecycle_verification_scope_v1",
]
