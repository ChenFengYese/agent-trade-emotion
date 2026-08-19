"""Deterministic equal-budget single-Agent versus cluster gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext

from ..domain.contracts.canonical import canonical_digest


TOPOLOGY_IDS = (
    "SINGLE_STRONG",
    "CLUSTER_POST_PROPOSAL",
    "CLUSTER_BLIND",
)


@dataclass(frozen=True, slots=True)
class TopologyObservation:
    session_id: str
    topology_id: str
    input_digest: str
    model_class: str
    total_budget_digest: str
    dynamic_candidate_coverage: Decimal
    material_challenge_coverage: Decimal
    action_quality_score: Decimal
    safety_state_pit_authority_failures: int
    role_overreach_failures: int
    model_calls: int
    tokens: int
    latency_ms: int
    cost_microunits: int | None
    timeout_count: int
    missing_role_count: int

    def __post_init__(self) -> None:
        scores = (
            self.dynamic_candidate_coverage,
            self.material_challenge_coverage,
            self.action_quality_score,
        )
        counts = (
            self.safety_state_pit_authority_failures,
            self.role_overreach_failures,
            self.model_calls,
            self.tokens,
            self.latency_ms,
            self.timeout_count,
            self.missing_role_count,
        )
        if (
            not isinstance(self.session_id, str)
            or not self.session_id
            or self.topology_id not in TOPOLOGY_IDS
            or not isinstance(self.input_digest, str)
            or not self.input_digest
            or not isinstance(self.model_class, str)
            or not self.model_class
            or not isinstance(self.total_budget_digest, str)
            or not self.total_budget_digest
            or any(
                not isinstance(value, Decimal) or not value.is_finite()
                for value in scores
            )
            or any(
                value < 0 or value > 1
                for value in scores
            )
            or any(type(value) is not int or value < 0 for value in counts)
            or (
                self.cost_microunits is not None
                and (
                    type(self.cost_microunits) is not int
                    or self.cost_microunits < 0
                )
            )
        ):
            raise ValueError("TOPOLOGY_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class TopologyArmSummary:
    topology_id: str
    paired_session_count: int
    mean_dynamic_candidate_coverage: Decimal | None
    mean_material_challenge_coverage: Decimal | None
    mean_action_quality_score: Decimal | None
    action_quality_delta_vs_single: Decimal | None
    action_quality_interval_lower: Decimal | None
    action_quality_interval_upper: Decimal | None
    safety_state_pit_authority_failures: int | None
    role_overreach_failures: int | None
    model_calls: int | None
    tokens: int | None
    latency_ms: int | None
    cost_microunits: int | None
    timeout_count: int | None
    missing_role_count: int | None


@dataclass(frozen=True, slots=True)
class TopologyEvaluationResult:
    compared_topology_ids: tuple[str, ...]
    minimum_paired_sessions: int
    observed_complete_paired_sessions: int
    equal_input_model_budget_verified: bool
    interval_method: str
    interval_alpha: Decimal
    arm_summaries: tuple[TopologyArmSummary, ...]
    selection_status: str
    selected_topology_id: str
    reason_codes: tuple[str, ...]
    result_digest: str
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def _paired_hoeffding_interval(
    differences: tuple[Decimal, ...],
    *,
    alpha: Decimal,
) -> tuple[Decimal, Decimal]:
    """One-sided distribution-free bound for scores in [-1, 1]."""

    with localcontext() as context:
        context.prec = 50
        mean = _mean(differences)
        half_width = (
            Decimal(2) * (Decimal(1) / alpha).ln()
            / Decimal(len(differences))
        ).sqrt()
        return (
            max(Decimal("-1"), mean - half_width),
            min(Decimal("1"), mean + half_width),
        )


def _unknown_summary(topology_id: str) -> TopologyArmSummary:
    return TopologyArmSummary(
        topology_id=topology_id,
        paired_session_count=0,
        mean_dynamic_candidate_coverage=None,
        mean_material_challenge_coverage=None,
        mean_action_quality_score=None,
        action_quality_delta_vs_single=None,
        action_quality_interval_lower=None,
        action_quality_interval_upper=None,
        safety_state_pit_authority_failures=None,
        role_overreach_failures=None,
        model_calls=None,
        tokens=None,
        latency_ms=None,
        cost_microunits=None,
        timeout_count=None,
        missing_role_count=None,
    )


def evaluate_agent_topologies(
    observations: tuple[TopologyObservation, ...],
    *,
    minimum_paired_sessions: int = 32,
    interval_alpha: Decimal = Decimal("0.05"),
    compared_topology_ids: tuple[str, ...] = TOPOLOGY_IDS,
) -> TopologyEvaluationResult:
    if (
        minimum_paired_sessions < 32
        or not (Decimal(0) < interval_alpha < Decimal(1))
        or len(compared_topology_ids) < 2
        or compared_topology_ids[0] != "SINGLE_STRONG"
        or len(set(compared_topology_ids)) != len(compared_topology_ids)
        or not set(compared_topology_ids).issubset(TOPOLOGY_IDS)
    ):
        raise ValueError("TOPOLOGY_EVALUATION_POLICY_INVALID")

    by_session: dict[str, dict[str, TopologyObservation]] = {}
    duplicate = False
    for observation in observations:
        bucket = by_session.setdefault(observation.session_id, {})
        if observation.topology_id in bucket:
            duplicate = True
        bucket[observation.topology_id] = observation
    complete_ids = tuple(
        sorted(
            session_id
            for session_id, bucket in by_session.items()
            if set(bucket) == set(compared_topology_ids)
        )
    )
    binding_mismatch = duplicate
    for session_id in complete_ids:
        bucket = by_session[session_id]
        bindings = {
            (
                item.input_digest,
                item.model_class,
                item.total_budget_digest,
            )
            for item in bucket.values()
        }
        if len(bindings) != 1:
            binding_mismatch = True
            break
    equal = bool(complete_ids) and not binding_mismatch

    reasons: list[str] = []
    if duplicate:
        reasons.append("DUPLICATE_TOPOLOGY_OBSERVATION")
    if not equal:
        reasons.append("EQUAL_INPUT_MODEL_BUDGET_NOT_VERIFIED")
    if len(complete_ids) < minimum_paired_sessions:
        reasons.append("MINIMUM_32_PAIRED_SESSIONS_NOT_MET")

    if binding_mismatch or len(complete_ids) < minimum_paired_sessions:
        summaries = tuple(
            _unknown_summary(item) for item in compared_topology_ids
        )
        selection_status = (
            "FAIL_INVALID_EXPERIMENT"
            if binding_mismatch
            else "INCONCLUSIVE_USE_SINGLE_AGENT"
        )
        payload = {
            "compared_topology_ids": compared_topology_ids,
            "minimum_paired_sessions": minimum_paired_sessions,
            "observed_complete_paired_sessions": len(complete_ids),
            "equal_input_model_budget_verified": equal,
            "interval_method": "PAIRED_HOEFFDING_SCORE_RANGE_MINUS1_PLUS1",
            "interval_alpha": interval_alpha,
            "arm_summaries": tuple(asdict(item) for item in summaries),
            "selection_status": selection_status,
            "selected_topology_id": "SINGLE_STRONG",
            "reason_codes": tuple(reasons),
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        }
        return TopologyEvaluationResult(
            compared_topology_ids=compared_topology_ids,
            minimum_paired_sessions=minimum_paired_sessions,
            observed_complete_paired_sessions=len(complete_ids),
            equal_input_model_budget_verified=equal,
            interval_method=payload["interval_method"],
            interval_alpha=interval_alpha,
            arm_summaries=summaries,
            selection_status=selection_status,
            selected_topology_id="SINGLE_STRONG",
            reason_codes=tuple(reasons),
            result_digest=canonical_digest(payload),
        )

    ordered = {
        topology_id: tuple(
            by_session[session_id][topology_id]
            for session_id in complete_ids
        )
        for topology_id in compared_topology_ids
    }
    single = ordered["SINGLE_STRONG"]
    summaries: list[TopologyArmSummary] = []
    for topology_id in compared_topology_ids:
        rows = ordered[topology_id]
        coverage = _mean(
            tuple(item.dynamic_candidate_coverage for item in rows)
        )
        challenge = _mean(
            tuple(item.material_challenge_coverage for item in rows)
        )
        quality = _mean(tuple(item.action_quality_score for item in rows))
        if topology_id == "SINGLE_STRONG":
            quality_delta = Decimal(0)
            lower = Decimal(0)
            upper = Decimal(0)
        else:
            differences = tuple(
                row.action_quality_score - base.action_quality_score
                for row, base in zip(rows, single, strict=True)
            )
            quality_delta = _mean(differences)
            lower, upper = _paired_hoeffding_interval(
                differences,
                alpha=interval_alpha,
            )
        summaries.append(
            TopologyArmSummary(
                topology_id=topology_id,
                paired_session_count=len(rows),
                mean_dynamic_candidate_coverage=coverage,
                mean_material_challenge_coverage=challenge,
                mean_action_quality_score=quality,
                action_quality_delta_vs_single=quality_delta,
                action_quality_interval_lower=lower,
                action_quality_interval_upper=upper,
                safety_state_pit_authority_failures=sum(
                    item.safety_state_pit_authority_failures
                    for item in rows
                ),
                role_overreach_failures=sum(
                    item.role_overreach_failures for item in rows
                ),
                model_calls=sum(item.model_calls for item in rows),
                tokens=sum(item.tokens for item in rows),
                latency_ms=sum(item.latency_ms for item in rows),
                cost_microunits=(
                    sum(
                        item.cost_microunits
                        for item in rows
                        if item.cost_microunits is not None
                    )
                    if all(
                        item.cost_microunits is not None for item in rows
                    )
                    else None
                ),
                timeout_count=sum(item.timeout_count for item in rows),
                missing_role_count=sum(
                    item.missing_role_count for item in rows
                ),
            )
        )
    by_topology = {item.topology_id: item for item in summaries}
    single_summary = by_topology["SINGLE_STRONG"]
    qualifying: list[TopologyArmSummary] = []
    for topology_id in compared_topology_ids[1:]:
        candidate = by_topology[topology_id]
        coverage_delta = (
            candidate.mean_dynamic_candidate_coverage
            - single_summary.mean_dynamic_candidate_coverage
        )
        challenge_delta = (
            candidate.mean_material_challenge_coverage
            - single_summary.mean_material_challenge_coverage
        )
        coverage_or_challenge = (
            coverage_delta >= Decimal("0.05")
            and challenge_delta >= 0
        ) or (
            challenge_delta >= Decimal("0.10")
            and coverage_delta >= 0
        )
        no_additional_failures = (
            candidate.safety_state_pit_authority_failures
            <= single_summary.safety_state_pit_authority_failures
            and candidate.role_overreach_failures
            <= single_summary.role_overreach_failures
            and candidate.missing_role_count == 0
        )
        if (
            coverage_or_challenge
            and no_additional_failures
            and candidate.action_quality_interval_lower >= 0
        ):
            qualifying.append(candidate)

    if qualifying:
        selected = max(
            qualifying,
            key=lambda item: (
                item.action_quality_interval_lower,
                item.mean_dynamic_candidate_coverage,
                item.mean_material_challenge_coverage,
                item.topology_id,
            ),
        )
        selection_status = "CLUSTER_SELECTED"
        selected_topology = selected.topology_id
    else:
        clusters = tuple(
            by_topology[item] for item in compared_topology_ids[1:]
        )
        single_better = all(
            single_summary.mean_dynamic_candidate_coverage
            >= item.mean_dynamic_candidate_coverage
            and single_summary.mean_material_challenge_coverage
            >= item.mean_material_challenge_coverage
            and single_summary.mean_action_quality_score
            >= item.mean_action_quality_score
            for item in clusters
        ) and any(
            single_summary.mean_dynamic_candidate_coverage
            > item.mean_dynamic_candidate_coverage
            or single_summary.mean_material_challenge_coverage
            > item.mean_material_challenge_coverage
            or single_summary.mean_action_quality_score
            > item.mean_action_quality_score
            for item in clusters
        )
        selection_status = (
            "SINGLE_AGENT_SELECTED"
            if single_better
            else "INCONCLUSIVE_USE_SINGLE_AGENT"
        )
        selected_topology = "SINGLE_STRONG"
        if not single_better:
            reasons.append("PAIRED_INTERVAL_OR_IMPROVEMENT_GATE_UNRESOLVED")

    payload = {
        "compared_topology_ids": compared_topology_ids,
        "minimum_paired_sessions": minimum_paired_sessions,
        "observed_complete_paired_sessions": len(complete_ids),
        "equal_input_model_budget_verified": True,
        "interval_method": "PAIRED_HOEFFDING_SCORE_RANGE_MINUS1_PLUS1",
        "interval_alpha": interval_alpha,
        "arm_summaries": tuple(asdict(item) for item in summaries),
        "selection_status": selection_status,
        "selected_topology_id": selected_topology,
        "reason_codes": tuple(reasons),
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return TopologyEvaluationResult(
        compared_topology_ids=compared_topology_ids,
        minimum_paired_sessions=minimum_paired_sessions,
        observed_complete_paired_sessions=len(complete_ids),
        equal_input_model_budget_verified=True,
        interval_method=payload["interval_method"],
        interval_alpha=interval_alpha,
        arm_summaries=tuple(summaries),
        selection_status=selection_status,
        selected_topology_id=selected_topology,
        reason_codes=tuple(reasons),
        result_digest=canonical_digest(payload),
    )


__all__ = [
    "TOPOLOGY_IDS",
    "TopologyArmSummary",
    "TopologyEvaluationResult",
    "TopologyObservation",
    "evaluate_agent_topologies",
]
