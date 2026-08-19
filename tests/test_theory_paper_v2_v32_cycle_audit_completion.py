from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.v32_cycle_acceptance import (
    DIGEST_FIELD as ACCEPTANCE_DIGEST_FIELD,
    SCHEMA_ID as ACCEPTANCE_SCHEMA_ID,
)
from trade_system.theory_paper_v2.application.v32_cycle_audit_completion import (
    DIGEST_FIELD,
    V32CycleAuditCompletionError,
    build_v32_cycle_audit_completion_receipt_v1,
    verify_v32_cycle_audit_completion_receipt_v1,
    verify_v32_latest_cycle_audit_gate_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    DIRECTORY_DIGEST_FIELD,
    DIRECTORY_SCHEMA_ID,
    REQUIRED_SECTION_IDS,
    SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID,
    build_v32_cycle_audit_narrative_bundle_v1,
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    build_v32_tick_supervisor_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_audit_completion_store import (
    LocalV32CycleAuditCompletionStore,
)


RUN_ID = "v32-audit-completion-test"


def _physical(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document) + b"\n").hexdigest()


def _binding(
    relative_ref: str, document: dict, schema_id: str, digest_field: str
) -> dict[str, str]:
    return {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": _physical(document),
    }


def _fixture() -> dict:
    acceptance = self_digest(
        {
            "schema_id": ACCEPTANCE_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "accepted_at": "2026-08-08T00:00:10Z",
            "acceptance_status": (
                "ACCEPTED_SINGLE_ANALYSIS_CYCLE_WRITE_ONCE_REQUIRED"
            ),
        },
        ACCEPTANCE_DIGEST_FIELD,
    )
    acceptance_binding = _binding(
        "cycles/0001/acceptance.json",
        acceptance,
        ACCEPTANCE_SCHEMA_ID,
        ACCEPTANCE_DIGEST_FIELD,
    )
    policy = build_v32_cycle_audit_policy_v1(
        policy_id="v32-audit-policy",
        run_scope_id=RUN_ID,
        frozen_at="2026-08-07T23:59:00Z",
    )
    sections = [
        {
            "section_id": section_id,
            "title_zh": f"审查章节{index}",
            "content_zh": f"第{index}节记录已封存事实、未知限制与对应依据。",
            "source_bindings": [acceptance_binding],
        }
        for index, section_id in enumerate(REQUIRED_SECTION_IDS, start=1)
    ]
    bundle = build_v32_cycle_audit_narrative_bundle_v1(
        narrative_id="v32-cycle-1-audit",
        run_id=RUN_ID,
        cycle_index=1,
        boundary_type="ACCEPTANCE",
        generated_at="2026-08-08T00:00:11Z",
        sections=sections,
    )
    directory_binding = _binding(
        "cycles/0001/audit/directory.json",
        bundle["directory"],
        DIRECTORY_SCHEMA_ID,
        DIRECTORY_DIGEST_FIELD,
    )
    shard_bindings = [
        _binding(
            f"cycles/0001/audit/shards/{index:04d}.json",
            shard,
            SHARD_SCHEMA_ID,
            SHARD_DIGEST_FIELD,
        )
        for index, shard in enumerate(bundle["shards"])
    ]
    completion = build_v32_cycle_audit_completion_receipt_v1(
        completion_id="v32-cycle-1-audit-completion",
        cycle_audit_policy=policy,
        analysis_acceptance=acceptance,
        analysis_acceptance_binding=acceptance_binding,
        narrative_directory=bundle["directory"],
        narrative_directory_binding=directory_binding,
        narrative_shards=bundle["shards"],
        narrative_shard_bindings=shard_bindings,
        completed_at="2026-08-08T00:00:12Z",
    )
    return {
        "acceptance": acceptance,
        "policy": policy,
        "bundle": bundle,
        "completion": completion,
    }


class V32CycleAuditCompletionTests(unittest.TestCase):
    def test_full_post_acceptance_replay_and_write_once_store(self) -> None:
        fixture = _fixture()
        completion = fixture["completion"]
        self.assertEqual(
            completion[DIGEST_FIELD],
            verify_v32_cycle_audit_completion_receipt_v1(
                completion,
                cycle_audit_policy=fixture["policy"],
                analysis_acceptance=fixture["acceptance"],
                narrative_directory=fixture["bundle"]["directory"],
                narrative_shards=fixture["bundle"]["shards"],
            ),
        )
        self.assertFalse(completion["narrative_is_authority"])
        self.assertTrue(completion["typed_acceptance_remains_authoritative"])
        with tempfile.TemporaryDirectory() as directory:
            store = LocalV32CycleAuditCompletionStore(Path(directory))
            first = store.persist_completion(
                completion=completion,
                cycle_audit_policy=fixture["policy"],
                analysis_acceptance=fixture["acceptance"],
                narrative_directory=fixture["bundle"]["directory"],
                narrative_shards=fixture["bundle"]["shards"],
            )
            second = store.persist_completion(
                completion=completion,
                cycle_audit_policy=fixture["policy"],
                analysis_acceptance=fixture["acceptance"],
                narrative_directory=fixture["bundle"]["directory"],
                narrative_shards=fixture["bundle"]["shards"],
            )
            self.assertEqual(first, second)
            self.assertEqual(
                completion,
                store.load_completion(run_id=RUN_ID, cycle_index=1),
            )

    def test_narrative_must_be_generated_after_acceptance_and_bind_it(self) -> None:
        fixture = _fixture()
        directory = deepcopy(fixture["bundle"]["directory"])
        directory["generated_at"] = "2026-08-08T00:00:09Z"
        directory = self_digest(directory, DIRECTORY_DIGEST_FIELD)
        with self.assertRaises(V32CycleAuditCompletionError):
            build_v32_cycle_audit_completion_receipt_v1(
                completion_id="bad",
                cycle_audit_policy=fixture["policy"],
                analysis_acceptance=fixture["acceptance"],
                analysis_acceptance_binding=fixture["completion"][
                    "analysis_acceptance_binding"
                ],
                narrative_directory=directory,
                narrative_directory_binding=fixture["completion"][
                    "narrative_directory_binding"
                ],
                narrative_shards=fixture["bundle"]["shards"],
                narrative_shard_bindings=fixture["completion"][
                    "narrative_shard_bindings"
                ],
                completed_at="2026-08-08T00:00:12Z",
            )

    def test_genesis_audit_gate_accepts_exactly_no_prior_completion(self) -> None:
        checkpoint = build_v32_tick_supervisor_checkpoint(
            run_id=RUN_ID,
            experiment_contract_digest="1" * 64,
            active_authority_digest="2" * 64,
            research_checkpoint_digest="3" * 64,
            outcome_checkpoint_digest="4" * 64,
            timeframe_cache_digest="5" * 64,
            created_at="2026-08-08T00:00:00Z",
        )
        self.assertIsNone(
            verify_v32_latest_cycle_audit_gate_v1(
                supervisor_checkpoint=checkpoint,
                latest_audit_completion=None,
            )
        )
        with self.assertRaisesRegex(
            V32CycleAuditCompletionError, "GENESIS_COMPLETION_FORBIDDEN"
        ):
            verify_v32_latest_cycle_audit_gate_v1(
                supervisor_checkpoint=checkpoint,
                latest_audit_completion=_fixture()["completion"],
            )


if __name__ == "__main__":
    unittest.main()
