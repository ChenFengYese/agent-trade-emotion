from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    BOUNDARY_TYPES,
    DIRECTORY_DIGEST_FIELD,
    POLICY_DIGEST_FIELD,
    REQUIRED_SECTION_IDS,
    SHARD_DIGEST_FIELD,
    V32CycleAuditNarrativeError,
    build_v32_cycle_audit_narrative_bundle_v1,
    build_v32_cycle_audit_policy_v1,
    verify_v32_cycle_audit_narrative_bundle_v1,
    verify_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_authorized_revision_store import (
    LocalV32AuthorizedRevisionStore,
    V32AuthorizedRevisionStoreError,
)
from trade_system.theory_paper_v2.presentation.v32_cycle_audit_presenter import (
    render_v32_cycle_audit_narrative_markdown_v1,
)


RUN_ID = "v32-authorized-revision-test"
NOW = "2026-08-08T01:00:00Z"
SOURCE_BINDING = {
    "relative_ref": "accepted/cycle.json",
    "schema_id": "test_accepted_cycle_v1",
    "digest_field": "accepted_cycle_digest",
    "semantic_digest": "a" * 64,
    "physical_sha256": "b" * 64,
}


def _sections(*, suffix: str = "", repeat: int = 1) -> list[dict]:
    return [
        {
            "section_id": section_id,
            "title_zh": f"审计章节：{section_id}",
            "content_zh": (
                f"本节记录{section_id}的事实来源、限制与未知。{suffix}"
                * repeat
            ),
            "source_bindings": [SOURCE_BINDING],
        }
        for section_id in REQUIRED_SECTION_IDS
    ]


class CycleAuditNarrativeTests(unittest.TestCase):
    def test_all_thirteen_sections_split_replay_and_render(self) -> None:
        bundle = build_v32_cycle_audit_narrative_bundle_v1(
            narrative_id="cycle-audit-1",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            generated_at=NOW,
            sections=_sections(repeat=30),
            max_text_part_utf8_bytes=256,
            max_shard_canonical_bytes=4096,
        )
        directory = bundle["directory"]
        self.assertGreater(directory["shard_count"], len(REQUIRED_SECTION_IDS))
        self.assertEqual(
            verify_v32_cycle_audit_narrative_bundle_v1(
                directory, bundle["shards"]
            ),
            directory[DIRECTORY_DIGEST_FIELD],
        )
        rendered = render_v32_cycle_audit_narrative_markdown_v1(
            directory=directory, shards=bundle["shards"]
        )
        self.assertIn("V3.2 周期审计", rendered)
        self.assertIn("仅供人工审查", rendered)
        self.assertFalse(directory["narrative_is_authority"])
        self.assertFalse(directory["private_chain_of_thought_recorded"])

    def test_omission_reordering_and_non_chinese_fail(self) -> None:
        with self.assertRaises(V32CycleAuditNarrativeError):
            build_v32_cycle_audit_narrative_bundle_v1(
                narrative_id="missing",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                generated_at=NOW,
                sections=_sections()[:-1],
            )
        reordered = _sections()
        reordered[0], reordered[1] = reordered[1], reordered[0]
        with self.assertRaises(V32CycleAuditNarrativeError):
            build_v32_cycle_audit_narrative_bundle_v1(
                narrative_id="reordered",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                generated_at=NOW,
                sections=reordered,
            )
        non_chinese = _sections()
        non_chinese[0]["content_zh"] = "english only"
        with self.assertRaises(V32CycleAuditNarrativeError):
            build_v32_cycle_audit_narrative_bundle_v1(
                narrative_id="non-chinese",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                generated_at=NOW,
                sections=non_chinese,
            )

    def test_resigned_shard_tamper_is_detected_by_directory_replay(self) -> None:
        bundle = build_v32_cycle_audit_narrative_bundle_v1(
            narrative_id="tamper",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            generated_at=NOW,
            sections=_sections(),
        )
        shards = copy.deepcopy(bundle["shards"])
        shards[0]["content_part_zh"] += "篡改"
        shards[0]["content_part_utf8_bytes"] = len(
            shards[0]["content_part_zh"].encode("utf-8")
        )
        shards[0] = self_digest(shards[0], SHARD_DIGEST_FIELD)
        with self.assertRaises(V32CycleAuditNarrativeError):
            verify_v32_cycle_audit_narrative_bundle_v1(
                bundle["directory"], shards
            )

    def test_resource_limit_fails_closed(self) -> None:
        with self.assertRaises(V32CycleAuditNarrativeError) as raised:
            build_v32_cycle_audit_narrative_bundle_v1(
                narrative_id="capacity",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                generated_at=NOW,
                sections=_sections(repeat=100),
                max_text_part_utf8_bytes=1800,
                max_shard_canonical_bytes=2048,
            )
        self.assertEqual(str(raised.exception), "CONTEXT_CAPACITY_UNRESOLVED")

    def test_write_once_store_rejects_same_boundary_rewrite(self) -> None:
        first = build_v32_cycle_audit_narrative_bundle_v1(
            narrative_id="first",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            generated_at=NOW,
            sections=_sections(suffix="首版"),
        )
        second = build_v32_cycle_audit_narrative_bundle_v1(
            narrative_id="second",
            run_id=RUN_ID,
            cycle_index=1,
            boundary_type="ACCEPTANCE",
            generated_at=NOW,
            sections=_sections(suffix="改写版"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = LocalV32AuthorizedRevisionStore(Path(temporary))
            store.persist_audit_bundle(
                directory=first["directory"], shards=first["shards"]
            )
            with self.assertRaises(V32AuthorizedRevisionStoreError):
                store.persist_audit_bundle(
                    directory=second["directory"], shards=second["shards"]
                )

    def test_audit_policy_is_exact(self) -> None:
        policy = build_v32_cycle_audit_policy_v1(
            policy_id="audit-policy", run_scope_id=RUN_ID, frozen_at=NOW
        )
        self.assertEqual(
            verify_v32_cycle_audit_policy_v1(policy),
            policy[POLICY_DIGEST_FIELD],
        )
        self.assertTrue(policy["typed_boundary_must_be_sealed_before_narrative"])
        self.assertTrue(policy["acceptance_narrative_post_acceptance_only"])
        self.assertNotIn("post_acceptance_only", policy)
        policy["narrative_is_authority"] = True
        policy = self_digest(policy, POLICY_DIGEST_FIELD)
        with self.assertRaises(V32CycleAuditNarrativeError):
            verify_v32_cycle_audit_policy_v1(policy)

    def test_every_authorized_boundary_type_has_a_replayable_narrative(self) -> None:
        for boundary_type in sorted(BOUNDARY_TYPES):
            cycle_index = 0 if boundary_type == "QUALIFICATION" else 1
            with self.subTest(boundary_type=boundary_type):
                bundle = build_v32_cycle_audit_narrative_bundle_v1(
                    narrative_id=f"audit-{boundary_type.lower()}",
                    run_id=RUN_ID,
                    cycle_index=cycle_index,
                    boundary_type=boundary_type,
                    generated_at=NOW,
                    sections=_sections(suffix=f"边界为{boundary_type}"),
                )
                self.assertEqual(
                    verify_v32_cycle_audit_narrative_bundle_v1(
                        bundle["directory"], bundle["shards"]
                    ),
                    bundle["directory"][DIRECTORY_DIGEST_FIELD],
                )


if __name__ == "__main__":
    unittest.main()
