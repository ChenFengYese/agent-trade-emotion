"""Explicit immutable V2 run bootstrap; no ambient `current` authority."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..domain.contracts.canonical import (
    self_digest,
    write_once_json,
)


_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class RuntimeBootstrapError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OfflineRunManifestInput:
    offline_run_id: str
    theory_contract_digest: str
    code_digest: str
    schema_bundle_digest: str
    policy_digest: str
    dataset_digest: str
    automation_status_observed: str
    authority_snapshot_digest: str
    cluster_bootstrap_receipt_digest: str
    project_state_genesis_contract_digest: str


def build_offline_run_manifest(
    inputs: OfflineRunManifestInput,
) -> dict[str, object]:
    if (
        _RUN_ID.fullmatch(inputs.offline_run_id) is None
        or inputs.offline_run_id in {"current", "latest"}
    ):
        raise RuntimeBootstrapError("EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED")
    digest_fields = (
        inputs.theory_contract_digest,
        inputs.code_digest,
        inputs.schema_bundle_digest,
        inputs.policy_digest,
        inputs.dataset_digest,
        inputs.authority_snapshot_digest,
        inputs.cluster_bootstrap_receipt_digest,
        inputs.project_state_genesis_contract_digest,
    )
    if any(_HEX64.fullmatch(value) is None for value in digest_fields):
        raise RuntimeBootstrapError("RUN_MANIFEST_DIGEST_INVALID")
    manifest = {
        "schema_id": "project_bootstrap_manifest",
        "schema_version": "1.0.0",
        "manifest_id": inputs.offline_run_id,
        "manifest_version": "1.0.0",
        "entry_refs": [
            "mode:OFFLINE_REPLAY",
            "paper_action_authority:NONE",
            "live_action_authority:NONE",
            "legacy_write_authority:NONE",
            f"theory_contract_digest:{inputs.theory_contract_digest}",
            f"code_digest:{inputs.code_digest}",
            f"schema_bundle_digest:{inputs.schema_bundle_digest}",
            f"policy_digest:{inputs.policy_digest}",
            f"dataset_digest:{inputs.dataset_digest}",
            (
                "automation_status_observed:"
                f"{inputs.automation_status_observed}"
            ),
            (
                "authority_snapshot_digest:"
                f"{inputs.authority_snapshot_digest}"
            ),
            (
                "cluster_bootstrap_receipt_digest:"
                f"{inputs.cluster_bootstrap_receipt_digest}"
            ),
            (
                "project_state_genesis_contract_digest:"
                f"{inputs.project_state_genesis_contract_digest}"
            ),
        ],
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(manifest, "manifest_digest")


def initialize_offline_runtime(
    runtime_root: Path,
    inputs: OfflineRunManifestInput,
) -> Path:
    manifest = build_offline_run_manifest(inputs)
    root = Path(runtime_root).resolve() / inputs.offline_run_id
    manifest_path = root / "manifest.json"
    write_once_json(manifest_path, manifest)
    return manifest_path
