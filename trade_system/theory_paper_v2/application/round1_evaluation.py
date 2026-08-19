"""Point-in-time first-round characterization and A-I gate evaluation.

The V1 record does not contain persistent V2 strategic state, CORE/TACTICAL
roles, reentry contracts, dynamic-geometry lifecycle or a complete candidate
proposal stream.  This evaluator preserves those absences as UNKNOWN instead
of optimizing a hindsight reconstruction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
import re
from typing import Mapping

from ..domain.contracts.canonical import canonical_digest
from ..infrastructure.legacy_v1 import LegacyCycleEnvelope, LegacyV1Adapter
from trade_system.theory_paper.common import digest_json
from trade_system.theory_paper.inference_v2.infrastructure import (
    read_json_object,
)


ARMS = {
    "A": ("FROZEN_V1_BEHAVIOR",),
    "B": ("FROZEN_V1_BEHAVIOR", "PERSISTENT_STRATEGIC_STATE"),
    "C": (
        "FROZEN_V1_BEHAVIOR",
        "PERSISTENT_STRATEGIC_STATE",
        "CORE_TACTICAL_ROLE_SEPARATION",
    ),
    "D": (
        "FROZEN_V1_BEHAVIOR",
        "PERSISTENT_STRATEGIC_STATE",
        "CORE_TACTICAL_ROLE_SEPARATION",
        "FOUR_PATH_POST_TARGET_REVIEW",
    ),
    "E": (
        "FROZEN_V1_BEHAVIOR",
        "PERSISTENT_STRATEGIC_STATE",
        "CORE_TACTICAL_ROLE_SEPARATION",
        "FOUR_PATH_POST_TARGET_REVIEW",
        "MANDATORY_REENTRY_CONTRACT",
    ),
    "F": (
        "FROZEN_V1_BEHAVIOR",
        "PERSISTENT_STRATEGIC_STATE",
        "CORE_TACTICAL_ROLE_SEPARATION",
        "FOUR_PATH_POST_TARGET_REVIEW",
        "MANDATORY_REENTRY_CONTRACT",
        "DYNAMIC_EXPIRING_GEOMETRY",
    ),
    "G": (
        "FROZEN_V1_BEHAVIOR",
        "PERSISTENT_STRATEGIC_STATE",
        "CORE_TACTICAL_ROLE_SEPARATION",
        "FOUR_PATH_POST_TARGET_REVIEW",
        "MANDATORY_REENTRY_CONTRACT",
        "DYNAMIC_EXPIRING_GEOMETRY",
        "SCHEDULER_AND_EVENT_MATCHING",
    ),
    "H": (
        "FROZEN_V1_BEHAVIOR",
        "PERSISTENT_STRATEGIC_STATE",
        "CORE_TACTICAL_ROLE_SEPARATION",
        "FOUR_PATH_POST_TARGET_REVIEW",
        "MANDATORY_REENTRY_CONTRACT",
        "DYNAMIC_EXPIRING_GEOMETRY",
        "SCHEDULER_AND_EVENT_MATCHING",
        "PATH_PAYOFF_RISK_AND_STAGED_POSITION",
    ),
    "I": (
        "FROZEN_V1_BEHAVIOR",
        "PERSISTENT_STRATEGIC_STATE",
        "CORE_TACTICAL_ROLE_SEPARATION",
        "FOUR_PATH_POST_TARGET_REVIEW",
        "MANDATORY_REENTRY_CONTRACT",
        "DYNAMIC_EXPIRING_GEOMETRY",
        "SCHEDULER_AND_EVENT_MATCHING",
        "PATH_PAYOFF_RISK_AND_STAGED_POSITION",
        "SUPERVISION_AND_UNATTENDED_SAFETY",
    ),
}

COUNTERFACTUAL_POLICIES = (
    "ORIGINAL_AGENT_RULES",
    "STRATEGIC_THESIS_PRESERVATION",
    "TACTICAL_REDUCTION_ONLY",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class IdentifiedAccounting:
    initial_equity: Decimal
    cash_balance: Decimal
    realized_pnl_gross: Decimal
    fees: Decimal
    net_realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_net_pnl: Decimal
    max_drawdown_fraction: Decimal
    fill_count: int
    funding_status: str


@dataclass(frozen=True, slots=True)
class FrozenCostPolicy:
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    market_slippage_bps: Decimal
    stop_slippage_bps: Decimal
    funding_accrual_status: str
    policy_digest: str

    def __post_init__(self) -> None:
        values = (
            self.maker_fee_rate,
            self.taker_fee_rate,
            self.market_slippage_bps,
            self.stop_slippage_bps,
        )
        if (
            any(not value.is_finite() or value < 0 for value in values)
            or self.maker_fee_rate >= 1
            or self.taker_fee_rate >= 1
            or not self.funding_accrual_status
            or _HEX64.fullmatch(self.policy_digest) is None
            or canonical_digest(_cost_policy_payload(self))
            != self.policy_digest
        ):
            raise ValueError("COST_POLICY_INVALID")


@dataclass(frozen=True, slots=True)
class ArmEvaluation:
    arm_id: str
    enabled_features: tuple[str, ...]
    point_in_time_bundle_digest: str
    candidate_proposal_stream_digest: str | None
    functional_status: str
    economic_status: str
    accounting: IdentifiedAccounting | None
    primary_path_capture: Decimal | None
    unknown_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CounterfactualEvaluation:
    policy_id: str
    identifiability: str
    result_status: str
    terminal_mark_net_pnl: Decimal | None
    hypothetical_exit_net_pnl: Decimal | None
    formula: str | None
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Round1EvaluationResult:
    legacy_run_id: str
    cycle_ids: tuple[str, ...]
    point_in_time_bundle_digest: str
    chronology_digest: str
    cost_policy_digest: str
    proposal_stream_status: str
    candidate_proposal_stream_digest: str | None
    a_observed: IdentifiedAccounting
    a_replayed_accounting_match: bool
    a_replayed_action_fill_identity_match: bool
    arms: tuple[ArmEvaluation, ...]
    counterfactuals: tuple[CounterfactualEvaluation, ...]
    canonical_scenario_suite_digest: str
    canonical_scenarios_passed: bool
    hard_functional_gate_status: str
    behavior_economic_gate_status: str
    terminal_status: str
    terminal_reason_codes: tuple[str, ...]
    result_digest: str
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _cost_policy_payload(policy: FrozenCostPolicy) -> dict[str, object]:
    return {
        "maker_fee_rate": policy.maker_fee_rate,
        "taker_fee_rate": policy.taker_fee_rate,
        "market_slippage_bps": policy.market_slippage_bps,
        "stop_slippage_bps": policy.stop_slippage_bps,
        "funding_accrual_status": policy.funding_accrual_status,
    }


def build_frozen_cost_policy(
    *,
    maker_fee_rate: object,
    taker_fee_rate: object,
    market_slippage_bps: object,
    stop_slippage_bps: object,
    funding_accrual_status: str = "NOT_SIMULATED_V0_1",
) -> FrozenCostPolicy:
    maker = _decimal(maker_fee_rate)
    taker = _decimal(taker_fee_rate)
    market = _decimal(market_slippage_bps)
    stop = _decimal(stop_slippage_bps)
    payload = {
        "maker_fee_rate": maker,
        "taker_fee_rate": taker,
        "market_slippage_bps": market,
        "stop_slippage_bps": stop,
        "funding_accrual_status": funding_accrual_status,
    }
    return FrozenCostPolicy(
        maker_fee_rate=maker,
        taker_fee_rate=taker,
        market_slippage_bps=market,
        stop_slippage_bps=stop,
        funding_accrual_status=funding_accrual_status,
        policy_digest=canonical_digest(payload),
    )


def _require_digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{field_name}_INVALID")
    return value


def _load_bound_decision(
    run_root: Path,
    envelope: LegacyCycleEnvelope,
) -> Mapping[str, object]:
    """Read a V1 decision only when it matches the adapter-bound digest."""

    decision = read_json_object(
        run_root / "cycles" / envelope.cycle_id / "decision.json"
    )
    expected = dict(envelope.source_artifact_digests).get("decision.json")
    if expected is None or digest_json(decision) != expected:
        raise ValueError("LEGACY_MANIFEST_DIGEST_MISMATCH")
    return decision


def _extract_fills(
    envelopes: tuple[LegacyCycleEnvelope, ...],
) -> tuple[Mapping[str, object], ...]:
    fills: dict[str, Mapping[str, object]] = {}

    def add(fill: object) -> None:
        if not isinstance(fill, Mapping):
            return
        fill_id = fill.get("fill_id")
        if not isinstance(fill_id, str) or not fill_id:
            return
        prior = fills.get(fill_id)
        if prior is not None and prior != fill:
            raise ValueError("A_REPLAYED_V1_FILL_CONFLICT")
        fills[fill_id] = fill

    for envelope in envelopes:
        market_fills = envelope.market_execution.get("fills", ())
        if isinstance(market_fills, list):
            for fill in market_fills:
                add(fill)
        chaos_results = envelope.chaos_execution.get("results", ())
        if isinstance(chaos_results, list):
            for result in chaos_results:
                if isinstance(result, Mapping):
                    add(result.get("fill"))
        execution = envelope.validated_decision
        # The actual applied execution lives alongside validated_decision in
        # decision.json.  LegacyCycleEnvelope intentionally exposes the
        # validated action and source digests, so load the committed result
        # from the source tree only through its digest-bound envelope extension
        # in `analysis["__unused__"]` is forbidden.  Decision-generated fills
        # are therefore recovered from the decision artifact below by the
        # evaluator's explicit run-root reader.
        del execution
    return tuple(fills[key] for key in sorted(fills))


def _all_committed_fills(
    run_root: Path,
    envelopes: tuple[LegacyCycleEnvelope, ...],
) -> tuple[Mapping[str, object], ...]:
    """Merge envelope-bound market/chaos fills and committed decision fills."""

    fills = {
        str(fill["fill_id"]): fill
        for fill in _extract_fills(envelopes)
    }
    for envelope in envelopes:
        decision = _load_bound_decision(run_root, envelope)
        results = decision.get("execution", {}).get("results", ())
        if not isinstance(results, list):
            raise ValueError("A_REPLAYED_V1_ACTION_STREAM_INVALID")
        for result in results:
            if not isinstance(result, Mapping):
                continue
            fill = result.get("fill")
            if not isinstance(fill, Mapping):
                continue
            fill_id = fill.get("fill_id")
            if not isinstance(fill_id, str):
                continue
            prior = fills.get(fill_id)
            if prior is not None and prior != fill:
                raise ValueError("A_REPLAYED_V1_FILL_CONFLICT")
            fills[fill_id] = fill
    return tuple(fills[key] for key in sorted(fills))


def _identified_accounting(
    run_root: Path,
    envelopes: tuple[LegacyCycleEnvelope, ...],
) -> tuple[IdentifiedAccounting, bool]:
    fills = _all_committed_fills(run_root, envelopes)
    fees = sum((_decimal(fill.get("fee_usdt", 0)) for fill in fills), Decimal(0))
    gross = Decimal(0)
    for fill in fills:
        closed = fill.get("closed_lots", ())
        if isinstance(closed, list):
            gross += sum(
                (
                    _decimal(item.get("realized_pnl_usdt", 0))
                    for item in closed
                    if isinstance(item, Mapping)
                ),
                Decimal(0),
            )
    drawdowns: list[Decimal] = []
    final_metrics: Mapping[str, object] | None = None
    action_receipts: list[str] = []
    for envelope in envelopes:
        decision = _load_bound_decision(run_root, envelope)
        metrics = decision.get("portfolio_metrics")
        if not isinstance(metrics, Mapping):
            raise ValueError("A_REPLAYED_V1_ACCOUNTING_MISSING")
        final_metrics = metrics
        drawdowns.append(_decimal(metrics["drawdown_fraction"]))
        action_receipts.append(str(decision["decision_receipt_digest"]))
    if final_metrics is None:
        raise ValueError("A_REPLAYED_V1_ACCOUNTING_MISSING")
    accounting = IdentifiedAccounting(
        initial_equity=Decimal("10000"),
        cash_balance=_decimal(final_metrics["cash_balance_usdt"]),
        realized_pnl_gross=_decimal(final_metrics["realized_pnl_usdt"]),
        fees=_decimal(final_metrics["fees_paid_usdt"]),
        net_realized_pnl=_decimal(final_metrics["net_realized_pnl_usdt"]),
        unrealized_pnl=_decimal(final_metrics["unrealized_pnl_usdt"]),
        total_net_pnl=_decimal(final_metrics["total_net_pnl_usdt"]),
        max_drawdown_fraction=max(drawdowns),
        fill_count=len(fills),
        funding_status=str(final_metrics["funding_accrual_status"]),
    )
    replay_match = (
        gross == accounting.realized_pnl_gross
        and fees == accounting.fees
        and gross - fees == accounting.total_net_pnl
        and accounting.unrealized_pnl == 0
        and len(action_receipts) == 24
        and len(set(action_receipts)) == 24
    )
    return accounting, replay_match


def _sndk_counterfactuals(
    run_root: Path,
    envelopes: tuple[LegacyCycleEnvelope, ...],
    cost_policy: FrozenCostPolicy,
) -> tuple[CounterfactualEvaluation, ...]:
    fills = _all_committed_fills(run_root, envelopes)
    entry = next(
        fill for fill in fills if fill.get("opened_lot_id") == "lot-000007"
    )
    actual_exit = next(
        fill
        for fill in fills
        if any(
            isinstance(item, Mapping)
            and item.get("lot_id") == "lot-000007"
            for item in fill.get("closed_lots", ())
        )
    )
    terminal_symbol = next(
        item
        for item in envelopes[-1].analysis["symbols"]
        if item["symbol"] == "SNDKUSDT"
    )
    terminal_mark = _decimal(
        terminal_symbol["measurement_snapshot"]["reference_price"]
    )
    entry_price = _decimal(entry["price"])
    quantity = _decimal(entry["quantity"])
    entry_fee = _decimal(entry["fee_usdt"])
    actual_net = _decimal(
        next(
            item
            for item in actual_exit["closed_lots"]
            if item["lot_id"] == "lot-000007"
        )["net_realized_pnl_usdt"]
    )
    terminal_mark_net = (
        (terminal_mark - entry_price) * quantity - entry_fee
    )
    hypothetical_fill = terminal_mark * (
        Decimal(1)
        - cost_policy.market_slippage_bps / Decimal("10000")
    )
    hypothetical_exit_fee = (
        hypothetical_fill * quantity * cost_policy.taker_fee_rate
    )
    hypothetical_exit_net = (
        (hypothetical_fill - entry_price) * quantity
        - entry_fee
        - hypothetical_exit_fee
    )
    opportunity_mark = terminal_mark_net - actual_net
    opportunity_exit = hypothetical_exit_net - actual_net
    return (
        CounterfactualEvaluation(
            policy_id="ORIGINAL_AGENT_RULES",
            identifiability="IDENTIFIED_CONTROL",
            result_status="EXACT",
            terminal_mark_net_pnl=actual_net,
            hypothetical_exit_net_pnl=actual_net,
            formula=None,
            notes=(
                "cycle-0016 actual exit; no later price used by the action",
            ),
        ),
        CounterfactualEvaluation(
            policy_id="STRATEGIC_THESIS_PRESERVATION",
            identifiability="SENSITIVITY_ONLY",
            result_status="NOT_A_FROZEN_V1_RULE",
            terminal_mark_net_pnl=terminal_mark_net,
            hypothetical_exit_net_pnl=hypothetical_exit_net,
            formula=(
                "lot-000007 retained to cycle-0024 terminal evaluation; "
                "terminal price is evaluation-only"
            ),
            notes=(
                f"mark opportunity difference={opportunity_mark}",
                f"hypothetical-exit opportunity difference={opportunity_exit}",
            ),
        ),
        CounterfactualEvaluation(
            policy_id="TACTICAL_REDUCTION_ONLY",
            identifiability="PARAMETRIC_ALPHA_UNKNOWN",
            result_status="NO_UNIQUE_RESULT",
            terminal_mark_net_pnl=None,
            hypothetical_exit_net_pnl=None,
            formula=(
                f"mark={terminal_mark_net}-{opportunity_mark}*alpha; "
                f"hypothetical_exit={hypothetical_exit_net}-"
                f"{opportunity_exit}*alpha; alpha in [0,1]"
            ),
            notes=(
                "V1 declared neither CORE/TACTICAL role nor tactical fraction",
            ),
        ),
    )


def evaluate_frozen_round1(
    *,
    run_root: Path,
    expected_run_id: str,
    expected_manifest_digest: str,
    cost_policy: FrozenCostPolicy,
    canonical_scenario_suite_digest: str,
    canonical_scenarios_passed: bool,
) -> Round1EvaluationResult:
    root = Path(run_root).resolve(strict=True)
    _require_digest(expected_manifest_digest, "EXPECTED_MANIFEST_DIGEST")
    _require_digest(cost_policy.policy_digest, "COST_POLICY_DIGEST")
    _require_digest(
        canonical_scenario_suite_digest,
        "CANONICAL_SCENARIO_SUITE_DIGEST",
    )
    adapter = LegacyV1Adapter(expected_run_id=expected_run_id)
    envelopes = tuple(
        adapter.load_cycle(root, cycle_id, expected_manifest_digest)
        for cycle_id in range(1, 25)
    )
    if tuple(item.cycle_id for item in envelopes) != tuple(
        f"cycle-{index:04d}" for index in range(1, 25)
    ):
        raise ValueError("LEGACY_CYCLE_OUT_OF_SCOPE")
    point_in_time_bundle_digest = canonical_digest(
        tuple(
            (
                envelope.cycle_id,
                envelope.analysis_committed_at,
                envelope.decision_committed_at,
                envelope.source_artifact_digests,
                envelope.integrity_verdict,
            )
            for envelope in envelopes
        )
    )
    chronology_digest = canonical_digest(
        tuple(
            (
                envelope.cycle_id,
                envelope.analysis.get("decision_at"),
                envelope.analysis_committed_at,
                envelope.decision_committed_at,
            )
            for envelope in envelopes
        )
    )
    accounting, replay_match = _identified_accounting(root, envelopes)
    unknown_fields = (
        "strategic_episode_state",
        "core_tactical_lot_role",
        "reentry_contract",
        "geometry_lifecycle",
        "complete_candidate_proposal_stream",
    )
    arms = tuple(
        ArmEvaluation(
            arm_id=arm_id,
            enabled_features=features,
            point_in_time_bundle_digest=point_in_time_bundle_digest,
            candidate_proposal_stream_digest=None,
            functional_status=(
                "PASS_SYNTHETIC_CONTRACT"
                if canonical_scenarios_passed
                else "FAIL_SYNTHETIC_CONTRACT"
            ),
            economic_status=(
                "IDENTIFIED_OBSERVED"
                if arm_id == "A"
                else "UNKNOWN_LEGACY_UNDECLARED"
            ),
            accounting=accounting if arm_id == "A" else None,
            primary_path_capture=None,
            unknown_fields=() if arm_id == "A" else unknown_fields,
        )
        for arm_id, features in ARMS.items()
    )
    functional_gate = (
        "PASS_ENGINEERING"
        if canonical_scenarios_passed and replay_match
        else "FAIL_ENGINEERING"
    )
    behavior_gate = "INCONCLUSIVE_NOT_IDENTIFIABLE"
    reasons = [
        "COMPLETE_CANDIDATE_PROPOSAL_STREAM_UNKNOWN",
        "V2_STRATEGIC_STATE_NOT_PRESENT_IN_V1",
        "I_ARM_ECONOMIC_RESULT_NOT_IDENTIFIABLE",
        "FORMAL_PRIMARY_PATH_CAPTURE_COMPARATOR_NOT_FROZEN_EX_ANTE",
    ]
    if not canonical_scenarios_passed:
        reasons.append("CANONICAL_SCENARIO_GATE_FAILED")
    if not replay_match:
        reasons.append("A_REPLAYED_V1_ACCOUNTING_MISMATCH")
    terminal_status = (
        "FAIL_REPAIR_AND_RESTART_ROUND_1"
        if functional_gate == "FAIL_ENGINEERING"
        else "INCONCLUSIVE_NO_ADVANCE"
    )
    counterfactuals = _sndk_counterfactuals(
        root,
        envelopes,
        cost_policy,
    )
    digest_payload = {
        "legacy_run_id": expected_run_id,
        "cycles": tuple(item.cycle_id for item in envelopes),
        "point_in_time_bundle_digest": point_in_time_bundle_digest,
        "chronology_digest": chronology_digest,
        "cost_policy_digest": cost_policy.policy_digest,
        "proposal_stream_status": "UNKNOWN_LEGACY_UNDECLARED",
        "a": asdict(accounting),
        "a_replayed_accounting_match": replay_match,
        "arms": tuple(asdict(item) for item in arms),
        "counterfactuals": tuple(
            asdict(item) for item in counterfactuals
        ),
        "canonical_scenario_suite_digest": (
            canonical_scenario_suite_digest
        ),
        "canonical_scenarios_passed": canonical_scenarios_passed,
        "functional_gate": functional_gate,
        "behavior_gate": behavior_gate,
        "terminal_status": terminal_status,
        "reason_codes": tuple(reasons),
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return Round1EvaluationResult(
        legacy_run_id=expected_run_id,
        cycle_ids=tuple(item.cycle_id for item in envelopes),
        point_in_time_bundle_digest=point_in_time_bundle_digest,
        chronology_digest=chronology_digest,
        cost_policy_digest=cost_policy.policy_digest,
        proposal_stream_status="UNKNOWN_LEGACY_UNDECLARED",
        candidate_proposal_stream_digest=None,
        a_observed=accounting,
        a_replayed_accounting_match=replay_match,
        a_replayed_action_fill_identity_match=replay_match,
        arms=arms,
        counterfactuals=counterfactuals,
        canonical_scenario_suite_digest=canonical_scenario_suite_digest,
        canonical_scenarios_passed=canonical_scenarios_passed,
        hard_functional_gate_status=functional_gate,
        behavior_economic_gate_status=behavior_gate,
        terminal_status=terminal_status,
        terminal_reason_codes=tuple(reasons),
        result_digest=canonical_digest(digest_payload),
    )
