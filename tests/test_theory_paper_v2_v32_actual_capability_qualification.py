from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests import test_theory_paper_v2_v32_agent_lifecycle as lifecycle_fixture
from tests import test_theory_paper_v2_v32_public_source_collector as source_fixture
from tests.test_theory_paper_v2_v32_agent_semantic_compiler import _full_fixture
from trade_system.theory_paper_v2.application.v32_actual_capability_qualification import (
    V32ActualCapabilityQualificationError,
    _enforce_current_codex_duration,
    run_v32_actual_capability_qualification,
    seal_v32_actual_capability_qualification_from_completed_attempts,
)
from trade_system.theory_paper_v2.application.v32_agent_semantic_compiler import (
    build_v32_selection_semantic_output_v1,
    canonical_v32_agent_semantic_json_v1,
    compile_v32_proposal_delivery_v1,
)
from trade_system.theory_paper_v2.application.v32_cycle_composition import (
    run_v32_single_boundary_wake,
)
from trade_system.theory_paper_v2.application.v32_cycle_source_admission import (
    admit_fresh_v32_source_to_cycle,
)
from trade_system.theory_paper_v2.application.v32_durable_source_replay import (
    compose_and_persist_v32_durable_source_replay_receipt,
)
from trade_system.theory_paper_v2.application.v32_outcome_tick_composition import (
    initialize_v32_outcome_tick_runtime,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_outcome_adapter import (
    OKX_V32_MARK_PRICE_URL,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
    AUTHORITY_SCHEMA_ID,
    CAPABILITY_KEYS,
    QUALIFICATION_PROFILE,
    build_v32_actual_capability_receipt_v1,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    ACTION_EVALUATION_DIGEST_FIELD,
    ACTION_EVALUATION_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    SELECTION_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_SCHEMA_ID,
    V32_QUALIFICATION_CONTEXT_PROFILE,
    build_v32_agent_input_context_v1,
    build_v32_selection_canonical_packet_v1,
)
from trade_system.theory_paper_v2.domain.v32_current_root_agent_mailbox import (
    CHECKPOINT_DIGEST_FIELD as MAILBOX_CHECKPOINT_DIGEST_FIELD,
    CURRENT_CODEX_PRESENTATION_DIGEST_FIELD,
    build_v32_current_codex_presentation_envelope_v1,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_qualification_monitor_probe import (
    build_v32_qualification_monitor_probe_v1,
)
from trade_system.theory_paper_v2.domain.v32_runtime_support_contracts import (
    TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_actual_capability_replay import (
    EVIDENCE_ROOT_SPECS,
    LocalV32ActualCapabilityEvidenceStore,
    build_v32_actual_capability_full_replay_registry,
    build_v32_actual_capability_evidence_root_v1,
    compose_v32_current_codex_actual_evidence_root,
    compose_v32_outcome_monitor_actual_evidence_root,
    compose_v32_public_source_actual_evidence_root,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_monitor_probe_store import (
    LocalV32QualificationMonitorProbeStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_current_root_agent_mailbox import (
    LocalV32CurrentRootAgentMailbox,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_local_outcome_lane import (
    LocalV32OutcomeLane,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
    build_v32_outcome_tick_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_evidence_verifier import (
    V32InfrastructurePublicEvidenceVerifier,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    V32RawFirstOkxPublicBundleCollector,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def write_authority(root: Path, authority: dict) -> dict[str, str]:
    relative_ref = "config/v32/qualification/authority.json"
    path = root / relative_ref
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(authority) + b"\n"
    path.write_bytes(payload)
    return {
        "path": relative_ref,
        "schema_id": AUTHORITY_SCHEMA_ID,
        "digest_field": AUTHORITY_DIGEST_FIELD,
        "semantic_digest": authority[AUTHORITY_DIGEST_FIELD],
        "physical_sha256": hashlib.sha256(payload).hexdigest(),
    }


class SequenceClock:
    def __init__(self, values: list[str]) -> None:
        self.values = iter(values)

    def __call__(self) -> str:
        return next(self.values)


class PublicSourceAttempt:
    def __init__(self, *, project_root: Path, store, projection: dict) -> None:
        self.project_root = project_root
        self.store = store
        self.projection = projection
        self.calls = 0
        self.transport_calls = 0

    def execute_once(self, **kwargs):
        self.calls += 1
        authority = kwargs["qualification_authority"]
        base = datetime(2026, 8, 7, 0, 14, tzinfo=UTC)
        source_root = "runtime/qualification-public-source"
        run_root = "runtime/qualification-public-run"
        source_store = LocalV32CycleSourceAdmissionStore(
            self.project_root / source_root
        )
        run_store = LocalV32CycleSourceAdmissionStore(self.project_root / run_root)
        with patch.object(source_fixture, "BASE", base), patch.object(
            source_fixture,
            "SERVER_MS",
            int((base + timedelta(seconds=3)).timestamp() * 1000),
        ):
            transport = source_fixture.BundleTransport(source_fixture.raw_bundle())
            collected = V32RawFirstOkxPublicBundleCollector(
                transport=transport,
                clock=source_fixture.SequenceClock(),
                store=source_store,
            ).collect_and_qualify(
                qualification_id="v32-actual-public-source",
                run_id=authority["run_id"],
                cycle_index=1,
                active_authority=self.projection,
            )
        self.transport_calls += transport.calls
        admit_fresh_v32_source_to_cycle(
            source_store=source_store,
            run_store=run_store,
            active_authority=self.projection,
            qualification_id="v32-actual-public-source",
            run_id=authority["run_id"],
            cycle_index=1,
            decision_time=collected.formal_qualification["decision_time"],
            admitted_at=iso(base + timedelta(seconds=6, microseconds=500_000)),
        )
        compose_and_persist_v32_durable_source_replay_receipt(
            public_evidence_verifier=V32InfrastructurePublicEvidenceVerifier(),
            source_store=source_store,
            run_store=run_store,
            active_authority=self.projection,
            qualification_id="v32-actual-public-source",
            run_id=authority["run_id"],
            cycle_index=1,
            replayed_at=iso(base + timedelta(seconds=7)),
        )
        root = compose_v32_public_source_actual_evidence_root(
            project_root=self.project_root,
            qualification_authority=authority,
            attempt_reservation_binding=kwargs["reservation_binding"],
            active_authority_projection=self.projection,
            source_store_root=source_root,
            run_store_root=run_root,
            qualification_id="v32-actual-public-source",
            started_at=iso(base + timedelta(seconds=1)),
            completed_at=iso(base + timedelta(seconds=7)),
        )
        binding = self.store.persist_evidence_root(root)
        return {"evidence_root": root, "evidence_root_binding": binding}


class CurrentCodexAttempt:
    def __init__(self, *, project_root: Path, store, fixture: dict) -> None:
        self.project_root = project_root
        self.store = store
        self.fixture = fixture
        self.calls = 0

    def _selection(self, proposal: dict) -> tuple[dict, dict, str]:
        proposal_receipt = compile_v32_proposal_delivery_v1(
            proposal_input_context=self.fixture["proposal_context"],
            proposal_delivery=proposal["agent_delivery"],
            proposal_consumption=proposal["agent_consumption"],
            compiled_at="2026-08-07T00:16:40Z",
        )
        dynamic = proposal_receipt["compiled_dynamic_research_state"]
        evaluation = proposal_receipt["sealed_action_evaluation"]
        dynamic_binding = lifecycle_fixture._embedded(
            "qualification-mailbox/compiled-dynamic",
            dynamic,
            "theory_paper_v32_dynamic_research_state_v1",
            "dynamic_research_state_digest",
        )
        evaluation_binding = lifecycle_fixture._embedded(
            "qualification-mailbox/sealed-evaluation",
            evaluation,
            ACTION_EVALUATION_SCHEMA_ID,
            ACTION_EVALUATION_DIGEST_FIELD,
        )
        packet = build_v32_selection_canonical_packet_v1(
            proposal_input_context=self.fixture["proposal_context"],
            proposal_input_context_binding=self.fixture["proposal_context_binding"],
            proposal_delivery=proposal["agent_delivery"],
            proposal_delivery_binding=proposal["agent_delivery_binding"],
            proposal_consumption=proposal["agent_consumption"],
            proposal_consumption_binding=proposal["agent_consumption_binding"],
            compiled_dynamic_research_state=dynamic,
            compiled_dynamic_research_state_binding=dynamic_binding,
            sealed_action_evaluation=evaluation,
            sealed_action_evaluation_binding=evaluation_binding,
            prepared_at="2026-08-07T00:16:45Z",
        )
        packet_binding = lifecycle_fixture._embedded(
            "qualification-mailbox/selection-packet",
            packet,
            SELECTION_PACKET_SCHEMA_ID,
            SELECTION_PACKET_DIGEST_FIELD,
        )
        context = build_v32_agent_input_context_v1(
            agent_stage="SELECTION",
            canonical_packet=packet,
            canonical_packet_binding=packet_binding,
            created_at="2026-08-07T00:16:50Z",
        )
        context_binding = lifecycle_fixture._embedded(
            "qualification-mailbox/selection-context",
            context,
            AGENT_INPUT_CONTEXT_SCHEMA_ID,
            AGENT_INPUT_CONTEXT_DIGEST_FIELD,
        )
        output = build_v32_selection_semantic_output_v1(
            selection_input_context=context, selected_candidate_id="open-short"
        )
        return context, context_binding, canonical_v32_agent_semantic_json_v1(output)

    def execute_once(self, **kwargs):
        self.calls += 1
        authority = kwargs["qualification_authority"]
        mailbox_root = "runtime/qualification-mailbox"
        mailbox = LocalV32CurrentRootAgentMailbox(self.project_root / mailbox_root)
        checkpoint = mailbox.initialize_checkpoint(
            mailbox_id=f"qualification::{authority['run_id']}",
            run_id=authority["run_id"],
            cycle_index=1,
            created_at="2026-08-07T00:16:00Z",
        )
        opened = mailbox.enqueue_request(
            run_id=authority["run_id"],
            cycle_index=1,
            expected_checkpoint_digest=checkpoint[MAILBOX_CHECKPOINT_DIGEST_FIELD],
            agent_input_context=self.fixture["proposal_context"],
            agent_input_context_binding=self.fixture["proposal_context_binding"],
            reserved_at="2026-08-07T00:16:05Z",
        )
        claimed = mailbox.claim_request(
            run_id=authority["run_id"],
            cycle_index=1,
            stage="PROPOSAL",
            expected_checkpoint_digest=opened["checkpoint"][
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at="2026-08-07T00:16:10Z",
        )
        current_codex_presentation = (
            build_v32_current_codex_presentation_envelope_v1(
                mailbox_checkpoint=claimed["checkpoint"],
                request=claimed["request"],
                claim=claimed["claim"],
                lossless_context_package=None,
                control_context={
                    "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                    "stage": "PROPOSAL",
                    "stage_status": "CLAIMED",
                    "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                },
            )
        )
        delivered = mailbox.submit_delivery(
            run_id=authority["run_id"],
            cycle_index=1,
            stage="PROPOSAL",
            expected_checkpoint_digest=claimed["checkpoint"][
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            current_codex_presentation_envelope=current_codex_presentation,
            expected_current_codex_presentation_digest=current_codex_presentation[
                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
            ],
            delivered_at="2026-08-07T00:16:20Z",
            payload_utf8=self.fixture["proposal_payload"],
        )
        proposal = mailbox.consume_delivery(
            run_id=authority["run_id"],
            cycle_index=1,
            stage="PROPOSAL",
            expected_checkpoint_digest=delivered["checkpoint"][
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            consumed_at="2026-08-07T00:16:30Z",
        )
        selection_context, selection_binding, selection_payload = self._selection(
            proposal
        )
        opened = mailbox.enqueue_request(
            run_id=authority["run_id"],
            cycle_index=1,
            expected_checkpoint_digest=proposal["checkpoint"][
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            agent_input_context=selection_context,
            agent_input_context_binding=selection_binding,
            reserved_at="2026-08-07T00:16:55Z",
        )
        claimed = mailbox.claim_request(
            run_id=authority["run_id"],
            cycle_index=1,
            stage="SELECTION",
            expected_checkpoint_digest=opened["checkpoint"][
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            claimed_at="2026-08-07T00:17:00Z",
        )
        current_codex_presentation = (
            build_v32_current_codex_presentation_envelope_v1(
                mailbox_checkpoint=claimed["checkpoint"],
                request=claimed["request"],
                claim=claimed["claim"],
                lossless_context_package=None,
                control_context={
                    "presentation_kind": "QUALIFICATION_AGENT_CLAIM",
                    "stage": "SELECTION",
                    "stage_status": "CLAIMED",
                    "next_action": "CURRENT_ROOT_CODEX_SUBMIT_DELIVERY",
                },
            )
        )
        delivered = mailbox.submit_delivery(
            run_id=authority["run_id"],
            cycle_index=1,
            stage="SELECTION",
            expected_checkpoint_digest=claimed["checkpoint"][
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            current_codex_presentation_envelope=current_codex_presentation,
            expected_current_codex_presentation_digest=current_codex_presentation[
                CURRENT_CODEX_PRESENTATION_DIGEST_FIELD
            ],
            delivered_at="2026-08-07T00:17:10Z",
            payload_utf8=selection_payload,
        )
        mailbox.consume_delivery(
            run_id=authority["run_id"],
            cycle_index=1,
            stage="SELECTION",
            expected_checkpoint_digest=delivered["checkpoint"][
                MAILBOX_CHECKPOINT_DIGEST_FIELD
            ],
            consumed_at="2026-08-07T00:17:20Z",
        )
        root = compose_v32_current_codex_actual_evidence_root(
            project_root=self.project_root,
            qualification_authority=authority,
            attempt_reservation_binding=kwargs["reservation_binding"],
            mailbox_store_root=mailbox_root,
            started_at="2026-08-07T00:16:05Z",
            completed_at="2026-08-07T00:17:20Z",
        )
        binding = self.store.persist_evidence_root(root)
        return {"evidence_root": root, "evidence_root_binding": binding}


class CapturePort:
    def __init__(self) -> None:
        self.calls = 0

    def capture_public_mark(self, *, attempt, requested_at):
        self.calls += 1
        observed = datetime(2026, 8, 7, 1, 0, 1, tzinfo=UTC)
        raw = json.dumps(
            {
                "code": "0",
                "msg": "",
                "data": [
                    {
                        "instType": "SWAP",
                        "instId": "BTC-USDT-SWAP",
                        "markPx": "65000.1",
                        "ts": str(int(observed.timestamp() * 1000)),
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()
        return {
            "transport_status": "RESPONSE_CAPTURED",
            "source_request_id": attempt["source_request_id"],
            "received_at": "2026-08-07T01:00:02Z",
            "captured_at": "2026-08-07T01:00:02Z",
            "final_url": OKX_V32_MARK_PRICE_URL,
            "http_status": 200,
            "raw_payload": raw,
        }


class OutcomeMonitorAttempt:
    def __init__(self, *, project_root: Path, store) -> None:
        self.project_root = project_root
        self.store = store
        self.calls = 0
        self.capture = CapturePort()

    def execute_once(self, **kwargs):
        self.calls += 1
        authority = kwargs["qualification_authority"]
        probe_root = "runtime/qualification-monitor-probe"
        probe_store = LocalV32QualificationMonitorProbeStore(
            self.project_root / probe_root,
            capture_port=self.capture,
            clock=SequenceClock(
                [
                    "2026-08-07T01:00:01Z",
                    "2026-08-07T01:00:01Z",
                    "2026-08-07T01:00:02Z",
                    "2026-08-07T01:00:03Z",
                ]
            ),
        )
        schedule = build_v32_qualification_monitor_probe_v1(
            probe_id="qualification-monitor-probe:one-shot-test",
            qualification_authority=authority,
            final_action_plan_digest=canonical_digest(
                {"kind": "qualification-final-plan", "cycle": 1}
            ),
            selection_consumption_digest=canonical_digest(
                {"kind": "qualification-selection-consumption", "cycle": 1}
            ),
            decision_time="2026-08-07T00:45:01Z",
        )
        probe_store.initialize(schedule)
        results = [probe_store.advance_once() for _ in range(4)]
        if results[-1]["status"] != "COMPLETE":
            raise AssertionError(results)
        completion = results[-1]["completion"]
        root = compose_v32_outcome_monitor_actual_evidence_root(
            project_root=self.project_root,
            qualification_authority=authority,
            attempt_reservation_binding=kwargs["reservation_binding"],
            probe_store_root=probe_root,
            probe_id=schedule["probe_id"],
            started_at=completion["started_at"],
            completed_at=completion["completed_at"],
        )
        binding = self.store.persist_evidence_root(root)
        return {"evidence_root": root, "evidence_root_binding": binding}


class V32ActualCapabilityQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = lifecycle_fixture._proposal_packet(
            profile=V32_QUALIFICATION_CONTEXT_PROFILE
        )

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.authority = self.packet["authority_document"]
        self.assertEqual(QUALIFICATION_PROFILE, self.authority["profile"])
        self.authority_binding = write_authority(self.project, self.authority)
        self.store = LocalV32ActualCapabilityEvidenceStore(
            self.project, "qualification-evidence"
        )
        self.public = PublicSourceAttempt(
            project_root=self.project,
            store=self.store,
            projection=self.packet["support_documents"][
                "active_authority_projection"
            ],
        )
        self.codex = CurrentCodexAttempt(
            project_root=self.project,
            store=self.store,
            fixture=None,
        )
        self.outcome = OutcomeMonitorAttempt(
            project_root=self.project, store=self.store
        )
        self.ports = {
            "CURRENT_CODEX": self.codex,
            "OUTCOME_MONITOR": self.outcome,
            "PUBLIC_SOURCE": self.public,
        }

    def test_current_codex_duration_has_a_hard_runtime_safety_gate(self):
        started = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
        _enforce_current_codex_duration(
            capability="CURRENT_CODEX",
            started=started,
            completed=started
            + timedelta(seconds=TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS),
        )
        with self.assertRaisesRegex(
            V32ActualCapabilityQualificationError,
            "CURRENT_CODEX_DURATION_EXCEEDED",
        ):
            _enforce_current_codex_duration(
                capability="CURRENT_CODEX",
                started=started,
                completed=started
                + timedelta(seconds=TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS + 1),
            )
        _enforce_current_codex_duration(
            capability="PUBLIC_SOURCE",
            started=started,
            completed=started
            + timedelta(seconds=TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS + 1),
        )

    def _lightweight_completed_attempts(
        self, *, current_codex_seconds: int = 75
    ) -> tuple[dict[str, dict], dict[str, object]]:
        """Build self-validating roots while stubbing only owning full replay."""

        projection = self.packet["support_documents"][
            "active_authority_projection"
        ]
        started = {
            "PUBLIC_SOURCE": datetime(2026, 8, 7, 0, 14, tzinfo=UTC),
            "CURRENT_CODEX": datetime(2026, 8, 7, 0, 16, tzinfo=UTC),
            "OUTCOME_MONITOR": datetime(2026, 8, 7, 0, 40, tzinfo=UTC),
        }
        completed = {
            "PUBLIC_SOURCE": started["PUBLIC_SOURCE"] + timedelta(seconds=7),
            "CURRENT_CODEX": started["CURRENT_CODEX"]
            + timedelta(seconds=current_codex_seconds),
            "OUTCOME_MONITOR": started["OUTCOME_MONITOR"] + timedelta(seconds=2),
        }
        reservation_at = {
            "PUBLIC_SOURCE": "2026-08-07T00:13:59Z",
            "CURRENT_CODEX": "2026-08-07T00:15:59Z",
            "OUTCOME_MONITOR": "2026-08-07T00:39:59Z",
        }
        descriptors = {
            "PUBLIC_SOURCE": {
                "source_store_root": "runtime/light-source",
                "run_store_root": "runtime/light-run",
                "qualification_id": "lightweight-qualification",
                "cycle_index": 1,
                "active_authority_projection": projection,
            },
            "CURRENT_CODEX": {
                "mailbox_store_root": "runtime/light-mailbox",
                "cycle_index": 1,
            },
            "OUTCOME_MONITOR": {
                "probe_store_root": "runtime/light-outcome-probe",
                "probe_id": "light-outcome-probe",
            },
        }
        terminal_binding = {
            "path": "runtime/light-terminal.json",
            "schema_id": "light-terminal-v1",
            "digest_field": "light_terminal_digest",
            "semantic_digest": "b" * 64,
            "physical_sha256": "c" * 64,
        }
        attempts: dict[str, dict] = {}
        replayers: dict[str, object] = {}
        for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR"):
            reservation = self.store.reserve_attempt(
                capability=capability,
                qualification_run_id=self.authority["run_id"],
                target_run_id=self.authority["target_run_id"],
                qualification_authority_digest=self.authority[
                    AUTHORITY_DIGEST_FIELD
                ],
                reserved_at=reservation_at[capability],
            )
            root = build_v32_actual_capability_evidence_root_v1(
                root_id=f"light-root:{capability.lower()}",
                capability=capability,
                qualification_run_id=self.authority["run_id"],
                target_run_id=self.authority["target_run_id"],
                qualification_authority_digest=self.authority[
                    AUTHORITY_DIGEST_FIELD
                ],
                attempt_reservation_binding=reservation["reservation_binding"],
                started_at=iso(started[capability]),
                completed_at=iso(completed[capability]),
                replay_descriptor=descriptors[capability],
                terminal_evidence_binding=terminal_binding,
            )
            binding = self.store.persist_evidence_root(root)
            attempts[capability] = {
                "evidence_root": root,
                "evidence_root_binding": binding,
            }
            root_digest = root[EVIDENCE_ROOT_SPECS[capability][1]]
            replayers[capability] = (
                lambda *, _capability=capability, _digest=root_digest, **_: {
                    "capability": _capability,
                    "evidence_root_semantic_digest": _digest,
                    "full_replay_verified": True,
                    "replay_network_calls": 0,
                }
            )
        return attempts, replayers

    def _assert_no_final_receipts(self) -> None:
        paths = [
            self.project / self.store.receipt_ref(capability)
            for capability in CAPABILITY_KEYS
        ] + [self.project / self.store.qualification_receipt_ref]
        self.assertFalse(any(path.exists() for path in paths), paths)

    def test_duration_failure_writes_no_receipt(self):
        attempts, replayers = self._lightweight_completed_attempts(
            current_codex_seconds=TOTAL_ANALYSIS_PHASE_BUDGET_SECONDS + 1
        )
        with patch.object(
            self.store,
            "full_replay_registry",
            return_value=replayers,
        ), self.assertRaisesRegex(
            V32ActualCapabilityQualificationError,
            "CURRENT_CODEX_DURATION_EXCEEDED",
        ):
            seal_v32_actual_capability_qualification_from_completed_attempts(
                project_root=self.project,
                evidence_store=self.store,
                qualification_id="duration-failure",
                qualification_authority=self.authority,
                qualification_authority_binding=self.authority_binding,
                completed_attempts=attempts,
            )
        self._assert_no_final_receipts()

    def _assert_stage_write_failure_is_atomic(self, failure_index: int) -> None:
        attempts, replayers = self._lightweight_completed_attempts()
        from trade_system.theory_paper_v2.infrastructure.authority.v32_secure_write_once_store import (
            _write_new_payload_at as real_write_new_payload_at,
        )

        calls = 0

        def fail_stage_write(parent_fd, leaf, payload):
            nonlocal calls
            calls += 1
            if calls == failure_index:
                raise OSError(f"injected stage failure {failure_index}")
            return real_write_new_payload_at(parent_fd, leaf, payload)

        with patch.object(
            self.store,
            "full_replay_registry",
            return_value=replayers,
        ), patch(
            "trade_system.theory_paper_v2.infrastructure.authority."
            "v32_secure_write_once_store._write_new_payload_at",
            side_effect=fail_stage_write,
        ), self.assertRaisesRegex(ValueError, "BATCH_WRITE_FAILED"):
            seal_v32_actual_capability_qualification_from_completed_attempts(
                project_root=self.project,
                evidence_store=self.store,
                qualification_id=f"install-failure-{failure_index}",
                qualification_authority=self.authority,
                qualification_authority_binding=self.authority_binding,
                completed_attempts=attempts,
            )
        self.assertEqual(failure_index, calls)
        self._assert_no_final_receipts()

    def test_second_receipt_install_failure_leaves_no_partial_state(self):
        self._assert_stage_write_failure_is_atomic(2)

    def test_third_receipt_install_failure_leaves_no_partial_state(self):
        self._assert_stage_write_failure_is_atomic(3)

    def test_publish_failure_leaves_no_final_bundle(self):
        attempts, replayers = self._lightweight_completed_attempts()
        with patch.object(
            self.store,
            "full_replay_registry",
            return_value=replayers,
        ), patch(
            "trade_system.theory_paper_v2.infrastructure.authority."
            "v32_secure_write_once_store.rename_directory_noreplace_at",
            side_effect=OSError("injected atomic publish failure"),
        ), self.assertRaisesRegex(ValueError, "BATCH_WRITE_FAILED"):
            seal_v32_actual_capability_qualification_from_completed_attempts(
                project_root=self.project,
                evidence_store=self.store,
                qualification_id="publish-failure",
                qualification_authority=self.authority,
                qualification_authority_binding=self.authority_binding,
                completed_attempts=attempts,
            )
        self.assertFalse((self.project / self.store.seal_bundle_ref).exists())
        self._assert_no_final_receipts()

    def test_existing_partial_final_bundle_fails_without_repair(self):
        attempts, replayers = self._lightweight_completed_attempts()
        bundle = self.project / self.store.seal_bundle_ref
        bundle.mkdir(parents=True)
        orphan = bundle / "qualification-receipt.json"
        orphan.write_bytes(b"{}\n")
        with patch.object(
            self.store,
            "full_replay_registry",
            return_value=replayers,
        ), self.assertRaisesRegex(ValueError, "EXISTING_CONFLICT"):
            seal_v32_actual_capability_qualification_from_completed_attempts(
                project_root=self.project,
                evidence_store=self.store,
                qualification_id="partial-existing",
                qualification_authority=self.authority,
                qualification_authority_binding=self.authority_binding,
                completed_attempts=attempts,
            )
        self.assertEqual({orphan}, {path for path in bundle.rglob("*") if path.is_file()})
        self.assertEqual(b"{}\n", orphan.read_bytes())

    def _run_qualification(self):
        if self.codex.fixture is None:
            with patch.object(
                lifecycle_fixture, "_proposal_packet", return_value=self.packet
            ):
                self.codex.fixture = _full_fixture()
        return run_v32_actual_capability_qualification(
            project_root=self.project,
            evidence_store=self.store,
            qualification_id="v32-actual-capability-qualification-test",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            attempt_ports=self.ports,
            clock=SequenceClock(
                [
                    "2026-08-07T00:13:59Z",
                    "2026-08-07T00:15:59Z",
                    "2026-08-07T00:59:59Z",
                ]
            ),
        )

    def test_runs_three_real_one_shot_paths_and_replays_without_network(self):
        result = self._run_qualification()
        self.assertEqual(0, self.authority["outcome_schedules"])
        self.assertEqual(1, self.authority["qualification_monitor_probes"])
        self.assertEqual(
            ["PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR"],
            result["attempt_order"],
        )
        self.assertEqual(set(CAPABILITY_KEYS), set(result["evidence_roots"]))
        self.assertEqual(0, result["network_replay_calls"])
        self.assertEqual(1, self.public.transport_calls)
        self.assertEqual(1, self.outcome.capture.calls)
        self.assertEqual((1, 1, 1), (self.public.calls, self.codex.calls, self.outcome.calls))
        self.assertEqual(
            {"probe_store_root", "probe_id"},
            set(result["evidence_roots"]["OUTCOME_MONITOR"]["replay_descriptor"]),
        )
        resealed = seal_v32_actual_capability_qualification_from_completed_attempts(
            project_root=self.project,
            evidence_store=self.store,
            qualification_id="v32-actual-capability-qualification-test",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            completed_attempts={
                capability: {
                    "evidence_root": result["evidence_roots"][capability],
                    "evidence_root_binding": result["evidence_root_bindings"][
                        capability
                    ],
                }
                for capability in CAPABILITY_KEYS
            },
        )
        self.assertEqual(
            result["qualification_receipt_binding"],
            resealed["qualification_receipt_binding"],
        )
        registry = build_v32_actual_capability_full_replay_registry()
        for capability in CAPABILITY_KEYS:
            replay = registry[capability](
                project_root=self.project,
                capability_receipt=result["actual_capability_receipts"][capability],
                evidence_root_binding=result["evidence_root_bindings"][capability],
                qualification_authority=self.authority,
            )
            self.assertTrue(replay["full_replay_verified"])
            self.assertEqual(0, replay["replay_network_calls"])

        with self.assertRaisesRegex(ValueError, "IDENTITY_INVALID"):
            registry["PUBLIC_SOURCE"](
                project_root=self.project,
                capability_receipt=result["actual_capability_receipts"][
                    "CURRENT_CODEX"
                ],
                evidence_root_binding=result["evidence_root_bindings"][
                    "CURRENT_CODEX"
                ],
                qualification_authority=self.authority,
            )

        public_receipt = result["actual_capability_receipts"]["PUBLIC_SOURCE"]
        cross_run_receipt = build_v32_actual_capability_receipt_v1(
            capability="PUBLIC_SOURCE",
            receipt_id="actual-capability:public-source:cross-run",
            qualification_run_id="different-qualification-run",
            target_run_id=self.authority["target_run_id"],
            started_at=public_receipt["started_at"],
            completed_at=public_receipt["completed_at"],
            qualification_authority_binding=self.authority_binding,
            evidence_root_binding=result["evidence_root_bindings"][
                "PUBLIC_SOURCE"
            ],
        )
        with self.assertRaisesRegex(ValueError, "IDENTITY_INVALID"):
            registry["PUBLIC_SOURCE"](
                project_root=self.project,
                capability_receipt=cross_run_receipt,
                evidence_root_binding=result["evidence_root_bindings"][
                    "PUBLIC_SOURCE"
                ],
                qualification_authority=self.authority,
            )

        public_root = result["evidence_roots"]["PUBLIC_SOURCE"]
        early_root = build_v32_actual_capability_evidence_root_v1(
            root_id="actual-root:public-source:early-time",
            capability="PUBLIC_SOURCE",
            qualification_run_id=self.authority["run_id"],
            target_run_id=self.authority["target_run_id"],
            qualification_authority_digest=self.authority[AUTHORITY_DIGEST_FIELD],
            attempt_reservation_binding=public_root[
                "attempt_reservation_binding"
            ],
            started_at=self.authority["recorded_at"],
            completed_at=public_root["completed_at"],
            replay_descriptor=public_root["replay_descriptor"],
            terminal_evidence_binding=public_root["terminal_evidence_binding"],
        )
        schema_id, digest_field = EVIDENCE_ROOT_SPECS["PUBLIC_SOURCE"]
        early_binding = self.store.persist_typed_document(
            relative_ref="qualification-evidence/negative/early-public-root.json",
            document=early_root,
            schema_id=schema_id,
            digest_field=digest_field,
        )
        early_receipt = build_v32_actual_capability_receipt_v1(
            capability="PUBLIC_SOURCE",
            receipt_id="actual-capability:public-source:early-time",
            qualification_run_id=self.authority["run_id"],
            target_run_id=self.authority["target_run_id"],
            started_at=early_root["started_at"],
            completed_at=early_root["completed_at"],
            qualification_authority_binding=self.authority_binding,
            evidence_root_binding=early_binding,
        )
        with self.assertRaisesRegex(ValueError, "ROOT_TIME_INVALID"):
            registry["PUBLIC_SOURCE"](
                project_root=self.project,
                capability_receipt=early_receipt,
                evidence_root_binding=early_binding,
                qualification_authority=self.authority,
            )

        with self.assertRaisesRegex(
            V32ActualCapabilityQualificationError,
            "ATTEMPT_FAILED:PUBLIC_SOURCE",
        ):
            self._run_qualification()
        self.assertEqual(1, self.public.calls)

        terminal_path = self.project / public_root["terminal_evidence_binding"][
            "path"
        ]
        terminal_path.write_bytes(terminal_path.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            registry["PUBLIC_SOURCE"](
                project_root=self.project,
                capability_receipt=public_receipt,
                evidence_root_binding=result["evidence_root_bindings"][
                    "PUBLIC_SOURCE"
                ],
                qualification_authority=self.authority,
            )

    def test_missing_port_fails_before_any_attempt(self):
        ports = dict(self.ports)
        ports.pop("OUTCOME_MONITOR")
        with self.assertRaisesRegex(
            V32ActualCapabilityQualificationError, "ATTEMPT_PORTS_INVALID"
        ):
            run_v32_actual_capability_qualification(
                project_root=self.project,
                evidence_store=self.store,
                qualification_id="missing-port",
                qualification_authority=self.authority,
                qualification_authority_binding=self.authority_binding,
                attempt_ports=ports,
                clock=SequenceClock(["2026-08-07T00:13:59Z"]),
            )
        self.assertEqual((0, 0, 0), (self.public.calls, self.codex.calls, self.outcome.calls))

    def test_missing_replay_registry_fails_before_any_attempt(self):
        with patch.object(
            self.store,
            "full_replay_registry",
            return_value={"PUBLIC_SOURCE": object()},
        ), self.assertRaisesRegex(
            V32ActualCapabilityQualificationError,
            "FULL_REPLAY_REGISTRY_INVALID",
        ):
            self._run_qualification()
        self.assertEqual(
            (0, 0, 0), (self.public.calls, self.codex.calls, self.outcome.calls)
        )

    def test_weak_replay_result_stops_after_first_attempt(self):
        registry = build_v32_actual_capability_full_replay_registry()
        registry["PUBLIC_SOURCE"] = lambda **_: {
            "capability": "PUBLIC_SOURCE",
            "evidence_root_semantic_digest": "0" * 64,
            "full_replay_verified": False,
            "replay_network_calls": 0,
        }
        with patch.object(
            self.store,
            "full_replay_registry",
            return_value=registry,
        ), self.assertRaisesRegex(
            V32ActualCapabilityQualificationError,
            "FULL_REPLAY_FAILED:PUBLIC_SOURCE",
        ):
            self._run_qualification()
        self.assertEqual(
            (1, 0, 0), (self.public.calls, self.codex.calls, self.outcome.calls)
        )


if __name__ == "__main__":
    unittest.main()
