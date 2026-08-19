"""Durable, fact-rebuilt storage for V3.3.2 paper capability assessment."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime
import hashlib
from pathlib import Path
import stat
from typing import Any, Callable, Mapping, Sequence, TypeVar

from ...application.market_cycle.agent_session import AgentSessionService
from ...application.market_cycle.paper_capability_evaluation import (
    AttentionSchedulingEvidenceInputV1,
    PaperCapabilityEvidenceInputV1,
    PaperDecisionEvidenceInputV1,
    build_paper_position_and_open_order_ref,
    build_pre_outcome_paper_capability_assessment,
    build_pre_outcome_paper_capability_task,
)
from ...domain.contracts.canonical import canonical_bytes, canonical_digest, loads_json_strict
from ...domain.market_cycle.attention import (
    AttentionContractError,
    AttentionRequest,
    GoalAttentionCheckpointV1,
)
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
)
from ...domain.market_cycle.experiment import ExperimentPolicyV1
from ...domain.market_cycle.paper import PaperExecutionIntentV1
from ...domain.market_cycle.paper_capability_evaluation import (
    PAPER_CAPABILITY_IDS,
    PaperCapabilityFindingV1,
    PreOutcomePaperCapabilityAssessmentV1,
    PreOutcomePaperCapabilityTaskV1,
)
from ...domain.market_cycle.capability_evaluation import is_physical_goal_identity
from ...v32_durable_json import write_once_json
from .attention_repository import FileAttentionRepository
from .capability_assessor_mailbox import (
    CapabilityAssessorMailboxError,
    LocalCapabilityAssessorMailbox,
)
from .clock import SystemUTCMonotonicClock
from .paper_intent_mailbox import LocalPaperExecutionIntentMailbox
from .paper_ledger import FilePaperLedger
from .runtime import MarketCycleRuntime


_ENTRY_SCHEMA = "agent-trade-emotion.v332-paper-capability-store-entry"
_ENTRY_VERSION = "1.0.0"
_T = TypeVar("_T", PreOutcomePaperCapabilityTaskV1, PreOutcomePaperCapabilityAssessmentV1)


class PaperCapabilityEvaluationStoreError(RuntimeError):
    """A durable paper-capability fact or pre-outcome boundary is invalid."""


class FilePaperCapabilityEvaluationStore:
    """Rebuild evaluation evidence from existing owners; never accept fact digests."""

    def __init__(
        self,
        runtime: MarketCycleRuntime,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(runtime, MarketCycleRuntime):
            raise PaperCapabilityEvaluationStoreError("PAPER_CAPABILITY_RUNTIME_INVALID")
        trusted = SystemUTCMonotonicClock() if clock is None else clock
        if not callable(trusted):
            raise PaperCapabilityEvaluationStoreError("PAPER_CAPABILITY_CLOCK_INVALID")
        self._runtime = runtime
        self._repository = runtime.repository
        self._clock = trusted
        self._ledger = FilePaperLedger(runtime.runtime_root / "paper")
        self._attention_repository = FileAttentionRepository(
            runtime.runtime_root / "attention"
        )
        self._sessions = AgentSessionService(self._attention_repository)
        self._intent_mailbox = LocalPaperExecutionIntentMailbox(
            runtime.repository.root, clock=trusted
        )
        self._assessor_mailbox = LocalCapabilityAssessorMailbox(
            runtime.runtime_root
        )

    def _policy(self, capability_id: str) -> ExperimentPolicyV1:
        policy = self._runtime.experiment_policy
        if (
            capability_id not in PAPER_CAPABILITY_IDS
            or not isinstance(policy, ExperimentPolicyV1)
            or policy.phase != "CAPABILITY_PILOT"
            or policy.capability_ids != (capability_id,)
            or not policy.local_paper_authorized
            or policy.paper_account is None
            or self._runtime.run_manifest.experiment_identity != policy.policy_sha256
        ):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_SINGLETON_POLICY_REQUIRED"
            )
        return policy

    def _path(self, capability_id: str, kind: str) -> Path:
        if capability_id not in PAPER_CAPABILITY_IDS or kind not in {"TASK", "ASSESSMENT"}:
            raise PaperCapabilityEvaluationStoreError("PAPER_CAPABILITY_PATH_INVALID")
        return (
            self._runtime.runtime_root
            / "paper-capability-evaluation"
            / capability_id.lower()
            / f"{kind.lower()}.json"
        )

    @staticmethod
    def _read_document(path: Path, *, code: str) -> tuple[dict[str, Any], bytes]:
        try:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise OSError
            raw = path.read_bytes()
            value = loads_json_strict(raw)
        except (OSError, ValueError, FileNotFoundError) as exc:
            raise PaperCapabilityEvaluationStoreError(code) from exc
        if canonical_bytes(value) + b"\n" != raw:
            raise PaperCapabilityEvaluationStoreError(code)
        return value, raw

    @staticmethod
    def _snapshot_ref(state: object) -> ArtifactRef:
        values = tuple(
            item for item in getattr(state, "artifact_refs", ())
            if isinstance(item, ArtifactRef) and item.artifact_type == "InputSnapshot"
        )
        if len(values) != 1:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_SNAPSHOT_REF_INVALID"
            )
        return values[0]

    def _assessor_worker(
        self, cycle_id: str, *, required_status: str
    ) -> Mapping[str, Any]:
        try:
            worker = self._runtime.controller_state.recover_worker(
                cycle_id, "capability-assessor-v1"
            )
        except Exception as exc:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_WORKER_UNAVAILABLE"
            ) from exc
        if (
            not isinstance(worker, Mapping)
            or worker.get("cycle_id") != cycle_id
            or worker.get("worker_id") != "capability-assessor-v1"
            or worker.get("status") != required_status
            or not isinstance(worker.get("spawn_execution_ref"), str)
            or not worker["spawn_execution_ref"]
        ):
            raise PaperCapabilityEvaluationStoreError(
                f"PAPER_CAPABILITY_ASSESSOR_WORKER_{required_status}_REQUIRED"
            )
        return worker

    @staticmethod
    def _task_basis(task: PreOutcomePaperCapabilityTaskV1) -> dict[str, Any]:
        document = task.to_dict()
        document.pop("assessor_id")
        document.pop("created_at")
        return document

    @staticmethod
    def _seconds(start: str, end: str) -> int:
        try:
            started = datetime.fromisoformat(start.replace("Z", "+00:00"))
            ended = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_WINDOW_INVALID"
            ) from exc
        seconds = int((ended - started).total_seconds())
        if seconds <= 0 or seconds > 86_400:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_WINDOW_INVALID"
            )
        return seconds

    def _paper_evidence(
        self,
        cycle_id: str,
        *,
        policy: ExperimentPolicyV1,
        require_complete: bool,
    ) -> PaperDecisionEvidenceInputV1:
        self._runtime.service.verify_cycle_read(cycle_id)
        state = self._repository.load_state(cycle_id)
        artifact_types = tuple(item.artifact_type for item in state.artifact_refs)
        if "HypothesisRecord" not in artifact_types or "BehaviorPlan" not in artifact_types:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_DECISION_NOT_SEALED"
            )
        if require_complete and (
            state.stage != "COMPLETE"
            or not {"Outcome", "Review"}.issubset(artifact_types)
        ):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_PRIOR_CYCLE_NOT_COMPLETE"
            )
        if not require_complete and "Outcome" in artifact_types:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_OUTCOME_ALREADY_SEALED"
            )
        snapshot_ref = self._snapshot_ref(state)
        snapshot = InputSnapshot.from_dict(
            self._repository.load_artifact(cycle_id, "InputSnapshot")
        )
        hypothesis = HypothesisRecord.from_dict(
            self._repository.load_artifact(cycle_id, "HypothesisRecord")
        )
        request_document = self._runtime.mailbox.request(cycle_id)
        if not isinstance(request_document, Mapping):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_AGENT_REQUEST_MISSING"
            )
        packet = request_document.get("packet")
        context = packet.get("paper_context") if isinstance(packet, Mapping) else None
        if not isinstance(context, Mapping):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_CONTEXT_MISSING"
            )
        try:
            received_intent = self._intent_mailbox.receive(cycle_id)
        except ValueError as exc:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_AGENT_SIDECAR_INVALID"
            ) from exc
        intent = received_intent.intent
        intent_request, _ = self._read_document(
            self._intent_mailbox.intent_request_path(cycle_id),
            code="PAPER_CAPABILITY_INTENT_REQUEST_INVALID",
        )
        physical_task_id = intent_request.get("physical_task_id")
        try:
            registry = self._sessions.current(intent.logical_agent_id)
        except ValueError as exc:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_AGENT_REGISTRY_MISSING"
            ) from exc
        if (
            physical_task_id != registry.physical_task_id
            or registry.logical_agent_id != intent.logical_agent_id
            or registry.generation != intent.agent_generation
            or registry.symbol != intent.symbol
        ):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_PHYSICAL_TASK_BINDING_MISMATCH"
            )
        assert policy.paper_account is not None
        records = self._ledger.load_records(str(policy.paper_account["account_id"]))
        pre_index = intent.expected_account_version - 1
        post_index = intent.expected_account_version
        if pre_index < 0 or post_index >= len(records):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_LEDGER_TRANSITION_MISSING"
            )
        pre, post = records[pre_index], records[post_index]
        try:
            ledger_intent_matches = canonical_bytes(
                post.payload.get("execution_intent")
            ) == canonical_bytes(intent.to_dict())
        except (TypeError, ValueError):
            ledger_intent_matches = False
        if not ledger_intent_matches:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_LEDGER_INTENT_MISMATCH"
            )
        return PaperDecisionEvidenceInputV1(
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
            request_document=request_document,
            paper_context=context,
            hypothesis=hypothesis,
            execution_intent_request_document=intent_request,
            execution_intent=intent,
            pre_ledger_head=pre,
            post_ledger_head=post,
            current_agent=registry,
            cycle_stage=state.stage,
        )

    def _attention_evidence(
        self, cycle_id: str, *, policy: ExperimentPolicyV1
    ) -> AttentionSchedulingEvidenceInputV1:
        self._runtime.service.verify_cycle_read(cycle_id)
        state = self._repository.load_state(cycle_id)
        artifact_types = tuple(item.artifact_type for item in state.artifact_refs)
        if "HypothesisRecord" not in artifact_types or "BehaviorPlan" not in artifact_types:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_DECISION_NOT_SEALED"
            )
        if "Outcome" in artifact_types:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_OUTCOME_ALREADY_SEALED"
            )
        snapshot_ref = self._snapshot_ref(state)
        snapshot = InputSnapshot.from_dict(
            self._repository.load_artifact(cycle_id, "InputSnapshot")
        )
        hypothesis = HypothesisRecord.from_dict(
            self._repository.load_artifact(cycle_id, "HypothesisRecord")
        )
        behavior_plan = BehaviorPlan.from_dict(
            self._repository.load_artifact(cycle_id, "BehaviorPlan")
        )
        request_document = self._runtime.mailbox.request(cycle_id)
        if not isinstance(request_document, Mapping):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_AGENT_REQUEST_MISSING"
            )
        packet = request_document.get("packet")
        context = packet.get("paper_context") if isinstance(packet, Mapping) else None
        if not isinstance(context, Mapping):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_CONTEXT_MISSING"
            )
        try:
            continuity = context["continuity_projection"]
            latest = continuity["latest_attention_request"]
            if latest.get("status") != "EXACT_AGENT_ATTENTION_REQUEST":
                raise ValueError("attention checkpoint unavailable")
            request = AttentionRequest.from_dict(latest["request"])
            sources = latest["source_refs"]
            head_revision = sources["stream_revision"]
            head_event_sha256 = sources["stream_head_event_sha256"]
            if type(head_revision) is not int or head_revision < 2:
                raise ValueError("attention checkpoint revision invalid")
            events = self._attention_repository.replay(request.logical_agent_id)
            event = events[head_revision - 1]
            event_document = event.to_dict()
            goal_checkpoint = GoalAttentionCheckpointV1.from_dict(
                event.payload["goal_checkpoint"]
            )
            if (
                event.event_sha256 != head_event_sha256
                or event.event_type != "ATTENTION_REQUEST_SUBMITTED"
                or event.payload.get("request") != request.to_dict()
                or event.payload.get("accepted_at") != latest.get("accepted_at")
                or goal_checkpoint.run_id != self._runtime.run_manifest.run_id
                or goal_checkpoint.run_manifest_identity_sha256
                != self._runtime.run_manifest.identity_sha256
                or goal_checkpoint.experiment_policy_sha256
                != policy.policy_sha256
                or goal_checkpoint.request_sha256 != request.agent_owned_sha256
                or goal_checkpoint.accepted_at != latest.get("accepted_at")
                or latest.get("active_request_id") != request.request_id
                or latest.get("request_status") != "PENDING"
                or latest.get("request_sha256") != request.agent_owned_sha256
            ):
                raise ValueError("attention checkpoint head mismatch")
            head_document = {
                "schema_id": "agent-trade-emotion.v332-attention-head",
                "schema_version": "1.0.0",
                "logical_agent_id": request.logical_agent_id,
                "revision": head_revision,
                "event_sha256": head_event_sha256,
            }
            registry = self._sessions.current(request.logical_agent_id)
        except (
            AttentionContractError,
            IndexError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ATTENTION_CHECKPOINT_INVALID"
            ) from exc
        if (
            registry.logical_agent_id != request.logical_agent_id
            or registry.generation != request.agent_generation
            or registry.continuity_nonce != request.continuity_nonce
            or registry.symbol != request.symbol
            or registry.physical_task_id is None
            or registry.status not in {"ACTIVE", "IDLE"}
        ):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_PHYSICAL_TASK_BINDING_MISMATCH"
            )
        assert policy.paper_account is not None
        records = self._ledger.load_records(str(policy.paper_account["account_id"]))
        head = context.get("ledger_head")
        revision = head.get("revision") if isinstance(head, Mapping) else None
        if type(revision) is not int or revision < 1 or revision > len(records):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_LEDGER_HEAD_MISSING"
            )
        pre = records[revision - 1]
        if not isinstance(head, Mapping) or head.get("record_sha256") != pre.record_sha256:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_LEDGER_HEAD_MISMATCH"
            )
        expected_position_ref = build_paper_position_and_open_order_ref(
            account_id=policy.paper_account["account_id"],
            ledger_revision=pre.revision,
            ledger_head_sha256=pre.record_sha256,
        )
        if request.position_and_open_order_ref != expected_position_ref:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ATTENTION_PAPER_STATE_REF_MISMATCH"
            )
        return AttentionSchedulingEvidenceInputV1(
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
            request_document=request_document,
            paper_context=context,
            hypothesis=hypothesis,
            behavior_plan=behavior_plan,
            pre_ledger_head=pre,
            attention_request=request,
            attention_checkpoint_event_document=event_document,
            attention_stream_head_document=head_document,
            current_agent=registry,
        )

    def _evidence(
        self,
        cycle_id: str,
        *,
        capability_id: str,
        policy: ExperimentPolicyV1,
        require_complete: bool = False,
    ) -> PaperCapabilityEvidenceInputV1:
        if capability_id == "ATTENTION_SCHEDULING":
            return self._attention_evidence(cycle_id, policy=policy)
        return self._paper_evidence(
            cycle_id,
            policy=policy,
            require_complete=require_complete,
        )

    @staticmethod
    def _entry(document: Mapping[str, Any], kind: str) -> dict[str, Any]:
        return {
            "schema_id": _ENTRY_SCHEMA,
            "schema_version": _ENTRY_VERSION,
            "entry_type": kind,
            "document_sha256": canonical_digest(document),
            "document": dict(document),
        }

    @classmethod
    def _read_entry(cls, path: Path, *, kind: str, model: type[_T]) -> _T:
        value, _ = cls._read_document(path, code=f"PAPER_CAPABILITY_{kind}_INVALID")
        document = value.get("document")
        if (
            frozenset(value)
            != {"schema_id", "schema_version", "entry_type", "document_sha256", "document"}
            or value.get("schema_id") != _ENTRY_SCHEMA
            or value.get("schema_version") != _ENTRY_VERSION
            or value.get("entry_type") != kind
            or not isinstance(document, Mapping)
            or value.get("document_sha256") != canonical_digest(document)
        ):
            raise PaperCapabilityEvaluationStoreError(
                f"PAPER_CAPABILITY_{kind}_INVALID"
            )
        try:
            result = model.from_dict(document)
        except (TypeError, ValueError) as exc:
            raise PaperCapabilityEvaluationStoreError(
                f"PAPER_CAPABILITY_{kind}_INVALID"
            ) from exc
        expected = result.task_sha256 if kind == "TASK" else result.assessment_sha256
        if expected != value["document_sha256"]:
            raise PaperCapabilityEvaluationStoreError(
                f"PAPER_CAPABILITY_{kind}_HASH_MISMATCH"
            )
        return result

    def _facts(
        self, cycle_ids: Sequence[str], *, capability_id: str, policy: ExperimentPolicyV1
    ) -> tuple[PaperCapabilityEvidenceInputV1, ...]:
        cycles = tuple(cycle_ids)
        if len(cycles) != len(set(cycles)) or not cycles:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_CYCLES_INVALID"
            )
        if (capability_id == "TRADING_DECISION" and len(cycles) != 1) or (
            capability_id == "POSITION_MANAGEMENT" and len(cycles) < 2
        ) or (
            capability_id == "ATTENTION_SCHEDULING" and len(cycles) < 1
        ):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_CYCLE_CARDINALITY_INVALID"
            )
        return tuple(
            self._evidence(
                cycle,
                capability_id=capability_id,
                policy=policy,
                require_complete=(
                    capability_id == "POSITION_MANAGEMENT"
                    and index < len(cycles) - 1
                ),
            )
            for index, cycle in enumerate(cycles)
        )

    @staticmethod
    def _subject_agent_id(
        facts: Sequence[PaperCapabilityEvidenceInputV1],
    ) -> str:
        physical_ids = {
            fact.current_agent.physical_task_id for fact in facts
        }
        if len(physical_ids) != 1:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_LONG_GOAL_AGENT_IDENTITY_MISMATCH"
            )
        subject = next(iter(physical_ids))
        if not isinstance(subject, str) or not subject:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_LONG_GOAL_AGENT_IDENTITY_MISSING"
            )
        return subject

    def prepare_assessor(
        self,
        *,
        cycle_ids: Sequence[str],
        task_id: str,
        capability_id: str,
        assessment_due_at: str,
    ) -> Mapping[str, Any]:
        """Freeze paper evidence and request one physical assessor spawn."""

        with self._runtime.mutation_guard():
            return self._prepare_assessor(
                cycle_ids=cycle_ids,
                task_id=task_id,
                capability_id=capability_id,
                assessment_due_at=assessment_due_at,
            )

    def _prepare_assessor(
        self,
        *,
        cycle_ids: Sequence[str],
        task_id: str,
        capability_id: str,
        assessment_due_at: str,
    ) -> Mapping[str, Any]:

        policy = self._policy(capability_id)
        cycles = tuple(cycle_ids)
        anchor = cycles[-1] if cycles else ""
        with ExitStack() as stack:
            for cycle in sorted(set(cycles)):
                stack.enter_context(self._repository.locked(cycle))
            facts = self._facts(cycles, capability_id=capability_id, policy=policy)
            subject = self._subject_agent_id(facts)
            issued_at = self._clock()
            if not isinstance(issued_at, str):
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_CLOCK_RESULT_INVALID"
                )
            provisional = build_pre_outcome_paper_capability_task(
                task_id=task_id,
                capability_id=capability_id,
                policy=policy,
                evidence_points=facts,
                subject_agent_id=subject,
                assessor_id="pending-capability-assessor",
                created_at=issued_at,
                assessment_due_at=assessment_due_at,
            )
            request_document = self._runtime.mailbox.request(anchor)
            packet = (
                request_document.get("packet")
                if isinstance(request_document, Mapping)
                else None
            )
            theory_identity = (
                packet.get("theory_identity")
                if isinstance(packet, Mapping)
                else None
            )
            if not isinstance(theory_identity, Mapping):
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_AGENT_REQUEST_MISSING"
                )
            basis = self._task_basis(provisional)
            try:
                self._assessor_mailbox.issue(
                    cycle_id=anchor,
                    packet={
                        "cycle_id": anchor,
                        "task_id": task_id,
                        "capability_id": capability_id,
                        "policy_sha256": policy.policy_sha256,
                        "subject_agent_id": subject,
                        "evidence_kind": "PAPER",
                        "task_basis": basis,
                        "task_basis_sha256": canonical_digest(basis),
                        "capability_task_path": str(
                            self._path(capability_id, "TASK").absolute()
                        ),
                        "issued_at": issued_at,
                        "assessment_due_at": assessment_due_at,
                        "time_budget_seconds": self._seconds(
                            issued_at, assessment_due_at
                        ),
                        "theory_identity": dict(theory_identity),
                        "output_contract": self._assessor_mailbox.output_contract(
                            cycle_id=anchor,
                            evidence_kind="PAPER",
                            capability_id=capability_id,
                            capability_task_path=str(
                                self._path(capability_id, "TASK").absolute()
                            ),
                            task_basis=basis,
                        ),
                        "instructions": (
                            "Read packet.output_contract. Wait until "
                            "capability_task_path exists; assess only that "
                            "pre-outcome task, write every fixed criterion in "
                            "order, serialize exactly as required, and write only "
                            "the controller task boundary."
                        ),
                    },
                )
            except CapabilityAssessorMailboxError as exc:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSOR_REQUEST_INVALID"
                ) from exc
            controller = self._runtime.controller_state
            try:
                controller_task = controller.materialize_worker_task(
                    anchor, "capability-assessor-v1"
                )
                prepared = controller.prepare_worker(
                    anchor, "capability-assessor-v1", controller_task
                )
                return controller.mark_spawn_requested(
                    anchor,
                    "capability-assessor-v1",
                    str(prepared["dispatch_id"]),
                )
            except Exception as exc:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSOR_PREPARE_FAILED"
                ) from exc

    def acknowledge_assessor_spawn(
        self,
        *,
        cycle_id: str,
        dispatch_id: str,
        execution_ref: str,
    ) -> Mapping[str, Any]:
        """Reject a non-physical or subject Goal before controller ACK writes."""

        with self._runtime.mutation_guard():
            return self._acknowledge_assessor_spawn(
                cycle_id=cycle_id,
                dispatch_id=dispatch_id,
                execution_ref=execution_ref,
            )

    def _acknowledge_assessor_spawn(
        self,
        *,
        cycle_id: str,
        dispatch_id: str,
        execution_ref: str,
    ) -> Mapping[str, Any]:

        self._runtime.service.verify_cycle_read(cycle_id)
        try:
            request = self._assessor_mailbox.load_request(cycle_id)
        except CapabilityAssessorMailboxError as exc:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_REQUEST_INVALID"
            ) from exc
        packet = request.get("packet")
        capability_id = (
            packet.get("capability_id")
            if isinstance(packet, Mapping)
            else None
        )
        if not isinstance(capability_id, str):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_REQUEST_BINDING_MISMATCH"
            )
        policy = self._policy(capability_id)
        task_basis = packet.get("task_basis") if isinstance(packet, Mapping) else None
        subject = (
            packet.get("subject_agent_id")
            if isinstance(packet, Mapping)
            else None
        )
        if (
            not isinstance(task_basis, Mapping)
            or packet.get("cycle_id") != cycle_id
            or packet.get("capability_id") != capability_id
            or packet.get("policy_sha256") != policy.policy_sha256
            or packet.get("evidence_kind") != "PAPER"
            or task_basis.get("subject_agent_id") != subject
            or task_basis.get("capability_id") != capability_id
            or task_basis.get("policy_sha256") != policy.policy_sha256
            or not is_physical_goal_identity(subject)
        ):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_REQUEST_BINDING_MISMATCH"
            )
        if not is_physical_goal_identity(execution_ref):
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_PHYSICAL_GOAL_REQUIRED"
            )
        if execution_ref == subject:
            raise PaperCapabilityEvaluationStoreError(
                "PAPER_CAPABILITY_ASSESSOR_MUST_BE_INDEPENDENT"
            )
        return self._runtime.controller_state.acknowledge_spawn(
            cycle_id,
            "capability-assessor-v1",
            dispatch_id,
            execution_ref,
        )

    def preregister(
        self,
        *,
        cycle_ids: Sequence[str],
        capability_id: str,
    ) -> PreOutcomePaperCapabilityTaskV1:
        """Bind the task to the controller-acknowledged assessor identity."""

        with self._runtime.mutation_guard():
            return self._preregister(
                cycle_ids=cycle_ids, capability_id=capability_id
            )

    def _preregister(
        self,
        *,
        cycle_ids: Sequence[str],
        capability_id: str,
    ) -> PreOutcomePaperCapabilityTaskV1:

        policy = self._policy(capability_id)
        cycles = tuple(cycle_ids)
        anchor = cycles[-1] if cycles else ""
        with ExitStack() as stack:
            for cycle in sorted(set(cycles)):
                stack.enter_context(self._repository.locked(cycle))
            facts = self._facts(cycles, capability_id=capability_id, policy=policy)
            subject = self._subject_agent_id(facts)
            assessor = self._assessor_worker(
                anchor, required_status="DISPATCHED"
            )
            try:
                request = self._assessor_mailbox.load_request(anchor)
            except CapabilityAssessorMailboxError as exc:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSOR_REQUEST_INVALID"
                ) from exc
            request_packet = request["packet"]
            created_at = self._clock()
            if not isinstance(created_at, str):
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_CLOCK_RESULT_INVALID"
                )
            task = build_pre_outcome_paper_capability_task(
                task_id=str(request_packet["task_id"]),
                capability_id=capability_id,
                policy=policy,
                evidence_points=facts,
                subject_agent_id=subject,
                assessor_id=str(assessor["spawn_execution_ref"]),
                created_at=created_at,
                assessment_due_at=str(request_packet["assessment_due_at"]),
            )
            if (
                request_packet.get("capability_id") != capability_id
                or request_packet.get("policy_sha256") != policy.policy_sha256
                or request_packet.get("subject_agent_id") != subject
                or request_packet.get("evidence_kind") != "PAPER"
                or request_packet.get("capability_task_path")
                != str(self._path(capability_id, "TASK").absolute())
                or request_packet.get("task_basis") != self._task_basis(task)
                or request_packet.get("task_basis_sha256")
                != canonical_digest(self._task_basis(task))
            ):
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSOR_REQUEST_BINDING_MISMATCH"
                )
            try:
                write_once_json(
                    self._path(capability_id, "TASK"),
                    self._entry(task.to_dict(), "TASK"),
                )
            except (OSError, ValueError) as exc:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_TASK_WRITE_ONCE_CONFLICT"
                ) from exc
            persisted = self._read_entry(
                self._path(capability_id, "TASK"),
                kind="TASK",
                model=PreOutcomePaperCapabilityTaskV1,
            )
            if persisted.task_sha256 != task.task_sha256:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_TASK_READBACK_MISMATCH"
                )
            return persisted

    def seal_assessment(
        self,
        *,
        cycle_ids: Sequence[str],
        capability_id: str,
        assessment_id: str,
    ) -> PreOutcomePaperCapabilityAssessmentV1:
        with self._runtime.mutation_guard():
            return self._seal_assessment(
                cycle_ids=cycle_ids,
                capability_id=capability_id,
                assessment_id=assessment_id,
            )

    def _seal_assessment(
        self,
        *,
        cycle_ids: Sequence[str],
        capability_id: str,
        assessment_id: str,
    ) -> PreOutcomePaperCapabilityAssessmentV1:
        policy = self._policy(capability_id)
        cycles = tuple(cycle_ids)
        anchor = cycles[-1] if cycles else ""
        with ExitStack() as stack:
            for cycle in sorted(set(cycles)):
                stack.enter_context(self._repository.locked(cycle))
            task = self._read_entry(
                self._path(capability_id, "TASK"),
                kind="TASK",
                model=PreOutcomePaperCapabilityTaskV1,
            )
            assessor = self._assessor_worker(
                anchor, required_status="COMPLETED"
            )
            try:
                result, result_raw = self._assessor_mailbox.load_result(anchor)
                findings = tuple(
                    PaperCapabilityFindingV1.from_dict(item)
                    for item in result["findings"]
                )
            except (CapabilityAssessorMailboxError, TypeError, ValueError) as exc:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSOR_RESULT_INVALID"
                ) from exc
            if (
                result.get("task_sha256") != task.task_sha256
                or result.get("task_id") != task.task_id
                or result.get("capability_id") != capability_id
                or result.get("assessor_execution_ref") != task.assessor_id
                or assessor.get("spawn_execution_ref") != task.assessor_id
                or assessor.get("output_sha256")
                != hashlib.sha256(result_raw).hexdigest()
            ):
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSOR_RECEIPT_BINDING_MISMATCH"
                )
            facts = self._facts(cycles, capability_id=capability_id, policy=policy)
            assessed_at = self._clock()
            if not isinstance(assessed_at, str):
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_CLOCK_RESULT_INVALID"
                )
            assessment = build_pre_outcome_paper_capability_assessment(
                assessment_id=assessment_id,
                task=task,
                policy=policy,
                evidence_points=facts,
                assessed_at=assessed_at,
                findings=findings,
            )
            try:
                write_once_json(
                    self._path(capability_id, "ASSESSMENT"),
                    self._entry(assessment.to_dict(), "ASSESSMENT"),
                )
            except (OSError, ValueError) as exc:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSMENT_WRITE_ONCE_CONFLICT"
                ) from exc
            persisted = self._read_entry(
                self._path(capability_id, "ASSESSMENT"),
                kind="ASSESSMENT",
                model=PreOutcomePaperCapabilityAssessmentV1,
            )
            if persisted.assessment_sha256 != assessment.assessment_sha256:
                raise PaperCapabilityEvaluationStoreError(
                    "PAPER_CAPABILITY_ASSESSMENT_READBACK_MISMATCH"
                )
            return persisted

    def load_task(self, capability_id: str) -> PreOutcomePaperCapabilityTaskV1:
        self._policy(capability_id)
        return self._read_entry(
            self._path(capability_id, "TASK"), kind="TASK", model=PreOutcomePaperCapabilityTaskV1
        )

    def load_assessment(
        self, capability_id: str
    ) -> PreOutcomePaperCapabilityAssessmentV1:
        self._policy(capability_id)
        return self._read_entry(
            self._path(capability_id, "ASSESSMENT"),
            kind="ASSESSMENT",
            model=PreOutcomePaperCapabilityAssessmentV1,
        )


__all__ = ["FilePaperCapabilityEvaluationStore", "PaperCapabilityEvaluationStoreError"]
