"""Command-line entry point for the immutable first-round E0 evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from trade_system.theory_paper.common import digest_json
from trade_system.theory_paper.inference_v2.infrastructure import (
    read_json_object,
)

from ..application.round1_run import execute_frozen_round1
from ..application.round1_evaluation import build_frozen_cost_policy
from ..application.runtime import (
    OfflineRunManifestInput,
    initialize_offline_runtime,
)
from ..domain.contracts.canonical import (
    canonical_digest,
    load_json_strict,
    self_digest,
    write_once_json,
)
from ..infrastructure.legacy_v1 import legacy_tree_digest
from .report import materialize_round1_report


def _project_source_digest(project_root: Path) -> str:
    root = Path(project_root).resolve(strict=True)
    package = root / "trade_system" / "theory_paper_v2"
    entries = []
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts or path.is_symlink():
            continue
        payload = path.read_bytes()
        entries.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "byte_length": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    if not entries:
        raise ValueError("V2_SOURCE_SET_EMPTY")
    return canonical_digest(entries)


def _build_authority_snapshot(
    *,
    offline_run_id: str,
    legacy_run_id: str,
    dataset_digest: str,
    automation_status_observed: str,
) -> dict[str, object]:
    return self_digest(
        {
            "schema_id": "authority_snapshot",
            "schema_version": "1.0.0",
            "record_id": f"{offline_run_id}:authority",
            "revision": 1,
            "value_refs": [
                f"legacy-run-id:{legacy_run_id}",
                f"dataset-digest:{dataset_digest}",
                (
                    "automation-status-observed:"
                    f"{automation_status_observed}"
                ),
                "paper-action-authority:NONE",
                "live-action-authority:NONE",
                "legacy-write-authority:NONE",
            ],
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "record_digest",
    )


def _build_replay_genesis_contract(
    *,
    offline_run_id: str,
    legacy_run_id: str,
    dataset_digest: str,
) -> dict[str, object]:
    return self_digest(
        {
            "schema_id": "project_state_genesis_contract",
            "schema_version": "1.0.0",
            "contract_id": f"{offline_run_id}:replay-genesis",
            "contract_version": "1.0.0",
            "input_refs": [
                f"legacy-run-id:{legacy_run_id}",
                f"legacy-source-tree-digest:{dataset_digest}",
                "cycle-scope:0001-0024",
                "persistent-v2-strategic-state:UNKNOWN",
                "active-v2-episode:NONE_CREATED",
            ],
            "output_refs": [
                "historical-observed-arm:A",
                "counterfactual-arms:B-I:UNKNOWN_WHERE_UNDECLARED",
                "legacy-write-authority:NONE",
            ],
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "contract_digest",
    )


def build_parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Run the read-only Theory Agent V2 first-round gate."
    )
    parser.add_argument("--offline-run-id", required=True)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument(
        "--legacy-run-root",
        type=Path,
        default=project_root / ".runtime/theory-paper-v1/current",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=project_root / ".runtime/theory-paper-v2",
    )
    parser.add_argument(
        "--automation-status-observed",
        default="PAUSED_FROZEN_REQUIREMENT",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    project_root = arguments.project_root.resolve(strict=True)
    legacy_root = arguments.legacy_run_root.resolve(strict=True)
    legacy_manifest = read_json_object(legacy_root / "manifest.json")
    legacy_config = read_json_object(
        project_root / "config/theory_paper_experiment.v1.json"
    )
    bundle_index = load_json_strict(
        project_root / "agent-cluster/contracts/bundle.index.json"
    )
    canonical_contract = load_json_strict(
        project_root
        / "config/theory_agent_v2.canonical_contract_manifest.v1.json"
    )
    cluster_receipt = load_json_strict(
        project_root
        / "agent-cluster/install-receipts/"
        "cluster-bootstrap.resolution.v1.json"
    )
    if cluster_receipt.get("verdict") != "PASS":
        raise ValueError("BOOTSTRAP_INCOMPLETE_NO_COMMIT")

    dataset_digest = legacy_tree_digest(legacy_root)
    authority = _build_authority_snapshot(
        offline_run_id=arguments.offline_run_id,
        legacy_run_id=str(legacy_manifest["run_id"]),
        dataset_digest=dataset_digest,
        automation_status_observed=arguments.automation_status_observed,
    )
    genesis = _build_replay_genesis_contract(
        offline_run_id=arguments.offline_run_id,
        legacy_run_id=str(legacy_manifest["run_id"]),
        dataset_digest=dataset_digest,
    )
    theory_digest = hashlib.sha256(
        (
            project_root
            / "archive/authority/THEORY_AGENT_V2_IMPLEMENTATION_CONTRACT_v1_0.md"
        ).read_bytes()
    ).hexdigest()
    manifest_path = initialize_offline_runtime(
        arguments.runtime_root,
        OfflineRunManifestInput(
            offline_run_id=arguments.offline_run_id,
            theory_contract_digest=theory_digest,
            code_digest=_project_source_digest(project_root),
            schema_bundle_digest=str(
                bundle_index["bundle_index_digest"]
            ),
            policy_digest=str(canonical_contract["manifest_digest"]),
            dataset_digest=dataset_digest,
            automation_status_observed=(
                arguments.automation_status_observed
            ),
            authority_snapshot_digest=str(authority["record_digest"]),
            cluster_bootstrap_receipt_digest=str(
                cluster_receipt["receipt_digest"]
            ),
            project_state_genesis_contract_digest=str(
                genesis["contract_digest"]
            ),
        ),
    )
    run_root = manifest_path.parent
    write_once_json(run_root / "bootstrap/authority-snapshot.json", authority)
    write_once_json(
        run_root / "bootstrap/replay-genesis-contract.json",
        genesis,
    )

    risk_policy = legacy_config.get("risk_policy")
    if not isinstance(risk_policy, dict):
        raise ValueError("COST_POLICY_MISSING")
    cost_policy = build_frozen_cost_policy(
        maker_fee_rate=risk_policy["default_maker_fee_rate"],
        taker_fee_rate=risk_policy["default_taker_fee_rate"],
        market_slippage_bps=(
            risk_policy["default_market_slippage_bps"]
        ),
        stop_slippage_bps=risk_policy["default_stop_slippage_bps"],
    )
    result = execute_frozen_round1(
        run_root=legacy_root,
        expected_run_id=str(legacy_manifest["run_id"]),
        expected_manifest_digest=digest_json(legacy_manifest),
        cost_policy=cost_policy,
    )
    report = materialize_round1_report(
        runtime_root=arguments.runtime_root,
        offline_run_id=arguments.offline_run_id,
        result=result,
    )
    print(
        json.dumps(
            {
                "offline_run_id": arguments.offline_run_id,
                "terminal_status": result.evaluation.terminal_status,
                "hard_functional_gate_status": (
                    result.evaluation.hard_functional_gate_status
                ),
                "behavior_economic_gate_status": (
                    result.evaluation.behavior_economic_gate_status
                ),
                "round2_authorized": result.round2_authorized,
                "scenario_pass_count": result.scenario_report.pass_count,
                "run_result_digest": result.run_result_digest,
                "artifact_index_digest": report.artifact_index_digest,
                "report_path": str(report.markdown_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
