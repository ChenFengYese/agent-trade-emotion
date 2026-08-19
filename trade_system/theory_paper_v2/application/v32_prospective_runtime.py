"""Production V3.2 prospective-run genesis and deterministic wake routing.

This module is deliberately an orchestration boundary, not a market or Agent
adapter.  It has no network, account, credential, order, fill, portfolio, or
execution capability.  A fresh wake chooses one high-level boundary in this
order (after non-preemptible active-permit recovery): due outcome, post-cycle
audit, analysis, or ``NOT_DUE``.

An active analysis permit uses a bounded burst of the existing append-only
analysis substages.  The permit-open and Supervisor-close transitions remain
separate wakes.  The burst stops at a current-root Codex mailbox request, a
sealed lane terminal, the fixed step bound, or the frozen outcome deadline.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..domain.contracts.canonical import canonical_digest, verify_self_digest
from ..domain.v32_cycle_audit_narrative import (
    verify_v32_cycle_audit_policy_v1,
)
from ..domain.v32_current_root_agent_mailbox import (
    build_v32_current_codex_presentation_envelope_v1,
)
from ..domain.v32_outcome_tick import (
    build_v32_outcome_tick_attempt,
    verify_v32_outcome_schedule_set,
)
from ..domain.v32_cycle_source_admission import MAX_SOURCE_AGE_SECONDS
from ..domain.v32_runtime_support_contracts import (
    ANALYSIS_INTERVAL_SECONDS,
    EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS,
    MAX_ANALYSIS_SUBSTAGES_PER_WAKE,
    TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS,
)
from ..domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD,
    PERMIT_DIGEST_FIELD,
    build_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_checkpoint,
    verify_v32_tick_supervisor_permit,
    verify_v32_tick_supervisor_transition,
)
from .v32_cycle_audit_completion import (
    verify_v32_cycle_audit_completion_receipt_v1,
    verify_v32_latest_cycle_audit_gate_v1,
)
from .v32_cycle_composition import run_v32_single_boundary_wake


MAX_ANALYSIS_BURST_STEPS = MAX_ANALYSIS_SUBSTAGES_PER_WAKE
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_PUBLIC_BINDING_FIELDS = (
    "relative_ref",
    "schema_id",
    "digest_field",
    "semantic_digest",
    "physical_sha256",
)
_OUTCOME_HORIZON_ORDER = {"15M": 0, "1H": 1, "4H": 2}


class V32ProspectiveRuntimeError(ValueError):
    """The V3.2 production router could not choose one safe next boundary."""


class V32ProspectiveDynamicStorePort(Protocol):
    def initialize_checkpoint(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def replay_cycle_acceptance(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any]: ...

    def load_artifact(self, binding: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def mark_terminal(self, **kwargs: Any) -> Mapping[str, Any]: ...


class V32ProspectiveOutcomeStorePort(Protocol):
    def initialize_checkpoint(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def load_schedule_sets(self, *, run_id: str) -> list[Mapping[str, Any]]: ...

    def load_terminal_receipt_materials(
        self, *, run_id: str
    ) -> list[Mapping[str, Any]]: ...


class V32ProspectiveSupervisorStorePort(Protocol):
    def initialize_checkpoint(
        self, *, checkpoint: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def load_checkpoint_by_digest(
        self, *, run_id: str, checkpoint_digest: str
    ) -> Mapping[str, Any]: ...

    def load_permit(
        self, *, run_id: str, permit_digest: str
    ) -> Mapping[str, Any]: ...

    def fail_closed(self, **kwargs: Any) -> Mapping[str, Any]: ...


class V32ProspectiveMailboxPort(Protocol):
    def next_pending_request(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any] | None: ...

    def load_checkpoint(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any]: ...

    def load_stage_chain(
        self, *, run_id: str, cycle_index: int, stage: str
    ) -> Mapping[str, Any]: ...


class V32ProspectiveAuditRevisionPort(Protocol):
    def load_audit_bundle(
        self, *, run_id: str, cycle_index: int, boundary_type: str
    ) -> Mapping[str, Any] | None: ...


class V32ProspectiveAuditCompletionPort(Protocol):
    def load_completion(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any] | None: ...


class V32ProspectiveAuditLanePort(Protocol):
    def advance_once(self, **kwargs: Any) -> Mapping[str, Any]: ...


class V32ReadOnlySupervisorAlertPort(Protocol):
    def load_alert_status(self, *, run_id: str) -> Mapping[str, Any] | None: ...


class V32SupervisionEvidencePort(Protocol):
    def load_material_bindings(self, *, run_id: str) -> Mapping[str, Any]: ...

    def load_recovery_audit_materials(
        self, *, run_id: str
    ) -> list[Mapping[str, Any]]: ...


class V32TerminalSealPort(Protocol):
    def load_terminal_pointer(self, *, run_id: str) -> Mapping[str, Any] | None: ...

    def seal_terminal(self, **kwargs: Any) -> Mapping[str, Any]: ...


Clock = Callable[[], str]
WakeRunner = Callable[..., Mapping[str, Any]]


def _time(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ProspectiveRuntimeError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ProspectiveRuntimeError(code) from exc
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if parsed.tzinfo is None or canonical != value:
        raise V32ProspectiveRuntimeError(code)
    return value


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00"))


def _digest(value: Any, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise V32ProspectiveRuntimeError(code)
    return value


def _clock_time(clock: Clock) -> str:
    if not callable(clock):
        raise V32ProspectiveRuntimeError("V32_RUNTIME_CLOCK_INVALID")
    try:
        value = clock()
    except Exception as exc:
        raise V32ProspectiveRuntimeError("V32_RUNTIME_CLOCK_FAILED") from exc
    return _time(value, "V32_RUNTIME_CLOCK_INVALID")


def _monotonic_ns(clock: Clock) -> int | None:
    reader = getattr(clock, "monotonic_ns", None)
    if reader is None:
        return None
    if not callable(reader):
        raise V32ProspectiveRuntimeError("V32_RUNTIME_MONOTONIC_CLOCK_INVALID")
    try:
        value = reader()
    except Exception as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_MONOTONIC_CLOCK_FAILED"
        ) from exc
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise V32ProspectiveRuntimeError("V32_RUNTIME_MONOTONIC_CLOCK_INVALID")
    return value


def _elapsed_monotonic_ms(clock: Clock, started_ns: int | None) -> int | None:
    if started_ns is None:
        return None
    ended_ns = _monotonic_ns(clock)
    if ended_ns is None or ended_ns < started_ns:
        raise V32ProspectiveRuntimeError("V32_RUNTIME_MONOTONIC_CLOCK_ROLLBACK")
    return (ended_ns - started_ns) // 1_000_000


def _base_result(*, run_id: str, status: str, now: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "runtime_status": status,
        "observed_at": now,
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "account_access": False,
        "order_submission": False,
        "router_has_direct_network_capability": False,
        "lane_owned_network_activity_not_inferred": True,
        "agent_output_generated_by_router": False,
    }


def _with_alert(
    result: Mapping[str, Any],
    *,
    run_id: str,
    alert_port: V32ReadOnlySupervisorAlertPort | None,
) -> Mapping[str, Any]:
    wrapped = deepcopy(dict(result))
    if alert_port is None:
        wrapped["supervisor_alert_status"] = None
    else:
        try:
            alert = alert_port.load_alert_status(run_id=run_id)
            wrapped["supervisor_alert_status"] = (
                None if alert is None else deepcopy(dict(alert))
            )
        except Exception as exc:
            wrapped["supervisor_alert_status"] = {
                "status": "READ_ONLY_ALERT_UNAVAILABLE",
                "error_class": type(exc).__name__,
            }
    wrapped["supervisor_alert_state_mutations"] = 0
    return wrapped


def initialize_v32_prospective_runtime_v1(
    *,
    dynamic_store: V32ProspectiveDynamicStorePort,
    outcome_store: V32ProspectiveOutcomeStorePort,
    supervisor_store: V32ProspectiveSupervisorStorePort,
    run_id: str,
    experiment_contract_digest: str,
    active_authority_digest: str,
    initial_timeframe_cache_digest: str,
    cycle_audit_policy: Mapping[str, Any],
    created_at: str,
) -> Mapping[str, Any]:
    """Create or replay the three idempotent runtime genesis checkpoints.

    The mailbox remains cycle-scoped and is initialized by the existing
    analysis lane immediately before its first request.  Audit stores are
    append-only and intentionally have no empty mutable genesis document.
    """

    created = _time(created_at, "V32_RUNTIME_GENESIS_TIME_INVALID")
    contract_digest = _digest(
        experiment_contract_digest, "V32_RUNTIME_CONTRACT_DIGEST_INVALID"
    )
    authority_digest = _digest(
        active_authority_digest, "V32_RUNTIME_AUTHORITY_DIGEST_INVALID"
    )
    timeframe_digest = _digest(
        initial_timeframe_cache_digest,
        "V32_RUNTIME_TIMEFRAME_DIGEST_INVALID",
    )
    try:
        audit_policy_digest = verify_v32_cycle_audit_policy_v1(
            cycle_audit_policy
        )
    except (TypeError, ValueError) as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_AUDIT_POLICY_INVALID"
        ) from exc
    if cycle_audit_policy.get("run_scope_id") != run_id:
        raise V32ProspectiveRuntimeError("V32_RUNTIME_AUDIT_SCOPE_INVALID")

    try:
        dynamic = dynamic_store.initialize_checkpoint(
            run_id=run_id,
            experiment_contract_digest=contract_digest,
            active_authority_digest=authority_digest,
            created_at=created,
        )
        research_digest = verify_self_digest(
            dynamic, "dynamic_research_checkpoint_digest"
        )
        outcome = outcome_store.initialize_checkpoint(
            run_id=run_id, created_at=created
        )
        outcome_digest = verify_self_digest(outcome, "checkpoint_digest")
        candidate = build_v32_tick_supervisor_checkpoint(
            run_id=run_id,
            experiment_contract_digest=contract_digest,
            active_authority_digest=authority_digest,
            research_checkpoint_digest=research_digest,
            outcome_checkpoint_digest=outcome_digest,
            timeframe_cache_digest=timeframe_digest,
            created_at=created,
        )
        supervisor = supervisor_store.initialize_checkpoint(checkpoint=candidate)
        supervisor_digest = verify_v32_tick_supervisor_checkpoint(supervisor)
    except (KeyError, TypeError, ValueError) as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_GENESIS_INITIALIZATION_FAILED"
        ) from exc

    if (
        supervisor.get("run_id") != run_id
        or supervisor.get("experiment_contract_digest") != contract_digest
        or supervisor.get("active_authority_digest") != authority_digest
        or supervisor.get("current_research_checkpoint_digest")
        != research_digest
        or supervisor.get("current_outcome_checkpoint_digest") != outcome_digest
        or supervisor.get("current_timeframe_cache_digest") != timeframe_digest
    ):
        raise V32ProspectiveRuntimeError("V32_RUNTIME_GENESIS_BINDING_INVALID")
    return {
        **_base_result(run_id=run_id, status="READY", now=created),
        "genesis_replay_safe": True,
        "dynamic_checkpoint_digest": research_digest,
        "outcome_checkpoint_digest": outcome_digest,
        "timeframe_cache_digest": timeframe_digest,
        "supervisor_checkpoint_digest": supervisor_digest,
        "cycle_audit_policy_digest": audit_policy_digest,
        "mailbox_initialization": "DEFERRED_TO_CYCLE_ANALYSIS_LANE",
        "audit_store_initialization": "APPEND_ONLY_NO_EMPTY_GENESIS",
    }


def _schedule_registry(
    *, run_id: str, schedule_sets: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    by_digest: dict[str, Mapping[str, Any]] = {}
    by_id: dict[str, Mapping[str, Any]] = {}
    for schedule_set in schedule_sets:
        try:
            digest = verify_v32_outcome_schedule_set(schedule_set)
        except (TypeError, ValueError) as exc:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_SCHEDULE_SET_INVALID"
            ) from exc
        if schedule_set.get("run_id") != run_id or digest in by_digest:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_SCHEDULE_SET_REGISTRY_INVALID"
            )
        by_digest[digest] = schedule_set
        for schedule in schedule_set["schedules"]:
            schedule_id = str(schedule["schedule_id"])
            if schedule_id in by_id:
                raise V32ProspectiveRuntimeError(
                    "V32_RUNTIME_SCHEDULE_DUPLICATE"
                )
            by_id[schedule_id] = schedule
    return by_digest, by_id


def _bound_schedule_sets(
    *,
    checkpoint: Mapping[str, Any],
    permit: Mapping[str, Any] | None,
    by_digest: Mapping[str, Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    digests = list(
        permit["outcome_schedule_set_digests"]
        if permit is not None
        else checkpoint["outcome_schedule_set_digests"]
    )
    try:
        result = [by_digest[digest] for digest in digests]
    except KeyError as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_BOUND_SCHEDULE_SET_MISSING"
        ) from exc
    if permit is None and set(by_digest) != set(digests):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_LIVE_SCHEDULE_REGISTRY_DRIFT"
        )
    return result


def _next_due(
    *,
    checkpoint: Mapping[str, Any],
    by_id: Mapping[str, Mapping[str, Any]],
    now: str,
) -> tuple[list[str], str | None]:
    terminal = set(checkpoint["terminal_schedule_ids"])
    outstanding = [
        schedule
        for schedule_id, schedule in by_id.items()
        if schedule_id not in terminal
    ]
    due = sorted(
        str(schedule["schedule_id"])
        for schedule in outstanding
        if _moment(schedule["outcome_not_before"], "V32_RUNTIME_SCHEDULE_TIME_INVALID")
        <= _moment(now, "V32_RUNTIME_CLOCK_INVALID")
    )
    next_due_at = (
        None
        if not outstanding
        else min(str(schedule["outcome_not_before"]) for schedule in outstanding)
    )
    return due, next_due_at


def _analysis_deadline(
    *, permit: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]
) -> tuple[str, str]:
    # ``analysis_decision_at`` is the legacy name for the already-sealed
    # source cutoff.  The bounded Agent phase starts when the permit opens.
    started = _moment(permit["issued_at"], "V32_RUNTIME_PERMIT_TIME_INVALID")
    synthetic_due = started + timedelta(seconds=ANALYSIS_INTERVAL_SECONDS)
    candidates = [synthetic_due]
    for schedule_id in permit["future_schedule_ids"]:
        if schedule_id not in by_id:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_PERMIT_FUTURE_SCHEDULE_MISSING"
            )
        candidates.append(
            _moment(
                by_id[schedule_id]["outcome_not_before"],
                "V32_RUNTIME_SCHEDULE_TIME_INVALID",
            )
        )
    next_due = min(candidates)
    # The analysis lane must stop before the first observable outcome.  The
    # smaller bound wins: the complete five-phase budget, or the first due
    # mark less the frozen reserve needed to schedule/capture that outcome.
    deadline = min(
        started + timedelta(seconds=TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS),
        next_due
        - timedelta(seconds=EARLIEST_OUTCOME_GRACE_RESERVE_SECONDS),
    )
    return (
        next_due.isoformat().replace("+00:00", "Z"),
        deadline.isoformat().replace("+00:00", "Z"),
    )


def resolve_v32_active_analysis_agent_window_v1(
    *,
    run_id: str,
    supervisor_checkpoint: Mapping[str, Any],
    active_permit: Mapping[str, Any],
    predecessor_checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    observed_at: str,
) -> Mapping[str, Any]:
    """Replay and resolve the sole active analysis Agent time window.

    This is the Application-owned source of truth for both the production
    wake and the presentation claim/delivery entries.  It reconstructs the
    permit from its exact predecessor and bound schedule registry before it
    computes the frozen deadline.  It reports whether ``observed_at`` is
    strictly before that deadline but performs no durable state transition.
    """

    try:
        supervisor_digest = verify_v32_tick_supervisor_checkpoint(
            supervisor_checkpoint
        )
        predecessor_digest = verify_v32_tick_supervisor_checkpoint(
            predecessor_checkpoint
        )
        verify_v32_tick_supervisor_transition(
            predecessor_checkpoint, supervisor_checkpoint
        )
        by_digest, by_id = _schedule_registry(
            run_id=run_id, schedule_sets=schedule_sets
        )
        bound_schedule_sets = _bound_schedule_sets(
            checkpoint=supervisor_checkpoint,
            permit=active_permit,
            by_digest=by_digest,
        )
        permit_digest = verify_v32_tick_supervisor_permit(
            active_permit,
            checkpoint=predecessor_checkpoint,
            schedule_sets=bound_schedule_sets,
        )
        next_due_at, permit_deadline_at = _analysis_deadline(
            permit=active_permit, by_id=by_id
        )
        observed = _moment(observed_at, "V32_RUNTIME_CLOCK_INVALID")
        issued = _moment(
            active_permit["issued_at"], "V32_RUNTIME_PERMIT_TIME_INVALID"
        )
        updated = _moment(
            supervisor_checkpoint["updated_at"],
            "V32_RUNTIME_SUPERVISOR_TIME_INVALID",
        )
        deadline = _moment(
            permit_deadline_at, "V32_RUNTIME_DEADLINE_INVALID"
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ProspectiveRuntimeError):
            raise
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_ACTIVE_ANALYSIS_WINDOW_INVALID"
        ) from exc
    if (
        supervisor_checkpoint.get("run_id") != run_id
        or predecessor_checkpoint.get("run_id") != run_id
        or active_permit.get("run_id") != run_id
        or supervisor_checkpoint.get("status") != "ANALYSIS_TICK_OPEN"
        or supervisor_checkpoint.get("active_permit_kind")
        != "ANALYSIS_TICK"
        or active_permit.get("permit_kind") != "ANALYSIS_TICK"
        or supervisor_checkpoint.get("active_permit_digest")
        != permit_digest
        or supervisor_checkpoint.get("predecessor_checkpoint_digest")
        != predecessor_digest
        or active_permit.get(
            "supervisor_checkpoint_digest_before_permit"
        )
        != predecessor_digest
        or active_permit.get("analysis_cycle_index")
        != supervisor_checkpoint.get("next_analysis_cycle_index")
        or active_permit.get("analysis_cycle_index")
        != supervisor_checkpoint.get("accepted_analysis_cycles") + 1
        or observed < issued
        or observed < updated
    ):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_ACTIVE_ANALYSIS_WINDOW_BINDING_INVALID"
        )
    return {
        "run_id": run_id,
        "analysis_cycle_index": int(active_permit["analysis_cycle_index"]),
        "supervisor_checkpoint_digest": supervisor_digest,
        "predecessor_checkpoint_digest": predecessor_digest,
        "active_permit_digest": permit_digest,
        "bound_schedule_set_digests": [
            verify_v32_outcome_schedule_set(schedule_set)
            for schedule_set in bound_schedule_sets
        ],
        "bound_schedule_sets": [
            deepcopy(dict(schedule_set)) for schedule_set in bound_schedule_sets
        ],
        "next_due_at": next_due_at,
        "permit_deadline_at": permit_deadline_at,
        "observed_at": observed_at,
        "strictly_before_deadline": observed < deadline,
        "outcome_values_read": False,
        "network_request_count": 0,
        "account_access": False,
        "order_submission": False,
        "executable": False,
    }


def verify_v32_active_analysis_agent_window_v1(
    *,
    run_id: str,
    supervisor_checkpoint: Mapping[str, Any],
    active_permit: Mapping[str, Any],
    predecessor_checkpoint: Mapping[str, Any],
    schedule_sets: Sequence[Mapping[str, Any]],
    observed_at: str,
) -> Mapping[str, Any]:
    """Require one claim/delivery timestamp to be strictly before deadline."""

    result = resolve_v32_active_analysis_agent_window_v1(
        run_id=run_id,
        supervisor_checkpoint=supervisor_checkpoint,
        active_permit=active_permit,
        predecessor_checkpoint=predecessor_checkpoint,
        schedule_sets=schedule_sets,
        observed_at=observed_at,
    )
    if result["strictly_before_deadline"] is not True:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_ACTIVE_ANALYSIS_AGENT_WINDOW_EXPIRED"
        )
    return result


def _public_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    try:
        result = {field: binding[field] for field in _PUBLIC_BINDING_FIELDS}
    except KeyError as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_AUDIT_BINDING_INVALID"
        ) from exc
    return result


def _audit_sources(
    *,
    dynamic_store: V32ProspectiveDynamicStorePort,
    replay: Mapping[str, Any],
    boundary_type: str,
) -> list[Mapping[str, Any]]:
    if boundary_type == "ACCEPTANCE":
        return [
            {
                "role": "analysis_acceptance",
                "document": deepcopy(dict(replay["acceptance"])),
                "binding": _public_binding(replay["binding"]),
            }
        ]
    required = replay.get("required_bindings")
    if not isinstance(required, Mapping) or not required:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_ANALYSIS_AUDIT_SOURCES_MISSING"
        )
    return [
        {
            "role": str(role),
            "document": deepcopy(dict(dynamic_store.load_artifact(binding))),
            "binding": _public_binding(binding),
        }
        for role, binding in sorted(required.items())
    ]


def _pending_external_action(
    *,
    mailbox: V32ProspectiveMailboxPort,
    run_id: str,
    cycle_index: int,
) -> Mapping[str, Any] | None:
    try:
        pending = mailbox.next_pending_request(
            run_id=run_id, cycle_index=cycle_index
        )
    except Exception as exc:
        cause: BaseException | None = exc
        missing = False
        while cause is not None:
            if isinstance(cause, FileNotFoundError):
                missing = True
                break
            cause = cause.__cause__
        if missing:
            return None
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_MAILBOX_READ_FAILED"
        ) from exc
    if pending is None:
        return None
    expected_action_by_status = {
        "REQUESTED": "CURRENT_ROOT_CODEX_CLAIM",
        "CLAIMED": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
        "DELIVERED": "CONTROLLER_CONSUME_DELIVERY",
    }
    if not isinstance(pending, Mapping) or (
        pending.get("stage") not in {"PROPOSAL", "SELECTION"}
        or pending.get("run_id") != run_id
        or pending.get("cycle_index") != cycle_index
        or not isinstance(pending.get("stage_status"), str)
        or pending.get("stage_status") not in expected_action_by_status
        or pending.get("next_action")
        != expected_action_by_status.get(pending.get("stage_status"))
    ):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_MAILBOX_PENDING_STATE_INVALID"
        )
    try:
        checkpoint = mailbox.load_checkpoint(
            run_id=run_id, cycle_index=cycle_index
        )
        chain = mailbox.load_stage_chain(
            run_id=run_id,
            cycle_index=cycle_index,
            stage=str(pending["stage"]),
        )
    except Exception as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_MAILBOX_PRESENTATION_READ_FAILED"
        ) from exc
    if (
        not isinstance(checkpoint, Mapping)
        or not isinstance(chain, Mapping)
        or not isinstance(pending.get("request"), Mapping)
        or chain.get("request") != pending.get("request")
        or chain.get("claim") != pending.get("claim")
        or chain.get("stage_status") != pending.get("stage_status")
        or chain.get("checkpoint_digest") != pending.get("checkpoint_digest")
        or chain.get("ordered_agent_input_delivery_units")
        != pending.get("ordered_agent_input_delivery_units")
    ):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_MAILBOX_PRESENTATION_REPLAY_INVALID"
        )
    if pending["stage_status"] == "DELIVERED":
        if (
            not isinstance(chain.get("claim"), Mapping)
            or not isinstance(chain.get("agent_delivery"), Mapping)
            or not isinstance(chain.get("delivery_receipt"), Mapping)
            or chain.get("agent_consumption") is not None
            or chain.get("consumption_receipt") is not None
        ):
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_MAILBOX_DELIVERED_REPLAY_INVALID"
            )
        # Delivery is already durable, including the exact current-Codex
        # presentation acknowledgement.  It is controller-owned work now;
        # return no external action so the analysis lane can consume it.
        return None
    if pending["stage_status"] == "REQUESTED":
        if (
            chain.get("claim") is not None
            and not isinstance(chain.get("claim"), Mapping)
        ) or any(
            chain.get(field) is not None
            for field in (
                "agent_delivery",
                "delivery_receipt",
                "agent_consumption",
                "consumption_receipt",
            )
        ):
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_MAILBOX_REQUESTED_REPLAY_INVALID"
            )
        # A claim file can be durable before the checkpoint CAS.  REQUESTED is
        # still the owning state until exact-tail recovery completes, so the
        # read-only wake must present a REQUESTED envelope and leave the orphan
        # claim to the dedicated claim entry.  Passing it here would create an
        # impossible REQUESTED-checkpoint/CLAIMED-presentation combination.
        presentation_claim: Mapping[str, Any] | None = None
    else:
        if not isinstance(chain.get("claim"), Mapping) or any(
            chain.get(field) is not None
            for field in (
                "agent_delivery",
                "delivery_receipt",
                "agent_consumption",
                "consumption_receipt",
            )
        ):
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_MAILBOX_CLAIMED_REPLAY_INVALID"
            )
        presentation_claim = chain["claim"]
    request = chain["request"]
    if (
        not isinstance(request, Mapping)
        or request.get("context_delivery_mode") != "INLINE"
    ):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_AGENT_PRESENTATION_MODE_NOT_QUALIFIED"
        )
    try:
        return build_v32_current_codex_presentation_envelope_v1(
            mailbox_checkpoint=checkpoint,
            request=request,
            claim=presentation_claim,
            lossless_context_package=chain.get("lossless_context_package"),
            control_context={
                "presentation_kind": "PROSPECTIVE_PENDING_AGENT_ACTION",
                "request_kind": "CURRENT_ROOT_CODEX_AGENT_ACTION_REQUIRED",
                "stage": pending["stage"],
                "stage_status": pending["stage_status"],
                "next_action": pending["next_action"],
            },
        )
    except Exception as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_AGENT_PRESENTATION_BUILD_FAILED"
        ) from exc


def _audit_gate_or_next(
    *,
    supervisor: Mapping[str, Any],
    dynamic_store: V32ProspectiveDynamicStorePort,
    revision_store: V32ProspectiveAuditRevisionPort,
    completion_store: V32ProspectiveAuditCompletionPort,
    audit_lane: V32ProspectiveAuditLanePort,
    cycle_audit_policy: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    cycle = int(supervisor["accepted_analysis_cycles"])
    if cycle == 0:
        return None
    run_id = str(supervisor["run_id"])
    replay = dynamic_store.replay_cycle_acceptance(
        run_id=run_id, cycle_index=cycle
    )
    acceptance = replay["acceptance"]
    try:
        acceptance_digest = verify_self_digest(
            acceptance, str(replay["binding"]["digest_field"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_ACCEPTANCE_REPLAY_INVALID"
        ) from exc
    if acceptance_digest != supervisor["accepted_state_digests"][-1]:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_ACCEPTANCE_SUPERVISOR_MISMATCH"
        )
    analysis_audit = revision_store.load_audit_bundle(
        run_id=run_id, cycle_index=cycle, boundary_type="ANALYSIS"
    )
    if analysis_audit is None:
        return audit_lane.advance_once(
            narrative_id=f"v32-analysis::{run_id}::{cycle:04d}",
            completion_id=None,
            run_id=run_id,
            cycle_index=cycle,
            boundary_type="ANALYSIS",
            boundary_sealed_at=acceptance["accepted_at"],
            sealed_sources=_audit_sources(
                dynamic_store=dynamic_store,
                replay=replay,
                boundary_type="ANALYSIS",
            ),
            cycle_audit_policy=cycle_audit_policy,
        )

    acceptance_audit = revision_store.load_audit_bundle(
        run_id=run_id, cycle_index=cycle, boundary_type="ACCEPTANCE"
    )
    completion = completion_store.load_completion(
        run_id=run_id, cycle_index=cycle
    )
    if completion is None:
        return audit_lane.advance_once(
            narrative_id=f"v32-acceptance::{run_id}::{cycle:04d}",
            completion_id=f"v32-audit-complete::{run_id}::{cycle:04d}",
            run_id=run_id,
            cycle_index=cycle,
            boundary_type="ACCEPTANCE",
            boundary_sealed_at=acceptance["accepted_at"],
            sealed_sources=_audit_sources(
                dynamic_store=dynamic_store,
                replay=replay,
                boundary_type="ACCEPTANCE",
            ),
            cycle_audit_policy=cycle_audit_policy,
        )
    if acceptance_audit is None:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_ACCEPTANCE_AUDIT_BUNDLE_MISSING"
        )
    try:
        verify_v32_cycle_audit_completion_receipt_v1(
            completion,
            cycle_audit_policy=cycle_audit_policy,
            analysis_acceptance=acceptance,
            narrative_directory=acceptance_audit["directory"],
            narrative_shards=acceptance_audit["shards"],
        )
        verify_v32_latest_cycle_audit_gate_v1(
            supervisor_checkpoint=supervisor,
            latest_audit_completion=completion,
        )
    except (TypeError, ValueError) as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_AUDIT_GATE_INVALID"
        ) from exc
    return None


def _outcome_audit_or_next(
    *,
    supervisor: Mapping[str, Any],
    outcome_store: V32ProspectiveOutcomeStorePort,
    revision_store: V32ProspectiveAuditRevisionPort,
    audit_lane: V32ProspectiveAuditLanePort,
    cycle_audit_policy: Mapping[str, Any],
    schedule_by_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Render the earliest complete three-horizon outcome boundary once.

    Outcome ticks may resolve schedules from several cycles in one public
    capture.  The human audit boundary is nevertheless cycle scoped: it is
    eligible only after that cycle's exact 15m, 1h and 4h receipts are all
    terminal.  The typed receipts remain authoritative and no outcome value
    is re-fetched here.
    """

    run_id = str(supervisor["run_id"])
    terminal_schedule_ids = set(supervisor["terminal_schedule_ids"])
    accepted_cycles = int(supervisor["accepted_analysis_cycles"])
    pending_cycle: int | None = None
    pending_schedule_ids: list[str] = []
    for cycle_index in range(1, accepted_cycles + 1):
        cycle_schedules = sorted(
            (
                schedule
                for schedule in schedule_by_id.values()
                if schedule.get("cycle_index") == cycle_index
            ),
            key=lambda row: str(row["horizon"]),
        )
        if len(cycle_schedules) != 3 or {
            str(row["horizon"]) for row in cycle_schedules
        } != set(_OUTCOME_HORIZON_ORDER):
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_OUTCOME_AUDIT_SCHEDULE_SET_INVALID"
            )
        schedule_ids = [str(row["schedule_id"]) for row in cycle_schedules]
        if not set(schedule_ids).issubset(terminal_schedule_ids):
            continue
        existing = revision_store.load_audit_bundle(
            run_id=run_id,
            cycle_index=cycle_index,
            boundary_type="OUTCOME",
        )
        if existing is None:
            pending_cycle = cycle_index
            pending_schedule_ids = schedule_ids
            break
    if pending_cycle is None:
        return None

    try:
        materials = outcome_store.load_terminal_receipt_materials(run_id=run_id)
    except Exception as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_OUTCOME_AUDIT_RECEIPT_LOAD_FAILED"
        ) from exc
    matching = [
        material
        for material in materials
        if isinstance(material, Mapping)
        and isinstance(material.get("receipt"), Mapping)
        and material["receipt"].get("cycle_index") == pending_cycle
    ]
    if (
        len(matching) != 3
        or {str(row["receipt"].get("schedule_id")) for row in matching}
        != set(pending_schedule_ids)
        or {str(row["receipt"].get("horizon")) for row in matching}
        != set(_OUTCOME_HORIZON_ORDER)
        or any(row["receipt"].get("terminal") is not True for row in matching)
    ):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_OUTCOME_AUDIT_RECEIPT_SET_INVALID"
        )
    expiry_aggregates: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for material in materials:
        binding = material.get("receipt_binding")
        if (
            isinstance(binding, Mapping)
            and binding.get("binding_kind") == "EXPIRY_AGGREGATE_MEMBER"
        ):
            aggregate = binding.get("aggregate_document")
            aggregate_binding = binding.get("aggregate_binding")
            if not isinstance(aggregate, Mapping) or not isinstance(
                aggregate_binding, Mapping
            ):
                raise V32ProspectiveRuntimeError(
                    "V32_RUNTIME_OUTCOME_AUDIT_RECEIPT_SET_INVALID"
                )
            semantic = str(aggregate_binding.get("semantic_digest"))
            if semantic in expiry_aggregates:
                raise V32ProspectiveRuntimeError(
                    "V32_RUNTIME_OUTCOME_AUDIT_RECEIPT_SET_INVALID"
                )
            expiry_aggregates[semantic] = (aggregate, aggregate_binding)
    sealed_sources = []
    sealed_expiry_aggregates: set[str] = set()
    for material in sorted(
        matching,
        key=lambda row: _OUTCOME_HORIZON_ORDER[str(row["receipt"]["horizon"])],
    ):
        binding = material["receipt_binding"]
        binding_kind = binding.get("binding_kind")
        aggregate_member = binding_kind in {
            "EXPIRY_AGGREGATE_MEMBER",
            "EXPIRY_AGGREGATE_MEMBER_REF",
        }
        if aggregate_member:
            if binding_kind == "EXPIRY_AGGREGATE_MEMBER":
                aggregate = binding.get("aggregate_document")
                aggregate_binding = binding.get("aggregate_binding")
                aggregate_semantic = str(
                    aggregate_binding.get("semantic_digest")
                    if isinstance(aggregate_binding, Mapping)
                    else ""
                )
            else:
                aggregate_semantic = str(
                    binding.get("aggregate_semantic_digest")
                )
                aggregate, aggregate_binding = expiry_aggregates.get(
                    aggregate_semantic, (None, None)
                )
            if (
                not aggregate_semantic
                or not isinstance(aggregate, Mapping)
                or not isinstance(aggregate_binding, Mapping)
            ):
                raise V32ProspectiveRuntimeError(
                    "V32_RUNTIME_OUTCOME_AUDIT_RECEIPT_SET_INVALID"
                )
            if aggregate_semantic in sealed_expiry_aggregates:
                continue
            sealed_expiry_aggregates.add(aggregate_semantic)
        sealed_sources.append(
            {
                "role": (
                    "outcome_expiry_" if aggregate_member else "outcome_"
                )
                + str(material["receipt"]["horizon"]).lower(),
                "document": deepcopy(
                    dict(
                        aggregate
                        if aggregate_member
                        else material["receipt"]
                    )
                ),
                "binding": _public_binding(
                    aggregate_binding if aggregate_member else binding
                ),
            }
        )
    boundary_sealed_at = max(
        str(material["receipt"]["resolved_at"]) for material in matching
    )
    return audit_lane.advance_once(
        narrative_id=f"v32-outcome::{run_id}::{pending_cycle:04d}",
        completion_id=None,
        run_id=run_id,
        cycle_index=pending_cycle,
        boundary_type="OUTCOME",
        boundary_sealed_at=boundary_sealed_at,
        sealed_sources=sealed_sources,
        cycle_audit_policy=cycle_audit_policy,
    )


def _recovery_audit_or_next(
    *,
    supervisor: Mapping[str, Any],
    revision_store: V32ProspectiveAuditRevisionPort,
    audit_lane: V32ProspectiveAuditLanePort,
    cycle_audit_policy: Mapping[str, Any],
    supervision_evidence_port: V32SupervisionEvidencePort | None,
) -> Mapping[str, Any] | None:
    """Render at most one audit from already sealed deterministic recovery bytes."""

    if supervision_evidence_port is None:
        return None
    run_id = str(supervisor["run_id"])
    try:
        materials = supervision_evidence_port.load_recovery_audit_materials(
            run_id=run_id
        )
    except Exception as exc:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_RECOVERY_AUDIT_MATERIAL_LOAD_FAILED"
        ) from exc
    for material in sorted(materials, key=lambda row: int(row["cycle_index"])):
        cycle = material.get("cycle_index")
        sealed_sources = material.get("sealed_sources")
        if (
            isinstance(cycle, bool)
            or not isinstance(cycle, int)
            or not 1 <= cycle <= int(supervisor["accepted_analysis_cycles"])
            or not isinstance(sealed_sources, Sequence)
            or isinstance(sealed_sources, (str, bytes))
            or not sealed_sources
        ):
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_RECOVERY_AUDIT_MATERIAL_INVALID"
            )
        existing = revision_store.load_audit_bundle(
            run_id=run_id, cycle_index=cycle, boundary_type="RECOVERY"
        )
        if existing is not None:
            continue
        return audit_lane.advance_once(
            narrative_id=f"v32-recovery::{run_id}::{cycle:04d}",
            completion_id=None,
            run_id=run_id,
            cycle_index=cycle,
            boundary_type="RECOVERY",
            boundary_sealed_at=str(material["boundary_sealed_at"]),
            sealed_sources=deepcopy(list(sealed_sources)),
            cycle_audit_policy=cycle_audit_policy,
        )
    return None


def _terminal_audit_materials(
    *,
    run_id: str,
    revision_store: V32ProspectiveAuditRevisionPort,
    supervision_evidence_port: V32SupervisionEvidencePort | None,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Replay the exact 49 required directories and any recovery directories."""

    required_identities = [("QUALIFICATION", 0)] + [
        (boundary, cycle)
        for cycle in range(1, 17)
        for boundary in ("ANALYSIS", "ACCEPTANCE", "OUTCOME")
    ]
    required: list[Mapping[str, Any]] = []
    for boundary, cycle in required_identities:
        bundle = revision_store.load_audit_bundle(
            run_id=run_id, cycle_index=cycle, boundary_type=boundary
        )
        if bundle is None or not isinstance(bundle.get("directory"), Mapping):
            raise V32ProspectiveRuntimeError(
                f"V32_RUNTIME_TERMINAL_AUDIT_MISSING:{boundary}:{cycle}"
            )
        required.append(
            {
                "boundary_type": boundary,
                "cycle_index": cycle,
                "directory": deepcopy(dict(bundle["directory"])),
            }
        )

    expected_recovery_cycles: set[int] = set()
    if supervision_evidence_port is not None:
        try:
            recovery_materials = (
                supervision_evidence_port.load_recovery_audit_materials(
                    run_id=run_id
                )
            )
        except Exception as exc:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_RECOVERY_AUDIT_MATERIAL_LOAD_FAILED"
            ) from exc
        expected_recovery_cycles = {
            int(material["cycle_index"]) for material in recovery_materials
        }
    recovery: list[Mapping[str, Any]] = []
    for cycle in range(1, 17):
        bundle = revision_store.load_audit_bundle(
            run_id=run_id, cycle_index=cycle, boundary_type="RECOVERY"
        )
        if bundle is None:
            if cycle in expected_recovery_cycles:
                raise V32ProspectiveRuntimeError(
                    f"V32_RUNTIME_TERMINAL_RECOVERY_AUDIT_MISSING:{cycle}"
                )
            continue
        if cycle not in expected_recovery_cycles:
            raise V32ProspectiveRuntimeError(
                f"V32_RUNTIME_TERMINAL_RECOVERY_AUDIT_ORPHANED:{cycle}"
            )
        if not isinstance(bundle.get("directory"), Mapping):
            raise V32ProspectiveRuntimeError(
                f"V32_RUNTIME_TERMINAL_RECOVERY_AUDIT_INVALID:{cycle}"
            )
        recovery.append(
            {
                "boundary_type": "RECOVERY",
                "cycle_index": cycle,
                "directory": deepcopy(dict(bundle["directory"])),
            }
        )
    return required, recovery


def _deadline_fail_closed(
    *,
    supervisor_store: V32ProspectiveSupervisorStorePort,
    supervisor: Mapping[str, Any],
    permit: Mapping[str, Any],
    now: str,
    next_due_at: str,
    permit_deadline_at: str,
) -> Mapping[str, Any]:
    evidence_digest = canonical_digest(
        {
            "schema_id": "theory_paper_v32_analysis_permit_deadline_evidence_v1",
            "run_id": supervisor["run_id"],
            "permit_digest": permit[PERMIT_DIGEST_FIELD],
            "next_due_at": next_due_at,
            "permit_deadline_at": permit_deadline_at,
            "observed_at": now,
            "outcome_values_read": False,
        }
    )
    failed = supervisor_store.fail_closed(
        expected_checkpoint_digest=supervisor[CHECKPOINT_DIGEST_FIELD],
        failure_lane="ANALYSIS_LANE",
        failure_code="ANALYSIS_CLOCK_CONFLICT",
        failure_summary=(
            "active analysis permit exceeded its frozen phase budget or "
            "earliest-outcome reserve deadline"
        ),
        failure_evidence_digest=evidence_digest,
        occurred_at=now,
    )
    return {
        **_base_result(
            run_id=str(supervisor["run_id"]),
            status="FAILED_CLOSED",
            now=now,
        ),
        "boundary_kind": "SUPERVISOR_ANALYSIS_DEADLINE_FAILED_CLOSED",
        "high_level_boundaries_completed_this_wake": 1,
        "durable_state_boundaries_this_wake": 1,
        "outcome_values_read": False,
        "next_due_at": next_due_at,
        "permit_deadline_at": permit_deadline_at,
        "permit_digest": permit[PERMIT_DIGEST_FIELD],
        "supervisor_checkpoint_digest": failed[CHECKPOINT_DIGEST_FIELD],
    }


def _outcome_permit_expired_fail_closed(
    *,
    supervisor_store: V32ProspectiveSupervisorStorePort,
    supervisor: Mapping[str, Any],
    permit: Mapping[str, Any],
    now: str,
    expired_schedule_ids: Sequence[str],
) -> Mapping[str, Any]:
    evidence_digest = canonical_digest(
        {
            "schema_id": "theory_paper_v32_active_outcome_permit_expired_v1",
            "run_id": supervisor["run_id"],
            "permit_digest": permit[PERMIT_DIGEST_FIELD],
            "expired_schedule_ids": sorted(expired_schedule_ids),
            "observed_at": now,
            "outcome_values_read": False,
            "network_requests": 0,
        }
    )
    failed = supervisor_store.fail_closed(
        expected_checkpoint_digest=supervisor[CHECKPOINT_DIGEST_FIELD],
        failure_lane="OUTCOME_LANE",
        failure_code="OUTCOME_CLOCK_CONFLICT",
        failure_summary=(
            "active public outcome permit crossed a bound observation grace "
            "deadline before capture"
        ),
        failure_evidence_digest=evidence_digest,
        occurred_at=now,
    )
    return {
        **_base_result(
            run_id=str(supervisor["run_id"]), status="FAILED_CLOSED", now=now
        ),
        "boundary_kind": "SUPERVISOR_OUTCOME_DEADLINE_FAILED_CLOSED",
        "high_level_boundaries_completed_this_wake": 1,
        "durable_state_boundaries_this_wake": 1,
        "outcome_values_read": False,
        "network_requests": 0,
        "expired_schedule_ids": sorted(expired_schedule_ids),
        "permit_digest": permit[PERMIT_DIGEST_FIELD],
        "supervisor_checkpoint_digest": failed[CHECKPOINT_DIGEST_FIELD],
    }


def _active_permit_integrity_fail_closed(
    *,
    supervisor_store: V32ProspectiveSupervisorStorePort,
    supervisor: Mapping[str, Any],
    now: str,
    error: Exception,
) -> Mapping[str, Any]:
    outcome_lane = supervisor.get("status") == "OUTCOME_TICK_OPEN"
    evidence_digest = canonical_digest(
        {
            "schema_id": "theory_paper_v32_active_permit_integrity_failure_v1",
            "run_id": supervisor["run_id"],
            "active_permit_digest": supervisor["active_permit_digest"],
            "observed_at": now,
            "failure_class": type(error).__name__,
            "failure_message": str(error)[:512],
            "outcome_values_read": False,
            "network_requests": 0,
        }
    )
    failed = supervisor_store.fail_closed(
        expected_checkpoint_digest=supervisor[CHECKPOINT_DIGEST_FIELD],
        failure_lane="OUTCOME_LANE" if outcome_lane else "ANALYSIS_LANE",
        failure_code=(
            "OUTCOME_SCHEMA_OR_DIGEST_INVALID"
            if outcome_lane
            else "ANALYSIS_SCHEMA_OR_DIGEST_INVALID"
        ),
        failure_summary="active permit or predecessor failed integrity replay",
        failure_evidence_digest=evidence_digest,
        occurred_at=now,
    )
    return {
        **_base_result(
            run_id=str(supervisor["run_id"]), status="FAILED_CLOSED", now=now
        ),
        "boundary_kind": "SUPERVISOR_ACTIVE_PERMIT_FAILED_CLOSED",
        "high_level_boundaries_completed_this_wake": 1,
        "durable_state_boundaries_this_wake": 1,
        "outcome_values_read": False,
        "network_requests": 0,
        "supervisor_checkpoint_digest": failed[CHECKPOINT_DIGEST_FIELD],
    }


def _source_preparation_fail_closed(
    *,
    supervisor_store: V32ProspectiveSupervisorStorePort,
    supervisor: Mapping[str, Any],
    now: str,
    failure_code: str,
    error: Exception,
) -> Mapping[str, Any]:
    evidence_digest = canonical_digest(
        {
            "schema_id": "theory_paper_v32_source_preparation_failure_evidence_v1",
            "run_id": supervisor["run_id"],
            "cycle_index": supervisor["next_analysis_cycle_index"],
            "observed_at": now,
            "failure_class": type(error).__name__,
            "failure_message": str(error)[:512],
            "outcome_values_read": False,
            "retry_allowed": False,
        }
    )
    failed = supervisor_store.fail_closed(
        expected_checkpoint_digest=supervisor[CHECKPOINT_DIGEST_FIELD],
        failure_lane="SOURCE_LANE",
        failure_code=failure_code,
        failure_summary="pre-permit public source preparation failed closed",
        failure_evidence_digest=evidence_digest,
        occurred_at=now,
    )
    return {
        **_base_result(
            run_id=str(supervisor["run_id"]),
            status="FAILED_CLOSED",
            now=now,
        ),
        "boundary_kind": "SUPERVISOR_SOURCE_PREPARATION_FAILED_CLOSED",
        "high_level_boundaries_completed_this_wake": 1,
        "durable_state_boundaries_this_wake": 1,
        "outcome_values_read": False,
        "failure_code": failure_code,
        "supervisor_checkpoint_digest": failed[CHECKPOINT_DIGEST_FIELD],
    }


def _source_preparation_supervisor_failure_code(error: Exception) -> str:
    """Map stable typed error-code tokens without inspecting prose text."""

    stable_code = (str(error).strip() or type(error).__name__).split(":", 1)[0]
    tokens = set(stable_code.split("_"))
    if tokens & {"CLOCK", "TIME", "CHRONOLOGY", "FRESHNESS", "STALE", "PIT"}:
        return "SOURCE_CLOCK_OR_PIT_INVALID"
    return "SOURCE_SCHEMA_OR_DIGEST_INVALID"


def _verify_prepared_source_projection(
    document: Mapping[str, Any],
    *,
    run_id: str,
    cycle_index: int,
    observed_at: str,
) -> Mapping[str, Any]:
    fields = {
        "run_id",
        "cycle_index",
        "source_cutoff_at",
        "admitted_at",
        "replayed_at",
        "source_qualification_digest",
        "source_admission_digest",
        "durable_source_replay_receipt_digest",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_PREPARED_SOURCE_PROJECTION_INVALID"
        )
    if document.get("run_id") != run_id or document.get("cycle_index") != cycle_index:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_PREPARED_SOURCE_SCOPE_INVALID"
        )
    for name in (
        "source_qualification_digest",
        "source_admission_digest",
        "durable_source_replay_receipt_digest",
    ):
        _digest(document.get(name), "V32_RUNTIME_PREPARED_SOURCE_DIGEST_INVALID")
    cutoff = _moment(
        document["source_cutoff_at"],
        "V32_RUNTIME_PREPARED_SOURCE_TIME_INVALID",
    )
    admitted = _moment(
        document["admitted_at"], "V32_RUNTIME_PREPARED_SOURCE_TIME_INVALID"
    )
    replayed = _moment(
        document["replayed_at"], "V32_RUNTIME_PREPARED_SOURCE_TIME_INVALID"
    )
    observed = _moment(observed_at, "V32_RUNTIME_CLOCK_INVALID")
    if not cutoff <= admitted <= replayed <= observed:
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_PREPARED_SOURCE_TIME_INVALID"
        )
    if observed - cutoff > timedelta(seconds=MAX_SOURCE_AGE_SECONDS):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_PREPARED_SOURCE_STALE_BEFORE_PERMIT"
        )
    return deepcopy(dict(document))


def route_v32_prospective_wake_v1(
    *,
    supervisor_store: V32ProspectiveSupervisorStorePort,
    dynamic_store: V32ProspectiveDynamicStorePort,
    outcome_store: V32ProspectiveOutcomeStorePort,
    mailbox: V32ProspectiveMailboxPort,
    revision_store: V32ProspectiveAuditRevisionPort,
    audit_completion_store: V32ProspectiveAuditCompletionPort,
    audit_lane: V32ProspectiveAuditLanePort,
    analysis_port: Any,
    outcome_port: Any,
    cycle_audit_policy: Mapping[str, Any],
    run_id: str,
    clock: Clock,
    supervisor_alert_port: V32ReadOnlySupervisorAlertPort | None = None,
    supervision_evidence_port: V32SupervisionEvidencePort | None = None,
    terminal_seal_port: V32TerminalSealPort | None = None,
    wake_runner: WakeRunner = run_v32_single_boundary_wake,
) -> Mapping[str, Any]:
    """Route one production wake without ever synthesizing an Agent output."""

    now = _clock_time(clock)
    try:
        verify_v32_cycle_audit_policy_v1(cycle_audit_policy)
        supervisor = supervisor_store.load_checkpoint(run_id=run_id)
        verify_v32_tick_supervisor_checkpoint(supervisor)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, V32ProspectiveRuntimeError):
            raise
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_STATE_LOAD_INVALID"
        ) from exc
    if cycle_audit_policy.get("run_scope_id") != run_id:
        raise V32ProspectiveRuntimeError("V32_RUNTIME_AUDIT_SCOPE_INVALID")
    if supervisor.get("run_id") != run_id:
        raise V32ProspectiveRuntimeError("V32_RUNTIME_RUN_MISMATCH")
    # A terminal failure must remain observable even when the lower outcome
    # registry that caused it is still corrupt.  No terminal replay needs or
    # is allowed to re-open that registry.
    if supervisor["status"] == "FAILED_CLOSED":
        result = {
            **_base_result(
                run_id=run_id, status=supervisor["status"], now=now
            ),
            "boundary_kind": "NO_MUTATION_TERMINAL_STATE",
            "high_level_boundaries_completed_this_wake": 0,
            "durable_state_boundaries_this_wake": 0,
            "outcome_values_read": False,
            "network_requests": 0,
            "supervisor_checkpoint_digest": supervisor[
                CHECKPOINT_DIGEST_FIELD
            ],
        }
        return _with_alert(
            result, run_id=run_id, alert_port=supervisor_alert_port
        )
    try:
        schedule_sets = outcome_store.load_schedule_sets(run_id=run_id)
        by_digest, by_id = _schedule_registry(
            run_id=run_id, schedule_sets=schedule_sets
        )
    except (TypeError, ValueError) as exc:
        if supervisor.get("active_permit_digest") is not None:
            return _with_alert(
                _active_permit_integrity_fail_closed(
                    supervisor_store=supervisor_store,
                    supervisor=supervisor,
                    now=now,
                    error=exc,
                ),
                run_id=run_id,
                alert_port=supervisor_alert_port,
            )
        if isinstance(exc, V32ProspectiveRuntimeError):
            raise
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_STATE_LOAD_INVALID"
        ) from exc
    if (
        supervisor["accepted_analysis_cycles"] == 0
        and revision_store.load_audit_bundle(
            run_id=run_id,
            cycle_index=0,
            boundary_type="QUALIFICATION",
        )
        is None
    ):
        raise V32ProspectiveRuntimeError(
            "V32_RUNTIME_QUALIFICATION_AUDIT_REQUIRED_BEFORE_ANALYSIS"
        )
    active_permit: Mapping[str, Any] | None = None
    if supervisor["active_permit_digest"] is not None:
        try:
            active_permit = supervisor_store.load_permit(
                run_id=run_id,
                permit_digest=supervisor["active_permit_digest"],
            )
        except Exception as exc:
            return _with_alert(
                _active_permit_integrity_fail_closed(
                    supervisor_store=supervisor_store,
                    supervisor=supervisor,
                    now=now,
                    error=exc,
                ),
                run_id=run_id,
                alert_port=supervisor_alert_port,
            )
    try:
        bound_schedule_sets = _bound_schedule_sets(
            checkpoint=supervisor,
            permit=active_permit,
            by_digest=by_digest,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if active_permit is None:
            raise
        return _with_alert(
            _active_permit_integrity_fail_closed(
                supervisor_store=supervisor_store,
                supervisor=supervisor,
                now=now,
                error=exc,
            ),
            run_id=run_id,
            alert_port=supervisor_alert_port,
        )
    active_analysis_window: Mapping[str, Any] | None = None
    if active_permit is not None:
        try:
            predecessor = supervisor_store.load_checkpoint_by_digest(
                run_id=run_id,
                checkpoint_digest=active_permit[
                    "supervisor_checkpoint_digest_before_permit"
                ],
            )
            if active_permit.get("permit_kind") == "ANALYSIS_TICK":
                active_analysis_window = (
                    resolve_v32_active_analysis_agent_window_v1(
                        run_id=run_id,
                        supervisor_checkpoint=supervisor,
                        active_permit=active_permit,
                        predecessor_checkpoint=predecessor,
                        schedule_sets=schedule_sets,
                        observed_at=now,
                    )
                )
                bound_schedule_sets = list(
                    active_analysis_window["bound_schedule_sets"]
                )
            else:
                tick_attempt = None
                if active_permit.get("permit_kind") == "OUTCOME_TICK":
                    tick_attempt = build_v32_outcome_tick_attempt(
                        run_id=run_id,
                        tick_index=active_permit["outcome_tick_index"],
                        planned_tick_at=active_permit[
                            "planned_outcome_tick_at"
                        ],
                        reserved_at=active_permit["issued_at"],
                    )
                elif active_permit.get("permit_kind") != "OUTCOME_WINDOW_EXPIRY":
                    raise V32ProspectiveRuntimeError(
                        "V32_RUNTIME_ACTIVE_PERMIT_INVALID"
                    )
                verify_v32_tick_supervisor_permit(
                    active_permit,
                    checkpoint=predecessor,
                    schedule_sets=bound_schedule_sets,
                    tick_attempt=tick_attempt,
                )
        except (KeyError, TypeError, ValueError) as exc:
            return _with_alert(
                _active_permit_integrity_fail_closed(
                    supervisor_store=supervisor_store,
                    supervisor=supervisor,
                    now=now,
                    error=exc,
                ),
                run_id=run_id,
                alert_port=supervisor_alert_port,
            )

    # Active permits are a non-preemptible recovery invariant.  Outcome
    # deadlines bound that privilege so an Agent wait cannot silently consume
    # the observation grace window.
    if active_permit is not None:
        lane = (
            "ANALYSIS"
            if active_permit.get("permit_kind") == "ANALYSIS_TICK"
            else "OUTCOME"
        )
        request = (
            {
                "lane": "ANALYSIS",
                "analysis_decision_at": active_permit["analysis_decision_at"],
                "issued_at": active_permit["issued_at"],
            }
            if lane == "ANALYSIS"
            else {
                "lane": "OUTCOME",
                "planned_tick_at": active_permit[
                    "planned_outcome_tick_at"
                ],
                "requested_at": active_permit["issued_at"],
            }
        )
        if lane == "OUTCOME":
            if active_permit.get("permit_kind") == "OUTCOME_TICK":
                expired_schedule_ids = [
                    schedule_id
                    for schedule_id in active_permit["due_schedule_ids"]
                    if _moment(now, "V32_RUNTIME_CLOCK_INVALID")
                    > _moment(
                        by_id[schedule_id]["expires_at"],
                        "V32_RUNTIME_OUTCOME_EXPIRY_INVALID",
                    )
                ]
                if expired_schedule_ids:
                    return _with_alert(
                        _outcome_permit_expired_fail_closed(
                            supervisor_store=supervisor_store,
                            supervisor=supervisor,
                            permit=active_permit,
                            now=now,
                            expired_schedule_ids=expired_schedule_ids,
                        ),
                        run_id=run_id,
                        alert_port=supervisor_alert_port,
                    )
            result = wake_runner(
                supervisor_store=supervisor_store,
                run_id=run_id,
                lane_requests=[request],
                schedule_sets=bound_schedule_sets,
                outcome_port=outcome_port,
            )
            return _with_alert(
                result, run_id=run_id, alert_port=supervisor_alert_port
            )

        if active_analysis_window is None:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_ACTIVE_ANALYSIS_WINDOW_MISSING"
            )
        next_due_at = str(active_analysis_window["next_due_at"])
        permit_deadline_at = str(
            active_analysis_window["permit_deadline_at"]
        )
        completion = analysis_port.load_durable_analysis_completion(
            permit=deepcopy(active_permit)
        )
        failure = analysis_port.load_durable_analysis_failure(
            permit=deepcopy(active_permit)
        )
        if completion is not None or failure is not None:
            result = wake_runner(
                supervisor_store=supervisor_store,
                run_id=run_id,
                lane_requests=[request],
                schedule_sets=bound_schedule_sets,
                analysis_port=analysis_port,
            )
            result = {
                **dict(result),
                "next_due_at": next_due_at,
                "permit_deadline_at": permit_deadline_at,
            }
            return _with_alert(
                result, run_id=run_id, alert_port=supervisor_alert_port
            )
        if _moment(now, "V32_RUNTIME_CLOCK_INVALID") >= _moment(
            permit_deadline_at, "V32_RUNTIME_DEADLINE_INVALID"
        ):
            return _with_alert(
                _deadline_fail_closed(
                    supervisor_store=supervisor_store,
                    supervisor=supervisor,
                    permit=active_permit,
                    now=now,
                    next_due_at=next_due_at,
                    permit_deadline_at=permit_deadline_at,
                ),
                run_id=run_id,
                alert_port=supervisor_alert_port,
            )

        cycle = int(active_permit["analysis_cycle_index"])
        external = _pending_external_action(
            mailbox=mailbox, run_id=run_id, cycle_index=cycle
        )
        if external is not None:
            # This is the object consumed by the current Codex.  Return the
            # already capacity-bounded presentation itself: adding a runtime
            # wrapper or an unbounded alert outside it would invalidate the
            # one-megabyte Agent-facing ceiling checked by its constructor.
            return external

        burst_started_ns = _monotonic_ns(clock)
        transition_digests: list[str] = []
        last_result: Mapping[str, Any] | None = None
        stop_reason = "BURST_STEP_BOUND_REACHED"
        external = None
        for _ in range(MAX_ANALYSIS_BURST_STEPS):
            step_now = _clock_time(clock)
            if _moment(step_now, "V32_RUNTIME_CLOCK_INVALID") >= _moment(
                permit_deadline_at, "V32_RUNTIME_DEADLINE_INVALID"
            ):
                if not transition_digests:
                    return _with_alert(
                        _deadline_fail_closed(
                            supervisor_store=supervisor_store,
                            supervisor=supervisor,
                            permit=active_permit,
                            now=step_now,
                            next_due_at=next_due_at,
                            permit_deadline_at=permit_deadline_at,
                        ),
                        run_id=run_id,
                        alert_port=supervisor_alert_port,
                    )
                stop_reason = "DEADLINE_REACHED_AFTER_DURABLE_SUBSTAGE"
                break
            last_result = wake_runner(
                supervisor_store=supervisor_store,
                run_id=run_id,
                lane_requests=[request],
                schedule_sets=bound_schedule_sets,
                analysis_port=analysis_port,
            )
            digest = last_result.get("durable_transition_digest")
            if isinstance(digest, str):
                transition_digests.append(digest)
            if last_result.get("lane_advance_status") in {
                "COMPLETION_SEALED",
                "FAILURE_SEALED",
            }:
                stop_reason = str(last_result["lane_advance_status"])
                break
            try:
                external = _pending_external_action(
                    mailbox=mailbox, run_id=run_id, cycle_index=cycle
                )
            except V32ProspectiveRuntimeError as exc:
                # The lane step may already be durable.  Preserve that exact
                # boundary in the response and never run another substage in
                # this wake merely because the read-only presentation failed.
                count = len(transition_digests)
                result = {
                    **_base_result(
                        run_id=run_id,
                        status="PENDING",
                        now=now,
                    ),
                    "boundary_kind": (
                        "ANALYSIS_SUBSTAGE_COMMITTED_AGENT_PRESENTATION_FAILED"
                    ),
                    "high_level_boundaries_completed_this_wake": 1,
                    "durable_state_boundaries_this_wake": count,
                    "internal_append_only_substages": count,
                    "analysis_burst_stop_reason": (
                        "AGENT_PRESENTATION_FAILED"
                    ),
                    "internal_transition_digests": transition_digests,
                    "agent_presentation_error_code": str(exc),
                    "outcome_values_read": False,
                    "permit_digest": active_permit[PERMIT_DIGEST_FIELD],
                    "next_due_at": next_due_at,
                    "permit_deadline_at": permit_deadline_at,
                }
                return _with_alert(
                    result,
                    run_id=run_id,
                    alert_port=supervisor_alert_port,
                )
            if external is not None:
                stop_reason = "CURRENT_ROOT_CODEX_REQUIRED"
                break

        count = len(transition_digests)
        if last_result is None:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_ANALYSIS_BURST_EMPTY"
            )
        if external is not None:
            # As above, the current Codex receives exactly the verified,
            # capacity-bounded envelope and no outer runtime/alert object.
            return external
        result = {
            **_base_result(run_id=run_id, status="PENDING", now=now),
            "boundary_kind": "ANALYSIS_BOUNDED_APPEND_ONLY_BURST",
            "high_level_boundaries_completed_this_wake": 1,
            "durable_state_boundaries_this_wake": count,
            "internal_append_only_substages": count,
            "analysis_burst_step_limit": MAX_ANALYSIS_BURST_STEPS,
            "analysis_burst_stop_reason": stop_reason,
            "internal_transition_digests": transition_digests,
            "analysis_burst_trace_digest": canonical_digest(
                {
                    "run_id": run_id,
                    "permit_digest": active_permit[PERMIT_DIGEST_FIELD],
                    "transition_digests": transition_digests,
                    "stop_reason": stop_reason,
                }
            ),
            "analysis_burst_monotonic_elapsed_ms": _elapsed_monotonic_ms(
                clock, burst_started_ns
            ),
            "permit_digest": active_permit[PERMIT_DIGEST_FIELD],
            "next_due_at": next_due_at,
            "permit_deadline_at": permit_deadline_at,
            "last_lane_advance_status": last_result.get(
                "lane_advance_status"
            ),
        }
        return _with_alert(
            result, run_id=run_id, alert_port=supervisor_alert_port
        )

    due_ids, next_due_at = _next_due(
        checkpoint=supervisor, by_id=by_id, now=now
    )
    if due_ids:
        planned_tick_at = min(
            str(by_id[schedule_id]["outcome_not_before"])
            for schedule_id in due_ids
        )
        result = wake_runner(
            supervisor_store=supervisor_store,
            run_id=run_id,
            lane_requests=[
                {
                    "lane": "OUTCOME",
                    "planned_tick_at": planned_tick_at,
                    "requested_at": now,
                }
            ],
            schedule_sets=bound_schedule_sets,
            outcome_port=outcome_port,
        )
        return _with_alert(
            {**dict(result), "next_due_at": planned_tick_at},
            run_id=run_id,
            alert_port=supervisor_alert_port,
        )

    audit_result = _audit_gate_or_next(
        supervisor=supervisor,
        dynamic_store=dynamic_store,
        revision_store=revision_store,
        completion_store=audit_completion_store,
        audit_lane=audit_lane,
        cycle_audit_policy=cycle_audit_policy,
    )
    if audit_result is not None:
        result = {
            **_base_result(run_id=run_id, status="AUDIT_ADVANCED", now=now),
            "boundary_kind": f"{audit_result['boundary_type']}_AUDIT_ADVANCED",
            "high_level_boundaries_completed_this_wake": 1,
            "durable_state_boundaries_this_wake": 1,
            "audit_result": deepcopy(dict(audit_result)),
            "next_due_at": next_due_at,
        }
        return _with_alert(
            result, run_id=run_id, alert_port=supervisor_alert_port
        )

    outcome_audit_result = _outcome_audit_or_next(
        supervisor=supervisor,
        outcome_store=outcome_store,
        revision_store=revision_store,
        audit_lane=audit_lane,
        cycle_audit_policy=cycle_audit_policy,
        schedule_by_id=by_id,
    )
    if outcome_audit_result is not None:
        result = {
            **_base_result(run_id=run_id, status="AUDIT_ADVANCED", now=now),
            "boundary_kind": "OUTCOME_AUDIT_ADVANCED",
            "high_level_boundaries_completed_this_wake": 1,
            "durable_state_boundaries_this_wake": 1,
            "audit_result": deepcopy(dict(outcome_audit_result)),
            "next_due_at": next_due_at,
        }
        return _with_alert(
            result, run_id=run_id, alert_port=supervisor_alert_port
        )

    recovery_audit_result = _recovery_audit_or_next(
        supervisor=supervisor,
        revision_store=revision_store,
        audit_lane=audit_lane,
        cycle_audit_policy=cycle_audit_policy,
        supervision_evidence_port=supervision_evidence_port,
    )
    if recovery_audit_result is not None:
        result = {
            **_base_result(run_id=run_id, status="AUDIT_ADVANCED", now=now),
            "boundary_kind": "RECOVERY_AUDIT_ADVANCED",
            "high_level_boundaries_completed_this_wake": 1,
            "durable_state_boundaries_this_wake": 1,
            "audit_result": deepcopy(dict(recovery_audit_result)),
            "next_due_at": next_due_at,
        }
        return _with_alert(
            result, run_id=run_id, alert_port=supervisor_alert_port
        )

    if supervisor["status"] == "TERMINAL_COMPLETE":
        required_audits, recovery_audits = _terminal_audit_materials(
            run_id=run_id,
            revision_store=revision_store,
            supervision_evidence_port=supervision_evidence_port,
        )
        try:
            dynamic = dynamic_store.load_checkpoint(run_id=run_id)
            outcome = outcome_store.load_checkpoint(run_id=run_id)
        except Exception as exc:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_TERMINAL_CHECKPOINT_LOAD_FAILED"
            ) from exc
        if outcome.get("status") != "TERMINAL":
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_TERMINAL_OUTCOME_CHECKPOINT_REQUIRED"
            )
        if dynamic.get("status") == "OUTCOME_TAIL":
            try:
                marked = dynamic_store.mark_terminal(
                    run_id=run_id,
                    expected_checkpoint_digest=dynamic[
                        "dynamic_research_checkpoint_digest"
                    ],
                    terminal_outcome_checkpoint_digest=outcome[
                        "checkpoint_digest"
                    ],
                    completed_at=now,
                )
            except Exception as exc:
                raise V32ProspectiveRuntimeError(
                    "V32_RUNTIME_DYNAMIC_TERMINAL_MARK_FAILED"
                ) from exc
            result = {
                **_base_result(
                    run_id=run_id, status="TERMINAL_MARKED", now=now
                ),
                "boundary_kind": "DYNAMIC_TERMINAL_MARKED",
                "high_level_boundaries_completed_this_wake": 1,
                "durable_state_boundaries_this_wake": 1,
                "dynamic_checkpoint_digest": marked[
                    "dynamic_research_checkpoint_digest"
                ],
                "supervisor_checkpoint_digest": supervisor[
                    CHECKPOINT_DIGEST_FIELD
                ],
                "required_audit_directory_count": len(required_audits),
                "recovery_audit_directory_count": len(recovery_audits),
            }
            return _with_alert(
                result, run_id=run_id, alert_port=supervisor_alert_port
            )
        if dynamic.get("status") != "TERMINAL":
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_DYNAMIC_TERMINAL_SEQUENCE_INVALID"
            )
        if terminal_seal_port is None:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_TERMINAL_SEAL_PORT_REQUIRED"
            )
        try:
            terminal_pointer = terminal_seal_port.load_terminal_pointer(
                run_id=run_id
            )
        except Exception as exc:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_TERMINAL_POINTER_LOAD_FAILED"
            ) from exc
        if terminal_pointer is not None:
            result = {
                **_base_result(
                    run_id=run_id, status="TERMINAL_SEALED", now=now
                ),
                "boundary_kind": "NO_MUTATION_TERMINAL_SEALED",
                "high_level_boundaries_completed_this_wake": 0,
                "durable_state_boundaries_this_wake": 0,
                "supervisor_checkpoint_digest": supervisor[
                    CHECKPOINT_DIGEST_FIELD
                ],
                "terminal_pointer_digest": terminal_pointer.get(
                    "v32_terminal_pointer_digest"
                ),
            }
            return _with_alert(
                result, run_id=run_id, alert_port=supervisor_alert_port
            )
        supervision_bindings: Mapping[str, Any] = {
            "supervisor_observation_bindings": [],
            "deterministic_recovery_receipt_bindings": [],
        }
        if supervision_evidence_port is not None:
            try:
                supervision_bindings = (
                    supervision_evidence_port.load_material_bindings(
                        run_id=run_id
                    )
                )
            except Exception as exc:
                raise V32ProspectiveRuntimeError(
                    "V32_RUNTIME_SUPERVISION_BINDING_LOAD_FAILED"
                ) from exc
        try:
            sealed = terminal_seal_port.seal_terminal(
                run_id=run_id,
                sealed_at=now,
                supervisor_checkpoint=supervisor,
                dynamic_checkpoint=dynamic,
                outcome_checkpoint=outcome,
                required_audit_materials=required_audits,
                recovery_audit_materials=recovery_audits,
                supervision_material_bindings=supervision_bindings,
            )
        except Exception as exc:
            raise V32ProspectiveRuntimeError(
                "V32_RUNTIME_TERMINAL_SEAL_FAILED"
            ) from exc
        result = {
            **_base_result(run_id=run_id, status="TERMINAL_SEALED", now=now),
            "boundary_kind": "FINAL_TERMINAL_RECEIPT_AND_POINTER_SEALED",
            "high_level_boundaries_completed_this_wake": 1,
            "durable_state_boundaries_this_wake": 1,
            "supervisor_checkpoint_digest": supervisor[
                CHECKPOINT_DIGEST_FIELD
            ],
            "terminal_seal": deepcopy(dict(sealed)),
        }
        return _with_alert(
            result, run_id=run_id, alert_port=supervisor_alert_port
        )

    last_decision = supervisor.get("last_analysis_decision_at")
    cadence_ready = last_decision is None or _moment(
        now, "V32_RUNTIME_CLOCK_INVALID"
    ) >= _moment(last_decision, "V32_RUNTIME_LAST_DECISION_INVALID") + timedelta(
        seconds=ANALYSIS_INTERVAL_SECONDS
    )
    if supervisor["status"] == "READY" and cadence_ready:
        cycle_index = supervisor["next_analysis_cycle_index"]
        load_prepared = getattr(
            analysis_port, "load_durable_prepared_source", None
        )
        prepare_source = getattr(analysis_port, "prepare_cycle_source", None)
        if not callable(load_prepared) or not callable(prepare_source):
            error = V32ProspectiveRuntimeError(
                "V32_RUNTIME_SOURCE_PREPARATION_PORT_INVALID"
            )
            result = _source_preparation_fail_closed(
                supervisor_store=supervisor_store,
                supervisor=supervisor,
                now=now,
                failure_code="SOURCE_SCHEMA_OR_DIGEST_INVALID",
                error=error,
            )
            return _with_alert(
                result, run_id=run_id, alert_port=supervisor_alert_port
            )
        try:
            prepared = load_prepared(
                run_id=run_id,
                cycle_index=cycle_index,
                supervisor_checkpoint=deepcopy(supervisor),
            )
            if prepared is None:
                source_result = prepare_source(
                    run_id=run_id,
                    cycle_index=cycle_index,
                    supervisor_checkpoint=deepcopy(supervisor),
                )
                if (
                    not isinstance(source_result, Mapping)
                    or source_result.get("state_changed") is not True
                    or source_result.get("run_id") != run_id
                    or source_result.get("cycle_index") != cycle_index
                    or source_result.get("preparation_status") != "SOURCE_READY"
                    or isinstance(
                        source_result.get("internal_append_only_substage_count"),
                        bool,
                    )
                    or not isinstance(
                        source_result.get("internal_append_only_substage_count"),
                        int,
                    )
                    or not 1
                    <= source_result["internal_append_only_substage_count"]
                    <= 3
                ):
                    raise V32ProspectiveRuntimeError(
                        "V32_RUNTIME_SOURCE_PREPARATION_RESULT_INVALID"
                    )
                substage_sequence = source_result.get(
                    "internal_append_only_substages"
                )
                if (
                    not isinstance(substage_sequence, list)
                    or tuple(substage_sequence)
                    not in {
                        # A fresh preparation or one of its two legal
                        # crash-prefix continuations.
                        (
                            "SOURCE_QUALIFICATION_SEALED",
                            "SOURCE_ADMISSION_SEALED",
                            "SOURCE_REPLAY_SEALED",
                        ),
                        (
                            "SOURCE_ADMISSION_SEALED",
                            "SOURCE_REPLAY_SEALED",
                        ),
                        ("SOURCE_REPLAY_SEALED",),
                    }
                    or len(substage_sequence)
                    != source_result["internal_append_only_substage_count"]
                ):
                    raise V32ProspectiveRuntimeError(
                        "V32_RUNTIME_SOURCE_PREPARATION_RESULT_INVALID"
                    )
                source_ready_at = _time(
                    clock(), "V32_RUNTIME_CLOCK_INVALID"
                )
                prepared = _verify_prepared_source_projection(
                    {
                        key: source_result[key]
                        for key in {
                            "run_id",
                            "cycle_index",
                            "source_cutoff_at",
                            "admitted_at",
                            "replayed_at",
                            "source_qualification_digest",
                            "source_admission_digest",
                            "durable_source_replay_receipt_digest",
                        }
                    },
                    run_id=run_id,
                    cycle_index=cycle_index,
                    observed_at=source_ready_at,
                )
                result = {
                    **_base_result(
                        run_id=run_id,
                        status="SOURCE_READY",
                        now=source_ready_at,
                    ),
                    "boundary_kind": "SOURCE_PREPARATION_COMPLETED",
                    "high_level_boundaries_completed_this_wake": 1,
                    "durable_state_boundaries_this_wake": 1,
                    "outcome_values_read": False,
                    "cycle_index": cycle_index,
                    "source_preparation_status": source_result[
                        "preparation_status"
                    ],
                    "source_cutoff_at": source_result.get(
                        "source_cutoff_at"
                    ),
                    "durable_transition_digest": source_result.get(
                        "durable_transition_digest"
                    ),
                    "internal_append_only_substage_count": source_result[
                        "internal_append_only_substage_count"
                    ],
                    "internal_append_only_substages": list(
                        source_result["internal_append_only_substages"]
                    ),
                    "next_due_at": next_due_at,
                }
                return _with_alert(
                    result,
                    run_id=run_id,
                    alert_port=supervisor_alert_port,
                )
            prepared = _verify_prepared_source_projection(
                prepared,
                run_id=run_id,
                cycle_index=cycle_index,
                observed_at=now,
            )
        except Exception as exc:
            failure_code = _source_preparation_supervisor_failure_code(exc)
            result = _source_preparation_fail_closed(
                supervisor_store=supervisor_store,
                supervisor=supervisor,
                now=now,
                failure_code=failure_code,
                error=exc,
            )
            return _with_alert(
                result, run_id=run_id, alert_port=supervisor_alert_port
            )
        result = wake_runner(
            supervisor_store=supervisor_store,
            run_id=run_id,
            lane_requests=[
                {
                    "lane": "ANALYSIS",
                    # Legacy field name: this is the verified source cutoff,
                    # not admission/open/sealed decision time.
                    "analysis_decision_at": prepared["source_cutoff_at"],
                    "issued_at": now,
                }
            ],
            schedule_sets=bound_schedule_sets,
            analysis_port=analysis_port,
        )
        return _with_alert(
            {**dict(result), "next_due_at": next_due_at},
            run_id=run_id,
            alert_port=supervisor_alert_port,
        )

    result = {
        **_base_result(run_id=run_id, status="NOT_DUE", now=now),
        "boundary_kind": "NO_MUTATION_NOT_DUE",
        "high_level_boundaries_completed_this_wake": 0,
        "durable_state_boundaries_this_wake": 0,
        "next_due_at": next_due_at,
        "next_analysis_not_before": (
            None
            if last_decision is None
            else (
                _moment(last_decision, "V32_RUNTIME_LAST_DECISION_INVALID")
                + timedelta(seconds=ANALYSIS_INTERVAL_SECONDS)
            )
            .isoformat()
            .replace("+00:00", "Z")
        ),
    }
    return _with_alert(
        result, run_id=run_id, alert_port=supervisor_alert_port
    )


__all__ = [
    "ANALYSIS_INTERVAL_SECONDS",
    "MAX_ANALYSIS_BURST_STEPS",
    "V32ProspectiveRuntimeError",
    "initialize_v32_prospective_runtime_v1",
    "resolve_v32_active_analysis_agent_window_v1",
    "route_v32_prospective_wake_v1",
    "verify_v32_active_analysis_agent_window_v1",
]
