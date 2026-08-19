"""Conservative single-instrument absorption episode state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from .types import BookHealth, EpisodeState, FeatureSnapshot, Side


@dataclass(frozen=True)
class EpisodeConfig:
    pressure_threshold: Decimal = Decimal("0.0001")
    resilience_threshold: Decimal = Decimal("0")
    response_fraction: Decimal = Decimal("0.0005")
    max_observation: timedelta = timedelta(minutes=15)
    confirmation_updates: int = 2


@dataclass
class Episode:
    episode_id: str
    reversal_side: Side
    anchor_price: Decimal
    opened_at: datetime
    state: EpisodeState = EpisodeState.OBSERVE
    response_updates: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.state in (EpisodeState.REVERSAL_CONFIRMED, EpisodeState.FAILED, EpisodeState.TIMED_OUT)


class EpisodeMachine:
    """It only describes a frozen episode; it cannot directly place an order."""

    def __init__(self, config: EpisodeConfig = EpisodeConfig()) -> None:
        self.config = config
        self.active: Optional[Episode] = None
        self._counter = 0
        self._prior_pressure: Optional[Decimal] = None

    def observe_extreme(self, *, now: datetime, price: Decimal, reversal_side: Side) -> Episode:
        if self.active and not self.active.is_terminal:
            raise RuntimeError("only one active episode is allowed per instrument")
        self._counter += 1
        self.active = Episode("episode-%06d" % self._counter, reversal_side, price, now)
        self._prior_pressure = None
        return self.active

    def advance(
        self,
        snapshot: FeatureSnapshot,
        *,
        resilience_override: Optional[Decimal] = None,
        allow_absorption: bool = True,
    ) -> Optional[Episode]:
        episode = self.active
        if episode is None or episode.is_terminal:
            return episode
        hard_failures = {"book_invalid", "gap", "sequence_gap", "late_critical"}
        if snapshot.book_health != BookHealth.VALID or not snapshot.values or hard_failures.intersection(snapshot.quality_flags):
            episode.state = EpisodeState.UNKNOWN
            return episode
        if snapshot.available_at - episode.opened_at > self.config.max_observation:
            episode.state = EpisodeState.TIMED_OUT
            return episode
        pressure = snapshot.values["D_directional_pressure"]
        price = snapshot.values["mid_price"]
        is_long_reversal = episode.reversal_side == Side.BUY
        extending = pressure < -self.config.pressure_threshold if is_long_reversal else pressure > self.config.pressure_threshold
        opposite = pressure > self.config.pressure_threshold if is_long_reversal else pressure < -self.config.pressure_threshold
        resilience = resilience_override if resilience_override is not None else (snapshot.values["R_sell_bid_resilience"] if is_long_reversal else snapshot.values["R_buy_ask_resilience"])
        response = (price - episode.anchor_price) / episode.anchor_price
        response_ok = response >= self.config.response_fraction if is_long_reversal else response <= -self.config.response_fraction
        if episode.state == EpisodeState.OBSERVE and extending:
            episode.state = EpisodeState.EXPANDING
        elif episode.state == EpisodeState.EXPANDING:
            if opposite:
                episode.state = EpisodeState.FAILED
            elif self._prior_pressure is not None and abs(pressure) < abs(self._prior_pressure):
                episode.state = EpisodeState.DECELERATING
        elif episode.state == EpisodeState.DECELERATING:
            if allow_absorption and extending and resilience >= self.config.resilience_threshold:
                episode.state = EpisodeState.ABSORBING
            elif opposite:
                episode.state = EpisodeState.FAILED
        elif episode.state == EpisodeState.ABSORBING:
            if response_ok:
                episode.state, episode.response_updates = EpisodeState.RESPONDING, 1
            elif opposite:
                episode.state = EpisodeState.FAILED
        elif episode.state == EpisodeState.RESPONDING:
            if not response_ok:
                episode.state = EpisodeState.FAILED
            else:
                episode.response_updates += 1
                if episode.response_updates >= self.config.confirmation_updates:
                    episode.state = EpisodeState.REVERSAL_CONFIRMED
        self._prior_pressure = pressure
        return episode
