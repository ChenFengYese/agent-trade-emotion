"""Canonical, deterministic validation scenarios from contract section 19.2.

The harness is deliberately offline and side-effect free.  A scenario PASS
means that the observed domain/application predicate exactly matched the
scenario's frozen expected outcome and code.  It is not a profitability,
prediction, calibration, paper, or live-trading claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Callable

from ..domain.common import DomainError, DomainResult, ReducerStatus
from ..domain.contracts.canonical import canonical_digest
from ..domain.deliberation import (
    AgentSelection,
    CandidateBundle,
    CandidateBundleSet,
    CandidateDecisionMetrics,
    DecisionContext,
    ProposedActionPlan,
    make_decision_criterion_policy,
    make_no_action_plan,
    select_by_frozen_policy,
)
from ..domain.evaluation import (
    CoherenceVerdict,
    ContinuationBranch,
    CounterfactualTier,
    CoverageVerdict,
    DecimalInterval,
    ForecastCoherenceReceipt,
    OpportunityStatus,
    PathKind,
    ProbabilityStatus as EvaluationProbabilityStatus,
    ProbabilityUse,
    ProbabilityUseAuthorization,
    RecedingHorizonPlan,
    assess_recursive_feasibility,
    authorize_current_plan_action,
    authorize_probability_use,
    calculate_linear_pnl_interval,
    create_empty_e0_calibration_registry,
    issue_ex_ante_opportunity_cost,
    make_stress_scenario_set,
    validate_e0_calibration_registry,
)
from ..domain.evidence import (
    EvidenceQuality,
    EvidenceRecord,
    EvidenceScope,
    PhysicalExistence,
    SignalClass,
    admit_evidence,
)
from ..domain.geometry import (
    AnalysisGeometry,
    AnalysisGeometryStatus,
    ExecutionBarrierStatus,
    GeometryAggregate,
    PositionSide,
    ProbabilityStatus as GeometryProbabilityStatus,
    ProtectionBarrier,
    ProtectionRevision,
    revise_protection,
)
from ..domain.governance import (
    FeasibleActionSet,
    GovernanceAssessmentReceipt,
    GovernanceVerdict,
)
from ..domain.matching import (
    BarrierOrder,
    BarrierType,
    ClosedBar,
    MatchingPolicy,
    OrderSide,
    match_closed_bar,
)
from ..domain.policy import ActionIntent, GeometryOperation, ProtectiveActionType
from ..domain.position import (
    GateVerdict,
    LotRole,
    StageEvaluation,
    StageKind,
    StageSpec,
    StageState,
    StageStatus,
    SupervisionContract,
    SupervisionMode,
    SupervisionWindow,
    assess_supervision,
    reduce_stage,
)
from ..domain.reentry import (
    EligibilityVerdict,
    ReentryEvaluation,
    ReentryStatus,
    open_reentry_contract,
    reduce_reentry,
)
from ..domain.strategic import (
    CrossTimescaleLease,
    ExposureStatus,
    StrategicEpisode,
    StrategicStatus,
    StrategicTransition,
    reduce_strategic_episode,
    validate_fast_action,
)
from ..domain.time_authority import ReviewClock
from .bootstrap import BootstrapError, build_cluster_manifest
from .commit import (
    AggregateMutation,
    CommitContext,
    ReplayOutcome,
    commit_e0_session,
)


FROZEN_AT = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
SNDK_COHORT = "SNDK_SEEN_FUNCTIONAL"
INDEPENDENT_COHORT = "BTCUSDT_INDEPENDENT_FROZEN_SYNTHETIC"
DATASET_TYPE = "SYNTHETIC_CONTRACT_FIXTURE"


class PredicateOutcome(StrEnum):
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    NO_CHANGE = "NO_CHANGE"


class ScenarioValidationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PredicateObservation:
    outcome: PredicateOutcome
    code: str
    evidence_digest: str


ScenarioExecutor = Callable[[], PredicateObservation]


@dataclass(frozen=True, slots=True)
class CanonicalScenarioDefinition:
    scenario_id: str
    ordinal: int
    title: str
    cohort_id: str
    dataset_type: str
    predicate_id: str
    expected_outcome: PredicateOutcome
    expected_code: str
    executor: ScenarioExecutor


@dataclass(frozen=True, slots=True)
class CanonicalScenarioResult:
    scenario_id: str
    title: str
    cohort_id: str
    predicate_id: str
    expected_outcome: PredicateOutcome
    expected_code: str
    observed_outcome: PredicateOutcome
    observed_code: str
    status: ScenarioValidationStatus
    evidence_digest: str
    result_digest: str


@dataclass(frozen=True, slots=True)
class CanonicalScenarioReport:
    contract_section: str
    registry_digest: str
    results: tuple[CanonicalScenarioResult, ...]
    pass_count: int
    fail_count: int
    unknown_count: int
    report_digest: str


def _observation(
    outcome: PredicateOutcome, code: str, evidence: object
) -> PredicateObservation:
    return PredicateObservation(outcome, code, canonical_digest(evidence))


def _domain_observation(
    result: DomainResult,
    *,
    applied_code: str,
    applied_evidence: object | None = None,
) -> PredicateObservation:
    if result.status is ReducerStatus.APPLIED:
        return _observation(
            PredicateOutcome.APPLIED,
            applied_code,
            applied_evidence
            if applied_evidence is not None
            else {
                "event": result.evaluated_event_id,
                "value_type": type(result.value).__name__,
            },
        )
    if result.status is ReducerStatus.NO_CHANGE:
        return _observation(
            PredicateOutcome.NO_CHANGE,
            result.evaluated_event_id or "NO_CHANGE",
            {"event": result.evaluated_event_id},
        )
    assert result.error is not None
    return _observation(
        (
            PredicateOutcome.UNKNOWN
            if result.status is ReducerStatus.UNKNOWN
            else PredicateOutcome.REJECTED
        ),
        result.error.code,
        {
            "category": result.error.category,
            "retryability": result.error.retryability,
            "code": result.error.code,
        },
    )


def _path_payoff_observation(
    *,
    code: str,
    terminal_lower: str,
    terminal_upper: str,
    required_relation: str,
) -> PredicateObservation:
    pnl = calculate_linear_pnl_interval(
        side="LONG",
        entry_price=Decimal("100"),
        terminal_price=DecimalInterval(
            Decimal(terminal_lower), Decimal(terminal_upper), "PRICE"
        ),
        quantity=Decimal("1"),
        fees=DecimalInterval(Decimal("0.1"), Decimal("0.2"), "ACCOUNT_USD"),
        slippage=DecimalInterval(
            Decimal("0.1"), Decimal("0.3"), "ACCOUNT_USD"
        ),
        funding=DecimalInterval(Decimal("0"), Decimal("0.1"), "ACCOUNT_USD"),
        account_unit_ref="ACCOUNT_USD",
    )
    relations = {
        "POSITIVE": pnl.lower > 0,
        "NEGATIVE": pnl.upper < 0,
        "STRADDLES_ZERO": pnl.lower < 0 < pnl.upper,
        "BOUNDED_RANGE": pnl.lower >= Decimal("-3")
        and pnl.upper <= Decimal("3"),
        "WIDE_PATH_DEPENDENCE": pnl.lower <= Decimal("-15")
        and pnl.upper >= Decimal("15"),
    }
    if not relations[required_relation]:
        return _observation(
            PredicateOutcome.REJECTED,
            "PATH_PAYOFF_INVARIANT_FAILED",
            {
                "relation": required_relation,
                "lower": pnl.lower,
                "upper": pnl.upper,
            },
        )
    return _observation(
        PredicateOutcome.APPLIED,
        code,
        {
            "relation": required_relation,
            "lower": pnl.lower,
            "upper": pnl.upper,
        },
    )


def _matching_policy() -> MatchingPolicy:
    return MatchingPolicy(
        policy_id="scenario-matching-policy",
        instrument_id="BTCUSDT",
        venue_id="FROZEN_TEST",
        price_tick=Decimal("1"),
        quantity_step=Decimal("1"),
        contract_multiplier=Decimal("1"),
        fee_rate=Decimal("0.001"),
        adverse_slippage_bps=Decimal("0"),
    )


def _bar(
    *,
    bar_id: str,
    start: datetime,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> ClosedBar:
    close_time = start + timedelta(hours=1)
    return ClosedBar(
        bar_id=bar_id,
        instrument_id="BTCUSDT",
        venue_id="FROZEN_TEST",
        open_time=start,
        close_time=close_time,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
        observed_at=close_time,
        available_at=close_time + timedelta(seconds=1),
        ingested_at=close_time + timedelta(seconds=2),
        source_committed_at=close_time + timedelta(seconds=3),
        source_commit_receipt_valid=True,
        lineage_digest_valid=True,
    )


def _bar_cutoff(bar: ClosedBar) -> datetime:
    return bar.source_committed_at


def _order(
    *,
    order_id: str,
    barrier_type: BarrierType,
    side: OrderSide,
    active_from: datetime,
    trigger: str | None = None,
    limit: str | None = None,
    lot_id: str | None = "lot:scenario",
    stage_id: str | None = None,
) -> BarrierOrder:
    is_entry = barrier_type in {
        BarrierType.ENTRY_STOP_MARKET,
        BarrierType.ENTRY_LIMIT,
    }
    return BarrierOrder(
        order_id=order_id,
        instrument_id="BTCUSDT",
        venue_id="FROZEN_TEST",
        barrier_type=barrier_type,
        side=side,
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        trigger_price=None if trigger is None else Decimal(trigger),
        limit_price=None if limit is None else Decimal(limit),
        reduce_only=not is_entry,
        active_from=active_from - timedelta(hours=1),
        active_until=active_from + timedelta(hours=3),
        protection_priority=0,
        lot_id=None if is_entry else lot_id,
        stage_id="stage:scenario" if is_entry else stage_id,
        geometry_id="geometry:scenario",
    )


def _scenario_07() -> PredicateObservation:
    bar = _bar(
        bar_id="bar:gap-stop",
        start=FROZEN_AT,
        open_="93",
        high="96",
        low="90",
        close="92",
    )
    result = match_closed_bar(
        bar=bar,
        orders=(
            _order(
                order_id="stop:gap",
                barrier_type=BarrierType.STOP_MARKET,
                side=OrderSide.SELL,
                active_from=FROZEN_AT,
                trigger="95",
            ),
        ),
        policy=_matching_policy(),
        decision_cutoff=_bar_cutoff(bar),
    )
    if (
        result.status is ReducerStatus.APPLIED
        and result.value is not None
        and result.value.fill_price == Decimal("93")
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "MATCHING_GAP_STOP_CONSERVATIVE",
            {
                "fill_price": result.value.fill_price,
                "bar_id": result.value.bar_id,
            },
        )
    return _domain_observation(result, applied_code="MATCHING_GAP_STOP_INVALID")


def _stage_spec(kind: StageKind, index: int) -> StageSpec:
    return StageSpec(
        stage_id=f"stage:{kind.value.lower()}",
        plan_id="staged-plan:scenario",
        stage_index=index,
        stage_kind=kind,
        lot_role=LotRole.CORE if index == 0 else LotRole.TACTICAL,
        predecessor_stage_id=None if index == 0 else "stage:prior",
        expiry=FROZEN_AT + timedelta(hours=8),
        maximum_retries=1,
        frozen_before_first_fill=True,
    )


def _eligibility(
    requested: StageStatus,
    **overrides: object,
) -> StageEvaluation:
    values: dict[str, object] = {
        "decision_cutoff": FROZEN_AT,
        "requested_status": requested,
        "strategic_status": StrategicStatus.ACTIVE,
        "trigger": GateVerdict.PASS,
        "predecessor": GateVerdict.PASS,
        "evidence": GateVerdict.PASS,
        "time_authority": GateVerdict.PASS,
        "geometry": GateVerdict.PASS,
        "forward_reward_risk": GateVerdict.PASS,
        "reserved_risk": GateVerdict.PASS,
        "portfolio_stress": GateVerdict.PASS,
        "cost_liquidity_margin": GateVerdict.PASS,
        "supervision": GateVerdict.PASS,
        "protection_atomicity": GateVerdict.PASS,
    }
    values.update(overrides)
    return StageEvaluation(**values)


def _scenario_08() -> PredicateObservation:
    result = reduce_stage(
        StageState(_stage_spec(StageKind.INITIAL, 0), StageStatus.REGISTERED, 1),
        _eligibility(
            StageStatus.ELIGIBLE,
            reserved_risk=GateVerdict.FAIL,
        ),
    )
    return _domain_observation(
        result, applied_code="INITIAL_STAGE_UNEXPECTEDLY_ELIGIBLE"
    )


def _scenario_09() -> PredicateObservation:
    result = reduce_stage(
        StageState(
            _stage_spec(StageKind.CONFIRMATION, 1),
            StageStatus.ARMED,
            3,
        ),
        _eligibility(
            StageStatus.COUNTERFACTUAL_FILLED,
            matching_fill_candidate=True,
            portfolio_fill_reconciled=False,
        ),
    )
    return _domain_observation(
        result, applied_code="CONFIRMATION_REVERSAL_UNEXPECTEDLY_FILLED"
    )


def _scenario_10() -> PredicateObservation:
    result = reduce_stage(
        StageState(
            _stage_spec(StageKind.TREND, 2), StageStatus.REGISTERED, 1
        ),
        _eligibility(
            StageStatus.ELIGIBLE,
            forward_reward_risk=GateVerdict.FAIL,
        ),
    )
    return _domain_observation(
        result, applied_code="TREND_STAGE_UNEXPECTEDLY_RR_ELIGIBLE"
    )


def _scenario_11() -> PredicateObservation:
    bar = _bar(
        bar_id="bar:stop-target",
        start=FROZEN_AT,
        open_="100",
        high="106",
        low="94",
        close="101",
    )
    result = match_closed_bar(
        bar=bar,
        orders=(
            _order(
                order_id="target",
                barrier_type=BarrierType.TARGET_LIMIT,
                side=OrderSide.SELL,
                active_from=FROZEN_AT,
                limit="105",
            ),
            _order(
                order_id="stop",
                barrier_type=BarrierType.STOP_MARKET,
                side=OrderSide.SELL,
                active_from=FROZEN_AT,
                trigger="95",
            ),
        ),
        policy=_matching_policy(),
        decision_cutoff=_bar_cutoff(bar),
    )
    if (
        result.status is ReducerStatus.APPLIED
        and result.value is not None
        and result.value.order_id == "stop"
        and result.value.ambiguous_barrier_order
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "MATCHING_STOP_FIRST_AMBIGUITY_RECORDED",
            {
                "winner": result.value.order_id,
                "diagnostics": result.value.diagnostic_codes,
            },
        )
    return _domain_observation(
        result, applied_code="MATCHING_STOP_FIRST_INVARIANT_FAILED"
    )


def _scenario_12() -> PredicateObservation:
    first = _bar(
        bar_id="bar:missed-entry",
        start=FROZEN_AT,
        open_="100",
        high="106",
        low="99",
        close="105",
    )
    entry = match_closed_bar(
        bar=first,
        orders=(
            _order(
                order_id="entry:intermediate",
                barrier_type=BarrierType.ENTRY_STOP_MARKET,
                side=OrderSide.BUY,
                active_from=FROZEN_AT,
                trigger="105",
            ),
        ),
        policy=_matching_policy(),
        decision_cutoff=_bar_cutoff(first),
    )
    second_start = FROZEN_AT + timedelta(hours=1)
    second = _bar(
        bar_id="bar:reversal",
        start=second_start,
        open_="104",
        high="105",
        low="94",
        close="95",
    )
    reversal = match_closed_bar(
        bar=second,
        orders=(
            _order(
                order_id="stop:after-entry",
                barrier_type=BarrierType.STOP_MARKET,
                side=OrderSide.SELL,
                active_from=second_start,
                trigger="95",
            ),
        ),
        policy=_matching_policy(),
        decision_cutoff=_bar_cutoff(second),
    )
    if (
        entry.status is ReducerStatus.APPLIED
        and reversal.status is ReducerStatus.APPLIED
        and entry.value is not None
        and reversal.value is not None
        and entry.value.barrier_type is BarrierType.ENTRY_STOP_MARKET
        and reversal.value.barrier_type is BarrierType.STOP_MARKET
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "MISSED_WAKE_INTERMEDIATE_TRIGGER_AND_REVERSAL_REPLAYED",
            {
                "first_bar": entry.value.bar_id,
                "entry_order": entry.value.order_id,
                "second_bar": reversal.value.bar_id,
                "reversal_order": reversal.value.order_id,
            },
        )
    return _observation(
        PredicateOutcome.REJECTED,
        "MISSED_WAKE_INTERMEDIATE_REPLAY_FAILED",
        {
            "entry_status": entry.status.value,
            "reversal_status": reversal.status.value,
        },
    )


def _geometry_fixture() -> GeometryAggregate:
    return GeometryAggregate(
        aggregate_id="geometry-aggregate:scenario",
        revision=3,
        analysis=AnalysisGeometry(
            geometry_id="analysis:scenario",
            revision=2,
            side=PositionSide.LONG,
            status=AnalysisGeometryStatus.ACTIVE_ANALYSIS,
            stop_price=Decimal("90"),
            target_price=Decimal("120"),
            horizon_at=FROZEN_AT + timedelta(hours=12),
            valid_until=FROZEN_AT + timedelta(hours=4),
        ),
        protection=ProtectionBarrier(
            barrier_id="barrier:old",
            revision=2,
            side=PositionSide.LONG,
            status=ExecutionBarrierStatus.ACTIVE_PROTECTION,
            stop_price=Decimal("90"),
            target_price=Decimal("120"),
            horizon_at=FROZEN_AT + timedelta(hours=12),
            position_locked=True,
            active_from=FROZEN_AT - timedelta(hours=1),
            acknowledged_at=FROZEN_AT - timedelta(hours=1),
        ),
    )


def _scenario_13() -> PredicateObservation:
    result = revise_protection(
        _geometry_fixture(),
        ProtectionRevision(
            event_id="geometry-race",
            expected_aggregate_revision=3,
            expected_barrier_revision=2,
            replacement_barrier_id="barrier:new",
            requested_at=FROZEN_AT,
            acknowledged_at=FROZEN_AT + timedelta(seconds=1),
            old_barrier_crossed_at=FROZEN_AT + timedelta(milliseconds=500),
            new_stop_price=Decimal("95"),
            new_target_price=Decimal("120"),
            new_horizon_at=FROZEN_AT + timedelta(hours=10),
            probability_status=GeometryProbabilityStatus.ORDINAL_ONLY,
            t023_core_gates_pass=False,
            t023_governance_ack_pass=False,
        ),
    )
    return _domain_observation(
        result, applied_code="GEOMETRY_RACE_UNEXPECTEDLY_REPLACED"
    )


def _open_reentry(*, atomic: bool = True):
    return open_reentry_contract(
        contract_id="reentry:scenario",
        strategic_episode_id="episode:scenario",
        opened_at=FROZEN_AT,
        earliest_review_at=FROZEN_AT + timedelta(hours=1),
        latest_review_at=FROZEN_AT + timedelta(hours=4),
        expires_at=FROZEN_AT + timedelta(hours=5),
        maximum_deferrals=1,
        minimum_core_quantity=Decimal("1"),
        strategic_status=StrategicStatus.ACTIVE,
        authoritative_core_quantity=Decimal("0"),
        atomic_create_effect_present=atomic,
    )


def _scenario_14() -> PredicateObservation:
    return _domain_observation(
        _open_reentry(atomic=False),
        applied_code="CORE_EXIT_WITHOUT_REENTRY_OBLIGATION_ACCEPTED",
    )


def _scenario_15() -> PredicateObservation:
    opened = _open_reentry().value
    assert opened is not None
    due = reduce_reentry(
        opened,
        ReentryEvaluation(
            event_id="reentry:due",
            expected_revision=opened.revision,
            decision_cutoff=FROZEN_AT + timedelta(hours=1),
            requested_status=ReentryStatus.DUE,
            strategic_status=StrategicStatus.ACTIVE,
        ),
    )
    if due.status is not ReducerStatus.APPLIED or due.value is None:
        return _domain_observation(
            due, applied_code="CONTINUATION_REENTRY_DUE_FAILED"
        )
    eligible = reduce_reentry(
        due.value,
        ReentryEvaluation(
            event_id="reentry:continuation-route",
            expected_revision=due.value.revision,
            decision_cutoff=FROZEN_AT + timedelta(hours=1),
            requested_status=ReentryStatus.ELIGIBLE,
            strategic_status=StrategicStatus.ACTIVE,
            eligibility=EligibilityVerdict.PASS,
        ),
    )
    return _domain_observation(
        eligible, applied_code="CONTINUATION_REENTRY_ELIGIBLE"
    )


def _supervision_contract() -> SupervisionContract:
    return SupervisionContract(
        contract_id="supervision:scenario",
        revision=1,
        windows=(
            SupervisionWindow(
                FROZEN_AT,
                FROZEN_AT + timedelta(hours=1),
                SupervisionMode.SUPERVISED,
            ),
            SupervisionWindow(
                FROZEN_AT + timedelta(hours=1),
                FROZEN_AT + timedelta(hours=8),
                SupervisionMode.UNATTENDED_PROTECTED,
            ),
        ),
    )


def _scenario_16() -> PredicateObservation:
    contract = _supervision_contract()
    supervised = assess_supervision(
        contract,
        effective_at=FROZEN_AT,
        protection_pass=True,
        ack_freshness_pass=True,
        data_freshness_pass=True,
        account_consistency_pass=True,
        worst_case_loss_pass=True,
    )
    unattended = assess_supervision(
        contract,
        effective_at=FROZEN_AT + timedelta(hours=1),
        protection_pass=True,
        ack_freshness_pass=True,
        data_freshness_pass=True,
        account_consistency_pass=True,
        worst_case_loss_pass=True,
    )
    if (
        supervised.value is not None
        and supervised.value.mode is SupervisionMode.SUPERVISED
        and unattended.value is not None
        and unattended.value.mode is SupervisionMode.UNATTENDED_PROTECTED
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "SUPERVISED_TO_UNATTENDED_PROTECTED",
            {
                "before": supervised.value.mode.value,
                "after": unattended.value.mode.value,
            },
        )
    return _observation(
        PredicateOutcome.REJECTED,
        "SUPERVISION_TRANSITION_INVARIANT_FAILED",
        {"supervised": str(supervised), "unattended": str(unattended)},
    )


def _scenario_17() -> PredicateObservation:
    result = assess_supervision(
        _supervision_contract(),
        effective_at=FROZEN_AT + timedelta(hours=2),
        protection_pass=True,
        ack_freshness_pass=True,
        data_freshness_pass=False,
        account_consistency_pass=True,
        worst_case_loss_pass=True,
    )
    if (
        result.status is ReducerStatus.APPLIED
        and result.value is not None
        and result.value.mode is SupervisionMode.NO_NEW_RISK
        and "DATA_FRESHNESS" in result.value.reason_codes
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "UNATTENDED_STALE_DATA_DEGRADES_NO_NEW_RISK",
            {"mode": result.value.mode.value, "reasons": result.value.reason_codes},
        )
    return _domain_observation(
        result, applied_code="UNATTENDED_STALE_DATA_NOT_DEGRADED"
    )


def _episode() -> StrategicEpisode:
    return StrategicEpisode(
        episode_id="episode:scenario",
        revision=1,
        state_digest="a" * 64,
        previous_state_digest=None,
        strategic_status=StrategicStatus.ACTIVE,
        exposure_status=ExposureStatus.EXPOSED,
        strategic_timeframe_seconds=14_400,
        hypothesis_set_id="hypotheses:scenario",
        premise_ids=("premise:scenario",),
        hard_invalidator_ids=("invalidator:scenario",),
        review_clock=ReviewClock(
            "review:scenario",
            FROZEN_AT + timedelta(hours=4),
            FROZEN_AT + timedelta(hours=8),
        ),
        episode_risk_allocation_id="risk:scenario",
    )


def _lease(*, expired: bool = False) -> CrossTimescaleLease:
    return CrossTimescaleLease(
        lease_id="lease:scenario",
        strategic_episode_id="episode:scenario",
        strategic_state_digest="a" * 64,
        strategic_state_revision=1,
        valid_from=FROZEN_AT - timedelta(hours=2),
        valid_until=FROZEN_AT - timedelta(hours=1)
        if expired
        else FROZEN_AT + timedelta(hours=1),
        next_strategic_review_at=FROZEN_AT + timedelta(hours=1),
        permitted_fast_action_intents=frozenset(
            {ActionIntent.KEEP_CORE, ActionIntent.REDUCE_TACTICAL}
        ),
        permitted_protective_actions=frozenset(
            {ProtectiveActionType.NONE, ProtectiveActionType.REDUCE_ONLY}
        ),
        permitted_geometry_operations=frozenset({GeometryOperation.KEEP}),
        terminal_safe_action_intent=ActionIntent.REDUCE_TACTICAL,
    )


def _scenario_18() -> PredicateObservation:
    result = validate_fast_action(
        _episode(),
        _lease(),
        decision_cutoff=FROZEN_AT,
        action_intent=ActionIntent.KEEP_CORE,
        protective_action=ProtectiveActionType.NONE,
        geometry_operation=GeometryOperation.KEEP,
        requests_strategic_mutation=True,
    )
    return _domain_observation(
        result, applied_code="TACTICAL_STRATEGIC_MUTATION_ACCEPTED"
    )


def _selection_fixture() -> tuple[
    FeasibleActionSet,
    DecisionContext,
    tuple[CandidateDecisionMetrics, ...],
]:
    no_action = make_no_action_plan(
        strategic_episode_ref="episode:scenario",
        decision_cutoff=FROZEN_AT,
        path_ref="path:unknown",
        envelope_ref="lease:scenario",
        next_review_at=FROZEN_AT + timedelta(hours=1),
        unmet_dependency_refs=("dependency:scenario",),
    )
    keep = ProposedActionPlan(
        plan_id="plan:keep",
        strategic_episode_ref="episode:scenario",
        decision_cutoff=FROZEN_AT,
        path_ref="path:continuation",
        cross_timescale_control_envelope_ref="lease:scenario",
        strategic_delta_facet_ref="strategic:same",
        position_facet_ref="position:keep",
        action_intent=ActionIntent.KEEP_CORE,
        protective_action_type=ProtectiveActionType.NONE,
        geometry_operation=GeometryOperation.KEEP,
        atomic_effect_types=(),
        position_delta=Decimal("0"),
        risk_delta=Decimal("0"),
    )
    no_action_candidate = CandidateBundle(
        candidate_ref="candidate:no-action",
        proposal_ref="proposal:scenario",
        proposed_action_plan_ref=no_action.plan_id,
        plan=no_action,
        semantic_fingerprint="1" * 64,
        candidate_digest="1" * 64,
    )
    keep_candidate = CandidateBundle(
        candidate_ref="candidate:keep",
        proposal_ref="proposal:scenario",
        proposed_action_plan_ref=keep.plan_id,
        plan=keep,
        semantic_fingerprint="2" * 64,
        candidate_digest="2" * 64,
    )
    candidate_set = CandidateBundleSet(
        proposal_ref="proposal:scenario",
        challenge_ref="challenge:scenario",
        challenge_disposition_ref="disposition:scenario",
        candidates=(keep_candidate, no_action_candidate),
        no_action_candidate_ref=no_action_candidate.candidate_ref,
        rejected_plans=(),
        candidate_set_digest="3" * 64,
    )
    policy = make_decision_criterion_policy(
        policy_id="policy:scenario",
        revision=1,
        valid_from=FROZEN_AT - timedelta(hours=1),
        valid_until=FROZEN_AT + timedelta(days=1),
        tie_break_order=(
            "LOWER_WORST_CASE_LOSS",
            "LOWER_TAIL_LOSS",
            "LOWER_COST",
            "LOWER_TURNOVER",
            "EARLIER_OBLIGATION_REVIEW",
            "CANONICAL_ACTION_ID",
        ),
    )
    feasible = FeasibleActionSet(
        candidate_bundle_set=candidate_set,
        feasible_candidates=(keep_candidate, no_action_candidate),
        removed_candidates=(),
        no_action_candidate_ref=no_action_candidate.candidate_ref,
        non_abstain_feasible_count=1,
        no_hard_feasible_action=False,
        unexpectedly_empty_before_no_action=False,
        retained_soft_verdict_refs=(),
        retained_informational_verdict_refs=(),
        decision_criterion_policy_ref=policy.policy_id,
        decision_criterion_policy_digest=policy.policy_digest,
        feasible_set_digest="4" * 64,
    )
    context = DecisionContext(
        context_id="decision-context:scenario",
        decision_cutoff=FROZEN_AT,
        probability_status=EvaluationProbabilityStatus.ORDINAL_ONLY,
        decision_criterion_policy_ref=policy.policy_id,
        decision_criterion_policy_digest=policy.policy_digest,
    )
    metrics = (
        CandidateDecisionMetrics(
            candidate_ref=keep_candidate.candidate_ref,
            robust_dominated=False,
            minimax_regret=Decimal("1"),
            worst_case_loss=Decimal("1"),
            tail_loss=Decimal("1"),
            cost=Decimal("0"),
            turnover=Decimal("0"),
            obligation_review_at=None,
        ),
        CandidateDecisionMetrics(
            candidate_ref=no_action_candidate.candidate_ref,
            robust_dominated=False,
            minimax_regret=Decimal("0"),
            worst_case_loss=Decimal("0"),
            tail_loss=Decimal("0"),
            cost=Decimal("0"),
            turnover=Decimal("0"),
            obligation_review_at=FROZEN_AT + timedelta(hours=1),
        ),
    )
    return feasible, context, metrics


def _scenario_19() -> PredicateObservation:
    feasible, context, metrics = _selection_fixture()
    policy = make_decision_criterion_policy(
        policy_id=context.decision_criterion_policy_ref,
        revision=1,
        valid_from=FROZEN_AT - timedelta(hours=1),
        valid_until=FROZEN_AT + timedelta(days=1),
        tie_break_order=(
            "LOWER_WORST_CASE_LOSS",
            "LOWER_TAIL_LOSS",
            "LOWER_COST",
            "LOWER_TURNOVER",
            "EARLIER_OBLIGATION_REVIEW",
            "CANONICAL_ACTION_ID",
        ),
    )
    first = select_by_frozen_policy(
        feasible_set=feasible,
        context=context,
        policy=policy,
        metrics=metrics,
    )
    second = select_by_frozen_policy(
        feasible_set=feasible,
        context=context,
        policy=policy,
        metrics=metrics,
    )
    if (
        first.status is ReducerStatus.APPLIED
        and second.status is ReducerStatus.APPLIED
        and first.value is not None
        and second.value is not None
        and first.value.no_action_despite_non_abstain_feasible
        and second.value.no_action_despite_non_abstain_feasible
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "REPEATED_NO_ACTION_WITH_FEASIBLE_ACTION_AUDIT_TRIGGERED",
            {
                "first": first.value.selection_digest,
                "second": second.value.selection_digest,
                "non_abstain_count": feasible.non_abstain_feasible_count,
            },
        )
    return _observation(
        PredicateOutcome.REJECTED,
        "REPEATED_NO_ACTION_AUDIT_NOT_TRIGGERED",
        {"first": str(first), "second": str(second)},
    )


def _scenario_20() -> PredicateObservation:
    try:
        build_cluster_manifest({})
    except BootstrapError as exc:
        return _observation(
            PredicateOutcome.REJECTED,
            str(exc),
            {"exception_type": type(exc).__name__, "code": str(exc)},
        )
    return _observation(
        PredicateOutcome.APPLIED,
        "MISSING_ROLE_BOOTSTRAP_ACCEPTED",
        {"unexpected": "cluster manifest created"},
    )


def _scenario_21() -> PredicateObservation:
    mutation = validate_fast_action(
        _episode(),
        _lease(expired=True),
        decision_cutoff=FROZEN_AT,
        action_intent=ActionIntent.KEEP_CORE,
        protective_action=ProtectiveActionType.NONE,
        geometry_operation=GeometryOperation.KEEP,
        requests_strategic_mutation=True,
    )
    expired_add = validate_fast_action(
        _episode(),
        _lease(expired=True),
        decision_cutoff=FROZEN_AT,
        action_intent=ActionIntent.KEEP_CORE,
        protective_action=ProtectiveActionType.NONE,
        geometry_operation=GeometryOperation.KEEP,
    )
    if (
        mutation.error is not None
        and mutation.error.code
        == "LOWER_TIMEFRAME_STRATEGIC_MUTATION_FORBIDDEN"
        and expired_add.error is not None
        and expired_add.error.code == "CROSS_TIMESCALE_LEASE_CURRENT"
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "EXPIRED_LEASE_AND_FAST_STRATEGIC_MUTATION_BLOCKED",
            {
                "mutation": mutation.error.code,
                "expired_lease": expired_add.error.code,
            },
        )
    return _observation(
        PredicateOutcome.REJECTED,
        "EXPIRED_LEASE_FAST_LAYER_INVARIANT_FAILED",
        {"mutation": str(mutation), "expired": str(expired_add)},
    )


def _recursive(candidate_ref: str, coverage: CoverageVerdict):
    stress = make_stress_scenario_set(
        scenario_set_id=f"stress:{coverage.value.lower()}",
        frozen_at=FROZEN_AT,
        scenario_refs=("stress:gap", "stress:reversal"),
        required_scenario_class_refs=("class:gap", "class:reversal"),
        coverage_verdict=coverage,
    )
    return assess_recursive_feasibility(
        receipt_id=f"recursive:{coverage.value.lower()}",
        candidate_action_ref=candidate_ref,
        decision_cutoff=FROZEN_AT,
        starting_aggregate_head_refs=("head:episode", "head:position"),
        planning_horizon_ref="horizon:scenario",
        next_review_at=FROZEN_AT + timedelta(hours=1),
        stress_scenario_set=stress,
        reachable_state_summary_refs=("reachable:scenario",),
        scenario_continuation_refs={
            "stress:gap": ("action:terminal",),
            "stress:reversal": ("action:reduce",),
        },
        terminal_safe_action_ref="action:terminal",
        hard_constraint_result_refs=("constraints:scenario",),
        solver_or_evaluator_version="1.0.0",
        solver_or_evaluator_digest="a" * 64,
    )


def _scenario_22() -> PredicateObservation:
    failed = _recursive("candidate:attractive-add", CoverageVerdict.FAIL)
    unknown = _recursive("candidate:attractive-add", CoverageVerdict.UNKNOWN)
    if (
        failed.value is not None
        and failed.value.status.value == "FAIL"
        and unknown.value is not None
        and unknown.value.status.value == "UNKNOWN"
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "RECURSIVE_FAIL_AND_UNKNOWN_NOT_PASS",
            {
                "fail": failed.value.status.value,
                "unknown": unknown.value.status.value,
            },
        )
    return _observation(
        PredicateOutcome.REJECTED,
        "RECURSIVE_FAIL_UNKNOWN_COERCED",
        {"fail": str(failed), "unknown": str(unknown)},
    )


def _scenario_23() -> PredicateObservation:
    branch = ContinuationBranch(
        branch_id="branch:future",
        trigger_predicate_refs=("predicate:future",),
        planned_action_ref="action:future",
        remaining_risk_budget_ref="risk:remaining",
        review_at=FROZEN_AT + timedelta(hours=1),
    )
    plan = RecedingHorizonPlan(
        plan_id="receding:scenario",
        strategic_episode_ref="episode:scenario",
        revision=1,
        decision_cutoff=FROZEN_AT,
        planning_context_id="planning:scenario",
        candidate_action_set_digest="a" * 64,
        current_authorized_action_ref="action:current",
        conditional_continuation_branches=(branch,),
        planned_review_points=(FROZEN_AT + timedelta(hours=1),),
        terminal_fallback_action_ref="action:terminal",
        cost_model_ref="cost:scenario",
        path_payoff_matrix_ref="matrix:scenario",
        recursive_feasibility_receipt_ref="recursive:scenario",
        first_step_only=True,
        future_branch_authority="REQUIRES_CURRENT_DATA_REAPPROVAL",
        previous_revision_ref=None,
        plan_digest="b" * 64,
    )
    return _domain_observation(
        authorize_current_plan_action(plan, branch.planned_action_ref),
        applied_code="FUTURE_BRANCH_WITHOUT_REAPPROVAL_ACCEPTED",
    )


def _scenario_24() -> PredicateObservation:
    registry = create_empty_e0_calibration_registry(
        registry_id="calibration:e0",
        registry_version="1.0.0",
        valid_from=FROZEN_AT,
    )
    coherence = ForecastCoherenceReceipt(
        receipt_id="coherence:scenario",
        probability_status=EvaluationProbabilityStatus.ORDINAL_ONLY,
        status=CoherenceVerdict.PASS,
        other_path_present=True,
    )
    result = authorize_probability_use(
        probability_status=EvaluationProbabilityStatus.ORDINAL_ONLY,
        requested_use=ProbabilityUse.EXPECTED_VALUE,
        registry=registry,
        authorization=None,
        coherence_receipt=coherence,
        decision_cutoff=FROZEN_AT,
    )
    return _domain_observation(
        result, applied_code="COHERENCE_CREATED_CALIBRATION_AUTHORITY"
    )


def validate_regime_signal_action(
    *, regime_status: str, requested_action_ref: str | None
) -> DomainResult[str]:
    """Regime monitoring may request review but cannot emit an action."""

    if regime_status not in {"SUSPECTED", "CONFIRMED"}:
        return DomainResult(status=ReducerStatus.NO_CHANGE)
    if requested_action_ref is not None:
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                code="REGIME_SIGNAL_NO_TRADE_AUTHORITY",
                category="EVALUATION",
                retryability="NEVER",
                message="regime signal cannot trade or invalidate",
            ),
        )
    return DomainResult(status=ReducerStatus.APPLIED, value="REVIEW_REQUESTED")


def _scenario_25() -> PredicateObservation:
    return _domain_observation(
        validate_regime_signal_action(
            regime_status="CONFIRMED",
            requested_action_ref="action:invalidate-and-trade",
        ),
        applied_code="REGIME_SIGNAL_TRADED",
    )


def _scenario_26() -> PredicateObservation:
    episode = _episode()
    base = {
        "event_id": "strategic-head-check",
        "requested_status": StrategicStatus.ACTIVE,
        "next_state_digest": "b" * 64,
        "next_review_clock": episode.review_clock,
    }
    digest_mismatch = reduce_strategic_episode(
        episode,
        StrategicTransition(
            expected_revision=episode.revision,
            expected_state_digest="f" * 64,
            **base,
        ),
    )
    revision_mismatch = reduce_strategic_episode(
        episode,
        StrategicTransition(
            expected_revision=episode.revision + 1,
            expected_state_digest=episode.state_digest,
            **base,
        ),
    )
    if (
        digest_mismatch.error is not None
        and digest_mismatch.error.code == "STRATEGIC_PRIOR_HEAD_MISMATCH"
        and revision_mismatch.error is not None
        and revision_mismatch.error.code == "STRATEGIC_PRIOR_HEAD_MISMATCH"
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "REVISION_AND_DIGEST_DUAL_COMPARE_ENFORCED",
            {
                "digest_mismatch": digest_mismatch.error.code,
                "revision_mismatch": revision_mismatch.error.code,
            },
        )
    return _observation(
        PredicateOutcome.REJECTED,
        "AGGREGATE_DUAL_COMPARE_NOT_ENFORCED",
        {"digest": str(digest_mismatch), "revision": str(revision_mismatch)},
    )


def validate_command_head(head_kind: str) -> DomainResult[str]:
    """Only an exact aggregate-head receipt may be a command precondition."""

    if head_kind != "AGGREGATE_HEAD_RECEIPT":
        return DomainResult(
            status=ReducerStatus.REJECTED,
            error=DomainError(
                code="PROJECTION_NOT_COMMAND_HEAD",
                category="STATE",
                retryability="NEVER",
                message="projection or snapshot is not a command head",
            ),
        )
    return DomainResult(
        status=ReducerStatus.APPLIED, value="AGGREGATE_HEAD_RECEIPT"
    )


def _scenario_27() -> PredicateObservation:
    projection = validate_command_head("WORKFLOW_PROJECTION")
    snapshot = validate_command_head("PORTFOLIO_SNAPSHOT")
    if (
        projection.error is not None
        and projection.error.code == "PROJECTION_NOT_COMMAND_HEAD"
        and snapshot.error is not None
        and snapshot.error.code == "PROJECTION_NOT_COMMAND_HEAD"
    ):
        return _observation(
            PredicateOutcome.REJECTED,
            "PROJECTION_NOT_COMMAND_HEAD",
            {
                "projection": projection.error.code,
                "snapshot": snapshot.error.code,
            },
        )
    return _observation(
        PredicateOutcome.APPLIED,
        "LAGGING_VIEW_ACCEPTED_AS_COMMAND_HEAD",
        {"projection": str(projection), "snapshot": str(snapshot)},
    )


def _scenario_28() -> PredicateObservation:
    comparator = _recursive(
        "candidate:comparator", CoverageVerdict.PASS
    ).value
    assert comparator is not None
    common = {
        "candidate_ref": "candidate:evaluated",
        "evaluated_action_ref": "candidate:evaluated",
        "comparator_action_ref": "candidate:comparator",
        "comparator_policy_ref": "policy:comparator",
        "comparator_policy_digest": "c" * 64,
        "decision_cutoff": FROZEN_AT,
        "comparator_feasibility": comparator,
        "same_risk_and_authority_constraints": True,
        "comparison_horizon_ref": "horizon:scenario",
        "path_complexity_or_switch_count": 1,
        "fill_slippage_and_fee_model_ref": "cost:scenario",
        "support_overlap_status": "PASS",
        "identification_contract_ref": None,
        "counterfactual_tier": CounterfactualTier.MODEL_CONDITIONAL,
        "evaluated_value_interval": DecimalInterval(
            Decimal("1"), Decimal("3"), "ACCOUNT_USD"
        ),
        "comparator_value_interval": DecimalInterval(
            Decimal("4"), Decimal("8"), "ACCOUNT_USD"
        ),
        "uncertainty_interval": DecimalInterval(
            Decimal("0"), Decimal("2"), "ACCOUNT_USD"
        ),
        "status": OpportunityStatus.PARTIALLY_IDENTIFIED,
        "assumption_refs": ("assumption:scenario",),
        "calculator_contract_version": "1.0.0",
    }
    frozen = issue_ex_ante_opportunity_cost(
        receipt_id="opportunity:frozen",
        comparator_frozen_at=FROZEN_AT,
        **common,
    )
    hindsight = issue_ex_ante_opportunity_cost(
        receipt_id="opportunity:hindsight",
        comparator_frozen_at=FROZEN_AT + timedelta(seconds=1),
        **common,
    )
    if (
        frozen.status is ReducerStatus.APPLIED
        and hindsight.error is not None
        and hindsight.error.code == "OPPORTUNITY_COMPARATOR_NOT_FROZEN"
    ):
        return _observation(
            PredicateOutcome.APPLIED,
            "FROZEN_COMPARATOR_ACCEPTED_HINTSIGHT_REJECTED",
            {
                "frozen_receipt": frozen.value.receipt_digest
                if frozen.value is not None
                else None,
                "hindsight": hindsight.error.code,
            },
        )
    return _observation(
        PredicateOutcome.REJECTED,
        "OPPORTUNITY_COMPARATOR_BOUNDARY_FAILED",
        {"frozen": str(frozen), "hindsight": str(hindsight)},
    )


def _scenario_29() -> PredicateObservation:
    result = reduce_stage(
        StageState(_stage_spec(StageKind.INITIAL, 0), StageStatus.REGISTERED, 1),
        _eligibility(
            StageStatus.COUNTERFACTUAL_FILLED,
            matching_fill_candidate=True,
            portfolio_fill_reconciled=True,
        ),
    )
    return _domain_observation(
        result, applied_code="FORGED_STAGE_RECEIPT_CREATED_FILL"
    )


def _scenario_30() -> PredicateObservation:
    nonempty = create_empty_e0_calibration_registry(
        registry_id="calibration:e0",
        registry_version="1.0.0",
        valid_from=FROZEN_AT,
    )
    nonempty = type(nonempty)(
        registry_id=nonempty.registry_id,
        registry_version=nonempty.registry_version,
        calibration_record_refs=("calibration-record:forbidden",),
        registry_status=nonempty.registry_status,
        valid_from=nonempty.valid_from,
    )
    registry_result = validate_e0_calibration_registry(nonempty)
    empty = create_empty_e0_calibration_registry(
        registry_id="calibration:empty",
        registry_version="1.0.0",
        valid_from=FROZEN_AT,
    )
    authorization = ProbabilityUseAuthorization(
        authorization_id="probability-auth:forbidden",
        calibration_record_ref="calibration-record:forbidden",
        coherence_receipt_ref="coherence:forbidden",
        allowed_uses=frozenset({"EXPECTED_VALUE"}),
        valid_from=FROZEN_AT,
        valid_until=FROZEN_AT + timedelta(hours=1),
    )
    authorization_result = authorize_probability_use(
        probability_status=EvaluationProbabilityStatus.ORDINAL_ONLY,
        requested_use=ProbabilityUse.ORDINAL_PATH_RANKING,
        registry=empty,
        authorization=authorization,
        coherence_receipt=None,
        decision_cutoff=FROZEN_AT,
    )
    if (
        registry_result.error is not None
        and registry_result.error.code == "CALIBRATION_REGISTRY_NONEMPTY_E0"
        and authorization_result.error is not None
        and authorization_result.error.code == "PROBABILITY_USE_UNAUTHORIZED_E0"
    ):
        return _observation(
            PredicateOutcome.REJECTED,
            "E0_CALIBRATION_AND_AUTHORIZATION_INSTANCES_FORBIDDEN",
            {
                "registry": registry_result.error.code,
                "authorization": authorization_result.error.code,
            },
        )
    return _observation(
        PredicateOutcome.APPLIED,
        "E0_CALIBRATION_AUTHORITY_ACCEPTED",
        {
            "registry": str(registry_result),
            "authorization": str(authorization_result),
        },
    )


def _scenario_31() -> PredicateObservation:
    record = EvidenceRecord(
        evidence_id="evidence:unanimous-agent-claim",
        source_id="source:stale",
        available_at=FROZEN_AT,
        ingested_at=FROZEN_AT,
        source_committed_at=FROZEN_AT,
        source_commit_receipt_valid=True,
        physical_existence=PhysicalExistence.PROVEN,
        usage_scope=EvidenceScope.DECISION_CONTEMPORANEOUS,
        quality=EvidenceQuality.STALE,
        signal_class=SignalClass.STRUCTURAL,
        timeframe_seconds=14_400,
        premise_ids=("premise:scenario",),
        independent_source_ids=("agent:1", "agent:2", "agent:3"),
        observation_count=3,
    )
    result = admit_evidence(
        record,
        decision_cutoff=FROZEN_AT,
        strategic_timeframe_seconds=14_400,
    )
    return _domain_observation(
        result, applied_code="UNANIMOUS_AGENTS_ERASED_EVIDENCE_UNCERTAINTY"
    )


class _AtomicEffectFailure(RuntimeError):
    pass


class _FailingAtomicUnitOfWork:
    def __init__(self) -> None:
        self.visible_commit_count = 0
        self.attempted_effect_refs: tuple[str, ...] = ()

    def commit(self, plan: object) -> object:
        effect_refs = tuple(getattr(plan, "atomic_effect_refs", ()))
        self.attempted_effect_refs = effect_refs
        if "effect:fail-deliberately" in effect_refs:
            # Failure occurs before visibility, modeling all-or-nothing UoW.
            raise _AtomicEffectFailure("UOW_ATOMIC_EFFECT_FAILED_NO_COMMIT")
        self.visible_commit_count += 1
        return {"committed": True}


def _scenario_32() -> PredicateObservation:
    selection = AgentSelection(
        selection_ref="selection:scenario",
        feasible_action_set_ref="feasible:scenario",
        selection_disposition="SELECT_ACTION",
        selected_candidate_ref="candidate:exit-to-reentry",
        ranked_alternative_refs=(),
        no_action_candidate_ref="candidate:no-action",
        retained_soft_warning_refs=(),
        residual_unknown_refs=(),
        selection_reason="frozen scenario selection",
        decision_criterion_policy_ref="policy:scenario",
        decision_criterion_policy_digest="d" * 64,
        no_action_despite_non_abstain_feasible=False,
        selection_digest="e" * 64,
    )
    governance = GovernanceAssessmentReceipt(
        selection_ref=selection.selection_ref,
        selection_valid=GovernanceVerdict.PASS,
        market_feasibility="FEASIBLE",
        counterfactual_permission="ALLOWED",
        schema_pit_state_verdict_refs=("pit:pass",),
        hard_constraint_verdict_refs=("constraints:pass",),
        challenge_disposition_ref="disposition:scenario",
        expected_head_ref="head:scenario",
    )
    plan = RecedingHorizonPlan(
        plan_id="receding:exit-to-reentry",
        strategic_episode_ref="episode:scenario",
        revision=1,
        decision_cutoff=FROZEN_AT,
        planning_context_id="planning:scenario",
        candidate_action_set_digest="a" * 64,
        current_authorized_action_ref=selection.selected_candidate_ref,
        conditional_continuation_branches=(),
        planned_review_points=(FROZEN_AT + timedelta(hours=1),),
        terminal_fallback_action_ref="action:terminal",
        cost_model_ref="cost:scenario",
        path_payoff_matrix_ref="matrix:scenario",
        recursive_feasibility_receipt_ref="recursive:scenario",
        first_step_only=True,
        future_branch_authority="REQUIRES_CURRENT_DATA_REAPPROVAL",
        previous_revision_ref=None,
        plan_digest="f" * 64,
    )
    replay = ReplayOutcome(
        result_ref="replay:scenario",
        result_digest="1" * 64,
        counterfactual_policy_ref="counterfactual:scenario",
        aggregate_mutations=(
            AggregateMutation(
                aggregate_id="episode:scenario",
                aggregate_type="STRATEGIC_EPISODE",
                expected_revision=1,
                expected_state_digest="a" * 64,
                next_revision=2,
                state_ref="state:episode:2",
                state_digest="b" * 64,
            ),
        ),
        atomic_effect_refs=(
            "effect:create-reentry-contract",
            "effect:fail-deliberately",
        ),
    )
    context = CommitContext(
        commit_id="commit:scenario",
        offline_run_id="scenario-run",
        decision_session_id="decision-session:scenario",
        committed_at="2026-07-31T00:00:00Z",
        idempotent_command_id="command:scenario",
        idempotency_key="command:scenario",
        expected_previous_event_sequence=None,
        expected_previous_event_digest=None,
        accepted_artifact_digests=("a" * 64,),
    )
    unit_of_work = _FailingAtomicUnitOfWork()
    try:
        commit_e0_session(
            context=context,
            selection=selection,
            governance=governance,
            receding_horizon_plan=plan,
            replay=replay,
            unit_of_work=unit_of_work,
        )
    except _AtomicEffectFailure as exc:
        if (
            str(exc) == "UOW_ATOMIC_EFFECT_FAILED_NO_COMMIT"
            and unit_of_work.visible_commit_count == 0
            and "effect:fail-deliberately" in unit_of_work.attempted_effect_refs
        ):
            return _observation(
                PredicateOutcome.REJECTED,
                "UOW_ATOMIC_EFFECT_FAILED_NO_COMMIT",
                {
                    "effects": unit_of_work.attempted_effect_refs,
                    "visible_commit_count": unit_of_work.visible_commit_count,
                },
            )
        return _observation(
            PredicateOutcome.UNKNOWN,
            "UOW_ATOMIC_FAILURE_VISIBILITY_UNKNOWN",
            {
                "error": str(exc),
                "visible_commit_count": unit_of_work.visible_commit_count,
            },
        )
    return _observation(
        PredicateOutcome.APPLIED,
        "UOW_PARTIAL_EFFECT_COMMIT_VISIBLE",
        {"visible_commit_count": unit_of_work.visible_commit_count},
    )


def _scenario_definition(
    ordinal: int,
    title: str,
    cohort_id: str,
    predicate_id: str,
    expected_outcome: PredicateOutcome,
    expected_code: str,
    executor: ScenarioExecutor,
) -> CanonicalScenarioDefinition:
    return CanonicalScenarioDefinition(
        scenario_id=f"S19_2_{ordinal:02d}",
        ordinal=ordinal,
        title=title,
        cohort_id=cohort_id,
        dataset_type=DATASET_TYPE,
        predicate_id=predicate_id,
        expected_outcome=expected_outcome,
        expected_code=expected_code,
        executor=executor,
    )


CANONICAL_SCENARIOS: tuple[CanonicalScenarioDefinition, ...] = (
    _scenario_definition(
        1,
        "trend continuation after rebound",
        SNDK_COHORT,
        "calculate_linear_pnl_interval:positive",
        PredicateOutcome.APPLIED,
        "TREND_CONTINUATION_PAYOFF_POSITIVE",
        lambda: _path_payoff_observation(
            code="TREND_CONTINUATION_PAYOFF_POSITIVE",
            terminal_lower="115",
            terminal_upper="130",
            required_relation="POSITIVE",
        ),
    ),
    _scenario_definition(
        2,
        "rebound failure",
        SNDK_COHORT,
        "calculate_linear_pnl_interval:negative",
        PredicateOutcome.APPLIED,
        "REBOUND_FAILURE_PAYOFF_NEGATIVE",
        lambda: _path_payoff_observation(
            code="REBOUND_FAILURE_PAYOFF_NEGATIVE",
            terminal_lower="80",
            terminal_upper="90",
            required_relation="NEGATIVE",
        ),
    ),
    _scenario_definition(
        3,
        "false breakout",
        SNDK_COHORT,
        "calculate_linear_pnl_interval:straddles_zero",
        PredicateOutcome.APPLIED,
        "FALSE_BREAKOUT_PAYOFF_STRADDLES_ZERO",
        lambda: _path_payoff_observation(
            code="FALSE_BREAKOUT_PAYOFF_STRADDLES_ZERO",
            terminal_lower="98",
            terminal_upper="104",
            required_relation="STRADDLES_ZERO",
        ),
    ),
    _scenario_definition(
        4,
        "range",
        SNDK_COHORT,
        "calculate_linear_pnl_interval:bounded_range",
        PredicateOutcome.APPLIED,
        "RANGE_PAYOFF_BOUNDED",
        lambda: _path_payoff_observation(
            code="RANGE_PAYOFF_BOUNDED",
            terminal_lower="99",
            terminal_upper="102",
            required_relation="BOUNDED_RANGE",
        ),
    ),
    _scenario_definition(
        5,
        "deep pullback and recovery",
        SNDK_COHORT,
        "calculate_linear_pnl_interval:wide_path",
        PredicateOutcome.APPLIED,
        "DEEP_PULLBACK_RECOVERY_PATH_DEPENDENT",
        lambda: _path_payoff_observation(
            code="DEEP_PULLBACK_RECOVERY_PATH_DEPENDENT",
            terminal_lower="80",
            terminal_upper="125",
            required_relation="WIDE_PATH_DEPENDENCE",
        ),
    ),
    _scenario_definition(
        6,
        "no-pullback acceleration",
        SNDK_COHORT,
        "calculate_linear_pnl_interval:acceleration",
        PredicateOutcome.APPLIED,
        "NO_PULLBACK_ACCELERATION_PAYOFF_POSITIVE",
        lambda: _path_payoff_observation(
            code="NO_PULLBACK_ACCELERATION_PAYOFF_POSITIVE",
            terminal_lower="108",
            terminal_upper="120",
            required_relation="POSITIVE",
        ),
    ),
    _scenario_definition(
        7,
        "event gap through stop",
        INDEPENDENT_COHORT,
        "match_closed_bar:gap_stop",
        PredicateOutcome.APPLIED,
        "MATCHING_GAP_STOP_CONSERVATIVE",
        _scenario_07,
    ),
    _scenario_definition(
        8,
        "initial stage fails immediately",
        INDEPENDENT_COHORT,
        "reduce_stage:risk_fail",
        PredicateOutcome.REJECTED,
        "STAGE_RISK_CAP_FAILED",
        _scenario_08,
    ),
    _scenario_definition(
        9,
        "confirmation stage triggers and reverses",
        INDEPENDENT_COHORT,
        "reduce_stage:unreconciled_reversal",
        PredicateOutcome.REJECTED,
        "STAGE_PROTECTION_ATOMICITY_UNKNOWN",
        _scenario_09,
    ),
    _scenario_definition(
        10,
        "trend stage becomes forward-RR ineligible after appreciation",
        INDEPENDENT_COHORT,
        "reduce_stage:forward_rr",
        PredicateOutcome.REJECTED,
        "STAGE_FORWARD_RR_INELIGIBLE",
        _scenario_10,
    ),
    _scenario_definition(
        11,
        "target and stop touched in one bar",
        INDEPENDENT_COHORT,
        "match_closed_bar:stop_first",
        PredicateOutcome.APPLIED,
        "MATCHING_STOP_FIRST_AMBIGUITY_RECORDED",
        _scenario_11,
    ),
    _scenario_definition(
        12,
        "missed wake with an intermediate trigger and reversal",
        INDEPENDENT_COHORT,
        "match_closed_bar:ordered_intermediate_replay",
        PredicateOutcome.APPLIED,
        "MISSED_WAKE_INTERMEDIATE_TRIGGER_AND_REVERSAL_REPLAYED",
        _scenario_12,
    ),
    _scenario_definition(
        13,
        "geometry replacement ACK race",
        INDEPENDENT_COHORT,
        "revise_protection:ack_race",
        PredicateOutcome.REJECTED,
        "GEOMETRY_OLD_BARRIER_ALREADY_CROSSED",
        _scenario_13,
    ),
    _scenario_definition(
        14,
        "CORE exit with surviving thesis and reentry obligation",
        SNDK_COHORT,
        "open_reentry_contract:atomic_effect",
        PredicateOutcome.UNKNOWN,
        "REENTRY_ATOMIC_OPEN_MISSING",
        _scenario_14,
    ),
    _scenario_definition(
        15,
        "continuation reentry without preferred pullback",
        INDEPENDENT_COHORT,
        "reduce_reentry:continuation_route",
        PredicateOutcome.APPLIED,
        "CONTINUATION_REENTRY_ELIGIBLE",
        _scenario_15,
    ),
    _scenario_definition(
        16,
        "supervised to unattended transition",
        INDEPENDENT_COHORT,
        "assess_supervision:mode_transition",
        PredicateOutcome.APPLIED,
        "SUPERVISED_TO_UNATTENDED_PROTECTED",
        _scenario_16,
    ),
    _scenario_definition(
        17,
        "unattended stale data or lost protection",
        INDEPENDENT_COHORT,
        "assess_supervision:stale_data",
        PredicateOutcome.APPLIED,
        "UNATTENDED_STALE_DATA_DEGRADES_NO_NEW_RISK",
        _scenario_17,
    ),
    _scenario_definition(
        18,
        "tactical signal attempting strategic invalidation",
        INDEPENDENT_COHORT,
        "validate_fast_action:strategic_mutation",
        PredicateOutcome.REJECTED,
        "LOWER_TIMEFRAME_STRATEGIC_MUTATION_FORBIDDEN",
        _scenario_18,
    ),
    _scenario_definition(
        19,
        "feasible non-no-action candidates with repeated Agent no-action selection",
        SNDK_COHORT,
        "select_by_frozen_policy:repeated_no_action_audit",
        PredicateOutcome.APPLIED,
        "REPEATED_NO_ACTION_WITH_FEASIBLE_ACTION_AUDIT_TRIGGERED",
        _scenario_19,
    ),
    _scenario_definition(
        20,
        "missing required Agent role or bootstrap state",
        INDEPENDENT_COHORT,
        "build_cluster_manifest:required_roles",
        PredicateOutcome.REJECTED,
        "CLUSTER_SKILL_SET_MISMATCH",
        _scenario_20,
    ),
    _scenario_definition(
        21,
        "expired cross-timescale lease with a fast-layer strategic mutation attempt",
        INDEPENDENT_COHORT,
        "validate_fast_action:expired_mutation",
        PredicateOutcome.APPLIED,
        "EXPIRED_LEASE_AND_FAST_STRATEGIC_MUTATION_BLOCKED",
        _scenario_21,
    ),
    _scenario_definition(
        22,
        "recursive feasibility FAIL and UNKNOWN after an otherwise attractive add",
        INDEPENDENT_COHORT,
        "assess_recursive_feasibility:fail_unknown",
        PredicateOutcome.APPLIED,
        "RECURSIVE_FAIL_AND_UNKNOWN_NOT_PASS",
        _scenario_22,
    ),
    _scenario_definition(
        23,
        "conditional future branch submitted without current-data reapproval",
        INDEPENDENT_COHORT,
        "authorize_current_plan_action:future_branch",
        PredicateOutcome.REJECTED,
        "RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED",
        _scenario_23,
    ),
    _scenario_definition(
        24,
        "coherent forecasts without calibration or probability-use authorization",
        INDEPENDENT_COHORT,
        "authorize_probability_use:coherence_not_calibration",
        PredicateOutcome.REJECTED,
        "PROBABILITY_USE_UNAUTHORIZED_E0",
        _scenario_24,
    ),
    _scenario_definition(
        25,
        "suspected/confirmed regime shift attempting to invalidate or trade",
        INDEPENDENT_COHORT,
        "validate_regime_signal_action:no_trade_authority",
        PredicateOutcome.REJECTED,
        "REGIME_SIGNAL_NO_TRADE_AUTHORITY",
        _scenario_25,
    ),
    _scenario_definition(
        26,
        "aggregate revision match with state-digest mismatch, and the converse",
        INDEPENDENT_COHORT,
        "reduce_strategic_episode:dual_head_compare",
        PredicateOutcome.APPLIED,
        "REVISION_AND_DIGEST_DUAL_COMPARE_ENFORCED",
        _scenario_26,
    ),
    _scenario_definition(
        27,
        "lagging projection or snapshot used as a command head",
        INDEPENDENT_COHORT,
        "validate_command_head:projection_rejection",
        PredicateOutcome.REJECTED,
        "PROJECTION_NOT_COMMAND_HEAD",
        _scenario_27,
    ),
    _scenario_definition(
        28,
        "frozen feasible opportunity comparator versus a hindsight-only comparator",
        SNDK_COHORT,
        "issue_ex_ante_opportunity_cost:frozen_vs_hindsight",
        PredicateOutcome.APPLIED,
        "FROZEN_COMPARATOR_ACCEPTED_HINTSIGHT_REJECTED",
        _scenario_28,
    ),
    _scenario_definition(
        29,
        "forged stage receipt attempting to create a fill or quantity",
        INDEPENDENT_COHORT,
        "reduce_stage:forged_fill_transition",
        PredicateOutcome.REJECTED,
        "STAGE_PRIOR_RECEIPT_MISMATCH",
        _scenario_29,
    ),
    _scenario_definition(
        30,
        "nonempty E0 calibration registry or probability-authorization instance",
        INDEPENDENT_COHORT,
        "validate_e0_calibration_registry:zero_instances",
        PredicateOutcome.REJECTED,
        "E0_CALIBRATION_AND_AUTHORIZATION_INSTANCES_FORBIDDEN",
        _scenario_30,
    ),
    _scenario_definition(
        31,
        "unanimous Agent output attempting to erase PIT/data/path uncertainty",
        INDEPENDENT_COHORT,
        "admit_evidence:stale_unknown_preserved",
        PredicateOutcome.UNKNOWN,
        "EVIDENCE_LINEAGE_INVALID",
        _scenario_31,
    ),
    _scenario_definition(
        32,
        "atomic strategic exit-to-reentry commit with one deliberately failed effect",
        INDEPENDENT_COHORT,
        "commit_e0_session:atomic_effect_failure",
        PredicateOutcome.REJECTED,
        "UOW_ATOMIC_EFFECT_FAILED_NO_COMMIT",
        _scenario_32,
    ),
)


def _definition_payload(definition: CanonicalScenarioDefinition) -> dict[str, object]:
    return {
        "scenario_id": definition.scenario_id,
        "ordinal": definition.ordinal,
        "title": definition.title,
        "cohort_id": definition.cohort_id,
        "dataset_type": definition.dataset_type,
        "predicate_id": definition.predicate_id,
        "expected_outcome": definition.expected_outcome.value,
        "expected_code": definition.expected_code,
        "executor_name": definition.executor.__name__,
    }


def canonical_scenario_registry_digest() -> str:
    return canonical_digest(
        tuple(_definition_payload(item) for item in CANONICAL_SCENARIOS)
    )


def validate_canonical_scenario_registry() -> None:
    expected_ids = tuple(f"S19_2_{index:02d}" for index in range(1, 33))
    actual_ids = tuple(item.scenario_id for item in CANONICAL_SCENARIOS)
    if actual_ids != expected_ids:
        raise ValueError("CANONICAL_SCENARIO_REGISTRY_ID_MISMATCH")
    if tuple(item.ordinal for item in CANONICAL_SCENARIOS) != tuple(range(1, 33)):
        raise ValueError("CANONICAL_SCENARIO_REGISTRY_ORDINAL_MISMATCH")
    if any(
        not item.title
        or not item.predicate_id
        or not item.expected_code
        or item.dataset_type != DATASET_TYPE
        for item in CANONICAL_SCENARIOS
    ):
        raise ValueError("CANONICAL_SCENARIO_REGISTRY_ENTRY_INCOMPLETE")
    cohorts = {item.cohort_id for item in CANONICAL_SCENARIOS}
    if SNDK_COHORT not in cohorts or INDEPENDENT_COHORT not in cohorts:
        raise ValueError("CANONICAL_SCENARIO_NON_SNDK_COHORT_MISSING")


def run_canonical_scenario(
    definition: CanonicalScenarioDefinition,
) -> CanonicalScenarioResult:
    try:
        observed = definition.executor()
    except Exception as exc:  # deterministic no-crash boundary
        observed = _observation(
            PredicateOutcome.UNKNOWN,
            "SCENARIO_EXECUTION_EXCEPTION",
            {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )
        status = ScenarioValidationStatus.UNKNOWN
    else:
        status = (
            ScenarioValidationStatus.PASS
            if (
                observed.outcome is definition.expected_outcome
                and observed.code == definition.expected_code
            )
            else ScenarioValidationStatus.FAIL
        )
    payload = {
        **_definition_payload(definition),
        "observed_outcome": observed.outcome.value,
        "observed_code": observed.code,
        "status": status.value,
        "evidence_digest": observed.evidence_digest,
    }
    return CanonicalScenarioResult(
        scenario_id=definition.scenario_id,
        title=definition.title,
        cohort_id=definition.cohort_id,
        predicate_id=definition.predicate_id,
        expected_outcome=definition.expected_outcome,
        expected_code=definition.expected_code,
        observed_outcome=observed.outcome,
        observed_code=observed.code,
        status=status,
        evidence_digest=observed.evidence_digest,
        result_digest=canonical_digest(payload),
    )


def run_canonical_scenarios() -> CanonicalScenarioReport:
    validate_canonical_scenario_registry()
    results = tuple(run_canonical_scenario(item) for item in CANONICAL_SCENARIOS)
    pass_count = sum(item.status is ScenarioValidationStatus.PASS for item in results)
    fail_count = sum(item.status is ScenarioValidationStatus.FAIL for item in results)
    unknown_count = sum(
        item.status is ScenarioValidationStatus.UNKNOWN for item in results
    )
    registry_digest = canonical_scenario_registry_digest()
    payload = {
        "contract_section": "THEORY_AGENT_V2_IMPLEMENTATION_CONTRACT_v1_0:19.2",
        "registry_digest": registry_digest,
        "result_digests": tuple(item.result_digest for item in results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "unknown_count": unknown_count,
    }
    return CanonicalScenarioReport(
        contract_section=payload["contract_section"],
        registry_digest=registry_digest,
        results=results,
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=unknown_count,
        report_digest=canonical_digest(payload),
    )


__all__ = [
    "CANONICAL_SCENARIOS",
    "CanonicalScenarioDefinition",
    "CanonicalScenarioReport",
    "CanonicalScenarioResult",
    "INDEPENDENT_COHORT",
    "PredicateOutcome",
    "SNDK_COHORT",
    "ScenarioValidationStatus",
    "canonical_scenario_registry_digest",
    "run_canonical_scenario",
    "run_canonical_scenarios",
    "validate_canonical_scenario_registry",
    "validate_command_head",
    "validate_regime_signal_action",
]

