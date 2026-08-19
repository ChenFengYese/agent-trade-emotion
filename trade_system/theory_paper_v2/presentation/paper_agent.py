"""Thin replay-only CLI for one persistent-Goal V3.3.2 paper action."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    loads_json_strict,
)
from ..domain.market_cycle.attention import AttentionRequest
from ..domain.market_cycle.theory import V332_THEORY_IDENTITY
from ..infrastructure.market_cycle.paper_runtime import (
    V332AgentPaperActionPort,
    V332HypePaperRuntime,
)
from ..infrastructure.market_cycle.goal_identity import (
    CodexGoalIdentityError,
    current_codex_goal_identity,
)
from ..infrastructure.market_cycle.runtime import build_market_cycle_runtime


_DEFAULT_V332_THEORY_PACKAGE = (
    Path(__file__).resolve().parents[3] / "theory" / "versions" / "v3.3.2"
)


def _write(value: Mapping[str, Any]) -> None:
    """Emit one canonical machine-readable result."""

    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="v332-paper-agent",
        allow_abbrev=False,
        description=(
            "Submit one Agent-owned attention checkpoint or paper action "
            "through the frozen V3.3.2 replay-only runtime."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        required=True,
        help="exact initialized V3.3.2 run root",
    )
    parser.add_argument(
        "--theory-package",
        type=Path,
        default=_DEFAULT_V332_THEORY_PACKAGE,
        help="exact frozen V3.3.2 theory package",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "setup",
        allow_abbrev=False,
        help="open the policy-frozen account for the current Codex Goal",
    )
    prepare = commands.add_parser(
        "prepare",
        allow_abbrev=False,
        help="issue the Goal-bound intent request for one decision cycle",
    )
    prepare.add_argument("decision_cycle_id")
    process = commands.add_parser(
        "process",
        allow_abbrev=False,
        help=(
            "apply one admitted market cycle and its strictly bracketed "
            "funding facts to the local-paper ledger"
        ),
    )
    process.add_argument("cycle_id")
    checkpoint = commands.add_parser(
        "checkpoint",
        allow_abbrev=False,
        help="seal one exact Agent-authored AttentionRequest fact",
    )
    checkpoint.add_argument("attention_request_path", type=Path)
    commit = commands.add_parser(
        "commit",
        allow_abbrev=False,
        help="commit the sealed paper-action outputs for one decision cycle",
    )
    commit.add_argument("decision_cycle_id")
    return parser


def _paper_runtime(
    *, runtime_root: Path, theory_package: Path
) -> V332HypePaperRuntime:
    """Compose the policy-bound local-paper runtime without external access."""

    runtime = build_market_cycle_runtime(
        runtime_root=runtime_root,
        theory_package=theory_package,
        expected_theory_identity=V332_THEORY_IDENTITY,
        allow_public_collection=False,
    )
    policy = runtime.experiment_policy
    paper_account = None if policy is None else policy.paper_account
    if not isinstance(paper_account, Mapping):
        raise ValueError("V332_PAPER_AGENT_POLICY_ACCOUNT_REQUIRED")
    setup_cycle_id = paper_account.get("setup_cycle_id")
    if not isinstance(setup_cycle_id, str) or not setup_cycle_id:
        raise ValueError("V332_PAPER_AGENT_SETUP_CYCLE_REQUIRED")
    return V332HypePaperRuntime(
        runtime, setup_cycle_id=setup_cycle_id
    )


def _action_port(
    *, runtime_root: Path, theory_package: Path
) -> V332AgentPaperActionPort:
    """Compose the sole direct local-paper transaction port."""

    paper = _paper_runtime(
        runtime_root=runtime_root,
        theory_package=theory_package,
    )
    current_goal_id = _current_codex_goal_identity()
    if paper._registered_goal_identity() != current_goal_id:
        raise ValueError("V332_PAPER_AGENT_CALLER_GOAL_MISMATCH")
    return V332AgentPaperActionPort(paper)


def _current_codex_goal_identity() -> str:
    """Derive identity only from the Codex host's current task environment."""

    try:
        return current_codex_goal_identity()
    except CodexGoalIdentityError as exc:
        raise ValueError(
            "V332_PAPER_AGENT_CODEX_THREAD_ID_REQUIRED"
        ) from exc


def setup_paper_account(
    *,
    runtime_root: Path,
    theory_package: Path,
) -> Mapping[str, Any]:
    """Open the frozen account for this Goal with no caller identity controls."""

    paper = _paper_runtime(
        runtime_root=runtime_root,
        theory_package=theory_package,
    )
    current_goal_id = _current_codex_goal_identity()
    account = paper.setup()
    physical_goal_id = paper._registered_goal_identity()
    if physical_goal_id != current_goal_id:
        raise ValueError("V332_PAPER_AGENT_CALLER_GOAL_MISMATCH")
    status = paper.status()
    return {
        "schema_id": "agent-trade-emotion.v332-paper-agent-setup",
        "schema_version": "1.0.0",
        "status": "SETUP",
        "run_id": paper._runtime.run_manifest.run_id,
        "physical_goal_id": physical_goal_id,
        "logical_agent_id": paper.logical_agent_id,
        "agent_generation": paper.agent_generation,
        "account_id": account.account_id,
        "account_version": account.version,
        "ledger_head_record_sha256": status["ledger_head_record_sha256"],
        "external_orders_supported": False,
    }


def prepare_paper_action(
    *,
    runtime_root: Path,
    theory_package: Path,
    decision_cycle_id: str,
) -> Mapping[str, Any]:
    """Issue one sealed intent request to the registered persistent Goal."""

    result = _action_port(
        runtime_root=runtime_root,
        theory_package=theory_package,
    ).prepare_paper_action(decision_cycle_id=decision_cycle_id)
    if not isinstance(result, Mapping):
        raise TypeError("V332_PAPER_AGENT_RESULT_INVALID")
    return result


def commit_paper_action(
    *,
    runtime_root: Path,
    theory_package: Path,
    decision_cycle_id: str,
) -> Mapping[str, Any]:
    """Commit one sealed Agent action through the sole local-paper port."""

    result = _action_port(
        runtime_root=runtime_root,
        theory_package=theory_package,
    ).commit_paper_action(
        decision_cycle_id=decision_cycle_id
    )
    if not isinstance(result, Mapping):
        raise TypeError("V332_PAPER_AGENT_RESULT_INVALID")
    return result


def process_market_cycle(
    *,
    runtime_root: Path,
    theory_package: Path,
    cycle_id: str,
) -> Mapping[str, Any]:
    """Process admitted market/funding facts with no caller controls."""

    result = _action_port(
        runtime_root=runtime_root,
        theory_package=theory_package,
    ).process_market_cycle(cycle_id=cycle_id)
    if not isinstance(result, Mapping):
        raise TypeError("V332_PAPER_AGENT_RESULT_INVALID")
    return result


def submit_attention_checkpoint(
    *,
    runtime_root: Path,
    theory_package: Path,
    attention_request_path: Path,
) -> Mapping[str, Any]:
    """Seal one canonical Agent-authored request with runtime-owned provenance."""

    try:
        raw = attention_request_path.read_bytes()
        document = loads_json_strict(raw)
        if canonical_bytes(document) + b"\n" != raw:
            raise ValueError("V332_ATTENTION_REQUEST_NONCANONICAL")
        request = AttentionRequest.from_dict(document)
    except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
        raise ValueError("V332_ATTENTION_REQUEST_FILE_INVALID") from exc
    runtime = build_market_cycle_runtime(
        runtime_root=runtime_root,
        theory_package=theory_package,
        expected_theory_identity=V332_THEORY_IDENTITY,
        allow_public_collection=False,
    )
    result = runtime.submit_goal_attention_checkpoint(request)
    if not isinstance(result, Mapping):
        raise TypeError("V332_ATTENTION_CHECKPOINT_RESULT_INVALID")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    common = {
        "runtime_root": arguments.runtime_root,
        "theory_package": arguments.theory_package,
    }
    if arguments.command == "setup":
        result = setup_paper_account(**common)
    elif arguments.command == "checkpoint":
        result = submit_attention_checkpoint(
            **common,
            attention_request_path=arguments.attention_request_path,
        )
    elif arguments.command == "prepare":
        result = prepare_paper_action(
            **common, decision_cycle_id=arguments.decision_cycle_id
        )
    elif arguments.command == "process":
        result = process_market_cycle(**common, cycle_id=arguments.cycle_id)
    else:
        result = commit_paper_action(
            **common, decision_cycle_id=arguments.decision_cycle_id
        )
    _write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
