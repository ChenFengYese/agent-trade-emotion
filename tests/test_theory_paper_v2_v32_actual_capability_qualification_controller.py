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
from tests.test_theory_paper_v2_v32_actual_capability_qualification import (
    SequenceClock,
    write_authority,
)
from trade_system.theory_paper_v2.application import (
    v32_actual_capability_qualification_controller as controller_module,
)
from trade_system.theory_paper_v2.application.v32_actual_capability_qualification_controller import (
    LocalV32ActualCapabilityQualificationControllerStore,
    V32ActualCapabilityQualificationControllerError,
    advance_v32_actual_capability_qualification_controller_once,
    build_v32_actual_capability_controller_genesis_v1,
    stable_v32_materialization_failure_codes_v1,
)
from trade_system.theory_paper_v2.application.v32_outcome_tick_composition import (
    initialize_v32_outcome_tick_runtime,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_context_compaction import (
    MAX_MEMBERS,
    V32ContextCompactionError,
    build_v32_context_compaction_bundle_v1,
)
from trade_system.theory_paper_v2.domain.v32_actual_capability_attempt_progress import (
    V32ActualCapabilityAttemptProgressError,
    verify_v32_actual_capability_attempt_progress_v1,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    build_v32_active_authority_projection,
)
from trade_system.theory_paper_v2.domain.governance.v32_authorization import (
    AUTHORITY_DIGEST_FIELD,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    V32_QUALIFICATION_CONTEXT_PROFILE,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_qualification_monitor_probe import (
    build_v32_qualification_monitor_probe_v1,
)
from trade_system.theory_paper_v2.domain.v32_tick_supervisor import (
    CHECKPOINT_DIGEST_FIELD as SUPERVISOR_CHECKPOINT_DIGEST_FIELD,
    build_v32_analysis_tick_permit,
    build_v32_tick_supervisor_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_actual_capability_attempt_ports import (
    V32ActualCapabilityAttemptAdapterError,
    V32CurrentCodexQualificationAttemptPort,
    V32OutcomeMonitorQualificationAttemptPort,
    V32PublicSourceQualificationAttemptPort,
    verify_v32_current_codex_attempt_time_v1,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_actual_capability_replay import (
    EVIDENCE_ROOT_SPECS,
    LocalV32ActualCapabilityEvidenceStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_outcome_tick_store import (
    LocalV32OutcomeTickStore,
    build_v32_outcome_tick_checkpoint,
)
from trade_system.theory_paper_v2.infrastructure.v32_okx_public_outcome_adapter import (
    OKX_V32_MARK_PRICE_URL,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    TRANSPORT_FAILURE_SCHEMA_ID,
    V32PublicSourceCollectorError,
)
from trade_system.theory_paper_v2.infrastructure.v32_tick_supervisor_store import (
    LocalV32TickSupervisorStore,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_monitor_probe_store import (
    LocalV32QualificationMonitorProbeStore,
)
from trade_system.theory_paper_v2.infrastructure.authority.v32_qualification_materializer import (
    LocalV32QualificationMaterialStore,
)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class PendingPort:
    def __init__(self) -> None:
        self.calls = 0
        self.digest = canonical_digest({"pending": "same-logical-attempt"})

    def advance_once(self, **kwargs):
        self.calls += 1
        return {
            "capability": kwargs["reservation"]["capability"],
            "status": "PENDING",
            "state_changed": False,
            "pending_reason": "WAITING_EXTERNAL_DELIVERY",
            "resume_token": None,
            "resume_requested_at": None,
            "observed_state_digest": self.digest,
            "evidence_root": None,
            "evidence_root_binding": None,
            "attempt_count": 1,
            "retry_performed": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }


class MalformedCompletePort:
    def __init__(self) -> None:
        self.calls = 0

    def advance_once(self, **kwargs):
        self.calls += 1
        digest = "a" * 64
        return {
            "capability": kwargs["reservation"]["capability"],
            "status": "COMPLETE",
            "state_changed": True,
            "pending_reason": None,
            "resume_token": None,
            "resume_requested_at": None,
            "observed_state_digest": digest,
            "evidence_root": {
                "capability": kwargs["reservation"]["capability"]
            },
            "evidence_root_binding": {"semantic_digest": digest},
            "attempt_count": 1,
            "retry_performed": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        }


class ForgedFullShapeCompletePort(MalformedCompletePort):
    def advance_once(self, **kwargs):
        result = super().advance_once(**kwargs)
        result["evidence_root_binding"] = {
            "path": "runtime/missing-evidence-root.json",
            "schema_id": "forged-root-schema",
            "digest_field": "forged_root_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "c" * 64,
        }
        return result


class TypedFailingPort:
    def __init__(self) -> None:
        self.calls = 0

    def advance_once(self, **kwargs):
        self.calls += 1
        cause = OSError("V32_OKX_TRANSPORT_SERVER_TIME_FAILED")
        cause.failure_code = "V32_OKX_TRANSPORT_SERVER_TIME_FAILED"
        cause.failure_context = {
            "failure_codes": [
                "V32_OKX_TRANSPORT_SERVER_TIME_FAILED",
                "PUBLIC_TIMEOUT",
            ]
        }
        top = ValueError("V32_PUBLIC_SOURCE_TRANSPORT_FAILED")
        top.failure_code = "V32_PUBLIC_SOURCE_TRANSPORT_FAILED"
        top.failure_evidence_binding = {
            "path": "runtime/source/transport-failure.json",
            "schema_id": "theory_paper_v32_public_source_transport_failure_v1",
            "digest_field": "public_source_transport_failure_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "b" * 64,
        }
        raise top from cause

    def verify_failure_evidence_binding(self, binding_value):
        return dict(binding_value)


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


class V32ActualCapabilityQualificationControllerTests(unittest.TestCase):
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
        self.authority_binding = write_authority(self.project, self.authority)
        self.evidence = LocalV32ActualCapabilityEvidenceStore(
            self.project, "qualification-evidence"
        )

    def reserve(self, capability: str, at: str):
        return self.evidence.reserve_attempt(
            capability=capability,
            qualification_run_id=self.authority["run_id"],
            target_run_id=self.authority["target_run_id"],
            qualification_authority_digest=self.authority[
                AUTHORITY_DIGEST_FIELD
            ],
            reserved_at=at,
        )

    def _advance_controller(
        self,
        *,
        controller,
        ports,
        clock,
        controller_id="progress-failure-controller",
        qualification_id="progress-failure-qualification",
    ):
        return advance_v32_actual_capability_qualification_controller_once(
            controller_store=controller,
            evidence_store=self.evidence,
            controller_id=controller_id,
            qualification_id=qualification_id,
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            attempt_ports=ports,
            clock=clock,
        )

    def _current_codex_pending_controller(self, root: str):
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, root
        )
        genesis = build_v32_actual_capability_controller_genesis_v1(
            controller_id=f"controller::{root}",
            qualification_id=f"qualification::{root}",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            evidence_store_root=self.evidence.root_relative_ref,
            created_at="2026-08-07T00:13:30Z",
        )
        controller.append(genesis)
        public = self.reserve("PUBLIC_SOURCE", "2026-08-07T00:13:31Z")
        states = {
            name: dict(genesis["capability_states"][name])
            for name in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        states["PUBLIC_SOURCE"] = {
            **states["PUBLIC_SOURCE"],
            "status": "PENDING",
            "reservation_binding": public["reservation_binding"],
            "pending_reason": "ATTEMPT_RESERVED_NOT_STARTED",
        }
        reserved = controller_module._next_checkpoint(
            genesis,
            updated_at="2026-08-07T00:13:31Z",
            states=states,
            boundary="ATTEMPT_RESERVED:PUBLIC_SOURCE",
        )
        controller.append(reserved)
        states = {
            name: dict(reserved["capability_states"][name])
            for name in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        states["PUBLIC_SOURCE"] = {
            **states["PUBLIC_SOURCE"],
            "status": "COMPLETE",
            "evidence_root_binding": {
                "path": "qualification-evidence/roots/public-source.json",
                "schema_id": "public-source-root",
                "digest_field": "public_source_root_digest",
                "semantic_digest": "1" * 64,
                "physical_sha256": "2" * 64,
            },
            "pending_reason": None,
            "observed_state_digest": "1" * 64,
            "adapter_advances": 1,
        }
        completed = controller_module._next_checkpoint(
            reserved,
            updated_at="2026-08-07T00:13:32Z",
            states=states,
            boundary="ATTEMPT_COMPLETED:PUBLIC_SOURCE",
        )
        controller.append(completed)
        current = self.reserve("CURRENT_CODEX", "2026-08-07T00:13:33Z")
        states = {
            name: dict(completed["capability_states"][name])
            for name in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        states["CURRENT_CODEX"] = {
            **states["CURRENT_CODEX"],
            "status": "PENDING",
            "reservation_binding": current["reservation_binding"],
            "pending_reason": "ATTEMPT_RESERVED_NOT_STARTED",
        }
        pending = controller_module._next_checkpoint(
            completed,
            updated_at="2026-08-07T00:13:33Z",
            states=states,
            boundary="ATTEMPT_RESERVED:CURRENT_CODEX",
        )
        controller.append(pending)
        return controller, current

    def _material_prefix(self, root: str):
        store = LocalV32QualificationMaterialStore(self.project, root)
        document = self_digest(
            {
                "schema_id": "test_v32_material_predecessor_v1",
                "role": "source_capture",
            },
            "test_material_predecessor_digest",
        )
        store.persist("source_capture", document)
        return store, store.predecessor_bindings()

    def _write_bound_document(
        self, relative_ref: str, *, schema_id: str, digest_field: str
    ) -> dict[str, str]:
        document = self_digest(
            {"schema_id": schema_id, "state": "POST_WRITE_DURABLE"},
            digest_field,
        )
        payload = canonical_bytes(document) + b"\n"
        path = self.project / relative_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return {
            "path": relative_ref,
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": document[digest_field],
            "physical_sha256": hashlib.sha256(payload).hexdigest(),
        }

    def test_malformed_complete_binding_fails_closed_without_adapter_retry(self):
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, "malformed-progress-controller"
        )
        port = MalformedCompletePort()
        ports = {
            capability: port
            for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        clock = SequenceClock(
            [
                "2026-08-07T00:13:30Z",
                "2026-08-07T00:13:59Z",
                "2026-08-07T00:14:01Z",
            ]
        )
        self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="malformed-progress-controller",
        )
        self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="malformed-progress-controller",
        )
        failed = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="malformed-progress-controller",
        )
        terminal = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="malformed-progress-controller",
        )
        self.assertEqual(1, port.calls)
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual("FAILED_CLOSED", failed["checkpoint"]["status"])
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(failed["checkpoint"], terminal["checkpoint"])

    def test_real_context_capacity_failure_seals_exact_material_prefix_and_never_retries(self):
        controller, current = self._current_codex_pending_controller(
            "material-capacity-controller"
        )
        material, predecessors = self._material_prefix("material-capacity")
        oversized = self_digest(
            {
                "schema_id": "test_oversized_context_packet_v1",
                "values": list(range(MAX_MEMBERS + 1)),
            },
            "test_oversized_context_packet_digest",
        )
        packet_bytes = canonical_bytes(oversized)
        with self.assertRaises(V32ContextCompactionError) as raised:
            build_v32_context_compaction_bundle_v1(
                run_id=self.authority["run_id"],
                cycle_index=1,
                created_at="2026-08-07T00:13:34Z",
                source_artifacts=[
                    {
                        "artifact_binding": {
                            "relative_ref": "fixtures/oversized-packet.json",
                            "schema_id": oversized["schema_id"],
                            "digest_field": "test_oversized_context_packet_digest",
                            "semantic_digest": oversized[
                                "test_oversized_context_packet_digest"
                            ],
                            "physical_sha256": hashlib.sha256(
                                packet_bytes + b"\n"
                            ).hexdigest(),
                        },
                        "canonical_bytes": len(packet_bytes),
                    }
                ],
                original_documents=[oversized],
        )
        self.assertEqual("CONTEXT_CAPACITY_UNRESOLVED", str(raised.exception))
        mailbox_root = "material-capacity-mailbox"
        mailbox_binding = self._write_bound_document(
            f"{mailbox_root}/v32-current-root-agent-mailbox-v1/"
            "cycles/0001/checkpoint.json",
            schema_id="test_mailbox_checkpoint_v1",
            digest_field="test_mailbox_checkpoint_digest",
        )
        orphan_request_binding = self._write_bound_document(
            f"{mailbox_root}/v32-current-root-agent-mailbox-v1/"
            "cycles/0001/proposal/request.json",
            schema_id="test_orphan_request_v1",
            digest_field="test_orphan_request_digest",
        )
        probe_root = "material-capacity-probe"
        probe_binding = self._write_bound_document(
            f"{probe_root}/v32-qualification-monitor-probe-v1/schedule.json",
            schema_id="test_probe_schedule_v1",
            digest_field="test_probe_schedule_digest",
        )
        failed = controller.seal_materialization_failure(
            materialization_stage="PERSIST:PROPOSAL_INPUT",
            failure_codes=stable_v32_materialization_failure_codes_v1(
                raised.exception
            ),
            failure_time_status="OBSERVED",
            failed_at="2026-08-07T00:13:35Z",
            last_known_at="2026-08-07T00:13:35Z",
            qualification_authority_binding=self.authority_binding,
            attempt_reservation_binding=current["reservation_binding"],
            material_store_root=material.root_relative_ref,
            material_prefix_status="VERIFIED_EXACT",
            material_scan_failure_codes=(),
            material_predecessor_bindings=predecessors,
            mailbox_store_root=mailbox_root,
            mailbox_prefix_status="VERIFIED_EXACT",
            mailbox_scan_failure_codes=(),
            mailbox_prefix_bindings=[mailbox_binding, orphan_request_binding],
            probe_store_root=probe_root,
            probe_prefix_status="VERIFIED_EXACT",
            probe_scan_failure_codes=(),
            probe_schedule_binding=probe_binding,
        )
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual(
            "CONTEXT_CAPACITY_UNRESOLVED",
            failed["failure_receipt"]["failure_codes"][0],
        )
        self.assertEqual(
            predecessors,
            failed["failure_receipt"]["material_predecessor_bindings"],
        )
        self.assertEqual(
            current["reservation_binding"],
            failed["failure_receipt"]["attempt_reservation_binding"],
        )
        self.assertEqual(
            [mailbox_binding, orphan_request_binding],
            failed["failure_receipt"]["mailbox_prefix_bindings"],
        )
        self.assertEqual(
            probe_binding,
            failed["failure_receipt"]["probe_schedule_binding"],
        )
        ports = {
            capability: PendingPort()
            for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        terminal = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=SequenceClock([]),
            controller_id="controller::material-capacity-controller",
            qualification_id="qualification::material-capacity-controller",
        )
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(0, sum(port.calls for port in ports.values()))
        altered = dict(failed["failure_evidence_binding"])
        altered["physical_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            V32ActualCapabilityQualificationControllerError,
            "MATERIAL_FAILURE_BINDING_INVALID",
        ):
            controller.verify_materialization_failure_binding(
                failed_checkpoint=failed["checkpoint"],
                binding_value=altered,
            )
        self._write_bound_document(
            f"{mailbox_root}/v32-current-root-agent-mailbox-v1/"
            "cycles/0001/proposal/late-orphan.json",
            schema_id="test_late_orphan_v1",
            digest_field="test_late_orphan_digest",
        )
        with self.assertRaisesRegex(
            V32ActualCapabilityQualificationControllerError,
            "MATERIAL_FAILURE_MAILBOX_INVALID",
        ):
            controller.verify_materialization_failure_binding(
                failed_checkpoint=failed["checkpoint"],
                binding_value=failed["failure_evidence_binding"],
            )

    def test_arbitrary_materializer_exception_is_permanent_and_typed_by_class(self):
        controller, current = self._current_codex_pending_controller(
            "material-arbitrary-controller"
        )
        material, predecessors = self._material_prefix("material-arbitrary")
        exc = RuntimeError("arbitrary prose must not enter durable state")
        failed = controller.seal_materialization_failure(
            materialization_stage="PERSIST:AGENT_MARKET_GRAPH_VIEW",
            failure_codes=stable_v32_materialization_failure_codes_v1(exc),
            failure_time_status="UNKNOWN_CLOCK_UNAVAILABLE",
            failed_at=None,
            last_known_at="2026-08-07T00:13:33Z",
            qualification_authority_binding=self.authority_binding,
            attempt_reservation_binding=current["reservation_binding"],
            material_store_root=material.root_relative_ref,
            material_prefix_status="VERIFIED_EXACT",
            material_scan_failure_codes=(),
            material_predecessor_bindings=predecessors,
            mailbox_store_root="material-arbitrary-mailbox",
            mailbox_prefix_status="UNKNOWN_REPLAY_FAILED",
            mailbox_scan_failure_codes=("MAILBOX_PREFIX_REPLAY_FAILED",),
            mailbox_prefix_bindings=[],
            probe_store_root="material-arbitrary-probe",
            probe_prefix_status="VERIFIED_EXACT",
            probe_scan_failure_codes=(),
            probe_schedule_binding=None,
        )
        replay = controller.seal_materialization_failure(
            materialization_stage="PERSIST:AGENT_MARKET_GRAPH_VIEW",
            failure_codes=("SHOULD_NOT_REPLACE_DURABLE_FAILURE",),
            failure_time_status="OBSERVED",
            failed_at="2026-08-07T00:13:36Z",
            last_known_at="2026-08-07T00:13:36Z",
            qualification_authority_binding=self.authority_binding,
            attempt_reservation_binding=current["reservation_binding"],
            material_store_root=material.root_relative_ref,
            material_prefix_status="VERIFIED_EXACT",
            material_scan_failure_codes=(),
            material_predecessor_bindings=predecessors,
            mailbox_store_root="material-arbitrary-mailbox",
            mailbox_prefix_status="VERIFIED_EXACT",
            mailbox_scan_failure_codes=(),
            mailbox_prefix_bindings=[],
            probe_store_root="material-arbitrary-probe",
            probe_prefix_status="VERIFIED_EXACT",
            probe_scan_failure_codes=(),
            probe_schedule_binding=None,
        )
        self.assertEqual(
            ["UNCLASSIFIED_RUNTIMEERROR"],
            failed["failure_receipt"]["failure_codes"],
        )
        self.assertEqual(
            "UNKNOWN_CLOCK_UNAVAILABLE",
            failed["failure_receipt"]["failure_time_status"],
        )
        self.assertIsNone(failed["failure_receipt"]["failed_at"])
        self.assertEqual(
            "UNKNOWN_REPLAY_FAILED",
            failed["failure_receipt"]["mailbox_prefix_status"],
        )
        self.assertEqual(
            ["MAILBOX_PREFIX_REPLAY_FAILED"],
            failed["failure_receipt"]["mailbox_scan_failure_codes"],
        )
        self.assertEqual(
            "2026-08-07T00:13:33Z", failed["checkpoint"]["updated_at"]
        )
        self.assertNotIn("arbitrary prose", json.dumps(failed))
        self.assertEqual("NO_ADVANCE_TERMINAL", replay["boundary_kind"])
        self.assertEqual(failed["checkpoint"], replay["checkpoint"])

    def test_failed_closed_transition_accepts_only_owned_failure_boundaries(self):
        controller, _ = self._current_codex_pending_controller(
            "illegal-failed-transition-controller"
        )
        before = controller.load()
        assert before is not None
        cases = (
            controller_module._next_checkpoint(
                before,
                updated_at="2026-08-07T00:13:34Z",
                status="FAILED_CLOSED",
                boundary="UNOWNED_FAILED_CLOSED",
                failure_code="UNOWNED_FAILURE",
            ),
            controller_module._next_checkpoint(
                before,
                updated_at="2026-08-07T00:13:34Z",
                status="FAILED_CLOSED",
                boundary="ATTEMPT_FAILED_CLOSED:OUTCOME_MONITOR",
                failure_code="ATTEMPT_FAILED:OUTCOME_MONITOR:INJECTED",
            ),
            controller_module._next_checkpoint(
                before,
                updated_at="2026-08-07T00:13:34Z",
                status="FAILED_CLOSED",
                boundary="MATERIALIZATION_FAILED_CLOSED:CURRENT_CODEX",
                failure_code="MATERIALIZATION_FAILED:CURRENT_CODEX:INJECTED",
                failure_evidence_binding=None,
            ),
        )
        for candidate in cases:
            with self.subTest(
                boundary=candidate["last_boundary_kind"]
            ), self.assertRaisesRegex(
                V32ActualCapabilityQualificationControllerError,
                "FAILURE_TRANSITION_INVALID",
            ):
                controller_module._verify_transition(before, candidate)

    def test_typed_failure_chain_is_stable_and_terminal_without_exception_prose(self):
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, "typed-failure-controller"
        )
        port = TypedFailingPort()
        ports = {
            capability: port
            for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        clock = SequenceClock(
            [
                "2026-08-07T00:13:30Z",
                "2026-08-07T00:13:59Z",
                "2026-08-07T00:14:01Z",
            ]
        )
        for _ in range(2):
            self._advance_controller(
                controller=controller,
                ports=ports,
                clock=clock,
                controller_id="typed-failure-controller",
            )
        failed = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="typed-failure-controller",
        )
        terminal = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="typed-failure-controller",
        )
        self.assertEqual(1, port.calls)
        self.assertEqual(
            "ATTEMPT_FAILED:PUBLIC_SOURCE:"
            "V32_PUBLIC_SOURCE_TRANSPORT_FAILED:"
            "V32_OKX_TRANSPORT_SERVER_TIME_FAILED:PUBLIC_TIMEOUT",
            failed["checkpoint"]["failure_code"],
        )
        self.assertNotIn("ValueError", failed["checkpoint"]["failure_code"])
        self.assertEqual(
            {
                "path": "runtime/source/transport-failure.json",
                "schema_id": (
                    "theory_paper_v32_public_source_transport_failure_v1"
                ),
                "digest_field": "public_source_transport_failure_digest",
                "semantic_digest": "a" * 64,
                "physical_sha256": "b" * 64,
            },
            failed["checkpoint"]["failure_evidence_binding"],
        )
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(1, port.calls)

    def test_resume_fields_are_paired_and_complete_clears_resume_state(self):
        pending = PendingPort().advance_once(
            reservation={"capability": "PUBLIC_SOURCE"}
        )
        pending["resume_token"] = "b" * 64
        with self.assertRaises(V32ActualCapabilityAttemptProgressError):
            verify_v32_actual_capability_attempt_progress_v1(
                pending,
                evidence_root_verifier=self.evidence.verify_evidence_root,
            )
        complete = MalformedCompletePort().advance_once(
            reservation={"capability": "PUBLIC_SOURCE"}
        )
        complete["evidence_root_binding"] = {
            "path": "runtime/root.json",
            "schema_id": "root-schema",
            "digest_field": "root_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "c" * 64,
        }
        complete["resume_token"] = "b" * 64
        complete["resume_requested_at"] = "2026-08-07T00:14:00Z"
        with self.assertRaises(V32ActualCapabilityAttemptProgressError):
            verify_v32_actual_capability_attempt_progress_v1(
                complete,
                evidence_root_verifier=lambda _: "a" * 64,
            )

    def test_forged_full_shape_root_binding_fails_closed_before_next_capability(self):
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, "forged-root-controller"
        )
        port = ForgedFullShapeCompletePort()
        ports = {
            capability: port
            for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        clock = SequenceClock(
            [
                "2026-08-07T00:13:30Z",
                "2026-08-07T00:13:59Z",
                "2026-08-07T00:14:01Z",
            ]
        )
        self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="forged-root-controller",
        )
        self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="forged-root-controller",
        )
        with patch.object(
            self.evidence, "verify_evidence_root", return_value="a" * 64
        ) as root_verifier:
            failed = self._advance_controller(
                controller=controller,
                ports=ports,
                clock=clock,
                controller_id="forged-root-controller",
            )
        terminal = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="forged-root-controller",
        )
        self.assertEqual(1, port.calls)
        self.assertEqual(1, root_verifier.call_count)
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual(
            "READY",
            failed["checkpoint"]["capability_states"]["CURRENT_CODEX"]["status"],
        )
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(failed["checkpoint"], terminal["checkpoint"])

    def test_post_progress_checkpoint_failure_is_permanently_failed_closed(self):
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, "post-progress-failure-controller"
        )
        port = PendingPort()
        ports = {
            capability: port
            for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        clock = SequenceClock(
            [
                "2026-08-07T00:13:30Z",
                "2026-08-07T00:13:59Z",
                "2026-08-07T00:14:01Z",
            ]
        )
        self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="post-progress-failure-controller",
        )
        self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="post-progress-failure-controller",
        )
        real_next = controller_module._next_checkpoint

        def fail_normal_progress(*args, **kwargs):
            if kwargs.get("boundary") == "ATTEMPT_PENDING:PUBLIC_SOURCE":
                raise ValueError("injected post-progress checkpoint failure")
            return real_next(*args, **kwargs)

        with patch.object(
            controller_module,
            "_next_checkpoint",
            side_effect=fail_normal_progress,
        ):
            failed = self._advance_controller(
                controller=controller,
                ports=ports,
                clock=clock,
                controller_id="post-progress-failure-controller",
            )
        terminal = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=clock,
            controller_id="post-progress-failure-controller",
        )
        self.assertEqual(1, port.calls)
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual("FAILED_CLOSED", controller.load()["status"])
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(failed["checkpoint"], terminal["checkpoint"])

    def test_controller_persists_pending_without_reserving_a_second_attempt(self):
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, "qualification-controller"
        )
        port = PendingPort()
        ports = {capability: port for capability in (
            "PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR"
        )}
        clock = SequenceClock(
            [
                "2026-08-07T00:13:30Z",
                "2026-08-07T00:13:59Z",
                "2026-08-07T00:14:01Z",
            ]
        )
        first = advance_v32_actual_capability_qualification_controller_once(
            controller_store=controller,
            evidence_store=self.evidence,
            controller_id="qualification-controller-test",
            qualification_id="qualification-controller-test",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            attempt_ports=ports,
            clock=clock,
        )
        second = advance_v32_actual_capability_qualification_controller_once(
            controller_store=controller,
            evidence_store=self.evidence,
            controller_id="qualification-controller-test",
            qualification_id="qualification-controller-test",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            attempt_ports=ports,
            clock=clock,
        )
        third = advance_v32_actual_capability_qualification_controller_once(
            controller_store=controller,
            evidence_store=self.evidence,
            controller_id="qualification-controller-test",
            qualification_id="qualification-controller-test",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            attempt_ports=ports,
            clock=clock,
        )
        fourth = advance_v32_actual_capability_qualification_controller_once(
            controller_store=controller,
            evidence_store=self.evidence,
            controller_id="qualification-controller-test",
            qualification_id="qualification-controller-test",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            attempt_ports=ports,
            clock=clock,
        )
        self.assertEqual("CONTROLLER_INITIALIZED", first["boundary_kind"])
        self.assertEqual("ATTEMPT_RESERVED:PUBLIC_SOURCE", second["boundary_kind"])
        self.assertEqual("ATTEMPT_PENDING:PUBLIC_SOURCE", third["boundary_kind"])
        self.assertEqual("NO_ADVANCE_NOT_DUE", fourth["boundary_kind"])
        self.assertEqual(2, port.calls)
        self.assertEqual(2, controller.load()["revision"])
        self.assertEqual(
            1,
            len(list((self.project / "qualification-evidence/attempts").glob("*.json"))),
        )

    def _ready_to_seal_checkpoint(
        self,
    ) -> tuple[LocalV32ActualCapabilityQualificationControllerStore, dict]:
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, "seal-failure-controller"
        )
        checkpoint = build_v32_actual_capability_controller_genesis_v1(
            controller_id="seal-failure-controller",
            qualification_id="seal-failure-qualification",
            qualification_authority=self.authority,
            qualification_authority_binding=self.authority_binding,
            evidence_store_root=self.evidence.root_relative_ref,
            created_at="2026-08-07T00:13:30Z",
        )
        controller.append(checkpoint)
        times = {
            "PUBLIC_SOURCE": ("2026-08-07T00:13:59Z", "2026-08-07T00:14:10Z"),
            "CURRENT_CODEX": ("2026-08-07T00:15:59Z", "2026-08-07T00:17:20Z"),
            "OUTCOME_MONITOR": ("2026-08-07T00:59:59Z", "2026-08-07T01:00:02Z"),
        }
        for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR"):
            reserved_at, completed_at = times[capability]
            reserved = self.reserve(capability, reserved_at)
            states = {
                name: dict(checkpoint["capability_states"][name])
                for name in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
            }
            states[capability] = {
                "status": "PENDING",
                "reservation_binding": reserved["reservation_binding"],
                "evidence_root_binding": None,
                "resume_token": None,
                "resume_requested_at": None,
                "observed_state_digest": None,
                "pending_reason": "ATTEMPT_RESERVED_NOT_STARTED",
                "adapter_advances": 0,
            }
            checkpoint = controller_module._next_checkpoint(
                checkpoint,
                updated_at=reserved_at,
                states=states,
                boundary=f"ATTEMPT_RESERVED:{capability}",
            )
            controller.append(checkpoint)
            schema_id, digest_field = EVIDENCE_ROOT_SPECS[capability]
            root_binding = {
                "path": self.evidence.root_ref(capability),
                "schema_id": schema_id,
                "digest_field": digest_field,
                "semantic_digest": "d" * 64,
                "physical_sha256": "e" * 64,
            }
            states = {
                name: dict(checkpoint["capability_states"][name])
                for name in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
            }
            states[capability] = {
                "status": "COMPLETE",
                "reservation_binding": reserved["reservation_binding"],
                "evidence_root_binding": root_binding,
                "resume_token": None,
                "resume_requested_at": None,
                "observed_state_digest": "f" * 64,
                "pending_reason": None,
                "adapter_advances": 1,
            }
            checkpoint = controller_module._next_checkpoint(
                checkpoint,
                updated_at=completed_at,
                states=states,
                boundary=f"ATTEMPT_COMPLETED:{capability}",
            )
            controller.append(checkpoint)
        self.assertEqual("READY_TO_SEAL", checkpoint["status"])
        return controller, checkpoint

    def test_seal_failure_is_permanent_failed_closed_and_never_retried(self):
        controller, ready = self._ready_to_seal_checkpoint()
        ports = {
            capability: PendingPort()
            for capability in ("PUBLIC_SOURCE", "CURRENT_CODEX", "OUTCOME_MONITOR")
        }
        recovered = {
            "evidence_root": {},
            "evidence_root_binding": {},
        }
        with patch.object(
            self.evidence, "load_evidence_root", return_value=recovered
        ), patch.object(
            controller_module,
            "seal_v32_actual_capability_qualification_from_completed_attempts",
            side_effect=RuntimeError("injected seal failure"),
        ) as seal:
            failed = advance_v32_actual_capability_qualification_controller_once(
                controller_store=controller,
                evidence_store=self.evidence,
                controller_id="seal-failure-controller",
                qualification_id="seal-failure-qualification",
                qualification_authority=self.authority,
                qualification_authority_binding=self.authority_binding,
                attempt_ports=ports,
                clock=SequenceClock(["2026-08-07T01:00:03Z"]),
            )
            terminal = advance_v32_actual_capability_qualification_controller_once(
                controller_store=controller,
                evidence_store=self.evidence,
                controller_id="seal-failure-controller",
                qualification_id="seal-failure-qualification",
                qualification_authority=self.authority,
                qualification_authority_binding=self.authority_binding,
                attempt_ports=ports,
                clock=SequenceClock([]),
            )
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual(
            "QUALIFICATION_SEAL_FAILED_CLOSED", failed["boundary_kind"]
        )
        self.assertEqual(ready["revision"] + 1, failed["checkpoint"]["revision"])
        self.assertEqual("FAILED_CLOSED", terminal["runtime_status"])
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(failed["checkpoint"], terminal["checkpoint"])
        self.assertEqual(1, seal.call_count)
        self.assertEqual(
            "QUALIFICATION_SEAL_FAILED:UNCLASSIFIED_STRUCTURAL_FAILURE",
            failed["checkpoint"]["failure_code"],
        )
        self.assertNotIn("RuntimeError", failed["checkpoint"]["failure_code"])
        self.assertEqual(
            ready["revision"] + 2,
            len(list(controller.events.glob("*.json"))),
        )

    def test_current_codex_adapter_exposes_external_mailbox_boundary(self):
        reserved = self.reserve("CURRENT_CODEX", "2026-08-07T00:15:59Z")
        adapter = V32CurrentCodexQualificationAttemptPort(
            project_root=self.project,
            evidence_store=self.evidence,
            mailbox_store_root="runtime/qualification-mailbox",
        )
        first = adapter.advance_once(
            qualification_authority=self.authority,
            reservation=reserved["reservation"],
            reservation_binding=reserved["reservation_binding"],
            resume_token=None,
            resume_requested_at=None,
        )
        second = adapter.advance_once(
            qualification_authority=self.authority,
            reservation=reserved["reservation"],
            reservation_binding=reserved["reservation_binding"],
            resume_token=None,
            resume_requested_at=None,
        )
        self.assertEqual("PENDING", first["status"])
        self.assertEqual("MAILBOX_READY_FOR_PROPOSAL", first["pending_reason"])
        self.assertEqual(first["observed_state_digest"], second["observed_state_digest"])
        self.assertFalse(second["state_changed"])

    def test_public_source_adapter_captures_once_and_recovers_root(self):
        base = datetime(2026, 8, 7, 0, 14, tzinfo=UTC)
        reserved = self.reserve("PUBLIC_SOURCE", "2026-08-07T00:13:59Z")
        values = [
            iso(base + timedelta(seconds=value))
            for value in (1, 2, 4, 5, 5.5, 7)
        ]
        with patch.object(source_fixture, "BASE", base), patch.object(
            source_fixture,
            "SERVER_MS",
            int((base + timedelta(seconds=3)).timestamp() * 1000),
        ):
            transport = source_fixture.BundleTransport(source_fixture.raw_bundle())
            adapter = V32PublicSourceQualificationAttemptPort(
                project_root=self.project,
                evidence_store=self.evidence,
                source_store_root="runtime/qualification-public-source",
                run_store_root="runtime/qualification-public-run",
                source_qualification_id="v32-controller-public-source",
                active_authority_projection=self.packet["support_documents"][
                    "active_authority_projection"
                ],
                transport=transport,
                clock=SequenceClock(values),
            )
            first = adapter.advance_once(
                qualification_authority=self.authority,
                reservation=reserved["reservation"],
                reservation_binding=reserved["reservation_binding"],
                resume_token=None,
                resume_requested_at=None,
            )
            second = adapter.advance_once(
                qualification_authority=self.authority,
                reservation=reserved["reservation"],
                reservation_binding=reserved["reservation_binding"],
                resume_token=None,
                resume_requested_at=None,
            )
        self.assertEqual("COMPLETE", first["status"])
        self.assertEqual("COMPLETE", second["status"])
        self.assertEqual(1, transport.calls)
        self.assertFalse(second["state_changed"])

    def test_public_semantic_failure_binding_replays_through_terminal_controller(self):
        base = datetime(2026, 8, 7, 0, 14, tzinfo=UTC)
        with patch.object(source_fixture, "BASE", base), patch.object(
            source_fixture,
            "SERVER_MS",
            int((base + timedelta(seconds=3)).timestamp() * 1000),
        ):
            bundle = source_fixture.raw_bundle()
            mark = next(
                row
                for row in bundle["components"]
                if row["component_id"] == "MARK_PRICE"
            )
            mark["body_utf8"] = source_fixture.okx_body(
                [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "markPx": "60000",
                        "ts": str(
                            int(
                                (base + timedelta(seconds=9)).timestamp()
                                * 1000
                            )
                        ),
                    }
                ]
            )
            transport = source_fixture.BundleTransport(bundle)
            public = V32PublicSourceQualificationAttemptPort(
                project_root=self.project,
                evidence_store=self.evidence,
                source_store_root="runtime/controller-failed-source",
                run_store_root="runtime/controller-failed-run",
                source_qualification_id="v32-controller-failed-source",
                active_authority_projection=self.packet["support_documents"][
                    "active_authority_projection"
                ],
                transport=transport,
                clock=SequenceClock(
                    [
                        iso(base + timedelta(seconds=1)),
                        iso(base + timedelta(seconds=2)),
                        iso(base + timedelta(seconds=4)),
                        iso(base + timedelta(seconds=5)),
                    ]
                ),
            )
            controller = LocalV32ActualCapabilityQualificationControllerStore(
                self.project, "public-semantic-failure-controller"
            )
            ports = {
                "PUBLIC_SOURCE": public,
                "CURRENT_CODEX": PendingPort(),
                "OUTCOME_MONITOR": PendingPort(),
            }
            controller_clock = SequenceClock(
                [
                    iso(base + timedelta(microseconds=100_000)),
                    iso(base + timedelta(microseconds=200_000)),
                    iso(base + timedelta(seconds=6)),
                ]
            )
            initialized = self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="public-semantic-failure-controller",
                qualification_id="public-semantic-failure-qualification",
            )
            self.assertEqual("CONTROLLER_INITIALIZED", initialized["boundary_kind"])
            self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="public-semantic-failure-controller",
                qualification_id="public-semantic-failure-qualification",
            )
            failed = self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="public-semantic-failure-controller",
                qualification_id="public-semantic-failure-qualification",
            )
            terminal = self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="public-semantic-failure-controller",
                qualification_id="public-semantic-failure-qualification",
            )
        binding = failed["checkpoint"]["failure_evidence_binding"]
        self.assertIsNotNone(binding)
        self.assertEqual(
            "theory_paper_v32_public_source_validation_failure_v1",
            binding["schema_id"],
        )
        self.assertTrue((self.project / binding["path"]).is_file())
        self.assertEqual("FAILED_CLOSED", failed["runtime_status"])
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(1, transport.calls)

        before = controller.load()
        capture_path = (
            self.project
            / "runtime/controller-failed-source/qualifications/"
            "v32-controller-failed-source/capture.json"
        )
        capture_path.write_bytes(b" " + capture_path.read_bytes())
        with self.assertRaises(
            V32ActualCapabilityQualificationControllerError
        ):
            self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="public-semantic-failure-controller",
                qualification_id="public-semantic-failure-qualification",
            )
        self.assertEqual(before, controller.load())
        self.assertEqual(1, transport.calls)

    def test_partial_public_attempt_recovers_failure_without_second_transport(self):
        base = datetime(2026, 8, 7, 0, 14, tzinfo=UTC)
        reserved = self.reserve("PUBLIC_SOURCE", iso(base - timedelta(seconds=1)))
        with patch.object(source_fixture, "BASE", base), patch.object(
            source_fixture,
            "SERVER_MS",
            int((base + timedelta(seconds=3)).timestamp() * 1000),
        ):
            bundle = source_fixture.raw_bundle()
            mark = next(
                row
                for row in bundle["components"]
                if row["component_id"] == "MARK_PRICE"
            )
            mark["body_utf8"] = source_fixture.okx_body(
                [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "markPx": "60000",
                        "ts": str(
                            int(
                                (base + timedelta(seconds=9)).timestamp()
                                * 1000
                            )
                        ),
                    }
                ]
            )
            transport = source_fixture.BundleTransport(bundle)
            kwargs = {
                "project_root": self.project,
                "evidence_store": self.evidence,
                "source_store_root": "runtime/partial-failed-source",
                "run_store_root": "runtime/partial-failed-run",
                "source_qualification_id": "v32-partial-failed-source",
                "active_authority_projection": self.packet[
                    "support_documents"
                ]["active_authority_projection"],
                "transport": transport,
            }
            first = V32PublicSourceQualificationAttemptPort(
                **kwargs,
                clock=SequenceClock(
                    [
                        iso(base + timedelta(seconds=1)),
                        iso(base + timedelta(seconds=2)),
                        iso(base + timedelta(seconds=4)),
                        iso(base + timedelta(seconds=5)),
                    ]
                ),
            )
            with self.assertRaises(V32PublicSourceCollectorError):
                first.advance_once(
                    qualification_authority=self.authority,
                    reservation=reserved["reservation"],
                    reservation_binding=reserved["reservation_binding"],
                    resume_token=None,
                    resume_requested_at=None,
                )
            second = V32PublicSourceQualificationAttemptPort(
                **kwargs,
                clock=lambda: (_ for _ in ()).throw(
                    AssertionError("recovery must not read wall clock")
                ),
            )
            with self.assertRaisesRegex(
                V32ActualCapabilityAttemptAdapterError,
                "RECOVERED_FAILED_CLOSED",
            ) as recovered:
                second.advance_once(
                    qualification_authority=self.authority,
                    reservation=reserved["reservation"],
                    reservation_binding=reserved["reservation_binding"],
                    resume_token=None,
                    resume_requested_at=None,
                )
        self.assertIsNotNone(
            recovered.exception.failure_evidence_binding
        )
        self.assertEqual(1, transport.calls)

    def test_partial_transport_failure_reaches_controller_and_rejects_authority_swap(self):
        base = datetime(2026, 8, 7, 0, 14, tzinfo=UTC)
        projection = self.packet["support_documents"][
            "active_authority_projection"
        ]
        source_root = "runtime/partial-transport-failed-source"
        run_root = "runtime/partial-transport-failed-run"
        source_qualification_id = "v32-partial-transport-failed-source"
        transport = source_fixture.TypedBodyFailureTransport()
        common = {
            "project_root": self.project,
            "evidence_store": self.evidence,
            "source_store_root": source_root,
            "run_store_root": run_root,
            "source_qualification_id": source_qualification_id,
            "active_authority_projection": projection,
            "transport": transport,
        }
        public = V32PublicSourceQualificationAttemptPort(
            **common,
            clock=SequenceClock(
                [
                    iso(base + timedelta(seconds=1)),
                    iso(base + timedelta(seconds=2)),
                    iso(base + timedelta(seconds=4)),
                    iso(base + timedelta(seconds=5)),
                    iso(base + timedelta(seconds=6)),
                ]
            ),
        )
        controller = LocalV32ActualCapabilityQualificationControllerStore(
            self.project, "partial-transport-failure-controller"
        )
        ports = {
            "PUBLIC_SOURCE": public,
            "CURRENT_CODEX": PendingPort(),
            "OUTCOME_MONITOR": PendingPort(),
        }
        controller_clock = SequenceClock(
            [
                iso(base + timedelta(microseconds=100_000)),
                iso(base + timedelta(microseconds=200_000)),
                iso(base + timedelta(seconds=6)),
            ]
        )
        with patch.object(source_fixture, "BASE", base):
            self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="partial-transport-failure-controller",
                qualification_id="partial-transport-failure-qualification",
            )
            self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="partial-transport-failure-controller",
                qualification_id="partial-transport-failure-qualification",
            )
            reservation = self.evidence.load_attempt_reservation(
                "PUBLIC_SOURCE"
            )
            self.assertIsNotNone(reservation)
            with self.assertRaises(V32PublicSourceCollectorError):
                public.advance_once(
                    qualification_authority=self.authority,
                    reservation=reservation["reservation"],
                    reservation_binding=reservation["reservation_binding"],
                    resume_token=None,
                    resume_requested_at=None,
                )

            recovered_public = V32PublicSourceQualificationAttemptPort(
                **common,
                clock=lambda: (_ for _ in ()).throw(
                    AssertionError("recovery must not read wall clock")
                ),
            )
            ports["PUBLIC_SOURCE"] = recovered_public
            failed = self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="partial-transport-failure-controller",
                qualification_id="partial-transport-failure-qualification",
            )

        binding = failed["checkpoint"]["failure_evidence_binding"]
        self.assertIsNotNone(binding)
        self.assertEqual(TRANSPORT_FAILURE_SCHEMA_ID, binding["schema_id"])
        self.assertIn(
            "V32_ACTUAL_PUBLIC_PORT_RECOVERED_FAILED_CLOSED",
            failed["checkpoint"]["failure_code"],
        )
        self.assertNotIn(
            "UNCLASSIFIED_STRUCTURAL_FAILURE",
            failed["checkpoint"]["failure_code"],
        )
        self.assertEqual(1, transport.calls)

        swapped_governing_binding = dict(
            projection["governing_authority_binding"]
        )
        swapped_governing_binding.update(
            {"semantic_digest": "f" * 64, "physical_sha256": "f" * 64}
        )
        swapped_projection = build_v32_active_authority_projection(
            run_id=projection["authorized_run_id"],
            recorded_at=projection["recorded_at"],
            experiment_contract_digest=projection[
                "experiment_contract_digest"
            ],
            governing_authority_binding=swapped_governing_binding,
        )
        swapped_public = V32PublicSourceQualificationAttemptPort(
            **{**common, "active_authority_projection": swapped_projection},
            clock=lambda: (_ for _ in ()).throw(
                AssertionError("terminal replay must not read wall clock")
            ),
        )
        before = controller.load()
        ports["PUBLIC_SOURCE"] = swapped_public
        with self.assertRaises(
            V32ActualCapabilityQualificationControllerError
        ):
            self._advance_controller(
                controller=controller,
                ports=ports,
                clock=controller_clock,
                controller_id="partial-transport-failure-controller",
                qualification_id="partial-transport-failure-qualification",
            )
        self.assertEqual(before, controller.load())
        self.assertEqual(1, transport.calls)

        ports["PUBLIC_SOURCE"] = recovered_public
        terminal = self._advance_controller(
            controller=controller,
            ports=ports,
            clock=controller_clock,
            controller_id="partial-transport-failure-controller",
            qualification_id="partial-transport-failure-qualification",
        )
        self.assertEqual("NO_ADVANCE_TERMINAL", terminal["boundary_kind"])
        self.assertEqual(1, transport.calls)

    def test_missing_public_failure_evidence_does_not_create_directories(self):
        source_root = self.project / "runtime/missing-public-failure-source"
        source_root.mkdir(parents=True)
        missing_qualification_root = (
            source_root / "qualifications/v32-missing-public-failure"
        )
        public = V32PublicSourceQualificationAttemptPort(
            project_root=self.project,
            evidence_store=self.evidence,
            source_store_root="runtime/missing-public-failure-source",
            run_store_root="runtime/missing-public-failure-run",
            source_qualification_id="v32-missing-public-failure",
            active_authority_projection=self.packet["support_documents"][
                "active_authority_projection"
            ],
            transport=source_fixture.BundleTransport(
                source_fixture.raw_bundle()
            ),
            clock=lambda: (_ for _ in ()).throw(
                AssertionError("failure replay must not read wall clock")
            ),
        )
        self.assertFalse(missing_qualification_root.exists())
        with self.assertRaises(ValueError):
            public.verify_failure_evidence_binding(
                {
                    "path": (
                        "runtime/missing-public-failure-source/"
                        "qualifications/v32-missing-public-failure/"
                        "validation-failure.json"
                    ),
                    "schema_id": (
                        "theory_paper_v32_public_source_validation_failure_v1"
                    ),
                    "digest_field": "public_source_validation_failure_digest",
                    "semantic_digest": "a" * 64,
                    "physical_sha256": "b" * 64,
                }
            )
        self.assertFalse(missing_qualification_root.exists())

    def test_current_codex_attempt_expiry_fails_before_mailbox_mutation(self):
        reserved = self.reserve("CURRENT_CODEX", "2026-08-07T00:15:00Z")
        adapter = V32CurrentCodexQualificationAttemptPort(
            project_root=self.project,
            evidence_store=self.evidence,
            mailbox_store_root="runtime/expired-qualification-mailbox",
            clock=SequenceClock(["2026-08-07T00:26:01Z"]),
        )
        with self.assertRaisesRegex(
            V32ActualCapabilityAttemptAdapterError, "ATTEMPT_EXPIRED"
        ):
            adapter.advance_once(
                qualification_authority=self.authority,
                reservation=reserved["reservation"],
                reservation_binding=reserved["reservation_binding"],
                resume_token=None,
                resume_requested_at=None,
            )
        self.assertFalse(
            (self.project / "runtime/expired-qualification-mailbox").exists()
        )
        self.assertEqual(
            verify_v32_current_codex_attempt_time_v1(
                qualification_authority=self.authority,
                reservation=reserved["reservation"],
                observed_at="2026-08-07T00:26:00Z",
            ),
            "2026-08-07T00:26:00Z",
        )

    def _outcome_runtime(self, runtime_root: str) -> None:
        physical = self.project / runtime_root
        physical.mkdir(parents=True, exist_ok=True)
        outcome_store = LocalV32OutcomeTickStore(physical)
        outcome_genesis = build_v32_outcome_tick_checkpoint(
            run_id=self.authority["run_id"], created_at="2026-08-07T00:45:00Z"
        )
        supervisor_genesis = build_v32_tick_supervisor_checkpoint(
            run_id=self.authority["run_id"],
            experiment_contract_digest=self.authority[
                "experiment_contract_binding"
            ]["semantic_digest"],
            active_authority_digest=self.authority[AUTHORITY_DIGEST_FIELD],
            research_checkpoint_digest="c" * 64,
            outcome_checkpoint_digest=outcome_genesis["checkpoint_digest"],
            timeframe_cache_digest="e" * 64,
            created_at="2026-08-07T00:45:00Z",
        )
        supervisor = LocalV32TickSupervisorStore(physical)
        supervisor.initialize_checkpoint(checkpoint=supervisor_genesis)
        initialize_v32_outcome_tick_runtime(
            store=outcome_store,
            run_id=self.authority["run_id"],
            created_at="2026-08-07T00:45:00Z",
            supervisor_checkpoint=supervisor_genesis,
        )
        schedule = build_v32_outcome_schedule_set(
            run_id=self.authority["run_id"],
            decision_id="qualification-decision:0001",
            cycle_index=1,
            decision_time="2026-08-07T00:45:00Z",
            scheduled_at="2026-08-07T00:45:01Z",
            sealed_decision_digest="1" * 64,
            evaluation_contract_digest="2" * 64,
        )
        before = supervisor.load_checkpoint(run_id=self.authority["run_id"])
        schedules_before = outcome_store.load_schedule_sets(
            run_id=self.authority["run_id"]
        )
        permit = build_v32_analysis_tick_permit(
            checkpoint=before,
            schedule_sets=schedules_before,
            analysis_decision_at="2026-08-07T00:45:00Z",
            issued_at="2026-08-07T00:45:01Z",
            research_checkpoint_digest=before["current_research_checkpoint_digest"],
            outcome_checkpoint_digest=before["current_outcome_checkpoint_digest"],
            timeframe_cache_digest=before["current_timeframe_cache_digest"],
            prior_dynamic_state_digest=None,
        )
        opened = supervisor.open_permit(
            permit=permit,
            schedule_sets=schedules_before,
            expected_checkpoint_digest=before[SUPERVISOR_CHECKPOINT_DIGEST_FIELD],
            opened_at="2026-08-07T00:45:01Z",
        )
        outcome_after = outcome_store.register_schedule_set(
            schedule_set=schedule, registered_at="2026-08-07T00:45:02Z"
        )
        supervisor.complete_analysis_tick(
            permit=permit,
            completion={
                "schedule_sets_before": schedules_before,
                "new_schedule_set": schedule,
                "accepted_state_digest": "3" * 64,
                "shadow_decision_bundle_digest": "4" * 64,
                "source_admission_digest": "5" * 64,
                "source_admission_physical_sha256": "6" * 64,
                "proposal_lifecycle_digest": "7" * 64,
                "selection_lifecycle_digest": "8" * 64,
                "final_action_plan_digest": "9" * 64,
                "commit_envelope_digest": "a" * 64,
                "new_research_checkpoint_digest": "b" * 64,
                "new_outcome_checkpoint_digest": outcome_after["checkpoint_digest"],
                "new_timeframe_cache_digest": "c" * 64,
                "new_dynamic_state_digest": "d" * 64,
                "completed_at": "2026-08-07T00:45:03Z",
            },
            expected_checkpoint_digest=opened[SUPERVISOR_CHECKPOINT_DIGEST_FIELD],
        )

    def test_outcome_adapter_resumes_same_permit_and_captures_once(self):
        probe_root = "runtime/qualification-monitor-probe"
        reserved = self.reserve("OUTCOME_MONITOR", "2026-08-07T00:59:59Z")
        capture = CapturePort()
        clock = SequenceClock(
            [
                "2026-08-07T01:00:01Z",
                "2026-08-07T01:00:01Z",
                "2026-08-07T01:00:02Z",
                "2026-08-07T01:00:03Z",
            ]
        )
        probe_store = LocalV32QualificationMonitorProbeStore(
            self.project / probe_root, capture_port=capture, clock=clock
        )
        probe_store.initialize(
            build_v32_qualification_monitor_probe_v1(
                probe_id="qualification-monitor-probe:0001",
                qualification_authority=self.authority,
                final_action_plan_digest=canonical_digest(
                    {"kind": "qualification-final-plan", "cycle": 1}
                ),
                selection_consumption_digest=canonical_digest(
                    {"kind": "qualification-selection-consumption", "cycle": 1}
                ),
                decision_time="2026-08-07T00:45:01Z",
            )
        )
        adapter = V32OutcomeMonitorQualificationAttemptPort(
            project_root=self.project,
            evidence_store=self.evidence,
            probe_store_root=probe_root,
            capture_port=capture,
            clock=clock,
        )
        resume_token = None
        resume_requested_at = None
        rows = []
        for _ in range(5):
            row = adapter.advance_once(
                qualification_authority=self.authority,
                reservation=reserved["reservation"],
                reservation_binding=reserved["reservation_binding"],
                resume_token=resume_token,
                resume_requested_at=resume_requested_at,
            )
            rows.append(row)
            resume_token = row["resume_token"]
            resume_requested_at = row["resume_requested_at"]
        self.assertEqual(
            ["PENDING", "PENDING", "PENDING", "PENDING", "COMPLETE"],
            [row["status"] for row in rows],
        )
        self.assertEqual(1, capture.calls)
        self.assertEqual({None}, {row["resume_token"] for row in rows})


if __name__ == "__main__":
    unittest.main()
