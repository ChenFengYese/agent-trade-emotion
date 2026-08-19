"""Admit one sealed public-source qualification into an authorized V3.1 cycle.

The use case first replays the isolated qualification store and the active
authority/genesis chain.  It then copies the exact source bytes into the run
store, reads every copy back, and writes the admission receipt last.  It never
opens or advances the research checkpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any, Mapping

from ..domain.contracts.canonical import verify_self_digest
from ..domain.agent_research_contract import (
    AgentResearchContractError,
    verify_v31_inputs_receipt,
)
from ..domain.governance.v31_authorization import (
    V31AuthorizationError,
    validate_v31_active_authority,
)
from ..domain.v31_cycle_source_admission import (
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    V31CycleSourceAdmissionError,
    admitted_authoring_source_bindings,
    cycle_source_admission_ref,
    seal_v31_cycle_source_admission,
    verify_v31_cycle_source_admission,
)
from ..domain.v31_experiment_contracts import (
    V31ExperimentContractError,
    verify_minimal_experiment_contract,
)
from ..domain.v31_source_qualification import (
    seal_v31_source_qualification_completion,
    validate_v31_source_qualification_collection,
    verify_v31_source_qualification_checkpoint,
    verify_v31_source_qualification_completion,
    verify_v31_source_qualification_information_event_record,
    verify_v31_source_qualification_plan,
    verify_v31_source_qualification_reservation,
)
from .ports import V31ResearchStorePort
from .v31_research_cycle import (
    V31ResearchCycleError,
    verify_v31_accepted_state,
    verify_v31_completion_receipt,
)
from .v31_source_qualification import (
    V31SourceQualificationStorePort,
    verify_durable_v31_source_qualification_completion,
)


class V31CycleSourceAdmissionWorkflowError(ValueError):
    """Formal source admission failed closed without moving the run cursor."""


def _typed_admission_binding(binding: Mapping[str, Any]) -> dict[str, str]:
    """Add the schema identity required by the authoring-packet contract."""

    return {
        "relative_ref": str(binding["relative_ref"]),
        "schema_id": SOURCE_ADMISSION_SCHEMA_ID,
        "digest_field": SOURCE_ADMISSION_DIGEST_FIELD,
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }


_DOCUMENT_SPECS = {
    "QUALIFICATION_PLAN": (
        "source_qualification_plan_digest",
        "theory_paper_v31_source_qualification_plan",
        "qualification/plan.json",
    ),
    "QUALIFICATION_RESERVATION": (
        "source_qualification_reservation_digest",
        "theory_paper_v31_source_qualification_reservation",
        "qualification/reservation.json",
    ),
    "QUALIFICATION_CHECKPOINT": (
        "source_qualification_checkpoint_digest",
        "theory_paper_v31_source_qualification_checkpoint",
        "qualification/checkpoint.json",
    ),
    "QUALIFICATION_COMPLETION": (
        "source_qualification_completion_digest",
        "theory_paper_v31_source_qualification_completion",
        "qualification/completion.json",
    ),
    "MARKET_SNAPSHOT": (
        "native_market_snapshot_digest",
        "native_btc_public_market_snapshot",
        "snapshot/native-market-snapshot.json",
    ),
    "PIT_DATASET": (
        "dataset_digest",
        "theory_paper_v2_v31_point_in_time_dataset",
        "adapted/pit-dataset.json",
    ),
}
_PREVIOUS_HEAD_KEYS = (
    "previous_accepted_state",
    "previous_information_revision_registry",
    "previous_pit_dataset",
    "previous_datum_revision_registry",
    "previous_sentiment_state",
    "previous_hypothesis_registry",
    "previous_expectation_ledger",
    "previous_probability_cloud",
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or not value.endswith("Z"):
        raise V31CycleSourceAdmissionWorkflowError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31CycleSourceAdmissionWorkflowError(code) from exc
    if parsed.tzinfo is None:
        raise V31CycleSourceAdmissionWorkflowError(code)
    return parsed.astimezone(UTC)


def _assert_no_legacy_authority(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "external_execution_authority" and nested != "NONE_LOCAL_SIMULATION":
                raise V31CycleSourceAdmissionWorkflowError(
                    "V31_CYCLE_SOURCE_LEGACY_OR_EXPANDED_AUTHORITY_FORBIDDEN"
                )
            _assert_no_legacy_authority(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_no_legacy_authority(nested)


def _validate_active_chain(
    *, active_chain: Mapping[str, Any], run_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], str, str]:
    try:
        approval = active_chain["theory_approval"]
        contract = active_chain["experiment_contract"]
        manifest = active_chain["manifest"]
        authorization = active_chain["authorization_receipt"]
        authority = active_chain["authority"]
        contract_digest = verify_minimal_experiment_contract(contract)
        authority_digest = validate_v31_active_authority(
            authority,
            theory_approval=approval,
            manifest=manifest,
            experiment_contract=contract,
            authorization_receipt=authorization,
        )
    except (KeyError, TypeError, V31AuthorizationError, V31ExperimentContractError) as exc:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_ACTIVE_AUTHORITY_CHAIN_INVALID"
        ) from exc
    if (
        authority.get("authorized_run_id") != run_id
        or contract.get("run_id") != run_id
        or manifest.get("run_id") != run_id
        or authority.get("data_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or authority.get("instrument")
        != {
            "venue": "OKX",
            "instrument_id": "BTC-USDT-SWAP",
            "market_type": "PERPETUAL_SWAP",
            "underlying_symbol": "BTC-USDT",
        }
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_ACTIVE_AUTHORITY_SCOPE_MISMATCH"
        )
    _assert_no_legacy_authority(active_chain)
    return authority, contract, authority_digest, contract_digest


def _validate_run_genesis(
    *,
    store: V31ResearchStorePort,
    run_id: str,
    cycle_index: int,
    active_chain: Mapping[str, Any],
    authority_digest: str,
    contract_digest: str,
) -> Mapping[str, Any]:
    checkpoint = store.load_checkpoint(run_id=run_id)
    if (
        checkpoint.get("status") != "READY_FOR_CYCLE"
        or checkpoint.get("total_cycles") != 8
        or active_chain["authority"].get("total_cycles") != 8
        or checkpoint.get("next_cycle_index") != cycle_index
        or checkpoint.get("active_cycle_index") is not None
        or checkpoint.get("completed_cycles") != cycle_index - 1
        or checkpoint.get("current_authority_digest") != authority_digest
        or checkpoint.get("experiment_manifest_digest")
        != active_chain["manifest"]["manifest_digest"]
        or checkpoint.get("failure_digest") is not None
        or checkpoint.get("resume_allowed") is not True
        or checkpoint.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or checkpoint.get("executable") is not False
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_RUN_CHECKPOINT_NOT_READY"
        )
    local_authority = store.read_document(
        relative_ref=str(checkpoint["current_authority_ref"]),
        digest_field="authority_digest",
        expected_semantic_digest=authority_digest,
    )
    local_contract = store.read_document(
        relative_ref="genesis/experiment-contract.json",
        digest_field="experiment_contract_digest",
        expected_semantic_digest=contract_digest,
    )
    run_genesis = store.read_document(
        relative_ref=str(checkpoint["run_genesis_ref"]),
        digest_field="run_genesis_digest",
        expected_semantic_digest=str(checkpoint["run_genesis_digest"]),
    )
    if (
        dict(local_authority) != dict(active_chain["authority"])
        or dict(local_contract) != dict(active_chain["experiment_contract"])
        or run_genesis.get("run_id") != run_id
        or run_genesis.get("experiment_contract_binding", {}).get(
            "semantic_digest"
        )
        != contract_digest
        or run_genesis.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or run_genesis.get("executable") is not False
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_RUN_GENESIS_BINDING_INVALID"
        )
    return checkpoint


def _source_document(
    *,
    source_store: V31SourceQualificationStorePort,
    relative_ref: str,
    digest_field: str,
    expected_semantic_digest: str | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, str], bytes]:
    document = source_store.read_document(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=expected_semantic_digest,
    )
    binding = source_store.artifact_binding(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=str(document[digest_field]),
    )
    raw = source_store.read_raw(
        relative_ref=relative_ref,
        expected_sha256=str(binding["physical_sha256"]),
    )
    if hashlib.sha256(raw).hexdigest() != binding["physical_sha256"]:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_SOURCE_PHYSICAL_DRIFT"
        )
    return document, dict(binding), raw


def _load_source_bundle(
    *,
    source_store: V31SourceQualificationStorePort,
    qualification_id: str,
) -> dict[str, Any]:
    replay = verify_durable_v31_source_qualification_completion(
        store=source_store, qualification_id=qualification_id
    )
    completion = replay["completion"]
    checkpoint = replay["checkpoint"]
    plan = replay["plan"]
    reservation = replay["reservation"]
    document_inputs = {
        "QUALIFICATION_PLAN": (
            str(checkpoint["plan_binding"]["relative_ref"]),
            _DOCUMENT_SPECS["QUALIFICATION_PLAN"][0],
            str(plan["source_qualification_plan_digest"]),
        ),
        "QUALIFICATION_RESERVATION": (
            str(checkpoint["reservation_binding"]["relative_ref"]),
            _DOCUMENT_SPECS["QUALIFICATION_RESERVATION"][0],
            str(reservation["source_qualification_reservation_digest"]),
        ),
        "QUALIFICATION_CHECKPOINT": (
            "qualification-checkpoint.json",
            _DOCUMENT_SPECS["QUALIFICATION_CHECKPOINT"][0],
            str(checkpoint["source_qualification_checkpoint_digest"]),
        ),
        "QUALIFICATION_COMPLETION": (
            str(replay["completion_binding"]["relative_ref"]),
            _DOCUMENT_SPECS["QUALIFICATION_COMPLETION"][0],
            str(completion["source_qualification_completion_digest"]),
        ),
        "MARKET_SNAPSHOT": (
            str(completion["snapshot_binding"]["relative_ref"]),
            _DOCUMENT_SPECS["MARKET_SNAPSHOT"][0],
            str(completion["native_market_snapshot_digest"]),
        ),
        "PIT_DATASET": (
            str(completion["pit_dataset_binding"]["relative_ref"]),
            _DOCUMENT_SPECS["PIT_DATASET"][0],
            str(completion["pit_dataset_digest"]),
        ),
    }
    documents: dict[str, Mapping[str, Any]] = {}
    bindings: dict[str, Mapping[str, str]] = {}
    raw_bytes: dict[str, bytes] = {}
    for role, (relative_ref, digest_field, digest) in document_inputs.items():
        document, binding, raw = _source_document(
            source_store=source_store,
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=digest,
        )
        documents[role] = document
        bindings[role] = binding
        raw_bytes[role] = raw

    event_documents: list[Mapping[str, Any]] = []
    event_bindings: list[Mapping[str, str]] = []
    event_raw_bytes: list[bytes] = []
    for binding in completion["information_event_bindings"]:
        document, durable_binding, raw = _source_document(
            source_store=source_store,
            relative_ref=str(binding["relative_ref"]),
            digest_field="source_qualification_information_event_record_digest",
            expected_semantic_digest=str(binding["semantic_digest"]),
        )
        if durable_binding != dict(binding):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_INFORMATION_PHYSICAL_BINDING_DRIFT"
            )
        event_documents.append(document)
        event_bindings.append(durable_binding)
        event_raw_bytes.append(raw)

    raw_payloads: dict[str, bytes] = {}
    raw_bindings: dict[str, Mapping[str, str]] = {}
    for request_id, binding in completion["raw_bindings"].items():
        payload = source_store.read_raw(
            relative_ref=str(binding["relative_ref"]),
            expected_sha256=str(binding["physical_sha256"]),
        )
        physical = hashlib.sha256(payload).hexdigest()
        if physical != binding["semantic_digest"] or physical != binding["physical_sha256"]:
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_RAW_PHYSICAL_BINDING_DRIFT"
            )
        raw_payloads[str(request_id)] = payload
        raw_bindings[str(request_id)] = dict(binding)
    return {
        "replay": replay,
        "documents": documents,
        "bindings": bindings,
        "raw_bytes": raw_bytes,
        "event_documents": event_documents,
        "event_bindings": event_bindings,
        "event_raw_bytes": event_raw_bytes,
        "raw_payloads": raw_payloads,
        "raw_bindings": raw_bindings,
    }


def _validate_source_scope(
    *,
    bundle: Mapping[str, Any],
    qualification_id: str,
    authority: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> tuple[str, str, str]:
    documents = bundle["documents"]
    plan = documents["QUALIFICATION_PLAN"]
    checkpoint = documents["QUALIFICATION_CHECKPOINT"]
    completion = documents["QUALIFICATION_COMPLETION"]
    snapshot = documents["MARKET_SNAPSHOT"]
    dataset = documents["PIT_DATASET"]
    authority_time = _time(
        authority["recorded_at"], "V31_CYCLE_SOURCE_AUTHORITY_TIME_INVALID"
    )
    captures = snapshot.get("source_captures")
    if not isinstance(captures, list) or not captures:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_CAPTURES_INVALID"
        )
    started = [
        _time(row.get("request_started_at"), "V31_CYCLE_SOURCE_CAPTURE_TIME_INVALID")
        for row in captures
        if isinstance(row, Mapping)
    ]
    received = [
        _time(row.get("response_received_at"), "V31_CYCLE_SOURCE_CAPTURE_TIME_INVALID")
        for row in captures
        if isinstance(row, Mapping)
    ]
    if (
        len(started) != len(captures)
        or len(received) != len(captures)
        or min(started) <= authority_time
        or any(end < begin for begin, end in zip(started, received))
        or _time(completion.get("decision_at"), "V31_CYCLE_SOURCE_DECISION_TIME_INVALID")
        < max(received)
        or _time(completion.get("completed_at"), "V31_CYCLE_SOURCE_COMPLETION_TIME_INVALID")
        < _time(completion.get("decision_at"), "V31_CYCLE_SOURCE_DECISION_TIME_INVALID")
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_CAPTURE_NOT_FRESH_AFTER_AUTHORITY"
        )
    information = snapshot.get("market_information_snapshot")
    if (
        plan.get("qualification_id") != qualification_id
        or checkpoint.get("qualification_id") != qualification_id
        or checkpoint.get("status") != "SEALED"
        or completion.get("qualification_id") != qualification_id
        or snapshot.get("run_id") != qualification_id
        or snapshot.get("cycle_index") != 1
        or snapshot.get("instrument_id") != "BTC-USDT-SWAP"
        or snapshot.get("data_scope") != "OFFICIAL_PUBLIC_MARKET_ONLY"
        or snapshot.get("prior_market_snapshot_digest") is not None
        or not isinstance(information, Mapping)
        or information.get("run_id") != qualification_id
        or information.get("cycle_index") != 1
        or dataset.get("decision_at") != completion.get("decision_at")
        or dataset.get("point_in_time") is not True
        or dataset.get("missing_is_zero") is not False
        or set(bundle["raw_payloads"]) != set(completion["raw_bindings"])
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_QUALIFICATION_IDENTITY_MISMATCH"
        )
    specification = snapshot.get("contract_specification")
    financial = (
        contract.get("portfolio_scope", {})
        .get("financial_shadow", {})
        .get("market_economics_policy", {})
    )
    if (
        not isinstance(specification, Mapping)
        or specification.get("instrument_id") != "BTC-USDT-SWAP"
        or specification.get("contract_multiplier") != financial.get("contract_multiplier")
        or specification.get("contract_multiplier_unit")
        != financial.get("contract_multiplier_unit")
        or specification.get("okx_ct_mult") != financial.get("contract_size_multiplier")
        or specification.get("quantity_step_contracts")
        != financial.get("quantity_step_contracts")
        or specification.get("minimum_quantity_contracts")
        != financial.get("minimum_quantity_contracts")
        or specification.get("price_tick_usdt") != financial.get("price_tick_usdt")
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_INSTRUMENT_CONTRACT_MISMATCH"
        )
    _assert_no_legacy_authority(bundle)
    closed_rows = [
        row
        for row in dataset.get("data", [])
        if isinstance(row, Mapping)
        and row.get("metric") == "candle-1h-return-pct"
        and row.get("timeframe") == "1h"
    ]
    if len(closed_rows) != 1 or closed_rows[0].get("value") is None:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_CLOSED_1H_BINDING_INVALID"
        )
    closed_1h_as_of = str(closed_rows[0].get("as_of"))
    _time(closed_1h_as_of, "V31_CYCLE_SOURCE_CLOSED_1H_TIME_INVALID")
    return (
        min(started).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        max(received).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        closed_1h_as_of,
    )


def _copy_rows(
    *, bundle: Mapping[str, Any], cycle_index: int
) -> list[dict[str, Any]]:
    base = f"cycles/{cycle_index:04d}/market/source-admission"
    rows: list[dict[str, Any]] = []
    for role, (_, schema_id, suffix) in _DOCUMENT_SPECS.items():
        binding = bundle["bindings"][role]
        rows.append(
            {
                "artifact_role": role,
                "artifact_id": role.lower(),
                "source_relative_ref": binding["relative_ref"],
                "target_relative_ref": f"{base}/{suffix}",
                "schema_id": schema_id,
                "digest_field": _DOCUMENT_SPECS[role][0],
                "semantic_digest": binding["semantic_digest"],
                "source_physical_sha256": binding["physical_sha256"],
                "target_physical_sha256": binding["physical_sha256"],
                "exact_bytes_copied": True,
            }
        )
    for index, binding in enumerate(bundle["event_bindings"], start=1):
        rows.append(
            {
                "artifact_role": "INFORMATION_EVENT",
                "artifact_id": f"{index:04d}",
                "source_relative_ref": binding["relative_ref"],
                "target_relative_ref": f"{base}/adapted/information-event-{index:04d}.json",
                "schema_id": "theory_paper_v31_source_qualification_information_event",
                "digest_field": "source_qualification_information_event_record_digest",
                "semantic_digest": binding["semantic_digest"],
                "source_physical_sha256": binding["physical_sha256"],
                "target_physical_sha256": binding["physical_sha256"],
                "exact_bytes_copied": True,
            }
        )
    for request_id in sorted(bundle["raw_bindings"]):
        binding = bundle["raw_bindings"][request_id]
        rows.append(
            {
                "artifact_role": "RAW_RESPONSE",
                "artifact_id": request_id,
                "source_relative_ref": binding["relative_ref"],
                "target_relative_ref": f"{base}/raw/{request_id}.body",
                "schema_id": None,
                "digest_field": None,
                "semantic_digest": binding["semantic_digest"],
                "source_physical_sha256": binding["physical_sha256"],
                "target_physical_sha256": binding["physical_sha256"],
                "exact_bytes_copied": True,
            }
        )
    return sorted(rows, key=lambda row: (row["artifact_role"], row["artifact_id"]))


def _payload_by_identity(bundle: Mapping[str, Any]) -> dict[tuple[str, str], bytes]:
    payloads = {
        (role, role.lower()): bundle["raw_bytes"][role]
        for role in _DOCUMENT_SPECS
    }
    payloads.update(
        {
            ("INFORMATION_EVENT", f"{index:04d}"): raw
            for index, raw in enumerate(bundle["event_raw_bytes"], start=1)
        }
    )
    payloads.update(
        {
            ("RAW_RESPONSE", request_id): payload
            for request_id, payload in bundle["raw_payloads"].items()
        }
    )
    return payloads


def _replay_target_copies(
    *, store: V31ResearchStorePort, receipt: Mapping[str, Any]
) -> None:
    for row in receipt["artifact_copies"]:
        raw = store.read_raw(
            relative_ref=row["target_relative_ref"],
            expected_sha256=row["target_physical_sha256"],
        )
        if hashlib.sha256(raw).hexdigest() != row["source_physical_sha256"]:
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_TARGET_PHYSICAL_DRIFT"
            )
        if row["artifact_role"] != "RAW_RESPONSE":
            binding = store.artifact_binding(
                relative_ref=row["target_relative_ref"],
                digest_field=row["digest_field"],
                expected_semantic_digest=row["semantic_digest"],
            )
            if (
                binding["semantic_digest"] != row["semantic_digest"]
                or binding["physical_sha256"] != row["target_physical_sha256"]
            ):
                raise V31CycleSourceAdmissionWorkflowError(
                    "V31_CYCLE_SOURCE_TARGET_SEMANTIC_DRIFT"
                )


def _replay_target_source_semantics(
    *, store: V31ResearchStorePort, receipt: Mapping[str, Any]
) -> None:
    """Rebuild the Q6 closure solely from the copied run-local bytes."""

    rows = list(receipt["artifact_copies"])

    def singleton(role: str) -> Mapping[str, Any]:
        row = next(item for item in rows if item["artifact_role"] == role)
        return store.read_document(
            relative_ref=row["target_relative_ref"],
            digest_field=row["digest_field"],
            expected_semantic_digest=row["semantic_digest"],
        )

    plan = singleton("QUALIFICATION_PLAN")
    reservation = singleton("QUALIFICATION_RESERVATION")
    checkpoint = singleton("QUALIFICATION_CHECKPOINT")
    completion = singleton("QUALIFICATION_COMPLETION")
    snapshot = singleton("MARKET_SNAPSHOT")
    dataset = singleton("PIT_DATASET")
    verify_v31_source_qualification_plan(plan)
    verify_v31_source_qualification_reservation(reservation, plan=plan)
    verify_v31_source_qualification_checkpoint(checkpoint)
    verify_v31_source_qualification_completion(completion)
    if (
        checkpoint.get("status") != "SEALED"
        or checkpoint.get("qualification_id") != receipt["source_qualification_id"]
        or checkpoint.get("source_qualification_checkpoint_digest")
        != receipt["source_qualification_checkpoint_digest"]
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_COPIED_CHECKPOINT_INVALID"
        )

    raw_rows = {
        row["artifact_id"]: row
        for row in rows
        if row["artifact_role"] == "RAW_RESPONSE"
    }
    raw_payloads = {
        request_id: store.read_raw(
            relative_ref=row["target_relative_ref"],
            expected_sha256=row["target_physical_sha256"],
        )
        for request_id, row in raw_rows.items()
    }
    validate_v31_source_qualification_collection(
        plan=plan,
        snapshot=snapshot,
        raw_body_by_request_id=raw_payloads,
        decision_at=str(completion["decision_at"]),
    )
    event_rows = sorted(
        (row for row in rows if row["artifact_role"] == "INFORMATION_EVENT"),
        key=lambda row: row["artifact_id"],
    )
    event_records = [
        store.read_document(
            relative_ref=row["target_relative_ref"],
            digest_field=row["digest_field"],
            expected_semantic_digest=row["semantic_digest"],
        )
        for row in event_rows
    ]
    for record in event_records:
        verify_v31_source_qualification_information_event_record(
            record, qualification_id=str(receipt["source_qualification_id"])
        )

    def source_binding(row: Mapping[str, Any]) -> dict[str, str]:
        return {
            "relative_ref": row["source_relative_ref"],
            "semantic_digest": row["semantic_digest"],
            "physical_sha256": row["source_physical_sha256"],
        }

    snapshot_row = next(
        row for row in rows if row["artifact_role"] == "MARKET_SNAPSHOT"
    )
    dataset_row = next(row for row in rows if row["artifact_role"] == "PIT_DATASET")
    rebuilt = seal_v31_source_qualification_completion(
        plan=plan,
        reservation=reservation,
        completed_at=str(completion["completed_at"]),
        decision_at=str(completion["decision_at"]),
        snapshot=snapshot,
        snapshot_binding=source_binding(snapshot_row),
        raw_bindings={
            request_id: source_binding(row)
            for request_id, row in sorted(raw_rows.items())
        },
        pit_dataset=dataset,
        pit_dataset_binding=source_binding(dataset_row),
        information_event_records=event_records,
        information_event_bindings=[source_binding(row) for row in event_rows],
        adapter_id=str(completion["adapter_id"]),
    )
    captures = {
        str(row["request_id"]): str(row["record_digest"])
        for row in snapshot["source_captures"]
    }
    if (
        rebuilt != dict(completion)
        or captures != dict(receipt["source_capture_record_digests"])
        or receipt.get("source_capture_records_embedded_in_copied_snapshot")
        is not True
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_RUN_LOCAL_REPLAY_MISMATCH"
        )


def _prior_open_interest_binding(
    dataset: Mapping[str, Any],
) -> tuple[str, str]:
    rows = [
        row
        for row in dataset.get("data", [])
        if isinstance(row, Mapping)
        and row.get("metric") == "open-interest-btc"
        and row.get("instrument_id") == "BTC-USDT-SWAP"
    ]
    if len(rows) != 1:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PRIOR_OPEN_INTEREST_BINDING_INVALID"
        )
    row = rows[0]
    digest = row.get("datum_digest")
    if not isinstance(digest, str) or len(digest) != 64 or row.get("missing_is_zero") is not False:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PRIOR_OPEN_INTEREST_BINDING_INVALID"
        )
    if row.get("value") is None:
        if row.get("missingness") == "OBSERVED" or not row.get("missing_reason"):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_PRIOR_OPEN_INTEREST_UNKNOWN_INVALID"
            )
        return digest, "UNKNOWN"
    if row.get("missingness") != "OBSERVED" or row.get("missing_reason") is not None:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PRIOR_OPEN_INTEREST_OBSERVED_INVALID"
        )
    return digest, "OBSERVED"


def _derive_previous_cycle_context(
    *,
    store: V31ResearchStorePort,
    checkpoint: Mapping[str, Any],
    run_id: str,
    cycle_index: int,
    authority_digest: str,
    contract_digest: str,
    current_qualification_id: str,
    current_completion_digest: str,
    current_snapshot_digest: str,
    caller_previous_admission_binding: Mapping[str, Any] | None,
    caller_prior_snapshot_binding: Mapping[str, Any] | None,
    caller_prior_open_interest_digest: str | None,
) -> tuple[
    dict[str, Any], dict[str, Mapping[str, str] | None]
]:
    if cycle_index == 1:
        if any(
            value is not None
            for value in (
                caller_previous_admission_binding,
                caller_prior_snapshot_binding,
                caller_prior_open_interest_digest,
            )
        ):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_GENESIS_PRIOR_CONTEXT_FORBIDDEN"
            )
        return (
            {
                "status": "GENESIS_NO_PRIOR_SOURCE_CONTEXT",
                "previous_cycle_source_admission_binding": None,
                "prior_snapshot_binding": None,
                "prior_open_interest_datum_digest": None,
                "prior_open_interest_status": "NOT_APPLICABLE_GENESIS",
                "prior_open_interest_zero_imputed": False,
                "previous_decision_at": None,
                "previous_admitted_at": None,
                "previous_closed_1h_as_of": None,
            },
            {name: None for name in _PREVIOUS_HEAD_KEYS},
        )

    previous_cycle = cycle_index - 1
    if (
        checkpoint.get("completed_cycles") != previous_cycle
        or checkpoint.get("next_cycle_index") != cycle_index
        or checkpoint.get("accepted_state_ref")
        != f"cycles/{previous_cycle:04d}/accepted-research-state.json"
        or checkpoint.get("last_completion_ref")
        != f"cycles/{previous_cycle:04d}/completion-receipt.json"
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PREVIOUS_CYCLE_NOT_ACCEPTED"
        )
    events = list(store.read_events(run_id=run_id, cycle_index=previous_cycle))
    if (
        len(events) != 6
        or [event.get("event_type") for event in events]
        != [
            "INPUTS_ADMITTED",
            "PROPOSAL_SEALED",
            "EVALUATION_SEALED",
            "SELECTION_SEALED",
            "STATE_ACCEPTED",
            "COMPLETION_SEALED",
        ]
        or events[-1].get("artifact_semantic_digest")
        != checkpoint.get("last_completion_digest")
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PREVIOUS_EVENT_CHAIN_INCOMPLETE"
        )
    accepted = store.read_document(
        relative_ref=str(checkpoint["accepted_state_ref"]),
        digest_field="accepted_state_digest",
        expected_semantic_digest=str(checkpoint["accepted_state_digest"]),
    )
    completion = store.read_document(
        relative_ref=str(checkpoint["last_completion_ref"]),
        digest_field="completion_receipt_digest",
        expected_semantic_digest=str(checkpoint["last_completion_digest"]),
    )
    inputs = store.read_document(
        relative_ref=f"cycles/{previous_cycle:04d}/inputs-receipt.json",
        digest_field="inputs_receipt_digest",
    )
    try:
        verify_v31_accepted_state(accepted)
        verify_v31_completion_receipt(completion)
        verify_v31_inputs_receipt(inputs)
    except (V31ResearchCycleError, AgentResearchContractError) as exc:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PREVIOUS_ACCEPTED_ARTIFACT_INVALID"
        ) from exc
    if (
        accepted.get("run_id") != run_id
        or accepted.get("cycle_index") != previous_cycle
        or completion.get("accepted_state_digest") != accepted.get("accepted_state_digest")
        or inputs.get("inputs_receipt_digest") != accepted.get("inputs_receipt_digest")
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PREVIOUS_ACCEPTED_IDENTITY_MISMATCH"
        )

    previous_source = verify_durable_v31_cycle_source_admission(
        run_store=store,
        run_id=run_id,
        cycle_index=previous_cycle,
        expected_authority_digest=authority_digest,
        expected_experiment_contract_digest=contract_digest,
    )
    previous_receipt = previous_source["cycle_source_admission"]
    previous_binding = previous_source["cycle_source_admission_binding"]
    prior_snapshot_binding = previous_source["authoring_source_bindings"][
        "market_snapshot_binding"
    ]
    prior_dataset_binding = previous_source["authoring_source_bindings"][
        "pit_dataset_binding"
    ]
    prior_dataset = store.read_document(
        relative_ref=prior_dataset_binding["relative_ref"],
        digest_field="dataset_digest",
        expected_semantic_digest=prior_dataset_binding["semantic_digest"],
    )
    oi_digest, oi_status = _prior_open_interest_binding(prior_dataset)
    if (
        checkpoint.get("accepted_pit_dataset_digest")
        != previous_receipt.get("pit_dataset_digest")
        or accepted.get("pit_dataset_digest")
        != previous_receipt.get("pit_dataset_digest")
        or inputs.get("pit_dataset_digest")
        != previous_receipt.get("pit_dataset_digest")
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PREVIOUS_SOURCE_NOT_ACCEPTED"
        )

    # The eight semantic heads are verified and uniquely resolved by the
    # durable-cycle owner.  Source admission consumes that fixed projection but
    # does not copy it into the source receipt.
    try:
        from .v31_durable_cycle import v31_cycle_authoring_head_bindings

        previous_heads = v31_cycle_authoring_head_bindings(
            store=store, run_id=run_id, cycle_index=previous_cycle
        )
    except (ImportError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PREVIOUS_HEADS_UNAVAILABLE"
        ) from exc
    if (
        set(previous_heads) != set(_PREVIOUS_HEAD_KEYS)
        or previous_heads["previous_accepted_state"]["semantic_digest"]
        != accepted["accepted_state_digest"]
        or previous_heads["previous_pit_dataset"]["semantic_digest"]
        != previous_receipt["pit_dataset_digest"]
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_PREVIOUS_HEAD_GAP_OR_MISMATCH"
        )

    if (
        caller_previous_admission_binding != previous_binding
        or caller_prior_snapshot_binding != prior_snapshot_binding
        or caller_prior_open_interest_digest != oi_digest
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_CALLER_PREVIOUS_BINDING_MISMATCH"
        )

    for prior_cycle in range(1, cycle_index):
        prior = verify_durable_v31_cycle_source_admission(
            run_store=store,
            run_id=run_id,
            cycle_index=prior_cycle,
            expected_authority_digest=authority_digest,
            expected_experiment_contract_digest=contract_digest,
        )["cycle_source_admission"]
        if (
            prior.get("source_qualification_id") == current_qualification_id
            or prior.get("source_qualification_completion_digest")
            == current_completion_digest
            or prior.get("native_market_snapshot_digest") == current_snapshot_digest
        ):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_QUALIFICATION_RESURRECTION_FORBIDDEN"
            )

    return (
        {
            "status": "BOUND_TO_PREVIOUS_ACCEPTED_CYCLE",
            "previous_cycle_source_admission_binding": previous_binding,
            "prior_snapshot_binding": prior_snapshot_binding,
            "prior_open_interest_datum_digest": oi_digest,
            "prior_open_interest_status": oi_status,
            "prior_open_interest_zero_imputed": False,
            "previous_decision_at": previous_receipt["decision_at"],
            "previous_admitted_at": previous_receipt["admitted_at"],
            "previous_closed_1h_as_of": previous_receipt["closed_1h_as_of"],
        },
        dict(previous_heads),
    )


def admit_fresh_v31_source_to_authorized_cycle(
    *,
    source_store: V31SourceQualificationStorePort,
    run_store: V31ResearchStorePort,
    active_chain: Mapping[str, Any],
    qualification_id: str,
    run_id: str,
    cycle_index: int,
    admitted_at: str,
    previous_cycle_source_admission_binding: Mapping[str, Any] | None = None,
    prior_snapshot_binding: Mapping[str, Any] | None = None,
    prior_open_interest_datum_digest: str | None = None,
) -> dict[str, Any]:
    """Copy a fresh Q6 evidence bundle into a READY authorized cycle.

    Each isolated qualification keeps its truthful internal ``cycle_index=1``.
    For formal cycles 2--8 this use case uniquely derives and verifies the
    previous accepted source/snapshot/open-interest context from the run store;
    caller-supplied bindings are comparisons, never authority.
    """

    try:
        if (
            isinstance(cycle_index, bool)
            or not isinstance(cycle_index, int)
            or not 1 <= cycle_index <= 8
        ):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_CYCLE_OUTSIDE_FROZEN_CONTRACT"
            )
        authority, contract, authority_digest, contract_digest = _validate_active_chain(
            active_chain=active_chain, run_id=run_id
        )
        checkpoint_before = _validate_run_genesis(
            store=run_store,
            run_id=run_id,
            cycle_index=cycle_index,
            active_chain=active_chain,
            authority_digest=authority_digest,
            contract_digest=contract_digest,
        )
        bundle = _load_source_bundle(
            source_store=source_store, qualification_id=qualification_id
        )
        earliest, latest, closed_1h_as_of = _validate_source_scope(
            bundle=bundle,
            qualification_id=qualification_id,
            authority=authority,
            contract=contract,
        )
        completion = bundle["documents"]["QUALIFICATION_COMPLETION"]
        snapshot = bundle["documents"]["MARKET_SNAPSHOT"]
        dataset = bundle["documents"]["PIT_DATASET"]
        q_checkpoint = bundle["documents"]["QUALIFICATION_CHECKPOINT"]
        plan = bundle["documents"]["QUALIFICATION_PLAN"]
        copy_rows = _copy_rows(bundle=bundle, cycle_index=cycle_index)
        previous_context, previous_heads = _derive_previous_cycle_context(
            store=run_store,
            checkpoint=checkpoint_before,
            run_id=run_id,
            cycle_index=cycle_index,
            authority_digest=authority_digest,
            contract_digest=contract_digest,
            current_qualification_id=qualification_id,
            current_completion_digest=str(
                completion["source_qualification_completion_digest"]
            ),
            current_snapshot_digest=str(snapshot["native_market_snapshot_digest"]),
            caller_previous_admission_binding=(
                previous_cycle_source_admission_binding
            ),
            caller_prior_snapshot_binding=prior_snapshot_binding,
            caller_prior_open_interest_digest=prior_open_interest_datum_digest,
        )
        if cycle_index > 1 and _time(
            earliest, "V31_CYCLE_SOURCE_CAPTURE_TIME_INVALID"
        ) <= _time(
            previous_context["previous_decision_at"],
            "V31_CYCLE_SOURCE_PREVIOUS_CONTEXT_INVALID",
        ):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_CROSS_CYCLE_CAPTURE_TIME_REVERSAL"
            )
        receipt = seal_v31_cycle_source_admission(
            run_id=run_id,
            cycle_index=cycle_index,
            admitted_at=admitted_at,
            decision_at=str(completion["decision_at"]),
            closed_1h_as_of=closed_1h_as_of,
            active_authority_digest=authority_digest,
            active_authority_recorded_at=str(authority["recorded_at"]),
            experiment_contract_digest=contract_digest,
            source_qualification_id=qualification_id,
            source_qualification_plan_digest=str(
                plan["source_qualification_plan_digest"]
            ),
            source_qualification_checkpoint_digest=str(
                q_checkpoint["source_qualification_checkpoint_digest"]
            ),
            source_qualification_completion_digest=str(
                completion["source_qualification_completion_digest"]
            ),
            source_qualification_decision_at=str(completion["decision_at"]),
            native_market_snapshot_digest=str(
                snapshot["native_market_snapshot_digest"]
            ),
            pit_dataset_digest=str(dataset["dataset_digest"]),
            information_event_digests=list(
                completion["information_event_digests"]
            ),
            information_event_record_digests=[
                binding["semantic_digest"]
                for binding in completion["information_event_bindings"]
            ],
            source_capture_record_digests=dict(
                completion["source_capture_record_digests"]
            ),
            raw_physical_sha256_by_request_id={
                request_id: binding["physical_sha256"]
                for request_id, binding in sorted(bundle["raw_bindings"].items())
            },
            earliest_capture_started_at=earliest,
            latest_capture_received_at=latest,
            artifact_copies=copy_rows,
            previous_source_context=previous_context,
        )

        payloads = _payload_by_identity(bundle)
        for row in copy_rows:
            payload = payloads[(row["artifact_role"], row["artifact_id"])]
            binding = run_store.write_raw(
                relative_ref=row["target_relative_ref"], payload=payload
            )
            readback = run_store.read_raw(
                relative_ref=row["target_relative_ref"],
                expected_sha256=row["target_physical_sha256"],
            )
            if (
                readback != payload
                or binding["physical_sha256"] != row["target_physical_sha256"]
            ):
                raise V31CycleSourceAdmissionWorkflowError(
                    "V31_CYCLE_SOURCE_COPY_READBACK_MISMATCH"
                )
        _replay_target_copies(store=run_store, receipt=receipt)
        _replay_target_source_semantics(store=run_store, receipt=receipt)

        receipt_ref = cycle_source_admission_ref(cycle_index)
        receipt_binding = run_store.write_document(
            relative_ref=receipt_ref,
            document=receipt,
            digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
        )
        durable = run_store.read_document(
            relative_ref=receipt_ref,
            digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
            expected_semantic_digest=receipt[SOURCE_ADMISSION_DIGEST_FIELD],
        )
        if dict(durable) != receipt:
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_RECEIPT_READBACK_MISMATCH"
            )
        verify_v31_cycle_source_admission(durable)
        _replay_target_copies(store=run_store, receipt=durable)
        _replay_target_source_semantics(store=run_store, receipt=durable)
        checkpoint_after = run_store.load_checkpoint(run_id=run_id)
        if dict(checkpoint_after) != dict(checkpoint_before):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_CHECKPOINT_MUTATION_FORBIDDEN"
            )
        return {
            "status": "CYCLE_SOURCE_ADMITTED_NOT_STARTED",
            "cycle_source_admission": dict(durable),
            "cycle_source_admission_binding": _typed_admission_binding(
                receipt_binding
            ),
            "authoring_source_bindings": admitted_authoring_source_bindings(
                durable
            ),
            "previous_head_bindings": previous_heads,
            "checkpoint": dict(checkpoint_after),
            "source_qualification_is_start_authority": False,
            "cycle_started": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
    except V31CycleSourceAdmissionWorkflowError:
        raise
    except (V31CycleSourceAdmissionError, KeyError, TypeError, ValueError) as exc:
        raise V31CycleSourceAdmissionWorkflowError(
            f"V31_CYCLE_SOURCE_ADMISSION_FAILED:{exc}"
        ) from exc


def verify_durable_v31_cycle_source_admission(
    *,
    run_store: V31ResearchStorePort,
    run_id: str,
    cycle_index: int,
    expected_authority_digest: str,
    expected_experiment_contract_digest: str,
) -> dict[str, Any]:
    """Replay the sealed run-local receipt and every copied byte."""

    receipt_ref = cycle_source_admission_ref(cycle_index)
    receipt = run_store.read_document(
        relative_ref=receipt_ref,
        digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
    )
    digest = verify_v31_cycle_source_admission(receipt)
    if (
        receipt.get("run_id") != run_id
        or receipt.get("cycle_index") != cycle_index
        or receipt.get("active_authority_digest") != expected_authority_digest
        or receipt.get("experiment_contract_digest")
        != expected_experiment_contract_digest
    ):
        raise V31CycleSourceAdmissionWorkflowError(
            "V31_CYCLE_SOURCE_DURABLE_IDENTITY_MISMATCH"
        )
    _replay_target_copies(store=run_store, receipt=receipt)
    _replay_target_source_semantics(store=run_store, receipt=receipt)
    previous_heads: dict[str, Mapping[str, str] | None] = {
        name: None for name in _PREVIOUS_HEAD_KEYS
    }
    if cycle_index > 1:
        previous = verify_durable_v31_cycle_source_admission(
            run_store=run_store,
            run_id=run_id,
            cycle_index=cycle_index - 1,
            expected_authority_digest=expected_authority_digest,
            expected_experiment_contract_digest=(
                expected_experiment_contract_digest
            ),
        )
        context = receipt["previous_source_context"]
        prior_snapshot_binding = previous["authoring_source_bindings"][
            "market_snapshot_binding"
        ]
        prior_dataset_binding = previous["authoring_source_bindings"][
            "pit_dataset_binding"
        ]
        prior_dataset = run_store.read_document(
            relative_ref=prior_dataset_binding["relative_ref"],
            digest_field="dataset_digest",
            expected_semantic_digest=prior_dataset_binding["semantic_digest"],
        )
        oi_digest, oi_status = _prior_open_interest_binding(prior_dataset)
        if (
            context.get("previous_cycle_source_admission_binding")
            != previous["cycle_source_admission_binding"]
            or context.get("prior_snapshot_binding") != prior_snapshot_binding
            or context.get("prior_open_interest_datum_digest") != oi_digest
            or context.get("prior_open_interest_status") != oi_status
            or context.get("prior_open_interest_zero_imputed") is not False
            or context.get("previous_decision_at")
            != previous["cycle_source_admission"]["decision_at"]
            or context.get("previous_admitted_at")
            != previous["cycle_source_admission"]["admitted_at"]
            or context.get("previous_closed_1h_as_of")
            != previous["cycle_source_admission"]["closed_1h_as_of"]
        ):
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_DURABLE_PREVIOUS_CHAIN_MISMATCH"
            )
        try:
            from .v31_durable_cycle import v31_cycle_authoring_head_bindings

            previous_heads = dict(
                v31_cycle_authoring_head_bindings(
                    store=run_store,
                    run_id=run_id,
                    cycle_index=cycle_index - 1,
                )
            )
        except (ImportError, AttributeError, KeyError, TypeError, ValueError) as exc:
            raise V31CycleSourceAdmissionWorkflowError(
                "V31_CYCLE_SOURCE_PREVIOUS_HEADS_UNAVAILABLE"
            ) from exc
    binding = run_store.artifact_binding(
        relative_ref=receipt_ref,
        digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
        expected_semantic_digest=digest,
    )
    return {
        "cycle_source_admission": dict(receipt),
        "cycle_source_admission_binding": _typed_admission_binding(binding),
        "authoring_source_bindings": admitted_authoring_source_bindings(receipt),
        "previous_head_bindings": previous_heads,
    }


__all__ = [
    "V31CycleSourceAdmissionWorkflowError",
    "admit_fresh_v31_source_to_authorized_cycle",
    "verify_durable_v31_cycle_source_admission",
]
