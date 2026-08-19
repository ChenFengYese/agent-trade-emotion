from __future__ import annotations

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
from trade_system.theory_paper_v2.application.v32_prospective_runtime import (
    route_v32_prospective_wake_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import load_json_strict
from trade_system.theory_paper_v2.infrastructure.authority.v32_current_research import (
    load_v32_current_research_authority,
)
from trade_system.theory_paper_v2.infrastructure.v32_authorized_revision_store import (
    LocalV32AuthorizedRevisionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_audit_completion_store import (
    LocalV32CycleAuditCompletionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_dynamic_store import (
    LocalV32DynamicStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_local_audit_lane import (
    LocalV32BoundaryAuditLane,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_run_control_store import (
    CONTROL_ROOT_RELATIVE,
    CURRENT_RUN_POINTER_REF,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)
from trade_system.theory_paper_v2.presentation import (
    v32_target_run_composition as composition,
)


class RecordingClock:
    adapter_id = "TEST_SYSTEM_UTC_MONOTONIC_CLOCK_V1"

    def __init__(self, value: str) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.value


class EmptyMailbox:
    def next_pending_request(self, *, run_id, cycle_index):
        return None


class NoopAnalysisPort:
    def load_durable_prepared_source(
        self, *, run_id, cycle_index, supervisor_checkpoint
    ):
        del supervisor_checkpoint
        return {
            "run_id": run_id,
            "cycle_index": cycle_index,
            "source_cutoff_at": "2026-08-08T10:01:00Z",
            "admitted_at": "2026-08-08T10:01:10Z",
            "replayed_at": "2026-08-08T10:01:20Z",
            "source_qualification_digest": "1" * 64,
            "source_admission_digest": "2" * 64,
            "durable_source_replay_receipt_digest": "3" * 64,
        }

    def prepare_cycle_source(self, **_kwargs):
        raise AssertionError("durable prepared source must be consumed")

    def load_durable_analysis_completion(self, *, permit):
        return None

    def load_durable_analysis_failure(self, *, permit):
        return None


class RecordingWakeRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "runtime_status": "PENDING",
            "boundary_kind": "ANALYSIS_GATE_ADMITTED_NO_TEST_PERMIT",
            "high_level_boundaries_completed_this_wake": 0,
            "durable_state_boundaries_this_wake": 0,
        }


class V32CycleZeroQualificationAuditTests(unittest.TestCase):
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
        self.genesis_clock = RecordingClock("2026-08-08T10:00:00Z")
        self.audit_clock = RecordingClock("2026-08-08T10:01:00Z")

    def _initialize(self):
        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=self.projection,
        ), patch.object(
            composition,
            "build_v32_system_clock_v1",
            return_value=self.genesis_clock,
        ):
            return composition.initialize_v32_target_run_from_current_authority_v1(
                project_root=self.root,
                expected_run_id=TARGET_RUN,
            )

    def _audit(self, *, expected_run_id: str = TARGET_RUN):
        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=self.projection,
        ) as loader, patch.object(
            composition,
            "build_v32_system_clock_v1",
            return_value=self.audit_clock,
        ):
            result = composition.seal_v32_cycle_zero_qualification_audit_v1(
                project_root=self.root,
                expected_run_id=expected_run_id,
            )
        loader.assert_called_once_with(
            self.root,
            expected_run_id=expected_run_id,
            capability_verifiers=(
                composition.build_v32_actual_capability_full_replay_registry()
            ),
        )
        return result

    @staticmethod
    def _snapshot(paths: list[Path], root: Path) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        for supplied in paths:
            if supplied.is_dir():
                candidates = supplied.rglob("*")
            else:
                candidates = (supplied,)
            for path in candidates:
                if path.is_file():
                    result[path.relative_to(root).as_posix()] = path.read_bytes()
        return result

    def _cycle_audit_policy(self):
        binding = self.fixture["revision_component_bindings"][
            "cycle_audit_policy"
        ]
        return load_json_strict(self.root / binding["relative_ref"])

    def _route_with_real_qualification_store(self, *, run_root: Path):
        revision_store = LocalV32AuthorizedRevisionStore(run_root)
        completion_store = LocalV32CycleAuditCompletionStore(run_root)
        audit_lane = LocalV32BoundaryAuditLane(
            revision_store=revision_store,
            acceptance_completion_store=completion_store,
            clock=RecordingClock("2026-08-08T10:02:00Z"),
        )
        runner = RecordingWakeRunner()
        result = route_v32_prospective_wake_v1(
            supervisor_store=LocalV32TickSupervisorStore(run_root),
            dynamic_store=LocalV32DynamicStore(run_root),
            outcome_store=LocalV32OutcomeTickStore(run_root),
            mailbox=EmptyMailbox(),
            revision_store=revision_store,
            audit_completion_store=completion_store,
            audit_lane=audit_lane,
            analysis_port=NoopAnalysisPort(),
            outcome_port=object(),
            cycle_audit_policy=self._cycle_audit_policy(),
            run_id=TARGET_RUN,
            clock=RecordingClock("2026-08-08T10:02:00Z"),
            wake_runner=runner,
        )
        return result, runner

    def test_router_blocks_before_audit_then_allows_analysis_gate_only(self):
        genesis = self._initialize()
        run_root = Path(genesis["run_root"])
        with self.assertRaisesRegex(
            ValueError,
            "V32_RUNTIME_QUALIFICATION_AUDIT_REQUIRED_BEFORE_ANALYSIS",
        ):
            self._route_with_real_qualification_store(run_root=run_root)

        before = self._snapshot(
            [
                self.root / CONTROL_ROOT_RELATIVE / CURRENT_RUN_POINTER_REF,
                run_root / "genesis",
            ],
            self.root,
        )
        first = self._audit()
        second = self._audit()
        after = self._snapshot(
            [
                self.root / CONTROL_ROOT_RELATIVE / CURRENT_RUN_POINTER_REF,
                run_root / "genesis",
            ],
            self.root,
        )

        self.assertEqual("QUALIFICATION_AUDIT_CREATED", first["composition_status"])
        self.assertEqual(
            "QUALIFICATION_AUDIT_REPLAYED", second["composition_status"]
        )
        self.assertEqual(1, self.audit_clock.calls)
        self.assertEqual(before, after)
        self.assertTrue(first["genesis_and_pointer_unchanged"])
        self.assertFalse(first["first_analysis_permit_opened"])
        self.assertFalse(first["cycle_one_started"])
        self.assertEqual(0, first["network_request_count"])
        self.assertFalse(first["account_access"])
        self.assertFalse(first["order_submission"])
        self.assertFalse(first["executable"])

        bundle = LocalV32AuthorizedRevisionStore(run_root).load_audit_bundle(
            run_id=TARGET_RUN,
            cycle_index=0,
            boundary_type="QUALIFICATION",
        )
        self.assertIsNotNone(bundle)
        self.assertEqual(13, bundle["directory"]["section_count"])
        self.assertEqual("zh-CN", bundle["directory"]["language"])
        self.assertEqual(
            {"qualification_retirement", "target_authority", "run_genesis"},
            set(first["source_bindings"]),
        )
        admitted, runner = self._route_with_real_qualification_store(
            run_root=run_root
        )
        self.assertEqual(
            "ANALYSIS_GATE_ADMITTED_NO_TEST_PERMIT", admitted["boundary_kind"]
        )
        self.assertEqual(1, len(runner.calls))
        self.assertEqual("ANALYSIS", runner.calls[0]["lane_requests"][0]["lane"])

    def test_public_signature_forbids_docs_bindings_and_time_injection(self):
        parameters = set(
            inspect.signature(
                composition.seal_v32_cycle_zero_qualification_audit_v1
            ).parameters
        )
        self.assertEqual({"project_root", "expected_run_id"}, parameters)
        for name, value in {
            "clock": self.audit_clock,
            "generated_at": "2026-08-08T10:01:00Z",
            "boundary_sealed_at": "2026-08-08T10:00:00Z",
            "sealed_sources": [],
            "qualification_retirement": self.fixture["retirement"],
        }.items():
            with self.subTest(name=name), self.assertRaises(TypeError):
                composition.seal_v32_cycle_zero_qualification_audit_v1(
                    project_root=self.root,
                    expected_run_id=TARGET_RUN,
                    **{name: value},
                )

    def test_public_genesis_replay_is_non_creating_and_non_injectable(self):
        replay_parameters = set(
            inspect.signature(
                composition.replay_v32_target_run_from_current_authority_v1
            ).parameters
        )
        self.assertEqual({"project_root", "expected_run_id"}, replay_parameters)
        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=self.projection,
        ):
            with self.assertRaisesRegex(
                composition.V32TargetRunCompositionError,
                "PUBLISHED_GENESIS_REQUIRED",
            ):
                composition.replay_v32_target_run_from_current_authority_v1(
                    project_root=self.root,
                    expected_run_id=TARGET_RUN,
                )
        self.assertFalse((self.root / CONTROL_ROOT_RELATIVE).exists())

        self._initialize()
        before = self._snapshot(
            [self.root / CONTROL_ROOT_RELATIVE], self.root
        )
        with patch.object(
            composition,
            "load_v32_current_research_authority",
            return_value=self.projection,
        ) as loader:
            replay = composition.replay_v32_target_run_from_current_authority_v1(
                project_root=self.root,
                expected_run_id=TARGET_RUN,
            )
        after = self._snapshot(
            [self.root / CONTROL_ROOT_RELATIVE], self.root
        )
        loader.assert_called_once_with(
            self.root,
            expected_run_id=TARGET_RUN,
            capability_verifiers=(
                composition.build_v32_actual_capability_full_replay_registry()
            ),
        )
        self.assertEqual(before, after)
        self.assertEqual("GENESIS_REPLAYED_READ_ONLY", replay["composition_status"])
        self.assertEqual(self.projection, replay["authority_projection"])
        self.assertEqual(0, replay["state_mutation_count"])
        for name, value in {
            "clock": self.audit_clock,
            "authority_projection": self.projection,
            "created_at": "2026-08-08T10:00:00Z",
        }.items():
            with self.subTest(name=name), self.assertRaises(TypeError):
                composition.replay_v32_target_run_from_current_authority_v1(
                    project_root=self.root,
                    expected_run_id=TARGET_RUN,
                    **{name: value},
                )

    def test_missing_genesis_wrong_run_and_local_authority_tamper_fail_closed(self):
        with self.assertRaisesRegex(
            composition.V32TargetRunCompositionError,
            "PUBLISHED_GENESIS_REQUIRED",
        ):
            self._audit()

        genesis = self._initialize()
        run_root = Path(genesis["run_root"])
        with self.assertRaisesRegex(
            composition.V32TargetRunCompositionError,
            "RUN_SCOPE_INVALID",
        ):
            self._audit(expected_run_id="v32-wrong-target-run")
        self.assertIsNone(
            LocalV32AuthorizedRevisionStore(run_root).load_audit_bundle(
                run_id=TARGET_RUN,
                cycle_index=0,
                boundary_type="QUALIFICATION",
            )
        )

        authority_binding = genesis["qualification_audit_source_bindings"][
            "target_authority"
        ]
        authority_path = run_root / authority_binding["relative_ref"]
        authority_path.write_bytes(authority_path.read_bytes() + b" ")
        with self.assertRaises(composition.V32TargetRunCompositionError):
            self._audit()
        self.assertIsNone(
            LocalV32AuthorizedRevisionStore(run_root).load_audit_bundle(
                run_id=TARGET_RUN,
                cycle_index=0,
                boundary_type="QUALIFICATION",
            )
        )


if __name__ == "__main__":
    unittest.main()
