from __future__ import annotations

import copy
from contextlib import ExitStack, nullcontext
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    ACTUAL_CAPABILITY_RECEIPT_SPECS,
    AUTHORITY_DIGEST_FIELD,
    AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    CAPABILITY_GATE_MAP,
    CAPABILITY_KEYS,
    GATE_EVIDENCE_DIGEST_FIELD,
    PHASE_A_DIGEST_FIELD,
    Q0_Q8_GATE_IDS,
    QUALIFICATION_PHASE_PROFILE,
    QUALIFICATION_PROFILE,
    QUALIFICATION_RECEIPT_DIGEST_FIELD,
    QUALIFICATION_RETIREMENT_DIGEST_FIELD,
    RUNTIME_MANIFEST_DIGEST_FIELD,
    SUPPORT_DOCUMENT_BINDING_SPECS,
    TARGET_PHASE_PROFILE,
    TARGET_PROFILE,
    THEORY_APPROVAL_DIGEST_FIELD,
    V32AuthorizationError,
    build_v32_actual_capability_receipt_v1,
    build_v32_authority_v1,
    build_v32_authorization_receipt_v1,
    build_v32_fresh_capability_qualification_receipt_v1,
    build_v32_phase_a_qualification_receipt_v1,
    build_v32_qualification_gate_evidence_v1,
    build_v32_qualification_retirement_receipt_v1,
    build_v32_runtime_manifest_v1,
    build_v32_runtime_manifest_v2,
    build_v32_theory_approval_receipt_v1,
    verify_v32_runtime_manifest,
)
from trade_system.theory_paper_v2.application.v32_authorized_revision_orchestration import (
    SUPPORT_BUNDLE_DIGEST_FIELD,
    build_v32_authorized_revision_support_bundle_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_workspace_freeze import (
    DIGEST_FIELD as WORKSPACE_DIGEST_FIELD,
    build_v32_workspace_freeze_receipt_v1,
    build_v32_workspace_freeze_receipt_v1_1,
)
from trade_system.theory_paper_v2.domain.governance.v311_fresh_process_trace_v2 import (
    build_v311_fresh_process_trace_receipt_v2,
)
from trade_system.theory_paper_v2.domain.governance.v32_postcommit_regression import (
    qualification_support_paths_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_preflight_gate_subject import (
    DIGEST_FIELD as PREFLIGHT_SUBJECT_DIGEST_FIELD,
    EXPIRED_AGENT_WINDOW_SUBJECT_DIGESTS,
    EXPIRED_CURRENT_CODEX_SUBJECT_DIGESTS,
    FAILED_CONCURRENT_MATERIALIZATION_SUBJECT_DIGESTS,
    FAILED_CONTEXT_CAPACITY_SUBJECT_DIGESTS,
    FAILED_FUNDING_TIME_SUBJECT_DIGESTS,
    FAILED_MATERIALIZATION_SUBJECT_DIGESTS,
    FAILED_OPENAPI_ROUTE_SUBJECT_DIGESTS,
    FAILED_PRE_NETWORK_SUBJECT_DIGESTS,
    GATE_ANCHOR_ROLES,
    GATE_IMPLEMENTATION_PATHS,
    FAILED_PUBLIC_SOURCE_SUBJECT_DIGESTS,
    PRODUCTION_ROOT_PATHS,
    build_v32_typed_preflight_gate_subject_v1,
    verify_v32_typed_preflight_gate_subject_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_qualification_identity import (
    EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
    EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
    EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID,
    EXPIRED_V32_CURRENT_CODEX_TARGET_RUN_ID,
    FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
    FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
    FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
    FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
    FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID,
    FAILED_V32_FUNDING_TIME_TARGET_RUN_ID,
    FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
    FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
    FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
    FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID,
    FAILED_V32_QUALIFICATION_RUN_ID,
    FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
    FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID,
    FAILED_V32_TARGET_RUN_ID,
)
from trade_system.theory_paper_v2.domain.v31_sentiment_native_projection_v2 import (
    build_v31_native_sentiment_source_registry,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    THEORY_DOCUMENT_DIGEST_FIELD,
    build_v32_theory_semantic_document_v1,
)
from trade_system.theory_paper_v2.domain.v32_association_preregistration import (
    DIGEST_FIELD as ASSOCIATION_DIGEST_FIELD,
    build_v32_association_preregistration,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    POLICY_DIGEST_FIELD as CONTEXT_POLICY_DIGEST_FIELD,
    build_v32_context_compaction_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    POLICY_DIGEST_FIELD as AUDIT_POLICY_DIGEST_FIELD,
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_data_gap_escalation import (
    POLICY_DIGEST_FIELD as DATA_GAP_POLICY_DIGEST_FIELD,
    build_v32_data_gap_manual_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_environment_capability import (
    CAPABILITY_CATEGORIES,
    DIGEST_FIELD as ENVIRONMENT_DIGEST_FIELD,
    build_v32_environment_capability_profile_v1,
)
from trade_system.theory_paper_v2.domain.v32_evaluation_contract import (
    DIGEST_FIELD as EVALUATION_DIGEST_FIELD,
    build_v32_evaluation_contract,
)
from trade_system.theory_paper_v2.domain.v32_recovery_supervision import (
    POLICY_DIGEST_FIELD as RECOVERY_POLICY_DIGEST_FIELD,
    build_v32_recovery_supervision_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_runtime_support_contracts import (
    CLOCK_DIGEST_FIELD,
    OUTCOME_ADAPTER_DIGEST_FIELD,
    build_v32_clock_and_tick_policy_v1,
    build_v32_public_outcome_adapter_contract_v1,
)
from trade_system.theory_paper_v2.domain.v32_unknown_assessment import (
    POLICY_DIGEST_FIELD as UNKNOWN_POLICY_DIGEST_FIELD,
    build_v32_unknown_subjective_policy_v1,
)
from trade_system.theory_paper_v2.domain.governance.v32_experiment_contract import (
    DIGEST_FIELD as EXPERIMENT_CONTRACT_DIGEST_FIELD,
    SUPPORT_BINDING_KEYS,
    THEORY_VERSION,
    build_v32_experiment_contract_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    V31_CURRENT_RESEARCH_AUTHORITY_PATH,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_runtime_closure_v2 import (
    build_v31_runtime_closure_bindings_v2,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_current_research import (
    V32_APPLICATION_PROJECTION_KEYS,
    V32_CURRENT_RESEARCH_AUTHORITY_PATH,
    V32CurrentResearchAuthorityError,
    load_v32_current_research_authority,
    load_v32_qualification_phase_a_authority,
    replay_v32_actual_capability_qualification_receipt,
)
from trade_system.theory_paper_v2.infrastructure.authority import (
    v32_current_research as loader_implementation,
)
from trade_system.theory_paper_v2.presentation import (
    v32_qualification_composition as qualification_composition,
)
from tests.v32_postcommit_regression_support import (
    write_valid_postcommit_regression_support,
)


TARGET_RUN = "v32-target-btcusdt-20260807t000600z"
QUALIFICATION_RUN = "v32-qualification-btcusdt-20260807t000600z"
AUTHORITY_ROOT = f".runtime/v32/qualifications/{QUALIFICATION_RUN}"
LOADER_MODULE = (
    "trade_system.theory_paper_v2.infrastructure.authority.v32_current_research"
)


def token(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def write_document(root: Path, relative_ref: str, document: dict) -> dict:
    path = root / relative_ref
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(document) + b"\n"
    path.write_bytes(payload)
    digest_field = [key for key in document if key.endswith("_digest")][-1]
    return {
        "path": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(payload).hexdigest(),
    }


def rewrite_document(
    root: Path, relative_ref: str, document: dict, digest_field: str
) -> dict:
    path = root / relative_ref
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(document) + b"\n"
    path.write_bytes(payload)
    return {
        "path": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(payload).hexdigest(),
    }


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_revision_document(
    root: Path, relative_ref: str, document: dict, digest_field: str
) -> dict[str, str]:
    binding = rewrite_document(root, relative_ref, document, digest_field)
    return {
        "relative_ref": binding["path"],
        "schema_id": binding["schema_id"],
        "digest_field": binding["digest_field"],
        "semantic_digest": binding["semantic_digest"],
        "physical_sha256": binding["physical_sha256"],
    }


def capabilities() -> list[dict]:
    return [
        {
            "category": category,
            "status": "AVAILABLE",
            "observed_value": f"fixture:{category}",
            "limit": "LOCAL_TEST_ONLY",
            "evidence_refs": [f"fixture:{category.lower()}"],
            "claim_ceiling": "CAPABILITY_ONLY",
        }
        for category in CAPABILITY_CATEGORIES
    ]


def build_gate_evidence_set(
    root: Path,
    *,
    directory: str,
    profile: str,
    run_id: str,
    target_run_id: str,
    evaluated_at: str,
    implementation_bindings: dict[str, str],
    anchor_bindings: dict[str, dict],
    subject_binding_overrides: dict[str, dict] | None = None,
) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict], dict[str, dict]]:
    subjects: dict[str, dict] = {}
    subject_bindings: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    evidence_bindings: dict[str, dict] = {}
    overrides = subject_binding_overrides or {}
    for gate_id in Q0_Q8_GATE_IDS:
        subject_binding = overrides.get(gate_id)
        if subject_binding is None:
            subject = build_v32_typed_preflight_gate_subject_v1(
                subject_id=f"v32-{directory}-{gate_id.lower()}-preflight",
                gate_id=gate_id,
                profile=profile,
                run_id=run_id,
                target_run_id=target_run_id,
                evaluated_at=evaluated_at,
                implementation_bindings={
                    path: implementation_bindings[path]
                    for path in GATE_IMPLEMENTATION_PATHS[gate_id]
                },
                anchor_bindings={
                    role: anchor_bindings[role]
                    for role in GATE_ANCHOR_ROLES[gate_id]
                },
            )
            subject_binding = write_document(
                root,
                f"{AUTHORITY_ROOT}/{directory}/subjects/{gate_id.lower()}.json",
                subject,
            )
        else:
            subject = {}
        gate = build_v32_qualification_gate_evidence_v1(
            gate_id=gate_id,
            profile=profile,
            run_id=run_id,
            target_run_id=target_run_id,
            evaluated_at=evaluated_at,
            subject_bindings=[subject_binding],
        )
        gate_binding = write_document(
            root,
            f"{AUTHORITY_ROOT}/{directory}/gates/{gate_id.lower()}.json",
            gate,
        )
        subjects[gate_id] = subject
        subject_bindings[gate_id] = subject_binding
        evidence[gate_id] = gate
        evidence_bindings[gate_id] = gate_binding
    return subjects, subject_bindings, evidence, evidence_bindings


def fixture_capability_verifiers() -> dict[str, object]:
    """Strict test doubles for the three capability-owning full replayers."""

    def verifier_for(capability: str):
        def verify(
            *,
            project_root: Path,
            capability_receipt: dict,
            evidence_root_binding: dict,
            qualification_authority: dict,
        ) -> dict:
            path = project_root / evidence_root_binding["path"]
            document = load_json_strict(path)
            if (
                capability_receipt.get("capability") != capability
                or capability_receipt.get("qualification_authority_binding", {}).get(
                    "semantic_digest"
                )
                != qualification_authority.get(AUTHORITY_DIGEST_FIELD)
                or document.get("schema_id")
                != f"theory_paper_v32_{capability.lower()}_full_replay_fixture_v1"
                or document.get("capability") != capability
                or document.get("full_replay_verified") is not True
                or document.get("replay_network_calls") != 0
                or verify_self_digest(
                    document, evidence_root_binding["digest_field"]
                )
                != evidence_root_binding["semantic_digest"]
            ):
                raise ValueError("fixture owning full replay failed")
            return {
                "capability": capability,
                "evidence_root_semantic_digest": evidence_root_binding[
                    "semantic_digest"
                ],
                "full_replay_verified": True,
                "replay_network_calls": 0,
            }

        return verify

    return {capability: verifier_for(capability) for capability in CAPABILITY_KEYS}


def rewrite_target_descendants(
    root: Path,
    fixture: dict,
    *,
    retirement: dict,
    retirement_binding: dict,
    target_phase: dict | None = None,
) -> None:
    phase = copy.deepcopy(target_phase or fixture["target_phase"])
    phase["predecessor_retirement_digest"] = retirement[
        QUALIFICATION_RETIREMENT_DIGEST_FIELD
    ]
    phase = self_digest(phase, PHASE_A_DIGEST_FIELD)
    phase_binding = rewrite_document(
        root,
        fixture["target_phase_binding"]["path"],
        phase,
        PHASE_A_DIGEST_FIELD,
    )
    authorization = copy.deepcopy(fixture["target_authorization"])
    authorization["phase_a_receipt_binding"] = phase_binding
    authorization["qualification_retirement_binding"] = retirement_binding
    authorization = self_digest(
        authorization, AUTHORIZATION_RECEIPT_DIGEST_FIELD
    )
    authorization_binding = rewrite_document(
        root,
        fixture["target_authorization_binding"]["path"],
        authorization,
        AUTHORIZATION_RECEIPT_DIGEST_FIELD,
    )
    authority = copy.deepcopy(fixture["target_authority"])
    authority["phase_a_receipt_binding"] = phase_binding
    authority["authorization_receipt_binding"] = authorization_binding
    authority["qualification_retirement_binding"] = retirement_binding
    authority = self_digest(authority, AUTHORITY_DIGEST_FIELD)
    rewrite_document(
        root,
        V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
        authority,
        AUTHORITY_DIGEST_FIELD,
    )


def build_fixture(
    root: Path,
    *,
    runtime_mode: str = "VALID",
    contract_mismatch_key: str | None = None,
    semantic_drift_key: str | None = None,
    legacy_workspace: bool = False,
    runtime_manifest_version: int = 2,
    fresh_trace_completed_at: str = "2026-08-06T23:58:01Z",
    theory_bytes: bytes | None = None,
) -> dict:
    theory_ref = "theory/current/V3_2_DYNAMIC_AGGRESSIVE.md"
    theory_bytes = (
        "# V3.2\n\npublic-only non-executable theory\n".encode()
        if theory_bytes is None
        else theory_bytes
    )
    theory_path = root / theory_ref
    theory_path.parent.mkdir(parents=True, exist_ok=True)
    theory_path.write_bytes(theory_bytes)
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
    theory_semantic_document_binding = write_document(
        root,
        f"{AUTHORITY_ROOT}/theory-semantic-document.json",
        theory_semantic_document,
    )

    legacy_authority = self_digest(
        {
            "schema_id": "theory_paper_v31_current_research_authority",
            "authorized_run_id": "v31-prospective-btcusdt-20260806t183742z",
        },
        "authority_digest",
    )
    legacy_binding = write_document(
        root,
        V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
        legacy_authority,
    )
    legacy_chain = {
        "authority": legacy_authority,
        "qualification_receipts": {gate: {} for gate in Q0_Q8_GATE_IDS},
        "manifest": {
            "implementation_bindings": {
                f"legacy/path-{index:02d}.py": token(f"legacy:{index}")
                for index in range(74)
            }
        },
    }
    legacy_failure = {
        "research_checkpoint": {"status": "READY_FOR_CYCLE", "completed_cycles": 1},
        "monitor_checkpoint": {
            "status": "FAILED_CLOSED",
            "resume_allowed": False,
            "outcome_bindings": [],
        },
        "monitor_failure": {
            "resume_allowed": False,
            "reserved_attempts": 1,
            "resolved_cycles": 0,
        },
        "resolution_attempt": {"attempt_number": 1, "retry_allowed": False},
    }

    runtime_root = root / "runtime"
    runtime_root.mkdir()
    (runtime_root / "probe.py").write_text(
        "from runtime import dependency\nVALUE = dependency.VALUE\n",
        encoding="utf-8",
    )
    (runtime_root / "dependency.py").write_text("VALUE = 1\n", encoding="utf-8")
    for relative_ref in PRODUCTION_ROOT_PATHS:
        implementation_path = root / relative_ref
        implementation_path.parent.mkdir(parents=True, exist_ok=True)
        implementation_path.write_text(
            f'"""Fixture production root: {relative_ref}."""\n',
            encoding="utf-8",
        )
    roots = tuple(sorted({"runtime/probe.py", *PRODUCTION_ROOT_PATHS}))
    trace = roots
    fresh_process_trace = build_v311_fresh_process_trace_receipt_v2(
        trace_id="v32-current-loader-fixture-trace",
        started_at="2026-08-06T23:58:00Z",
        completed_at=fresh_trace_completed_at,
        parent_pid=200,
        worker_pid=201,
        invocation_nonce="fixture-nonce",
        echoed_nonce="fixture-nonce",
        python_executable="/opt/homebrew/bin/python3.12",
        python_version="3.12-fixture",
        production_root_paths=roots,
        imported_root_modules=tuple(
            sorted(f"trace_root_{index}" for index, _ in enumerate(roots))
        ),
        observed_project_python_paths=trace,
        stderr_sha256=hashlib.sha256(b"").hexdigest(),
        stderr_empty=True,
    )
    implementation_bindings = build_v31_runtime_closure_bindings_v2(
        project_root=root,
        production_root_paths=roots,
        trace_paths=trace,
    )
    if runtime_mode == "MISSING":
        implementation_bindings = {
            path: digest
            for path, digest in implementation_bindings.items()
            if path != "runtime/dependency.py"
        }
    elif runtime_mode == "EXTRA":
        (runtime_root / "extra.py").write_text("EXTRA = True\n", encoding="utf-8")
        implementation_bindings = dict(implementation_bindings)
        implementation_bindings["runtime/extra.py"] = hashlib.sha256(
            (runtime_root / "extra.py").read_bytes()
        ).hexdigest()
    implementation_bindings = dict(sorted(implementation_bindings.items()))

    (root / ".gitignore").write_text("config/\n.runtime/\n", encoding="utf-8")
    git(root, "init", "-b", "codex/test")
    git(root, "config", "user.email", "v32-test@example.invalid")
    git(root, "config", "user.name", "V32 Test")
    git(root, "add", ".gitignore", theory_ref, "runtime", "trade_system")
    git(root, "commit", "-m", "freeze v32 fixture")
    frozen_commit = git(root, "rev-parse", "HEAD")
    frozen_tree = git(root, "show", "-s", "--format=%T", "HEAD")
    relevant_paths = git(root, "ls-files").splitlines()
    postcommit = write_valid_postcommit_regression_support(
        root,
        target_run_id=TARGET_RUN,
        qualification_run_id=QUALIFICATION_RUN,
    )
    postcommit_paths = qualification_support_paths_v1(QUALIFICATION_RUN)
    write_document(
        root,
        postcommit_paths["reservation"],
        postcommit["reservation"],
    )
    for suite_id, receipt in postcommit["receipts"].items():
        write_document(
            root,
            postcommit_paths[f"receipt:{suite_id}"],
            receipt,
        )
    postcommit_aggregate_binding = write_document(
        root,
        postcommit_paths["aggregate"],
        postcommit["aggregate"],
    )
    workspace_kwargs = {
        "receipt_id": "v32-workspace-freeze-fixture",
        "observed_at": "2026-08-06T23:59:00Z",
        "branch": "codex/test",
        "frozen_commit_sha": frozen_commit,
        "frozen_tree_sha": frozen_tree,
        "relevant_paths": relevant_paths,
        "relevant_path_sha256": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in relevant_paths
        },
        "allowed_untracked_user_artifacts": [],
        "ignored_runtime_roots": [".runtime"],
    }
    workspace = (
        build_v32_workspace_freeze_receipt_v1(**workspace_kwargs)
        if legacy_workspace
        else build_v32_workspace_freeze_receipt_v1_1(
            **workspace_kwargs,
            postcommit_regression_aggregate_binding=(
                postcommit_aggregate_binding
            ),
            postcommit_regression_target_run_id=TARGET_RUN,
            postcommit_regression_qualification_run_id=QUALIFICATION_RUN,
        )
    )
    workspace_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/workspace-freeze.json", workspace
    )
    fresh_process_trace_binding = None
    if runtime_manifest_version == 2:
        fresh_process_trace_binding = write_document(
            root,
            f"{AUTHORITY_ROOT}/support/fresh-process-trace.json",
            fresh_process_trace,
        )

    association = build_v32_association_preregistration(
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    association_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/association.json", association
    )
    evaluation = build_v32_evaluation_contract(
        association_preregistration=association,
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    evaluation_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/evaluation.json", evaluation
    )
    clock = build_v32_clock_and_tick_policy_v1(
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    if semantic_drift_key == "clock_policy_digest":
        clock["analysis_clock"]["minimum_decision_spacing_seconds"] = 1
        clock = self_digest(clock, CLOCK_DIGEST_FIELD)
    clock_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/clock.json", clock
    )
    outcome_adapter = build_v32_public_outcome_adapter_contract_v1(
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    outcome_adapter_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/outcome-adapter.json", outcome_adapter
    )
    recovery = build_v32_recovery_supervision_policy_v1(
        policy_id="v32-recovery-policy-fixture",
        frozen_at="2026-08-07T00:00:00Z",
    )
    recovery_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/recovery.json", recovery
    )
    twelve_axis = build_v31_native_sentiment_source_registry()
    twelve_axis_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/twelve-axis.json", twelve_axis
    )

    context = build_v32_context_compaction_policy_v1(
        policy_id="context-policy-fixture",
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    unknown = build_v32_unknown_subjective_policy_v1(
        policy_id="unknown-policy-fixture",
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    data_gap = build_v32_data_gap_manual_policy_v1(
        policy_id="data-gap-policy-fixture",
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    audit = build_v32_cycle_audit_policy_v1(
        policy_id="audit-policy-fixture",
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
    )
    environment = build_v32_environment_capability_profile_v1(
        profile_id="environment-profile-fixture",
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
        capabilities=capabilities(),
        localization_adapters=[],
    )
    component_bindings = {
        "context_compaction_policy": write_revision_document(
            root,
            f"{AUTHORITY_ROOT}/support/revision/context.json",
            context,
            CONTEXT_POLICY_DIGEST_FIELD,
        ),
        "unknown_subjective_policy": write_revision_document(
            root,
            f"{AUTHORITY_ROOT}/support/revision/unknown.json",
            unknown,
            UNKNOWN_POLICY_DIGEST_FIELD,
        ),
        "data_gap_manual_policy": write_revision_document(
            root,
            f"{AUTHORITY_ROOT}/support/revision/data-gap.json",
            data_gap,
            DATA_GAP_POLICY_DIGEST_FIELD,
        ),
        "cycle_audit_policy": write_revision_document(
            root,
            f"{AUTHORITY_ROOT}/support/revision/audit.json",
            audit,
            AUDIT_POLICY_DIGEST_FIELD,
        ),
        "environment_capability_profile": write_revision_document(
            root,
            f"{AUTHORITY_ROOT}/support/revision/environment.json",
            environment,
            ENVIRONMENT_DIGEST_FIELD,
        ),
    }
    revision_support = build_v32_authorized_revision_support_bundle_v1(
        support_bundle_id="v32-revision-support-fixture",
        run_scope_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
        context_compaction_policy=context,
        context_compaction_policy_binding=component_bindings[
            "context_compaction_policy"
        ],
        unknown_subjective_policy=unknown,
        unknown_subjective_policy_binding=component_bindings[
            "unknown_subjective_policy"
        ],
        data_gap_manual_policy=data_gap,
        data_gap_manual_policy_binding=component_bindings[
            "data_gap_manual_policy"
        ],
        cycle_audit_policy=audit,
        cycle_audit_policy_binding=component_bindings["cycle_audit_policy"],
        environment_capability_profile=environment,
        environment_capability_profile_binding=component_bindings[
            "environment_capability_profile"
        ],
    )
    revision_support_binding = write_document(
        root, f"{AUTHORITY_ROOT}/support/revision-bundle.json", revision_support
    )

    support_documents = {
        "association_preregistration_digest": association,
        "authorized_revision_support_bundle_digest": revision_support,
        "clock_policy_digest": clock,
        "evaluation_contract_digest": evaluation,
        "outcome_adapter_contract_digest": outcome_adapter,
        "recovery_supervision_policy_digest": recovery,
        "twelve_axis_source_registry_digest": twelve_axis,
        "workspace_freeze_receipt_digest": workspace,
    }
    support_document_bindings = {
        "association_preregistration_digest": association_binding,
        "authorized_revision_support_bundle_digest": revision_support_binding,
        "clock_policy_digest": clock_binding,
        "evaluation_contract_digest": evaluation_binding,
        "outcome_adapter_contract_digest": outcome_adapter_binding,
        "recovery_supervision_policy_digest": recovery_binding,
        "twelve_axis_source_registry_digest": twelve_axis_binding,
        "workspace_freeze_receipt_digest": workspace_binding,
    }
    support_digests = {
        "association_preregistration_digest": association[
            ASSOCIATION_DIGEST_FIELD
        ],
        "authorized_revision_support_bundle_digest": revision_support[
            SUPPORT_BUNDLE_DIGEST_FIELD
        ],
        "clock_policy_digest": clock[CLOCK_DIGEST_FIELD],
        "evaluation_contract_digest": evaluation[EVALUATION_DIGEST_FIELD],
        "outcome_adapter_contract_digest": outcome_adapter[
            OUTCOME_ADAPTER_DIGEST_FIELD
        ],
        "recovery_supervision_policy_digest": recovery[
            RECOVERY_POLICY_DIGEST_FIELD
        ],
        "twelve_axis_source_registry_digest": twelve_axis["registry_digest"],
        "workspace_freeze_receipt_digest": workspace[WORKSPACE_DIGEST_FIELD],
    }
    if contract_mismatch_key is not None:
        support_digests[contract_mismatch_key] = token(
            f"contract-mismatch:{contract_mismatch_key}"
        )

    contract = build_v32_experiment_contract_v1(
        contract_id="v32-contract-fixture",
        run_id=TARGET_RUN,
        frozen_at="2026-08-07T00:00:00Z",
        theory_relative_ref=theory_ref,
        theory_physical_sha256=theory_sha,
        theory_semantic_digest=theory_semantic_document[
            THEORY_DOCUMENT_DIGEST_FIELD
        ],
        support_bindings=support_digests,
    )
    contract_binding = write_document(
        root, f"{AUTHORITY_ROOT}/experiment-contract.json", contract
    )
    approval = build_v32_theory_approval_receipt_v1(
        approval_id="v32-approval-fixture",
        approved_at="2026-08-07T00:02:00Z",
        theory_relative_ref=theory_ref,
        theory_physical_sha256=theory_sha,
        theory_semantic_digest=theory_semantic_document[
            THEORY_DOCUMENT_DIGEST_FIELD
        ],
    )
    approval_binding = write_document(
        root, f"{AUTHORITY_ROOT}/theory-approval.json", approval
    )
    manifest_builder = (
        build_v32_runtime_manifest_v2
        if runtime_manifest_version == 2
        else build_v32_runtime_manifest_v1
    )
    manifest_kwargs = dict(
        manifest_id="v32-manifest-fixture",
        created_at="2026-08-07T00:03:00Z",
        runtime_frozen_at="2026-08-07T00:01:00Z",
        target_run_id=TARGET_RUN,
        qualification_run_id=QUALIFICATION_RUN,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        theory_semantic_document_binding=theory_semantic_document_binding,
        support_document_bindings=support_document_bindings,
        production_root_paths=roots,
        fresh_trace_paths=trace,
        implementation_bindings=implementation_bindings,
    )
    if runtime_manifest_version == 2:
        manifest_kwargs["fresh_process_trace_binding"] = (
            fresh_process_trace_binding
        )
    manifest = manifest_builder(**manifest_kwargs)
    manifest_binding = write_document(
        root, f"{AUTHORITY_ROOT}/runtime-manifest.json", manifest
    )

    (
        qualification_gate_subjects,
        qualification_gate_subject_bindings,
        qualification_gate_evidence,
        qualification_gate_bindings,
    ) = build_gate_evidence_set(
        root,
        directory="qualification",
        profile=QUALIFICATION_PHASE_PROFILE,
        run_id=QUALIFICATION_RUN,
        target_run_id=TARGET_RUN,
        evaluated_at="2026-08-07T00:04:00Z",
        implementation_bindings=implementation_bindings,
        anchor_bindings={
            "predecessor_authority": legacy_binding,
            "runtime_manifest": manifest_binding,
            "experiment_contract": contract_binding,
            "clock_policy": support_document_bindings["clock_policy_digest"],
            "outcome_adapter_contract": support_document_bindings[
                "outcome_adapter_contract_digest"
            ],
            "theory_approval": approval_binding,
        },
    )
    qualification_phase = build_v32_phase_a_qualification_receipt_v1(
        phase_id="v32-qualification-phase-a",
        profile=QUALIFICATION_PHASE_PROFILE,
        run_id=QUALIFICATION_RUN,
        target_run_id=TARGET_RUN,
        evaluated_at="2026-08-07T00:04:00Z",
        theory_approval_digest=approval[THEORY_APPROVAL_DIGEST_FIELD],
        experiment_contract_digest=contract[EXPERIMENT_CONTRACT_DIGEST_FIELD],
        runtime_manifest_digest=manifest[RUNTIME_MANIFEST_DIGEST_FIELD],
        q0_q8_evidence_bindings=qualification_gate_bindings,
        predecessor_retirement_digest=None,
    )
    qualification_phase_binding = write_document(
        root, f"{AUTHORITY_ROOT}/qualification/phase-a.json", qualification_phase
    )
    qualification_authorization = build_v32_authorization_receipt_v1(
        authorization_id="v32-qualification-authorization",
        profile=QUALIFICATION_PROFILE,
        issued_at="2026-08-07T00:05:00Z",
        run_id=QUALIFICATION_RUN,
        target_run_id=TARGET_RUN,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=qualification_phase_binding,
        qualification_retirement_binding=None,
    )
    qualification_authorization_binding = write_document(
        root,
        f"{AUTHORITY_ROOT}/qualification/authorization.json",
        qualification_authorization,
    )
    qualification_authority = build_v32_authority_v1(
        authority_id="v32-qualification-authority",
        profile=QUALIFICATION_PROFILE,
        recorded_at="2026-08-07T00:06:00Z",
        run_id=QUALIFICATION_RUN,
        target_run_id=TARGET_RUN,
        predecessor_authority_binding=legacy_binding,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=qualification_phase_binding,
        authorization_receipt_binding=qualification_authorization_binding,
        qualification_retirement_binding=None,
    )
    qualification_authority_binding = write_document(
        root, f"{AUTHORITY_ROOT}/qualification/authority.json", qualification_authority
    )
    capability_roots: dict[str, dict] = {}
    capability_root_bindings: dict[str, dict] = {}
    actual_capability_receipts: dict[str, dict] = {}
    actual_capability_receipt_bindings: dict[str, dict] = {}
    capability_times = {
        "CURRENT_CODEX": ("2026-08-07T00:07:00Z", "2026-08-07T00:07:15Z"),
        "OUTCOME_MONITOR": ("2026-08-07T00:07:15Z", "2026-08-07T00:07:30Z"),
        "PUBLIC_SOURCE": ("2026-08-07T00:07:30Z", "2026-08-07T00:07:45Z"),
    }
    for capability in CAPABILITY_KEYS:
        root_document = self_digest(
            {
                "schema_id": (
                    f"theory_paper_v32_{capability.lower()}_full_replay_fixture_v1"
                ),
                "schema_version": "1.0.0",
                "capability": capability,
                "qualification_run_id": QUALIFICATION_RUN,
                "full_replay_verified": True,
                "replay_network_calls": 0,
            },
            "full_replay_fixture_digest",
        )
        slug = capability.lower().replace("_", "-")
        root_binding = write_document(
            root,
            f"{AUTHORITY_ROOT}/evidence/roots/{slug}.json",
            root_document,
        )
        started_at, completed_at = capability_times[capability]
        receipt = build_v32_actual_capability_receipt_v1(
            capability=capability,
            receipt_id=f"v32-{capability.lower()}-actual-capability",
            qualification_run_id=QUALIFICATION_RUN,
            target_run_id=TARGET_RUN,
            started_at=started_at,
            completed_at=completed_at,
            qualification_authority_binding=qualification_authority_binding,
            evidence_root_binding=root_binding,
        )
        receipt_binding = write_document(
            root,
            f"{AUTHORITY_ROOT}/evidence/seal-bundle/receipts/{slug}.json",
            receipt,
        )
        capability_roots[capability] = root_document
        capability_root_bindings[capability] = root_binding
        actual_capability_receipts[capability] = receipt
        actual_capability_receipt_bindings[capability] = receipt_binding
    qualification_receipt = build_v32_fresh_capability_qualification_receipt_v1(
        qualification_id="v32-fresh-capability-qualification",
        qualification_run_id=QUALIFICATION_RUN,
        target_run_id=TARGET_RUN,
        started_at="2026-08-07T00:07:00Z",
        completed_at="2026-08-07T00:08:00Z",
        qualification_authority_binding=qualification_authority_binding,
        capability_evidence_bindings=actual_capability_receipt_bindings,
    )
    qualification_receipt_binding = write_document(
        root,
        f"{AUTHORITY_ROOT}/evidence/seal-bundle/qualification-receipt.json",
        qualification_receipt,
    )
    retirement = build_v32_qualification_retirement_receipt_v1(
        retirement_id="v32-qualification-retirement",
        retired_at="2026-08-07T00:09:00Z",
        qualification_run_id=QUALIFICATION_RUN,
        target_run_id=TARGET_RUN,
        qualification_authority_binding=qualification_authority_binding,
        qualification_receipt_binding=qualification_receipt_binding,
    )
    retirement_binding = write_document(
        root, f"{AUTHORITY_ROOT}/qualification/retirement.json", retirement
    )

    (
        target_gate_subjects,
        target_gate_subject_bindings,
        target_gate_evidence,
        target_gate_bindings,
    ) = build_gate_evidence_set(
        root,
        directory="target",
        profile=TARGET_PHASE_PROFILE,
        run_id=TARGET_RUN,
        target_run_id=TARGET_RUN,
        evaluated_at="2026-08-07T00:10:00Z",
        implementation_bindings=implementation_bindings,
        anchor_bindings={
            "predecessor_authority": qualification_authority_binding,
            "runtime_manifest": manifest_binding,
            "experiment_contract": contract_binding,
            "clock_policy": support_document_bindings["clock_policy_digest"],
            "outcome_adapter_contract": support_document_bindings[
                "outcome_adapter_contract_digest"
            ],
            "theory_approval": approval_binding,
        },
        subject_binding_overrides={
            gate_id: actual_capability_receipt_bindings[capability]
            for capability, gate_id in CAPABILITY_GATE_MAP.items()
        },
    )
    target_phase = build_v32_phase_a_qualification_receipt_v1(
        phase_id="v32-target-phase-a",
        profile=TARGET_PHASE_PROFILE,
        run_id=TARGET_RUN,
        target_run_id=TARGET_RUN,
        evaluated_at="2026-08-07T00:10:00Z",
        theory_approval_digest=approval[THEORY_APPROVAL_DIGEST_FIELD],
        experiment_contract_digest=contract[EXPERIMENT_CONTRACT_DIGEST_FIELD],
        runtime_manifest_digest=manifest[RUNTIME_MANIFEST_DIGEST_FIELD],
        q0_q8_evidence_bindings=target_gate_bindings,
        predecessor_retirement_digest=retirement[
            QUALIFICATION_RETIREMENT_DIGEST_FIELD
        ],
    )
    target_phase_binding = write_document(
        root, f"{AUTHORITY_ROOT}/target/phase-a.json", target_phase
    )
    target_authorization = build_v32_authorization_receipt_v1(
        authorization_id="v32-target-authorization",
        profile=TARGET_PROFILE,
        issued_at="2026-08-07T00:11:00Z",
        run_id=TARGET_RUN,
        target_run_id=TARGET_RUN,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=target_phase_binding,
        qualification_retirement_binding=retirement_binding,
    )
    target_authorization_binding = write_document(
        root, f"{AUTHORITY_ROOT}/target/authorization.json", target_authorization
    )
    target_authority = build_v32_authority_v1(
        authority_id="v32-target-authority",
        profile=TARGET_PROFILE,
        recorded_at="2026-08-07T00:12:00Z",
        run_id=TARGET_RUN,
        target_run_id=TARGET_RUN,
        predecessor_authority_binding=qualification_authority_binding,
        theory_approval_binding=approval_binding,
        experiment_contract_binding=contract_binding,
        runtime_manifest_binding=manifest_binding,
        phase_a_receipt_binding=target_phase_binding,
        authorization_receipt_binding=target_authorization_binding,
        qualification_retirement_binding=retirement_binding,
    )
    target_authority_binding = write_document(
        root, V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(), target_authority
    )
    return {
        "legacy_chain": legacy_chain,
        "legacy_failure": legacy_failure,
        "approval": approval,
        "approval_binding": approval_binding,
        "contract": contract,
        "contract_binding": contract_binding,
        "manifest": manifest,
        "manifest_binding": manifest_binding,
        "support_documents": support_documents,
        "support_document_bindings": support_document_bindings,
        "theory_semantic_document": theory_semantic_document,
        "theory_semantic_document_binding": theory_semantic_document_binding,
        "revision_component_bindings": component_bindings,
        "qualification_phase": qualification_phase,
        "qualification_phase_binding": qualification_phase_binding,
        "qualification_gate_subjects": qualification_gate_subjects,
        "qualification_gate_subject_bindings": qualification_gate_subject_bindings,
        "qualification_gate_evidence": qualification_gate_evidence,
        "qualification_gate_bindings": qualification_gate_bindings,
        "qualification_authorization": qualification_authorization,
        "qualification_authorization_binding": qualification_authorization_binding,
        "qualification_authority": qualification_authority,
        "qualification_authority_binding": qualification_authority_binding,
        "capability_roots": capability_roots,
        "capability_root_bindings": capability_root_bindings,
        "actual_capability_receipts": actual_capability_receipts,
        "actual_capability_receipt_bindings": actual_capability_receipt_bindings,
        "qualification_receipt": qualification_receipt,
        "qualification_receipt_binding": qualification_receipt_binding,
        "retirement": retirement,
        "retirement_binding": retirement_binding,
        "target_phase": target_phase,
        "target_phase_binding": target_phase_binding,
        "target_gate_subjects": target_gate_subjects,
        "target_gate_subject_bindings": target_gate_subject_bindings,
        "target_gate_evidence": target_gate_evidence,
        "target_gate_bindings": target_gate_bindings,
        "target_authorization": target_authorization,
        "target_authorization_binding": target_authorization_binding,
        "target_authority": target_authority,
        "target_authority_binding": target_authority_binding,
    }


class V32CurrentResearchAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.live_temp = tempfile.TemporaryDirectory()
        cls.live_root = Path(cls.live_temp.name)
        cls.base_fixture = build_fixture(cls.live_root)
        cls.fresh_temp = None
        cls.fresh_root = None
        cls.fresh_base_fixture = None
        cls.snapshot_temp = tempfile.TemporaryDirectory()
        cls.snapshot_root = Path(cls.snapshot_temp.name)
        cls.live_snapshot_root = cls.snapshot_root / "live"
        cls.fresh_snapshot_root = cls.snapshot_root / "fresh"
        shutil.copytree(cls.live_root, cls.live_snapshot_root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.snapshot_temp.cleanup()
        if cls.fresh_temp is not None:
            cls.fresh_temp.cleanup()
        cls.live_temp.cleanup()

    def setUp(self) -> None:
        # Receipts bind the absolute cwd, so cloning into a different path is
        # invalid. Restore a pristine snapshot at the same class-owned path;
        # every method still starts from identical bytes without rebuilding
        # Git history and the complete authority graph 29 times.
        shutil.rmtree(type(self).live_root)
        shutil.copytree(type(self).live_snapshot_root, type(self).live_root)
        self.root = type(self).live_root
        self.fixture = copy.deepcopy(type(self).base_fixture)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def load(
        self,
        root: Path | None = None,
        fixture: dict | None = None,
        *,
        capability_verifiers: dict[str, object] | None = None,
    ) -> dict:
        root = root or self.root
        fixture = fixture or self.fixture
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=fixture["legacy_failure"],
        ):
            return load_v32_current_research_authority(
                root,
                expected_run_id=TARGET_RUN,
                capability_verifiers=(
                    capability_verifiers or fixture_capability_verifiers()
                ),
            )

    def load_phase_a(self) -> dict:
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.fixture["legacy_failure"],
        ):
            return load_v32_qualification_phase_a_authority(
                self.root,
                expected_target_run_id=TARGET_RUN,
                expected_qualification_run_id=QUALIFICATION_RUN,
            )

    def fresh_fixture(self) -> tuple[Path, dict]:
        owner = type(self)
        if owner.fresh_temp is None:
            owner.fresh_temp = tempfile.TemporaryDirectory()
            owner.fresh_root = Path(owner.fresh_temp.name)
            owner.fresh_base_fixture = build_fixture(owner.fresh_root)
            shutil.copytree(owner.fresh_root, owner.fresh_snapshot_root)
        else:
            shutil.rmtree(owner.fresh_root)
            shutil.copytree(owner.fresh_snapshot_root, owner.fresh_root)
        return (
            owner.fresh_root,
            copy.deepcopy(owner.fresh_base_fixture),
        )

    def test_full_loader_returns_only_exact_five_documents_and_is_read_only(self) -> None:
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        projected = self.load()
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(V32_APPLICATION_PROJECTION_KEYS, tuple(projected))
        self.assertEqual(TARGET_RUN, projected["authority"]["run_id"])
        self.assertEqual(TARGET_PROFILE, projected["authority"]["profile"])
        self.assertNotIn("qualification_receipt", projected)
        self.assertNotIn("q0_q8_evidence_bindings", projected)
        self.assertEqual(before, after)

    def test_legacy_v1_manifest_replays_without_synthetic_fresh_trace_receipt(self) -> None:
        root = Path(tempfile.mkdtemp(dir=self.temp.name))
        fixture = build_fixture(root, runtime_manifest_version=1)
        trace_path = root / AUTHORITY_ROOT / "support/fresh-process-trace.json"
        self.assertFalse(trace_path.exists())

        projected = self.load(root, fixture)

        self.assertEqual("1.0.0", projected["manifest"]["schema_version"])
        self.assertNotIn("fresh_process_trace_binding", projected["manifest"])
        self.assertFalse(trace_path.exists())

    def test_manifest_router_rejects_schema_and_version_shape_mismatch(self) -> None:
        v2_manifest = self.fixture["manifest"]
        self.assertEqual(
            v2_manifest[RUNTIME_MANIFEST_DIGEST_FIELD],
            verify_v32_runtime_manifest(v2_manifest),
        )

        v2_shape_claiming_v1 = copy.deepcopy(v2_manifest)
        v2_shape_claiming_v1["schema_version"] = "1.0.0"
        v2_shape_claiming_v1 = self_digest(
            v2_shape_claiming_v1, RUNTIME_MANIFEST_DIGEST_FIELD
        )
        with self.assertRaises(V32AuthorizationError):
            verify_v32_runtime_manifest(v2_shape_claiming_v1)

        wrong_schema_family = copy.deepcopy(v2_manifest)
        wrong_schema_family["schema_id"] = "theory_paper_v32_runtime_manifest_v2"
        wrong_schema_family = self_digest(
            wrong_schema_family, RUNTIME_MANIFEST_DIGEST_FIELD
        )
        with self.assertRaisesRegex(
            V32AuthorizationError, "V32_MANIFEST_SCHEMA_UNSUPPORTED"
        ):
            verify_v32_runtime_manifest(wrong_schema_family)

        unknown_version = copy.deepcopy(v2_manifest)
        unknown_version["schema_version"] = "3.0.0"
        unknown_version = self_digest(
            unknown_version, RUNTIME_MANIFEST_DIGEST_FIELD
        )
        with self.assertRaisesRegex(
            V32AuthorizationError, "V32_MANIFEST_VERSION_UNSUPPORTED"
        ):
            verify_v32_runtime_manifest(unknown_version)

    def test_v2_full_loaders_reject_trace_completed_after_workspace_observation(self) -> None:
        root = Path(tempfile.mkdtemp(dir=self.temp.name))
        fixture = build_fixture(
            root,
            fresh_trace_completed_at="2026-08-07T00:00:01Z",
        )
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=fixture["legacy_failure"],
        ):
            with self.assertRaisesRegex(
                V32CurrentResearchAuthorityError, "V32_CHRONOLOGY_INVALID"
            ):
                load_v32_qualification_phase_a_authority(
                    root,
                    expected_target_run_id=TARGET_RUN,
                    expected_qualification_run_id=QUALIFICATION_RUN,
                )
            with self.assertRaisesRegex(
                V32CurrentResearchAuthorityError, "V32_CHRONOLOGY_INVALID"
            ):
                load_v32_current_research_authority(
                    root,
                    expected_run_id=TARGET_RUN,
                    capability_verifiers=fixture_capability_verifiers(),
                )

    def test_phase_a_loader_replays_complete_read_only_qualification_base(self) -> None:
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        replay = self.load_phase_a()
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertTrue(replay["full_replay_verified"])
        self.assertEqual(0, replay["replay_network_calls"])
        self.assertEqual(QUALIFICATION_RUN, replay["qualification_authority"]["run_id"])
        self.assertEqual(Q0_Q8_GATE_IDS, tuple(replay["qualification_gates"]))
        self.assertEqual(set(SUPPORT_BINDING_KEYS), set(replay["support_documents"]))
        self.assertEqual(before, after)

    def test_qualification_tamper_matrix_fails_before_any_runtime_side_effect(self) -> None:
        manifest = self.fixture["manifest"]
        transitive_non_entry = next(
            path
            for path in manifest["implementation_bindings"]
            if path not in manifest["production_root_paths"]
        )
        cases = {
            "theory_approval": self.fixture["approval_binding"]["path"],
            "qualification_phase": self.fixture[
                "qualification_phase_binding"
            ]["path"],
            "qualification_authorization": self.fixture[
                "qualification_authorization_binding"
            ]["path"],
            "q0_gate": self.fixture["qualification_gate_bindings"]["Q0"][
                "path"
            ],
            "q0_subject": self.fixture[
                "qualification_gate_subject_bindings"
            ]["Q0"]["path"],
            "non_workspace_support": self.fixture[
                "support_document_bindings"
            ]["association_preregistration_digest"]["path"],
            "revision_component": self.fixture["revision_component_bindings"][
                "context_compaction_policy"
            ]["relative_ref"],
            "fresh_process_trace_receipt": manifest[
                "fresh_process_trace_binding"
            ]["path"],
            "transitive_non_entry_implementation": transitive_non_entry,
        }
        side_effect_names = (
            "build_v32_system_clock_v1",
            "LocalV32ActualCapabilityEvidenceStore",
            "LocalV32ActualCapabilityQualificationControllerStore",
            "LocalV32QualificationMaterializer",
            "LocalV32CurrentRootAgentMailbox",
            "LocalV32QualificationMonitorProbeStore",
            "V32OkxPublicBundleTransport",
            "V32OkxPublicMarkCaptureAdapter",
            "advance_v32_actual_capability_qualification_controller_once",
        )
        runtime_root = self.root / AUTHORITY_ROOT

        for label, relative_ref in cases.items():
            with self.subTest(label=label):
                path = self.root / relative_ref
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                before = {
                    item.relative_to(runtime_root).as_posix(): item.read_bytes()
                    for item in runtime_root.rglob("*")
                    if item.is_file()
                }
                try:
                    with ExitStack() as stack:
                        stack.enter_context(
                            patch.object(
                                qualification_composition,
                                "PROJECT_ROOT",
                                self.root,
                            )
                        )
                        stack.enter_context(
                            patch(
                                f"{LOADER_MODULE}.load_v31_active_authorization_chain",
                                return_value=self.fixture["legacy_chain"],
                            )
                        )
                        stack.enter_context(
                            patch(
                                f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
                                return_value=self.fixture["legacy_failure"],
                            )
                        )
                        side_effects = {
                            name: stack.enter_context(
                                patch.object(qualification_composition, name)
                            )
                            for name in side_effect_names
                        }
                        with self.assertRaisesRegex(
                            qualification_composition.V32QualificationCompositionError,
                            "V32_QUALIFICATION_PHASE_A_FULL_REPLAY_FAILED",
                        ):
                            qualification_composition.advance_v32_qualification_once_v1(
                                target_run_id=TARGET_RUN,
                                qualification_run_id=QUALIFICATION_RUN,
                            )
                        self.assertTrue(
                            all(mock.call_count == 0 for mock in side_effects.values())
                        )
                    after = {
                        item.relative_to(runtime_root).as_posix(): item.read_bytes()
                        for item in runtime_root.rglob("*")
                        if item.is_file()
                    }
                    self.assertEqual(before, after)
                finally:
                    path.write_bytes(original)

    def test_all_qualification_operations_gate_ports_and_writes_on_full_loader(self) -> None:
        operations = {
            "advance": lambda: qualification_composition.advance_v32_qualification_once_v1(
                target_run_id=TARGET_RUN,
                qualification_run_id=QUALIFICATION_RUN,
            ),
            "claim": lambda: qualification_composition.read_and_claim_v32_qualification_agent_request_v1(
                target_run_id=TARGET_RUN,
                qualification_run_id=QUALIFICATION_RUN,
            ),
            "submit": lambda: qualification_composition.submit_v32_qualification_agent_delivery_v1(
                target_run_id=TARGET_RUN,
                qualification_run_id=QUALIFICATION_RUN,
                stage="PROPOSAL",
                expected_request_digest="not-opened",
                expected_current_codex_presentation_digest="0" * 64,
                payload_utf8="not-written",
            ),
            "finalize": lambda: qualification_composition.finalize_v32_target_authority_from_completed_qualification_v1(
                target_run_id=TARGET_RUN,
                qualification_run_id=QUALIFICATION_RUN,
            ),
        }
        side_effect_names = (
            "build_v32_system_clock_v1",
            "LocalV32ActualCapabilityEvidenceStore",
            "LocalV32ActualCapabilityQualificationControllerStore",
            "LocalV32CurrentRootAgentMailbox",
            "V32OkxPublicBundleTransport",
            "load_v32_target_finalization_phase_times_if_started",
            "finalize_v32_target_authority",
        )
        for label, operation in operations.items():
            with self.subTest(label=label), ExitStack() as stack:
                stack.enter_context(
                    patch.object(
                        qualification_composition,
                        "load_v32_qualification_phase_a_authority",
                        side_effect=V32CurrentResearchAuthorityError(
                            "V32_PHASE_A_FIXTURE_REJECTED"
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(
                        qualification_composition,
                        "_qualification_composition_guard_v1",
                        return_value=nullcontext(),
                    )
                )
                side_effects = {
                    name: stack.enter_context(
                        patch.object(qualification_composition, name)
                    )
                    for name in side_effect_names
                }
                with self.assertRaisesRegex(
                    qualification_composition.V32QualificationCompositionError,
                    "V32_QUALIFICATION_PHASE_A_FULL_REPLAY_FAILED",
                ):
                    operation()
                self.assertTrue(
                    all(mock.call_count == 0 for mock in side_effects.values())
                )

    def test_phase_b_does_not_open_actual_receipt_before_phase_a_base(self) -> None:
        approval_path = self.root / self.fixture["approval_binding"]["path"]
        approval_path.write_bytes(approval_path.read_bytes() + b" ")
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.fixture["legacy_failure"],
        ), patch.object(
            loader_implementation, "_load_actual_capability_receipts"
        ) as actual_receipts:
            with self.assertRaisesRegex(
                V32CurrentResearchAuthorityError,
                "V32_THEORY_APPROVAL_BINDING_INVALID",
            ):
                replay_v32_actual_capability_qualification_receipt(
                    self.root,
                    qualification_authority_binding=self.fixture[
                        "qualification_authority_binding"
                    ],
                    qualification_receipt_binding=self.fixture[
                        "qualification_receipt_binding"
                    ],
                    capability_verifiers=fixture_capability_verifiers(),
                )
        actual_receipts.assert_not_called()

    def test_preflight_is_not_actual_capability_and_target_binds_actual_receipts(self) -> None:
        for capability, gate_id in CAPABILITY_GATE_MAP.items():
            with self.subTest(capability=capability):
                qualification_gate = self.fixture["qualification_gate_evidence"][
                    gate_id
                ]
                target_gate = self.fixture["target_gate_evidence"][gate_id]
                actual_binding = self.fixture[
                    "actual_capability_receipt_bindings"
                ][capability]
                self.assertIn("PREFLIGHT_READINESS", qualification_gate["evidence_kind"])
                self.assertEqual(
                    "PREFLIGHT_READINESS_ONLY_NOT_ACTUAL_CAPABILITY",
                    qualification_gate["claim_ceiling"],
                )
                self.assertEqual([actual_binding], target_gate["subject_bindings"])
                self.assertEqual(
                    ACTUAL_CAPABILITY_RECEIPT_SPECS[capability],
                    (actual_binding["schema_id"], actual_binding["digest_field"]),
                )

    def test_historical_compatibility_is_exact_terminal_identity_and_digest_only(self) -> None:
        gate_id = "Q2"
        old_paths = (
            "trade_system/theory_paper_v2/application/"
            "v32_actual_capability_qualification_controller.py",
            "trade_system/theory_paper_v2/infrastructure/authority/"
            "v32_actual_capability_attempt_ports.py",
            "trade_system/theory_paper_v2/infrastructure/"
            "v32_okx_public_bundle_transport.py",
            "trade_system/theory_paper_v2/infrastructure/"
            "v32_public_source_collector.py",
            "trade_system/theory_paper_v2/presentation/"
            "v32_qualification_composition.py",
        )
        subject = self.fixture["qualification_gate_subjects"][gate_id]
        with self.assertRaisesRegex(ValueError, "IMPLEMENTATION_INVALID"):
            build_v32_typed_preflight_gate_subject_v1(
                subject_id="arbitrary-new-pre-network-shape",
                gate_id=gate_id,
                profile=QUALIFICATION_PHASE_PROFILE,
                run_id="v32-arbitrary-new-qualification",
                target_run_id="v32-arbitrary-new-target",
                evaluated_at="2026-08-07T00:04:00Z",
                implementation_bindings={path: token(path) for path in old_paths},
                anchor_bindings=subject["anchor_bindings"],
            )

        forged_historical = copy.deepcopy(subject)
        forged_historical["run_id"] = FAILED_V32_QUALIFICATION_RUN_ID
        forged_historical["target_run_id"] = FAILED_V32_TARGET_RUN_ID
        forged_historical = self_digest(
            forged_historical, PREFLIGHT_SUBJECT_DIGEST_FIELD
        )
        with self.assertRaisesRegex(ValueError, "HISTORICAL_SUBJECT_INVALID"):
            verify_v32_typed_preflight_gate_subject_v1(forged_historical)

        historical_root = (
            Path(__file__).resolve().parents[1]
            / ".runtime/v32/qualification/qualification/subjects"
        )
        if historical_root.is_dir():
            for historical_gate, expected_digest in (
                FAILED_PRE_NETWORK_SUBJECT_DIGESTS.items()
            ):
                with self.subTest(historical_gate=historical_gate):
                    historical = load_json_strict(
                        historical_root / f"{historical_gate.lower()}.json"
                    )
                    self.assertEqual(
                        expected_digest,
                        verify_v32_typed_preflight_gate_subject_v1(historical),
                    )

        failed_public_source_root = (
            Path(__file__).resolve().parents[1]
            / ".runtime/v32/qualifications"
            / FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID
            / "qualification/subjects"
        )
        if failed_public_source_root.is_dir():
            for historical_gate, expected_digest in (
                FAILED_PUBLIC_SOURCE_SUBJECT_DIGESTS.items()
            ):
                with self.subTest(
                    failed_public_source_gate=historical_gate
                ):
                    historical = load_json_strict(
                        failed_public_source_root
                        / f"{historical_gate.lower()}.json"
                    )
                    self.assertEqual(
                        FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
                        historical["run_id"],
                    )
                    self.assertEqual(
                        FAILED_V32_PUBLIC_SOURCE_TARGET_RUN_ID,
                        historical["target_run_id"],
                    )
                    self.assertEqual(
                        expected_digest,
                        verify_v32_typed_preflight_gate_subject_v1(
                            historical
                        ),
                    )

        for qualification_id, target_id, expected_digests in (
            (
                FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
                FAILED_V32_OPENAPI_ROUTE_TARGET_RUN_ID,
                FAILED_OPENAPI_ROUTE_SUBJECT_DIGESTS,
            ),
            (
                FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID,
                FAILED_V32_FUNDING_TIME_TARGET_RUN_ID,
                FAILED_FUNDING_TIME_SUBJECT_DIGESTS,
            ),
            (
                FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
                FAILED_V32_MATERIALIZATION_TARGET_RUN_ID,
                FAILED_MATERIALIZATION_SUBJECT_DIGESTS,
            ),
            (
                FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
                FAILED_V32_CONTEXT_CAPACITY_TARGET_RUN_ID,
                FAILED_CONTEXT_CAPACITY_SUBJECT_DIGESTS,
            ),
            (
                EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
                EXPIRED_V32_AGENT_WINDOW_TARGET_RUN_ID,
                EXPIRED_AGENT_WINDOW_SUBJECT_DIGESTS,
            ),
            (
                EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID,
                EXPIRED_V32_CURRENT_CODEX_TARGET_RUN_ID,
                EXPIRED_CURRENT_CODEX_SUBJECT_DIGESTS,
            ),
            (
                FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
                FAILED_V32_CONCURRENT_MATERIALIZATION_TARGET_RUN_ID,
                FAILED_CONCURRENT_MATERIALIZATION_SUBJECT_DIGESTS,
            ),
        ):
            historical_root = (
                Path(__file__).resolve().parents[1]
                / ".runtime/v32/qualifications"
                / qualification_id
                / "qualification/subjects"
            )
            if not historical_root.is_dir():
                continue
            for historical_gate, expected_digest in expected_digests.items():
                with self.subTest(
                    qualification_id=qualification_id,
                    historical_gate=historical_gate,
                ):
                    historical = load_json_strict(
                        historical_root / f"{historical_gate.lower()}.json"
                    )
                    self.assertEqual(qualification_id, historical["run_id"])
                    self.assertEqual(target_id, historical["target_run_id"])
                    self.assertEqual(
                        expected_digest,
                        verify_v32_typed_preflight_gate_subject_v1(historical),
                    )

    def test_full_loader_requires_and_invokes_all_owning_replayers(self) -> None:
        calls: list[str] = []
        base = fixture_capability_verifiers()

        def observed(capability: str):
            def replay(**kwargs):
                calls.append(capability)
                return base[capability](**kwargs)

            return replay

        registry = {
            capability: observed(capability) for capability in CAPABILITY_KEYS
        }
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.fixture["legacy_failure"],
        ), patch(
            "trade_system.theory_paper_v2.infrastructure.authority."
            "v32_actual_capability_replay."
            "build_v32_actual_capability_full_replay_registry",
            return_value=registry,
        ) as built_in_registry:
            load_v32_current_research_authority(
                self.root, expected_run_id=TARGET_RUN
            )
        built_in_registry.assert_called_once_with()
        self.assertEqual(list(CAPABILITY_KEYS), calls)

    def test_arbitrary_self_digested_pass_cannot_replace_target_actual_receipt(self) -> None:
        root, fixture = self.fresh_fixture()
        gate = copy.deepcopy(fixture["target_gate_evidence"]["Q2"])
        gate["subject_bindings"] = [fixture["target_gate_subject_bindings"]["Q1"]]
        gate["subject_binding_count"] = 1
        gate = self_digest(gate, GATE_EVIDENCE_DIGEST_FIELD)
        gate_binding = rewrite_document(
            root,
            fixture["target_gate_bindings"]["Q2"]["path"],
            gate,
            GATE_EVIDENCE_DIGEST_FIELD,
        )
        phase = copy.deepcopy(fixture["target_phase"])
        phase["q0_q8_evidence_bindings"]["Q2"] = gate_binding
        rewrite_target_descendants(
            root,
            fixture,
            retirement=fixture["retirement"],
            retirement_binding=fixture["retirement_binding"],
            target_phase=phase,
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "TARGET_GATE_EVIDENCE_INVALID"
        ):
            self.load(root, fixture)

    def test_owning_replay_result_cannot_be_replaced_by_receipt_self_digest(self) -> None:
        registry = fixture_capability_verifiers()

        def weak_replay(**kwargs):
            return {
                "capability": "PUBLIC_SOURCE",
                "evidence_root_semantic_digest": kwargs[
                    "evidence_root_binding"
                ]["semantic_digest"],
                "full_replay_verified": False,
                "replay_network_calls": 0,
            }

        registry["PUBLIC_SOURCE"] = weak_replay
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "CAPABILITY_FULL_REPLAY_INVALID:PUBLIC_SOURCE",
        ):
            self.load(capability_verifiers=registry)

        root, fixture = self.fresh_fixture()
        evidence_path = root / fixture["capability_root_bindings"]["PUBLIC_SOURCE"][
            "path"
        ]
        evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "CAPABILITY_EVIDENCE_ROOT_INVALID:PUBLIC_SOURCE",
        ):
            self.load(root, fixture)

    def test_capability_evidence_root_alias_is_rejected_even_when_fully_rebound(self) -> None:
        root, fixture = self.fresh_fixture()
        capability = "PUBLIC_SOURCE"
        original = fixture["capability_roots"][capability]
        alias_binding = write_document(
            root,
            f"{AUTHORITY_ROOT}/evidence/roots/public-source-alias.json",
            original,
        )
        started_at, completed_at = (
            fixture["actual_capability_receipts"][capability]["started_at"],
            fixture["actual_capability_receipts"][capability]["completed_at"],
        )
        receipt = build_v32_actual_capability_receipt_v1(
            capability=capability,
            receipt_id="v32-public-source-aliased-root",
            qualification_run_id=QUALIFICATION_RUN,
            target_run_id=TARGET_RUN,
            started_at=started_at,
            completed_at=completed_at,
            qualification_authority_binding=fixture[
                "qualification_authority_binding"
            ],
            evidence_root_binding=alias_binding,
        )
        receipt_binding = rewrite_document(
            root,
            fixture["actual_capability_receipt_bindings"][capability]["path"],
            receipt,
            ACTUAL_CAPABILITY_RECEIPT_SPECS[capability][1],
        )
        qualification_receipt = copy.deepcopy(fixture["qualification_receipt"])
        qualification_receipt["capability_evidence_bindings"][capability] = (
            receipt_binding
        )
        qualification_receipt = self_digest(
            qualification_receipt, QUALIFICATION_RECEIPT_DIGEST_FIELD
        )
        qualification_receipt_binding = rewrite_document(
            root,
            fixture["qualification_receipt_binding"]["path"],
            qualification_receipt,
            QUALIFICATION_RECEIPT_DIGEST_FIELD,
        )
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=fixture["legacy_failure"],
        ), self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "CAPABILITY_EVIDENCE_ROOT_INVALID:PUBLIC_SOURCE",
        ):
            replay_v32_actual_capability_qualification_receipt(
                root,
                qualification_authority_binding=fixture[
                    "qualification_authority_binding"
                ],
                qualification_receipt_binding=qualification_receipt_binding,
                capability_verifiers=fixture_capability_verifiers(),
            )

    def test_actual_capability_receipts_must_postdate_qualification_authority(self) -> None:
        root, fixture = self.fresh_fixture()
        capability = "CURRENT_CODEX"
        stale = build_v32_actual_capability_receipt_v1(
            capability=capability,
            receipt_id="v32-current_codex-stale-actual-capability",
            qualification_run_id=QUALIFICATION_RUN,
            target_run_id=TARGET_RUN,
            started_at="2026-08-07T00:05:30Z",
            completed_at="2026-08-07T00:05:45Z",
            qualification_authority_binding=fixture[
                "qualification_authority_binding"
            ],
            evidence_root_binding=fixture["capability_root_bindings"][capability],
        )
        stale_binding = rewrite_document(
            root,
            fixture["actual_capability_receipt_bindings"][capability]["path"],
            stale,
            ACTUAL_CAPABILITY_RECEIPT_SPECS[capability][1],
        )
        qualification_receipt = copy.deepcopy(fixture["qualification_receipt"])
        qualification_receipt["capability_evidence_bindings"][capability] = (
            stale_binding
        )
        qualification_receipt = self_digest(
            qualification_receipt, QUALIFICATION_RECEIPT_DIGEST_FIELD
        )
        qualification_receipt_binding = rewrite_document(
            root,
            fixture["qualification_receipt_binding"]["path"],
            qualification_receipt,
            QUALIFICATION_RECEIPT_DIGEST_FIELD,
        )
        retirement = copy.deepcopy(fixture["retirement"])
        retirement["qualification_receipt_binding"] = qualification_receipt_binding
        retirement = self_digest(
            retirement, QUALIFICATION_RETIREMENT_DIGEST_FIELD
        )
        retirement_binding = rewrite_document(
            root,
            fixture["retirement_binding"]["path"],
            retirement,
            QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        )
        gate_id = CAPABILITY_GATE_MAP[capability]
        target_gate = build_v32_qualification_gate_evidence_v1(
            gate_id=gate_id,
            profile=TARGET_PHASE_PROFILE,
            run_id=TARGET_RUN,
            target_run_id=TARGET_RUN,
            evaluated_at="2026-08-07T00:10:00Z",
            subject_bindings=[stale_binding],
        )
        target_gate_binding = rewrite_document(
            root,
            fixture["target_gate_bindings"][gate_id]["path"],
            target_gate,
            GATE_EVIDENCE_DIGEST_FIELD,
        )
        target_phase = copy.deepcopy(fixture["target_phase"])
        target_phase["q0_q8_evidence_bindings"][gate_id] = target_gate_binding
        rewrite_target_descendants(
            root,
            fixture,
            retirement=retirement,
            retirement_binding=retirement_binding,
            target_phase=target_phase,
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "CHRONOLOGY_INVALID"
        ):
            self.load(root, fixture)

    def test_legacy_loader_failure_precedes_every_v32_document_read(self) -> None:
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            side_effect=ValueError("legacy drift"),
        ), patch(f"{LOADER_MODULE}._strict_document") as strict:
            with self.assertRaisesRegex(
                V32CurrentResearchAuthorityError, "LEGACY_FULL_LOADER_FAILED"
            ):
                load_v32_current_research_authority(
                    self.root, expected_run_id=TARGET_RUN
                )
        strict.assert_not_called()
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            side_effect=ValueError("legacy drift"),
        ), patch(f"{LOADER_MODULE}._strict_document") as phase_a_strict:
            with self.assertRaisesRegex(
                V32CurrentResearchAuthorityError, "LEGACY_FULL_LOADER_FAILED"
            ):
                load_v32_qualification_phase_a_authority(
                    self.root,
                    expected_target_run_id=TARGET_RUN,
                    expected_qualification_run_id=QUALIFICATION_RUN,
                )
        phase_a_strict.assert_not_called()

    def test_runtime_exact_path_set_and_physical_sha_are_enforced(self) -> None:
        for mode in ("MISSING", "EXTRA"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture = build_fixture(root, runtime_mode=mode)
                with self.assertRaisesRegex(
                    V32CurrentResearchAuthorityError,
                    "RUNTIME_CLOSURE_PHYSICAL_REPLAY_INVALID",
                ):
                    self.load(root, fixture)
        (self.root / "runtime/probe.py").write_text("VALUE = 99\n", encoding="utf-8")
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "RUNTIME_CLOSURE_PHYSICAL_REPLAY_INVALID",
        ):
            self.load()

    def test_symlink_wrong_run_qualification_profile_and_v31_schema_fail(self) -> None:
        original = (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).read_bytes()
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.fixture["legacy_failure"],
        ):
            with self.assertRaisesRegex(
                V32CurrentResearchAuthorityError, "PROFILE_OR_RUN"
            ):
                load_v32_current_research_authority(
                    self.root,
                    expected_run_id="wrong-target-run",
                    capability_verifiers=fixture_capability_verifiers(),
                )

        (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).write_bytes(
            canonical_bytes(self.fixture["qualification_authority"]) + b"\n"
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "PROFILE_OR_RUN"
        ):
            self.load()

        v31 = self_digest(
            {"schema_id": "theory_paper_v31_current_research_authority"},
            AUTHORITY_DIGEST_FIELD,
        )
        (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).write_bytes(
            canonical_bytes(v31) + b"\n"
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "TARGET_AUTHORITY_INVALID"
        ):
            self.load()

        (self.root / V32_CURRENT_RESEARCH_AUTHORITY_PATH).write_bytes(original)
        approval_path = self.root / self.fixture["approval_binding"]["path"]
        outside = self.root.parent / f"{self.root.name}-approval-copy.json"
        outside.write_bytes(approval_path.read_bytes())
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        approval_path.unlink()
        approval_path.symlink_to(outside)
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "QUALIFICATION_RUNTIME_NAMESPACE_INVALID",
        ):
            self.load()

    def test_resigned_cross_document_disconnect_and_permission_expansion_fail(self) -> None:
        fixture = self.fixture
        q_phase = copy.deepcopy(fixture["qualification_phase"])
        q_phase["runtime_manifest_digest"] = "f" * 64
        q_phase = self_digest(q_phase, PHASE_A_DIGEST_FIELD)
        q_phase_binding = rewrite_document(
            self.root,
            fixture["qualification_phase_binding"]["path"],
            q_phase,
            PHASE_A_DIGEST_FIELD,
        )
        q_authorization = copy.deepcopy(fixture["qualification_authorization"])
        q_authorization["phase_a_receipt_binding"] = q_phase_binding
        q_authorization = self_digest(
            q_authorization, AUTHORIZATION_RECEIPT_DIGEST_FIELD
        )
        q_authorization_binding = rewrite_document(
            self.root,
            fixture["qualification_authorization_binding"]["path"],
            q_authorization,
            AUTHORIZATION_RECEIPT_DIGEST_FIELD,
        )
        q_authority = copy.deepcopy(fixture["qualification_authority"])
        q_authority["phase_a_receipt_binding"] = q_phase_binding
        q_authority["authorization_receipt_binding"] = q_authorization_binding
        q_authority = self_digest(q_authority, AUTHORITY_DIGEST_FIELD)
        q_authority_binding = rewrite_document(
            self.root,
            fixture["qualification_authority_binding"]["path"],
            q_authority,
            AUTHORITY_DIGEST_FIELD,
        )
        q_receipt = copy.deepcopy(fixture["qualification_receipt"])
        q_receipt["qualification_authority_binding"] = q_authority_binding
        q_receipt = self_digest(q_receipt, QUALIFICATION_RECEIPT_DIGEST_FIELD)
        q_receipt_binding = rewrite_document(
            self.root,
            fixture["qualification_receipt_binding"]["path"],
            q_receipt,
            QUALIFICATION_RECEIPT_DIGEST_FIELD,
        )
        retirement = copy.deepcopy(fixture["retirement"])
        retirement["qualification_authority_binding"] = q_authority_binding
        retirement["qualification_receipt_binding"] = q_receipt_binding
        retirement = self_digest(retirement, QUALIFICATION_RETIREMENT_DIGEST_FIELD)
        retirement_binding = rewrite_document(
            self.root,
            fixture["retirement_binding"]["path"],
            retirement,
            QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        )
        target_phase = copy.deepcopy(fixture["target_phase"])
        target_phase["predecessor_retirement_digest"] = retirement[
            QUALIFICATION_RETIREMENT_DIGEST_FIELD
        ]
        target_phase = self_digest(target_phase, PHASE_A_DIGEST_FIELD)
        target_phase_binding = rewrite_document(
            self.root,
            fixture["target_phase_binding"]["path"],
            target_phase,
            PHASE_A_DIGEST_FIELD,
        )
        target_authorization = copy.deepcopy(fixture["target_authorization"])
        target_authorization["phase_a_receipt_binding"] = target_phase_binding
        target_authorization["qualification_retirement_binding"] = retirement_binding
        target_authorization = self_digest(
            target_authorization, AUTHORIZATION_RECEIPT_DIGEST_FIELD
        )
        target_authorization_binding = rewrite_document(
            self.root,
            fixture["target_authorization_binding"]["path"],
            target_authorization,
            AUTHORIZATION_RECEIPT_DIGEST_FIELD,
        )
        target_authority = copy.deepcopy(fixture["target_authority"])
        target_authority["predecessor_authority_binding"] = q_authority_binding
        target_authority["phase_a_receipt_binding"] = target_phase_binding
        target_authority[
            "authorization_receipt_binding"
        ] = target_authorization_binding
        target_authority["qualification_retirement_binding"] = retirement_binding
        target_authority = self_digest(target_authority, AUTHORITY_DIGEST_FIELD)
        rewrite_document(
            self.root,
            V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
            target_authority,
            AUTHORITY_DIGEST_FIELD,
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "ACTUAL_CAPABILITY_RECEIPT_CHAIN_INVALID|PHASE_CHAIN_DISCONNECTED",
        ):
            self.load()

        fresh_root, permission_fixture = self.fresh_fixture()
        authority = copy.deepcopy(permission_fixture["target_authority"])
        for field in (
            "account_access",
            "paper_trading",
            "live_trading",
            "order_submission",
            "credential_access",
            "funds_access",
        ):
            with self.subTest(field=field):
                expanded = copy.deepcopy(authority)
                expanded[field] = True
                expanded = self_digest(expanded, AUTHORITY_DIGEST_FIELD)
                rewrite_document(
                    fresh_root,
                    V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
                    expanded,
                    AUTHORITY_DIGEST_FIELD,
                )
                with self.assertRaisesRegex(
                    V32CurrentResearchAuthorityError, "TARGET_AUTHORITY_INVALID"
                ):
                    self.load(fresh_root, permission_fixture)

    def test_gate_envelope_and_subject_files_are_all_physically_required(self) -> None:
        root, fixture = self.fresh_fixture()
        (root / fixture["qualification_gate_bindings"]["Q0"]["path"]).unlink()
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "QUALIFICATION_GATE_EVIDENCE_INVALID",
        ):
            self.load(root, fixture)

        root, fixture = self.fresh_fixture()
        (root / fixture["target_gate_subject_bindings"]["Q1"]["path"]).unlink()
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "TARGET_GATE_EVIDENCE_INVALID"
        ):
            self.load(root, fixture)

        root, fixture = self.fresh_fixture()
        gate_path = root / fixture["target_gate_bindings"]["Q2"]["path"]
        gate_path.write_bytes(gate_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "TARGET_GATE_EVIDENCE_INVALID"
        ):
            self.load(root, fixture)

        root, fixture = self.fresh_fixture()
        subject_path = (
            root / fixture["qualification_gate_subject_bindings"]["Q3"]["path"]
        )
        subject_path.write_bytes(subject_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "QUALIFICATION_GATE_EVIDENCE_INVALID",
        ):
            self.load(root, fixture)

        root, fixture = self.fresh_fixture()
        replacement = copy.deepcopy(fixture["qualification_gate_subjects"]["Q4"])
        replacement["result"] = "SELF_RESIGNED_REPLACEMENT"
        replacement = self_digest(replacement, "gate_subject_digest")
        rewrite_document(
            root,
            fixture["qualification_gate_subject_bindings"]["Q4"]["path"],
            replacement,
            "gate_subject_digest",
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "QUALIFICATION_GATE_EVIDENCE_INVALID",
        ):
            self.load(root, fixture)

    def test_capabilities_must_map_to_exact_qualification_gate_bindings(self) -> None:
        root, fixture = self.fresh_fixture()
        receipt = copy.deepcopy(fixture["qualification_receipt"])
        receipt["capability_evidence_bindings"]["CURRENT_CODEX"] = receipt[
            "capability_evidence_bindings"
        ]["OUTCOME_MONITOR"]
        receipt = self_digest(receipt, QUALIFICATION_RECEIPT_DIGEST_FIELD)
        receipt_binding = rewrite_document(
            root,
            fixture["qualification_receipt_binding"]["path"],
            receipt,
            QUALIFICATION_RECEIPT_DIGEST_FIELD,
        )
        retirement = copy.deepcopy(fixture["retirement"])
        retirement["qualification_receipt_binding"] = receipt_binding
        retirement = self_digest(
            retirement, QUALIFICATION_RETIREMENT_DIGEST_FIELD
        )
        retirement_binding = rewrite_document(
            root,
            fixture["retirement_binding"]["path"],
            retirement,
            QUALIFICATION_RETIREMENT_DIGEST_FIELD,
        )
        rewrite_target_descendants(
            root,
            fixture,
            retirement=retirement,
            retirement_binding=retirement_binding,
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "QUALIFICATION_RECEIPT_BINDING_INVALID",
        ):
            self.load(root, fixture)

    def test_gate_profile_run_target_and_retirement_chronology_are_exact(self) -> None:
        root, fixture = self.fresh_fixture()
        wrong_context = copy.deepcopy(fixture["target_gate_evidence"]["Q5"])
        wrong_context["profile"] = QUALIFICATION_PHASE_PROFILE
        wrong_context["run_id"] = QUALIFICATION_RUN
        wrong_context = self_digest(
            wrong_context, GATE_EVIDENCE_DIGEST_FIELD
        )
        wrong_context_binding = rewrite_document(
            root,
            fixture["target_gate_bindings"]["Q5"]["path"],
            wrong_context,
            GATE_EVIDENCE_DIGEST_FIELD,
        )
        phase = copy.deepcopy(fixture["target_phase"])
        phase["q0_q8_evidence_bindings"]["Q5"] = wrong_context_binding
        rewrite_target_descendants(
            root,
            fixture,
            retirement=fixture["retirement"],
            retirement_binding=fixture["retirement_binding"],
            target_phase=phase,
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "TARGET_GATE_EVIDENCE_INVALID"
        ):
            self.load(root, fixture)

        root, fixture = self.fresh_fixture()
        inverted = build_v32_qualification_gate_evidence_v1(
            gate_id="Q6",
            profile=TARGET_PHASE_PROFILE,
            run_id=TARGET_RUN,
            target_run_id=TARGET_RUN,
            evaluated_at="2026-08-07T00:08:59Z",
            subject_bindings=[fixture["target_gate_subject_bindings"]["Q6"]],
        )
        inverted_binding = rewrite_document(
            root,
            fixture["target_gate_bindings"]["Q6"]["path"],
            inverted,
            GATE_EVIDENCE_DIGEST_FIELD,
        )
        phase = copy.deepcopy(fixture["target_phase"])
        phase["q0_q8_evidence_bindings"]["Q6"] = inverted_binding
        rewrite_target_descendants(
            root,
            fixture,
            retirement=fixture["retirement"],
            retirement_binding=fixture["retirement_binding"],
            target_phase=phase,
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "TARGET_GATE_EVIDENCE_INVALID"
        ):
            self.load(root, fixture)

    def test_path_traversal_alternate_root_and_chronology_fail(self) -> None:
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "AUTHORITY_PATH_INVALID"
        ):
            with patch(
                f"{LOADER_MODULE}.load_v31_active_authorization_chain",
                return_value=self.fixture["legacy_chain"],
            ), patch(
                f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
                return_value=self.fixture["legacy_failure"],
            ):
                load_v32_current_research_authority(
                    self.root,
                    expected_run_id=TARGET_RUN,
                    authority_relative_path="config/../escape.json",
                    capability_verifiers=fixture_capability_verifiers(),
                )
        authority = copy.deepcopy(self.fixture["target_authority"])
        authority["recorded_at"] = "2026-08-07T00:05:30Z"
        authority = self_digest(authority, AUTHORITY_DIGEST_FIELD)
        rewrite_document(
            self.root,
            V32_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix(),
            authority,
            AUTHORITY_DIGEST_FIELD,
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError, "CHRONOLOGY_INVALID"
        ):
            self.load()

    def test_all_contract_supports_are_physical_and_replayed_by_owners(self) -> None:
        manifest = self.fixture["manifest"]
        bindings = manifest["support_document_bindings"]
        self.assertEqual(SUPPORT_BINDING_KEYS, tuple(bindings))
        for key in SUPPORT_BINDING_KEYS:
            with self.subTest(key=key):
                binding = bindings[key]
                self.assertEqual(
                    SUPPORT_DOCUMENT_BINDING_SPECS[key],
                    (binding["schema_id"], binding["digest_field"]),
                )
                self.assertEqual(
                    self.fixture["contract"]["support_bindings"][key],
                    binding["semantic_digest"],
                )
                self.assertEqual(
                    binding["physical_sha256"],
                    hashlib.sha256(
                        (self.root / binding["path"]).read_bytes()
                    ).hexdigest(),
                )

        verifier_names = (
            "verify_v32_association_preregistration",
            "verify_v32_authorized_revision_support_bundle_v1",
            "verify_v32_clock_and_tick_policy_v1",
            "verify_v32_evaluation_contract",
            "verify_v32_public_outcome_adapter_contract_v1",
            "verify_v32_recovery_supervision_policy_v1",
            "verify_v31_native_sentiment_source_registry",
            "verify_live_v32_workspace_freeze_v1",
        )
        originals = {
            name: getattr(loader_implementation, name) for name in verifier_names
        }
        with ExitStack() as stack:
            calls = {
                name: stack.enter_context(
                    patch.object(
                        loader_implementation,
                        name,
                        wraps=originals[name],
                    )
                )
                for name in verifier_names
            }
            component_loader = stack.enter_context(
                patch.object(
                    loader_implementation,
                    "_load_revision_component",
                    wraps=loader_implementation._load_revision_component,
                )
            )
            projected = self.load()
        self.assertEqual(V32_APPLICATION_PROJECTION_KEYS, tuple(projected))
        for verifier in calls.values():
            self.assertGreaterEqual(verifier.call_count, 1)
        self.assertEqual(
            set(loader_implementation._REVISION_COMPONENT_SPECS),
            {call.kwargs["role"] for call in component_loader.call_args_list},
        )
        self.assertEqual(5, component_loader.call_count)

    def test_support_physical_drift_and_component_drift_fail_closed(self) -> None:
        clock_binding = self.fixture["support_document_bindings"][
            "clock_policy_digest"
        ]
        clock_path = self.root / clock_binding["path"]
        clock_path.write_bytes(clock_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "SUPPORT_DOCUMENT_INVALID:clock_policy_digest",
        ):
            self.load()

        root, fixture = self.fresh_fixture()
        component = fixture["revision_component_bindings"][
            "context_compaction_policy"
        ]
        component_path = root / component["relative_ref"]
        component_path.write_bytes(component_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "REVISION_SUPPORT_COMPONENT_INVALID:context_compaction_policy",
        ):
            self.load(root, fixture)

    def test_resigned_support_semantic_drift_and_contract_mismatch_fail(self) -> None:
        root = Path(tempfile.mkdtemp(dir=self.temp.name))
        drifted = build_fixture(
            root, semantic_drift_key="clock_policy_digest"
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "SUPPORT_DOCUMENT_INVALID:clock_policy_digest",
        ):
            self.load(root, drifted)

        root = Path(tempfile.mkdtemp(dir=self.temp.name))
        mismatched = build_fixture(
            root, contract_mismatch_key="clock_policy_digest"
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "SUPPORT_CONTRACT_DIGEST_MISMATCH:clock_policy_digest",
        ):
            self.load(root, mismatched)

    def test_loader_workspace_support_uses_live_git_state(self) -> None:
        (self.root / ".gitignore").write_text(
            "config/\n.runtime/\n# drift\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "SUPPORT_DOCUMENT_INVALID:workspace_freeze_receipt_digest",
        ):
            self.load()

    def test_new_authority_rejects_legacy_workspace_schema(self) -> None:
        root = Path(tempfile.mkdtemp(dir=self.temp.name))
        fixture = build_fixture(root, legacy_workspace=True)
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "POSTCOMMIT_WORKSPACE_SUPPORT_REQUIRED",
        ):
            self.load(root, fixture)

    def test_loader_reopens_both_postcommit_execution_receipts(self) -> None:
        workspace = self.fixture["support_documents"][
            "workspace_freeze_receipt_digest"
        ]
        aggregate_path = self.root / workspace[
            "postcommit_regression_aggregate_binding"
        ]["path"]
        aggregate = load_json_strict(aggregate_path)
        receipt_binding = next(
            iter(aggregate["execution_receipt_bindings"].values())
        )
        receipt_path = self.root / receipt_binding["path"]
        receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CurrentResearchAuthorityError,
            "SUPPORT_DOCUMENT_INVALID:workspace_freeze_receipt_digest",
        ):
            self.load()


if __name__ == "__main__":
    unittest.main()
