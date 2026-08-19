from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import hashlib
import tempfile
import unittest

from trade_system.theory_paper_v2.application.market_cycle.paper import (
    PaperTradingService,
)
from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.application.market_cycle.attention import (
    AttentionService,
)
from trade_system.theory_paper_v2.application.market_cycle.source import (
    capture_input_snapshot,
)
from trade_system.theory_paper_v2.application.market_cycle.data_profiles import (
    AssetDataProfileMarketDataAdapter,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    ArtifactRef,
    AGENT_OUTPUT_INCOMPLETE,
    BehaviorPlan,
    CycleRequest,
    Outcome,
    Review,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    PaperBracketV1,
    PaperCommandV1,
    PaperCostModelV1,
    PaperExecutionIntentV1,
    PaperMarketSliceV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_context import (
    PaperDecisionContextProvider,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_ledger import (
    FilePaperLedger,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.repository import (
    FileCycleRepository,
    MarketCycleRepositoryError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
    HYPE_OKX_INSTRUMENT_ID,
    build_hype_data_profile_service,
)
from trade_system.theory_paper_v2.infrastructure.market_data.paper_evidence import (
    AdmittedAssetSlicePaperMarketEvidence,
    PaperAssetEvidenceBinding,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)

from tests.test_theory_paper_v2_v332_hype_data import _seal_core, _time
from tests.test_theory_paper_v2_v332_paper_capability_evaluation import (
    _hypothesis as _capability_hypothesis,
    _snapshot as _capability_snapshot,
)


class _ReviewDecisionAuthority:
    @staticmethod
    def current_generation(logical_agent_id: str) -> int | None:
        return 1

    @staticmethod
    def verifies_decision(command: PaperCommandV1) -> bool:
        return True

    @staticmethod
    def verifies_execution_intent(intent: PaperExecutionIntentV1) -> bool:
        return True


class _ReviewMarketEvidence:
    def __init__(self, instrument_evidence: object) -> None:
        self._instrument_evidence = instrument_evidence

    @staticmethod
    def verifies_market_slice(market: PaperMarketSliceV1) -> bool:
        return market.source_sha256 == "f" * 64

    def verifies_instrument_spec(self, spec: object, *, available_by: str) -> bool:
        return bool(
            self._instrument_evidence.verifies_instrument_spec(
                spec, available_by=available_by
            )
        )


def _censored_outcome_path(
    *, path_start_at: str, path_end_at: str, expected_point_count: int
) -> dict[str, object]:
    return {
        "schema_id": "agent_trade_emotion_v332_ordered_outcome_path",
        "schema_version": "1.0.0",
        "status": "CENSORED",
        "path_start_at": path_start_at,
        "path_end_at": path_end_at,
        "interval": "15m",
        "intrabar_order": "UNRESOLVED_WITHIN_BAR",
        "points": [],
        "coverage": {
            "expected_point_count": expected_point_count,
            "observed_point_count": 0,
            "gap_count": expected_point_count,
            "covers_all_closed_intervals": False,
        },
        "missing_reason": "ORDERED_PATH_UNAVAILABLE",
        "source_health": [],
    }


class _PriorCycleRepository(FileCycleRepository):
    def __init__(self, *, stage: str, artifacts: dict[str, dict[str, object]]):
        self._cycle_id = str(artifacts["HypothesisRecord"]["cycle_id"])
        self._documents = artifacts
        self._state = SimpleNamespace(
            stage=stage,
            artifact_refs=tuple(
                ArtifactRef(
                    artifact_type=kind,
                    artifact_id=f"{self._cycle_id}.{kind.lower()}",
                    path=f"artifacts/{kind}.json",
                    size_bytes=len(canonical_bytes(document)),
                    sha256=hashlib.sha256(canonical_bytes(document)).hexdigest(),
                )
                for kind, document in artifacts.items()
            ),
        )

    def list_cycle_ids(self):
        return (self._cycle_id,)

    def load_state(self, cycle_id: str):
        if cycle_id != self._cycle_id:
            raise AssertionError(cycle_id)
        return self._state

    def load_artifact(self, cycle_id: str, artifact_type: str):
        if cycle_id != self._cycle_id:
            raise AssertionError(cycle_id)
        return self._documents[artifact_type]


class _PriorCyclesRepository(FileCycleRepository):
    def __init__(
        self,
        cycles: dict[str, tuple[str, dict[str, dict[str, object]]]],
    ) -> None:
        self._cycles = {
            cycle_id: _PriorCycleRepository(stage=stage, artifacts=artifacts)
            for cycle_id, (stage, artifacts) in cycles.items()
        }

    def list_cycle_ids(self):
        return tuple(sorted(self._cycles))

    def load_state(self, cycle_id: str):
        return self._cycles[cycle_id].load_state(cycle_id)

    def load_artifact(self, cycle_id: str, artifact_type: str):
        return self._cycles[cycle_id].load_artifact(cycle_id, artifact_type)


class _CurrentOutcomeRepository(FileCycleRepository):
    def __init__(self, *, cycle_id: str, outcome: Outcome):
        self._cycle_id = cycle_id
        self._outcome = outcome.to_dict()

    def list_cycle_ids(self):
        return (self._cycle_id,)

    def load_state(self, cycle_id: str):
        raise MarketCycleRepositoryError("cycle state intentionally unavailable")

    def load_artifact(self, cycle_id: str, artifact_type: str):
        if cycle_id == self._cycle_id and artifact_type == "Outcome":
            return self._outcome
        raise MarketCycleRepositoryError("artifact intentionally unavailable")


def _prior_artifacts(
    *,
    complete: bool,
    cycle_id: str = "prior-wait-cycle",
    reviewed_at: str = "2026-08-13T00:10:03+00:00",
    review_sentinel: str = "D0_REVIEW_SENTINEL_EXACT_TEXT",
) -> tuple[dict[str, dict[str, object]], str]:
    snapshot, reference = _capability_snapshot(cycle_id, 0)
    hypothesis = _capability_hypothesis(
        snapshot,
        reference,
        request_sha256="9" * 64,
        minute=0,
    )
    hypothesis_raw = canonical_bytes(hypothesis.to_dict())
    plan = BehaviorPlan(
        plan_id=f"{cycle_id}.plan",
        cycle_id=cycle_id,
        hypothesis_record_ref=ArtifactRef(
            artifact_type="HypothesisRecord",
            artifact_id=hypothesis.record_id,
            path="artifacts/HypothesisRecord.json",
            size_bytes=len(hypothesis_raw),
            sha256=hashlib.sha256(hypothesis_raw).hexdigest(),
        ),
        decision_at=hypothesis.decision_at,
        agent_delivered_at=hypothesis.agent_delivered_at,
        sealed_at=hypothesis.sealed_at,
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
        outcome_due_at=snapshot.outcome_due_at,
        outcome_tolerance_seconds=snapshot.outcome_tolerance_seconds,
        theory_identity=hypothesis.theory_identity,
    )
    documents: dict[str, dict[str, object]] = {
        "HypothesisRecord": hypothesis.to_dict(),
        "BehaviorPlan": plan.to_dict(),
    }
    if complete:
        plan_document = plan.to_dict()
        plan_raw = canonical_bytes(plan_document)
        plan_ref = ArtifactRef(
            artifact_type="BehaviorPlan",
            artifact_id=plan.plan_id,
            path="artifacts/BehaviorPlan.json",
            size_bytes=len(plan_raw),
            sha256=hashlib.sha256(plan_raw).hexdigest(),
        )
        censored_path = _censored_outcome_path(
            path_start_at="2026-08-13T00:09:00+00:00",
            path_end_at="2026-08-13T00:10:00+00:00",
            expected_point_count=0,
        )
        outcome = Outcome(
            outcome_id=f"{cycle_id}.outcome",
            cycle_id=cycle_id,
            behavior_plan_ref=plan_ref,
            due_at="2026-08-13T00:10:00+00:00",
            tolerance_seconds=60,
            observed_at="2026-08-13T00:10:01+00:00",
            sealed_at="2026-08-13T00:10:02+00:00",
            terminal_status="TYPED_MISSING",
            endpoint_observation=None,
            typed_missing="UNKNOWN_COVERAGE_LOSS",
            path_observations=censored_path,
            raw_refs=(),
            theory_identity=hypothesis.theory_identity,
        )
        outcome_document = outcome.to_dict()
        outcome_raw = canonical_bytes(outcome_document)
        outcome_ref = ArtifactRef(
            artifact_type="Outcome",
            artifact_id=outcome.outcome_id,
            path="artifacts/Outcome.json",
            size_bytes=len(outcome_raw),
            sha256=hashlib.sha256(outcome_raw).hexdigest(),
        )
        review_text = (
            f"{review_sentinel}: WAIT preserved optionality, but the "
            "next Decision must compare opportunity cost and fresh geometry.\n"
        )
        review_raw = review_text.encode("utf-8")
        review = Review(
            review_id=f"{cycle_id}.review",
            cycle_id=cycle_id,
            behavior_plan_ref=plan_ref,
            outcome_ref=outcome_ref,
            reviewed_at=reviewed_at,
            outcome_status="TYPED_MISSING",
            agent_decision_sha256=hypothesis.agent_decision_sha256,
            projection_status="UNKNOWN",
            projection_reason=AGENT_OUTPUT_INCOMPLETE,
            system_facts={
                "outcome_status": "TYPED_MISSING",
                "typed_missing": "UNKNOWN_COVERAGE_LOSS",
                "endpoint_observation": None,
                "path_observations": censored_path,
                "outcome_raw_refs": [],
            },
            agent_review_delivered_at=reviewed_at,
            agent_review_request_sha256="d" * 64,
            agent_review_delivery_path="transport/agent-review-delivery.json",
            agent_review_delivery_sha256="e" * 64,
            agent_review_text=review_text,
            agent_review_size_bytes=len(review_raw),
            agent_review_sha256=hashlib.sha256(review_raw).hexdigest(),
            theory_writeback=False,
            theory_identity=hypothesis.theory_identity,
        )
        documents.update(
            {
                "Outcome": outcome_document,
                "Review": review.to_dict(),
            }
        )
    return documents, hypothesis.agent_decision_sha256


class V332PaperDecisionContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.raw_store = FileRawCaptureStore(self.root)
        self.cycle_id = "paper-context-cycle"
        _seal_core(self.raw_store, cycle_id=self.cycle_id)
        self.profiles = build_hype_data_profile_service(
            raw_store=self.raw_store
        )
        adapter = AssetDataProfileMarketDataAdapter(
            service=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
        )
        request = CycleRequest(
            request_id="paper-context-request",
            cycle_id=self.cycle_id,
            requested_at=_time(0),
            venue_id="OKX",
            instrument_id=HYPE_OKX_INSTRUMENT_ID,
            contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
            analysis_profile="COLD",
            data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
            outcome_horizon_seconds=3600,
            outcome_tolerance_seconds=60,
            lawful_actions=("LONG_REFERENCE", "SHORT_REFERENCE", "WAIT"),
            theory_identity=V332_THEORY_IDENTITY,
        )
        self.snapshot = capture_input_snapshot(
            request, market_data=adapter, clock=lambda: _time(20)
        )
        snapshot_payload = canonical_bytes(self.snapshot.to_dict())
        self.snapshot_ref = ArtifactRef(
            artifact_type="InputSnapshot",
            artifact_id=self.snapshot.snapshot_id,
            path="artifacts/InputSnapshot.json",
            sha256=hashlib.sha256(snapshot_payload).hexdigest(),
            size_bytes=len(snapshot_payload),
        )
        self.ledger = FilePaperLedger(self.root / "paper")
        self.policy = {
            "account_id": "hype-paper-capability",
            "setup_cycle_id": self.cycle_id,
            "logical_agent_id": "hype-capability-agent",
            "agent_generation": 1,
            "account_mode": "LINEAR_PERP",
            "base_currency": "USDT",
            "initial_balance": "10000",
            "max_leverage": "2",
            "max_position_notional": "2000",
            "max_decision_loss": "100",
            "max_observed_drawdown": "500",
            "cost_model": {
                "model_id": "paper-cost-capability-v1",
                "maker_fee_bps": "1",
                "taker_fee_bps": "2",
                "market_impact_bps": "1",
                "funding_status": "UNKNOWN",
                "borrow_status": "NOT_APPLICABLE",
                "effective_from": None,
                "effective_to": None,
            },
        }
        self.attention_repository = FileAttentionRepository(self.root / "attention")
        self.attention_service = AttentionService(self.attention_repository)
        AgentSessionService(self.attention_repository).register(
            AgentRegistry(
                logical_agent_id=self.policy["logical_agent_id"],
                symbol=HYPE_OKX_INSTRUMENT_ID,
                generation=1,
                continuity_nonce="paper-context-continuity",
                physical_task_id="paper-context-physical-agent",
                status="ACTIVE",
                registered_at=_time(18),
            )
        )
        self.provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
        )

    def _open_paper_account(self):
        evidence = AdmittedAssetSlicePaperMarketEvidence(
            profiles=self.profiles,
            bindings=(
                PaperAssetEvidenceBinding(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                    cycle_ids=(self.cycle_id,),
                ),
            ),
        )
        spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=_time(20),
        )
        self.assertIsNotNone(spec)
        assert spec is not None
        PaperTradingService(
            self.ledger,
            cost_models=(PaperCostModelV1(**self.policy["cost_model"]),),
            market_evidence=evidence,
        ).open_account(
            account_id=self.policy["account_id"],
            account_mode="LINEAR_PERP",
            owner_logical_agent_id=self.policy["logical_agent_id"],
            owner_agent_generation=1,
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage=self.policy["max_leverage"],
            initial_balance=self.policy["initial_balance"],
            opened_at=_time(18),
            instrument_spec=spec,
        )
        return self.ledger.load_records(self.policy["account_id"])[-1]

    def test_unopened_account_is_explicit_and_digest_bound(self) -> None:
        context = self.provider.context(self.snapshot, self.snapshot_ref)

        self.assertEqual("ACCOUNT_NOT_OPENED", context["status"])
        self.assertEqual(0, context["ledger_head"]["revision"])
        self.assertIsNone(context["account"])
        self.assertIn(
            "MARKET", context["paper_action_space"]["standalone_command_types"]
        )
        self.assertEqual(
            ["LIMIT"],
            context["paper_action_space"]["protected_flat_entry"][
                "entry_command_types"
            ],
        )
        self.assertTrue(
            self.provider.verifies_context(
                self.snapshot, self.snapshot_ref, context
            )
        )
        altered = dict(context)
        altered["status"] = "OBSERVED"
        self.assertFalse(
            self.provider.verifies_context(
                self.snapshot, self.snapshot_ref, altered
            )
        )
        altered = dict(context)
        altered["paper_action_space"] = {
            **context["paper_action_space"],
            "standalone_command_types": ["LIMIT"],
        }
        altered.pop("paper_context_sha256")
        altered = self_digest(altered, "paper_context_sha256")
        self.assertFalse(
            self.provider.verifies_context(
                self.snapshot, self.snapshot_ref, altered
            )
        )
        review = self.provider.review_context(
            self.snapshot,
            self.snapshot_ref,
            review_cutoff_at=self.snapshot.sealed_at,
        )
        self.assertEqual(
            "NOT_EVALUATED",
            review["static_no_transition_evaluation"]["status"],
        )

    def test_episode_projection_counts_only_current_open_orders(self) -> None:
        intent = PaperExecutionIntentV1(
            intent_id="paper-context-open-order-count",
            execution_intent_request_sha256="1" * 64,
            decision_request_sha256="2" * 64,
            paper_context_sha256="3" * 64,
            ledger_head_record_sha256="4" * 64,
            decision_cycle_id="paper-context-open-order-count-cycle",
            decision_sha256="5" * 64,
            account_id=self.policy["account_id"],
            logical_agent_id=self.policy["logical_agent_id"],
            agent_generation=1,
            expected_account_version=4,
            symbol=HYPE_OKX_INSTRUMENT_ID,
            authored_at=_time(19),
            valid_until=_time(30),
            action="WAIT",
            episode_id="paper-context-open-order-count-episode",
            transition_id="paper-context-open-order-count-transition",
            tranche_id=None,
            role="CASH_FLAT",
            pre_state={"signed_quantity": "0"},
            target_state={"signed_quantity": "0"},
            position_delta={"signed_quantity_change": "0"},
            evidence_delta="No discriminating observation yet.",
            activation="Reassess on the declared next review.",
            hard_invalidation="A new sealed decision supersedes this wait.",
            risk_budget={
                "maximum_loss": "1",
                "notional_cap": "1",
                "max_observed_drawdown": "1",
            },
            command=None,
        )
        terminal_orders = (
            SimpleNamespace(state="FILLED"),
            SimpleNamespace(state="CANCELED"),
            SimpleNamespace(state="REJECTED"),
        )
        account = SimpleNamespace(positions=(), orders=terminal_orders)
        ledger_head = {"record_sha256": "6" * 64}
        order_history = [
            {"order_id": "historical-filled", "state": "FILLED"},
            {"order_id": "historical-canceled", "state": "CANCELED"},
            {"order_id": "historical-rejected", "state": "REJECTED"},
        ]

        no_open = self.provider._episode_exposure_projection(
            account=account,
            ledger_head=ledger_head,
            intents=(intent.to_dict(),),
            orders_and_fills={
                "open_orders": [],
                "order_history": order_history,
                "fills": [],
                "unresolved": [],
            },
        )
        with_open = self.provider._episode_exposure_projection(
            account=account,
            ledger_head=ledger_head,
            intents=(intent.to_dict(),),
            orders_and_fills={
                "open_orders": [
                    {"order_id": "current-open", "state": "OPEN"},
                    {
                        "order_id": "current-partially-filled",
                        "state": "PARTIALLY_FILLED",
                    },
                ],
                "order_history": order_history,
                "fills": [],
                "unresolved": [],
            },
        )

        self.assertEqual(0, no_open["open_order_count"])
        self.assertEqual(2, with_open["open_order_count"])
        self.assertEqual(3, len(order_history))
        self.assertEqual(3, len(account.orders))

    def test_opened_account_context_replays_frozen_prefix_after_later_event(self) -> None:
        evidence = AdmittedAssetSlicePaperMarketEvidence(
            profiles=self.profiles,
            bindings=(
                PaperAssetEvidenceBinding(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                    cycle_ids=(self.cycle_id,),
                ),
            ),
        )
        spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=_time(20),
        )
        self.assertIsNotNone(spec)
        assert spec is not None
        service = PaperTradingService(
            self.ledger,
            cost_models=(PaperCostModelV1(**self.policy["cost_model"]),),
            market_evidence=evidence,
        )
        service.open_account(
            account_id=self.policy["account_id"],
            account_mode="LINEAR_PERP",
            owner_logical_agent_id="hype-capability-agent",
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage=self.policy["max_leverage"],
            initial_balance=self.policy["initial_balance"],
            opened_at=_time(18),
            instrument_spec=spec,
        )
        context = self.provider.context(self.snapshot, self.snapshot_ref)

        self.assertEqual("OBSERVED", context["status"])
        self.assertEqual(1, context["ledger_head"]["revision"])
        self.assertEqual("10000", context["account"]["cash_balance"])
        self.assertEqual("43.125", context["valuation"]["mark"])
        self.assertEqual(
            "UNKNOWN_MARK_PREDATES_CURRENT_ACCOUNT_VERSION",
            context["valuation"]["status"],
        )

        self.ledger.append(
            account_id=self.policy["account_id"],
            expected_revision=1,
            event_id="future-account-event",
            event_type="MARKET_OBSERVED",
            occurred_at=_time(25),
            payload={
                "symbol": HYPE_OKX_INSTRUMENT_ID,
                "observed_at": _time(25),
                "available_at": _time(25),
                "source_sha256": "b" * 64,
                "market": {
                    "symbol": HYPE_OKX_INSTRUMENT_ID,
                    "observed_at": _time(25),
                    "available_at": _time(25),
                    "source_sha256": "b" * 64,
                    "granularity": "MARK",
                    "path_status": "ORDERED",
                    "bid": None,
                    "ask": None,
                    "last": None,
                    "high": None,
                    "low": None,
                    "mark": "44",
                    "available_quantity": None,
                },
            },
        )
        self.assertTrue(
            self.provider.verifies_context(
                self.snapshot, self.snapshot_ref, context
            )
        )
        rebuilt = self.provider.context(self.snapshot, self.snapshot_ref)
        self.assertEqual(context, rebuilt)

    def test_review_context_uses_outcome_fact_cutoff_and_decision_snapshot_mark(
        self,
    ) -> None:
        instrument_evidence = AdmittedAssetSlicePaperMarketEvidence(
            profiles=self.profiles,
            bindings=(
                PaperAssetEvidenceBinding(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                    cycle_ids=(self.cycle_id,),
                ),
            ),
        )
        spec = instrument_evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=_time(18),
        )
        self.assertIsNotNone(spec)
        assert spec is not None
        service = PaperTradingService(
            self.ledger,
            cost_models=(PaperCostModelV1(**self.policy["cost_model"]),),
            market_evidence=_ReviewMarketEvidence(instrument_evidence),
            decision_authority=_ReviewDecisionAuthority(),
            require_execution_intent=True,
        )
        service.open_account(
            account_id=self.policy["account_id"],
            account_mode="LINEAR_PERP",
            owner_logical_agent_id=self.policy["logical_agent_id"],
            owner_agent_generation=1,
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage=self.policy["max_leverage"],
            initial_balance=self.policy["initial_balance"],
            opened_at=_time(18),
            instrument_spec=spec,
        )
        decision_context = self.provider.context(self.snapshot, self.snapshot_ref)
        command = PaperCommandV1(
            command_id="review-same-cycle-command",
            account_id=self.policy["account_id"],
            logical_agent_id=self.policy["logical_agent_id"],
            agent_generation=1,
            decision_cycle_id=self.cycle_id,
            decision_sha256="9" * 64,
            expected_account_version=1,
            symbol=HYPE_OKX_INSTRUMENT_ID,
            command_type="LIMIT",
            side="BUY",
            quantity="1",
            limit_price="43.2",
            trigger_price=None,
            target_order_id=None,
            reduce_only=False,
            time_in_force="GTC",
            submitted_at=_time(21),
            expires_at=_time(1800),
            cost_model_id=self.policy["cost_model"]["model_id"],
        )
        stop = replace(
            command,
            command_id="review-same-cycle-stop",
            command_type="STOP_LOSS",
            side="SELL",
            limit_price=None,
            trigger_price="42",
            reduce_only=True,
        )
        target = replace(
            stop,
            command_id="review-same-cycle-target",
            command_type="TAKE_PROFIT",
            trigger_price="45",
        )
        bracket = PaperBracketV1(
            bracket_id=command.command_id,
            entry=command,
            protective_stop=stop,
            take_profits=(target,),
        )
        intent = PaperExecutionIntentV1(
            intent_id=command.command_id,
            execution_intent_request_sha256="1" * 64,
            decision_request_sha256="2" * 64,
            paper_context_sha256=decision_context["paper_context_sha256"],
            ledger_head_record_sha256=decision_context["ledger_head"][
                "record_sha256"
            ],
            decision_cycle_id=self.cycle_id,
            decision_sha256=command.decision_sha256,
            account_id=self.policy["account_id"],
            logical_agent_id=self.policy["logical_agent_id"],
            agent_generation=1,
            expected_account_version=1,
            symbol=HYPE_OKX_INSTRUMENT_ID,
            authored_at=_time(21),
            valid_until=_time(1800),
            action="OPEN",
            episode_id="review-same-cycle-episode",
            transition_id="review-same-cycle-transition",
            tranche_id="review-same-cycle-tranche",
            role="CORE",
            pre_state={"signed_quantity": "0"},
            target_state={"signed_quantity": "1"},
            position_delta={"signed_quantity_change": "1"},
            evidence_delta="The Agent selected this local paper entry.",
            activation="Submit only this exact bounded paper command.",
            hard_invalidation="Do not submit after the declared validity window.",
            risk_budget={
                "maximum_loss": "100",
                "notional_cap": "2000",
                "max_observed_drawdown": "500",
            },
            command=command,
            bracket=bracket,
        )
        submitted = service.submit_intent(intent, received_at=_time(22))

        behavior_plan_ref = ArtifactRef(
            artifact_type="BehaviorPlan",
            artifact_id=f"{self.cycle_id}.plan",
            path="artifacts/BehaviorPlan.json",
            size_bytes=1,
            sha256="6" * 64,
        )
        behavior_plan_binding = (
            f"{behavior_plan_ref.artifact_id}:{behavior_plan_ref.sha256}"
        )
        attention = AttentionRequest(
            request_id="review-same-cycle-attention",
            logical_agent_id=self.policy["logical_agent_id"],
            agent_generation=1,
            continuity_nonce="paper-context-continuity",
            symbol=HYPE_OKX_INSTRUMENT_ID,
            mode="WAKE_AFTER",
            issued_at=_time(23),
            continue_until=None,
            earliest_wake_at=_time(30),
            latest_useful_at=_time(40),
            reason_summary="Review the same-cycle fill and modeled costs.",
            requested_focus="Compare exact order, fill, position, and cost facts.",
            hypothesis_or_episode_ref=behavior_plan_binding,
            position_and_open_order_ref=self.policy["account_id"],
            data_cursor=decision_context["data_evidence"]["data_cursor"],
            supersedes=None,
        )
        self.attention_service.submit_request(
            attention, received_at=_time(23), expected_revision=1
        )
        later_attention = replace(
            attention,
            request_id="review-later-cycle-attention",
            issued_at=_time(26),
            earliest_wake_at=_time(31),
            latest_useful_at=_time(50),
            hypothesis_or_episode_ref=f"later-cycle.plan:{'7' * 64}",
            data_cursor="later-cycle-data-cursor",
            supersedes=attention.request_id,
        )
        self.attention_service.submit_request(
            later_attention, received_at=_time(26), expected_revision=2
        )
        filled = service.observe(
            account_id=self.policy["account_id"],
            expected_account_version=submitted.version,
            market=PaperMarketSliceV1(
                symbol=HYPE_OKX_INSTRUMENT_ID,
                observed_at=_time(24),
                available_at=_time(25),
                source_sha256="f" * 64,
                granularity="QUOTE",
                path_status="ORDERED",
                bid="43",
                ask="43.1",
                last="43.05",
                mark="43.05",
                available_quantity="10",
            ),
        )
        head_at_review = self.ledger.load_records(self.policy["account_id"])[-1]
        self.assertEqual(filled.version, head_at_review.revision)
        path_raw_ref = ArtifactRef(
            artifact_type="RawCapture",
            artifact_id="review-static-path-raw",
            path="raw/review-static-path.json",
            size_bytes=1,
            sha256="7" * 64,
        )
        ordered_path = {
            "schema_id": "agent_trade_emotion_v332_ordered_outcome_path",
            "schema_version": "1.0.0",
            "status": "ORDERED",
            "path_start_at": _time(21),
            "path_end_at": _time(2700),
            "interval": "15m",
            "intrabar_order": "UNRESOLVED_WITHIN_BAR",
            "points": [
                {
                    "sequence_index": 0,
                    "opened_at": _time(900),
                    "closed_at": _time(1800),
                    "open": "43.3",
                    "high": "44",
                    "low": "43",
                    "close": "43.8",
                    "confirmed_closed": True,
                    "available_at": _time(1801),
                    "raw_sha256": path_raw_ref.sha256,
                },
                {
                    "sequence_index": 1,
                    "opened_at": _time(1800),
                    "closed_at": _time(2700),
                    "open": "43.8",
                    "high": "44.2",
                    "low": "43.5",
                    "close": "44",
                    "confirmed_closed": True,
                    "available_at": _time(2701),
                    "raw_sha256": path_raw_ref.sha256,
                },
            ],
            "coverage": {
                "expected_point_count": 2,
                "observed_point_count": 2,
                "gap_count": 0,
                "covers_all_closed_intervals": True,
            },
            "missing_reason": None,
            "source_health": [],
        }
        outcome = Outcome(
            outcome_id=f"{self.cycle_id}.outcome",
            cycle_id=self.cycle_id,
            behavior_plan_ref=behavior_plan_ref,
            due_at=_time(2700),
            tolerance_seconds=60,
            observed_at=_time(2701),
            sealed_at=_time(2702),
            terminal_status="TYPED_MISSING",
            endpoint_observation=None,
            typed_missing="ENDPOINT_UNAVAILABLE_WITH_ORDERED_PATH",
            path_observations=ordered_path,
            raw_refs=(path_raw_ref,),
            theory_identity=V332_THEORY_IDENTITY,
        )
        self.ledger.append(
            account_id=self.policy["account_id"],
            expected_revision=head_at_review.revision,
            event_id="review-future-market-fact",
            event_type="MARKET_OBSERVED",
            occurred_at=_time(2805),
            payload={
                "symbol": HYPE_OKX_INSTRUMENT_ID,
                "observed_at": _time(2805),
                "available_at": _time(2805),
                "source_sha256": "8" * 64,
                "market": PaperMarketSliceV1(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    observed_at=_time(2805),
                    available_at=_time(2805),
                    source_sha256="8" * 64,
                    granularity="MARK",
                    path_status="ORDERED",
                    mark="99",
                ).to_dict(),
            },
        )
        review_provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
            cycle_repository=_CurrentOutcomeRepository(
                cycle_id=self.cycle_id, outcome=outcome
            ),
        )
        review = review_provider.review_context(
            self.snapshot,
            self.snapshot_ref,
            review_cutoff_at=outcome.sealed_at,
        )

        self.assertEqual(outcome.sealed_at, review["paper_fact_cutoff_at"])
        self.assertEqual(
            self.snapshot.sealed_at,
            review["data_evidence"]["market_fact_cutoff_at"],
        )
        self.assertEqual(head_at_review.revision, review["ledger_head"]["revision"])
        self.assertEqual([intent.to_dict()], review["same_cycle_execution_intents"])
        self.assertEqual(attention.to_dict(), review["same_cycle_attention"]["request"])
        self.assertEqual(
            "SUPERSEDED", review["same_cycle_attention"]["request_status"]
        )
        self.assertEqual(
            later_attention.request_id,
            review["same_cycle_attention"]["active_request_id"],
        )
        self.assertEqual(
            3,
            len(
                self.attention_repository.replay(
                    self.policy["logical_agent_id"]
                )
            ),
        )
        self.assertIn(
            command.command_id,
            {
                item["command_id"]
                for item in review["orders_and_fills"]["order_history"]
            },
        )
        self.assertEqual(1, len(review["orders_and_fills"]["fills"]))
        self.assertEqual(1, review["cost_effect"]["fill_count"])
        self.assertEqual("43.125", review["valuation"]["mark"])
        self.assertEqual(
            "DECISION_SNAPSHOT_MARK_ONLY",
            review["valuation"]["mark_basis"]["status"],
        )
        static_evaluation = review["static_no_transition_evaluation"]
        self.assertEqual(
            "OBSERVED", static_evaluation["status"], static_evaluation
        )
        self.assertEqual(1, len(static_evaluation["results"]))
        self.assertEqual(
            "IDEALIZED_STATIC_REFERENCE",
            static_evaluation["results"][0]["static_endpoint"]["status"],
        )
        self.assertTrue(
            review_provider.verifies_review_context(
                self.snapshot,
                self.snapshot_ref,
                review,
                review_cutoff_at=outcome.sealed_at,
            )
        )
        censored_provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
            cycle_repository=_CurrentOutcomeRepository(
                cycle_id=self.cycle_id,
                outcome=replace(
                    outcome,
                    path_observations=_censored_outcome_path(
                        path_start_at=_time(21),
                        path_end_at=_time(2700),
                        expected_point_count=2,
                    ),
                ),
            ),
        )
        censored = censored_provider.review_context(
            self.snapshot,
            self.snapshot_ref,
            review_cutoff_at=outcome.sealed_at,
        )
        self.assertEqual(
            "CENSORED",
            censored["static_no_transition_evaluation"]["status"],
        )

    def test_latest_complete_decision_and_review_are_included_verbatim(self) -> None:
        self._open_paper_account()
        complete_artifacts, _ = _prior_artifacts(complete=True)
        provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
            cycle_repository=_PriorCycleRepository(
                stage="COMPLETE", artifacts=complete_artifacts
            ),
        )

        context = provider.context(self.snapshot, self.snapshot_ref)

        self.assertEqual([], context["prior_execution_intents"])
        self.assertIsNone(context["latest_transition"])
        self.assertEqual(
            "PRIOR_COMPLETE_OBSERVED", context["prior_decision_status"]
        )
        prior = context["latest_prior_decision"]
        self.assertEqual("prior-wait-cycle", prior["decision_cycle_id"])
        self.assertIsNone(prior["execution_intent_sha256"])
        self.assertEqual(
            "NON_AUTHORITATIVE_CONTINUITY_CONTEXT", prior["authority"]
        )
        self.assertEqual(
            "LATEST_COMPLETE_INCLUDED_BOUNDED", prior["retrieval_policy"]
        )
        self.assertTrue(prior["agent_decision_body"]["included_in_context"])
        self.assertTrue(prior["agent_review_body"]["included_in_context"])
        self.assertEqual(
            complete_artifacts["HypothesisRecord"]["agent_decision_text"],
            prior["agent_decision_body"]["verbatim_text"],
        )
        self.assertEqual(
            complete_artifacts["Review"]["agent_review_text"],
            prior["agent_review_body"]["verbatim_text"],
        )
        self.assertEqual(
            complete_artifacts["Review"]["agent_review_sha256"],
            prior["agent_review_body"]["sha256"],
        )
        self.assertEqual(
            prior["artifact_refs"]["Review"],
            prior["agent_review_body"]["artifact_ref"],
        )
        self.assertTrue(
            provider.verifies_context(self.snapshot, self.snapshot_ref, context)
        )

    def test_newer_complete_review_reference_is_not_hidden_by_older_intent(self) -> None:
        head = self._open_paper_account()
        older_artifacts, older_decision_sha256 = _prior_artifacts(
            complete=True,
            cycle_id="older-intent-cycle",
            reviewed_at="2026-08-13T00:10:03+00:00",
            review_sentinel="OLDER_REVIEW_MUST_NOT_WIN",
        )
        newer_artifacts, _ = _prior_artifacts(
            complete=True,
            cycle_id="newer-complete-cycle",
            reviewed_at="2026-08-13T00:11:03+00:00",
            review_sentinel="NEWER_REVIEW_MUST_WIN",
        )
        older_intent = PaperExecutionIntentV1(
            intent_id="older-cycle-wait",
            execution_intent_request_sha256="1" * 64,
            decision_request_sha256="2" * 64,
            paper_context_sha256="3" * 64,
            ledger_head_record_sha256=head.record_sha256,
            decision_cycle_id="older-intent-cycle",
            decision_sha256=older_decision_sha256,
            account_id=self.policy["account_id"],
            logical_agent_id=self.policy["logical_agent_id"],
            agent_generation=1,
            expected_account_version=head.revision,
            symbol=HYPE_OKX_INSTRUMENT_ID,
            authored_at=_time(19),
            valid_until=_time(30),
            action="WAIT",
            episode_id="older-episode",
            transition_id="older-transition",
            tranche_id=None,
            role="CASH_FLAT",
            pre_state={"signed_quantity": "0"},
            target_state={"signed_quantity": "0"},
            position_delta={"signed_quantity_change": "0"},
            evidence_delta="Older cycle evidence.",
            activation="Wait for fresh evidence.",
            hard_invalidation="A later sealed decision supersedes it.",
            risk_budget={
                "maximum_loss": "1",
                "notional_cap": "1",
                "max_observed_drawdown": "1",
            },
            command=None,
        )
        self.ledger.append(
            account_id=self.policy["account_id"],
            expected_revision=head.revision,
            event_id="older-cycle-wait-recorded",
            event_type="INTENT_RECORDED",
            occurred_at=_time(19),
            payload={"execution_intent": older_intent.to_dict()},
        )
        provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
            cycle_repository=_PriorCyclesRepository(
                {
                    "older-intent-cycle": ("COMPLETE", older_artifacts),
                    "newer-complete-cycle": ("COMPLETE", newer_artifacts),
                }
            ),
        )

        context = provider.context(self.snapshot, self.snapshot_ref)

        self.assertIsNone(context["latest_transition"])
        prior = context["latest_prior_decision"]
        self.assertEqual("newer-complete-cycle", prior["decision_cycle_id"])
        self.assertIsNone(prior["execution_intent_sha256"])
        self.assertEqual(
            newer_artifacts["Review"]["agent_review_sha256"],
            prior["agent_review_body"]["sha256"],
        )
        self.assertEqual(
            newer_artifacts["Review"]["agent_review_text"],
            prior["agent_review_body"]["verbatim_text"],
        )
        self.assertNotIn(
            "OLDER_REVIEW_MUST_NOT_WIN",
            prior["agent_review_body"]["verbatim_text"],
        )

    def test_future_complete_review_is_excluded_by_current_pit_cutoff(self) -> None:
        self._open_paper_account()
        eligible_artifacts, _ = _prior_artifacts(
            complete=True,
            cycle_id="eligible-complete-cycle",
            reviewed_at="2026-08-13T00:10:03+00:00",
            review_sentinel="ELIGIBLE_REVIEW_MUST_WIN",
        )
        future_artifacts, _ = _prior_artifacts(
            complete=True,
            cycle_id="future-complete-cycle",
            reviewed_at="2026-08-13T13:00:00+00:00",
            review_sentinel="FUTURE_REVIEW_MUST_NOT_APPEAR",
        )
        provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
            cycle_repository=_PriorCyclesRepository(
                {
                    "eligible-complete-cycle": ("COMPLETE", eligible_artifacts),
                    "future-complete-cycle": ("COMPLETE", future_artifacts),
                }
            ),
        )

        context = provider.context(self.snapshot, self.snapshot_ref)

        prior = context["latest_prior_decision"]
        self.assertEqual("eligible-complete-cycle", prior["decision_cycle_id"])
        self.assertIn(
            "ELIGIBLE_REVIEW_MUST_WIN",
            prior["agent_review_body"]["verbatim_text"],
        )
        self.assertNotIn(
            "FUTURE_REVIEW_MUST_NOT_APPEAR",
            prior["agent_review_body"]["verbatim_text"],
        )

    def test_flat_account_does_not_replay_terminal_intent_text(self) -> None:
        pending_artifacts, prior_decision_sha256 = _prior_artifacts(complete=False)
        evidence = AdmittedAssetSlicePaperMarketEvidence(
            profiles=self.profiles,
            bindings=(
                PaperAssetEvidenceBinding(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                    cycle_ids=(self.cycle_id,),
                ),
            ),
        )
        spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID, "LINEAR_PERP", available_by=_time(18)
        )
        self.assertIsNotNone(spec)
        PaperTradingService(
            self.ledger,
            cost_models=(PaperCostModelV1(**self.policy["cost_model"]),),
            market_evidence=evidence,
        ).open_account(
            account_id=self.policy["account_id"],
            account_mode="LINEAR_PERP",
            owner_logical_agent_id=self.policy["logical_agent_id"],
            owner_agent_generation=1,
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage=self.policy["max_leverage"],
            initial_balance=self.policy["initial_balance"],
            opened_at=_time(18),
            instrument_spec=spec,
        )
        head = self.ledger.load_records(self.policy["account_id"])[-1]
        wait = PaperExecutionIntentV1(
            intent_id="paper-context-wait",
            execution_intent_request_sha256="1" * 64,
            decision_request_sha256="2" * 64,
            paper_context_sha256="3" * 64,
            ledger_head_record_sha256=head.record_sha256,
            decision_cycle_id="prior-wait-cycle",
            decision_sha256=prior_decision_sha256,
            account_id=self.policy["account_id"],
            logical_agent_id=self.policy["logical_agent_id"],
            agent_generation=1,
            expected_account_version=1,
            symbol=HYPE_OKX_INSTRUMENT_ID,
            authored_at=_time(19),
            valid_until=_time(30),
            action="WAIT",
            episode_id="paper-context-episode",
            transition_id="paper-context-wait-transition",
            tranche_id=None,
            role="CASH_FLAT",
            pre_state={"signed_quantity": "0"},
            target_state={"signed_quantity": "0"},
            position_delta={"signed_quantity_change": "0"},
            evidence_delta="No discriminating observation yet.",
            activation="Reassess on the declared next review.",
            hard_invalidation="A new sealed decision supersedes this wait.",
            risk_budget={
                "maximum_loss": "1",
                "notional_cap": "1",
                "max_observed_drawdown": "1",
            },
            command=None,
        )
        later_episode = replace(
            wait,
            intent_id="paper-context-later-episode",
            decision_cycle_id="paper-context-later-cycle",
            episode_id="paper-context-later-episode",
            transition_id="paper-context-later-transition",
        )
        intent_history = [wait.to_dict(), later_episode.to_dict()]
        no_active_orders = {"open_orders": [], "unresolved": []}
        self.assertEqual(
            [],
            self.provider._agent_facing_prior_intents(
                account=SimpleNamespace(
                    positions=(SimpleNamespace(quantity="0"),)
                ),
                intents=intent_history,
                orders_and_fills=no_active_orders,
            ),
        )
        self.assertEqual(
            intent_history,
            self.provider._agent_facing_prior_intents(
                account=SimpleNamespace(
                    positions=(SimpleNamespace(quantity="1"),)
                ),
                intents=intent_history,
                orders_and_fills=no_active_orders,
            ),
        )
        self.assertEqual(
            intent_history,
            self.provider._agent_facing_prior_intents(
                account=SimpleNamespace(positions=()),
                intents=intent_history,
                orders_and_fills={
                    "open_orders": [{"order_id": "still-open"}],
                    "unresolved": [],
                },
            ),
        )
        self.ledger.append(
            account_id=self.policy["account_id"],
            expected_revision=1,
            event_id="paper-context-wait-recorded",
            event_type="INTENT_RECORDED",
            occurred_at=_time(19),
            payload={"execution_intent": wait.to_dict()},
        )

        context = self.provider.context(self.snapshot, self.snapshot_ref)

        self.assertEqual([], context["prior_execution_intents"])
        self.assertIsNone(context["latest_transition"])
        self.assertEqual(
            "UNAVAILABLE_CYCLE_REPOSITORY", context["prior_decision_status"]
        )
        self.assertIsNone(context["latest_prior_decision"])
        self.assertEqual(
            "NO_PRIOR_INTENT",
            context["episode_exposure_projection"]["status"],
        )
        self.assertEqual({}, context["episode_exposure_projection"]["source_refs"])
        self.assertEqual((), tuple(context["account"]["orders"]))

        pending_provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
            cycle_repository=_PriorCycleRepository(
                stage="BEHAVIOR_PLANNED", artifacts=pending_artifacts
            ),
        )
        pending = pending_provider.context(self.snapshot, self.snapshot_ref)
        self.assertEqual(
            "PRIOR_OUTCOME_REVIEW_PENDING", pending["prior_decision_status"]
        )
        self.assertIsNone(pending["latest_prior_decision"])

        complete_artifacts, _ = _prior_artifacts(complete=True)
        attention_request = AttentionRequest(
            request_id="paper-context-attention",
            logical_agent_id=self.policy["logical_agent_id"],
            agent_generation=1,
            continuity_nonce="paper-context-continuity",
            symbol=HYPE_OKX_INSTRUMENT_ID,
            mode="WAKE_AFTER",
            issued_at=_time(19),
            continue_until=None,
            earliest_wake_at=_time(20),
            latest_useful_at=_time(30),
            reason_summary="WAIT remains unresolved; preserve a bounded next review.",
            requested_focus="Compare activation, opportunity cost, and fresh geometry.",
            hypothesis_or_episode_ref="paper-context-episode",
            position_and_open_order_ref=self.policy["account_id"],
            data_cursor="paper-context-cursor-001",
        )
        self.attention_service.submit_request(
            attention_request,
            received_at=_time(19),
            expected_revision=1,
        )
        complete_provider = PaperDecisionContextProvider(
            ledger=self.ledger,
            profiles=self.profiles,
            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
            account_id=self.policy["account_id"],
            paper_account_policy=self.policy,
            experiment_policy_sha256="a" * 64,
            attention_repository=self.attention_repository,
            attention_service=self.attention_service,
            cycle_repository=_PriorCycleRepository(
                stage="COMPLETE", artifacts=complete_artifacts
            ),
        )
        complete = complete_provider.context(self.snapshot, self.snapshot_ref)
        self.assertEqual(
            "PRIOR_COMPLETE_OBSERVED", complete["prior_decision_status"]
        )
        prior = complete["latest_prior_decision"]
        self.assertEqual("prior-wait-cycle", prior["decision_cycle_id"])
        self.assertEqual(wait.intent_sha256, prior["execution_intent_sha256"])
        self.assertEqual(
            {"HypothesisRecord", "BehaviorPlan", "Outcome", "Review"},
            set(prior["artifact_refs"]),
        )
        self.assertEqual("1.5.0", complete["schema_version"])
        self.assertEqual(
            "NON_AUTHORITATIVE_CONTINUITY_CONTEXT", prior["authority"]
        )
        self.assertEqual(
            "LATEST_COMPLETE_INCLUDED_BOUNDED", prior["retrieval_policy"]
        )
        self.assertTrue(prior["agent_decision_body"]["included_in_context"])
        self.assertTrue(prior["agent_review_body"]["included_in_context"])
        self.assertEqual(
            complete_artifacts["HypothesisRecord"]["agent_decision_text"],
            prior["agent_decision_body"]["verbatim_text"],
        )
        self.assertEqual(
            complete_artifacts["Review"]["agent_review_text"],
            prior["agent_review_body"]["verbatim_text"],
        )
        self.assertEqual(
            complete_artifacts["Review"]["agent_review_sha256"],
            prior["agent_review_body"]["sha256"],
        )
        continuity = complete["continuity_projection"]
        self.assertEqual(
            [],
            continuity["terminal_non_execution_suffix"]["actions"],
        )
        self.assertEqual(
            attention_request.to_dict(),
            continuity["latest_attention_request"]["request"],
        )
        self.assertEqual(
            attention_request.agent_owned_sha256,
            continuity["latest_attention_request"]["request_sha256"],
        )
        self.assertEqual(
            {"UNRESOLVED_AGENT_JUDGMENT"},
            {
                item["status"]
                for item in continuity["subjective_assessments"].values()
            },
        )
        self.assertTrue(
            complete_provider.verifies_context(
                self.snapshot, self.snapshot_ref, complete
            )
        )
        complete_artifacts["Review"]["agent_review_text"] = "tampered review\n"
        self.assertFalse(
            complete_provider.verifies_context(
                self.snapshot, self.snapshot_ref, complete
            )
        )

        def append_non_execution(
            source: PaperExecutionIntentV1,
            *,
            intent_id: str,
            action: str,
            episode_id: str,
            transition_id: str,
        ) -> PaperExecutionIntentV1:
            current_head = self.ledger.load_records(self.policy["account_id"])[-1]
            candidate = replace(
                source,
                intent_id=intent_id,
                ledger_head_record_sha256=current_head.record_sha256,
                expected_account_version=current_head.revision,
                decision_cycle_id=intent_id,
                action=action,
                episode_id=episode_id,
                transition_id=transition_id,
                position_delta={"signed_quantity_change": "0"},
            )
            self.ledger.append(
                account_id=self.policy["account_id"],
                expected_revision=current_head.revision,
                event_id=f"{intent_id}-recorded",
                event_type="INTENT_RECORDED",
                occurred_at=_time(19),
                payload={"execution_intent": candidate.to_dict()},
            )
            return candidate

        hold = append_non_execution(
            wait,
            intent_id="paper-context-hold",
            action="HOLD",
            episode_id="paper-context-episode",
            transition_id="paper-context-hold-transition",
        )
        suffix = self.provider.context(self.snapshot, self.snapshot_ref)[
            "continuity_projection"
        ]["terminal_non_execution_suffix"]
        self.assertEqual([], suffix["actions"])
        conditional = append_non_execution(
            hold,
            intent_id="paper-context-conditional",
            action="CONDITIONAL",
            episode_id="paper-context-episode",
            transition_id="paper-context-conditional-transition",
        )
        suffix = self.provider.context(self.snapshot, self.snapshot_ref)[
            "continuity_projection"
        ]["terminal_non_execution_suffix"]
        self.assertEqual(0, suffix["length"])
        append_non_execution(
            conditional,
            intent_id="paper-context-watch",
            action="WATCH",
            episode_id="paper-context-episode-2",
            transition_id="paper-context-watch-transition",
        )
        suffix = self.provider.context(self.snapshot, self.snapshot_ref)[
            "continuity_projection"
        ]["terminal_non_execution_suffix"]
        self.assertEqual([], suffix["actions"])
        self.assertIsNone(suffix["episode_id"])


if __name__ == "__main__":
    unittest.main()
