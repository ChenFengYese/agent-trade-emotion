"""Typed, evidence-bearing Q6/Q7 qualification receipts for V3.1.

Unlike the legacy generic gate receipt, these constructors never accept a list
of opaque digests.  Q6 embeds and cross-validates the sealed source plan,
reservation, terminal checkpoint, and completion.  Q7 embeds and validates the
terminal two-stage transport checkpoint and its content-addressed evidence.

Physical-byte replay is an Application/Infrastructure responsibility.  The
receipt carries exact project-relative physical bindings so that the authority
loader can repeat that check before admitting the gate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from ..contracts.canonical import canonical_digest, self_digest, verify_self_digest
from ..v31_agent_transport import (
    V31_AGENT_ID,
    V31_TRANSPORT_EVIDENCE_LEVEL,
    V31AgentTransportError,
    validate_v31_transport_evidence,
)
from ..v31_experiment_contracts import (
    EXPERIMENT_SCHEMA_ID,
    verify_minimal_experiment_contract,
)
from ..v31_cycle_authoring import (
    AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
    AUTHORING_COMPILATION_ADMISSION_SCHEMA_ID,
    AUTHORING_COMPILATION_DIGEST_FIELD,
    AUTHORING_COMPILATION_SCHEMA_ID,
    COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
    COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID,
    AUTHORING_ENVELOPE_DIGEST_FIELD,
    AUTHORING_PACKET_DIGEST_FIELD,
    AUTHORING_PACKET_SCHEMA_ID,
    V31CycleAuthoringError,
    validate_v31_agent_open_analysis_envelope,
    validate_v31_authoring_compilation_admission,
    validate_v31_authoring_compilation_receipt,
    validate_v31_proposal_authoring_packet,
)
from ..v31_source_qualification import (
    OKX_QUALIFICATION_INSTRUMENT_ID,
    V31SourceQualificationError,
    verify_v31_source_qualification_checkpoint,
    verify_v31_source_qualification_completion,
    verify_v31_source_qualification_information_event_record,
    verify_v31_source_qualification_plan,
    verify_v31_source_qualification_reservation,
)


# Q7 is deliberately absent until the production open-analysis packet,
# fail-closed compiler, final proposal, and post-seal selection are all bound
# into one terminal qualification chain.  The older two-stage final-proposal
# transport is useful regression evidence but is not RUN_READY evidence.
EXTERNAL_TYPED_QUALIFICATION_GATE_IDS = ("Q6", "Q7")
EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID = (
    "theory_paper_v31_typed_qualification_gate_receipt"
)
EXTERNAL_TYPED_QUALIFICATION_SCHEMA_VERSION = "1.1.0"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ROOT_PREFIX = PurePosixPath(
    "agent-cluster/experiments/v31-qualifications"
)
_Q6_IMPLEMENTATION_PATHS = (
    "tests/test_theory_paper_v2_v31_external_qualification.py",
    "tests/test_theory_paper_v2_v31_source_qualification.py",
    "trade_system/theory_paper_v2/application/v31_external_qualification.py",
    "trade_system/theory_paper_v2/application/v31_source_qualification.py",
    "trade_system/theory_paper_v2/domain/governance/v31_external_qualification.py",
    "trade_system/theory_paper_v2/domain/v31_source_qualification.py",
    "trade_system/theory_paper_v2/infrastructure/v31_market_adapter.py",
    "trade_system/theory_paper_v2/infrastructure/v31_source_qualification_store.py",
    "trade_system/theory_paper_v2/presentation/v31_source_qualification_composition.py",
)
_Q7_IMPLEMENTATION_PATHS = (
    "tests/test_theory_paper_v2_v31_agent_transport.py",
    "tests/test_theory_paper_v2_v31_external_qualification.py",
    "tests/test_theory_paper_v2_v31_semantic_compiler.py",
    "trade_system/theory_paper_v2/application/v31_agent_transport.py",
    "trade_system/theory_paper_v2/application/v31_cycle_authoring.py",
    "trade_system/theory_paper_v2/application/v31_external_qualification.py",
    "trade_system/theory_paper_v2/domain/governance/v31_external_qualification.py",
    "trade_system/theory_paper_v2/domain/v31_agent_transport.py",
    "trade_system/theory_paper_v2/domain/v31_cycle_authoring.py",
    "trade_system/theory_paper_v2/infrastructure/v31_agent_transport_store.py",
    "trade_system/theory_paper_v2/infrastructure/v31_semantic_compiler.py",
    "trade_system/theory_paper_v2/presentation/v31_agent_transport_worker.py",
)
_Q6_ARTIFACT_SPECS = {
    "plan": (
        "frozen/source-qualification-plan.json",
        "theory_paper_v31_source_qualification_plan",
        "source_qualification_plan_digest",
    ),
    "reservation": (
        "reservation/source-qualification-reservation.json",
        "theory_paper_v31_source_qualification_reservation",
        "source_qualification_reservation_digest",
    ),
    "checkpoint": (
        "qualification-checkpoint.json",
        "theory_paper_v31_source_qualification_checkpoint",
        "source_qualification_checkpoint_digest",
    ),
    "completion": (
        "receipts/source-qualification-completion.json",
        "theory_paper_v31_source_qualification_completion",
        "source_qualification_completion_digest",
    ),
}
_Q7_ARTIFACT_SPECS = {
    "checkpoint": (
        "cycles/0001/agent-transport/checkpoint.json",
        "theory_paper_v31_agent_transport_checkpoint",
        "checkpoint_digest",
    ),
    "transport_evidence": (
        None,
        "theory_paper_v31_agent_transport_evidence",
        "transport_evidence_digest",
    ),
    "authoring_packet": (
        None,
        AUTHORING_PACKET_SCHEMA_ID,
        AUTHORING_PACKET_DIGEST_FIELD,
    ),
    "compilation_receipt": (
        "cycles/0001/agent-transport/compilation/compilation-receipt.json",
        AUTHORING_COMPILATION_SCHEMA_ID,
        AUTHORING_COMPILATION_DIGEST_FIELD,
    ),
    "compilation_admission": (
        "cycles/0001/agent-transport/compilation/compilation-admission.json",
        AUTHORING_COMPILATION_ADMISSION_SCHEMA_ID,
        AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
    ),
    "compiled_assembly_bundle": (
        "cycles/0001/agent-transport/compilation/compiled-assembly-bundle.json",
        COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID,
        COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
    ),
    "experiment_subject": (
        None,
        EXPERIMENT_SCHEMA_ID,
        "experiment_contract_digest",
    ),
}


class V31ExternalQualificationError(ValueError):
    """A dynamic V3.1 qualification gate could not honestly pass."""


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise V31ExternalQualificationError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31ExternalQualificationError(code)
    return value


def _timestamp(value: Any, code: str) -> datetime:
    value = _text(value, code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31ExternalQualificationError(code) from exc
    if parsed.tzinfo is None:
        raise V31ExternalQualificationError(code)
    normalized = parsed.astimezone(UTC)
    if normalized.isoformat().replace("+00:00", "Z") != value:
        raise V31ExternalQualificationError(code)
    return normalized


def _path(value: Any, code: str) -> str:
    value = _text(value, code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.as_posix() != value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31ExternalQualificationError(code)
    return value


def _contains_retired_execution_authority(value: Any) -> bool:
    """Find the retired label at any depth without trusting projections."""

    if isinstance(value, Mapping):
        if value.get("external_execution_authority") == "NONE_E0":
            return True
        return any(
            _contains_retired_execution_authority(nested)
            for nested in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_retired_execution_authority(row) for row in value)
    return False


def _manifest_context(
    *, experiment_contract: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[str, str]:
    # Local import keeps this module available to the central qualification
    # router without creating a module-import cycle.
    from .v31_experiment_qualification import (
        manifest_qualification_subject_digest,
        validate_manifest_experiment_contract_alignment,
    )

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    subject_digest = validate_manifest_experiment_contract_alignment(
        manifest, experiment_contract
    )
    if subject_digest != manifest_qualification_subject_digest(manifest):
        raise V31ExternalQualificationError(
            "EXTERNAL_QUALIFICATION_MANIFEST_SUBJECT_INVALID"
        )
    return contract_digest, subject_digest


def _implementation_evidence(
    *, gate_id: str, manifest: Mapping[str, Any]
) -> list[dict[str, str]]:
    paths = _Q6_IMPLEMENTATION_PATHS if gate_id == "Q6" else _Q7_IMPLEMENTATION_PATHS
    bindings = manifest.get("implementation_bindings")
    if not isinstance(bindings, Mapping):
        raise V31ExternalQualificationError(
            "EXTERNAL_QUALIFICATION_IMPLEMENTATION_BINDINGS_INVALID"
        )
    result: list[dict[str, str]] = []
    for path in sorted(paths):
        physical = _digest(
            bindings.get(path),
            "EXTERNAL_QUALIFICATION_IMPLEMENTATION_EVIDENCE_MISSING",
        )
        result.append(
            {
                "evidence_id": f"{gate_id}:{path}",
                "evidence_kind": (
                    "TEST_SOURCE" if path.startswith("tests/") else "IMPLEMENTATION_SOURCE"
                ),
                "path": path,
                "physical_sha256": physical,
                "binding_digest": canonical_digest(
                    {"path": path, "physical_sha256": physical}
                ),
            }
        )
    return result


def _artifact_binding(
    value: Any,
    *,
    expected_path: str | None,
    expected_schema_id: str,
    expected_digest_field: str,
    expected_semantic_digest: str,
    code: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "path",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }:
        raise V31ExternalQualificationError(code)
    result = {
        "path": _path(value.get("path"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }
    if (
        (expected_path is not None and result["path"] != expected_path)
        or result["schema_id"] != expected_schema_id
        or result["digest_field"] != expected_digest_field
        or result["semantic_digest"] != expected_semantic_digest
    ):
        raise V31ExternalQualificationError(code)
    return result


def _q6_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "plan",
        "reservation",
        "checkpoint",
        "completion",
        "information_event_records",
        "artifact_bindings",
    }:
        raise V31ExternalQualificationError("Q6_EVIDENCE_SCHEMA_INVALID")
    if _contains_retired_execution_authority(value):
        raise V31ExternalQualificationError(
            "Q6_EVIDENCE_RETIRED_EXECUTION_AUTHORITY"
        )
    plan = dict(value["plan"])
    reservation = dict(value["reservation"])
    checkpoint = dict(value["checkpoint"])
    completion = dict(value["completion"])
    try:
        plan_digest = verify_v31_source_qualification_plan(plan)
        reservation_digest = verify_v31_source_qualification_reservation(
            reservation, plan=plan
        )
        checkpoint_digest = verify_v31_source_qualification_checkpoint(checkpoint)
        completion_digest = verify_v31_source_qualification_completion(completion)
    except (TypeError, ValueError, V31SourceQualificationError) as exc:
        raise V31ExternalQualificationError("Q6_EVIDENCE_DOCUMENT_INVALID") from exc
    qualification_id = _text(plan.get("qualification_id"), "Q6_IDENTITY_INVALID")
    expected_root = _SOURCE_ROOT_PREFIX / qualification_id
    if (
        not qualification_id.startswith("v31-source-qualification-")
        or reservation.get("qualification_id") != qualification_id
        or checkpoint.get("qualification_id") != qualification_id
        or completion.get("qualification_id") != qualification_id
        or checkpoint.get("status") != "SEALED"
        or checkpoint.get("revision") != 2
        or checkpoint.get("attempt_count") != 1
        or checkpoint.get("failure_binding") is not None
        or completion.get("source_qualification_plan_digest") != plan_digest
        or completion.get("source_qualification_reservation_digest")
        != reservation_digest
        or plan.get("venue") != "OKX"
        or plan.get("instrument_id") != OKX_QUALIFICATION_INSTRUMENT_ID
        or plan.get("method") != "GET"
    ):
        raise V31ExternalQualificationError("Q6_EVIDENCE_CROSS_BINDING_INVALID")
    record_values = value["information_event_records"]
    if (
        not isinstance(record_values, list)
        or not record_values
        or any(not isinstance(row, Mapping) for row in record_values)
    ):
        raise V31ExternalQualificationError(
            "Q6_INFORMATION_EVENT_RECORDS_INVALID"
        )
    records: list[dict[str, Any]] = []
    record_digests: list[str] = []
    information_event_digests: list[str] = []
    try:
        for row in record_values:
            record = dict(row)
            record_digests.append(
                verify_v31_source_qualification_information_event_record(
                    record, qualification_id=qualification_id
                )
            )
            information_event_digests.append(
                _digest(
                    record.get("information_event_digest"),
                    "Q6_INFORMATION_EVENT_RECORDS_INVALID",
                )
            )
            records.append(record)
    except (TypeError, ValueError, V31SourceQualificationError) as exc:
        raise V31ExternalQualificationError(
            "Q6_INFORMATION_EVENT_RECORDS_INVALID"
        ) from exc
    record_bindings = completion.get("information_event_bindings")
    if (
        completion.get("information_event_digests")
        != information_event_digests
        or not isinstance(record_bindings, list)
        or len(record_bindings) != len(records)
        or any(
            not isinstance(binding, Mapping)
            or binding.get("semantic_digest") != record_digest
            for binding, record_digest in zip(record_bindings, record_digests)
        )
    ):
        raise V31ExternalQualificationError(
            "Q6_INFORMATION_EVENT_BINDINGS_INVALID"
        )
    artifact_values = value["artifact_bindings"]
    if not isinstance(artifact_values, Mapping) or set(artifact_values) != set(
        _Q6_ARTIFACT_SPECS
    ):
        raise V31ExternalQualificationError("Q6_ARTIFACT_BINDINGS_INVALID")
    digests = {
        "plan": plan_digest,
        "reservation": reservation_digest,
        "checkpoint": checkpoint_digest,
        "completion": completion_digest,
    }
    artifacts: dict[str, dict[str, str]] = {}
    for name, (suffix, schema_id, digest_field) in _Q6_ARTIFACT_SPECS.items():
        artifacts[name] = _artifact_binding(
            artifact_values[name],
            expected_path=(expected_root / suffix).as_posix(),
            expected_schema_id=schema_id,
            expected_digest_field=digest_field,
            expected_semantic_digest=digests[name],
            code="Q6_ARTIFACT_BINDINGS_INVALID",
        )
    if (
        checkpoint.get("plan_binding")
        != {
            "relative_ref": _Q6_ARTIFACT_SPECS["plan"][0],
            "semantic_digest": plan_digest,
            "physical_sha256": artifacts["plan"]["physical_sha256"],
        }
        or checkpoint.get("reservation_binding")
        != {
            "relative_ref": _Q6_ARTIFACT_SPECS["reservation"][0],
            "semantic_digest": reservation_digest,
            "physical_sha256": artifacts["reservation"]["physical_sha256"],
        }
        or checkpoint.get("completion_binding")
        != {
            "relative_ref": _Q6_ARTIFACT_SPECS["completion"][0],
            "semantic_digest": completion_digest,
            "physical_sha256": artifacts["completion"]["physical_sha256"],
        }
    ):
        raise V31ExternalQualificationError("Q6_CHECKPOINT_BINDING_INVALID")
    return {
        "plan": plan,
        "reservation": reservation,
        "checkpoint": checkpoint,
        "completion": completion,
        "information_event_records": records,
        "artifact_bindings": artifacts,
    }


def _q7_evidence(
    value: Any, *, experiment_contract: Mapping[str, Any]
) -> dict[str, Any]:
    required = {
        "checkpoint",
        "transport_evidence",
        "authoring_packet",
        "agent_authoring_envelope",
        "compilation_receipt",
        "compilation_admission",
        "compiled_assembly_bundle",
        "experiment_subject",
        "terminal_assertions",
        "artifact_bindings",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise V31ExternalQualificationError("Q7_EVIDENCE_SCHEMA_INVALID")
    checkpoint = dict(value["checkpoint"])
    evidence = dict(value["transport_evidence"])
    packet = dict(value["authoring_packet"])
    envelope = dict(value["agent_authoring_envelope"])
    compilation = dict(value["compilation_receipt"])
    admission = dict(value["compilation_admission"])
    assembly_bundle = dict(value["compiled_assembly_bundle"])
    subject = dict(value["experiment_subject"])
    try:
        checkpoint_digest = verify_self_digest(checkpoint, "checkpoint_digest")
        evidence_digest = validate_v31_transport_evidence(evidence)
        packet_digest = validate_v31_proposal_authoring_packet(packet)
        envelope_digest = validate_v31_agent_open_analysis_envelope(
            envelope, authoring_packet=packet
        )
        compilation_digest = validate_v31_authoring_compilation_receipt(
            compilation,
            authoring_packet=packet,
            authoring_envelope=envelope,
        )
        admission_digest = validate_v31_authoring_compilation_admission(admission)
        assembly_bundle_digest = verify_self_digest(
            assembly_bundle, COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD
        )
        subject_digest = verify_minimal_experiment_contract(subject)
        contract_digest = verify_minimal_experiment_contract(experiment_contract)
    except (
        TypeError,
        ValueError,
        V31AgentTransportError,
        V31CycleAuthoringError,
    ) as exc:
        raise V31ExternalQualificationError("Q7_EVIDENCE_DOCUMENT_INVALID") from exc
    run_id = _text(experiment_contract.get("run_id"), "Q7_RUN_ID_INVALID")
    authority = packet.get("authority_context")
    assertions = value["terminal_assertions"]
    expected_assertions = {
        "authoring_purpose": "TRANSPORT_QUALIFICATION_ONLY",
        "active_authority_binding": None,
        "experiment_start_authorized": False,
        "qualification_evidence_is_start_authority": False,
        "subject_run_id_matches": True,
        "postseal_selection_consumed": True,
        "source_qualification_completion_digest": packet[
            "source_qualification_completion_binding"
        ]["semantic_digest"],
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    if (
        subject != dict(experiment_contract)
        or subject_digest != contract_digest
        or not isinstance(authority, Mapping)
        or packet.get("run_id") != run_id
        or packet.get("cycle_index") != 1
        or packet.get("authoring_purpose") != "TRANSPORT_QUALIFICATION_ONLY"
        or packet.get("cycle_source_admission_binding") is not None
        or packet.get("qualification_evidence_is_start_authority") is not False
        or authority.get("active_authority_binding") is not None
        or authority.get("experiment_start_authorized") is not False
        or authority.get("experiment_subject_binding", {}).get(
            "semantic_digest"
        )
        != subject_digest
        or checkpoint.get("schema_id")
        != "theory_paper_v31_agent_transport_checkpoint"
        or checkpoint.get("schema_version") != "1.0.0"
        or checkpoint.get("run_id") != run_id
        or checkpoint.get("cycle_index") != 1
        or checkpoint.get("status") != "COMPLETED"
        or checkpoint.get("resume_allowed") is not False
        or checkpoint.get("failure_binding") is not None
        or evidence.get("run_id") != run_id
        or evidence.get("cycle_index") != 1
        or evidence.get("agent_id") != V31_AGENT_ID
        or evidence.get("evidence_level") != V31_TRANSPORT_EVIDENCE_LEVEL
        or evidence.get("proposal_payload_digest") != envelope_digest
        or admission.get("run_id") != run_id
        or admission.get("cycle_index") != 1
        or admission.get("compiler_id") != compilation.get("compiler_id")
        or admission.get("deterministic_replay_passed") is not True
        or admission.get("selection_unblocked") is not True
        or admission.get("selection_performed") is not False
        or admission.get("authoring_packet_binding", {}).get(
            "semantic_digest"
        )
        != packet_digest
        or admission.get("compilation_receipt_binding", {}).get(
            "semantic_digest"
        )
        != compilation_digest
        or admission.get("compiled_assembly_bundle_binding", {}).get(
            "semantic_digest"
        )
        != assembly_bundle_digest
        or assembly_bundle.get("schema_id")
        != COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID
        or assembly_bundle.get("schema_version") != "1.0.0"
        or assembly_bundle.get("run_id") != run_id
        or assembly_bundle.get("cycle_index") != 1
        or assembly_bundle.get("authoring_packet_digest") != packet_digest
        or assembly_bundle.get("agent_authoring_envelope_digest")
        != envelope_digest
        or assembly_bundle.get("compiler_id") != compilation.get("compiler_id")
        or assembly_bundle.get("inputs_receipt_digest")
        != compilation.get("inputs_receipt_digest")
        or assembly_bundle.get("agent_proposal_digest")
        != compilation.get("agent_proposal_digest")
        or assembly_bundle.get("action_evaluation_digest")
        != compilation.get("action_evaluation_digest")
        or assembly_bundle.get("preselection_digest")
        != compilation.get("preselection_digest")
        or assembly_bundle.get("deterministic_replay_required") is not True
        or assembly_bundle.get("selection_fields_admitted") is not False
        or assembly_bundle.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or assembly_bundle.get("executable") is not False
        or compilation.get("authoring_packet_digest") != packet_digest
        or compilation.get("agent_authoring_envelope_digest") != envelope_digest
        or compilation.get("inputs_receipt_digest")
        != admission.get("inputs_receipt_binding", {}).get("semantic_digest")
        or compilation.get("agent_proposal_digest")
        != admission.get("agent_proposal_binding", {}).get("semantic_digest")
        or compilation.get("action_evaluation_digest")
        != admission.get("action_evaluation_binding", {}).get("semantic_digest")
        or compilation.get("preselection_digest")
        != admission.get("preselection_binding", {}).get("semantic_digest")
        or assertions != expected_assertions
    ):
        raise V31ExternalQualificationError("Q7_EVIDENCE_CROSS_BINDING_INVALID")
    stage_states = checkpoint.get("stage_states")
    evidence_stages = evidence.get("stages")
    if (
        not isinstance(stage_states, Mapping)
        or set(stage_states) != {"PROPOSAL", "SELECTION"}
        or not isinstance(evidence_stages, Mapping)
        or set(evidence_stages) != {"PROPOSAL", "SELECTION"}
        or any(
            not isinstance(stage_states[stage], Mapping)
            or stage_states[stage].get("status") != "CONSUMED"
            or any(
                evidence_stages[stage].get(f"{kind}_binding")
                != stage_states[stage].get(f"{kind}_binding")
                for kind in ("attempt", "request", "claim", "delivery", "consume")
            )
            for stage in ("PROPOSAL", "SELECTION")
        )
        or any(
            admission.get(f"proposal_{kind}_binding")
            != stage_states["PROPOSAL"].get(f"{kind}_binding")
            for kind in ("attempt", "request", "claim", "delivery", "consume")
        )
    ):
        raise V31ExternalQualificationError("Q7_CHECKPOINT_STAGE_INVALID")

    artifact_values = value["artifact_bindings"]
    if not isinstance(artifact_values, Mapping) or set(artifact_values) != set(
        _Q7_ARTIFACT_SPECS
    ):
        raise V31ExternalQualificationError("Q7_ARTIFACT_BINDINGS_INVALID")
    checkpoint_artifact = _artifact_binding(
        artifact_values["checkpoint"],
        expected_path=None,
        expected_schema_id=_Q7_ARTIFACT_SPECS["checkpoint"][1],
        expected_digest_field=_Q7_ARTIFACT_SPECS["checkpoint"][2],
        expected_semantic_digest=checkpoint_digest,
        code="Q7_ARTIFACT_BINDINGS_INVALID",
    )
    checkpoint_suffix = PurePosixPath(_Q7_ARTIFACT_SPECS["checkpoint"][0])
    checkpoint_path = PurePosixPath(checkpoint_artifact["path"])
    if (
        len(checkpoint_path.parts) <= len(checkpoint_suffix.parts)
        or checkpoint_path.parts[-len(checkpoint_suffix.parts) :]
        != checkpoint_suffix.parts
    ):
        raise V31ExternalQualificationError("Q7_ARTIFACT_ROOT_INVALID")
    root = PurePosixPath(
        *checkpoint_path.parts[: -len(checkpoint_suffix.parts)]
    )
    evidence_suffix = f"cycles/0001/transport-evidence/{evidence_digest}.json"
    expected_paths = {
        "checkpoint": (root / checkpoint_suffix).as_posix(),
        "transport_evidence": (root / evidence_suffix).as_posix(),
        "authoring_packet": (
            root / admission["authoring_packet_binding"]["relative_ref"]
        ).as_posix(),
        "compilation_receipt": (
            root / admission["compilation_receipt_binding"]["relative_ref"]
        ).as_posix(),
        "compilation_admission": (
            root / _Q7_ARTIFACT_SPECS["compilation_admission"][0]
        ).as_posix(),
        "compiled_assembly_bundle": (
            root / admission["compiled_assembly_bundle_binding"]["relative_ref"]
        ).as_posix(),
        "experiment_subject": (
            root / authority["experiment_subject_binding"]["relative_ref"]
        ).as_posix(),
    }
    semantic_digests = {
        "checkpoint": checkpoint_digest,
        "transport_evidence": evidence_digest,
        "authoring_packet": packet_digest,
        "compilation_receipt": compilation_digest,
        "compilation_admission": admission_digest,
        "compiled_assembly_bundle": assembly_bundle_digest,
        "experiment_subject": subject_digest,
    }
    artifacts = {
        name: _artifact_binding(
            artifact_values[name],
            expected_path=expected_paths[name],
            expected_schema_id=_Q7_ARTIFACT_SPECS[name][1],
            expected_digest_field=_Q7_ARTIFACT_SPECS[name][2],
            expected_semantic_digest=semantic_digests[name],
            code="Q7_ARTIFACT_BINDINGS_INVALID",
        )
        for name in _Q7_ARTIFACT_SPECS
    }

    def matches_internal(name: str, binding: Mapping[str, Any]) -> bool:
        return artifacts[name] == {
            "path": (root / binding["relative_ref"]).as_posix(),
            "schema_id": binding["schema_id"],
            "digest_field": binding["digest_field"],
            "semantic_digest": binding["semantic_digest"],
            "physical_sha256": binding["physical_sha256"],
        }

    if (
        checkpoint["transport_evidence_binding"]
        != {
            "cycle_index": 1,
            "relative_ref": evidence_suffix,
            "semantic_digest": evidence_digest,
            "physical_sha256": artifacts["transport_evidence"]["physical_sha256"],
        }
        or not matches_internal(
            "authoring_packet", admission["authoring_packet_binding"]
        )
        or not matches_internal(
            "compilation_receipt", admission["compilation_receipt_binding"]
        )
        or not matches_internal(
            "compiled_assembly_bundle",
            admission["compiled_assembly_bundle_binding"],
        )
        or not matches_internal(
            "experiment_subject", authority["experiment_subject_binding"]
        )
    ):
        raise V31ExternalQualificationError("Q7_ARTIFACT_CROSS_BINDING_INVALID")
    return {
        "checkpoint": checkpoint,
        "transport_evidence": evidence,
        "authoring_packet": packet,
        "agent_authoring_envelope": envelope,
        "compilation_receipt": compilation,
        "compilation_admission": admission,
        "compiled_assembly_bundle": assembly_bundle,
        "experiment_subject": subject,
        "terminal_assertions": expected_assertions,
        "artifact_bindings": artifacts,
    }


def _checks(gate_id: str, evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    if gate_id == "Q6":
        plan = evidence["plan"]
        completion = evidence["completion"]
        projections = {
            "Q6_FIXED_PUBLIC_SOURCE_SCOPE": {
                "venue": plan["venue"],
                "instrument_id": plan["instrument_id"],
                "method": plan["method"],
                "base_url": plan["base_url"],
            },
            "Q6_SINGLE_DURABLE_ATTEMPT": {
                "reservation_digest": evidence["reservation"][
                    "source_qualification_reservation_digest"
                ],
                "attempt_count": completion["attempt_count"],
                "retry_count": completion["retry_count"],
            },
            "Q6_REQUIRED_REQUESTS_AND_RAW_READBACK": {
                "required_request_ids": completion["required_request_ids"],
                "required_requests_complete": completion[
                    "required_requests_complete"
                ],
                "raw_bytes_read_back_and_verified": completion[
                    "raw_bytes_read_back_and_verified"
                ],
                "raw_binding_digest": canonical_digest(completion["raw_bindings"]),
            },
            "Q6_PIT_UNKNOWN_PRESERVED": {
                "decision_at": completion["decision_at"],
                "pit_dataset_digest": completion["pit_dataset_digest"],
                "missing_is_zero": completion["missing_is_zero"],
                "unknown_count": completion["unknown_count"],
            },
            "Q6_SEALED_NO_EXECUTION_AUTHORITY": {
                "checkpoint_digest": evidence["checkpoint"][
                    "source_qualification_checkpoint_digest"
                ],
                "completion_digest": completion[
                    "source_qualification_completion_digest"
                ],
                "information_event_record_digests": [
                    row[
                        "source_qualification_information_event_record_digest"
                    ]
                    for row in evidence["information_event_records"]
                ],
                "retired_execution_authority_absent": True,
                "external_execution_authority": completion[
                    "external_execution_authority"
                ],
                "executable": completion["executable"],
            },
        }
    else:
        transport = evidence["transport_evidence"]
        admission = evidence["compilation_admission"]
        assertions = evidence["terminal_assertions"]
        projections = {
            "Q7_OPEN_ANALYSIS_TWO_STAGE_ORDER": {
                "agent_id": transport["agent_id"],
                "stage_order": transport["stage_order"],
                "chronology": transport["chronology"],
            },
            "Q7_ONE_DURABLE_ATTEMPT_PER_STAGE": {
                "attempt_limit_per_stage": transport["attempt_limit_per_stage"],
                "stage_attempt_counts": {
                    stage: transport["stages"][stage]["attempt_count"]
                    for stage in transport["stage_order"]
                },
            },
            "Q7_COMPILATION_REPLAY_ADMITTED": {
                "compiler_id": admission["compiler_id"],
                "compilation_admission_digest": admission[
                    AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD
                ],
                "compiled_assembly_bundle_digest": evidence[
                    "compiled_assembly_bundle"
                ][COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD],
                "deterministic_replay_passed": admission[
                    "deterministic_replay_passed"
                ],
                "selection_unblocked": admission["selection_unblocked"],
                "selection_performed": admission["selection_performed"],
            },
            "Q7_POSTSEAL_SELECTION_CONSUMED": {
                "proposal_payload_digest": transport["proposal_payload_digest"],
                "selection_payload_digest": transport["selection_payload_digest"],
                "all_deliveries_consumed": transport["all_deliveries_consumed"],
                "postseal_selection_consumed": assertions[
                    "postseal_selection_consumed"
                ],
            },
            "Q7_EXACT_SUBJECT_NO_START_OR_EXECUTION_AUTHORITY": {
                "run_id": transport["run_id"],
                "authoring_purpose": assertions["authoring_purpose"],
                "active_authority_binding": assertions[
                    "active_authority_binding"
                ],
                "experiment_start_authorized": assertions[
                    "experiment_start_authorized"
                ],
                "subject_run_id_matches": assertions["subject_run_id_matches"],
                "external_execution_authority": assertions[
                    "external_execution_authority"
                ],
                "executable": assertions["executable"],
            },
        }
    paths = [row["path"] for row in evidence["artifact_bindings"].values()]
    return [
        {
            "check_id": check_id,
            "status": "PASS",
            "verified_projection_digest": canonical_digest(projection),
            "evidence_paths": paths,
        }
        for check_id, projection in projections.items()
    ]


def _build_external_receipt(
    *,
    gate_id: str,
    evaluated_at: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    qualification_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if gate_id not in EXTERNAL_TYPED_QUALIFICATION_GATE_IDS:
        raise V31ExternalQualificationError("EXTERNAL_QUALIFICATION_GATE_INVALID")
    contract_digest, subject_digest = _manifest_context(
        experiment_contract=experiment_contract, manifest=manifest
    )
    evidence = (
        _q6_evidence(qualification_evidence)
        if gate_id == "Q6"
        else _q7_evidence(
            qualification_evidence, experiment_contract=experiment_contract
        )
    )
    evaluated = _timestamp(evaluated_at, "EXTERNAL_QUALIFICATION_TIME_INVALID")
    completed_at = (
        evidence["completion"]["completed_at"]
        if gate_id == "Q6"
        else evidence["transport_evidence"]["completed_at"]
    )
    if evaluated < _timestamp(
        completed_at, "EXTERNAL_QUALIFICATION_COMPLETION_TIME_INVALID"
    ):
        raise V31ExternalQualificationError(
            "EXTERNAL_QUALIFICATION_PRECEDES_EVIDENCE"
        )
    if gate_id == "Q6" and evidence["plan"].get(
        "theory_sha256"
    ) != experiment_contract.get("approved_theory_sha256"):
        raise V31ExternalQualificationError("Q6_THEORY_BINDING_INVALID")
    limitations = [
        (
            "Q6 proves one replayable public-source qualification capture only; it does not prove future provider availability."
            if gate_id == "Q6"
            else "Q7 proves one replayable open-analysis, deterministic-compilation, and postseal-selection qualification chain only; it does not prove future Agent availability or predictive validity."
        ),
        "This receipt creates no run, trading permission, account access, or execution authority.",
    ]
    document = {
        "schema_id": EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID,
        "schema_version": EXTERNAL_TYPED_QUALIFICATION_SCHEMA_VERSION,
        "gate_id": gate_id,
        "evaluated_at": evaluated_at,
        "verdict": "PASS",
        "experiment_contract_digest": contract_digest,
        "manifest_qualification_subject_digest": subject_digest,
        "evidence_bindings": _implementation_evidence(
            gate_id=gate_id, manifest=manifest
        ),
        "qualification_evidence": evidence,
        "checks": _checks(gate_id, evidence),
        "limitations": limitations,
        "authority_boundary": experiment_contract["authority_boundary"],
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, "qualification_receipt_digest")


def build_q6_source_qualification_receipt(
    *,
    evaluated_at: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    qualification_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return _build_external_receipt(
        gate_id="Q6",
        evaluated_at=evaluated_at,
        experiment_contract=experiment_contract,
        manifest=manifest,
        qualification_evidence=qualification_evidence,
    )


def build_q7_agent_transport_receipt(
    *,
    evaluated_at: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    qualification_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return _build_external_receipt(
        gate_id="Q7",
        evaluated_at=evaluated_at,
        experiment_contract=experiment_contract,
        manifest=manifest,
        qualification_evidence=qualification_evidence,
    )


def verify_external_typed_qualification_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_gate_id: str,
    experiment_contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> str:
    if (
        not isinstance(receipt, Mapping)
        or expected_gate_id not in EXTERNAL_TYPED_QUALIFICATION_GATE_IDS
    ):
        raise V31ExternalQualificationError(
            "EXTERNAL_QUALIFICATION_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(receipt, "qualification_receipt_digest")
        if (
            receipt.get("schema_id") != EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID
            or receipt.get("schema_version")
            != EXTERNAL_TYPED_QUALIFICATION_SCHEMA_VERSION
            or receipt.get("gate_id") != expected_gate_id
            or receipt.get("verdict") != "PASS"
        ):
            raise V31ExternalQualificationError(
                "EXTERNAL_QUALIFICATION_RECEIPT_INVALID"
            )
        rebuilt = _build_external_receipt(
            gate_id=expected_gate_id,
            evaluated_at=receipt["evaluated_at"],
            experiment_contract=experiment_contract,
            manifest=manifest,
            qualification_evidence=receipt["qualification_evidence"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31ExternalQualificationError):
            raise
        raise V31ExternalQualificationError(
            "EXTERNAL_QUALIFICATION_RECEIPT_INVALID"
        ) from exc
    if rebuilt != dict(receipt) or supplied != rebuilt["qualification_receipt_digest"]:
        raise V31ExternalQualificationError(
            "EXTERNAL_QUALIFICATION_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def required_external_gate_evidence_paths(gate_id: str) -> tuple[str, ...]:
    if gate_id == "Q6":
        return tuple(sorted(_Q6_IMPLEMENTATION_PATHS))
    if gate_id == "Q7":
        return tuple(sorted(_Q7_IMPLEMENTATION_PATHS))
    raise V31ExternalQualificationError("EXTERNAL_QUALIFICATION_GATE_INVALID")


__all__ = [
    "EXTERNAL_TYPED_QUALIFICATION_GATE_IDS",
    "EXTERNAL_TYPED_QUALIFICATION_SCHEMA_ID",
    "V31ExternalQualificationError",
    "build_q6_source_qualification_receipt",
    "build_q7_agent_transport_receipt",
    "required_external_gate_evidence_paths",
    "verify_external_typed_qualification_receipt",
]
