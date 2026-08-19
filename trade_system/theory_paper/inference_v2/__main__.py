"""CLI presentation layer for successor-v2 shadow inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .application import replay_cycles
from .domain import HISTORICAL_MODE, LIVE_MODE, InferenceV2Error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build read-only successor-v2 missing-data inference sidecars from "
            "frozen theory-paper v1 cycles."
        )
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/theory_paper_inference_framework.v2.json"),
    )
    parser.add_argument("--from-cycle", required=True)
    parser.add_argument("--to-cycle", required=True)
    parser.add_argument(
        "--mode",
        choices=(HISTORICAL_MODE, LIVE_MODE),
        default=HISTORICAL_MODE,
    )
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = replay_cycles(
            run_dir=args.run_dir,
            output_dir=args.output_dir,
            config_path=args.config,
            first_cycle=args.from_cycle,
            last_cycle=args.to_cycle,
            mode=args.mode,
            validate_only=args.validate_only,
        )
    except InferenceV2Error as exc:
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
