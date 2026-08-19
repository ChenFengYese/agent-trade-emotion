from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes

from trade_system.theory_paper_v2.domain.market_cycle import (
    AGENT_OUTPUT_INCOMPLETE,
    CURRENT_THEORY_IDENTITY,
    MEMORY_CONTEXT_MAX_UTF8_BYTES,
    MEMORY_ITEM_LIMITS,
    MEMORY_ITEM_MAX_UTF8_BYTES,
    RUN_STATE_LOGICAL_OWNER,
    RUN_STATE_PHYSICAL_WRITER,
    ArtifactRef,
    BehaviorPlan,
    CycleRequest,
    HypothesisRecord,
    InputSnapshot,
    MarketCycleContractError,
    Outcome,
    Review,
    RunState,
    TheoryIdentity,
    TheoryIdentityError,
    VerifiedMemoryItem,
    build_review,
    calculate_multitimeframe_context,
    copy_agent_decision_to_behavior_plan,
    normalize_verified_memory_items,
    record_agent_decision,
    snapshot_bound_memory_context,
    validate_snapshot_bound_memory_context,
    validate_run_state_transition,
    verified_memory_context,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class MarketCycleContractTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.raw_ref = ArtifactRef(
            artifact_type="RawCapture",
            artifact_id="raw-0001",
            path="raw/raw-0001.json",
            size_bytes=100,
            sha256="a" * 64,
        )
        self.request = CycleRequest(
            request_id="request-0001",
            cycle_id="cycle-0001",
            requested_at="2026-08-11T00:00:00+00:00",
            venue_id="OKX",
            instrument_id="BTC-USDT-SWAP",
            contract_identity="OKX:BTC-USDT-SWAP:linear",
            analysis_profile="COLD",
            data_profile="BASELINE_PRICE",
            outcome_horizon_seconds=900,
            outcome_tolerance_seconds=30,
            lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
        )
        self.snapshot = InputSnapshot.seal(
            self.request,
            snapshot_id="snapshot-0001",
            source_cutoff_at="2026-08-11T00:01:00+00:00",
            decision_at="2026-08-11T00:01:00+00:00",
            sealed_at="2026-08-11T00:01:01+00:00",
            core_observations=self._core_observations(),
            optional_observations={},
            unknowns=("ORDER_FLOW:UNKNOWN_NOT_OBSERVED",),
            raw_refs=(self.raw_ref,),
            source_health=(),
        )
        self.snapshot_ref = ArtifactRef(
            artifact_type="InputSnapshot",
            artifact_id=self.snapshot.snapshot_id,
            path="artifacts/InputSnapshot.json",
            size_bytes=1000,
            sha256="1" * 64,
        )

    def _core_observations(self) -> dict[str, object]:
        common = {
            "available_at": "2026-08-11T00:00:59+00:00",
            "raw_sha256": self.raw_ref.sha256,
        }
        return {
            "server_time": {**common, "value": "2026-08-11T00:00:59+00:00"},
            "instrument": {**common, "value": "BTC-USDT-SWAP"},
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
        }

    def _record(
        self,
        text: str,
        *,
        action: object = None,
        position: object = None,
        index: object = (),
        delivered_at: str = "2026-08-11T00:01:02+00:00",
        sealed_at: str = "2026-08-11T00:01:02+00:00",
        decision_sha256: str | None = None,
    ) -> HypothesisRecord:
        raw = text.encode("utf-8")
        return record_agent_decision(
            self.snapshot,
            self.snapshot_ref,
            record_id="hypotheses-0001",
            sealed_at=sealed_at,
            agent_delivered_at=delivered_at,
            agent_request_sha256="b" * 64,
            agent_delivery_path="transport/agent-delivery.json",
            agent_delivery_sha256="c" * 64,
            agent_decision_text=text,
            agent_decision_size_bytes=len(raw),
            agent_decision_sha256=decision_sha256 or hashlib.sha256(raw).hexdigest(),
            hypothesis_index=index,
            agent_action_text=action,
            agent_position_text=position,
            unresolved_unknowns=("ORDER_FLOW:UNKNOWN_NOT_OBSERVED",),
        )

    @staticmethod
    def _record_ref(record: HypothesisRecord) -> ArtifactRef:
        return ArtifactRef(
            artifact_type="HypothesisRecord",
            artifact_id=record.record_id,
            path="artifacts/HypothesisRecord.json",
            size_bytes=1200,
            sha256="2" * 64,
        )

    def _plan(self, record: HypothesisRecord) -> BehaviorPlan:
        return copy_agent_decision_to_behavior_plan(
            record,
            self._record_ref(record),
            plan_id="plan-0001",
            sealed_at=record.agent_delivered_at,
        )

    @staticmethod
    def _plan_ref(plan: BehaviorPlan) -> ArtifactRef:
        return ArtifactRef(
            artifact_type="BehaviorPlan",
            artifact_id=plan.plan_id,
            path="artifacts/BehaviorPlan.json",
            size_bytes=900,
            sha256="3" * 64,
        )

    def _typed_missing_outcome(self, plan: BehaviorPlan) -> Outcome:
        return Outcome(
            outcome_id="outcome-0001",
            cycle_id=plan.cycle_id,
            behavior_plan_ref=self._plan_ref(plan),
            due_at=plan.outcome_due_at,
            tolerance_seconds=plan.outcome_tolerance_seconds,
            observed_at="2026-08-11T00:16:01+00:00",
            sealed_at="2026-08-11T00:16:02+00:00",
            terminal_status="TYPED_MISSING",
            endpoint_observation=None,
            typed_missing="UNKNOWN_COVERAGE_LOSS",
            path_observations={},
            raw_refs=(),
        )

    def _calculation_snapshot(
        self, bar_count: int
    ) -> tuple[InputSnapshot, ArtifactRef, list[dict[str, object]]]:
        start = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
        bars: list[dict[str, object]] = []
        for index in range(bar_count):
            opened = start + timedelta(minutes=15 * index)
            closed = opened + timedelta(minutes=15)
            base = 100_000 + index
            bars.append(
                {
                    "opened_at": opened.isoformat(),
                    "closed_at": closed.isoformat(),
                    "open": str(base),
                    "high": str(base + 10),
                    "low": str(base - 10),
                    "close": str(base + 5),
                    "confirmed_closed": True,
                }
            )
        last_closed = bars[-1]["closed_at"] if bars else start.isoformat()
        common = {
            "available_at": "2026-08-11T00:00:59+00:00",
            "raw_sha256": self.raw_ref.sha256,
        }
        snapshot = replace(
            self.snapshot,
            snapshot_id=f"calculation-{bar_count}",
            core_observations={
                "server_time": {
                    **common,
                    "value": "2026-08-11T00:00:59+00:00",
                },
                "instrument": {**common, "value": "BTC-USDT-SWAP"},
                "mark_price": {**common, "value": "100100"},
                "closed_15m_bars": {
                    **common,
                    "last_closed_at": last_closed,
                    "value": bars,
                },
            },
        )
        raw = canonical_bytes(snapshot.to_dict())
        snapshot_ref = ArtifactRef(
            artifact_type="InputSnapshot",
            artifact_id=snapshot.snapshot_id,
            path="artifacts/InputSnapshot.json",
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        return snapshot, snapshot_ref, bars

    @staticmethod
    def _assert_no_float(value: object) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                MarketCycleContractTest._assert_no_float(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                MarketCycleContractTest._assert_no_float(nested)
        elif isinstance(value, float):
            raise AssertionError(f"deterministic result leaked float {value!r}")

    @staticmethod
    def _outcome_ref(outcome: Outcome) -> ArtifactRef:
        return ArtifactRef(
            artifact_type="Outcome",
            artifact_id=outcome.outcome_id,
            path="artifacts/Outcome.json",
            size_bytes=400,
            sha256="4" * 64,
        )

    def test_current_identity_request_snapshot_and_refs_round_trip(self) -> None:
        self.assertEqual(self.request.theory_identity, CURRENT_THEORY_IDENTITY)
        self.assertEqual(
            TheoryIdentity.from_dict(CURRENT_THEORY_IDENTITY.to_dict()),
            CURRENT_THEORY_IDENTITY,
        )
        self.assertEqual(
            TheoryIdentity.from_dict(V332_THEORY_IDENTITY.to_dict()),
            V332_THEORY_IDENTITY,
        )
        changed = CURRENT_THEORY_IDENTITY.to_dict()
        changed["manifest_digest"] = "0" * 64
        with self.assertRaises(TheoryIdentityError):
            TheoryIdentity.from_dict(changed)
        malformed = V332_THEORY_IDENTITY.to_dict()
        malformed["theory_version"] = 332
        with self.assertRaises(TheoryIdentityError):
            TheoryIdentity.from_dict(malformed)

        v332_request = replace(
            self.request,
            request_id="request-v332",
            cycle_id="cycle-v332",
            theory_identity=V332_THEORY_IDENTITY,
        )
        v332_snapshot = InputSnapshot.seal(
            v332_request,
            snapshot_id="snapshot-v332",
            source_cutoff_at="2026-08-11T00:01:00+00:00",
            decision_at="2026-08-11T00:01:00+00:00",
            sealed_at="2026-08-11T00:01:01+00:00",
            core_observations=self._core_observations(),
            optional_observations={},
            unknowns=("ORDER_FLOW:UNKNOWN_NOT_OBSERVED",),
            raw_refs=(self.raw_ref,),
            source_health=(),
        )
        self.assertEqual(v332_snapshot.theory_identity, V332_THEORY_IDENTITY)
        self.assertEqual(
            CycleRequest.from_dict(v332_request.to_dict()), v332_request
        )
        self.assertEqual(
            InputSnapshot.from_dict(v332_snapshot.to_dict()), v332_snapshot
        )

        self.assertEqual(CycleRequest.from_dict(self.request.to_dict()), self.request)
        self.assertEqual(InputSnapshot.from_dict(self.snapshot.to_dict()), self.snapshot)
        self.assertEqual(
            ArtifactRef.from_dict(self.snapshot_ref.to_dict()), self.snapshot_ref
        )
        with self.assertRaises(MarketCycleContractError):
            ArtifactRef(
                artifact_type="InputSnapshot",
                artifact_id="snapshot",
                path="../outside.json",
                size_bytes=1,
                sha256="1" * 64,
            )

        future = self._core_observations()
        future["mark_price"]["available_at"] = "2026-08-11T00:01:01+00:00"
        with self.assertRaises(MarketCycleContractError):
            InputSnapshot.seal(
                self.request,
                snapshot_id="future-input",
                source_cutoff_at="2026-08-11T00:01:00+00:00",
                decision_at="2026-08-11T00:01:00+00:00",
                sealed_at="2026-08-11T00:01:02+00:00",
                core_observations=future,
                optional_observations={},
                unknowns=(),
                raw_refs=(self.raw_ref,),
                source_health=(),
            )

    def test_agent_actions_position_geometry_and_text_are_never_rewritten(self) -> None:
        cases = (
            (
                "LONG",
                "# 决策\n\n动作：LONG\n入场点位：118000\n止损：117200\nTargets：119500 / 121000\n仓位：0.25R，分批管理\n",
                "LONG",
                "入场点位：118000\n止损：117200\nTargets：119500 / 121000\n仓位：0.25R，分批管理",
            ),
            (
                "SHORT",
                "我选择 SHORT 作为不可执行参考动作。点位 117900；止损 118650；targets 116800、115900；仓位文本：最大 0.20R。\n",
                "SHORT",
                "点位 117900；止损 118650；targets 116800、115900；仓位文本：最大 0.20R",
            ),
            (
                "WAIT",
                "[观察日志]\naction=WAIT\nposition=保持空仓观察；不建立参考风险。\n",
                "WAIT",
                "position=保持空仓观察；不建立参考风险",
            ),
            (
                "natural-language",
                "先等待价格站稳区间上沿，再考虑小规模多头参考仓位。\n仓位管理：确认前为零，确认后分两段；止损与 targets 由 Agent 原文保留。\n",
                "先等待价格站稳区间上沿，再考虑小规模多头参考仓位",
                "仓位管理：确认前为零，确认后分两段；止损与 targets 由 Agent 原文保留",
            ),
        )
        for name, text, action, position in cases:
            with self.subTest(name=name):
                record = self._record(
                    text,
                    action=action,
                    position=position,
                    index=("候选路径保持开放",),
                )
                plan = self._plan(record)
                self.assertTrue(text.endswith("\n"))
                self.assertEqual(record.projection_status, "AVAILABLE")
                self.assertEqual(record.agent_action_text, action)
                self.assertEqual(record.agent_position_text, position)
                self.assertEqual(record.agent_decision_text, text)
                self.assertEqual(record.agent_decision_sha256, _sha256(text))
                self.assertEqual(
                    HypothesisRecord.from_dict(record.to_dict()), record
                )
                self.assertEqual(BehaviorPlan.from_dict(plan.to_dict()), plan)
                self.assertEqual(plan.agent_decision_text, text)
                self.assertEqual(plan.agent_decision_sha256, _sha256(text))
                self.assertEqual(plan.agent_action_text, action)
                self.assertEqual(plan.agent_position_text, position)
                self.assertEqual(plan.agent_request_sha256, record.agent_request_sha256)
                self.assertEqual(plan.agent_delivery_sha256, record.agent_delivery_sha256)

    def test_optional_projection_gaps_are_unknown_not_contract_failures(self) -> None:
        text = (
            "# 市场观察\n"
            "价格结构仍有冲突。\n"
            "## 额外章节\n"
            "未校准概率 70%，不是可用的统计校准。\n"
            "没有 lead/runner/OTHER，也没有动作或仓位字段。\n"
        )
        record = self._record(
            text,
            action="文本中不存在的标准化动作",
            position=None,
            index="不是数组",
        )
        plan = self._plan(record)

        self.assertEqual(record.projection_status, "UNKNOWN")
        self.assertEqual(record.projection_reason, AGENT_OUTPUT_INCOMPLETE)
        self.assertEqual(record.hypothesis_index, ())
        self.assertIsNone(record.agent_action_text)
        self.assertIsNone(record.agent_position_text)
        self.assertIn(AGENT_OUTPUT_INCOMPLETE, record.unresolved_unknowns)
        self.assertEqual(record.agent_decision_text, text)
        self.assertEqual(plan.agent_decision_text, text)
        self.assertEqual(plan.projection_status, "UNKNOWN")
        self.assertEqual(plan.projection_reason, AGENT_OUTPUT_INCOMPLETE)
        self.assertIsNone(plan.agent_action_text)
        self.assertIsNone(plan.agent_position_text)

    def test_prospective_artifacts_and_sha_bindings_fail_closed(self) -> None:
        outcome_due_at = "2026-08-11T00:16:00+00:00"
        with self.assertRaises(MarketCycleContractError):
            InputSnapshot.seal(
                self.request,
                snapshot_id="late-snapshot",
                source_cutoff_at="2026-08-11T00:01:00+00:00",
                decision_at="2026-08-11T00:01:00+00:00",
                sealed_at=outcome_due_at,
                core_observations=self._core_observations(),
                optional_observations={},
                unknowns=(),
                raw_refs=(self.raw_ref,),
                source_health=(),
            )
        with self.assertRaises(MarketCycleContractError):
            self._record(
                "late\n",
                delivered_at=outcome_due_at,
                sealed_at=outcome_due_at,
            )
        with self.assertRaises(MarketCycleContractError):
            self._record("sha mismatch\n", decision_sha256="0" * 64)

        record = self._record("valid decision\n")
        with self.assertRaises(MarketCycleContractError):
            copy_agent_decision_to_behavior_plan(
                record,
                self._record_ref(record),
                plan_id="late-plan",
                sealed_at=outcome_due_at,
            )

    def test_unknown_projection_typed_missing_and_agent_review_round_trip(self) -> None:
        decision_text = "证据仍冲突；此轮不提供结构化动作或仓位。\n"
        record = self._record(decision_text)
        plan = self._plan(record)
        outcome = self._typed_missing_outcome(plan)
        review_text = (
            "# Agent 复盘\n"
            "Outcome 缺失，因此不做市场成败判断；保留原假说供下一独立周期审查。\n"
        )
        review = build_review(
            plan,
            self._plan_ref(plan),
            outcome,
            self._outcome_ref(outcome),
            review_id="review-0001",
            reviewed_at="2026-08-11T00:16:03+00:00",
            agent_review_delivered_at="2026-08-11T00:16:03+00:00",
            agent_review_request_sha256="5" * 64,
            agent_review_delivery_path="transport/agent-review-delivery.json",
            agent_review_delivery_sha256="6" * 64,
            agent_review_text=review_text,
            agent_review_size_bytes=len(review_text.encode("utf-8")),
            agent_review_sha256=_sha256(review_text),
            agent_review_theory_identity=CURRENT_THEORY_IDENTITY,
        )

        with self.assertRaisesRegex(
            MarketCycleContractError, "same theory identity"
        ):
            mixed_path = {
                "schema_id": "agent_trade_emotion_v332_ordered_outcome_path",
                "schema_version": "1.0.0",
                "status": "CENSORED",
                "path_start_at": plan.agent_delivered_at,
                "path_end_at": outcome.due_at,
                "interval": "15m",
                "intrabar_order": "UNRESOLVED_WITHIN_BAR",
                "points": [],
                "coverage": {
                    "expected_point_count": 0,
                    "observed_point_count": 0,
                    "gap_count": 0,
                    "covers_all_closed_intervals": False,
                },
                "missing_reason": "ORDERED_PATH_UNAVAILABLE",
                "source_health": [],
            }
            build_review(
                plan,
                self._plan_ref(plan),
                replace(
                    outcome,
                    path_observations=mixed_path,
                    theory_identity=V332_THEORY_IDENTITY,
                ),
                self._outcome_ref(outcome),
                review_id="mixed-identity-review",
                reviewed_at="2026-08-11T00:16:03+00:00",
                agent_review_delivered_at="2026-08-11T00:16:03+00:00",
                agent_review_request_sha256="5" * 64,
                agent_review_delivery_path="transport/agent-review-delivery.json",
                agent_review_delivery_sha256="6" * 64,
                agent_review_text=review_text,
                agent_review_size_bytes=len(review_text.encode("utf-8")),
                agent_review_sha256=_sha256(review_text),
                agent_review_theory_identity=CURRENT_THEORY_IDENTITY,
            )

        self.assertEqual(Outcome.from_dict(outcome.to_dict()), outcome)
        self.assertEqual(Review.from_dict(review.to_dict()), review)
        self.assertEqual(review.projection_status, "UNKNOWN")
        self.assertEqual(review.projection_reason, AGENT_OUTPUT_INCOMPLETE)
        self.assertEqual(review.agent_review_text, review_text)
        self.assertEqual(review.agent_review_sha256, _sha256(review_text))
        self.assertEqual(
            set(review.system_facts),
            {
                "outcome_status",
                "typed_missing",
                "endpoint_observation",
                "path_observations",
                "outcome_raw_refs",
            },
        )
        self.assertEqual(review.system_facts["outcome_status"], "TYPED_MISSING")
        self.assertEqual(
            review.system_facts["typed_missing"], "UNKNOWN_COVERAGE_LOSS"
        )
        self.assertFalse(review.theory_writeback)
        serialized = review.to_dict()
        for forbidden in (
            "selected_action",
            "decision_assessment",
            "action_counterfactuals",
            "opportunity_cost",
            "recommendations",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_observed_outcome_requires_sealed_raw_and_tolerance(self) -> None:
        record = self._record("WAIT\n")
        plan = self._plan(record)
        raw = ArtifactRef(
            artifact_type="RawOutcomeCapture",
            artifact_id="raw-outcome",
            path="raw/raw-outcome.json",
            size_bytes=100,
            sha256="d" * 64,
        )
        outcome = Outcome(
            outcome_id="outcome-observed",
            cycle_id=plan.cycle_id,
            behavior_plan_ref=self._plan_ref(plan),
            due_at=plan.outcome_due_at,
            tolerance_seconds=30,
            observed_at="2026-08-11T00:16:20+00:00",
            sealed_at="2026-08-11T00:16:21+00:00",
            terminal_status="OBSERVED",
            endpoint_observation={
                "value": "118100.0",
                "unit": "USDT",
                "price_field": "MARK_PRICE",
                "effective_at": "2026-08-11T00:16:10+00:00",
                "available_at": "2026-08-11T00:16:15+00:00",
                "raw_sha256": raw.sha256,
            },
            typed_missing=None,
            path_observations={"reference_metrics": {"MFE": "UNKNOWN_NOT_COLLECTED"}},
            raw_refs=(raw,),
        )
        self.assertEqual(Outcome.from_dict(outcome.to_dict()), outcome)

    def test_run_state_is_application_owned_and_transitions_only_forward(self) -> None:
        self.assertEqual(RUN_STATE_LOGICAL_OWNER, "Application.CycleService")
        self.assertEqual(RUN_STATE_PHYSICAL_WRITER, "Infrastructure.CycleRepository")
        requested = RunState(
            cycle_id=self.request.cycle_id,
            stage="REQUESTED",
            revision=0,
            artifact_refs=(),
            next_action="CAPTURE_INPUT",
            terminal=False,
            failure_reason=None,
        )
        input_sealed = RunState(
            cycle_id=self.request.cycle_id,
            stage="INPUT_SEALED",
            revision=1,
            artifact_refs=(self.snapshot_ref,),
            next_action="ANALYZE",
            terminal=False,
            failure_reason=None,
        )
        validate_run_state_transition(requested, input_sealed)
        with self.assertRaisesRegex(
            MarketCycleContractError, "cannot change theory identity"
        ):
            validate_run_state_transition(
                requested,
                replace(input_sealed, theory_identity=V332_THEORY_IDENTITY),
            )
        self.assertEqual(RunState.from_dict(input_sealed.to_dict()), input_sealed)
        record = self._record("WAIT\n")
        illegal = RunState(
            cycle_id=self.request.cycle_id,
            stage="ANALYZED",
            revision=2,
            artifact_refs=(self.snapshot_ref, self._record_ref(record)),
            next_action="COPY_AGENT_DECISION_TO_PLAN",
            terminal=False,
            failure_reason=None,
        )
        with self.assertRaises(MarketCycleContractError):
            validate_run_state_transition(requested, illegal)

    def test_verified_memory_is_bounded_provenance_bound_and_empty_is_unknown(
        self,
    ) -> None:
        empty = verified_memory_context(())
        self.assertEqual(empty["status"], "UNKNOWN")
        self.assertEqual(empty["typed_unknown"], "MEMORY_CONTEXT_NOT_PROVIDED")
        self.assertEqual(empty["items"], [])
        self.assertEqual(
            empty["bounds"],
            {
                "item_limits": dict(MEMORY_ITEM_LIMITS),
                "max_item_utf8_bytes": MEMORY_ITEM_MAX_UTF8_BYTES,
                "max_context_utf8_bytes": MEMORY_CONTEXT_MAX_UTF8_BYTES,
            },
        )

        def memory(kind: str, index: int, text: str) -> VerifiedMemoryItem:
            raw = text.encode("utf-8")
            return VerifiedMemoryItem(
                kind=kind,
                status="AVAILABLE",
                source_path=f"runs/prior/memory-{index}.md",
                source_sha256=hashlib.sha256(raw).hexdigest(),
                source_cycle_id=f"prior-cycle-{index}",
                venue_id=self.snapshot.venue_id,
                instrument_id=self.snapshot.instrument_id,
                contract_identity=self.snapshot.contract_identity,
                availability_basis="REVIEWED_AT",
                source_available_at="2026-08-11T00:00:59+00:00",
                verbatim_text=text,
            )

        exact_max = memory(
            "DERIVED_OLDER_SUMMARY", 0, "x" * MEMORY_ITEM_MAX_UTF8_BYTES
        )
        self.assertEqual(exact_max.size_bytes, MEMORY_ITEM_MAX_UTF8_BYTES)
        self.assertEqual(
            normalize_verified_memory_items((exact_max,)), (exact_max,)
        )
        with self.assertRaisesRegex(
            MarketCycleContractError, "exceeds .* UTF-8 bytes"
        ):
            memory(
                "DERIVED_OLDER_SUMMARY",
                1,
                "x" * (MEMORY_ITEM_MAX_UTF8_BYTES + 1),
            )

        two_recent = tuple(
            memory("RECENT_FULL_DAILY", index, f"daily {index}\n")
            for index in range(2)
        )
        self.assertEqual(normalize_verified_memory_items(two_recent), two_recent)
        with self.assertRaisesRegex(
            MarketCycleContractError, "exceeds RECENT_FULL_DAILY bound"
        ):
            normalize_verified_memory_items(
                two_recent + (memory("RECENT_FULL_DAILY", 2, "daily 2\n"),)
            )
        with self.assertRaisesRegex(
            MarketCycleContractError,
            f"exceeds {MEMORY_CONTEXT_MAX_UTF8_BYTES} UTF-8 bytes",
        ):
            normalize_verified_memory_items(
                tuple(
                    memory(
                        "RELATED_DECISION_REVIEW",
                        10 + index,
                        "y" * MEMORY_ITEM_MAX_UTF8_BYTES,
                    )
                    for index in range(5)
                )
            )
        with self.assertRaisesRegex(
            MarketCycleContractError, "source_sha256 does not match"
        ):
            VerifiedMemoryItem(
                kind="RELATED_DECISION_REVIEW",
                status="AVAILABLE",
                source_path="runs/prior/review.md",
                source_sha256="0" * 64,
                source_cycle_id="prior-review-cycle",
                venue_id=self.snapshot.venue_id,
                instrument_id=self.snapshot.instrument_id,
                contract_identity=self.snapshot.contract_identity,
                availability_basis="REVIEWED_AT",
                source_available_at="2026-08-11T00:00:59+00:00",
                verbatim_text="review\n",
            )

        eligible = memory("RELATED_DECISION_REVIEW", 20, "eligible review\n")
        future = replace(
            memory("RELATED_DECISION_REVIEW", 21, "future review secret\n"),
            source_available_at="2026-08-11T00:01:01+00:00",
        )
        other_instrument = replace(
            memory("RELATED_DECISION_REVIEW", 22, "other instrument secret\n"),
            instrument_id="ETH-USDT-SWAP",
        )
        filtered = snapshot_bound_memory_context(
            self.snapshot, (eligible, future, other_instrument)
        )
        self.assertEqual(filtered["status"], "UNKNOWN")
        self.assertEqual(filtered["typed_unknown"], "MEMORY_CONTEXT_PARTIAL")
        self.assertEqual(filtered["items"][0]["verbatim_text"], "eligible review\n")
        self.assertNotIn("verbatim_text", filtered["items"][1])
        self.assertNotIn("verbatim_text", filtered["items"][2])
        self.assertEqual(
            {
                filtered["items"][1]["typed_unknown"],
                filtered["items"][2]["typed_unknown"],
            },
            {
                "MEMORY_SOURCE_AFTER_SNAPSHOT_CUTOFF",
                "MEMORY_SOURCE_INSTRUMENT_MISMATCH",
            },
        )
        self.assertNotIn("future review secret", repr(filtered))
        self.assertNotIn("other instrument secret", repr(filtered))
        self.assertEqual(
            validate_snapshot_bound_memory_context(self.snapshot, filtered),
            filtered,
        )

    def test_non_authoritative_96x15m_calculation_is_exact_and_95_is_unknown(
        self,
    ) -> None:
        snapshot, snapshot_ref, bars = self._calculation_snapshot(96)
        value = calculate_multitimeframe_context(snapshot, snapshot_ref).to_dict()
        self.assertEqual(value["authority"], "NON_AUTHORITATIVE_CALCULATION_ONLY")
        self.assertEqual(value["status"], "AVAILABLE")
        self.assertIsNone(value["typed_unknown"])
        self.assertEqual(value["input_snapshot_ref"], snapshot_ref.to_dict())
        self.assertEqual(value["source_raw_sha256"], self.raw_ref.sha256)
        self.assertEqual(
            value["source_bars_sha256"],
            hashlib.sha256(canonical_bytes(bars)).hexdigest(),
        )
        self.assertEqual(value["source_bar_count"], 96)
        self.assertEqual(value["required_source_bar_count"], 96)
        self.assertEqual(
            {
                name: frame["bar_count"]
                for name, frame in value["result"]["timeframes"].items()
            },
            {"1D": 1, "4H": 6, "1H": 24, "15m": 96},
        )
        self.assertEqual(
            value["formulas"],
            [
                "aggregate.open=first(source.open)",
                "aggregate.high=max(source.high)",
                "aggregate.low=min(source.low)",
                "aggregate.close=last(source.close)",
                "statistics.absolute_change=last_close-first_open",
                "statistics.change_ratio=(last_close-first_open)/first_open",
                "statistics.high_low_range=max(high)-min(low)",
                "statistics.close_mean=sum(close)/96",
            ],
        )
        self._assert_no_float(value)

        short_snapshot, short_ref, short_bars = self._calculation_snapshot(95)
        unknown = calculate_multitimeframe_context(short_snapshot, short_ref).to_dict()
        self.assertEqual(unknown["status"], "UNKNOWN")
        self.assertEqual(
            unknown["typed_unknown"], "INSUFFICIENT_96_CLOSED_15M_BARS"
        )
        self.assertEqual(unknown["source_bar_count"], 95)
        self.assertEqual(unknown["result"], {})
        self.assertEqual(
            unknown["source_bars_sha256"],
            hashlib.sha256(canonical_bytes(short_bars)).hexdigest(),
        )
        self._assert_no_float(unknown)


if __name__ == "__main__":
    unittest.main()
