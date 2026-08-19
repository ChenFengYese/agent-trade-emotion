from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.v32_deterministic_audit import (
    V32DeterministicAuditError,
    compose_v32_deterministic_boundary_audit_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    DIRECTORY_DIGEST_FIELD,
    REQUIRED_SECTION_IDS,
    verify_v32_cycle_audit_narrative_bundle_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_authorized_revision_store import (
    LocalV32AuthorizedRevisionStore,
    V32AuthorizedRevisionStoreError,
)


RUN_ID = "v32-audit-render-test"
DIGEST_FIELD = "test_boundary_digest"


def _source(*, role: str = "analysis_acceptance") -> dict:
    document = self_digest(
        {
            "schema_id": "test_v32_sealed_boundary_v1",
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "audit_source_role": role,
            "accepted_at": "2026-08-08T01:00:00Z",
            "source_coverage_status": "PARTIAL_WITH_TYPED_UNKNOWN",
            "objective_unknown_count": 2,
            "subjective_plausibility_tier": "LOW",
            "hypothesis_ids": ["long-path", "short-path", "other", "unknown"],
            "legal_actions": [
                "OPEN_PROBE",
                "ADD",
                "HOLD",
                "REDUCE",
                "CLOSE",
                "REENTER",
                "REVERSE",
                "WAIT",
            ],
            "selected_action": "OPEN_PROBE",
            "runner_up_action": "WAIT",
            "reference_risk_budget": "4.2",
            "shadow_arm_count": 6,
            "outcome_schedule_count": 3,
            "recovery_status": "NONE_REQUIRED",
            "executable": False,
            "account_access": False,
            "order_submission": False,
            "large_public_series": list(range(5000)),
        },
        DIGEST_FIELD,
    )
    return {
        "role": role,
        "document": document,
        "binding": {
            "relative_ref": f"cycles/0001/{role}.json",
            "schema_id": document["schema_id"],
            "digest_field": DIGEST_FIELD,
            "semantic_digest": document[DIGEST_FIELD],
            "physical_sha256": hashlib.sha256(
                canonical_bytes(document) + b"\n"
            ).hexdigest(),
        },
    }


class V32DeterministicAuditTests(unittest.TestCase):
    def test_all_sections_are_mechanical_bounded_and_replayable(self) -> None:
        bundle = compose_v32_deterministic_boundary_audit_v1(
            narrative_id="acceptance-audit-1",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            boundary_sealed_at="2026-08-08T01:00:00Z",
            generated_at="2026-08-08T01:00:01Z",
            sealed_sources=[_source()],
        )
        self.assertEqual(
            [row["section_id"] for row in bundle["directory"]["section_entries"]],
            list(REQUIRED_SECTION_IDS),
        )
        verify_v32_cycle_audit_narrative_bundle_v1(
            bundle["directory"], bundle["shards"]
        )
        text = "".join(row["content_part_zh"] for row in bundle["shards"])
        self.assertIn("完整原件仍是唯一权威", text)
        self.assertIn("完整工件规范字节数", text)
        self.assertNotIn("4999", text)

        with tempfile.TemporaryDirectory() as directory:
            store = LocalV32AuthorizedRevisionStore(Path(directory))
            store.persist_audit_bundle(
                directory=bundle["directory"], shards=bundle["shards"]
            )
            self.assertEqual(
                {"directory": bundle["directory"], "shards": bundle["shards"]},
                store.load_audit_bundle(
                    run_id=RUN_ID,
                    cycle_index=1,
                    boundary_type="ACCEPTANCE",
                ),
            )
            base = (
                Path(directory)
                / "v32-authorized-revisions-v1"
                / RUN_ID
                / "cycles"
                / "0001"
                / "audit"
                / "acceptance"
            )
            (base / "unexpected.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                store.load_audit_bundle(
                    run_id=RUN_ID,
                    cycle_index=1,
                    boundary_type="ACCEPTANCE",
                )

    def test_source_order_cannot_change_directory(self) -> None:
        first = _source(role="z-source")
        second = _source(role="a-source")
        arguments = dict(
            narrative_id="ordered-audit",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ANALYSIS",
            boundary_sealed_at="2026-08-08T01:00:00Z",
            generated_at="2026-08-08T01:00:01Z",
        )
        left = compose_v32_deterministic_boundary_audit_v1(
            **arguments, sealed_sources=[first, second]
        )
        right = compose_v32_deterministic_boundary_audit_v1(
            **arguments, sealed_sources=[second, first]
        )
        self.assertEqual(left, right)

    def test_legacy_exact_layout_replays_the_original_public_bundle(self) -> None:
        bundle = compose_v32_deterministic_boundary_audit_v1(
            narrative_id="legacy-audit-1",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            boundary_sealed_at="2026-08-08T01:00:00Z",
            generated_at="2026-08-08T01:00:01Z",
            sealed_sources=[_source()],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = (
                root
                / "v32-authorized-revisions-v1"
                / RUN_ID
                / "cycles"
                / "0001"
                / "audit"
                / "acceptance"
            )
            shard_root = base / "shards"
            shard_root.mkdir(parents=True)
            directory_document = bundle["directory"]
            (
                base / f"{directory_document[DIRECTORY_DIGEST_FIELD]}.json"
            ).write_bytes(canonical_bytes(directory_document) + b"\n")
            for index, shard in enumerate(bundle["shards"]):
                (shard_root / f"{index:04d}.json").write_bytes(
                    canonical_bytes(shard) + b"\n"
                )

            store = LocalV32AuthorizedRevisionStore(root)
            self.assertEqual(
                {"directory": bundle["directory"], "shards": bundle["shards"]},
                store.load_audit_bundle(
                    run_id=RUN_ID,
                    cycle_index=1,
                    boundary_type="ACCEPTANCE",
                ),
            )
            (shard_root / "unexpected.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                store.load_audit_bundle(
                    run_id=RUN_ID,
                    cycle_index=1,
                    boundary_type="ACCEPTANCE",
                )

    def test_tamper_private_reasoning_and_preboundary_time_fail(self) -> None:
        source = _source()
        tampered = deepcopy(source)
        tampered["binding"]["physical_sha256"] = "0" * 64
        with self.assertRaises(V32DeterministicAuditError):
            compose_v32_deterministic_boundary_audit_v1(
                narrative_id="tampered",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                boundary_sealed_at="2026-08-08T01:00:00Z",
                generated_at="2026-08-08T01:00:01Z",
                sealed_sources=[tampered],
            )

        private = _source()
        private["document"]["private_reasoning"] = "禁止记录"
        private["document"] = self_digest(private["document"], DIGEST_FIELD)
        private["binding"]["semantic_digest"] = private["document"][DIGEST_FIELD]
        private["binding"]["physical_sha256"] = hashlib.sha256(
            canonical_bytes(private["document"]) + b"\n"
        ).hexdigest()
        with self.assertRaises(V32DeterministicAuditError):
            compose_v32_deterministic_boundary_audit_v1(
                narrative_id="private",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ANALYSIS",
                boundary_sealed_at="2026-08-08T01:00:00Z",
                generated_at="2026-08-08T01:00:01Z",
                sealed_sources=[private],
            )

        with self.assertRaisesRegex(
            V32DeterministicAuditError, "BEFORE_BOUNDARY"
        ):
            compose_v32_deterministic_boundary_audit_v1(
                narrative_id="early",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="OUTCOME",
                boundary_sealed_at="2026-08-08T01:00:02Z",
                generated_at="2026-08-08T01:00:01Z",
                sealed_sources=[source],
            )


if __name__ == "__main__":
    unittest.main()
