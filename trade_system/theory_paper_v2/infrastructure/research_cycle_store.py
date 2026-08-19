"""Write-once process ledger for one continuous research cycle.

The ledger is deliberately local and specialized.  It is not a transport or a
generic event platform: it only proves the ordered steps and final artifact
bindings needed by the single-Strategy-Agent experiment.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)


class ResearchCycleStoreError(ValueError):
    pass


ZERO_DIGEST = "0" * 64
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
PRE_EVIDENCE_RECEIPT_EVENT_TYPES = (
    "RESUME_CAPSULE_SEALED",
    "CYCLE_DUE",
    "COLLECTION_STARTED",
    "COLLECTION_ATTEMPTS_SEALED",
    "COLLECTION_SEALED",
    "PIT_ADMITTED",
    "MARKET_INFORMATION_SEALED",
    "REPLAY_SEALED",
    "PRE_DECISION_STATE_SEALED",
    "AGENT_CONTEXT_SEALED",
    "AGENT_INPUT_PLAN_SEALED",
    "AGENT_PROPOSAL_ATTEMPT_SEALED",
    "AGENT_PROPOSAL_SEALED",
    "SENTIMENT_STATE_SEALED",
    "HYPOTHESIS_DELTA_SEALED",
    "HYPOTHESIS_REGISTRY_SEALED",
    "EXPECTATION_DELTA_SEALED",
    "EXPECTATION_LEDGER_SEALED",
    "PUBLIC_INFERENCE_TRACE_SEALED",
    "BELIEF_UPDATE_SEALED",
    "ACTION_EVALUATION_SEALED",
    "DELIBERATION_SEALED",
    "ACTION_SELECTION_SEALED",
    "RISK_DECISION_SEALED",
    "DECISION_SEALED",
    "CURRENT_CYCLE_GROUNDING_SEALED",
    "PREACCEPT_VALIDATION_SEALED",
    "STATE_ACCEPTED",
    "ACTION_RECEIPT_SEALED",
    "COMPARATOR_SEALED",
    "REVIEW_SOURCE_SEALED",
)
PRE_COMPLETION_EVENT_TYPES = PRE_EVIDENCE_RECEIPT_EVENT_TYPES + (
    "CYCLE_EVIDENCE_RECEIPT_SEALED",
    "REPORT_SEALED",
)
REQUIRED_EVIDENCE_ARTIFACT_BINDINGS = frozenset(
    {
        "market_context_digest",
        "resume_capsule_digest",
        "market_information_snapshot_digest",
        "pre_decision_state_digest",
        "agent_context_digest",
        "agent_input_plan_digest",
        "agent_invocation_receipt_digest",
        "agent_proposal_digest",
        "sentiment_state_digest",
        "hypothesis_registry_delta_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_delta_digest",
        "expectation_ledger_digest",
        "public_inference_trace_digest",
        "belief_state_digest",
        "action_evaluation_digest",
        "deliberation_digest",
        "action_selection_digest",
        "risk_decision_digest",
        "decision_digest",
        "current_cycle_grounding_digest",
        "preaccept_validation_receipt_digest",
        "accepted_state_digest",
        "action_receipt_digest",
        "comparator_digest",
        "cycle_review_source_digest",
    }
)
REQUIRED_ARTIFACT_BINDINGS = frozenset(
    {
        *REQUIRED_EVIDENCE_ARTIFACT_BINDINGS,
        "cycle_evidence_receipt_digest",
        "report_sha256",
    }
)
EVENT_ARTIFACT_BINDINGS = {
    "RESUME_CAPSULE_SEALED": "resume_capsule_digest",
    "COLLECTION_SEALED": "market_context_digest",
    "MARKET_INFORMATION_SEALED": "market_information_snapshot_digest",
    "PRE_DECISION_STATE_SEALED": "pre_decision_state_digest",
    "AGENT_CONTEXT_SEALED": "agent_context_digest",
    "AGENT_INPUT_PLAN_SEALED": "agent_input_plan_digest",
    "AGENT_PROPOSAL_ATTEMPT_SEALED": "agent_invocation_receipt_digest",
    "AGENT_PROPOSAL_SEALED": "agent_proposal_digest",
    "SENTIMENT_STATE_SEALED": "sentiment_state_digest",
    "HYPOTHESIS_DELTA_SEALED": "hypothesis_registry_delta_digest",
    "HYPOTHESIS_REGISTRY_SEALED": "hypothesis_registry_digest",
    "EXPECTATION_DELTA_SEALED": "expectation_ledger_delta_digest",
    "EXPECTATION_LEDGER_SEALED": "expectation_ledger_digest",
    "PUBLIC_INFERENCE_TRACE_SEALED": "public_inference_trace_digest",
    "BELIEF_UPDATE_SEALED": "belief_state_digest",
    "ACTION_EVALUATION_SEALED": "action_evaluation_digest",
    "DELIBERATION_SEALED": "deliberation_digest",
    "ACTION_SELECTION_SEALED": "action_selection_digest",
    "RISK_DECISION_SEALED": "risk_decision_digest",
    "DECISION_SEALED": "decision_digest",
    "CURRENT_CYCLE_GROUNDING_SEALED": "current_cycle_grounding_digest",
    "PREACCEPT_VALIDATION_SEALED": "preaccept_validation_receipt_digest",
    "STATE_ACCEPTED": "accepted_state_digest",
    "ACTION_RECEIPT_SEALED": "action_receipt_digest",
    "COMPARATOR_SEALED": "comparator_digest",
    "REVIEW_SOURCE_SEALED": "cycle_review_source_digest",
    "CYCLE_EVIDENCE_RECEIPT_SEALED": "cycle_evidence_receipt_digest",
    "REPORT_SEALED": "report_sha256",
}
EVENT_ACTORS = {
    "RESUME_CAPSULE_SEALED": "DETERMINISTIC_WINDOW_RECOVERY_GATE",
    "CYCLE_DUE": "DETERMINISTIC_SCHEDULER",
    "COLLECTION_STARTED": "DATA_ACQUISITION_COORDINATOR",
    "COLLECTION_ATTEMPTS_SEALED": "DATA_ACQUISITION_COORDINATOR",
    "COLLECTION_SEALED": "DATA_ACQUISITION_COORDINATOR",
    "PIT_ADMITTED": "PIT_ADMISSION_GATE",
    "MARKET_INFORMATION_SEALED": "DETERMINISTIC_MARKET_INFORMATION_BUILDER",
    "REPLAY_SEALED": "DETERMINISTIC_STATE_REDUCER",
    "PRE_DECISION_STATE_SEALED": "DETERMINISTIC_STATE_REDUCER",
    "AGENT_CONTEXT_SEALED": "AGENT_CONTEXT_BUILDER",
    "AGENT_INPUT_PLAN_SEALED": "DETERMINISTIC_CONTEXT_BUDGET_GATE",
    "AGENT_PROPOSAL_ATTEMPT_SEALED": "PLATFORM_INVOCATION_ADAPTER",
    "AGENT_PROPOSAL_SEALED": "SINGLE_STRATEGY_AGENT",
    "SENTIMENT_STATE_SEALED": "DETERMINISTIC_SENTIMENT_REDUCER",
    "HYPOTHESIS_DELTA_SEALED": "SINGLE_STRATEGY_AGENT",
    "HYPOTHESIS_REGISTRY_SEALED": "DETERMINISTIC_HYPOTHESIS_REDUCER",
    "EXPECTATION_DELTA_SEALED": "SINGLE_STRATEGY_AGENT",
    "EXPECTATION_LEDGER_SEALED": "DETERMINISTIC_EXPECTATION_REDUCER",
    "PUBLIC_INFERENCE_TRACE_SEALED": "DETERMINISTIC_EPISTEMIC_CONTRACT",
    "BELIEF_UPDATE_SEALED": "DETERMINISTIC_BELIEF_REDUCER",
    "ACTION_EVALUATION_SEALED": "DETERMINISTIC_ACTION_EVALUATOR",
    "DELIBERATION_SEALED": "SINGLE_STRATEGY_AGENT",
    "ACTION_SELECTION_SEALED": "SINGLE_STRATEGY_AGENT",
    "RISK_DECISION_SEALED": "DETERMINISTIC_RISK_KERNEL",
    "DECISION_SEALED": "DETERMINISTIC_DECISION_BUILDER",
    "CURRENT_CYCLE_GROUNDING_SEALED": "DETERMINISTIC_CURRENT_CYCLE_GROUNDER",
    "PREACCEPT_VALIDATION_SEALED": "DETERMINISTIC_PREACCEPT_GATE",
    "STATE_ACCEPTED": "DETERMINISTIC_STATE_REDUCER",
    "ACTION_RECEIPT_SEALED": "DETERMINISTIC_ACTION_RECEIPT_BUILDER",
    "COMPARATOR_SEALED": "DETERMINISTIC_COMPARATOR",
    "REVIEW_SOURCE_SEALED": "DETERMINISTIC_REVIEW_SOURCE_BUILDER",
    "CYCLE_EVIDENCE_RECEIPT_SEALED": "DETERMINISTIC_EVIDENCE_COORDINATOR",
    "REPORT_SEALED": "DETERMINISTIC_REPORT_BUILDER",
    "REVIEW_SEALED": "DETERMINISTIC_REVIEW",
    "CYCLE_COMPLETED": "DETERMINISTIC_CYCLE_COORDINATOR",
}
_INTERNAL_EVENT_TYPES = frozenset(
    {"CYCLE_EVIDENCE_RECEIPT_SEALED", "CYCLE_COMPLETED"}
)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_bytes(dict(value)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ResearchCycleStore:
    """Append and verify one fixed research-process chronology."""

    def __init__(self, run_root: Path, *, run_id: str, cycle_index: int) -> None:
        if not run_id or cycle_index < 1:
            raise ResearchCycleStoreError("CYCLE_EVENT_IDENTITY_INVALID")
        self.run_root = Path(run_root).resolve()
        self.run_id = run_id
        self.cycle_index = cycle_index
        self.events_root = (
            self.run_root / "process-events" / f"cycle-{cycle_index:04d}"
        )

    @property
    def required_pre_completion_types(self) -> tuple[str, ...]:
        if self.cycle_index % 4 == 0:
            return PRE_COMPLETION_EVENT_TYPES + ("REVIEW_SEALED",)
        return PRE_COMPLETION_EVENT_TYPES

    def read_events(self) -> tuple[dict[str, Any], ...]:
        if not self.events_root.exists():
            return ()
        events: list[dict[str, Any]] = []
        prior = ZERO_DIGEST
        for sequence, path in enumerate(sorted(self.events_root.glob("*.json"))):
            event = load_json_strict(path)
            try:
                verify_self_digest(event, "event_digest")
            except ValueError as exc:
                raise ResearchCycleStoreError("CYCLE_EVENT_DIGEST_INVALID") from exc
            if (
                event.get("run_id") != self.run_id
                or event.get("cycle_index") != self.cycle_index
                or event.get("sequence") != sequence
                or event.get("previous_event_digest") != prior
                or path.name != f"{sequence:04d}-{event.get('event_type')}.json"
                or event.get("actor") != EVENT_ACTORS.get(event.get("event_type"))
            ):
                raise ResearchCycleStoreError("CYCLE_EVENT_CHAIN_BROKEN")
            self._verify_payload(
                str(event.get("payload_ref") or ""),
                str(event.get("payload_digest") or ""),
                expected_sha256=str(event.get("payload_sha256") or ""),
            )
            prior = event["event_digest"]
            events.append(event)
        return tuple(events)

    def next_required_event_type(self) -> str | None:
        events = self.read_events()
        expected = self.required_pre_completion_types + ("CYCLE_COMPLETED",)
        if len(events) >= len(expected):
            return None
        return expected[len(events)]

    def append_event(
        self,
        *,
        event_type: str,
        payload_ref: str,
        payload_digest: str,
        actor: str,
        recorded_at: str,
        evidence_boundary: str,
    ) -> dict[str, Any]:
        if event_type in _INTERNAL_EVENT_TYPES:
            raise ResearchCycleStoreError("CYCLE_INTERNAL_EVENT_WRITE_FORBIDDEN")
        return self._append_event(
            event_type=event_type,
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            actor=actor,
            recorded_at=recorded_at,
            evidence_boundary=evidence_boundary,
        )

    def _append_event(
        self,
        *,
        event_type: str,
        payload_ref: str,
        payload_digest: str,
        actor: str,
        recorded_at: str,
        evidence_boundary: str,
    ) -> dict[str, Any]:
        if event_type != self.next_required_event_type():
            raise ResearchCycleStoreError("CYCLE_EVENT_ORDER_INVALID")
        if (
            not payload_ref
            or _HEX_64.fullmatch(str(payload_digest or "")) is None
            or actor != EVENT_ACTORS.get(event_type)
            or not recorded_at
            or not evidence_boundary
        ):
            raise ResearchCycleStoreError("CYCLE_EVENT_FIELDS_INVALID")
        payload_sha256 = self._verify_payload(payload_ref, payload_digest)
        events = self.read_events()
        try:
            event_time = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
            prior_time = (
                None
                if not events
                else datetime.fromisoformat(
                    str(events[-1]["recorded_at"]).replace("Z", "+00:00")
                )
            )
        except ValueError as exc:
            raise ResearchCycleStoreError("CYCLE_EVENT_TIME_INVALID") from exc
        if event_time.tzinfo is None or (
            prior_time is not None and event_time < prior_time
        ):
            raise ResearchCycleStoreError("CYCLE_EVENT_TIME_INVALID")
        sequence = len(events)
        event = self_digest(
            {
                "schema_id": "continuous_research_process_event",
                "schema_version": "1.1.0",
                "run_id": self.run_id,
                "cycle_index": self.cycle_index,
                "sequence": sequence,
                "event_type": event_type,
                "payload_ref": payload_ref,
                "payload_digest": payload_digest,
                "payload_sha256": payload_sha256,
                "actor": actor,
                "recorded_at": recorded_at,
                "evidence_boundary": evidence_boundary,
                "previous_event_digest": (
                    ZERO_DIGEST if not events else events[-1]["event_digest"]
                ),
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "event_digest",
        )
        write_once_json(
            self.events_root / f"{sequence:04d}-{event_type}.json", event
        )
        return event

    def _verify_payload(
        self,
        payload_ref: str,
        payload_digest: str,
        *,
        expected_sha256: str | None = None,
    ) -> str:
        """Bind an event to a real contained file and its current physical bytes."""

        if (
            not payload_ref
            or Path(payload_ref).is_absolute()
            or _HEX_64.fullmatch(str(payload_digest or "")) is None
        ):
            raise ResearchCycleStoreError("CYCLE_EVENT_PAYLOAD_REF_INVALID")
        try:
            target = (self.run_root / payload_ref).resolve(strict=True)
            target.relative_to(self.run_root)
        except (OSError, ValueError) as exc:
            raise ResearchCycleStoreError("CYCLE_EVENT_PAYLOAD_REF_INVALID") from exc
        if not target.is_file():
            raise ResearchCycleStoreError("CYCLE_EVENT_PAYLOAD_REF_INVALID")
        physical_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected_sha256 is not None and (
            _HEX_64.fullmatch(expected_sha256) is None
            or physical_sha256 != expected_sha256
        ):
            raise ResearchCycleStoreError("CYCLE_EVENT_PAYLOAD_PHYSICAL_DRIFT")
        if payload_digest == physical_sha256:
            return physical_sha256
        try:
            document = load_json_strict(target)
        except ValueError as exc:
            raise ResearchCycleStoreError("CYCLE_EVENT_PAYLOAD_DIGEST_MISMATCH") from exc
        for field, value in document.items():
            if field.endswith("_digest") and value == payload_digest:
                try:
                    verify_self_digest(document, field)
                except ValueError:
                    continue
                return physical_sha256
        raise ResearchCycleStoreError("CYCLE_EVENT_PAYLOAD_DIGEST_MISMATCH")

    def seal_evidence_receipt(
        self,
        *,
        artifact_bindings: Mapping[str, str],
        recorded_at: str,
    ) -> dict[str, Any]:
        """Seal accepted cycle evidence without authorizing checkpoint advance."""

        receipt_path = (
            self.run_root
            / "evidence-receipts"
            / f"cycle-{self.cycle_index:04d}.json"
        )
        events = self.read_events()
        sorted_bindings = dict(sorted(artifact_bindings.items()))
        if receipt_path.exists():
            existing = load_json_strict(receipt_path)
            try:
                existing_digest = verify_self_digest(
                    existing, "cycle_evidence_receipt_digest"
                )
            except ValueError as exc:
                raise ResearchCycleStoreError(
                    "CYCLE_EVIDENCE_RECEIPT_DIGEST_INVALID"
                ) from exc
            if existing.get("artifact_bindings") != sorted_bindings:
                raise ResearchCycleStoreError(
                    "CYCLE_EVIDENCE_RECEIPT_WRITE_ONCE_CONFLICT"
                )
            if (
                events
                and events[-1]["event_type"]
                == "CYCLE_EVIDENCE_RECEIPT_SEALED"
            ):
                if events[-1]["payload_digest"] != existing_digest:
                    raise ResearchCycleStoreError(
                        "CYCLE_EVIDENCE_EVENT_BINDING_INVALID"
                    )
                return {
                    **existing,
                    "evidence_event_digest": events[-1]["event_digest"],
                }
            if tuple(event["event_type"] for event in events) != (
                PRE_EVIDENCE_RECEIPT_EVENT_TYPES
            ):
                raise ResearchCycleStoreError(
                    "CYCLE_PRE_EVIDENCE_CHAIN_INCOMPLETE"
                )
            evidence_event = self._append_event(
                event_type="CYCLE_EVIDENCE_RECEIPT_SEALED",
                payload_ref=receipt_path.relative_to(self.run_root).as_posix(),
                payload_digest=existing_digest,
                actor="DETERMINISTIC_EVIDENCE_COORDINATOR",
                recorded_at=recorded_at,
                evidence_boundary="BINDS_ACCEPTED_CYCLE_EVIDENCE_WITHOUT_CHECKPOINT_ADVANCE",
            )
            return {
                **existing,
                "evidence_event_digest": evidence_event["event_digest"],
            }
        if tuple(event["event_type"] for event in events) != (
            PRE_EVIDENCE_RECEIPT_EVENT_TYPES
        ):
            raise ResearchCycleStoreError("CYCLE_PRE_EVIDENCE_CHAIN_INCOMPLETE")
        if set(artifact_bindings) != REQUIRED_EVIDENCE_ARTIFACT_BINDINGS or any(
            _HEX_64.fullmatch(str(value or "")) is None
            for value in artifact_bindings.values()
        ):
            raise ResearchCycleStoreError(
                "CYCLE_EVIDENCE_BINDINGS_INCOMPLETE"
            )
        by_type = {event["event_type"]: event for event in events}
        for event_type, artifact_name in EVENT_ARTIFACT_BINDINGS.items():
            if artifact_name not in REQUIRED_EVIDENCE_ARTIFACT_BINDINGS:
                continue
            if by_type[event_type]["payload_digest"] != artifact_bindings[
                artifact_name
            ]:
                raise ResearchCycleStoreError(
                    f"CYCLE_EVIDENCE_ARTIFACT_BINDING_MISMATCH:{artifact_name}"
                )
        artifact_refs = {
            artifact_name: by_type[event_type]["payload_ref"]
            for event_type, artifact_name in EVENT_ARTIFACT_BINDINGS.items()
            if artifact_name in REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
        }
        artifact_sha256s = {
            artifact_name: by_type[event_type]["payload_sha256"]
            for event_type, artifact_name in EVENT_ARTIFACT_BINDINGS.items()
            if artifact_name in REQUIRED_EVIDENCE_ARTIFACT_BINDINGS
        }
        receipt = self_digest(
            {
                "schema_id": "continuous_cycle_evidence_receipt",
                "schema_version": "1.1.0",
                "run_id": self.run_id,
                "cycle_index": self.cycle_index,
                "recorded_at": recorded_at,
                "evidence_event_count": len(events),
                "evidence_chain_head_digest": events[-1]["event_digest"],
                "artifact_bindings": sorted_bindings,
                "artifact_refs": dict(sorted(artifact_refs.items())),
                "artifact_sha256s": dict(sorted(artifact_sha256s.items())),
                "checkpoint_advance_authorized": False,
                "review_source_artifact": artifact_refs[
                    "cycle_review_source_digest"
                ],
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "cycle_evidence_receipt_digest",
        )
        write_once_json(receipt_path, receipt)
        evidence_event = self._append_event(
            event_type="CYCLE_EVIDENCE_RECEIPT_SEALED",
            payload_ref=receipt_path.relative_to(self.run_root).as_posix(),
            payload_digest=receipt["cycle_evidence_receipt_digest"],
            actor="DETERMINISTIC_EVIDENCE_COORDINATOR",
            recorded_at=recorded_at,
            evidence_boundary="BINDS_ACCEPTED_CYCLE_EVIDENCE_WITHOUT_CHECKPOINT_ADVANCE",
        )
        return {
            **receipt,
            "evidence_event_digest": evidence_event["event_digest"],
        }

    def seal_completion(
        self,
        *,
        artifact_bindings: Mapping[str, str],
        accepted_state_path: str,
        recorded_at: str,
        review_digest: str | None,
    ) -> dict[str, Any]:
        receipt_path = (
            self.run_root
            / "completion-receipts"
            / f"cycle-{self.cycle_index:04d}.json"
        )
        events = self.read_events()
        if receipt_path.exists():
            existing = load_json_strict(receipt_path)
            try:
                existing_digest = verify_self_digest(
                    existing, "completion_receipt_digest"
                )
            except ValueError as exc:
                raise ResearchCycleStoreError(
                    "CYCLE_COMPLETION_DIGEST_INVALID"
                ) from exc
            if (
                existing.get("artifact_bindings")
                != dict(sorted(artifact_bindings.items()))
                or existing.get("accepted_state_path") != accepted_state_path
                or existing.get("review_digest") != review_digest
            ):
                raise ResearchCycleStoreError("CYCLE_COMPLETION_WRITE_ONCE_CONFLICT")
            if events and events[-1]["event_type"] == "CYCLE_COMPLETED":
                if events[-1]["payload_digest"] != existing_digest:
                    raise ResearchCycleStoreError(
                        "CYCLE_COMPLETION_EVENT_BINDING_INVALID"
                    )
                return {
                    **existing,
                    "completion_event_digest": events[-1]["event_digest"],
                }
            if tuple(event["event_type"] for event in events) != self.required_pre_completion_types:
                raise ResearchCycleStoreError("CYCLE_PRE_COMPLETION_CHAIN_INCOMPLETE")
            completed_event = self._append_event(
                event_type="CYCLE_COMPLETED",
                payload_ref=receipt_path.relative_to(self.run_root).as_posix(),
                payload_digest=existing_digest,
                actor="DETERMINISTIC_CYCLE_COORDINATOR",
                recorded_at=recorded_at,
                evidence_boundary="BINDS_ACCEPTED_STATE_COMPARATOR_REPORT_AND_DUE_REVIEW",
            )
            return {
                **existing,
                "completion_event_digest": completed_event["event_digest"],
            }
        expected = self.required_pre_completion_types
        if tuple(event["event_type"] for event in events) != expected:
            raise ResearchCycleStoreError("CYCLE_PRE_COMPLETION_CHAIN_INCOMPLETE")
        if set(artifact_bindings) != REQUIRED_ARTIFACT_BINDINGS or any(
            _HEX_64.fullmatch(str(value or "")) is None
            for value in artifact_bindings.values()
        ):
            raise ResearchCycleStoreError("CYCLE_COMPLETION_BINDINGS_INCOMPLETE")
        if self.cycle_index % 4 == 0:
            if _HEX_64.fullmatch(str(review_digest or "")) is None:
                raise ResearchCycleStoreError("CYCLE_REVIEW_BINDING_MISSING")
            if events[-1]["payload_digest"] != review_digest:
                raise ResearchCycleStoreError("CYCLE_REVIEW_BINDING_MISMATCH")
        elif review_digest is not None:
            raise ResearchCycleStoreError("CYCLE_REVIEW_UNSCHEDULED")
        by_type = {event["event_type"]: event for event in events}
        for event_type, artifact_name in EVENT_ARTIFACT_BINDINGS.items():
            if by_type[event_type]["payload_digest"] != artifact_bindings[artifact_name]:
                raise ResearchCycleStoreError(
                    f"CYCLE_EVENT_ARTIFACT_BINDING_MISMATCH:{artifact_name}"
                )
        if by_type["STATE_ACCEPTED"]["payload_ref"] != accepted_state_path:
            raise ResearchCycleStoreError("CYCLE_ACCEPTED_STATE_PATH_MISMATCH")
        artifact_refs = {
            artifact_name: by_type[event_type]["payload_ref"]
            for event_type, artifact_name in EVENT_ARTIFACT_BINDINGS.items()
        }
        artifact_sha256s = {
            artifact_name: by_type[event_type]["payload_sha256"]
            for event_type, artifact_name in EVENT_ARTIFACT_BINDINGS.items()
        }
        receipt = self_digest(
            {
                "schema_id": "continuous_research_cycle_completion_receipt",
                "schema_version": "1.1.0",
                "run_id": self.run_id,
                "cycle_index": self.cycle_index,
                "recorded_at": recorded_at,
                "pre_completion_event_count": len(events),
                "pre_completion_chain_head_digest": events[-1]["event_digest"],
                "artifact_bindings": dict(sorted(artifact_bindings.items())),
                "artifact_refs": dict(sorted(artifact_refs.items())),
                "artifact_sha256s": dict(sorted(artifact_sha256s.items())),
                "accepted_state_path": accepted_state_path,
                "review_digest": review_digest,
                "checkpoint_advance_authorized": True,
                "agent_reinvocation_required_for_recovery": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "completion_receipt_digest",
        )
        write_once_json(receipt_path, receipt)
        completed_event = self._append_event(
            event_type="CYCLE_COMPLETED",
            payload_ref=receipt_path.relative_to(self.run_root).as_posix(),
            payload_digest=receipt["completion_receipt_digest"],
            actor="DETERMINISTIC_CYCLE_COORDINATOR",
            recorded_at=recorded_at,
            evidence_boundary="BINDS_ACCEPTED_STATE_COMPARATOR_REPORT_AND_DUE_REVIEW",
        )
        return {
            **receipt,
            "completion_event_digest": completed_event["event_digest"],
        }

    def advance_checkpoint(
        self, *, checkpoint_path: Path, completion_receipt: Mapping[str, Any]
    ) -> dict[str, Any]:
        checkpoint = load_json_strict(checkpoint_path)
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except ValueError as exc:
            raise ResearchCycleStoreError("CHECKPOINT_DIGEST_INVALID") from exc
        events = self.read_events()
        if (
            checkpoint.get("run_id") != self.run_id
            or checkpoint.get("status") != "POST_ACCEPT_FINALIZATION"
            or checkpoint.get("next_cycle_index") != self.cycle_index
            or not events
            or events[-1]["event_type"] != "CYCLE_COMPLETED"
        ):
            raise ResearchCycleStoreError("CHECKPOINT_ADVANCE_PRECONDITION_FAILED")
        receipt_document = dict(completion_receipt)
        completion_event_digest = receipt_document.pop(
            "completion_event_digest", None
        )
        try:
            completion_digest = verify_self_digest(
                receipt_document, "completion_receipt_digest"
            )
        except ValueError as exc:
            raise ResearchCycleStoreError("CYCLE_COMPLETION_DIGEST_INVALID") from exc
        if (
            completion_receipt.get("run_id") != self.run_id
            or completion_receipt.get("cycle_index") != self.cycle_index
            or completion_receipt.get("checkpoint_advance_authorized") is not True
            or events[-1]["payload_digest"] != completion_digest
            or events[-1]["event_digest"] != completion_event_digest
        ):
            raise ResearchCycleStoreError("CHECKPOINT_COMPLETION_BINDING_INVALID")
        accepted_digest = completion_receipt["artifact_bindings"][
            "accepted_state_digest"
        ]
        if checkpoint.get("pending_accepted_state_digest") != accepted_digest:
            raise ResearchCycleStoreError("CHECKPOINT_ACCEPTED_STATE_MISMATCH")
        if (
            checkpoint.get("pending_accepted_state_path")
            != completion_receipt["accepted_state_path"]
        ):
            raise ResearchCycleStoreError("CHECKPOINT_ACCEPTED_STATE_MISMATCH")
        updated = dict(checkpoint)
        updated.update(
            {
                "status": "RUNNING_OUTCOMES_SEALED",
                "completed_cycles": self.cycle_index,
                "next_cycle_index": self.cycle_index + 1,
                "accepted_state_path": completion_receipt["accepted_state_path"],
                "accepted_state_digest": accepted_digest,
                "last_completion_receipt_digest": completion_digest,
                "last_process_chain_head_digest": events[-1]["event_digest"],
                "pending_accepted_state_path": None,
                "pending_accepted_state_digest": None,
                "pending_finalization_cycle": None,
            }
        )
        updated = self_digest(updated, "checkpoint_digest")
        _atomic_json(Path(checkpoint_path), updated)
        return updated

    def enter_post_accept_checkpoint(
        self,
        *,
        checkpoint_path: Path,
        accepted_state_path: str,
        accepted_state_digest: str,
    ) -> dict[str, Any]:
        checkpoint = load_json_strict(checkpoint_path)
        try:
            verify_self_digest(checkpoint, "checkpoint_digest")
        except ValueError as exc:
            raise ResearchCycleStoreError("CHECKPOINT_DIGEST_INVALID") from exc
        events = self.read_events()
        if (
            checkpoint.get("run_id") != self.run_id
            or checkpoint.get("next_cycle_index") != self.cycle_index
            or checkpoint.get("status")
            not in {
                "READY_FOR_CYCLE",
                "RUNNING_OUTCOMES_SEALED",
                "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED",
                "PRE_ACCEPT_RECOVERABLE_FAILURE",
                "POST_ACCEPT_FINALIZATION",
                "POST_ACCEPT_RECOVERABLE_FAILURE",
            }
            or not events
            or events[-1]["event_type"] != "ACTION_RECEIPT_SEALED"
        ):
            raise ResearchCycleStoreError("POST_ACCEPT_CHECKPOINT_PRECONDITION_FAILED")
        by_type = {event["event_type"]: event for event in events}
        if (
            by_type["STATE_ACCEPTED"]["payload_digest"] != accepted_state_digest
            or by_type["STATE_ACCEPTED"]["payload_ref"] != accepted_state_path
        ):
            raise ResearchCycleStoreError("POST_ACCEPT_CHECKPOINT_PRECONDITION_FAILED")
        updated = dict(checkpoint)
        updated.update(
            {
                "status": "POST_ACCEPT_FINALIZATION",
                "pending_finalization_cycle": self.cycle_index,
                "pending_accepted_state_path": accepted_state_path,
                "pending_accepted_state_digest": accepted_state_digest,
            }
        )
        updated = self_digest(updated, "checkpoint_digest")
        _atomic_json(Path(checkpoint_path), updated)
        return updated

    def post_accept_recovery_status(self) -> dict[str, Any]:
        next_event = self.next_required_event_type()
        deterministic_tail = {
            "COMPARATOR_SEALED",
            "REVIEW_SOURCE_SEALED",
            "CYCLE_EVIDENCE_RECEIPT_SEALED",
            "REPORT_SEALED",
            "REVIEW_SEALED",
            "CYCLE_COMPLETED",
            None,
        }
        return {
            "run_id": self.run_id,
            "cycle_index": self.cycle_index,
            "next_required_event_type": next_event,
            "agent_reinvocation_forbidden": next_event in deterministic_tail,
            "recovery_mode": (
                "DETERMINISTIC_POST_ACCEPT_FINALIZATION"
                if next_event in deterministic_tail
                else "PRE_ACCEPT_CONTINUE_WITH_EXISTING_SEALED_INPUTS"
            ),
        }
