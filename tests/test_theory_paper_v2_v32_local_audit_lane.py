from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.v32_cycle_acceptance import (
    DIGEST_FIELD as ACCEPTANCE_DIGEST_FIELD,
    SCHEMA_ID as ACCEPTANCE_SCHEMA_ID,
)
from trade_system.theory_paper_v2.application.v32_deterministic_audit import (
    compose_v32_deterministic_boundary_audit_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_cycle_audit_narrative import (
    DIRECTORY_DIGEST_FIELD,
    build_v32_cycle_audit_policy_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_authorized_revision_store import (
    LocalV32AuthorizedRevisionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_audit_completion_store import (
    LocalV32CycleAuditCompletionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_durable_json import (
    write_once_json,
)
from trade_system.theory_paper_v2.infrastructure.v32_local_audit_lane import (
    LocalV32BoundaryAuditLane,
    V32LocalAuditLaneError,
)


RUN_ID = "v32-local-audit-lane-test"


def _binding(relative_ref: str, document: dict, digest_field: str) -> dict:
    return {
        "relative_ref": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }


def _acceptance_source() -> dict:
    acceptance = self_digest(
        {
            "schema_id": ACCEPTANCE_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "cycle_index": 1,
            "accepted_at": "2026-08-08T02:00:00Z",
            "acceptance_status": (
                "ACCEPTED_SINGLE_ANALYSIS_CYCLE_WRITE_ONCE_REQUIRED"
            ),
            "objective_unknown_count": 1,
            "selected_action": "WAIT",
            "runner_up_action": "OPEN_PROBE",
            "outcome_schedule_count": 3,
        },
        ACCEPTANCE_DIGEST_FIELD,
    )
    return {
        "role": "analysis_acceptance",
        "document": acceptance,
        "binding": _binding(
            "cycles/0001/acceptance.json",
            acceptance,
            ACCEPTANCE_DIGEST_FIELD,
        ),
    }


class _Clock:
    def __init__(self, values: list[str]) -> None:
        self.values = iter(values)

    def __call__(self) -> str:
        return next(self.values)


class V32LocalAuditLaneTests(unittest.TestCase):
    def test_acceptance_audit_and_completion_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = build_v32_cycle_audit_policy_v1(
                policy_id="audit-policy",
                run_scope_id=RUN_ID,
                frozen_at="2026-08-08T01:59:00Z",
            )
            lane = LocalV32BoundaryAuditLane(
                revision_store=LocalV32AuthorizedRevisionStore(root),
                acceptance_completion_store=LocalV32CycleAuditCompletionStore(root),
                clock=_Clock(
                    ["2026-08-08T02:00:01Z", "2026-08-08T02:00:02Z"]
                ),
            )
            arguments = dict(
                narrative_id="acceptance-audit-cycle-1",
                completion_id="acceptance-audit-completion-cycle-1",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                boundary_sealed_at="2026-08-08T02:00:00Z",
                sealed_sources=[_acceptance_source()],
                cycle_audit_policy=policy,
            )
            first = lane.advance_once(**arguments)
            second = lane.advance_once(**arguments)
            self.assertEqual("CREATED", first["audit_status"])
            self.assertEqual("EXISTING_VERIFIED", second["audit_status"])
            self.assertEqual(first["directory"], second["directory"])
            self.assertEqual(
                first["acceptance_audit_completion"],
                second["acceptance_audit_completion"],
            )
            self.assertEqual(0, first["network_request_count"])
            self.assertEqual(0, first["agent_invocation_count"])
            self.assertFalse(first["executable"])

    def test_preboundary_clock_and_wrong_completion_mode_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = build_v32_cycle_audit_policy_v1(
                policy_id="audit-policy",
                run_scope_id=RUN_ID,
                frozen_at="2026-08-08T01:59:00Z",
            )
            lane = LocalV32BoundaryAuditLane(
                revision_store=LocalV32AuthorizedRevisionStore(root),
                acceptance_completion_store=LocalV32CycleAuditCompletionStore(root),
                clock=_Clock(["2026-08-08T01:59:59Z"]),
            )
            with self.assertRaises(V32LocalAuditLaneError):
                lane.advance_once(
                    narrative_id="early",
                    completion_id="completion",
                    run_id=RUN_ID,
                    cycle_index=1,
                    boundary_type="ACCEPTANCE",
                    boundary_sealed_at="2026-08-08T02:00:00Z",
                    sealed_sources=[_acceptance_source()],
                    cycle_audit_policy=policy,
                )

            lane = LocalV32BoundaryAuditLane(
                revision_store=LocalV32AuthorizedRevisionStore(root),
                acceptance_completion_store=LocalV32CycleAuditCompletionStore(root),
                clock=_Clock(["2026-08-08T02:00:01Z"]),
            )
            with self.assertRaisesRegex(
                V32LocalAuditLaneError, "COMPLETION_ID_FORBIDDEN"
            ):
                lane.advance_once(
                    narrative_id="analysis-audit",
                    completion_id="not-allowed",
                    run_id=RUN_ID,
                    cycle_index=1,
                    boundary_type="ANALYSIS",
                    boundary_sealed_at="2026-08-08T02:00:00Z",
                    sealed_sources=[_acceptance_source()],
                    cycle_audit_policy=policy,
                )

    def test_complete_legacy_audit_replays_without_new_clock_or_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_document = self_digest(
                {
                    "schema_id": "v32_legacy_audit_source_v1",
                    "run_id": RUN_ID,
                    "cycle_index": 0,
                    "value": "sealed",
                },
                "source_digest",
            )
            sealed_sources = [
                {
                    "role": "qualification_source",
                    "document": source_document,
                    "binding": _binding(
                        "qualification/source.json",
                        source_document,
                        "source_digest",
                    ),
                }
            ]
            policy = build_v32_cycle_audit_policy_v1(
                policy_id="legacy-audit-policy",
                run_scope_id=RUN_ID,
                frozen_at="2026-08-08T00:59:00Z",
            )
            bundle = compose_v32_deterministic_boundary_audit_v1(
                narrative_id="legacy-qualification-audit",
                run_id=RUN_ID,
                cycle_index=0,
                boundary_type="QUALIFICATION",
                boundary_sealed_at="2026-08-08T01:00:00Z",
                generated_at="2026-08-08T01:01:00Z",
                sealed_sources=sealed_sources,
                max_text_part_utf8_bytes=policy["max_text_part_utf8_bytes"],
                max_shard_canonical_bytes=policy["max_shard_canonical_bytes"],
            )
            base = (
                root
                / "v32-authorized-revisions-v1"
                / RUN_ID
                / "cycles/0000/audit/qualification"
            )
            for index, shard in enumerate(bundle["shards"]):
                write_once_json(base / f"shards/{index:04d}.json", shard)
            write_once_json(
                base
                / f"{bundle['directory'][DIRECTORY_DIGEST_FIELD]}.json",
                bundle["directory"],
            )

            lane = LocalV32BoundaryAuditLane(
                revision_store=LocalV32AuthorizedRevisionStore(root),
                acceptance_completion_store=LocalV32CycleAuditCompletionStore(root),
                clock=_Clock([]),
            )
            result = lane.advance_once(
                narrative_id="legacy-qualification-audit",
                completion_id=None,
                run_id=RUN_ID,
                cycle_index=0,
                boundary_type="QUALIFICATION",
                boundary_sealed_at="2026-08-08T01:00:00Z",
                sealed_sources=sealed_sources,
                cycle_audit_policy=policy,
            )
            self.assertEqual("EXISTING_VERIFIED", result["audit_status"])
            self.assertTrue(
                result["directory_binding"]["relative_ref"].endswith(
                    f"/{bundle['directory'][DIRECTORY_DIGEST_FIELD]}.json"
                )
            )
            self.assertTrue(
                all(
                    "/shards/" in row["relative_ref"]
                    for row in result["shard_bindings"]
                )
            )

    def test_legacy_acceptance_completion_preserves_first_binding_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sealed_sources = [_acceptance_source()]
            policy = build_v32_cycle_audit_policy_v1(
                policy_id="legacy-acceptance-policy",
                run_scope_id=RUN_ID,
                frozen_at="2026-08-08T01:59:00Z",
            )
            bundle = compose_v32_deterministic_boundary_audit_v1(
                narrative_id="legacy-acceptance-audit",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                boundary_sealed_at="2026-08-08T02:00:00Z",
                generated_at="2026-08-08T02:00:01Z",
                sealed_sources=sealed_sources,
                max_text_part_utf8_bytes=policy["max_text_part_utf8_bytes"],
                max_shard_canonical_bytes=policy["max_shard_canonical_bytes"],
            )
            base = (
                root
                / "v32-authorized-revisions-v1"
                / RUN_ID
                / "cycles/0001/audit/acceptance"
            )
            for index, shard in enumerate(bundle["shards"]):
                write_once_json(base / f"shards/{index:04d}.json", shard)
            write_once_json(
                base
                / f"{bundle['directory'][DIRECTORY_DIGEST_FIELD]}.json",
                bundle["directory"],
            )
            lane = LocalV32BoundaryAuditLane(
                revision_store=LocalV32AuthorizedRevisionStore(root),
                acceptance_completion_store=LocalV32CycleAuditCompletionStore(root),
                clock=_Clock(["2026-08-08T02:00:02Z"]),
            )
            arguments = dict(
                narrative_id="legacy-acceptance-audit",
                completion_id="legacy-acceptance-completion",
                run_id=RUN_ID,
                cycle_index=1,
                boundary_type="ACCEPTANCE",
                boundary_sealed_at="2026-08-08T02:00:00Z",
                sealed_sources=sealed_sources,
                cycle_audit_policy=policy,
            )
            first = lane.advance_once(**arguments)
            second = lane.advance_once(**arguments)
            completion = first["acceptance_audit_completion"]
            self.assertEqual(completion, second["acceptance_audit_completion"])
            self.assertEqual(
                first["directory_binding"],
                completion["narrative_directory_binding"],
            )
            self.assertEqual(
                first["shard_bindings"],
                completion["narrative_shard_bindings"],
            )
            self.assertIn(
                "/shards/",
                completion["narrative_shard_bindings"][0]["relative_ref"],
            )


if __name__ == "__main__":
    unittest.main()
