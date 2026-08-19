"""Write-once persistence and replay for executed successor probe evidence.

This store owns only ``qualification-probe-v2`` under an explicit output root.
It never creates an experiment checkpoint, run, automation, network request,
account connection, or executable action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from ..application.v31_successor_probe_runner_v2 import (
    run_successor_qualification_probes_v2,
)
from ..domain.governance.v31_successor_probe_evidence_v2 import (
    PERSISTED_PROBE_RECEIPT_DIGEST_FIELD,
    PROBE_CASE_DIGEST_FIELD,
    PROBE_FAMILY_DIGEST_FIELD,
    RUNTIME_CLOSURE_DIGEST_FIELD,
    build_persisted_probe_receipt_v2,
    verify_executed_probe_case_receipt_v2,
    verify_executed_probe_family_evidence_v2,
    verify_persisted_probe_receipt_v2,
    verify_probe_runtime_closure_evidence_v2,
)
from ..domain.governance.v31_successor_qualification_v2 import (
    RAW_FIRST_FAILURE_CASES,
    RAW_FIRST_PROBE_DIGEST_FIELD,
    SUPERVISOR_GATE_CASES,
    SUPERVISOR_PROBE_DIGEST_FIELD,
    verify_raw_first_failure_probe_v2,
    verify_supervisor_gate_probe_v2,
)
from ..domain.v31_outcome_capture_v2 import verify_outcome_clock_policy
from .v31_research_store import LocalV31ResearchStore


class V31SuccessorProbeStoreV2Error(ValueError):
    """Executed probe evidence could not be persisted or replayed exactly."""


PROBE_ROOT = "qualification-probe-v2"
PERSISTED_RECEIPT_REF = f"{PROBE_ROOT}/persisted-receipt.json"
PROBE_STORE_MODULE_PATH = (
    "trade_system/theory_paper_v2/infrastructure/v31_successor_probe_store_v2.py"
)


def _output_root(value: Path) -> Path:
    supplied = Path(value)
    if supplied.exists() and supplied.is_symlink():
        raise V31SuccessorProbeStoreV2Error("V31_PROBE_OUTPUT_ROOT_SYMLINK")
    try:
        supplied.mkdir(parents=True, exist_ok=True)
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V31SuccessorProbeStoreV2Error(
            "V31_PROBE_OUTPUT_ROOT_INVALID"
        ) from exc
    if not root.is_dir() or root.is_symlink():
        raise V31SuccessorProbeStoreV2Error("V31_PROBE_OUTPUT_ROOT_INVALID")
    return root


def _enriched_binding(
    *,
    store: LocalV31ResearchStore,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    binding = store.write_document(
        relative_ref=relative_ref,
        document=document,
        digest_field=digest_field,
    )
    return {
        "relative_ref": str(binding["relative_ref"]),
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }


def _replay_binding(
    *, store: LocalV31ResearchStore, binding: Mapping[str, Any]
) -> Mapping[str, Any]:
    try:
        document = store.read_document(
            relative_ref=str(binding["relative_ref"]),
            digest_field=str(binding["digest_field"]),
            expected_semantic_digest=str(binding["semantic_digest"]),
        )
        physical = store.artifact_binding(
            relative_ref=str(binding["relative_ref"]),
            digest_field=str(binding["digest_field"]),
            expected_semantic_digest=str(binding["semantic_digest"]),
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V31SuccessorProbeStoreV2Error(
            "V31_PROBE_ARTIFACT_REPLAY_INVALID"
        ) from exc
    actual = {
        "relative_ref": str(physical["relative_ref"]),
        "schema_id": str(document.get("schema_id")),
        "digest_field": str(binding["digest_field"]),
        "semantic_digest": str(physical["semantic_digest"]),
        "physical_sha256": str(physical["physical_sha256"]),
    }
    if actual != dict(binding):
        raise V31SuccessorProbeStoreV2Error(
            "V31_PROBE_ARTIFACT_PHYSICAL_DRIFT"
        )
    return document


def _validated_result(result: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise V31SuccessorProbeStoreV2Error("V31_PROBE_RESULT_INVALID")
    try:
        clock_policy = dict(result["clock_policy"])
        clock_digest = verify_outcome_clock_policy(clock_policy)
        runtime = dict(result["runtime_closure_evidence"])
        verify_probe_runtime_closure_evidence_v2(runtime)
        raw_receipts = [dict(row) for row in result["raw_first_case_receipts"]]
        supervisor_receipts = [
            dict(row) for row in result["supervisor_case_receipts"]
        ]
        for receipt in (*raw_receipts, *supervisor_receipts):
            verify_executed_probe_case_receipt_v2(receipt)
        raw_probe = dict(result["raw_first_probe"])
        supervisor_probe = dict(result["supervisor_probe"])
        verify_raw_first_failure_probe_v2(raw_probe)
        verify_supervisor_gate_probe_v2(supervisor_probe)
        raw_family = dict(result["raw_first_family_evidence"])
        supervisor_family = dict(result["supervisor_family_evidence"])
        verify_executed_probe_family_evidence_v2(
            raw_family,
            case_receipts=raw_receipts,
            aggregate_probe=raw_probe,
        )
        verify_executed_probe_family_evidence_v2(
            supervisor_family,
            case_receipts=supervisor_receipts,
            aggregate_probe=supervisor_probe,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SuccessorProbeStoreV2Error("V31_PROBE_RESULT_INVALID") from exc
    if (
        tuple(sorted(row["case_id"] for row in raw_receipts))
        != RAW_FIRST_FAILURE_CASES
        or tuple(sorted(row["case_id"] for row in supervisor_receipts))
        != SUPERVISOR_GATE_CASES
        or result.get("network_access_performed") is not False
        or result.get("real_run_created") is not False
        or result.get("automation_created") is not False
        or result.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or result.get("executable") is not False
        or runtime.get("runtime_closure_digest")
        != raw_family.get("runtime_closure_digest")
        or runtime.get("runtime_closure_digest")
        != supervisor_family.get("runtime_closure_digest")
        or clock_digest != raw_probe.get("clock_policy_digest")
        or clock_digest != raw_family.get("clock_policy_digest")
        or clock_digest != supervisor_family.get("clock_policy_digest")
        or result.get("executed_at") != runtime.get("executed_at")
    ):
        raise V31SuccessorProbeStoreV2Error(
            "V31_PROBE_RESULT_CROSS_BINDING_INVALID"
        )
    return {
        "executed_at": str(result["executed_at"]),
        "clock_policy": clock_policy,
        "clock_policy_digest": clock_digest,
        "runtime_closure_evidence": runtime,
        "raw_first_case_receipts": raw_receipts,
        "supervisor_case_receipts": supervisor_receipts,
        "raw_first_probe": raw_probe,
        "supervisor_probe": supervisor_probe,
        "raw_first_family_evidence": raw_family,
        "supervisor_family_evidence": supervisor_family,
    }


def persist_successor_qualification_probes_v2(
    *, output_root: Path, result: Mapping[str, Any]
) -> dict[str, Any]:
    """Persist all case receipts and return a physically replayed manifest."""

    root = _output_root(output_root)
    store = LocalV31ResearchStore(root)
    validated = _validated_result(result)
    runtime_binding = _enriched_binding(
        store=store,
        relative_ref=f"{PROBE_ROOT}/runtime-closure.json",
        document=validated["runtime_closure_evidence"],
        digest_field=RUNTIME_CLOSURE_DIGEST_FIELD,
    )
    clock_binding = _enriched_binding(
        store=store,
        relative_ref=f"{PROBE_ROOT}/clock-policy.json",
        document=validated["clock_policy"],
        digest_field="clock_policy_digest",
    )
    raw_case_bindings: dict[str, dict[str, str]] = {}
    for receipt in validated["raw_first_case_receipts"]:
        case_id = str(receipt["case_id"])
        raw_case_bindings[case_id] = _enriched_binding(
            store=store,
            relative_ref=(
                f"{PROBE_ROOT}/cases/raw-first/"
                f"{case_id.lower().replace('_', '-')}.json"
            ),
            document=receipt,
            digest_field=PROBE_CASE_DIGEST_FIELD,
        )
    supervisor_case_bindings: dict[str, dict[str, str]] = {}
    for receipt in validated["supervisor_case_receipts"]:
        case_id = str(receipt["case_id"])
        supervisor_case_bindings[case_id] = _enriched_binding(
            store=store,
            relative_ref=(
                f"{PROBE_ROOT}/cases/supervisor/"
                f"{case_id.lower().replace('_', '-')}.json"
            ),
            document=receipt,
            digest_field=PROBE_CASE_DIGEST_FIELD,
        )
    raw_probe_binding = _enriched_binding(
        store=store,
        relative_ref=f"{PROBE_ROOT}/aggregate/raw-first-probe.json",
        document=validated["raw_first_probe"],
        digest_field=RAW_FIRST_PROBE_DIGEST_FIELD,
    )
    supervisor_probe_binding = _enriched_binding(
        store=store,
        relative_ref=f"{PROBE_ROOT}/aggregate/supervisor-probe.json",
        document=validated["supervisor_probe"],
        digest_field=SUPERVISOR_PROBE_DIGEST_FIELD,
    )
    raw_family_binding = _enriched_binding(
        store=store,
        relative_ref=f"{PROBE_ROOT}/families/raw-first-evidence.json",
        document=validated["raw_first_family_evidence"],
        digest_field=PROBE_FAMILY_DIGEST_FIELD,
    )
    supervisor_family_binding = _enriched_binding(
        store=store,
        relative_ref=f"{PROBE_ROOT}/families/supervisor-evidence.json",
        document=validated["supervisor_family_evidence"],
        digest_field=PROBE_FAMILY_DIGEST_FIELD,
    )
    receipt = build_persisted_probe_receipt_v2(
        executed_at=validated["executed_at"],
        runtime_closure_digest=validated["runtime_closure_evidence"][
            "runtime_closure_digest"
        ],
        clock_policy_digest=validated["clock_policy_digest"],
        runtime_closure_binding=runtime_binding,
        clock_policy_binding=clock_binding,
        raw_first_case_bindings=raw_case_bindings,
        supervisor_case_bindings=supervisor_case_bindings,
        raw_first_probe_binding=raw_probe_binding,
        supervisor_probe_binding=supervisor_probe_binding,
        raw_first_family_binding=raw_family_binding,
        supervisor_family_binding=supervisor_family_binding,
    )
    _enriched_binding(
        store=store,
        relative_ref=PERSISTED_RECEIPT_REF,
        document=receipt,
        digest_field=PERSISTED_PROBE_RECEIPT_DIGEST_FIELD,
    )
    return load_persisted_successor_qualification_probes_v2(output_root=root)


def load_persisted_successor_qualification_probes_v2(
    *, output_root: Path
) -> dict[str, Any]:
    """Replay every semantic and physical binding from the persisted receipt."""

    root = _output_root(output_root)
    store = LocalV31ResearchStore(root)
    try:
        receipt = store.read_document(
            relative_ref=PERSISTED_RECEIPT_REF,
            digest_field=PERSISTED_PROBE_RECEIPT_DIGEST_FIELD,
        )
        verify_persisted_probe_receipt_v2(receipt)
    except (OSError, TypeError, ValueError) as exc:
        raise V31SuccessorProbeStoreV2Error(
            "V31_PROBE_PERSISTED_RECEIPT_INVALID"
        ) from exc
    bindings = receipt["artifact_bindings"]
    runtime = _replay_binding(store=store, binding=bindings["runtime_closure"])
    clock_policy = _replay_binding(store=store, binding=bindings["clock_policy"])
    raw_receipts = [
        _replay_binding(store=store, binding=bindings["raw_first_cases"][case])
        for case in RAW_FIRST_FAILURE_CASES
    ]
    supervisor_receipts = [
        _replay_binding(store=store, binding=bindings["supervisor_cases"][case])
        for case in SUPERVISOR_GATE_CASES
    ]
    raw_probe = _replay_binding(store=store, binding=bindings["raw_first_probe"])
    supervisor_probe = _replay_binding(
        store=store, binding=bindings["supervisor_probe"]
    )
    raw_family = _replay_binding(store=store, binding=bindings["raw_first_family"])
    supervisor_family = _replay_binding(
        store=store, binding=bindings["supervisor_family"]
    )
    replayed = _validated_result(
        {
            "executed_at": receipt["executed_at"],
            "clock_policy": clock_policy,
            "runtime_closure_evidence": runtime,
            "raw_first_case_receipts": raw_receipts,
            "supervisor_case_receipts": supervisor_receipts,
            "raw_first_probe": raw_probe,
            "supervisor_probe": supervisor_probe,
            "raw_first_family_evidence": raw_family,
            "supervisor_family_evidence": supervisor_family,
            "network_access_performed": False,
            "real_run_created": False,
            "automation_created": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }
    )
    if (
        replayed["runtime_closure_evidence"]["runtime_closure_digest"]
        != receipt["runtime_closure_digest"]
        or replayed["clock_policy_digest"] != receipt["clock_policy_digest"]
    ):
        raise V31SuccessorProbeStoreV2Error(
            "V31_PROBE_PERSISTED_RECEIPT_CROSS_BINDING_INVALID"
        )
    return {
        "receipt": receipt,
        **replayed,
        "output_root": str(root),
        "network_access_performed": False,
        "real_run_created": False,
        "automation_created": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


def execute_and_persist_successor_qualification_probes_v2(
    *,
    project_root: Path,
    output_root: Path,
    executed_at: str,
    production_root_paths: Sequence[str],
    trace_paths: Sequence[str],
    runtime_closure_bindings: Mapping[str, str],
    clock_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """CLI-like composition for a controller-owned temporary evidence root."""

    result = run_successor_qualification_probes_v2(
        project_root=project_root,
        executed_at=executed_at,
        production_root_paths=production_root_paths,
        trace_paths=trace_paths,
        runtime_closure_bindings=runtime_closure_bindings,
        clock_policy=clock_policy,
    )
    return persist_successor_qualification_probes_v2(
        output_root=output_root, result=result
    )


__all__ = [
    "PERSISTED_RECEIPT_REF",
    "PROBE_ROOT",
    "PROBE_STORE_MODULE_PATH",
    "V31SuccessorProbeStoreV2Error",
    "execute_and_persist_successor_qualification_probes_v2",
    "load_persisted_successor_qualification_probes_v2",
    "persist_successor_qualification_probes_v2",
]
