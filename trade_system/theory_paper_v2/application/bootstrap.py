"""Portable cluster manifests, skill installation, and resolution receipts."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    write_once_json,
)


SKILL_ROLES = {
    "trade-decision-proposer": "PROPOSER",
    "trade-decision-challenger": "CHALLENGER",
    "trade-bounded-selector": "SELECTOR",
}

REQUIRED_COMPONENT_IDS = (
    "APPLICATION_DECISION_SESSION",
    "APPLICATION_COMMIT",
    "DOMAIN_EVIDENCE_ADMISSION",
    "DOMAIN_CANDIDATE_ASSEMBLER",
    "DOMAIN_PAYOFF_RISK_CALCULATOR",
    "DOMAIN_CONSTRAINT_ENGINE",
    "DOMAIN_STATE_REDUCER",
    "DOMAIN_GOVERNANCE",
    "INFRASTRUCTURE_AGENT_ADAPTER",
    "INFRASTRUCTURE_CONTENT_STORE",
    "INFRASTRUCTURE_OFFLINE_REPLAY",
    "INFRASTRUCTURE_UNIT_OF_WORK",
)

KERNEL_COMPONENT_SPECS: dict[str, dict[str, object]] = {
    "APPLICATION_DECISION_SESSION": {
        "entrypoint": (
            "trade_system.theory_paper_v2.application.decision_session:"
            "run_decision_session"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/application/decision_session.py",
        ),
        "input_refs": ("decision_context", "frozen_role_outputs"),
        "output_refs": ("decision_session_result",),
    },
    "APPLICATION_COMMIT": {
        "entrypoint": (
            "trade_system.theory_paper_v2.application.commit:"
            "commit_e0_session"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/application/commit.py",
        ),
        "input_refs": ("governance_assessment_receipt", "replay_outcome"),
        "output_refs": ("e0_commit_plan", "commit_receipt"),
    },
    "DOMAIN_EVIDENCE_ADMISSION": {
        "entrypoint": (
            "trade_system.theory_paper_v2.domain.evidence.service:"
            "admit_evidence"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/domain/evidence/model.py",
            "trade_system/theory_paper_v2/domain/evidence/service.py",
        ),
        "input_refs": ("raw_evidence_record", "time_authority_receipt"),
        "output_refs": ("evidence_admission_receipt",),
    },
    "DOMAIN_CANDIDATE_ASSEMBLER": {
        "entrypoint": (
            "trade_system.theory_paper_v2.domain.deliberation.assembly:"
            "assemble_candidate_bundles"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/domain/deliberation/model.py",
            "trade_system/theory_paper_v2/domain/deliberation/assembly.py",
        ),
        "input_refs": ("proposed_action_plan", "challenge_disposition"),
        "output_refs": ("candidate_bundle_set",),
    },
    "DOMAIN_PAYOFF_RISK_CALCULATOR": {
        "entrypoint": (
            "trade_system.theory_paper_v2.domain.evaluation.payoff:"
            "build_path_payoff_matrix"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/domain/evaluation/model.py",
            "trade_system/theory_paper_v2/domain/evaluation/payoff.py",
            "trade_system/theory_paper_v2/domain/evaluation/opportunity.py",
            "trade_system/theory_paper_v2/domain/evaluation/planning.py",
            "trade_system/theory_paper_v2/domain/position/risk.py",
        ),
        "input_refs": ("candidate_bundle_set", "path_evidence"),
        "output_refs": (
            "path_payoff_matrix_spec",
            "recursive_feasibility_receipt",
        ),
    },
    "DOMAIN_CONSTRAINT_ENGINE": {
        "entrypoint": (
            "trade_system.theory_paper_v2.domain.governance.constraints:"
            "evaluate_hard_constraints"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/domain/governance/model.py",
            "trade_system/theory_paper_v2/domain/governance/constraints.py",
        ),
        "input_refs": ("candidate_bundle_set", "constraint_registry"),
        "output_refs": ("constraint_verdict_set", "feasible_action_set"),
    },
    "DOMAIN_STATE_REDUCER": {
        "entrypoint": (
            "trade_system.theory_paper_v2.domain.strategic.reducer:"
            "reduce_strategic_episode"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/domain/strategic/model.py",
            "trade_system/theory_paper_v2/domain/strategic/genesis.py",
            "trade_system/theory_paper_v2/domain/strategic/reducer.py",
            "trade_system/theory_paper_v2/domain/position/risk.py",
            "trade_system/theory_paper_v2/domain/position/stage.py",
            "trade_system/theory_paper_v2/domain/position/supervision.py",
            "trade_system/theory_paper_v2/domain/geometry/reducer.py",
            "trade_system/theory_paper_v2/domain/reentry/reducer.py",
        ),
        "input_refs": ("accepted_aggregate_heads", "authorized_current_action"),
        "output_refs": ("aggregate_state_updates", "transition_receipts"),
    },
    "DOMAIN_GOVERNANCE": {
        "entrypoint": (
            "trade_system.theory_paper_v2.domain.governance.assessment:"
            "assess_selection"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/domain/governance/assessment.py",
        ),
        "input_refs": ("agent_selection", "feasible_action_set"),
        "output_refs": ("governance_assessment_receipt",),
    },
    "INFRASTRUCTURE_AGENT_ADAPTER": {
        "entrypoint": (
            "trade_system.theory_paper_v2.infrastructure.agent_adapter."
            "adapter:OneShotAgentAdapter"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/infrastructure/agent_adapter/adapter.py",
        ),
        "input_refs": ("resolved_role_input_bundle", "skill_resolution_receipt"),
        "output_refs": ("raw_agent_result",),
    },
    "INFRASTRUCTURE_CONTENT_STORE": {
        "entrypoint": (
            "trade_system.theory_paper_v2.infrastructure.content_store.store:"
            "ContentAddressedStore"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/infrastructure/content_store/store.py",
        ),
        "input_refs": ("immutable_bytes",),
        "output_refs": ("content_addressed_ref",),
    },
    "INFRASTRUCTURE_OFFLINE_REPLAY": {
        "entrypoint": (
            "trade_system.theory_paper_v2.infrastructure.offline_portfolio."
            "engine:replay_protective_bar"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/infrastructure/offline_portfolio/model.py",
            "trade_system/theory_paper_v2/infrastructure/offline_portfolio/engine.py",
            "trade_system/theory_paper_v2/infrastructure/frozen_replay/bundle.py",
            "trade_system/theory_paper_v2/infrastructure/legacy_v1/adapter.py",
            "trade_system/theory_paper_v2/domain/matching/model.py",
            "trade_system/theory_paper_v2/domain/matching/engine.py",
        ),
        "input_refs": (
            "counterfactual_portfolio_state",
            "closed_bar",
            "frozen_replay_bundle",
            "legacy_cycle_envelope",
        ),
        "output_refs": (
            "portfolio_replay_result",
            "validated_frozen_replay_bundle",
        ),
    },
    "INFRASTRUCTURE_UNIT_OF_WORK": {
        "entrypoint": (
            "trade_system.theory_paper_v2.infrastructure.event_store.store:"
            "FileUnitOfWork"
        ),
        "source_files": (
            "trade_system/theory_paper_v2/infrastructure/event_store/models.py",
            "trade_system/theory_paper_v2/infrastructure/event_store/store.py",
            "trade_system/theory_paper_v2/infrastructure/event_store/compatibility.py",
        ),
        "input_refs": ("e0_commit_plan",),
        "output_refs": ("commit_receipt", "aggregate_head_receipt"),
    },
}


class BootstrapError(ValueError):
    pass


def _normal_relative(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    posix = PurePosixPath(relative.as_posix())
    if posix.is_absolute() or ".." in posix.parts or "." in posix.parts:
        raise BootstrapError("SKILL_PACKAGE_PATH_INVALID")
    return posix.as_posix()


def skill_package_entries(package_root: Path) -> tuple[dict[str, Any], ...]:
    root = Path(package_root).resolve(strict=True)
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().encode()):
        if path.is_symlink():
            raise BootstrapError("SKILL_PACKAGE_SYMLINK_FORBIDDEN")
        if path.is_dir():
            continue
        if not path.is_file():
            raise BootstrapError("SKILL_PACKAGE_SPECIAL_FILE_FORBIDDEN")
        relative = _normal_relative(path, root)
        if any(part.startswith(".") for part in PurePosixPath(relative).parts):
            raise BootstrapError("SKILL_PACKAGE_HIDDEN_FILE_FORBIDDEN")
        payload = path.read_bytes()
        mode = path.stat().st_mode
        entries.append(
            {
                "relative_posix_path": relative,
                "executable": bool(mode & stat.S_IXUSR),
                "byte_length": len(payload),
                "file_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    required = {"SKILL.md", "agents/openai.yaml"}
    paths = {entry["relative_posix_path"] for entry in entries}
    if not required.issubset(paths):
        raise BootstrapError("SKILL_PACKAGE_REQUIRED_FILE_MISSING")
    return tuple(entries)


def skill_package_digest(entries: tuple[Mapping[str, Any], ...]) -> str:
    return canonical_digest(
        [
            {
                "relative_posix_path": entry["relative_posix_path"],
                "executable": entry["executable"],
                "byte_length": entry["byte_length"],
                "file_sha256": entry["file_sha256"],
            }
            for entry in entries
        ]
    )


def build_role_skill_manifest(package_root: Path, skill_id: str) -> dict[str, Any]:
    if skill_id not in SKILL_ROLES:
        raise BootstrapError("SKILL_ID_UNREGISTERED")
    entries = skill_package_entries(package_root)
    package_digest = skill_package_digest(entries)
    manifest = {
        "schema_id": "role_skill_package_manifest",
        "schema_version": "1.0.0",
        "skill_id": skill_id,
        "skill_version": "1.0.0",
        "role_id": SKILL_ROLES[skill_id],
        "role_contract_ref": f"role-contract:{SKILL_ROLES[skill_id]}:1.0.0",
        "package_entries": [
            {
                **entry,
                "file_bytes_ref": (
                    f"immutable-byte-blob:{skill_id}:"
                    f"{entry['relative_posix_path']}:{entry['file_sha256']}"
                ),
            }
            for entry in entries
        ],
        "skill_md_ref": (
            f"immutable-byte-blob:{skill_id}:SKILL.md:"
            f"{next(e['file_sha256'] for e in entries if e['relative_posix_path'] == 'SKILL.md')}"
        ),
        "agents_openai_yaml_ref": (
            f"immutable-byte-blob:{skill_id}:agents/openai.yaml:"
            f"{next(e['file_sha256'] for e in entries if e['relative_posix_path'] == 'agents/openai.yaml')}"
        ),
        "package_digest": package_digest,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(manifest, "manifest_digest")


def build_cluster_manifest(
    skill_manifests: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if set(skill_manifests) != set(SKILL_ROLES):
        raise BootstrapError("CLUSTER_SKILL_SET_MISMATCH")
    ordered_skills = (
        "trade-decision-proposer",
        "trade-decision-challenger",
        "trade-bounded-selector",
    )
    manifest = {
        "schema_id": "cluster_manifest",
        "schema_version": "1.0.0",
        "cluster_id": "THEORY_AGENT_V2_E0_CLUSTER",
        "cluster_version": "1.0.0",
        "required_role_contract_refs": [
            f"role-contract:{SKILL_ROLES[skill_id]}:1.0.0"
            for skill_id in ordered_skills
        ],
        "required_role_ids": [SKILL_ROLES[skill_id] for skill_id in ordered_skills],
        "required_role_skill_refs": [
            (
                f"role-skill-package:{skill_id}:"
                f"{skill_manifests[skill_id]['manifest_digest']}"
            )
            for skill_id in ordered_skills
        ],
        "required_kernel_component_refs": [
            f"kernel-component:{component_id}:1.0.0"
            for component_id in REQUIRED_COMPONENT_IDS
        ],
        "bootstrap_producer_id": "BOOTSTRAP_TRUST_ROOT",
        "fixed_dag": (
            "PROPOSE_ONCE_CHALLENGE_ONCE_CALCULATE_ONCE_SELECT_ONCE_GOVERN_ONCE"
        ),
        "specialist_proposer_fanout": "OFF",
        "max_proposer_candidate_paths": 8,
        "max_candidate_plans_per_path": 4,
        "max_compatible_bundles": 32,
        "max_superseding_sessions_per_cutoff": 1,
        "role_timeout_ms": {
            "PROPOSER": 120_000,
            "CHALLENGER": 120_000,
            "SELECTOR": 60_000,
        },
        "role_token_cap": {
            "PROPOSER": 12_000,
            "CHALLENGER": 10_000,
            "SELECTOR": 5_000,
        },
        "role_tool_call_cap": {
            "PROPOSER": 0,
            "CHALLENGER": 0,
            "SELECTOR": 0,
        },
        "total_cost_cap": "10",
        "work_artifact_layout": (
            ".runtime/theory-paper-v2/<offline_run_id>/work/"
            "<decision_session_id>/<producer_id>/<object_id>"
        ),
        "missing_required_role_policy": "SESSION_INCOMPLETE_NO_COMMIT",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(manifest, "manifest_digest")


def install_skill_package(source: Path, target: Path) -> str:
    source_path = Path(source).resolve(strict=True)
    target_path = Path(target)
    source_entries = skill_package_entries(source_path)
    source_digest = skill_package_digest(source_entries)
    if target_path.exists():
        target_digest = skill_package_digest(skill_package_entries(target_path))
        if target_digest != source_digest:
            raise BootstrapError("SKILL_INSTALL_CONFLICT")
        return "EXISTING_IDENTICAL"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target_path.name}-", dir=target_path.parent)
    )
    try:
        shutil.copytree(source_path, temporary / "package", copy_function=shutil.copy2)
        installed = temporary / "package"
        if skill_package_digest(skill_package_entries(installed)) != source_digest:
            raise BootstrapError("SKILL_INSTALL_COPY_MISMATCH")
        os.rename(installed, target_path)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return "INSTALLED"


def build_skill_resolution_receipt(
    *,
    source_root: Path,
    resolved_root: Path,
    skill_manifest: Mapping[str, Any],
    verified_at: str,
    resolution_mode: str,
) -> dict[str, Any]:
    if resolution_mode not in {
        "USER_INSTALLED",
        "PLUGIN_RESOLVED",
        "EXPLICIT_PATH_INVOCATION",
    }:
        raise BootstrapError("SKILL_RESOLUTION_MODE_INVALID")
    source_digest = skill_package_digest(skill_package_entries(source_root))
    resolved_digest = skill_package_digest(skill_package_entries(resolved_root))
    entries = skill_package_entries(resolved_root)
    agents_digest = next(
        entry["file_sha256"]
        for entry in entries
        if entry["relative_posix_path"] == "agents/openai.yaml"
    )
    passed = (
        source_digest == skill_manifest["package_digest"]
        and resolved_digest == source_digest
    )
    receipt = {
        "schema_id": "skill_resolution_receipt",
        "schema_version": "1.0.0",
        "skill_id": skill_manifest["skill_id"],
        "role_id": skill_manifest["role_id"],
        "required_version": skill_manifest["skill_version"],
        "canonical_source_ref": (
            f"role-skill-package:{skill_manifest['skill_id']}:"
            f"{skill_manifest['manifest_digest']}"
        ),
        "canonical_source_digest": source_digest,
        "resolution_mode": resolution_mode,
        "resolved_location": str(Path(resolved_root).resolve()),
        "resolved_skill_digest": resolved_digest,
        "agents_metadata_digest": agents_digest,
        "execution_kind": "GENERATIVE_AGENT_ROLE",
        "allowed_caller": "APPLICATION_DECISION_SESSION",
        "callable": passed,
        "installed": resolution_mode == "USER_INSTALLED" and passed,
        "verified_at": verified_at,
        "verdict": "PASS" if passed else "SKILL_DIGEST_MISMATCH_NO_COMMIT",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(receipt, "receipt_digest")


def _kernel_spec(component_id: str) -> Mapping[str, object]:
    if (
        component_id not in REQUIRED_COMPONENT_IDS
        or component_id not in KERNEL_COMPONENT_SPECS
        or set(KERNEL_COMPONENT_SPECS) != set(REQUIRED_COMPONENT_IDS)
    ):
        raise BootstrapError("KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT")
    return KERNEL_COMPONENT_SPECS[component_id]


def _kernel_source_entries(
    project_root: Path, component_id: str
) -> tuple[dict[str, object], ...]:
    root = Path(project_root).resolve(strict=True)
    spec = _kernel_spec(component_id)
    entries: list[dict[str, object]] = []
    for relative in spec["source_files"]:
        if not isinstance(relative, str):
            raise BootstrapError("KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT")
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts:
            raise BootstrapError("KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT")
        source = root / relative
        if not source.is_file() or source.is_symlink():
            raise BootstrapError("KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT")
        payload = source.read_bytes()
        entries.append(
            {
                "relative_posix_path": posix.as_posix(),
                "byte_length": len(payload),
                "file_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return tuple(entries)


def kernel_component_source_digest(
    project_root: Path, component_id: str
) -> str:
    return canonical_digest(
        {
            "component_id": component_id,
            "entrypoint": _kernel_spec(component_id)["entrypoint"],
            "source_entries": _kernel_source_entries(
                project_root, component_id
            ),
        }
    )


def build_kernel_component_contract(
    project_root: Path, component_id: str
) -> dict[str, Any]:
    spec = _kernel_spec(component_id)
    source_digest = kernel_component_source_digest(project_root, component_id)
    contract = {
        "schema_id": "kernel_component_contract",
        "schema_version": "1.0.0",
        "contract_id": component_id,
        "contract_version": "1.0.0",
        "input_refs": [
            *spec["input_refs"],
            f"source-digest:{source_digest}",
            f"entrypoint:{spec['entrypoint']}",
        ],
        "output_refs": list(spec["output_refs"]),
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(contract, "contract_digest")


def _resolve_entrypoint(entrypoint: str) -> object:
    try:
        module_name, attribute_name = entrypoint.split(":", 1)
        module = importlib.import_module(module_name)
        value = getattr(module, attribute_name)
    except (ImportError, AttributeError, ValueError) as exc:
        raise BootstrapError(
            "KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT"
        ) from exc
    if not callable(value):
        raise BootstrapError("KERNEL_COMPONENT_HEALTH_UNKNOWN_NO_COMMIT")
    return value


def build_kernel_component_resolution_receipt(
    *,
    project_root: Path,
    component_contract: Mapping[str, Any],
    verified_at: str,
) -> dict[str, Any]:
    component_id = str(component_contract.get("contract_id", ""))
    spec = _kernel_spec(component_id)
    expected = build_kernel_component_contract(project_root, component_id)
    if dict(component_contract) != expected:
        verdict = "KERNEL_COMPONENT_DIGEST_MISMATCH_NO_COMMIT"
    else:
        _resolve_entrypoint(str(spec["entrypoint"]))
        verdict = "PASS"
    entries = _kernel_source_entries(project_root, component_id)
    source_refs = [
        f"kernel-contract:{component_id}:{expected['contract_digest']}",
        f"entrypoint:{spec['entrypoint']}",
        *(
            "source:"
            f"{entry['relative_posix_path']}:{entry['file_sha256']}"
            for entry in entries
        ),
        f"verified-at:{verified_at}",
    ]
    receipt = {
        "schema_id": "kernel_component_resolution_receipt",
        "schema_version": "1.0.0",
        "receipt_id": f"kernel-resolution:{component_id}:1.0.0",
        "source_refs": source_refs,
        "verdict": verdict,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(receipt, "receipt_digest")


def build_cluster_bootstrap_receipt(
    *,
    cluster_manifest: Mapping[str, Any],
    skill_resolution_receipts: Mapping[str, Mapping[str, Any]],
    kernel_resolution_receipts: Mapping[str, Mapping[str, Any]],
    verified_at: str,
) -> dict[str, Any]:
    required_roles = tuple(cluster_manifest.get("required_role_ids", ()))
    required_components = tuple(
        str(ref).removeprefix("kernel-component:").removesuffix(":1.0.0")
        for ref in cluster_manifest.get("required_kernel_component_refs", ())
    )
    skill_roles = {
        str(receipt.get("role_id"))
        for receipt in skill_resolution_receipts.values()
        if receipt.get("verdict") == "PASS"
        and receipt.get("callable") is True
    }
    kernel_pass = {
        component_id
        for component_id, receipt in kernel_resolution_receipts.items()
        if receipt.get("verdict") == "PASS"
    }
    passed = (
        tuple(required_roles) == ("PROPOSER", "CHALLENGER", "SELECTOR")
        and skill_roles == set(required_roles)
        and set(required_components) == set(REQUIRED_COMPONENT_IDS)
        and kernel_pass == set(REQUIRED_COMPONENT_IDS)
        and cluster_manifest.get("system_mode")
        == "E0_OFFLINE_COUNTERFACTUAL"
        and cluster_manifest.get("external_execution_authority")
        == "NONE_E0"
        and cluster_manifest.get("executable") is False
    )
    source_refs = [
        f"cluster-manifest:{cluster_manifest.get('manifest_digest', 'UNKNOWN')}",
        *(
            f"skill-resolution:{role}:{receipt.get('receipt_digest', 'UNKNOWN')}"
            for role, receipt in sorted(skill_resolution_receipts.items())
        ),
        *(
            f"kernel-resolution:{component}:{receipt.get('receipt_digest', 'UNKNOWN')}"
            for component, receipt in sorted(
                kernel_resolution_receipts.items()
            )
        ),
        f"verified-at:{verified_at}",
    ]
    receipt = {
        "schema_id": "cluster_bootstrap_receipt",
        "schema_version": "1.0.0",
        "receipt_id": "cluster-bootstrap:THEORY_AGENT_V2_E0_CLUSTER:1.0.0",
        "source_refs": source_refs,
        "verdict": (
            "PASS" if passed else "BOOTSTRAP_INCOMPLETE_NO_COMMIT"
        ),
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(receipt, "receipt_digest")


def materialize_cluster_sources(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    source_root = root / "agent-cluster" / "skill-sources"
    manifest_root = root / "agent-cluster" / "manifests"
    manifests: dict[str, dict[str, Any]] = {}
    for skill_id in sorted(SKILL_ROLES):
        manifest = build_role_skill_manifest(source_root / skill_id, skill_id)
        write_once_json(
            manifest_root / "role-skill-packages" / f"{skill_id}.v1.json",
            manifest,
        )
        manifests[skill_id] = manifest
    cluster = build_cluster_manifest(manifests)
    write_once_json(manifest_root / "cluster-manifest.v1.json", cluster)
    return {
        "skill_manifests": manifests,
        "cluster_manifest": cluster,
    }


def materialize_kernel_resolution(
    project_root: Path, *, verified_at: str
) -> dict[str, Any]:
    """Freeze all 12 project-local deterministic components and bootstrap."""

    root = Path(project_root).resolve(strict=True)
    manifest_root = root / "agent-cluster" / "manifests"
    receipt_root = root / "agent-cluster" / "install-receipts"
    contracts: dict[str, dict[str, Any]] = {}
    resolutions: dict[str, dict[str, Any]] = {}
    for component_id in REQUIRED_COMPONENT_IDS:
        contract = build_kernel_component_contract(root, component_id)
        receipt = build_kernel_component_resolution_receipt(
            project_root=root,
            component_contract=contract,
            verified_at=verified_at,
        )
        write_once_json(
            manifest_root
            / "kernel-components"
            / f"{component_id.lower()}.v1.json",
            contract,
        )
        write_once_json(
            receipt_root
            / "kernel-components"
            / f"{component_id.lower()}.resolution.v1.json",
            receipt,
        )
        contracts[component_id] = contract
        resolutions[component_id] = receipt

    cluster = load_json_strict(
        manifest_root / "cluster-manifest.v1.json"
    )
    skill_receipts: dict[str, Mapping[str, Any]] = {}
    for path in sorted((receipt_root / "user-installed").glob("*.json")):
        receipt = load_json_strict(path)
        role_id = str(receipt.get("role_id", ""))
        if role_id:
            skill_receipts[role_id] = receipt
    bootstrap_receipt = build_cluster_bootstrap_receipt(
        cluster_manifest=cluster,
        skill_resolution_receipts=skill_receipts,
        kernel_resolution_receipts=resolutions,
        verified_at=verified_at,
    )
    if bootstrap_receipt["verdict"] != "PASS":
        raise BootstrapError("BOOTSTRAP_INCOMPLETE_NO_COMMIT")
    write_once_json(
        receipt_root / "cluster-bootstrap.resolution.v1.json",
        bootstrap_receipt,
    )
    return {
        "kernel_component_contracts": contracts,
        "kernel_component_resolution_receipts": resolutions,
        "cluster_bootstrap_receipt": bootstrap_receipt,
    }
