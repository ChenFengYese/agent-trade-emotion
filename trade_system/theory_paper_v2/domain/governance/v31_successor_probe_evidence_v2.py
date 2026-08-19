"""Executed evidence contracts for successor V3.1 qualification probes.

The aggregate successor qualification document records that six raw-first and
four supervisor cases passed.  This module binds that aggregate statement to
case-level observations produced by the isolated failure-injection runner.

These documents are local research evidence only.  They do not authorize a
real run, network access, an account, an order, or any executable action.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping, Sequence

from ..contracts.canonical import canonical_digest, self_digest, verify_self_digest
from .v31_successor_qualification_v2 import (
    RAW_FIRST_FAILURE_CASES,
    RAW_FIRST_PROBE_DIGEST_FIELD,
    SUPERVISOR_GATE_CASES,
    SUPERVISOR_PROBE_DIGEST_FIELD,
    verify_raw_first_failure_probe_v2,
    verify_supervisor_gate_probe_v2,
)


class V31SuccessorProbeEvidenceV2Error(ValueError):
    """Executed qualification evidence was incomplete or non-reconstructible."""


PROBE_CASE_SCHEMA_ID = "theory_paper_v31_successor_executed_probe_case_v2"
PROBE_FAMILY_SCHEMA_ID = "theory_paper_v31_successor_executed_probe_family_v2"
RUNTIME_CLOSURE_SCHEMA_ID = "theory_paper_v31_successor_probe_runtime_closure_v2"
PERSISTED_PROBE_RECEIPT_SCHEMA_ID = (
    "theory_paper_v31_successor_persisted_probe_receipt_v2"
)
PROBE_EVIDENCE_SCHEMA_VERSION = "2.0.0"

PROBE_CASE_DIGEST_FIELD = "probe_case_receipt_digest"
PROBE_FAMILY_DIGEST_FIELD = "probe_family_evidence_digest"
RUNTIME_CLOSURE_DIGEST_FIELD = "runtime_closure_evidence_digest"
PERSISTED_PROBE_RECEIPT_DIGEST_FIELD = "persisted_probe_receipt_digest"

RAW_FIRST_FAMILY = "RAW_FIRST_OUTCOME"
SUPERVISOR_FAMILY = "EXPERIMENT_SUPERVISOR"

RAW_NETWORK_BOUNDARY = "LOCAL_INJECTED_PUBLIC_TRANSPORT_NO_NETWORK"
SUPERVISOR_NETWORK_BOUNDARY = "LOCAL_CONTROLLED_OWNER_PORTS_NO_NETWORK"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_BOUNDARY = {
    "qualification_scope": "LOCAL_FAILURE_INJECTION_ONLY",
    "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
    "external_execution_authority": "NONE_LOCAL_SIMULATION",
    "executable": False,
    "account_access": False,
    "paper_trading": False,
    "live_trading": False,
    "order_submission": False,
    "credential_use": False,
    "funds_access": False,
    "portfolio_mutation": False,
    "real_run_created": False,
    "automation_created": False,
}


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V31SuccessorProbeEvidenceV2Error(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31SuccessorProbeEvidenceV2Error(code)
    return value


def _time(value: Any, code: str) -> str:
    value = _text(value, code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SuccessorProbeEvidenceV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31SuccessorProbeEvidenceV2Error(code)
    normalized = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if normalized != value:
        raise V31SuccessorProbeEvidenceV2Error(code)
    return value


def _family_cases(family: str) -> tuple[str, ...]:
    if family == RAW_FIRST_FAMILY:
        return RAW_FIRST_FAILURE_CASES
    if family == SUPERVISOR_FAMILY:
        return SUPERVISOR_GATE_CASES
    raise V31SuccessorProbeEvidenceV2Error("V31_PROBE_FAMILY_INVALID")


def _module_bindings(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_MODULE_BINDINGS_INVALID"
        )
    rows: dict[str, str] = {}
    for path, digest in value.items():
        if (
            not isinstance(path, str)
            or not path.endswith(".py")
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or path in rows
        ):
            raise V31SuccessorProbeEvidenceV2Error(
                "V31_PROBE_MODULE_BINDINGS_INVALID"
            )
        rows[path] = _digest(digest, "V31_PROBE_MODULE_BINDINGS_INVALID")
    return dict(sorted(rows.items()))


def _observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_OBSERVATION_INVALID"
        )
    result = dict(value)
    try:
        canonical_digest(result)
    except (TypeError, ValueError) as exc:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_OBSERVATION_INVALID"
        ) from exc
    return result


def _artifact_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _ARTIFACT_BINDING_FIELDS:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_ARTIFACT_BINDING_INVALID"
        )
    relative_ref = _text(
        value.get("relative_ref"), "V31_PROBE_ARTIFACT_BINDING_INVALID"
    )
    if (
        relative_ref.startswith("/")
        or "\\" in relative_ref
        or any(part in {"", ".", ".."} for part in relative_ref.split("/"))
    ):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_ARTIFACT_BINDING_INVALID"
        )
    return {
        "relative_ref": relative_ref,
        "schema_id": _text(
            value.get("schema_id"), "V31_PROBE_ARTIFACT_BINDING_INVALID"
        ),
        "digest_field": _text(
            value.get("digest_field"), "V31_PROBE_ARTIFACT_BINDING_INVALID"
        ),
        "semantic_digest": _digest(
            value.get("semantic_digest"), "V31_PROBE_ARTIFACT_BINDING_INVALID"
        ),
        "physical_sha256": _digest(
            value.get("physical_sha256"), "V31_PROBE_ARTIFACT_BINDING_INVALID"
        ),
    }


def build_executed_probe_case_receipt_v2(
    *,
    probe_family: str,
    case_id: str,
    executed_at: str,
    runtime_closure_digest: str,
    tested_module_bindings: Mapping[str, str],
    clock_policy_digest: str,
    test_input_digest: str,
    observation: Mapping[str, Any],
    exception_code: str | None,
    network_boundary: str,
) -> dict[str, Any]:
    """Seal one observation after the runner has asserted its expected result.

    There is intentionally no ``status`` or ``case_results`` input.  PASS is
    emitted only by this executed-evidence path after a concrete observation is
    supplied and all bindings are reconstructible.
    """

    family = _text(probe_family, "V31_PROBE_FAMILY_INVALID")
    expected_cases = _family_cases(family)
    case = _text(case_id, "V31_PROBE_CASE_ID_INVALID")
    if case not in expected_cases:
        raise V31SuccessorProbeEvidenceV2Error("V31_PROBE_CASE_ID_INVALID")
    timestamp = _time(executed_at, "V31_PROBE_EXECUTED_AT_INVALID")
    modules = _module_bindings(tested_module_bindings)
    observed = _observation(observation)
    if exception_code is not None:
        exception = _text(exception_code, "V31_PROBE_EXCEPTION_CODE_INVALID")
    else:
        exception = None
    expected_boundary = (
        RAW_NETWORK_BOUNDARY
        if family == RAW_FIRST_FAMILY
        else SUPERVISOR_NETWORK_BOUNDARY
    )
    if network_boundary != expected_boundary:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_NETWORK_BOUNDARY_INVALID"
        )
    document = {
        "schema_id": PROBE_CASE_SCHEMA_ID,
        "schema_version": PROBE_EVIDENCE_SCHEMA_VERSION,
        "probe_family": family,
        "case_id": case,
        "executed_at": timestamp,
        "runtime_closure_digest": _digest(
            runtime_closure_digest, "V31_PROBE_RUNTIME_CLOSURE_DIGEST_INVALID"
        ),
        "tested_module_bindings": modules,
        "tested_module_bindings_digest": canonical_digest(modules),
        "clock_policy_digest": _digest(
            clock_policy_digest, "V31_PROBE_CLOCK_POLICY_DIGEST_INVALID"
        ),
        "test_input_digest": _digest(
            test_input_digest, "V31_PROBE_TEST_INPUT_DIGEST_INVALID"
        ),
        "observation": observed,
        "observation_digest": canonical_digest(observed),
        "exception_code": exception,
        "network_boundary": network_boundary,
        "result": "PASS_FROM_EXECUTED_OBSERVATION",
        "caller_supplied_pass_accepted": False,
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, PROBE_CASE_DIGEST_FIELD)


def verify_executed_probe_case_receipt_v2(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorProbeEvidenceV2Error("V31_PROBE_CASE_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, PROBE_CASE_DIGEST_FIELD)
        rebuilt = build_executed_probe_case_receipt_v2(
            probe_family=document["probe_family"],
            case_id=document["case_id"],
            executed_at=document["executed_at"],
            runtime_closure_digest=document["runtime_closure_digest"],
            tested_module_bindings=document["tested_module_bindings"],
            clock_policy_digest=document["clock_policy_digest"],
            test_input_digest=document["test_input_digest"],
            observation=document["observation"],
            exception_code=document["exception_code"],
            network_boundary=document["network_boundary"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorProbeEvidenceV2Error):
            raise
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_CASE_RECEIPT_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[PROBE_CASE_DIGEST_FIELD]:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_CASE_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_executed_probe_family_evidence_v2(
    *,
    probe_family: str,
    executed_at: str,
    runtime_closure_digest: str,
    clock_policy_digest: str,
    case_receipts: Sequence[Mapping[str, Any]],
    aggregate_probe: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind an aggregate six/four PASS document to exact executed receipts."""

    family = _text(probe_family, "V31_PROBE_FAMILY_INVALID")
    expected_cases = _family_cases(family)
    if isinstance(case_receipts, (str, bytes)):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_CASE_RECEIPTS_INVALID"
        )
    receipts = list(case_receipts)
    by_case: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts:
        verify_executed_probe_case_receipt_v2(receipt)
        case = str(receipt["case_id"])
        if (
            receipt.get("probe_family") != family
            or receipt.get("executed_at") != executed_at
            or receipt.get("runtime_closure_digest") != runtime_closure_digest
            or receipt.get("clock_policy_digest") != clock_policy_digest
            or case in by_case
        ):
            raise V31SuccessorProbeEvidenceV2Error(
                "V31_PROBE_CASE_RECEIPTS_INVALID"
            )
        by_case[case] = receipt
    if tuple(sorted(by_case)) != expected_cases:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_CASE_RECEIPTS_INCOMPLETE"
        )
    if family == RAW_FIRST_FAMILY:
        aggregate_digest = verify_raw_first_failure_probe_v2(aggregate_probe)
        aggregate_digest_field = RAW_FIRST_PROBE_DIGEST_FIELD
        if aggregate_probe.get("clock_policy_digest") != clock_policy_digest:
            raise V31SuccessorProbeEvidenceV2Error(
                "V31_PROBE_AGGREGATE_CROSS_BINDING_INVALID"
            )
    else:
        aggregate_digest = verify_supervisor_gate_probe_v2(aggregate_probe)
        aggregate_digest_field = SUPERVISOR_PROBE_DIGEST_FIELD
    if (
        aggregate_probe.get("tested_at") != executed_at
        or aggregate_probe.get("case_results")
        != {case: "PASS" for case in expected_cases}
    ):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_AGGREGATE_CROSS_BINDING_INVALID"
        )
    case_digests = {
        case: by_case[case][PROBE_CASE_DIGEST_FIELD] for case in expected_cases
    }
    document = {
        "schema_id": PROBE_FAMILY_SCHEMA_ID,
        "schema_version": PROBE_EVIDENCE_SCHEMA_VERSION,
        "probe_family": family,
        "executed_at": _time(executed_at, "V31_PROBE_EXECUTED_AT_INVALID"),
        "runtime_closure_digest": _digest(
            runtime_closure_digest, "V31_PROBE_RUNTIME_CLOSURE_DIGEST_INVALID"
        ),
        "clock_policy_digest": _digest(
            clock_policy_digest, "V31_PROBE_CLOCK_POLICY_DIGEST_INVALID"
        ),
        "case_receipt_digests": case_digests,
        "case_set_digest": canonical_digest(case_digests),
        "aggregate_probe_digest_field": aggregate_digest_field,
        "aggregate_probe_digest": aggregate_digest,
        "result": "QUALIFIED_FROM_EXECUTED_CASE_RECEIPTS",
        "caller_supplied_case_results_accepted": False,
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, PROBE_FAMILY_DIGEST_FIELD)


def verify_executed_probe_family_evidence_v2(
    document: Mapping[str, Any],
    *,
    case_receipts: Sequence[Mapping[str, Any]],
    aggregate_probe: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_FAMILY_EVIDENCE_INVALID"
        )
    try:
        supplied = verify_self_digest(document, PROBE_FAMILY_DIGEST_FIELD)
        rebuilt = build_executed_probe_family_evidence_v2(
            probe_family=document["probe_family"],
            executed_at=document["executed_at"],
            runtime_closure_digest=document["runtime_closure_digest"],
            clock_policy_digest=document["clock_policy_digest"],
            case_receipts=case_receipts,
            aggregate_probe=aggregate_probe,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorProbeEvidenceV2Error):
            raise
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_FAMILY_EVIDENCE_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[PROBE_FAMILY_DIGEST_FIELD]:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_FAMILY_EVIDENCE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_probe_runtime_closure_evidence_v2(
    *,
    executed_at: str,
    production_root_paths: Sequence[str],
    trace_paths: Sequence[str],
    runtime_closure_bindings: Mapping[str, str],
) -> dict[str, Any]:
    roots = tuple(production_root_paths)
    traces = tuple(trace_paths)
    bindings = _module_bindings(runtime_closure_bindings)
    if (
        not roots
        or not traces
        or len(roots) != len(set(roots))
        or len(traces) != len(set(traces))
        or any(path not in bindings for path in roots)
        or any(path not in bindings for path in traces)
    ):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_RUNTIME_CLOSURE_EVIDENCE_INVALID"
        )
    document = {
        "schema_id": RUNTIME_CLOSURE_SCHEMA_ID,
        "schema_version": PROBE_EVIDENCE_SCHEMA_VERSION,
        "executed_at": _time(executed_at, "V31_PROBE_EXECUTED_AT_INVALID"),
        "production_root_paths": list(sorted(roots)),
        "trace_paths": list(sorted(traces)),
        "runtime_closure_bindings": bindings,
        "runtime_closure_digest": canonical_digest(bindings),
        "closure_method": "STATIC_RECURSIVE_PLUS_FRESH_PROCESS_TRACE_BINDINGS",
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, RUNTIME_CLOSURE_DIGEST_FIELD)


def verify_probe_runtime_closure_evidence_v2(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_RUNTIME_CLOSURE_EVIDENCE_INVALID"
        )
    try:
        supplied = verify_self_digest(document, RUNTIME_CLOSURE_DIGEST_FIELD)
        rebuilt = build_probe_runtime_closure_evidence_v2(
            executed_at=document["executed_at"],
            production_root_paths=document["production_root_paths"],
            trace_paths=document["trace_paths"],
            runtime_closure_bindings=document["runtime_closure_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorProbeEvidenceV2Error):
            raise
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_RUNTIME_CLOSURE_EVIDENCE_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[RUNTIME_CLOSURE_DIGEST_FIELD]:
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_RUNTIME_CLOSURE_EVIDENCE_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_persisted_probe_receipt_v2(
    *,
    executed_at: str,
    runtime_closure_digest: str,
    clock_policy_digest: str,
    runtime_closure_binding: Mapping[str, Any],
    clock_policy_binding: Mapping[str, Any],
    raw_first_case_bindings: Mapping[str, Mapping[str, Any]],
    supervisor_case_bindings: Mapping[str, Mapping[str, Any]],
    raw_first_probe_binding: Mapping[str, Any],
    supervisor_probe_binding: Mapping[str, Any],
    raw_first_family_binding: Mapping[str, Any],
    supervisor_family_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal the physical write-once projection of all executed evidence."""

    if (
        not isinstance(raw_first_case_bindings, Mapping)
        or tuple(sorted(raw_first_case_bindings)) != RAW_FIRST_FAILURE_CASES
        or not isinstance(supervisor_case_bindings, Mapping)
        or tuple(sorted(supervisor_case_bindings)) != SUPERVISOR_GATE_CASES
    ):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_PERSISTED_CASE_BINDINGS_INVALID"
        )
    raw_cases = {
        case: _artifact_binding(raw_first_case_bindings[case])
        for case in RAW_FIRST_FAILURE_CASES
    }
    supervisor_cases = {
        case: _artifact_binding(supervisor_case_bindings[case])
        for case in SUPERVISOR_GATE_CASES
    }
    bindings = {
        "runtime_closure": _artifact_binding(runtime_closure_binding),
        "clock_policy": _artifact_binding(clock_policy_binding),
        "raw_first_cases": raw_cases,
        "supervisor_cases": supervisor_cases,
        "raw_first_probe": _artifact_binding(raw_first_probe_binding),
        "supervisor_probe": _artifact_binding(supervisor_probe_binding),
        "raw_first_family": _artifact_binding(raw_first_family_binding),
        "supervisor_family": _artifact_binding(supervisor_family_binding),
    }
    document = {
        "schema_id": PERSISTED_PROBE_RECEIPT_SCHEMA_ID,
        "schema_version": PROBE_EVIDENCE_SCHEMA_VERSION,
        "executed_at": _time(executed_at, "V31_PROBE_EXECUTED_AT_INVALID"),
        "runtime_closure_digest": _digest(
            runtime_closure_digest, "V31_PROBE_RUNTIME_CLOSURE_DIGEST_INVALID"
        ),
        "clock_policy_digest": _digest(
            clock_policy_digest, "V31_PROBE_CLOCK_POLICY_DIGEST_INVALID"
        ),
        "artifact_bindings": bindings,
        "artifact_bindings_digest": canonical_digest(bindings),
        "persistence_mode": "WRITE_ONCE_CANONICAL_JSON_WITH_PHYSICAL_SHA256",
        "network_access_performed": False,
        "result": "TEN_EXECUTED_CASE_RECEIPTS_PERSISTED",
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, PERSISTED_PROBE_RECEIPT_DIGEST_FIELD)


def verify_persisted_probe_receipt_v2(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_PERSISTED_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, PERSISTED_PROBE_RECEIPT_DIGEST_FIELD
        )
        bindings = document["artifact_bindings"]
        rebuilt = build_persisted_probe_receipt_v2(
            executed_at=document["executed_at"],
            runtime_closure_digest=document["runtime_closure_digest"],
            clock_policy_digest=document["clock_policy_digest"],
            runtime_closure_binding=bindings["runtime_closure"],
            clock_policy_binding=bindings["clock_policy"],
            raw_first_case_bindings=bindings["raw_first_cases"],
            supervisor_case_bindings=bindings["supervisor_cases"],
            raw_first_probe_binding=bindings["raw_first_probe"],
            supervisor_probe_binding=bindings["supervisor_probe"],
            raw_first_family_binding=bindings["raw_first_family"],
            supervisor_family_binding=bindings["supervisor_family"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31SuccessorProbeEvidenceV2Error):
            raise
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_PERSISTED_RECEIPT_INVALID"
        ) from exc
    if (
        rebuilt != dict(document)
        or supplied != rebuilt[PERSISTED_PROBE_RECEIPT_DIGEST_FIELD]
    ):
        raise V31SuccessorProbeEvidenceV2Error(
            "V31_PROBE_PERSISTED_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def probe_authority_boundary_v2() -> dict[str, Any]:
    """Return a copy for the isolated persistence composition."""

    return dict(_BOUNDARY)


__all__ = [
    "PERSISTED_PROBE_RECEIPT_DIGEST_FIELD",
    "PERSISTED_PROBE_RECEIPT_SCHEMA_ID",
    "PROBE_CASE_DIGEST_FIELD",
    "PROBE_EVIDENCE_SCHEMA_VERSION",
    "PROBE_FAMILY_DIGEST_FIELD",
    "RAW_FIRST_FAMILY",
    "RAW_NETWORK_BOUNDARY",
    "RUNTIME_CLOSURE_DIGEST_FIELD",
    "SUPERVISOR_FAMILY",
    "SUPERVISOR_NETWORK_BOUNDARY",
    "V31SuccessorProbeEvidenceV2Error",
    "build_executed_probe_case_receipt_v2",
    "build_executed_probe_family_evidence_v2",
    "build_persisted_probe_receipt_v2",
    "build_probe_runtime_closure_evidence_v2",
    "probe_authority_boundary_v2",
    "verify_executed_probe_case_receipt_v2",
    "verify_executed_probe_family_evidence_v2",
    "verify_persisted_probe_receipt_v2",
    "verify_probe_runtime_closure_evidence_v2",
]
