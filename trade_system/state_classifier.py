"""Deterministic, frozen state classification for research stratification.

This module classifies feature vectors only.  It is not a trading signal and
does not use labels or outcomes, so a frozen protocol can verify that its
state strata were not assigned after looking at research results.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


FROZEN_STATE_CLASSIFIER_STATUS = "FROZEN_STATE_CLASSIFIER"


class StateClassifierError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise StateClassifierError("%s must be a non-empty string" % name)
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise StateClassifierError("%s must be numeric" % name)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StateClassifierError("%s must be numeric" % name) from exc
    if not math.isfinite(number):
        raise StateClassifierError("%s must be finite" % name)
    return number


@dataclass(frozen=True)
class StateCondition:
    feature: str
    minimum: Optional[float]
    maximum: Optional[float]
    absolute_value: bool

    def matches(self, features: Dict[str, float]) -> bool:
        value = features.get(self.feature)
        if value is None:
            return False
        numeric = float(value)
        if not math.isfinite(numeric):
            return False
        if self.absolute_value:
            numeric = abs(numeric)
        return (self.minimum is None or numeric >= self.minimum) and (self.maximum is None or numeric < self.maximum)


@dataclass(frozen=True)
class StateRule:
    state_id: str
    conditions: Tuple[StateCondition, ...]

    def matches(self, features: Dict[str, float]) -> bool:
        return all(condition.matches(features) for condition in self.conditions)


@dataclass(frozen=True)
class StateClassifier:
    classifier_id: str
    status: str
    rules: Tuple[StateRule, ...]
    fallback_state_id: str
    digest: str

    @classmethod
    def load(cls, path: Path) -> "StateClassifier":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateClassifierError("cannot load state classifier") from exc
        if not isinstance(raw, dict):
            raise StateClassifierError("state classifier must be an object")
        classifier_id = _non_empty_string(raw.get("classifier_id"), "classifier_id")
        status = _non_empty_string(raw.get("status"), "status")
        if status != FROZEN_STATE_CLASSIFIER_STATUS:
            raise StateClassifierError("state classifier requires status %s" % FROZEN_STATE_CLASSIFIER_STATUS)
        fallback = _non_empty_string(raw.get("fallback_state_id"), "fallback_state_id")
        rule_values = raw.get("rules")
        if not isinstance(rule_values, list) or not rule_values:
            raise StateClassifierError("rules must be a non-empty list")
        rules = []
        state_ids = set()
        for index, value in enumerate(rule_values):
            if not isinstance(value, dict):
                raise StateClassifierError("rules[%d] must be an object" % index)
            state_id = _non_empty_string(value.get("state_id"), "rules[%d].state_id" % index)
            if state_id in state_ids or state_id == fallback:
                raise StateClassifierError("state IDs must be unique and distinct from fallback")
            state_ids.add(state_id)
            condition_values = value.get("all")
            if not isinstance(condition_values, list) or not condition_values:
                raise StateClassifierError("rules[%d].all must be a non-empty list" % index)
            conditions = []
            for condition_index, condition in enumerate(condition_values):
                if not isinstance(condition, dict):
                    raise StateClassifierError("rules[%d].all[%d] must be an object" % (index, condition_index))
                feature = _non_empty_string(condition.get("feature"), "rules[%d].all[%d].feature" % (index, condition_index))
                minimum = _finite_number(condition["min"], "rules[%d].all[%d].min" % (index, condition_index)) if "min" in condition else None
                maximum = _finite_number(condition["max"], "rules[%d].all[%d].max" % (index, condition_index)) if "max" in condition else None
                if minimum is None and maximum is None:
                    raise StateClassifierError("rules[%d].all[%d] needs min or max" % (index, condition_index))
                if minimum is not None and maximum is not None and minimum >= maximum:
                    raise StateClassifierError("rules[%d].all[%d] min must be below max" % (index, condition_index))
                absolute = condition.get("absolute", False)
                if not isinstance(absolute, bool):
                    raise StateClassifierError("rules[%d].all[%d].absolute must be boolean" % (index, condition_index))
                conditions.append(StateCondition(feature, minimum, maximum, absolute))
            rules.append(StateRule(state_id, tuple(conditions)))
        return cls(
            classifier_id=classifier_id,
            status=status,
            rules=tuple(rules),
            fallback_state_id=fallback,
            digest=hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest(),
        )

    @property
    def state_ids(self) -> Tuple[str, ...]:
        return tuple(rule.state_id for rule in self.rules) + (self.fallback_state_id,)

    def classify(self, features: Dict[str, float]) -> str:
        for rule in self.rules:
            if rule.matches(features):
                return rule.state_id
        return self.fallback_state_id
