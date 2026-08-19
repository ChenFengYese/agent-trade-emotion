from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import unittest

from trade_system.theory_paper_v2.application.market_cycle.capability_evaluation import (
    bind_utf8_decision_span,
    build_blind_capability_task,
    build_pre_outcome_capability_assessment,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
)
from trade_system.theory_paper_v2.domain.market_cycle.capability_evaluation import (
    CAPABILITY_CRITERIA,
    CAPABILITY_RUBRICS,
    BlindCapabilityTaskV1,
    CapabilityEvaluationContractError,
    CapabilityFindingV1,
    Utf8DecisionSpanV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    ArtifactRef,
    HypothesisRecord,
    InputSnapshot,
)
from trade_system.theory_paper_v2.domain.market_cycle.experiment import (
    EXPERIMENT_MISSING_DATA_POLICY,
    ExperimentPolicyV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
)


_CYCLE_ID = "v332-capability-cycle-001"
_PHYSICAL_GOAL_ID = "codex-thread:11111111-1111-1111-1111-111111111111"
_OTHER_PHYSICAL_GOAL_ID = "codex-thread:22222222-2222-2222-2222-222222222222"
_THIRD_PHYSICAL_GOAL_ID = "codex-thread:33333333-3333-3333-3333-333333333333"
_REQUEST_PACKET = {"cycle_id": _CYCLE_ID, "bounded": True}
_REQUEST = {
    "packet": _REQUEST_PACKET,
    "packet_sha256": canonical_digest(_REQUEST_PACKET),
}
_DECISION = (
    "市场状态：15分钟下跌后进入支撑争夺；当前数据覆盖约24小时。\n"
    "事实边界：订单簿只是一次REST快照，不能推出持续订单流。\n"
    "假说A：若支撑吸收延续，则先反弹；证伪条件是放量有效跌破。\n"
    "假说B：若卖压继续增强，则支撑失效；区分信号是成交量与OI同向扩张。\n"
    "参与者解释仅是假说，UNKNOWN不视为零。\n"
    "ACTION=WAIT\n"
    "POSITION=flat\n"
)


def _policy(capability_id: str = "MARKET_ANALYSIS") -> ExperimentPolicyV1:
    return ExperimentPolicyV1(
        experiment_id="v332-capability-pilot-001",
        run_id="v332-capability-run-001",
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


def _snapshot_and_ref() -> tuple[InputSnapshot, ArtifactRef]:
    raw_ref = ArtifactRef(
        artifact_type="RawCapture",
        artifact_id=f"{_CYCLE_ID}.raw",
        path="raw/input/body.bin",
        size_bytes=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
    )

    def observation(value: object) -> dict[str, object]:
        return {
            "value": value,
            "available_at": "2026-08-13T12:00:00+00:00",
            "raw_sha256": raw_ref.sha256,
        }

    bars = observation([])
    bars["last_closed_at"] = "2026-08-13T12:00:00+00:00"
    snapshot = InputSnapshot(
        snapshot_id=f"{_CYCLE_ID}.snapshot",
        cycle_id=_CYCLE_ID,
        request_id=f"{_CYCLE_ID}.request",
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
        lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
        core_observations={
            "server_time": observation("2026-08-13T12:00:00+00:00"),
            "instrument": observation(HYPE_OKX_DATA_PROFILE.instrument_id),
            "mark_price": observation("42.5"),
            "closed_15m_bars": bars,
        },
        optional_observations={},
        unknowns=("CONTINUOUS_ORDER_FLOW_UNKNOWN",),
        raw_refs=(raw_ref,),
        source_health=(),
        theory_identity=V332_THEORY_IDENTITY,
    )
    raw = canonical_bytes(snapshot.to_dict())
    return snapshot, ArtifactRef(
        artifact_type="InputSnapshot",
        artifact_id=snapshot.snapshot_id,
        path="artifacts/input-snapshot.json",
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _hypothesis(snapshot: InputSnapshot, snapshot_ref: ArtifactRef) -> HypothesisRecord:
    decision_raw = _DECISION.encode("utf-8")
    return HypothesisRecord(
        record_id=f"{_CYCLE_ID}.hypotheses",
        cycle_id=_CYCLE_ID,
        input_snapshot_ref=snapshot_ref,
        decision_at=snapshot.decision_at,
        agent_delivered_at="2026-08-13T12:00:10+00:00",
        sealed_at="2026-08-13T12:00:10+00:00",
        outcome_horizon_seconds=3600,
        outcome_tolerance_seconds=60,
        agent_request_sha256=canonical_digest(_REQUEST_PACKET),
        agent_delivery_path="transport/agent-delivery.json",
        agent_delivery_sha256="d" * 64,
        agent_decision_text=_DECISION,
        agent_decision_size_bytes=len(decision_raw),
        agent_decision_sha256=hashlib.sha256(decision_raw).hexdigest(),
        projection_status="AVAILABLE",
        projection_reason=None,
        hypothesis_index=(
            "假说A：若支撑吸收延续，则先反弹；证伪条件是放量有效跌破。",
            "假说B：若卖压继续增强，则支撑失效；区分信号是成交量与OI同向扩张。",
        ),
        agent_action_text="ACTION=WAIT",
        agent_position_text="POSITION=flat",
        lawful_actions=snapshot.lawful_actions,
        unresolved_unknowns=snapshot.unknowns,
        theory_identity=V332_THEORY_IDENTITY,
    )


def _span(excerpt: str) -> Utf8DecisionSpanV1:
    raw = _DECISION.encode("utf-8")
    start = raw.index(excerpt.encode("utf-8"))
    return bind_utf8_decision_span(
        _DECISION,
        start_byte=start,
        end_byte=start + len(excerpt.encode("utf-8")),
    )


def _task(capability_id: str):  # noqa: ANN202
    snapshot, snapshot_ref = _snapshot_and_ref()
    hypothesis = _hypothesis(snapshot, snapshot_ref)
    task = build_blind_capability_task(
        task_id=f"{_CYCLE_ID}.{capability_id.lower()}",
        capability_id=capability_id,
        policy=_policy(capability_id),
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
        request_document=_REQUEST,
        subject_agent_id=_PHYSICAL_GOAL_ID,
        decision_delivery_sha256=hypothesis.agent_delivery_sha256,
        assessor_id=_OTHER_PHYSICAL_GOAL_ID,
        created_at="2026-08-13T12:00:11+00:00",
        assessment_due_at="2026-08-13T12:59:00+00:00",
    )
    return task, snapshot, snapshot_ref, hypothesis


class V332CapabilityEvaluationTests(unittest.TestCase):
    def test_market_analysis_blind_vector_binds_every_hash_without_total_score(self) -> None:
        task, snapshot, snapshot_ref, hypothesis = _task("MARKET_ANALYSIS")
        excerpts = {
            "IDENTITY_AND_COVERAGE": "当前数据覆盖约24小时",
            "FACT_INFERENCE_BOUNDARY": "不能推出持续订单流",
            "MULTIFRAME_STATE_ANALYSIS": "15分钟下跌后进入支撑争夺",
            "ACTOR_HYPOTHESIS_DISCIPLINE": "参与者解释仅是假说",
        }
        findings = tuple(
            CapabilityFindingV1(
                criterion_id=criterion,
                status="DEMONSTRATED",
                rationale=f"exact evidence for {criterion}",
                evidence_spans=(_span(excerpts[criterion]),),
            )
            for criterion in CAPABILITY_CRITERIA["MARKET_ANALYSIS"]
        )
        assessment = build_pre_outcome_capability_assessment(
            assessment_id=f"{task.task_id}.assessment",
            task=task,
            policy=_policy("MARKET_ANALYSIS"),
            request_document=_REQUEST,
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
            hypothesis=hypothesis,
            subject_physical_goal_id=_PHYSICAL_GOAL_ID,
            decision_delivery_sha256=hypothesis.agent_delivery_sha256,
            assessed_at="2026-08-13T12:00:12+00:00",
            findings=findings,
        )
        document = assessment.to_dict()
        self.assertEqual(
            document["policy_sha256"],
            _policy("MARKET_ANALYSIS").policy_sha256,
        )
        self.assertEqual(document["task_sha256"], task.task_sha256)
        self.assertEqual(
            document["request_sha256"], canonical_digest(_REQUEST_PACKET)
        )
        self.assertEqual(
            document["request_document_sha256"], canonical_digest(_REQUEST)
        )
        self.assertEqual(document["snapshot_sha256"], snapshot_ref.sha256)
        self.assertEqual(
            document["decision_sha256"], hypothesis.agent_decision_sha256
        )
        self.assertEqual(
            document["subject_agent_id"],
            _PHYSICAL_GOAL_ID,
        )
        self.assertEqual(
            document["decision_delivery_sha256"],
            hypothesis.agent_delivery_sha256,
        )
        self.assertEqual(
            document["rubric"]["rubric_sha256"],
            CAPABILITY_RUBRICS["MARKET_ANALYSIS"]["rubric_sha256"],
        )
        self.assertEqual(
            document["assessment_vector"],
            {
                "operational": "PRE_OUTCOME_BINDINGS_VERIFIED",
                "capability": "DEMONSTRATED_ON_THIS_SAMPLE",
                "prediction": "NOT_EVALUATED_PRE_OUTCOME",
                "generalization": "NOT_EVALUATED_SINGLE_SAMPLE",
                "profitability": "NOT_EVALUATED_NO_COSTED_TRADING_EVIDENCE",
            },
        )
        self.assertNotIn("score", document)
        self.assertNotIn("total_score", document)
        self.assertNotIn(
            "SUBJECT_REFERENCE_IS_SEALED_DELIVERY_NOT_PHYSICAL_GOAL_IDENTITY",
            document["limitations"],
        )
        self.assertNotIn("outcome", inspect.signature(
            build_pre_outcome_capability_assessment
        ).parameters)

    def test_missing_quality_is_recorded_not_rejected_or_promoted(self) -> None:
        task, snapshot, snapshot_ref, hypothesis = _task("HYPOTHESIS_GENERATION")
        findings = (
            CapabilityFindingV1(
                criterion_id="COMPETING_HYPOTHESES",
                status="DEMONSTRATED",
                rationale="two incompatible paths are stated",
                evidence_spans=(_span("假说A"), _span("假说B")),
            ),
            CapabilityFindingV1(
                criterion_id="FALSIFIABILITY",
                status="NOT_DEMONSTRATED",
                rationale="assessor did not find a sufficiently bounded expiry",
            ),
            CapabilityFindingV1(
                criterion_id="DISCRIMINATING_OBSERVATION",
                status="UNRESOLVED",
                rationale="the available wording may not uniquely separate both paths",
            ),
        )
        assessment = build_pre_outcome_capability_assessment(
            assessment_id=f"{task.task_id}.assessment",
            task=task,
            policy=_policy("HYPOTHESIS_GENERATION"),
            request_document=_REQUEST,
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
            hypothesis=hypothesis,
            subject_physical_goal_id=_PHYSICAL_GOAL_ID,
            decision_delivery_sha256=hypothesis.agent_delivery_sha256,
            assessed_at="2026-08-13T12:00:12+00:00",
            findings=findings,
        )
        self.assertEqual(
            assessment.assessment_vector["capability"],
            "NOT_DEMONSTRATED_ON_THIS_SAMPLE",
        )
        self.assertEqual(hypothesis.record_id, f"{_CYCLE_ID}.hypotheses")

    def test_identity_chronology_and_utf8_spans_fail_closed(self) -> None:
        snapshot, snapshot_ref = _snapshot_and_ref()
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError, "assessor must be independent"
        ):
            build_blind_capability_task(
                task_id=f"{_CYCLE_ID}.invalid",
                capability_id="MARKET_ANALYSIS",
                policy=_policy("MARKET_ANALYSIS"),
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                request_document=_REQUEST,
                subject_agent_id=_PHYSICAL_GOAL_ID,
                decision_delivery_sha256="d" * 64,
                assessor_id=_PHYSICAL_GOAL_ID,
                created_at="2026-08-13T12:00:03+00:00",
                assessment_due_at="2026-08-13T12:59:00+00:00",
            )
        first_character_size = len(_DECISION[0].encode("utf-8"))
        self.assertGreater(first_character_size, 1)
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError, "UTF-8 code-point boundaries"
        ):
            bind_utf8_decision_span(_DECISION, start_byte=1, end_byte=3)

        task, snapshot, snapshot_ref, hypothesis = _task("MARKET_ANALYSIS")
        valid = _span("当前数据覆盖约24小时")
        forged = replace(valid, utf8_sha256="0" * 64)
        findings = tuple(
            CapabilityFindingV1(
                criterion_id=criterion,
                status="DEMONSTRATED",
                rationale="forged for binding test",
                evidence_spans=(forged,),
            )
            for criterion in CAPABILITY_CRITERIA["MARKET_ANALYSIS"]
        )
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError, "span digest"
        ):
            build_pre_outcome_capability_assessment(
                assessment_id=f"{task.task_id}.forged",
                task=task,
                policy=_policy("MARKET_ANALYSIS"),
                request_document=_REQUEST,
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                hypothesis=hypothesis,
                subject_physical_goal_id=_PHYSICAL_GOAL_ID,
                decision_delivery_sha256=hypothesis.agent_delivery_sha256,
                assessed_at="2026-08-13T12:00:12+00:00",
                findings=findings,
            )

    def test_request_binding_and_pre_outcome_deadline_reject_tampering(self) -> None:
        task, snapshot, snapshot_ref, hypothesis = _task("HYPOTHESIS_GENERATION")
        findings = tuple(
            CapabilityFindingV1(
                criterion_id=criterion,
                status="UNRESOLVED",
                rationale="deliberately unresolved binding fixture",
            )
            for criterion in CAPABILITY_CRITERIA["HYPOTHESIS_GENERATION"]
        )
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError, "task does not bind"
        ):
            build_pre_outcome_capability_assessment(
                assessment_id=f"{task.task_id}.request-tamper",
                task=task,
                policy=_policy("HYPOTHESIS_GENERATION"),
                request_document={
                    "packet": {"cycle_id": _CYCLE_ID, "bounded": False},
                    "packet_sha256": canonical_digest(
                        {"cycle_id": _CYCLE_ID, "bounded": False}
                    ),
                },
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                hypothesis=hypothesis,
                subject_physical_goal_id=_PHYSICAL_GOAL_ID,
                decision_delivery_sha256=hypothesis.agent_delivery_sha256,
                assessed_at="2026-08-13T12:00:12+00:00",
                findings=findings,
            )
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError, "physical Goal delivery"
        ):
            build_pre_outcome_capability_assessment(
                assessment_id=f"{task.task_id}.author-tamper",
                task=replace(task, subject_agent_id=_THIRD_PHYSICAL_GOAL_ID),
                policy=_policy("HYPOTHESIS_GENERATION"),
                request_document=_REQUEST,
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                hypothesis=hypothesis,
                subject_physical_goal_id=_PHYSICAL_GOAL_ID,
                decision_delivery_sha256=hypothesis.agent_delivery_sha256,
                assessed_at="2026-08-13T12:00:12+00:00",
                findings=findings,
            )
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError,
            "missed the preregistered assessor deadline|before Outcome",
        ):
            build_pre_outcome_capability_assessment(
                assessment_id=f"{task.task_id}.late",
                task=task,
                policy=_policy("HYPOTHESIS_GENERATION"),
                request_document=_REQUEST,
                snapshot=snapshot,
                snapshot_ref=snapshot_ref,
                hypothesis=hypothesis,
                subject_physical_goal_id=_PHYSICAL_GOAL_ID,
                decision_delivery_sha256=hypothesis.agent_delivery_sha256,
                assessed_at=snapshot.outcome_due_at,
                findings=findings,
            )

    def test_frozen_rubric_body_and_digest_reject_tampering(self) -> None:
        task, _, _, _ = _task("MARKET_ANALYSIS")
        changed_body = task.to_dict()
        changed_body["rubric"]["criteria"][0]["assessment_instruction"] = (
            "accept any readable statement"
        )
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError, "frozen capability rubric"
        ):
            BlindCapabilityTaskV1.from_dict(changed_body)

        changed_digest = task.to_dict()
        changed_digest["rubric"]["rubric_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            CapabilityEvaluationContractError, "frozen capability rubric"
        ):
            BlindCapabilityTaskV1.from_dict(changed_digest)


if __name__ == "__main__":
    unittest.main()
