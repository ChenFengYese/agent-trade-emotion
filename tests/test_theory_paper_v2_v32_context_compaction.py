from __future__ import annotations

import copy
import hashlib
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD,
    SELECTION_DIGEST_FIELD,
    V32ContextCompactionError,
    _build_shard,
    _fits_shard_limit,
    _shard_canonical_size_from_parts,
    build_v32_context_compaction_bundle_v1,
    build_v32_context_compaction_policy_v1,
    build_v32_context_shard_selection_v1,
    verify_v32_context_compaction_bundle_v1,
    verify_v32_context_compaction_policy_v1,
    verify_v32_context_shard_selection_v1,
)


RUN_ID = "v32-authorized-revision-test"
NOW = "2026-08-08T01:00:00Z"


def _physical(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()


def _binding(document: dict, digest_field: str, relative_ref: str) -> dict:
    return {
        "relative_ref": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": _physical(document),
    }


def _original(*, oversized: bool = False) -> dict:
    thesis = "市场测试历史磁区" + ("压" * 5000 if oversized else "")
    return self_digest(
        {
            "schema_id": "test_v32_complete_original_v1",
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "created_at": NOW,
            "objective_unknown": "UNKNOWN",
            "conflict_note": "成交量不能区分机构承接与散户挂单",
            "hypotheses": [
                {
                    "hypothesis_id": "h-long",
                    "thesis": thesis,
                    "falsifier": "跌破后无承接",
                    "hazard": "假跌破与止损穿透",
                    "evidence_refs": ["fact-a"],
                },
                {
                    "hypothesis_id": "h-short",
                    "opposing_hypothesis": "磁区是陷阱区",
                    "falsifier": "跌破后快速收复",
                    "evidence_refs": ["fact-b"],
                },
            ],
            "unrelated": {"a": "same-value", "b": "same-value"},
        },
        "artifact_digest",
    )


def _source(original: dict) -> dict:
    return {
        "artifact_binding": _binding(
            original, "artifact_digest", "originals/source.json"
        ),
        "canonical_bytes": len(canonical_bytes(original)),
    }


class ContextCompactionTests(unittest.TestCase):
    def _bundle(self, original: dict | None = None, *, limit: int = 65_536):
        original = original or _original()
        bundle = build_v32_context_compaction_bundle_v1(
            run_id=RUN_ID,
            cycle_index=1,
            created_at=NOW,
            source_artifacts=[_source(original)],
            original_documents=[original],
            max_shard_canonical_bytes=limit,
        )
        return original, bundle

    def test_complete_replay_coverage_and_policy_root_selection(self) -> None:
        original, bundle = self._bundle()
        manifest = bundle["manifest"]
        self.assertEqual(
            verify_v32_context_compaction_bundle_v1(
                manifest, bundle["shards"], original_documents=[original]
            ),
            manifest[MANIFEST_DIGEST_FIELD],
        )
        proof = manifest["source_coverage_proofs"][0]
        self.assertGreater(proof["leaf_count"], 0)
        self.assertEqual(64, len(proof["member_ids_digest"]))
        self.assertEqual(proof["leaf_count"], manifest["member_count"])
        self.assertTrue(proof["complete_recursive_leaf_coverage"])

        manifest_binding = _binding(
            manifest,
            MANIFEST_DIGEST_FIELD,
            "context-compaction/manifest.json",
        )
        selection = build_v32_context_shard_selection_v1(
            manifest=manifest,
            manifest_binding=manifest_binding,
            shards=bundle["shards"],
            original_documents=[original],
            caller_required_member_ids=[],
            selected_at=NOW,
            max_agent_context_canonical_bytes=262_144,
        )
        self.assertTrue(set(manifest["policy_required_member_ids"]))
        self.assertEqual(
            selection["selected_member_count"], manifest["member_count"]
        )
        self.assertEqual(selection["selected_shard_count"], len(bundle["shards"]))
        self.assertEqual(
            selection["selected_member_ids_digest"],
            manifest["folded_member_ids_digest"],
        )
        self.assertTrue(selection["forced_full_member_inventory"])
        self.assertTrue(selection["forced_full_shard_inventory"])
        self.assertTrue(selection["sequential_delivery_required"])
        self.assertEqual(
            verify_v32_context_shard_selection_v1(
                selection,
                manifest=manifest,
                shards=bundle["shards"],
                original_documents=[original],
            ),
            selection[SELECTION_DIGEST_FIELD],
        )

    def test_dictionary_equality_does_not_create_dependency(self) -> None:
        _, bundle = self._bundle()
        rows = [row for shard in bundle["shards"] for row in shard["member_rows"]]
        repeated = [
            row
            for row in rows
            if row["json_pointer"] in {"/unrelated/a", "/unrelated/b"}
        ]
        self.assertEqual(len(repeated), 2)
        self.assertEqual(
            repeated[0]["dictionary_value_digest"],
            repeated[1]["dictionary_value_digest"],
        )
        self.assertEqual(repeated[0]["dependency_refs"], [])
        self.assertEqual(repeated[1]["dependency_refs"], [])
        self.assertFalse(bundle["manifest"]["dictionary_equality_creates_dependency"])

    def test_incremental_shard_size_is_exact_for_unicode_and_escaping(self) -> None:
        value = '市场\n"磁区"\\路径🙂' + ("压" * 900)
        value_digest = canonical_digest(value)
        row = {
            "member_id": "leaf:" + ("a" * 64),
            "source_artifact_semantic_digest": "b" * 64,
            "json_pointer": "/复杂~1路径/0",
            "semantic_role": "DATA",
            "dictionary_value_digest": value_digest,
            "dependency_refs": [],
        }
        dictionary = {value_digest: value}
        shard = _build_shard(
            run_id=RUN_ID,
            cycle_index=1,
            created_at=NOW,
            shard_index=7,
            rows=[row],
            dictionary=dictionary,
        )
        entry = {"value_digest": value_digest, "value": value}
        estimated = _shard_canonical_size_from_parts(
            run_id=RUN_ID,
            cycle_index=1,
            created_at=NOW,
            shard_index=7,
            member_count=1,
            member_row_bytes=len(canonical_bytes(row)),
            member_id_bytes=len(canonical_bytes(row["member_id"])),
            dictionary_entry_count=1,
            dictionary_entry_bytes=len(canonical_bytes(entry)),
            dependency_closure_complete=True,
        )
        self.assertEqual(estimated, len(canonical_bytes(shard)))

    def test_incremental_shard_size_preserves_exact_limit_plus_one_boundary(self) -> None:
        values = ["alpha", "βeta"]
        digests = [canonical_digest(value) for value in values]
        rows = [
            {
                "member_id": "leaf:" + character * 64,
                "source_artifact_semantic_digest": "d" * 64,
                "json_pointer": f"/rows/{index}/value",
                "semantic_role": "DATA",
                "dictionary_value_digest": digest,
                "dependency_refs": ([] if index == 0 else ["leaf:" + "a" * 64]),
            }
            for index, (character, digest) in enumerate(zip(("a", "c"), digests))
        ]
        dictionary = dict(zip(digests, values))
        shard = _build_shard(
            run_id=RUN_ID,
            cycle_index=1,
            created_at=NOW,
            shard_index=0,
            rows=rows,
            dictionary=dictionary,
        )
        exact_limit = _shard_canonical_size_from_parts(
            run_id=RUN_ID,
            cycle_index=1,
            created_at=NOW,
            shard_index=0,
            member_count=len(rows),
            member_row_bytes=sum(len(canonical_bytes(row)) for row in rows),
            member_id_bytes=sum(
                len(canonical_bytes(row["member_id"])) for row in rows
            ),
            dictionary_entry_count=len(dictionary),
            dictionary_entry_bytes=sum(
                len(
                    canonical_bytes(
                        {"value_digest": digest, "value": dictionary[digest]}
                    )
                )
                for digest in dictionary
            ),
            dependency_closure_complete=True,
        )
        self.assertEqual(exact_limit, len(canonical_bytes(shard)))
        self.assertTrue(
            _fits_shard_limit(
                estimated_canonical_bytes=exact_limit,
                shard_limit=exact_limit,
            )
        )
        self.assertFalse(
            _fits_shard_limit(
                estimated_canonical_bytes=exact_limit,
                shard_limit=exact_limit - 1,
            )
        )

    def test_repeated_identifier_dependencies_are_linear_not_quadratic(self) -> None:
        repeated_count = 128
        original = self_digest(
            {
                "schema_id": "test_v32_repeated_identifier_original_v1",
                "schema_version": "1.0.0",
                "run_id": RUN_ID,
                "cycle_index": 1,
                "created_at": NOW,
                "rows": [
                    {"entity_id": "shared-entity", "value": index}
                    for index in range(repeated_count)
                ],
            },
            "artifact_digest",
        )
        _, bundle = self._bundle(original, limit=262_144)
        identifier_rows = [
            row
            for shard in bundle["shards"]
            for row in shard["member_rows"]
            if row["json_pointer"].endswith("/entity_id")
        ]
        dependency_edge_count = sum(
            len(row["dependency_refs"]) for row in identifier_rows
        )
        self.assertEqual(len(identifier_rows), repeated_count)
        self.assertEqual(dependency_edge_count, repeated_count - 1)
        self.assertEqual(bundle["manifest"]["dependency_closure_count"], 1 + repeated_count + 6)

    def test_resigned_manifest_tamper_and_missing_original_fail_replay(self) -> None:
        original, bundle = self._bundle()
        tampered = copy.deepcopy(bundle["manifest"])
        tampered["source_coverage_proofs"][0]["leaf_count"] -= 1
        tampered = self_digest(tampered, MANIFEST_DIGEST_FIELD)
        with self.assertRaises(V32ContextCompactionError):
            verify_v32_context_compaction_bundle_v1(
                tampered, bundle["shards"], original_documents=[original]
            )
        with self.assertRaises(V32ContextCompactionError):
            verify_v32_context_compaction_bundle_v1(
                bundle["manifest"], bundle["shards"], original_documents=[]
            )

    def test_resigned_selection_tamper_fails_reconstruction(self) -> None:
        original, bundle = self._bundle()
        manifest = bundle["manifest"]
        selection = build_v32_context_shard_selection_v1(
            manifest=manifest,
            manifest_binding=_binding(
                manifest,
                MANIFEST_DIGEST_FIELD,
                "context-compaction/manifest.json",
            ),
            shards=bundle["shards"],
            original_documents=[original],
            caller_required_member_ids=[],
            selected_at=NOW,
            max_agent_context_canonical_bytes=262_144,
        )
        selection["policy_roots_may_be_removed_by_caller"] = True
        selection = self_digest(selection, SELECTION_DIGEST_FIELD)
        with self.assertRaises(V32ContextCompactionError):
            verify_v32_context_shard_selection_v1(
                selection,
                manifest=manifest,
                shards=bundle["shards"],
                original_documents=[original],
            )

    def test_minimum_capacity_exhausts_structural_fallback_without_truncation(self) -> None:
        original, bundle = self._bundle(_original(oversized=True), limit=2048)
        manifest = bundle["manifest"]
        self.assertEqual(manifest["status"], "CONTEXT_CAPACITY_UNRESOLVED")
        self.assertEqual(bundle["shards"], [])
        self.assertTrue(manifest["manual_escalation_required"])
        self.assertTrue(manifest["unfragmentable_original_member_ids"])
        with self.assertRaises(V32ContextCompactionError):
            build_v32_context_shard_selection_v1(
                manifest=manifest,
                manifest_binding=_binding(
                    manifest,
                    MANIFEST_DIGEST_FIELD,
                    "context-compaction/manifest.json",
                ),
                shards=[],
                original_documents=[original],
                caller_required_member_ids=[],
                selected_at=NOW,
                max_agent_context_canonical_bytes=262_144,
            )

    def test_oversized_leaf_uses_exact_canonical_byte_range_fragments(self) -> None:
        original, bundle = self._bundle(_original(oversized=True), limit=4096)
        manifest = bundle["manifest"]
        self.assertEqual(manifest["status"], "READY_LOSSLESS_SHARDED")
        self.assertEqual(manifest["fragmented_leaf_count"], 1)
        self.assertGreater(manifest["fragment_member_count"], 1)
        self.assertTrue(manifest["exact_fragment_reassembly_verified"])
        self.assertEqual(manifest["unfragmentable_original_member_ids"], [])
        self.assertTrue(
            all(len(canonical_bytes(shard)) <= 4096 for shard in bundle["shards"])
        )
        self.assertEqual(
            verify_v32_context_compaction_bundle_v1(
                manifest, bundle["shards"], original_documents=[original]
            ),
            manifest[MANIFEST_DIGEST_FIELD],
        )

    def test_policy_is_exact_and_self_digested(self) -> None:
        policy = build_v32_context_compaction_policy_v1(
            policy_id="context-policy",
            run_scope_id=RUN_ID,
            frozen_at=NOW,
        )
        self.assertEqual(
            verify_v32_context_compaction_policy_v1(policy),
            policy["context_compaction_policy_digest"],
        )
        policy["top_k_or_truncation_allowed"] = True
        policy = self_digest(policy, "context_compaction_policy_digest")
        with self.assertRaises(V32ContextCompactionError):
            verify_v32_context_compaction_policy_v1(policy)


if __name__ == "__main__":
    unittest.main()
