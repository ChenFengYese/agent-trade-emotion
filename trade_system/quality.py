"""Data-health state derived from explicit freshness and gap observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional, Set

from .types import BookHealth, SystemHealth


@dataclass(frozen=True)
class HealthPolicy:
    critical_streams: Set[str]
    max_age: timedelta
    recovery_cooldown: timedelta


@dataclass
class StreamObservation:
    observed_at: datetime
    valid: bool = True
    reasons: Set[str] = field(default_factory=set)


class DataQualityEngine:
    def __init__(self, policy: HealthPolicy) -> None:
        self.policy = policy
        self.observations: Dict[str, StreamObservation] = {}
        self._healthy_since: Optional[datetime] = None

    def observe(self, stream: str, observed_at: datetime, *, valid: bool = True, reason: str = "") -> None:
        observation = self.observations.get(stream)
        if observation is None or observed_at >= observation.observed_at:
            self.observations[stream] = StreamObservation(observed_at, valid, {reason} if reason else set())
        if not valid:
            self._healthy_since = None

    def observe_book(self, observed_at: datetime, health: BookHealth, reason: str = "") -> None:
        self.observe("depth", observed_at, valid=health == BookHealth.VALID, reason=reason or health.value)

    def evaluate(self, now: datetime) -> SystemHealth:
        missing_or_invalid = []
        stale = []
        for stream in self.policy.critical_streams:
            observation = self.observations.get(stream)
            if observation is None or not observation.valid:
                missing_or_invalid.append(stream)
            elif now - observation.observed_at > self.policy.max_age:
                stale.append(stream)
        if missing_or_invalid:
            self._healthy_since = None
            return SystemHealth.HALTED
        if stale:
            self._healthy_since = None
            return SystemHealth.DEGRADED
        if self._healthy_since is None:
            self._healthy_since = now
            return SystemHealth.WARMUP
        if now - self._healthy_since < self.policy.recovery_cooldown:
            return SystemHealth.WARMUP
        return SystemHealth.READY

    def quality_flags(self, now: datetime) -> Iterable[str]:
        for stream, observation in sorted(self.observations.items()):
            if not observation.valid:
                yield "%s_invalid" % stream
            elif now - observation.observed_at > self.policy.max_age:
                yield "%s_stale" % stream
