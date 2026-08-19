from __future__ import annotations

import ast
import copy
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from trade_system.theory_paper_v2.application.market_cycle.ports import (
    AgentPacket,
    AgentReviewPacket,
    MarketDataObservation,
    OutcomeObservation,
)
from trade_system.theory_paper_v2.application.market_cycle.service import (
    CONTROLLER_DECISION_DEADLINE_EXPIRED,
    CONTROLLER_REVIEW_DEADLINE_EXPIRED,
    AdvanceResult,
    CycleService,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle import (
    AGENT_OUTPUT_INCOMPLETE,
    VerifiedMemoryItem,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    CURRENT_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    CycleRequest,
    LAWFUL_REFERENCE_ACTIONS,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.codex_mailbox import (
    LocalMarketCycleAgentMailbox,
    MarketCycleAgentMailboxError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.controller_state import (
    FileControllerState,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.repository import (
    FileCycleRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.runtime import (
    ManifestBoundCycleService,
)
from trade_system.theory_paper_v2.presentation import market_cycle as market_cycle_cli
from trade_system.theory_paper_v2.presentation.market_cycle import _parser


_ROOT = Path(__file__).resolve().parents[1]
_ACTIVE_ROOTS = (
    _ROOT / "trade_system" / "theory_paper_v2" / "domain" / "market_cycle",
    _ROOT / "trade_system" / "theory_paper_v2" / "application" / "market_cycle",
    _ROOT / "trade_system" / "theory_paper_v2" / "infrastructure" / "market_cycle",
    _ROOT / "trade_system" / "theory_paper_v2" / "infrastructure" / "market_data",
    _ROOT / "trade_system" / "theory_paper_v2" / "presentation" / "market_cycle.py",
)
_AGENT_HOT_PATH_THEORY_FILES = (
    "README.md",
    "01_MARKET_COGNITION.md",
    "02_DYNAMIC_POSITION_MANAGEMENT.md",
    "03_HYPOTHESIS_SYSTEM.md",
    "04_EXECUTION_AND_AGENT.md",
    "05_RISK_AND_BOUNDARIES.md",
)
_MINIMAL_COLD_THEORY = {
    name: (_ROOT / "theory" / "versions" / "v3.3.1" / name).read_text(
        encoding="utf-8"
    )
    for name in _AGENT_HOT_PATH_THEORY_FILES
}


class MutableClock:
    def __init__(self, current: str) -> None:
        self.current = current

    def __call__(self) -> str:
        return self.current

    def monotonic_ns(self) -> int:
        return 1


class FixedMarketData:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self, request) -> MarketDataObservation:  # noqa: ANN001
        self.calls += 1
        raw = {
            "artifact_type": "RawCapture",
            "artifact_id": f"{request.cycle_id}.raw",
            "path": f"raw/{request.cycle_id}.json",
            "size_bytes": 100,
            "sha256": "a" * 64,
        }
        common = {
            "available_at": "2026-08-11T00:00:59+00:00",
            "raw_sha256": raw["sha256"],
        }
        return MarketDataObservation(
            captured_at="2026-08-11T00:01:00+00:00",
            cutoff_at="2026-08-11T00:01:00+00:00",
            core_observations={
                "server_time": {
                    **common,
                    "value": "2026-08-11T00:00:59+00:00",
                },
                "instrument": {**common, "value": request.instrument_id},
                "mark_price": {**common, "value": "118000.1"},
                "closed_15m_bars": {
                    **common,
                    "last_closed_at": "2026-08-11T00:00:00+00:00",
                    "value": [
                        {
                            "closed_at": "2026-08-11T00:00:00+00:00",
                            "close": "118000.0",
                        }
                    ],
                },
            },
            optional_observations={},
            unknowns=(
                {
                    "component_id": "ORDER_FLOW",
                    "status": "UNKNOWN",
                    "missing_reason": "UNKNOWN_NOT_OBSERVED",
                    "missing_is_zero": False,
                },
            ),
            raw_refs=(raw,),
            source_health=(),
        )


class FixedOutcome:
    def __init__(self, *, observed: bool = False) -> None:
        self.calls = 0
        self.observed = observed

    def observe(self, request) -> OutcomeObservation:  # noqa: ANN001
        self.calls += 1
        if self.observed:
            raw = {
                "artifact_type": "RawOutcomeCapture",
                "artifact_id": f"{request.cycle_id}.outcome.raw",
                "path": f"raw/{request.cycle_id}.outcome.json",
                "size_bytes": 120,
                "sha256": "d" * 64,
            }
            return OutcomeObservation(
                observed_at=request.due_at,
                effective_at=request.due_at,
                available_at=request.due_at,
                terminal_status="OBSERVED",
                value="118250.5",
                unit="USDT",
                missing_reason=None,
                raw_ref=raw,
                source_health=(),
            )
        return OutcomeObservation(
            observed_at=request.due_at,
            effective_at=None,
            available_at=None,
            terminal_status="MISSING",
            value=None,
            unit=None,
            missing_reason="UNKNOWN_COVERAGE_LOSS",
            raw_ref=None,
            source_health=(),
        )


class MarketCycleCoreTest(unittest.TestCase):
    maxDiff = None

    @staticmethod
    def _request(
        cycle_id: str,
        *,
        profile: str = "COLD",
        data_profile: str = "BASELINE_PRICE",
    ) -> CycleRequest:
        return CycleRequest(
            request_id=f"{cycle_id}.request",
            cycle_id=cycle_id,
            requested_at="2026-08-11T00:00:00+00:00",
            venue_id="OKX",
            instrument_id="BTC-USDT-SWAP",
            contract_identity="OKX:BTC-USDT-SWAP:linear",
            analysis_profile=profile,
            data_profile=data_profile,
            outcome_horizon_seconds=900,
            outcome_tolerance_seconds=30,
            lawful_actions=(
                "LONG_REFERENCE",
                "SHORT_REFERENCE",
                "WATCH_REFERENCE",
                "WAIT",
                "CONDITIONAL_TRIGGER",
                "OPEN_REFERENCE",
                "ADD_REFERENCE",
                "HARVEST_REFERENCE",
                "HEDGE_REFERENCE",
                "OTHER_INFORMATION_ACTION",
            ),
        )

    @staticmethod
    def _service(
        cycles_root: Path,
        clock: MutableClock,
        *,
        observed_outcome: bool = False,
        verified_memory: tuple[VerifiedMemoryItem, ...] = (),
    ) -> tuple[
        CycleService,
        FileCycleRepository,
        LocalMarketCycleAgentMailbox,
        FixedMarketData,
        FixedOutcome,
    ]:
        market = FixedMarketData()
        outcome = FixedOutcome(observed=observed_outcome)
        repository = FileCycleRepository(cycles_root)
        mailbox = LocalMarketCycleAgentMailbox(cycles_root, clock=clock)
        runtime_root = cycles_root.parent
        controller_state = FileControllerState(
            runtime_root,
            run_id=runtime_root.name,
            run_manifest_identity_sha256="1" * 64,
            run_manifest_raw_sha256="2" * 64,
            theory_manifest_sha256=CURRENT_THEORY_IDENTITY.manifest_digest,
            implementation_sha256="4" * 64,
            contract_identity="V331_AGENT_FIRST_VERBATIM_DECISION_REVIEW_V1",
            market_contract_identity="OKX:BTC-USDT-SWAP:linear",
            experiment_identity=("V331_OFFLINE_CONTROLLER_TEST@" + "5" * 64),
            clock=clock,
        )
        service = CycleService(
            market_data=market,
            agent=mailbox,
            clock=clock,
            repository=repository,
            outcome=outcome,
            theory_fragments=_MINIMAL_COLD_THEORY,
            controller_dispatch=controller_state,
            verified_memory=verified_memory,
        )
        return service, repository, mailbox, market, outcome

    def _open_decision_request(
        self,
        service: CycleService,
        mailbox: LocalMarketCycleAgentMailbox,
        cycle_id: str,
        *,
        data_profile: str = "BASELINE_PRICE",
        dispatch: bool = True,
    ) -> dict[str, object]:
        self.assertEqual(
            service.create(self._request(cycle_id, data_profile=data_profile)).stage,
            "REQUESTED",
        )
        self.assertEqual(service.run_next(cycle_id).state.stage, "INPUT_SEALED")
        pending = service.run_next(cycle_id)
        self.assertFalse(pending.changed)
        self.assertEqual(pending.state.stage, "INPUT_SEALED")
        self.assertEqual(pending.pending_reason, "AGENT_DELIVERY_PENDING")
        request = mailbox.request(cycle_id)
        self.assertIsNotNone(request)
        request_value = dict(request or {})
        packet = request_value["packet"]
        self.assertIsInstance(packet, dict)
        self.assertEqual(
            packet["decision_deadline_at"], "2026-08-11T00:16:00+00:00"
        )
        self.assertEqual(packet["time_budget_seconds"], 600)
        if dispatch:
            clock = service._clock
            assert isinstance(clock, MutableClock)
            self._dispatch_worker(
                service,
                Path(mailbox._root),
                clock,
                cycle_id,
                "decision-v1",
                request_value,
            )
        return request_value

    def _to_plan_sealed(
        self,
        service: CycleService,
        mailbox: LocalMarketCycleAgentMailbox,
        clock: MutableClock,
        cycle_id: str,
        decision_bytes: bytes,
    ) -> None:
        self._open_decision_request(service, mailbox, cycle_id)
        clock.current = "2026-08-11T00:01:02+00:00"
        self.assertEqual(
            service.deliver_agent_decision(cycle_id, decision_bytes), "CREATED"
        )
        self.assertEqual(
            self._complete_worker(
                service, Path(mailbox._root), cycle_id, "decision-v1"
            )["status"],
            "COMPLETED",
        )
        self.assertEqual(service.run_next(cycle_id).state.stage, "ANALYZED")
        self.assertEqual(service.run_next(cycle_id).state.stage, "PLAN_SEALED")
        pending = service.run_next(cycle_id)
        self.assertFalse(pending.changed)
        self.assertEqual(pending.state.stage, "PLAN_SEALED")
        self.assertEqual(pending.pending_reason, "OUTCOME_WINDOW_NOT_OPEN")
        self.assertFalse(
            any(
                str(event_id).startswith("outcome-due:")
                for event_id in service.controller_status()["events"]
            )
        )

    def _to_outcome_sealed(
        self,
        service: CycleService,
        mailbox: LocalMarketCycleAgentMailbox,
        clock: MutableClock,
        cycle_id: str,
        decision_bytes: bytes = b"No structured action or position supplied.\n",
    ) -> None:
        self._to_plan_sealed(service, mailbox, clock, cycle_id, decision_bytes)
        clock.current = "2026-08-11T00:16:00+00:00"
        self.assertEqual(service.run_next(cycle_id).state.stage, "OUTCOME_DUE")
        self.assertEqual(service.run_next(cycle_id).state.stage, "OUTCOME_SEALED")

    def _dispatch_pending_review(
        self,
        service: CycleService,
        mailbox: LocalMarketCycleAgentMailbox,
        clock: MutableClock,
        cycle_id: str,
    ) -> dict[str, object]:
        request = mailbox.review_request(cycle_id)
        self.assertIsNotNone(request)
        request_value = dict(request or {})
        self._dispatch_worker(
            service,
            Path(mailbox._root),
            clock,
            cycle_id,
            "review-v1",
            request_value,
        )
        return request_value

    @staticmethod
    def _decision_packet(request: dict[str, object]) -> AgentPacket:
        packet = request["packet"]
        assert isinstance(packet, dict)
        return AgentPacket(
            cycle_id=packet["cycle_id"],
            request_id=packet["request_id"],
            theory_identity=packet["theory_identity"],
            theory_fragments=packet["theory_fragments"],
            input_snapshot_ref=packet["input_snapshot_ref"],
            input_snapshot=packet["input_snapshot"],
            lawful_actions=tuple(packet["lawful_actions"]),
            memory_context=packet["memory_context"],
            deterministic_calculations=packet["deterministic_calculations"],
            decision_deadline_at=packet["decision_deadline_at"],
            token_budget=packet["token_budget"],
            time_budget_seconds=packet["time_budget_seconds"],
        )

    @staticmethod
    def _review_packet(request: dict[str, object]) -> AgentReviewPacket:
        packet = request["packet"]
        assert isinstance(packet, dict)
        return AgentReviewPacket(
            cycle_id=packet["cycle_id"],
            theory_identity=packet["theory_identity"],
            theory_fragments=packet["theory_fragments"],
            input_snapshot_ref=packet["input_snapshot_ref"],
            input_snapshot=packet["input_snapshot"],
            agent_decision_ref=packet["agent_decision_ref"],
            agent_decision=packet["agent_decision"],
            hypothesis_record_ref=packet["hypothesis_record_ref"],
            hypothesis_record=packet["hypothesis_record"],
            behavior_plan_ref=packet["behavior_plan_ref"],
            behavior_plan=packet["behavior_plan"],
            outcome_ref=packet["outcome_ref"],
            outcome=packet["outcome"],
            memory_context=packet["memory_context"],
            deterministic_calculations=packet["deterministic_calculations"],
            token_budget=packet["token_budget"],
            time_budget_seconds=packet["time_budget_seconds"],
        )

    @staticmethod
    def _write_canonical_sidecar(path: Path, document: dict[str, object]) -> bytes:
        raw = canonical_bytes(document) + b"\n"
        path.write_bytes(raw)
        return raw

    @staticmethod
    def _write_controller_worker_task(
        cycles_root: Path,
        cycle_id: str,
        request: dict[str, object],
        worker_id: str,
        *,
        created_at: str,
    ) -> Path:
        specs = {
            "decision-v1": (
                "DECISION",
                "INPUT_SEALED",
                "V331_AGENT_FIRST_DECISION_READABLE_V1",
                "agent-request.json",
                "agent_request_and_non_authoritative_calculations",
            ),
            "review-v1": (
                "REVIEW",
                "OUTCOME_SEALED",
                "V331_AGENT_FIRST_REVIEW_READABLE_V1",
                "agent-review-request.json",
                "review_request",
            ),
        }
        task_kind, stage, worker_contract, request_name, input_role = specs[worker_id]
        request_path = cycles_root / cycle_id / "transport" / request_name
        request_raw = request_path.read_bytes()
        packet = request["packet"]
        assert isinstance(packet, dict)
        budget = packet["time_budget_seconds"]
        assert isinstance(budget, int)
        if worker_id == "review-v1":
            deadline_at = packet["review_due_at"]
            available_at = packet["review_requested_at"]
        else:
            created = datetime.fromisoformat(created_at)
            deadline_at = (created + timedelta(seconds=budget)).isoformat()
            snapshot = packet["input_snapshot"]
            assert isinstance(snapshot, dict)
            available_at = snapshot["sealed_at"]
        assert isinstance(deadline_at, str)
        assert isinstance(available_at, str)
        task_path = (
            cycles_root.parent
            / "agents"
            / f"{cycle_id}--{worker_id}"
            / "task.json"
        )
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task = {
            "schema_id": "agent_trade_emotion_v331_worker_task",
            "schema_version": "1.0.0",
            "worker_contract_identity": worker_contract,
            "run_id": cycles_root.parent.name,
            "cycle_id": cycle_id,
            "worker_id": worker_id,
            "task_kind": task_kind,
            "stage": stage,
            "identities": {
                "agent_contract_identity": (
                    "V331_AGENT_FIRST_VERBATIM_DECISION_REVIEW_V1"
                ),
                "implementation_sha256": "4" * 64,
                "run_manifest_sha256": "2" * 64,
                "theory_manifest_sha256": CURRENT_THEORY_IDENTITY.manifest_digest,
                "experiment_contract_sha256": "5" * 64,
            },
            "experiment_identity": "V331_OFFLINE_CONTROLLER_TEST@" + "5" * 64,
            "timing": {
                "created_at": created_at,
                "not_before_at": created_at,
                "frozen_deadline_at": deadline_at,
                "hard_stop_seconds": budget,
            },
            "input_refs": [
                {
                    "role": input_role,
                    "path": str(request_path.resolve(strict=True)),
                    "sha256": hashlib.sha256(request_raw).hexdigest(),
                    "available_at": available_at,
                }
            ],
            "write_boundary": {
                "worker_root": str(task_path.parent.resolve()),
                "events_path": str((task_path.parent / "events.jsonl").resolve()),
                "result_path": str((task_path.parent / "result.json").resolve()),
                "worker_may_write_only": ["events.jsonl", "result.json"],
            },
        }
        task_path.write_bytes(canonical_bytes(task) + b"\n")
        return task_path

    def _dispatch_worker(
        self,
        service: CycleService,
        cycles_root: Path,
        clock: MutableClock,
        cycle_id: str,
        worker_id: str,
        request: dict[str, object],
    ) -> dict[str, object]:
        task_path = self._write_controller_worker_task(
            cycles_root,
            cycle_id,
            request,
            worker_id,
            created_at=clock.current,
        )
        prepared = service.controller_prepare_worker(
            cycle_id, worker_id, task_path
        )
        dispatch_id = prepared["dispatch_id"]
        assert isinstance(dispatch_id, str)
        service.controller_mark_worker_spawn_requested(
            cycle_id, worker_id, dispatch_id
        )
        dispatched = service.controller_acknowledge_worker_spawn(
            cycle_id,
            worker_id,
            dispatch_id,
            f"codex-worker:{cycle_id}:{worker_id}",
        )
        return dict(dispatched)

    @staticmethod
    def _complete_worker(
        service: CycleService,
        cycles_root: Path,
        cycle_id: str,
        worker_id: str,
    ) -> dict[str, object]:
        dispatch = service.controller_recover_worker(cycle_id, worker_id)
        dispatch_id = dispatch["dispatch_id"]
        assert isinstance(dispatch_id, str)
        output_name = (
            "agent-review-delivery.json"
            if worker_id == "review-v1"
            else "agent-delivery.json"
        )
        output_path = cycles_root / cycle_id / "transport" / output_name
        delivery = loads_json_strict(output_path.read_bytes())
        text_field = (
            "review_text" if worker_id == "review-v1" else "decision_text"
        )
        completed_at = delivery["delivered_at"]
        task_path = (
            cycles_root.parent
            / "agents"
            / f"{cycle_id}--{worker_id}"
            / "task.json"
        )
        task = loads_json_strict(task_path.read_bytes())
        result = {
            "schema_id": "agent_trade_emotion_v331_worker_result",
            "schema_version": "1.0.0",
            "run_id": cycles_root.parent.name,
            "cycle_id": cycle_id,
            "worker_id": worker_id,
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
            "body_markdown": delivery[text_field],
        }
        (task_path.parent / "result.json").write_bytes(
            canonical_bytes(result) + b"\n"
        )
        completed = service.controller_complete_worker(
            cycle_id,
            worker_id,
            dispatch_id,
            hashlib.sha256(output_path.read_bytes()).hexdigest(),
        )
        return dict(completed)

    @staticmethod
    def _resign_packet_document(document: dict[str, object]) -> None:
        packet = document["packet"]
        packet_bytes = canonical_bytes(packet)
        document["packet_size_bytes"] = len(packet_bytes)
        document["packet_sha256"] = hashlib.sha256(packet_bytes).hexdigest()

    def test_unimplemented_profiles_fail_before_cycle_or_external_calls(self) -> None:
        for profile in ("DELTA", "EVENT_FAST"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                clock = MutableClock("2026-08-11T00:00:01+00:00")
                service, _, _, market, outcome = self._service(
                    Path(temporary) / "cycles", clock
                )
                cycle_id = f"not-ready-{profile.lower()}"
                with self.assertRaisesRegex(
                    RuntimeError,
                    f"ANALYSIS_PROFILE_NOT_READY:{profile}",
                ):
                    service.create(self._request(cycle_id, profile=profile))
                self.assertFalse((Path(temporary) / "cycles" / cycle_id).exists())
                self.assertEqual((market.calls, outcome.calls), (0, 0))

    def test_worker_dispatch_admission_and_request_only_expiry_are_typed_and_artifact_free(
        self,
    ) -> None:
        parsed = _parser().parse_args(
            ["controller-expire-worker", "deadline-expired", "daily-deep-v1"]
        )
        self.assertEqual(parsed.command, "controller-expire-worker")
        self.assertEqual(parsed.cycle_id, "deadline-expired")
        self.assertEqual(parsed.worker_id, "daily-deep-v1")
        self.assertFalse(hasattr(parsed, "reason_code"))
        for worker_id in ("decision-v1", "review-v1"):
            with self.subTest(worker_id=worker_id), self.assertRaises(SystemExit):
                _parser().parse_args(
                    ["controller-expire-worker", "deadline-expired", worker_id]
                )
        with self.assertRaises(SystemExit):
            _parser().parse_args(["controller-resolve-event", "obsolete-event"])
        with self.assertRaises(SystemExit):
            _parser().parse_args(
                [
                    "controller-prepare-worker",
                    "cycle",
                    "daily-deep-v1",
                    "--next-slot-at",
                    "2026-08-11T00:30:00+00:00",
                ]
            )
        for service_type in (CycleService, ManifestBoundCycleService):
            for method_name in (
                "controller_schedule_event",
                "controller_acknowledge_wake",
                "controller_resolve_event",
            ):
                with self.subTest(
                    service_type=service_type.__name__, method_name=method_name
                ):
                    self.assertFalse(hasattr(service_type, method_name))
        for command in (
            "controller-prepare-worker",
            "controller-mark-worker-spawn-requested",
            "controller-ack-worker-spawn",
            "controller-complete-worker",
            "controller-recover-worker",
            "controller-expire-worker",
        ):
            arguments = [command, "paper-action-cycle", "paper-action-v1"]
            if command == "controller-mark-worker-spawn-requested":
                arguments.append("dispatch-paper-action")
            elif command == "controller-ack-worker-spawn":
                arguments.extend(
                    ["dispatch-paper-action", "codex:/root/paper-agent"]
                )
            elif command == "controller-complete-worker":
                arguments.extend(["dispatch-paper-action", "a" * 64])
            with self.subTest(command=command), self.assertRaises(SystemExit):
                _parser().parse_args(arguments)

        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary)
            cycles_root = runtime_root / "cycles"
            clock = MutableClock("2026-08-11T00:01:01+00:00")
            service, repository, mailbox, _, _ = self._service(cycles_root, clock)

            wrong_stage = "deadline-wrong-stage"
            service.create(self._request(wrong_stage))
            with self.assertRaisesRegex(
                RuntimeError,
                "MARKET_CYCLE_CONTROLLER_AGENT_DECISION_STAGE_INVALID",
            ):
                service.controller_expire_worker(wrong_stage, "decision-v1")

            request_only_cycle = "deadline-request-only"
            request_only = self._open_decision_request(
                service, mailbox, request_only_cycle, dispatch=False
            )
            packet = request_only["packet"]
            assert isinstance(packet, dict)
            snapshot = packet["input_snapshot"]
            assert isinstance(snapshot, dict)
            expected_request_only_deadline = (
                datetime.fromisoformat(snapshot["sealed_at"])
                + timedelta(seconds=600)
            ).isoformat()
            deadline_record = service._controller_method("decision_deadline")(
                request_only_cycle
            )
            self.assertEqual(deadline_record["status"], "REQUEST_ONLY")
            self.assertIsNone(deadline_record["dispatch_id"])
            self.assertEqual(
                deadline_record["hard_stop_at"], expected_request_only_deadline
            )
            before = repository.load_state(request_only_cycle)
            clock.current = (
                datetime.fromisoformat(expected_request_only_deadline)
                - timedelta(seconds=1)
            ).isoformat()
            with self.assertRaisesRegex(
                RuntimeError, "CONTROLLER_WORKER_DEADLINE_NOT_EXPIRED"
            ):
                service.controller_expire_worker(request_only_cycle, "decision-v1")
            self.assertEqual(repository.load_state(request_only_cycle), before)

            clock.current = expected_request_only_deadline
            expired = service.controller_expire_worker(
                request_only_cycle, "decision-v1"
            )
            self.assertTrue(expired["domain_changed"])
            self.assertEqual(
                expired["reason_code"], CONTROLLER_DECISION_DEADLINE_EXPIRED
            )
            expired_state = repository.load_state(request_only_cycle)
            self.assertEqual(expired_state.stage, "ANALYSIS_FAILED")
            self.assertTrue(expired_state.terminal)
            self.assertEqual(
                expired_state.failure_reason, CONTROLLER_DECISION_DEADLINE_EXPIRED
            )
            self.assertEqual(expired_state.artifact_refs, before.artifact_refs)
            self.assertEqual(
                tuple(ref.artifact_type for ref in expired_state.artifact_refs),
                ("InputSnapshot",),
            )
            self.assertFalse(
                (
                    cycles_root
                    / request_only_cycle
                    / "transport"
                    / "agent-delivery.json"
                ).exists()
            )
            self.assertEqual(service.controller_status()["worker_dispatches"], {})

            replay = service.controller_expire_worker(
                request_only_cycle, "decision-v1"
            )
            self.assertFalse(replay["domain_changed"])
            self.assertEqual(replay["state"], expired_state.to_dict())

            prepared_cycle = "deadline-prepared-only"
            clock.current = "2026-08-11T00:01:01+00:00"
            prepared_request = self._open_decision_request(
                service, mailbox, prepared_cycle, dispatch=False
            )
            prepared_task = self._write_controller_worker_task(
                cycles_root,
                prepared_cycle,
                prepared_request,
                "decision-v1",
                created_at=clock.current,
            )
            prepared = service.controller_prepare_worker(
                prepared_cycle, "decision-v1", prepared_task
            )
            self.assertEqual(prepared["status"], "PREPARED")
            clock.current = prepared["hard_stop_at"]
            prepared_expired = service.controller_expire_worker(
                prepared_cycle, "decision-v1"
            )
            self.assertTrue(prepared_expired["domain_changed"])
            self.assertEqual(
                repository.load_state(prepared_cycle).stage, "ANALYSIS_FAILED"
            )
            self.assertFalse(
                (
                    cycles_root
                    / prepared_cycle
                    / "transport"
                    / "agent-delivery.json"
                ).exists()
            )

            spawn_requested_cycle = "delivery-after-spawn-request-before-ack"
            clock.current = "2026-08-11T00:01:01+00:00"
            spawn_request = self._open_decision_request(
                service, mailbox, spawn_requested_cycle, dispatch=False
            )
            spawn_task = self._write_controller_worker_task(
                cycles_root,
                spawn_requested_cycle,
                spawn_request,
                "decision-v1",
                created_at=clock.current,
            )
            spawn_prepared = service.controller_prepare_worker(
                spawn_requested_cycle, "decision-v1", spawn_task
            )
            spawn_dispatch_id = spawn_prepared["dispatch_id"]
            assert isinstance(spawn_dispatch_id, str)
            service.controller_mark_worker_spawn_requested(
                spawn_requested_cycle, "decision-v1", spawn_dispatch_id
            )
            clock.current = "2026-08-11T00:05:00+00:00"
            self.assertEqual(
                service.deliver_agent_decision(
                    spawn_requested_cycle, b"WAIT after durable spawn intent\n"
                ),
                "CREATED",
            )
            service.controller_acknowledge_worker_spawn(
                spawn_requested_cycle,
                "decision-v1",
                spawn_dispatch_id,
                f"codex-worker:{spawn_requested_cycle}:decision-v1",
            )
            self.assertEqual(
                self._complete_worker(
                    service,
                    cycles_root,
                    spawn_requested_cycle,
                    "decision-v1",
                )["status"],
                "COMPLETED",
            )

            admitted_cycle = "delivery-before-hard-stop"
            clock.current = "2026-08-11T00:01:01+00:00"
            self._open_decision_request(service, mailbox, admitted_cycle)
            self.assertEqual(
                service.controller_recover_worker(
                    admitted_cycle, "decision-v1"
                )["status"],
                "DISPATCHED",
            )
            clock.current = "2026-08-11T00:11:00+00:00"
            self.assertEqual(
                service.deliver_agent_decision(admitted_cycle, b"WAIT\n"),
                "CREATED",
            )
            admitted_path = (
                cycles_root
                / admitted_cycle
                / "transport"
                / "agent-delivery.json"
            )
            self.assertTrue(admitted_path.is_file())
            self.assertEqual(
                self._complete_worker(
                    service, cycles_root, admitted_cycle, "decision-v1"
                )["status"],
                "COMPLETED",
            )

            exact_cycle = "delivery-at-hard-stop"
            clock.current = "2026-08-11T00:01:01+00:00"
            self._open_decision_request(service, mailbox, exact_cycle)
            exact_path = (
                cycles_root / exact_cycle / "transport" / "agent-delivery.json"
            )
            clock.current = "2026-08-11T00:11:01+00:00"
            self.assertEqual(
                service.deliver_agent_decision(exact_cycle, b"WAIT\n"),
                CONTROLLER_DECISION_DEADLINE_EXPIRED,
            )
            self.assertFalse(exact_path.exists())
            exact_state = repository.load_state(exact_cycle)
            self.assertEqual(exact_state.stage, "ANALYSIS_FAILED")
            self.assertTrue(exact_state.terminal)
            self.assertEqual(
                exact_state.failure_reason, CONTROLLER_DECISION_DEADLINE_EXPIRED
            )
            exact_dispatches = [
                record
                for record in service.controller_status()[
                    "worker_dispatches"
                ].values()
                if record["cycle_id"] == exact_cycle
                and record["worker_id"] == "decision-v1"
            ]
            self.assertEqual(len(exact_dispatches), 1)
            self.assertEqual(exact_dispatches[0]["status"], "EXPIRED")

            missing_dispatch_cycle = "delivery-without-dispatch"
            clock.current = "2026-08-11T00:01:01+00:00"
            self._open_decision_request(
                service, mailbox, missing_dispatch_cycle, dispatch=False
            )
            with self.assertRaisesRegex(
                RuntimeError, "CONTROLLER_WORKER_DISPATCH_MISSING"
            ):
                service.deliver_agent_decision(
                    missing_dispatch_cycle, b"WAIT\n"
                )
            self.assertFalse(
                (
                    cycles_root
                    / missing_dispatch_cycle
                    / "transport"
                    / "agent-delivery.json"
                ).exists()
            )

            cli_runtime = mock.Mock()
            cli_runtime.service.controller_expire_worker.return_value = expired
            with (
                mock.patch.object(
                    market_cycle_cli,
                    "build_market_cycle_runtime",
                    return_value=cli_runtime,
                ),
                mock.patch.object(market_cycle_cli, "_write") as write,
            ):
                self.assertEqual(
                    market_cycle_cli.main(
                        [
                            "--runtime-root",
                            str(runtime_root),
                            "controller-expire-worker",
                            request_only_cycle,
                            "daily-deep-v1",
                        ]
                    ),
                    0,
                )
            cli_runtime.service.controller_expire_worker.assert_called_once_with(
                request_only_cycle, "daily-deep-v1"
            )
            write.assert_called_once_with(expired)
    def test_three_readable_agent_text_formats_round_trip_verbatim(self) -> None:
        v332_cli = _parser().parse_args(
            [
                "--theory-version",
                "3.3.2",
                "--allow-public-collection",
                "create",
                "hype-forward-pilot",
            ]
        )
        create_cli = _parser().parse_args(
            [
                "create",
                "cycle-optional",
                "--data-profile",
                "BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1",
            ]
        )
        decision_cli = _parser().parse_args(
            [
                "deliver",
                "cycle-json",
                "decision.json",
                "--media-type",
                "application/json",
            ]
        )
        review_cli = _parser().parse_args(
            [
                "deliver-review",
                "cycle-json",
                "review.json",
                "--media-type",
                "application/json",
            ]
        )
        evaluation_cli = _parser().parse_args(
            [
                "--theory-version",
                "3.3.2",
                "evaluate-operational",
                "hype-forward-pilot",
            ]
        )
        self.assertEqual(
            create_cli.data_profile,
            "BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1",
        )
        self.assertEqual("3.3.2", v332_cli.theory_version)
        self.assertTrue(v332_cli.allow_public_collection)
        self.assertIsNone(v332_cli.instrument)
        self.assertTrue(
            (market_cycle_cli._DEFAULT_V332_THEORY_PACKAGE / "MANIFEST.json").is_file()
        )
        self.assertEqual(decision_cli.media_type, "application/json")
        self.assertEqual(review_cli.media_type, "application/json")
        self.assertEqual(evaluation_cli.command, "evaluate-operational")
        self.assertFalse(hasattr(evaluation_cli, "evaluated_at"))
        cases = (
            (
                "markdown-long",
                "text/markdown",
                "# 决策\n\n动作：LONG\n入场：118000\n止损：117200\nTargets：119500 / 121000\n仓位：0.25R，分批管理\n",
            ),
            (
                "plain-short",
                "text/plain",
                "ACTION=SHORT\nENTRY=117900; STOP=118650; TARGETS=116800,115900\nPOSITION=最大0.20R，逐步减仓\n",
            ),
            (
                "json-wait",
                "application/json",
                '{"decision":"WAIT","position":"保持空仓，等待下一根收盘确认"}\n',
            ),
            (
                "natural-action",
                "application/x-agent-natural-language",
                "先等待价格站稳区间上沿，再考虑小规模多头参考仓位。\n确认前仓位为零；确认后分两段，点位、止损和 targets 均以本段原文为准。\n",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            clock = MutableClock("2026-08-11T00:01:01+00:00")
            cycles_root = Path(temporary) / "cycles"
            service, repository, mailbox, _, _ = self._service(cycles_root, clock)

            for cycle_id, media_type, decision_text in cases:
                with self.subTest(cycle_id=cycle_id):
                    clock.current = "2026-08-11T00:01:01+00:00"
                    request = self._open_decision_request(
                        service, mailbox, cycle_id
                    )
                    self.assertEqual(
                        request["schema_id"],
                        "agent_trade_emotion_market_cycle_agent_decision_request",
                    )
                    self.assertTrue(
                        any("262144" in line for line in request["instructions"])
                    )
                    self.assertTrue(
                        {
                            "WATCH_REFERENCE",
                            "OPEN_REFERENCE",
                            "ADD_REFERENCE",
                            "HARVEST_REFERENCE",
                            "HEDGE_REFERENCE",
                        }.issubset(LAWFUL_REFERENCE_ACTIONS)
                    )
                    self.assertTrue(
                        any(
                            "reference navigation" in line
                            and "OTHER_INFORMATION_ACTION" in line
                            for line in request["instructions"]
                        )
                    )
                    self.assertTrue(
                        any(
                            "does not choose, normalize, or execute" in line
                            for line in request["instructions"]
                        )
                    )
                    packet = request["packet"]
                    self.assertIsInstance(packet, dict)
                    self.assertNotIn("proposal_schema", packet)
                    self.assertEqual(packet["memory_context"]["status"], "UNKNOWN")
                    self.assertEqual(
                        packet["deterministic_calculations"]["status"], "UNKNOWN"
                    )
                    self.assertEqual(
                        packet["deterministic_calculations"]["typed_unknown"],
                        "INSUFFICIENT_96_CLOSED_15M_BARS",
                    )
                    decision_bytes = decision_text.encode("utf-8")
                    self.assertTrue(decision_bytes.endswith(b"\n"))
                    decision_sha = hashlib.sha256(decision_bytes).hexdigest()

                    clock.current = "2026-08-11T00:01:02+00:00"
                    self.assertEqual(
                        service.deliver_agent_decision(
                            cycle_id,
                            decision_bytes,
                            media_type=media_type,
                        ),
                        "CREATED",
                    )
                    self.assertEqual(
                        service.deliver_agent_decision(
                            cycle_id,
                            decision_bytes,
                            media_type="application/different-non-authoritative-hint",
                        ),
                        "EXISTING_IDENTICAL",
                    )
                    delivery_path = (
                        cycles_root
                        / cycle_id
                        / "transport"
                        / "agent-delivery.json"
                    )
                    delivery_raw = delivery_path.read_bytes()
                    delivery = loads_json_strict(delivery_raw)
                    self.assertEqual(delivery["decision_text"], decision_text)
                    self.assertEqual(delivery["decision_size_bytes"], len(decision_bytes))
                    self.assertEqual(delivery["decision_sha256"], decision_sha)
                    self.assertEqual(delivery["encoding"], "UTF-8")
                    self.assertEqual(delivery["media_type"], media_type)
                    self.assertEqual(
                        self._complete_worker(
                            service, cycles_root, cycle_id, "decision-v1"
                        )["status"],
                        "COMPLETED",
                    )

                    self.assertEqual(service.run_next(cycle_id).state.stage, "ANALYZED")
                    record = repository.load_artifact(cycle_id, "HypothesisRecord")
                    self.assertEqual(record["agent_decision_text"], decision_text)
                    self.assertEqual(record["agent_decision_size_bytes"], len(decision_bytes))
                    self.assertEqual(record["agent_decision_sha256"], decision_sha)
                    self.assertEqual(
                        record["agent_delivery_sha256"],
                        hashlib.sha256(delivery_raw).hexdigest(),
                    )

                    self.assertEqual(service.run_next(cycle_id).state.stage, "PLAN_SEALED")
                    plan = repository.load_artifact(cycle_id, "BehaviorPlan")
                    self.assertEqual(plan["agent_decision_text"], decision_text)
                    self.assertEqual(plan["agent_decision_size_bytes"], len(decision_bytes))
                    self.assertEqual(plan["agent_decision_sha256"], decision_sha)
                    self.assertEqual(plan["agent_delivery_sha256"], record["agent_delivery_sha256"])
                    self.assertEqual(plan["risk_mode"], "REFERENCE")
                    self.assertEqual(plan["execution_mapping"], "NOT_READY")
                    self.assertIsNone(plan["executable_quantity"])

    def test_decision_mailbox_content_binding_late_and_overwrite_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clock = MutableClock("2026-08-11T00:01:01+00:00")
            cycles_root = Path(temporary) / "cycles"
            service, repository, mailbox, _, _ = self._service(cycles_root, clock)

            content_cycle = "decision-content-gates"
            self._open_decision_request(service, mailbox, content_cycle)
            state_before = repository.load_state(content_cycle)
            request_path = (
                cycles_root / content_cycle / "transport" / "agent-request.json"
            )
            request_before = request_path.read_bytes()
            delivery_path = (
                cycles_root / content_cycle / "transport" / "agent-delivery.json"
            )
            invalid_cases = (
                ("nonbytes", "not-bytes", "text/plain", "DECISION_BYTES_INVALID"),
                ("empty", b"", "text/plain", "DECISION_BLANK"),
                ("blank", b" \n\t", "text/plain", "DECISION_BLANK"),
                ("invalid-utf8", b"\xff", "text/plain", "DECISION_UTF8_INVALID"),
                ("nul", b"WAIT\x00now\n", "text/plain", "DECISION_NUL_FORBIDDEN"),
                (
                    "oversize",
                    b"x" * (256 * 1024 + 1),
                    "text/plain",
                    "DECISION_TRANSPORT_CAPACITY_EXCEEDED",
                ),
            )
            for name, raw, media_type, code in invalid_cases:
                with self.subTest(gate=name), self.assertRaises(
                    MarketCycleAgentMailboxError
                ) as rejected:
                    service.deliver_agent_decision(  # type: ignore[arg-type]
                        content_cycle, raw, media_type=media_type
                    )
                self.assertEqual(str(rejected.exception), f"MARKET_CYCLE_AGENT_{code}")
                self.assertFalse(delivery_path.exists())
                self.assertEqual(request_path.read_bytes(), request_before)
                self.assertEqual(repository.load_state(content_cycle), state_before)
            clock.current = "2026-08-11T00:11:01+00:00"
            self.assertTrue(
                service.controller_expire_worker(
                    content_cycle, "decision-v1"
                )["domain_changed"]
            )

            late_cycle = "decision-late"
            clock.current = "2026-08-11T00:01:01+00:00"
            request = self._open_decision_request(service, mailbox, late_cycle)
            clock.current = "2026-08-11T00:11:01+00:00"
            self.assertEqual(
                service.deliver_agent_decision(late_cycle, b"WAIT\n"),
                CONTROLLER_DECISION_DEADLINE_EXPIRED,
            )
            clock.current = "2026-08-11T00:16:00+00:00"
            with self.assertRaises(MarketCycleAgentMailboxError) as expired:
                mailbox.analyze(self._decision_packet(request))
            self.assertEqual(
                str(expired.exception),
                "MARKET_CYCLE_AGENT_DECISION_WINDOW_EXPIRED",
            )
            self.assertEqual(
                repository.load_state(late_cycle).stage, "ANALYSIS_FAILED"
            )
            self.assertFalse(
                (cycles_root / late_cycle / "transport" / "agent-delivery.json").exists()
            )

            overwrite_cycle = "decision-overwrite"
            clock.current = "2026-08-11T00:01:01+00:00"
            self._open_decision_request(service, mailbox, overwrite_cycle)
            overwrite_state = repository.load_state(overwrite_cycle)
            clock.current = "2026-08-11T00:01:02+00:00"
            original = "原始 WAIT 决策；仓位保持零。\n".encode("utf-8")
            self.assertEqual(
                service.deliver_agent_decision(overwrite_cycle, original), "CREATED"
            )
            overwrite_path = (
                cycles_root / overwrite_cycle / "transport" / "agent-delivery.json"
            )
            original_envelope = overwrite_path.read_bytes()
            self.assertEqual(
                service.deliver_agent_decision(overwrite_cycle, original),
                "EXISTING_IDENTICAL",
            )
            with self.assertRaises(MarketCycleAgentMailboxError) as conflict:
                service.deliver_agent_decision(overwrite_cycle, b"replacement\n")
            self.assertEqual(
                str(conflict.exception), "MARKET_CYCLE_AGENT_DELIVERY_CONFLICT"
            )
            self.assertEqual(overwrite_path.read_bytes(), original_envelope)
            self.assertEqual(repository.load_state(overwrite_cycle), overwrite_state)
            self.assertEqual(
                self._complete_worker(
                    service, cycles_root, overwrite_cycle, "decision-v1"
                )["status"],
                "COMPLETED",
            )

            for index, field in enumerate(
                ("cycle_id", "request_sha256", "theory_identity")
            ):
                with self.subTest(binding=field):
                    cycle_id = f"decision-binding-{index}"
                    clock.current = "2026-08-11T00:01:01+00:00"
                    bound_request = self._open_decision_request(
                        service, mailbox, cycle_id
                    )
                    packet = self._decision_packet(bound_request)
                    clock.current = "2026-08-11T00:01:02+00:00"
                    service.deliver_agent_decision(cycle_id, b"bound WAIT\n")
                    path = cycles_root / cycle_id / "transport" / "agent-delivery.json"
                    original_delivery = path.read_bytes()
                    document = loads_json_strict(original_delivery)
                    if field == "theory_identity":
                        identity = dict(document[field])
                        identity["manifest_digest"] = "0" * 64
                        document[field] = identity
                    else:
                        document[field] = (
                            "wrong-cycle" if field == "cycle_id" else "0" * 64
                        )
                    tampered = self._write_canonical_sidecar(path, document)
                    with self.assertRaises(MarketCycleAgentMailboxError) as binding:
                        mailbox.analyze(packet)
                    self.assertEqual(
                        str(binding.exception),
                        "MARKET_CYCLE_AGENT_DELIVERY_BINDING_INVALID",
                    )
                    self.assertEqual(path.read_bytes(), tampered)
                    path.write_bytes(original_delivery)
                    self.assertEqual(
                        self._complete_worker(
                            service, cycles_root, cycle_id, "decision-v1"
                        )["status"],
                        "COMPLETED",
                    )

    def test_agent_review_pending_context_binding_late_and_overwrite_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clock = MutableClock("2026-08-11T00:01:01+00:00")
            cycles_root = Path(temporary) / "cycles"
            service, repository, mailbox, _, _ = self._service(cycles_root, clock)

            content_cycle = "review-content-gates"
            maximum_decision = b"x" * (256 * 1024 - 1) + b"\n"
            self._to_outcome_sealed(
                service,
                mailbox,
                clock,
                content_cycle,
                decision_bytes=maximum_decision,
            )
            outcome_state = repository.load_state(content_cycle)
            pending = service.run_next(content_cycle)
            self.assertFalse(pending.changed)
            self.assertEqual(pending.state.stage, "OUTCOME_SEALED")
            self.assertEqual(
                pending.pending_reason, "AGENT_REVIEW_DELIVERY_PENDING"
            )
            review_request = mailbox.review_request(content_cycle)
            self.assertIsNotNone(review_request)
            review_request = dict(review_request or {})
            self._dispatch_worker(
                service,
                cycles_root,
                clock,
                content_cycle,
                "review-v1",
                review_request,
            )
            self.assertTrue(
                any("262144" in line for line in review_request["instructions"])
            )
            review_packet = review_request["packet"]
            self.assertIsInstance(review_packet, dict)
            state_refs = {
                reference.artifact_type: reference.to_dict()
                for reference in repository.load_state(content_cycle).artifact_refs
            }
            snapshot = repository.load_artifact(content_cycle, "InputSnapshot")
            record = repository.load_artifact(content_cycle, "HypothesisRecord")
            plan = repository.load_artifact(content_cycle, "BehaviorPlan")
            outcome = repository.load_artifact(content_cycle, "Outcome")
            self.assertEqual(review_packet["input_snapshot"], snapshot)
            self.assertEqual(
                review_packet["input_snapshot_ref"], state_refs["InputSnapshot"]
            )
            self.assertEqual(review_packet["hypothesis_record"], record)
            self.assertEqual(
                review_packet["hypothesis_record_ref"],
                state_refs["HypothesisRecord"],
            )
            self.assertEqual(review_packet["behavior_plan"], plan)
            self.assertEqual(
                review_packet["behavior_plan_ref"], state_refs["BehaviorPlan"]
            )
            self.assertEqual(review_packet["outcome"], outcome)
            self.assertEqual(review_packet["outcome_ref"], state_refs["Outcome"])
            self.assertEqual(
                review_packet["agent_decision"],
                {
                    "cycle_id": content_cycle,
                    "request_sha256": record["agent_request_sha256"],
                    "theory_identity": record["theory_identity"],
                    "delivered_at": record["agent_delivered_at"],
                    "decision_text": record["agent_decision_text"],
                    "decision_size_bytes": record["agent_decision_size_bytes"],
                    "decision_sha256": record["agent_decision_sha256"],
                    "delivery_path": record["agent_delivery_path"],
                    "delivery_sha256": record["agent_delivery_sha256"],
                },
            )
            self.assertEqual(
                review_packet["agent_decision_ref"],
                {
                    "transport_path": record["agent_delivery_path"],
                    "transport_sha256": record["agent_delivery_sha256"],
                    "decision_sha256": record["agent_decision_sha256"],
                },
            )
            decision_packet = dict((mailbox.request(content_cycle) or {})["packet"])
            self.assertEqual(
                review_packet["memory_context"], decision_packet["memory_context"]
            )
            self.assertEqual(
                review_packet["deterministic_calculations"],
                decision_packet["deterministic_calculations"],
            )
            mailbox._review_context(review_request, cycle_id=content_cycle)
            review_request_path = (
                cycles_root
                / content_cycle
                / "transport"
                / "agent-review-request.json"
            )
            request_before = review_request_path.read_bytes()
            review_delivery_path = (
                cycles_root
                / content_cycle
                / "transport"
                / "agent-review-delivery.json"
            )
            invalid_cases = (
                ("nonbytes", object(), "text/plain", "REVIEW_BYTES_INVALID"),
                ("empty", b"", "text/plain", "REVIEW_BLANK"),
                ("blank", b" \n\t", "text/plain", "REVIEW_BLANK"),
                ("invalid-utf8", b"\xff", "text/plain", "REVIEW_UTF8_INVALID"),
                ("nul", b"review\x00bad\n", "text/plain", "REVIEW_NUL_FORBIDDEN"),
                (
                    "oversize",
                    b"x" * (256 * 1024 + 1),
                    "text/plain",
                    "REVIEW_TRANSPORT_CAPACITY_EXCEEDED",
                ),
            )
            for name, raw, media_type, code in invalid_cases:
                with self.subTest(gate=name), self.assertRaises(
                    MarketCycleAgentMailboxError
                ) as rejected:
                    service.deliver_agent_review(  # type: ignore[arg-type]
                        content_cycle, raw, media_type=media_type
                    )
                self.assertEqual(str(rejected.exception), f"MARKET_CYCLE_AGENT_{code}")
                self.assertFalse(review_delivery_path.exists())
                self.assertEqual(review_request_path.read_bytes(), request_before)
                self.assertEqual(repository.load_state(content_cycle), outcome_state)

            context_cases = []
            invalid_time = copy.deepcopy(review_request)
            invalid_time["packet"]["review_due_at"] = "not-a-timestamp"
            self._resign_packet_document(invalid_time)
            context_cases.append(("timestamp", invalid_time))
            wrong_due = copy.deepcopy(review_request)
            wrong_due["packet"]["review_due_at"] = "2026-08-11T00:26:01+00:00"
            self._resign_packet_document(wrong_due)
            context_cases.append(("due", wrong_due))
            wrong_plan = copy.deepcopy(review_request)
            wrong_plan["packet"]["behavior_plan_ref"]["sha256"] = "0" * 64
            self._resign_packet_document(wrong_plan)
            context_cases.append(("plan-binding", wrong_plan))
            tamper_specs = (
                ("snapshot-content", "input_snapshot", "snapshot_id"),
                ("snapshot-ref", "input_snapshot_ref", "sha256"),
                ("decision-content", "agent_decision", "decision_text"),
                ("decision-ref", "agent_decision_ref", "decision_sha256"),
                ("record-content", "hypothesis_record", "record_id"),
                ("record-ref", "hypothesis_record_ref", "sha256"),
                ("plan-content", "behavior_plan", "plan_id"),
                ("outcome-content", "outcome", "outcome_id"),
                ("outcome-ref", "outcome_ref", "sha256"),
            )
            for name, section, field in tamper_specs:
                tampered = copy.deepcopy(review_request)
                tampered["packet"][section][field] = (
                    "tampered" if field.endswith("_id") or field == "decision_text" else "0" * 64
                )
                self._resign_packet_document(tampered)
                context_cases.append((name, tampered))
            wrong_memory = copy.deepcopy(review_request)
            wrong_memory["packet"]["memory_context"]["status"] = "AVAILABLE"
            self._resign_packet_document(wrong_memory)
            context_cases.append(("memory-context", wrong_memory))
            wrong_calculation = copy.deepcopy(review_request)
            wrong_calculation["packet"]["deterministic_calculations"][
                "source_bar_count"
            ] = 2
            self._resign_packet_document(wrong_calculation)
            context_cases.append(("calculation-context", wrong_calculation))
            for name, document in context_cases:
                with self.subTest(context=name), self.assertRaises(
                    MarketCycleAgentMailboxError
                ) as invalid_context:
                    mailbox._review_context(document, cycle_id=content_cycle)
                self.assertEqual(
                    str(invalid_context.exception),
                    "MARKET_CYCLE_AGENT_REVIEW_REQUEST_INVALID",
                )
                self.assertEqual(review_request_path.read_bytes(), request_before)

            clock.current = "2026-08-11T00:26:00+00:00"
            self.assertTrue(
                service.controller_expire_worker(
                    content_cycle, "review-v1"
                )["domain_changed"]
            )

            delayed_request_cycle = "review-request-after-recovery-gap"
            clock.current = "2026-08-11T00:01:01+00:00"
            self._to_outcome_sealed(
                service, mailbox, clock, delayed_request_cycle
            )
            clock.current = "2026-08-11T01:00:00+00:00"
            delayed_pending = service.run_next(delayed_request_cycle)
            self.assertEqual(
                delayed_pending.pending_reason,
                "AGENT_REVIEW_DELIVERY_PENDING",
            )
            delayed_request = dict(
                mailbox.review_request(delayed_request_cycle) or {}
            )
            self.assertEqual(
                delayed_request["packet"]["review_requested_at"],
                "2026-08-11T01:00:00+00:00",
            )
            self.assertEqual(
                delayed_request["packet"]["review_due_at"],
                "2026-08-11T01:10:00+00:00",
            )
            self._dispatch_worker(
                service,
                cycles_root,
                clock,
                delayed_request_cycle,
                "review-v1",
                delayed_request,
            )
            clock.current = "2026-08-11T01:00:01+00:00"
            self.assertEqual(
                service.deliver_agent_review(
                    delayed_request_cycle, b"recovered review request\n"
                ),
                "CREATED",
            )
            self.assertEqual(
                self._complete_worker(
                    service,
                    cycles_root,
                    delayed_request_cycle,
                    "review-v1",
                )["status"],
                "COMPLETED",
            )
            self.assertEqual(
                service.run_next(delayed_request_cycle).state.stage,
                "REVIEWED",
            )

            late_cycle = "review-late"
            clock.current = "2026-08-11T00:01:01+00:00"
            self._to_outcome_sealed(service, mailbox, clock, late_cycle)
            late_pending = service.run_next(late_cycle)
            self.assertEqual(
                late_pending.pending_reason, "AGENT_REVIEW_DELIVERY_PENDING"
            )
            late_request = dict(mailbox.review_request(late_cycle) or {})
            self._dispatch_worker(
                service,
                cycles_root,
                clock,
                late_cycle,
                "review-v1",
                late_request,
            )
            clock.current = "2026-08-11T00:26:00+00:00"
            self.assertEqual(
                service.deliver_agent_review(late_cycle, b"late review\n"),
                CONTROLLER_REVIEW_DEADLINE_EXPIRED,
            )
            with self.assertRaises(MarketCycleAgentMailboxError) as expired:
                mailbox.review(self._review_packet(late_request))
            self.assertEqual(
                str(expired.exception),
                "MARKET_CYCLE_AGENT_REVIEW_WINDOW_EXPIRED",
            )
            self.assertEqual(repository.load_state(late_cycle).stage, "REVIEW_FAILED")
            self.assertFalse(
                (
                    cycles_root
                    / late_cycle
                    / "transport"
                    / "agent-review-delivery.json"
                ).exists()
            )

            overwrite_cycle = "review-overwrite"
            clock.current = "2026-08-11T00:01:01+00:00"
            self._to_outcome_sealed(service, mailbox, clock, overwrite_cycle)
            self.assertEqual(
                service.run_next(overwrite_cycle).pending_reason,
                "AGENT_REVIEW_DELIVERY_PENDING",
            )
            overwrite_request = dict(
                mailbox.review_request(overwrite_cycle) or {}
            )
            self._dispatch_worker(
                service,
                cycles_root,
                clock,
                overwrite_cycle,
                "review-v1",
                overwrite_request,
            )
            overwrite_state = repository.load_state(overwrite_cycle)
            clock.current = "2026-08-11T00:16:01+00:00"
            original = "# Agent Review\n保持 UNKNOWN；不补造市场结论。\n".encode()
            self.assertEqual(
                service.deliver_agent_review(
                    overwrite_cycle, original, media_type="application/json"
                ),
                "CREATED",
            )
            overwrite_path = (
                cycles_root
                / overwrite_cycle
                / "transport"
                / "agent-review-delivery.json"
            )
            original_envelope = overwrite_path.read_bytes()
            self.assertEqual(
                loads_json_strict(original_envelope)["media_type"],
                "application/json",
            )
            self.assertEqual(
                service.deliver_agent_review(
                    overwrite_cycle,
                    original,
                    media_type="text/x-different-non-authoritative-hint",
                ),
                "EXISTING_IDENTICAL",
            )
            with self.assertRaises(MarketCycleAgentMailboxError) as conflict:
                service.deliver_agent_review(overwrite_cycle, b"replacement review\n")
            self.assertEqual(
                str(conflict.exception),
                "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_CONFLICT",
            )
            self.assertEqual(overwrite_path.read_bytes(), original_envelope)
            self.assertEqual(repository.load_state(overwrite_cycle), overwrite_state)
            self.assertEqual(
                self._complete_worker(
                    service, cycles_root, overwrite_cycle, "review-v1"
                )["status"],
                "COMPLETED",
            )

            for index, field in enumerate(
                (
                    "cycle_id",
                    "request_sha256",
                    "theory_identity",
                    "behavior_plan_sha256",
                    "outcome_sha256",
                )
            ):
                with self.subTest(binding=field):
                    cycle_id = f"review-binding-{index}"
                    clock.current = "2026-08-11T00:01:01+00:00"
                    self._to_outcome_sealed(service, mailbox, clock, cycle_id)
                    self.assertEqual(
                        service.run_next(cycle_id).pending_reason,
                        "AGENT_REVIEW_DELIVERY_PENDING",
                    )
                    bound_request = dict(mailbox.review_request(cycle_id) or {})
                    packet = self._review_packet(bound_request)
                    self._dispatch_worker(
                        service,
                        cycles_root,
                        clock,
                        cycle_id,
                        "review-v1",
                        bound_request,
                    )
                    clock.current = "2026-08-11T00:16:01+00:00"
                    service.deliver_agent_review(cycle_id, b"bound review\n")
                    path = (
                        cycles_root
                        / cycle_id
                        / "transport"
                        / "agent-review-delivery.json"
                    )
                    original_delivery = path.read_bytes()
                    document = loads_json_strict(original_delivery)
                    if field == "theory_identity":
                        identity = dict(document[field])
                        identity["manifest_digest"] = "0" * 64
                        document[field] = identity
                    else:
                        document[field] = (
                            "wrong-cycle" if field == "cycle_id" else "0" * 64
                        )
                    tampered = self._write_canonical_sidecar(path, document)
                    with self.assertRaises(MarketCycleAgentMailboxError) as binding:
                        mailbox.review(packet)
                    self.assertEqual(
                        str(binding.exception),
                        "MARKET_CYCLE_AGENT_REVIEW_DELIVERY_BINDING_INVALID",
                    )
                    self.assertEqual(path.read_bytes(), tampered)
                    path.write_bytes(original_delivery)
                    self.assertEqual(
                        self._complete_worker(
                            service, cycles_root, cycle_id, "review-v1"
                        )["status"],
                        "COMPLETED",
                    )

    def test_one_agent_first_offline_observed_cycle_with_unknown_projection_reaches_complete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clock = MutableClock("2026-08-11T00:01:01+00:00")
            cycles_root = Path(temporary) / "cycles"
            memory_text = "# Prior review\nKeep earlier evidence UNKNOWN.\n"
            memory = VerifiedMemoryItem(
                kind="RELATED_DECISION_REVIEW",
                status="AVAILABLE",
                source_path="prior-run/cycles/previous/Review.md",
                source_sha256=hashlib.sha256(memory_text.encode()).hexdigest(),
                source_cycle_id="previous-cycle",
                venue_id="OKX",
                instrument_id="BTC-USDT-SWAP",
                contract_identity="OKX:BTC-USDT-SWAP:linear",
                availability_basis="REVIEWED_AT",
                source_available_at="2026-08-10T23:59:59+00:00",
                verbatim_text=memory_text,
            )
            service, repository, mailbox, market, outcome_port = self._service(
                cycles_root,
                clock,
                observed_outcome=True,
                verified_memory=(memory,),
            )
            cycle_id = "agent-first-e2e"
            decision_text = (
                "# 市场观察\n"
                "价格证据仍冲突。\n"
                "## 额外章节\n"
                "未校准概率 70%，不作为统计校准。\n"
                "本轮没有 lead/runner/OTHER，也不提供动作或仓位字段。\n"
            )
            decision_bytes = decision_text.encode("utf-8")

            request = self._open_decision_request(
                service,
                mailbox,
                cycle_id,
                data_profile="BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1",
                dispatch=False,
            )
            self.assertEqual(
                set(request),
                {
                    "schema_id",
                    "schema_version",
                    "cycle_id",
                    "request_id",
                    "packet_sha256",
                    "packet_size_bytes",
                    "packet",
                    "instructions",
                },
            )
            self.assertEqual(request["packet"]["memory_context"]["status"], "AVAILABLE")
            self.assertEqual(
                request["packet"]["input_snapshot"]["data_profile"],
                "BASELINE_PRICE_PLUS_OKX_PUBLIC_OPTIONAL_V1",
            )
            self.assertEqual(
                request["packet"]["memory_context"]["items"], [memory.to_dict()]
            )
            self.assertEqual(
                request["packet"]["deterministic_calculations"]["status"],
                "UNKNOWN",
            )
            task_path = self._write_controller_worker_task(
                cycles_root,
                cycle_id,
                request,
                "decision-v1",
                created_at=clock.current,
            )
            prepared = service.controller_prepare_worker(
                cycle_id,
                "decision-v1",
                task_path,
            )
            self.assertEqual(prepared["status"], "PREPARED")
            self.assertEqual(
                service.controller_recover_worker(cycle_id, "decision-v1")[
                    "recovery_action"
                ],
                "RECOVER_PREPARED",
            )
            dispatch_id = prepared["dispatch_id"]
            spawn_requested = service.controller_mark_worker_spawn_requested(
                cycle_id, "decision-v1", dispatch_id
            )
            self.assertEqual(spawn_requested["status"], "SPAWN_REQUESTED")
            self.assertEqual(
                service.controller_recover_worker(cycle_id, "decision-v1")[
                    "recovery_action"
                ],
                "RECONCILE_SPAWN",
            )
            dispatched = service.controller_acknowledge_worker_spawn(
                cycle_id,
                "decision-v1",
                dispatch_id,
                "codex-worker:agent-first-e2e",
            )
            self.assertEqual(dispatched["status"], "DISPATCHED")
            self.assertEqual(
                service.controller_recover_worker(cycle_id, "decision-v1")[
                    "recovery_action"
                ],
                "WAIT_FOR_OUTPUT",
            )
            clock.current = "2026-08-11T00:01:02+00:00"
            service.deliver_agent_decision(cycle_id, decision_bytes)
            completed_dispatch = self._complete_worker(
                service,
                cycles_root,
                cycle_id,
                "decision-v1",
            )
            self.assertEqual(completed_dispatch["status"], "COMPLETED")
            self.assertEqual(
                service.controller_recover_worker(cycle_id, "decision-v1")[
                    "status"
                ],
                "COMPLETED",
            )
            analyzed = service.run_next(cycle_id).state
            self.assertEqual(analyzed.stage, "ANALYZED")
            record = repository.load_artifact(cycle_id, "HypothesisRecord")
            self.assertEqual(record["agent_decision_text"], decision_text)
            self.assertEqual(record["projection_status"], "UNKNOWN")
            self.assertEqual(record["projection_reason"], AGENT_OUTPUT_INCOMPLETE)
            self.assertIn(AGENT_OUTPUT_INCOMPLETE, record["unresolved_unknowns"])
            self.assertIsNone(record["agent_action_text"])
            self.assertIsNone(record["agent_position_text"])

            self.assertEqual(service.run_next(cycle_id).state.stage, "PLAN_SEALED")
            plan = repository.load_artifact(cycle_id, "BehaviorPlan")
            self.assertEqual(plan["agent_decision_text"], decision_text)
            self.assertEqual(plan["agent_decision_sha256"], record["agent_decision_sha256"])
            self.assertEqual(plan["projection_status"], "UNKNOWN")
            self.assertIsNone(plan["agent_action_text"])
            self.assertIsNone(plan["agent_position_text"])

            clock.current = "2026-08-11T00:16:00+00:00"
            self.assertEqual(service.run_next(cycle_id).state.stage, "OUTCOME_DUE")
            self.assertEqual(service.run_next(cycle_id).state.stage, "OUTCOME_SEALED")
            outcome = repository.load_artifact(cycle_id, "Outcome")
            self.assertEqual(outcome["terminal_status"], "OBSERVED")
            self.assertIsNone(outcome["typed_missing"])
            self.assertEqual(outcome["endpoint_observation"]["value"], "118250.5")
            self.assertEqual(outcome["endpoint_observation"]["unit"], "USDT")
            self.assertEqual(len(outcome["raw_refs"]), 1)

            pending_review = service.run_next(cycle_id)
            self.assertFalse(pending_review.changed)
            self.assertEqual(pending_review.state.stage, "OUTCOME_SEALED")
            self.assertEqual(
                pending_review.pending_reason, "AGENT_REVIEW_DELIVERY_PENDING"
            )
            review_request = mailbox.review_request(cycle_id)
            self.assertIsNotNone(review_request)
            review_request = dict(review_request or {})
            self.assertEqual(
                review_request["schema_id"],
                "agent_trade_emotion_market_cycle_agent_review_request",
            )
            self.assertEqual(
                review_request["packet"]["review_requested_at"], outcome["sealed_at"]
            )
            self.assertEqual(review_request["packet"]["time_budget_seconds"], 600)
            self.assertEqual(
                review_request["packet"]["memory_context"],
                request["packet"]["memory_context"],
            )
            self.assertEqual(
                review_request["packet"]["deterministic_calculations"],
                request["packet"]["deterministic_calculations"],
            )
            self.assertEqual(
                review_request["packet"]["input_snapshot"],
                repository.load_artifact(cycle_id, "InputSnapshot"),
            )
            self.assertEqual(review_request["packet"]["behavior_plan"], plan)
            self.assertEqual(review_request["packet"]["outcome"], outcome)

            review_text = (
                "# Agent 复盘\n"
                "Outcome 已观测，但由我而不是系统判断原始 WAIT 是否合理。\n"
                "下一独立周期继续保留竞争路径，不补造账户、仓位或市场事实。\n"
            )
            review_bytes = review_text.encode("utf-8")
            self._dispatch_worker(
                service,
                cycles_root,
                clock,
                cycle_id,
                "review-v1",
                review_request,
            )
            clock.current = "2026-08-11T00:16:01+00:00"
            service.deliver_agent_review(cycle_id, review_bytes)
            self.assertEqual(
                self._complete_worker(
                    service, cycles_root, cycle_id, "review-v1"
                )["status"],
                "COMPLETED",
            )
            self.assertEqual(service.run_next(cycle_id).state.stage, "REVIEWED")
            complete = service.run_next(cycle_id).state
            self.assertEqual(complete.stage, "COMPLETE")
            self.assertTrue(complete.terminal)
            self.assertEqual(
                tuple(reference.artifact_type for reference in complete.artifact_refs),
                (
                    "InputSnapshot",
                    "HypothesisRecord",
                    "BehaviorPlan",
                    "Outcome",
                    "Review",
                ),
            )

            review = repository.load_artifact(cycle_id, "Review")
            self.assertEqual(review["agent_review_text"], review_text)
            self.assertEqual(review["agent_review_size_bytes"], len(review_bytes))
            self.assertEqual(
                review["agent_review_sha256"],
                hashlib.sha256(review_bytes).hexdigest(),
            )
            self.assertEqual(
                review["agent_review_request_sha256"],
                review_request["packet_sha256"],
            )
            self.assertEqual(review["projection_status"], "UNKNOWN")
            self.assertEqual(review["projection_reason"], AGENT_OUTPUT_INCOMPLETE)
            self.assertEqual(
                review["system_facts"],
                {
                    "outcome_status": "OBSERVED",
                    "typed_missing": None,
                    "endpoint_observation": outcome["endpoint_observation"],
                    "path_observations": {"source_health": []},
                    "outcome_raw_refs": outcome["raw_refs"],
                },
            )
            self.assertFalse(review["theory_writeback"])
            for forbidden in (
                "selected_action",
                "decision_assessment",
                "action_counterfactuals",
                "opportunity_cost",
                "recommendations",
            ):
                self.assertNotIn(forbidden, review)
            self.assertEqual((market.calls, outcome_port.calls), (1, 1))

    def test_agent_first_active_call_chain_has_no_deterministic_decision_or_review(self) -> None:
        paths: list[Path] = []
        for root in _ACTIVE_ROOTS:
            if root.is_file():
                paths.append(root)
            else:
                paths.extend(sorted(root.rglob("*.py")))
        trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in paths}
        names = {
            value
            for tree in trees.values()
            for node in ast.walk(tree)
            for value in (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else None,
            )
            if value is not None
        }
        strings = {
            node.value
            for tree in trees.values()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        forbidden_names = {
            "AgentProposalContractV1",
            "ActionComparison",
            "CONTROLLER_AGENT_REJECTION_CODES",
            "controller_reject_agent_proposal",
            "normalize_agent_proposal",
            "plan_behavior",
            "select_action",
            "selected_action",
            "action_comparisons",
            "decision_assessment",
            "action_counterfactuals",
            "opportunity_cost",
            "recommendations",
        }
        self.assertFalse(forbidden_names & names)
        forbidden_fragments = (
            "agent_trade_emotion_market_cycle_agent_proposal",
            "HYPOTHESES_ONLY",
            "ACTION_COMPARISON_AND_SELECTION",
            "REVIEW_FORWARD_EVIDENCE_ONLY",
            "RETAIN_UNKNOWN",
            "RISK_INCREASING",
        )
        self.assertFalse(
            {
                fragment
                for fragment in forbidden_fragments
                if any(fragment in value for value in strings)
            }
        )

        service_path = (
            _ROOT
            / "trade_system"
            / "theory_paper_v2"
            / "application"
            / "market_cycle"
            / "service.py"
        )
        service_tree = trees[service_path]
        service_calls = {
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
            for node in ast.walk(service_tree)
            if isinstance(node, ast.Call)
        }
        self.assertIn("copy_agent_decision_to_behavior_plan", service_calls)
        self.assertNotIn("plan_behavior", service_calls)
        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.endswith("position")
                for node in ast.walk(service_tree)
            )
        )

        position_path = service_path.with_name("position.py")
        position_tree = trees[position_path]
        position_constructors = {
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
            for node in ast.walk(position_tree)
            if isinstance(node, ast.Call)
        }
        position_imports = {
            alias.name
            for node in ast.walk(position_tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("BehaviorPlan", position_constructors | position_imports)
        self.assertNotIn(
            "copy_agent_decision_to_behavior_plan",
            position_constructors | position_imports,
        )

        cli_path = _ROOT / "trade_system" / "theory_paper_v2" / "presentation" / "market_cycle.py"
        cli_tree = trees[cli_path]
        cli_attributes = {
            node.attr for node in ast.walk(cli_tree) if isinstance(node, ast.Attribute)
        }
        self.assertIn("read_bytes", cli_attributes)
        self.assertIn("deliver_agent_decision", cli_attributes)
        self.assertIn("deliver_agent_review", cli_attributes)
        for controller_method in (
            "controller_prepare_worker",
            "controller_mark_worker_spawn_requested",
            "controller_acknowledge_worker_spawn",
            "controller_complete_worker",
            "controller_recover_worker",
            "controller_expire_worker",
        ):
            self.assertIn(controller_method, cli_attributes)


if __name__ == "__main__":
    unittest.main()
