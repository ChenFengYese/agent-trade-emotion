from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from trade_system.theory_paper_v2.application.topology_evaluation import (
    TOPOLOGY_IDS,
    TopologyObservation,
    evaluate_agent_topologies,
)


def _observation(
    session: int,
    topology_id: str,
    *,
    coverage: str,
    challenge: str,
    quality: str,
) -> TopologyObservation:
    return TopologyObservation(
        session_id=f"session-{session:02d}",
        topology_id=topology_id,
        input_digest=f"{session:064x}",
        model_class="SAME_MODEL_CLASS",
        total_budget_digest="b" * 64,
        dynamic_candidate_coverage=Decimal(coverage),
        material_challenge_coverage=Decimal(challenge),
        action_quality_score=Decimal(quality),
        safety_state_pit_authority_failures=0,
        role_overreach_failures=0,
        model_calls=1 if topology_id == "SINGLE_STRONG" else 3,
        tokens=3000,
        latency_ms=1000,
        cost_microunits=300,
        timeout_count=0,
        missing_role_count=0,
    )


class TopologyEvaluationTests(unittest.TestCase):
    def test_missing_paired_agent_outputs_falls_back_without_inferiority_claim(self):
        result = evaluate_agent_topologies(())
        self.assertEqual("INCONCLUSIVE_USE_SINGLE_AGENT", result.selection_status)
        self.assertEqual("SINGLE_STRONG", result.selected_topology_id)
        self.assertFalse(result.equal_input_model_budget_verified)
        self.assertIn(
            "MINIMUM_32_PAIRED_SESSIONS_NOT_MET",
            result.reason_codes,
        )

    def test_cluster_requires_all_frozen_improvement_and_interval_gates(self):
        observations = []
        for session in range(32):
            observations.extend(
                (
                    _observation(
                        session,
                        "SINGLE_STRONG",
                        coverage="0.50",
                        challenge="0.40",
                        quality="0.10",
                    ),
                    _observation(
                        session,
                        "CLUSTER_POST_PROPOSAL",
                        coverage="0.60",
                        challenge="0.60",
                        quality="0.90",
                    ),
                    _observation(
                        session,
                        "CLUSTER_BLIND",
                        coverage="0.51",
                        challenge="0.41",
                        quality="0.20",
                    ),
                )
            )
        result = evaluate_agent_topologies(tuple(observations))
        self.assertEqual(tuple(TOPOLOGY_IDS), tuple(
            item.topology_id for item in result.arm_summaries
        ))
        self.assertEqual("CLUSTER_SELECTED", result.selection_status)
        self.assertEqual(
            "CLUSTER_POST_PROPOSAL",
            result.selected_topology_id,
        )
        selected = result.arm_summaries[1]
        self.assertGreaterEqual(
            selected.action_quality_interval_lower,
            Decimal(0),
        )
        repeat = evaluate_agent_topologies(tuple(observations))
        self.assertEqual(result.result_digest, repeat.result_digest)

    def test_budget_mismatch_fails_experiment_not_trading_safety(self):
        observations = []
        for session in range(32):
            rows = [
                _observation(
                    session,
                    topology_id,
                    coverage="0.5",
                    challenge="0.5",
                    quality="0.5",
                )
                for topology_id in TOPOLOGY_IDS
            ]
            if session == 0:
                rows[1] = replace(
                    rows[1],
                    total_budget_digest="c" * 64,
                )
            observations.extend(rows)
        result = evaluate_agent_topologies(tuple(observations))
        self.assertEqual("FAIL_INVALID_EXPERIMENT", result.selection_status)
        self.assertFalse(result.equal_input_model_budget_verified)
        self.assertEqual("SINGLE_STRONG", result.selected_topology_id)


if __name__ == "__main__":
    unittest.main()
