from __future__ import annotations

from copy import deepcopy
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_analysis_clock_view,
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_outcome_window_expiry import (
    EXPIRY_ROW_DIGEST_FIELD,
    EXPIRY_TERMINAL_DIGEST_FIELD,
    V32OutcomeWindowExpiryError,
    build_v32_outcome_window_expiry_terminal,
    verify_v32_outcome_window_expiry_terminal,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64


class V32OutcomeWindowExpiryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run_id = "v32-expiry-test"
        self.schedule_set = build_v32_outcome_schedule_set(
            run_id=self.run_id,
            decision_id="decision-0001",
            cycle_index=1,
            decision_time="2026-08-10T00:00:00Z",
            scheduled_at="2026-08-10T00:01:00Z",
            sealed_decision_digest=DIGEST_A,
            evaluation_contract_digest=DIGEST_B,
        )

    def _terminal(
        self, *, classified_at: str = "2026-08-10T00:30:00.000001Z"
    ):
        return build_v32_outcome_window_expiry_terminal(
            run_id=self.run_id,
            classified_at=classified_at,
            schedule_sets=[self.schedule_set],
            prior_terminal_schedule_ids=[],
            permit_digest=DIGEST_A,
            supervisor_checkpoint_digest_before_permit=DIGEST_B,
            outcome_checkpoint_digest_before=DIGEST_C,
            experiment_contract_digest=DIGEST_D,
            active_authority_digest="e" * 64,
        )

    def test_one_aggregate_contains_typed_zero_network_terminal_rows(self) -> None:
        terminal = self._terminal()
        self.assertEqual(
            terminal[EXPIRY_TERMINAL_DIGEST_FIELD],
            verify_v32_outcome_window_expiry_terminal(
                terminal, schedule_sets=[self.schedule_set]
            ),
        )
        self.assertEqual(0, terminal["network_request_count"])
        self.assertEqual(0, terminal["attempt_count"])
        self.assertFalse(terminal["raw_evidence_present"])
        self.assertFalse(terminal["observation_tick_present"])
        self.assertEqual(1, len(terminal["rows"]))
        row = terminal["rows"][0]
        self.assertEqual("UNKNOWN_COVERAGE_LOSS", row["resolution_status"])
        self.assertEqual(
            "OBSERVATION_WINDOW_MISSED", row["coverage_loss_reason"]
        )
        self.assertEqual(0, row["attempt_count"])
        self.assertIsNone(row["value"])

        clock = build_v32_analysis_clock_view(
            run_id=self.run_id,
            cycle_index=2,
            decision_time=terminal["classified_at"],
            schedule_sets=[self.schedule_set],
            terminal_outcome_receipts=terminal["rows"],
        )
        self.assertIn(row["schedule_id"], clock["mature_terminal_schedule_ids"])
        self.assertIn(
            row[EXPIRY_ROW_DIGEST_FIELD],
            clock["available_outcome_receipt_digests"],
        )

    def test_expiry_requires_strictly_after_grace_boundary(self) -> None:
        with self.assertRaisesRegex(
            V32OutcomeWindowExpiryError, "V32_EXPIRY_NO_EXPIRED_SCHEDULES"
        ):
            self._terminal(classified_at="2026-08-10T00:30:00Z")

    def test_structural_tamper_does_not_become_unknown(self) -> None:
        terminal = self._terminal()
        tampered = deepcopy(terminal)
        tampered["rows"][0]["schedule_digest"] = "f" * 64
        tampered = self_digest(
            {
                key: value
                for key, value in tampered.items()
                if key != EXPIRY_TERMINAL_DIGEST_FIELD
            },
            EXPIRY_TERMINAL_DIGEST_FIELD,
        )
        with self.assertRaises(V32OutcomeWindowExpiryError):
            verify_v32_outcome_window_expiry_terminal(
                tampered, schedule_sets=[self.schedule_set]
            )


if __name__ == "__main__":
    unittest.main()
