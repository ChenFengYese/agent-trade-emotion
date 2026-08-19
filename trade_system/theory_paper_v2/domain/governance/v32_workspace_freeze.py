"""Typed V3.2 workspace/commit freeze receipt.

This pure contract records the exact committed implementation base that must
precede qualification.  Git inspection and byte replay belong to the
Infrastructure verifier; the receipt itself grants no research or execution
authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ..contracts.canonical import self_digest, verify_self_digest


class V32WorkspaceFreezeError(ValueError):
    """The committed workspace boundary is invalid or has drifted."""


SCHEMA_ID = "theory_paper_v32_workspace_freeze_receipt_v1"
SCHEMA_VERSION = "1.0.0"
SCHEMA_VERSION_POSTCOMMIT = "1.1.0"
DIGEST_FIELD = "workspace_freeze_receipt_digest"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_FIELDS = frozenset({"relative_ref", "physical_sha256"})
_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "receipt_id",
        "observed_at",
        "project_relative_root",
        "branch",
        "frozen_commit_sha",
        "frozen_tree_sha",
        "relevant_paths",
        "relevant_path_sha256",
        "allowed_untracked_user_artifacts",
        "ignored_runtime_roots",
        "tracked_worktree_clean",
        "index_clean",
        "untracked_state_exact_allowlist",
        "frozen_commit_must_be_ancestor_of_runtime_head",
        "relevant_paths_must_equal_frozen_commit_bytes",
        "qualification_must_postdate_observed_at",
        "authority_must_bind_receipt_physically",
        "chat_history_is_workspace_authority",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "paper_trading",
        "live_trading",
        "order_submission",
        "credential_use",
        "funds_access",
        "portfolio_mutation",
        DIGEST_FIELD,
    }
)
_FIELDS_POSTCOMMIT = _FIELDS | {
    "postcommit_regression_aggregate_binding",
    "postcommit_regression_target_run_id",
    "postcommit_regression_qualification_run_id",
}
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32WorkspaceFreezeError(code)
    return value


def _time(value: Any, code: str) -> str:
    candidate = _text(value, code)
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32WorkspaceFreezeError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != candidate
    ):
        raise V32WorkspaceFreezeError(code)
    return candidate


def _relative(value: Any, code: str, *, allow_dot: bool = False) -> str:
    candidate = _text(value, code)
    if allow_dot and candidate == ".":
        return candidate
    path = PurePosixPath(candidate)
    if (
        "\\" in candidate
        or path.is_absolute()
        or path.as_posix() != candidate
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32WorkspaceFreezeError(code)
    return candidate


def _ordered_paths(value: Any, code: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32WorkspaceFreezeError(code)
    rows = [_relative(item, code) for item in value]
    if (
        (not allow_empty and not rows)
        or rows != sorted(rows)
        or len(rows) != len(set(rows))
    ):
        raise V32WorkspaceFreezeError(code)
    return rows


def _digest_map(value: Any, paths: Sequence[str], code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or tuple(value) != tuple(paths):
        raise V32WorkspaceFreezeError(code)
    result: dict[str, str] = {}
    for path in paths:
        digest = value.get(path)
        if not isinstance(digest, str) or _HEX_64.fullmatch(digest) is None:
            raise V32WorkspaceFreezeError(code)
        result[path] = digest
    return result


def _artifacts(value: Any, code: str) -> list[dict[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32WorkspaceFreezeError(code)
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _ARTIFACT_FIELDS:
            raise V32WorkspaceFreezeError(code)
        physical = item.get("physical_sha256")
        if not isinstance(physical, str) or _HEX_64.fullmatch(physical) is None:
            raise V32WorkspaceFreezeError(code)
        rows.append(
            {
                "relative_ref": _relative(item.get("relative_ref"), code),
                "physical_sha256": physical,
            }
        )
    if (
        rows != sorted(rows, key=lambda row: row["relative_ref"])
        or len({row["relative_ref"] for row in rows}) != len(rows)
    ):
        raise V32WorkspaceFreezeError(code)
    return rows


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_use": False,
        "funds_access": False,
        "portfolio_mutation": False,
    }


def build_v32_workspace_freeze_receipt_v1(
    *,
    receipt_id: str,
    observed_at: str,
    branch: str,
    frozen_commit_sha: str,
    frozen_tree_sha: str,
    relevant_paths: Sequence[str],
    relevant_path_sha256: Mapping[str, str],
    allowed_untracked_user_artifacts: Sequence[Mapping[str, str]],
    ignored_runtime_roots: Sequence[str],
) -> dict[str, Any]:
    commit = _text(frozen_commit_sha, "V32_WORKSPACE_COMMIT_INVALID")
    tree = _text(frozen_tree_sha, "V32_WORKSPACE_TREE_INVALID")
    if _HEX_40.fullmatch(commit) is None or _HEX_40.fullmatch(tree) is None:
        raise V32WorkspaceFreezeError("V32_WORKSPACE_COMMIT_INVALID")
    paths = _ordered_paths(relevant_paths, "V32_WORKSPACE_RELEVANT_PATHS_INVALID")
    ignored = _ordered_paths(
        ignored_runtime_roots, "V32_WORKSPACE_IGNORED_ROOTS_INVALID"
    )
    if any(
        path in ignored
        or any(path.startswith(root + "/") for root in ignored)
        for path in paths
    ):
        raise V32WorkspaceFreezeError("V32_WORKSPACE_RELEVANT_PATH_IGNORED")
    artifacts = _artifacts(
        allowed_untracked_user_artifacts,
        "V32_WORKSPACE_ALLOWED_UNTRACKED_INVALID",
    )
    if any(row["relative_ref"] in paths for row in artifacts):
        raise V32WorkspaceFreezeError("V32_WORKSPACE_ALLOWED_UNTRACKED_INVALID")
    return self_digest(
        {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "receipt_id": _text(receipt_id, "V32_WORKSPACE_RECEIPT_ID_INVALID"),
            "observed_at": _time(observed_at, "V32_WORKSPACE_TIME_INVALID"),
            "project_relative_root": ".",
            "branch": _text(branch, "V32_WORKSPACE_BRANCH_INVALID"),
            "frozen_commit_sha": commit,
            "frozen_tree_sha": tree,
            "relevant_paths": paths,
            "relevant_path_sha256": _digest_map(
                relevant_path_sha256,
                paths,
                "V32_WORKSPACE_RELEVANT_DIGEST_INVALID",
            ),
            "allowed_untracked_user_artifacts": artifacts,
            "ignored_runtime_roots": ignored,
            "tracked_worktree_clean": True,
            "index_clean": True,
            "untracked_state_exact_allowlist": True,
            "frozen_commit_must_be_ancestor_of_runtime_head": True,
            "relevant_paths_must_equal_frozen_commit_bytes": True,
            "qualification_must_postdate_observed_at": True,
            "authority_must_bind_receipt_physically": True,
            "chat_history_is_workspace_authority": False,
            **_boundary(),
        },
        DIGEST_FIELD,
    )


def _postcommit_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32WorkspaceFreezeError("V32_WORKSPACE_POSTCOMMIT_BINDING_INVALID")
    result = {key: value[key] for key in _BINDING_FIELDS}
    if (
        not isinstance(result["path"], str)
        or not result["path"].endswith("/support/postcommit-regression/aggregate.json")
        or result["schema_id"]
        != "theory_paper_v32_postcommit_regression_aggregate_support_v1"
        or result["digest_field"] != "postcommit_regression_aggregate_digest"
        or not isinstance(result["semantic_digest"], str)
        or _HEX_64.fullmatch(result["semantic_digest"]) is None
        or not isinstance(result["physical_sha256"], str)
        or _HEX_64.fullmatch(result["physical_sha256"]) is None
    ):
        raise V32WorkspaceFreezeError("V32_WORKSPACE_POSTCOMMIT_BINDING_INVALID")
    _relative(result["path"], "V32_WORKSPACE_POSTCOMMIT_BINDING_INVALID")
    return result


def build_v32_workspace_freeze_receipt_v1_1(
    *,
    receipt_id: str,
    observed_at: str,
    branch: str,
    frozen_commit_sha: str,
    frozen_tree_sha: str,
    relevant_paths: Sequence[str],
    relevant_path_sha256: Mapping[str, str],
    allowed_untracked_user_artifacts: Sequence[Mapping[str, str]],
    ignored_runtime_roots: Sequence[str],
    postcommit_regression_aggregate_binding: Mapping[str, str],
    postcommit_regression_target_run_id: str,
    postcommit_regression_qualification_run_id: str,
) -> dict[str, Any]:
    """Build the mandatory post-commit-aware receipt for a new qualification.

    Version 1.0 remains verifiable only for historical byte replay.  All new
    V3.2 qualification composition calls this builder and therefore binds the
    aggregate plus its two physical execution receipts transitively.
    """

    legacy = build_v32_workspace_freeze_receipt_v1(
        receipt_id=receipt_id,
        observed_at=observed_at,
        branch=branch,
        frozen_commit_sha=frozen_commit_sha,
        frozen_tree_sha=frozen_tree_sha,
        relevant_paths=relevant_paths,
        relevant_path_sha256=relevant_path_sha256,
        allowed_untracked_user_artifacts=allowed_untracked_user_artifacts,
        ignored_runtime_roots=ignored_runtime_roots,
    )
    upgraded = {key: value for key, value in legacy.items() if key != DIGEST_FIELD}
    upgraded["schema_version"] = SCHEMA_VERSION_POSTCOMMIT
    upgraded["postcommit_regression_aggregate_binding"] = _postcommit_binding(
        postcommit_regression_aggregate_binding
    )
    upgraded["postcommit_regression_target_run_id"] = _text(
        postcommit_regression_target_run_id,
        "V32_WORKSPACE_POSTCOMMIT_IDENTITY_INVALID",
    )
    upgraded["postcommit_regression_qualification_run_id"] = _text(
        postcommit_regression_qualification_run_id,
        "V32_WORKSPACE_POSTCOMMIT_IDENTITY_INVALID",
    )
    if (
        upgraded["postcommit_regression_target_run_id"]
        == upgraded["postcommit_regression_qualification_run_id"]
    ):
        raise V32WorkspaceFreezeError(
            "V32_WORKSPACE_POSTCOMMIT_IDENTITY_INVALID"
        )
    return self_digest(upgraded, DIGEST_FIELD)


def verify_v32_workspace_freeze_receipt_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise V32WorkspaceFreezeError("V32_WORKSPACE_RECEIPT_INVALID")
    version = document.get("schema_version")
    expected_fields = (
        _FIELDS_POSTCOMMIT if version == SCHEMA_VERSION_POSTCOMMIT else _FIELDS
    )
    if set(document) != expected_fields:
        raise V32WorkspaceFreezeError("V32_WORKSPACE_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        kwargs = {
            "receipt_id": document["receipt_id"],
            "observed_at": document["observed_at"],
            "branch": document["branch"],
            "frozen_commit_sha": document["frozen_commit_sha"],
            "frozen_tree_sha": document["frozen_tree_sha"],
            "relevant_paths": document["relevant_paths"],
            "relevant_path_sha256": document["relevant_path_sha256"],
            "allowed_untracked_user_artifacts": document[
                "allowed_untracked_user_artifacts"
            ],
            "ignored_runtime_roots": document["ignored_runtime_roots"],
        }
        if version == SCHEMA_VERSION_POSTCOMMIT:
            rebuilt = build_v32_workspace_freeze_receipt_v1_1(
                **kwargs,
                postcommit_regression_aggregate_binding=document[
                    "postcommit_regression_aggregate_binding"
                ],
                postcommit_regression_target_run_id=document[
                    "postcommit_regression_target_run_id"
                ],
                postcommit_regression_qualification_run_id=document[
                    "postcommit_regression_qualification_run_id"
                ],
            )
        elif version == SCHEMA_VERSION:
            rebuilt = build_v32_workspace_freeze_receipt_v1(**kwargs)
        else:
            raise V32WorkspaceFreezeError("V32_WORKSPACE_RECEIPT_INVALID")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32WorkspaceFreezeError):
            raise
        raise V32WorkspaceFreezeError("V32_WORKSPACE_RECEIPT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32WorkspaceFreezeError("V32_WORKSPACE_RECEIPT_INVALID")
    if any(document.get(key) != value for key, value in _boundary().items()):
        raise V32WorkspaceFreezeError("V32_WORKSPACE_BOUNDARY_INVALID")
    return supplied


__all__ = [
    "DIGEST_FIELD",
    "SCHEMA_ID",
    "V32WorkspaceFreezeError",
    "build_v32_workspace_freeze_receipt_v1",
    "build_v32_workspace_freeze_receipt_v1_1",
    "verify_v32_workspace_freeze_receipt_v1",
]
