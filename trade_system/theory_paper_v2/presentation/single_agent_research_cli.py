"""CLI for the local non-executable single-Strategy-Agent research loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from ..application.single_agent_research import (
    research_status,
)
from ..application.research_authority import research_authority_status
from ..application.prospective_single_agent import (
    comparator_results,
)
from ..infrastructure.legacy_v1.read_only import read_existing_evaluation
from .continuous_fixture_composition import run_continuous_fixture


LEGACY_MUTATION_DISABLED = "LEGACY_MUTATION_DISABLED_USE_CONTINUOUS_FIXTURE"
_LEGACY_MUTATION_COMMANDS = frozenset(
    {
        "prepare-seen-v1",
        "prepare-prospective",
        "recover-prospective",
        "collect-prospective-cycle",
        "interrupt-prospective",
        "open-cycle",
        "accept",
        "finalize",
    }
)


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare-seen-v1")
    prepare.add_argument("--project-root", type=Path, required=True)
    prepare.add_argument("--source-root", type=Path, required=True)
    prepare.add_argument("--runtime-root", type=Path, required=True)
    prepare.add_argument("--contract", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)

    prepare_prospective = sub.add_parser("prepare-prospective")
    prepare_prospective.add_argument("--project-root", type=Path, required=True)
    prepare_prospective.add_argument("--runtime-root", type=Path, required=True)
    prepare_prospective.add_argument("--template", type=Path, required=True)
    prepare_prospective.add_argument("--run-id", required=True)

    recover_prospective = sub.add_parser("recover-prospective")
    recover_prospective.add_argument("--project-root", type=Path, required=True)
    recover_prospective.add_argument("--runtime-root", type=Path, required=True)
    recover_prospective.add_argument(
        "--predecessor-run-root", type=Path, required=True
    )
    recover_prospective.add_argument("--template", type=Path, required=True)
    recover_prospective.add_argument("--run-id", required=True)

    collect_prospective = sub.add_parser("collect-prospective-cycle")
    collect_prospective.add_argument("--run-root", type=Path, required=True)
    collect_prospective.add_argument("--cycle-index", type=int, required=True)

    comparators = sub.add_parser("prospective-comparators")
    comparators.add_argument("--run-root", type=Path, required=True)
    comparators.add_argument("--through-cycle", type=int)

    evaluate_prospective = sub.add_parser("evaluate-prospective")
    evaluate_prospective.add_argument("--run-root", type=Path, required=True)

    interrupt_prospective = sub.add_parser("interrupt-prospective")
    interrupt_prospective.add_argument("--run-root", type=Path, required=True)
    interrupt_prospective.add_argument("--reason-code", required=True)

    open_cycle = sub.add_parser("open-cycle")
    open_cycle.add_argument("--run-root", type=Path, required=True)
    open_cycle.add_argument("--cycle-index", type=int, required=True)

    accept = sub.add_parser("accept")
    accept.add_argument("--run-root", type=Path, required=True)
    accept.add_argument("--decision", type=Path, required=True)

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--run-root", type=Path, required=True)

    evaluate = sub.add_parser("evaluate-seen-v1")
    evaluate.add_argument("--run-root", type=Path, required=True)
    evaluate.add_argument("--artifact-root", type=Path)

    status = sub.add_parser("status")
    status.add_argument("--run-root", type=Path, required=True)
    authority_status = sub.add_parser("authority-status")
    authority_status.add_argument("--project-root", type=Path, required=True)
    fixture = sub.add_parser("run-continuous-fixture")
    fixture.add_argument("--runtime-root", type=Path, required=True)
    fixture.add_argument("--run-id", required=True)
    fixture.add_argument("--through-cycle", type=int, default=4)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in _LEGACY_MUTATION_COMMANDS:
        _print(
            {
                "status": "DENIED",
                "error": LEGACY_MUTATION_DISABLED,
                "command": args.command,
                "mutation_performed": False,
            }
        )
        return 2
    handlers: dict[str, Callable[[], dict[str, Any]]] = {
        "prospective-comparators": lambda: comparator_results(
            run_root=args.run_root,
            through_cycle=args.through_cycle,
        ),
        "evaluate-prospective": lambda: read_existing_evaluation(
            run_root=args.run_root,
        ),
        "evaluate-seen-v1": lambda: read_existing_evaluation(
            run_root=args.run_root,
        ),
        "status": lambda: research_status(run_root=args.run_root),
        "authority-status": lambda: research_authority_status(
            project_root=args.project_root
        ),
        "run-continuous-fixture": lambda: run_continuous_fixture(
            runtime_root=args.runtime_root,
            run_id=args.run_id,
            through_cycle=args.through_cycle,
        ),
    }
    _print(handlers[args.command]())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
