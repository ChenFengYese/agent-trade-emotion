"""V3.1 probability-cloud contracts.

The module separates subjective plausibility, model-conditional estimates,
market-implied beliefs, and genuinely calibrated predictive distributions.
It performs no IO and deliberately refuses to turn uncalibrated judgements into
expected value, normalized probability, or position sizing inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_decimal, canonical_digest, self_digest


class ProbabilityCloudError(ValueError):
    """A probability-cloud claim exceeded its evidence contract."""


class ProbabilityMode(StrEnum):
    SUBJECTIVE_PLAUSIBILITY = "SUBJECTIVE_PLAUSIBILITY"
    EMPIRICAL_OR_MODEL_CONDITIONAL = "EMPIRICAL_OR_MODEL_CONDITIONAL"
    MARKET_IMPLIED_BELIEF = "MARKET_IMPLIED_BELIEF"
    CALIBRATED_PREDICTIVE_DISTRIBUTION = "CALIBRATED_PREDICTIVE_DISTRIBUTION"


class PlausibilityLevel(StrEnum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
    UNKNOWN = "UNKNOWN"


class EvidenceEffect(StrEnum):
    SUPPORT = "SUPPORT"
    OPPOSE = "OPPOSE"
    CONFLICT = "CONFLICT"
    MISSING_CONSTRAINT = "MISSING_CONSTRAINT"
    CONTEXT = "CONTEXT"


class ProperScoringRule(StrEnum):
    BRIER = "BRIER"
    LOG_SCORE = "LOG_SCORE"
    CRPS = "CRPS"


_ONE = Decimal("1")
_ZERO = Decimal("0")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_MIN_VALIDATION_SPLIT_SIZE = 100
_MIN_OUTCOME_COUNT_PER_SPLIT = 10
_MAX_CALIBRATION_ERROR = Decimal("0.10")
_MAX_OOS_CALIBRATION_ERROR = Decimal("0.10")
_MAX_CALIBRATION_ERROR_DRIFT = Decimal("0.05")
_MAX_PROPER_SCORE_DEGRADATION = Decimal("0.05")
_MAX_DISTRIBUTION_DRIFT = Decimal("0.20")
_CONSTANT_MODEL_IMPLEMENTATION_DIGEST = canonical_digest(
    {
        "algorithm": "CONSTANT_CATEGORICAL_DISTRIBUTION",
        "version": "1.0.0",
        "input_usage": "IGNORED_BY_DESIGN",
    }
)


def _timestamp(value: str, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProbabilityCloudError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProbabilityCloudError(code) from exc
    if parsed.tzinfo is None:
        raise ProbabilityCloudError(code)
    return parsed.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | str | None, code: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise ProbabilityCloudError("BINARY_FLOAT_FORBIDDEN")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProbabilityCloudError(code) from exc
    if not parsed.is_finite() or parsed < _ZERO or parsed > _ONE:
        raise ProbabilityCloudError(code)
    return parsed


def _decimal_unbounded(value: Decimal | str, code: str) -> Decimal:
    if isinstance(value, float):
        raise ProbabilityCloudError("BINARY_FLOAT_FORBIDDEN")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProbabilityCloudError(code) from exc
    if not parsed.is_finite():
        raise ProbabilityCloudError(code)
    return parsed


def _refs(values: Sequence[str], code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ProbabilityCloudError(code)
    result = tuple(values)
    if (not allow_empty and not result) or any(
        not isinstance(value, str) or not value.strip() for value in result
    ) or len(result) != len(set(result)):
        raise ProbabilityCloudError(code)
    return result


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProbabilityCloudError(code)
    return value.strip()


def _bound_digest(value: Any, code: str) -> str:
    """Reject malformed and obvious placeholder values used as fake bindings."""

    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise ProbabilityCloudError(code)
    # A genuine SHA-256 digest with fewer than eight distinct hexadecimal
    # symbols is astronomically unlikely.  This explicitly rejects fixtures
    # such as ``"1" * 64``; substantive bindings are still recomputed below.
    if len(set(value)) < 8:
        raise ProbabilityCloudError("CALIBRATION_PLACEHOLDER_DIGEST_FORBIDDEN")
    return value


@dataclass(frozen=True, slots=True)
class CloudComponent:
    """One hypothesis entry within a probability cloud.

    ``lower``/``upper`` are an uncertainty envelope, not a calibrated point
    probability.  ``probability`` is reserved for the calibrated mode.
    """

    hypothesis_id: str
    plausibility: PlausibilityLevel | None = None
    lower: Decimal | str | None = None
    upper: Decimal | str | None = None
    probability: Decimal | str | None = None
    evidence_refs: tuple[str, ...] = ()
    opposition_refs: tuple[str, ...] = ()
    conflict_refs: tuple[str, ...] = ()
    dependency_groups: tuple[str, ...] = ()
    data_uncertainty: tuple[str, ...] = ()
    model_uncertainty: tuple[str, ...] = ()
    sensitivity_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.hypothesis_id, str) or not self.hypothesis_id.strip():
            raise ProbabilityCloudError("CLOUD_HYPOTHESIS_ID_INVALID")
        for field_name in (
            "evidence_refs",
            "opposition_refs",
            "conflict_refs",
            "dependency_groups",
            "data_uncertainty",
            "model_uncertainty",
            "sensitivity_notes",
        ):
            object.__setattr__(
                self,
                field_name,
                _refs(getattr(self, field_name), "CLOUD_COMPONENT_REFS_INVALID", allow_empty=True),
            )
        low = _decimal(self.lower, "CLOUD_INTERVAL_INVALID")
        high = _decimal(self.upper, "CLOUD_INTERVAL_INVALID")
        point = _decimal(self.probability, "CLOUD_PROBABILITY_INVALID")
        if (low is None) != (high is None) or (
            low is not None and high is not None and low > high
        ):
            raise ProbabilityCloudError("CLOUD_INTERVAL_INVALID")
        object.__setattr__(self, "lower", low)
        object.__setattr__(self, "upper", high)
        object.__setattr__(self, "probability", point)
        if self.plausibility is not None and not isinstance(
            self.plausibility, PlausibilityLevel
        ):
            raise ProbabilityCloudError("CLOUD_PLAUSIBILITY_ENUM_INVALID")

    def to_document(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "plausibility": self.plausibility.value if self.plausibility else None,
            "lower": canonical_decimal(self.lower) if self.lower is not None else None,
            "upper": canonical_decimal(self.upper) if self.upper is not None else None,
            "probability": (
                canonical_decimal(self.probability)
                if self.probability is not None
                else None
            ),
            "evidence_refs": list(self.evidence_refs),
            "opposition_refs": list(self.opposition_refs),
            "conflict_refs": list(self.conflict_refs),
            "dependency_groups": list(self.dependency_groups),
            "data_uncertainty": list(self.data_uncertainty),
            "model_uncertainty": list(self.model_uncertainty),
            "sensitivity_notes": list(self.sensitivity_notes),
        }


@dataclass(frozen=True, slots=True)
class FrozenPredictiveForecast:
    """A prediction frozen before its outcome can be known.

    The probability vector and model-input digest are immutable inputs to the
    validation calculation.  No score or pass/fail flag is accepted here.
    """

    forecast_id: str
    prediction_at: str
    model_input_digest: str
    probabilities: tuple[tuple[str, Decimal | str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "forecast_id", _text(self.forecast_id, "FORECAST_ID_INVALID")
        )
        object.__setattr__(
            self,
            "prediction_at",
            _timestamp_text(
                _timestamp(self.prediction_at, "FORECAST_PREDICTION_TIME_INVALID")
            ),
        )
        object.__setattr__(
            self,
            "model_input_digest",
            _bound_digest(self.model_input_digest, "FORECAST_INPUT_DIGEST_INVALID"),
        )
        if isinstance(self.probabilities, (str, bytes)):
            raise ProbabilityCloudError("FORECAST_PROBABILITY_VECTOR_INVALID")
        normalized: list[tuple[str, Decimal]] = []
        seen: set[str] = set()
        for raw in self.probabilities:
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise ProbabilityCloudError("FORECAST_PROBABILITY_VECTOR_INVALID")
            outcome_id = _text(raw[0], "FORECAST_OUTCOME_ID_INVALID")
            probability = _decimal(raw[1], "FORECAST_PROBABILITY_INVALID")
            if outcome_id in seen or probability is None:
                raise ProbabilityCloudError("FORECAST_PROBABILITY_VECTOR_INVALID")
            seen.add(outcome_id)
            normalized.append((outcome_id, probability))
        normalized.sort(key=lambda item: item[0])
        if len(normalized) < 2 or sum((row[1] for row in normalized), _ZERO) != _ONE:
            raise ProbabilityCloudError("FORECAST_PROBABILITIES_MUST_SUM_TO_ONE")
        object.__setattr__(self, "probabilities", tuple(normalized))

    @property
    def outcome_ids(self) -> tuple[str, ...]:
        return tuple(row[0] for row in self.probabilities)

    def to_document(self) -> dict[str, Any]:
        return {
            "forecast_id": self.forecast_id,
            "prediction_at": self.prediction_at,
            "model_input_digest": self.model_input_digest,
            "probabilities": [
                {"outcome_id": outcome_id, "probability": canonical_decimal(value)}
                for outcome_id, value in self.probabilities
            ],
        }


@dataclass(frozen=True, slots=True)
class FrozenPredictionOutcome:
    """One immutable historical prediction joined to its resolved outcome."""

    forecast: FrozenPredictiveForecast
    observed_outcome: str
    outcome_available_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.forecast, FrozenPredictiveForecast):
            raise ProbabilityCloudError("VALIDATION_FORECAST_REQUIRED")
        outcome = _text(
            self.observed_outcome, "VALIDATION_OBSERVED_OUTCOME_INVALID"
        )
        if outcome not in self.forecast.outcome_ids:
            raise ProbabilityCloudError("VALIDATION_OBSERVED_OUTCOME_NOT_IN_PARTITION")
        outcome_available = _timestamp(
            self.outcome_available_at, "VALIDATION_OUTCOME_TIME_INVALID"
        )
        if outcome_available <= _timestamp(
            self.forecast.prediction_at, "FORECAST_PREDICTION_TIME_INVALID"
        ):
            raise ProbabilityCloudError("VALIDATION_OUTCOME_NOT_AFTER_PREDICTION")
        object.__setattr__(self, "observed_outcome", outcome)
        object.__setattr__(
            self, "outcome_available_at", _timestamp_text(outcome_available)
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "forecast": self.forecast.to_document(),
            "observed_outcome": self.observed_outcome,
            "outcome_available_at": self.outcome_available_at,
        }


def _sample_digest(
    split_name: str, rows: Sequence[FrozenPredictionOutcome]
) -> str:
    return canonical_digest(
        {
            "schema_id": "theory_paper_v2_v31_frozen_prediction_outcome_sample",
            "schema_version": "1.0.0",
            "split": split_name,
            "observations": [row.to_document() for row in rows],
        }
    )


def _probability_map(row: FrozenPredictionOutcome) -> dict[str, Decimal]:
    return dict(row.forecast.probabilities)


def _proper_score(
    rows: Sequence[FrozenPredictionOutcome],
    scoring_rule: ProperScoringRule,
    *,
    constant_probabilities: Mapping[str, Decimal] | None = None,
) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        total = _ZERO
        for row in rows:
            probabilities = (
                dict(constant_probabilities)
                if constant_probabilities is not None
                else _probability_map(row)
            )
            if scoring_rule is ProperScoringRule.BRIER:
                total += sum(
                    (
                        probability
                        - (_ONE if outcome_id == row.observed_outcome else _ZERO)
                    )
                    ** 2
                    for outcome_id, probability in probabilities.items()
                )
            elif scoring_rule is ProperScoringRule.LOG_SCORE:
                observed_probability = probabilities[row.observed_outcome]
                if observed_probability <= _ZERO:
                    raise ProbabilityCloudError("LOG_SCORE_ZERO_OBSERVED_PROBABILITY")
                total -= observed_probability.ln()
            else:
                # CRPS requires an ordered/continuous outcome contract.  The V3.1
                # receipt currently verifies categorical finite partitions only.
                raise ProbabilityCloudError("CALIBRATION_SCORING_RULE_UNSUPPORTED")
        return total / Decimal(len(rows))


def _observed_frequencies(
    rows: Sequence[FrozenPredictionOutcome], outcome_ids: Sequence[str]
) -> dict[str, Decimal]:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        denominator = Decimal(len(rows))
        return {
            outcome_id: Decimal(
                sum(row.observed_outcome == outcome_id for row in rows)
            )
            / denominator
            for outcome_id in outcome_ids
        }


def _mean_probabilities(
    rows: Sequence[FrozenPredictionOutcome], outcome_ids: Sequence[str]
) -> dict[str, Decimal]:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        denominator = Decimal(len(rows))
        return {
            outcome_id: sum(
                (_probability_map(row)[outcome_id] for row in rows), _ZERO
            )
            / denominator
            for outcome_id in outcome_ids
        }


def _classwise_calibration_error(
    rows: Sequence[FrozenPredictionOutcome], outcome_ids: Sequence[str]
) -> Decimal:
    """Fixed-decile classwise ECE; bins and limits are not caller-controlled."""

    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        weighted_error = _ZERO
        denominator = Decimal(len(rows) * len(outcome_ids))
        for outcome_id in outcome_ids:
            bins: dict[int, list[tuple[Decimal, Decimal]]] = {}
            for row in rows:
                probability = _probability_map(row)[outcome_id]
                bin_index = min(9, int(probability * Decimal("10")))
                bins.setdefault(bin_index, []).append(
                    (
                        probability,
                        _ONE if row.observed_outcome == outcome_id else _ZERO,
                    )
                )
            for values in bins.values():
                count = Decimal(len(values))
                mean_probability = sum((row[0] for row in values), _ZERO) / count
                observed_frequency = sum((row[1] for row in values), _ZERO) / count
                weighted_error += count / denominator * abs(
                    mean_probability - observed_frequency
                )
        return weighted_error


def _total_variation(
    left: Mapping[str, Decimal], right: Mapping[str, Decimal]
) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        return sum(
            (abs(left[key] - right[key]) for key in left), _ZERO
        ) / Decimal("2")


_EVENT_CONTRACT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "event_contract_ref",
        "horizon",
        "outcome_ids",
        "mutually_exclusive",
        "exhaustive",
        "resolution_rule",
    }
)
_MODEL_CONTRACT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "model_ref",
        "event_contract_ref",
        "event_contract_digest",
        "horizon",
        "outcome_ids",
        "frozen_at",
        "training_data_cutoff",
        "model_kind",
        "frozen_probabilities",
        "implementation_digest",
    }
)


def _verify_event_contract(
    document: Mapping[str, Any], *, event_contract_ref: str, horizon: str
) -> tuple[dict[str, Any], tuple[str, ...], str]:
    if not isinstance(document, Mapping) or set(document) != _EVENT_CONTRACT_FIELDS:
        raise ProbabilityCloudError("CALIBRATION_EVENT_CONTRACT_SCHEMA_INVALID")
    normalized = dict(document)
    outcome_ids = tuple(
        sorted(
            _refs(
                normalized.get("outcome_ids"),
                "CALIBRATION_EVENT_OUTCOMES_INVALID",
            )
        )
    )
    if (
        normalized.get("schema_id")
        != "theory_paper_v2_v31_predictive_event_contract"
        or normalized.get("schema_version") != "1.0.0"
        or normalized.get("event_contract_ref") != event_contract_ref
        or normalized.get("horizon") != horizon
        or normalized.get("mutually_exclusive") is not True
        or normalized.get("exhaustive") is not True
        or "OTHER" not in outcome_ids
        or len(outcome_ids) < 2
    ):
        raise ProbabilityCloudError("CALIBRATION_EVENT_CONTRACT_INVALID")
    _text(normalized.get("resolution_rule"), "CALIBRATION_RESOLUTION_RULE_INVALID")
    normalized["outcome_ids"] = list(outcome_ids)
    return normalized, outcome_ids, canonical_digest(normalized)


def _verify_model_contract(
    document: Mapping[str, Any],
    *,
    model_ref: str,
    event_contract_ref: str,
    event_contract_digest: str,
    horizon: str,
    outcome_ids: tuple[str, ...],
) -> tuple[dict[str, Any], str, tuple[tuple[str, Decimal], ...]]:
    if not isinstance(document, Mapping) or set(document) != _MODEL_CONTRACT_FIELDS:
        raise ProbabilityCloudError("CALIBRATION_MODEL_CONTRACT_SCHEMA_INVALID")
    normalized = dict(document)
    model_outcomes = tuple(
        sorted(
            _refs(
                normalized.get("outcome_ids"),
                "CALIBRATION_MODEL_OUTCOMES_INVALID",
            )
        )
    )
    frozen_probabilities_raw = normalized.get("frozen_probabilities")
    if not isinstance(frozen_probabilities_raw, (list, tuple)):
        raise ProbabilityCloudError("CALIBRATION_MODEL_PROBABILITIES_INVALID")
    frozen_probabilities: list[tuple[str, Decimal]] = []
    frozen_outcomes: set[str] = set()
    for raw in frozen_probabilities_raw:
        if not isinstance(raw, Mapping) or set(raw) != {
            "outcome_id",
            "probability",
        }:
            raise ProbabilityCloudError("CALIBRATION_MODEL_PROBABILITIES_INVALID")
        outcome_id = _text(
            raw.get("outcome_id"), "CALIBRATION_MODEL_OUTCOMES_INVALID"
        )
        probability = _decimal(
            raw.get("probability"), "CALIBRATION_MODEL_PROBABILITIES_INVALID"
        )
        if outcome_id in frozen_outcomes or probability is None:
            raise ProbabilityCloudError("CALIBRATION_MODEL_PROBABILITIES_INVALID")
        frozen_outcomes.add(outcome_id)
        frozen_probabilities.append((outcome_id, probability))
    frozen_probabilities.sort(key=lambda row: row[0])
    if (
        normalized.get("schema_id")
        != "theory_paper_v2_v31_frozen_predictive_model"
        or normalized.get("schema_version") != "1.0.0"
        or normalized.get("model_ref") != model_ref
        or normalized.get("event_contract_ref") != event_contract_ref
        or normalized.get("event_contract_digest") != event_contract_digest
        or normalized.get("horizon") != horizon
        or model_outcomes != outcome_ids
        or normalized.get("model_kind")
        != "CONSTANT_CATEGORICAL_DISTRIBUTION_V1"
        or tuple(row[0] for row in frozen_probabilities) != outcome_ids
        or sum((row[1] for row in frozen_probabilities), _ZERO) != _ONE
    ):
        raise ProbabilityCloudError("CALIBRATION_MODEL_CONTRACT_INVALID")
    frozen = _timestamp(normalized.get("frozen_at"), "CALIBRATION_MODEL_TIME_INVALID")
    training_cutoff = _timestamp(
        normalized.get("training_data_cutoff"), "CALIBRATION_MODEL_TIME_INVALID"
    )
    if training_cutoff > frozen:
        raise ProbabilityCloudError("CALIBRATION_MODEL_TIME_INVALID")
    implementation_digest = _bound_digest(
        normalized.get("implementation_digest"),
        "CALIBRATION_MODEL_IMPLEMENTATION_DIGEST_INVALID",
    )
    if implementation_digest != _CONSTANT_MODEL_IMPLEMENTATION_DIGEST:
        raise ProbabilityCloudError("CALIBRATION_MODEL_IMPLEMENTATION_UNSUPPORTED")
    normalized["outcome_ids"] = list(model_outcomes)
    normalized["frozen_at"] = _timestamp_text(frozen)
    normalized["training_data_cutoff"] = _timestamp_text(training_cutoff)
    normalized["frozen_probabilities"] = [
        {"outcome_id": outcome_id, "probability": canonical_decimal(probability)}
        for outcome_id, probability in frozen_probabilities
    ]
    return normalized, canonical_digest(normalized), tuple(frozen_probabilities)


@dataclass(frozen=True, slots=True)
class PredictiveValidationReceipt:
    """Locally replayable validation over frozen prediction/outcome samples.

    All digests, scores, calibration errors, and drift decisions are derived.
    The constructor deliberately exposes no caller-set pass flag, score, or
    result digest.
    """

    receipt_id: str
    event_contract_ref: str
    event_contract: Mapping[str, Any]
    horizon: str
    model_ref: str
    model_contract: Mapping[str, Any]
    development_sample: tuple[FrozenPredictionOutcome, ...]
    calibration_sample: tuple[FrozenPredictionOutcome, ...]
    oos_sample: tuple[FrozenPredictionOutcome, ...]
    deployment_forecast: FrozenPredictiveForecast
    scoring_rule: ProperScoringRule
    available_at: str
    invalidation_conditions: tuple[str, ...]
    limitations: tuple[str, ...]
    event_contract_digest: str = field(init=False)
    model_digest: str = field(init=False)
    outcome_ids: tuple[str, ...] = field(init=False)
    development_sample_digest: str = field(init=False)
    calibration_sample_digest: str = field(init=False)
    oos_sample_digest: str = field(init=False)
    deployment_forecast_digest: str = field(init=False)
    oos_evaluation_digest: str = field(init=False)
    calibration_result_digest: str = field(init=False)
    proper_scoring_result_digest: str = field(init=False)
    drift_assessment_digest: str = field(init=False)
    score_value: Decimal = field(init=False)
    calibration_error: Decimal = field(init=False)
    oos_calibration_error: Decimal = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "receipt_id", _text(self.receipt_id, "CALIBRATION_RECEIPT_ID_INVALID")
        )
        object.__setattr__(
            self,
            "event_contract_ref",
            _text(
                self.event_contract_ref, "CALIBRATION_EVENT_CONTRACT_REF_INVALID"
            ),
        )
        object.__setattr__(
            self, "horizon", _text(self.horizon, "CALIBRATION_HORIZON_INVALID")
        )
        object.__setattr__(
            self, "model_ref", _text(self.model_ref, "CALIBRATION_MODEL_REF_INVALID")
        )
        if not isinstance(self.scoring_rule, ProperScoringRule):
            raise ProbabilityCloudError("CALIBRATION_SCORING_RULE_INVALID")
        object.__setattr__(
            self,
            "available_at",
            _timestamp_text(
                _timestamp(self.available_at, "CALIBRATION_AVAILABLE_AT_INVALID")
            ),
        )
        if not isinstance(self.deployment_forecast, FrozenPredictiveForecast):
            raise ProbabilityCloudError("CALIBRATION_DEPLOYMENT_FORECAST_REQUIRED")
        for field_name in (
            "development_sample",
            "calibration_sample",
            "oos_sample",
        ):
            rows = tuple(getattr(self, field_name))
            if len(rows) < _MIN_VALIDATION_SPLIT_SIZE or any(
                not isinstance(row, FrozenPredictionOutcome) for row in rows
            ):
                raise ProbabilityCloudError("CALIBRATION_SAMPLE_TOO_SMALL_OR_INVALID")
            object.__setattr__(self, field_name, rows)
        object.__setattr__(
            self,
            "invalidation_conditions",
            _refs(
                self.invalidation_conditions,
                "CALIBRATION_INVALIDATION_CONDITIONS_REQUIRED",
            ),
        )
        object.__setattr__(
            self,
            "limitations",
            _refs(self.limitations, "CALIBRATION_LIMITATIONS_REQUIRED"),
        )
        event_contract, outcome_ids, event_digest = _verify_event_contract(
            self.event_contract,
            event_contract_ref=self.event_contract_ref,
            horizon=self.horizon,
        )
        model_contract, model_digest, _ = _verify_model_contract(
            self.model_contract,
            model_ref=self.model_ref,
            event_contract_ref=self.event_contract_ref,
            event_contract_digest=event_digest,
            horizon=self.horizon,
            outcome_ids=outcome_ids,
        )
        object.__setattr__(self, "event_contract", event_contract)
        object.__setattr__(self, "model_contract", model_contract)
        object.__setattr__(self, "event_contract_digest", event_digest)
        object.__setattr__(self, "model_digest", model_digest)
        object.__setattr__(self, "outcome_ids", outcome_ids)
        computed = self._recompute()
        for name, value in computed.items():
            object.__setattr__(self, name, value)

    def _recompute(self) -> dict[str, Any]:
        event_contract, outcome_ids, event_digest = _verify_event_contract(
            self.event_contract,
            event_contract_ref=self.event_contract_ref,
            horizon=self.horizon,
        )
        model_contract, model_digest, model_probabilities = _verify_model_contract(
            self.model_contract,
            model_ref=self.model_ref,
            event_contract_ref=self.event_contract_ref,
            event_contract_digest=event_digest,
            horizon=self.horizon,
            outcome_ids=outcome_ids,
        )
        del event_contract, model_contract
        splits = (
            ("DEVELOPMENT", self.development_sample),
            ("CALIBRATION", self.calibration_sample),
            ("OOS", self.oos_sample),
        )
        all_ids: list[str] = []
        for _, rows in splits:
            observed_counts = {outcome_id: 0 for outcome_id in outcome_ids}
            for row in rows:
                if row.forecast.outcome_ids != outcome_ids:
                    raise ProbabilityCloudError("CALIBRATION_SAMPLE_PARTITION_MISMATCH")
                if row.forecast.probabilities != model_probabilities:
                    raise ProbabilityCloudError(
                        "CALIBRATION_FORECAST_NOT_REPRODUCED_BY_MODEL"
                    )
                observed_counts[row.observed_outcome] += 1
                all_ids.append(row.forecast.forecast_id)
            if min(observed_counts.values()) < _MIN_OUTCOME_COUNT_PER_SPLIT:
                raise ProbabilityCloudError("CALIBRATION_OUTCOME_COVERAGE_INSUFFICIENT")
        if len(all_ids) != len(set(all_ids)):
            raise ProbabilityCloudError("CALIBRATION_SAMPLE_OVERLAP_FORBIDDEN")
        development_end = max(
            _timestamp(row.outcome_available_at, "VALIDATION_OUTCOME_TIME_INVALID")
            for row in self.development_sample
        )
        calibration_start = min(
            _timestamp(row.forecast.prediction_at, "FORECAST_PREDICTION_TIME_INVALID")
            for row in self.calibration_sample
        )
        calibration_end = max(
            _timestamp(row.outcome_available_at, "VALIDATION_OUTCOME_TIME_INVALID")
            for row in self.calibration_sample
        )
        oos_start = min(
            _timestamp(row.forecast.prediction_at, "FORECAST_PREDICTION_TIME_INVALID")
            for row in self.oos_sample
        )
        oos_end = max(
            _timestamp(row.outcome_available_at, "VALIDATION_OUTCOME_TIME_INVALID")
            for row in self.oos_sample
        )
        model_frozen = _timestamp(
            self.model_contract["frozen_at"], "CALIBRATION_MODEL_TIME_INVALID"
        )
        first_development_prediction = min(
            _timestamp(row.forecast.prediction_at, "FORECAST_PREDICTION_TIME_INVALID")
            for row in self.development_sample
        )
        receipt_available = _timestamp(
            self.available_at, "CALIBRATION_AVAILABLE_AT_INVALID"
        )
        deployment_prediction = _timestamp(
            self.deployment_forecast.prediction_at,
            "FORECAST_PREDICTION_TIME_INVALID",
        )
        if not (
            model_frozen <= first_development_prediction
            and development_end <= calibration_start
            and calibration_end <= oos_start
            and oos_end <= receipt_available <= deployment_prediction
        ):
            raise ProbabilityCloudError("CALIBRATION_TEMPORAL_SEPARATION_INVALID")
        if self.deployment_forecast.outcome_ids != outcome_ids:
            raise ProbabilityCloudError("CALIBRATION_DEPLOYMENT_PARTITION_MISMATCH")
        if self.deployment_forecast.probabilities != model_probabilities:
            raise ProbabilityCloudError(
                "CALIBRATION_FORECAST_NOT_REPRODUCED_BY_MODEL"
            )

        development_digest = _sample_digest(
            "DEVELOPMENT", self.development_sample
        )
        calibration_digest = _sample_digest(
            "CALIBRATION", self.calibration_sample
        )
        oos_digest = _sample_digest("OOS", self.oos_sample)
        if len({development_digest, calibration_digest, oos_digest}) != 3:
            raise ProbabilityCloudError("CALIBRATION_SAMPLE_SEPARATION_REQUIRED")
        deployment_digest = canonical_digest(
            {
                "schema_id": "theory_paper_v2_v31_deployment_forecast",
                "schema_version": "1.0.0",
                "model_digest": model_digest,
                "event_contract_digest": event_digest,
                "forecast": self.deployment_forecast.to_document(),
            }
        )

        calibration_score = _proper_score(
            self.calibration_sample, self.scoring_rule
        )
        oos_score = _proper_score(self.oos_sample, self.scoring_rule)
        development_frequencies = _observed_frequencies(
            self.development_sample, outcome_ids
        )
        oos_baseline_score = _proper_score(
            self.oos_sample,
            self.scoring_rule,
            constant_probabilities=development_frequencies,
        )
        calibration_error = _classwise_calibration_error(
            self.calibration_sample, outcome_ids
        )
        oos_calibration_error = _classwise_calibration_error(
            self.oos_sample, outcome_ids
        )
        score_degradation = oos_score - calibration_score
        calibration_error_drift = abs(oos_calibration_error - calibration_error)
        outcome_distribution_drift = _total_variation(
            _observed_frequencies(self.calibration_sample, outcome_ids),
            _observed_frequencies(self.oos_sample, outcome_ids),
        )
        prediction_distribution_drift = _total_variation(
            _mean_probabilities(self.calibration_sample, outcome_ids),
            _mean_probabilities(self.oos_sample, outcome_ids),
        )
        if calibration_error > _MAX_CALIBRATION_ERROR:
            raise ProbabilityCloudError("CALIBRATION_ERROR_LIMIT_EXCEEDED")
        if oos_calibration_error > _MAX_OOS_CALIBRATION_ERROR:
            raise ProbabilityCloudError("OOS_CALIBRATION_ERROR_LIMIT_EXCEEDED")
        if oos_score > oos_baseline_score:
            raise ProbabilityCloudError("OOS_PROPER_SCORE_WORSE_THAN_BASELINE")
        if (
            score_degradation > _MAX_PROPER_SCORE_DEGRADATION
            or calibration_error_drift > _MAX_CALIBRATION_ERROR_DRIFT
            or outcome_distribution_drift > _MAX_DISTRIBUTION_DRIFT
            or prediction_distribution_drift > _MAX_DISTRIBUTION_DRIFT
        ):
            raise ProbabilityCloudError("CALIBRATION_DRIFT_LIMIT_EXCEEDED")

        calibration_result = {
            "calibration_sample_digest": calibration_digest,
            "oos_sample_digest": oos_digest,
            "calibration_error": canonical_decimal(calibration_error),
            "oos_calibration_error": canonical_decimal(oos_calibration_error),
            "calibration_error_limit": canonical_decimal(_MAX_CALIBRATION_ERROR),
            "oos_calibration_error_limit": canonical_decimal(
                _MAX_OOS_CALIBRATION_ERROR
            ),
            "method": "FIXED_DECILE_CLASSWISE_ECE",
        }
        calibration_result_digest = canonical_digest(calibration_result)
        proper_scoring_result = {
            "scoring_rule": self.scoring_rule.value,
            "calibration_score": canonical_decimal(calibration_score),
            "oos_score": canonical_decimal(oos_score),
            "development_frequency_baseline_oos_score": canonical_decimal(
                oos_baseline_score
            ),
            "lower_is_better": True,
            "calibration_sample_digest": calibration_digest,
            "oos_sample_digest": oos_digest,
        }
        proper_scoring_result_digest = canonical_digest(proper_scoring_result)
        drift_assessment = {
            "score_degradation": canonical_decimal(score_degradation),
            "calibration_error_drift": canonical_decimal(calibration_error_drift),
            "outcome_distribution_total_variation": canonical_decimal(
                outcome_distribution_drift
            ),
            "prediction_distribution_total_variation": canonical_decimal(
                prediction_distribution_drift
            ),
            "maximum_score_degradation": canonical_decimal(
                _MAX_PROPER_SCORE_DEGRADATION
            ),
            "maximum_calibration_error_drift": canonical_decimal(
                _MAX_CALIBRATION_ERROR_DRIFT
            ),
            "maximum_distribution_drift": canonical_decimal(
                _MAX_DISTRIBUTION_DRIFT
            ),
            "status": "WITHIN_FIXED_LIMITS",
        }
        drift_assessment_digest = canonical_digest(drift_assessment)
        oos_evaluation_digest = canonical_digest(
            {
                "oos_sample_digest": oos_digest,
                "calibration_result_digest": calibration_result_digest,
                "proper_scoring_result_digest": proper_scoring_result_digest,
                "drift_assessment_digest": drift_assessment_digest,
            }
        )
        return {
            "event_contract_digest": event_digest,
            "model_digest": model_digest,
            "outcome_ids": outcome_ids,
            "development_sample_digest": development_digest,
            "calibration_sample_digest": calibration_digest,
            "oos_sample_digest": oos_digest,
            "deployment_forecast_digest": deployment_digest,
            "oos_evaluation_digest": oos_evaluation_digest,
            "calibration_result_digest": calibration_result_digest,
            "proper_scoring_result_digest": proper_scoring_result_digest,
            "drift_assessment_digest": drift_assessment_digest,
            "score_value": oos_score,
            "calibration_error": calibration_error,
            "oos_calibration_error": oos_calibration_error,
        }

    def assert_verified(self) -> None:
        computed = self._recompute()
        if any(getattr(self, name) != value for name, value in computed.items()):
            raise ProbabilityCloudError("CALIBRATION_RECEIPT_RECOMPUTATION_MISMATCH")

    def to_document(self) -> dict[str, Any]:
        self.assert_verified()
        return self_digest(
            {
                "schema_id": "theory_paper_v2_v31_predictive_validation_receipt",
                "schema_version": "2.0.0",
                "receipt_id": self.receipt_id,
                "event_contract_ref": self.event_contract_ref,
                "event_contract": dict(self.event_contract),
                "event_contract_digest": self.event_contract_digest,
                "horizon": self.horizon,
                "model_ref": self.model_ref,
                "model_contract": dict(self.model_contract),
                "model_digest": self.model_digest,
                "outcome_ids": list(self.outcome_ids),
                "development_sample": [
                    row.to_document() for row in self.development_sample
                ],
                "development_sample_digest": self.development_sample_digest,
                "calibration_sample": [
                    row.to_document() for row in self.calibration_sample
                ],
                "calibration_sample_digest": self.calibration_sample_digest,
                "oos_sample": [row.to_document() for row in self.oos_sample],
                "oos_sample_digest": self.oos_sample_digest,
                "deployment_forecast": self.deployment_forecast.to_document(),
                "deployment_forecast_digest": self.deployment_forecast_digest,
                "oos_evaluation_digest": self.oos_evaluation_digest,
                "calibration_result_digest": self.calibration_result_digest,
                "proper_scoring_result_digest": self.proper_scoring_result_digest,
                "drift_assessment_digest": self.drift_assessment_digest,
                "scoring_rule": self.scoring_rule.value,
                "score_value": canonical_decimal(self.score_value),
                "calibration_error": canonical_decimal(self.calibration_error),
                "oos_calibration_error": canonical_decimal(
                    self.oos_calibration_error
                ),
                "available_at": self.available_at,
                "calibration_method": "FIXED_DECILE_ECE_AND_PROPER_SCORE_REPLAY",
                "drift_guard": "FIXED_SCORE_ECE_AND_DISTRIBUTION_LIMITS",
                "minimum_split_size": _MIN_VALIDATION_SPLIT_SIZE,
                "verification_status": "VERIFIED_BY_DETERMINISTIC_RECOMPUTATION",
                "evidence_boundary": (
                    "LOCAL_RECOMPUTATION_DOES_NOT_PROVE_EXTERNAL_SOURCE_PROVENANCE"
                ),
                "invalidation_conditions": list(self.invalidation_conditions),
                "limitations": list(self.limitations),
            },
            "validation_receipt_digest",
        )


@dataclass(frozen=True, slots=True)
class CloudUpdateEvidence:
    evidence_ref: str
    evidence_digest: str
    available_at: str
    quality: str
    effect: EvidenceEffect
    dependency_group: str
    regime_ref: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.evidence_ref,
                self.dependency_group,
                self.regime_ref,
            )
        ):
            raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_INVALID")
        if _HEX_64.fullmatch(str(self.evidence_digest or "")) is None:
            raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_DIGEST_INVALID")
        _timestamp(self.available_at, "CLOUD_UPDATE_EVIDENCE_TIME_INVALID")
        if self.quality not in {"HIGH", "MEDIUM", "LOW", "UNUSABLE", "UNKNOWN"}:
            raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_QUALITY_INVALID")
        if not isinstance(self.effect, EvidenceEffect):
            raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_EFFECT_INVALID")
        if self.quality == "UNUSABLE" and self.effect in {
            EvidenceEffect.SUPPORT,
            EvidenceEffect.OPPOSE,
        }:
            raise ProbabilityCloudError("UNUSABLE_EVIDENCE_CANNOT_MOVE_CLOUD")
        object.__setattr__(
            self,
            "limitations",
            _refs(
                self.limitations,
                "CLOUD_UPDATE_EVIDENCE_LIMITATIONS_INVALID",
                allow_empty=True,
            ),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "evidence_ref": self.evidence_ref,
            "evidence_digest": self.evidence_digest,
            "available_at": self.available_at,
            "quality": self.quality,
            "effect": self.effect.value,
            "dependency_group": self.dependency_group,
            "regime_ref": self.regime_ref,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class ProbabilityCloud:
    cloud_id: str
    mode: ProbabilityMode
    decision_at: str
    available_at: str
    horizon: str
    components: tuple[CloudComponent, ...]
    event_contract_ref: str | None = None
    event_contract_digest: str | None = None
    sample_contract_refs: tuple[str, ...] = ()
    model_refs: tuple[str, ...] = ()
    market_contract_refs: tuple[str, ...] = ()
    liquidity_assumptions: tuple[str, ...] = ()
    risk_premium_assumptions: tuple[str, ...] = ()
    validation_receipts: tuple[PredictiveValidationReceipt, ...] = ()
    unknown_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    mutually_exclusive: bool = False
    exhaustive: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.cloud_id, str) or not self.cloud_id.strip():
            raise ProbabilityCloudError("CLOUD_ID_INVALID")
        if not isinstance(self.mode, ProbabilityMode):
            raise ProbabilityCloudError("CLOUD_MODE_INVALID")
        decision = _timestamp(self.decision_at, "CLOUD_DECISION_AT_INVALID")
        available = _timestamp(self.available_at, "CLOUD_AVAILABLE_AT_INVALID")
        if available > decision:
            raise ProbabilityCloudError("CLOUD_FUTURE_INFORMATION_FORBIDDEN")
        if not isinstance(self.horizon, str) or not self.horizon.strip():
            raise ProbabilityCloudError("CLOUD_HORIZON_INVALID")
        components = tuple(self.components)
        if not components or any(not isinstance(item, CloudComponent) for item in components):
            raise ProbabilityCloudError("CLOUD_COMPONENTS_INVALID")
        ids = tuple(item.hypothesis_id for item in components)
        if len(ids) != len(set(ids)):
            raise ProbabilityCloudError("CLOUD_COMPONENT_DUPLICATE")
        object.__setattr__(self, "components", components)
        for field_name in (
            "sample_contract_refs",
            "model_refs",
            "market_contract_refs",
            "liquidity_assumptions",
            "risk_premium_assumptions",
            "unknown_refs",
            "limitations",
        ):
            object.__setattr__(
                self,
                field_name,
                _refs(getattr(self, field_name), "CLOUD_METADATA_INVALID", allow_empty=True),
            )
        if self.event_contract_ref is not None and (
            not isinstance(self.event_contract_ref, str)
            or not self.event_contract_ref.strip()
        ):
            raise ProbabilityCloudError("CLOUD_EVENT_CONTRACT_INVALID")
        if (self.event_contract_ref is None) != (self.event_contract_digest is None) or (
            self.event_contract_digest is not None
            and _HEX_64.fullmatch(self.event_contract_digest) is None
        ):
            raise ProbabilityCloudError("CLOUD_EVENT_CONTRACT_BINDING_INVALID")
        receipts = tuple(self.validation_receipts)
        if any(not isinstance(item, PredictiveValidationReceipt) for item in receipts):
            raise ProbabilityCloudError("CLOUD_VALIDATION_RECEIPTS_INVALID")
        receipt_ids = tuple(item.receipt_id for item in receipts)
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ProbabilityCloudError("CLOUD_VALIDATION_RECEIPTS_DUPLICATE")
        object.__setattr__(self, "validation_receipts", receipts)
        if not isinstance(self.mutually_exclusive, bool) or not isinstance(
            self.exhaustive, bool
        ):
            raise ProbabilityCloudError("CLOUD_PARTITION_FLAGS_INVALID")
        self._validate_mode(ids)

    def _validate_mode(self, ids: tuple[str, ...]) -> None:
        has_other = "OTHER" in ids
        has_unknown = "UNKNOWN" in ids
        if not has_other:
            raise ProbabilityCloudError("CLOUD_OTHER_REQUIRED")

        if self.mode is ProbabilityMode.SUBJECTIVE_PLAUSIBILITY:
            if not has_unknown:
                raise ProbabilityCloudError("CLOUD_UNKNOWN_REQUIRED")
            for component in self.components:
                if component.probability is not None:
                    raise ProbabilityCloudError("UNCALIBRATED_POINT_PROBABILITY_FORBIDDEN")
                if component.hypothesis_id != "UNKNOWN" and component.plausibility is None:
                    raise ProbabilityCloudError("SUBJECTIVE_PLAUSIBILITY_REQUIRED")
                if component.hypothesis_id == "UNKNOWN" and component.plausibility is not PlausibilityLevel.UNKNOWN:
                    raise ProbabilityCloudError("SUBJECTIVE_UNKNOWN_PLAUSIBILITY_REQUIRED")
                if (
                    component.lower is not None
                    and component.upper is not None
                    and component.lower == component.upper
                ):
                    raise ProbabilityCloudError("SUBJECTIVE_POINT_ESTIMATE_FORBIDDEN")
                if component.hypothesis_id not in {"UNKNOWN", "OTHER"} and (
                    not component.evidence_refs
                    or not (component.opposition_refs or component.conflict_refs)
                    or not component.sensitivity_notes
                ):
                    raise ProbabilityCloudError("SUBJECTIVE_COMPETITION_AND_SENSITIVITY_REQUIRED")
            if self.mutually_exclusive or self.exhaustive:
                raise ProbabilityCloudError("SUBJECTIVE_NORMALIZATION_CONTRACT_FORBIDDEN")
            if not self.unknown_refs or not self.limitations:
                raise ProbabilityCloudError("SUBJECTIVE_UNKNOWN_AND_LIMITATIONS_REQUIRED")
            if self.validation_receipts:
                raise ProbabilityCloudError("UNCALIBRATED_VALIDATION_RECEIPTS_FORBIDDEN")
            return

        if self.mode is ProbabilityMode.EMPIRICAL_OR_MODEL_CONDITIONAL:
            if not has_unknown:
                raise ProbabilityCloudError("CLOUD_UNKNOWN_REQUIRED")
            if not (self.sample_contract_refs or self.model_refs) or not self.event_contract_ref:
                raise ProbabilityCloudError("MODEL_CONDITIONAL_CONTRACT_REQUIRED")
            for component in self.components:
                if component.probability is not None:
                    raise ProbabilityCloudError("UNCALIBRATED_POINT_PROBABILITY_FORBIDDEN")
                if component.plausibility is not None:
                    raise ProbabilityCloudError("MODEL_CONDITIONAL_PLAUSIBILITY_FORBIDDEN")
                if component.hypothesis_id != "UNKNOWN" and component.lower is None:
                    raise ProbabilityCloudError("MODEL_CONDITIONAL_INTERVAL_REQUIRED")
            self._validate_interval_partition()
            if self.validation_receipts:
                raise ProbabilityCloudError("UNCALIBRATED_VALIDATION_RECEIPTS_FORBIDDEN")
            return

        if self.mode is ProbabilityMode.MARKET_IMPLIED_BELIEF:
            if not has_unknown:
                raise ProbabilityCloudError("CLOUD_UNKNOWN_REQUIRED")
            if (
                not self.event_contract_ref
                or not self.market_contract_refs
                or not self.liquidity_assumptions
                or not self.risk_premium_assumptions
            ):
                raise ProbabilityCloudError("MARKET_IMPLIED_BOUNDARY_REQUIRED")
            for component in self.components:
                if component.probability is not None:
                    raise ProbabilityCloudError("MARKET_PRICE_NOT_OBJECTIVE_PROBABILITY")
                if component.plausibility is not None:
                    raise ProbabilityCloudError("MARKET_IMPLIED_PLAUSIBILITY_FORBIDDEN")
                if component.hypothesis_id != "UNKNOWN" and component.lower is None:
                    raise ProbabilityCloudError("MARKET_IMPLIED_INTERVAL_REQUIRED")
            self._validate_interval_partition()
            if self.validation_receipts:
                raise ProbabilityCloudError("UNCALIBRATED_VALIDATION_RECEIPTS_FORBIDDEN")
            return

        if self.mode is ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION:
            if has_unknown:
                raise ProbabilityCloudError("CALIBRATED_OUTCOME_UNKNOWN_FORBIDDEN")
            if not (
                self.event_contract_ref
                and self.mutually_exclusive
                and self.exhaustive
                and self.validation_receipts
            ):
                raise ProbabilityCloudError("CALIBRATED_DISTRIBUTION_GATE_FAILED")
            decision = _timestamp(self.decision_at, "CLOUD_DECISION_AT_INVALID")
            available = _timestamp(self.available_at, "CLOUD_AVAILABLE_AT_INVALID")
            cloud_probability_vector = tuple(
                sorted(
                    (
                        component.hypothesis_id,
                        component.probability,
                    )
                    for component in self.components
                )
            )
            receipt_model_refs: set[str] = set()
            receipt_ids: set[str] = set()
            for receipt in self.validation_receipts:
                receipt.assert_verified()
                deployment_prediction = _timestamp(
                    receipt.deployment_forecast.prediction_at,
                    "FORECAST_PREDICTION_TIME_INVALID",
                )
                if (
                    receipt.event_contract_ref != self.event_contract_ref
                    or receipt.event_contract_digest != self.event_contract_digest
                    or receipt.horizon != self.horizon
                    or receipt.outcome_ids != tuple(sorted(ids))
                    or receipt.deployment_forecast.probabilities
                    != cloud_probability_vector
                    or _timestamp(receipt.available_at, "CALIBRATION_AVAILABLE_AT_INVALID")
                    > decision
                    or deployment_prediction < _timestamp(
                        receipt.available_at, "CALIBRATION_AVAILABLE_AT_INVALID"
                    )
                    or deployment_prediction > available
                ):
                    raise ProbabilityCloudError("CALIBRATION_RECEIPT_CLOUD_BINDING_INVALID")
                receipt_model_refs.add(receipt.model_ref)
                receipt_ids.add(receipt.receipt_id)
            if set(self.model_refs) != receipt_model_refs or set(
                self.sample_contract_refs
            ) != receipt_ids:
                raise ProbabilityCloudError("CALIBRATION_RECEIPT_CLOUD_BINDING_INVALID")
            total = _ZERO
            for component in self.components:
                if (
                    component.probability is None
                    or component.lower is not None
                    or component.upper is not None
                    or component.plausibility is not None
                ):
                    raise ProbabilityCloudError("CALIBRATED_COMPONENT_INVALID")
                total += component.probability
            if total != _ONE:
                raise ProbabilityCloudError("CALIBRATED_PROBABILITIES_MUST_SUM_TO_ONE")
            return

        raise ProbabilityCloudError("CLOUD_MODE_INVALID")

    def _validate_interval_partition(self) -> None:
        if self.mutually_exclusive != self.exhaustive:
            raise ProbabilityCloudError("CLOUD_PARTITION_FLAGS_INCONSISTENT")
        if not self.mutually_exclusive:
            return
        if any(item.lower is None or item.upper is None for item in self.components):
            raise ProbabilityCloudError("CLOUD_COMPLETE_INTERVAL_PARTITION_REQUIRED")
        lower_total = sum((item.lower for item in self.components), _ZERO)
        upper_total = sum((item.upper for item in self.components), _ZERO)
        if lower_total > _ONE or upper_total < _ONE:
            raise ProbabilityCloudError("CLOUD_INTERVAL_PARTITION_INCOHERENT")

    @property
    def allows_expected_value(self) -> bool:
        if self.mode is not ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION:
            return False
        try:
            for receipt in self.validation_receipts:
                receipt.assert_verified()
        except ProbabilityCloudError:
            return False
        return True

    def assert_expected_value_allowed(self) -> None:
        if not self.allows_expected_value:
            raise ProbabilityCloudError("EXPECTED_VALUE_REQUIRES_CALIBRATED_DISTRIBUTION")

    def to_document(self) -> dict[str, Any]:
        document = {
            "schema_id": "theory_paper_v2_v31_probability_cloud",
            "schema_version": "1.0.0",
            "cloud_id": self.cloud_id,
            "mode": self.mode.value,
            "decision_at": self.decision_at,
            "available_at": self.available_at,
            "horizon": self.horizon,
            "components": [item.to_document() for item in self.components],
            "event_contract_ref": self.event_contract_ref,
            "event_contract_digest": self.event_contract_digest,
            "sample_contract_refs": list(self.sample_contract_refs),
            "model_refs": list(self.model_refs),
            "market_contract_refs": list(self.market_contract_refs),
            "liquidity_assumptions": list(self.liquidity_assumptions),
            "risk_premium_assumptions": list(self.risk_premium_assumptions),
            "validation_receipts": [
                item.to_document() for item in self.validation_receipts
            ],
            "unknown_refs": list(self.unknown_refs),
            "limitations": list(self.limitations),
            "mutually_exclusive": self.mutually_exclusive,
            "exhaustive": self.exhaustive,
            "expected_value_allowed": self.allows_expected_value,
        }
        document["cloud_digest"] = canonical_digest(document)
        return document


def seal_probability_cloud_update(
    *,
    prior_cloud: ProbabilityCloud,
    updated_cloud: ProbabilityCloud,
    evidence: Sequence[CloudUpdateEvidence],
    dependency_adjustments: Sequence[str],
    conflict_refs: Sequence[str],
    update_method: str,
    model_version: str,
    sensitivity_notes: Sequence[str],
    updated_at: str,
    no_update_reason: str | None = None,
) -> dict[str, Any]:
    """Create an append-only receipt for one explicit cloud transition."""

    evidence_rows = tuple(evidence)
    if not evidence_rows or any(
        not isinstance(item, CloudUpdateEvidence) for item in evidence_rows
    ):
        raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_REQUIRED")
    identities = tuple((item.evidence_ref, item.evidence_digest) for item in evidence_rows)
    if len(identities) != len(set(identities)):
        raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_DUPLICATE")
    dependencies = _refs(
        dependency_adjustments, "CLOUD_UPDATE_DEPENDENCY_INVALID", allow_empty=True
    )
    conflicts = _refs(conflict_refs, "CLOUD_UPDATE_CONFLICT_INVALID", allow_empty=True)
    sensitivities = _refs(
        sensitivity_notes, "CLOUD_UPDATE_SENSITIVITY_INVALID", allow_empty=True
    )
    if not isinstance(update_method, str) or not update_method.strip():
        raise ProbabilityCloudError("CLOUD_UPDATE_METHOD_REQUIRED")
    if not isinstance(model_version, str) or not model_version.strip():
        raise ProbabilityCloudError("CLOUD_UPDATE_MODEL_VERSION_REQUIRED")
    update_time = _timestamp(updated_at, "CLOUD_UPDATE_TIME_INVALID")
    prior_decision = _timestamp(prior_cloud.decision_at, "CLOUD_DECISION_AT_INVALID")
    decision_time = _timestamp(updated_cloud.decision_at, "CLOUD_DECISION_AT_INVALID")
    if update_time < decision_time or decision_time < prior_decision:
        raise ProbabilityCloudError("CLOUD_UPDATE_PRECEDES_DECISION")
    if _timestamp(updated_cloud.available_at, "CLOUD_AVAILABLE_AT_INVALID") < _timestamp(
        prior_cloud.available_at, "CLOUD_AVAILABLE_AT_INVALID"
    ):
        raise ProbabilityCloudError("CLOUD_UPDATE_AVAILABILITY_REGRESSION")
    if any(
        _timestamp(item.available_at, "CLOUD_UPDATE_EVIDENCE_TIME_INVALID")
        > decision_time
        for item in evidence_rows
    ):
        raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_NOT_PIT")
    if (
        prior_cloud.cloud_id != updated_cloud.cloud_id
        or prior_cloud.mode is not updated_cloud.mode
        or prior_cloud.horizon != updated_cloud.horizon
        or prior_cloud.event_contract_ref != updated_cloud.event_contract_ref
        or prior_cloud.event_contract_digest != updated_cloud.event_contract_digest
        or {item.hypothesis_id for item in prior_cloud.components}
        != {item.hypothesis_id for item in updated_cloud.components}
    ):
        raise ProbabilityCloudError("CLOUD_UPDATE_IDENTITY_OR_PARTITION_CHANGED")
    prior_digest = prior_cloud.to_document()["cloud_digest"]
    updated_digest = updated_cloud.to_document()["cloud_digest"]
    if prior_digest == updated_digest and not (
        isinstance(no_update_reason, str) and no_update_reason.strip()
    ):
        raise ProbabilityCloudError("CLOUD_NO_CHANGE_REASON_REQUIRED")
    if prior_digest != updated_digest and no_update_reason is not None:
        raise ProbabilityCloudError("CLOUD_NO_CHANGE_REASON_CONTRADICTS_UPDATE")
    prior_components = {
        item.hypothesis_id: item.to_document() for item in prior_cloud.components
    }
    updated_components = {
        item.hypothesis_id: item.to_document() for item in updated_cloud.components
    }
    component_deltas = [
        {
            "hypothesis_id": hypothesis_id,
            "prior": prior_components[hypothesis_id],
            "updated": updated_components[hypothesis_id],
            "changed": prior_components[hypothesis_id]
            != updated_components[hypothesis_id],
        }
        for hypothesis_id in sorted(prior_components)
    ]
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_probability_cloud_update",
            "schema_version": "1.0.0",
            "cloud_id": updated_cloud.cloud_id,
            "prior_cloud_digest": prior_digest,
            "updated_cloud_digest": updated_digest,
            "evidence": [item.to_document() for item in evidence_rows],
            "support_evidence_refs": [
                item.evidence_ref
                for item in evidence_rows
                if item.effect is EvidenceEffect.SUPPORT
            ],
            "opposition_evidence_refs": [
                item.evidence_ref
                for item in evidence_rows
                if item.effect is EvidenceEffect.OPPOSE
            ],
            "missing_constraint_refs": [
                item.evidence_ref
                for item in evidence_rows
                if item.effect is EvidenceEffect.MISSING_CONSTRAINT
            ],
            "regime_refs": sorted({item.regime_ref for item in evidence_rows}),
            "dependency_adjustments": list(dependencies),
            "conflict_refs": list(conflicts),
            "component_deltas": component_deltas,
            "update_method": update_method,
            "model_version": model_version,
            "sensitivity_notes": list(sensitivities),
            "updated_at": updated_at,
            "no_update_reason": no_update_reason,
        },
        "update_receipt_digest",
    )


def seal_probability_cloud_repartition(
    *,
    prior_cloud: ProbabilityCloud,
    repartitioned_cloud: ProbabilityCloud,
    evidence: Sequence[CloudUpdateEvidence],
    added_hypothesis_reasons: Mapping[str, str],
    retired_hypothesis_reasons: Mapping[str, str],
    sensitivity_notes: Sequence[str],
    repartitioned_at: str,
) -> dict[str, Any]:
    """Create a distinct, explicit lineage receipt when hypothesis membership changes."""

    rows = tuple(evidence)
    if not rows or any(not isinstance(item, CloudUpdateEvidence) for item in rows):
        raise ProbabilityCloudError("CLOUD_REPARTITION_EVIDENCE_REQUIRED")
    prior_ids = {item.hypothesis_id for item in prior_cloud.components}
    updated_ids = {item.hypothesis_id for item in repartitioned_cloud.components}
    added = updated_ids - prior_ids
    retired = prior_ids - updated_ids
    if not added and not retired:
        raise ProbabilityCloudError("CLOUD_REPARTITION_MEMBERSHIP_UNCHANGED")
    if (
        prior_cloud.cloud_id == repartitioned_cloud.cloud_id
        or prior_cloud.mode is not repartitioned_cloud.mode
        or prior_cloud.horizon != repartitioned_cloud.horizon
        or prior_cloud.event_contract_ref != repartitioned_cloud.event_contract_ref
        or prior_cloud.event_contract_digest
        != repartitioned_cloud.event_contract_digest
        or set(added_hypothesis_reasons) != added
        or set(retired_hypothesis_reasons) != retired
        or any(
            not isinstance(reason, str) or not reason.strip()
            for reason in (
                *added_hypothesis_reasons.values(),
                *retired_hypothesis_reasons.values(),
            )
        )
    ):
        raise ProbabilityCloudError("CLOUD_REPARTITION_CONTRACT_INVALID")
    occurred = _timestamp(repartitioned_at, "CLOUD_REPARTITION_TIME_INVALID")
    decision = _timestamp(
        repartitioned_cloud.decision_at, "CLOUD_DECISION_AT_INVALID"
    )
    if _timestamp(
        repartitioned_cloud.available_at, "CLOUD_AVAILABLE_AT_INVALID"
    ) < _timestamp(prior_cloud.available_at, "CLOUD_AVAILABLE_AT_INVALID"):
        raise ProbabilityCloudError(
            "CLOUD_REPARTITION_AVAILABILITY_REGRESSION"
        )
    if (
        occurred < decision
        or decision
        < _timestamp(prior_cloud.decision_at, "CLOUD_DECISION_AT_INVALID")
        or any(
            _timestamp(item.available_at, "CLOUD_UPDATE_EVIDENCE_TIME_INVALID")
            > decision
            for item in rows
        )
    ):
        raise ProbabilityCloudError("CLOUD_REPARTITION_NOT_PIT")
    sensitivities = _refs(
        sensitivity_notes, "CLOUD_REPARTITION_SENSITIVITY_REQUIRED"
    )
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_probability_cloud_repartition",
            "schema_version": "1.0.0",
            "prior_cloud_id": prior_cloud.cloud_id,
            "repartitioned_cloud_id": repartitioned_cloud.cloud_id,
            "prior_cloud_digest": prior_cloud.to_document()["cloud_digest"],
            "repartitioned_cloud_digest": repartitioned_cloud.to_document()[
                "cloud_digest"
            ],
            "added_hypothesis_reasons": dict(
                sorted(added_hypothesis_reasons.items())
            ),
            "retired_hypothesis_reasons": dict(
                sorted(retired_hypothesis_reasons.items())
            ),
            "evidence": [item.to_document() for item in rows],
            "sensitivity_notes": list(sensitivities),
            "repartitioned_at": repartitioned_at,
            "mode_unchanged": True,
        },
        "repartition_receipt_digest",
    )


_CLOUD_UPDATE_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cloud_id",
        "prior_cloud_digest",
        "updated_cloud_digest",
        "evidence",
        "support_evidence_refs",
        "opposition_evidence_refs",
        "missing_constraint_refs",
        "regime_refs",
        "dependency_adjustments",
        "conflict_refs",
        "component_deltas",
        "update_method",
        "model_version",
        "sensitivity_notes",
        "updated_at",
        "no_update_reason",
        "update_receipt_digest",
    }
)
_CLOUD_REPARTITION_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "prior_cloud_id",
        "repartitioned_cloud_id",
        "prior_cloud_digest",
        "repartitioned_cloud_digest",
        "added_hypothesis_reasons",
        "retired_hypothesis_reasons",
        "evidence",
        "sensitivity_notes",
        "repartitioned_at",
        "mode_unchanged",
        "repartition_receipt_digest",
    }
)
_CLOUD_UPDATE_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_ref",
        "evidence_digest",
        "available_at",
        "quality",
        "effect",
        "dependency_group",
        "regime_ref",
        "limitations",
    }
)


def _cloud_update_evidence_from_document(
    document: Mapping[str, Any],
) -> CloudUpdateEvidence:
    if not isinstance(document, Mapping) or set(document) != _CLOUD_UPDATE_EVIDENCE_FIELDS:
        raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_SCHEMA_INVALID")
    limitations = document["limitations"]
    if not isinstance(limitations, list):
        raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_SCHEMA_INVALID")
    try:
        rebuilt = CloudUpdateEvidence(
            evidence_ref=document["evidence_ref"],
            evidence_digest=document["evidence_digest"],
            available_at=document["available_at"],
            quality=document["quality"],
            effect=EvidenceEffect(document["effect"]),
            dependency_group=document["dependency_group"],
            regime_ref=document["regime_ref"],
            limitations=tuple(limitations),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ProbabilityCloudError):
            raise
        raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_INVALID") from exc
    if rebuilt.to_document() != dict(document):
        raise ProbabilityCloudError("CLOUD_UPDATE_EVIDENCE_CANONICAL_INVALID")
    return rebuilt


def verify_probability_cloud_update(
    document: Mapping[str, Any],
    *,
    prior_cloud: ProbabilityCloud,
    updated_cloud: ProbabilityCloud,
) -> str:
    """Rebuild an update receipt from its primitive evidence and exact clouds."""

    if not isinstance(document, Mapping) or set(document) != _CLOUD_UPDATE_RECEIPT_FIELDS:
        raise ProbabilityCloudError("CLOUD_UPDATE_RECEIPT_SCHEMA_INVALID")
    evidence_raw = document.get("evidence")
    if not isinstance(evidence_raw, list):
        raise ProbabilityCloudError("CLOUD_UPDATE_RECEIPT_SCHEMA_INVALID")
    evidence = tuple(
        _cloud_update_evidence_from_document(row) for row in evidence_raw
    )
    rebuilt = seal_probability_cloud_update(
        prior_cloud=prior_cloud,
        updated_cloud=updated_cloud,
        evidence=evidence,
        dependency_adjustments=document["dependency_adjustments"],
        conflict_refs=document["conflict_refs"],
        update_method=document["update_method"],
        model_version=document["model_version"],
        sensitivity_notes=document["sensitivity_notes"],
        updated_at=document["updated_at"],
        no_update_reason=document["no_update_reason"],
    )
    if rebuilt != dict(document):
        raise ProbabilityCloudError("CLOUD_UPDATE_RECEIPT_REPLAY_MISMATCH")
    return rebuilt["update_receipt_digest"]


def verify_probability_cloud_repartition(
    document: Mapping[str, Any],
    *,
    prior_cloud: ProbabilityCloud,
    repartitioned_cloud: ProbabilityCloud,
) -> str:
    """Rebuild a repartition receipt from primitive evidence and exact clouds."""

    if (
        not isinstance(document, Mapping)
        or set(document) != _CLOUD_REPARTITION_RECEIPT_FIELDS
    ):
        raise ProbabilityCloudError("CLOUD_REPARTITION_RECEIPT_SCHEMA_INVALID")
    evidence_raw = document.get("evidence")
    if not isinstance(evidence_raw, list):
        raise ProbabilityCloudError("CLOUD_REPARTITION_RECEIPT_SCHEMA_INVALID")
    evidence = tuple(
        _cloud_update_evidence_from_document(row) for row in evidence_raw
    )
    rebuilt = seal_probability_cloud_repartition(
        prior_cloud=prior_cloud,
        repartitioned_cloud=repartitioned_cloud,
        evidence=evidence,
        added_hypothesis_reasons=document["added_hypothesis_reasons"],
        retired_hypothesis_reasons=document["retired_hypothesis_reasons"],
        sensitivity_notes=document["sensitivity_notes"],
        repartitioned_at=document["repartitioned_at"],
    )
    if rebuilt != dict(document):
        raise ProbabilityCloudError("CLOUD_REPARTITION_RECEIPT_REPLAY_MISMATCH")
    return rebuilt["repartition_receipt_digest"]


__all__ = [
    "CloudComponent",
    "CloudUpdateEvidence",
    "EvidenceEffect",
    "FrozenPredictionOutcome",
    "FrozenPredictiveForecast",
    "PlausibilityLevel",
    "PredictiveValidationReceipt",
    "ProperScoringRule",
    "ProbabilityCloud",
    "ProbabilityCloudError",
    "ProbabilityMode",
    "seal_probability_cloud_update",
    "seal_probability_cloud_repartition",
    "verify_probability_cloud_repartition",
    "verify_probability_cloud_update",
]
