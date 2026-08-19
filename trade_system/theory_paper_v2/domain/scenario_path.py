"""Typed V3.1 if--then scenario-path contracts.

A scenario rule may advance exactly one epistemic step.  Action implications
express what a path favours or opposes; they never authorize an action and
cannot bypass portfolio, risk, cost, or permission checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    CanonicalContractError,
    canonical_decimal,
    canonical_digest,
)
from .behavior_planning import ActionType


class ScenarioPathError(ValueError):
    """A scenario path is incomplete or crosses an epistemic boundary."""


class PredicateOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    EXISTS = "EXISTS"


class EpistemicStage(StrEnum):
    OBSERVED_INFORMATION = "OBSERVED_INFORMATION"
    OBSERVED_FACT = "OBSERVED_FACT"
    DERIVED_MEASURE = "DERIVED_MEASURE"
    ASSOCIATION = "ASSOCIATION"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    FORECAST = "FORECAST"
    POLICY_CANDIDATE = "POLICY_CANDIDATE"
    AUTHORIZED_ACTION = "AUTHORIZED_ACTION"
    OUTCOME = "OUTCOME"


class ImplicationEffect(StrEnum):
    FAVORS = "FAVORS"
    OPPOSES = "OPPOSES"
    CONDITIONAL = "CONDITIONAL"


class PredicateTruth(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class PredicateTiming(StrEnum):
    DECISION_INPUT = "DECISION_INPUT"
    FUTURE_MONITOR = "FUTURE_MONITOR"


class PredicateQuality(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"
    UNUSABLE = "UNUSABLE"


_ALLOWED_TRANSITIONS = frozenset(
    {
        (EpistemicStage.OBSERVED_INFORMATION, EpistemicStage.OBSERVED_FACT),
        (EpistemicStage.OBSERVED_FACT, EpistemicStage.DERIVED_MEASURE),
        (EpistemicStage.DERIVED_MEASURE, EpistemicStage.ASSOCIATION),
        (EpistemicStage.DERIVED_MEASURE, EpistemicStage.INFERENCE),
        (EpistemicStage.ASSOCIATION, EpistemicStage.INFERENCE),
        (EpistemicStage.INFERENCE, EpistemicStage.HYPOTHESIS),
        (EpistemicStage.HYPOTHESIS, EpistemicStage.FORECAST),
        (EpistemicStage.FORECAST, EpistemicStage.POLICY_CANDIDATE),
        (EpistemicStage.AUTHORIZED_ACTION, EpistemicStage.OUTCOME),
    }
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_QUALITY_RANK = {
    PredicateQuality.UNUSABLE: 0,
    PredicateQuality.UNKNOWN: 0,
    PredicateQuality.LOW: 1,
    PredicateQuality.MEDIUM: 2,
    PredicateQuality.HIGH: 3,
}
_TRANSITION_UPDATE_TYPES = frozenset(
    {"ADD", "REVISE", "PROMOTE", "DEMOTE", "INVALIDATE", "RETIRE"}
)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise ScenarioPathError(code)
    return value


def _timestamp(value: str, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ScenarioPathError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScenarioPathError(code) from exc
    if parsed.tzinfo is None:
        raise ScenarioPathError(code)
    return parsed.astimezone(UTC)


def _strings(values: Sequence[str], code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ScenarioPathError(code)
    result = tuple(values)
    if (not allow_empty and not result) or any(
        not isinstance(value, str) or not value.strip() for value in result
    ) or len(result) != len(set(result)):
        raise ScenarioPathError(code)
    return result


def _coverage(value: Decimal | str, code: str) -> Decimal:
    if isinstance(value, float):
        raise ScenarioPathError("PATH_BINARY_FLOAT_FORBIDDEN")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ScenarioPathError(code) from exc
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise ScenarioPathError(code)
    return parsed


@dataclass(frozen=True, slots=True)
class PathFactSnapshot:
    fact_ref: str
    fact_digest: str
    value: Any
    available_at: str
    missingness: str
    quality: PredicateQuality
    coverage: Decimal | str
    conflict_state: str

    def __post_init__(self) -> None:
        if not isinstance(self.fact_ref, str) or not self.fact_ref.strip():
            raise ScenarioPathError("PATH_FACT_REF_INVALID")
        if _HEX_64.fullmatch(str(self.fact_digest or "")) is None:
            raise ScenarioPathError("PATH_FACT_DIGEST_INVALID")
        _timestamp(self.available_at, "PATH_FACT_AVAILABLE_AT_INVALID")
        if not isinstance(self.missingness, str) or not self.missingness:
            raise ScenarioPathError("PATH_FACT_MISSINGNESS_INVALID")
        if not isinstance(self.quality, PredicateQuality):
            raise ScenarioPathError("PATH_FACT_QUALITY_INVALID")
        object.__setattr__(
            self, "coverage", _coverage(self.coverage, "PATH_FACT_COVERAGE_INVALID")
        )
        if not isinstance(self.conflict_state, str) or not self.conflict_state:
            raise ScenarioPathError("PATH_FACT_CONFLICT_INVALID")
        if self.missingness == "OBSERVED" and self.value is None:
            raise ScenarioPathError("PATH_FACT_VALUE_MISSING_CONTRADICTION")
        if self.missingness != "OBSERVED" and self.value is not None:
            raise ScenarioPathError("PATH_FACT_VALUE_MISSING_CONTRADICTION")
        try:
            canonical_digest(self.value)
        except CanonicalContractError as exc:
            raise ScenarioPathError("PATH_FACT_VALUE_INVALID") from exc


@dataclass(frozen=True, slots=True)
class PathPredicate:
    predicate_id: str
    fact_ref: str
    fact_digest: str | None
    timing: PredicateTiming
    operator: PredicateOperator
    expected: Any
    available_at: str
    minimum_quality: PredicateQuality
    minimum_coverage: Decimal | str
    allowed_conflict_states: tuple[str, ...]
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.predicate_id, self.fact_ref)
        ):
            raise ScenarioPathError("PATH_PREDICATE_INVALID")
        if not isinstance(self.operator, PredicateOperator) or not isinstance(
            self.timing, PredicateTiming
        ):
            raise ScenarioPathError("PATH_PREDICATE_OPERATOR_INVALID")
        _timestamp(self.available_at, "PATH_PREDICATE_AVAILABLE_AT_INVALID")
        if self.timing is PredicateTiming.DECISION_INPUT:
            if _HEX_64.fullmatch(str(self.fact_digest or "")) is None:
                raise ScenarioPathError("PATH_PREDICATE_FACT_DIGEST_REQUIRED")
        elif self.fact_digest is not None:
            raise ScenarioPathError("PATH_FUTURE_PREDICATE_DIGEST_FORBIDDEN")
        if self.minimum_quality not in {
            PredicateQuality.LOW,
            PredicateQuality.MEDIUM,
            PredicateQuality.HIGH,
        }:
            raise ScenarioPathError("PATH_PREDICATE_QUALITY_INVALID")
        object.__setattr__(
            self,
            "minimum_coverage",
            _coverage(self.minimum_coverage, "PATH_PREDICATE_COVERAGE_INVALID"),
        )
        object.__setattr__(
            self,
            "allowed_conflict_states",
            _strings(
                self.allowed_conflict_states,
                "PATH_PREDICATE_CONFLICT_STATES_REQUIRED",
            ),
        )
        if self.operator is PredicateOperator.EXISTS and self.expected is not None:
            raise ScenarioPathError("PATH_EXISTS_EXPECTED_MUST_BE_NULL")
        if self.operator is not PredicateOperator.EXISTS and self.expected is None:
            raise ScenarioPathError("PATH_PREDICATE_EXPECTED_REQUIRED")
        if self.operator is PredicateOperator.IN and (
            not isinstance(self.expected, (list, tuple)) or not self.expected
        ):
            raise ScenarioPathError("PATH_IN_EXPECTED_COLLECTION_REQUIRED")
        try:
            canonical_digest(self.expected)
        except CanonicalContractError as exc:
            raise ScenarioPathError("PATH_PREDICATE_EXPECTED_INVALID") from exc
        object.__setattr__(
            self,
            "limitations",
            _strings(self.limitations, "PATH_PREDICATE_LIMITATIONS_INVALID", allow_empty=True),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "predicate_id": self.predicate_id,
            "fact_ref": self.fact_ref,
            "fact_digest": self.fact_digest,
            "timing": self.timing.value,
            "operator": self.operator.value,
            "expected": self.expected,
            "available_at": self.available_at,
            "minimum_quality": self.minimum_quality.value,
            "minimum_coverage": canonical_decimal(self.minimum_coverage),
            "allowed_conflict_states": list(self.allowed_conflict_states),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class EpistemicTransition:
    from_stage: EpistemicStage
    to_stage: EpistemicStage
    target_ref: str
    update_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.from_stage, EpistemicStage) or not isinstance(
            self.to_stage, EpistemicStage
        ):
            raise ScenarioPathError("PATH_TRANSITION_STAGE_INVALID")
        if (self.from_stage, self.to_stage) not in _ALLOWED_TRANSITIONS:
            raise ScenarioPathError("PATH_EPISTEMIC_JUMP_FORBIDDEN")
        if self.to_stage is EpistemicStage.AUTHORIZED_ACTION:
            raise ScenarioPathError("PATH_CANNOT_AUTHORIZE_ACTION")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.target_ref, self.update_type)
        ):
            raise ScenarioPathError("PATH_TRANSITION_INVALID")
        if self.update_type not in _TRANSITION_UPDATE_TYPES:
            raise ScenarioPathError("PATH_TRANSITION_UPDATE_TYPE_INVALID")

    def to_document(self) -> dict[str, str]:
        return {
            "from_stage": self.from_stage.value,
            "to_stage": self.to_stage.value,
            "target_ref": self.target_ref,
            "update_type": self.update_type,
        }


@dataclass(frozen=True, slots=True)
class ExpectedObservation:
    observation_id: str
    hypothesis_id: str
    expectation_revision_digest: str
    observable_ref: str
    horizon_at: str
    direction_or_state: str
    confirms_when: str
    contradicts_when: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.observation_id,
                self.hypothesis_id,
                self.observable_ref,
                self.direction_or_state,
                self.confirms_when,
                self.contradicts_when,
            )
        ):
            raise ScenarioPathError("PATH_EXPECTATION_INVALID")
        _digest(
            self.expectation_revision_digest,
            "PATH_EXPECTATION_REVISION_DIGEST_INVALID",
        )
        _timestamp(self.horizon_at, "PATH_EXPECTATION_HORIZON_INVALID")

    def to_document(self) -> dict[str, str]:
        return {
            "observation_id": self.observation_id,
            "hypothesis_id": self.hypothesis_id,
            "expectation_revision_digest": self.expectation_revision_digest,
            "observable_ref": self.observable_ref,
            "horizon_at": self.horizon_at,
            "direction_or_state": self.direction_or_state,
            "confirms_when": self.confirms_when,
            "contradicts_when": self.contradicts_when,
        }


@dataclass(frozen=True, slots=True)
class ActionImplication:
    action: ActionType
    effect: ImplicationEffect
    rationale: str
    risk_refs: tuple[str, ...]
    opportunity_cost: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.rationale, self.opportunity_cost)
        ) or not isinstance(self.action, ActionType) or not isinstance(
            self.effect, ImplicationEffect
        ):
            raise ScenarioPathError("PATH_ACTION_IMPLICATION_INVALID")
        object.__setattr__(
            self,
            "risk_refs",
            _strings(self.risk_refs, "PATH_ACTION_RISK_REFS_REQUIRED"),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "effect": self.effect.value,
            "rationale": self.rationale,
            "risk_refs": list(self.risk_refs),
            "opportunity_cost": self.opportunity_cost,
            "authorized": False,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPathRule:
    path_id: str
    decision_at: str
    triggers: tuple[PathPredicate, ...]
    guards: tuple[PathPredicate, ...]
    unless: tuple[PathPredicate, ...]
    transition: EpistemicTransition
    mechanism: str
    mechanism_hypothesis_refs: tuple[str, ...]
    expectations: tuple[ExpectedObservation, ...]
    falsifiers: tuple[PathPredicate, ...]
    else_path_refs: tuple[str, ...]
    preserves_other_unknown: bool
    action_implications: tuple[ActionImplication, ...]
    expires_at: str
    next_review_at: str
    next_observation: str
    regime_refs: tuple[str, ...] = ()
    probability_cloud_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.path_id, str) or not self.path_id.strip():
            raise ScenarioPathError("PATH_ID_INVALID")
        decision = _timestamp(self.decision_at, "PATH_DECISION_AT_INVALID")
        expiry = _timestamp(self.expires_at, "PATH_EXPIRY_INVALID")
        review = _timestamp(self.next_review_at, "PATH_NEXT_REVIEW_INVALID")
        if review < decision or expiry <= decision or review > expiry:
            raise ScenarioPathError("PATH_TIME_ORDER_INVALID")
        for field_name, item_type, code, allow_empty in (
            ("triggers", PathPredicate, "PATH_TRIGGERS_REQUIRED", False),
            ("guards", PathPredicate, "PATH_GUARDS_REQUIRED", False),
            ("unless", PathPredicate, "PATH_UNLESS_INVALID", True),
            ("falsifiers", PathPredicate, "PATH_FALSIFIERS_REQUIRED", False),
            ("expectations", ExpectedObservation, "PATH_EXPECTATIONS_REQUIRED", False),
            ("action_implications", ActionImplication, "PATH_ACTION_IMPLICATIONS_REQUIRED", False),
        ):
            values = tuple(getattr(self, field_name))
            if (not allow_empty and not values) or any(
                not isinstance(value, item_type) for value in values
            ):
                raise ScenarioPathError(code)
            object.__setattr__(self, field_name, values)
        predicates = self.triggers + self.guards + self.unless + self.falsifiers
        predicate_ids = tuple(item.predicate_id for item in predicates)
        if len(predicate_ids) != len(set(predicate_ids)):
            raise ScenarioPathError("PATH_PREDICATE_IDS_DUPLICATE")
        decision_predicates = self.triggers + self.guards + self.unless
        if any(
            item.timing is not PredicateTiming.DECISION_INPUT
            or _timestamp(item.available_at, "PATH_PREDICATE_AVAILABLE_AT_INVALID")
            > decision
            for item in decision_predicates
        ):
            raise ScenarioPathError("PATH_FUTURE_INFORMATION_FORBIDDEN")
        if any(
            item.timing is not PredicateTiming.FUTURE_MONITOR
            or _timestamp(item.available_at, "PATH_PREDICATE_AVAILABLE_AT_INVALID")
            <= decision
            or _timestamp(item.available_at, "PATH_PREDICATE_AVAILABLE_AT_INVALID")
            > expiry
            for item in self.falsifiers
        ):
            raise ScenarioPathError("PATH_FALSIFIER_WINDOW_INVALID")
        if any(
            _timestamp(item.horizon_at, "PATH_EXPECTATION_HORIZON_INVALID") <= decision
            or _timestamp(item.horizon_at, "PATH_EXPECTATION_HORIZON_INVALID")
            > expiry
            for item in self.expectations
        ):
            raise ScenarioPathError("PATH_EXPECTATION_WINDOW_INVALID")
        if not isinstance(self.transition, EpistemicTransition):
            raise ScenarioPathError("PATH_TRANSITION_INVALID")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.mechanism, self.next_observation)
        ):
            raise ScenarioPathError("PATH_MECHANISM_OR_NEXT_OBSERVATION_REQUIRED")
        for field_name, allow_empty in (
            ("mechanism_hypothesis_refs", False),
            ("else_path_refs", True),
            ("regime_refs", True),
            ("probability_cloud_refs", True),
        ):
            object.__setattr__(
                self,
                field_name,
                _strings(
                    getattr(self, field_name),
                    "PATH_REFS_INVALID",
                    allow_empty=allow_empty,
                ),
            )
        if not self.else_path_refs and not self.preserves_other_unknown:
            raise ScenarioPathError("PATH_ELSE_OR_OTHER_REQUIRED")

    def to_document(self) -> dict[str, Any]:
        document = {
            "schema_id": "theory_paper_v2_v31_scenario_path",
            "schema_version": "1.0.0",
            "path_id": self.path_id,
            "decision_at": self.decision_at,
            "if_triggers": [item.to_document() for item in self.triggers],
            "and_guards": [item.to_document() for item in self.guards],
            "unless": [item.to_document() for item in self.unless],
            "then_transition": self.transition.to_document(),
            "because_mechanism": self.mechanism,
            "mechanism_hypothesis_refs": list(self.mechanism_hypothesis_refs),
            "expect_by_horizon": [item.to_document() for item in self.expectations],
            "falsified_when": [item.to_document() for item in self.falsifiers],
            "else_path_refs": list(self.else_path_refs),
            "preserves_other_unknown": self.preserves_other_unknown,
            "action_implications": [item.to_document() for item in self.action_implications],
            "expires_at": self.expires_at,
            "next_review_at": self.next_review_at,
            "next_observation": self.next_observation,
            "regime_refs": list(self.regime_refs),
            "probability_cloud_refs": list(self.probability_cloud_refs),
            "executable": False,
        }
        document["path_digest"] = canonical_digest(document)
        return document


@dataclass(frozen=True, slots=True)
class ScenarioPathSet:
    set_id: str
    decision_at: str
    paths: tuple[ScenarioPathRule, ...]
    lead_path_id: str
    runner_up_path_id: str
    residual_path_id: str = "OTHER"

    def __post_init__(self) -> None:
        if not isinstance(self.set_id, str) or not self.set_id.strip():
            raise ScenarioPathError("PATH_SET_ID_INVALID")
        decision = _timestamp(self.decision_at, "PATH_SET_DECISION_AT_INVALID")
        paths = tuple(self.paths)
        if len(paths) < 2 or any(not isinstance(path, ScenarioPathRule) for path in paths):
            raise ScenarioPathError("PATH_SET_INSUFFICIENT_COMPETITION")
        ids = tuple(path.path_id for path in paths)
        if len(ids) != len(set(ids)):
            raise ScenarioPathError("PATH_SET_DUPLICATE")
        if self.lead_path_id not in ids or self.runner_up_path_id not in ids:
            raise ScenarioPathError("PATH_SET_LEAD_RUNNER_INVALID")
        if self.lead_path_id == self.runner_up_path_id or self.residual_path_id != "OTHER":
            raise ScenarioPathError("PATH_SET_OTHER_OR_COMPETITION_INVALID")
        if any(
            _timestamp(path.decision_at, "PATH_DECISION_AT_INVALID") != decision
            for path in paths
        ):
            raise ScenarioPathError("PATH_SET_DECISION_TIME_MISMATCH")
        object.__setattr__(self, "paths", paths)

    def to_document(self) -> dict[str, Any]:
        document = {
            "schema_id": "theory_paper_v2_v31_scenario_path_set",
            "schema_version": "1.0.0",
            "set_id": self.set_id,
            "decision_at": self.decision_at,
            "paths": [path.to_document() for path in self.paths],
            "lead_path_id": self.lead_path_id,
            "runner_up_path_id": self.runner_up_path_id,
            "residual_path_id": self.residual_path_id,
            "executable": False,
        }
        document["path_set_digest"] = canonical_digest(document)
        return document


def evaluate_predicate(
    predicate: PathPredicate,
    facts: Mapping[str, PathFactSnapshot],
    *,
    evaluated_at: str,
) -> PredicateTruth:
    """Evaluate a digest-bound PIT predicate without treating missing as false."""

    cutoff = _timestamp(evaluated_at, "PATH_EVALUATION_TIME_INVALID")
    observation = facts.get(predicate.fact_ref)
    if observation is None:
        return PredicateTruth.UNKNOWN
    if not isinstance(observation, PathFactSnapshot):
        raise ScenarioPathError("PATH_FACT_SNAPSHOT_REQUIRED")
    if observation.fact_ref != predicate.fact_ref:
        raise ScenarioPathError("PATH_FACT_REF_MISMATCH")
    if predicate.fact_digest is not None and observation.fact_digest != predicate.fact_digest:
        raise ScenarioPathError("PATH_FACT_DIGEST_MISMATCH")
    if _timestamp(observation.available_at, "PATH_FACT_AVAILABLE_AT_INVALID") > cutoff:
        return PredicateTruth.UNKNOWN
    if observation.missingness != "OBSERVED" or observation.value is None:
        return PredicateTruth.UNKNOWN
    if _QUALITY_RANK[observation.quality] < _QUALITY_RANK[predicate.minimum_quality]:
        return PredicateTruth.UNKNOWN
    if observation.coverage < predicate.minimum_coverage:
        return PredicateTruth.UNKNOWN
    if observation.conflict_state not in predicate.allowed_conflict_states:
        return PredicateTruth.UNKNOWN
    actual = observation.value
    expected = predicate.expected
    try:
        if predicate.operator is PredicateOperator.EXISTS:
            result = True
        elif predicate.operator is PredicateOperator.EQ:
            result = actual == expected
        elif predicate.operator is PredicateOperator.NE:
            result = actual != expected
        elif predicate.operator is PredicateOperator.GT:
            result = actual > expected
        elif predicate.operator is PredicateOperator.GTE:
            result = actual >= expected
        elif predicate.operator is PredicateOperator.LT:
            result = actual < expected
        elif predicate.operator is PredicateOperator.LTE:
            result = actual <= expected
        elif predicate.operator is PredicateOperator.IN:
            result = actual in expected
        else:  # pragma: no cover - enum exhaustiveness
            raise ScenarioPathError("PATH_PREDICATE_OPERATOR_INVALID")
    except (TypeError, ValueError) as exc:
        raise ScenarioPathError("PATH_PREDICATE_COMPARISON_INVALID") from exc
    return PredicateTruth.TRUE if result else PredicateTruth.FALSE


def evaluate_path_conditions(
    rule: ScenarioPathRule,
    facts: Mapping[str, PathFactSnapshot],
    *,
    evaluated_at: str,
) -> PredicateTruth:
    """Three-valued path evaluation including PIT, expiry, and hard falsifiers."""

    evaluation_time = _timestamp(evaluated_at, "PATH_EVALUATION_TIME_INVALID")
    decision = _timestamp(rule.decision_at, "PATH_DECISION_AT_INVALID")
    expiry = _timestamp(rule.expires_at, "PATH_EXPIRY_INVALID")
    if evaluation_time < decision:
        raise ScenarioPathError("PATH_EVALUATION_PRECEDES_DECISION")
    if evaluation_time >= expiry:
        return PredicateTruth.FALSE
    positives = [
        evaluate_predicate(item, facts, evaluated_at=rule.decision_at)
        for item in rule.triggers + rule.guards
    ]
    blockers = [
        evaluate_predicate(item, facts, evaluated_at=rule.decision_at)
        for item in rule.unless
    ]
    if PredicateTruth.FALSE in positives or PredicateTruth.TRUE in blockers:
        return PredicateTruth.FALSE
    if PredicateTruth.UNKNOWN in positives or PredicateTruth.UNKNOWN in blockers:
        return PredicateTruth.UNKNOWN
    due_falsifiers = [
        item
        for item in rule.falsifiers
        if _timestamp(item.available_at, "PATH_PREDICATE_AVAILABLE_AT_INVALID")
        <= evaluation_time
    ]
    falsifier_results = [
        evaluate_predicate(item, facts, evaluated_at=evaluated_at)
        for item in due_falsifiers
    ]
    if PredicateTruth.TRUE in falsifier_results:
        return PredicateTruth.FALSE
    if PredicateTruth.UNKNOWN in falsifier_results:
        return PredicateTruth.UNKNOWN
    return PredicateTruth.TRUE


__all__ = [
    "ActionImplication",
    "EpistemicStage",
    "EpistemicTransition",
    "ExpectedObservation",
    "ImplicationEffect",
    "PathPredicate",
    "PathFactSnapshot",
    "PredicateOperator",
    "PredicateQuality",
    "PredicateTiming",
    "PredicateTruth",
    "ScenarioPathError",
    "ScenarioPathRule",
    "ScenarioPathSet",
    "evaluate_path_conditions",
    "evaluate_predicate",
]
