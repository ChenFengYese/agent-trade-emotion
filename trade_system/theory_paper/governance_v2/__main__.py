"""CLI presentation layer for successor-v2 governance shadow audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .application import audit_cycles
from .domain import GovernanceV2Error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit immutable theory-paper v1 cycles for multi-timescale "
            "decision-governance gaps without changing v1."
        )
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/theory_paper_decision_governance.v2.json"),
    )
    parser.add_argument("--from-cycle", required=True)
    parser.add_argument("--to-cycle", required=True)
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = audit_cycles(
            run_dir=args.run_dir,
            output_dir=args.output_dir,
            config_path=args.config,
            first_cycle=args.from_cycle,
            last_cycle=args.to_cycle,
            validate_only=args.validate_only,
        )
    except GovernanceV2Error as exc:
        print(
            json.dumps(
                {"status": "REJECTED", "reason_code": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
