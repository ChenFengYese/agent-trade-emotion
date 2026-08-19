from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
from typing import Mapping
import unittest
from unittest import mock

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.capability_evaluation import (
    CAPABILITY_CRITERIA,
    CAPABILITY_RUBRICS,
    BlindCapabilityTaskV1,
    CapabilityFindingV1,
    PreOutcomeCapabilityAssessmentV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    CycleRequest,
    HypothesisRecord,
    InputSnapshot,
    Outcome,
)
from trade_system.theory_paper_v2.domain.market_cycle.experiment import (
    EXPERIMENT_MISSING_DATA_POLICY,
    ExperimentPolicyV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.capability_evaluation_store import (
    CapabilityEvaluationStoreError,
    FileCapabilityEvaluationStore,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.capability_assessor_mailbox import (
    LocalCapabilityAssessorMailbox,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.codex_mailbox import (
    LocalMarketCycleAgentMailbox,
    MarketCycleAgentMailboxError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.repository import (
    FileCycleRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    MarketCycleRuntime,
    build_market_cycle_runtime,
    initialize_v332_run,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
)
from trade_system.theory_paper_v2.v32_durable_json import write_once_json
from trade_system.theory_paper_v2.presentation import market_cycle as market_cycle_cli


_CYCLE = "capability-store-cycle-001"
_SUBJECT_THREAD_ID = "11111111-1111-1111-1111-111111111111"
_SUBJECT_GOAL_ID = f"codex-thread:{_SUBJECT_THREAD_ID}"
_ASSESSOR_GOAL_ID = "codex-thread:22222222-2222-2222-2222-222222222222"
_V332_PACKAGE = (
    Path(__file__).resolve().parents[1] / "theory" / "versions" / "v3.3.2"
)
_PACKET = {
    "cycle_id": _CYCLE,
    "sealed": True,
    "theory_identity": V332_THEORY_IDENTITY.to_dict(),
}
_REQUEST_DOCUMENT = {
    "packet": _PACKET,
    "packet_sha256": canonical_digest(_PACKET),
}
_DECISION = (
    "状态与覆盖明确；事实和推论分层。\n"
    "假说A与假说B互斥，均给出证伪和区分信号。\n"
    "ACTION=WAIT\n"
    "POSITION=flat\n"
)


class _Clock:
    def __init__(self) -> None:
        self.value = "2026-08-13T12:00:03+00:00"

    def __call__(self) -> str:
        return self.value

    def monotonic_ns(self) -> int:
        return 1


class _ReadGate:
    def __init__(self) -> None:
        self.calls = 0

    def verify_cycle_read(self, cycle_id: str) -> None:
        if cycle_id != _CYCLE:
            raise AssertionError("unexpected cycle")
        self.calls += 1


class _AssessorController:
    def __init__(self) -> None:
        self.record: dict[str, object] | None = None

    def materialize_worker_task(self, cycle_id: str, worker_id: str) -> Path:
        if cycle_id != _CYCLE or worker_id != "capability-assessor-v1":
            raise AssertionError("unexpected assessor worker")
        return Path("/controller-owned/capability-assessor-task.json")

    def prepare_worker(
        self, cycle_id: str, worker_id: str, task_path: Path
    ) -> dict[str, object]:
        del task_path
        if self.record is None:
            self.record = {
                "cycle_id": cycle_id,
                "worker_id": worker_id,
                "dispatch_id": "assessor-dispatch-001",
                "status": "PREPARED",
                "spawn_execution_ref": None,
                "output_sha256": None,
            }
        return dict(self.record)

    def mark_spawn_requested(
        self, cycle_id: str, worker_id: str, dispatch_id: str
    ) -> dict[str, object]:
        assert self.record is not None
        if (
            cycle_id != self.record["cycle_id"]
            or worker_id != self.record["worker_id"]
            or dispatch_id != self.record["dispatch_id"]
        ):
            raise AssertionError("assessor dispatch mismatch")
        if self.record["status"] == "PREPARED":
            self.record["status"] = "SPAWN_REQUESTED"
        return dict(self.record)

    def acknowledge_spawn(self, execution_ref: str) -> None:
        assert self.record is not None
        self.record["status"] = "DISPATCHED"
        self.record["spawn_execution_ref"] = execution_ref

    def complete(self, output_sha256: str) -> None:
        assert self.record is not None
        self.record["status"] = "COMPLETED"
        self.record["output_sha256"] = output_sha256

    def recover_worker(
        self, cycle_id: str, worker_id: str
    ) -> dict[str, object]:
        assert self.record is not None
        if cycle_id != _CYCLE or worker_id != "capability-assessor-v1":
            raise AssertionError("unexpected assessor recovery")
        return dict(self.record)


def _policy(capability_id: str = "MARKET_ANALYSIS") -> ExperimentPolicyV1:
    return ExperimentPolicyV1(
        experiment_id="capability-store-pilot-001",
        run_id="capability-store-run-001",
        phase="CAPABILITY_PILOT",
        venue_id="OKX",
        instrument_id=HYPE_OKX_DATA_PROFILE.instrument_id,
        market_contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        starts_at="2026-08-13T11:59:00+00:00",
        duration_seconds=3600,
        decision_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        base_sampling_seconds=300,
        active_sampling_seconds=60,
        capability_ids=(capability_id,),
        public_data_authorized=True,
        local_paper_authorized=False,
        testnet_authorized=False,
        live_authorized=False,
        private_credentials_authorized=False,
        external_orders_authorized=False,
        funds_authorized=False,
        paper_account=None,
        evaluation={
            "mode": "INDEPENDENT_CAPABILITY_PILOT",
            "total_score_enabled": False,
            "actual_execution_status": "NOT_APPLICABLE_NOT_AUTHORIZED",
            "predictive_claim": "NOT_EVALUATED",
            "continuity_claim": "NOT_TESTED",
        },
        missing_data_policy=EXPERIMENT_MISSING_DATA_POLICY,
        restart_if=("FUTURE_DATA_LEAKAGE",),
        continue_if=("OPTIONAL_DATA_TYPED_UNKNOWN",),
    )


def _raw_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_type="RawCapture",
        artifact_id=f"{_CYCLE}.raw",
        path="raw/input/body.bin",
        size_bytes=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
    )


def _snapshot(raw: ArtifactRef | None = None) -> InputSnapshot:
    raw = _raw_ref() if raw is None else raw

    def observation(value: object) -> dict[str, object]:
        return {
            "value": value,
            "available_at": "2026-08-13T12:00:00+00:00",
            "raw_sha256": raw.sha256,
        }

    bars = observation([])
    bars["last_closed_at"] = "2026-08-13T12:00:00+00:00"
    return InputSnapshot(
        snapshot_id=f"{_CYCLE}.snapshot",
        cycle_id=_CYCLE,
        request_id=f"{_CYCLE}.request",
        source_cutoff_at="2026-08-13T12:00:00+00:00",
        decision_at="2026-08-13T12:00:01+00:00",
        sealed_at="2026-08-13T12:00:02+00:00",
        venue_id="OKX",
        instrument_id=HYPE_OKX_DATA_PROFILE.instrument_id,
        contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        analysis_profile="COLD",
        data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        outcome_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        lawful_actions=("WAIT", "LONG_REFERENCE", "SHORT_REFERENCE"),
        core_observations={
            "server_time": observation("2026-08-13T12:00:00+00:00"),
            "instrument": observation(HYPE_OKX_DATA_PROFILE.instrument_id),
            "mark_price": observation("42.5"),
            "closed_15m_bars": bars,
        },
        optional_observations={},
        unknowns=("CONTINUOUS_ORDER_FLOW_UNKNOWN",),
        raw_refs=(raw,),
        source_health=(),
        theory_identity=V332_THEORY_IDENTITY,
    )


def _request() -> CycleRequest:
    return CycleRequest(
        request_id=f"{_CYCLE}.request",
        cycle_id=_CYCLE,
        requested_at="2026-08-13T12:00:00+00:00",
        venue_id="OKX",
        instrument_id=HYPE_OKX_DATA_PROFILE.instrument_id,
        contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        analysis_profile="COLD",
        data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        outcome_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        lawful_actions=("WAIT", "LONG_REFERENCE", "SHORT_REFERENCE"),
        theory_identity=V332_THEORY_IDENTITY,
    )


def _hypothesis(
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
    *,
    delivery_sha256: str,
) -> HypothesisRecord:
    raw = _DECISION.encode("utf-8")
    return HypothesisRecord(
        record_id=f"{_CYCLE}.hypotheses",
        cycle_id=_CYCLE,
        input_snapshot_ref=snapshot_ref,
        decision_at=snapshot.decision_at,
        agent_delivered_at="2026-08-13T12:00:10+00:00",
        sealed_at="2026-08-13T12:00:10+00:00",
        outcome_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        agent_request_sha256=canonical_digest(_PACKET),
        agent_delivery_path="transport/agent-delivery.json",
        agent_delivery_sha256=delivery_sha256,
        agent_decision_text=_DECISION,
        agent_decision_size_bytes=len(raw),
        agent_decision_sha256=hashlib.sha256(raw).hexdigest(),
        projection_status="AVAILABLE",
        projection_reason=None,
        hypothesis_index=("假说A", "假说B"),
        agent_action_text="ACTION=WAIT",
        agent_position_text="POSITION=flat",
        lawful_actions=snapshot.lawful_actions,
        unresolved_unknowns=snapshot.unknowns,
        theory_identity=V332_THEORY_IDENTITY,
    )


class CapabilityEvaluationStoreTests(unittest.TestCase):
    def _goal_delivery_binding(self, cycle_id: str) -> Mapping[str, str] | None:
        path = self.repository.root / cycle_id / "transport" / "agent-delivery.json"
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
            delivery = loads_json_strict(raw)
            decision_raw = delivery["decision_text"].encode("utf-8")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_GOAL_DELIVERY_BINDING_INVALID"
            ) from exc
        if (
            canonical_bytes(delivery) + b"\n" != raw
            or delivery.get("schema_id")
            != "agent_trade_emotion_market_cycle_agent_decision_delivery"
            or delivery.get("schema_version") != "1.1.0"
            or delivery.get("cycle_id") != cycle_id
            or delivery.get("physical_goal_id") != _SUBJECT_GOAL_ID
            or delivery.get("decision_size_bytes") != len(decision_raw)
            or delivery.get("decision_sha256")
            != hashlib.sha256(decision_raw).hexdigest()
        ):
            raise MarketCycleAgentMailboxError(
                "MARKET_CYCLE_AGENT_GOAL_DELIVERY_BINDING_INVALID"
            )
        return {
            "physical_goal_id": _SUBJECT_GOAL_ID,
            "delivery_sha256": hashlib.sha256(raw).hexdigest(),
        }

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = FileCycleRepository(self.root / "cycles")
        state = self.repository.create(_request())
        self.snapshot = _snapshot()
        self.state = self.repository.transition(
            expected=state,
            artifacts=(self.snapshot,),
            next_stage="INPUT_SEALED",
            next_action="ANALYZE",
        )
        self.mailbox = LocalMarketCycleAgentMailbox(
            self.repository.root, clock=_Clock()
        )
        self.mailbox.goal_decision_delivery_binding = (  # type: ignore[method-assign]
            self._goal_delivery_binding
        )
        write_once_json(
            self.repository.root / _CYCLE / "transport" / "agent-request.json",
            _REQUEST_DOCUMENT,
        )
        self.policy = _policy()
        self.gate = _ReadGate()
        self.assessor = _AssessorController()
        self.runtime = MarketCycleRuntime(
            service=self.gate,  # type: ignore[arg-type]
            repository=self.repository,
            mailbox=self.mailbox,
            controller_state=self.assessor,  # type: ignore[arg-type]
            identity=V332_THEORY_IDENTITY,
            run_manifest=SimpleNamespace(
                experiment_identity=self.policy.policy_sha256,
                run_id=self.policy.run_id,
            ),
            experiment_policy=self.policy,
            verified_memory=(),
            runtime_root=self.root,
        )
        self.clock = _Clock()
        self.store = FileCapabilityEvaluationStore(
            self.runtime, clock=self.clock
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _seal_hypothesis(self) -> HypothesisRecord:
        artifact_types = tuple(
            item.artifact_type for item in self.state.artifact_refs
        )
        if "HypothesisRecord" in artifact_types:
            return HypothesisRecord.from_dict(
                self.repository.load_artifact(_CYCLE, "HypothesisRecord")
            )
        delivery = {
            "schema_id": "agent_trade_emotion_market_cycle_agent_decision_delivery",
            "schema_version": "1.1.0",
            "cycle_id": _CYCLE,
            "request_sha256": canonical_digest(_PACKET),
            "theory_identity": V332_THEORY_IDENTITY.to_dict(),
            "delivered_at": "2026-08-13T12:00:10+00:00",
            "media_type": "text/markdown",
            "encoding": "UTF-8",
            "decision_size_bytes": len(_DECISION.encode("utf-8")),
            "decision_sha256": hashlib.sha256(
                _DECISION.encode("utf-8")
            ).hexdigest(),
            "decision_text": _DECISION,
            "physical_goal_id": _SUBJECT_GOAL_ID,
        }
        delivery_path = (
            self.repository.root
            / _CYCLE
            / "transport"
            / "agent-delivery.json"
        )
        write_once_json(delivery_path, delivery)
        hypothesis = _hypothesis(
            self.snapshot,
            self.state.artifact_refs[0],
            delivery_sha256=hashlib.sha256(delivery_path.read_bytes()).hexdigest(),
        )
        self.state = self.repository.transition(
            expected=self.state,
            artifacts=(hypothesis,),
            next_stage="ANALYZED",
            next_action="COPY_AGENT_DECISION_TO_PLAN",
        )
        self.clock.value = "2026-08-13T12:00:11+00:00"
        return hypothesis

    def _preregister(self, capability_id: str) -> BlindCapabilityTaskV1:
        self._seal_hypothesis()
        self.store.prepare_assessor(
            cycle_id=_CYCLE,
            task_id=f"{_CYCLE}.{capability_id.lower()}",
            capability_id=capability_id,
            assessment_due_at="2026-08-13T12:59:00+00:00",
        )
        self.assessor.acknowledge_spawn(_ASSESSOR_GOAL_ID)
        return self.store.preregister(
            cycle_id=_CYCLE,
            capability_id=capability_id,
        )

    def _use_capability_policy(self, capability_id: str) -> None:
        self.policy = _policy(capability_id)
        self.runtime = MarketCycleRuntime(
            service=self.gate,  # type: ignore[arg-type]
            repository=self.repository,
            mailbox=self.mailbox,
            controller_state=self.assessor,  # type: ignore[arg-type]
            identity=V332_THEORY_IDENTITY,
            run_manifest=SimpleNamespace(
                experiment_identity=self.policy.policy_sha256,
                run_id=self.policy.run_id,
            ),
            experiment_policy=self.policy,
            verified_memory=(),
            runtime_root=self.root,
        )
        self.store = FileCapabilityEvaluationStore(
            self.runtime, clock=self.clock
        )

    def _complete_assessor(self, capability_id: str) -> None:
        task = self.store.load_task(_CYCLE, capability_id)
        result = {
            "schema_id": "agent-trade-emotion.v332-capability-assessor-findings",
            "schema_version": "1.0.0",
            "cycle_id": _CYCLE,
            "worker_id": "capability-assessor-v1",
            "capability_id": capability_id,
            "task_id": task.task_id,
            "task_sha256": task.task_sha256,
            "assessor_execution_ref": task.assessor_id,
            "completed_at": self.clock.value,
            "findings": [item.to_dict() for item in self._findings(capability_id)],
        }
        path = self.root / "cycles" / _CYCLE / "transport" / "capability-assessor-findings.json"
        write_once_json(path, result)
        self.assessor.complete(hashlib.sha256(path.read_bytes()).hexdigest())

    @staticmethod
    def _findings(capability_id: str) -> tuple[CapabilityFindingV1, ...]:
        return tuple(
            CapabilityFindingV1(
                criterion_id=criterion,
                status="UNRESOLVED",
                rationale="conservative pre-outcome assessor result",
            )
            for criterion in CAPABILITY_CRITERIA[capability_id]
        )

    @staticmethod
    def _write_worker_result(
        *,
        runtime: MarketCycleRuntime,
        record: Mapping[str, object],
        body: str,
        completed_at: str,
    ) -> None:
        task_path = Path(str(record["task_path"]))
        task = loads_json_strict(task_path.read_bytes())
        assert isinstance(task, dict)
        write_once_json(
            task_path.parent / "result.json",
            {
                "schema_id": "agent_trade_emotion_v331_worker_result",
                "schema_version": "1.0.0",
                "run_id": runtime.run_manifest.run_id,
                "cycle_id": _CYCLE,
                "worker_id": record["worker_id"],
                "status": "COMPLETED",
                "started_at": task["timing"]["created_at"],
                "completed_at": completed_at,
                "elapsed_seconds": 1,
                "input_refs": [
                    {
                        field: item[field]
                        for field in ("role", "path", "sha256")
                    }
                    for item in task["input_refs"]
                ],
                "body_markdown": body,
            },
        )

    def test_preregister_is_write_once_and_requires_sealed_decision(self) -> None:
        self.assertNotIn(
            "assessor_id",
            inspect.signature(FileCapabilityEvaluationStore.preregister).parameters,
        )
        self.assertNotIn(
            "findings",
            inspect.signature(
                FileCapabilityEvaluationStore.seal_assessment
            ).parameters,
        )
        with self.assertRaisesRegex(
            CapabilityEvaluationStoreError, "HYPOTHESIS_NOT_SEALED"
        ):
            self.store.prepare_assessor(
                cycle_id=_CYCLE,
                task_id=f"{_CYCLE}.market_analysis",
                capability_id="MARKET_ANALYSIS",
                assessment_due_at="2026-08-13T12:59:00+00:00",
            )
        hypothesis = self._seal_hypothesis()
        task = self._preregister("MARKET_ANALYSIS")
        self.assertEqual(_SUBJECT_GOAL_ID, task.subject_agent_id)
        self.assertEqual(
            hypothesis.agent_delivery_sha256, task.decision_delivery_sha256
        )
        self.assertEqual(
            CAPABILITY_RUBRICS["MARKET_ANALYSIS"]["rubric_sha256"],
            task.rubric["rubric_sha256"],
        )
        self.assertEqual(self.clock.value, task.created_at)
        assessor_request = LocalCapabilityAssessorMailbox(
            self.root
        ).load_request(_CYCLE)
        self.assertEqual(
            task.to_dict()["rubric"],
            assessor_request["packet"]["task_basis"]["rubric"],
        )
        self.assertEqual(
            LocalCapabilityAssessorMailbox(self.root).output_contract(
                cycle_id=_CYCLE,
                evidence_kind="GENERAL",
                capability_id="MARKET_ANALYSIS",
                capability_task_path=assessor_request["packet"][
                    "capability_task_path"
                ],
                task_basis=assessor_request["packet"]["task_basis"],
            ),
            assessor_request["packet"]["output_contract"],
        )
        mailbox = LocalCapabilityAssessorMailbox(self.root)
        contract = assessor_request["packet"]["output_contract"]
        self.assertEqual("1.2.0", contract["schema_version"])
        self.assertEqual(sorted(contract["exact_fields"]), contract["exact_fields"])
        self.assertEqual(
            sorted(contract["findings"]["exact_fields"]),
            contract["findings"]["exact_fields"],
        )
        self.assertEqual(
            sorted(contract["findings"]["evidence_span_exact_fields"]),
            contract["findings"]["evidence_span_exact_fields"],
        )

        span_values = {
            "start_byte": 0,
            "end_byte": len(_DECISION.encode("utf-8")),
            "utf8_sha256": hashlib.sha256(_DECISION.encode("utf-8")).hexdigest(),
        }
        span = {
            field: span_values[field]
            for field in contract["findings"]["evidence_span_exact_fields"]
        }
        findings = []
        for index, criterion_id in enumerate(
            contract["findings"]["criterion_ids"]
        ):
            finding_values = {
                "criterion_id": criterion_id,
                "status": "DEMONSTRATED" if index == 0 else "UNRESOLVED",
                "rationale": "exact pre-outcome decision-byte evidence",
                "evidence_spans": [span] if index == 0 else [],
            }
            findings.append(
                {
                    field: finding_values[field]
                    for field in contract["findings"]["exact_fields"]
                }
            )
        result_values = {
            **contract["fixed_values"],
            "task_id": task.task_id,
            "task_sha256": task.task_sha256,
            "assessor_execution_ref": task.assessor_id,
            "completed_at": self.clock.value,
            "findings": findings,
        }
        result = {
            field: result_values[field] for field in contract["exact_fields"]
        }
        raw = (
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(canonical_bytes(result) + b"\n", raw)
        with mailbox.result_path(_CYCLE).open("xb") as stream:
            stream.write(raw)
        loaded, loaded_raw = mailbox.load_result(_CYCLE)
        self.assertEqual(result, loaded)
        self.assertEqual(raw, loaded_raw)

        paper_contract = mailbox.output_contract(
            cycle_id=_CYCLE,
            evidence_kind="PAPER",
            capability_id="POSITION_MANAGEMENT",
            capability_task_path="/tmp/position-task.json",
            task_basis={"decision_points": [{"cycle_id": _CYCLE}]},
        )
        self.assertEqual("1.2.0", paper_contract["schema_version"])
        self.assertEqual(
            sorted(paper_contract["findings"]["evidence_span_exact_fields"]),
            paper_contract["findings"]["evidence_span_exact_fields"],
        )
        replayed = self._preregister("MARKET_ANALYSIS")
        self.assertEqual(replayed.task_sha256, task.task_sha256)
        self.assertEqual(
            BlindCapabilityTaskV1.from_dict(task.to_dict()).task_sha256,
            task.task_sha256,
        )
        with self.assertRaisesRegex(
            CapabilityEvaluationStoreError, "ASSESSOR_REQUEST_INVALID"
        ):
            self.store.prepare_assessor(
                cycle_id=_CYCLE,
                task_id=f"{_CYCLE}.different-task",
                capability_id="MARKET_ANALYSIS",
                assessment_due_at="2026-08-13T12:59:00+00:00",
            )

        delivery_path = (
            self.repository.root
            / _CYCLE
            / "transport"
            / "agent-delivery.json"
        )
        delivery_path.write_bytes(b"{}\n")
        with self.assertRaisesRegex(
            CapabilityEvaluationStoreError, "AGENT_DELIVERY_INVALID"
        ):
            self._preregister("MARKET_ANALYSIS")

    def test_same_goal_assessor_ack_is_rejected_before_controller_write(self) -> None:
        self._seal_hypothesis()
        prepared = self.store.prepare_assessor(
            cycle_id=_CYCLE,
            task_id=f"{_CYCLE}.market-analysis",
            capability_id="MARKET_ANALYSIS",
            assessment_due_at="2026-08-13T12:59:00+00:00",
        )
        assert self.assessor.record is not None
        before = dict(self.assessor.record)
        with self.assertRaisesRegex(
            CapabilityEvaluationStoreError, "ASSESSOR_MUST_BE_INDEPENDENT"
        ):
            self.store.acknowledge_assessor_spawn(
                cycle_id=_CYCLE,
                dispatch_id=str(prepared["dispatch_id"]),
                execution_ref=_SUBJECT_GOAL_ID,
            )
        self.assertEqual(before, self.assessor.record)

    def test_general_capability_cli_has_only_derived_three_step_surface(self) -> None:
        parsed = (
            market_cycle_cli._parser()  # noqa: SLF001 - direct CLI contract probe
            .parse_args(
                [
                    "capability-prepare-assessor",
                    _CYCLE,
                    "MARKET_ANALYSIS",
                    f"{_CYCLE}.market-analysis",
                    "2026-08-13T12:59:00+00:00",
                ]
            )
        )
        self.assertEqual("capability-prepare-assessor", parsed.command)
        preregistered = market_cycle_cli._parser().parse_args(  # noqa: SLF001
            ["capability-preregister", _CYCLE, "MARKET_ANALYSIS"]
        )
        sealed = market_cycle_cli._parser().parse_args(  # noqa: SLF001
            [
                "capability-seal-assessment",
                _CYCLE,
                "MARKET_ANALYSIS",
                f"{_CYCLE}.assessment",
            ]
        )
        self.assertEqual("capability-preregister", preregistered.command)
        self.assertEqual("capability-seal-assessment", sealed.command)
        for namespace in (parsed, preregistered, sealed):
            for forbidden in ("subject", "assessor", "rubric", "findings"):
                self.assertNotIn(forbidden, vars(namespace))
        assessor_ack = market_cycle_cli._parser().parse_args(  # noqa: SLF001
            [
                "controller-ack-worker-spawn",
                _CYCLE,
                "capability-assessor-v1",
                "dispatch-001",
                _ASSESSOR_GOAL_ID,
            ]
        )
        assessor_complete = market_cycle_cli._parser().parse_args(  # noqa: SLF001
            [
                "controller-complete-worker",
                _CYCLE,
                "capability-assessor-v1",
                "dispatch-001",
                "0" * 64,
            ]
        )
        self.assertEqual("capability-assessor-v1", assessor_ack.worker_id)
        self.assertEqual("capability-assessor-v1", assessor_complete.worker_id)

    def test_assessment_round_trips_sealed_author_and_decision_hashes(self) -> None:
        hypothesis = self._seal_hypothesis()
        task = self._preregister("MARKET_ANALYSIS")
        self.clock.value = "2026-08-13T12:00:12+00:00"
        self._complete_assessor("MARKET_ANALYSIS")
        assessment = self.store.seal_assessment(
            cycle_id=_CYCLE,
            capability_id="MARKET_ANALYSIS",
            assessment_id=f"{_CYCLE}.market.assessment",
        )
        self.assertEqual(self.clock.value, assessment.assessed_at)
        self.assertEqual(task.subject_agent_id, assessment.subject_agent_id)
        self.assertEqual(task.rubric, assessment.rubric)
        self.assertEqual(
            task.decision_delivery_sha256,
            assessment.decision_delivery_sha256,
        )
        self.assertEqual(
            hypothesis.agent_decision_sha256, assessment.decision_sha256
        )
        replayed = self.store.load_assessment(_CYCLE, "MARKET_ANALYSIS")
        self.assertEqual(replayed.assessment_sha256, assessment.assessment_sha256)
        idempotent = self.store.seal_assessment(
            cycle_id=_CYCLE,
            capability_id="MARKET_ANALYSIS",
            assessment_id=f"{_CYCLE}.market.assessment",
        )
        self.assertEqual(idempotent.assessment_sha256, assessment.assessment_sha256)
        self.assertEqual(
            PreOutcomeCapabilityAssessmentV1.from_dict(
                assessment.to_dict()
            ).assessment_sha256,
            assessment.assessment_sha256,
        )
        self.assertGreaterEqual(self.gate.calls, 4)
        self._assert_production_runtime_seals_assessment_without_outcome()

    def test_assessment_after_outcome_is_rejected_under_same_cycle_lock(self) -> None:
        self._use_capability_policy("HYPOTHESIS_GENERATION")
        self._preregister("HYPOTHESIS_GENERATION")
        hypothesis = HypothesisRecord.from_dict(
            self.repository.load_artifact(_CYCLE, "HypothesisRecord")
        )
        hypothesis_ref = self.state.artifact_refs[1]
        due = (
            datetime.fromisoformat(self.snapshot.decision_at)
            + timedelta(seconds=self.snapshot.outcome_horizon_seconds)
        ).isoformat()
        plan = BehaviorPlan(
            plan_id=f"{_CYCLE}.plan",
            cycle_id=_CYCLE,
            hypothesis_record_ref=hypothesis_ref,
            decision_at=hypothesis.decision_at,
            agent_delivered_at=hypothesis.agent_delivered_at,
            sealed_at="2026-08-13T12:00:11+00:00",
            risk_mode="REFERENCE",
            execution_mapping="NOT_READY",
            executable_quantity=None,
            agent_request_sha256=hypothesis.agent_request_sha256,
            agent_delivery_path=hypothesis.agent_delivery_path,
            agent_delivery_sha256=hypothesis.agent_delivery_sha256,
            agent_decision_text=hypothesis.agent_decision_text,
            agent_decision_size_bytes=hypothesis.agent_decision_size_bytes,
            agent_decision_sha256=hypothesis.agent_decision_sha256,
            projection_status=hypothesis.projection_status,
            projection_reason=hypothesis.projection_reason,
            hypothesis_index=hypothesis.hypothesis_index,
            agent_action_text=hypothesis.agent_action_text,
            agent_position_text=hypothesis.agent_position_text,
            outcome_due_at=due,
            outcome_tolerance_seconds=hypothesis.outcome_tolerance_seconds,
            theory_identity=V332_THEORY_IDENTITY,
        )
        self.state = self.repository.transition(
            expected=self.state,
            artifacts=(plan,),
            next_stage="PLAN_SEALED",
            next_action="WAIT_FOR_OUTCOME",
        )
        self.state = self.repository.transition(
            expected=self.state,
            artifacts=(),
            next_stage="OUTCOME_DUE",
            next_action="CAPTURE_OUTCOME",
        )
        outcome = Outcome(
            outcome_id=f"{_CYCLE}.outcome",
            cycle_id=_CYCLE,
            behavior_plan_ref=self.state.artifact_refs[2],
            due_at=due,
            tolerance_seconds=60,
            observed_at=due,
            sealed_at=due,
            terminal_status="TYPED_MISSING",
            endpoint_observation=None,
            typed_missing="UNKNOWN_COVERAGE_LOSS",
            path_observations={
                "schema_id": "agent_trade_emotion_v332_ordered_outcome_path",
                "schema_version": "1.0.0",
                "status": "CENSORED",
                "path_start_at": self.repository.load_artifact(
                    _CYCLE, "BehaviorPlan"
                )["agent_delivered_at"],
                "path_end_at": due,
                "interval": "15m",
                "intrabar_order": "UNRESOLVED_WITHIN_BAR",
                "points": [],
                "coverage": {
                    "expected_point_count": 3,
                    "observed_point_count": 0,
                    "gap_count": 3,
                    "covers_all_closed_intervals": False,
                },
                "missing_reason": "ORDERED_PATH_UNAVAILABLE",
                "source_health": [],
            },
            raw_refs=(),
            theory_identity=V332_THEORY_IDENTITY,
        )
        self.state = self.repository.transition(
            expected=self.state,
            artifacts=(outcome,),
            next_stage="OUTCOME_SEALED",
            next_action="REVIEW",
        )
        with self.assertRaisesRegex(
            CapabilityEvaluationStoreError, "OUTCOME_ALREADY_SEALED"
        ):
            self.store.seal_assessment(
                cycle_id=_CYCLE,
                capability_id="HYPOTHESIS_GENERATION",
                assessment_id=f"{_CYCLE}.hypothesis.assessment",
            )

    def test_assessment_rejects_delivery_or_physical_goal_tampering(self) -> None:
        task = self._preregister("MARKET_ANALYSIS")
        delivery_path = (
            self.repository.root
            / _CYCLE
            / "transport"
            / "agent-delivery.json"
        )
        original_delivery = delivery_path.read_bytes()
        delivery_path.write_bytes(b"{}\n")
        with self.assertRaisesRegex(
            CapabilityEvaluationStoreError,
            "AGENT_DELIVERY_INVALID",
        ):
            self.store.seal_assessment(
                cycle_id=_CYCLE,
                capability_id="MARKET_ANALYSIS",
                assessment_id=f"{_CYCLE}.market.assessment",
            )
        delivery_path.write_bytes(original_delivery)

        task_path = self.store._entry_path(  # noqa: SLF001 - corruption probe
            _CYCLE, "MARKET_ANALYSIS", "TASK"
        )
        entry = loads_json_strict(task_path.read_bytes())
        assert isinstance(entry, dict)
        document = dict(entry["document"])
        document["subject_agent_id"] = (
            "codex-thread:33333333-3333-3333-3333-333333333333"
        )
        entry["document"] = document
        entry["document_sha256"] = canonical_digest(document)
        task_path.write_bytes(canonical_bytes(entry) + b"\n")
        self.assertNotEqual(task.subject_agent_id, document["subject_agent_id"])
        with self.assertRaisesRegex(
            CapabilityEvaluationStoreError,
            "PHYSICAL_GOAL_DELIVERY_BINDING_MISMATCH",
        ):
            self.store.seal_assessment(
                cycle_id=_CYCLE,
                capability_id="MARKET_ANALYSIS",
                assessment_id=f"{_CYCLE}.market.assessment",
            )

    def _assert_production_runtime_seals_assessment_without_outcome(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "capability-production-runtime"
            policy = replace(
                _policy("HYPOTHESIS_GENERATION"),
                experiment_id="capability-production-runtime.policy",
                run_id=runtime_root.name,
            )
            initialize_v332_run(
                runtime_root,
                theory_package=_V332_PACKAGE,
                experiment_policy=policy,
            )
            clock = _Clock()
            runtime = build_market_cycle_runtime(
                runtime_root=runtime_root,
                theory_package=_V332_PACKAGE,
                expected_theory_identity=V332_THEORY_IDENTITY,
                clock=clock,
            )
            state = runtime.service.create(_request())
            raw_store = FileRawCaptureStore(runtime_root)
            raw_ref = ArtifactRef.from_dict(
                raw_store.seal_response(
                    cycle_id=_CYCLE,
                    capture_id="production-fixture",
                    payload=b"production-fixture",
                    summary={"component_id": "PRODUCTION_REGRESSION_FIXTURE"},
                )
            )
            snapshot = _snapshot(raw_ref)
            state = runtime.repository.transition(
                expected=state,
                artifacts=(snapshot,),
                next_stage="INPUT_SEALED",
                next_action="ANALYZE",
            )
            pending = runtime.service.run_next(_CYCLE)
            self.assertEqual("AGENT_DELIVERY_PENDING", pending.pending_reason)

            with mock.patch.dict(
                os.environ, {"CODEX_THREAD_ID": _SUBJECT_THREAD_ID}, clear=False
            ):
                self.assertEqual(
                    "CREATED",
                    runtime.mailbox.persist_goal_decision(
                        _CYCLE,
                        _DECISION.encode("utf-8"),
                        media_type="text/markdown",
                    ),
                )
            analyzed = runtime.service.run_next(_CYCLE)
            self.assertTrue(analyzed.changed)
            self.assertEqual("ANALYZED", analyzed.state.stage)
            delivery_binding = runtime.mailbox.goal_decision_delivery_binding(_CYCLE)
            assert delivery_binding is not None
            self.assertEqual(_SUBJECT_GOAL_ID, delivery_binding["physical_goal_id"])
            production_store = FileCapabilityEvaluationStore(
                runtime, clock=clock
            )
            assessor = production_store.prepare_assessor(
                cycle_id=_CYCLE,
                task_id=f"{_CYCLE}.hypothesis-generation",
                capability_id="HYPOTHESIS_GENERATION",
                assessment_due_at="2026-08-13T12:58:00+00:00",
            )
            assessor = production_store.acknowledge_assessor_spawn(
                cycle_id=_CYCLE,
                dispatch_id=str(assessor["dispatch_id"]),
                execution_ref=_ASSESSOR_GOAL_ID,
            )
            task = production_store.preregister(
                cycle_id=_CYCLE,
                capability_id="HYPOTHESIS_GENERATION",
            )
            hypothesis = HypothesisRecord.from_dict(
                runtime.repository.load_artifact(_CYCLE, "HypothesisRecord")
            )
            self.assertEqual(_SUBJECT_GOAL_ID, task.subject_agent_id)
            self.assertEqual(
                hypothesis.agent_delivery_sha256,
                task.decision_delivery_sha256,
            )

            clock.value = "2026-08-13T12:00:04+00:00"
            findings_result = {
                "schema_id": "agent-trade-emotion.v332-capability-assessor-findings",
                "schema_version": "1.0.0",
                "cycle_id": _CYCLE,
                "worker_id": "capability-assessor-v1",
                "capability_id": "HYPOTHESIS_GENERATION",
                "task_id": task.task_id,
                "task_sha256": task.task_sha256,
                "assessor_execution_ref": task.assessor_id,
                "completed_at": clock.value,
                "findings": [
                    item.to_dict()
                    for item in self._findings("HYPOTHESIS_GENERATION")
                ],
            }
            findings_path = (
                runtime_root
                / "cycles"
                / _CYCLE
                / "transport"
                / "capability-assessor-findings.json"
            )
            write_once_json(findings_path, findings_result)
            self._write_worker_result(
                runtime=runtime,
                record=assessor,
                body="Independent pre-outcome findings sealed.\n",
                completed_at=clock.value,
            )
            runtime.controller_state.complete_worker(
                _CYCLE,
                "capability-assessor-v1",
                str(assessor["dispatch_id"]),
                hashlib.sha256(findings_path.read_bytes()).hexdigest(),
            )

            self.assertNotIn(
                "Outcome",
                tuple(item.artifact_type for item in analyzed.state.artifact_refs),
            )
            clock.value = "2026-08-13T12:00:05+00:00"
            assessment = production_store.seal_assessment(
                cycle_id=_CYCLE,
                capability_id="HYPOTHESIS_GENERATION",
                assessment_id=f"{_CYCLE}.hypothesis.assessment",
            )
            self.assertEqual(task.task_sha256, assessment.task_sha256)
            self.assertEqual(clock.value, assessment.assessed_at)


if __name__ == "__main__":
    unittest.main()
