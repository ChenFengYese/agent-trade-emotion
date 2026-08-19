from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from trade_system.theory_paper_v2.application.v31_successor_qualification_v2 import (
    compose_current_codex_durable_qualification_v2,
    compose_fresh_public_source_qualification_v2,
    compose_monitor_runtime_qualification_v2,
    verify_current_codex_qualification_durable_v2,
    verify_fresh_public_source_qualification_durable_v2,
    verify_monitor_qualification_durable_v2,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.governance.v31_successor_qualification_v2 import (
    CODEX_QUALIFICATION_DIGEST_FIELD,
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    RAW_FIRST_FAILURE_CASES,
    RAW_FIRST_PROBE_DIGEST_FIELD,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
    SUPERVISOR_GATE_CASES,
    SUPERVISOR_PROBE_DIGEST_FIELD,
    V31SuccessorQualificationV2Error,
    build_raw_first_failure_probe_v2,
    build_supervisor_gate_probe_v2,
    qualification_summary_v2,
    verify_successor_codex_durable_qualification_v2,
    verify_successor_monitor_qualification_v2,
    verify_successor_public_source_qualification_v2,
)
from trade_system.theory_paper_v2.domain.v31_outcome_capture_v2 import (
    build_outcome_clock_policy,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_successor_qualification_v2 import (
    V31SuccessorQualificationAuthorityV2Error,
    build_successor_qualification_authority_envelope_v2,
    load_successor_qualification_authority_input_v2,
    verify_successor_qualification_authority_envelope_v2,
)
from trade_system.theory_paper_v2.infrastructure.v31_monitor_store import (
    LocalV31MonitorStore,
)


PROJECT = Path(__file__).resolve().parents[1]
SOURCE_QUALIFICATION_ID = (
    "v31-source-qualification-formal-cycle1-20260806t185222z"
)
SOURCE_QUALIFICATION_REF = (
    "agent-cluster/experiments/v31-qualifications/"
    f"{SOURCE_QUALIFICATION_ID}"
)
FORMAL_RUN_ID = "v31-prospective-btcusdt-20260806t183742z"
FORMAL_RUN_REF = f"agent-cluster/experiments/{FORMAL_RUN_ID}"
PREDECESSOR = "v31-earlier-failed-run"


def _fake_authority(run_id: str) -> tuple[dict, dict]:
    authority = self_digest(
        {
            "schema_id": "test_successor_active_authority",
            "schema_version": "2.0.0",
            "authorized_run_id": run_id,
            "experiment_start_authorized": True,
            "status": "ACTIVE_FROZEN_SUCCESSOR_RESEARCH",
            "chat_history_is_authority": False,
            "recorded_at": "2026-08-06T18:52:00Z",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "authority_digest",
    )
    binding = {
        "relative_ref": "genesis/current-authority.json",
        "schema_id": authority["schema_id"],
        "digest_field": "authority_digest",
        "semantic_digest": authority["authority_digest"],
        "physical_sha256": "a" * 64,
    }
    return authority, binding


def _formal_authority() -> tuple[dict, dict]:
    run_root = PROJECT / FORMAL_RUN_REF
    authority = __import__("json").loads(
        (run_root / "genesis/current-authority.json").read_text()
    )
    packet = __import__("json").loads(
        (run_root / "cycles/0001/proposal-authoring-packet.json").read_text()
    )
    return authority, packet["authority_context"]["active_authority_binding"]


def _document_binding(
    relative_ref: str, document: dict, digest_field: str
) -> dict[str, str]:
    payload = canonical_bytes(document) + b"\n"
    return {
        "relative_ref": relative_ref,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(payload).hexdigest(),
    }


class V31SuccessorQualificationV2Tests(unittest.TestCase):
    def _source(
        self,
        *,
        run_id: str,
        authority: dict,
        authority_binding: dict,
        predecessor: str = PREDECESSOR,
    ) -> dict:
        return compose_fresh_public_source_qualification_v2(
            project_root=PROJECT,
            qualification_root_ref=SOURCE_QUALIFICATION_REF,
            qualification_id=SOURCE_QUALIFICATION_ID,
            run_id=run_id,
            predecessor_run_id=predecessor,
            authority=authority,
            authority_binding=authority_binding,
            validated_authority_digest=authority["authority_digest"],
            qualified_at="2026-08-06T18:53:00Z",
            expires_at="2026-08-06T19:20:00Z",
        )

    def _codex(
        self,
        *,
        authority: dict,
        authority_binding: dict,
        predecessor: str = PREDECESSOR,
        source_digest: str = "c" * 64,
    ) -> dict:
        return compose_current_codex_durable_qualification_v2(
            project_root=PROJECT,
            run_root_ref=FORMAL_RUN_REF,
            run_id=FORMAL_RUN_ID,
            predecessor_run_id=predecessor,
            cycle_index=1,
            authority=authority,
            authority_binding=authority_binding,
            validated_authority_digest=authority["authority_digest"],
            source_qualification_v2_digest=source_digest,
            qualified_at="2026-08-06T19:09:00Z",
        )

    def _monitor_material(self, run_root: Path) -> tuple[dict, dict, dict, dict]:
        clock = build_outcome_clock_policy()
        raw_probe = build_raw_first_failure_probe_v2(
            tested_at="2026-08-06T19:09:00Z",
            clock_policy_digest=clock["clock_policy_digest"],
            case_results={name: "PASS" for name in RAW_FIRST_FAILURE_CASES},
        )
        supervisor_probe = build_supervisor_gate_probe_v2(
            tested_at="2026-08-06T19:09:00Z",
            case_results={name: "PASS" for name in SUPERVISOR_GATE_CASES},
        )
        documents = {
            "qualification/clock-policy.json": (
                clock,
                "clock_policy_digest",
            ),
            "qualification/raw-first-probe.json": (
                raw_probe,
                RAW_FIRST_PROBE_DIGEST_FIELD,
            ),
            "qualification/supervisor-probe.json": (
                supervisor_probe,
                SUPERVISOR_PROBE_DIGEST_FIELD,
            ),
        }
        bindings = {}
        for relative_ref, (document, digest_field) in documents.items():
            target = run_root / relative_ref
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(canonical_bytes(document) + b"\n")
            bindings[relative_ref] = _document_binding(
                relative_ref, document, digest_field
            )
        return clock, raw_probe, supervisor_probe, bindings

    def _monitor(
        self,
        *,
        run_id: str,
        authority: dict,
        authority_binding: dict,
        run_root: Path,
        predecessor: str = PREDECESSOR,
    ) -> dict:
        clock, raw_probe, supervisor_probe, bindings = self._monitor_material(
            run_root
        )
        return compose_monitor_runtime_qualification_v2(
            run_id=run_id,
            predecessor_run_id=predecessor,
            authority=authority,
            authority_binding=authority_binding,
            validated_authority_digest=authority["authority_digest"],
            qualified_at="2026-08-06T19:09:30Z",
            clock_policy=clock,
            clock_policy_binding=bindings["qualification/clock-policy.json"],
            raw_first_probe=raw_probe,
            raw_first_probe_binding=bindings[
                "qualification/raw-first-probe.json"
            ],
            supervisor_probe=supervisor_probe,
            supervisor_probe_binding=bindings[
                "qualification/supervisor-probe.json"
            ],
        )

    def test_fresh_public_source_replays_real_raw_and_is_self_summarizing(self) -> None:
        run_id = "v31-successor-source-contract-test"
        authority, authority_binding = _fake_authority(run_id)
        receipt = self._source(
            run_id=run_id,
            authority=authority,
            authority_binding=authority_binding,
        )
        self.assertEqual(
            receipt[SOURCE_QUALIFICATION_DIGEST_FIELD],
            verify_successor_public_source_qualification_v2(receipt),
        )
        self.assertEqual(12, len(receipt["capture_summaries"]))
        self.assertEqual(
            "REAL_PUBLIC_HTTP_CAPTURE_NONFIXTURE", receipt["transport_origin"]
        )
        self.assertTrue(
            receipt["qualification_summary"]["authority_postdating"]
        )
        self.assertEqual(
            receipt[SOURCE_QUALIFICATION_DIGEST_FIELD],
            verify_fresh_public_source_qualification_durable_v2(
                project_root=PROJECT,
                authority=authority,
                validated_authority_digest=authority["authority_digest"],
                document=receipt,
            ),
        )
        summary = qualification_summary_v2(receipt)
        self.assertFalse(summary["prediction_claim"])
        self.assertFalse(summary["profitability_claim"])

    def test_source_rejects_pre_authority_and_raw_physical_drift(self) -> None:
        run_id = "v31-successor-source-negative-test"
        authority, authority_binding = _fake_authority(run_id)
        late_authority = copy.deepcopy(authority)
        late_authority.pop("authority_digest")
        late_authority["recorded_at"] = "2026-08-06T18:53:00Z"
        late_authority = self_digest(late_authority, "authority_digest")
        late_binding = {
            **authority_binding,
            "semantic_digest": late_authority["authority_digest"],
        }
        with self.assertRaisesRegex(
            V31SuccessorQualificationV2Error,
            "SOURCE_FRESHNESS_OR_DURABILITY_INVALID",
        ):
            self._source(
                run_id=run_id,
                authority=late_authority,
                authority_binding=late_binding,
            )

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            target_ref = (
                "agent-cluster/experiments/v31-qualifications/"
                "v31-source-qualification-successor-proof"
            )
            target = project / target_ref
            shutil.copytree(PROJECT / SOURCE_QUALIFICATION_REF, target)
            raw = target / "cycles/0001/market/raw/okx-native-ticker.body"
            raw.write_bytes(raw.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                compose_fresh_public_source_qualification_v2(
                    project_root=project,
                    qualification_root_ref=target_ref,
                    qualification_id=SOURCE_QUALIFICATION_ID,
                    run_id=run_id,
                    predecessor_run_id=PREDECESSOR,
                    authority=authority,
                    authority_binding=authority_binding,
                    validated_authority_digest=authority["authority_digest"],
                    qualified_at="2026-08-06T18:53:00Z",
                    expires_at="2026-08-06T19:20:00Z",
                )

    def test_current_codex_chain_replays_compile_postseal_and_accept(self) -> None:
        authority, authority_binding = _formal_authority()
        receipt = self._codex(
            authority=authority, authority_binding=authority_binding
        )
        self.assertEqual(
            receipt[CODEX_QUALIFICATION_DIGEST_FIELD],
            verify_successor_codex_durable_qualification_v2(receipt),
        )
        self.assertEqual("CURRENT_CODEX_TASK", receipt["agent_id"])
        self.assertTrue(
            receipt["qualification_summary"][
                "proposal_compilation_postseal_acceptance_durable"
            ]
        )
        self.assertEqual(
            receipt[CODEX_QUALIFICATION_DIGEST_FIELD],
            verify_current_codex_qualification_durable_v2(
                project_root=PROJECT,
                run_root_ref=FORMAL_RUN_REF,
                authority=authority,
                validated_authority_digest=authority["authority_digest"],
                document=receipt,
            ),
        )

    def test_codex_rejects_old_run_reuse_and_chat_substitute(self) -> None:
        authority, authority_binding = _formal_authority()
        with self.assertRaisesRegex(
            V31SuccessorQualificationV2Error,
            "OLD_RUN_REUSE_FORBIDDEN",
        ):
            self._codex(
                authority=authority,
                authority_binding=authority_binding,
                predecessor=FORMAL_RUN_ID,
            )
        receipt = self._codex(
            authority=authority, authority_binding=authority_binding
        )
        tampered = copy.deepcopy(receipt)
        tampered.pop(CODEX_QUALIFICATION_DIGEST_FIELD)
        tampered["delivery_origin"] = "CHAT_MEMORY_SUBSTITUTE"
        tampered = self_digest(tampered, CODEX_QUALIFICATION_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V31SuccessorQualificationV2Error,
            "CODEX_QUALIFICATION_INVALID",
        ):
            verify_successor_codex_durable_qualification_v2(tampered)

    def test_monitor_binds_clock_failure_injection_supervisor_and_physical_files(self) -> None:
        run_id = "v31-successor-monitor-contract-test"
        authority, authority_binding = _fake_authority(run_id)
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary)
            receipt = self._monitor(
                run_id=run_id,
                authority=authority,
                authority_binding=authority_binding,
                run_root=run_root,
            )
            self.assertEqual(
                receipt[MONITOR_QUALIFICATION_DIGEST_FIELD],
                verify_successor_monitor_qualification_v2(receipt),
            )
            policy = receipt["monitor_policy"]
            self.assertEqual(
                "ACCEPTED_STATE_DECISION_AT_ABSOLUTE_UTC",
                policy["schedule_basis"],
            )
            self.assertEqual(1, policy["attempt_limit_per_cycle"])
            self.assertFalse(policy["retry_allowed"])
            self.assertEqual(1, policy["state_change_boundaries_per_wake"])
            self.assertEqual(
                receipt[MONITOR_QUALIFICATION_DIGEST_FIELD],
                verify_monitor_qualification_durable_v2(
                    run_root=run_root, document=receipt
                ),
            )
            target = run_root / "qualification/raw-first-probe.json"
            target.write_bytes(target.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "BOUND_EVIDENCE_INVALID"):
                verify_monitor_qualification_durable_v2(
                    run_root=run_root, document=receipt
                )

    def test_monitor_rejects_incomplete_probe_and_clock_policy_drift(self) -> None:
        clock = build_outcome_clock_policy()
        incomplete = {name: "PASS" for name in RAW_FIRST_FAILURE_CASES[:-1]}
        with self.assertRaisesRegex(
            V31SuccessorQualificationV2Error,
            "RAW_FIRST_CASES_INCOMPLETE",
        ):
            build_raw_first_failure_probe_v2(
                tested_at="2026-08-06T19:09:00Z",
                clock_policy_digest=clock["clock_policy_digest"],
                case_results=incomplete,
            )

        run_id = "v31-successor-monitor-drift-test"
        authority, authority_binding = _fake_authority(run_id)
        with tempfile.TemporaryDirectory() as temporary:
            receipt = self._monitor(
                run_id=run_id,
                authority=authority,
                authority_binding=authority_binding,
                run_root=Path(temporary),
            )
        tampered = copy.deepcopy(receipt)
        tampered.pop(MONITOR_QUALIFICATION_DIGEST_FIELD)
        tampered["clock_policy"]["max_provider_age_ms"] += 1
        tampered = self_digest(tampered, MONITOR_QUALIFICATION_DIGEST_FIELD)
        with self.assertRaises(ValueError):
            verify_successor_monitor_qualification_v2(tampered)

    def test_three_receipts_form_one_nonexecuting_authority_input(self) -> None:
        authority, authority_binding = _formal_authority()
        source = self._source(
            run_id=FORMAL_RUN_ID,
            authority=authority,
            authority_binding=authority_binding,
        )
        codex = self._codex(
            authority=authority,
            authority_binding=authority_binding,
            source_digest=source[SOURCE_QUALIFICATION_DIGEST_FIELD],
        )
        with tempfile.TemporaryDirectory() as temporary:
            monitor = self._monitor(
                run_id=FORMAL_RUN_ID,
                authority=authority,
                authority_binding=authority_binding,
                run_root=Path(temporary),
            )
        source_binding = _document_binding(
            "qualifications/source.json",
            source,
            SOURCE_QUALIFICATION_DIGEST_FIELD,
        )
        codex_binding = _document_binding(
            "qualifications/codex.json",
            codex,
            CODEX_QUALIFICATION_DIGEST_FIELD,
        )
        monitor_binding = _document_binding(
            "qualifications/monitor.json",
            monitor,
            MONITOR_QUALIFICATION_DIGEST_FIELD,
        )
        predecessor_binding = {
            "relative_ref": "lineage/predecessor-failure.json",
            "schema_id": "predecessor_failure",
            "digest_field": "failure_digest",
            "semantic_digest": "e" * 64,
            "physical_sha256": "f" * 64,
        }
        envelope = build_successor_qualification_authority_envelope_v2(
            frozen_at="2026-08-06T19:10:00Z",
            run_root_ref=FORMAL_RUN_REF,
            predecessor_run_id=PREDECESSOR,
            predecessor_failure_binding=predecessor_binding,
            predecessor_failure_digest="e" * 64,
            source_qualification_binding=source_binding,
            source_qualification=source,
            codex_qualification_binding=codex_binding,
            codex_qualification=codex,
            monitor_qualification_binding=monitor_binding,
            monitor_qualification=monitor,
        )
        self.assertEqual(
            envelope["successor_qualification_envelope_digest"],
            verify_successor_qualification_authority_envelope_v2(envelope),
        )
        self.assertFalse(envelope["executable"])
        self.assertIn("NO_PREDICTION_INCREMENT_CLAIM", envelope["limitations"])

        wrong = copy.deepcopy(monitor)
        wrong.pop(MONITOR_QUALIFICATION_DIGEST_FIELD)
        wrong["run_id"] = "different-successor-run"
        wrong = self_digest(wrong, MONITOR_QUALIFICATION_DIGEST_FIELD)
        wrong_binding = _document_binding(
            "qualifications/monitor-wrong.json",
            wrong,
            MONITOR_QUALIFICATION_DIGEST_FIELD,
        )
        with self.assertRaises(
            (V31SuccessorQualificationAuthorityV2Error, ValueError)
        ):
            build_successor_qualification_authority_envelope_v2(
                frozen_at="2026-08-06T19:10:00Z",
                run_root_ref=FORMAL_RUN_REF,
                predecessor_run_id=PREDECESSOR,
                predecessor_failure_binding=predecessor_binding,
                predecessor_failure_digest="e" * 64,
                source_qualification_binding=source_binding,
                source_qualification=source,
                codex_qualification_binding=codex_binding,
                codex_qualification=codex,
                monitor_qualification_binding=wrong_binding,
                monitor_qualification=wrong,
            )

    def test_authority_loader_physically_replays_all_three_qualifications(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_root = project / FORMAL_RUN_REF
            source_root = project / SOURCE_QUALIFICATION_REF
            run_root.parent.mkdir(parents=True, exist_ok=True)
            source_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(PROJECT / FORMAL_RUN_REF, run_root)
            shutil.copytree(PROJECT / SOURCE_QUALIFICATION_REF, source_root)
            authority = __import__("json").loads(
                (run_root / "genesis/current-authority.json").read_text()
            )
            packet = __import__("json").loads(
                (
                    run_root
                    / "cycles/0001/proposal-authoring-packet.json"
                ).read_text()
            )
            authority_binding = packet["authority_context"][
                "active_authority_binding"
            ]
            source = compose_fresh_public_source_qualification_v2(
                project_root=project,
                qualification_root_ref=SOURCE_QUALIFICATION_REF,
                qualification_id=SOURCE_QUALIFICATION_ID,
                run_id=FORMAL_RUN_ID,
                predecessor_run_id=PREDECESSOR,
                authority=authority,
                authority_binding=authority_binding,
                validated_authority_digest=authority["authority_digest"],
                qualified_at="2026-08-06T18:53:00Z",
                expires_at="2026-08-06T19:20:00Z",
            )
            codex = compose_current_codex_durable_qualification_v2(
                project_root=project,
                run_root_ref=FORMAL_RUN_REF,
                run_id=FORMAL_RUN_ID,
                predecessor_run_id=PREDECESSOR,
                cycle_index=1,
                authority=authority,
                authority_binding=authority_binding,
                validated_authority_digest=authority["authority_digest"],
                source_qualification_v2_digest=source[
                    SOURCE_QUALIFICATION_DIGEST_FIELD
                ],
                qualified_at="2026-08-06T19:09:00Z",
            )
            monitor = self._monitor(
                run_id=FORMAL_RUN_ID,
                authority=authority,
                authority_binding=authority_binding,
                run_root=run_root,
            )

            qualification_specs = {
                "source": (source, SOURCE_QUALIFICATION_DIGEST_FIELD),
                "codex": (codex, CODEX_QUALIFICATION_DIGEST_FIELD),
                "monitor": (monitor, MONITOR_QUALIFICATION_DIGEST_FIELD),
            }
            qualification_bindings = {}
            for name, (document, digest_field) in qualification_specs.items():
                relative_ref = (
                    f"{FORMAL_RUN_REF}/qualification-receipts/{name}.json"
                )
                target = project / relative_ref
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(canonical_bytes(document) + b"\n")
                qualification_bindings[name] = _document_binding(
                    relative_ref, document, digest_field
                )

            predecessor_run_ref = "lineage/predecessor-run"
            predecessor_store = LocalV31MonitorStore(
                project / predecessor_run_ref
            )
            predecessor_store.initialize_checkpoint(
                run_id=PREDECESSOR,
                experiment_contract_digest="9" * 64,
                total_cycles=8,
                created_at="2026-08-06T18:00:00Z",
            )
            active_predecessor = predecessor_store.load_checkpoint(
                run_id=PREDECESSOR
            )
            failed_predecessor = predecessor_store.fail_checkpoint(
                run_id=PREDECESSOR,
                expected_checkpoint_digest=active_predecessor[
                    "checkpoint_digest"
                ],
                failure_code="PREDECESSOR_TERMINAL_FAILURE",
                failure_summary="The predecessor cannot resume.",
                occurred_at="2026-08-06T18:01:00Z",
            )
            predecessor_failure = predecessor_store.read_document(
                relative_ref=failed_predecessor["failure_ref"],
                digest_field="failure_digest",
                expected_semantic_digest=failed_predecessor["failure_digest"],
            )
            predecessor_ref = (
                f"{predecessor_run_ref}/{failed_predecessor['failure_ref']}"
            )
            predecessor_binding = _document_binding(
                predecessor_ref, predecessor_failure, "failure_digest"
            )
            predecessor_checkpoint_ref = (
                f"{predecessor_run_ref}/monitor/checkpoint.json"
            )
            predecessor_checkpoint_binding = _document_binding(
                predecessor_checkpoint_ref,
                failed_predecessor,
                "checkpoint_digest",
            )
            loaded = load_successor_qualification_authority_input_v2(
                project_root=project,
                run_root_ref=FORMAL_RUN_REF,
                frozen_at="2026-08-06T19:10:00Z",
                predecessor_run_id=PREDECESSOR,
                predecessor_failure_binding=predecessor_binding,
                authority=authority,
                validated_authority_digest=authority["authority_digest"],
                source_qualification_binding=qualification_bindings["source"],
                codex_qualification_binding=qualification_bindings["codex"],
                monitor_qualification_binding=qualification_bindings[
                    "monitor"
                ],
                predecessor_run_root_ref=predecessor_run_ref,
                predecessor_monitor_checkpoint_binding=(
                    predecessor_checkpoint_binding
                ),
            )
            self.assertEqual(
                "SUCCESSOR_QUALIFICATIONS_COMPLETE_NOT_RUN_ACTIVATION",
                loaded["envelope"]["qualification_summary"]["verdict"],
            )
            self.assertEqual(
                loaded["envelope"][
                    "successor_qualification_envelope_digest"
                ],
                verify_successor_qualification_authority_envelope_v2(
                    loaded["envelope"]
                ),
            )
            self.assertNotIn("status", loaded["predecessor_failure"])
            self.assertEqual(
                "FAILED_CLOSED",
                loaded["predecessor_monitor_checkpoint"]["status"],
            )


if __name__ == "__main__":
    unittest.main()
