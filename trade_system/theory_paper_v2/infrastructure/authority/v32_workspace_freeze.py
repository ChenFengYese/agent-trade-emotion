"""Git-backed verifier for the V3.2 committed-workspace freeze receipt."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import subprocess
from typing import Any, Mapping

from ...domain.governance.v32_workspace_freeze import (
    SCHEMA_VERSION_POSTCOMMIT,
    V32WorkspaceFreezeError,
    verify_v32_workspace_freeze_receipt_v1,
)
from ...domain.governance.v32_postcommit_regression import (
    FIXED_ENVIRONMENT,
    FIXED_GIT_EXECUTABLE,
)
from .v32_postcommit_regression import (
    V32PostCommitRegressionInfrastructureError,
    replay_v32_postcommit_regression_aggregate_support_v1,
)


class V32WorkspaceFreezeInfrastructureError(ValueError):
    """The live Git worktree no longer matches the frozen receipt."""


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            [FIXED_GIT_EXECUTABLE, "-C", str(root), *args],
            check=True,
            capture_output=True,
            env=dict(FIXED_ENVIRONMENT),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise V32WorkspaceFreezeInfrastructureError(
            "V32_WORKSPACE_GIT_COMMAND_FAILED"
        ) from exc
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_live_v32_workspace_freeze_v1(
    *, project_root: Path, receipt: Mapping[str, Any]
) -> str:
    try:
        receipt_digest = verify_v32_workspace_freeze_receipt_v1(receipt)
    except V32WorkspaceFreezeError as exc:
        raise V32WorkspaceFreezeInfrastructureError(
            "V32_WORKSPACE_RECEIPT_INVALID"
        ) from exc
    supplied = Path(project_root)
    try:
        if supplied.is_symlink():
            raise V32WorkspaceFreezeInfrastructureError("V32_WORKSPACE_ROOT_INVALID")
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V32WorkspaceFreezeInfrastructureError(
            "V32_WORKSPACE_ROOT_INVALID"
        ) from exc
    if not root.is_dir() or _git(root, "rev-parse", "--show-toplevel") != str(root):
        raise V32WorkspaceFreezeInfrastructureError("V32_WORKSPACE_ROOT_INVALID")

    if _git(root, "branch", "--show-current") != receipt["branch"]:
        raise V32WorkspaceFreezeInfrastructureError("V32_WORKSPACE_BRANCH_DRIFT")
    if _git(root, "show", "-s", "--format=%T", receipt["frozen_commit_sha"]) != receipt["frozen_tree_sha"]:
        raise V32WorkspaceFreezeInfrastructureError("V32_WORKSPACE_TREE_DRIFT")
    try:
        subprocess.run(
            [
                FIXED_GIT_EXECUTABLE,
                "-C",
                str(root),
                "merge-base",
                "--is-ancestor",
                receipt["frozen_commit_sha"],
                "HEAD",
            ],
            check=True,
            capture_output=True,
            env=dict(FIXED_ENVIRONMENT),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise V32WorkspaceFreezeInfrastructureError(
            "V32_WORKSPACE_FROZEN_COMMIT_NOT_ANCESTOR"
        ) from exc

    status_raw = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored=no",
        binary=True,
    )
    assert isinstance(status_raw, bytes)
    entries = [row for row in status_raw.split(b"\0") if row]
    allowed = {
        row["relative_ref"]: row["physical_sha256"]
        for row in receipt["allowed_untracked_user_artifacts"]
    }
    seen: set[str] = set()
    for entry in entries:
        try:
            status = entry[:2].decode("ascii")
            relative = entry[3:].decode("utf-8")
        except UnicodeError as exc:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_STATUS_INVALID"
            ) from exc
        if status != "??" or relative not in allowed:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_NOT_CLEAN_OR_UNTRACKED_DRIFT"
            )
        path = root / relative
        if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != allowed[relative]:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_ALLOWED_USER_ARTIFACT_DRIFT"
            )
        seen.add(relative)
    if seen != set(allowed):
        raise V32WorkspaceFreezeInfrastructureError(
            "V32_WORKSPACE_ALLOWED_USER_ARTIFACT_MISSING"
        )

    for relative in receipt["relevant_paths"]:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_RELEVANT_PATH_MISSING"
            )
        committed = _git(
            root,
            "show",
            f"{receipt['frozen_commit_sha']}:{relative}",
            binary=True,
        )
        assert isinstance(committed, bytes)
        current = path.read_bytes()
        expected = receipt["relevant_path_sha256"][relative]
        if current != committed or _sha256(current) != expected:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_RELEVANT_PATH_DRIFT"
            )

    for relative in receipt["ignored_runtime_roots"]:
        probe = f"{relative}/.v32-ignore-probe"
        try:
            subprocess.run(
                [FIXED_GIT_EXECUTABLE, "-C", str(root), "check-ignore", "-q", probe],
                check=True,
                capture_output=True,
                env=dict(FIXED_ENVIRONMENT),
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_RUNTIME_ROOT_NOT_IGNORED"
            ) from exc
    if receipt.get("schema_version") == SCHEMA_VERSION_POSTCOMMIT:
        try:
            replay = replay_v32_postcommit_regression_aggregate_support_v1(
                project_root=root,
                aggregate_binding=receipt[
                    "postcommit_regression_aggregate_binding"
                ],
                expected_target_run_id=receipt[
                    "postcommit_regression_target_run_id"
                ],
                expected_qualification_run_id=receipt[
                    "postcommit_regression_qualification_run_id"
                ],
            )
        except (KeyError, V32PostCommitRegressionInfrastructureError) as exc:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_POSTCOMMIT_REGRESSION_REPLAY_FAILED"
            ) from exc
        if replay.get("full_physical_replay_verified") is not True:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_POSTCOMMIT_REGRESSION_REPLAY_FAILED"
            )
        try:
            completed = datetime.fromisoformat(
                replay["aggregate"]["completed_at"].replace("Z", "+00:00")
            ).astimezone(UTC)
            observed = datetime.fromisoformat(
                receipt["observed_at"].replace("Z", "+00:00")
            ).astimezone(UTC)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_POSTCOMMIT_REGRESSION_TIME_INVALID"
            ) from exc
        if completed > observed:
            raise V32WorkspaceFreezeInfrastructureError(
                "V32_WORKSPACE_POSTCOMMIT_REGRESSION_TIME_INVALID"
            )
    return receipt_digest


__all__ = [
    "V32WorkspaceFreezeInfrastructureError",
    "verify_live_v32_workspace_freeze_v1",
]
