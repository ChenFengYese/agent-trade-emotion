from __future__ import annotations

import copy
from inspect import signature
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.v31_successor_probe_runner_v2 import (
    RUNNER_MODULE_PATH,
    run_successor_qualification_probes_v2,
)
from trade_system.theory_paper_v2.domain.governance.v31_successor_probe_evidence_v2 import (
    PROBE_CASE_DIGEST_FIELD,
    verify_executed_probe_case_receipt_v2,
    verify_executed_probe_family_evidence_v2,
    verify_persisted_probe_receipt_v2,
    verify_probe_runtime_closure_evidence_v2,
)
from trade_system.theory_paper_v2.domain.governance.v31_successor_qualification_v2 import (
    RAW_FIRST_FAILURE_CASES,
    SUPERVISOR_GATE_CASES,
    verify_raw_first_failure_probe_v2,
    verify_supervisor_gate_probe_v2,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_runtime_closure_v2 import (
    V31RuntimeClosureError,
    build_v31_runtime_closure_bindings_v2,
    collect_v31_static_runtime_closure_v2,
)
from trade_system.theory_paper_v2.infrastructure.v31_successor_probe_store_v2 import (
    PERSISTED_RECEIPT_REF,
    V31SuccessorProbeStoreV2Error,
    execute_and_persist_successor_qualification_probes_v2,
    load_persisted_successor_qualification_probes_v2,
    persist_successor_qualification_probes_v2,
)


EXECUTED_AT = "2026-08-07T08:00:00Z"
STORE_MODULE_PATH = (
    "trade_system/theory_paper_v2/infrastructure/v31_successor_probe_store_v2.py"
)


class V31SuccessorProbeRunnerV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[1]
        cls.production_roots = (STORE_MODULE_PATH,)
        cls.trace_paths = collect_v31_static_runtime_closure_v2(
            project_root=cls.project_root,
            production_root_paths=cls.production_roots,
        )
        cls.bindings = build_v31_runtime_closure_bindings_v2(
            project_root=cls.project_root,
            production_root_paths=cls.production_roots,
            trace_paths=cls.trace_paths,
        )
        cls.result = run_successor_qualification_probes_v2(
            project_root=cls.project_root,
            executed_at=EXECUTED_AT,
            production_root_paths=cls.production_roots,
            trace_paths=cls.trace_paths,
            runtime_closure_bindings=cls.bindings,
        )

    def raw(self, case_id: str) -> dict:
        return next(
            row
            for row in self.result["raw_first_case_receipts"]
            if row["case_id"] == case_id
        )

    def supervisor(self, case_id: str) -> dict:
        return next(
            row
            for row in self.result["supervisor_case_receipts"]
            if row["case_id"] == case_id
        )

    def test_public_runner_has_no_pass_or_case_result_input(self) -> None:
        parameters = signature(run_successor_qualification_probes_v2).parameters
        self.assertNotIn("case_results", parameters)
        self.assertNotIn("status", parameters)
        self.assertNotIn("passed", parameters)
        self.assertEqual(
            {
                "project_root",
                "executed_at",
                "production_root_paths",
                "trace_paths",
                "runtime_closure_bindings",
                "clock_policy",
            },
            set(parameters),
        )
        self.assertFalse(self.result["network_access_performed"])
        self.assertFalse(self.result["real_run_created"])
        self.assertFalse(self.result["automation_created"])
        self.assertFalse(self.result["executable"])
        self.assertEqual("NONE_LOCAL_SIMULATION", self.result["external_execution_authority"])

    def test_all_case_and_family_documents_reconstruct(self) -> None:
        verify_probe_runtime_closure_evidence_v2(
            self.result["runtime_closure_evidence"]
        )
        self.assertEqual(
            RAW_FIRST_FAILURE_CASES,
            tuple(sorted(row["case_id"] for row in self.result["raw_first_case_receipts"])),
        )
        self.assertEqual(
            SUPERVISOR_GATE_CASES,
            tuple(sorted(row["case_id"] for row in self.result["supervisor_case_receipts"])),
        )
        for receipt in (
            *self.result["raw_first_case_receipts"],
            *self.result["supervisor_case_receipts"],
        ):
            self.assertEqual(
                receipt[PROBE_CASE_DIGEST_FIELD],
                verify_executed_probe_case_receipt_v2(receipt),
            )
            self.assertEqual("PASS_FROM_EXECUTED_OBSERVATION", receipt["result"])
            self.assertFalse(receipt["caller_supplied_pass_accepted"])
            self.assertIn(RUNNER_MODULE_PATH, receipt["tested_module_bindings"])
        verify_raw_first_failure_probe_v2(self.result["raw_first_probe"])
        verify_supervisor_gate_probe_v2(self.result["supervisor_probe"])
        verify_executed_probe_family_evidence_v2(
            self.result["raw_first_family_evidence"],
            case_receipts=self.result["raw_first_case_receipts"],
            aggregate_probe=self.result["raw_first_probe"],
        )
        verify_executed_probe_family_evidence_v2(
            self.result["supervisor_family_evidence"],
            case_receipts=self.result["supervisor_case_receipts"],
            aggregate_probe=self.result["supervisor_probe"],
        )

    def test_raw_first_receipts_cover_required_failure_injections(self) -> None:
        attempt = self.raw("ATTEMPT_ONLY_CRASH_FAILS_CLOSED_WITHOUT_REFETCH")[
            "observation"
        ]
        self.assertEqual(1, attempt["transport_get_count"])
        self.assertEqual(0, attempt["second_get_count"])
        self.assertEqual("FAILED_CLOSED", attempt["evidence_status"])

        clock = self.raw("CLOCK_POLICY_DRIFT_REJECTED_BEFORE_PARSE")["observation"]
        self.assertEqual(0, clock["transport_get_count_before_rejection"])
        self.assertEqual(0, clock["attempt_count_before_rejection"])
        self.assertEqual(
            {
                "provider_lead_plus_2000_ms": "ADMITTED_OBSERVED",
                "provider_lead_plus_2001_ms": "ADMITTED_UNKNOWN",
                "provider_lag_minus_5000_ms": "ADMITTED_OBSERVED",
                "provider_lag_minus_5001_ms": "ADMITTED_UNKNOWN",
            },
            clock["boundary_parse_statuses"],
        )

        capture = self.raw(
            "CRASH_AFTER_CAPTURE_RECOVERS_LOCALLY_WITHOUT_REFETCH"
        )["observation"]
        self.assertTrue(capture["raw_exists_before_parse"])
        self.assertTrue(capture["record_exists_before_parse"])
        self.assertTrue(capture["raw_matches_before_parse"])
        self.assertEqual(1, capture["transport_get_count"])
        self.assertEqual(0, capture["recovery_get_count"])

        invalid = self.raw("INVALID_JSON_RAW_PRESERVED_BEFORE_PARSE_FAILURE")[
            "observation"
        ]
        self.assertTrue(invalid["raw_persisted_before_rejection"])
        self.assertEqual("REJECTED", invalid["parse_status"])
        self.assertEqual("PUBLIC_JSON_INVALID", invalid["parse_error_code"])
        self.assertEqual(
            "V31_EVIDENCE_PARSE_SEQUENCE_INVALID",
            invalid["failed_checkpoint_parse_append_exception"],
        )
        self.assertTrue(invalid["parse_receipt_absent_after_failed_append"])

        tamper = self.raw("RAW_TAMPER_BLOCKS_REPLAY")["observation"]
        self.assertFalse(tamper["replay_admitted"])
        self.assertEqual(
            "V31_EVIDENCE_CAPTURE_BINDING_INVALID", tamper["replay_exception"]
        )

        transport = self.raw(
            "TRANSPORT_FAILURE_CRASH_BINDS_FAILURE_WITHOUT_REFETCH"
        )["observation"]
        self.assertTrue(transport["transport_receipt_durable_before_crash"])
        self.assertEqual(1, transport["failure_transport_get_count"])
        self.assertEqual(0, transport["failure_recovery_get_count"])
        self.assertEqual(1, transport["concurrent_transport_get_count"])
        self.assertEqual(2, transport["concurrent_worker_count"])
        self.assertEqual([], transport["concurrent_errors"])

    def test_supervisor_receipts_cover_commit_failure_stale_and_outcome_gates(self) -> None:
        commit = self.supervisor("COMMIT_INTENT_PRECEDES_ACCEPTED_STATE")[
            "observation"
        ]
        self.assertEqual("COMMIT_RESERVED", commit["status_before_owner_commit"])
        self.assertEqual(0, commit["research_completed_before_intent"])
        self.assertFalse(commit["agent_reinvocation_allowed"])
        self.assertTrue(commit["fresh_store_recovery_used"])
        self.assertEqual("AWAITING_OUTCOME", commit["status_after_recovery"])

        failed = self.supervisor("FAILED_MONITOR_BLOCKS_NEW_CYCLE")["observation"]
        self.assertEqual("FAILED_CLOSED", failed["supervisor_status"])
        self.assertFalse(failed["resume_allowed"])

        stale = self.supervisor("ONE_STATE_CHANGE_BOUNDARY_PER_WAKE")["observation"]
        self.assertEqual("V31_SUPERVISOR_V2_PERMIT_STALE", stale["stale_permit_exception"])
        self.assertTrue(stale["supervisor_checkpoint_unchanged_by_stale_rejection"])
        self.assertFalse(stale["commit_intent_created"])

        outcome = self.supervisor(
            "PREVIOUS_DURABLE_OUTCOME_REQUIRED_FOR_NEXT_CYCLE"
        )["observation"]
        self.assertEqual(
            "V31_SUPERVISOR_V2_PRIOR_OUTCOME_MISSING",
            outcome["missing_outcome_exception"],
        )
        self.assertEqual(
            "V31_SUPERVISOR_V2_RESERVED_ATTEMPT_WITHOUT_OUTCOME",
            outcome["reserved_attempt_exception"],
        )
        self.assertEqual(2, outcome["next_cycle_index_after_durable_unknown"])
        self.assertEqual(
            outcome["durable_unknown_outcome_digest"],
            outcome["next_permit_previous_outcome_digest"],
        )

    def test_runtime_closure_drift_is_rejected_before_probe_execution(self) -> None:
        drifted = dict(self.bindings)
        drifted[RUNNER_MODULE_PATH] = "0" * 64
        with self.assertRaisesRegex(
            V31RuntimeClosureError, "V31_RUNTIME_CLOSURE_PHYSICAL_DRIFT"
        ):
            run_successor_qualification_probes_v2(
                project_root=self.project_root,
                executed_at=EXECUTED_AT,
                production_root_paths=self.production_roots,
                trace_paths=self.trace_paths,
                runtime_closure_bindings=drifted,
            )

    def test_write_once_persistence_replays_and_physical_tamper_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persisted = persist_successor_qualification_probes_v2(
                output_root=root, result=self.result
            )
            verify_persisted_probe_receipt_v2(persisted["receipt"])
            self.assertEqual(17, len(tuple(root.rglob("*.json"))))
            replayed = load_persisted_successor_qualification_probes_v2(
                output_root=root
            )
            self.assertEqual(
                persisted["receipt"]["persisted_probe_receipt_digest"],
                replayed["receipt"]["persisted_probe_receipt_digest"],
            )
            self.assertTrue((root / PERSISTED_RECEIPT_REF).is_file())
            case_ref = persisted["receipt"]["artifact_bindings"]["raw_first_cases"][
                RAW_FIRST_FAILURE_CASES[0]
            ]["relative_ref"]
            case_path = root / case_ref
            case_path.write_bytes(case_path.read_bytes() + b" ")
            with self.assertRaises(V31SuccessorProbeStoreV2Error):
                load_persisted_successor_qualification_probes_v2(output_root=root)

    def test_cli_like_composition_executes_and_persists_without_run_or_automation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            persisted = execute_and_persist_successor_qualification_probes_v2(
                project_root=self.project_root,
                output_root=Path(directory),
                executed_at=EXECUTED_AT,
                production_root_paths=self.production_roots,
                trace_paths=self.trace_paths,
                runtime_closure_bindings=self.bindings,
            )
            self.assertEqual(
                "TEN_EXECUTED_CASE_RECEIPTS_PERSISTED",
                persisted["receipt"]["result"],
            )
            self.assertFalse(persisted["network_access_performed"])
            self.assertFalse(persisted["real_run_created"])
            self.assertFalse(persisted["automation_created"])

    def test_resigned_case_observation_drift_breaks_family_cross_binding(self) -> None:
        result = copy.deepcopy(self.result)
        result["raw_first_case_receipts"][0]["observation"][
            "transport_get_count"
        ] = 2
        with self.assertRaises(V31SuccessorProbeStoreV2Error):
            with tempfile.TemporaryDirectory() as directory:
                persist_successor_qualification_probes_v2(
                    output_root=Path(directory), result=result
                )


if __name__ == "__main__":
    unittest.main()
