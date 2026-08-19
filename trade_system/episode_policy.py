"""Frozen trigger policy for turning feature snapshots into episodes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from .episode import EpisodeConfig
from .types import BookHealth, FeatureSnapshot, Side, parse_utc


FROZEN_EPISODE_POLICY = "FROZEN_EPISODE_POLICY"


class EpisodePolicyError(ValueError):
    pass


def _number(value: Any, field: str, *, positive: bool = False, non_negative: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise EpisodePolicyError("%s must be numeric" % field) from exc
    if positive and result <= 0:
        raise EpisodePolicyError("%s must be positive" % field)
    if non_negative and result < 0:
        raise EpisodePolicyError("%s must be non-negative" % field)
    return result


@dataclass(frozen=True)
class EpisodePolicy:
    policy_id: str
    frozen_at: str
    feature_version: str
    trigger_feature: str
    trigger_threshold: Decimal
    # All elapsed-time policy values become ``timedelta`` at the config
    # boundary.  FeaturePipeline compares this directly with timestamps.
    min_seconds_between_episodes: timedelta
    # v1 omitted this field and remains event-driven.  A declared interval is
    # a frozen, UTC-aligned episode decision clock; raw features still arrive
    # at their original cadence.
    decision_interval: Optional[timedelta]
    derived_semantics_version: Optional[str]
    config: EpisodeConfig
    digest: str

    @classmethod
    def load(cls, path: Path) -> "EpisodePolicy":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EpisodePolicyError("cannot load episode policy") from exc
        if not isinstance(raw, dict) or raw.get("status") != FROZEN_EPISODE_POLICY:
            raise EpisodePolicyError("episode policy must have status %s" % FROZEN_EPISODE_POLICY)
        required_strings = ("policy_id", "frozen_at", "feature_version", "trigger_feature")
        for field in required_strings:
            if not isinstance(raw.get(field), str) or not raw[field]:
                raise EpisodePolicyError("%s must be a non-empty string" % field)
        try:
            parse_utc(raw["frozen_at"])
        except ValueError as exc:
            raise EpisodePolicyError("frozen_at must be UTC ISO-8601") from exc
        threshold = _number(raw.get("trigger_threshold"), "trigger_threshold", positive=True)
        cooldown_seconds = _number(raw.get("min_seconds_between_episodes"), "min_seconds_between_episodes", non_negative=True)
        cooldown = timedelta(seconds=float(cooldown_seconds))
        decision_interval = None
        derived_semantics_version = None
        if "decision_frequency_seconds" in raw:
            decision_seconds = _number(raw.get("decision_frequency_seconds"), "decision_frequency_seconds", positive=True)
            decision_interval = timedelta(seconds=float(decision_seconds))
            derived_semantics_version = raw.get("derived_semantics_version")
            if not isinstance(derived_semantics_version, str) or not derived_semantics_version:
                raise EpisodePolicyError("clocked episode policy requires derived_semantics_version")
        state = raw.get("state_machine")
        if not isinstance(state, dict):
            raise EpisodePolicyError("state_machine must be an object")
        config = EpisodeConfig(
            pressure_threshold=_number(state.get("pressure_threshold"), "state_machine.pressure_threshold", positive=True),
            resilience_threshold=_number(state.get("resilience_threshold"), "state_machine.resilience_threshold"),
            response_fraction=_number(state.get("response_fraction"), "state_machine.response_fraction", positive=True),
            max_observation=timedelta(seconds=float(_number(state.get("max_observation_seconds"), "state_machine.max_observation_seconds", positive=True))),
            confirmation_updates=int(_number(state.get("confirmation_updates"), "state_machine.confirmation_updates", positive=True)),
        )
        if Decimal(config.confirmation_updates) != _number(state.get("confirmation_updates"), "state_machine.confirmation_updates", positive=True):
            raise EpisodePolicyError("state_machine.confirmation_updates must be an integer")
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return cls(
            raw["policy_id"], raw["frozen_at"], raw["feature_version"], raw["trigger_feature"],
            threshold, cooldown, decision_interval, derived_semantics_version, config,
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def trigger_side(self, snapshot: FeatureSnapshot) -> Optional[Side]:
        if snapshot.feature_version != self.feature_version or snapshot.book_health != BookHealth.VALID:
            return None
        try:
            pressure = Decimal(str(snapshot.values[self.trigger_feature]))
        except (KeyError, ArithmeticError):
            return None
        if pressure <= -self.trigger_threshold:
            return Side.BUY
        if pressure >= self.trigger_threshold:
            return Side.SELL
        return None
