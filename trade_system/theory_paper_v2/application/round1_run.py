"""One read-only first-round use case over the frozen V1 cycles 1--24."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..domain.contracts.canonical import canonical_digest
from ..infrastructure.legacy_v1 import legacy_tree_digest
from .round1_evaluation import (
    FrozenCostPolicy,
    Round1EvaluationResult,
    evaluate_frozen_round1,
)
from .scenarios import (
    CanonicalScenarioReport,
    run_canonical_scenarios,
)
from .topology_evaluation import (
    TopologyEvaluationResult,
    evaluate_agent_topologies,
)


@dataclass(frozen=True, slots=True)
class FrozenRound1RunResult:
    source_tree_digest_before: str
    source_tree_digest_after: str
    source_tree_unchanged: bool
    scenario_report: CanonicalScenarioReport
    evaluation: Round1EvaluationResult
    topology_evaluation: TopologyEvaluationResult
    round2_authorized: bool
    round2_status: str
    run_result_digest: str
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False


def execute_frozen_round1(
    *,
    run_root: Path,
    expected_run_id: str,
    expected_manifest_digest: str,
    cost_policy: FrozenCostPolicy,
) -> FrozenRound1RunResult:
    """Run scenarios and the frozen comparison without mutating V1."""

    root = Path(run_root).resolve(strict=True)
    source_before = legacy_tree_digest(root)
    scenarios = run_canonical_scenarios()
    scenarios_passed = (
        scenarios.pass_count == 32
        and scenarios.fail_count == 0
        and scenarios.unknown_count == 0
    )
    evaluation = evaluate_frozen_round1(
        run_root=root,
        expected_run_id=expected_run_id,
        expected_manifest_digest=expected_manifest_digest,
        cost_policy=cost_policy,
        canonical_scenario_suite_digest=scenarios.report_digest,
        canonical_scenarios_passed=scenarios_passed,
    )
    topology = evaluate_agent_topologies(())
    source_after = legacy_tree_digest(root)
    if source_after != source_before:
        raise ValueError("LEGACY_WRITE_ATTEMPT_FORBIDDEN")

    round2_authorized = (
        evaluation.terminal_status == "PASS_ADVANCE_TO_ROUND_2"
    )
    round2_status = (
        "AUTHORIZED_BY_FROZEN_GATE"
        if round2_authorized
        else "NOT_AUTHORIZED"
    )
    payload = {
        "source_tree_digest_before": source_before,
        "source_tree_digest_after": source_after,
        "source_tree_unchanged": True,
        "scenario_report": asdict(scenarios),
        "evaluation": asdict(evaluation),
        "topology_evaluation": asdict(topology),
        "round2_authorized": round2_authorized,
        "round2_status": round2_status,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return FrozenRound1RunResult(
        source_tree_digest_before=source_before,
        source_tree_digest_after=source_after,
        source_tree_unchanged=True,
        scenario_report=scenarios,
        evaluation=evaluation,
        topology_evaluation=topology,
        round2_authorized=round2_authorized,
        round2_status=round2_status,
        run_result_digest=canonical_digest(payload),
    )


__all__ = ["FrozenRound1RunResult", "execute_frozen_round1"]
