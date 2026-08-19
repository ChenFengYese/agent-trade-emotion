from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trade_system.theory_paper_v2.application.prospective_single_agent import (
    prepare_prospective_research,
)
from trade_system.theory_paper_v2.application.single_agent_research import (
    prepare_seen_v1_research,
)
from trade_system.theory_paper_v2.domain.governance.research_authority import (
    ResearchAuthorityError,
    assert_research_start_authorized,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.infrastructure.authority.current_research import (
    load_current_research_authority,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_AUTHORIZED_TEMPLATE = (
    PROJECT_ROOT
    / "config/theory_paper_v2.prospective_24h.v1_4_authorized_20260805.json"
)
LEGACY_SEEN_CONTRACT = (
    PROJECT_ROOT / "config/theory_paper_v2.seen_v1_diagnostic.v1_4.json"
)


class CurrentResearchAuthorityTests(unittest.TestCase):
    def test_v31_is_frozen_but_experiment_start_remains_qualification_gated(self) -> None:
        authority = load_current_research_authority(PROJECT_ROOT)
        self.assertEqual(
            "FROZEN_V3_1_QUALIFICATION_PENDING", authority["status"]
        )
        self.assertFalse(authority["experiment_start_authorized"])
        self.assertEqual([], authority["authorized_operations"])
        self.assertEqual([], authority["authorized_run_ids"])
        self.assertEqual([], authority["authorized_template_sha256s"])
        self.assertEqual(
            "theory/history/RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md",
            authority["current_theory"]["path"],
        )
        self.assertEqual(
            "FROZEN_APPROVED",
            authority["current_theory"]["review_status"],
        )

    def test_active_authority_requires_exact_operation_run_template_and_receipt(self) -> None:
        authority = copy.deepcopy(load_current_research_authority(PROJECT_ROOT))
        authority.update(
            {
                "status": "ACTIVE_FROZEN_RESEARCH",
                "experiment_start_authorized": True,
                "authorized_operations": ["PREPARE_PROSPECTIVE"],
                "authorized_run_ids": ["explicit-run-id"],
                "authorized_template_sha256s": ["a" * 64],
                "authorization_receipt_path": "config/explicit-receipt.json",
                "authorization_receipt_digest": "b" * 64,
            }
        )
        authority["current_theory"]["review_status"] = "FROZEN_APPROVED"
        receipt = self_digest(
            {
                "schema_id": "theory_paper_v2_research_authorization_receipt",
                "schema_version": "1.0.0",
                "authority_id": authority["authority_id"],
                "issued_at": "2026-08-06T01:00:00Z",
                "current_theory_sha256": authority["current_theory"][
                    "physical_sha256"
                ],
                "authorized_operations": authority["authorized_operations"],
                "authorized_run_ids": authority["authorized_run_ids"],
                "authorized_template_sha256s": authority[
                    "authorized_template_sha256s"
                ],
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "authorization_receipt_digest",
        )
        authority["authorization_receipt_digest"] = receipt[
            "authorization_receipt_digest"
        ]
        assert_research_start_authorized(
            authority,
            operation="PREPARE_PROSPECTIVE",
            run_id="explicit-run-id",
            template_sha256="a" * 64,
            authorization_receipt=receipt,
        )
        forged_receipt = self_digest(
            {
                key: value
                for key, value in receipt.items()
                if key != "authorization_receipt_digest"
            }
            | {"authorized_run_ids": ["different-run-id"]},
            "authorization_receipt_digest",
        )
        with self.assertRaisesRegex(
            ResearchAuthorityError,
            "CURRENT_RESEARCH_AUTHORIZATION_RECEIPT_INVALID",
        ):
            assert_research_start_authorized(
                authority,
                operation="PREPARE_PROSPECTIVE",
                run_id="explicit-run-id",
                template_sha256="a" * 64,
                authorization_receipt=forged_receipt,
            )
        with self.assertRaisesRegex(
            ResearchAuthorityError, "RESEARCH_START_RUN_ID_NOT_AUTHORIZED"
        ):
            assert_research_start_authorized(
                authority,
                operation="PREPARE_PROSPECTIVE",
                run_id="different-run-id",
                template_sha256="a" * 64,
                authorization_receipt=receipt,
            )

    def test_legacy_start_authorized_template_cannot_collect_or_create_run(self) -> None:
        run_id = "legacy-template-must-not-start"
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            with patch(
                "trade_system.theory_paper_v2.application.prospective_single_agent.collect_okx_six_context"
            ) as collector:
                with self.assertRaisesRegex(
                    ResearchAuthorityError,
                    "RESEARCH_START_SUSPENDED_USER_REVIEW_REQUIRED",
                ):
                    prepare_prospective_research(
                        project_root=PROJECT_ROOT,
                        runtime_root=runtime_root,
                        template_path=LEGACY_AUTHORIZED_TEMPLATE,
                        run_id=run_id,
                    )
            collector.assert_not_called()
            self.assertFalse((runtime_root / run_id).exists())

    def test_seen_replay_prepare_is_also_denied_before_source_access(self) -> None:
        run_id = "seen-replay-must-not-start"
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            with self.assertRaisesRegex(
                ResearchAuthorityError,
                "RESEARCH_START_SUSPENDED_USER_REVIEW_REQUIRED",
            ):
                prepare_seen_v1_research(
                    project_root=PROJECT_ROOT,
                    source_root=runtime_root / "missing-source",
                    runtime_root=runtime_root,
                    contract_path=LEGACY_SEEN_CONTRACT,
                    run_id=run_id,
                )
            self.assertFalse((runtime_root / run_id).exists())


if __name__ == "__main__":
    unittest.main()
