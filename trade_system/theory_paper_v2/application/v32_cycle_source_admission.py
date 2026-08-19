"""Full typed V3.2 source admission, exact-byte copy, and durable replay."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import verify_self_digest
from ..domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    CAPTURE_DIGEST_FIELD,
    CAPTURE_SCHEMA_ID,
    FULL_LOADER_DIGEST_FIELD,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    QUALIFICATION_DIGEST_FIELD,
    QUALIFICATION_SCHEMA_ID,
    SNAPSHOT_DIGEST_FIELD,
    SNAPSHOT_SCHEMA_ID,
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    SOURCE_ADMISSION_SCHEMA_VERSION,
    V32CycleSourceAdmissionError,
    build_v32_cycle_source_full_loader_receipt,
    cycle_source_admission_ref,
    cycle_source_full_loader_ref,
    qualification_ref,
    seal_v32_cycle_source_admission,
    verify_v32_active_authority_projection,
    verify_v32_cycle_source_admission,
    verify_v32_cycle_source_full_loader_receipt,
    verify_v32_formal_source_qualification,
    verify_v32_pit_evidence_registry,
    verify_v32_public_market_snapshot,
    verify_v32_public_source_capture,
)
from .v32_cycle_source_store_port import (
    V32CycleSourcePersistenceError,
    V32CycleSourceStorePort,
)


class V32CycleSourceAdmissionWorkflowError(ValueError):
    """The application failed closed before granting an analysis source head."""


_ROLE_SPECS = {
    "SOURCE_QUALIFICATION": (QUALIFICATION_SCHEMA_ID, QUALIFICATION_DIGEST_FIELD),
    "SOURCE_CAPTURE": (CAPTURE_SCHEMA_ID, CAPTURE_DIGEST_FIELD),
    "MARKET_SNAPSHOT": (SNAPSHOT_SCHEMA_ID, SNAPSHOT_DIGEST_FIELD),
    "PIT_REGISTRY": (PIT_REGISTRY_SCHEMA_ID, PIT_REGISTRY_DIGEST_FIELD),
}


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32CycleSourceAdmissionWorkflowError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32CycleSourceAdmissionWorkflowError(code) from exc
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        raise V32CycleSourceAdmissionWorkflowError(code)
    return parsed.astimezone(UTC)


def _typed_binding(
    store: V32CycleSourceStorePort,
    *,
    relative_ref: str,
    digest_field: str,
    expected_semantic_digest: str,
) -> dict[str, str]:
    return store.artifact_binding(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=expected_semantic_digest,
    )


def _read_typed(
    store: V32CycleSourceStorePort,
    *,
    binding: Mapping[str, Any],
    verifier: Any,
) -> tuple[dict[str, Any], bytes]:
    try:
        document = store.read_document(
            relative_ref=str(binding["relative_ref"]),
            digest_field=str(binding["digest_field"]),
            expected_semantic_digest=str(binding["semantic_digest"]),
            expected_physical_sha256=str(binding["physical_sha256"]),
        )
        semantic = verifier(document)
        raw = store.read_raw(
            relative_ref=str(binding["relative_ref"]),
            expected_sha256=str(binding["physical_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_TYPED_DOCUMENT_REPLAY_FAILED"
        ) from exc
    if (
        document.get("schema_id") != binding.get("schema_id")
        or semantic != binding.get("semantic_digest")
        or hashlib.sha256(raw).hexdigest() != binding.get("physical_sha256")
    ):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_TYPED_DOCUMENT_BINDING_MISMATCH"
        )
    return document, raw


def _load_qualified_bundle(
    *,
    source_store: V32CycleSourceStorePort,
    qualification_id: str,
) -> dict[str, Any]:
    q_ref = qualification_ref(qualification_id)
    try:
        qualification = source_store.read_document(
            relative_ref=q_ref,
            digest_field=QUALIFICATION_DIGEST_FIELD,
        )
        q_digest = verify_v32_formal_source_qualification(qualification)
        q_binding = _typed_binding(
            source_store,
            relative_ref=q_ref,
            digest_field=QUALIFICATION_DIGEST_FIELD,
            expected_semantic_digest=q_digest,
        )
        q_raw = source_store.read_raw(
            relative_ref=q_ref, expected_sha256=q_binding["physical_sha256"]
        )
        capture, capture_raw = _read_typed(
            source_store,
            binding=qualification["capture_binding"],
            verifier=verify_v32_public_source_capture,
        )
        snapshot, snapshot_raw = _read_typed(
            source_store,
            binding=qualification["snapshot_binding"],
            verifier=verify_v32_public_market_snapshot,
        )
        pit, pit_raw = _read_typed(
            source_store,
            binding=qualification["pit_registry_binding"],
            verifier=verify_v32_pit_evidence_registry,
        )
        raw_binding = capture["raw_response_binding"]
        raw_payload = source_store.read_raw(
            relative_ref=raw_binding["relative_ref"],
            expected_sha256=raw_binding["physical_sha256"],
        )
    except (
        V32CycleSourcePersistenceError,
        V32CycleSourceAdmissionError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_QUALIFIED_BUNDLE_INVALID"
        ) from exc
    if (
        hashlib.sha256(q_raw).hexdigest() != q_binding["physical_sha256"]
        or hashlib.sha256(raw_payload).hexdigest() != raw_binding["semantic_digest"]
        or capture[CAPTURE_DIGEST_FIELD]
        != qualification["capture_binding"]["semantic_digest"]
        or snapshot[SNAPSHOT_DIGEST_FIELD]
        != qualification["snapshot_binding"]["semantic_digest"]
        or pit[PIT_REGISTRY_DIGEST_FIELD]
        != qualification["pit_registry_binding"]["semantic_digest"]
    ):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_QUALIFIED_BUNDLE_BINDING_MISMATCH"
        )
    return {
        "qualification": qualification,
        "qualification_binding": q_binding,
        "capture": capture,
        "snapshot": snapshot,
        "pit": pit,
        "raw_binding": dict(raw_binding),
        "payloads": {
            "SOURCE_QUALIFICATION": q_raw,
            "SOURCE_CAPTURE": capture_raw,
            "MARKET_SNAPSHOT": snapshot_raw,
            "PIT_REGISTRY": pit_raw,
            "RAW_RESPONSE": raw_payload,
        },
        "source_bindings": {
            "SOURCE_QUALIFICATION": q_binding,
            "SOURCE_CAPTURE": dict(qualification["capture_binding"]),
            "MARKET_SNAPSHOT": dict(qualification["snapshot_binding"]),
            "PIT_REGISTRY": dict(qualification["pit_registry_binding"]),
        },
    }


def _validate_bundle_for_cycle(
    *,
    bundle: Mapping[str, Any],
    authority: Mapping[str, Any],
    run_id: str,
    cycle_index: int,
    schema_version: str,
    source_cutoff_at: str | None,
    decision_time: str,
    admitted_at: str,
    experiment_contract_digest: str,
) -> None:
    qualification = bundle["qualification"]
    capture = bundle["capture"]
    snapshot = bundle["snapshot"]
    pit = bundle["pit"]
    authority_projection_digest = authority[
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
    ]
    governing_authority_digest = authority[GOVERNING_AUTHORITY_DIGEST_FIELD]
    authority_time = _time(authority["recorded_at"], "V32_SOURCE_AUTHORITY_TIME_INVALID")
    started = _time(qualification["started_at"], "V32_SOURCE_QUALIFICATION_TIME_INVALID")
    capture_started = _time(capture["request_started_at"], "V32_SOURCE_CAPTURE_TIME_INVALID")
    received = _time(capture["response_received_at"], "V32_SOURCE_CAPTURE_TIME_INVALID")
    completed = _time(qualification["completed_at"], "V32_SOURCE_QUALIFICATION_TIME_INVALID")
    admitted = _time(admitted_at, "V32_SOURCE_ADMISSION_TIME_INVALID")
    decision = _time(decision_time, "V32_SOURCE_ADMISSION_TIME_INVALID")
    if schema_version == LEGACY_SOURCE_ADMISSION_SCHEMA_VERSION:
        if source_cutoff_at is not None:
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_CYCLE_SCHEMA_VERSION_INVALID"
            )
        qualification_cutoff = decision_time
        freshness_clock = decision
        chronology_valid = (
            authority_time
            < started
            <= capture_started
            <= received
            <= completed
            <= admitted
            <= decision
        )
    elif schema_version == SOURCE_ADMISSION_SCHEMA_VERSION:
        cutoff = _time(
            source_cutoff_at, "V32_SOURCE_CUTOFF_TIME_INVALID"
        )
        if decision_time != source_cutoff_at:
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_CUTOFF_ALIAS_INVALID"
            )
        qualification_cutoff = str(source_cutoff_at)
        freshness_clock = cutoff
        chronology_valid = (
            authority_time
            < started
            <= capture_started
            <= received
            <= completed
            <= cutoff
            <= admitted
        )
    else:
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_CYCLE_SCHEMA_VERSION_INVALID"
        )
    snapshot_as_of = _time(snapshot["as_of"], "V32_SOURCE_PIT_TIME_INVALID")
    available = _time(snapshot["available_at"], "V32_SOURCE_PIT_TIME_INVALID")
    closed = _time(snapshot["closed_bar_as_of"], "V32_SOURCE_CLOSED_BAR_INVALID")
    pit_as_of = _time(pit["as_of"], "V32_SOURCE_PIT_TIME_INVALID")
    if (
        qualification.get("run_id") != run_id
        or capture.get("run_id") != run_id
        or snapshot.get("run_id") != run_id
        or pit.get("run_id") != run_id
        or qualification.get("cycle_index") != cycle_index
        or capture.get("cycle_index") != cycle_index
        or snapshot.get("cycle_index") != cycle_index
        or pit.get("cycle_index") != cycle_index
        or qualification.get("decision_time") != qualification_cutoff
        or qualification.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != authority_projection_digest
        or qualification.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != governing_authority_digest
        or qualification.get("active_authority_recorded_at") != authority.get("recorded_at")
        or qualification.get("experiment_contract_digest") != experiment_contract_digest
        or capture.get("qualification_id") != qualification.get("qualification_id")
        or snapshot.get("qualification_id") != qualification.get("qualification_id")
        or snapshot.get("capture_attempt_digest") != capture.get(CAPTURE_DIGEST_FIELD)
        or pit.get("upstream_semantic_digest") != snapshot.get(SNAPSHOT_DIGEST_FIELD)
        or pit.get("full_verification_receipt_digest") != capture.get(CAPTURE_DIGEST_FIELD)
        or snapshot.get("open_interest_datum_digest") not in pit.get("members", ())
    ):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_CYCLE_IDENTITY_OR_BINDING_MISMATCH"
        )
    if not (
        chronology_valid
        and snapshot_as_of <= available <= completed
        and snapshot_as_of <= pit_as_of <= completed
        and closed <= snapshot_as_of
        and freshness_clock - received <= timedelta(seconds=900)
        and freshness_clock - closed <= timedelta(seconds=1800)
    ):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_CYCLE_CHRONOLOGY_OR_FRESHNESS_INVALID"
        )


def _copy_rows(bundle: Mapping[str, Any], *, cycle_index: int) -> list[dict[str, Any]]:
    base = f"cycles/{cycle_index:04d}/market/v32-source-admission"
    suffix = {
        "SOURCE_QUALIFICATION": "qualified/qualification.json",
        "SOURCE_CAPTURE": "qualified/source-capture.json",
        "MARKET_SNAPSHOT": "qualified/market-snapshot.json",
        "PIT_REGISTRY": "qualified/pit-evidence-registry.json",
        "RAW_RESPONSE": "raw/public-market-bundle.body",
    }
    rows: list[dict[str, Any]] = []
    for role in _ROLE_SPECS:
        schema_id, digest_field = _ROLE_SPECS[role]
        source = bundle["source_bindings"][role]
        rows.append(
            {
                "artifact_role": role,
                "artifact_id": role.lower(),
                "source_relative_ref": source["relative_ref"],
                "target_relative_ref": f"{base}/{suffix[role]}",
                "schema_id": schema_id,
                "digest_field": digest_field,
                "semantic_digest": source["semantic_digest"],
                "source_physical_sha256": source["physical_sha256"],
                "target_physical_sha256": source["physical_sha256"],
                "exact_bytes_copied": True,
                "readback_verified": True,
            }
        )
    raw = bundle["raw_binding"]
    rows.append(
        {
            "artifact_role": "RAW_RESPONSE",
            "artifact_id": "public-market-bundle",
            "source_relative_ref": raw["relative_ref"],
            "target_relative_ref": f"{base}/{suffix['RAW_RESPONSE']}",
            "schema_id": None,
            "digest_field": None,
            "semantic_digest": raw["semantic_digest"],
            "source_physical_sha256": raw["physical_sha256"],
            "target_physical_sha256": raw["physical_sha256"],
            "exact_bytes_copied": True,
            "readback_verified": True,
        }
    )
    return sorted(rows, key=lambda row: (row["artifact_role"], row["artifact_id"]))


def _replay_copy_rows(
    *, run_store: V32CycleSourceStorePort, receipt: Mapping[str, Any]
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    target_bindings: dict[str, dict[str, str]] = {}
    typed_documents: dict[str, dict[str, Any]] = {}
    raw_copy_row: dict[str, Any] | None = None
    for row in receipt["artifact_copies"]:
        raw = run_store.read_raw(
            relative_ref=row["target_relative_ref"],
            expected_sha256=row["target_physical_sha256"],
        )
        if hashlib.sha256(raw).hexdigest() != row["source_physical_sha256"]:
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_TARGET_COPY_PHYSICAL_MISMATCH"
            )
        role = row["artifact_role"]
        if role == "RAW_RESPONSE":
            if hashlib.sha256(raw).hexdigest() != row["semantic_digest"]:
                raise V32CycleSourceAdmissionWorkflowError(
                    "V32_SOURCE_TARGET_RAW_SEMANTIC_MISMATCH"
                )
            raw_copy_row = dict(row)
            continue
        verifier = {
            "SOURCE_QUALIFICATION": verify_v32_formal_source_qualification,
            "SOURCE_CAPTURE": verify_v32_public_source_capture,
            "MARKET_SNAPSHOT": verify_v32_public_market_snapshot,
            "PIT_REGISTRY": verify_v32_pit_evidence_registry,
        }[role]
        document = run_store.read_document(
            relative_ref=row["target_relative_ref"],
            digest_field=row["digest_field"],
            expected_semantic_digest=row["semantic_digest"],
            expected_physical_sha256=row["target_physical_sha256"],
        )
        if verifier(document) != row["semantic_digest"]:
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_TARGET_TYPED_REPLAY_MISMATCH"
            )
        target_bindings[role] = _typed_binding(
            run_store,
            relative_ref=row["target_relative_ref"],
            digest_field=row["digest_field"],
            expected_semantic_digest=row["semantic_digest"],
        )
        typed_documents[role] = document
    if raw_copy_row is None or set(target_bindings) != set(_ROLE_SPECS):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_TARGET_COPY_SET_INCOMPLETE"
        )
    return target_bindings, typed_documents, raw_copy_row


def _validate_durable_bundle_links(
    *,
    full: Mapping[str, Any],
    admission: Mapping[str, Any],
    typed_documents: Mapping[str, Mapping[str, Any]],
    target_bindings: Mapping[str, Mapping[str, Any]],
    raw_copy_row: Mapping[str, Any],
    expected_authority_projection_digest: str,
    expected_governing_authority_digest: str,
    expected_experiment_contract_digest: str,
) -> None:
    """Rebuild cross-document truth instead of trusting receipt booleans."""

    qualification = typed_documents["SOURCE_QUALIFICATION"]
    capture = typed_documents["SOURCE_CAPTURE"]
    snapshot = typed_documents["MARKET_SNAPSHOT"]
    pit = typed_documents["PIT_REGISTRY"]

    for qualification_key, role in (
        ("capture_binding", "SOURCE_CAPTURE"),
        ("snapshot_binding", "MARKET_SNAPSHOT"),
        ("pit_registry_binding", "PIT_REGISTRY"),
    ):
        source_binding = qualification[qualification_key]
        target_binding = target_bindings[role]
        copy_row = next(
            row for row in full["artifact_copies"] if row["artifact_role"] == role
        )
        if (
            source_binding["relative_ref"] != copy_row["source_relative_ref"]
            or source_binding["schema_id"] != target_binding["schema_id"]
            or source_binding["digest_field"] != target_binding["digest_field"]
            or source_binding["semantic_digest"]
            != target_binding["semantic_digest"]
            or source_binding["physical_sha256"]
            != target_binding["physical_sha256"]
        ):
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_DURABLE_QUALIFICATION_BINDING_MISMATCH"
            )

    raw_binding = capture["raw_response_binding"]
    if (
        raw_binding["relative_ref"] != raw_copy_row["source_relative_ref"]
        or raw_binding["semantic_digest"] != raw_copy_row["semantic_digest"]
        or raw_binding["physical_sha256"]
        != raw_copy_row["source_physical_sha256"]
    ):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_DURABLE_RAW_BINDING_MISMATCH"
        )

    bundle = {
        "qualification": qualification,
        "capture": capture,
        "snapshot": snapshot,
        "pit": pit,
    }
    authority_projection = {
        ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD: (
            expected_authority_projection_digest
        ),
        GOVERNING_AUTHORITY_DIGEST_FIELD: (
            expected_governing_authority_digest
        ),
        "recorded_at": full["active_authority_recorded_at"],
    }
    _validate_bundle_for_cycle(
        bundle=bundle,
        authority=authority_projection,
        run_id=str(full["run_id"]),
        cycle_index=int(full["cycle_index"]),
        schema_version=str(full["schema_version"]),
        source_cutoff_at=(
            str(full["source_cutoff_at"])
            if full["schema_version"] == SOURCE_ADMISSION_SCHEMA_VERSION
            else None
        ),
        decision_time=str(full["decision_time"]),
        admitted_at=str(full["admitted_at"]),
        experiment_contract_digest=expected_experiment_contract_digest,
    )
    if (
        full["qualification_binding"] != target_bindings["SOURCE_QUALIFICATION"]
        or full["capture_binding"] != target_bindings["SOURCE_CAPTURE"]
        or full["current_snapshot_binding"] != target_bindings["MARKET_SNAPSHOT"]
        or full["pit_registry_binding"] != target_bindings["PIT_REGISTRY"]
        or full["qualification_started_at"] != qualification["started_at"]
        or full["qualification_completed_at"] != qualification["completed_at"]
        or full["earliest_capture_started_at"] != capture["request_started_at"]
        or full["latest_capture_received_at"] != capture["response_received_at"]
        or full["closed_bar_as_of"] != snapshot["closed_bar_as_of"]
        or full["current_open_interest_datum_digest"]
        != snapshot["open_interest_datum_digest"]
        or full["current_open_interest_status"] != snapshot["open_interest_status"]
        or admission["previous_source_context"] != full["previous_source_context"]
    ):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_DURABLE_FULL_BODY_MISMATCH"
        )


def verify_durable_v32_cycle_source_admission(
    *,
    run_store: V32CycleSourceStorePort,
    run_id: str,
    cycle_index: int,
    expected_authority_projection_digest: str,
    expected_governing_authority_digest: str,
    expected_experiment_contract_digest: str,
) -> dict[str, Any]:
    """Replay the admission body, full-loader receipt, typed copies, and CAS chain."""

    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or not 1 <= cycle_index <= 16:
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_CYCLE_OUTSIDE_FROZEN_CONTRACT"
        )
    try:
        admission_ref = cycle_source_admission_ref(cycle_index)
        admission = run_store.read_document(
            relative_ref=admission_ref,
            digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
        )
        admission_digest = verify_v32_cycle_source_admission(admission)
        full_ref = cycle_source_full_loader_ref(cycle_index)
        full = run_store.read_document(
            relative_ref=full_ref,
            digest_field=FULL_LOADER_DIGEST_FIELD,
            expected_semantic_digest=admission["full_loader_receipt_binding"][
                "semantic_digest"
            ],
            expected_physical_sha256=admission["full_loader_receipt_binding"][
                "physical_sha256"
            ],
        )
        full_digest = verify_v32_cycle_source_full_loader_receipt(full)
        target_bindings, typed_documents, raw_copy_row = _replay_copy_rows(
            run_store=run_store, receipt=full
        )
        full_binding = _typed_binding(
            run_store,
            relative_ref=full_ref,
            digest_field=FULL_LOADER_DIGEST_FIELD,
            expected_semantic_digest=full_digest,
        )
        _validate_durable_bundle_links(
            full=full,
            admission=admission,
            typed_documents=typed_documents,
            target_bindings=target_bindings,
            raw_copy_row=raw_copy_row,
            expected_authority_projection_digest=(
                expected_authority_projection_digest
            ),
            expected_governing_authority_digest=(
                expected_governing_authority_digest
            ),
            expected_experiment_contract_digest=expected_experiment_contract_digest,
        )
    except (
        V32CycleSourcePersistenceError,
        V32CycleSourceAdmissionError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_DURABLE_REPLAY_FAILED"
        ) from exc
    if (
        admission.get("run_id") != run_id
        or full.get("run_id") != run_id
        or admission.get("cycle_index") != cycle_index
        or full.get("cycle_index") != cycle_index
        or admission.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != expected_authority_projection_digest
        or admission.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != expected_governing_authority_digest
        or admission.get("experiment_contract_digest")
        != expected_experiment_contract_digest
        or full.get(ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD)
        != expected_authority_projection_digest
        or full.get(GOVERNING_AUTHORITY_DIGEST_FIELD)
        != expected_governing_authority_digest
        or full.get("experiment_contract_digest") != expected_experiment_contract_digest
        or admission.get("qualification_binding")
        != target_bindings.get("SOURCE_QUALIFICATION")
        or admission.get("capture_binding")
        != target_bindings.get("SOURCE_CAPTURE")
        or admission.get("current_snapshot_binding") != target_bindings.get("MARKET_SNAPSHOT")
        or admission.get("pit_registry_binding") != target_bindings.get("PIT_REGISTRY")
        or admission.get("schema_version") != full.get("schema_version")
        or admission.get("decision_time") != full.get("decision_time")
        or admission.get("admitted_at") != full.get("admitted_at")
        or (
            admission.get("schema_version") == SOURCE_ADMISSION_SCHEMA_VERSION
            and admission.get("source_cutoff_at") != full.get("source_cutoff_at")
        )
        or admission.get("full_loader_receipt_binding") != full_binding
        or admission.get("current_open_interest_datum_digest")
        != full.get("current_open_interest_datum_digest")
        or admission.get("current_open_interest_status")
        != full.get("current_open_interest_status")
        or admission.get("current_open_interest_zero_imputed") is not False
    ):
        raise V32CycleSourceAdmissionWorkflowError(
            "V32_SOURCE_DURABLE_IDENTITY_MISMATCH"
        )
    previous: dict[str, Any] | None = None
    if cycle_index > 1:
        previous = verify_durable_v32_cycle_source_admission(
            run_store=run_store,
            run_id=run_id,
            cycle_index=cycle_index - 1,
            expected_authority_projection_digest=(
                expected_authority_projection_digest
            ),
            expected_governing_authority_digest=(
                expected_governing_authority_digest
            ),
            expected_experiment_contract_digest=expected_experiment_contract_digest,
        )
        context = admission["previous_source_context"]
        expected_context = {
            "status": "BOUND_TO_PREVIOUS_ACCEPTED_V32_CYCLE",
            "previous_cycle_source_admission_binding": previous["cycle_source_admission_binding"],
            "prior_snapshot_binding": previous["current_snapshot_binding"],
            "prior_open_interest_datum_digest": previous["current_open_interest_datum_digest"],
            "prior_open_interest_status": previous["current_open_interest_status"],
            "prior_open_interest_zero_imputed": False,
        }
        if (
            context != expected_context
            or full["previous_source_context"] != expected_context
            or full["cas_predecessor_admission_digest"]
            != previous["cycle_source_admission"][SOURCE_ADMISSION_DIGEST_FIELD]
        ):
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_DURABLE_PREVIOUS_CHAIN_MISMATCH"
            )
    admission_binding = _typed_binding(
        run_store,
        relative_ref=admission_ref,
        digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
        expected_semantic_digest=admission_digest,
    )
    return {
        "cycle_source_admission": admission,
        "cycle_source_admission_binding": admission_binding,
        "full_loader_receipt": full,
        "full_loader_receipt_binding": full_binding,
        "current_snapshot_binding": target_bindings["MARKET_SNAPSHOT"],
        "pit_registry_binding": target_bindings["PIT_REGISTRY"],
        "current_open_interest_datum_digest": full[
            "current_open_interest_datum_digest"
        ],
        "current_open_interest_status": full["current_open_interest_status"],
        "current_open_interest_zero_imputed": False,
        "previous_cycle": previous,
    }


def admit_fresh_v32_source_to_cycle(
    *,
    source_store: V32CycleSourceStorePort,
    run_store: V32CycleSourceStorePort,
    active_authority: Mapping[str, Any],
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    decision_time: str,
    admitted_at: str,
    previous_cycle_source_admission_binding: Mapping[str, Any] | None = None,
    prior_snapshot_binding: Mapping[str, Any] | None = None,
    prior_open_interest_datum_digest: str | None = None,
    prior_open_interest_status: str | None = None,
    prior_open_interest_zero_imputed: bool = False,
) -> dict[str, Any]:
    """Copy and admit exactly one fresh typed public-source transaction."""

    try:
        if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or not 1 <= cycle_index <= 16:
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_CYCLE_OUTSIDE_FROZEN_CONTRACT"
            )
        authority_projection_digest = verify_v32_active_authority_projection(
            active_authority
        )
        governing_authority_digest = str(
            active_authority[GOVERNING_AUTHORITY_DIGEST_FIELD]
        )
        contract_digest = str(active_authority["experiment_contract_digest"])
        if active_authority.get("authorized_run_id") != run_id:
            raise V32CycleSourceAdmissionWorkflowError(
                "V32_SOURCE_AUTHORITY_RUN_MISMATCH"
            )
        bundle = _load_qualified_bundle(
            source_store=source_store, qualification_id=qualification_id
        )
        source_cutoff_at = str(bundle["qualification"]["decision_time"])
        _validate_bundle_for_cycle(
            bundle=bundle,
            authority=active_authority,
            run_id=run_id,
            cycle_index=cycle_index,
            schema_version=SOURCE_ADMISSION_SCHEMA_VERSION,
            source_cutoff_at=source_cutoff_at,
            decision_time=decision_time,
            admitted_at=admitted_at,
            experiment_contract_digest=contract_digest,
        )
        if cycle_index == 1:
            if any(
                value is not None
                for value in (
                    previous_cycle_source_admission_binding,
                    prior_snapshot_binding,
                    prior_open_interest_datum_digest,
                    prior_open_interest_status,
                )
            ) or prior_open_interest_zero_imputed is not False:
                raise V32CycleSourceAdmissionWorkflowError(
                    "V32_SOURCE_GENESIS_PRIOR_CONTEXT_FORBIDDEN"
                )
            previous_context = {
                "status": "GENESIS_NO_PRIOR_SOURCE_CONTEXT",
                "previous_cycle_source_admission_binding": None,
                "prior_snapshot_binding": None,
                "prior_open_interest_datum_digest": None,
                "prior_open_interest_status": "NOT_APPLICABLE_GENESIS",
                "prior_open_interest_zero_imputed": False,
            }
        else:
            previous = verify_durable_v32_cycle_source_admission(
                run_store=run_store,
                run_id=run_id,
                cycle_index=cycle_index - 1,
                expected_authority_projection_digest=(
                    authority_projection_digest
                ),
                expected_governing_authority_digest=(
                    governing_authority_digest
                ),
                expected_experiment_contract_digest=contract_digest,
            )
            if _time(
                bundle["qualification"]["started_at"],
                "V32_SOURCE_QUALIFICATION_TIME_INVALID",
            ) <= _time(
                previous["cycle_source_admission"]["decision_time"],
                "V32_SOURCE_PREVIOUS_DECISION_TIME_INVALID",
            ):
                raise V32CycleSourceAdmissionWorkflowError(
                    "V32_SOURCE_QUALIFICATION_NOT_AFTER_PREVIOUS_CYCLE"
                )
            expected_triplet = (
                previous["cycle_source_admission_binding"],
                previous["current_snapshot_binding"],
                previous["current_open_interest_datum_digest"],
                previous["current_open_interest_status"],
                False,
            )
            caller_triplet = (
                previous_cycle_source_admission_binding,
                prior_snapshot_binding,
                prior_open_interest_datum_digest,
                prior_open_interest_status,
                prior_open_interest_zero_imputed,
            )
            if caller_triplet != expected_triplet:
                raise V32CycleSourceAdmissionWorkflowError(
                    "V32_SOURCE_CALLER_PREVIOUS_TRIPLET_MISMATCH"
                )
            previous_context = {
                "status": "BOUND_TO_PREVIOUS_ACCEPTED_V32_CYCLE",
                "previous_cycle_source_admission_binding": expected_triplet[0],
                "prior_snapshot_binding": expected_triplet[1],
                "prior_open_interest_datum_digest": expected_triplet[2],
                "prior_open_interest_status": expected_triplet[3],
                "prior_open_interest_zero_imputed": False,
            }
            for prior_cycle in range(1, cycle_index):
                prior = verify_durable_v32_cycle_source_admission(
                    run_store=run_store,
                    run_id=run_id,
                    cycle_index=prior_cycle,
                    expected_authority_projection_digest=(
                        authority_projection_digest
                    ),
                    expected_governing_authority_digest=(
                        governing_authority_digest
                    ),
                    expected_experiment_contract_digest=contract_digest,
                )
                prior_full = prior["full_loader_receipt"]
                if (
                    prior_full["qualification_binding"]["semantic_digest"]
                    == bundle["qualification_binding"]["semantic_digest"]
                    or prior_full["current_snapshot_binding"]["semantic_digest"]
                    == bundle["snapshot"][SNAPSHOT_DIGEST_FIELD]
                ):
                    raise V32CycleSourceAdmissionWorkflowError(
                        "V32_SOURCE_QUALIFICATION_REUSE_FORBIDDEN"
                    )
        copy_rows = _copy_rows(bundle, cycle_index=cycle_index)
        for row in copy_rows:
            payload = bundle["payloads"][row["artifact_role"]]
            result = run_store.write_raw(
                relative_ref=row["target_relative_ref"], payload=payload
            )
            readback = run_store.read_raw(
                relative_ref=row["target_relative_ref"],
                expected_sha256=row["target_physical_sha256"],
            )
            if result["physical_sha256"] != row["target_physical_sha256"] or readback != payload:
                raise V32CycleSourceAdmissionWorkflowError(
                    "V32_SOURCE_EXACT_COPY_READBACK_FAILED"
                )
        provisional = {
            "artifact_copies": copy_rows,
        }
        target_bindings, _, _ = _replay_copy_rows(
            run_store=run_store, receipt=provisional
        )
        qualification = bundle["qualification"]
        capture = bundle["capture"]
        snapshot = bundle["snapshot"]
        full = build_v32_cycle_source_full_loader_receipt(
            run_id=run_id,
            cycle_index=cycle_index,
            admitted_at=admitted_at,
            decision_time=decision_time,
            source_cutoff_at=source_cutoff_at,
            active_authority_projection_digest=authority_projection_digest,
            governing_authority_digest=governing_authority_digest,
            active_authority_recorded_at=str(active_authority["recorded_at"]),
            experiment_contract_digest=contract_digest,
            qualification_binding=target_bindings["SOURCE_QUALIFICATION"],
            capture_binding=target_bindings["SOURCE_CAPTURE"],
            current_snapshot_binding=target_bindings["MARKET_SNAPSHOT"],
            pit_registry_binding=target_bindings["PIT_REGISTRY"],
            qualification_started_at=qualification["started_at"],
            qualification_completed_at=qualification["completed_at"],
            earliest_capture_started_at=capture["request_started_at"],
            latest_capture_received_at=capture["response_received_at"],
            closed_bar_as_of=snapshot["closed_bar_as_of"],
            current_open_interest_datum_digest=snapshot[
                "open_interest_datum_digest"
            ],
            current_open_interest_status=snapshot["open_interest_status"],
            previous_source_context=previous_context,
            artifact_copies=copy_rows,
        )
        full_binding = run_store.write_document(
            relative_ref=cycle_source_full_loader_ref(cycle_index),
            document=full,
            digest_field=FULL_LOADER_DIGEST_FIELD,
        )
        durable_full = run_store.read_document(
            relative_ref=cycle_source_full_loader_ref(cycle_index),
            digest_field=FULL_LOADER_DIGEST_FIELD,
            expected_semantic_digest=full[FULL_LOADER_DIGEST_FIELD],
        )
        verify_v32_cycle_source_full_loader_receipt(durable_full)
        admission = seal_v32_cycle_source_admission(
            run_id=run_id,
            cycle_index=cycle_index,
            decision_time=decision_time,
            source_cutoff_at=source_cutoff_at,
            admitted_at=admitted_at,
            current_snapshot_binding=target_bindings["MARKET_SNAPSHOT"],
            pit_registry_binding=target_bindings["PIT_REGISTRY"],
            previous_source_context=previous_context,
            full_loader_receipt_binding=full_binding,
            active_authority_projection_digest=authority_projection_digest,
            governing_authority_digest=governing_authority_digest,
            experiment_contract_digest=contract_digest,
            qualification_binding=target_bindings["SOURCE_QUALIFICATION"],
            capture_binding=target_bindings["SOURCE_CAPTURE"],
            current_open_interest_datum_digest=snapshot[
                "open_interest_datum_digest"
            ],
            current_open_interest_status=snapshot["open_interest_status"],
        )
        run_store.write_document(
            relative_ref=cycle_source_admission_ref(cycle_index),
            document=admission,
            digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
        )
        replay = verify_durable_v32_cycle_source_admission(
            run_store=run_store,
            run_id=run_id,
            cycle_index=cycle_index,
            expected_authority_projection_digest=authority_projection_digest,
            expected_governing_authority_digest=governing_authority_digest,
            expected_experiment_contract_digest=contract_digest,
        )
        return {
            "status": "V32_CYCLE_SOURCE_ADMITTED_NOT_STARTED",
            **replay,
            "source_collection_transactions": 1,
            "proposal_attempts": 0,
            "selection_attempts": 0,
            "cycle_started": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
    except V32CycleSourceAdmissionWorkflowError:
        raise
    except (
        V32CycleSourceAdmissionError,
        V32CycleSourcePersistenceError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V32CycleSourceAdmissionWorkflowError(
            f"V32_CYCLE_SOURCE_ADMISSION_FAILED:{exc}"
        ) from exc


__all__ = [
    "V32CycleSourceAdmissionWorkflowError",
    "admit_fresh_v32_source_to_cycle",
    "verify_durable_v32_cycle_source_admission",
]
