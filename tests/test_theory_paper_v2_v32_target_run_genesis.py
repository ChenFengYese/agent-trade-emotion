from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.test_theory_paper_v2_v32_current_research_authority import (
    LOADER_MODULE,
    TARGET_RUN,
    build_fixture,
    fixture_capability_verifiers,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    self_digest,
    write_once_json,
)
from trade_system.theory_paper_v2.domain.v32_run_genesis import (
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_SCHEMA_ID,
    V32RunGenesisError,
    build_v32_current_run_pointer_v1,
    verify_v32_revision_zero_checkpoints_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_current_research import (
    load_v32_current_research_authority,
)
from trade_system.theory_paper_v2.infrastructure.v32_run_control_store import (
    CONTROL_ROOT_RELATIVE,
    CURRENT_RUN_POINTER_REF,
    LocalV32RunControlStore,
)
from trade_system.theory_paper_v2.presentation import (
    v32_target_run_composition as composition,
)


class RecordingSystemClock:
    adapter_id = "TEST_SYSTEM_UTC_MONOTONIC_CLOCK_V1"

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return "2026-08-08T10:00:00Z"


class V32TargetRunGenesisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = build_fixture(self.root)
        with patch(
            f"{LOADER_MODULE}.load_v31_active_authorization_chain",
            return_value=self.fixture["legacy_chain"],
        ), patch(
            f"{LOADER_MODULE}.load_v311_legacy_failure_evidence_v2",
            return_value=self.fixture["legacy_failure"],
        ):
            self.projection = load_v32_current_research_authority(
                self.root,
                expected_run_id=TARGET_RUN,
                capability_verifiers=fixture_capability_verifiers(),
            )
        self.clock = RecordingSystemClock()

    def _compose(self):
        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=self.projection,
        ) as loader, patch.object(
            composition,
            "build_v32_system_clock_v1",
            return_value=self.clock,
        ):
            result = composition.initialize_v32_target_run_from_current_authority_v1(
                project_root=self.root,
                expected_run_id=TARGET_RUN,
            )
        loader.assert_called_once_with(
            self.root,
            expected_run_id=TARGET_RUN,
            capability_verifiers=(
                composition.build_v32_actual_capability_full_replay_registry()
            ),
        )
        return result

    def test_full_loader_system_clock_and_exact_copies_publish_blocked_genesis(self):
        result = self._compose()
        self.assertEqual("GENESIS_CREATED", result["composition_status"])
        self.assertEqual(
            "GENESIS_SEALED_AWAITING_QUALIFICATION_AUDIT",
            result["runtime_status"],
        )
        self.assertEqual(
            "BLOCKED_PENDING_QUALIFICATION_BOUNDARY_AUDIT",
            result["first_analysis_permit_status"],
        )
        self.assertEqual(1, self.clock.calls)
        timeframe = result["initial_timeframe_entity"]
        self.assertEqual(
            "UNINITIALIZED_PENDING_FIRST_FORMAL_SOURCE", timeframe["state"]
        )
        self.assertEqual(1, timeframe["cycle_index"])
        self.assertFalse(timeframe["market_data_present"])
        self.assertFalse(timeframe["market_values_present"])
        self.assertFalse(timeframe["market_payload_digest_present"])
        self.assertNotIn("frames", timeframe)
        self.assertNotIn("payload_digest", timeframe)
        self.assertEqual(
            {"qualification_retirement", "target_authority", "run_genesis"},
            set(result["qualification_audit_source_bindings"]),
        )
        receipt = result["run_genesis"]
        self.assertEqual(RUN_GENESIS_SCHEMA_ID, receipt["schema_id"])
        self.assertEqual(16, receipt["experiment_scope"]["analysis_cycles"])
        self.assertEqual(48, receipt["experiment_scope"]["outcome_schedules"])
        self.assertTrue(
            receipt["qualification_boundary_audit_gate"][
                "typed_completion_required_before_first_analysis_permit"
            ]
        )
        self.assertEqual(
            "REQUIRED_NOT_COMPLETED",
            receipt["qualification_boundary_audit_gate"]["status_at_genesis"],
        )
        run_root = Path(result["run_root"])
        for row in receipt["authority_projection_copies"]:
            self.assertEqual(
                (self.root / row["source_ref"]).read_bytes(),
                (run_root / row["local_ref"]).read_bytes(),
            )
            self.assertEqual(
                row["source_physical_sha256"], row["local_physical_sha256"]
            )

    def test_public_signature_rejects_docs_digests_time_and_timeframe_injection(self):
        parameters = set(
            inspect.signature(
                composition.initialize_v32_target_run_from_current_authority_v1
            ).parameters
        )
        self.assertEqual({"project_root", "expected_run_id"}, parameters)
        forbidden = {
            "authority_documents": self.projection,
            "active_authority_digest": "a" * 64,
            "created_at": "2026-08-08T10:00:00Z",
            "clock": self.clock,
            "initial_timeframe_entity": {"fake": True},
            "initial_timeframe_cache_digest": "f" * 64,
        }
        for name, value in forbidden.items():
            with self.subTest(name=name), self.assertRaises(TypeError):
                composition.initialize_v32_target_run_from_current_authority_v1(
                    project_root=self.root,
                    expected_run_id=TARGET_RUN,
                    **{name: value},
                )

    def test_fake_five_document_projection_fails_before_runtime_write(self):
        fake = {
            role: {
                "schema_id": "fake",
                "fake_digest": "a" * 64,
            }
            for role in (
                "theory_approval",
                "experiment_contract",
                "manifest",
                "authorization_receipt",
                "authority",
            )
        }
        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=fake,
        ), patch.object(
            composition,
            "build_v32_system_clock_v1",
            return_value=self.clock,
        ):
            with self.assertRaises(composition.V32TargetRunCompositionError):
                composition.initialize_v32_target_run_from_current_authority_v1(
                    project_root=self.root,
                    expected_run_id=TARGET_RUN,
                )
        self.assertFalse((self.root / CONTROL_ROOT_RELATIVE).exists())

    def test_wrong_revision_zero_checkpoint_cross_binding_is_rejected(self):
        result = self._compose()
        checkpoints = deepcopy(result["revision_zero_checkpoints"])
        supervisor = deepcopy(checkpoints["supervisor"])
        supervisor["current_timeframe_cache_digest"] = "f" * 64
        checkpoints["supervisor"] = self_digest(
            supervisor, "tick_supervisor_checkpoint_digest"
        )
        with self.assertRaises(V32RunGenesisError):
            verify_v32_revision_zero_checkpoints_v1(
                checkpoints=checkpoints,
                run_id=TARGET_RUN,
                experiment_contract_digest=result["run_genesis"][
                    "cross_bindings"
                ]["experiment_contract_digest"],
                active_authority_digest=result["run_genesis"]["cross_bindings"][
                    "active_authority_digest"
                ],
                initial_timeframe_digest=result["run_genesis"]["cross_bindings"][
                    "initial_timeframe_digest"
                ],
                created_at=result["run_genesis"]["created_at"],
            )

    def test_partial_immutable_write_never_publishes_and_reentry_recovers(self):
        def crash_after_manifest(_store, *, role: str, relative_ref: str) -> None:
            if role == "manifest":
                raise RuntimeError(f"simulated-crash:{relative_ref}")

        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=self.projection,
        ), patch.object(
            composition,
            "build_v32_system_clock_v1",
            return_value=self.clock,
        ), patch.object(
            LocalV32RunControlStore,
            "_after_immutable_write",
            crash_after_manifest,
        ):
            with self.assertRaises(RuntimeError):
                composition.initialize_v32_target_run_from_current_authority_v1(
                    project_root=self.root,
                    expected_run_id=TARGET_RUN,
                )
        pointer = self.root / CONTROL_ROOT_RELATIVE / CURRENT_RUN_POINTER_REF
        self.assertFalse(pointer.exists())
        result = self._compose()
        self.assertEqual("GENESIS_CREATED", result["composition_status"])
        self.assertTrue(pointer.is_file())
        self.assertTrue(result["system_clock_timestamp_reused"])

    def test_old_or_second_active_pointer_conflicts_before_target_run_write(self):
        store = LocalV32RunControlStore(self.root)
        fake_genesis_binding = {
            "relative_ref": "runs/v31-old-run/genesis/run-genesis.json",
            "schema_id": RUN_GENESIS_SCHEMA_ID,
            "digest_field": RUN_GENESIS_DIGEST_FIELD,
            "semantic_digest": "a" * 64,
            "physical_sha256": "b" * 64,
        }
        pointer = build_v32_current_run_pointer_v1(
            published_at="2026-08-08T09:00:00Z",
            run_id="v31-old-run",
            run_genesis_binding=fake_genesis_binding,
            experiment_contract_digest="c" * 64,
            active_authority_digest="d" * 64,
        )
        write_once_json(
            store.control_root / CURRENT_RUN_POINTER_REF,
            pointer,
        )
        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=self.projection,
        ), patch.object(
            composition,
            "build_v32_system_clock_v1",
            return_value=self.clock,
        ):
            with self.assertRaises(composition.V32TargetRunCompositionError):
                composition.initialize_v32_target_run_from_current_authority_v1(
                    project_root=self.root,
                    expected_run_id=TARGET_RUN,
                )
        target_root = store.control_root / "runs" / TARGET_RUN
        self.assertFalse(target_root.exists())

    def test_identical_reentry_is_read_only_and_does_not_read_wall_time_again(self):
        first = self._compose()
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in (self.root / CONTROL_ROOT_RELATIVE).rglob("*")
            if path.is_file() and ".locks" not in path.parts
        }
        second = self._compose()
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in (self.root / CONTROL_ROOT_RELATIVE).rglob("*")
            if path.is_file() and ".locks" not in path.parts
        }
        self.assertEqual("GENESIS_REPLAYED", second["composition_status"])
        self.assertEqual("EXISTING_IDENTICAL", second["publication_status"])
        self.assertEqual(
            first["run_genesis"][RUN_GENESIS_DIGEST_FIELD],
            second["run_genesis"][RUN_GENESIS_DIGEST_FIELD],
        )
        self.assertEqual(before, after)
        self.assertEqual(1, self.clock.calls)


if __name__ == "__main__":
    unittest.main()
