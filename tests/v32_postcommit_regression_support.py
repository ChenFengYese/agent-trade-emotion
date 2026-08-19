"""Deterministic unit-test fixtures for typed post-commit support documents."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import subprocess
from typing import Any

from trade_system.theory_paper_v2.application.v31_authority_freeze import (
    document_binding,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes
from trade_system.theory_paper_v2.domain.governance.v32_postcommit_regression import (
    AGGREGATE_DIGEST_FIELD,
    EXECUTION_DIGEST_FIELD,
    FIXED_PYTHON_EXECUTABLE,
    RESERVATION_DIGEST_FIELD,
    SUITE_IDS,
    build_v32_postcommit_regression_aggregate_support_v1,
    build_v32_postcommit_regression_execution_receipt_v1,
    build_v32_postcommit_regression_reservation_v1,
    prequalification_paths_v1,
    qualification_support_paths_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_secure_write_once_store import (
    secure_write_once_json,
)


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    )
    return result.stdout if binary else result.stdout.decode().strip()


def _binding(path: str, document: dict[str, Any], digest_field: str) -> dict[str, str]:
    return {
        **document_binding(path=path, document=document, digest_field=digest_field),
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }


def write_valid_postcommit_regression_support(
    root: Path, *, target_run_id: str, qualification_run_id: str
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored=no",
        binary=True,
    )
    assert isinstance(status, bytes)
    artifacts: list[dict[str, str]] = []
    for entry in (row for row in status.split(b"\0") if row):
        state = entry[:2].decode("ascii")
        relative = entry[3:].decode("utf-8")
        if state != "??":
            raise AssertionError("test fixture requires a clean tracked workspace")
        path = root / relative
        artifacts.append(
            {
                "relative_ref": relative,
                "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    artifacts.sort(key=lambda row: row["relative_ref"])
    executable = Path(FIXED_PYTHON_EXECUTABLE)
    realpath = executable.resolve(strict=True)
    python_sha = hashlib.sha256(realpath.read_bytes()).hexdigest()
    identity = {
        "target_run_id": target_run_id,
        "qualification_run_id": qualification_run_id,
        "branch": str(_git(root, "branch", "--show-current")),
        "frozen_commit_sha": str(_git(root, "rev-parse", "HEAD")),
        "frozen_tree_sha": str(_git(root, "show", "-s", "--format=%T", "HEAD")),
        "python_executable": FIXED_PYTHON_EXECUTABLE,
        "python_realpath": realpath.as_posix(),
        "python_physical_sha256": python_sha,
        "python_version": platform.python_version(),
        "cwd": root.as_posix(),
    }
    status_digest = hashlib.sha256(status).hexdigest()
    reservation = build_v32_postcommit_regression_reservation_v1(
        reservation_id=f"{qualification_run_id}:postcommit-regression:attempt-1",
        reserved_at="2026-08-06T23:58:00Z",
        **identity,
        workspace_status="CLEAN_EXACT_ALLOWLIST",
        workspace_porcelain_sha256=status_digest,
        allowed_untracked_user_artifacts=artifacts,
    )
    receipts: dict[str, dict[str, Any]] = {}
    for index, suite_id in enumerate(SUITE_IDS):
        seconds = 10 + index * 10
        receipts[suite_id] = build_v32_postcommit_regression_execution_receipt_v1(
            receipt_id=f"{qualification_run_id}:{suite_id.lower()}:attempt-1",
            suite_id=suite_id,
            started_at=f"2026-08-06T23:58:{seconds:02d}Z",
            completed_at=f"2026-08-06T23:58:{seconds + 5:02d}Z",
            **identity,
            status="PASS",
            runner_outcome="COMPLETED",
            exit_code=0,
            stdout_utf8="",
            stderr_utf8="Ran 1 test in 0.001s\n\nOK\n",
            workspace_porcelain_sha256_before=status_digest,
            workspace_porcelain_sha256_after=status_digest,
        )
    support_paths = qualification_support_paths_v1(qualification_run_id)
    reservation_binding = _binding(
        support_paths["reservation"], reservation, RESERVATION_DIGEST_FIELD
    )
    receipt_bindings = {
        suite_id: _binding(
            support_paths[f"receipt:{suite_id}"],
            receipts[suite_id],
            EXECUTION_DIGEST_FIELD,
        )
        for suite_id in SUITE_IDS
    }
    aggregate = build_v32_postcommit_regression_aggregate_support_v1(
        aggregate_id=f"{qualification_run_id}:postcommit-regression:aggregate",
        reservation=reservation,
        reservation_binding=reservation_binding,
        execution_receipts=receipts,
        execution_receipt_bindings=receipt_bindings,
    )
    paths = prequalification_paths_v1(qualification_run_id)
    secure_write_once_json(
        root,
        paths["reservation"],
        reservation,
        digest_field=RESERVATION_DIGEST_FIELD,
        require_new=True,
    )
    for suite_id in SUITE_IDS:
        secure_write_once_json(
            root,
            paths[f"receipt:{suite_id}"],
            receipts[suite_id],
            digest_field=EXECUTION_DIGEST_FIELD,
            require_new=True,
        )
    secure_write_once_json(
        root,
        paths["aggregate"],
        aggregate,
        digest_field=AGGREGATE_DIGEST_FIELD,
        require_new=True,
    )
    return {
        "reservation": reservation,
        "receipts": receipts,
        "aggregate": aggregate,
    }


__all__ = ["write_valid_postcommit_regression_support"]
