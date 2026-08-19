"""Composition root for the current-Codex four-cycle BTC market pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..application.native_market_pilot import (
    advance_native_market_pilot,
    claim_native_market_request,
    initialize_native_market_pilot,
    native_market_prior_snapshot,
    native_market_pilot_status,
    submit_native_market_delivery,
)
from ..domain.contracts.canonical import load_json_strict, self_digest
from ..infrastructure.continuous_fixture import LocalRunLease
from ..infrastructure.fresh_market.okx_public import (
    OkxCurlPublicHttpTransport,
    OkxPublicFreshCollector,
)
from ..infrastructure.native_market_collector import OkxNativeMarketCollector
from ..infrastructure.native_market_pilot_store import LocalNativeMarketPilotStore


_IMPLEMENTATION_PATHS = (
    "trade_system/theory_paper_v2/domain/contracts/canonical.py",
    "trade_system/theory_paper_v2/domain/native_agent_transport.py",
    "trade_system/theory_paper_v2/domain/native_market_cycle.py",
    "trade_system/theory_paper_v2/domain/dynamic_research.py",
    "trade_system/theory_paper_v2/domain/governance/research_authority.py",
    "trade_system/theory_paper_v2/application/native_market_pilot.py",
    "trade_system/theory_paper_v2/application/ports.py",
    "trade_system/theory_paper_v2/infrastructure/native_agent_mailbox.py",
    "trade_system/theory_paper_v2/infrastructure/native_market_collector.py",
    "trade_system/theory_paper_v2/infrastructure/native_market_pilot_store.py",
    "trade_system/theory_paper_v2/infrastructure/fresh_market/okx_public.py",
    "trade_system/theory_paper_v2/presentation/native_market_pilot_cli.py",
    "archive/authority/CORE_TRADING_THEORY_v2_1.md",
    "theory/history/MARKET_SENTIMENT_ORDINAL_STANDARD_v1_2.md",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _print(value: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _bindings(project_root: Path) -> dict[str, dict[str, str]]:
    root = project_root.resolve()
    result: dict[str, dict[str, str]] = {}
    for relative_ref in _IMPLEMENTATION_PATHS:
        path = (root / relative_ref).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("NATIVE_MARKET_IMPLEMENTATION_REF_INVALID") from exc
        if not path.is_file():
            raise ValueError(f"NATIVE_MARKET_IMPLEMENTATION_MISSING:{relative_ref}")
        result[relative_ref] = {
            "relative_ref": relative_ref,
            "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return result


def _run_root(runtime_root: Path, run_id: str) -> Path:
    root = runtime_root.resolve()
    result = (root / run_id).resolve()
    try:
        result.relative_to(root)
    except ValueError as exc:
        raise ValueError("NATIVE_MARKET_RUN_ROOT_INVALID") from exc
    return result


def _payload(run_root: Path, payload_path: Path) -> Mapping[str, Any]:
    path = payload_path.resolve()
    authoring = (run_root / "authoring").resolve()
    try:
        path.relative_to(authoring)
    except ValueError as exc:
        raise ValueError("NATIVE_MARKET_PAYLOAD_OUTSIDE_AUTHORING_ROOT") from exc
    return load_json_strict(path)


def _verify_implementation(
    *, project_root: Path, store: LocalNativeMarketPilotStore
) -> None:
    manifest = store.read_document(
        relative_ref="manifest.json",
        digest_field="native_market_pilot_manifest_digest",
    )
    if manifest.get("implementation_bindings") != _bindings(project_root):
        raise ValueError("NATIVE_MARKET_IMPLEMENTATION_BINDING_DRIFT")


def _verify_current_authority(
    *, project_root: Path, store: LocalNativeMarketPilotStore
) -> None:
    current = load_json_strict(
        project_root.resolve()
        / "config/theory_paper_v2.current_research_authority.v1.json"
    )
    frozen = store.read_document(
        relative_ref="frozen/current-research-authority.json",
        digest_field="native_market_frozen_authority_digest",
    )
    if frozen.get("authority") != current:
        raise ValueError("NATIVE_MARKET_CURRENT_AUTHORITY_REVOKED_OR_DRIFTED")


def _phase_b(run_root: Path) -> tuple[Mapping[str, Any], Mapping[str, str]]:
    path = run_root.resolve() / "completion" / "receipt.json"
    receipt = load_json_strict(path)
    return receipt, {
        "relative_ref": path.name,
        "semantic_digest": str(
            receipt["native_transport_completion_receipt_digest"]
        ),
        "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _monitor_receipt(
    *, store: LocalNativeMarketPilotStore, run_id: str, now: str
) -> Mapping[str, Any]:
    status = native_market_pilot_status(store=store, run_id=run_id, now=now)
    receipt = self_digest(
        {
            "schema_id": "native_market_monitor_receipt",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "observed_at": now,
            "observed_checkpoint_digest": status["checkpoint_digest"],
            "observed_status": status["status"],
            "observed_cycle_index": status["cycle_index"],
            "observed_active_stage": status["active_stage"],
            "observed_next_action": status["next_action"],
            "actual_state_verified": True,
            "lease_held_during_observation": True,
            "kill_switch_for_external_execution": True,
            "order_sent": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_market_monitor_receipt_digest",
    )
    safe_time = now.replace(":", "").replace("-", "").replace(".", "")
    store.write_document(
        relative_ref=f"monitor/receipts/{safe_time}.json",
        document=receipt,
        digest_field="native_market_monitor_receipt_digest",
    )
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    initialize = sub.add_parser("init-market")
    initialize.add_argument("--project-root", type=Path, required=True)
    initialize.add_argument("--runtime-root", type=Path, required=True)
    initialize.add_argument("--run-id", required=True)
    initialize.add_argument("--config", type=Path, required=True)
    initialize.add_argument("--authority", type=Path, required=True)
    initialize.add_argument("--authorization-receipt", type=Path, required=True)
    initialize.add_argument("--phase-b-run-root", type=Path, required=True)

    for command in ("status", "monitor", "advance"):
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
    now = _now()
    if args.command == "init-market":
        run_root = _run_root(args.runtime_root, args.run_id)
        if run_root.exists() and not (run_root / "manifest.json").is_file():
            entries = {path.name for path in run_root.iterdir()}
            if entries - {"controller"}:
                raise ValueError("NATIVE_MARKET_EXISTING_ROOT_HAS_NO_MANIFEST")
        config_path = args.config.resolve()
        phase_b, phase_b_binding = _phase_b(args.phase_b_run_root)
        with LocalRunLease(run_root, run_id=args.run_id):
            result = initialize_native_market_pilot(
                store=LocalNativeMarketPilotStore(run_root),
                run_id=args.run_id,
                created_at=now,
                config=load_json_strict(config_path),
                config_physical_sha256=hashlib.sha256(
                    config_path.read_bytes()
                ).hexdigest(),
                authority=load_json_strict(args.authority.resolve()),
                authorization_receipt=load_json_strict(
                    args.authorization_receipt.resolve()
                ),
                phase_b_completion=phase_b,
                phase_b_completion_binding=phase_b_binding,
                implementation_bindings=_bindings(args.project_root),
            )
        _print(result)
        return 0

    run_root = args.run_root.resolve()
    run_id = run_root.name
    store = LocalNativeMarketPilotStore(run_root)
    _verify_implementation(project_root=args.project_root, store=store)
    _verify_current_authority(project_root=args.project_root, store=store)
    if args.command == "status":
        _print(native_market_pilot_status(store=store, run_id=run_id, now=now))
        return 0
    if args.command == "monitor":
        with LocalRunLease(run_root, run_id=run_id):
            receipt = _monitor_receipt(store=store, run_id=run_id, now=now)
        _print(receipt)
        return 0
    if args.command == "advance":
        status = native_market_pilot_status(store=store, run_id=run_id, now=now)
        collection = None
        if status["next_action"] == "COLLECT_ONE_DUE_CYCLE":
            collection = OkxNativeMarketCollector(
                collector=OkxPublicFreshCollector(
                    transport=OkxCurlPublicHttpTransport(), timeout=20
                )
            ).collect(
                run_id=run_id,
                cycle_index=int(status["cycle_index"]),
                prior_market_snapshot=native_market_prior_snapshot(
                    store=store,
                    run_id=run_id,
                    cycle_index=int(status["cycle_index"]),
                ),
            )
        with LocalRunLease(run_root, run_id=run_id):
            result = advance_native_market_pilot(
                store=store,
                run_id=run_id,
                now=now,
                snapshot=(collection.snapshot if collection else None),
                raw_body_by_request_id=(
                    collection.raw_body_by_request_id if collection else None
                ),
            )
        _print(result)
        return 0
    if args.command == "claim":
        result = claim_native_market_request(
            store=store,
            run_id=run_id,
            stage=args.stage,
            claimed_at=now,
        )
        _print(result)
        return 0
    if args.command == "submit":
        result = submit_native_market_delivery(
            store=store,
            run_id=run_id,
            stage=args.stage,
            payload=_payload(run_root, args.payload),
            delivered_at=now,
        )
        _print(result)
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
