"""Single-transition orchestration for the V3.3 market-cycle core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, TypeVar

from ...domain.market_cycle.contracts import (
    RUN_NEXT_ACTION,
    ArtifactRef,
    BehaviorPlan,
    CycleRequest,
    HypothesisRecord,
    InputSnapshot,
    Outcome,
    Review,
    RunState,
    VerifiedMemoryItem,
    normalize_verified_memory_items,
)
from ...domain.market_cycle.theory import V332_THEORY_IDENTITY
from ...domain.market_cycle.analysis import copy_agent_decision_to_behavior_plan
from .analysis import analyze_snapshot
from .outcomes import capture_outcome
from .ports import (
    AgentAnalysisPending,
    AgentDecisionDeadlineExpired,
    AgentPort,
    AgentReviewDeadlineExpired,
    AgentReviewPending,
    ClockPort,
    ControllerDispatchPort,
    CycleRepository,
    DecisionContextPort,
    MarketCyclePortError,
    MarketDataPort,
    OutcomePort,
)
from .review import review_cycle
from .source import capture_input_snapshot


@dataclass(frozen=True, slots=True)
class AdvanceResult:
    state: RunState
    changed: bool
    pending_reason: str | None = None
    pending_ref: str | None = None


ArtifactT = TypeVar("ArtifactT", InputSnapshot, HypothesisRecord, BehaviorPlan, Outcome, Review)

CONTROLLER_DECISION_DEADLINE_EXPIRED = "CONTROLLER_DECISION_DEADLINE_EXPIRED"
CONTROLLER_DAILY_DEEP_DEADLINE_EXPIRED = "CONTROLLER_DAILY_DEEP_DEADLINE_EXPIRED"
CONTROLLER_REVIEW_DEADLINE_EXPIRED = "CONTROLLER_REVIEW_DEADLINE_EXPIRED"

_CONTROLLER_WORKER_STAGES = {
    "daily-deep-v1": "INPUT_SEALED",
    "decision-v1": "INPUT_SEALED",
    "review-v1": "OUTCOME_SEALED",
}
_CONTROLLER_WORKER_EXPIRY_REASONS = {
    "daily-deep-v1": CONTROLLER_DAILY_DEEP_DEADLINE_EXPIRED,
    "decision-v1": CONTROLLER_DECISION_DEADLINE_EXPIRED,
    "review-v1": CONTROLLER_REVIEW_DEADLINE_EXPIRED,
}
CONTROLLER_CYCLE_WORKER_IDS = tuple(_CONTROLLER_WORKER_STAGES)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _reference(state: RunState, artifact_type: str) -> ArtifactRef:
    try:
        return next(ref for ref in state.artifact_refs if ref.artifact_type == artifact_type)
    except StopIteration as exc:
        raise ValueError(f"run state lacks {artifact_type}") from exc


class CycleService:
    """Application owner of legal next-stage choices; performs one per wake."""

    def __init__(
        self,
        *,
        market_data: MarketDataPort,
        agent: AgentPort,
        clock: ClockPort,
        repository: CycleRepository,
        outcome: OutcomePort,
        theory_fragments: Mapping[str, str],
        controller_dispatch: ControllerDispatchPort | None = None,
        decision_context: DecisionContextPort | None = None,
        verified_memory: Iterable[
            VerifiedMemoryItem | Mapping[str, Any]
        ] = (),
    ) -> None:
        if not theory_fragments or not all(
            isinstance(name, str)
            and name
            and isinstance(content, str)
            and content
            for name, content in theory_fragments.items()
        ):
            raise ValueError("verified named theory fragments are required")
        self._market_data = market_data
        self._agent = agent
        self._clock = clock
        self._repository = repository
        self._outcome = outcome
        self._controller_dispatch = controller_dispatch
        self._decision_context = decision_context
        self._theory_fragments = dict(theory_fragments)
        self._verified_memory = normalize_verified_memory_items(verified_memory)

    def _controller_method(self, name: str) -> Any:
        controller = self._controller_dispatch
        method = None if controller is None else getattr(controller, name, None)
        if not callable(method):
            raise MarketCyclePortError("MARKET_CYCLE_CONTROLLER_DISPATCH_UNAVAILABLE")
        return method

    def _decision_delivery_present(self, cycle_id: str) -> bool:
        present = getattr(self._agent, "delivery_present", None)
        if not callable(present):
            raise MarketCyclePortError(
                "MARKET_CYCLE_AGENT_DECISION_TRANSPORT_UNAVAILABLE"
            )
        observed = present(cycle_id)
        if type(observed) is not bool:
            raise MarketCyclePortError(
                "MARKET_CYCLE_AGENT_DECISION_TRANSPORT_INVALID"
            )
        return observed

    def _review_delivery_present(self, cycle_id: str) -> bool:
        present = getattr(self._agent, "review_delivery_present", None)
        if not callable(present):
            raise MarketCyclePortError(
                "MARKET_CYCLE_AGENT_REVIEW_TRANSPORT_UNAVAILABLE"
            )
        observed = present(cycle_id)
        if type(observed) is not bool:
            raise MarketCyclePortError(
                "MARKET_CYCLE_AGENT_REVIEW_TRANSPORT_INVALID"
            )
        return observed

    def _current_state(self, cycle_id: str) -> RunState:
        recovered = self._repository.recover_pending(cycle_id)
        return recovered or self._repository.load_state(cycle_id)

    def _require_worker_stage(self, cycle_id: str, worker_id: str) -> RunState:
        expected_stage = _CONTROLLER_WORKER_STAGES.get(worker_id)
        if expected_stage is None:
            raise MarketCyclePortError("MARKET_CYCLE_CONTROLLER_WORKER_ID_INVALID")
        state = self._current_state(cycle_id)
        if state.terminal or state.stage != expected_stage:
            terminal = "TERMINAL" if state.terminal else "NONTERMINAL"
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_WORKER_STAGE_INVALID:"
                f"{worker_id}:"
                f"{state.stage}:{terminal}"
            )
        return state

    def _require_worker_output_absent(self, cycle_id: str, worker_id: str) -> None:
        if worker_id == "decision-v1" and self._decision_delivery_present(cycle_id):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_AGENT_DECISION_DELIVERY_PRESENT"
            )
        if worker_id == "review-v1" and self._review_delivery_present(cycle_id):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_AGENT_REVIEW_DELIVERY_PRESENT"
            )

    def _recover_worker(self, cycle_id: str, worker_id: str) -> Mapping[str, Any]:
        value = self._controller_method("recover_worker")(cycle_id, worker_id)
        if not isinstance(value, Mapping):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_DISPATCH_RECORD_INVALID"
            )
        return value

    def _delivery_deadline(self, cycle_id: str, worker_id: str) -> str:
        dispatch = self._recover_worker(cycle_id, worker_id)
        status = dispatch.get("status")
        if status not in {"SPAWN_REQUESTED", "DISPATCHED", "COMPLETED"}:
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_WORKER_NOT_DISPATCHED:"
                f"{worker_id}:{status or 'UNKNOWN'}"
            )
        deadline = dispatch.get("hard_stop_at")
        if type(deadline) is not str or not deadline:
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_DISPATCH_RECORD_INVALID"
            )
        return deadline

    def _require_worker_completed(self, cycle_id: str, worker_id: str) -> None:
        dispatch = self._recover_worker(cycle_id, worker_id)
        if (
            dispatch.get("status") != "COMPLETED"
            or dispatch.get("recovery_action") != "COMPLETED"
        ):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_WORKER_COMPLETION_REQUIRED:"
                f"{worker_id}"
            )

    @staticmethod
    def _dispatch_id(record: Mapping[str, Any]) -> str:
        if not isinstance(record, Mapping):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_DISPATCH_RECORD_INVALID"
            )
        dispatch_id = record.get("dispatch_id")
        if type(dispatch_id) is not str or not dispatch_id:
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_DISPATCH_RECORD_INVALID"
            )
        return dispatch_id

    def controller_status(self) -> Mapping[str, Any]:
        return self._controller_method("status")()

    def controller_prepare_worker(
        self,
        cycle_id: str,
        worker_id: str,
        task_path: str | Path,
    ) -> Mapping[str, Any]:
        with self._repository.locked(cycle_id):
            self._require_worker_stage(cycle_id, worker_id)
            self._require_worker_output_absent(cycle_id, worker_id)
            return self._controller_method("prepare_worker")(
                cycle_id, worker_id, task_path
            )

    def controller_materialize_worker_task(
        self, cycle_id: str, worker_id: str
    ) -> Path:
        with self._repository.locked(cycle_id):
            self._require_worker_stage(cycle_id, worker_id)
            self._require_worker_output_absent(cycle_id, worker_id)
            value = self._controller_method("materialize_worker_task")(
                cycle_id, worker_id
            )
            if not isinstance(value, Path):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_WORKER_TASK_INVALID"
                )
            return value

    def controller_mark_worker_spawn_requested(
        self, cycle_id: str, worker_id: str, dispatch_id: str
    ) -> Mapping[str, Any]:
        with self._repository.locked(cycle_id):
            self._require_worker_stage(cycle_id, worker_id)
            self._require_worker_output_absent(cycle_id, worker_id)
            return self._controller_method("mark_spawn_requested")(
                cycle_id, worker_id, dispatch_id
            )

    def controller_acknowledge_worker_spawn(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        execution_ref: str,
    ) -> Mapping[str, Any]:
        with self._repository.locked(cycle_id):
            self._require_worker_stage(cycle_id, worker_id)
            return self._controller_method("acknowledge_spawn")(
                cycle_id, worker_id, dispatch_id, execution_ref
            )

    def controller_admit_worker_result_for_delivery(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        """Validate a Worker result without creating a delivery artifact."""

        with self._repository.locked(cycle_id):
            self._require_worker_stage(cycle_id, worker_id)
            self._require_worker_output_absent(cycle_id, worker_id)
            value = self._controller_method(
                "admit_worker_result_for_delivery"
            )(cycle_id, worker_id)
            if not isinstance(value, Mapping):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_RESULT_ADMISSION_INVALID"
                )
            return dict(value)

    def controller_complete_worker(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        output_sha256: str,
    ) -> Mapping[str, Any]:
        """Bind one timely Worker output before releasing the dispatch lane."""

        with self._repository.locked(cycle_id):
            self._require_worker_stage(cycle_id, worker_id)
            if worker_id == "decision-v1" and not self._decision_delivery_present(
                cycle_id
            ):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_AGENT_DECISION_DELIVERY_MISSING"
                )
            if worker_id == "review-v1" and not self._review_delivery_present(
                cycle_id
            ):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_AGENT_REVIEW_DELIVERY_MISSING"
                )
            return self._controller_method("complete_worker")(
                cycle_id, worker_id, dispatch_id, output_sha256
            )

    def controller_recover_worker(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        with self._repository.locked(cycle_id):
            self._require_worker_stage(cycle_id, worker_id)
            return self._recover_worker(cycle_id, worker_id)

    def controller_prepare_agent_decision(
        self,
        cycle_id: str,
        task_path: str | Path,
    ) -> Mapping[str, Any]:
        """Deprecated name; delegates to the single generic Worker owner."""

        return self.controller_prepare_worker(cycle_id, "decision-v1", task_path)

    def controller_mark_spawn_requested(
        self, cycle_id: str, dispatch_id: str
    ) -> Mapping[str, Any]:
        return self.controller_mark_worker_spawn_requested(
            cycle_id, "decision-v1", dispatch_id
        )

    def controller_acknowledge_spawn(
        self, cycle_id: str, dispatch_id: str, execution_ref: str
    ) -> Mapping[str, Any]:
        return self.controller_acknowledge_worker_spawn(
            cycle_id, "decision-v1", dispatch_id, execution_ref
        )

    def controller_complete_agent_decision(
        self, cycle_id: str, dispatch_id: str, delivery_sha256: str
    ) -> Mapping[str, Any]:
        return self.controller_complete_worker(
            cycle_id, "decision-v1", dispatch_id, delivery_sha256
        )

    def controller_recover_agent_decision(
        self, cycle_id: str
    ) -> Mapping[str, Any]:
        return self.controller_recover_worker(cycle_id, "decision-v1")

    def controller_expire_agent_decision(
        self, cycle_id: str, reason_code: str
    ) -> AdvanceResult:
        """Close one overdue Agent decision without a business artifact."""

        if (
            type(reason_code) is not str
            or reason_code != CONTROLLER_DECISION_DEADLINE_EXPIRED
        ):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_DECISION_EXPIRY_REASON_INVALID"
            )
        with self._repository.locked(cycle_id):
            state = self._current_state(cycle_id)
            return self._expire_agent_decision_locked(state, reason_code)

    def _expire_agent_decision_locked(
        self, state: RunState, reason_code: str
    ) -> AdvanceResult:
        cycle_id = state.cycle_id
        if self._decision_delivery_present(cycle_id):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_AGENT_DECISION_DELIVERY_PRESENT"
            )

        require_expired = self._controller_method("require_worker_deadline_expired")
        mark_expired = self._controller_method("mark_worker_expired")
        if state.terminal:
            if (
                state.stage != "ANALYSIS_FAILED"
                or state.failure_reason != reason_code
            ):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_DECISION_EXPIRY_CONFLICT"
                )
            dispatch = require_expired(cycle_id, "decision-v1")
            dispatch_id = dispatch.get("dispatch_id")
            if dispatch_id is not None:
                mark_expired(
                    cycle_id,
                    "decision-v1",
                    self._dispatch_id(dispatch),
                    reason_code,
                )
            return AdvanceResult(
                state=state,
                changed=False,
                pending_reason=reason_code,
            )
        if state.stage != "INPUT_SEALED":
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_AGENT_DECISION_STAGE_INVALID:"
                f"{state.stage}:NONTERMINAL"
            )

        dispatch = require_expired(cycle_id, "decision-v1")
        dispatch_id = dispatch.get("dispatch_id")
        failed = self._repository.transition(
            expected=state,
            artifacts=(),
            next_stage="ANALYSIS_FAILED",
            next_action=None,
            terminal=True,
            failure_reason=reason_code,
        )
        if dispatch_id is not None:
            mark_expired(
                cycle_id,
                "decision-v1",
                self._dispatch_id(dispatch),
                reason_code,
            )
        return AdvanceResult(
            state=failed,
            changed=True,
            pending_reason=reason_code,
        )

    def _expire_agent_review_locked(self, state: RunState) -> AdvanceResult:
        cycle_id = state.cycle_id
        reason_code = CONTROLLER_REVIEW_DEADLINE_EXPIRED
        if self._review_delivery_present(cycle_id):
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_AGENT_REVIEW_DELIVERY_PRESENT"
            )
        require_expired = self._controller_method("require_worker_deadline_expired")
        mark_expired = self._controller_method("mark_worker_expired")
        if state.terminal:
            if state.stage != "REVIEW_FAILED" or state.failure_reason != reason_code:
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_REVIEW_EXPIRY_CONFLICT"
                )
            dispatch = require_expired(cycle_id, "review-v1")
            mark_expired(
                cycle_id,
                "review-v1",
                self._dispatch_id(dispatch),
                reason_code,
            )
            return AdvanceResult(state, False, pending_reason=reason_code)
        if state.stage != "OUTCOME_SEALED":
            raise MarketCyclePortError(
                "MARKET_CYCLE_CONTROLLER_AGENT_REVIEW_STAGE_INVALID:"
                f"{state.stage}:NONTERMINAL"
            )
        dispatch = require_expired(cycle_id, "review-v1")
        failed = self._repository.transition(
            expected=state,
            artifacts=(),
            next_stage="REVIEW_FAILED",
            next_action=None,
            terminal=True,
            failure_reason=reason_code,
        )
        mark_expired(
            cycle_id,
            "review-v1",
            self._dispatch_id(dispatch),
            reason_code,
        )
        return AdvanceResult(failed, True, pending_reason=reason_code)

    def controller_expire_worker(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        """Expire one durable Worker with a fixed kind-owned reason."""

        reason_code = _CONTROLLER_WORKER_EXPIRY_REASONS.get(worker_id)
        if reason_code is None:
            raise MarketCyclePortError("MARKET_CYCLE_CONTROLLER_WORKER_ID_INVALID")
        if worker_id == "decision-v1":
            result = self.controller_expire_agent_decision(cycle_id, reason_code)
            return {
                "domain_changed": result.changed,
                "reason_code": reason_code,
                "state": result.state.to_dict(),
            }
        with self._repository.locked(cycle_id):
            state = self._current_state(cycle_id)
            if worker_id == "review-v1":
                result = self._expire_agent_review_locked(state)
                return {
                    "domain_changed": result.changed,
                    "reason_code": reason_code,
                    "state": result.state.to_dict(),
                }
            self._require_worker_stage(cycle_id, worker_id)
            dispatch = self._controller_method("require_worker_deadline_expired")(
                cycle_id, worker_id
            )
            worker = self._controller_method("mark_worker_expired")(
                cycle_id,
                worker_id,
                self._dispatch_id(dispatch),
                reason_code,
            )
            return {
                "domain_changed": False,
                "reason_code": reason_code,
                "state": state.to_dict(),
                "worker": dict(worker),
            }

    def create(self, request: CycleRequest) -> RunState:
        if request.analysis_profile != "COLD":
            raise MarketCyclePortError(
                f"ANALYSIS_PROFILE_NOT_READY:{request.analysis_profile}"
            )
        return self._repository.create(request)

    def status(self, cycle_id: str) -> RunState:
        return self._repository.load_state(cycle_id)

    def deliver_agent_decision(
        self,
        cycle_id: str,
        decision_bytes: bytes,
        *,
        media_type: str = "text/markdown",
    ) -> str:
        """Wrap verbatim Agent text only at the exact pending analysis stage."""

        with self._repository.locked(cycle_id):
            recovered = self._repository.recover_pending(cycle_id)
            state = recovered or self._repository.load_state(cycle_id)
            if state.terminal or state.stage != "INPUT_SEALED":
                terminal = "TERMINAL" if state.terminal else "NONTERMINAL"
                raise MarketCyclePortError(
                    "MARKET_CYCLE_AGENT_DECISION_STAGE_INVALID:"
                    f"{state.stage}:{terminal}"
                )
            persist = getattr(self._agent, "persist_decision", None)
            if not callable(persist):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_AGENT_DECISION_TRANSPORT_UNAVAILABLE"
                )
            deadline_at = self._delivery_deadline(cycle_id, "decision-v1")
            try:
                return persist(
                    cycle_id,
                    decision_bytes,
                    media_type=media_type,
                    deadline_at=deadline_at,
                )
            except AgentDecisionDeadlineExpired:
                result = self._expire_agent_decision_locked(
                    state, CONTROLLER_DECISION_DEADLINE_EXPIRED
                )
                return str(result.pending_reason)

    def deliver_goal_decision(
        self,
        cycle_id: str,
        decision_bytes: bytes,
        *,
        media_type: str = "text/markdown",
    ) -> str:
        """Seal the current Goal's verbatim decision without a Worker permit."""

        with self._repository.locked(cycle_id):
            state = self._current_state(cycle_id)
            if state.terminal or state.stage != "INPUT_SEALED":
                terminal = "TERMINAL" if state.terminal else "NONTERMINAL"
                raise MarketCyclePortError(
                    "MARKET_CYCLE_GOAL_DECISION_STAGE_INVALID:"
                    f"{state.stage}:{terminal}"
                )
            persist = getattr(self._agent, "persist_goal_decision", None)
            if not callable(persist):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_GOAL_DECISION_TRANSPORT_UNAVAILABLE"
                )
            return persist(
                cycle_id,
                decision_bytes,
                media_type=media_type,
            )

    def deliver_worker_result(
        self,
        cycle_id: str,
        worker_id: str,
        *,
        media_type: str = "text/markdown",
        expected_body_bytes: bytes | None = None,
    ) -> Mapping[str, Any]:
        """Admit one V3.3.2 result, then persist exactly its validated body."""

        if worker_id not in {"decision-v1", "review-v1"}:
            raise MarketCyclePortError(
                "MARKET_CYCLE_WORKER_RESULT_DELIVERY_NOT_APPLICABLE"
            )
        if expected_body_bytes is not None and not isinstance(
            expected_body_bytes, bytes
        ):
            raise MarketCyclePortError(
                "MARKET_CYCLE_WORKER_RESULT_EXPECTED_BODY_INVALID"
            )
        with self._repository.locked(cycle_id):
            state = self._current_state(cycle_id)
            expected_stage = (
                "INPUT_SEALED"
                if worker_id == "decision-v1"
                else "OUTCOME_SEALED"
            )
            if state.terminal or state.stage != expected_stage:
                terminal = "TERMINAL" if state.terminal else "NONTERMINAL"
                raise MarketCyclePortError(
                    "MARKET_CYCLE_WORKER_RESULT_DELIVERY_STAGE_INVALID:"
                    f"{worker_id}:{state.stage}:{terminal}"
                )
            self._require_worker_output_absent(cycle_id, worker_id)
            admitted = self._controller_method(
                "admit_worker_result_for_delivery"
            )(cycle_id, worker_id)
            if not isinstance(admitted, Mapping):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_RESULT_ADMISSION_INVALID"
                )
            body = admitted.get("body_markdown")
            if not isinstance(body, str) or not body.strip():
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_RESULT_ADMISSION_INVALID"
                )
            try:
                body_bytes = body.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_RESULT_ADMISSION_INVALID"
                ) from exc
            if (
                expected_body_bytes is not None
                and expected_body_bytes != body_bytes
            ):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_WORKER_RESULT_BODY_MISMATCH"
                )
            deadline_at = admitted.get("hard_stop_at")
            if type(deadline_at) is not str or not deadline_at:
                raise MarketCyclePortError(
                    "MARKET_CYCLE_CONTROLLER_RESULT_ADMISSION_INVALID"
                )
            if worker_id == "decision-v1":
                persist = getattr(self._agent, "persist_decision", None)
                deadline_error = AgentDecisionDeadlineExpired
            else:
                persist = getattr(self._agent, "persist_review", None)
                deadline_error = AgentReviewDeadlineExpired
            if not callable(persist):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_AGENT_RESULT_TRANSPORT_UNAVAILABLE"
                )
            try:
                delivery_status = persist(
                    cycle_id,
                    body_bytes,
                    media_type=media_type,
                    deadline_at=deadline_at,
                )
            except deadline_error:
                if worker_id == "decision-v1":
                    expired = self._expire_agent_decision_locked(
                        state, CONTROLLER_DECISION_DEADLINE_EXPIRED
                    )
                else:
                    expired = self._expire_agent_review_locked(state)
                return {
                    "cycle_id": cycle_id,
                    "worker_id": worker_id,
                    "delivery_status": str(expired.pending_reason),
                    "result_admission": {
                        key: value
                        for key, value in admitted.items()
                        if key != "body_markdown"
                    },
                }
            return {
                "cycle_id": cycle_id,
                "worker_id": worker_id,
                "delivery_status": str(delivery_status),
                "result_admission": {
                    key: value
                    for key, value in admitted.items()
                    if key != "body_markdown"
                },
            }

    def deliver_agent_review(
        self,
        cycle_id: str,
        review_bytes: bytes,
        *,
        media_type: str = "text/markdown",
    ) -> str:
        """Wrap verbatim Agent review text only after Outcome is sealed."""

        with self._repository.locked(cycle_id):
            recovered = self._repository.recover_pending(cycle_id)
            state = recovered or self._repository.load_state(cycle_id)
            if state.terminal or state.stage != "OUTCOME_SEALED":
                terminal = "TERMINAL" if state.terminal else "NONTERMINAL"
                raise MarketCyclePortError(
                    "MARKET_CYCLE_AGENT_REVIEW_STAGE_INVALID:"
                    f"{state.stage}:{terminal}"
                )
            persist = getattr(self._agent, "persist_review", None)
            if not callable(persist):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_AGENT_REVIEW_TRANSPORT_UNAVAILABLE"
                )
            deadline_at = self._delivery_deadline(cycle_id, "review-v1")
            try:
                return persist(
                    cycle_id,
                    review_bytes,
                    media_type=media_type,
                    deadline_at=deadline_at,
                )
            except AgentReviewDeadlineExpired:
                result = self._expire_agent_review_locked(state)
                return str(result.pending_reason)

    def deliver_goal_review(
        self,
        cycle_id: str,
        review_bytes: bytes,
        *,
        media_type: str = "text/markdown",
    ) -> str:
        """Seal the current Goal's verbatim review without a Worker permit."""

        with self._repository.locked(cycle_id):
            state = self._current_state(cycle_id)
            if state.terminal or state.stage != "OUTCOME_SEALED":
                terminal = "TERMINAL" if state.terminal else "NONTERMINAL"
                raise MarketCyclePortError(
                    "MARKET_CYCLE_GOAL_REVIEW_STAGE_INVALID:"
                    f"{state.stage}:{terminal}"
                )
            persist = getattr(self._agent, "persist_goal_review", None)
            if not callable(persist):
                raise MarketCyclePortError(
                    "MARKET_CYCLE_GOAL_REVIEW_TRANSPORT_UNAVAILABLE"
                )
            return persist(
                cycle_id,
                review_bytes,
                media_type=media_type,
            )

    def _load(self, state: RunState, cls: type[ArtifactT]) -> tuple[ArtifactT, ArtifactRef]:
        ref = _reference(state, cls.__name__)
        value = cls.from_dict(self._repository.load_artifact(state.cycle_id, cls.__name__))
        return value, ref

    def _advance(
        self,
        state: RunState,
        *,
        artifacts: tuple[InputSnapshot | HypothesisRecord | BehaviorPlan | Outcome | Review, ...],
        next_stage: str,
    ) -> RunState:
        return self._repository.transition(
            expected=state,
            artifacts=artifacts,
            next_stage=next_stage,
            next_action=RUN_NEXT_ACTION[next_stage],
            terminal=next_stage == "COMPLETE",
        )

    def _fail(self, state: RunState, stage: str, error: BaseException) -> RunState:
        reason = f"{type(error).__name__}:{str(error) or 'UNSPECIFIED'}"
        return self._repository.transition(
            expected=state,
            artifacts=(),
            next_stage=stage,
            next_action=None,
            terminal=True,
            failure_reason=reason,
        )

    def run_next(self, cycle_id: str) -> AdvanceResult:
        """Resume from durable state and perform at most one legal transition."""

        with self._repository.locked(cycle_id):
            recovered = self._repository.recover_pending(cycle_id)
            if recovered is not None:
                return AdvanceResult(
                    state=recovered,
                    changed=True,
                    pending_reason="RECOVERED_PENDING_TRANSITION",
                )
            state = self._repository.load_state(cycle_id)
            if state.terminal:
                return AdvanceResult(state=state, changed=False, pending_reason="TERMINAL")

            if state.stage == "REQUESTED":
                request = self._repository.load_request(cycle_id)
                if request.analysis_profile != "COLD":
                    failed = self._fail(
                        state,
                        "REJECTED_SCOPE",
                        ValueError(
                            "ANALYSIS_PROFILE_NOT_READY:"
                            f"{request.analysis_profile}"
                        ),
                    )
                    return AdvanceResult(failed, True)
                try:
                    snapshot = capture_input_snapshot(
                        request, market_data=self._market_data, clock=self._clock
                    )
                except (MarketCyclePortError, OSError) as exc:
                    failed = self._fail(state, "INPUT_UNAVAILABLE", exc)
                    return AdvanceResult(failed, True)
                except ValueError as exc:
                    failed = self._fail(state, "INPUT_INVALID", exc)
                    return AdvanceResult(failed, True)
                return AdvanceResult(
                    self._advance(state, artifacts=(snapshot,), next_stage="INPUT_SEALED"),
                    True,
                )

            if state.stage == "INPUT_SEALED":
                snapshot, snapshot_ref = self._load(state, InputSnapshot)
                if (
                    self._decision_delivery_present(cycle_id)
                    and snapshot.theory_identity != V332_THEORY_IDENTITY
                ):
                    self._require_worker_completed(cycle_id, "decision-v1")
                try:
                    record = analyze_snapshot(
                        snapshot,
                        snapshot_ref,
                        agent=self._agent,
                        clock=self._clock,
                        theory_fragments=self._theory_fragments,
                        verified_memory=self._verified_memory,
                        decision_context=self._decision_context,
                    )
                except AgentAnalysisPending as exc:
                    return AdvanceResult(
                        state,
                        False,
                        pending_reason="AGENT_DELIVERY_PENDING",
                        pending_ref=exc.request_ref,
                    )
                except (MarketCyclePortError, ValueError) as exc:
                    failed = self._fail(state, "ANALYSIS_FAILED", exc)
                    return AdvanceResult(failed, True)
                return AdvanceResult(
                    self._advance(state, artifacts=(record,), next_stage="ANALYZED"),
                    True,
                )

            if state.stage == "ANALYZED":
                record, record_ref = self._load(state, HypothesisRecord)
                try:
                    plan = copy_agent_decision_to_behavior_plan(
                        record,
                        record_ref,
                        plan_id=f"{record.cycle_id}.plan",
                        sealed_at=record.agent_delivered_at,
                    )
                except ValueError as exc:
                    failed = self._fail(state, "PLAN_INVALID", exc)
                    return AdvanceResult(failed, True)
                advanced = self._advance(
                    state, artifacts=(plan,), next_stage="PLAN_SEALED"
                )
                return AdvanceResult(advanced, True)

            if state.stage == "PLAN_SEALED":
                plan, _ = self._load(state, BehaviorPlan)
                if _timestamp(self._clock()) < _timestamp(plan.outcome_due_at):
                    return AdvanceResult(
                        state,
                        False,
                        pending_reason="OUTCOME_WINDOW_NOT_OPEN",
                        pending_ref=plan.outcome_due_at,
                    )
                advanced = self._advance(
                    state, artifacts=(), next_stage="OUTCOME_DUE"
                )
                return AdvanceResult(advanced, True)

            if state.stage == "OUTCOME_DUE":
                request = self._repository.load_request(cycle_id)
                plan, plan_ref = self._load(state, BehaviorPlan)
                try:
                    outcome = capture_outcome(
                        plan,
                        plan_ref,
                        venue_id=request.venue_id,
                        instrument_id=request.instrument_id,
                        outcome_port=self._outcome,
                        clock=self._clock,
                    )
                except (MarketCyclePortError, OSError, ValueError) as exc:
                    failed = self._fail(state, "OUTCOME_INVALID", exc)
                    return AdvanceResult(failed, True)
                if outcome is None:
                    return AdvanceResult(
                        state, False, pending_reason="OUTCOME_OBSERVATION_PENDING"
                    )
                return AdvanceResult(
                    self._advance(
                        state, artifacts=(outcome,), next_stage="OUTCOME_SEALED"
                    ),
                    True,
                )

            if state.stage == "OUTCOME_SEALED":
                snapshot, snapshot_ref = self._load(state, InputSnapshot)
                record, record_ref = self._load(state, HypothesisRecord)
                plan, plan_ref = self._load(state, BehaviorPlan)
                outcome, outcome_ref = self._load(state, Outcome)
                if (
                    self._review_delivery_present(cycle_id)
                    and plan.theory_identity != V332_THEORY_IDENTITY
                ):
                    self._require_worker_completed(cycle_id, "review-v1")
                try:
                    review = review_cycle(
                        plan,
                        plan_ref,
                        outcome,
                        outcome_ref,
                        input_snapshot=snapshot,
                        input_snapshot_ref=snapshot_ref,
                        hypothesis_record=record,
                        hypothesis_record_ref=record_ref,
                        agent=self._agent,
                        clock=self._clock,
                        theory_fragments=self._theory_fragments,
                        analysis_profile=snapshot.analysis_profile,
                        decision_context=self._decision_context,
                        verified_memory=self._verified_memory,
                    )
                except AgentReviewPending as exc:
                    return AdvanceResult(
                        state,
                        False,
                        pending_reason="AGENT_REVIEW_DELIVERY_PENDING",
                        pending_ref=exc.request_ref,
                    )
                except ValueError as exc:
                    failed = self._fail(state, "REVIEW_FAILED", exc)
                    return AdvanceResult(failed, True)
                return AdvanceResult(
                    self._advance(state, artifacts=(review,), next_stage="REVIEWED"),
                    True,
                )

            if state.stage == "REVIEWED":
                return AdvanceResult(
                    self._advance(state, artifacts=(), next_stage="COMPLETE"),
                    True,
                )

            raise ValueError(f"unsupported nonterminal stage: {state.stage}")


__all__ = [
    "AdvanceResult",
    "CONTROLLER_DECISION_DEADLINE_EXPIRED",
    "CycleService",
]
