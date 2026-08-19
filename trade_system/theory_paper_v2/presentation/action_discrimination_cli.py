"""Minimal CLI for prepare, status, packet, record and evaluate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from ..application.action_discrimination_experiment import (
    evaluate_completed_action_experiment,
    parse_role_output,
    parse_single_bundle,
    role_packet,
)
from ..domain.contracts.canonical import canonical_bytes, load_json_strict
from ..infrastructure.action_discrimination_store import (
    EXPECTED_ROLE_KEYS,
    prepare_action_experiment,
    record_action_case,
    verify_action_experiment,
)


def _emit(value: Any) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="theory-action-e0a")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--runtime-root", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--source-run-root", type=Path, required=True)
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--design", type=Path, required=True)
    prepare.add_argument("--frozen-at", required=True)
    status = commands.add_parser("status")
    status.add_argument("--run-root", type=Path, required=True)
    packet = commands.add_parser("packet")
    packet.add_argument("--run-root", type=Path, required=True)
    packet.add_argument("--sample", type=int, required=True)
    packet.add_argument(
        "--role",
        choices=(
            "single-strong-bundle",
            "cluster-proposal",
            "cluster-challenge",
            "cluster-selection",
        ),
        required=True,
    )
    packet.add_argument("--proposal", type=Path)
    packet.add_argument("--challenge", type=Path)
    record = commands.add_parser("record")
    record.add_argument("--run-root", type=Path, required=True)
    record.add_argument("--sample", type=int, required=True)
    record.add_argument("--output-dir", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--run-root", type=Path, required=True)
    evaluate.add_argument("--source-run-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        root = prepare_action_experiment(
            runtime_root=args.runtime_root,
            run_id=args.run_id,
            source_run_root=args.source_run_root,
            config_path=args.config,
            design_path=args.design,
            frozen_at=args.frozen_at,
        )
        _emit({"run_root": str(root), **verify_action_experiment(root)})
    elif args.command == "status":
        _emit(verify_action_experiment(args.run_root))
    elif args.command == "packet":
        proposal = load_json_strict(args.proposal) if args.proposal else None
        challenge = load_json_strict(args.challenge) if args.challenge else None
        _emit(
            role_packet(
                run_root=args.run_root,
                sample_index=args.sample,
                role=args.role,
                proposal=proposal,
                challenge=challenge,
            )
        )
    elif args.command == "record":
        raw: dict[str, dict[str, Any]] = {}
        single_path = args.output_dir / "single-strong-bundle.json"
        single = parse_single_bundle(single_path.read_bytes())
        raw.update(single)
        for key in (
            "cluster-proposal",
            "cluster-challenge",
            "cluster-selection",
        ):
            raw[key] = parse_role_output(
                (args.output_dir / f"{key}.json").read_bytes(),
                role_key=key,
            )
        ordered = {key: raw[key] for key in EXPECTED_ROLE_KEYS}
        receipts_path = args.output_dir / "invocation-receipts.json"
        receipts = (
            load_json_strict(receipts_path) if receipts_path.exists() else None
        )
        event = record_action_case(
            run_root=args.run_root,
            sample_index=args.sample,
            semantic_outputs=ordered,
            invocation_receipts=receipts,
        )
        _emit(event)
    elif args.command == "evaluate":
        _emit(
            evaluate_completed_action_experiment(
                run_root=args.run_root,
                source_run_root=args.source_run_root,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
