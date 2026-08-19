from __future__ import annotations

from copy import deepcopy
import unittest

from trade_system.theory_paper_v2.domain.v32_recovery_supervision import (
    POLICY_DIGEST_FIELD,
    RECOVERY_DIGEST_FIELD,
    V32RecoverySupervisionError,
    build_v32_deterministic_recovery_receipt_v1,
    build_v32_recovery_supervision_policy_v1,
    build_v32_supervisor_observation_v1,
    verify_v32_deterministic_recovery_receipt_v1,
)


def binding(ref: str, value: str = "a") -> dict[str, str]:
    return {
        "relative_ref": ref,
        "schema_id": "fixture_v1",
        "digest_field": "fixture_digest",
        "semantic_digest": value * 64,
        "physical_sha256": value * 64,
    }


class V32RecoverySupervisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = build_v32_recovery_supervision_policy_v1(
            policy_id="v32-recovery-policy", frozen_at="2026-08-08T00:00:00Z"
        )
        self.observation = build_v32_supervisor_observation_v1(
            observation_id="obs-1",
            policy=self.policy,
            run_id="v32-run",
            cycle_index=1,
            observed_at="2026-08-08T00:01:00Z",
            lane="AUDIT",
            severity="WARNING",
            failure_code="AUDIT_INDEX_MISSING_AFTER_SHARDS_SEALED",
            summary="Audit shards are sealed but the derived index is absent.",
            evidence_bindings=[binding("cycles/0001/audit-shard-0001.json")],
            disposition="SAME_RUN_DETERMINISTIC_RECOVERY_ALLOWED",
            proposed_action=(
                "REBUILD_POINTER_OR_INDEX_FROM_UNIQUE_PREDECESSOR_SUCCESSOR"
            ),
            reason="The index contains no new semantic or market fact.",
        )

    def test_policy_is_read_only_public_and_non_executable(self) -> None:
        self.assertEqual(
            self.policy[POLICY_DIGEST_FIELD],
            build_v32_recovery_supervision_policy_v1(
                policy_id="v32-recovery-policy", frozen_at="2026-08-08T00:00:00Z"
            )[POLICY_DIGEST_FIELD],
        )
        self.assertFalse(self.policy["supervisor_may_mutate_state"])
        self.assertFalse(self.policy["supervisor_is_execution_risk_supervisor"])
        self.assertFalse(self.policy["future_outcome_access"])
        self.assertFalse(self.policy["executable"])

    def test_same_run_recovery_is_zero_network_zero_agent_zero_outcome(self) -> None:
        receipt = build_v32_deterministic_recovery_receipt_v1(
            receipt_id="recovery-1",
            policy=self.policy,
            observation=self.observation,
            action="REBUILD_POINTER_OR_INDEX_FROM_UNIQUE_PREDECESSOR_SUCCESSOR",
            started_at="2026-08-08T00:02:00Z",
            completed_at="2026-08-08T00:02:01Z",
            input_bindings=[binding("cycles/0001/audit-shard-0001.json")],
            output_bindings=[binding("cycles/0001/audit-index.json", "b")],
            result="COMPLETED",
            state_change_boundaries=1,
        )
        self.assertEqual(
            receipt[RECOVERY_DIGEST_FIELD],
            verify_v32_deterministic_recovery_receipt_v1(
                receipt, policy=self.policy, observation=self.observation
            ),
        )
        self.assertEqual(0, receipt["network_request_count"])
        self.assertEqual(0, receipt["agent_attempt_count"])
        self.assertEqual(0, receipt["outcome_read_count"])
        self.assertFalse(receipt["sealed_or_accepted_bytes_mutated"])

    def test_network_or_agent_retry_cannot_be_relabelled_auto_repair(self) -> None:
        for action in (
            "SECOND_NETWORK_ATTEMPT_WITHIN_SEALED_CYCLE",
            "SECOND_AGENT_ATTEMPT_WITHIN_STAGE",
            "LOCAL_ADAPTER_CONFIGURATION",
        ):
            with self.subTest(action=action), self.assertRaises(
                V32RecoverySupervisionError
            ):
                build_v32_supervisor_observation_v1(
                    observation_id="obs-bad",
                    policy=self.policy,
                    run_id="v32-run",
                    cycle_index=1,
                    observed_at="2026-08-08T00:01:00Z",
                    lane="AGENT",
                    severity="STOP",
                    failure_code="FAIL",
                    summary="Failure.",
                    evidence_bindings=[binding("failure.json")],
                    disposition="SAME_RUN_DETERMINISTIC_RECOVERY_ALLOWED",
                    proposed_action=action,
                    reason="Invalid same-run recovery.",
                )

    def test_tamper_fails_closed(self) -> None:
        receipt = build_v32_deterministic_recovery_receipt_v1(
            receipt_id="recovery-1",
            policy=self.policy,
            observation=self.observation,
            action="REBUILD_POINTER_OR_INDEX_FROM_UNIQUE_PREDECESSOR_SUCCESSOR",
            started_at="2026-08-08T00:02:00Z",
            completed_at="2026-08-08T00:02:01Z",
            input_bindings=[binding("cycles/0001/audit-shard-0001.json")],
            output_bindings=[binding("cycles/0001/audit-index.json", "b")],
            result="COMPLETED",
            state_change_boundaries=1,
        )
        tampered = deepcopy(receipt)
        tampered["network_request_count"] = 1
        with self.assertRaises(V32RecoverySupervisionError):
            verify_v32_deterministic_recovery_receipt_v1(
                tampered, policy=self.policy, observation=self.observation
            )


if __name__ == "__main__":
    unittest.main()
