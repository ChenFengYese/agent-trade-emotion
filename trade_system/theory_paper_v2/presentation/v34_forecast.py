"""CLI for the local, non-executable V3.4 FORECAST_ONLY harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..application.market_cycle.forecast_qualification import V340ForecastQualificationService
from ..infrastructure.market_cycle.strategic_state_repository import FileStrategicStateRepository


def _json_file(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _service(args: argparse.Namespace) -> V340ForecastQualificationService:
    return V340ForecastQualificationService(
        FileStrategicStateRepository(Path(args.root)),
        context_max_utf8_bytes=args.context_max_bytes,
    )


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _context(args: argparse.Namespace) -> int:
    value = _service(args).build_context(
        asset_id=args.asset,
        committee_slot_at=args.slot_at,
        input_cutoff_at=args.input_cutoff_at,
        reference_price=args.reference_price,
        theory_identity=args.theory_identity,
        shared_context_summary=_json_file(args.shared_context),
        asset_delta_summary=_json_file(args.asset_delta),
        portfolio_summary=_json_file(args.portfolio),
        source_refs=args.source_ref,
    )
    _print(value)
    return 0


def _seal(args: argparse.Namespace) -> int:
    record = _service(args).seal_forecast(
        asset_id=args.asset,
        context=_json_file(args.context),
        agent_text=Path(args.agent_text).read_text(encoding="utf-8"),
        forecast=_json_file(args.forecast),
        model_usage=None if args.usage is None else _json_file(args.usage),
    )
    _print(record)
    return 0


def _outcome(args: argparse.Namespace) -> int:
    record = _service(args).seal_outcome(
        asset_id=args.asset,
        committee_slot_at=args.slot_at,
        observed_through_at=args.observed_through_at,
        outcome=_json_file(args.outcome),
    )
    _print(record)
    return 0


def _latest(args: argparse.Namespace) -> int:
    value = FileStrategicStateRepository(Path(args.root)).latest_forecast(args.asset)
    _print({"status": "EMPTY"} if value is None else value)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="V3.4 scheduled FORECAST_ONLY research harness")
    parser.add_argument("--root", required=True, help="Local forecast artifact root")
    parser.add_argument("--context-max-bytes", type=int, default=64 * 1024)
    sub = parser.add_subparsers(dest="command", required=True)

    context = sub.add_parser("context", help="Build one bounded 4H committee context")
    context.add_argument("--asset", required=True)
    context.add_argument("--slot-at", required=True)
    context.add_argument("--input-cutoff-at", required=True)
    context.add_argument("--reference-price", required=True)
    context.add_argument("--theory-identity", required=True)
    context.add_argument("--shared-context", required=True)
    context.add_argument("--asset-delta", required=True)
    context.add_argument("--portfolio", required=True)
    context.add_argument("--source-ref", action="append", default=[])
    context.set_defaults(func=_context)

    seal = sub.add_parser("seal", help="Seal one Agent forecast at a fixed 4H slot")
    seal.add_argument("--asset", required=True)
    seal.add_argument("--context", required=True)
    seal.add_argument("--agent-text", required=True)
    seal.add_argument("--forecast", required=True)
    seal.add_argument("--usage", help="Optional provider-observed token usage JSON; otherwise UNKNOWN")
    seal.set_defaults(func=_seal)

    outcome = sub.add_parser("outcome", help="Seal a complete 24H forecast outcome and evaluation")
    outcome.add_argument("--asset", required=True)
    outcome.add_argument("--slot-at", required=True)
    outcome.add_argument("--observed-through-at", required=True)
    outcome.add_argument("--outcome", required=True)
    outcome.set_defaults(func=_outcome)

    latest = sub.add_parser("latest", help="Read the latest durable strategic forecast state")
    latest.add_argument("--asset", required=True)
    latest.set_defaults(func=_latest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
