#!/usr/bin/env python3.12
"""Prepare, preflight and resume the frozen TA2 formal-E0 batch."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trade_system.theory_paper_v2.application.formal_e0_batch import (
    FormalE0BatchError,
    FormalE0BatchRunner,
    parse_index_expression,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
)
from trade_system.theory_paper_v2.infrastructure.formal_e0_batch_store import (
    FormalE0BatchStoreError,
    load_prepared_formal_e0_run,
    prepare_formal_e0_run,
)
from trade_system.theory_paper_v2.infrastructure.generative_topology.codex_exec import (
    CodexExecGenerativeTransport,
)


def _print(value: object) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Frozen-input, no-paper/no-live formal E0 topology experiment."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--runtime-root", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--formal-contract", type=Path, required=True)
    prepare.add_argument("--dataset-bundle", type=Path, required=True)
    prepare.add_argument(
        "--frozen-at",
        default=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )

    for name in (
        "preflight",
        "run-selection",
        "run-qualification",
        "run-formal",
        "run-all",
    ):
        item = commands.add_parser(name)
        item.add_argument("--run-root", type=Path, required=True)
        item.add_argument("--codex-binary")
        if name.startswith("run-"):
            item.add_argument("--indices")
            item.add_argument("--concurrency", type=int, default=1)

    status = commands.add_parser("status")
    status.add_argument("--run-root", type=Path, required=True)
    return parser


def _runner(arguments: argparse.Namespace) -> FormalE0BatchRunner:
    return FormalE0BatchRunner(
        prepared_run_root=arguments.run_root,
        model_port=CodexExecGenerativeTransport(
            codex_binary=getattr(arguments, "codex_binary", None)
        ),
    )


def _status(run_root: Path) -> dict[str, object]:
    prepared = load_prepared_formal_e0_run(run_root)
    observations = {}
    decisions = {}
    for name in ("selection", "qualification", "formal"):
        observations[name] = len(
            tuple(
                (
                    prepared.run_root / "observations" / name
                ).glob("*.json")
            )
        )
        decisions[name] = len(
            tuple(
                (prepared.run_root / "decisions" / name).glob("*.json")
            )
        )
    gates = {}
    for name in ("topology-selection", "policy-qualification"):
        path = prepared.run_root / "gates" / f"{name}.json"
        gates[name] = (
            load_json_strict(path).get("status")
            if path.exists()
            else "NOT_MATERIALIZED"
        )
    preflight_path = (
        prepared.run_root / "preflight" / "transport-admission.json"
    )
    return {
        "run_id": prepared.run_id,
        "run_root": str(prepared.run_root),
        "run_bindings_digest": prepared.run_bindings_digest,
        "policy_digests": {
            "scoring": prepared.scoring_policy_digest,
            "cost": prepared.cost_policy_digest,
            "initial_account": prepared.initial_account_digest,
            "termination": prepared.termination_policy_digest,
        },
        "transport_preflight": (
            load_json_strict(preflight_path).get("status")
            if preflight_path.exists()
            else "NOT_RUN"
        ),
        "observation_counts": observations,
        "decision_receipt_counts": decisions,
        "gates": gates,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "prepare":
            prepared = prepare_formal_e0_run(
                runtime_root=arguments.runtime_root,
                run_id=arguments.run_id,
                formal_contract_path=arguments.formal_contract,
                dataset_bundle_root=arguments.dataset_bundle,
                frozen_at=arguments.frozen_at,
            )
            _print(
                {
                    "status": "PREPARED",
                    "run_id": prepared.run_id,
                    "run_root": str(prepared.run_root),
                    "run_bindings_digest": (
                        prepared.run_bindings_digest
                    ),
                    "dataset_manifest_digest": (
                        prepared.dataset_manifest_digest
                    ),
                    "scoring_policy_digest": (
                        prepared.scoring_policy_digest
                    ),
                    "cost_policy_digest": (
                        prepared.cost_policy_digest
                    ),
                    "initial_account_digest": (
                        prepared.initial_account_digest
                    ),
                    "termination_policy_digest": (
                        prepared.termination_policy_digest
                    ),
                    "real_model_calls_started": False,
                    "external_execution_authority": "NONE_E0",
                    "executable": False,
                }
            )
            return 0
        if arguments.command == "status":
            _print(_status(arguments.run_root))
            return 0
        runner = _runner(arguments)
        if arguments.command == "preflight":
            receipt = runner.preflight()
            _print(receipt)
            return 0 if receipt["status"] == "PASS" else 2
        if arguments.command == "run-selection":
            indices = parse_index_expression(
                arguments.indices, cohort="TOPOLOGY_SELECTION"
            )
            rows = runner.run_selection(
                indices=indices, concurrency=arguments.concurrency
            )
        elif arguments.command == "run-qualification":
            indices = parse_index_expression(
                arguments.indices, cohort="POLICY_QUALIFICATION"
            )
            rows = runner.run_policy_qualification(
                indices=indices, concurrency=arguments.concurrency
            )
        elif arguments.command == "run-formal":
            indices = parse_index_expression(
                arguments.indices, cohort="FORMAL_EXPERIMENT"
            )
            rows = runner.run_formal(
                indices=indices, concurrency=arguments.concurrency
            )
        else:
            runner.run_selection(concurrency=arguments.concurrency)
            runner.run_policy_qualification(concurrency=1)
            rows = runner.run_formal(concurrency=1)
        _print(
            {
                "status": "COMPLETED_REQUESTED_BATCH",
                "receipt_count": len(rows),
                "status_snapshot": _status(arguments.run_root),
                "external_execution_authority": "NONE_E0",
                "executable": False,
            }
        )
        return 0
    except (
        FormalE0BatchError,
        FormalE0BatchStoreError,
        ValueError,
    ) as exc:
        _print(
            {
                "status": "NO_GO",
                "error_code": str(exc),
                "model_call_start_status": (
                    "NONE_IF_FAILURE_IS_TRANSPORT_PREFLIGHT_OTHERWISE_"
                    "INSPECT_WRITE_ONCE_SESSION_RECEIPTS"
                ),
                "external_execution_authority": "NONE_E0",
                "executable": False,
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
