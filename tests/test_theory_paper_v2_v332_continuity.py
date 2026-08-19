from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.continuity import (
    ABSOLUTE_SLOT_GAP,
    FINALIZATION_AWAITING_RUN_CLOSE,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
)
from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.application.market_cycle.attention import (
    AttentionService,
)
from trade_system.theory_paper_v2.domain.market_cycle.experiment import (
    EXPERIMENT_MISSING_DATA_POLICY,
    ExperimentPolicyV1,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.continuity_checkpoint import (
    OWNER_HEAD_DIVERGENCE,
    ContinuityCheckpointError,
    FileContinuityCheckpointStore,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)


class MutableClock:
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


class FakeService:
    def __init__(self) -> None:
        self.revision = 0
        self.worker_dispatches: dict[str, dict[str, object]] = {}
        self.controller_status_calls = 0
        self.valid_cycles: set[str] = set()

    def controller_status(self) -> dict[str, object]:
        self.controller_status_calls += 1
        return {
            "revision": self.revision,
            "events": {},
            "worker_dispatches": self.worker_dispatches,
        }

    def verify_cycle_read(self, cycle_id: str) -> None:
        if cycle_id not in self.valid_cycles:
            raise AssertionError(f"unexpected cycle {cycle_id}")


@dataclass(frozen=True)
class FakeArtifactRef:
    artifact_type: str
    sha256: str = "9" * 64

    def to_dict(self) -> dict[str, str]:
        return {"artifact_type": self.artifact_type, "sha256": self.sha256}


@dataclass(frozen=True)
class FakeState:
    cycle_id: str
    stage: str
    revision: int
    artifact_refs: tuple[FakeArtifactRef, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cycle_id": self.cycle_id,
            "stage": self.stage,
            "revision": self.revision,
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
        }


@dataclass
class FakeRepository:
    root: Path
    states: dict[str, object] = field(default_factory=dict)
    requests: dict[str, object] = field(default_factory=dict)
    artifacts: dict[tuple[str, str], dict[str, object]] = field(
        default_factory=dict
    )

    def load_state(self, cycle_id: str) -> object:
        return self.states[cycle_id]

    def load_request(self, cycle_id: str) -> object:
        return self.requests[cycle_id]

    def load_artifact(self, cycle_id: str, artifact_type: str) -> dict[str, object]:
        return self.artifacts[(cycle_id, artifact_type)]


def _policy(run_id: str, starts_at: str) -> ExperimentPolicyV1:
    return ExperimentPolicyV1(
        experiment_id=f"experiment-{run_id}",
        run_id=run_id,
        phase="CONTINUITY_24H",
        venue_id="OKX",
        instrument_id="HYPE-USDT-SWAP",
        market_contract_identity="OKX:HYPE-USDT-SWAP:LINEAR_PERPETUAL_SWAP",
        data_profile="HYPE_OKX_PUBLIC_V1",
        starts_at=starts_at,
        duration_seconds=86_400,
        decision_horizon_seconds=3_600,
        outcome_tolerance_seconds=60,
        base_sampling_seconds=3_600,
        active_sampling_seconds=300,
        capability_ids=("SYSTEM_EXECUTION", "RECOVERY_REPLAY"),
        public_data_authorized=True,
        local_paper_authorized=False,
        testnet_authorized=False,
        live_authorized=False,
        private_credentials_authorized=False,
        external_orders_authorized=False,
        funds_authorized=False,
        paper_account=None,
        evaluation={
            "mode": "CONTINUITY_FORWARD_PAPER",
            "total_score_enabled": False,
            "actual_execution_status": "NOT_APPLICABLE_NOT_AUTHORIZED",
            "predictive_claim": "NOT_ESTABLISHED",
            "continuity_claim": "PRIMARY",
        },
        missing_data_policy=EXPERIMENT_MISSING_DATA_POLICY,
        restart_if=(ABSOLUTE_SLOT_GAP, OWNER_HEAD_DIVERGENCE),
        continue_if=("OPTIONAL_PUBLIC_SOURCE_LAG",),
    )


def _paper_policy(run_id: str, starts_at: str) -> ExperimentPolicyV1:
    document = _policy(run_id, starts_at).to_dict()
    document["local_paper_authorized"] = True
    document["paper_account"] = {
        "account_id": f"{run_id}.paper",
        "setup_cycle_id": f"{run_id}.setup",
        "logical_agent_id": "HYPE_CONTINUITY_TRADER",
        "agent_generation": 1,
        "account_mode": "LINEAR_PERP",
        "base_currency": "USDT",
        "initial_balance": "10000",
        "max_leverage": "2",
        "max_position_notional": "10000",
        "max_decision_loss": "100",
        "max_observed_drawdown": "500",
        "cost_model": {
            "model_id": "v332-continuity-cost-v1",
            "maker_fee_bps": "2",
            "taker_fee_bps": "5",
            "market_impact_bps": "3",
            "funding_status": "UNKNOWN",
            "borrow_status": "NOT_APPLICABLE",
            "effective_from": starts_at,
            "effective_to": "2026-08-15T00:00:00+00:00",
        },
    }
    return ExperimentPolicyV1.from_dict(document)


def _recovery_policy(run_id: str, starts_at: str) -> ExperimentPolicyV1:
    document = _policy(run_id, starts_at).to_dict()
    document["phase"] = "CAPABILITY_PILOT"
    document["duration_seconds"] = 3_600
    document["capability_ids"] = ["RECOVERY_REPLAY"]
    document["evaluation"] = {
        "mode": "INDEPENDENT_CAPABILITY_PILOT",
        "total_score_enabled": False,
        "actual_execution_status": "NOT_APPLICABLE_NOT_AUTHORIZED",
        "predictive_claim": "NOT_ESTABLISHED",
        "continuity_claim": "NOT_TESTED",
    }
    return ExperimentPolicyV1.from_dict(document)


class ContinuityCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "continuity-run"
        (self.root / "cycles").mkdir(parents=True)
        self.start = "2026-08-13T00:00:00+00:00"
        self.policy = _policy(self.root.name, self.start)
        self.service = FakeService()
        self.runtime = SimpleNamespace(
            experiment_policy=self.policy,
            run_manifest=SimpleNamespace(
                run_id=self.root.name,
                experiment_identity=self.policy.policy_sha256,
                identity_sha256="a" * 64,
                status="OPEN",
            ),
            runtime_root=self.root,
            repository=FakeRepository(self.root / "cycles"),
            service=self.service,
        )
        self.clock = MutableClock("2026-08-13T00:00:10+00:00")
        self.store = FileContinuityCheckpointStore(
            self.runtime, clock=self.clock
        )

    def _at_slot(self, slot: int, seconds: int = 10) -> str:
        start = datetime.fromisoformat(self.start)
        return (start + timedelta(hours=slot, seconds=seconds)).isoformat()

    def test_create_only_hash_chain_and_recovery_are_consistent(self) -> None:
        opened = self.store.open()
        opened_bytes = (
            self.root / "controller" / "continuity" / "records" / "00000001.json"
        ).read_bytes()
        self.assertEqual(self.store.open().record_sha256, opened.record_sha256)
        self.assertEqual(opened.owner_heads["paper"]["status"], "NOT_INCLUDED")
        self.assertEqual(
            opened.owner_heads["attention"]["status"], "NOT_INCLUDED"
        )
        self.assertEqual(
            (
                self.root
                / "controller"
                / "continuity"
                / "records"
                / "00000001.json"
            ).read_bytes(),
            opened_bytes,
        )

        self.clock.value = self._at_slot(1)
        second = self.store.record()
        self.assertEqual(second.previous_record_sha256, opened.record_sha256)
        self.assertEqual(second.absolute_slot, 1)

        restarted = FileContinuityCheckpointStore(
            self.runtime, clock=self.clock
        )
        recovered = restarted.recover()
        self.assertEqual(recovered.action, "CONTINUE")
        self.assertEqual(recovered.owner_head_status, "UNCHANGED")
        self.assertEqual(recovered.last_record_sha256, second.record_sha256)

    def test_unknown_issue_fails_closed_and_absolute_gap_requires_restart(self) -> None:
        self.store.open()
        with self.assertRaisesRegex(
            ContinuityCheckpointError, "CONTINUITY_ISSUE_NOT_CLASSIFIED"
        ):
            self.store.record(issue_code="UNREGISTERED_ISSUE")

        self.clock.value = self._at_slot(2)
        record = self.store.record()
        self.assertEqual(record.issue_code, ABSOLUTE_SLOT_GAP)
        self.assertEqual(record.disposition, "RESTART_REQUIRED")
        recovered = self.store.recover()
        self.assertEqual(recovered.action, "RESTART_REQUIRED")
        self.assertEqual(recovered.issue_code, ABSOLUTE_SLOT_GAP)

    def test_recovery_accepts_monotonic_progress_and_rejects_head_regression(self) -> None:
        self.store.open()
        self.service.revision = 1
        recovered = self.store.recover()
        self.assertEqual(recovered.action, "CONTINUE")
        self.assertEqual(recovered.owner_head_status, "MONOTONIC_PROGRESS")

        self.clock.value = self._at_slot(1)
        self.store.record()
        self.service.revision = 0
        restarted = self.store.recover()
        self.assertEqual(restarted.action, "RESTART_REQUIRED")
        self.assertEqual(restarted.issue_code, OWNER_HEAD_DIVERGENCE)

    def test_chain_tamper_is_detected_through_previous_hash(self) -> None:
        self.store.open()
        self.clock.value = self._at_slot(1)
        self.store.record()
        first_path = (
            self.root / "controller" / "continuity" / "records" / "00000001.json"
        )
        first = loads_json_strict(first_path.read_bytes())
        first["owner_heads"]["controller"]["revision"] = 99
        # A local writer can recompute an individual body hash, but cannot make
        # the already-created next record point at the replacement.
        body = {key: value for key, value in first.items() if key != "record_sha256"}
        from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_digest

        first["record_sha256"] = canonical_digest(body)
        first_path.write_bytes(canonical_bytes(first) + b"\n")
        with self.assertRaisesRegex(
            ContinuityCheckpointError, "CONTINUITY_RECORD_CHAIN_INVALID"
        ):
            self.store.recover()

    def test_finalize_awaits_authoritative_run_close(self) -> None:
        self.store.open()
        for slot in range(1, 24):
            self.clock.value = self._at_slot(slot)
            self.store.record()
        self.clock.value = "2026-08-14T00:00:00+00:00"
        final = self.store.finalize()
        self.assertEqual(final.record_kind, "FINAL")
        self.assertEqual(final.absolute_slot, 24)
        self.assertEqual(
            final.finalization_status, FINALIZATION_AWAITING_RUN_CLOSE
        )
        self.assertEqual(self.runtime.run_manifest.status, "OPEN")
        self.assertEqual(self.store.recover().action, "FINALIZED")

    def _paper_store(self, suffix: str):
        root = self.root.parent / f"paper-{suffix}"
        (root / "cycles").mkdir(parents=True)
        policy = _paper_policy(root.name, self.start)
        service = FakeService()
        runtime = SimpleNamespace(
            experiment_policy=policy,
            run_manifest=SimpleNamespace(
                run_id=root.name,
                experiment_identity=policy.policy_sha256,
                identity_sha256="b" * 64,
                status="OPEN",
            ),
            runtime_root=root,
            repository=FakeRepository(root / "cycles"),
            service=service,
        )
        clock = MutableClock("2026-08-13T00:00:10+00:00")
        attention_repository = FileAttentionRepository(root / "attention")
        sessions = AgentSessionService(attention_repository)
        attention = AttentionService(attention_repository)
        sessions.register(
            AgentRegistry(
                logical_agent_id="HYPE_CONTINUITY_TRADER",
                symbol="HYPE-USDT-SWAP",
                generation=1,
                continuity_nonce="continuity-nonce-g1",
                physical_task_id="continuity-agent-task-g1",
                status="ACTIVE",
                registered_at="2026-08-13T00:00:00+00:00",
            )
        )
        store = FileContinuityCheckpointStore(runtime, clock=clock)
        store.open()
        request = AttentionRequest(
            request_id=f"attention-{suffix}",
            logical_agent_id="HYPE_CONTINUITY_TRADER",
            agent_generation=1,
            continuity_nonce="continuity-nonce-g1",
            symbol="HYPE-USDT-SWAP",
            mode="WAKE_AFTER",
            issued_at="2026-08-13T00:00:20+00:00",
            continue_until=None,
            earliest_wake_at="2026-08-13T00:05:00+00:00",
            latest_useful_at="2026-08-13T00:10:00+00:00",
            reason_summary="Agent-selected continuity review window.",
            requested_focus="Re-evaluate the Agent hypothesis and paper position.",
            hypothesis_or_episode_ref="episode-continuity-1",
            position_and_open_order_ref=f"{root.name}.paper",
            data_cursor="cursor-continuity-1",
        )
        attention.submit_request(request)
        return store, runtime, clock, attention, request

    @staticmethod
    def _add_agent_decision_cycle(
        runtime: object,
        *,
        cycle_id: str,
        delivered_at: str,
        requested_at: str | None = None,
    ) -> None:
        repository = runtime.repository
        service = runtime.service
        (repository.root / cycle_id).mkdir()
        service.valid_cycles.add(cycle_id)
        reference = FakeArtifactRef("HypothesisRecord")
        repository.states[cycle_id] = FakeState(
            cycle_id=cycle_id,
            stage="ANALYZED",
            revision=2,
            artifact_refs=(
                FakeArtifactRef("InputSnapshot", "8" * 64),
                reference,
            ),
        )
        repository.requests[cycle_id] = SimpleNamespace(
            requested_at=requested_at or delivered_at,
            venue_id="OKX",
            instrument_id="HYPE-USDT-SWAP",
        )
        repository.artifacts[(cycle_id, "HypothesisRecord")] = {
            "agent_delivered_at": delivered_at
        }

    def test_agent_attention_followup_decision_is_owner_derived_and_single_use(
        self,
    ) -> None:
        store, runtime, clock, _attention, request = self._paper_store("followup")
        self._add_agent_decision_cycle(
            runtime,
            cycle_id="cycle-followup-on-time",
            delivered_at="2026-08-13T00:06:00+00:00",
        )
        clock.value = "2026-08-13T00:06:00+00:00"
        record = store.record_agent_attention(request_id=request.request_id)
        self.assertEqual(record.slot_kind, "AGENT_ATTENTION")
        self.assertEqual(record.source_event_id, request.request_id)
        self.assertEqual(record.attempt_status, "ATTEMPTED_TERMINAL")
        self.assertEqual(record.slot_scheduled_at, request.earliest_wake_at)
        self.assertEqual(record.latest_useful_at, request.latest_useful_at)
        with self.assertRaisesRegex(
            ContinuityCheckpointError, "CONTINUITY_ATTENTION_REQUEST_REUSED"
        ):
            store.record_agent_attention(request_id=request.request_id)

    def test_agent_attention_attempt_uses_cycle_request_time_not_late_delivery(
        self,
    ) -> None:
        store, runtime, clock, _attention, request = self._paper_store(
            "late-delivery"
        )
        self._add_agent_decision_cycle(
            runtime,
            cycle_id="cycle-requested-on-time-delivered-late",
            requested_at="2026-08-13T00:06:00+00:00",
            delivered_at="2026-08-13T00:11:00+00:00",
        )
        clock.value = "2026-08-13T00:20:00+00:00"
        record = store.record_agent_attention(request_id=request.request_id)
        self.assertEqual(record.attempt_status, "ATTEMPTED_TERMINAL")
        cycle_head = next(
            cycle
            for cycle in record.owner_heads["cycles"]
            if cycle["cycle_id"] == "cycle-requested-on-time-delivered-late"
        )
        self.assertEqual(
            cycle_head["requested_at"], "2026-08-13T00:06:00+00:00"
        )
        self.assertEqual(
            cycle_head["agent_decision_delivered_at"],
            "2026-08-13T00:11:00+00:00",
        )

    def test_agent_attention_ignores_cycle_started_before_exact_window(self) -> None:
        store, runtime, clock, _attention, request = self._paper_store(
            "pre-window"
        )
        self._add_agent_decision_cycle(
            runtime,
            cycle_id="cycle-requested-before-window",
            requested_at="2026-08-13T00:04:00+00:00",
            delivered_at="2026-08-13T00:06:00+00:00",
        )
        clock.value = "2026-08-13T00:06:00+00:00"
        with self.assertRaisesRegex(
            ContinuityCheckpointError,
            "CONTINUITY_ATTENTION_FOLLOWUP_DECISION_NOT_OBSERVED",
        ):
            store.record_agent_attention(request_id=request.request_id)

    def test_agent_attention_does_not_substitute_for_a_missing_base_slot(self) -> None:
        store, runtime, clock, _attention, request = self._paper_store("base-gap")
        self._add_agent_decision_cycle(
            runtime,
            cycle_id="cycle-base-gap-followup",
            delivered_at="2026-08-13T00:06:00+00:00",
        )
        clock.value = "2026-08-13T01:00:10+00:00"
        attention_record = store.record_agent_attention(
            request_id=request.request_id
        )
        self.assertEqual(attention_record.absolute_slot, 1)
        clock.value = "2026-08-13T02:00:10+00:00"
        recovered = store.recover()
        self.assertEqual(recovered.action, "RESTART_REQUIRED")
        self.assertEqual(recovered.issue_code, ABSOLUTE_SLOT_GAP)

    def test_agent_attention_late_followup_is_recorded_without_supervisor_action(self) -> None:
        store, runtime, clock, _attention, request = self._paper_store("missed")
        clock.value = "2026-08-13T00:11:00+00:00"
        recovered = store.recover()
        self.assertEqual(recovered.action, "CONTINUE")
        self.assertIsNone(recovered.issue_code)
        with self.assertRaisesRegex(
            ContinuityCheckpointError,
            "CONTINUITY_ATTENTION_FOLLOWUP_DECISION_NOT_OBSERVED",
        ):
            store.record_agent_attention(request_id=request.request_id)
        self._add_agent_decision_cycle(
            runtime,
            cycle_id="cycle-followup-late",
            delivered_at="2026-08-13T00:11:00+00:00",
        )
        record = store.record_agent_attention(request_id=request.request_id)
        self.assertEqual(record.attempt_status, "NOT_ATTEMPTED")
        self.assertIsNone(record.issue_code)
        self.assertEqual(record.disposition, "CONTINUE")
        self.assertEqual(store.recover().action, "CONTINUE")

    def _recovery_store(self, suffix: str, *, status: str):
        root = self.root.parent / f"recovery-{suffix}"
        (root / "cycles").mkdir(parents=True)
        policy = _recovery_policy(root.name, self.start)
        service = FakeService()
        service.revision = 1
        service.worker_dispatches = {
            "dispatch-key-1": {
                "cycle_id": "cycle-recovery-1",
                "worker_id": "decision-v1",
                "dispatch_id": "dispatch-recovery-1",
                "status": status,
                "task_sha256": "1" * 64,
                "request_sha256": "2" * 64,
                "spawn_requested_at": (
                    "2026-08-13T00:00:05+00:00"
                    if status == "SPAWN_REQUESTED"
                    else None
                ),
                "spawn_execution_ref": None,
                "spawn_acknowledged_at": None,
                "output_sha256": None,
            }
        }
        runtime = SimpleNamespace(
            experiment_policy=policy,
            run_manifest=SimpleNamespace(
                run_id=root.name,
                experiment_identity=policy.policy_sha256,
                identity_sha256="c" * 64,
                status="OPEN",
            ),
            runtime_root=root,
            repository=FakeRepository(root / "cycles"),
            service=service,
        )
        clock = MutableClock("2026-08-13T00:00:10+00:00")
        return (
            FileContinuityCheckpointStore(runtime, clock=clock),
            runtime,
            clock,
            service,
        )

    def test_recovery_probe_safe_prepared_restart_is_identical_and_idempotent(self) -> None:
        store, runtime, clock, _service = self._recovery_store(
            "prepared", status="PREPARED"
        )
        probe = store.preregister_recovery_probe(
            probe_id="probe-prepared-1",
            injection_point="WORKER_PREPARED_RESTART",
        )
        self.assertEqual(probe.created_by, "TRUSTED_CONTINUITY_CLOCK")
        self.assertEqual(probe.created_at, "2026-08-13T00:00:10+00:00")
        probe_bytes = (
            runtime.runtime_root
            / "controller"
            / "continuity"
            / "recovery-probes"
            / probe.probe_id
            / "probe.json"
        ).read_bytes()
        clock.value = "2026-08-13T00:00:20+00:00"
        restarted = FileContinuityCheckpointStore(runtime, clock=clock)
        observation = restarted.observe_recovery_probe(probe.probe_id)
        self.assertEqual(observation.action, "CONTINUE")
        self.assertEqual(observation.replay_status, "IDENTICAL")
        self.assertEqual(observation.duplicate_status, "NONE_OBSERVED")
        clock.value = "2026-08-13T00:00:30+00:00"
        self.assertEqual(
            restarted.preregister_recovery_probe(
                probe_id=probe.probe_id,
                injection_point="WORKER_PREPARED_RESTART",
            ).probe_sha256,
            probe.probe_sha256,
        )
        self.assertEqual(
            restarted.observe_recovery_probe(probe.probe_id).observation_sha256,
            observation.observation_sha256,
        )
        self.assertEqual(
            (
                runtime.runtime_root
                / "controller"
                / "continuity"
                / "recovery-probes"
                / probe.probe_id
                / "probe.json"
            ).read_bytes(),
            probe_bytes,
        )

    def test_spawn_requested_without_ack_is_unresolved_restart_without_resend(self) -> None:
        store, runtime, clock, service = self._recovery_store(
            "spawn-unresolved", status="SPAWN_REQUESTED"
        )
        probe = store.preregister_recovery_probe(
            probe_id="probe-spawn-unresolved-1",
            injection_point="WORKER_SPAWN_REQUESTED_BEFORE_ACK_RESTART",
        )
        calls_before = service.controller_status_calls
        clock.value = "2026-08-13T00:00:20+00:00"
        observation = FileContinuityCheckpointStore(
            runtime, clock=clock
        ).observe_recovery_probe(probe.probe_id)
        self.assertEqual(observation.action, "RESTART_REQUIRED")
        self.assertEqual(observation.replay_status, "UNRESOLVED")
        self.assertEqual(observation.duplicate_status, "UNRESOLVED")
        self.assertEqual(
            observation.reason_code,
            "SPAWN_REQUESTED_ACK_UNRESOLVED_NO_AUTORETRY",
        )
        self.assertEqual(service.controller_status_calls, calls_before + 1)
        self.assertEqual(
            service.worker_dispatches["dispatch-key-1"]["status"],
            "SPAWN_REQUESTED",
        )

    def test_recovery_probe_tamper_is_rejected(self) -> None:
        store, runtime, _clock, _service = self._recovery_store(
            "tamper", status="PREPARED"
        )
        probe = store.preregister_recovery_probe(
            probe_id="probe-tamper-1",
            injection_point="WORKER_PREPARED_RESTART",
        )
        path = (
            runtime.runtime_root
            / "controller"
            / "continuity"
            / "recovery-probes"
            / probe.probe_id
            / "probe.json"
        )
        document = loads_json_strict(path.read_bytes())
        document["created_by"] = "CALLER_REWRITTEN_CLOCK"
        path.write_bytes(canonical_bytes(document) + b"\n")
        with self.assertRaisesRegex(
            ContinuityCheckpointError, "CONTINUITY_RECOVERY_PROBE_INVALID"
        ):
            store.observe_recovery_probe(probe.probe_id)


if __name__ == "__main__":
    unittest.main()
