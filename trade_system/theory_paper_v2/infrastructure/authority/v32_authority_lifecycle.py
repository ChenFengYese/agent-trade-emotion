"""Two-phase, write-once composer for the V3.2 authority lifecycle.

Phase A may run only on a committed clean workspace.  It creates the frozen
support/contract/approval/manifest chain and a qualification-only authority.
Phase B first fully replays the three post-authority capability receipts,
seals one exact target-finalization intent before retirement, then creates the
bound target tail and publishes the one exact ignored current-authority
pointer.  Interrupted writes can replay only that sealed plan.  This module
performs no network, Agent, automation, account, order, credential, or funds
operation.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Callable, Mapping, Sequence

from ...application.v31_authority_freeze import document_binding
from ...application.v32_authorized_revision_orchestration import (
    SUPPORT_BUNDLE_DIGEST_FIELD,
    build_v32_authorized_revision_support_bundle_v1,
)
from ...domain.contracts.canonical import (
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ...domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    CAPABILITY_GATE_MAP,
    GATE_EVIDENCE_DIGEST_FIELD,
    PHASE_A_DIGEST_FIELD,
    Q0_Q8_GATE_IDS,
    QUALIFICATION_PHASE_PROFILE,
    QUALIFICATION_PROFILE,
    QUALIFICATION_RECEIPT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    TARGET_PHASE_PROFILE,
    TARGET_PROFILE,
    THEORY_APPROVAL_DIGEST_FIELD,
    build_v32_authority_v1,
    build_v32_authorization_receipt_v1,
    build_v32_phase_a_qualification_receipt_v1,
    build_v32_qualification_gate_evidence_v1,
    build_v32_qualification_retirement_receipt_v1,
    build_v32_runtime_manifest_v2,
    build_v32_theory_approval_receipt_v1,
    verify_v32_authority_v1,
    verify_v32_authorization_receipt_v1,
    verify_v32_phase_a_qualification_receipt_v1,
    verify_v32_qualification_gate_evidence_v1,
    verify_v32_qualification_retirement_receipt_v1,
    verify_v32_runtime_manifest,
    verify_v32_runtime_manifest_v2,
    verify_v32_theory_approval_receipt_v1,
)
from ...domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
    THEORY_VERSION,
    build_v32_experiment_contract_v1,
    verify_v32_experiment_contract_v1,
)
from ...domain.governance.v32_qualification_identity import (
    V32QualificationIdentityError,
    validate_v32_active_qualification_identity_v1,
)
from ...domain.governance.v32_preflight_gate_subject import (
    DIGEST_FIELD as PREFLIGHT_SUBJECT_DIGEST_FIELD,
    GATE_ANCHOR_ROLES,
    GATE_IMPLEMENTATION_PATHS,
    PRODUCTION_ROOT_PATHS,
    build_v32_typed_preflight_gate_subject_v1,
    verify_v32_typed_preflight_gate_subject_v1,
)
from ...domain.governance.v32_workspace_freeze import (
    DIGEST_FIELD as WORKSPACE_DIGEST_FIELD,
    SCHEMA_ID as WORKSPACE_SCHEMA_ID,
    SCHEMA_VERSION_POSTCOMMIT as WORKSPACE_POSTCOMMIT_SCHEMA_VERSION,
    build_v32_workspace_freeze_receipt_v1_1,
)
from ...domain.governance.v311_fresh_process_trace_v2 import (
    FRESH_PROCESS_TRACE_DIGEST_FIELD,
    verify_v311_fresh_process_trace_receipt_v2,
)
from ...domain.governance.v32_postcommit_regression import (
    FIXED_ENVIRONMENT,
    FIXED_GIT_EXECUTABLE,
)
from ...domain.v31_sentiment_native_projection_v2 import (
    build_v31_native_sentiment_source_registry,
)
from ...domain.v32_agent_lifecycle import (
    THEORY_DOCUMENT_DIGEST_FIELD,
    build_v32_theory_semantic_document_v1,
    verify_v32_theory_semantic_document_v1,
)
from ...domain.v32_association_preregistration import (
    DIGEST_FIELD as ASSOCIATION_DIGEST_FIELD,
    build_v32_association_preregistration,
)
from ...domain.v32_context_compaction import (
    POLICY_DIGEST_FIELD as CONTEXT_POLICY_DIGEST_FIELD,
    build_v32_context_compaction_policy_v1,
)
from ...domain.v32_cycle_audit_narrative import (
    POLICY_DIGEST_FIELD as AUDIT_POLICY_DIGEST_FIELD,
    build_v32_cycle_audit_policy_v1,
)
from ...domain.v32_data_gap_escalation import (
    POLICY_DIGEST_FIELD as DATA_GAP_POLICY_DIGEST_FIELD,
    build_v32_data_gap_manual_policy_v1,
)
from ...domain.v32_evaluation_contract import (
    DIGEST_FIELD as EVALUATION_DIGEST_FIELD,
    build_v32_evaluation_contract,
)
from ...domain.v32_environment_capability import (
    DIGEST_FIELD as ENVIRONMENT_CAPABILITY_DIGEST_FIELD,
)
from ...domain.v32_recovery_supervision import (
    POLICY_DIGEST_FIELD as RECOVERY_POLICY_DIGEST_FIELD,
    build_v32_recovery_supervision_policy_v1,
)
from ...domain.v32_runtime_support_contracts import (
    CLOCK_DIGEST_FIELD,
    OUTCOME_ADAPTER_DIGEST_FIELD,
    build_v32_clock_and_tick_policy_v1,
    build_v32_public_outcome_adapter_contract_v1,
)
from ...domain.v32_unknown_assessment import (
    POLICY_DIGEST_FIELD as UNKNOWN_POLICY_DIGEST_FIELD,
    build_v32_unknown_subjective_policy_v1,
)
from ..v32_environment_capability_adapter import (
    build_local_v32_environment_capability_profile_v1,
)
from .v31_runtime_closure_v2 import build_v31_runtime_closure_bindings_v2
from .v32_qualification_runtime_namespace import (
    V32QualificationRuntimeNamespaceError,
    assert_v32_qualification_runtime_namespace_v1,
    build_v32_qualification_runtime_paths_v1,
)
from .v32_secure_write_once_store import (
    secure_binding_for_existing_document,
    secure_preflight_write_once_json,
    secure_publish_json_directory_bundle,
    secure_read_bytes,
    secure_write_once_json,
)
from .v32_current_research import (
    V32ActualCapabilityFullReplayVerifier,
    V32_CURRENT_RESEARCH_AUTHORITY_PATH,
    V32CurrentResearchAuthorityError,
    load_v32_current_research_authority,
    replay_v32_actual_capability_qualification_receipt,
    replay_v32_legacy_predecessor,
)
from .v32_workspace_freeze import verify_live_v32_workspace_freeze_v1
from .v32_postcommit_regression import (
    V32PostCommitRegressionInfrastructureError,
    load_v32_postcommit_regression_prequalification_support_v1,
)


# One pre-existing user-owned duplicate is intentionally outside the research
# commit.  This is an exact-path exception, not a general dirty-worktree or
# untracked-files waiver.  Its bytes are bound into the workspace receipt when
# it is present, and the runtime verifier rejects deletion, replacement, or any
# additional untracked path after qualification.
_ALLOWED_UNTRACKED_USER_ARTIFACTS = (
    "archive/user-preserved/THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md",
)


class V32AuthorityLifecycleComposerError(ValueError):
    """The V3.2 two-phase authority lifecycle failed closed."""


_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_PHASE_A_TIME_KEYS = frozenset(
    {
        "workspace_observed_at",
        "support_frozen_at",
        "runtime_frozen_at",
        "approved_at",
        "manifest_created_at",
        "qualification_gate_evaluated_at",
        "qualification_phase_evaluated_at",
        "qualification_authorization_issued_at",
        "qualification_authority_recorded_at",
    }
)
_PHASE_B_TIME_KEYS = frozenset(
    {
        "retired_at",
        "target_gate_evaluated_at",
        "target_phase_evaluated_at",
        "target_authorization_issued_at",
        "target_authority_recorded_at",
    }
)
_TARGET_FINALIZATION_INTENT_SCHEMA_ID = (
    "theory_paper_v32_target_finalization_intent_v1"
)
_TARGET_FINALIZATION_INTENT_DIGEST_FIELD = "target_finalization_intent_digest"


def _root(value: Path) -> Path:
    try:
        supplied = Path(value)
        if supplied.is_symlink():
            raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_ROOT_INVALID")
        root = supplied.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_ROOT_INVALID"
        ) from exc
    if not root.is_dir():
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_ROOT_INVALID")
    return root


def _relative(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32AuthorityLifecycleComposerError(code)
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32AuthorityLifecycleComposerError(code)
    return value


def _join(root_ref: str, suffix: str) -> str:
    return PurePosixPath(_relative(root_ref, "V32_LIFECYCLE_RUNTIME_ROOT_INVALID"), suffix).as_posix()


def _active_runtime_namespace(
    root: Path,
    *,
    target_run_id: Any,
    qualification_run_id: Any,
    supplied_runtime_root: Any,
    require_root: bool,
) -> tuple[str, str, str]:
    """Validate identity and prove the sole legal physical namespace."""

    try:
        target, qualification = validate_v32_active_qualification_identity_v1(
            target_run_id=target_run_id,
            qualification_run_id=qualification_run_id,
        )
        expected = build_v32_qualification_runtime_paths_v1(qualification)
        supplied = _relative(
            supplied_runtime_root, "V32_LIFECYCLE_RUNTIME_ROOT_INVALID"
        )
        if supplied != expected["root"]:
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_RUNTIME_ROOT_INVALID"
            )
        assert_v32_qualification_runtime_namespace_v1(
            project_root=root,
            qualification_run_id=qualification,
            require_root=require_root,
        )
    except V32AuthorityLifecycleComposerError:
        raise
    except (V32QualificationIdentityError, V32QualificationRuntimeNamespaceError) as exc:
        raise V32AuthorityLifecycleComposerError(str(exc)) from exc
    return target, qualification, expected["root"]


def _require_exact_binding_path(
    binding: Mapping[str, Any], *, expected_path: str, code: str
) -> None:
    if not isinstance(binding, Mapping) or binding.get("path") != expected_path:
        raise V32AuthorityLifecycleComposerError(code)


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32AuthorityLifecycleComposerError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32AuthorityLifecycleComposerError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32AuthorityLifecycleComposerError(code)
    return parsed.astimezone(UTC)


def _times(value: Any, expected: frozenset[str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_TIMES_INVALID")
    return {
        key: str(value[key])
        for key in sorted(expected)
        if _moment(value[key], "V32_LIFECYCLE_TIMES_INVALID")
    }


def _build_target_finalization_intent_v1(
    *,
    target_run_id: str,
    qualification_run_id: str,
    qualification_authority_binding: Mapping[str, Any],
    qualification_receipt_binding: Mapping[str, Any],
    phase_times: Mapping[str, Any],
    qualification_retirement_binding: Mapping[str, Any],
) -> dict[str, Any]:
    return self_digest(
        {
            "schema_id": _TARGET_FINALIZATION_INTENT_SCHEMA_ID,
            "schema_version": "1.0.0",
            "target_run_id": str(target_run_id),
            "qualification_run_id": str(qualification_run_id),
            "qualification_authority_binding": dict(
                qualification_authority_binding
            ),
            "qualification_receipt_binding": dict(
                qualification_receipt_binding
            ),
            "phase_times": _times(phase_times, _PHASE_B_TIME_KEYS),
            "qualification_retirement_binding": dict(
                qualification_retirement_binding
            ),
            "recovery_policy": (
                "REPLAY_EXACT_SEALED_PLAN_WITHOUT_NETWORK_OR_AGENT_ATTEMPT"
            ),
            "network_calls": 0,
            "authority_boundary": "PUBLIC_LOCAL_NON_EXECUTABLE",
        },
        _TARGET_FINALIZATION_INTENT_DIGEST_FIELD,
    )


def _verify_target_finalization_intent_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or document.get(
        "schema_id"
    ) != _TARGET_FINALIZATION_INTENT_SCHEMA_ID:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_INTENT_INVALID"
        )
    try:
        return verify_self_digest(
            document, _TARGET_FINALIZATION_INTENT_DIGEST_FIELD
        )
    except (TypeError, ValueError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_INTENT_INVALID"
        ) from exc


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            [FIXED_GIT_EXECUTABLE, "-C", str(root), *args],
            check=True,
            capture_output=True,
            env=dict(FIXED_ENVIRONMENT),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_GIT_CHECK_FAILED"
        ) from exc
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def _is_ignored(root: Path, relative_ref: str) -> bool:
    result = subprocess.run(
        [FIXED_GIT_EXECUTABLE, "-C", str(root), "check-ignore", "-q", "--no-index", relative_ref],
        check=False,
        capture_output=True,
        env=dict(FIXED_ENVIRONMENT),
    )
    if result.returncode not in {0, 1}:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_GIT_CHECK_FAILED"
        )
    return result.returncode == 0


def _allowed_untracked_user_artifacts(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for relative_ref in _ALLOWED_UNTRACKED_USER_ARTIFACTS:
        path = root / relative_ref
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_ALLOWED_USER_ARTIFACT_INVALID"
            )
        rows.append(
            {
                "relative_ref": relative_ref,
                "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return rows


def _assert_clean_committed_workspace(root: Path, runtime_root: str) -> None:
    if _git(root, "rev-parse", "--show-toplevel") != str(root):
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_WORKSPACE_INVALID")
    branch = _git(root, "branch", "--show-current")
    if not isinstance(branch, str) or not branch:
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_WORKSPACE_INVALID")
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
    allowed = {
        row["relative_ref"]: row["physical_sha256"]
        for row in _allowed_untracked_user_artifacts(root)
    }
    seen: set[str] = set()
    for entry in (row for row in status.split(b"\0") if row):
        try:
            state = entry[:2].decode("ascii")
            relative_ref = entry[3:].decode("utf-8")
        except UnicodeError as exc:
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_WORKSPACE_NOT_CLEAN"
            ) from exc
        path = root / relative_ref
        if (
            state != "??"
            or relative_ref not in allowed
            or relative_ref in seen
            or path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest()
            != allowed[relative_ref]
        ):
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_WORKSPACE_NOT_CLEAN"
            )
        seen.add(relative_ref)
    if seen != set(allowed):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_WORKSPACE_NOT_CLEAN"
        )
    pointer = V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix()
    if (
        not _is_ignored(root, pointer)
        or _is_ignored(root, "config/.v32-unrelated-ignore-scope-probe")
        or not _is_ignored(root, f"{runtime_root}/.v32-ignore-probe")
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_IGNORE_SCOPE_INVALID"
        )
    pointer_path = root / pointer
    if pointer_path.exists() or pointer_path.is_symlink():
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_CURRENT_POINTER_PREEXISTS"
        )


def _canonical_binding(
    relative_ref: str, document: Mapping[str, Any], digest_field: str
) -> dict[str, str]:
    return document_binding(
        path=_relative(relative_ref, "V32_LIFECYCLE_PATH_INVALID"),
        document=document,
        digest_field=digest_field,
    )


def _revision_binding(binding: Mapping[str, str]) -> dict[str, str]:
    return {
        "relative_ref": binding["path"],
        "schema_id": binding["schema_id"],
        "digest_field": binding["digest_field"],
        "semantic_digest": binding["semantic_digest"],
        "physical_sha256": binding["physical_sha256"],
    }


def _persist_batch(
    root: Path,
    artifacts: Sequence[tuple[str, Mapping[str, Any], str]],
) -> dict[str, dict[str, str]]:
    paths = [path for path, _, _ in artifacts]
    if len(paths) != len(set(paths)):
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_PATH_DUPLICATE")
    try:
        for path, document, _ in artifacts:
            secure_preflight_write_once_json(root, path, document)
        bindings = {
            path: secure_write_once_json(
                root, path, document, digest_field=digest_field
            )
            for path, document, digest_field in artifacts
        }
    except (OSError, TypeError, ValueError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_WRITE_ONCE_FAILED"
        ) from exc
    for path, document, digest_field in artifacts:
        try:
            recovered = secure_binding_for_existing_document(
                root, path, digest_field=digest_field
            )
        except (OSError, TypeError, ValueError) as exc:
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_READBACK_FAILED"
            ) from exc
        if recovered != bindings[path]:
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_READBACK_FAILED"
            )
    return bindings


def _persist_atomic_runtime_bundle(
    root: Path,
    *,
    runtime_root: str,
    artifacts: Sequence[tuple[str, Mapping[str, Any], str]],
) -> dict[str, dict[str, str]]:
    """Publish the complete Phase-A authority as one directory boundary."""

    paths = [path for path, _, _ in artifacts]
    if len(paths) != len(set(paths)) or any(
        not path.startswith(f"{runtime_root}/") for path in paths
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_PATH_DUPLICATE"
        )
    try:
        return secure_publish_json_directory_bundle(
            root,
            bundle_relative_ref=runtime_root,
            documents=[
                {
                    "relative_ref": path,
                    "document": document,
                    "schema_id": str(document["schema_id"]),
                    "digest_field": digest_field,
                }
                for path, document, digest_field in artifacts
            ],
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_WRITE_ONCE_FAILED"
        ) from exc


def _workspace_receipt(
    root: Path,
    *,
    runtime_root: str,
    observed_at: str,
    receipt_id: str,
    postcommit_regression_aggregate_binding: Mapping[str, str],
    target_run_id: str,
    qualification_run_id: str,
) -> dict[str, Any]:
    commit = str(_git(root, "rev-parse", "HEAD"))
    tree = str(_git(root, "show", "-s", "--format=%T", "HEAD"))
    branch = str(_git(root, "branch", "--show-current"))
    rows = str(_git(root, "ls-files")).splitlines()
    paths = sorted(row for row in rows if row)
    return build_v32_workspace_freeze_receipt_v1_1(
        receipt_id=receipt_id,
        observed_at=observed_at,
        branch=branch,
        frozen_commit_sha=commit,
        frozen_tree_sha=tree,
        relevant_paths=paths,
        relevant_path_sha256={
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in paths
        },
        allowed_untracked_user_artifacts=_allowed_untracked_user_artifacts(root),
        ignored_runtime_roots=[runtime_root],
        postcommit_regression_aggregate_binding=(
            postcommit_regression_aggregate_binding
        ),
        postcommit_regression_target_run_id=target_run_id,
        postcommit_regression_qualification_run_id=qualification_run_id,
    )


def _preflight_anchor_set(
    *,
    predecessor: Mapping[str, str],
    approval: Mapping[str, str],
    contract: Mapping[str, str],
    manifest: Mapping[str, str],
    support: Mapping[str, Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    return {
        "clock_policy": support["clock_policy_digest"],
        "experiment_contract": contract,
        "outcome_adapter_contract": support[
            "outcome_adapter_contract_digest"
        ],
        "predecessor_authority": predecessor,
        "runtime_manifest": manifest,
        "theory_approval": approval,
    }


def _build_gate_artifacts(
    *,
    runtime_root: str,
    directory: str,
    profile: str,
    run_id: str,
    target_run_id: str,
    evaluated_at: str,
    implementation_bindings: Mapping[str, str],
    anchors: Mapping[str, Mapping[str, str]],
    actual_capability_bindings: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[
    list[tuple[str, Mapping[str, Any], str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, Any]],
]:
    artifacts: list[tuple[str, Mapping[str, Any], str]] = []
    gate_bindings: dict[str, dict[str, str]] = {}
    gates: dict[str, dict[str, Any]] = {}
    capability_by_gate = {
        gate: capability for capability, gate in CAPABILITY_GATE_MAP.items()
    }
    for gate_id in Q0_Q8_GATE_IDS:
        capability = capability_by_gate.get(gate_id)
        if profile == TARGET_PHASE_PROFILE and capability is not None:
            if actual_capability_bindings is None:
                raise V32AuthorityLifecycleComposerError(
                    "V32_LIFECYCLE_ACTUAL_CAPABILITIES_REQUIRED"
                )
            subjects = [actual_capability_bindings[capability]]
        else:
            required_paths = GATE_IMPLEMENTATION_PATHS[gate_id]
            if any(path not in implementation_bindings for path in required_paths):
                raise V32AuthorityLifecycleComposerError(
                    f"V32_LIFECYCLE_GATE_IMPLEMENTATION_MISSING:{gate_id}"
                )
            subject = build_v32_typed_preflight_gate_subject_v1(
                subject_id=f"{run_id}:{gate_id.lower()}:typed-preflight",
                gate_id=gate_id,
                profile=profile,
                run_id=run_id,
                target_run_id=target_run_id,
                evaluated_at=evaluated_at,
                implementation_bindings={
                    path: implementation_bindings[path]
                    for path in required_paths
                },
                anchor_bindings={
                    role: anchors[role] for role in GATE_ANCHOR_ROLES[gate_id]
                },
            )
            verify_v32_typed_preflight_gate_subject_v1(subject)
            subject_path = _join(
                runtime_root, f"{directory}/subjects/{gate_id.lower()}.json"
            )
            subject_binding = _canonical_binding(
                subject_path, subject, PREFLIGHT_SUBJECT_DIGEST_FIELD
            )
            artifacts.append(
                (subject_path, subject, PREFLIGHT_SUBJECT_DIGEST_FIELD)
            )
            subjects = [subject_binding]
        gate = build_v32_qualification_gate_evidence_v1(
            gate_id=gate_id,
            profile=profile,
            run_id=run_id,
            target_run_id=target_run_id,
            evaluated_at=evaluated_at,
            subject_bindings=subjects,
        )
        verify_v32_qualification_gate_evidence_v1(gate)
        gate_path = _join(
            runtime_root, f"{directory}/gates/{gate_id.lower()}.json"
        )
        gate_binding = _canonical_binding(
            gate_path, gate, GATE_EVIDENCE_DIGEST_FIELD
        )
        artifacts.append((gate_path, gate, GATE_EVIDENCE_DIGEST_FIELD))
        gate_bindings[gate_id] = gate_binding
        gates[gate_id] = gate
    return artifacts, gate_bindings, gates


def prepare_v32_qualification_authority(
    *,
    project_root: Path,
    runtime_root_relative_ref: str,
    target_run_id: str,
    qualification_run_id: str,
    theory_relative_ref: str,
    phase_times: Mapping[str, str],
    fresh_process_trace_receipt: Mapping[str, Any],
    public_network_status: str,
    codex_delivery_status: str,
    automation_status: str,
    tool_names: Sequence[str],
    localization_adapters: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create Phase A artifacts; never exercise or claim an actual capability."""

    root = _root(project_root)
    target, qualification, runtime_root = _active_runtime_namespace(
        root,
        target_run_id=target_run_id,
        qualification_run_id=qualification_run_id,
        supplied_runtime_root=runtime_root_relative_ref,
        require_root=False,
    )
    times = _times(phase_times, _PHASE_A_TIME_KEYS)
    chronology = [
        _moment(times[key], "V32_LIFECYCLE_CHRONOLOGY_INVALID")
        for key in (
            "workspace_observed_at",
            "support_frozen_at",
            "runtime_frozen_at",
            "approved_at",
            "manifest_created_at",
            "qualification_gate_evaluated_at",
            "qualification_phase_evaluated_at",
            "qualification_authorization_issued_at",
            "qualification_authority_recorded_at",
        )
    ]
    if not (
        chronology[0]
        <= chronology[1]
        <= chronology[2]
        <= chronology[3]
        <= chronology[4]
        < chronology[5]
        <= chronology[6]
        <= chronology[7]
        <= chronology[8]
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_CHRONOLOGY_INVALID"
        )
    _assert_clean_committed_workspace(root, runtime_root)
    theory_ref = _relative(theory_relative_ref, "V32_LIFECYCLE_THEORY_INVALID")
    theory_path = root / theory_ref
    if theory_path.is_symlink() or not theory_path.is_file():
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_THEORY_INVALID")
    try:
        theory_bytes = theory_path.read_bytes()
        theory_bytes.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_THEORY_INVALID"
        ) from exc
    theory_sha = hashlib.sha256(theory_bytes).hexdigest()
    theory_semantic_document = build_v32_theory_semantic_document_v1(
        theory_source_binding={
            "path": theory_ref,
            "version": THEORY_VERSION,
            "review_status": "FROZEN_APPROVED",
            "physical_sha256": theory_sha,
        },
        markdown_utf8=theory_bytes.decode("utf-8"),
    )
    verify_v32_theory_semantic_document_v1(theory_semantic_document)
    theory_semantic_path = _join(runtime_root, "theory-semantic-document.json")
    theory_semantic_binding = _canonical_binding(
        theory_semantic_path,
        theory_semantic_document,
        THEORY_DOCUMENT_DIGEST_FIELD,
    )
    legacy = replay_v32_legacy_predecessor(root)
    predecessor_binding = legacy["predecessor_authority_binding"]

    try:
        verify_v311_fresh_process_trace_receipt_v2(
            fresh_process_trace_receipt
        )
        fresh_trace_paths = tuple(
            fresh_process_trace_receipt["observed_project_python_paths"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FRESH_PROCESS_TRACE_INVALID"
        ) from exc
    if (
        tuple(fresh_process_trace_receipt.get("production_root_paths", ()))
        != tuple(PRODUCTION_ROOT_PATHS)
        or _moment(
            fresh_process_trace_receipt.get("completed_at"),
            "V32_LIFECYCLE_FRESH_PROCESS_TRACE_INVALID",
        )
        > chronology[0]
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FRESH_PROCESS_TRACE_INVALID"
        )
    fresh_trace_path = _join(
        runtime_root, "support/fresh-process-trace.json"
    )
    fresh_trace_binding = _canonical_binding(
        fresh_trace_path,
        fresh_process_trace_receipt,
        FRESH_PROCESS_TRACE_DIGEST_FIELD,
    )
    implementation_bindings = build_v31_runtime_closure_bindings_v2(
        project_root=root,
        production_root_paths=PRODUCTION_ROOT_PATHS,
        trace_paths=fresh_trace_paths,
    )
    if any(
        path not in implementation_bindings
        for paths in GATE_IMPLEMENTATION_PATHS.values()
        for path in paths
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_RUNTIME_CLOSURE_INCOMPLETE"
        )

    frozen_at = times["support_frozen_at"]
    try:
        postcommit_regression = (
            load_v32_postcommit_regression_prequalification_support_v1(
                project_root=root,
                target_run_id=target,
                qualification_run_id=qualification,
            )
        )
    except V32PostCommitRegressionInfrastructureError as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_POSTCOMMIT_REGRESSION_REQUIRED"
        ) from exc
    if _moment(
        postcommit_regression["aggregate"]["completed_at"],
        "V32_LIFECYCLE_POSTCOMMIT_REGRESSION_TIME_INVALID",
    ) > chronology[0]:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_POSTCOMMIT_REGRESSION_TIME_INVALID"
        )
    workspace = _workspace_receipt(
        root,
        runtime_root=runtime_root,
        observed_at=times["workspace_observed_at"],
        receipt_id=f"{target}:workspace-freeze",
        postcommit_regression_aggregate_binding=postcommit_regression[
            "aggregate_binding"
        ],
        target_run_id=target,
        qualification_run_id=qualification,
    )
    association = build_v32_association_preregistration(
        run_scope_id=target, frozen_at=frozen_at
    )
    evaluation = build_v32_evaluation_contract(
        association_preregistration=association,
        run_scope_id=target,
        frozen_at=frozen_at,
    )
    clock_policy = build_v32_clock_and_tick_policy_v1(
        run_scope_id=target, frozen_at=frozen_at
    )
    outcome_adapter = build_v32_public_outcome_adapter_contract_v1(
        run_scope_id=target, frozen_at=frozen_at
    )
    recovery = build_v32_recovery_supervision_policy_v1(
        policy_id=f"{target}:recovery-supervision", frozen_at=frozen_at
    )
    twelve_axis = build_v31_native_sentiment_source_registry()
    context = build_v32_context_compaction_policy_v1(
        policy_id=f"{target}:context-compaction",
        run_scope_id=target,
        frozen_at=frozen_at,
    )
    unknown = build_v32_unknown_subjective_policy_v1(
        policy_id=f"{target}:unknown-subjective",
        run_scope_id=target,
        frozen_at=frozen_at,
    )
    data_gap = build_v32_data_gap_manual_policy_v1(
        policy_id=f"{target}:data-gap-manual",
        run_scope_id=target,
        frozen_at=frozen_at,
    )
    audit = build_v32_cycle_audit_policy_v1(
        policy_id=f"{target}:cycle-audit",
        run_scope_id=target,
        frozen_at=frozen_at,
    )
    environment = build_local_v32_environment_capability_profile_v1(
        profile_id=f"{target}:environment",
        run_scope_id=target,
        frozen_at=frozen_at,
        project_root=root,
        public_network_status=public_network_status,
        codex_delivery_status=codex_delivery_status,
        automation_status=automation_status,
        tool_names=tool_names,
        localization_adapters=localization_adapters,
    )

    component_specs = {
        "context_compaction_policy": (
            "support/revision/context.json",
            context,
            CONTEXT_POLICY_DIGEST_FIELD,
        ),
        "cycle_audit_policy": (
            "support/revision/audit.json",
            audit,
            AUDIT_POLICY_DIGEST_FIELD,
        ),
        "data_gap_manual_policy": (
            "support/revision/data-gap.json",
            data_gap,
            DATA_GAP_POLICY_DIGEST_FIELD,
        ),
        "environment_capability_profile": (
            "support/revision/environment.json",
            environment,
            ENVIRONMENT_CAPABILITY_DIGEST_FIELD,
        ),
        "unknown_subjective_policy": (
            "support/revision/unknown.json",
            unknown,
            UNKNOWN_POLICY_DIGEST_FIELD,
        ),
    }
    component_bindings = {
        role: _canonical_binding(_join(runtime_root, suffix), document, digest)
        for role, (suffix, document, digest) in component_specs.items()
    }
    revision_bundle = build_v32_authorized_revision_support_bundle_v1(
        support_bundle_id=f"{target}:authorized-revision-support",
        run_scope_id=target,
        frozen_at=frozen_at,
        context_compaction_policy=context,
        context_compaction_policy_binding=_revision_binding(
            component_bindings["context_compaction_policy"]
        ),
        unknown_subjective_policy=unknown,
        unknown_subjective_policy_binding=_revision_binding(
            component_bindings["unknown_subjective_policy"]
        ),
        data_gap_manual_policy=data_gap,
        data_gap_manual_policy_binding=_revision_binding(
            component_bindings["data_gap_manual_policy"]
        ),
        cycle_audit_policy=audit,
        cycle_audit_policy_binding=_revision_binding(
            component_bindings["cycle_audit_policy"]
        ),
        environment_capability_profile=environment,
        environment_capability_profile_binding=_revision_binding(
            component_bindings["environment_capability_profile"]
        ),
    )

    support_specs = {
        "association_preregistration_digest": (
            "support/association.json",
            association,
            ASSOCIATION_DIGEST_FIELD,
        ),
        "authorized_revision_support_bundle_digest": (
            "support/revision-bundle.json",
            revision_bundle,
            SUPPORT_BUNDLE_DIGEST_FIELD,
        ),
        "clock_policy_digest": (
            "support/clock.json",
            clock_policy,
            CLOCK_DIGEST_FIELD,
        ),
        "evaluation_contract_digest": (
            "support/evaluation.json",
            evaluation,
            EVALUATION_DIGEST_FIELD,
        ),
        "outcome_adapter_contract_digest": (
            "support/outcome-adapter.json",
            outcome_adapter,
            OUTCOME_ADAPTER_DIGEST_FIELD,
        ),
        "recovery_supervision_policy_digest": (
            "support/recovery.json",
            recovery,
            RECOVERY_POLICY_DIGEST_FIELD,
        ),
        "twelve_axis_source_registry_digest": (
            "support/twelve-axis.json",
            twelve_axis,
            "registry_digest",
        ),
        "workspace_freeze_receipt_digest": (
            "support/workspace-freeze.json",
            workspace,
            WORKSPACE_DIGEST_FIELD,
        ),
    }
    support_bindings = {
        role: _canonical_binding(_join(runtime_root, suffix), document, digest)
        for role, (suffix, document, digest) in support_specs.items()
    }
    support_digests = {
        role: document[digest]
        for role, (_, document, digest) in support_specs.items()
    }
    contract = build_v32_experiment_contract_v1(
        contract_id=f"{target}:experiment-contract",
        run_id=target,
        frozen_at=frozen_at,
        theory_relative_ref=theory_ref,
        theory_physical_sha256=theory_sha,
        theory_semantic_digest=theory_semantic_document[
            THEORY_DOCUMENT_DIGEST_FIELD
        ],
        support_bindings=support_digests,
    )
    verify_v32_experiment_contract_v1(contract)
    contract_path = _join(runtime_root, "experiment-contract.json")
    contract_binding = _canonical_binding(
        contract_path, contract, EXPERIMENT_CONTRACT_DIGEST_FIELD
    )
    approval = build_v32_theory_approval_receipt_v1(
        approval_id=f"{target}:theory-approval",
        approved_at=times["approved_at"],
        theory_relative_ref=theory_ref,
        theory_physical_sha256=theory_sha,
        theory_semantic_digest=theory_semantic_document[
            THEORY_DOCUMENT_DIGEST_FIELD
        ],
    )
    verify_v32_theory_approval_receipt_v1(approval)
    approval_path = _join(runtime_root, "theory-approval.json")
    approval_binding = _canonical_binding(
        approval_path, approval, THEORY_APPROVAL_DIGEST_FIELD
    )
    manifest = build_v32_runtime_manifest_v2(
        manifest_id=f"{target}:runtime-manifest",
        created_at=times["manifest_created_at"],
        runtime_frozen_at=times["runtime_frozen_at"],
        target_run_id=target,
        qualification_run_id=qualification,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        theory_semantic_document_binding=theory_semantic_binding,
        support_document_bindings=support_bindings,
        production_root_paths=PRODUCTION_ROOT_PATHS,
        fresh_trace_paths=fresh_trace_paths,
        fresh_process_trace_binding=fresh_trace_binding,
        implementation_bindings=implementation_bindings,
    )
    verify_v32_runtime_manifest_v2(manifest)
    manifest_path = _join(runtime_root, "runtime-manifest.json")
    manifest_binding = _canonical_binding(
        manifest_path, manifest, RUNTIME_MANIFEST_DIGEST_FIELD
    )
    anchors = _preflight_anchor_set(
        predecessor=predecessor_binding,
        approval=approval_binding,
        contract=contract_binding,
        manifest=manifest_binding,
        support=support_bindings,
    )
    gate_artifacts, gate_bindings, gates = _build_gate_artifacts(
        runtime_root=runtime_root,
        directory="qualification",
        profile=QUALIFICATION_PHASE_PROFILE,
        run_id=qualification,
        target_run_id=target,
        evaluated_at=times["qualification_gate_evaluated_at"],
        implementation_bindings=implementation_bindings,
        anchors=anchors,
    )
    phase = build_v32_phase_a_qualification_receipt_v1(
        phase_id=f"{qualification}:phase-a",
        profile=QUALIFICATION_PHASE_PROFILE,
        run_id=qualification,
        target_run_id=target,
        evaluated_at=times["qualification_phase_evaluated_at"],
        theory_approval_digest=approval[THEORY_APPROVAL_DIGEST_FIELD],
        experiment_contract_digest=contract[EXPERIMENT_CONTRACT_DIGEST_FIELD],
        runtime_manifest_digest=manifest[RUNTIME_MANIFEST_DIGEST_FIELD],
        q0_q8_evidence_bindings=gate_bindings,
        predecessor_retirement_digest=None,
    )
    verify_v32_phase_a_qualification_receipt_v1(phase)
    phase_path = _join(runtime_root, "qualification/phase-a.json")
    phase_binding = _canonical_binding(phase_path, phase, PHASE_A_DIGEST_FIELD)
    authorization = build_v32_authorization_receipt_v1(
        authorization_id=f"{qualification}:authorization",
        profile=QUALIFICATION_PROFILE,
        issued_at=times["qualification_authorization_issued_at"],
        run_id=qualification,
        target_run_id=target,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=phase_binding,
        qualification_retirement_binding=None,
    )
    verify_v32_authorization_receipt_v1(authorization)
    authorization_path = _join(runtime_root, "qualification/authorization.json")
    authorization_binding = _canonical_binding(
        authorization_path, authorization, AUTHORIZATION_RECEIPT_DIGEST_FIELD
    )
    authority = build_v32_authority_v1(
        authority_id=f"{qualification}:authority",
        profile=QUALIFICATION_PROFILE,
        recorded_at=times["qualification_authority_recorded_at"],
        run_id=qualification,
        target_run_id=target,
        predecessor_authority_binding=predecessor_binding,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=phase_binding,
        authorization_receipt_binding=authorization_binding,
        qualification_retirement_binding=None,
    )
    verify_v32_authority_v1(authority)
    authority_path = _join(runtime_root, "qualification/authority.json")
    authority_binding = _canonical_binding(
        authority_path, authority, AUTHORITY_DIGEST_FIELD
    )

    artifacts: list[tuple[str, Mapping[str, Any], str]] = []
    artifacts.append(
        (
            fresh_trace_path,
            fresh_process_trace_receipt,
            FRESH_PROCESS_TRACE_DIGEST_FIELD,
        )
    )
    artifacts.extend(postcommit_regression["support_artifacts"])
    artifacts.extend(
        (
            _join(runtime_root, suffix),
            document,
            digest,
        )
        for suffix, document, digest in component_specs.values()
    )
    artifacts.extend(
        (_join(runtime_root, suffix), document, digest)
        for suffix, document, digest in support_specs.values()
    )
    artifacts.extend(
        [
            (contract_path, contract, EXPERIMENT_CONTRACT_DIGEST_FIELD),
            (approval_path, approval, THEORY_APPROVAL_DIGEST_FIELD),
            (
                theory_semantic_path,
                theory_semantic_document,
                THEORY_DOCUMENT_DIGEST_FIELD,
            ),
            (manifest_path, manifest, RUNTIME_MANIFEST_DIGEST_FIELD),
            *gate_artifacts,
            (phase_path, phase, PHASE_A_DIGEST_FIELD),
            (
                authorization_path,
                authorization,
                AUTHORIZATION_RECEIPT_DIGEST_FIELD,
            ),
            (authority_path, authority, AUTHORITY_DIGEST_FIELD),
        ]
    )
    persisted = _persist_atomic_runtime_bundle(
        root, runtime_root=runtime_root, artifacts=artifacts
    )
    try:
        assert_v32_qualification_runtime_namespace_v1(
            project_root=root,
            qualification_run_id=qualification,
            require_root=True,
        )
    except V32QualificationRuntimeNamespaceError as exc:
        raise V32AuthorityLifecycleComposerError(str(exc)) from exc
    if persisted[authority_path] != authority_binding:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_QUALIFICATION_AUTHORITY_DRIFT"
        )
    verify_live_v32_workspace_freeze_v1(project_root=root, receipt=workspace)
    return {
        "status": "QUALIFICATION_AUTHORITY_READY",
        "runtime_root_relative_ref": runtime_root,
        "target_run_id": target,
        "qualification_run_id": qualification,
        "support_documents": {
            role: document for role, (_, document, _) in support_specs.items()
        },
        "support_document_bindings": support_bindings,
        "postcommit_regression_support": postcommit_regression,
        "theory_approval": approval,
        "theory_approval_binding": approval_binding,
        "experiment_contract": contract,
        "experiment_contract_binding": contract_binding,
        "runtime_manifest": manifest,
        "runtime_manifest_binding": manifest_binding,
        "theory_semantic_document": theory_semantic_document,
        "theory_semantic_document_binding": theory_semantic_binding,
        "qualification_gates": gates,
        "qualification_gate_bindings": gate_bindings,
        "qualification_phase": phase,
        "qualification_phase_binding": phase_binding,
        "qualification_authorization": authorization,
        "qualification_authorization_binding": authorization_binding,
        "qualification_authority": authority,
        "qualification_authority_binding": authority_binding,
        "current_pointer_written": False,
        "network_calls": 0,
        "authority_boundary": "PUBLIC_LOCAL_NON_EXECUTABLE",
    }


def _load_bound(
    root: Path,
    binding: Mapping[str, Any],
    *,
    schema_id: str,
    digest_field: str,
    verifier: Callable[[Mapping[str, Any]], str],
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_FIELDS:
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_BINDING_INVALID")
    path = _relative(binding.get("path"), "V32_LIFECYCLE_BINDING_INVALID")
    target = root / path
    if target.is_symlink() or not target.is_file():
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_BINDING_INVALID")
    try:
        document = load_json_strict(target)
        semantic = verifier(document)
        recovered = secure_binding_for_existing_document(
            root, path, digest_field=digest_field
        )
    except (OSError, TypeError, ValueError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_BINDING_INVALID"
        ) from exc
    if (
        document.get("schema_id") != schema_id
        or semantic != binding.get("semantic_digest")
        or recovered != dict(binding)
    ):
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_BINDING_INVALID")
    return document, recovered


def _load_target_finalization_intent(
    root: Path, intent_path: str
) -> tuple[dict[str, Any], dict[str, str]] | None:
    try:
        if secure_read_bytes(root, intent_path, missing_ok=True) is None:
            return None
        binding = secure_binding_for_existing_document(
            root,
            intent_path,
            digest_field=_TARGET_FINALIZATION_INTENT_DIGEST_FIELD,
        )
        return _load_bound(
            root,
            binding,
            schema_id=_TARGET_FINALIZATION_INTENT_SCHEMA_ID,
            digest_field=_TARGET_FINALIZATION_INTENT_DIGEST_FIELD,
            verifier=_verify_target_finalization_intent_v1,
        )
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AuthorityLifecycleComposerError):
            raise
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_INTENT_INVALID"
        ) from exc


def load_v32_target_finalization_phase_times_if_started(
    *,
    project_root: Path,
    runtime_root_relative_ref: str,
    expected_target_run_id: str,
    expected_qualification_run_id: str,
    qualification_authority_binding: Mapping[str, Any],
    qualification_receipt_binding: Mapping[str, Any],
) -> dict[str, str] | None:
    """Return one sealed Phase-B clock plan, or ``None`` before first write.

    This performs local write-once evidence replay only.  In particular it
    does not call a public source, Agent, monitor, account, or order adapter.
    """

    root = _root(project_root)
    target, qualification, runtime_root = _active_runtime_namespace(
        root,
        target_run_id=expected_target_run_id,
        qualification_run_id=expected_qualification_run_id,
        supplied_runtime_root=runtime_root_relative_ref,
        require_root=True,
    )
    _require_exact_binding_path(
        qualification_authority_binding,
        expected_path=_join(runtime_root, "qualification/authority.json"),
        code="V32_LIFECYCLE_QUALIFICATION_AUTHORITY_BINDING_INVALID",
    )
    _require_exact_binding_path(
        qualification_receipt_binding,
        expected_path=_join(
            runtime_root,
            "evidence/seal-bundle/qualification-receipt.json",
        ),
        code="V32_LIFECYCLE_QUALIFICATION_RECEIPT_BINDING_INVALID",
    )
    intent_path = _join(runtime_root, "target/finalization-intent.json")
    loaded = _load_target_finalization_intent(root, intent_path)
    if loaded is None:
        try:
            retirement_exists = secure_read_bytes(
                root,
                _join(runtime_root, "qualification/retirement.json"),
                missing_ok=True,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_FINALIZATION_PREFIX_INVALID"
            ) from exc
        if retirement_exists is not None:
            raise V32AuthorityLifecycleComposerError(
                "V32_LIFECYCLE_FINALIZATION_INTENT_MISSING"
            )
        return None
    intent, _ = loaded
    if (
        intent.get("target_run_id") != target
        or intent.get("qualification_run_id") != qualification
        or intent.get("qualification_authority_binding")
        != dict(qualification_authority_binding)
        or intent.get("qualification_receipt_binding")
        != dict(qualification_receipt_binding)
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_INTENT_DRIFT"
        )
    return _times(intent.get("phase_times"), _PHASE_B_TIME_KEYS)


def finalize_v32_target_authority(
    *,
    project_root: Path,
    runtime_root_relative_ref: str,
    expected_target_run_id: str,
    expected_qualification_run_id: str,
    qualification_authority_binding: Mapping[str, Any],
    qualification_receipt_binding: Mapping[str, Any],
    phase_times: Mapping[str, str],
    capability_verifiers: Mapping[
        str, V32ActualCapabilityFullReplayVerifier
    ] | None = None,
) -> dict[str, Any]:
    """Replay actual qualification, retire it, then publish the target pointer."""

    root = _root(project_root)
    target, qualification, runtime_root = _active_runtime_namespace(
        root,
        target_run_id=expected_target_run_id,
        qualification_run_id=expected_qualification_run_id,
        supplied_runtime_root=runtime_root_relative_ref,
        require_root=True,
    )
    _require_exact_binding_path(
        qualification_authority_binding,
        expected_path=_join(runtime_root, "qualification/authority.json"),
        code="V32_LIFECYCLE_QUALIFICATION_AUTHORITY_BINDING_INVALID",
    )
    _require_exact_binding_path(
        qualification_receipt_binding,
        expected_path=_join(
            runtime_root,
            "evidence/seal-bundle/qualification-receipt.json",
        ),
        code="V32_LIFECYCLE_QUALIFICATION_RECEIPT_BINDING_INVALID",
    )
    times = _times(phase_times, _PHASE_B_TIME_KEYS)
    if capability_verifiers is None:
        from .v32_actual_capability_replay import (
            build_v32_actual_capability_full_replay_registry,
        )

        capability_verifiers = build_v32_actual_capability_full_replay_registry()
    try:
        replay = replay_v32_actual_capability_qualification_receipt(
            root,
            qualification_authority_binding=qualification_authority_binding,
            qualification_receipt_binding=qualification_receipt_binding,
            capability_verifiers=capability_verifiers,
        )
    except V32CurrentResearchAuthorityError as exc:
        code = "V32_LIFECYCLE_QUALIFICATION_REPLAY_INVALID"
        if "POSTCOMMIT" in str(exc) or "workspace_freeze" in str(exc):
            code = "V32_LIFECYCLE_POSTCOMMIT_REGRESSION_REPLAY_INVALID"
        raise V32AuthorityLifecycleComposerError(code) from exc
    qualification_authority = replay["qualification_authority"]
    qualification_receipt = replay["qualification_receipt"]
    qualification_authority_binding = replay[
        "qualification_authority_binding"
    ]
    qualification_receipt_binding = replay["qualification_receipt_binding"]
    if (
        qualification_authority.get("run_id") != qualification
        or qualification_authority.get("target_run_id") != target
        or replay.get("full_replay_verified") is not True
        or replay.get("replay_network_calls") != 0
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_QUALIFICATION_REPLAY_INVALID"
        )
    completed = _moment(
        qualification_receipt["completed_at"],
        "V32_LIFECYCLE_CHRONOLOGY_INVALID",
    )
    chronology = [
        _moment(times[key], "V32_LIFECYCLE_CHRONOLOGY_INVALID")
        for key in (
            "retired_at",
            "target_gate_evaluated_at",
            "target_phase_evaluated_at",
            "target_authorization_issued_at",
            "target_authority_recorded_at",
        )
    ]
    if not (
        completed <= chronology[0] < chronology[1] <= chronology[2] <= chronology[3] <= chronology[4]
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_CHRONOLOGY_INVALID"
        )
    approval_binding = qualification_authority["theory_approval_binding"]
    contract_binding = qualification_authority["experiment_contract_binding"]
    manifest_binding = qualification_authority["runtime_manifest_binding"]
    approval, approval_binding = _load_bound(
        root,
        approval_binding,
        schema_id="theory_paper_v32_theory_approval_receipt_v1",
        digest_field=THEORY_APPROVAL_DIGEST_FIELD,
        verifier=verify_v32_theory_approval_receipt_v1,
    )
    contract, contract_binding = _load_bound(
        root,
        contract_binding,
        schema_id="theory_paper_v32_dynamic_aggressive_process_pilot_contract_v1",
        digest_field=EXPERIMENT_CONTRACT_DIGEST_FIELD,
        verifier=verify_v32_experiment_contract_v1,
    )
    manifest, manifest_binding = _load_bound(
        root,
        manifest_binding,
        schema_id="theory_paper_v32_runtime_manifest_v1",
        digest_field=RUNTIME_MANIFEST_DIGEST_FIELD,
        verifier=verify_v32_runtime_manifest,
    )
    if (
        contract.get("run_id") != target
        or manifest.get("target_run_id") != target
        or manifest.get("qualification_run_id") != qualification
        or not qualification_authority_binding["path"].startswith(
            runtime_root + "/"
        )
    ):
        raise V32AuthorityLifecycleComposerError("V32_LIFECYCLE_CHAIN_INVALID")

    workspace_binding = manifest.get("support_document_bindings", {}).get(
        "workspace_freeze_receipt_digest"
    )
    workspace, recovered_workspace_binding = _load_bound(
        root,
        workspace_binding,
        schema_id=WORKSPACE_SCHEMA_ID,
        digest_field=WORKSPACE_DIGEST_FIELD,
        verifier=lambda document: verify_live_v32_workspace_freeze_v1(
            project_root=root, receipt=document
        ),
    )
    if (
        recovered_workspace_binding.get("path")
        != _join(runtime_root, "support/workspace-freeze.json")
        or workspace.get("schema_version")
        != WORKSPACE_POSTCOMMIT_SCHEMA_VERSION
        or workspace.get("postcommit_regression_target_run_id") != target
        or workspace.get("postcommit_regression_qualification_run_id")
        != qualification
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_POSTCOMMIT_REGRESSION_REPLAY_INVALID"
        )

    retirement = build_v32_qualification_retirement_receipt_v1(
        retirement_id=f"{qualification}:retirement",
        retired_at=times["retired_at"],
        qualification_run_id=qualification,
        target_run_id=target,
        qualification_authority_binding=qualification_authority_binding,
        qualification_receipt_binding=qualification_receipt_binding,
    )
    verify_v32_qualification_retirement_receipt_v1(retirement)
    retirement_path = _join(runtime_root, "qualification/retirement.json")
    retirement_binding = _canonical_binding(
        retirement_path, retirement, QUALIFICATION_RETIREMENT_DIGEST_FIELD
    )

    support_bindings = manifest["support_document_bindings"]
    anchors = _preflight_anchor_set(
        predecessor=qualification_authority_binding,
        approval=approval_binding,
        contract=contract_binding,
        manifest=manifest_binding,
        support=support_bindings,
    )
    target_gate_artifacts, target_gate_bindings, target_gates = (
        _build_gate_artifacts(
            runtime_root=runtime_root,
            directory="target",
            profile=TARGET_PHASE_PROFILE,
            run_id=target,
            target_run_id=target,
            evaluated_at=times["target_gate_evaluated_at"],
            implementation_bindings=manifest["implementation_bindings"],
            anchors=anchors,
            actual_capability_bindings=replay[
                "actual_capability_receipt_bindings"
            ],
        )
    )
    phase = build_v32_phase_a_qualification_receipt_v1(
        phase_id=f"{target}:phase-a",
        profile=TARGET_PHASE_PROFILE,
        run_id=target,
        target_run_id=target,
        evaluated_at=times["target_phase_evaluated_at"],
        theory_approval_digest=approval[THEORY_APPROVAL_DIGEST_FIELD],
        experiment_contract_digest=contract[EXPERIMENT_CONTRACT_DIGEST_FIELD],
        runtime_manifest_digest=manifest[RUNTIME_MANIFEST_DIGEST_FIELD],
        q0_q8_evidence_bindings=target_gate_bindings,
        predecessor_retirement_digest=retirement[
            QUALIFICATION_RETIREMENT_DIGEST_FIELD
        ],
    )
    verify_v32_phase_a_qualification_receipt_v1(phase)
    phase_path = _join(runtime_root, "target/phase-a.json")
    phase_binding = _canonical_binding(phase_path, phase, PHASE_A_DIGEST_FIELD)
    authorization = build_v32_authorization_receipt_v1(
        authorization_id=f"{target}:authorization",
        profile=TARGET_PROFILE,
        issued_at=times["target_authorization_issued_at"],
        run_id=target,
        target_run_id=target,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=phase_binding,
        qualification_retirement_binding=retirement_binding,
    )
    verify_v32_authorization_receipt_v1(authorization)
    authorization_path = _join(runtime_root, "target/authorization.json")
    authorization_binding = _canonical_binding(
        authorization_path, authorization, AUTHORIZATION_RECEIPT_DIGEST_FIELD
    )
    authority = build_v32_authority_v1(
        authority_id=f"{target}:authority",
        profile=TARGET_PROFILE,
        recorded_at=times["target_authority_recorded_at"],
        run_id=target,
        target_run_id=target,
        predecessor_authority_binding=qualification_authority_binding,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=phase_binding,
        authorization_receipt_binding=authorization_binding,
        qualification_retirement_binding=retirement_binding,
    )
    verify_v32_authority_v1(authority)
    pointer_path = V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix()
    pointer_binding = _canonical_binding(
        pointer_path, authority, AUTHORITY_DIGEST_FIELD
    )
    artifacts = [
        *target_gate_artifacts,
        (phase_path, phase, PHASE_A_DIGEST_FIELD),
        (
            authorization_path,
            authorization,
            AUTHORIZATION_RECEIPT_DIGEST_FIELD,
        ),
        (pointer_path, authority, AUTHORITY_DIGEST_FIELD),
    ]
    intent = _build_target_finalization_intent_v1(
        target_run_id=target,
        qualification_run_id=qualification,
        qualification_authority_binding=qualification_authority_binding,
        qualification_receipt_binding=qualification_receipt_binding,
        phase_times=times,
        qualification_retirement_binding=retirement_binding,
    )
    intent_path = _join(runtime_root, "target/finalization-intent.json")
    intent_binding = _canonical_binding(
        intent_path,
        intent,
        _TARGET_FINALIZATION_INTENT_DIGEST_FIELD,
    )
    prior_intent = _load_target_finalization_intent(root, intent_path)
    try:
        prior_retirement = secure_read_bytes(
            root, retirement_path, missing_ok=True
        )
    except (OSError, TypeError, ValueError) as exc:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_PREFIX_INVALID"
        ) from exc
    if prior_retirement is not None and prior_intent is None:
        # A retirement without its precommitted tail plan cannot be completed
        # deterministically.  Inventing new post-retirement times would make a
        # different authority look like recovery of the interrupted one.
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_INTENT_MISSING"
        )
    if prior_intent is not None and prior_intent != (intent, intent_binding):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_INTENT_DRIFT"
        )
    persisted_prefix = _persist_batch(
        root,
        [
            (
                intent_path,
                intent,
                _TARGET_FINALIZATION_INTENT_DIGEST_FIELD,
            ),
            (
                retirement_path,
                retirement,
                QUALIFICATION_RETIREMENT_DIGEST_FIELD,
            ),
        ],
    )
    persisted_intent_document, persisted_intent_binding = _load_bound(
        root,
        persisted_prefix[intent_path],
        schema_id=_TARGET_FINALIZATION_INTENT_SCHEMA_ID,
        digest_field=_TARGET_FINALIZATION_INTENT_DIGEST_FIELD,
        verifier=_verify_target_finalization_intent_v1,
    )
    if (
        persisted_intent_document != intent
        or persisted_intent_binding != intent_binding
    ):
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FINALIZATION_INTENT_REPLAY_INVALID"
        )
    retired_document, persisted_retirement = _load_bound(
        root,
        persisted_prefix[retirement_path],
        schema_id="theory_paper_v32_qualification_retirement_receipt_v1",
        digest_field=QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        verifier=verify_v32_qualification_retirement_receipt_v1,
    )
    if retired_document != retirement or persisted_retirement != retirement_binding:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_RETIREMENT_REPLAY_INVALID"
        )
    persisted = _persist_batch(root, artifacts)
    try:
        assert_v32_qualification_runtime_namespace_v1(
            project_root=root,
            qualification_run_id=qualification,
            require_root=True,
        )
    except V32QualificationRuntimeNamespaceError as exc:
        raise V32AuthorityLifecycleComposerError(str(exc)) from exc
    if persisted[pointer_path] != pointer_binding:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_CURRENT_POINTER_DRIFT"
        )
    projection = load_v32_current_research_authority(
        root,
        expected_run_id=target,
        capability_verifiers=capability_verifiers,
    )
    if projection.get("authority") != authority:
        raise V32AuthorityLifecycleComposerError(
            "V32_LIFECYCLE_FULL_LOADER_PROJECTION_INVALID"
        )
    return {
        "status": "TARGET_AUTHORITY_READY",
        "target_run_id": target,
        "qualification_run_id": qualification,
        "qualification_replay": replay,
        "qualification_retirement": retirement,
        "qualification_retirement_binding": retirement_binding,
        "target_finalization_intent": intent,
        "target_finalization_intent_binding": intent_binding,
        "target_gates": target_gates,
        "target_gate_bindings": target_gate_bindings,
        "target_phase": phase,
        "target_phase_binding": phase_binding,
        "target_authorization": authorization,
        "target_authorization_binding": authorization_binding,
        "target_authority": authority,
        "current_pointer_binding": pointer_binding,
        "application_projection": projection,
        "current_pointer_written": True,
        "full_loader_verified": True,
        "network_calls": 0,
        "authority_boundary": "PUBLIC_LOCAL_NON_EXECUTABLE",
    }


__all__ = [
    "PRODUCTION_ROOT_PATHS",
    "V32AuthorityLifecycleComposerError",
    "finalize_v32_target_authority",
    "load_v32_target_finalization_phase_times_if_started",
    "prepare_v32_qualification_authority",
]
