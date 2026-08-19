"""Pure, fail-closed G2 development evaluator for counterfactual market paths.

It intentionally has no file, protocol, execution, or CLI dependency.  Its
utility is an observed market-path counterfactual net of declared costs, never
an execution PnL or a trading authorization.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from .decision import MarketOutcome
from .research import LabeledObservation, OUTCOMES, RegularizedMultinomialLogistic, evaluate_predictions, purged_walk_forward
from .types import parse_utc


class G2EvaluationError(ValueError):
    """The supplied evidence violates the frozen G2 input boundary."""


@dataclass(frozen=True)
class FeatureTerm:
    """A declared raw feature, state indicator, or deterministic product."""

    name: str
    transform: str = "IDENTITY"
    sources: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AblationPair:
    hypothesis_id: str
    candidate_group: str
    control_group: str


@dataclass(frozen=True)
class G2EvaluatorPolicy:
    as_of: datetime
    folds: int
    embargo_seconds: int
    feature_groups: Mapping[str, Tuple[FeatureTerm, ...]]
    ablation_pairs: Mapping[str, AblationPair]
    utility_feature_group: str = "full"
    calibration_fraction: float = 0.20
    min_effective_episodes: int = 40
    min_effective_episodes_per_state: int = 5
    required_states: Tuple[str, ...] = ()
    min_utc_days: int = 7
    bootstrap_iterations: int = 400
    bootstrap_seed: int = 20260722
    base_round_trip_cost_bps: float = 10.0
    stress_round_trip_cost_bps: float = 20.0
    tp_gross_return_bps: float = 20.0
    sl_gross_return_bps: float = -12.0
    relative_logloss_improvement_min: float = 0.02
    min_successful_folds: int = 1
    max_day_concentration: float = 0.40
    max_state_concentration: float = 0.40
    max_direction_concentration: float = 0.70
    required_sides: Tuple[str, ...] = ()
    min_effective_episodes_per_side: int = 1
    min_effective_episodes_per_state_per_side: int = 1
    separate_models: bool = False


@dataclass(frozen=True)
class G2Row:
    episode_id: str
    decision_at: datetime
    label_end_at: datetime
    side: str
    state_id: str
    features: Dict[str, float]
    outcome: MarketOutcome
    gross_return_bps: float


_HYPOTHESES = ("H-001", "H-002", "H-003", "H-004")
_OUTCOME_NAMES = tuple(outcome.value for outcome in OUTCOMES)


def _finite(value: Any, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise G2EvaluationError("%s must be numeric" % name) from exc
    if not math.isfinite(numeric):
        raise G2EvaluationError("%s must be finite" % name)
    return numeric


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise G2EvaluationError("%s must be an ISO-8601 timestamp" % name)
    try:
        return parse_utc(value)
    except ValueError as exc:
        raise G2EvaluationError("%s must be an ISO-8601 timestamp" % name) from exc


def _validate_policy(policy: G2EvaluatorPolicy) -> None:
    if policy.as_of.tzinfo is None:
        raise G2EvaluationError("policy as_of must include timezone")
    if policy.folds < 1 or policy.embargo_seconds < 0:
        raise G2EvaluationError("policy folds/embargo are invalid")
    if not 0 < policy.calibration_fraction < 1:
        raise G2EvaluationError("policy calibration_fraction must be in (0, 1)")
    if policy.min_effective_episodes < 1 or policy.min_effective_episodes_per_state < 1 or policy.min_utc_days < 1:
        raise G2EvaluationError("policy minimums must be positive")
    if policy.bootstrap_iterations < 1:
        raise G2EvaluationError("policy bootstrap_iterations must be positive")
    if not policy.feature_groups or not policy.ablation_pairs:
        raise G2EvaluationError("policy requires feature groups and ablation pairs")
    if set(policy.ablation_pairs) != set(_HYPOTHESES):
        raise G2EvaluationError("policy requires one declared ablation pair for H-001 through H-004")
    if policy.utility_feature_group not in policy.feature_groups:
        raise G2EvaluationError("policy utility_feature_group is not declared")
    for name, terms in policy.feature_groups.items():
        if not name or not terms:
            raise G2EvaluationError("each feature group must be non-empty")
        for term in terms:
            if not term.name or term.transform not in {"IDENTITY", "PRODUCT", "STATE_INDICATOR"}:
                raise G2EvaluationError("feature term is invalid")
            sources = term.sources or ((term.name,) if term.transform == "IDENTITY" else ())
            if (term.transform == "IDENTITY" and len(sources) != 1) or (term.transform == "STATE_INDICATOR" and len(sources) != 1) or (term.transform == "PRODUCT" and len(sources) < 2) or any(not source for source in sources):
                raise G2EvaluationError("feature term sources are invalid")
    for hypothesis_id, pair in policy.ablation_pairs.items():
        if pair.hypothesis_id != hypothesis_id or pair.candidate_group not in policy.feature_groups or pair.control_group not in policy.feature_groups:
            raise G2EvaluationError("ablation pair is invalid")
        # Output names are only column labels.  Compare the actual transforms
        # and sources so a renamed duplicate cannot masquerade as an ablation.
        candidate_signature = tuple((term.transform, term.sources or ((term.name,) if term.transform == "IDENTITY" else ())) for term in policy.feature_groups[pair.candidate_group])
        control_signature = tuple((term.transform, term.sources or ((term.name,) if term.transform == "IDENTITY" else ())) for term in policy.feature_groups[pair.control_group])
        if candidate_signature == control_signature:
            raise G2EvaluationError("ablation candidate and control groups must differ")
    if not policy.required_states or len(set(policy.required_states)) != len(policy.required_states):
        raise G2EvaluationError("policy required_states must be non-empty and unique")
    for value, name in ((policy.base_round_trip_cost_bps, "base cost"), (policy.stress_round_trip_cost_bps, "stress cost"), (policy.tp_gross_return_bps, "TP return"), (policy.sl_gross_return_bps, "SL return")):
        _finite(value, name)
    if policy.base_round_trip_cost_bps < 0 or policy.stress_round_trip_cost_bps < policy.base_round_trip_cost_bps:
        raise G2EvaluationError("policy round-trip costs are invalid")
    if policy.tp_gross_return_bps <= 0 or policy.sl_gross_return_bps >= 0:
        raise G2EvaluationError("policy TP proxy must be positive and SL proxy must be negative")
    for value, name in ((policy.relative_logloss_improvement_min, "relative improvement"), (policy.max_day_concentration, "day concentration"), (policy.max_state_concentration, "state concentration"), (policy.max_direction_concentration, "direction concentration")):
        _finite(value, name)
    if any(not 0 < value <= 1 for value in (policy.max_day_concentration, policy.max_state_concentration, policy.max_direction_concentration)):
        raise G2EvaluationError("policy concentration limits must be in (0, 1]")
    if policy.relative_logloss_improvement_min <= 0:
        raise G2EvaluationError("policy relative_logloss_improvement_min must be positive")
    if not isinstance(policy.min_successful_folds, int) or not 1 <= policy.min_successful_folds <= policy.folds:
        raise G2EvaluationError("policy min_successful_folds must be an integer in [1, folds]")
    if policy.separate_models and tuple(sorted(policy.required_sides)) != ("BUY", "SELL"):
        raise G2EvaluationError("separate G2 models require BUY and SELL")
    if policy.separate_models and (policy.min_effective_episodes_per_side < 1 or policy.min_effective_episodes_per_state_per_side < 1):
        raise G2EvaluationError("separate G2 side minimums must be positive")


def parse_g2_rows(rows: Iterable[Mapping[str, Any]], *, policy: G2EvaluatorPolicy) -> Tuple[G2Row, ...]:
    """Validate the strict label boundary before any metric is calculated."""
    _validate_policy(policy)
    parsed = []
    seen = set()
    as_of = policy.as_of.astimezone(timezone.utc)
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise G2EvaluationError("row %d must be an object" % index)
        if raw.get("availability_kind") != "ACTUAL" or raw.get("censored") is not False or raw.get("stage") != "ENTER_PROBE":
            raise G2EvaluationError("row %d is not an ACTUAL uncensored ENTER_PROBE label" % index)
        episode_id = raw.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id or episode_id in seen:
            raise G2EvaluationError("row %d has a missing or duplicate episode_id" % index)
        seen.add(episode_id)
        decision_at = _utc(raw.get("decision_at"), "decision_at")
        label_end_at = _utc(raw.get("label_end_at"), "label_end_at")
        if label_end_at < decision_at or decision_at > as_of or label_end_at > as_of:
            raise G2EvaluationError("row %d has future or invalid label times" % index)
        side = raw.get("side")
        state_id = raw.get("state_id")
        if side not in {"BUY", "SELL"} or not isinstance(state_id, str) or not state_id:
            raise G2EvaluationError("row %d has unknown side or state" % index)
        if policy.required_states and state_id not in policy.required_states:
            raise G2EvaluationError("row %d state is outside the declared policy" % index)
        try:
            outcome = MarketOutcome(raw.get("outcome"))
        except (TypeError, ValueError) as exc:
            raise G2EvaluationError("row %d has unknown outcome" % index) from exc
        features = raw.get("features")
        if not isinstance(features, Mapping) or not features:
            raise G2EvaluationError("row %d requires a non-empty feature object" % index)
        finite_features = {str(name): _finite(value, "row %d feature %s" % (index, name)) for name, value in features.items()}
        parsed.append(G2Row(
            episode_id=episode_id, decision_at=decision_at, label_end_at=label_end_at, side=side,
            state_id=state_id, features=finite_features, outcome=outcome,
            gross_return_bps=_finite(raw.get("gross_return_bps"), "row %d gross_return_bps" % index),
        ))
    if not parsed:
        raise G2EvaluationError("G2 evaluation requires at least one row")
    return tuple(sorted(parsed, key=lambda item: (item.decision_at, item.episode_id)))


def _term_value(row: G2Row, term: FeatureTerm) -> float:
    sources = term.sources or ((term.name,) if term.transform == "IDENTITY" else ())
    if term.transform == "STATE_INDICATOR":
        return 1.0 if row.state_id == sources[0] else 0.0
    values = []
    missing = []
    for source in sources:
        if source.startswith("STATE:"):
            values.append(1.0 if row.state_id == source.split(":", 1)[1] else 0.0)
        elif source in row.features:
            values.append(row.features[source])
        else:
            missing.append(source)
    if missing:
        raise KeyError(",".join(missing))
    if term.transform == "IDENTITY":
        return values[0]
    product = 1.0
    for value in values:
        product *= value
    return product


def _observations(rows: Sequence[G2Row], terms: Sequence[FeatureTerm]) -> Tuple[LabeledObservation, ...]:
    output = []
    for row in rows:
        features = {term.name: _term_value(row, term) for term in terms}
        output.append(LabeledObservation(row.episode_id, row.decision_at, row.label_end_at, features, row.outcome, row.state_id))
    return tuple(output)


def _empirical_forecast(rows: Sequence[LabeledObservation]) -> Tuple[float, float, float, float]:
    counts = Counter(row.outcome for row in rows)
    total = len(rows)
    return tuple(counts[outcome] / total for outcome in OUTCOMES)  # type: ignore[return-value]


def _forecast_values(forecast) -> Tuple[float, float, float, float]:
    return (float(forecast.tp), float(forecast.sl), float(forecast.structure_exit), float(forecast.timeout))


def _forecast_from_values(values: Tuple[float, float, float, float]):
    from decimal import Decimal
    from .decision import OutcomeForecast
    return OutcomeForecast(*(Decimal(str(value)) for value in values))


def _temperature_scale(values: Tuple[float, float, float, float], temperature: float) -> Tuple[float, float, float, float]:
    """Deterministic scalar multinomial calibration from pre-calibration probabilities."""
    powered = [max(value, 1e-15) ** (1.0 / temperature) for value in values]
    total = sum(powered)
    return tuple(value / total for value in powered)  # type: ignore[return-value]


def _fit_temperature(actual: Sequence[MarketOutcome], probabilities: Sequence[Tuple[float, float, float, float]]) -> float:
    if not actual or len(actual) != len(probabilities):
        raise G2EvaluationError("calibration requires aligned non-empty rows")
    outcome_index = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    # A fixed grid avoids optimizer/version variance and uses calibration rows
    # only; test rows are never consulted to select the temperature.
    candidates = tuple(round(0.50 + step * 0.05, 2) for step in range(51))
    losses = []
    for temperature in candidates:
        loss = -mean(math.log(max(_temperature_scale(values, temperature)[outcome_index[target]], 1e-15)) for target, values in zip(actual, probabilities))
        losses.append((loss, abs(temperature - 1.0), temperature))
    return min(losses)[2]


def _diagnostics(actual: Sequence[MarketOutcome], probabilities: Sequence[Tuple[float, float, float, float]]) -> Dict[str, Any]:
    metrics = evaluate_predictions(zip(actual, (_forecast_from_values(item) for item in probabilities)))
    confusion = {outcome.value: {other.value: 0 for other in OUTCOMES} for outcome in OUTCOMES}
    recall = {}
    decile = [[{"count": 0, "probability_sum": 0.0, "actual_sum": 0.0} for _ in range(10)] for _ in OUTCOMES]
    for target, values in zip(actual, probabilities):
        predicted = OUTCOMES[max(range(len(values)), key=lambda index: values[index])]
        confusion[target.value][predicted.value] += 1
        for index, probability in enumerate(values):
            bucket = min(9, int(probability * 10))
            cell = decile[index][bucket]
            cell["count"] += 1
            cell["probability_sum"] += probability
            cell["actual_sum"] += 1.0 if target == OUTCOMES[index] else 0.0
    ece = 0.0
    rendered_deciles = {}
    total = max(1, len(actual) * len(OUTCOMES))
    for index, outcome in enumerate(OUTCOMES):
        rendered = []
        for bucket, cell in enumerate(decile[index]):
            count = cell["count"]
            mean_probability = cell["probability_sum"] / count if count else None
            frequency = cell["actual_sum"] / count if count else None
            if count:
                ece += (count / total) * abs(mean_probability - frequency)
            rendered.append({"decile": bucket, "count": count, "mean_probability": mean_probability, "observed_frequency": frequency})
        rendered_deciles[outcome.value] = rendered
        denominator = sum(confusion[outcome.value].values())
        recall[outcome.value] = confusion[outcome.value][outcome.value] / denominator if denominator else None
    return {
        "observations": metrics.observations, "log_loss": metrics.log_loss, "multiclass_brier": metrics.multiclass_brier,
        "accuracy": metrics.accuracy, "one_vs_rest_ece": ece, "confusion": confusion, "recall_by_class": recall,
        "probability_deciles_one_vs_rest": rendered_deciles,
    }


def _fold_models(rows: Sequence[G2Row], policy: G2EvaluatorPolicy, candidate_terms: Sequence[FeatureTerm], control_terms: Sequence[FeatureTerm]) -> Tuple[Tuple[Dict[str, Any], ...], Tuple[Tuple[G2Row, Tuple[float, float, float, float], Tuple[float, float, float, float]], ...]]:
    candidate = _observations(rows, candidate_terms)
    control = _observations(rows, control_terms)
    by_id = {row.episode_id: row for row in rows}
    candidate_folds = purged_walk_forward(candidate, folds=policy.folds, embargo=timedelta(seconds=policy.embargo_seconds))
    control_folds = purged_walk_forward(control, folds=policy.folds, embargo=timedelta(seconds=policy.embargo_seconds))
    if len(candidate_folds) != len(control_folds):
        raise G2EvaluationError("feature groups produced incompatible folds")
    output, utility_predictions = [], []
    for index, (candidate_fold, control_fold) in enumerate(zip(candidate_folds, control_folds)):
        if tuple(row.episode_id for row in candidate_fold.train) != tuple(row.episode_id for row in control_fold.train):
            raise G2EvaluationError("feature groups produced incompatible training rows")
        calibration_start = max(1, int(len(candidate_fold.train) * (1 - policy.calibration_fraction)))
        calibration_candidate = candidate_fold.train[calibration_start:]
        calibration_control = control_fold.train[calibration_start:]
        calibration_at = calibration_candidate[0].decision_at
        # A calibration label may not leak back into fitting.  The fit segment
        # ends before the first calibration decision and its complete label.
        fit_candidate = tuple(row for row in candidate_fold.train[:calibration_start] if row.label_end_at <= calibration_at)
        fit_control = tuple(row for row in control_fold.train[:calibration_start] if row.label_end_at <= calibration_at)
        if not fit_candidate or not calibration_candidate:
            raise G2EvaluationError("fold has insufficient temporally separated fit/calibration rows")
        candidate_model = RegularizedMultinomialLogistic(tuple(item for item in fit_candidate[0].features)).fit(fit_candidate)
        control_model = RegularizedMultinomialLogistic(tuple(item for item in fit_control[0].features)).fit(fit_control)
        empirical = _empirical_forecast(fit_candidate)
        candidate_test_raw = [_forecast_values(candidate_model.predict(row.features)) for row in candidate_fold.test]
        control_test_raw = [_forecast_values(control_model.predict(row.features)) for row in control_fold.test]
        empirical_test = [empirical] * len(candidate_fold.test)
        candidate_calibration_raw = [_forecast_values(candidate_model.predict(row.features)) for row in calibration_candidate]
        control_calibration_raw = [_forecast_values(control_model.predict(row.features)) for row in calibration_control]
        actual_test = [row.outcome for row in candidate_fold.test]
        actual_calibration = [row.outcome for row in calibration_candidate]
        candidate_temperature = _fit_temperature(actual_calibration, candidate_calibration_raw)
        control_temperature = _fit_temperature([row.outcome for row in calibration_control], control_calibration_raw)
        candidate_test = [_temperature_scale(values, candidate_temperature) for values in candidate_test_raw]
        control_test = [_temperature_scale(values, control_temperature) for values in control_test_raw]
        candidate_calibration = [_temperature_scale(values, candidate_temperature) for values in candidate_calibration_raw]
        control_calibration = [_temperature_scale(values, control_temperature) for values in control_calibration_raw]
        candidate_metrics = _diagnostics(actual_test, candidate_test)
        control_metrics = _diagnostics(actual_test, control_test)
        empirical_metrics = _diagnostics(actual_test, empirical_test)
        candidate_calibration_metrics = _diagnostics(actual_calibration, candidate_calibration)
        control_calibration_metrics = _diagnostics([row.outcome for row in calibration_control], control_calibration)
        output.append({
            "fold": index, "fit_observations": len(fit_candidate), "calibration_observations": len(calibration_candidate), "test_observations": len(candidate_fold.test),
            "fit_latest_label_end_at": fit_candidate[-1].label_end_at.isoformat(), "calibration_start_at": calibration_candidate[0].decision_at.isoformat(),
            "calibration_latest_label_end_at": calibration_candidate[-1].label_end_at.isoformat(), "test_start_at": candidate_fold.test[0].decision_at.isoformat(),
            "candidate_temperature": candidate_temperature, "control_temperature": control_temperature,
            "candidate": candidate_metrics, "candidate_uncalibrated": _diagnostics(actual_test, candidate_test_raw),
            "control": control_metrics, "control_uncalibrated": _diagnostics(actual_test, control_test_raw), "empirical_class_frequency": empirical_metrics,
            "candidate_calibration": candidate_calibration_metrics, "candidate_calibration_uncalibrated": _diagnostics(actual_calibration, candidate_calibration_raw),
            "control_calibration": control_calibration_metrics,
            "relative_logloss_improvement_vs_control": _relative_improvement(control_metrics["log_loss"], candidate_metrics["log_loss"]),
            "relative_logloss_improvement_vs_empirical": _relative_improvement(empirical_metrics["log_loss"], candidate_metrics["log_loss"]),
        })
        for observation, candidate_probability, empirical_probability in zip(candidate_fold.test, candidate_test, empirical_test):
            utility_predictions.append((by_id[observation.episode_id], candidate_probability, empirical_probability))
    return tuple(output), tuple(utility_predictions)


def _relative_improvement(control: float, candidate: float) -> float | None:
    return None if control <= 0 else (control - candidate) / control


def _conditional_returns(fit_rows: Sequence[G2Row], policy: G2EvaluatorPolicy) -> Dict[MarketOutcome, float]:
    values = defaultdict(list)
    for row in fit_rows:
        if row.outcome in {MarketOutcome.STRUCTURE_EXIT, MarketOutcome.TIMEOUT}:
            values[row.outcome].append(row.gross_return_bps)
    if not values[MarketOutcome.STRUCTURE_EXIT] or not values[MarketOutcome.TIMEOUT]:
        raise KeyError("STRUCTURE_EXIT/TIMEOUT")
    return {
        MarketOutcome.TP: policy.tp_gross_return_bps,
        MarketOutcome.SL: policy.sl_gross_return_bps,
        MarketOutcome.STRUCTURE_EXIT: mean(values[MarketOutcome.STRUCTURE_EXIT]),
        MarketOutcome.TIMEOUT: mean(values[MarketOutcome.TIMEOUT]),
    }


def _utility(rows: Sequence[G2Row], predictions, policy: G2EvaluatorPolicy) -> Tuple[Dict[str, Any], Tuple[Tuple[G2Row, float, float], ...]]:
    # Each test row must use outcome payoff estimates made from earlier fold
    # training only. Rebuild folds to obtain those estimates deterministically.
    observations = _observations(rows, policy.feature_groups[policy.utility_feature_group])
    folds = purged_walk_forward(observations, folds=policy.folds, embargo=timedelta(seconds=policy.embargo_seconds))
    by_id = {row.episode_id: row for row in rows}
    payoff_by_episode = {}
    for fold in folds:
        train_rows = [by_id[item.episode_id] for item in fold.train]
        returns = _conditional_returns(train_rows, policy)
        for test in fold.test:
            payoff_by_episode[test.episode_id] = returns
    candidate_base, candidate_stress, empirical_base, empirical_stress = [], [], [], []
    candidate_selected, empirical_selected = [], []
    for row, candidate_probability, empirical_probability in predictions:
        returns = payoff_by_episode[row.episode_id]
        candidate_ev = sum(probability * (returns[outcome] - policy.base_round_trip_cost_bps) for outcome, probability in zip(OUTCOMES, candidate_probability))
        empirical_ev = sum(probability * (returns[outcome] - policy.base_round_trip_cost_bps) for outcome, probability in zip(OUTCOMES, empirical_probability))
        actual_base = row.gross_return_bps - policy.base_round_trip_cost_bps
        actual_stress = row.gross_return_bps - policy.stress_round_trip_cost_bps
        if candidate_ev > 0:
            candidate_base.append(actual_base)
            candidate_stress.append(actual_stress)
            candidate_selected.append((row, actual_base, actual_stress))
        if empirical_ev > 0:
            empirical_base.append(actual_base)
            empirical_stress.append(actual_stress)
            empirical_selected.append((row, actual_base, actual_stress))
    return {
        "meaning": "counterfactual market-path utility after declared round-trip cost; not execution PnL",
        "selection_rule": "test episode is included only when its calibration-derived base-cost EV is strictly positive",
        "candidate": {"selected_episodes": len(candidate_selected), "base_mean_bps": mean(candidate_base) if candidate_base else None, "stress_mean_bps": mean(candidate_stress) if candidate_stress else None},
        "empirical_class_frequency": {"selected_episodes": len(empirical_selected), "base_mean_bps": mean(empirical_base) if empirical_base else None, "stress_mean_bps": mean(empirical_stress) if empirical_stress else None},
    }, tuple(candidate_selected)


def _bootstrap_day_ci(rows: Sequence[G2Row], utility_by_episode: Sequence[float], policy: G2EvaluatorPolicy) -> Dict[str, Any]:
    by_day = defaultdict(list)
    for row, utility in zip(rows, utility_by_episode):
        by_day[row.decision_at.date().isoformat()].append(utility)
    days = sorted(by_day)
    if len(days) < policy.min_utc_days:
        return {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "fewer than required UTC-day blocks", "distinct_utc_days": len(days)}
    rng = random.Random(policy.bootstrap_seed)
    samples = []
    for _ in range(policy.bootstrap_iterations):
        values = [value for day in (rng.choice(days) for _ in days) for value in by_day[day]]
        samples.append(mean(values))
    samples.sort()
    low_index = max(0, int(math.floor(0.025 * (len(samples) - 1))))
    high_index = min(len(samples) - 1, int(math.ceil(0.975 * (len(samples) - 1))))
    return {"status": "READY", "distinct_utc_days": len(days), "iterations": policy.bootstrap_iterations, "seed": policy.bootstrap_seed, "lower_95_bps": samples[low_index], "upper_95_bps": samples[high_index]}


def _concentration(rows: Sequence[G2Row], policy: G2EvaluatorPolicy) -> Dict[str, Any]:
    if not rows:
        return {"status": "INCONCLUSIVE/WAIT_DATA", "population": "candidate positive-EV selected episodes", "reason": "no positive-EV candidate selections"}
    dimensions = {
        "utc_day": [row.decision_at.date().isoformat() for row in rows],
        "state": [row.state_id for row in rows],
        "direction": [row.side for row in rows],
    }
    limits = {"utc_day": policy.max_day_concentration, "state": policy.max_state_concentration, "direction": policy.max_direction_concentration}
    result = {}
    for name, values in dimensions.items():
        counts = Counter(values)
        maximum = max(counts.values()) / len(values)
        result[name] = {"counts": dict(sorted(counts.items())), "max_share": maximum, "limit": limits[name], "passed": maximum <= limits[name]}
    return {"status": "READY", "population": "candidate positive-EV selected episodes", "selected_episodes": len(rows), "dimensions": result}


def _coverage(rows: Sequence[G2Row], policy: G2EvaluatorPolicy) -> Dict[str, Any]:
    states = Counter(row.state_id for row in rows)
    missing = [state for state in policy.required_states if states[state] < policy.min_effective_episodes_per_state]
    return {
        "effective_episodes": len(rows), "minimum_effective_episodes": policy.min_effective_episodes,
        "distinct_utc_days": len({row.decision_at.date() for row in rows}), "minimum_utc_days": policy.min_utc_days,
        "observations_by_state": dict(sorted(states.items())), "missing_states": missing,
        "sufficient": len(rows) >= policy.min_effective_episodes and not missing and len({row.decision_at.date() for row in rows}) >= policy.min_utc_days,
    }


def _gate(status: str, reason: str) -> Dict[str, str]:
    return {"status": status, "reason": reason}


def evaluate_g2(rows: Iterable[Mapping[str, Any]], *, policy: G2EvaluatorPolicy) -> Dict[str, Any]:
    """Evaluate declared G2 development gates without performing any I/O.

    Structural input violations raise ``G2EvaluationError``. Evidence shortages
    and unavailable declared features return ``INCONCLUSIVE/WAIT_DATA``.
    """
    parsed = parse_g2_rows(rows, policy=policy)
    if policy.separate_models:
        by_side = {side: tuple(row for row in parsed if row.side == side) for side in policy.required_sides}
        side_reports = {}
        for side, side_rows in by_side.items():
            if len(side_rows) < policy.min_effective_episodes_per_side:
                side_reports[side] = {"overall_status": "INCONCLUSIVE/WAIT_DATA", "reason": "side sample below frozen minimum", "effective_episodes": len(side_rows)}
                continue
            inner = replace(policy, separate_models=False, min_effective_episodes=policy.min_effective_episodes_per_side, min_effective_episodes_per_state=policy.min_effective_episodes_per_state_per_side)
            side_reports[side] = evaluate_g2(({"availability_kind": "ACTUAL", "censored": False, "stage": "ENTER_PROBE", "episode_id": row.episode_id, "decision_at": row.decision_at.isoformat(), "label_end_at": row.label_end_at.isoformat(), "side": row.side, "state_id": row.state_id, "features": row.features, "outcome": row.outcome.value, "gross_return_bps": row.gross_return_bps} for row in side_rows), policy=inner)
        gate_names = ("H-001", "H-002", "H-003", "H-004", "PREDICTIVE", "ECONOMIC", "STABILITY")
        gates = {}
        for gate in gate_names:
            statuses = [side_reports[side].get("gates", {}).get(gate, {"status": "INCONCLUSIVE/WAIT_DATA"})["status"] for side in policy.required_sides]
            status = "FAIL" if "FAIL" in statuses else ("SUPPORT" if all(value == "SUPPORT" for value in statuses) else "INCONCLUSIVE/WAIT_DATA")
            gates[gate] = _gate(status, "both separately trained/calibrated directions must pass")
        overall = "G2_FAIL" if any(item["status"] == "FAIL" for item in gates.values()) else ("G2_PASS" if all(item["status"] == "SUPPORT" for item in gates.values()) else "INCONCLUSIVE/WAIT_DATA")
        return {"record_type": "g2_development_evaluation.v1", "meaning": "separate BUY/SELL counterfactual market-path evaluation; not execution PnL", "directional_models": side_reports, "gates": gates, "overall_status": overall, "concentration": _concentration(parsed, policy)}
    coverage = _coverage(parsed, policy)
    gates = {hypothesis_id: _gate("INCONCLUSIVE/WAIT_DATA", "coverage is below the frozen minimum") for hypothesis_id in _HYPOTHESES}
    gates.update({
        "PREDICTIVE": _gate("INCONCLUSIVE/WAIT_DATA", "coverage is below the frozen minimum"),
        "ECONOMIC": _gate("INCONCLUSIVE/WAIT_DATA", "coverage is below the frozen minimum"),
        "STABILITY": _gate("INCONCLUSIVE/WAIT_DATA", "coverage is below the frozen minimum"),
    })
    result: Dict[str, Any] = {
        "record_type": "g2_development_evaluation.v1", "meaning": "development-only counterfactual market-path evaluation; not execution evidence or trading authorization",
        "coverage": coverage, "gates": gates, "overall_status": "INCONCLUSIVE/WAIT_DATA", "ablations": {},
    }
    if not coverage["sufficient"]:
        return result
    utility_predictions = None
    predictive_folds = None
    for hypothesis_id in _HYPOTHESES:
        pair = policy.ablation_pairs[hypothesis_id]
        try:
            folds, predictions = _fold_models(parsed, policy, policy.feature_groups[pair.candidate_group], policy.feature_groups[pair.control_group])
        except KeyError as exc:
            result["ablations"][hypothesis_id] = {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "missing required declared feature: %s" % exc.args[0]}
            gates[hypothesis_id] = _gate("INCONCLUSIVE/WAIT_DATA", "missing required declared feature")
            continue
        except ValueError as exc:
            result["ablations"][hypothesis_id] = {"status": "INCONCLUSIVE/WAIT_DATA", "reason": str(exc)}
            continue
        improvements = [fold["relative_logloss_improvement_vs_control"] for fold in folds if fold["relative_logloss_improvement_vs_control"] is not None]
        average = mean(improvements) if improvements else None
        result["ablations"][hypothesis_id] = {"status": "READY", "candidate_group": pair.candidate_group, "control_group": pair.control_group, "folds": folds, "mean_relative_logloss_improvement_vs_control": average}
        successful_folds = sum(value >= policy.relative_logloss_improvement_min for value in improvements)
        result["ablations"][hypothesis_id]["successful_folds"] = successful_folds
        result["ablations"][hypothesis_id]["required_successful_folds"] = policy.min_successful_folds
        if len(improvements) == policy.folds and successful_folds >= policy.min_successful_folds:
            gates[hypothesis_id] = _gate("SUPPORT", "declared ablation/control log-loss increment passed in required folds")
        elif average is not None and average <= 0:
            gates[hypothesis_id] = _gate("FAIL", "no positive out-of-sample ablation/control increment")
        else:
            gates[hypothesis_id] = _gate("INCONCLUSIVE/WAIT_DATA", "increment is between fail and support thresholds")
        if pair.candidate_group == policy.utility_feature_group:
            utility_predictions = predictions
            predictive_folds = folds
    if utility_predictions is None:
        result["utility"] = {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "utility feature group is not a declared ablation candidate"}
        return result
    predictive_improvements = [fold["relative_logloss_improvement_vs_empirical"] for fold in predictive_folds if fold["relative_logloss_improvement_vs_empirical"] is not None]
    if len(predictive_improvements) != len(predictive_folds):
        gates["PREDICTIVE"] = _gate("INCONCLUSIVE/WAIT_DATA", "empirical baseline comparison is incomplete")
    elif any(value <= 0 for value in predictive_improvements):
        gates["PREDICTIVE"] = _gate("FAIL", "full candidate has non-positive out-of-sample log-loss increment over empirical frequency baseline")
    elif all(value >= policy.relative_logloss_improvement_min for value in predictive_improvements):
        gates["PREDICTIVE"] = _gate("SUPPORT", "full candidate beats empirical frequency baseline by the frozen threshold in every fold")
    else:
        gates["PREDICTIVE"] = _gate("INCONCLUSIVE/WAIT_DATA", "full candidate empirical-baseline improvement is positive but below the frozen threshold in one or more folds")
    try:
        utility, candidate_selected = _utility(parsed, utility_predictions, policy)
    except KeyError:
        result["utility"] = {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "training folds lack STRUCTURE_EXIT or TIMEOUT payoff observations"}
        return result
    selected_rows = tuple(item[0] for item in candidate_selected)
    selected_base_utility = tuple(item[1] for item in candidate_selected)
    ci = _bootstrap_day_ci(selected_rows, selected_base_utility, policy) if selected_rows else {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "no positive-EV candidate selections", "distinct_utc_days": 0}
    concentration = _concentration(selected_rows, policy)
    result["utility"] = utility
    result["bootstrap_utc_day_block"] = ci
    result["concentration"] = concentration
    if not selected_rows:
        gates["ECONOMIC"] = _gate("INCONCLUSIVE/WAIT_DATA", "no positive-EV candidate selections")
        gates["STABILITY"] = _gate("INCONCLUSIVE/WAIT_DATA", "no positive-EV candidate selections")
    elif ci["status"] != "READY":
        gates["ECONOMIC"] = _gate("INCONCLUSIVE/WAIT_DATA", "fewer than seven UTC-day blocks among positive-EV selections")
    elif ci["lower_95_bps"] > 0:
        gates["ECONOMIC"] = _gate("SUPPORT", "candidate base-cost UTC-day bootstrap lower bound exceeds zero")
    elif ci["upper_95_bps"] <= 0:
        gates["ECONOMIC"] = _gate("FAIL", "candidate base-cost UTC-day bootstrap upper bound is non-positive")
    else:
        gates["ECONOMIC"] = _gate("INCONCLUSIVE/WAIT_DATA", "base-cost confidence interval crosses zero")
    if selected_rows and concentration["status"] == "READY" and all(item["passed"] for item in concentration["dimensions"].values()) and utility["candidate"]["stress_mean_bps"] >= 0:
        gates["STABILITY"] = _gate("SUPPORT", "stress market-path utility and concentration limits pass")
    elif selected_rows and (concentration["status"] != "READY" or not all(item["passed"] for item in concentration["dimensions"].values()) or utility["candidate"]["stress_mean_bps"] < 0):
        gates["STABILITY"] = _gate("FAIL", "stress utility or concentration limit fails")
    if all(gate["status"] == "SUPPORT" for gate in gates.values()):
        result["overall_status"] = "G2_PASS"
    elif any(gate["status"] == "FAIL" for gate in gates.values()):
        result["overall_status"] = "G2_FAIL"
    return result
