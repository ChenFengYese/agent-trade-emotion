"""Command-line adapter for already-collected formal E0 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from ..application.formal_experiment import (
    FormalExperimentError,
    execute_formal_experiment,
)
from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
)
from ..infrastructure.formal_experiment_store import (
    FormalExperimentStoreError,
    load_dataset_manifest_ref,
    load_formal_experiment_contract,
    load_paired_observation_receipts,
    materialize_formal_experiment,
)
from .formal_report import build_formal_experiment_markdown_zh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Consume frozen formal receipts, evaluate twice, and materialize "
            "one write-once E0 report. No data collection or model call."
        )
    )
    parser.add_argument("--offline-run-id", required=True)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument(
        "--formal-contract",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--dataset-manifest-ref",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--paired-observations-dir",
        required=True,
        type=Path,
    )
    parser.add_argument("--scoring-policy-digest", required=True)
    parser.add_argument("--cost-policy-digest", required=True)
    parser.add_argument("--initial-account-digest", required=True)
    parser.add_argument("--termination-policy-digest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        contract = load_formal_experiment_contract(
            args.formal_contract
        )
        dataset = load_dataset_manifest_ref(
            args.dataset_manifest_ref
        )
        receipts = load_paired_observation_receipts(
            args.paired_observations_dir
        )
        result = execute_formal_experiment(
            offline_run_id=args.offline_run_id,
            contract=contract,
            dataset_manifest_ref=dataset,
            receipts=receipts,
            scoring_policy_digest=args.scoring_policy_digest,
            cost_policy_digest=args.cost_policy_digest,
            initial_account_digest=args.initial_account_digest,
            termination_policy_digest=args.termination_policy_digest,
        )
        materialized = materialize_formal_experiment(
            runtime_root=args.runtime_root,
            result=result,
            receipts=receipts,
            report_markdown=build_formal_experiment_markdown_zh(result),
        )
    except (
        CanonicalContractError,
        FormalExperimentError,
        FormalExperimentStoreError,
    ) as exc:
        print(f"FORMAL_E0_BLOCKED:{exc}", file=sys.stderr)
        return 2
    summary = {
        "offline_run_id": result.offline_run_id,
        "terminal_status": result.terminal_status,
        "selected_topology_id": (
            result.topology_evaluation.selected_topology_id
        ),
        "round2_precondition_status": (
            result.round2_precondition_status
        ),
        "round2_instance_created": False,
        "result_digest": result.result_digest,
        "artifact_index_digest": (
            materialized.artifact_index_digest
        ),
        "run_root": str(materialized.run_root),
        "system_mode": result.system_mode,
        "external_execution_authority": (
            result.external_execution_authority
        ),
        "executable": False,
    }
    sys.stdout.buffer.write(canonical_bytes(summary) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
