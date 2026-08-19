"""Typed evidence for an actually observed fresh-process import trace.

The receipt deliberately distinguishes an observed child-process module set
from a static import closure.  It grants no execution or trading capability;
it only records which project-local Python sources were loaded while importing
an explicit set of production roots in a newly spawned interpreter.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from ..contracts.canonical import self_digest, verify_self_digest


class V311FreshProcessTraceV2Error(ValueError):
    """Fresh-process trace evidence is incomplete or internally inconsistent."""


FRESH_PROCESS_TRACE_SCHEMA_ID = (
    "theory_paper_v311_fresh_process_import_trace_v2"
)
FRESH_PROCESS_TRACE_SCHEMA_VERSION = "2.0.0"
FRESH_PROCESS_TRACE_DIGEST_FIELD = "fresh_process_trace_digest"
FRESH_PROCESS_TRACE_OBSERVATION_METHOD = (
    "FRESH_CHILD_PROCESS_SYS_MODULES_AFTER_EXPLICIT_ROOT_IMPORT"
)

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V311FreshProcessTraceV2Error(code)
    return value


def _safe_id(value: Any, code: str) -> str:
    result = _text(value, code)
    if _SAFE_ID.fullmatch(result) is None:
        raise V311FreshProcessTraceV2Error(code)
    return result


def _time(value: Any, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311FreshProcessTraceV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V311FreshProcessTraceV2Error(code)
    parsed = parsed.astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != text:
        raise V311FreshProcessTraceV2Error(code)
    return parsed


def _python_path(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or path.suffix != ".py"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V311FreshProcessTraceV2Error(code)
    return text


def _path_sequence(
    values: Sequence[str], *, code: str, allow_empty: bool
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise V311FreshProcessTraceV2Error(code)
    try:
        rows = tuple(_python_path(value, code) for value in values)
    except TypeError as exc:
        raise V311FreshProcessTraceV2Error(code) from exc
    if (not allow_empty and not rows) or rows != tuple(sorted(set(rows))):
        raise V311FreshProcessTraceV2Error(code)
    return rows


def _module_sequence(values: Sequence[str], code: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise V311FreshProcessTraceV2Error(code)
    try:
        rows = tuple(_text(value, code) for value in values)
    except TypeError as exc:
        raise V311FreshProcessTraceV2Error(code) from exc
    if (
        not rows
        or rows != tuple(sorted(set(rows)))
        or any(
            not all(part.isidentifier() for part in row.split("."))
            for row in rows
        )
    ):
        raise V311FreshProcessTraceV2Error(code)
    return rows


def _positive_pid(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise V311FreshProcessTraceV2Error(code)
    return value


def build_v311_fresh_process_trace_receipt_v2(
    *,
    trace_id: str,
    started_at: str,
    completed_at: str,
    parent_pid: int,
    worker_pid: int,
    invocation_nonce: str,
    echoed_nonce: str,
    python_executable: str,
    python_version: str,
    production_root_paths: Sequence[str],
    imported_root_modules: Sequence[str],
    observed_project_python_paths: Sequence[str],
    stderr_sha256: str,
    stderr_empty: bool,
) -> dict[str, Any]:
    """Build evidence only after a separate interpreter returned successfully."""

    trace = _safe_id(trace_id, "V311_TRACE_ID_INVALID")
    started = _time(started_at, "V311_TRACE_STARTED_AT_INVALID")
    completed = _time(completed_at, "V311_TRACE_COMPLETED_AT_INVALID")
    parent = _positive_pid(parent_pid, "V311_TRACE_PARENT_PID_INVALID")
    worker = _positive_pid(worker_pid, "V311_TRACE_WORKER_PID_INVALID")
    nonce = _text(invocation_nonce, "V311_TRACE_NONCE_INVALID")
    echo = _text(echoed_nonce, "V311_TRACE_NONCE_INVALID")
    executable = _text(python_executable, "V311_TRACE_PYTHON_INVALID")
    version = _text(python_version, "V311_TRACE_PYTHON_INVALID")
    roots = _path_sequence(
        production_root_paths,
        code="V311_TRACE_PRODUCTION_ROOTS_INVALID",
        allow_empty=False,
    )
    modules = _module_sequence(
        imported_root_modules, "V311_TRACE_ROOT_MODULES_INVALID"
    )
    observed = _path_sequence(
        observed_project_python_paths,
        code="V311_TRACE_OBSERVED_PATHS_INVALID",
        allow_empty=False,
    )
    stderr_digest = _text(stderr_sha256, "V311_TRACE_STDERR_DIGEST_INVALID")
    if _HEX_64.fullmatch(stderr_digest) is None:
        raise V311FreshProcessTraceV2Error(
            "V311_TRACE_STDERR_DIGEST_INVALID"
        )
    if (
        completed < started
        or parent == worker
        or nonce != echo
        or not executable.startswith("/")
        or len(roots) != len(modules)
        or not set(roots).issubset(observed)
        or not isinstance(stderr_empty, bool)
    ):
        raise V311FreshProcessTraceV2Error("V311_TRACE_CROSS_BINDING_INVALID")
    document = {
        "schema_id": FRESH_PROCESS_TRACE_SCHEMA_ID,
        "schema_version": FRESH_PROCESS_TRACE_SCHEMA_VERSION,
        "trace_id": trace,
        "started_at": started_at,
        "completed_at": completed_at,
        "observation_method": FRESH_PROCESS_TRACE_OBSERVATION_METHOD,
        "parent_pid": parent,
        "worker_pid": worker,
        "fresh_process_proven": True,
        "invocation_nonce": nonce,
        "echoed_nonce": echo,
        "process_exit_code": 0,
        "python_executable": executable,
        "python_version": version,
        "production_root_paths": list(roots),
        "imported_root_modules": list(modules),
        "observed_project_python_paths": list(observed),
        "stderr_sha256": stderr_digest,
        "stderr_empty": stderr_empty,
        "trace_claim": "OBSERVED_IMPORTS_ONLY_NOT_COMPLETE_RUNTIME_COVERAGE",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, FRESH_PROCESS_TRACE_DIGEST_FIELD)


def verify_v311_fresh_process_trace_receipt_v2(
    document: Mapping[str, Any],
) -> str:
    """Reconstruct the receipt so extra fields or relabeling fail closed."""

    if not isinstance(document, Mapping):
        raise V311FreshProcessTraceV2Error("V311_TRACE_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, FRESH_PROCESS_TRACE_DIGEST_FIELD)
        rebuilt = build_v311_fresh_process_trace_receipt_v2(
            trace_id=document["trace_id"],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            parent_pid=document["parent_pid"],
            worker_pid=document["worker_pid"],
            invocation_nonce=document["invocation_nonce"],
            echoed_nonce=document["echoed_nonce"],
            python_executable=document["python_executable"],
            python_version=document["python_version"],
            production_root_paths=document["production_root_paths"],
            imported_root_modules=document["imported_root_modules"],
            observed_project_python_paths=document[
                "observed_project_python_paths"
            ],
            stderr_sha256=document["stderr_sha256"],
            stderr_empty=document["stderr_empty"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V311FreshProcessTraceV2Error):
            raise
        raise V311FreshProcessTraceV2Error(
            "V311_TRACE_RECEIPT_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[FRESH_PROCESS_TRACE_DIGEST_FIELD]:
        raise V311FreshProcessTraceV2Error(
            "V311_TRACE_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "FRESH_PROCESS_TRACE_DIGEST_FIELD",
    "FRESH_PROCESS_TRACE_OBSERVATION_METHOD",
    "FRESH_PROCESS_TRACE_SCHEMA_ID",
    "FRESH_PROCESS_TRACE_SCHEMA_VERSION",
    "V311FreshProcessTraceV2Error",
    "build_v311_fresh_process_trace_receipt_v2",
    "verify_v311_fresh_process_trace_receipt_v2",
]
