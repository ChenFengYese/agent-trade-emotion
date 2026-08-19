"""Dependency-free M3 research primitives: purged walk-forward and baseline model.

These routines report predictive quality. They intentionally do not infer alpha
or approve trading on their own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Sequence, Tuple

from .decision import MarketOutcome, OutcomeForecast


OUTCOMES: Tuple[MarketOutcome, ...] = (
    MarketOutcome.TP,
    MarketOutcome.SL,
    MarketOutcome.STRUCTURE_EXIT,
    MarketOutcome.TIMEOUT,
)


@dataclass(frozen=True)
class LabeledObservation:
    episode_id: str
    decision_at: datetime
    label_end_at: datetime
    features: Dict[str, float]
    outcome: MarketOutcome
    # A frozen research protocol may require a pre-declared market-state
    # assignment. Development rows may leave this unassigned, but they cannot
    # then be used to satisfy a frozen state-coverage gate.
    state_id: str = "UNASSIGNED"


@dataclass(frozen=True)
class StateCoverageReport:
    """Coverage result, not a claim that an observed state is causal."""

    required_state_ids: Tuple[str, ...]
    observations_by_state: Dict[str, int]
    min_effective_episodes_per_state: int
    missing_state_ids: Tuple[str, ...]
    unexpected_state_ids: Tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing_state_ids and not self.unexpected_state_ids


def assess_state_coverage(
    observations: Sequence[LabeledObservation],
    *,
    required_state_ids: Sequence[str],
    min_effective_episodes_per_state: int,
) -> StateCoverageReport:
    """Apply an already-frozen state assignment contract to eligible rows.

    The function deliberately does not infer states from the same outcomes it
    will evaluate.  The caller must provide a state ID produced by the frozen
    classifier recorded in the protocol.
    """
    required = tuple(required_state_ids)
    if not required or len(set(required)) != len(required):
        raise ValueError("required_state_ids must be non-empty and unique")
    if min_effective_episodes_per_state < 1:
        raise ValueError("min_effective_episodes_per_state must be positive")
    counts = {state_id: 0 for state_id in required}
    unexpected = set()
    for row in observations:
        if row.state_id in counts:
            counts[row.state_id] += 1
        else:
            unexpected.add(row.state_id)
    missing = tuple(sorted(state_id for state_id, count in counts.items() if count < min_effective_episodes_per_state))
    return StateCoverageReport(
        required_state_ids=required,
        observations_by_state=counts,
        min_effective_episodes_per_state=min_effective_episodes_per_state,
        missing_state_ids=missing,
        unexpected_state_ids=tuple(sorted(unexpected)),
    )


@dataclass(frozen=True)
class WalkForwardFold:
    train: Tuple[LabeledObservation, ...]
    test: Tuple[LabeledObservation, ...]


def purged_walk_forward(
    observations: Sequence[LabeledObservation],
    *,
    folds: int,
    embargo: timedelta,
) -> List[WalkForwardFold]:
    """Forward-only folds; train labels must end before test/embargo begins."""
    if folds < 1:
        raise ValueError("folds must be positive")
    ordered = sorted(observations, key=lambda item: (item.decision_at, item.episode_id))
    if len(ordered) < folds + 1:
        raise ValueError("need more observations than folds")
    test_size = max(1, len(ordered) // (folds + 1))
    result: List[WalkForwardFold] = []
    for fold_index in range(folds):
        test_start_index = (fold_index + 1) * test_size
        test_end_index = len(ordered) if fold_index == folds - 1 else min(len(ordered), test_start_index + test_size)
        test = tuple(ordered[test_start_index:test_end_index])
        if not test:
            continue
        cutoff = test[0].decision_at - embargo
        train = tuple(item for item in ordered[:test_start_index] if item.label_end_at <= cutoff)
        if train:
            result.append(WalkForwardFold(train=train, test=test))
    if not result:
        raise ValueError("embargo purged every available training observation")
    return result


class RegularizedMultinomialLogistic:
    """Small deterministic multinomial baseline suitable for transparent experiments."""

    def __init__(self, feature_names: Sequence[str], l2: float = 0.01, learning_rate: float = 0.1, epochs: int = 250) -> None:
        if not feature_names:
            raise ValueError("at least one feature is required")
        self.feature_names = tuple(feature_names)
        self.l2 = l2
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.means: List[float] = []
        self.scales: List[float] = []
        self.weights: List[List[float]] = []

    def fit(self, rows: Sequence[LabeledObservation]) -> "RegularizedMultinomialLogistic":
        if not rows:
            raise ValueError("cannot fit empty data")
        matrix = [[float(row.features.get(name, 0.0)) for name in self.feature_names] for row in rows]
        self.means = [sum(row[index] for row in matrix) / len(matrix) for index in range(len(self.feature_names))]
        self.scales = []
        for index, mean in enumerate(self.means):
            variance = sum((row[index] - mean) ** 2 for row in matrix) / len(matrix)
            self.scales.append(max(math.sqrt(variance), 1e-9))
        normalized = [self._normalize_values(values) for values in matrix]
        self.weights = [[0.0 for _ in range(len(self.feature_names) + 1)] for _ in OUTCOMES]
        outcome_index = {outcome: index for index, outcome in enumerate(OUTCOMES)}
        for _ in range(self.epochs):
            gradient = [[0.0 for _ in range(len(self.feature_names) + 1)] for _ in OUTCOMES]
            for values, row in zip(normalized, rows):
                vector = [1.0] + values
                probabilities = self._softmax(vector)
                target = outcome_index[row.outcome]
                for class_index in range(len(OUTCOMES)):
                    error = probabilities[class_index] - (1.0 if class_index == target else 0.0)
                    for feature_index, value in enumerate(vector):
                        gradient[class_index][feature_index] += error * value
            for class_index in range(len(OUTCOMES)):
                for feature_index in range(len(self.weights[class_index])):
                    regularizer = self.l2 * self.weights[class_index][feature_index] if feature_index > 0 else 0.0
                    self.weights[class_index][feature_index] -= self.learning_rate * (gradient[class_index][feature_index] / len(rows) + regularizer)
        return self

    def _normalize_values(self, values: Sequence[float]) -> List[float]:
        return [(value - mean) / scale for value, mean, scale in zip(values, self.means, self.scales)]

    def _softmax(self, vector: Sequence[float]) -> List[float]:
        logits = [sum(weight * value for weight, value in zip(row, vector)) for row in self.weights]
        maximum = max(logits)
        exponentials = [math.exp(item - maximum) for item in logits]
        total = sum(exponentials)
        return [item / total for item in exponentials]

    def predict(self, features: Dict[str, float]) -> OutcomeForecast:
        if not self.weights:
            raise RuntimeError("model is not fitted")
        values = [float(features.get(name, 0.0)) for name in self.feature_names]
        probabilities = self._softmax([1.0] + self._normalize_values(values))
        return OutcomeForecast(*[self._decimal_probability(item) for item in probabilities])

    @staticmethod
    def _decimal_probability(value: float):
        from decimal import Decimal
        return Decimal(str(value))


@dataclass(frozen=True)
class PredictiveMetrics:
    observations: int
    log_loss: float
    multiclass_brier: float
    accuracy: float


def evaluate_predictions(rows: Iterable[Tuple[MarketOutcome, OutcomeForecast]]) -> PredictiveMetrics:
    outcome_index = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    log_loss = 0.0
    brier = 0.0
    correct = 0
    total = 0
    for actual, forecast in rows:
        probabilities = [float(forecast.tp), float(forecast.sl), float(forecast.structure_exit), float(forecast.timeout)]
        index = outcome_index[actual]
        log_loss -= math.log(max(probabilities[index], 1e-15))
        brier += sum((probability - (1.0 if item == index else 0.0)) ** 2 for item, probability in enumerate(probabilities))
        if max(range(len(probabilities)), key=lambda item: probabilities[item]) == index:
            correct += 1
        total += 1
    if total == 0:
        raise ValueError("cannot score empty predictions")
    return PredictiveMetrics(total, log_loss / total, brier / total, correct / total)


@dataclass(frozen=True)
class WalkForwardReport:
    folds: Tuple[PredictiveMetrics, ...]

    @property
    def mean_log_loss(self) -> float:
        return sum(item.log_loss for item in self.folds) / len(self.folds)

    @property
    def mean_brier(self) -> float:
        return sum(item.multiclass_brier for item in self.folds) / len(self.folds)


@dataclass(frozen=True)
class FinalHoldoutReport:
    """One deterministic fit on pre-holdout rows, scored on a fixed holdout."""

    training_observations: int
    holdout_observations: int
    metrics: PredictiveMetrics


def run_walk_forward_baseline(
    observations: Sequence[LabeledObservation],
    *,
    feature_names: Sequence[str],
    folds: int,
    embargo: timedelta,
) -> WalkForwardReport:
    reports: List[PredictiveMetrics] = []
    for fold in purged_walk_forward(observations, folds=folds, embargo=embargo):
        model = RegularizedMultinomialLogistic(feature_names).fit(fold.train)
        reports.append(evaluate_predictions((row.outcome, model.predict(row.features)) for row in fold.test))
    return WalkForwardReport(tuple(reports))


def run_final_holdout_baseline(
    training: Sequence[LabeledObservation],
    holdout: Sequence[LabeledObservation],
    *,
    feature_names: Sequence[str],
) -> FinalHoldoutReport:
    if not training:
        raise ValueError("final holdout baseline requires pre-holdout training observations")
    if not holdout:
        raise ValueError("final holdout baseline requires holdout observations")
    model = RegularizedMultinomialLogistic(feature_names).fit(training)
    metrics = evaluate_predictions((row.outcome, model.predict(row.features)) for row in holdout)
    return FinalHoldoutReport(len(training), len(holdout), metrics)
