"""Recoverable, one-durable-boundary-per-wake V3.2 coordinator.

Opening a Supervisor permit, advancing one lane substage, and completing (or
failing) the Supervisor are deliberately separate durable boundaries.  This
allows the current root Codex Proposal and Selection stages to span multiple
wakes without treating an ordinary wait as failure or repeating an external
attempt.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Mapping, Protocol, Sequence

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    verify_self_digest,
)
from ..domain.v32_outcome_tick import build_v32_outcome_tick_attempt
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    V32TickSupervisorError,
    build_v32_analysis_tick_permit,
    build_v32_outcome_tick_permit,
    classify_v32_outcome_permit_mode,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_permit,
)
from ..domain.v32_outcome_window_expiry import EXPIRY_TERMINAL_DIGEST_FIELD
from ..domain.v32_shadow_evaluation import (
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    SHADOW_DECISION_BUNDLE_SCHEMA_ID,
)
from .v32_cycle_acceptance import (
    DIGEST_FIELD as ANALYSIS_ACCEPTANCE_DIGEST_FIELD,
    SCHEMA_ID as ANALYSIS_ACCEPTANCE_SCHEMA_ID,
)
from .v32_public_evidence_port import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    GRAPH_PROJECTION_DIGEST_FIELD,
    GRAPH_REGISTRY_DIGEST_FIELD,
)
from .v32_durable_source_replay import (
    RECEIPT_DIGEST_FIELD as SOURCE_REPLAY_DIGEST_FIELD,
    verify_v32_durable_source_replay_receipt,
)


class V32CycleCompositionError(ValueError):
    """The single-wake coordination boundary failed closed."""


class V32TickSupervisorStorePort(Protocol):
    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def load_checkpoint_by_digest(
        self, *, run_id: str, checkpoint_digest: str
    ) -> Mapping[str, Any]: ...

    def load_permit(
        self, *, run_id: str, permit_digest: str
    ) -> Mapping[str, Any]: ...

    def open_permit(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def complete_analysis_tick(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def complete_outcome_tick(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def fail_closed(self, **kwargs: Any) -> Mapping[str, Any]: ...


class V32AnalysisLanePort(Protocol):
    """Port whose implementation owns and fully verifies analysis evidence.

    ``verify_durable_analysis_completion`` must apply the concrete full public
    analysis, graph projection, graph registry, source replay, and acceptance
    verifiers before returning.  This coordinator then checks exact digest and
    cross-document bindings without depending on an Infrastructure module.
    """

    def load_durable_prepared_source(
        self,
        *,
        run_id: str,
        cycle_index: int,
        supervisor_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any] | None: ...

    def prepare_cycle_source(
        self,
        *,
        run_id: str,
        cycle_index: int,
        supervisor_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def advance_analysis(
        self,
        *,
        permit: Mapping[str, Any],
        supervisor_checkpoint_before_permit: Mapping[str, Any],
        supervisor_open_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Advance exactly one durable analysis substage and return its receipt."""
        ...

    def load_durable_analysis_completion(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None: ...

    def verify_durable_analysis_completion(
        self,
        *,
        permit: Mapping[str, Any],
        completion_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def load_durable_analysis_failure(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None: ...

    def verify_durable_analysis_failure(
        self,
        *,
        permit: Mapping[str, Any],
        failure_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class V32OutcomeLanePort(Protocol):
    """Port whose implementation owns raw-first public outcome durability."""

    def advance_outcome(
        self,
        *,
        permit: Mapping[str, Any],
        supervisor_checkpoint_before_permit: Mapping[str, Any],
        supervisor_open_checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Advance exactly one durable outcome substage and return its receipt."""
        ...

    def load_durable_outcome_completion(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None: ...

    def verify_durable_outcome_completion(
        self,
        *,
        permit: Mapping[str, Any],
        completion_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def load_durable_outcome_failure(
        self, *, permit: Mapping[str, Any]
    ) -> Mapping[str, Any] | None: ...

    def verify_durable_outcome_failure(
        self,
        *,
        permit: Mapping[str, Any],
        failure_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


_ANALYSIS_REQUEST_FIELDS = frozenset(
    {"lane", "analysis_decision_at", "issued_at"}
)
_OUTCOME_REQUEST_FIELDS = frozenset(
    {"lane", "planned_tick_at", "requested_at"}
)
_ANALYSIS_ENVELOPE_FIELDS = frozenset(
    {
        "permit_digest",
        "analysis_acceptance_digest",
        "shadow_decision_bundle_digest",
        "durable_source_replay_receipt_digest",
        "public_market_analysis_bundle_digest",
        "public_market_graph_projection_digest",
        "graph_delta_digest",
        "graph_dependency_registry_digest",
        "public_market_analysis_bundle",
        "public_market_graph_projection",
        "previous_public_market_graph_projection",
        "graph_dependency_registry",
        "durable_source_replay_receipt",
        "analysis_acceptance",
        "shadow_decision_bundle",
        "completion",
    }
)
_OUTCOME_ENVELOPE_FIELDS = frozenset(
    {"permit_digest", "batch_completion_digest", "completion"}
)
_ADVANCE_RESULT_FIELDS = frozenset(
    {"advance_status", "durable_transition_digest"}
)
_ADVANCE_STATUSES = frozenset(
    {"PENDING", "COMPLETION_SEALED", "FAILURE_SEALED"}
)
_LEGACY_FAILURE_ENVELOPE_FIELDS = frozenset(
    {
        "permit_digest",
        "failure_summary",
        "failure_evidence_digest",
        "occurred_at",
    }
)
_TYPED_FAILURE_ENVELOPE_FIELDS = frozenset(
    {*_LEGACY_FAILURE_ENVELOPE_FIELDS, "failure_code"}
)


def _request(lane_requests: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if (
        isinstance(lane_requests, (str, bytes))
        or not isinstance(lane_requests, Sequence)
        or len(lane_requests) != 1
        or not isinstance(lane_requests[0], Mapping)
    ):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_EXACTLY_ONE_LANE_REQUIRED"
        )
    request = lane_requests[0]
    lane = request.get("lane")
    expected = (
        _ANALYSIS_REQUEST_FIELDS
        if lane == "ANALYSIS"
        else _OUTCOME_REQUEST_FIELDS
        if lane == "OUTCOME"
        else frozenset()
    )
    if set(request) != expected:
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_LANE_REQUEST_INVALID"
        )
    return request


def _build_permit(
    *,
    checkpoint: Mapping[str, Any],
    request: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    try:
        if request["lane"] == "ANALYSIS":
            return build_v32_analysis_tick_permit(
                checkpoint=checkpoint,
                schedule_sets=schedule_sets,
                analysis_decision_at=request["analysis_decision_at"],
                issued_at=request["issued_at"],
                research_checkpoint_digest=checkpoint[
                    "current_research_checkpoint_digest"
                ],
                outcome_checkpoint_digest=checkpoint[
                    "current_outcome_checkpoint_digest"
                ],
                timeframe_cache_digest=checkpoint[
                    "current_timeframe_cache_digest"
                ],
                prior_dynamic_state_digest=checkpoint[
                    "current_dynamic_state_digest"
                ],
            )
        mode = classify_v32_outcome_permit_mode(
            checkpoint=checkpoint,
            schedule_sets=schedule_sets,
            issued_at=request["requested_at"],
        )
        if mode == "OUTCOME_WINDOW_EXPIRY":
            return build_v32_outcome_tick_permit(
                checkpoint=checkpoint,
                schedule_sets=schedule_sets,
                tick_attempt=None,
                issued_at=request["requested_at"],
            )
        attempt = build_v32_outcome_tick_attempt(
            run_id=checkpoint["run_id"],
            tick_index=checkpoint["next_outcome_tick_index"],
            planned_tick_at=request["planned_tick_at"],
            reserved_at=request["requested_at"],
        )
        return build_v32_outcome_tick_permit(
            checkpoint=checkpoint,
            schedule_sets=schedule_sets,
            tick_attempt=attempt,
            issued_at=request["requested_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_PERMIT_BUILD_INVALID"
        ) from exc


def _request_matches_permit(
    request: Mapping[str, Any], permit: Mapping[str, Any]
) -> bool:
    if request["lane"] == "ANALYSIS":
        return (
            permit.get("permit_kind") == "ANALYSIS_TICK"
            and permit.get("analysis_decision_at")
            == request["analysis_decision_at"]
            and permit.get("issued_at") == request["issued_at"]
        )
    kind = permit.get("permit_kind")
    if kind == "OUTCOME_WINDOW_EXPIRY":
        return (
            permit.get("issued_at") == request["requested_at"]
        )
    return (
        kind == "OUTCOME_TICK"
        and permit.get("planned_outcome_tick_at") == request["planned_tick_at"]
        and permit.get("issued_at") == request["requested_at"]
    )


def _intrinsic_completion(
    *,
    permit: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> Mapping[str, Any]:
    kind = permit["permit_kind"]
    expected = (
        _ANALYSIS_ENVELOPE_FIELDS
        if kind == "ANALYSIS_TICK"
        else _OUTCOME_ENVELOPE_FIELDS
    )
    if not isinstance(envelope, Mapping) or set(envelope) != expected:
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_COMPLETION_ENVELOPE_INVALID"
        )
    if envelope.get("permit_digest") != permit[PERMIT_DIGEST_FIELD]:
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_COMPLETION_PERMIT_MISMATCH"
        )
    completion = envelope.get("completion")
    if not isinstance(completion, Mapping):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_COMPLETION_MATERIAL_INVALID"
        )
    if kind == "ANALYSIS_TICK":
        bundle = envelope.get("public_market_analysis_bundle")
        projection = envelope.get("public_market_graph_projection")
        previous_projection = envelope.get("previous_public_market_graph_projection")
        registry = envelope.get("graph_dependency_registry")
        source_replay = envelope.get("durable_source_replay_receipt")
        acceptance = envelope.get("analysis_acceptance")
        shadow_decision = envelope.get("shadow_decision_bundle")
        try:
            bundle_digest = verify_self_digest(
                bundle, ANALYSIS_BUNDLE_DIGEST_FIELD
            )
            projection_digest = verify_self_digest(
                projection, GRAPH_PROJECTION_DIGEST_FIELD
            )
            registry_digest = verify_self_digest(
                registry, GRAPH_REGISTRY_DIGEST_FIELD
            )
            source_replay_digest = verify_v32_durable_source_replay_receipt(
                source_replay
            )
            acceptance_digest = verify_self_digest(
                acceptance, ANALYSIS_ACCEPTANCE_DIGEST_FIELD
            )
            shadow_decision_digest = verify_self_digest(
                shadow_decision, SHADOW_DECISION_BUNDLE_DIGEST_FIELD
            )
        except (TypeError, ValueError) as exc:
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_PUBLIC_GRAPH_REPLAY_INVALID"
            ) from exc
        bundle_binding = source_replay.get("market_analysis_bundle_binding", {})
        bundle_physical = hashlib.sha256(
            canonical_bytes(dict(bundle)) + b"\n"
        ).hexdigest()
        shadow_physical = hashlib.sha256(
            canonical_bytes(dict(shadow_decision)) + b"\n"
        ).hexdigest()
        shadow_binding = acceptance.get("component_bindings", {}).get(
            "replayable_shadow_decision_bundle", {}
        )
        if (
            envelope.get("analysis_acceptance_digest")
            != completion.get("accepted_state_digest")
            or envelope.get("analysis_acceptance_digest") != acceptance_digest
            or acceptance.get("schema_id") != ANALYSIS_ACCEPTANCE_SCHEMA_ID
            or acceptance.get("run_id") != permit.get("run_id")
            or acceptance.get("cycle_index")
            != permit.get("analysis_cycle_index")
            or envelope.get("shadow_decision_bundle_digest")
            != shadow_decision_digest
            or completion.get("shadow_decision_bundle_digest")
            != shadow_decision_digest
            or acceptance.get("shadow_decision_bundle_digest")
            != shadow_decision_digest
            or shadow_binding.get("schema_id")
            != SHADOW_DECISION_BUNDLE_SCHEMA_ID
            or shadow_binding.get("digest_field")
            != SHADOW_DECISION_BUNDLE_DIGEST_FIELD
            or shadow_binding.get("semantic_digest")
            != shadow_decision_digest
            or shadow_binding.get("physical_sha256") != shadow_physical
            or shadow_decision.get("schema_id")
            != SHADOW_DECISION_BUNDLE_SCHEMA_ID
            or shadow_decision.get("run_id") != permit.get("run_id")
            or shadow_decision.get("cycle_index")
            != permit.get("analysis_cycle_index")
            or shadow_decision.get("outcome_values_present") is not False
            or shadow_decision.get("source_scope")
            != "PUBLIC_NON_ACCOUNT_ONLY"
            or shadow_decision.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or shadow_decision.get("executable") is not False
            or envelope.get("public_market_analysis_bundle_digest")
            != bundle_digest
            or envelope.get("public_market_graph_projection_digest")
            != projection_digest
            or envelope.get("graph_delta_digest")
            != projection.get("graph_delta_digest")
            or envelope.get("graph_dependency_registry_digest")
            != registry_digest
            or envelope.get("durable_source_replay_receipt_digest")
            != source_replay_digest
            or bundle_binding.get("semantic_digest") != bundle_digest
            or bundle_binding.get("physical_sha256") != bundle_physical
            or projection.get("cycle_index")
            != permit.get("analysis_cycle_index")
            or registry.get("cycle_index") != permit.get("analysis_cycle_index")
            or source_replay.get("cycle_index")
            != permit.get("analysis_cycle_index")
            or (
                permit.get("analysis_cycle_index") == 1
                and previous_projection is not None
            )
            or (
                permit.get("analysis_cycle_index", 0) > 1
                and previous_projection is None
            )
        ):
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_ANALYSIS_BINDING_INVALID"
            )
    elif kind == "OUTCOME_WINDOW_EXPIRY":
        if envelope.get("batch_completion_digest") != completion.get(
            "expiry_terminal", {}
        ).get(EXPIRY_TERMINAL_DIGEST_FIELD):
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_EXPIRY_BINDING_INVALID"
            )
    elif envelope.get("batch_completion_digest") != completion.get(
        "batch_completion", {}
    ).get("outcome_resolution_batch_digest"):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_OUTCOME_BINDING_INVALID"
        )
    return completion


def _verified_advance_result(result: Mapping[str, Any]) -> Mapping[str, Any]:
    if (
        not isinstance(result, Mapping)
        or set(result) != _ADVANCE_RESULT_FIELDS
        or result.get("advance_status") not in _ADVANCE_STATUSES
    ):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_LANE_ADVANCE_RESULT_INVALID"
        )
    digest = result.get("durable_transition_digest")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_LANE_ADVANCE_RESULT_INVALID"
        )
    return deepcopy(result)


def _intrinsic_failure(
    *, permit: Mapping[str, Any], envelope: Mapping[str, Any]
) -> Mapping[str, Any]:
    if (
        not isinstance(envelope, Mapping)
        or set(envelope)
        not in {_LEGACY_FAILURE_ENVELOPE_FIELDS, _TYPED_FAILURE_ENVELOPE_FIELDS}
    ):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_FAILURE_ENVELOPE_INVALID"
        )
    evidence_digest = envelope.get("failure_evidence_digest")
    failure_code = envelope.get("failure_code")
    if (
        envelope.get("permit_digest") != permit.get(PERMIT_DIGEST_FIELD)
        or not isinstance(envelope.get("failure_summary"), str)
        or not envelope["failure_summary"]
        or envelope["failure_summary"] != envelope["failure_summary"].strip()
        or not isinstance(evidence_digest, str)
        or len(evidence_digest) != 64
        or any(character not in "0123456789abcdef" for character in evidence_digest)
        or not isinstance(envelope.get("occurred_at"), str)
        or not envelope["occurred_at"]
        or (
            failure_code is not None
            and failure_code
            not in {"COMMIT_STATE_CONFLICT", "SOURCE_STALE_AFTER_AGENT"}
        )
    ):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_FAILURE_ENVELOPE_INVALID"
        )
    return deepcopy(envelope)


def _failure_time(request: Mapping[str, Any]) -> str:
    return str(
        request[
            "issued_at" if request["lane"] == "ANALYSIS" else "requested_at"
        ]
    )


def _fail_open_boundary(
    *,
    supervisor_store: V32TickSupervisorStorePort,
    checkpoint: Mapping[str, Any],
    request: Mapping[str, Any],
    error: Exception,
    occurred_at: str | None = None,
    failure_summary: str | None = None,
    failure_evidence_digest: str | None = None,
    failure_code: str | None = None,
) -> None:
    lane = request["lane"]
    if failure_code == "SOURCE_STALE_AFTER_AGENT":
        if lane != "ANALYSIS":
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_FAILURE_CODE_INVALID"
            )
        failure_lane = "SOURCE_LANE"
        owning_failure_code = "SOURCE_STALE_AFTER_AGENT"
    else:
        failure_lane = "COMMIT_LANE" if lane == "ANALYSIS" else "OUTCOME_LANE"
        owning_failure_code = (
            "COMMIT_STATE_CONFLICT"
            if lane == "ANALYSIS"
            else "OUTCOME_SCHEMA_OR_DIGEST_INVALID"
        )
    evidence = failure_evidence_digest or canonical_digest(
        {
            "schema_id": "theory_paper_v32_cycle_composition_failure_evidence_v1",
            "run_id": checkpoint["run_id"],
            "active_permit_digest": checkpoint["active_permit_digest"],
            "failure_class": type(error).__name__,
            "failure_message": str(error),
        }
    )
    supervisor_store.fail_closed(
        expected_checkpoint_digest=checkpoint[CHECKPOINT_DIGEST_FIELD],
        failure_lane=failure_lane,
        failure_code=owning_failure_code,
        failure_summary=failure_summary or (
            "single-boundary substore did not provide one exact durable terminal state"
        ),
        failure_evidence_digest=evidence,
        occurred_at=occurred_at or _failure_time(request),
    )


def _wake_result(
    *,
    run_id: str,
    lane: str,
    permit: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    runtime_status: str,
    boundary_kind: str,
    recovery_mode: str,
    lane_advance_status: str | None = None,
    durable_transition_digest: str | None = None,
) -> Mapping[str, Any]:
    return {
        "run_id": run_id,
        "opened_lane": lane,
        "runtime_status": runtime_status,
        "boundary_kind": boundary_kind,
        "recovery_mode": recovery_mode,
        "boundaries_completed_this_wake": 1,
        "durable_state_boundaries_this_wake": 1,
        "supervisor_boundary_completed_this_wake": runtime_status
        in {"COMPLETED", "FAILED_CLOSED"},
        "analysis_and_outcome_both_advanced": False,
        "lane_advance_status": lane_advance_status,
        "durable_transition_digest": durable_transition_digest,
        "permit_digest": permit[PERMIT_DIGEST_FIELD],
        "supervisor_checkpoint_digest": checkpoint[CHECKPOINT_DIGEST_FIELD],
        "supervisor_status": checkpoint["status"],
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def run_v32_single_boundary_wake(
    *,
    supervisor_store: V32TickSupervisorStorePort,
    run_id: str,
    lane_requests: Sequence[Mapping[str, Any]],
    schedule_sets: Sequence[Mapping[str, Any]],
    analysis_port: V32AnalysisLanePort | None = None,
    outcome_port: V32OutcomeLanePort | None = None,
) -> Mapping[str, Any]:
    """Advance exactly one durable boundary and never fail ordinary PENDING.

    A fresh wake opens the permit only.  A later wake either closes an already
    durable terminal lane state, or invokes exactly one lane ``advance_*``
    method.  Even when that method seals completion or failure, the Supervisor
    transition is intentionally deferred until the following wake.
    """

    request = _request(lane_requests)
    lane = request["lane"]
    if (lane == "ANALYSIS" and analysis_port is None) or (
        lane == "OUTCOME" and outcome_port is None
    ):
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_LANE_PORT_REQUIRED"
        )
    try:
        current = supervisor_store.load_checkpoint(run_id=run_id)
        verify_v32_tick_supervisor_checkpoint(current)
    except (TypeError, ValueError) as exc:
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_SUPERVISOR_INVALID"
        ) from exc
    if current.get("run_id") != run_id or current.get("status") in {
        "TERMINAL_COMPLETE",
        "FAILED_CLOSED",
    }:
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_SUPERVISOR_NOT_RUNNABLE"
        )

    recovered = current.get("active_permit_digest") is not None
    if recovered:
        try:
            permit = supervisor_store.load_permit(
                run_id=run_id,
                permit_digest=current["active_permit_digest"],
            )
            before = supervisor_store.load_checkpoint_by_digest(
                run_id=run_id,
                checkpoint_digest=permit[
                    "supervisor_checkpoint_digest_before_permit"
                ],
            )
            tick_attempt = None
            if permit.get("permit_kind") == "OUTCOME_TICK":
                tick_attempt = build_v32_outcome_tick_attempt(
                    run_id=run_id,
                    tick_index=permit["outcome_tick_index"],
                    planned_tick_at=permit["planned_outcome_tick_at"],
                    reserved_at=permit["issued_at"],
                )
            verify_v32_tick_supervisor_permit(
                permit,
                checkpoint=before,
                schedule_sets=schedule_sets,
                tick_attempt=tick_attempt,
            )
        except (KeyError, TypeError, ValueError) as exc:
            _fail_open_boundary(
                supervisor_store=supervisor_store,
                checkpoint=current,
                request=request,
                error=exc,
                failure_summary=(
                    "active supervisor permit or its predecessor failed "
                    "durable integrity verification"
                ),
            )
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_ACTIVE_PERMIT_INVALID_FAILED_CLOSED"
            ) from exc
        if not _request_matches_permit(request, permit):
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_DUAL_LANE_OR_WAKE_MISMATCH"
            )
        opened = current
    else:
        before = current
        permit = _build_permit(
            checkpoint=before, request=request, schedule_sets=schedule_sets
        )
        opened = supervisor_store.open_permit(
            permit=permit,
            schedule_sets=schedule_sets,
            expected_checkpoint_digest=before[CHECKPOINT_DIGEST_FIELD],
            opened_at=_failure_time(request),
        )
        return _wake_result(
            run_id=run_id,
            lane=lane,
            permit=permit,
            checkpoint=opened,
            runtime_status="PENDING",
            boundary_kind="SUPERVISOR_PERMIT_OPENED",
            recovery_mode="NORMAL_PERMIT_OPEN",
        )

    sealed_permit = deepcopy(permit)
    assert recovered
    try:
        if lane == "ANALYSIS":
            assert analysis_port is not None
            completion_envelope = analysis_port.load_durable_analysis_completion(
                permit=deepcopy(sealed_permit)
            )
            failure_envelope = analysis_port.load_durable_analysis_failure(
                permit=deepcopy(sealed_permit)
            )
        else:
            assert outcome_port is not None
            completion_envelope = outcome_port.load_durable_outcome_completion(
                permit=deepcopy(sealed_permit)
            )
            failure_envelope = outcome_port.load_durable_outcome_failure(
                permit=deepcopy(sealed_permit)
            )
    except Exception as exc:
        _fail_open_boundary(
            supervisor_store=supervisor_store,
            checkpoint=opened,
            request=request,
            error=exc,
        )
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_DURABLE_TERMINAL_LOAD_FAILED_CLOSED"
        ) from exc

    if completion_envelope is not None and failure_envelope is not None:
        error = V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_DUAL_DURABLE_TERMINAL_STATE"
        )
        _fail_open_boundary(
            supervisor_store=supervisor_store,
            checkpoint=opened,
            request=request,
            error=error,
        )
        raise error

    if completion_envelope is not None:
        try:
            if lane == "ANALYSIS":
                assert analysis_port is not None
                verified_envelope = (
                    analysis_port.verify_durable_analysis_completion(
                        permit=deepcopy(sealed_permit),
                        completion_envelope=deepcopy(completion_envelope),
                    )
                )
            else:
                assert outcome_port is not None
                verified_envelope = outcome_port.verify_durable_outcome_completion(
                    permit=deepcopy(sealed_permit),
                    completion_envelope=deepcopy(completion_envelope),
                )
            completion = _intrinsic_completion(
                permit=sealed_permit, envelope=verified_envelope
            )
            if lane == "ANALYSIS":
                final = supervisor_store.complete_analysis_tick(
                    permit=sealed_permit,
                    completion=completion,
                    expected_checkpoint_digest=opened[CHECKPOINT_DIGEST_FIELD],
                )
            else:
                final = supervisor_store.complete_outcome_tick(
                    permit=sealed_permit,
                    completion=completion,
                    expected_checkpoint_digest=opened[CHECKPOINT_DIGEST_FIELD],
                )
        except Exception as exc:
            _fail_open_boundary(
                supervisor_store=supervisor_store,
                checkpoint=opened,
                request=request,
                error=exc,
            )
            if isinstance(exc, V32CycleCompositionError):
                raise
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_COMPLETION_FAILED_CLOSED"
            ) from exc
        return _wake_result(
            run_id=run_id,
            lane=lane,
            permit=sealed_permit,
            checkpoint=final,
            runtime_status="COMPLETED",
            boundary_kind=f"SUPERVISOR_{lane}_COMPLETED",
            recovery_mode="DURABLE_SUBSTORE_COMPLETION_RECOVERY",
        )

    if failure_envelope is not None:
        try:
            if lane == "ANALYSIS":
                assert analysis_port is not None
                verified_failure = analysis_port.verify_durable_analysis_failure(
                    permit=deepcopy(sealed_permit),
                    failure_envelope=deepcopy(failure_envelope),
                )
            else:
                assert outcome_port is not None
                verified_failure = outcome_port.verify_durable_outcome_failure(
                    permit=deepcopy(sealed_permit),
                    failure_envelope=deepcopy(failure_envelope),
                )
            failure = _intrinsic_failure(
                permit=sealed_permit, envelope=verified_failure
            )
            _fail_open_boundary(
                supervisor_store=supervisor_store,
                checkpoint=opened,
                request=request,
                error=V32CycleCompositionError(failure["failure_summary"]),
                occurred_at=failure["occurred_at"],
                failure_summary=failure["failure_summary"],
                failure_evidence_digest=failure["failure_evidence_digest"],
                failure_code=failure.get("failure_code"),
            )
            final = supervisor_store.load_checkpoint(run_id=run_id)
            verify_v32_tick_supervisor_checkpoint(final)
        except Exception as exc:
            latest = supervisor_store.load_checkpoint(run_id=run_id)
            if latest.get("status") != "FAILED_CLOSED":
                _fail_open_boundary(
                    supervisor_store=supervisor_store,
                    checkpoint=opened,
                    request=request,
                    error=exc,
                )
            if isinstance(exc, V32CycleCompositionError):
                raise
            raise V32CycleCompositionError(
                "V32_CYCLE_COMPOSITION_FAILURE_FAILED_CLOSED"
            ) from exc
        return _wake_result(
            run_id=run_id,
            lane=lane,
            permit=sealed_permit,
            checkpoint=final,
            runtime_status="FAILED_CLOSED",
            boundary_kind=f"SUPERVISOR_{lane}_FAILED_CLOSED",
            recovery_mode="DURABLE_SUBSTORE_FAILURE_RECOVERY",
        )

    # A lane advance is the sole durable boundary of this wake.  Never mutate
    # the Supervisor after invoking it, even if it sealed a terminal substate or
    # raised after a durable write.  The next wake owns that Supervisor tail.
    try:
        if lane == "ANALYSIS":
            assert analysis_port is not None
            raw_advance = analysis_port.advance_analysis(
                permit=deepcopy(sealed_permit),
                supervisor_checkpoint_before_permit=deepcopy(before),
                supervisor_open_checkpoint=deepcopy(opened),
            )
        else:
            assert outcome_port is not None
            raw_advance = outcome_port.advance_outcome(
                permit=deepcopy(sealed_permit),
                supervisor_checkpoint_before_permit=deepcopy(before),
                supervisor_open_checkpoint=deepcopy(opened),
            )
        advance = _verified_advance_result(raw_advance)
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        if not isinstance(exc, Exception):
            raise
        raise V32CycleCompositionError(
            "V32_CYCLE_COMPOSITION_LANE_ADVANCE_INTERRUPTED_PENDING_RECOVERY"
        ) from exc

    return _wake_result(
        run_id=run_id,
        lane=lane,
        permit=sealed_permit,
        checkpoint=opened,
        runtime_status="PENDING",
        boundary_kind=f"{lane}_SUBSTAGE_ADVANCED",
        recovery_mode="ACTIVE_PERMIT_RESUME",
        lane_advance_status=str(advance["advance_status"]),
        durable_transition_digest=str(advance["durable_transition_digest"]),
    )


__all__ = [
    "V32AnalysisLanePort",
    "V32CycleCompositionError",
    "V32OutcomeLanePort",
    "V32TickSupervisorStorePort",
    "run_v32_single_boundary_wake",
]
