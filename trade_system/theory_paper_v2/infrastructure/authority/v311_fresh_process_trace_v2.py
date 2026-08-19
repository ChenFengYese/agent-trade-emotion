"""Collect and replay a real fresh-process project import trace."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Sequence

from ...domain.governance.v311_fresh_process_trace_v2 import (
    V311FreshProcessTraceV2Error,
    build_v311_fresh_process_trace_receipt_v2,
    verify_v311_fresh_process_trace_receipt_v2,
)


class V311FreshProcessTraceCollectorV2Error(ValueError):
    """The isolated import worker did not produce trustworthy trace evidence."""


_WORKER_SOURCE = r'''
import contextlib
import io
import json
import os
from pathlib import Path
import sys

request = json.loads(sys.argv[1])
root = Path(request["project_root"]).resolve(strict=True)
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
captured_stdout = io.StringIO()
captured_stderr = io.StringIO()
with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
    for module_name in request["root_modules"]:
        __import__(module_name, fromlist=["*"])

observed = set()
for module in tuple(sys.modules.values()):
    raw = getattr(module, "__file__", None)
    if not isinstance(raw, str) or not raw:
        continue
    try:
        path = Path(raw).resolve(strict=True)
        if path.suffix == ".pyc":
            source = Path(str(path)[:-1])
            if source.is_file():
                path = source.resolve(strict=True)
        relative = path.relative_to(root).as_posix()
    except (OSError, ValueError):
        continue
    if relative.endswith(".py"):
        observed.add(relative)

payload = {
    "echoed_nonce": request["nonce"],
    "worker_pid": os.getpid(),
    "python_version": sys.version,
    "observed_project_python_paths": sorted(observed),
    "captured_stdout": captured_stdout.getvalue(),
    "captured_stderr": captured_stderr.getvalue(),
}
sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
'''


def _canonical_time() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _project_root(value: Path) -> Path:
    supplied = Path(value)
    try:
        if supplied.is_symlink():
            raise ValueError("symlink")
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PROJECT_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PROJECT_ROOT_INVALID"
        )
    return root


def _root_module(relative_path: str) -> str:
    if not isinstance(relative_path, str):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PRODUCTION_ROOT_INVALID"
        )
    path = PurePosixPath(relative_path)
    if (
        "\\" in relative_path
        or path.is_absolute()
        or path.as_posix() != relative_path
        or path.suffix != ".py"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PRODUCTION_ROOT_INVALID"
        )
    parts = path.parts[:-1] if path.name == "__init__.py" else (*path.parts[:-1], path.stem)
    if not parts or not all(part.isidentifier() for part in parts):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PRODUCTION_ROOT_INVALID"
        )
    return ".".join(parts)


def collect_v311_fresh_process_trace_v2(
    *,
    project_root: Path,
    python_executable: Path,
    trace_id: str,
    invocation_nonce: str,
    production_root_paths: Sequence[str],
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Import the roots in a new interpreter and seal its observed modules."""

    root = _project_root(project_root)
    try:
        executable = Path(python_executable).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PYTHON_EXECUTABLE_INVALID"
        ) from exc
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PYTHON_EXECUTABLE_INVALID"
        )
    if isinstance(production_root_paths, (str, bytes)):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PRODUCTION_ROOTS_INVALID"
        )
    roots = tuple(sorted(set(production_root_paths)))
    if not roots or len(roots) != len(tuple(production_root_paths)):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_PRODUCTION_ROOTS_INVALID"
        )
    modules = tuple(_root_module(path) for path in roots)
    for relative_path in roots:
        candidate = root.joinpath(*PurePosixPath(relative_path).parts)
        try:
            target = candidate.resolve(strict=True)
            target.relative_to(root)
        except (OSError, ValueError) as exc:
            raise V311FreshProcessTraceCollectorV2Error(
                "V311_TRACE_PRODUCTION_ROOT_MISSING"
            ) from exc
        if not target.is_file() or target.is_symlink():
            raise V311FreshProcessTraceCollectorV2Error(
                "V311_TRACE_PRODUCTION_ROOT_MISSING"
            )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= 300
    ):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_TIMEOUT_INVALID"
        )
    request = json.dumps(
        {
            "project_root": str(root),
            "root_modules": modules,
            "nonce": invocation_nonce,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    started_at = _canonical_time()
    try:
        completed = subprocess.run(
            [str(executable), "-I", "-c", _WORKER_SOURCE, request],
            cwd=root,
            env={
                "LC_ALL": "C",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_WORKER_FAILED"
        ) from exc
    completed_at = _canonical_time()
    if completed.returncode != 0:
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_WORKER_FAILED"
        )
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_WORKER_OUTPUT_INVALID"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("captured_stdout") != ""
        or payload.get("captured_stderr") != ""
        or completed.stderr != b""
        or payload.get("echoed_nonce") != invocation_nonce
        or payload.get("worker_pid") == os.getpid()
    ):
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_WORKER_OUTPUT_INVALID"
        )
    try:
        receipt = build_v311_fresh_process_trace_receipt_v2(
            trace_id=trace_id,
            started_at=started_at,
            completed_at=completed_at,
            parent_pid=os.getpid(),
            worker_pid=payload["worker_pid"],
            invocation_nonce=invocation_nonce,
            echoed_nonce=payload["echoed_nonce"],
            python_executable=str(executable),
            python_version=payload["python_version"],
            production_root_paths=roots,
            imported_root_modules=modules,
            observed_project_python_paths=payload[
                "observed_project_python_paths"
            ],
            stderr_sha256=hashlib.sha256(completed.stderr).hexdigest(),
            stderr_empty=True,
        )
        verify_v311_fresh_process_trace_receipt_v2(receipt)
    except (KeyError, TypeError, ValueError, V311FreshProcessTraceV2Error) as exc:
        raise V311FreshProcessTraceCollectorV2Error(
            "V311_TRACE_RECEIPT_INVALID"
        ) from exc
    return receipt


__all__ = [
    "V311FreshProcessTraceCollectorV2Error",
    "collect_v311_fresh_process_trace_v2",
]
