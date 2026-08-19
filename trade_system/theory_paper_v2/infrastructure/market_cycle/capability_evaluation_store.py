"""Durable, pre-outcome storage for V3.3.2 capability-pilot assessments.

This adapter does not judge Agent output.  It reuses the existing pure
capability builders, the market-cycle repository lock, and write-once JSON to
freeze one task and one assessment per cycle/capability pair.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import stat
from typing import Any, Callable, Mapping, TypeVar

from ...application.market_cycle.capability_evaluation import (
    build_blind_capability_task,
    build_pre_outcome_capability_assessment,
)
from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from ...domain.market_cycle.capability_evaluation import (
    CAPABILITY_IDS,
    BlindCapabilityTaskV1,
    CapabilityFindingV1,
    PreOutcomeCapabilityAssessmentV1,
    is_physical_goal_identity,
)
from ...domain.market_cycle.contracts import ArtifactRef, HypothesisRecord, InputSnapshot
from ...domain.market_cycle.experiment import ExperimentPolicyV1
from ...v32_durable_json import write_once_json
from .clock import SystemUTCMonotonicClock
from .capability_assessor_mailbox import (
    CapabilityAssessorMailboxError,
    LocalCapabilityAssessorMailbox,
)
from .codex_mailbox import MarketCycleAgentMailboxError
from .runtime import MarketCycleRuntime


CAPABILITY_STORE_ENTRY_SCHEMA_ID = (
    "agent-trade-emotion.v332-capability-evaluation-store-entry"
)
CAPABILITY_STORE_ENTRY_SCHEMA_VERSION = "1.0.0"
_ENTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "entry_type",
        "document_sha256",
        "document",
    }
)
_MAX_ENTRY_BYTES = 256 * 1024
_T = TypeVar("_T", BlindCapabilityTaskV1, PreOutcomeCapabilityAssessmentV1)


class CapabilityEvaluationStoreError(RuntimeError):
    """A durable capability-pilot precondition or binding was not satisfied."""


class FileCapabilityEvaluationStore:
    """Persist pre-outcome tasks without becoming another evaluation owner."""

    def __init__(
        self,
        runtime: MarketCycleRuntime,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(runtime, MarketCycleRuntime):
            raise CapabilityEvaluationStoreError("CAPABILITY_RUNTIME_INVALID")
        trusted_clock = SystemUTCMonotonicClock() if clock is None else clock
        if not callable(trusted_clock):
            raise CapabilityEvaluationStoreError("CAPABILITY_CLOCK_INVALID")
        self._runtime = runtime
        self._repository = runtime.repository
        self._mailbox = runtime.mailbox
        self._clock = trusted_clock
        self._assessor_mailbox = LocalCapabilityAssessorMailbox(
            runtime.runtime_root
        )

    def _policy(self) -> ExperimentPolicyV1:
        policy = self._runtime.experiment_policy
        if (
            not isinstance(policy, ExperimentPolicyV1)
            or policy.phase != "CAPABILITY_PILOT"
            or len(policy.capability_ids) != 1
            or self._runtime.run_manifest.experiment_identity != policy.policy_sha256
            or self._runtime.run_manifest.run_id != policy.run_id
        ):
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_PILOT_POLICY_REQUIRED"
            )
        return policy

    @staticmethod
    def _capability_id(value: str) -> str:
        if value not in CAPABILITY_IDS:
            raise CapabilityEvaluationStoreError("CAPABILITY_ID_UNSUPPORTED")
        return value

    @staticmethod
    def _require_policy_capability(
        policy: ExperimentPolicyV1, capability_id: str
    ) -> None:
        if policy.capability_ids != (capability_id,):
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_PILOT_SINGLETON_MISMATCH"
            )

    def _entry_path(self, cycle_id: str, capability_id: str, kind: str) -> Path:
        directory = "tasks" if kind == "TASK" else "assessments"
        return (
            self._repository.root
            / cycle_id
            / "capability-evaluation"
            / directory
            / f"{self._capability_id(capability_id)}.json"
        )

    @staticmethod
    def _entry(document: Mapping[str, Any], *, entry_type: str) -> dict[str, Any]:
        return {
            "schema_id": CAPABILITY_STORE_ENTRY_SCHEMA_ID,
            "schema_version": CAPABILITY_STORE_ENTRY_SCHEMA_VERSION,
            "entry_type": entry_type,
            "document_sha256": canonical_digest(document),
            "document": dict(document),
        }

    @staticmethod
    def _read_entry(
        path: Path,
        *,
        entry_type: str,
        model: type[_T],
    ) -> _T:
        try:
            metadata = path.lstat()
        except FileNotFoundError as exc:
            raise CapabilityEvaluationStoreError(
                f"CAPABILITY_{entry_type}_MISSING"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CapabilityEvaluationStoreError(
                f"CAPABILITY_{entry_type}_FILE_UNSAFE"
            )
        if metadata.st_size < 2 or metadata.st_size > _MAX_ENTRY_BYTES:
            raise CapabilityEvaluationStoreError(
                f"CAPABILITY_{entry_type}_SIZE_INVALID"
            )
        raw = path.read_bytes()
        try:
            value = loads_json_strict(raw)
            if (
                not isinstance(value, Mapping)
                or frozenset(value) != _ENTRY_FIELDS
                or canonical_bytes(value) + b"\n" != raw
                or value.get("schema_id") != CAPABILITY_STORE_ENTRY_SCHEMA_ID
                or value.get("schema_version")
                != CAPABILITY_STORE_ENTRY_SCHEMA_VERSION
                or value.get("entry_type") != entry_type
                or not isinstance(value.get("document"), Mapping)
                or value.get("document_sha256")
                != canonical_digest(value["document"])
            ):
                raise CanonicalContractError("CAPABILITY_ENTRY_BINDING_INVALID")
            result = model.from_dict(value["document"])
        except (CanonicalContractError, TypeError, ValueError) as exc:
            raise CapabilityEvaluationStoreError(
                f"CAPABILITY_{entry_type}_INVALID"
            ) from exc
        digest = (
            result.task_sha256
            if isinstance(result, BlindCapabilityTaskV1)
            else result.assessment_sha256
        )
        if digest != value["document_sha256"]:
            raise CapabilityEvaluationStoreError(
                f"CAPABILITY_{entry_type}_HASH_MISMATCH"
            )
        return result

    @staticmethod
    def _snapshot_ref(state: object) -> ArtifactRef:
        references = getattr(state, "artifact_refs", ())
        snapshot_refs = tuple(
            item
            for item in references
            if isinstance(item, ArtifactRef) and item.artifact_type == "InputSnapshot"
        )
        if len(snapshot_refs) != 1:
            raise CapabilityEvaluationStoreError("CAPABILITY_SNAPSHOT_REF_INVALID")
        return snapshot_refs[0]

    def _request_document(self, cycle_id: str) -> Mapping[str, Any]:
        request = self._mailbox.request(cycle_id)
        if not isinstance(request, Mapping):
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_AGENT_REQUEST_NOT_SEALED"
            )
        return request

    def _sealed_hypothesis(
        self, cycle_id: str, state: object
    ) -> tuple[HypothesisRecord, Mapping[str, str]]:
        artifact_types = tuple(
            item.artifact_type
            for item in getattr(state, "artifact_refs", ())
            if isinstance(item, ArtifactRef)
        )
        if "HypothesisRecord" not in artifact_types:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_HYPOTHESIS_NOT_SEALED"
            )
        if "Outcome" in artifact_types:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_OUTCOME_ALREADY_SEALED"
            )
        try:
            hypothesis = HypothesisRecord.from_dict(
                self._repository.load_artifact(cycle_id, "HypothesisRecord")
            )
            delivery_binding = self._mailbox.goal_decision_delivery_binding(cycle_id)
        except (
            MarketCycleAgentMailboxError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_AGENT_DELIVERY_INVALID"
            ) from exc
        if (
            not isinstance(delivery_binding, Mapping)
            or frozenset(delivery_binding)
            != {"physical_goal_id", "delivery_sha256"}
            or delivery_binding.get("delivery_sha256")
            != hypothesis.agent_delivery_sha256
            or not isinstance(delivery_binding.get("physical_goal_id"), str)
        ):
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_AGENT_DELIVERY_INVALID"
            )
        return hypothesis, {
            "physical_goal_id": str(delivery_binding["physical_goal_id"]),
            "delivery_sha256": str(delivery_binding["delivery_sha256"]),
        }

    @staticmethod
    def _require_task_time_after_hypothesis(
        created_at: str, hypothesis: HypothesisRecord
    ) -> None:
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            sealed = datetime.fromisoformat(
                hypothesis.sealed_at.replace("Z", "+00:00")
            )
        except (AttributeError, ValueError) as exc:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_TASK_TIME_INVALID"
            ) from exc
        if created < sealed:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_TASK_PRECEDES_SEALED_DECISION"
            )

    def _assessor_worker(
        self, cycle_id: str, *, required_status: str
    ) -> Mapping[str, Any]:
        try:
            record = self._runtime.controller_state.recover_worker(
                cycle_id, "capability-assessor-v1"
            )
        except Exception as exc:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_ASSESSOR_WORKER_UNAVAILABLE"
            ) from exc
        if (
            not isinstance(record, Mapping)
            or record.get("cycle_id") != cycle_id
            or record.get("worker_id") != "capability-assessor-v1"
            or record.get("status") != required_status
            or not isinstance(record.get("spawn_execution_ref"), str)
            or not record["spawn_execution_ref"]
        ):
            raise CapabilityEvaluationStoreError(
                f"CAPABILITY_ASSESSOR_WORKER_{required_status}_REQUIRED"
            )
        return record

    @staticmethod
    def _task_basis(task: BlindCapabilityTaskV1) -> dict[str, Any]:
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
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_ASSESSOR_WINDOW_INVALID"
            ) from exc
        seconds = int((ended - started).total_seconds())
        if seconds <= 0 or seconds > 86_400:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_ASSESSOR_WINDOW_INVALID"
            )
        return seconds

    def prepare_assessor(
        self,
        *,
        cycle_id: str,
        task_id: str,
        capability_id: str,
        assessment_due_at: str,
    ) -> Mapping[str, Any]:
        """Freeze the sealed-decision basis and request one assessor spawn."""

        with self._runtime.mutation_guard():
            return self._prepare_assessor(
                cycle_id=cycle_id,
                task_id=task_id,
                capability_id=capability_id,
                assessment_due_at=assessment_due_at,
            )

    def _prepare_assessor(
        self,
        *,
        cycle_id: str,
        task_id: str,
        capability_id: str,
        assessment_due_at: str,
    ) -> Mapping[str, Any]:

        capability = self._capability_id(capability_id)
        with self._repository.locked(cycle_id):
            self._runtime.service.verify_cycle_read(cycle_id)
            policy = self._policy()
            self._require_policy_capability(policy, capability)
            state = self._repository.load_state(cycle_id)
            hypothesis, delivery_binding = self._sealed_hypothesis(cycle_id, state)
            snapshot_ref = self._snapshot_ref(state)
            snapshot = InputSnapshot.from_dict(
                self._repository.load_artifact(cycle_id, "InputSnapshot")
            )
            request_document = self._request_document(cycle_id)
            subject_agent_id = delivery_binding["physical_goal_id"]
            issued_at = self._clock()
            if not isinstance(issued_at, str):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_CLOCK_RESULT_INVALID"
                )
            self._require_task_time_after_hypothesis(issued_at, hypothesis)
            provisional = build_blind_capability_task(
                task_id=task_id,
                capability_id=capability,
                policy=policy,
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                request_document=request_document,
                subject_agent_id=subject_agent_id,
                decision_delivery_sha256=delivery_binding["delivery_sha256"],
                assessor_id="pending-capability-assessor",
                created_at=issued_at,
                assessment_due_at=assessment_due_at,
            )
            task_path = self._entry_path(cycle_id, capability, "TASK")
            packet = request_document.get("packet")
            theory_identity = (
                packet.get("theory_identity")
                if isinstance(packet, Mapping)
                else None
            )
            if not isinstance(theory_identity, Mapping):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_AGENT_REQUEST_NOT_SEALED"
                )
            basis = self._task_basis(provisional)
            try:
                self._assessor_mailbox.issue(
                    cycle_id=cycle_id,
                    packet={
                        "cycle_id": cycle_id,
                        "task_id": task_id,
                        "capability_id": capability,
                        "policy_sha256": policy.policy_sha256,
                        "subject_agent_id": subject_agent_id,
                        "evidence_kind": "GENERAL",
                        "task_basis": basis,
                        "task_basis_sha256": canonical_digest(basis),
                        "capability_task_path": str(task_path.absolute()),
                        "issued_at": issued_at,
                        "assessment_due_at": assessment_due_at,
                        "time_budget_seconds": self._seconds(
                            issued_at, assessment_due_at
                        ),
                        "theory_identity": dict(theory_identity),
                        "output_contract": self._assessor_mailbox.output_contract(
                            cycle_id=cycle_id,
                            evidence_kind="GENERAL",
                            capability_id=capability,
                            capability_task_path=str(task_path.absolute()),
                            task_basis=basis,
                        ),
                        "instructions": (
                            "Wait until capability_task_path exists; assess only "
                            "that pre-outcome task, write every fixed criterion in "
                            "order, read and obey the complete structured "
                            "output_contract, serialize its result as canonical "
                            "compact UTF-8 JSON plus exactly one newline, and "
                            "write only the controller task boundary."
                        ),
                    },
                )
            except CapabilityAssessorMailboxError as exc:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSOR_REQUEST_INVALID"
                ) from exc
            controller = self._runtime.controller_state
            try:
                controller_task = controller.materialize_worker_task(
                    cycle_id, "capability-assessor-v1"
                )
                prepared = controller.prepare_worker(
                    cycle_id, "capability-assessor-v1", controller_task
                )
                return controller.mark_spawn_requested(
                    cycle_id,
                    "capability-assessor-v1",
                    str(prepared["dispatch_id"]),
                )
            except Exception as exc:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSOR_PREPARE_FAILED"
                ) from exc

    def acknowledge_assessor_spawn(
        self,
        *,
        cycle_id: str,
        dispatch_id: str,
        execution_ref: str,
    ) -> Mapping[str, Any]:
        """Reject a subject Goal as assessor before the controller ACK is written."""

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
        policy = self._policy()
        capability = self._capability_id(policy.capability_ids[0])
        self._require_policy_capability(policy, capability)
        state = self._repository.load_state(cycle_id)
        _, delivery_binding = self._sealed_hypothesis(cycle_id, state)
        if not is_physical_goal_identity(execution_ref):
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_ASSESSOR_PHYSICAL_GOAL_REQUIRED"
            )
        if execution_ref == delivery_binding["physical_goal_id"]:
            raise CapabilityEvaluationStoreError(
                "CAPABILITY_ASSESSOR_MUST_BE_INDEPENDENT"
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
        cycle_id: str,
        capability_id: str,
    ) -> BlindCapabilityTaskV1:
        """Bind the sealed decision author to the acknowledged assessor."""

        with self._runtime.mutation_guard():
            return self._preregister(
                cycle_id=cycle_id, capability_id=capability_id
            )

    def _preregister(
        self,
        *,
        cycle_id: str,
        capability_id: str,
    ) -> BlindCapabilityTaskV1:

        capability = self._capability_id(capability_id)
        with self._repository.locked(cycle_id):
            self._runtime.service.verify_cycle_read(cycle_id)
            policy = self._policy()
            self._require_policy_capability(policy, capability)
            state = self._repository.load_state(cycle_id)
            hypothesis, delivery_binding = self._sealed_hypothesis(cycle_id, state)
            snapshot_ref = self._snapshot_ref(state)
            snapshot = InputSnapshot.from_dict(
                self._repository.load_artifact(cycle_id, "InputSnapshot")
            )
            request_document = self._request_document(cycle_id)
            subject_agent_id = delivery_binding["physical_goal_id"]
            assessor = self._assessor_worker(
                cycle_id, required_status="DISPATCHED"
            )
            if assessor.get("spawn_execution_ref") == subject_agent_id:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSOR_MUST_BE_INDEPENDENT"
                )
            try:
                assessor_request = self._assessor_mailbox.load_request(cycle_id)
            except CapabilityAssessorMailboxError as exc:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSOR_REQUEST_INVALID"
                ) from exc
            request_packet = assessor_request["packet"]
            created_at = self._clock()
            if not isinstance(created_at, str):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_CLOCK_RESULT_INVALID"
                )
            self._require_task_time_after_hypothesis(created_at, hypothesis)
            task = build_blind_capability_task(
                task_id=str(request_packet["task_id"]),
                capability_id=capability,
                policy=policy,
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                request_document=request_document,
                subject_agent_id=subject_agent_id,
                decision_delivery_sha256=delivery_binding["delivery_sha256"],
                assessor_id=str(assessor["spawn_execution_ref"]),
                created_at=created_at,
                assessment_due_at=str(request_packet["assessment_due_at"]),
            )
            if (
                request_packet.get("capability_id") != capability
                or request_packet.get("policy_sha256") != policy.policy_sha256
                or request_packet.get("subject_agent_id")
                != subject_agent_id
                or request_packet.get("evidence_kind") != "GENERAL"
                or request_packet.get("capability_task_path")
                != str(self._entry_path(cycle_id, capability, "TASK").absolute())
                or request_packet.get("task_basis") != self._task_basis(task)
                or request_packet.get("task_basis_sha256")
                != canonical_digest(self._task_basis(task))
            ):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSOR_REQUEST_BINDING_MISMATCH"
                )
            path = self._entry_path(cycle_id, capability, "TASK")
            try:
                write_once_json(path, self._entry(task.to_dict(), entry_type="TASK"))
            except (CanonicalContractError, OSError) as exc:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_TASK_WRITE_ONCE_CONFLICT"
                ) from exc
            persisted = self._read_entry(
                path, entry_type="TASK", model=BlindCapabilityTaskV1
            )
            if persisted.task_sha256 != task.task_sha256:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_TASK_READBACK_MISMATCH"
                )
            return persisted

    def load_task(self, cycle_id: str, capability_id: str) -> BlindCapabilityTaskV1:
        """Read and revalidate one frozen task without advancing the cycle."""

        capability = self._capability_id(capability_id)
        with self._repository.locked(cycle_id):
            self._runtime.service.verify_cycle_read(cycle_id)
            policy = self._policy()
            self._require_policy_capability(policy, capability)
            task = self._read_entry(
                self._entry_path(cycle_id, capability, "TASK"),
                entry_type="TASK",
                model=BlindCapabilityTaskV1,
            )
            if task.cycle_id != cycle_id or task.capability_id != capability:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_TASK_PATH_BINDING_MISMATCH"
                )
            return task

    def seal_assessment(
        self,
        *,
        cycle_id: str,
        capability_id: str,
        assessment_id: str,
    ) -> PreOutcomeCapabilityAssessmentV1:
        """Freeze findings from the completed, receipt-bound assessor Worker."""

        with self._runtime.mutation_guard():
            return self._seal_assessment(
                cycle_id=cycle_id,
                capability_id=capability_id,
                assessment_id=assessment_id,
            )

    def _seal_assessment(
        self,
        *,
        cycle_id: str,
        capability_id: str,
        assessment_id: str,
    ) -> PreOutcomeCapabilityAssessmentV1:

        capability = self._capability_id(capability_id)
        with self._repository.locked(cycle_id):
            self._runtime.service.verify_cycle_read(cycle_id)
            policy = self._policy()
            self._require_policy_capability(policy, capability)
            task = self._read_entry(
                self._entry_path(cycle_id, capability, "TASK"),
                entry_type="TASK",
                model=BlindCapabilityTaskV1,
            )
            if task.cycle_id != cycle_id or task.capability_id != capability:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_TASK_PATH_BINDING_MISMATCH"
                )
            state = self._repository.load_state(cycle_id)
            hypothesis, delivery_binding = self._sealed_hypothesis(cycle_id, state)
            snapshot_ref = self._snapshot_ref(state)
            snapshot = InputSnapshot.from_dict(
                self._repository.load_artifact(cycle_id, "InputSnapshot")
            )
            if (
                task.subject_agent_id != delivery_binding["physical_goal_id"]
                or task.decision_delivery_sha256
                != delivery_binding["delivery_sha256"]
            ):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_PHYSICAL_GOAL_DELIVERY_BINDING_MISMATCH"
                )
            assessor = self._assessor_worker(
                cycle_id, required_status="COMPLETED"
            )
            try:
                result, result_raw = self._assessor_mailbox.load_result(cycle_id)
                findings = tuple(
                    CapabilityFindingV1.from_dict(item)
                    for item in result["findings"]
                )
            except (CapabilityAssessorMailboxError, TypeError, ValueError) as exc:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSOR_RESULT_INVALID"
                ) from exc
            if (
                result.get("task_sha256") != task.task_sha256
                or result.get("task_id") != task.task_id
                or result.get("capability_id") != capability
                or result.get("assessor_execution_ref") != task.assessor_id
                or assessor.get("spawn_execution_ref") != task.assessor_id
                or assessor.get("output_sha256")
                != hashlib.sha256(result_raw).hexdigest()
            ):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSOR_RECEIPT_BINDING_MISMATCH"
                )
            assessed_at = self._clock()
            if not isinstance(assessed_at, str):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_CLOCK_RESULT_INVALID"
                )
            assessment = build_pre_outcome_capability_assessment(
                assessment_id=assessment_id,
                task=task,
                policy=policy,
                request_document=self._request_document(cycle_id),
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                hypothesis=hypothesis,
                subject_physical_goal_id=delivery_binding["physical_goal_id"],
                decision_delivery_sha256=delivery_binding["delivery_sha256"],
                assessed_at=assessed_at,
                findings=findings,
            )
            path = self._entry_path(cycle_id, capability, "ASSESSMENT")
            try:
                write_once_json(
                    path,
                    self._entry(assessment.to_dict(), entry_type="ASSESSMENT"),
                )
            except (CanonicalContractError, OSError) as exc:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSMENT_WRITE_ONCE_CONFLICT"
                ) from exc
            persisted = self._read_entry(
                path,
                entry_type="ASSESSMENT",
                model=PreOutcomeCapabilityAssessmentV1,
            )
            if persisted.assessment_sha256 != assessment.assessment_sha256:
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSMENT_READBACK_MISMATCH"
                )
            return persisted

    def load_assessment(
        self, cycle_id: str, capability_id: str
    ) -> PreOutcomeCapabilityAssessmentV1:
        """Read and revalidate one frozen pre-outcome assessment."""

        capability = self._capability_id(capability_id)
        with self._repository.locked(cycle_id):
            self._runtime.service.verify_cycle_read(cycle_id)
            policy = self._policy()
            self._require_policy_capability(policy, capability)
            assessment = self._read_entry(
                self._entry_path(cycle_id, capability, "ASSESSMENT"),
                entry_type="ASSESSMENT",
                model=PreOutcomeCapabilityAssessmentV1,
            )
            if (
                assessment.cycle_id != cycle_id
                or assessment.capability_id != capability
            ):
                raise CapabilityEvaluationStoreError(
                    "CAPABILITY_ASSESSMENT_PATH_BINDING_MISMATCH"
                )
            return assessment


__all__ = [
    "CAPABILITY_STORE_ENTRY_SCHEMA_ID",
    "CAPABILITY_STORE_ENTRY_SCHEMA_VERSION",
    "CapabilityEvaluationStoreError",
    "FileCapabilityEvaluationStore",
]
