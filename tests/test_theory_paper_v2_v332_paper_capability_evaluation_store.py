from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_theory_paper_v2_v332_paper_capability_evaluation as capability_fixture
from tests import test_theory_paper_v2_v332_execution_intent as intent_fixture
from tests import test_theory_paper_v2_v332_paper_runtime as paper_fixture
from tests.test_theory_paper_v2_v332_experiment_runtime import _policy as base_policy
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import AttentionRequest
from trade_system.theory_paper_v2.application.market_cycle.paper_capability_evaluation import (
    build_paper_position_and_open_order_ref,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper_capability_evaluation import (
    PAPER_CAPABILITY_CRITERIA,
    PaperCapabilityFindingV1,
    PaperEvidenceSpanV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    PaperBracketV1,
    PaperExecutionIntentV1,
    PaperLedgerRecordV1,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_capability_evaluation_store import (
    FilePaperCapabilityEvaluationStore,
    PaperCapabilityEvaluationStoreError,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.capability_assessor_mailbox import (
    LocalCapabilityAssessorMailbox,
    OUTPUT_CONTRACT_SCHEMA_ID,
)
from trade_system.theory_paper_v2.presentation import market_cycle as market_cycle_cli
from trade_system.theory_paper_v2.v32_durable_json import write_once_json


_ASSESSOR_TASK = "codex-thread:22222222-2222-2222-2222-222222222222"


def _singleton_policy(run_id: str, **kwargs: object):  # noqa: ANN201
    policy = base_policy(run_id, **kwargs)
    return replace(
        policy,
        capability_ids=("TRADING_DECISION",),
        decision_horizon_seconds=900,
        outcome_tolerance_seconds=30,
    )


def _attention_policy(run_id: str, **kwargs: object):  # noqa: ANN201
    return replace(
        _singleton_policy(run_id, **kwargs),
        capability_ids=("ATTENTION_SCHEDULING",),
    )


def _position_evidence_points():  # noqa: ANN201
    policy, facts = capability_fixture._protected_position_evidence_points()
    return policy, facts, facts[0].execution_intent


def _write_and_complete_assessor(
    fixture: paper_fixture.V332HypePaperRuntimeTests,
    *,
    cycle_id: str,
    dispatch_id: str,
    task: object,
    findings: tuple[PaperCapabilityFindingV1, ...],
    completed_at: str = "2026-08-13T12:00:30+00:00",
) -> None:
    controller = fixture.runtime.controller_state
    task_document = task.to_dict()
    controller_task_path = (
        fixture.runtime_root
        / "agents"
        / f"{cycle_id}--capability-assessor-v1"
        / "task.json"
    )
    controller_task = loads_json_strict(controller_task_path.read_bytes())
    structured = {
        "schema_id": "agent-trade-emotion.v332-capability-assessor-findings",
        "schema_version": "1.0.0",
        "cycle_id": cycle_id,
        "worker_id": "capability-assessor-v1",
        "capability_id": task_document["capability_id"],
        "task_id": task_document["task_id"],
        "task_sha256": task.task_sha256,
        "assessor_execution_ref": _ASSESSOR_TASK,
        "completed_at": completed_at,
        "findings": [item.to_dict() for item in findings],
    }
    structured_path = (
        fixture.runtime_root
        / "cycles"
        / cycle_id
        / "transport"
        / "capability-assessor-findings.json"
    )
    write_once_json(structured_path, structured)
    result = {
        "schema_id": "agent_trade_emotion_v331_worker_result",
        "schema_version": "1.0.0",
        "run_id": fixture.runtime.run_manifest.run_id,
        "cycle_id": cycle_id,
        "worker_id": "capability-assessor-v1",
        "status": "COMPLETED",
        "started_at": controller_task["timing"]["created_at"],
        "completed_at": completed_at,
        "elapsed_seconds": 2,
        "input_refs": [
            {field: item[field] for field in ("role", "path", "sha256")}
            for item in controller_task["input_refs"]
        ],
        "body_markdown": "Independent pre-outcome capability findings sealed.",
    }
    write_once_json(controller_task_path.parent / "result.json", result)
    fixture.clock.current = completed_at
    controller.complete_worker(
        cycle_id,
        "capability-assessor-v1",
        dispatch_id,
        hashlib.sha256(structured_path.read_bytes()).hexdigest(),
    )


class V332PaperCapabilityStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        policy_patch = patch.object(paper_fixture, "_policy", _singleton_policy)
        policy_patch.start()
        self.addCleanup(policy_patch.stop)
        self.fixture = paper_fixture.V332HypePaperRuntimeTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture._setup_account()
        self.cycle_id = self.fixture._seal_decision(seal_plan=False)
        self.assertEqual(
            "PLAN_SEALED",
            self.fixture.runtime.service.run_next(self.cycle_id).state.stage,
        )
        prepared = paper_fixture.V332AgentPaperActionPort(
            self.fixture.paper
        ).prepare_paper_action(decision_cycle_id=self.cycle_id)
        mailbox = self.fixture._mailbox()
        self.intent = self.fixture._short_bracket_intent(
            self.cycle_id,
            intent_request_sha256=str(prepared["intent_request_sha256"]),
        )
        self.fixture._write_intent(mailbox, self.intent)
        self.fixture.clock.current = "2026-08-13T12:00:28.500000+00:00"
        committed = paper_fixture.V332AgentPaperActionPort(
            self.fixture.paper
        ).commit_paper_action(
            decision_cycle_id=self.cycle_id
        )
        self.assertEqual("COMMITTED", committed["status"])
        submitted = self.fixture.paper._require_account()
        self.assertEqual("OPEN", submitted.orders[0].state)

    def _findings(self) -> tuple[PaperCapabilityFindingV1, ...]:
        raw = canonical_bytes(self.intent.to_dict())
        selected = raw[:32]
        selected.decode("utf-8")
        span = PaperEvidenceSpanV1(
            cycle_id=self.cycle_id,
            source_kind="EXECUTION_INTENT",
            source_sha256=hashlib.sha256(raw).hexdigest(),
            start_byte=0,
            end_byte=len(selected),
            selected_utf8_sha256=hashlib.sha256(selected).hexdigest(),
        )
        return tuple(
            PaperCapabilityFindingV1(
                criterion_id=criterion,
                status="DEMONSTRATED",
                rationale="Typed assessor finding over exact Agent intent bytes.",
                evidence_spans=(span,),
            )
            for criterion in PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"]
        )

    def test_store_rebuilds_facts_and_write_once_round_trips_same_digests(self) -> None:
        times = iter(
            (
                "2026-08-13T12:00:29+00:00",
                "2026-08-13T12:00:29.500000+00:00",
                "2026-08-13T12:00:31+00:00",
            )
        )
        self.fixture.clock.current = "2026-08-13T12:00:29+00:00"
        store = FilePaperCapabilityEvaluationStore(
            self.fixture.runtime, clock=lambda: next(times)
        )
        ledger_intent = store._ledger.load_records(  # noqa: SLF001
            self.fixture.paper.account_id
        )[self.intent.expected_account_version].payload["execution_intent"]
        self.assertNotEqual(ledger_intent, self.intent.to_dict())
        self.assertEqual(
            canonical_bytes(ledger_intent), canonical_bytes(self.intent.to_dict())
        )
        prepared = store.prepare_assessor(
            cycle_ids=(self.cycle_id,),
            task_id="trading-paper-task-001",
            capability_id="TRADING_DECISION",
            assessment_due_at="2026-08-13T12:14:00+00:00",
        )
        request = LocalCapabilityAssessorMailbox(
            self.fixture.runtime_root
        ).load_request(self.cycle_id)
        output = request["packet"]["output_contract"]
        self.assertEqual(OUTPUT_CONTRACT_SCHEMA_ID, output["schema_id"])
        self.assertEqual("1.2.0", output["schema_version"])
        self.assertEqual(
            list(PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"]),
            output["findings"]["criterion_ids"],
        )
        self.assertEqual(
            "RFC8259_CANONICAL_COMPACT_UTF8_SORTED_KEYS_PLUS_ONE_NEWLINE",
            output["canonical_encoding"],
        )
        execution_sources = [
            item
            for item in output["evidence_sources"]
            if item["source_kind"] == "EXECUTION_INTENT"
        ]
        self.assertEqual(1, len(execution_sources))
        self.assertTrue(
            execution_sources[0]["path"].endswith(
                "/transport/paper-execution-intent.json"
            )
        )
        self.assertEqual("", execution_sources[0]["json_pointer"])
        self.assertNotIn("checkpoint_revision", execution_sources[0])
        self.assertEqual(
            str(
                (
                    self.fixture.runtime_root
                    / "cycles"
                    / self.cycle_id
                    / "transport"
                    / "capability-assessor-findings.json"
                ).absolute()
            ),
            output["output_path"],
        )
        store.acknowledge_assessor_spawn(
            cycle_id=self.cycle_id,
            dispatch_id=str(prepared["dispatch_id"]),
            execution_ref=_ASSESSOR_TASK,
        )
        task = store.preregister(
            cycle_ids=(self.cycle_id,),
            capability_id="TRADING_DECISION",
        )
        _write_and_complete_assessor(
            self.fixture,
            cycle_id=self.cycle_id,
            dispatch_id=str(prepared["dispatch_id"]),
            task=task,
            findings=self._findings(),
        )
        assessment = store.seal_assessment(
            cycle_ids=(self.cycle_id,),
            capability_id="TRADING_DECISION",
            assessment_id="trading-paper-assessment-001",
        )
        self.assertEqual(self.fixture._GOAL_ID, task.subject_agent_id)
        self.assertEqual(task.task_sha256, store.load_task("TRADING_DECISION").task_sha256)
        self.assertEqual(
            assessment.assessment_sha256,
            store.load_assessment("TRADING_DECISION").assessment_sha256,
        )
        self.assertEqual(
            "NOT_EVALUATED_PRE_OUTCOME",
            assessment.assessment_vector["prediction"],
        )

    def test_api_accepts_no_caller_facts_assessor_or_findings(self) -> None:
        preregister_parameters = inspect.signature(
            FilePaperCapabilityEvaluationStore.preregister
        ).parameters
        seal_parameters = inspect.signature(
            FilePaperCapabilityEvaluationStore.seal_assessment
        ).parameters
        forbidden = {
            "snapshot_sha256",
            "intent_sha256",
            "pre_ledger_head",
            "post_ledger_head",
            "physical_task_id",
            "assessor_id",
            "findings",
        }
        self.assertTrue(forbidden.isdisjoint(preregister_parameters))
        self.assertTrue(forbidden.isdisjoint(seal_parameters))

    def test_paper_cli_has_repeatable_exact_cycles_and_derived_inputs_only(self) -> None:
        parser = market_cycle_cli._parser()  # noqa: SLF001 - direct CLI contract probe
        prepared = parser.parse_args(
            [
                "paper-capability-prepare-assessor",
                "POSITION_MANAGEMENT",
                "position-task-001",
                "2026-08-13T12:19:00+00:00",
                "--cycle-id",
                "position-d0",
                "--cycle-id",
                "position-d1",
            ]
        )
        preregistered = parser.parse_args(
            [
                "paper-capability-preregister",
                "POSITION_MANAGEMENT",
                "--cycle-id",
                "position-d0",
                "--cycle-id",
                "position-d1",
            ]
        )
        sealed = parser.parse_args(
            [
                "paper-capability-seal-assessment",
                "POSITION_MANAGEMENT",
                "position-assessment-001",
                "--cycle-id",
                "position-d0",
                "--cycle-id",
                "position-d1",
            ]
        )
        self.assertEqual(["position-d0", "position-d1"], prepared.cycle_ids)
        self.assertEqual(prepared.cycle_ids, preregistered.cycle_ids)
        self.assertEqual(prepared.cycle_ids, sealed.cycle_ids)
        for namespace in (prepared, preregistered, sealed):
            for forbidden in (
                "subject",
                "assessor",
                "findings",
                "rubric",
                "action",
                "position",
                "order",
                "account",
            ):
                self.assertNotIn(forbidden, vars(namespace))
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "paper-capability-preregister",
                    "POSITION_MANAGEMENT",
                    "--cycle-id",
                    "position-d0,position-d1",
                ]
            )

        with (
            patch.object(
                market_cycle_cli,
                "build_market_cycle_runtime",
                return_value=self.fixture.runtime,
            ),
            patch.object(market_cycle_cli, "_write"),
            patch.object(
                FilePaperCapabilityEvaluationStore,
                "acknowledge_assessor_spawn",
                return_value={"status": "DISPATCHED"},
            ) as paper_ack,
        ):
            self.assertEqual(
                0,
                market_cycle_cli.main(
                    [
                        "--runtime-root",
                        str(self.fixture.runtime_root),
                        "controller-ack-worker-spawn",
                        self.cycle_id,
                        "capability-assessor-v1",
                        "dispatch-001",
                        _ASSESSOR_TASK,
                    ]
                ),
            )
        paper_ack.assert_called_once_with(
            cycle_id=self.cycle_id,
            dispatch_id="dispatch-001",
            execution_ref=_ASSESSOR_TASK,
        )

    def test_position_bracket_then_commandless_point_reaches_preregister(self) -> None:
        policy, facts, d0_intent = _position_evidence_points()
        self.assertIsNotNone(facts[0].execution_intent.bracket)
        self.assertIsNone(facts[1].execution_intent.command)
        times = iter(
            (
                "2026-08-13T12:12:10+00:00",
                "2026-08-13T12:12:11+00:00",
            )
        )

        def trusted_clock() -> str:
            value = next(times)
            self.fixture.clock.current = value
            return value

        store = FilePaperCapabilityEvaluationStore(
            self.fixture.runtime, clock=trusted_clock
        )
        for fact in facts:
            (
                self.fixture.runtime_root
                / "cycles"
                / fact.snapshot.cycle_id
                / "transport"
            ).mkdir(parents=True)
        with (
            patch.object(store, "_policy", return_value=policy),
            patch.object(store, "_facts", return_value=facts),
        ):
            prepared = store.prepare_assessor(
                cycle_ids=(facts[0].snapshot.cycle_id, self.cycle_id),
                task_id="position-canonical-two-point",
                capability_id="POSITION_MANAGEMENT",
                assessment_due_at="2026-08-13T12:19:00+00:00",
            )
            self.assertEqual("SPAWN_REQUESTED", prepared["status"])
            store.acknowledge_assessor_spawn(
                cycle_id=self.cycle_id,
                dispatch_id=str(prepared["dispatch_id"]),
                execution_ref=_ASSESSOR_TASK,
            )
            task = store.preregister(
                cycle_ids=(facts[0].snapshot.cycle_id, self.cycle_id),
                capability_id="POSITION_MANAGEMENT",
            )
        self.assertEqual(2, len(task.decision_points))
        self.assertEqual(
            d0_intent.intent_id, task.decision_points[0].intent_id
        )
        self.assertEqual("COMPLETE", task.decision_points[0].cycle_completion_status)
        self.assertEqual("HOLD", task.decision_points[1].action)
        self.assertEqual(
            "PRIOR_COMPLETE_OBSERVED",
            task.decision_points[1].prior_decision_status,
        )
        task_basis = LocalCapabilityAssessorMailbox(
            self.fixture.runtime_root
        ).load_request(self.cycle_id)["packet"]["task_basis"]
        self.assertEqual(task.to_dict()["rubric"], task_basis["rubric"])
        self.assertEqual(
            task.decision_points[1].position_mechanical_evidence.to_dict(),
            task_basis["decision_points"][1]["position_mechanical_evidence"],
        )

    def test_store_rejects_nonphysical_or_subject_assessor_before_ack_write(self) -> None:
        self.fixture.clock.current = "2026-08-13T12:00:29+00:00"
        store = FilePaperCapabilityEvaluationStore(
            self.fixture.runtime,
            clock=lambda: "2026-08-13T12:00:29+00:00",
        )
        prepared = store.prepare_assessor(
            cycle_ids=(self.cycle_id,),
            task_id="trading-paper-task-independence",
            capability_id="TRADING_DECISION",
            assessment_due_at="2026-08-13T12:14:00+00:00",
        )
        before = dict(
            self.fixture.runtime.controller_state.recover_worker(
                self.cycle_id, "capability-assessor-v1"
            )
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationStoreError,
            "PAPER_CAPABILITY_ASSESSOR_PHYSICAL_GOAL_REQUIRED",
        ):
            store.acknowledge_assessor_spawn(
                cycle_id=self.cycle_id,
                dispatch_id=str(prepared["dispatch_id"]),
                execution_ref="codex-task:not-a-physical-goal",
            )
        self.assertEqual(
            before,
            self.fixture.runtime.controller_state.recover_worker(
                self.cycle_id, "capability-assessor-v1"
            ),
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationStoreError,
            "PAPER_CAPABILITY_ASSESSOR_MUST_BE_INDEPENDENT",
        ):
            store.acknowledge_assessor_spawn(
                cycle_id=self.cycle_id,
                dispatch_id=str(prepared["dispatch_id"]),
                execution_ref=self.fixture._GOAL_ID,
            )
        self.assertEqual(
            before,
            self.fixture.runtime.controller_state.recover_worker(
                self.cycle_id, "capability-assessor-v1"
            ),
        )


class V332PositionCapabilityFactRoutingTests(unittest.TestCase):
    def test_position_fact_rebuild_requires_completed_history_and_pre_outcome_tail(self) -> None:
        store = object.__new__(FilePaperCapabilityEvaluationStore)
        policy = replace(
            _singleton_policy("position-fact-routing"),
            capability_ids=("POSITION_MANAGEMENT",),
        )
        calls: list[tuple[str, bool]] = []

        def fake_evidence(cycle_id: str, **kwargs: object):
            calls.append((cycle_id, bool(kwargs["require_complete"])))
            return cycle_id

        with patch.object(store, "_evidence", side_effect=fake_evidence):
            facts = store._facts(
                ("position-d0", "position-d1"),
                capability_id="POSITION_MANAGEMENT",
                policy=policy,
            )
        self.assertEqual(("position-d0", "position-d1"), facts)
        self.assertEqual(
            [("position-d0", True), ("position-d1", False)], calls
        )


class V332AttentionCapabilityStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        policy_patch = patch.object(paper_fixture, "_policy", _attention_policy)
        policy_patch.start()
        self.addCleanup(policy_patch.stop)
        self.fixture = paper_fixture.V332HypePaperRuntimeTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.paper.setup()
        paper_status = self.fixture.paper.status()
        registry = paper_status["agent_registry"]
        self.goal_id = str(registry["physical_task_id"])
        self.continuity_nonce = str(registry["continuity_nonce"])
        self.prior_cycle_id = self.fixture._seal_decision()
        prior_agent_request = loads_json_strict(
            (
                self.fixture.runtime_root
                / "cycles"
                / self.prior_cycle_id
                / "transport"
                / "agent-request.json"
            ).read_bytes()
        )
        prior_cursor = prior_agent_request["packet"]["paper_context"][
            "data_evidence"
        ]["data_cursor"]
        self.fixture.clock.current = "2026-08-13T12:00:25.250000+00:00"
        checkpoint = self.fixture.runtime.submit_goal_attention_checkpoint(
            AttentionRequest(
                request_id=f"{self.prior_cycle_id}-attention",
                logical_agent_id=self.fixture.paper.logical_agent_id,
                agent_generation=1,
                continuity_nonce=self.continuity_nonce,
                symbol="HYPE-USDT-SWAP",
                mode="WAKE_AFTER",
                issued_at="2026-08-13T12:00:25+00:00",
                continue_until=None,
                earliest_wake_at="2026-08-13T12:00:30+00:00",
                latest_useful_at="2026-08-13T12:01:00+00:00",
                reason_summary="Re-check the exact sealed HYPE decision.",
                requested_focus="Paper transition and bounded risk.",
                hypothesis_or_episode_ref=self.prior_cycle_id,
                position_and_open_order_ref=(
                    build_paper_position_and_open_order_ref(
                        account_id=self.fixture.paper.account_id,
                        ledger_revision=int(paper_status["ledger_revision"]),
                        ledger_head_sha256=str(
                            paper_status["ledger_head_record_sha256"]
                        ),
                    )
                ),
                data_cursor=prior_cursor,
            )
        )
        self.assertEqual("CHECKPOINTED", checkpoint["status"])
        self.cycle_id = self._seal_followup_decision(
            "hype-decision-followup-001"
        )

    def _seal_followup_decision(self, cycle_id: str) -> str:
        request = replace(
            paper_fixture._v332_request(cycle_id),
            requested_at="2026-08-13T12:00:11.750000+00:00",
        )
        self.fixture.runtime.service.create(request)
        self.fixture._seal_post_account_core(cycle_id)
        self.fixture.clock.current = "2026-08-13T12:00:34+00:00"
        self.assertEqual(
            "INPUT_SEALED",
            self.fixture.runtime.service.run_next(cycle_id).state.stage,
        )
        self.assertEqual(
            "AGENT_DELIVERY_PENDING",
            self.fixture.runtime.service.run_next(cycle_id).pending_reason,
        )
        self.fixture.clock.current = "2026-08-13T12:00:40.200000+00:00"
        self.assertEqual(
            "CREATED",
            self.fixture.runtime.service.deliver_agent_decision(
                cycle_id, paper_fixture._DECISION_BYTES
            ),
        )
        self.assertEqual(
            "ANALYZED",
            self.fixture.runtime.service.run_next(cycle_id).state.stage,
        )
        self.assertEqual(
            "PLAN_SEALED",
            self.fixture.runtime.service.run_next(cycle_id).state.stage,
        )
        return cycle_id

    def _findings(self) -> tuple[PaperCapabilityFindingV1, ...]:
        request_document = loads_json_strict(
            (
            self.fixture.runtime_root
            / "cycles"
            / self.cycle_id
            / "transport"
                / "agent-request.json"
            ).read_bytes()
        )
        request = AttentionRequest.from_dict(
            request_document["packet"]["paper_context"]
            ["continuity_projection"]["latest_attention_request"]["request"]
        )
        raw = canonical_bytes(request.to_dict())
        excerpt = request.requested_focus.encode("utf-8")
        start = raw.index(excerpt)
        span = PaperEvidenceSpanV1(
            cycle_id=self.cycle_id,
            source_kind="ATTENTION_REQUEST",
            source_sha256=hashlib.sha256(raw).hexdigest(),
            start_byte=start,
            end_byte=start + len(excerpt),
            selected_utf8_sha256=hashlib.sha256(excerpt).hexdigest(),
        )
        return tuple(
            PaperCapabilityFindingV1(
                criterion_id=criterion,
                status="UNRESOLVED",
                rationale=(
                    "Exact Agent attention text is available; semantic sufficiency "
                    "requires the independent assessor's judgment."
                ),
                evidence_spans=(span,),
            )
            for criterion in PAPER_CAPABILITY_CRITERIA["ATTENTION_SCHEDULING"]
        )

    def test_store_seals_self_managed_checkpoint_followed_by_real_decision(self) -> None:
        times = iter(
            (
                "2026-08-13T12:00:42+00:00",
                "2026-08-13T12:00:43+00:00",
                "2026-08-13T12:00:45+00:00",
            )
        )
        self.fixture.clock.current = "2026-08-13T12:00:42+00:00"
        store = FilePaperCapabilityEvaluationStore(
            self.fixture.runtime, clock=lambda: next(times)
        )
        prepared = store.prepare_assessor(
            cycle_ids=(self.cycle_id,),
            task_id="attention-paper-task-001",
            capability_id="ATTENTION_SCHEDULING",
            assessment_due_at="2026-08-13T12:14:00+00:00",
        )
        request = LocalCapabilityAssessorMailbox(
            self.fixture.runtime_root
        ).load_request(self.cycle_id)
        self.assertEqual(
            ["DECISION_TEXT", "ATTENTION_REQUEST"],
            request["packet"]["output_contract"]["findings"][
                "allowed_source_kinds"
            ],
        )
        attention_sources = [
            item
            for item in request["packet"]["output_contract"]["evidence_sources"]
            if item["source_kind"] == "ATTENTION_REQUEST"
        ]
        self.assertEqual(1, len(attention_sources))
        attention_source = attention_sources[0]
        self.assertEqual("/payload/request", attention_source["json_pointer"])
        self.assertEqual(
            "CANONICAL_JSON_VALUE_BYTES", attention_source["bytes"]
        )
        self.assertNotIn("attention-decision.json", attention_source["path"])
        self.assertTrue(Path(attention_source["path"]).is_file())
        checkpoint_document = loads_json_strict(
            Path(attention_source["path"]).read_bytes()
        )
        self.assertEqual(
            attention_source["source_sha256"],
            canonical_digest(checkpoint_document["payload"]["request"]),
        )
        self.assertEqual(
            attention_source["checkpoint_document_sha256"],
            canonical_digest(checkpoint_document),
        )
        self.assertEqual(
            attention_source["checkpoint_event_sha256"],
            checkpoint_document["event_sha256"],
        )
        store.acknowledge_assessor_spawn(
            cycle_id=self.cycle_id,
            dispatch_id=str(prepared["dispatch_id"]),
            execution_ref=_ASSESSOR_TASK,
        )
        task = store.preregister(
            cycle_ids=(self.cycle_id,),
            capability_id="ATTENTION_SCHEDULING",
        )
        _write_and_complete_assessor(
            self.fixture,
            cycle_id=self.cycle_id,
            dispatch_id=str(prepared["dispatch_id"]),
            task=task,
            findings=self._findings(),
            completed_at="2026-08-13T12:00:44+00:00",
        )
        assessment = store.seal_assessment(
            cycle_ids=(self.cycle_id,),
            capability_id="ATTENTION_SCHEDULING",
            assessment_id="attention-paper-assessment-001",
        )
        point = task.decision_points[0]
        self.assertEqual(
            point.attention_sha256, attention_source["source_sha256"]
        )
        self.assertEqual(
            point.attention_checkpoint_document_sha256,
            attention_source["checkpoint_document_sha256"],
        )
        self.assertEqual(
            point.attention_checkpoint_event_sha256,
            attention_source["checkpoint_event_sha256"],
        )
        self.assertEqual(
            point.attention_checkpoint_revision,
            attention_source["checkpoint_revision"],
        )
        self.assertEqual(
            point.attention_stream_head_document_sha256,
            attention_source["stream_head_document_sha256"],
        )
        self.assertEqual(self.goal_id, task.subject_agent_id)
        self.assertEqual("WAKE_AFTER", point.attention_mode)
        self.assertEqual(
            "WITHIN_SELF_SELECTED_WINDOW", point.followup_window_status
        )
        self.assertEqual(2, point.attention_checkpoint_revision)
        self.assertEqual(
            point.attention_checkpoint_event_sha256,
            point.attention_stream_head_event_sha256,
        )
        self.assertNotIn("intent_id", point.to_dict())
        self.assertNotIn("attention_receipt_sha256", point.to_dict())
        self.assertEqual(
            "UNRESOLVED_ON_THIS_SAMPLE",
            assessment.assessment_vector["capability"],
        )
        self.assertEqual(
            task.task_sha256,
            store.load_task("ATTENTION_SCHEDULING").task_sha256,
        )


if __name__ == "__main__":
    unittest.main()
