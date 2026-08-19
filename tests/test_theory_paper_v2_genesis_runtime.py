from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trade_system.theory_paper_v2.application import (
    OfflineRunManifestInput,
    RuntimeBootstrapError,
    initialize_offline_runtime,
)
from trade_system.theory_paper_v2.domain.common import ReducerStatus
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.strategic import (
    OpenEpisodeCommand,
    StrategicStatus,
    TrustedReceiptAssertion,
    open_strategic_episode,
)
from trade_system.theory_paper_v2.domain.time_authority import ReviewClock


class GenesisRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 31, 12, tzinfo=UTC)

    def receipt(self, ref, owner):
        return TrustedReceiptAssertion(
            receipt_ref=ref,
            owner_module=owner,
            causal_cutoff=self.now,
            verdict="PASS",
        )

    def command(self):
        return OpenEpisodeCommand(
            request_id="request:open:1",
            expected_head_digest=None,
            episode_id="episode:1",
            instrument_id="SNDKUSDT",
            direction="LONG",
            decision_cutoff=self.now,
            strategic_timeframe_seconds=14_400,
            hypothesis_set_id="hypothesis-set:1",
            premise_ids=("premise:oversold", "premise:liquidity"),
            hard_invalidator_ids=("invalidator:mechanism-break",),
            review_clock=ReviewClock(
                clock_id="review:1",
                next_review_at=self.now + timedelta(hours=4),
                mandatory_review_at=self.now + timedelta(hours=8),
            ),
            episode_risk_allocation_id="risk-allocation:1",
            new_hypothesis_receipt=self.receipt(
                "hypothesis-receipt:1", "DOMAIN_HYPOTHESIS"
            ),
            time_authority_receipt=self.receipt(
                "time-receipt:1", "DOMAIN_TIME_AUTHORITY"
            ),
            evidence_admission_receipts=(
                self.receipt("evidence:1", "DOMAIN_EVIDENCE"),
            ),
            timeframe_authority_profile_receipt=self.receipt(
                "timeframe-profile:1", "DOMAIN_POLICY"
            ),
            portfolio_snapshot_receipt=self.receipt(
                "portfolio:1", "INFRASTRUCTURE_OFFLINE_PORTFOLIO"
            ),
            cooldown_receipt=self.receipt(
                "cooldown:1", "DOMAIN_STRATEGIC"
            ),
            episode_risk_allocation_receipt=self.receipt(
                "risk:1", "DOMAIN_POSITION"
            ),
        )

    def test_strict_genesis_is_owner_and_cutoff_bound(self):
        result = open_strategic_episode(self.command())
        self.assertEqual(ReducerStatus.APPLIED, result.status)
        self.assertEqual(StrategicStatus.ACTIVE, result.value.state.strategic_status)
        self.assertEqual(1, result.value.state.revision)
        self.assertFalse(result.value.opened_receipt.executable)
        wrong_owner = replace(
            self.command(),
            time_authority_receipt=self.receipt(
                "time-receipt:forged", "AGENT"
            ),
        )
        self.assertEqual(
            ReducerStatus.UNKNOWN,
            open_strategic_episode(wrong_owner).status,
        )

    def test_active_or_nonclosed_prior_blocks_genesis(self):
        active = replace(
            self.command(), expected_active_episode_ref="episode:active"
        )
        self.assertEqual(
            "GENESIS_ACTIVE_EPISODE_EXISTS",
            open_strategic_episode(active).error.code,
        )
        prior = replace(
            self.command(), prior_episode_status=StrategicStatus.INVALIDATED
        )
        self.assertEqual(
            "GENESIS_COOLDOWN_INCOMPLETE",
            open_strategic_episode(prior).error.code,
        )

    def test_runtime_requires_explicit_id_and_write_once_manifest(self):
        inputs = OfflineRunManifestInput(
            offline_run_id="round1-e0-001",
            theory_contract_digest="1" * 64,
            code_digest="2" * 64,
            schema_bundle_digest="3" * 64,
            policy_digest="4" * 64,
            dataset_digest="5" * 64,
            automation_status_observed="PAUSED",
            authority_snapshot_digest="6" * 64,
            cluster_bootstrap_receipt_digest="7" * 64,
            project_state_genesis_contract_digest="8" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            first = initialize_offline_runtime(Path(directory), inputs)
            second = initialize_offline_runtime(Path(directory), inputs)
            self.assertEqual(first, second)
            manifest = load_json_strict(first)
            verify_self_digest(manifest, "manifest_digest")
            self.assertFalse(manifest["executable"])
        with self.assertRaisesRegex(
            RuntimeBootstrapError, "EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED"
        ):
            initialize_offline_runtime(
                Path(tempfile.gettempdir()),
                replace(inputs, offline_run_id="current"),
            )


if __name__ == "__main__":
    unittest.main()
