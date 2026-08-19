"""CLI composition root for the current-Codex native transport experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..application.native_agent_transport import (
    advance_native_transport,
    claim_native_request,
    initialize_native_transport_run,
    native_transport_status,
    submit_native_delivery,
)
from ..domain.contracts.canonical import load_json_strict
from ..infrastructure.continuous_fixture import LocalRunLease
from ..infrastructure.native_agent_mailbox import LocalNativeAgentTransportStore


_IMPLEMENTATION_PATHS = (
    "trade_system/theory_paper_v2/domain/contracts/canonical.py",
    "trade_system/theory_paper_v2/domain/native_agent_transport.py",
    "trade_system/theory_paper_v2/domain/native_market_cycle.py",
    "trade_system/theory_paper_v2/domain/dynamic_research.py",
    "trade_system/theory_paper_v2/application/native_agent_transport.py",
    "trade_system/theory_paper_v2/infrastructure/native_agent_mailbox.py",
    "trade_system/theory_paper_v2/presentation/native_cycle_experiment_cli.py",
    "trade_system/theory_paper_v2/domain/window_reliability.py",
    "archive/authority/CORE_TRADING_THEORY_v2_1.md",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _print(value: Mapping[str, Any]) -> None:
    print(json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _implementation_bindings(project_root: Path) -> dict[str, dict[str, str]]:
    root = Path(project_root).resolve()
    bindings: dict[str, dict[str, str]] = {}
    for relative_ref in _IMPLEMENTATION_PATHS:
        path = (root / relative_ref).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("NATIVE_IMPLEMENTATION_REF_INVALID") from exc
        if not path.is_file():
            raise ValueError(f"NATIVE_IMPLEMENTATION_FILE_MISSING:{relative_ref}")
        bindings[relative_ref] = {
            "relative_ref": relative_ref,
            "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return bindings


def _run_root(runtime_root: Path, run_id: str) -> Path:
    root = Path(runtime_root).resolve()
    run_root = (root / run_id).resolve()
    try:
        run_root.relative_to(root)
    except ValueError as exc:
        raise ValueError("NATIVE_RUN_ROOT_INVALID") from exc
    return run_root


def _payload_in_run(run_root: Path, payload_path: Path) -> Mapping[str, Any]:
    path = Path(payload_path).resolve()
    authoring_root = (run_root / "authoring").resolve()
    try:
        path.relative_to(authoring_root)
    except ValueError as exc:
        raise ValueError("NATIVE_PAYLOAD_OUTSIDE_AUTHORING_ROOT") from exc
    return load_json_strict(path)


def _verify_implementation_bindings(
    *,
    project_root: Path,
    store: LocalNativeAgentTransportStore,
) -> None:
    manifest = store.read_document(
        relative_ref="manifest.json",
        digest_field="native_transport_manifest_digest",
    )
    if manifest.get("implementation_bindings") != _implementation_bindings(
        project_root
    ):
        raise ValueError("NATIVE_IMPLEMENTATION_BINDING_DRIFT")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    initialize = sub.add_parser("init-transport")
    initialize.add_argument("--project-root", type=Path, required=True)
    initialize.add_argument("--runtime-root", type=Path, required=True)
    initialize.add_argument("--run-id", required=True)
    initialize.add_argument("--contract", type=Path, required=True)

    for command in ("status", "advance"):
        item = sub.add_parser(command)
        item.add_argument("--project-root", type=Path, required=True)
        item.add_argument("--run-root", type=Path, required=True)

    claim = sub.add_parser("claim")
    claim.add_argument("--project-root", type=Path, required=True)
    claim.add_argument("--run-root", type=Path, required=True)
    claim.add_argument("--stage", choices=("PROPOSAL", "DELIBERATION"), required=True)

    submit = sub.add_parser("submit")
    submit.add_argument("--project-root", type=Path, required=True)
    submit.add_argument("--run-root", type=Path, required=True)
    submit.add_argument("--stage", choices=("PROPOSAL", "DELIBERATION"), required=True)
    submit.add_argument("--payload", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = _utc_now()
    if args.command == "init-transport":
        run_root = _run_root(args.runtime_root, args.run_id)
        if run_root.exists() and not (run_root / "manifest.json").is_file():
            entries = {path.name for path in run_root.iterdir()}
            if entries - {"controller"}:
                raise ValueError("NATIVE_EXISTING_ROOT_HAS_NO_MANIFEST")
        with LocalRunLease(run_root, run_id=args.run_id):
            result = initialize_native_transport_run(
                store=LocalNativeAgentTransportStore(run_root),
                run_id=args.run_id,
                created_at=now,
                contract=load_json_strict(args.contract.resolve()),
                implementation_bindings=_implementation_bindings(args.project_root),
            )
        _print(result)
        return 0

    run_root = Path(args.run_root).resolve()
    run_id = run_root.name
    store = LocalNativeAgentTransportStore(run_root)
    _verify_implementation_bindings(
        project_root=args.project_root,
        store=store,
    )
    if args.command == "status":
        _print(native_transport_status(store=store, run_id=run_id))
        return 0
    if args.command == "advance":
        with LocalRunLease(run_root, run_id=run_id):
            result = advance_native_transport(store=store, run_id=run_id, now=now)
        _print(result)
        return 0
    if args.command == "claim":
        result = claim_native_request(
            store=store,
            run_id=run_id,
            stage=args.stage,
            claimed_at=now,
        )
        _print(result)
        return 0
    if args.command == "submit":
        result = submit_native_delivery(
            store=store,
            run_id=run_id,
            stage=args.stage,
            payload=_payload_in_run(run_root, args.payload),
            delivered_at=now,
        )
        _print(result)
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
