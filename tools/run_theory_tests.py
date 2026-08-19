#!/usr/bin/env python3
"""Check Theory test overlap or run its unique legacy-wide suite once.

The disk cache is local developer state, never qualification evidence.  This
tool accepts no run, target, or qualification identity.
"""

from __future__ import annotations

import argparse
import ast
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trade_system.theory_paper_v2.infrastructure.authority import (  # noqa: E402
    v32_postcommit_regression as postcommit_runner,
)


V32_PATTERN = "test_theory_paper_v2_v32*.py"
THEORY_PATTERN = "test_theory_paper*.py"
THEORY_SUITE_ID = "THEORY_PAPER_FULL_DISCOVERY"
PYTHON = postcommit_runner.FIXED_PYTHON_EXECUTABLE
GIT = postcommit_runner.FIXED_GIT_EXECUTABLE
CACHE_BASE = ".runtime/test-cache/theory-wide"
CACHE_VERSION = "1"
CACHE_SCHEMA_ID = "theory_unique_legacy_wide_cache_v1"
CACHE_DIGEST_FIELD = "cache_record_sha256"
CLAIM_SCOPE = "LOCAL_TEST_CACHE_ONLY_NOT_QUALIFICATION_EVIDENCE"
ENV = dict(postcommit_runner.FIXED_ENVIRONMENT)
_RAN = re.compile(r"Ran ([0-9]+) tests? in [0-9.]+s", re.MULTILINE)
_SKIPPED = re.compile(r"skipped=([0-9]+)")
_IDENTITY_FIELDS = {
    "commit",
    "tree",
    "python",
    "python_realpath",
    "python_sha256",
    "python_version",
    "environment_digest",
}
_SUBJECT_FIELDS = {"identity", "catalog_digest", "argv"}
_RESULT_FIELDS = {
    "status",
    "exit_code",
    "tests_run",
    "skips",
    "duration_seconds",
    "output_tail",
}
_CACHE_FIELDS = {
    "schema_id",
    "schema_version",
    "cache_key",
    "subject",
    "claim_scope",
    "completed_at",
    *_RESULT_FIELDS,
    CACHE_DIGEST_FIELD,
}
_ALLOWED_UNTRACKED_USER_ARTIFACT = (
    "archive/user-preserved/"
    "THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md"
)


class TheoryTestRunnerError(ValueError):
    pass


def _bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def collect_test_ids(root: Path, pattern: str) -> tuple[str, ...]:
    """Collect stable unittest IDs without importing test modules."""

    found: list[str] = []
    paths = sorted((root / "tests").glob(pattern))
    if not paths:
        raise TheoryTestRunnerError("THEORY_TEST_PATTERN_EMPTY")
    for path in paths:
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (OSError, SyntaxError) as exc:
            raise TheoryTestRunnerError("THEORY_TEST_CATALOG_INVALID") from exc
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "load_tests"
            for node in tree.body
        ):
            raise TheoryTestRunnerError("THEORY_TEST_DYNAMIC_DISCOVERY_UNSUPPORTED")
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not any(
                _base_name(base).endswith("TestCase") for base in node.bases
            ):
                continue
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    member.name.startswith("test")
                ):
                    found.append(f"{module}.{node.name}.{member.name}")
    if not found:
        raise TheoryTestRunnerError("THEORY_TEST_CATALOG_EMPTY")
    if len(found) != len(set(found)):
        raise TheoryTestRunnerError("THEORY_TEST_ID_DUPLICATE")
    return tuple(sorted(found))


def build_unique_plan(root: Path) -> dict[str, Any]:
    root = root.resolve()
    v32 = collect_test_ids(root, V32_PATTERN)
    theory = collect_test_ids(root, THEORY_PATTERN)
    unique = tuple(sorted(set(v32) | set(theory)))
    if not set(v32) < set(theory) or unique != theory:
        raise TheoryTestRunnerError("THEORY_TEST_SUITE_RELATION_INVALID")
    files = []
    for path in sorted((root / "tests").glob(THEORY_PATTERN)):
        files.append(
            (path.relative_to(root).as_posix(), _sha(path.read_bytes()))
        )
    catalog_digest = _sha(
        _bytes(
            {
                "version": CACHE_VERSION,
                "patterns": [V32_PATTERN, THEORY_PATTERN],
                "test_ids": unique,
                "files": files,
            }
        )
    )
    return {"v32": v32, "theory": theory, "unique": unique, "catalog_digest": catalog_digest}


def suite_argv() -> list[str]:
    return [
        PYTHON,
        "-I",
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-t",
        ".",
        "-p",
        THEORY_PATTERN,
    ]


def build_code_key(identity: Mapping[str, str], catalog_digest: str) -> str:
    if set(identity) != _IDENTITY_FIELDS:
        raise TheoryTestRunnerError("THEORY_TEST_CODE_IDENTITY_INVALID")
    if re.fullmatch(r"[0-9a-f]{64}", catalog_digest) is None:
        raise TheoryTestRunnerError("THEORY_TEST_CATALOG_DIGEST_INVALID")
    return _sha(
        _bytes(
            {
                "version": CACHE_VERSION,
                "identity": dict(identity),
                "catalog_digest": catalog_digest,
                "argv": suite_argv(),
            }
        )
    )


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            [GIT, "-C", str(root), *args],
            check=True,
            capture_output=True,
            env=ENV,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TheoryTestRunnerError("THEORY_TEST_GIT_IDENTITY_FAILED") from exc
    return result.stdout.strip()


def _git_status_bytes(root: Path) -> bytes:
    try:
        result = subprocess.run(
            [
                GIT,
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            env=ENV,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TheoryTestRunnerError("THEORY_TEST_GIT_IDENTITY_FAILED") from exc
    return result.stdout


def _workspace_status_is_allowed(status: bytes) -> bool:
    allowed = _ALLOWED_UNTRACKED_USER_ARTIFACT
    for raw in (entry for entry in status.split(b"\0") if entry):
        if len(raw) < 4 or raw[:2] != b"??" or raw[2:3] != b" ":
            return False
        try:
            relative = raw[3:].decode("utf-8", errors="strict")
        except UnicodeError:
            return False
        if relative != allowed:
            return False
    return True


def _identity(root: Path) -> dict[str, str]:
    if not _workspace_status_is_allowed(_git_status_bytes(root)):
        raise TheoryTestRunnerError("THEORY_TEST_WORKSPACE_NOT_CLEAN")
    try:
        executable = Path(PYTHON).resolve(strict=True)
        physical_sha = _sha(executable.read_bytes())
        version = subprocess.run(
            [str(executable), "--version"],
            check=True,
            capture_output=True,
            env=ENV,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TheoryTestRunnerError("THEORY_TEST_PYTHON_IDENTITY_FAILED") from exc
    return {
        "commit": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "show", "-s", "--format=%T", "HEAD"),
        "python": PYTHON,
        "python_realpath": str(executable),
        "python_sha256": physical_sha,
        "python_version": (version.stdout or version.stderr).strip(),
        "environment_digest": _sha(_bytes(ENV)),
    }


def _record_digest(record: Mapping[str, Any]) -> str:
    unsigned = {
        key: value for key, value in record.items() if key != CACHE_DIGEST_FIELD
    }
    return _sha(_bytes(unsigned))


def _valid_subject(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != _SUBJECT_FIELDS:
        return False
    identity = value.get("identity")
    catalog_digest = value.get("catalog_digest")
    argv = value.get("argv")
    return (
        isinstance(identity, Mapping)
        and set(identity) == _IDENTITY_FIELDS
        and all(isinstance(item, str) and item for item in identity.values())
        and isinstance(catalog_digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", catalog_digest) is not None
        and argv == suite_argv()
    )


def _valid_completed_at(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") == value
    )


def _validate_result_shape(result: Mapping[str, Any], *, expected_tests: int) -> bool:
    if expected_tests <= 0 or set(result) != _RESULT_FIELDS:
        return False
    status = result.get("status")
    exit_code = result.get("exit_code")
    tests_run = result.get("tests_run")
    skips = result.get("skips")
    duration = result.get("duration_seconds")
    output_tail = result.get("output_tail")
    if (
        status not in {"PASS", "FAIL", "TIMEOUT", "RUNNER_ERROR"}
        or isinstance(exit_code, bool)
        or (exit_code is not None and not isinstance(exit_code, int))
        or isinstance(tests_run, bool)
        or (tests_run is not None and (not isinstance(tests_run, int) or tests_run < 0))
        or isinstance(skips, bool)
        or not isinstance(skips, int)
        or skips < 0
        or isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or duration < 0
        or not isinstance(output_tail, str)
        or len(output_tail) > 4000
    ):
        return False
    if status == "PASS":
        return exit_code == 0 and tests_run == expected_tests and skips == 0
    if status == "FAIL":
        return isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
    return exit_code is None


def _build_cache_record(
    *,
    key: str,
    subject: Mapping[str, Any],
    result: Mapping[str, Any],
    completed_at: str,
    expected_tests: int,
) -> dict[str, Any]:
    if (
        not _valid_subject(subject)
        or build_code_key(subject["identity"], subject["catalog_digest"]) != key
        or not _validate_result_shape(result, expected_tests=expected_tests)
    ):
        raise TheoryTestRunnerError("THEORY_TEST_RESULT_INVALID_NO_CACHE")
    record = {
        "schema_id": CACHE_SCHEMA_ID,
        "schema_version": CACHE_VERSION,
        "cache_key": key,
        "subject": dict(subject),
        "claim_scope": CLAIM_SCOPE,
        "completed_at": completed_at,
        **{field: result[field] for field in _RESULT_FIELDS},
    }
    if not _valid_completed_at(completed_at):
        raise TheoryTestRunnerError("THEORY_TEST_RESULT_INVALID_NO_CACHE")
    record[CACHE_DIGEST_FIELD] = _record_digest(record)
    return record


def _load_cache(
    path: Path,
    key: str,
    subject: Mapping[str, Any],
    *,
    expected_tests: int,
) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TheoryTestRunnerError("THEORY_TEST_CACHE_INVALID_NO_RERUN") from exc
    if (
        not isinstance(record, dict)
        or set(record) != _CACHE_FIELDS
        or record.get("schema_id") != CACHE_SCHEMA_ID
        or record.get("schema_version") != CACHE_VERSION
        or record.get("cache_key") != key
        or record.get("subject") != dict(subject)
        or not _valid_subject(record.get("subject"))
        or record.get("claim_scope") != CLAIM_SCOPE
        or not _valid_completed_at(record.get("completed_at"))
        or record.get(CACHE_DIGEST_FIELD) != _record_digest(record)
        or not _validate_result_shape(
            {field: record.get(field) for field in _RESULT_FIELDS},
            expected_tests=expected_tests,
        )
    ):
        raise TheoryTestRunnerError("THEORY_TEST_CACHE_INVALID_NO_RERUN")
    return record


def _write_cache(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(_bytes(record) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise TheoryTestRunnerError("THEORY_TEST_CACHE_WRITE_FAILED") from exc
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _execute(root: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = postcommit_runner._run_fixed_suite_bounded(root, THEORY_SUITE_ID)
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        if result.outcome == "COMPLETED" and result.exit_code == 0:
            status, exit_code = "PASS", 0
        elif result.outcome == "COMPLETED" and isinstance(result.exit_code, int):
            status, exit_code = "FAIL", result.exit_code
        elif result.outcome == "TIMEOUT":
            status, exit_code = "TIMEOUT", None
        else:
            status, exit_code = "RUNNER_ERROR", None
        if status in {"PASS", "FAIL"} and (
            not result.stdout_complete or not result.stderr_complete
        ):
            status, exit_code = "RUNNER_ERROR", None
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        output, status, exit_code = str(exc), "RUNNER_ERROR", None
    ran_matches = list(_RAN.finditer(output))
    tests_run = int(ran_matches[-1].group(1)) if ran_matches else None
    final_summary = output[ran_matches[-1].start():] if ran_matches else ""
    skipped_matches = _SKIPPED.findall(final_summary)
    skips = int(skipped_matches[-1]) if skipped_matches else 0
    if status == "PASS" and (tests_run is None or skips):
        status, exit_code = "RUNNER_ERROR", None
    return {
        "status": status,
        "exit_code": exit_code,
        "tests_run": tests_run,
        "skips": skips,
        "duration_seconds": round(time.monotonic() - started, 6),
        "output_tail": output[-4000:],
    }


def ensure_unique_result(root: Path) -> dict[str, Any]:
    root = root.resolve()
    plan = build_unique_plan(root)
    subject = {
        "identity": _identity(root),
        "catalog_digest": plan["catalog_digest"],
        "argv": suite_argv(),
    }
    key = build_code_key(subject["identity"], subject["catalog_digest"])
    cache = root / CACHE_BASE / f"{key}.json"
    lock = root / CACHE_BASE / f"{key}.lock"
    if cache.exists():
        return {
            **_load_cache(
                cache,
                key,
                subject,
                expected_tests=len(plan["unique"]),
            ),
            "cache_hit": True,
        }
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise TheoryTestRunnerError("THEORY_TEST_ALREADY_RUNNING_OR_INTERRUPTED") from exc
    try:
        try:
            os.write(descriptor, f"pid={os.getpid()}\nkey={key}\n".encode("ascii"))
        finally:
            os.close(descriptor)
        result = _execute(root)
        try:
            unchanged = _identity(root) == subject["identity"]
        except TheoryTestRunnerError:
            unchanged = False
        if not unchanged:
            result["status"] = "RUNNER_ERROR"
            result["exit_code"] = None
            result["output_tail"] = (
                "THEORY_TEST_WORKSPACE_DRIFT_DURING_EXECUTION\n"
                + result["output_tail"]
            )[-4000:]
        if result["status"] == "PASS" and result["tests_run"] != len(plan["unique"]):
            result["status"] = "RUNNER_ERROR"
            result["exit_code"] = None
            result["output_tail"] = (
                f"THEORY_TEST_DISCOVERY_COUNT_MISMATCH expected={len(plan['unique'])} "
                f"actual={result['tests_run']}\n{result['output_tail']}"
            )[-4000:]
        record = _build_cache_record(
            key=key,
            subject=subject,
            result=result,
            completed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            expected_tests=len(plan["unique"]),
        )
        _write_cache(cache, record)
        lock.unlink()
        return {**record, "cache_hit": False}
    except BaseException:
        # An interrupted or unrecorded attempt leaves the lock in place so an
        # unchanged identity cannot silently start the long suite again.
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "legacy-wide"))
    command = parser.parse_args(argv).command
    try:
        if command == "plan":
            plan = build_unique_plan(PROJECT_ROOT)
            result = {
                "v32": len(plan["v32"]),
                "theory": len(plan["theory"]),
                "overlap": len(set(plan["v32"]) & set(plan["theory"])),
                "unique": len(plan["unique"]),
                "suite_executions": 1,
                "catalog_digest": plan["catalog_digest"],
            }
        else:
            record = ensure_unique_result(PROJECT_ROOT)
            result = {
                key: record[key]
                for key in ("status", "tests_run", "duration_seconds", "cache_hit", "cache_key")
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if command == "plan" or result["status"] == "PASS" else 1
    except TheoryTestRunnerError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
