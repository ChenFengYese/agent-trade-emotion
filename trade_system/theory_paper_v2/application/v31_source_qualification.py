"""Production coordinator for one V3.1 OKX public-source qualification.

The coordinator accepts explicit collector, adapter, clock, and store ports.  It
has no authority/config mutation and no research-run creation path.  A durable
reservation and a CAS transition to ``COLLECTING`` occur under an exclusive
lease before the collector can be called.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from hashlib import sha256
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..domain.information_model import information_event_to_canonical_dict
from ..domain.v31_source_qualification import (
    V31SourceQualificationError,
    seal_v31_source_qualification_completion,
    seal_v31_source_qualification_failure,
    seal_v31_source_qualification_information_event_record,
    seal_v31_source_qualification_plan,
    seal_v31_source_qualification_reservation,
    transition_v31_source_qualification_checkpoint,
    validate_v31_source_qualification_collection,
    verify_v31_source_qualification_checkpoint,
    verify_v31_source_qualification_completion,
    verify_v31_source_qualification_plan,
    verify_v31_source_qualification_reservation,
)


class V31SourceQualificationWorkflowError(ValueError):
    """The Q6 workflow failed closed without retrying collection."""


_STABLE_FAILURE_CODE = re.compile(r"^[A-Z][A-Z0-9_:.\-]{0,159}$")


def _root_cause_code(exc: BaseException) -> str:
    """Persist a stable domain code without leaking arbitrary exception text."""

    if isinstance(exc, (V31SourceQualificationError, V31SourceQualificationWorkflowError)):
        candidate = str(exc).strip()
        if _STABLE_FAILURE_CODE.fullmatch(candidate) is not None:
            return candidate
    return f"UNAVAILABLE_{type(exc).__name__.upper()}"


PLAN_REF = "frozen/source-qualification-plan.json"
RESERVATION_REF = "reservation/source-qualification-reservation.json"
SNAPSHOT_REF = "source/native-market-snapshot.json"
DATASET_REF = "adapted/pit-dataset.json"
COMPLETION_REF = "receipts/source-qualification-completion.json"
FAILURE_REF = "receipts/source-qualification-failure.json"


class V31SourceQualificationStorePort(Protocol):
    def exclusive_lease(
        self, *, qualification_id: str
    ) -> AbstractContextManager[None]: ...

    def document_exists(self, *, relative_ref: str) -> bool: ...

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...

    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]: ...

    def read_raw(
        self, *, relative_ref: str, expected_sha256: str | None = None
    ) -> bytes: ...

    def initialize_checkpoint(
        self,
        *,
        qualification_id: str,
        plan_binding: Mapping[str, Any],
        reservation_binding: Mapping[str, Any],
        created_at: str,
    ) -> Mapping[str, Any]: ...

    def load_checkpoint(self, *, qualification_id: str) -> Mapping[str, Any]: ...

    def replace_checkpoint(
        self,
        *,
        qualification_id: str,
        expected_checkpoint_digest: str,
        checkpoint: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class SourceQualificationCollectionPort(Protocol):
    snapshot: Mapping[str, Any]
    raw_body_by_request_id: Mapping[str, bytes]


class V31SourceQualificationCollectorPort(Protocol):
    def collect(
        self,
        *,
        run_id: str,
        cycle_index: int,
        prior_market_snapshot: Mapping[str, Any] | None = None,
    ) -> SourceQualificationCollectionPort: ...


class SourceQualificationAdaptationPort(Protocol):
    adapter_id: str
    run_id: str
    cycle_index: int
    source_snapshot_digest: str
    dataset_document: Mapping[str, Any]
    information_events: Sequence[Any]


SourceAdapter = Callable[..., SourceQualificationAdaptationPort]
Clock = Callable[[], str]


def _binding_matches(
    store: V31SourceQualificationStorePort,
    *,
    binding: Mapping[str, Any],
    digest_field: str,
) -> None:
    current = store.artifact_binding(
        relative_ref=str(binding["relative_ref"]),
        digest_field=digest_field,
        expected_semantic_digest=str(binding["semantic_digest"]),
    )
    if current != dict(binding):
        raise V31SourceQualificationWorkflowError(
            "V31_SOURCE_QUALIFICATION_PHYSICAL_BINDING_DRIFT"
        )


def _load_plan_and_reservation(
    *,
    store: V31SourceQualificationStorePort,
    checkpoint: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    plan_binding = checkpoint["plan_binding"]
    reservation_binding = checkpoint["reservation_binding"]
    plan = store.read_document(
        relative_ref=str(plan_binding["relative_ref"]),
        digest_field="source_qualification_plan_digest",
        expected_semantic_digest=str(plan_binding["semantic_digest"]),
    )
    reservation = store.read_document(
        relative_ref=str(reservation_binding["relative_ref"]),
        digest_field="source_qualification_reservation_digest",
        expected_semantic_digest=str(reservation_binding["semantic_digest"]),
    )
    verify_v31_source_qualification_plan(plan)
    verify_v31_source_qualification_reservation(reservation, plan=plan)
    _binding_matches(
        store=store,
        binding=plan_binding,
        digest_field="source_qualification_plan_digest",
    )
    _binding_matches(
        store=store,
        binding=reservation_binding,
        digest_field="source_qualification_reservation_digest",
    )
    return plan, reservation


def initialize_v31_source_qualification(
    *,
    store: V31SourceQualificationStorePort,
    qualification_id: str,
    created_at: str,
    theory_sha256: str,
) -> Mapping[str, Any]:
    """Durably freeze and reserve a qualification without calling a source."""

    with store.exclusive_lease(qualification_id=qualification_id):
        plan = seal_v31_source_qualification_plan(
            qualification_id=qualification_id,
            created_at=created_at,
            theory_sha256=theory_sha256,
        )
        plan_binding = store.write_document(
            relative_ref=PLAN_REF,
            document=plan,
            digest_field="source_qualification_plan_digest",
        )
        reservation = seal_v31_source_qualification_reservation(
            plan=plan, reserved_at=created_at
        )
        reservation_binding = store.write_document(
            relative_ref=RESERVATION_REF,
            document=reservation,
            digest_field="source_qualification_reservation_digest",
        )
        checkpoint = store.initialize_checkpoint(
            qualification_id=qualification_id,
            plan_binding=plan_binding,
            reservation_binding=reservation_binding,
            created_at=created_at,
        )
        verify_v31_source_qualification_checkpoint(checkpoint)
        if checkpoint.get("status") != "RESERVED":
            raise V31SourceQualificationWorkflowError(
                "V31_SOURCE_QUALIFICATION_ALREADY_STARTED"
            )
        return source_qualification_status(
            store=store, qualification_id=qualification_id
        )


def _mark_failed(
    *,
    store: V31SourceQualificationStorePort,
    qualification_id: str,
    checkpoint: Mapping[str, Any],
    plan: Mapping[str, Any],
    reservation: Mapping[str, Any],
    failed_at: str,
    phase: str,
    reason_code: str,
    root_cause_code: str,
) -> Mapping[str, Any]:
    failure = seal_v31_source_qualification_failure(
        plan=plan,
        reservation=reservation,
        failed_at=failed_at,
        failed_phase=phase,
        reason_code=reason_code,
        root_cause_code=root_cause_code,
    )
    failure_binding = store.write_document(
        relative_ref=FAILURE_REF,
        document=failure,
        digest_field="source_qualification_failure_digest",
    )
    candidate = transition_v31_source_qualification_checkpoint(
        current=checkpoint,
        status="FAILED_CLOSED",
        updated_at=failed_at,
        failure_binding=failure_binding,
    )
    return store.replace_checkpoint(
        qualification_id=qualification_id,
        expected_checkpoint_digest=str(
            checkpoint["source_qualification_checkpoint_digest"]
        ),
        checkpoint=candidate,
    )


def _verify_durable_completion(
    *,
    store: V31SourceQualificationStorePort,
    checkpoint: Mapping[str, Any],
    plan: Mapping[str, Any],
    reservation: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, str]]:
    receipt = store.read_document(
        relative_ref=COMPLETION_REF,
        digest_field="source_qualification_completion_digest",
    )
    verify_v31_source_qualification_completion(receipt)
    completion_binding = store.artifact_binding(
        relative_ref=COMPLETION_REF,
        digest_field="source_qualification_completion_digest",
        expected_semantic_digest=str(
            receipt["source_qualification_completion_digest"]
        ),
    )
    if (
        receipt.get("qualification_id") != checkpoint["qualification_id"]
        or receipt.get("source_qualification_plan_digest")
        != plan["source_qualification_plan_digest"]
        or receipt.get("source_qualification_reservation_digest")
        != reservation["source_qualification_reservation_digest"]
    ):
        raise V31SourceQualificationWorkflowError(
            "V31_SOURCE_QUALIFICATION_COMPLETION_IDENTITY_INVALID"
        )
    snapshot_binding = receipt["snapshot_binding"]
    snapshot = store.read_document(
        relative_ref=str(snapshot_binding["relative_ref"]),
        digest_field="native_market_snapshot_digest",
        expected_semantic_digest=str(snapshot_binding["semantic_digest"]),
    )
    _binding_matches(
        store=store,
        binding=snapshot_binding,
        digest_field="native_market_snapshot_digest",
    )
    raw_bodies: dict[str, bytes] = {}
    for request_id, binding in receipt["raw_bindings"].items():
        payload = store.read_raw(
            relative_ref=str(binding["relative_ref"]),
            expected_sha256=str(binding["semantic_digest"]),
        )
        if sha256(payload).hexdigest() != binding["physical_sha256"]:
            raise V31SourceQualificationWorkflowError(
                "V31_SOURCE_QUALIFICATION_RAW_READBACK_MISMATCH"
            )
        raw_bodies[str(request_id)] = payload
    validate_v31_source_qualification_collection(
        plan=plan,
        snapshot=snapshot,
        raw_body_by_request_id=raw_bodies,
        decision_at=str(receipt["decision_at"]),
    )
    dataset_binding = receipt["pit_dataset_binding"]
    dataset = store.read_document(
        relative_ref=str(dataset_binding["relative_ref"]),
        digest_field="dataset_digest",
        expected_semantic_digest=str(dataset_binding["semantic_digest"]),
    )
    _binding_matches(
        store=store, binding=dataset_binding, digest_field="dataset_digest"
    )
    records: list[Mapping[str, Any]] = []
    record_bindings: list[Mapping[str, str]] = []
    for binding in receipt["information_event_bindings"]:
        record = store.read_document(
            relative_ref=str(binding["relative_ref"]),
            digest_field="source_qualification_information_event_record_digest",
            expected_semantic_digest=str(binding["semantic_digest"]),
        )
        _binding_matches(
            store=store,
            binding=binding,
            digest_field="source_qualification_information_event_record_digest",
        )
        records.append(record)
        record_bindings.append(dict(binding))
    rebuilt = seal_v31_source_qualification_completion(
        plan=plan,
        reservation=reservation,
        completed_at=str(receipt["completed_at"]),
        decision_at=str(receipt["decision_at"]),
        snapshot=snapshot,
        snapshot_binding=snapshot_binding,
        raw_bindings=receipt["raw_bindings"],
        pit_dataset=dataset,
        pit_dataset_binding=dataset_binding,
        information_event_records=records,
        information_event_bindings=record_bindings,
        adapter_id=str(receipt["adapter_id"]),
    )
    if rebuilt != dict(receipt):
        raise V31SourceQualificationWorkflowError(
            "V31_SOURCE_QUALIFICATION_COMPLETION_REPLAY_MISMATCH"
        )
    return receipt, dict(completion_binding)


def execute_v31_source_qualification(
    *,
    store: V31SourceQualificationStorePort,
    qualification_id: str,
    collector: V31SourceQualificationCollectorPort,
    adapter: SourceAdapter,
    clock: Clock,
) -> Mapping[str, Any]:
    """Execute at most one collector call and seal its durable Q6 evidence."""

    with store.exclusive_lease(qualification_id=qualification_id):
        checkpoint = store.load_checkpoint(qualification_id=qualification_id)
        verify_v31_source_qualification_checkpoint(checkpoint)
        plan, reservation = _load_plan_and_reservation(
            store=store, checkpoint=checkpoint
        )
        status = str(checkpoint["status"])
        if status == "SEALED":
            receipt, _ = _verify_durable_completion(
                store=store,
                checkpoint=checkpoint,
                plan=plan,
                reservation=reservation,
            )
            return {
                "qualification_id": qualification_id,
                "status": "SEALED",
                "collector_attempt_count": 1,
                "collector_called_this_invocation": False,
                "completion_digest": receipt[
                    "source_qualification_completion_digest"
                ],
                "checkpoint_digest": checkpoint[
                    "source_qualification_checkpoint_digest"
                ],
                "qualification_only": True,
                "experiment_started": False,
            }
        if status == "FAILED_CLOSED":
            raise V31SourceQualificationWorkflowError(
                "V31_SOURCE_QUALIFICATION_PERMANENTLY_FAILED"
            )
        if status == "COLLECTING":
            if store.document_exists(relative_ref=COMPLETION_REF):
                receipt, completion_binding = _verify_durable_completion(
                    store=store,
                    checkpoint=checkpoint,
                    plan=plan,
                    reservation=reservation,
                )
                candidate = transition_v31_source_qualification_checkpoint(
                    current=checkpoint,
                    status="SEALED",
                    updated_at=str(receipt["completed_at"]),
                    completion_binding=completion_binding,
                )
                sealed = store.replace_checkpoint(
                    qualification_id=qualification_id,
                    expected_checkpoint_digest=str(
                        checkpoint["source_qualification_checkpoint_digest"]
                    ),
                    checkpoint=candidate,
                )
                return {
                    "qualification_id": qualification_id,
                    "status": "SEALED",
                    "collector_attempt_count": 1,
                    "collector_called_this_invocation": False,
                    "completion_digest": receipt[
                        "source_qualification_completion_digest"
                    ],
                    "checkpoint_digest": sealed[
                        "source_qualification_checkpoint_digest"
                    ],
                    "recovered_deterministic_tail": True,
                    "qualification_only": True,
                    "experiment_started": False,
                }
            failed_at = clock()
            failed = _mark_failed(
                store=store,
                qualification_id=qualification_id,
                checkpoint=checkpoint,
                plan=plan,
                reservation=reservation,
                failed_at=failed_at,
                phase="COLLECTOR_DELIVERY_RECOVERY",
                reason_code="COLLECTING_WITHOUT_COMPLETE_DELIVERY_NO_RETRY",
                root_cause_code=(
                    "COLLECTING_WITHOUT_COMPLETE_DELIVERY_NO_RETRY"
                ),
            )
            raise V31SourceQualificationWorkflowError(
                "V31_SOURCE_QUALIFICATION_INTERRUPTED_NO_RETRY:"
                f"{failed['source_qualification_checkpoint_digest']}"
            )
        if status != "RESERVED":
            raise V31SourceQualificationWorkflowError(
                "V31_SOURCE_QUALIFICATION_CHECKPOINT_STATUS_INVALID"
            )

        collecting_at = clock()
        candidate = transition_v31_source_qualification_checkpoint(
            current=checkpoint,
            status="COLLECTING",
            updated_at=collecting_at,
        )
        checkpoint = store.replace_checkpoint(
            qualification_id=qualification_id,
            expected_checkpoint_digest=str(
                checkpoint["source_qualification_checkpoint_digest"]
            ),
            checkpoint=candidate,
        )
        readback = store.load_checkpoint(qualification_id=qualification_id)
        if (
            readback != checkpoint
            or readback.get("status") != "COLLECTING"
            or readback.get("attempt_count") != 1
        ):
            raise V31SourceQualificationWorkflowError(
                "V31_SOURCE_QUALIFICATION_RESERVATION_READBACK_INVALID"
            )

        phase = "SOURCE_COLLECTION"
        try:
            collection = collector.collect(
                run_id=qualification_id,
                cycle_index=1,
                prior_market_snapshot=None,
            )
            snapshot = collection.snapshot
            raw_bodies = collection.raw_body_by_request_id
            decision_at = clock()
            validate_v31_source_qualification_collection(
                plan=plan,
                snapshot=snapshot,
                raw_body_by_request_id=raw_bodies,
                decision_at=decision_at,
            )

            phase = "RAW_AND_SNAPSHOT_PERSISTENCE"
            raw_bindings: dict[str, Mapping[str, str]] = {}
            for request_id in sorted(raw_bodies):
                relative_ref = (
                    f"cycles/0001/market/raw/{request_id}.body"
                )
                binding = store.write_raw(
                    relative_ref=relative_ref, payload=raw_bodies[request_id]
                )
                readback_raw = store.read_raw(
                    relative_ref=relative_ref,
                    expected_sha256=str(binding["semantic_digest"]),
                )
                if (
                    readback_raw != raw_bodies[request_id]
                    or sha256(readback_raw).hexdigest()
                    != binding["physical_sha256"]
                ):
                    raise V31SourceQualificationWorkflowError(
                        "V31_SOURCE_QUALIFICATION_RAW_READBACK_MISMATCH"
                    )
                raw_bindings[request_id] = binding
            snapshot_binding = store.write_document(
                relative_ref=SNAPSHOT_REF,
                document=snapshot,
                digest_field="native_market_snapshot_digest",
            )

            phase = "V31_MARKET_ADAPTATION"
            adaptation = adapter(snapshot, decision_at=decision_at)
            if (
                adaptation.run_id != qualification_id
                or adaptation.cycle_index != 1
                or adaptation.source_snapshot_digest
                != snapshot["native_market_snapshot_digest"]
                or adaptation.adapter_id != "V31_NATIVE_PUBLIC_ADAPTER_V1"
                or not adaptation.information_events
            ):
                raise V31SourceQualificationWorkflowError(
                    "V31_SOURCE_QUALIFICATION_ADAPTER_BINDING_INVALID"
                )
            dataset = adaptation.dataset_document
            dataset_binding = store.write_document(
                relative_ref=DATASET_REF,
                document=dataset,
                digest_field="dataset_digest",
            )
            event_records: list[Mapping[str, Any]] = []
            event_bindings: list[Mapping[str, str]] = []
            for index, event in enumerate(adaptation.information_events, start=1):
                record = seal_v31_source_qualification_information_event_record(
                    qualification_id=qualification_id,
                    event_document=information_event_to_canonical_dict(event),
                )
                event_records.append(record)
                event_bindings.append(
                    store.write_document(
                        relative_ref=(
                            f"adapted/information-event-{index:04d}.json"
                        ),
                        document=record,
                        digest_field=(
                            "source_qualification_information_event_record_digest"
                        ),
                    )
                )

            phase = "COMPLETION_SEAL"
            completed_at = clock()
            receipt = seal_v31_source_qualification_completion(
                plan=plan,
                reservation=reservation,
                completed_at=completed_at,
                decision_at=decision_at,
                snapshot=snapshot,
                snapshot_binding=snapshot_binding,
                raw_bindings=raw_bindings,
                pit_dataset=dataset,
                pit_dataset_binding=dataset_binding,
                information_event_records=event_records,
                information_event_bindings=event_bindings,
                adapter_id=adaptation.adapter_id,
            )
            completion_binding = store.write_document(
                relative_ref=COMPLETION_REF,
                document=receipt,
                digest_field="source_qualification_completion_digest",
            )
            durable_receipt, durable_binding = _verify_durable_completion(
                store=store,
                checkpoint=checkpoint,
                plan=plan,
                reservation=reservation,
            )
            if (
                durable_receipt != receipt
                or durable_binding != dict(completion_binding)
            ):
                raise V31SourceQualificationWorkflowError(
                    "V31_SOURCE_QUALIFICATION_COMPLETION_READBACK_MISMATCH"
                )

            phase = "CHECKPOINT_SEAL"
            sealed_candidate = transition_v31_source_qualification_checkpoint(
                current=checkpoint,
                status="SEALED",
                updated_at=completed_at,
                completion_binding=completion_binding,
            )
            checkpoint = store.replace_checkpoint(
                qualification_id=qualification_id,
                expected_checkpoint_digest=str(
                    checkpoint["source_qualification_checkpoint_digest"]
                ),
                checkpoint=sealed_candidate,
            )
            return {
                "qualification_id": qualification_id,
                "status": "SEALED",
                "collector_attempt_count": 1,
                "collector_called_this_invocation": True,
                "completion_digest": receipt[
                    "source_qualification_completion_digest"
                ],
                "checkpoint_digest": checkpoint[
                    "source_qualification_checkpoint_digest"
                ],
                "source_evidence_boundary": "SOURCE_ATTESTED",
                "source_quality_ceiling": "VERIFIED_SECONDARY",
                "qualification_only": True,
                "experiment_started": False,
                "account_data_accessed": False,
                "order_data_accessed": False,
                "executable": False,
            }
        except Exception as exc:
            failed_at = clock()
            reason_code = f"{phase}_FAILED_{type(exc).__name__.upper()}"
            root_cause_code = _root_cause_code(exc)
            try:
                _mark_failed(
                    store=store,
                    qualification_id=qualification_id,
                    checkpoint=checkpoint,
                    plan=plan,
                    reservation=reservation,
                    failed_at=failed_at,
                    phase=phase,
                    reason_code=reason_code,
                    root_cause_code=root_cause_code,
                )
            except Exception as failure_exc:
                raise V31SourceQualificationWorkflowError(
                    "V31_SOURCE_QUALIFICATION_FAILURE_PERSISTENCE_FAILED"
                ) from failure_exc
            raise V31SourceQualificationWorkflowError(reason_code) from exc


def source_qualification_status(
    *, store: V31SourceQualificationStorePort, qualification_id: str
) -> Mapping[str, Any]:
    checkpoint = store.load_checkpoint(qualification_id=qualification_id)
    verify_v31_source_qualification_checkpoint(checkpoint)
    return {
        "schema_id": "theory_paper_v31_source_qualification_status",
        "qualification_id": qualification_id,
        "status": checkpoint["status"],
        "revision": checkpoint["revision"],
        "attempt_count": checkpoint["attempt_count"],
        "attempt_limit": 1,
        "collector_retry_allowed": False,
        "completion_digest": (
            None
            if checkpoint["completion_binding"] is None
            else checkpoint["completion_binding"]["semantic_digest"]
        ),
        "failure_digest": (
            None
            if checkpoint["failure_binding"] is None
            else checkpoint["failure_binding"]["semantic_digest"]
        ),
        "checkpoint_digest": checkpoint[
            "source_qualification_checkpoint_digest"
        ],
        "qualification_only": True,
        "research_run_created": False,
        "experiment_started": False,
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_access": False,
        "funds_access": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def verify_durable_v31_source_qualification_completion(
    *, store: V31SourceQualificationStorePort, qualification_id: str
) -> Mapping[str, Any]:
    """Replay one already-sealed Q6 qualification without network access.

    This is the public, read-only boundary used by governance qualification.
    It deliberately reuses the same full durable replay as restart recovery:
    the plan, reservation, checkpoint, completion, snapshot, raw bytes, PIT
    dataset, and information-event records must all still agree physically and
    semantically.  A digest copied out of a status document is not sufficient.
    """

    checkpoint = store.load_checkpoint(qualification_id=qualification_id)
    verify_v31_source_qualification_checkpoint(checkpoint)
    if (
        checkpoint.get("status") != "SEALED"
        or checkpoint.get("attempt_count") != 1
        or checkpoint.get("completion_binding") is None
        or checkpoint.get("failure_binding") is not None
    ):
        raise V31SourceQualificationWorkflowError(
            "V31_SOURCE_QUALIFICATION_NOT_DURABLY_SEALED"
        )
    plan, reservation = _load_plan_and_reservation(
        store=store, checkpoint=checkpoint
    )
    completion, completion_binding = _verify_durable_completion(
        store=store,
        checkpoint=checkpoint,
        plan=plan,
        reservation=reservation,
    )
    if checkpoint["completion_binding"] != completion_binding:
        raise V31SourceQualificationWorkflowError(
            "V31_SOURCE_QUALIFICATION_CHECKPOINT_COMPLETION_DRIFT"
        )
    return {
        "qualification_id": qualification_id,
        "plan": dict(plan),
        "reservation": dict(reservation),
        "checkpoint": dict(checkpoint),
        "completion": dict(completion),
        "completion_binding": dict(completion_binding),
    }


__all__ = [
    "COMPLETION_REF",
    "DATASET_REF",
    "FAILURE_REF",
    "PLAN_REF",
    "RESERVATION_REF",
    "SNAPSHOT_REF",
    "SourceAdapter",
    "SourceQualificationAdaptationPort",
    "SourceQualificationCollectionPort",
    "V31SourceQualificationCollectorPort",
    "V31SourceQualificationStorePort",
    "V31SourceQualificationWorkflowError",
    "execute_v31_source_qualification",
    "initialize_v31_source_qualification",
    "source_qualification_status",
    "verify_durable_v31_source_qualification_completion",
]
