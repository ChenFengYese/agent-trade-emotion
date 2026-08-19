"""Typed post-commit regression evidence for a V3.2 qualification.

The contracts in this module deliberately contain no process runner, file
store, clock, Git, network, Agent, account, or execution adapter.  A PASS
aggregate is possible only for the two fixed full-discovery suites and binds
their complete bounded UTF-8 output into exact physical document bindings.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ..contracts.canonical import canonical_bytes, self_digest, verify_self_digest


class V32PostCommitRegressionError(ValueError):
    """Post-commit regression evidence is malformed or incomplete."""


RESERVATION_SCHEMA_ID = "theory_paper_v32_postcommit_regression_reservation_v1"
RESERVATION_DIGEST_FIELD = "postcommit_regression_reservation_digest"
EXECUTION_SCHEMA_ID = "theory_paper_v32_postcommit_regression_execution_receipt_v1"
EXECUTION_DIGEST_FIELD = "postcommit_regression_execution_receipt_digest"
AGGREGATE_SCHEMA_ID = "theory_paper_v32_postcommit_regression_aggregate_support_v1"
AGGREGATE_DIGEST_FIELD = "postcommit_regression_aggregate_digest"
SCHEMA_VERSION = "1.0.0"

FIXED_PYTHON_EXECUTABLE = "/opt/homebrew/bin/python3.12"
FIXED_GIT_EXECUTABLE = "/usr/bin/git"
FIXED_TEST_DIRECTORY = "tests"
FIXED_MAX_STREAM_BYTES = 4 * 1024 * 1024
FIXED_TIMEOUT_SECONDS = 3600
FIXED_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "TZ": "UTC",
}
FIXED_ENVIRONMENT_DIGEST = hashlib.sha256(
    canonical_bytes(FIXED_ENVIRONMENT)
).hexdigest()
PREQUALIFICATION_BASE = ".runtime/v32/prequalification-regression"
QUALIFICATION_BASE = ".runtime/v32/qualifications"

SUITE_SPECS: dict[str, dict[str, Any]] = {
    "V32_FULL_DISCOVERY": {
        "pattern": "test_theory_paper_v2_v32*.py",
        "receipt_slug": "v32-full-discovery",
    },
    "THEORY_PAPER_FULL_DISCOVERY": {
        "pattern": "test_theory_paper*.py",
        "receipt_slug": "theory-paper-full-discovery",
    },
}
SUITE_IDS = tuple(SUITE_SPECS)

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^v32-(?:prospective|target|qualification)-btcusdt-[0-9]{8}t[0-9]{6}z$")
_RAN = re.compile(r"Ran ([0-9]+) tests? in [0-9.]+s", re.MULTILINE)
_COUNT = {
    "failures": re.compile(r"failures=([0-9]+)"),
    "errors": re.compile(r"errors=([0-9]+)"),
    "skipped": re.compile(r"skipped=([0-9]+)"),
}
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_COMMON_FIELDS = frozenset(
    {
        "target_run_id",
        "qualification_run_id",
        "branch",
        "frozen_commit_sha",
        "frozen_tree_sha",
        "python_executable",
        "python_realpath",
        "python_physical_sha256",
        "python_version",
        "cwd",
        "fixed_environment",
        "fixed_environment_digest",
    }
)
_RESERVATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "reservation_id",
        "reserved_at",
        *_COMMON_FIELDS,
        "suite_plan",
        "workspace_status",
        "workspace_porcelain_sha256",
        "allowed_untracked_user_artifacts",
        "attempt",
        "retry_allowed",
        "caller_argv_injection_allowed",
        "caller_environment_injection_allowed",
        "caller_clock_injection_allowed",
        "caller_store_injection_allowed",
        "caller_output_injection_allowed",
        RESERVATION_DIGEST_FIELD,
    }
)
_EXECUTION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "receipt_id",
        "suite_id",
        "discovery_pattern",
        "fixed_argv",
        "started_at",
        "completed_at",
        *_COMMON_FIELDS,
        "attempt",
        "retry_allowed",
        "timeout_seconds",
        "max_stdout_bytes",
        "max_stderr_bytes",
        "status",
        "runner_outcome",
        "exit_code",
        "tests_run",
        "failures",
        "errors",
        "skips",
        "stdout_utf8",
        "stderr_utf8",
        "stdout_bytes",
        "stderr_bytes",
        "stdout_sha256",
        "stderr_sha256",
        "stdout_complete",
        "stderr_complete",
        "workspace_porcelain_sha256_before",
        "workspace_porcelain_sha256_after",
        EXECUTION_DIGEST_FIELD,
    }
)
_RUNNER_OUTCOME_BY_STATUS = {
    "PASS": frozenset({"COMPLETED"}),
    "FAILED": frozenset({"TEST_FAILED"}),
    "TIMEOUT": frozenset({"TIMEOUT"}),
    "OUTPUT_LIMIT_EXCEEDED": frozenset({"OUTPUT_LIMIT_EXCEEDED"}),
    "INTERRUPTED": frozenset({"INTERRUPTED"}),
    "RUNNER_ERROR": frozenset(
        {"DESCENDANT_PROCESS_LEAK", "RUNNER_ERROR", "WORKSPACE_DRIFT"}
    ),
}
_AGGREGATE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "aggregate_id",
        "started_at",
        "completed_at",
        *_COMMON_FIELDS,
        "reservation_binding",
        "execution_receipt_bindings",
        "suite_ids",
        "attempt",
        "retry_allowed",
        "status",
        "verdict",
        "claim_ceiling",
        AGGREGATE_DIGEST_FIELD,
    }
)


def fixed_argv_for_suite_v1(suite_id: str) -> list[str]:
    spec = SUITE_SPECS.get(suite_id)
    if spec is None:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_SUITE_ID_INVALID")
    return [
        FIXED_PYTHON_EXECUTABLE,
        "-I",
        "-m",
        "unittest",
        "discover",
        "-s",
        FIXED_TEST_DIRECTORY,
        "-t",
        ".",
        "-p",
        str(spec["pattern"]),
    ]


def prequalification_paths_v1(qualification_run_id: str) -> dict[str, str]:
    qualification = _run_id(qualification_run_id, qualification=True)
    root = f"{PREQUALIFICATION_BASE}/{qualification}"
    return {
        "root": root,
        "reservation": f"{root}/reservation.json",
        "aggregate": f"{root}/aggregate.json",
        **{
            f"receipt:{suite_id}": (
                f"{root}/receipts/{SUITE_SPECS[suite_id]['receipt_slug']}.json"
            )
            for suite_id in SUITE_IDS
        },
    }


def qualification_support_paths_v1(qualification_run_id: str) -> dict[str, str]:
    qualification = _run_id(qualification_run_id, qualification=True)
    root = f"{QUALIFICATION_BASE}/{qualification}/support/postcommit-regression"
    return {
        "root": root,
        "reservation": f"{root}/reservation.json",
        "aggregate": f"{root}/aggregate.json",
        **{
            f"receipt:{suite_id}": (
                f"{root}/receipts/{SUITE_SPECS[suite_id]['receipt_slug']}.json"
            )
            for suite_id in SUITE_IDS
        },
    }


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32PostCommitRegressionError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32PostCommitRegressionError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text
    ):
        raise V32PostCommitRegressionError(code)
    return text


def _run_id(value: Any, *, qualification: bool = False) -> str:
    text = _text(value, "V32_POSTCOMMIT_RUN_ID_INVALID")
    if _RUN_ID.fullmatch(text) is None:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RUN_ID_INVALID")
    if qualification and not text.startswith("v32-qualification-"):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RUN_ID_INVALID")
    if not qualification and text.startswith("v32-qualification-"):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RUN_ID_INVALID")
    return text


def _git_identity(branch: Any, commit: Any, tree: Any) -> tuple[str, str, str]:
    branch_text = _text(branch, "V32_POSTCOMMIT_GIT_IDENTITY_INVALID")
    commit_text = _text(commit, "V32_POSTCOMMIT_GIT_IDENTITY_INVALID")
    tree_text = _text(tree, "V32_POSTCOMMIT_GIT_IDENTITY_INVALID")
    if _HEX_40.fullmatch(commit_text) is None or _HEX_40.fullmatch(tree_text) is None:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_GIT_IDENTITY_INVALID")
    return branch_text, commit_text, tree_text


def _cwd(value: Any) -> str:
    text = _text(value, "V32_POSTCOMMIT_CWD_INVALID")
    path = PurePosixPath(text)
    if not path.is_absolute() or path.as_posix() != text or ".." in path.parts:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_CWD_INVALID")
    return text


def _python(value: Any) -> tuple[str, str, str, str]:
    executable = _text(value.get("python_executable") if isinstance(value, Mapping) else None, "V32_POSTCOMMIT_PYTHON_INVALID")
    realpath = _text(value.get("python_realpath") if isinstance(value, Mapping) else None, "V32_POSTCOMMIT_PYTHON_INVALID")
    physical = value.get("python_physical_sha256") if isinstance(value, Mapping) else None
    version = _text(value.get("python_version") if isinstance(value, Mapping) else None, "V32_POSTCOMMIT_PYTHON_INVALID")
    if (
        executable != FIXED_PYTHON_EXECUTABLE
        or not PurePosixPath(realpath).is_absolute()
        or not isinstance(physical, str)
        or _HEX_64.fullmatch(physical) is None
        or re.fullmatch(r"3\.12\.[0-9]+", version) is None
    ):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_PYTHON_INVALID")
    return executable, realpath, physical, version


def _artifacts(value: Any) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_UNTRACKED_INVALID")
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"relative_ref", "physical_sha256"}:
            raise V32PostCommitRegressionError("V32_POSTCOMMIT_UNTRACKED_INVALID")
        relative = _text(item.get("relative_ref"), "V32_POSTCOMMIT_UNTRACKED_INVALID")
        path = PurePosixPath(relative)
        digest = item.get("physical_sha256")
        if path.is_absolute() or path.as_posix() != relative or ".." in path.parts or not isinstance(digest, str) or _HEX_64.fullmatch(digest) is None:
            raise V32PostCommitRegressionError("V32_POSTCOMMIT_UNTRACKED_INVALID")
        rows.append({"relative_ref": relative, "physical_sha256": digest})
    if rows != sorted(rows, key=lambda row: row["relative_ref"]) or len({row["relative_ref"] for row in rows}) != len(rows):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_UNTRACKED_INVALID")
    return rows


def _common(
    *,
    target_run_id: Any,
    qualification_run_id: Any,
    branch: Any,
    frozen_commit_sha: Any,
    frozen_tree_sha: Any,
    python_executable: Any,
    python_realpath: Any,
    python_physical_sha256: Any,
    python_version: Any,
    cwd: Any,
) -> dict[str, str]:
    target = _run_id(target_run_id)
    qualification = _run_id(qualification_run_id, qualification=True)
    if target == qualification:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RUN_ID_INVALID")
    if target.rsplit("-", 1)[-1] != qualification.rsplit("-", 1)[-1]:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_IDENTITY_PAIR_INVALID")
    branch_text, commit, tree = _git_identity(branch, frozen_commit_sha, frozen_tree_sha)
    executable, realpath, physical, version = _python(
        {
            "python_executable": python_executable,
            "python_realpath": python_realpath,
            "python_physical_sha256": python_physical_sha256,
            "python_version": python_version,
        }
    )
    return {
        "target_run_id": target,
        "qualification_run_id": qualification,
        "branch": branch_text,
        "frozen_commit_sha": commit,
        "frozen_tree_sha": tree,
        "python_executable": executable,
        "python_realpath": realpath,
        "python_physical_sha256": physical,
        "python_version": version,
        "cwd": _cwd(cwd),
        "fixed_environment": dict(FIXED_ENVIRONMENT),
        "fixed_environment_digest": FIXED_ENVIRONMENT_DIGEST,
    }


def _suite_plan() -> list[dict[str, Any]]:
    return [
        {
            "suite_id": suite_id,
            "discovery_pattern": SUITE_SPECS[suite_id]["pattern"],
            "fixed_argv": fixed_argv_for_suite_v1(suite_id),
            "timeout_seconds": FIXED_TIMEOUT_SECONDS,
            "max_stdout_bytes": FIXED_MAX_STREAM_BYTES,
            "max_stderr_bytes": FIXED_MAX_STREAM_BYTES,
        }
        for suite_id in SUITE_IDS
    ]


def build_v32_postcommit_regression_reservation_v1(
    *,
    reservation_id: str,
    reserved_at: str,
    target_run_id: str,
    qualification_run_id: str,
    branch: str,
    frozen_commit_sha: str,
    frozen_tree_sha: str,
    python_executable: str,
    python_realpath: str,
    python_physical_sha256: str,
    python_version: str,
    cwd: str,
    workspace_status: str,
    workspace_porcelain_sha256: str,
    allowed_untracked_user_artifacts: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    if workspace_status not in {"CLEAN_EXACT_ALLOWLIST", "PRECHECK_FAILED"}:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_WORKSPACE_STATUS_INVALID")
    if not isinstance(workspace_porcelain_sha256, str) or _HEX_64.fullmatch(workspace_porcelain_sha256) is None:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_WORKSPACE_STATUS_INVALID")
    return self_digest(
        {
            "schema_id": RESERVATION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "reservation_id": _text(reservation_id, "V32_POSTCOMMIT_RESERVATION_ID_INVALID"),
            "reserved_at": _time(reserved_at, "V32_POSTCOMMIT_TIME_INVALID"),
            **_common(
                target_run_id=target_run_id,
                qualification_run_id=qualification_run_id,
                branch=branch,
                frozen_commit_sha=frozen_commit_sha,
                frozen_tree_sha=frozen_tree_sha,
                python_executable=python_executable,
                python_realpath=python_realpath,
                python_physical_sha256=python_physical_sha256,
                python_version=python_version,
                cwd=cwd,
            ),
            "suite_plan": _suite_plan(),
            "workspace_status": workspace_status,
            "workspace_porcelain_sha256": workspace_porcelain_sha256,
            "allowed_untracked_user_artifacts": _artifacts(allowed_untracked_user_artifacts),
            "attempt": 1,
            "retry_allowed": False,
            "caller_argv_injection_allowed": False,
            "caller_environment_injection_allowed": False,
            "caller_clock_injection_allowed": False,
            "caller_store_injection_allowed": False,
            "caller_output_injection_allowed": False,
        },
        RESERVATION_DIGEST_FIELD,
    )


def verify_v32_postcommit_regression_reservation_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _RESERVATION_FIELDS:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RESERVATION_INVALID")
    try:
        supplied = verify_self_digest(document, RESERVATION_DIGEST_FIELD)
        rebuilt = build_v32_postcommit_regression_reservation_v1(
            reservation_id=document["reservation_id"],
            reserved_at=document["reserved_at"],
            target_run_id=document["target_run_id"],
            qualification_run_id=document["qualification_run_id"],
            branch=document["branch"],
            frozen_commit_sha=document["frozen_commit_sha"],
            frozen_tree_sha=document["frozen_tree_sha"],
            python_executable=document["python_executable"],
            python_realpath=document["python_realpath"],
            python_physical_sha256=document["python_physical_sha256"],
            python_version=document["python_version"],
            cwd=document["cwd"],
            workspace_status=document["workspace_status"],
            workspace_porcelain_sha256=document["workspace_porcelain_sha256"],
            allowed_untracked_user_artifacts=document["allowed_untracked_user_artifacts"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PostCommitRegressionError):
            raise
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RESERVATION_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[RESERVATION_DIGEST_FIELD]:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RESERVATION_INVALID")
    return supplied


def _parsed_counts(stdout: str, stderr: str) -> tuple[int | None, int | None, int | None, int | None, bool]:
    output = f"{stdout}\n{stderr}"
    matches = _RAN.findall(output)
    ran = int(matches[-1]) if matches else None
    failures = int(_COUNT["failures"].findall(output)[-1]) if _COUNT["failures"].findall(output) else 0 if ran is not None else None
    errors = int(_COUNT["errors"].findall(output)[-1]) if _COUNT["errors"].findall(output) else 0 if ran is not None else None
    skips = int(_COUNT["skipped"].findall(output)[-1]) if _COUNT["skipped"].findall(output) else 0 if ran is not None else None
    ok = ran is not None and ran > 0 and re.search(r"^OK(?: \([^\n]*\))?$", output, re.MULTILINE) is not None and "FAILED (" not in output
    return ran, failures, errors, skips, ok


def build_v32_postcommit_regression_execution_receipt_v1(
    *,
    receipt_id: str,
    suite_id: str,
    started_at: str,
    completed_at: str,
    target_run_id: str,
    qualification_run_id: str,
    branch: str,
    frozen_commit_sha: str,
    frozen_tree_sha: str,
    python_executable: str,
    python_realpath: str,
    python_physical_sha256: str,
    python_version: str,
    cwd: str,
    status: str,
    runner_outcome: str,
    exit_code: int | None,
    stdout_utf8: str,
    stderr_utf8: str,
    stdout_complete: bool = True,
    stderr_complete: bool = True,
    workspace_porcelain_sha256_before: str = "",
    workspace_porcelain_sha256_after: str = "",
) -> dict[str, Any]:
    if suite_id not in SUITE_SPECS:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_SUITE_ID_INVALID")
    if status not in _RUNNER_OUTCOME_BY_STATUS:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_EXECUTION_STATUS_INVALID")
    if runner_outcome not in _RUNNER_OUTCOME_BY_STATUS[status]:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_RUNNER_OUTCOME_INVALID")
    if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_EXIT_CODE_INVALID")
    stdout = stdout_utf8 if isinstance(stdout_utf8, str) else None
    stderr = stderr_utf8 if isinstance(stderr_utf8, str) else None
    if stdout is None or stderr is None:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_OUTPUT_INVALID")
    stdout_bytes = stdout.encode("utf-8", errors="strict")
    stderr_bytes = stderr.encode("utf-8", errors="strict")
    if not isinstance(stdout_complete, bool) or not isinstance(stderr_complete, bool):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_OUTPUT_INVALID")
    if len(stdout_bytes) > FIXED_MAX_STREAM_BYTES:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_OUTPUT_LIMIT_INVALID")
    if len(stderr_bytes) > FIXED_MAX_STREAM_BYTES:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_OUTPUT_LIMIT_INVALID")
    if (
        not isinstance(workspace_porcelain_sha256_before, str)
        or _HEX_64.fullmatch(workspace_porcelain_sha256_before) is None
        or not isinstance(workspace_porcelain_sha256_after, str)
        or _HEX_64.fullmatch(workspace_porcelain_sha256_after) is None
    ):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_WORKSPACE_STATUS_INVALID")
    started = _time(started_at, "V32_POSTCOMMIT_TIME_INVALID")
    completed = _time(completed_at, "V32_POSTCOMMIT_TIME_INVALID")
    if datetime.fromisoformat(started.replace("Z", "+00:00")) > datetime.fromisoformat(completed.replace("Z", "+00:00")):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_TIME_INVALID")
    ran, failures, errors, skips, output_says_ok = _parsed_counts(stdout, stderr)
    pass_valid = (
        exit_code == 0
        and stdout_complete
        and stderr_complete
        and output_says_ok
        and failures == 0
        and errors == 0
        and skips == 0
        and workspace_porcelain_sha256_before == workspace_porcelain_sha256_after
    )
    if (status == "PASS") != pass_valid:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_PASS_STATUS_INVALID")
    if status in {"TIMEOUT", "INTERRUPTED", "RUNNER_ERROR"} and exit_code is not None:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_EXIT_CODE_INVALID")
    if runner_outcome in {
        "TIMEOUT",
        "OUTPUT_LIMIT_EXCEEDED",
        "DESCENDANT_PROCESS_LEAK",
        "INTERRUPTED",
        "RUNNER_ERROR",
    } and (stdout_complete or stderr_complete):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_OUTPUT_COMPLETENESS_INVALID")
    if runner_outcome == "TEST_FAILED" and (
        not stdout_complete or not stderr_complete
    ):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_OUTPUT_COMPLETENESS_INVALID")
    return self_digest(
        {
            "schema_id": EXECUTION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "receipt_id": _text(receipt_id, "V32_POSTCOMMIT_RECEIPT_ID_INVALID"),
            "suite_id": suite_id,
            "discovery_pattern": SUITE_SPECS[suite_id]["pattern"],
            "fixed_argv": fixed_argv_for_suite_v1(suite_id),
            "started_at": started,
            "completed_at": completed,
            **_common(
                target_run_id=target_run_id,
                qualification_run_id=qualification_run_id,
                branch=branch,
                frozen_commit_sha=frozen_commit_sha,
                frozen_tree_sha=frozen_tree_sha,
                python_executable=python_executable,
                python_realpath=python_realpath,
                python_physical_sha256=python_physical_sha256,
                python_version=python_version,
                cwd=cwd,
            ),
            "attempt": 1,
            "retry_allowed": False,
            "timeout_seconds": FIXED_TIMEOUT_SECONDS,
            "max_stdout_bytes": FIXED_MAX_STREAM_BYTES,
            "max_stderr_bytes": FIXED_MAX_STREAM_BYTES,
            "status": status,
            "runner_outcome": runner_outcome,
            "exit_code": exit_code,
            "tests_run": ran,
            "failures": failures,
            "errors": errors,
            "skips": skips,
            "stdout_utf8": stdout,
            "stderr_utf8": stderr,
            "stdout_bytes": len(stdout_bytes),
            "stderr_bytes": len(stderr_bytes),
            "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
            "stdout_complete": stdout_complete,
            "stderr_complete": stderr_complete,
            "workspace_porcelain_sha256_before": workspace_porcelain_sha256_before,
            "workspace_porcelain_sha256_after": workspace_porcelain_sha256_after,
        },
        EXECUTION_DIGEST_FIELD,
    )


def verify_v32_postcommit_regression_execution_receipt_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _EXECUTION_FIELDS:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_EXECUTION_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, EXECUTION_DIGEST_FIELD)
        rebuilt = build_v32_postcommit_regression_execution_receipt_v1(
            receipt_id=document["receipt_id"],
            suite_id=document["suite_id"],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            target_run_id=document["target_run_id"],
            qualification_run_id=document["qualification_run_id"],
            branch=document["branch"],
            frozen_commit_sha=document["frozen_commit_sha"],
            frozen_tree_sha=document["frozen_tree_sha"],
            python_executable=document["python_executable"],
            python_realpath=document["python_realpath"],
            python_physical_sha256=document["python_physical_sha256"],
            python_version=document["python_version"],
            cwd=document["cwd"],
            status=document["status"],
            runner_outcome=document["runner_outcome"],
            exit_code=document["exit_code"],
            stdout_utf8=document["stdout_utf8"],
            stderr_utf8=document["stderr_utf8"],
            stdout_complete=document["stdout_complete"],
            stderr_complete=document["stderr_complete"],
            workspace_porcelain_sha256_before=document[
                "workspace_porcelain_sha256_before"
            ],
            workspace_porcelain_sha256_after=document[
                "workspace_porcelain_sha256_after"
            ],
        )
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        if isinstance(exc, V32PostCommitRegressionError):
            raise
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_EXECUTION_RECEIPT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[EXECUTION_DIGEST_FIELD]:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_EXECUTION_RECEIPT_INVALID")
    return supplied


def _binding(
    value: Any,
    *,
    expected_path: str,
    schema_id: str,
    digest_field: str,
    document: Mapping[str, Any],
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_BINDING_INVALID")
    payload = canonical_bytes(document) + b"\n"
    expected = {
        "path": expected_path,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if dict(value) != expected:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_BINDING_INVALID")
    return expected


def build_v32_postcommit_regression_aggregate_support_v1(
    *,
    aggregate_id: str,
    reservation: Mapping[str, Any],
    reservation_binding: Mapping[str, str],
    execution_receipts: Mapping[str, Mapping[str, Any]],
    execution_receipt_bindings: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    verify_v32_postcommit_regression_reservation_v1(reservation)
    if reservation.get("workspace_status") != "CLEAN_EXACT_ALLOWLIST":
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_WORKSPACE_NOT_CLEAN")
    if not isinstance(execution_receipts, Mapping) or set(execution_receipts) != set(SUITE_IDS):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_SUITE_SET_INVALID")
    if not isinstance(execution_receipt_bindings, Mapping) or set(execution_receipt_bindings) != set(SUITE_IDS):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_SUITE_SET_INVALID")
    support_paths = qualification_support_paths_v1(reservation["qualification_run_id"])
    reservation_bound = _binding(
        reservation_binding,
        expected_path=support_paths["reservation"],
        schema_id=RESERVATION_SCHEMA_ID,
        digest_field=RESERVATION_DIGEST_FIELD,
        document=reservation,
    )
    receipts: dict[str, Mapping[str, Any]] = {}
    bindings: dict[str, dict[str, str]] = {}
    common = {key: reservation[key] for key in _COMMON_FIELDS}
    for suite_id in SUITE_IDS:
        receipt = execution_receipts[suite_id]
        verify_v32_postcommit_regression_execution_receipt_v1(receipt)
        if (
            receipt.get("suite_id") != suite_id
            or receipt.get("status") != "PASS"
            or receipt.get("skips") != 0
            or receipt.get("workspace_porcelain_sha256_before")
            != reservation.get("workspace_porcelain_sha256")
            or receipt.get("workspace_porcelain_sha256_after")
            != reservation.get("workspace_porcelain_sha256")
            or any(receipt.get(key) != value for key, value in common.items())
        ):
            raise V32PostCommitRegressionError("V32_POSTCOMMIT_SUITE_NOT_PASS")
        receipts[suite_id] = receipt
        bindings[suite_id] = _binding(
            execution_receipt_bindings[suite_id],
            expected_path=support_paths[f"receipt:{suite_id}"],
            schema_id=EXECUTION_SCHEMA_ID,
            digest_field=EXECUTION_DIGEST_FIELD,
            document=receipt,
        )
    ordered_receipts = [receipts[suite_id] for suite_id in SUITE_IDS]
    reservation_moment = datetime.fromisoformat(
        reservation["reserved_at"].replace("Z", "+00:00")
    )
    ordered_windows = [
        (
            datetime.fromisoformat(receipt["started_at"].replace("Z", "+00:00")),
            datetime.fromisoformat(receipt["completed_at"].replace("Z", "+00:00")),
        )
        for receipt in ordered_receipts
    ]
    if reservation_moment > ordered_windows[0][0] or any(
        earlier[1] > later[0]
        for earlier, later in zip(ordered_windows, ordered_windows[1:])
    ):
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_TIME_INVALID")
    started = ordered_receipts[0]["started_at"]
    completed = ordered_receipts[-1]["completed_at"]
    return self_digest(
        {
            "schema_id": AGGREGATE_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "aggregate_id": _text(aggregate_id, "V32_POSTCOMMIT_AGGREGATE_ID_INVALID"),
            "started_at": started,
            "completed_at": completed,
            **common,
            "reservation_binding": reservation_bound,
            "execution_receipt_bindings": bindings,
            "suite_ids": list(SUITE_IDS),
            "attempt": 1,
            "retry_allowed": False,
            "status": "COMPLETE",
            "verdict": "PASS",
            "claim_ceiling": (
                "TRUSTED_LOCAL_CONTROLLER_POSTCOMMIT_AUDIT_ONLY_"
                "NOT_INDEPENDENT_PROVIDER_OR_HARDWARE_ATTESTATION_"
                "NOT_PREDICTION_PROFIT_OR_TRADING_EXECUTION"
            ),
        },
        AGGREGATE_DIGEST_FIELD,
    )


def verify_v32_postcommit_regression_aggregate_support_v1(
    document: Mapping[str, Any],
    *,
    reservation: Mapping[str, Any],
    execution_receipts: Mapping[str, Mapping[str, Any]],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _AGGREGATE_FIELDS:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_AGGREGATE_INVALID")
    try:
        supplied = verify_self_digest(document, AGGREGATE_DIGEST_FIELD)
        rebuilt = build_v32_postcommit_regression_aggregate_support_v1(
            aggregate_id=document["aggregate_id"],
            reservation=reservation,
            reservation_binding=document["reservation_binding"],
            execution_receipts=execution_receipts,
            execution_receipt_bindings=document["execution_receipt_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PostCommitRegressionError):
            raise
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_AGGREGATE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[AGGREGATE_DIGEST_FIELD]:
        raise V32PostCommitRegressionError("V32_POSTCOMMIT_AGGREGATE_INVALID")
    return supplied


__all__ = [
    "AGGREGATE_DIGEST_FIELD",
    "AGGREGATE_SCHEMA_ID",
    "EXECUTION_DIGEST_FIELD",
    "EXECUTION_SCHEMA_ID",
    "FIXED_MAX_STREAM_BYTES",
    "FIXED_ENVIRONMENT",
    "FIXED_ENVIRONMENT_DIGEST",
    "FIXED_GIT_EXECUTABLE",
    "FIXED_PYTHON_EXECUTABLE",
    "FIXED_TIMEOUT_SECONDS",
    "PREQUALIFICATION_BASE",
    "QUALIFICATION_BASE",
    "RESERVATION_DIGEST_FIELD",
    "RESERVATION_SCHEMA_ID",
    "SUITE_IDS",
    "SUITE_SPECS",
    "V32PostCommitRegressionError",
    "build_v32_postcommit_regression_aggregate_support_v1",
    "build_v32_postcommit_regression_execution_receipt_v1",
    "build_v32_postcommit_regression_reservation_v1",
    "fixed_argv_for_suite_v1",
    "prequalification_paths_v1",
    "qualification_support_paths_v1",
    "verify_v32_postcommit_regression_aggregate_support_v1",
    "verify_v32_postcommit_regression_execution_receipt_v1",
    "verify_v32_postcommit_regression_reservation_v1",
]
