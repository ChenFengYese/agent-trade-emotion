"""Fail-closed loader for the three successor V3.1 qualifications.

The loader verifies project-contained physical bytes, replays source/Codex/
monitor durability, checks one shared active authority and predecessor lineage,
then returns a typed authority-input envelope.  It does not activate a run.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ...application.v31_successor_qualification_v2 import (
    verify_current_codex_qualification_durable_v2,
    verify_fresh_public_source_qualification_durable_v2,
    verify_monitor_qualification_durable_v2,
)
from ...domain.contracts.canonical import (
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ...domain.governance.v31_successor_qualification_v2 import (
    CODEX_QUALIFICATION_DIGEST_FIELD,
    CODEX_QUALIFICATION_SCHEMA_ID,
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    MONITOR_QUALIFICATION_SCHEMA_ID,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
    SOURCE_QUALIFICATION_SCHEMA_ID,
    verify_successor_codex_durable_qualification_v2,
    verify_successor_monitor_qualification_v2,
    verify_successor_public_source_qualification_v2,
)
from ..v31_monitor_store import LocalV31MonitorStore, V31MonitorStoreError


class V31SuccessorQualificationAuthorityV2Error(ValueError):
    """The successor qualification authority input was not replayable."""


SUCCESSOR_QUALIFICATION_ENVELOPE_SCHEMA_ID = (
    "theory_paper_v31_successor_qualification_authority_envelope_v2"
)
SUCCESSOR_QUALIFICATION_ENVELOPE_SCHEMA_VERSION = "2.0.0"
SUCCESSOR_QUALIFICATION_ENVELOPE_DIGEST_FIELD = (
    "successor_qualification_envelope_digest"
)
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31SuccessorQualificationAuthorityV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SuccessorQualificationAuthorityV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31SuccessorQualificationAuthorityV2Error(code)
    normalized = parsed.astimezone(UTC)
    canonical_values = {
        normalized.isoformat(timespec="seconds").replace("+00:00", "Z"),
        normalized.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        normalized.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
    }
    if value not in canonical_values:
        raise V31SuccessorQualificationAuthorityV2Error(code)
    return normalized


def _project_root(value: Path) -> Path:
    try:
        supplied = Path(value)
        if supplied.is_symlink():
            raise ValueError("symlink")
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_QUALIFICATION_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_QUALIFICATION_PROJECT_ROOT_INVALID"
        )
    return root


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V31SuccessorQualificationAuthorityV2Error(code)
    result = {key: str(value[key]) for key in sorted(_BINDING_FIELDS)}
    relative = PurePosixPath(result["relative_ref"])
    if (
        "\\" in result["relative_ref"]
        or relative.is_absolute()
        or relative.as_posix() != result["relative_ref"]
        or any(part in {"", ".", ".."} for part in relative.parts)
        or len(result["semantic_digest"]) != 64
        or len(result["physical_sha256"]) != 64
    ):
        raise V31SuccessorQualificationAuthorityV2Error(code)
    return result


def _read_binding(
    *, root: Path, binding: Mapping[str, Any], code: str
) -> dict[str, Any]:
    normalized = _binding(binding, code)
    cursor = root
    try:
        for part in PurePosixPath(normalized["relative_ref"]).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("symlink")
        path = cursor.resolve(strict=True)
        path.relative_to(root)
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != normalized["physical_sha256"]:
            raise ValueError("physical drift")
        document = load_json_strict(path)
        digest = verify_self_digest(document, normalized["digest_field"])
    except (OSError, TypeError, ValueError) as exc:
        raise V31SuccessorQualificationAuthorityV2Error(code) from exc
    if (
        document.get("schema_id") != normalized["schema_id"]
        or digest != normalized["semantic_digest"]
    ):
        raise V31SuccessorQualificationAuthorityV2Error(code)
    return dict(document)


def _contained_run_root(root: Path, relative_ref: str) -> Path:
    relative = PurePosixPath(relative_ref)
    if (
        not relative_ref
        or "\\" in relative_ref
        or relative.is_absolute()
        or relative.as_posix() != relative_ref
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_RUN_ROOT_INVALID"
        )
    cursor = root
    try:
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("symlink")
        run_root = cursor.resolve(strict=True)
        run_root.relative_to(root)
    except (OSError, ValueError) as exc:
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_RUN_ROOT_INVALID"
        ) from exc
    if not run_root.is_dir():
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_RUN_ROOT_INVALID"
        )
    return run_root


def build_successor_qualification_authority_envelope_v2(
    *,
    frozen_at: str,
    run_root_ref: str,
    predecessor_run_id: str,
    predecessor_failure_binding: Mapping[str, Any],
    predecessor_failure_digest: str,
    source_qualification_binding: Mapping[str, Any],
    source_qualification: Mapping[str, Any],
    codex_qualification_binding: Mapping[str, Any],
    codex_qualification: Mapping[str, Any],
    monitor_qualification_binding: Mapping[str, Any],
    monitor_qualification: Mapping[str, Any],
) -> dict[str, Any]:
    """Cross-bind the three replayed receipts as one successor authority input."""

    frozen = _time(
        frozen_at, "V31_SUCCESSOR_QUALIFICATION_FROZEN_AT_INVALID"
    )
    source_digest = verify_successor_public_source_qualification_v2(
        source_qualification
    )
    codex_digest = verify_successor_codex_durable_qualification_v2(
        codex_qualification
    )
    monitor_digest = verify_successor_monitor_qualification_v2(
        monitor_qualification
    )
    bindings = {
        "source": _binding(
            source_qualification_binding,
            "V31_SUCCESSOR_SOURCE_QUALIFICATION_BINDING_INVALID",
        ),
        "codex": _binding(
            codex_qualification_binding,
            "V31_SUCCESSOR_CODEX_QUALIFICATION_BINDING_INVALID",
        ),
        "monitor": _binding(
            monitor_qualification_binding,
            "V31_SUCCESSOR_MONITOR_QUALIFICATION_BINDING_INVALID",
        ),
    }
    expected = {
        "source": (SOURCE_QUALIFICATION_SCHEMA_ID, SOURCE_QUALIFICATION_DIGEST_FIELD, source_digest),
        "codex": (CODEX_QUALIFICATION_SCHEMA_ID, CODEX_QUALIFICATION_DIGEST_FIELD, codex_digest),
        "monitor": (MONITOR_QUALIFICATION_SCHEMA_ID, MONITOR_QUALIFICATION_DIGEST_FIELD, monitor_digest),
    }
    for name, (schema_id, digest_field, semantic_digest) in expected.items():
        if (
            bindings[name]["schema_id"] != schema_id
            or bindings[name]["digest_field"] != digest_field
            or bindings[name]["semantic_digest"] != semantic_digest
        ):
            raise V31SuccessorQualificationAuthorityV2Error(
                "V31_SUCCESSOR_QUALIFICATION_BINDING_MISMATCH"
            )
    run_ids = {
        str(source_qualification["run_id"]),
        str(codex_qualification["run_id"]),
        str(monitor_qualification["run_id"]),
    }
    predecessors = {
        str(source_qualification["predecessor_run_id"]),
        str(codex_qualification["predecessor_run_id"]),
        str(monitor_qualification["predecessor_run_id"]),
        str(predecessor_run_id),
    }
    authorities = {
        str(source_qualification["authority_digest"]),
        str(codex_qualification["authority_digest"]),
        str(monitor_qualification["authority_digest"]),
    }
    if (
        len(run_ids) != 1
        or len(predecessors) != 1
        or len(authorities) != 1
        or next(iter(run_ids)) == predecessor_run_id
        or codex_qualification.get("source_qualification_v2_digest")
        != source_digest
        or codex_qualification.get("cycle_index") != 1
        or frozen < _time(
            source_qualification["qualified_at"],
            "V31_SUCCESSOR_SOURCE_QUALIFICATION_TIME_INVALID",
        )
        or frozen < _time(
            codex_qualification["qualified_at"],
            "V31_SUCCESSOR_CODEX_QUALIFICATION_TIME_INVALID",
        )
        or frozen < _time(
            monitor_qualification["qualified_at"],
            "V31_SUCCESSOR_MONITOR_QUALIFICATION_TIME_INVALID",
        )
        or frozen > _time(
            source_qualification["expires_at"],
            "V31_SUCCESSOR_SOURCE_QUALIFICATION_EXPIRED",
        )
    ):
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_QUALIFICATION_CROSS_BINDING_INVALID"
        )
    predecessor_binding = _binding(
        predecessor_failure_binding,
        "V31_SUCCESSOR_PREDECESSOR_FAILURE_BINDING_INVALID",
    )
    if predecessor_binding["semantic_digest"] != predecessor_failure_digest:
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_PREDECESSOR_FAILURE_BINDING_INVALID"
        )
    return self_digest(
        {
            "schema_id": SUCCESSOR_QUALIFICATION_ENVELOPE_SCHEMA_ID,
            "schema_version": SUCCESSOR_QUALIFICATION_ENVELOPE_SCHEMA_VERSION,
            "frozen_at": frozen_at,
            "run_id": next(iter(run_ids)),
            "run_root_ref": run_root_ref,
            "predecessor_run_id": predecessor_run_id,
            "predecessor_failure_binding": predecessor_binding,
            "predecessor_failure_digest": predecessor_failure_digest,
            "active_authority_digest": next(iter(authorities)),
            "qualification_bindings": bindings,
            "qualification_digests": {
                "source": source_digest,
                "codex": codex_digest,
                "monitor": monitor_digest,
            },
            "qualification_summary": {
                "verdict": "SUCCESSOR_QUALIFICATIONS_COMPLETE_NOT_RUN_ACTIVATION",
                "qualification_count": 3,
                "authority_postdating_source": True,
                "current_codex_durable_delivery": True,
                "raw_first_supervised_monitor": True,
                "old_run_reuse": False,
            },
            "limitations": [
                "AUTHORITY_INPUT_ONLY_NOT_RUN_ACTIVATION",
                "NO_PREDICTION_INCREMENT_CLAIM",
                "NO_CALIBRATION_OR_PROFITABILITY_CLAIM",
                "NO_PAPER_LIVE_ACCOUNT_ORDER_CREDENTIAL_OR_FUNDS_AUTHORITY",
            ],
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        SUCCESSOR_QUALIFICATION_ENVELOPE_DIGEST_FIELD,
    )


def verify_successor_qualification_authority_envelope_v2(
    document: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping):
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_QUALIFICATION_ENVELOPE_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, SUCCESSOR_QUALIFICATION_ENVELOPE_DIGEST_FIELD
        )
    except ValueError as exc:
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_QUALIFICATION_ENVELOPE_INVALID"
        ) from exc
    if (
        document.get("schema_id")
        != SUCCESSOR_QUALIFICATION_ENVELOPE_SCHEMA_ID
        or document.get("schema_version")
        != SUCCESSOR_QUALIFICATION_ENVELOPE_SCHEMA_VERSION
        or document.get("qualification_summary", {}).get(
            "qualification_count"
        )
        != 3
        or set(document.get("qualification_bindings", {}))
        != {"source", "codex", "monitor"}
        or set(document.get("qualification_digests", {}))
        != {"source", "codex", "monitor"}
        or document.get("run_id") == document.get("predecessor_run_id")
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
    ):
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_QUALIFICATION_ENVELOPE_INVALID"
        )
    _time(
        document.get("frozen_at"),
        "V31_SUCCESSOR_QUALIFICATION_FROZEN_AT_INVALID",
    )
    for name, binding in document["qualification_bindings"].items():
        normalized = _binding(
            binding, "V31_SUCCESSOR_QUALIFICATION_BINDING_INVALID"
        )
        if (
            normalized["semantic_digest"]
            != document["qualification_digests"][name]
        ):
            raise V31SuccessorQualificationAuthorityV2Error(
                "V31_SUCCESSOR_QUALIFICATION_BINDING_MISMATCH"
            )
    predecessor = _binding(
        document.get("predecessor_failure_binding"),
        "V31_SUCCESSOR_PREDECESSOR_FAILURE_BINDING_INVALID",
    )
    if predecessor["semantic_digest"] != document.get(
        "predecessor_failure_digest"
    ):
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_PREDECESSOR_FAILURE_BINDING_INVALID"
        )
    return supplied


def load_successor_qualification_authority_input_v2(
    *,
    project_root: Path,
    run_root_ref: str,
    frozen_at: str,
    predecessor_run_id: str,
    predecessor_failure_binding: Mapping[str, Any],
    authority: Mapping[str, Any],
    validated_authority_digest: str,
    source_qualification_binding: Mapping[str, Any],
    codex_qualification_binding: Mapping[str, Any],
    monitor_qualification_binding: Mapping[str, Any],
    predecessor_run_root_ref: str | None = None,
    predecessor_monitor_checkpoint_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Physically replay all successor qualification inputs before authority."""

    project = _project_root(project_root)
    run_root = _contained_run_root(project, run_root_ref)
    predecessor_failure = _read_binding(
        root=project,
        binding=predecessor_failure_binding,
        code="V31_SUCCESSOR_PREDECESSOR_FAILURE_EVIDENCE_INVALID",
    )
    predecessor_monitor_checkpoint: dict[str, Any] | None = None
    if (
        predecessor_run_root_ref is None
        and predecessor_monitor_checkpoint_binding is None
    ):
        # Compatibility for an explicitly self-describing failed checkpoint.
        # Real v1 monitor failure receipts do not contain ``status`` and must
        # use the full-store branch below; a failure receipt alone is never
        # upgraded to proof of terminal state.
        if (
            predecessor_failure.get("run_id") != predecessor_run_id
            or predecessor_failure.get("status") != "FAILED_CLOSED"
            or predecessor_failure.get("resume_allowed") is not False
            or predecessor_failure.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or predecessor_failure.get("executable") is not False
        ):
            raise V31SuccessorQualificationAuthorityV2Error(
                "V31_SUCCESSOR_PREDECESSOR_CHECKPOINT_EVIDENCE_REQUIRED"
            )
    elif (
        predecessor_run_root_ref is None
        or predecessor_monitor_checkpoint_binding is None
    ):
        raise V31SuccessorQualificationAuthorityV2Error(
            "V31_SUCCESSOR_PREDECESSOR_CHECKPOINT_EVIDENCE_INCOMPLETE"
        )
    else:
        predecessor_root = _contained_run_root(
            project, predecessor_run_root_ref
        )
        physically_bound_checkpoint = _read_binding(
            root=project,
            binding=predecessor_monitor_checkpoint_binding,
            code="V31_SUCCESSOR_PREDECESSOR_MONITOR_CHECKPOINT_INVALID",
        )
        try:
            monitor_store = LocalV31MonitorStore(predecessor_root)
            predecessor_monitor_checkpoint = dict(
                monitor_store.load_checkpoint(run_id=predecessor_run_id)
            )
            durable_failure = dict(
                monitor_store.read_document(
                    relative_ref=str(
                        predecessor_monitor_checkpoint["failure_ref"]
                    ),
                    digest_field="failure_digest",
                    expected_semantic_digest=str(
                        predecessor_monitor_checkpoint["failure_digest"]
                    ),
                )
            )
        except (KeyError, V31MonitorStoreError, ValueError) as exc:
            raise V31SuccessorQualificationAuthorityV2Error(
                "V31_SUCCESSOR_PREDECESSOR_MONITOR_REPLAY_INVALID"
            ) from exc
        checkpoint_relative_ref = (
            f"{predecessor_run_root_ref.rstrip('/')}/monitor/checkpoint.json"
        )
        failure_relative_ref = (
            f"{predecessor_run_root_ref.rstrip('/')}/"
            f"{predecessor_monitor_checkpoint['failure_ref']}"
        )
        plans = predecessor_monitor_checkpoint.get("plan_bindings")
        attempts = predecessor_monitor_checkpoint.get(
            "resolution_attempt_bindings"
        )
        outcomes = predecessor_monitor_checkpoint.get("outcome_bindings")
        if (
            physically_bound_checkpoint != predecessor_monitor_checkpoint
            or predecessor_monitor_checkpoint_binding.get("relative_ref")
            != checkpoint_relative_ref
            or predecessor_monitor_checkpoint.get("run_id")
            != predecessor_run_id
            or predecessor_monitor_checkpoint.get("status")
            != "FAILED_CLOSED"
            or predecessor_monitor_checkpoint.get("resume_allowed") is not False
            or predecessor_monitor_checkpoint.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or predecessor_monitor_checkpoint.get("executable") is not False
            or predecessor_failure_binding.get("relative_ref")
            != failure_relative_ref
            or predecessor_failure_binding.get("semantic_digest")
            != predecessor_monitor_checkpoint.get("failure_digest")
            or durable_failure != predecessor_failure
            or predecessor_failure.get("run_id") != predecessor_run_id
            or predecessor_failure.get("resume_allowed") is not False
            or predecessor_failure.get("external_execution_authority")
            != "NONE_LOCAL_SIMULATION"
            or predecessor_failure.get("executable") is not False
            or not isinstance(plans, list)
            or not isinstance(attempts, list)
            or not isinstance(outcomes, list)
            or predecessor_failure.get("planned_cycles") != len(plans)
            or predecessor_failure.get("reserved_attempts") != len(attempts)
            or predecessor_failure.get("resolved_cycles") != len(outcomes)
        ):
            raise V31SuccessorQualificationAuthorityV2Error(
                "V31_SUCCESSOR_PREDECESSOR_NOT_FAILED_CLOSED"
            )
    documents = {
        "source": _read_binding(
            root=project,
            binding=source_qualification_binding,
            code="V31_SUCCESSOR_SOURCE_QUALIFICATION_PHYSICAL_INVALID",
        ),
        "codex": _read_binding(
            root=project,
            binding=codex_qualification_binding,
            code="V31_SUCCESSOR_CODEX_QUALIFICATION_PHYSICAL_INVALID",
        ),
        "monitor": _read_binding(
            root=project,
            binding=monitor_qualification_binding,
            code="V31_SUCCESSOR_MONITOR_QUALIFICATION_PHYSICAL_INVALID",
        ),
    }
    verify_fresh_public_source_qualification_durable_v2(
        project_root=project,
        authority=authority,
        validated_authority_digest=validated_authority_digest,
        document=documents["source"],
    )
    verify_current_codex_qualification_durable_v2(
        project_root=project,
        run_root_ref=run_root_ref,
        authority=authority,
        validated_authority_digest=validated_authority_digest,
        document=documents["codex"],
    )
    verify_monitor_qualification_durable_v2(
        run_root=run_root, document=documents["monitor"]
    )
    envelope = build_successor_qualification_authority_envelope_v2(
        frozen_at=frozen_at,
        run_root_ref=run_root_ref,
        predecessor_run_id=predecessor_run_id,
        predecessor_failure_binding=predecessor_failure_binding,
        predecessor_failure_digest=str(
            predecessor_failure_binding["semantic_digest"]
        ),
        source_qualification_binding=source_qualification_binding,
        source_qualification=documents["source"],
        codex_qualification_binding=codex_qualification_binding,
        codex_qualification=documents["codex"],
        monitor_qualification_binding=monitor_qualification_binding,
        monitor_qualification=documents["monitor"],
    )
    return {
        "envelope": envelope,
        "source_qualification": documents["source"],
        "codex_qualification": documents["codex"],
        "monitor_qualification": documents["monitor"],
        "predecessor_failure": predecessor_failure,
        "predecessor_monitor_checkpoint": predecessor_monitor_checkpoint,
    }


__all__ = [
    "SUCCESSOR_QUALIFICATION_ENVELOPE_DIGEST_FIELD",
    "SUCCESSOR_QUALIFICATION_ENVELOPE_SCHEMA_ID",
    "V31SuccessorQualificationAuthorityV2Error",
    "build_successor_qualification_authority_envelope_v2",
    "load_successor_qualification_authority_input_v2",
    "verify_successor_qualification_authority_envelope_v2",
]
