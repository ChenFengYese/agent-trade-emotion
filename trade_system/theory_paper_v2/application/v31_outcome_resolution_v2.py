"""Raw-first successor composition for one delayed V3.1 outcome.

The frozen monitor remains a compatibility owner for monitor plans, sole
attempts, normalized source records, and outcome receipts.  This versioned
layer interposes a capture-only transport and an atomic evidence store so no
response body is semantically parsed before durable readback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ContextManager, Mapping, Protocol

from .v31_monitor_runtime import (
    V31MonitorRuntimeError,
    resolve_due_v31_monitor,
    v31_monitor_status,
)
from ..domain.v31_experiment_contracts import (
    ObservationMissingness,
    ObservationQuality,
    build_path_outcome_receipt,
    verify_minimal_experiment_contract,
    verify_path_outcome_receipt,
    verify_typed_path_monitor_plan,
)
from ..domain.v31_monitor_runtime import (
    OUTCOME_EVALUATOR_VERSION,
    PublicOutcomeReading,
    build_public_outcome_source_record,
    monitor_cycle_root,
    outcome_observation_from_source_record,
)
from ..domain.v31_outcome_capture_v2 import (
    OKX_MARK_PRICE_URL,
    build_outcome_clock_policy,
    parse_public_outcome_capture,
    verify_outcome_clock_policy,
    verify_public_outcome_parse_receipt,
)
class V31OutcomeResolutionV2Error(ValueError):
    """The raw-first successor outcome boundary failed closed."""


class V31PublicOutcomeCapturePortV2(Protocol):
    def capture_public_outcome(
        self,
        *,
        monitor_plan: Mapping[str, Any],
        attempt: Mapping[str, Any],
        requested_at: str,
    ) -> Mapping[str, Any]: ...


class V31OutcomeEvidenceStorePortV2(Protocol):
    def resolution_guard(self, *, run_id: str) -> ContextManager[None]: ...

    def initialize_checkpoint(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def register_legacy_attempt(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def commit_response_capture(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def recover_unbound_capture(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def load_committed_capture(
        self, **kwargs: Any
    ) -> tuple[Mapping[str, Any], bytes, Mapping[str, Any]]: ...

    def commit_parse_receipt(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def read_parse_receipt(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def bind_legacy_resolution(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def persist_transport_failure(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def recover_unbound_transport_failure(
        self, **kwargs: Any
    ) -> Mapping[str, Any] | None: ...

    def read_transport_failure(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def fail_checkpoint(self, **kwargs: Any) -> Mapping[str, Any]: ...


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31OutcomeResolutionV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31OutcomeResolutionV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31OutcomeResolutionV2Error(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31OutcomeResolutionV2Error(code)
    return normalized


def initialize_v31_outcome_evidence_runtime_v2(
    *,
    evidence_store: V31OutcomeEvidenceStorePortV2,
    experiment_contract: Mapping[str, Any],
    created_at: str,
    clock_policy: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    verify_minimal_experiment_contract(experiment_contract)
    _time(created_at, "V31_OUTCOME_V2_INITIALIZATION_TIME_INVALID")
    policy = dict(clock_policy or build_outcome_clock_policy())
    policy_digest = verify_outcome_clock_policy(policy)
    return evidence_store.initialize_checkpoint(
        run_id=str(experiment_contract["run_id"]),
        total_cycles=int(
            experiment_contract["cycle_protocol"]["accepted_cycle_count"]
        ),
        created_at=created_at,
        clock_policy_digest=policy_digest,
    )


def _verify_evidence_clock_policy(
    *,
    evidence_store: V31OutcomeEvidenceStorePortV2,
    run_id: str,
    clock_policy: Mapping[str, Any],
) -> str:
    policy_digest = verify_outcome_clock_policy(clock_policy)
    checkpoint = evidence_store.load_checkpoint(run_id=run_id)
    if checkpoint.get("clock_policy_digest") != policy_digest:
        raise V31OutcomeResolutionV2Error(
            "V31_OUTCOME_V2_CLOCK_POLICY_BINDING_MISMATCH"
        )
    return policy_digest


def _reading_from_receipt(
    *, receipt: Mapping[str, Any], raw_payload: bytes
) -> PublicOutcomeReading:
    status = receipt.get("parse_status")
    if status == "REJECTED":
        raise V31OutcomeResolutionV2Error(
            f"V31_OUTCOME_V2_PARSE_REJECTED:{receipt.get('error_code')}"
        )
    if status not in {"ADMITTED_OBSERVED", "ADMITTED_UNKNOWN"}:
        raise V31OutcomeResolutionV2Error(
            "V31_OUTCOME_V2_PARSE_STATUS_INVALID"
        )
    try:
        missingness = ObservationMissingness(str(receipt["missingness"]))
        quality = ObservationQuality(str(receipt["quality"]))
    except (KeyError, ValueError) as exc:
        raise V31OutcomeResolutionV2Error(
            "V31_OUTCOME_V2_PARSE_ENUM_INVALID"
        ) from exc
    return PublicOutcomeReading(
        raw_payload=raw_payload,
        source_locator=OKX_MARK_PRICE_URL,
        captured_at=str(receipt["evaluation_as_of"]),
        observable_ref=str(receipt["observable_ref"]),
        value=receipt["value"],
        as_of=str(receipt["evaluation_as_of"]),
        available_at=str(receipt["available_at"]),
        missingness=missingness,
        quality=quality,
        coverage=str(receipt["coverage"]),
        conflict_state=str(receipt["conflict_state"]),
        source_request_id=str(receipt["source_request_id"]),
    )


class _RawFirstObservationPortV2:
    def __init__(
        self,
        *,
        monitor_store: Any,
        evidence_store: V31OutcomeEvidenceStorePortV2,
        capture_port: V31PublicOutcomeCapturePortV2,
        clock_policy: Mapping[str, Any],
    ) -> None:
        self.monitor_store = monitor_store
        self.evidence_store = evidence_store
        self.capture_port = capture_port
        self.clock_policy = dict(clock_policy)
        verify_outcome_clock_policy(self.clock_policy)
        self.last_transport_failure: Mapping[str, Any] | None = None
        self.last_evidence_at: str | None = None

    def observe_public_outcome(
        self, *, monitor_plan: Mapping[str, Any], requested_at: str
    ) -> PublicOutcomeReading:
        run_id = str(monitor_plan["run_id"])
        cycle_index = int(monitor_plan["cycle_index"])
        checkpoint = self.monitor_store.load_checkpoint(run_id=run_id)
        if len(checkpoint["resolution_attempt_bindings"]) != cycle_index:
            raise V31OutcomeResolutionV2Error(
                "V31_OUTCOME_V2_ATTEMPT_NOT_RESERVED"
            )
        attempt_binding = checkpoint["resolution_attempt_bindings"][cycle_index - 1]
        attempt = self.monitor_store.read_document(
            relative_ref=attempt_binding["relative_ref"],
            digest_field="monitor_attempt_digest",
            expected_semantic_digest=attempt_binding["semantic_digest"],
        )
        self.evidence_store.register_legacy_attempt(
            run_id=run_id,
            cycle_index=cycle_index,
            recorded_at=requested_at,
        )
        envelope = self.capture_port.capture_public_outcome(
            monitor_plan=monitor_plan,
            attempt=attempt,
            requested_at=requested_at,
        )
        if envelope.get("transport_status") == "NO_RESPONSE":
            failure = envelope.get("transport_failure")
            if not isinstance(failure, Mapping):
                raise V31OutcomeResolutionV2Error(
                    "V31_OUTCOME_V2_TRANSPORT_FAILURE_INVALID"
                )
            self.evidence_store.persist_transport_failure(
                run_id=run_id,
                cycle_index=cycle_index,
                receipt=failure,
            )
            self.last_transport_failure = dict(failure)
            self.last_evidence_at = str(failure["failure_at"])
            raise V31OutcomeResolutionV2Error(
                f"V31_OUTCOME_V2_NO_RESPONSE:{failure['failure_code']}"
            )
        if envelope.get("transport_status") != "RESPONSE_CAPTURED":
            raise V31OutcomeResolutionV2Error(
                "V31_OUTCOME_V2_TRANSPORT_ENVELOPE_INVALID"
            )
        capture = envelope.get("capture")
        raw = envelope.get("raw_payload")
        if not isinstance(capture, Mapping) or not isinstance(raw, bytes):
            raise V31OutcomeResolutionV2Error(
                "V31_OUTCOME_V2_TRANSPORT_ENVELOPE_INVALID"
            )
        self.evidence_store.commit_response_capture(
            run_id=run_id,
            cycle_index=cycle_index,
            capture=capture,
            raw_payload=raw,
            committed_at=str(capture["response_received_at"]),
        )
        durable_capture, durable_raw, _ = (
            self.evidence_store.load_committed_capture(
                run_id=run_id, cycle_index=cycle_index
            )
        )
        receipt = parse_public_outcome_capture(
            capture=durable_capture,
            raw_payload=durable_raw,
            clock_policy=self.clock_policy,
            observable_ref=str(monitor_plan["observable"]["observable_ref"]),
        )
        self.evidence_store.commit_parse_receipt(
            run_id=run_id,
            cycle_index=cycle_index,
            receipt=receipt,
            clock_policy=self.clock_policy,
            observable_ref=str(monitor_plan["observable"]["observable_ref"]),
            committed_at=str(capture["response_received_at"]),
        )
        self.last_evidence_at = str(capture["response_received_at"])
        return _reading_from_receipt(receipt=receipt, raw_payload=durable_raw)


def _legacy_failure_digest(monitor_store: Any, *, run_id: str) -> str | None:
    try:
        checkpoint = monitor_store.load_checkpoint(run_id=run_id)
    except Exception:
        return None
    value = checkpoint.get("failure_digest")
    return value if isinstance(value, str) else None


def _fail_evidence_after_legacy_failure(
    *,
    evidence_store: V31OutcomeEvidenceStorePortV2,
    monitor_store: Any,
    run_id: str,
    cycle_index: int,
    failed_at: str,
    failure_code: str,
    transport_failure: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return evidence_store.fail_checkpoint(
        run_id=run_id,
        cycle_index=cycle_index,
        failure_code=failure_code,
        failed_at=failed_at,
        transport_failure=transport_failure,
        legacy_monitor_failure_digest=_legacy_failure_digest(
            monitor_store, run_id=run_id
        ),
    )


def _load_or_parse_committed_reading(
    *,
    evidence_store: V31OutcomeEvidenceStorePortV2,
    run_id: str,
    cycle_index: int,
    monitor_plan: Mapping[str, Any],
    clock_policy: Mapping[str, Any],
) -> PublicOutcomeReading:
    checkpoint = evidence_store.load_checkpoint(run_id=run_id)
    if len(checkpoint["capture_bindings"]) < cycle_index:
        evidence_store.recover_unbound_capture(
            run_id=run_id,
            cycle_index=cycle_index,
        )
        checkpoint = evidence_store.load_checkpoint(run_id=run_id)
    capture, raw, _ = evidence_store.load_committed_capture(
        run_id=run_id, cycle_index=cycle_index
    )
    observable_ref = str(monitor_plan["observable"]["observable_ref"])
    if len(checkpoint["parse_bindings"]) >= cycle_index:
        receipt = evidence_store.read_parse_receipt(
            run_id=run_id, cycle_index=cycle_index
        )
        verify_public_outcome_parse_receipt(
            receipt,
            capture=capture,
            raw_payload=raw,
            clock_policy=clock_policy,
            observable_ref=observable_ref,
        )
    else:
        receipt = parse_public_outcome_capture(
            capture=capture,
            raw_payload=raw,
            clock_policy=clock_policy,
            observable_ref=observable_ref,
        )
        evidence_store.commit_parse_receipt(
            run_id=run_id,
            cycle_index=cycle_index,
            receipt=receipt,
            clock_policy=clock_policy,
            observable_ref=observable_ref,
            committed_at=str(capture["response_received_at"]),
        )
    return _reading_from_receipt(receipt=receipt, raw_payload=raw)


def _complete_reserved_legacy_monitor(
    *,
    monitor_store: Any,
    experiment_contract: Mapping[str, Any],
    monitor_plan: Mapping[str, Any],
    reading: PublicOutcomeReading,
) -> Mapping[str, Any]:
    """Resume only deterministic local writes after a committed capture."""

    run_id = str(experiment_contract["run_id"])
    cycle_index = int(monitor_plan["cycle_index"])
    checkpoint = monitor_store.load_checkpoint(run_id=run_id)
    if (
        checkpoint["status"] != "ACTIVE"
        or len(checkpoint["resolution_attempt_bindings"]) != cycle_index
        or len(checkpoint["outcome_bindings"]) != cycle_index - 1
    ):
        raise V31OutcomeResolutionV2Error(
            "V31_OUTCOME_V2_RESERVED_STATE_INVALID"
        )
    origin_bindings = monitor_plan["origin_bindings"]
    verify_typed_path_monitor_plan(
        monitor_plan,
        experiment_contract=experiment_contract,
        expected_origin_bindings=origin_bindings,
    )
    captured = _time(
        reading.captured_at, "V31_OUTCOME_V2_CAPTURE_TIME_INVALID"
    )
    not_before = _time(
        monitor_plan["outcome_not_before"], "V31_OUTCOME_V2_PLAN_TIME_INVALID"
    )
    expires = _time(
        monitor_plan["expires_at"], "V31_OUTCOME_V2_PLAN_TIME_INVALID"
    )
    if (
        captured < not_before
        or captured > expires
        or reading.observable_ref != monitor_plan["observable"]["observable_ref"]
        or reading.source_request_id
        != monitor_plan["observable"]["source_request_id"]
    ):
        raise V31OutcomeResolutionV2Error(
            "V31_OUTCOME_V2_READING_WINDOW_MISMATCH"
        )
    previous_receipt = None
    previous_digest = checkpoint["last_outcome_receipt_digest"]
    if cycle_index > 1:
        previous_binding = checkpoint["outcome_bindings"][cycle_index - 2]
        previous_receipt = monitor_store.read_document(
            relative_ref=previous_binding["outcome_receipt_ref"],
            digest_field="outcome_receipt_digest",
            expected_semantic_digest=previous_binding["outcome_receipt_digest"],
        )
    root = monitor_cycle_root(cycle_index)
    raw_binding = monitor_store.write_raw(
        relative_ref=f"{root}/outcome-raw.bin", payload=reading.raw_payload
    )
    source_record = build_public_outcome_source_record(
        run_id=run_id,
        cycle_index=cycle_index,
        monitor_plan_digest=str(monitor_plan["monitor_plan_digest"]),
        reading=reading,
        raw_capture_ref=raw_binding["relative_ref"],
        raw_capture_sha256=raw_binding["physical_sha256"],
    )
    source_binding = monitor_store.write_document(
        relative_ref=f"{root}/source-record.json",
        document=source_record,
        digest_field="source_record_digest",
    )
    observation = outcome_observation_from_source_record(source_record)
    observation_binding = monitor_store.write_document(
        relative_ref=f"{root}/outcome-observation.json",
        document=observation.to_document(),
        digest_field="observation_digest",
    )
    outcome_receipt = build_path_outcome_receipt(
        experiment_contract=experiment_contract,
        monitor_plan=monitor_plan,
        expected_origin_bindings=origin_bindings,
        outcome_receipt_id=f"outcome:{cycle_index}",
        evaluated_at=reading.captured_at,
        evaluator_version=OUTCOME_EVALUATOR_VERSION,
        observation=observation,
        previous_outcome_receipt=previous_receipt,
        expected_previous_outcome_receipt_digest=previous_digest,
    )
    verify_path_outcome_receipt(
        outcome_receipt,
        experiment_contract=experiment_contract,
        monitor_plan=monitor_plan,
        expected_origin_bindings=origin_bindings,
        previous_outcome_receipt=previous_receipt,
        expected_previous_outcome_receipt_digest=previous_digest,
    )
    receipt_binding = monitor_store.write_document(
        relative_ref=f"{root}/outcome-receipt.json",
        document=outcome_receipt,
        digest_field="outcome_receipt_digest",
    )
    current = monitor_store.load_checkpoint(run_id=run_id)
    if current["checkpoint_digest"] != checkpoint["checkpoint_digest"]:
        raise V31OutcomeResolutionV2Error("V31_OUTCOME_V2_MONITOR_CAS_CONFLICT")
    outcome_binding = {
        "cycle_index": cycle_index,
        "raw_capture_ref": raw_binding["relative_ref"],
        "raw_capture_sha256": raw_binding["physical_sha256"],
        "source_record_ref": source_binding["relative_ref"],
        "source_record_digest": source_binding["semantic_digest"],
        "source_record_physical_sha256": source_binding["physical_sha256"],
        "observation_ref": observation_binding["relative_ref"],
        "observation_digest": observation_binding["semantic_digest"],
        "observation_physical_sha256": observation_binding["physical_sha256"],
        "outcome_receipt_ref": receipt_binding["relative_ref"],
        "outcome_receipt_digest": receipt_binding["semantic_digest"],
        "outcome_receipt_physical_sha256": receipt_binding["physical_sha256"],
    }
    resolved = monitor_store.replace_checkpoint(
        run_id=run_id,
        expected_checkpoint_digest=str(current["checkpoint_digest"]),
        checkpoint={
            **current,
            "revision": int(current["revision"]) + 1,
            "status": "TERMINAL" if cycle_index == 8 else "ACTIVE",
            "outcome_bindings": [*current["outcome_bindings"], outcome_binding],
            "last_outcome_receipt_digest": receipt_binding["semantic_digest"],
            "updated_at": reading.captured_at,
        },
    )
    return {
        "run_id": run_id,
        "runtime_status": "RESOLVED_FROM_COMMITTED_CAPTURE",
        "cycle_index": cycle_index,
        "expectation_outcome": outcome_receipt["expectation_outcome"],
        "path_outcome": outcome_receipt["path_outcome"],
        "coverage_loss": outcome_receipt["coverage_loss"],
        "outcome_receipt_digest": outcome_receipt["outcome_receipt_digest"],
        "checkpoint_digest": resolved["checkpoint_digest"],
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def _resolve_due_v31_monitor_v2_locked(
    *,
    monitor_store: Any,
    evidence_store: V31OutcomeEvidenceStorePortV2,
    experiment_contract: Mapping[str, Any],
    capture_port: V31PublicOutcomeCapturePortV2,
    requested_at: str,
    clock_policy: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Resolve at most one due outcome, with response capture before parse."""

    verify_minimal_experiment_contract(experiment_contract)
    policy = dict(clock_policy or build_outcome_clock_policy())
    verify_outcome_clock_policy(policy)
    run_id = str(experiment_contract["run_id"])
    _verify_evidence_clock_policy(
        evidence_store=evidence_store,
        run_id=run_id,
        clock_policy=policy,
    )
    status = v31_monitor_status(
        store=monitor_store,
        experiment_contract=experiment_contract,
        observed_at=requested_at,
    )
    runtime_status = status["runtime_status"]
    if runtime_status in {"NOT_DUE", "TERMINAL", "FAILED_CLOSED"}:
        return status
    if runtime_status == "AWAITING_ACCEPTED_STATE":
        evidence = evidence_store.load_checkpoint(run_id=run_id)
        if len(evidence["resolution_bindings"]) < len(
            monitor_store.load_checkpoint(run_id=run_id)["outcome_bindings"]
        ):
            cycle_index = len(evidence["resolution_bindings"]) + 1
            return evidence_store.bind_legacy_resolution(
                run_id=run_id, cycle_index=cycle_index, bound_at=requested_at
            )
        return status
    if runtime_status == "ATTEMPT_RESERVED_NO_RETRY":
        cycle_index = int(status["due_cycle_index"])
        evidence_store.register_legacy_attempt(
            run_id=run_id, cycle_index=cycle_index, recorded_at=requested_at
        )
        monitor_checkpoint = monitor_store.load_checkpoint(run_id=run_id)
        plan_binding = monitor_checkpoint["plan_bindings"][cycle_index - 1]
        monitor_plan = monitor_store.read_document(
            relative_ref=plan_binding["relative_ref"],
            digest_field="monitor_plan_digest",
            expected_semantic_digest=plan_binding["semantic_digest"],
        )
        recovered_transport = evidence_store.recover_unbound_transport_failure(
            run_id=run_id,
            cycle_index=cycle_index,
        )
        if recovered_transport is not None:
            transport_failure = evidence_store.read_transport_failure(
                run_id=run_id,
                cycle_index=cycle_index,
            )
            current = monitor_store.load_checkpoint(run_id=run_id)
            if current["status"] == "ACTIVE":
                monitor_store.fail_checkpoint(
                    run_id=run_id,
                    expected_checkpoint_digest=str(current["checkpoint_digest"]),
                    failure_code="V31_MONITOR_V2_NO_RESPONSE_RECOVERED",
                    failure_summary=str(transport_failure["failure_code"]),
                    occurred_at=requested_at,
                )
            evidence_store.fail_checkpoint(
                run_id=run_id,
                cycle_index=cycle_index,
                failure_code="V31_OUTCOME_V2_NO_RESPONSE_RECOVERED",
                failed_at=requested_at,
                transport_failure=transport_failure,
                legacy_monitor_failure_digest=_legacy_failure_digest(
                    monitor_store, run_id=run_id
                ),
            )
            raise V31OutcomeResolutionV2Error(
                "V31_OUTCOME_V2_NO_RESPONSE_RECOVERED:"
                f"{transport_failure['failure_code']}"
            )
        try:
            reading = _load_or_parse_committed_reading(
                evidence_store=evidence_store,
                run_id=run_id,
                cycle_index=cycle_index,
                monitor_plan=monitor_plan,
                clock_policy=policy,
            )
            result = _complete_reserved_legacy_monitor(
                monitor_store=monitor_store,
                experiment_contract=experiment_contract,
                monitor_plan=monitor_plan,
                reading=reading,
            )
            evidence_store.bind_legacy_resolution(
                run_id=run_id,
                cycle_index=cycle_index,
                bound_at=reading.captured_at,
            )
            return result
        except Exception as exc:
            try:
                current = monitor_store.load_checkpoint(run_id=run_id)
                if current["status"] == "ACTIVE":
                    monitor_store.fail_checkpoint(
                        run_id=run_id,
                        expected_checkpoint_digest=str(current["checkpoint_digest"]),
                        failure_code="V31_MONITOR_V2_LOCAL_RECOVERY_FAILED",
                        failure_summary=f"{type(exc).__name__}:{exc}",
                        occurred_at=requested_at,
                    )
            finally:
                _fail_evidence_after_legacy_failure(
                    evidence_store=evidence_store,
                    monitor_store=monitor_store,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    failed_at=requested_at,
                    failure_code="V31_OUTCOME_V2_LOCAL_RECOVERY_FAILED",
                )
            raise V31OutcomeResolutionV2Error(
                "V31_OUTCOME_V2_LOCAL_RECOVERY_FAILED"
            ) from exc
    if runtime_status != "DUE":
        raise V31OutcomeResolutionV2Error(
            f"V31_OUTCOME_V2_STATUS_INVALID:{runtime_status}"
        )
    cycle_index = int(status["due_cycle_index"])
    observation_port = _RawFirstObservationPortV2(
        monitor_store=monitor_store,
        evidence_store=evidence_store,
        capture_port=capture_port,
        clock_policy=policy,
    )
    try:
        result = resolve_due_v31_monitor(
            store=monitor_store,
            experiment_contract=experiment_contract,
            observation_port=observation_port,
            requested_at=requested_at,
        )
        evidence_store.bind_legacy_resolution(
            run_id=run_id,
            cycle_index=cycle_index,
            bound_at=observation_port.last_evidence_at or requested_at,
        )
        return result
    except Exception as exc:
        _fail_evidence_after_legacy_failure(
            evidence_store=evidence_store,
            monitor_store=monitor_store,
            run_id=run_id,
            cycle_index=cycle_index,
            failed_at=observation_port.last_evidence_at or requested_at,
            failure_code="V31_OUTCOME_V2_RESOLUTION_FAILED",
            transport_failure=observation_port.last_transport_failure,
        )
        if isinstance(exc, V31OutcomeResolutionV2Error):
            raise
        if isinstance(exc, V31MonitorRuntimeError):
            raise V31OutcomeResolutionV2Error(
                "V31_OUTCOME_V2_LEGACY_MONITOR_FAILED"
            ) from exc
        raise V31OutcomeResolutionV2Error(
            "V31_OUTCOME_V2_RESOLUTION_FAILED"
        ) from exc


def resolve_due_v31_monitor_v2(
    *,
    monitor_store: Any,
    evidence_store: V31OutcomeEvidenceStorePortV2,
    experiment_contract: Mapping[str, Any],
    capture_port: V31PublicOutcomeCapturePortV2,
    requested_at: str,
    clock_policy: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Serialize and resolve at most one due outcome for this run."""

    verify_minimal_experiment_contract(experiment_contract)
    run_id = str(experiment_contract["run_id"])
    with evidence_store.resolution_guard(run_id=run_id):
        return _resolve_due_v31_monitor_v2_locked(
            monitor_store=monitor_store,
            evidence_store=evidence_store,
            experiment_contract=experiment_contract,
            capture_port=capture_port,
            requested_at=requested_at,
            clock_policy=clock_policy,
        )


__all__ = [
    "V31OutcomeEvidenceStorePortV2",
    "V31OutcomeResolutionV2Error",
    "V31PublicOutcomeCapturePortV2",
    "initialize_v31_outcome_evidence_runtime_v2",
    "resolve_due_v31_monitor_v2",
]
