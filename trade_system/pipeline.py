"""Shared replay/live-normalized feature pipeline for the P0 research path."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .book_sync import BinanceBookSynchronizer
from .episode import EpisodeMachine
from .episode_policy import EpisodePolicy
from .feature_context import FeatureContextPolicy, MarketContextEngine
from .event_store import EventStore
from .features import FeatureEngine
from .order_book import BookGapError, OrderBook
from .replay import DeterministicReplay, ReplayEvent
from .types import AvailabilityKind, BookHealth, FeatureSnapshot, Side, TradePrint


@dataclass(frozen=True)
class FeatureRow:
    event_id: str
    available_at: str
    availability_kind: str
    feature_version: str
    episode_id: Optional[str]
    episode_state: Optional[str]
    episode_policy_id: Optional[str]
    episode_policy_sha256: Optional[str]
    episode_decision_eligible: Optional[bool]
    episode_reversal_side: Optional[str]
    quality_flags: List[str]
    values: Dict[str, str]
    # Absent for legacy/G1 artifacts.  v2 role bundles that declare a frozen
    # context policy carry the complete fail-closed decision proof here.
    context: Optional[Dict[str, object]] = None

    def to_dict(self) -> Dict[str, object]:
        output = {
            "event_id": self.event_id,
            "available_at": self.available_at,
            "availability_kind": self.availability_kind,
            "feature_version": self.feature_version,
            "episode_id": self.episode_id,
            "episode_state": self.episode_state,
            "episode_policy_id": self.episode_policy_id,
            "episode_policy_sha256": self.episode_policy_sha256,
            "quality_flags": self.quality_flags,
            "values": self.values,
        }
        if self.episode_decision_eligible is not None:
            output["episode_decision_eligible"] = self.episode_decision_eligible
        if self.episode_reversal_side is not None:
            output["episode_reversal_side"] = self.episode_reversal_side
        if self.context is not None:
            output["context"] = self.context
        return output


@dataclass(frozen=True)
class _ContextBucketSample:
    bucket: int
    source_event_id: str
    snapshot: FeatureSnapshot
    kind: AvailabilityKind
    episode_anchor_price: Optional[Decimal]
    bid_depth_notional: Optional[Decimal]
    ask_depth_notional: Optional[Decimal]


class FeaturePipeline:
    def __init__(
        self,
        episode_policy: Optional[EpisodePolicy] = None,
        context_policy: Optional[FeatureContextPolicy] = None,
    ) -> None:
        self.book = OrderBook()
        self.synchronizer = BinanceBookSynchronizer(self.book)
        self.features = FeatureEngine(feature_version=episode_policy.feature_version) if episode_policy is not None else FeatureEngine()
        self.episode_policy = episode_policy
        if context_policy is not None:
            if episode_policy is None:
                raise ValueError("a context policy requires a frozen episode policy")
            if context_policy.feature_version != episode_policy.feature_version:
                raise ValueError("context and episode policies must bind the same feature_version")
            if episode_policy.decision_interval is None or episode_policy.decision_interval.total_seconds() != context_policy.sampling_seconds:
                raise ValueError("context sampling requires a matching one-second episode decision clock")
        self.context_policy = context_policy
        self.context = MarketContextEngine(context_policy) if context_policy is not None else None
        # A context observation is published only after its UTC-second bucket
        # closes.  The stored snapshot is the last point actually observed in
        # that bucket; the later output row keeps its real (never floored)
        # available_at timestamp.
        self._pending_context_sample: Optional[_ContextBucketSample] = None
        self._last_closed_context_sample: Optional[_ContextBucketSample] = None
        self.episodes = EpisodeMachine(episode_policy.config) if episode_policy is not None else EpisodeMachine()
        self._last_terminal_at = None
        self._last_decision_bucket: Optional[int] = None

    @staticmethod
    def _decimal(value: object) -> Decimal:
        return Decimal(str(value))

    def _decision_eligible(self, available_at: datetime) -> bool:
        """Return one deterministic decision permission per frozen UTC bucket."""
        if self.episode_policy is None or self.episode_policy.decision_interval is None:
            return True
        if available_at.tzinfo is None:
            raise ValueError("episode decision clock requires timezone-aware available_at")
        interval = self.episode_policy.decision_interval
        elapsed = available_at.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        elapsed_microseconds = ((elapsed.days * 86400 + elapsed.seconds) * 1_000_000) + elapsed.microseconds
        interval_microseconds = ((interval.days * 86400 + interval.seconds) * 1_000_000) + interval.microseconds
        if interval_microseconds <= 0:
            raise ValueError("episode decision clock interval must be positive")
        bucket = elapsed_microseconds // interval_microseconds
        if self._last_decision_bucket == bucket:
            return False
        self._last_decision_bucket = bucket
        return True

    @staticmethod
    def _directional_resilience(values: Dict[str, Any]) -> Tuple[Optional[str], Optional[Decimal]]:
        """Return the pressure-side resilience without inventing a generic R.

        The raw feature contract has distinct buy/ask and sell/bid resilience
        measurements.  A context decision is invalid when pressure has no
        sign or its matching resilience is unavailable; zero-filling would
        silently turn an unknown book response into a tradable input.
        """
        try:
            pressure = Decimal(str(values["D_directional_pressure"]))
            if not pressure.is_finite() or pressure == 0:
                return None, None
            field = "R_buy_ask_resilience" if pressure > 0 else "R_sell_bid_resilience"
            resilience = Decimal(str(values[field]))
            if not resilience.is_finite():
                return None, None
            return field, resilience
        except (KeyError, ValueError, ArithmeticError):
            return None, None

    def _closed_context_row(
        self,
        *,
        available_at: datetime,
        decision_eligible: bool,
    ) -> Optional[Dict[str, object]]:
        if self.context is None or self.context_policy is None:
            return None
        if not decision_eligible:
            return {
                "context_policy_id": self.context_policy.context_policy_id,
                "context_policy_sha256": self.context_policy.digest,
                "context_status": "NOT_DECISION_BUCKET",
                "decision_permission": "ABSTAIN",
                "reason_codes": ["CONTEXT_NOT_DECISION_BUCKET"],
                "values": {},
                "unavailable": [],
            }
        bucket = int(available_at.astimezone(timezone.utc).timestamp())
        pending = self._pending_context_sample
        if pending is None:
            return {
                "context_policy_id": self.context_policy.context_policy_id,
                "context_policy_sha256": self.context_policy.digest,
                "context_status": "WARMUP",
                "decision_permission": "ABSTAIN",
                "reason_codes": ["CONTEXT_CLOSED_BUCKET_PENDING"],
                "values": {}, "unavailable": [],
            }
        pending_bucket, source_event_id, snapshot, kind, episode_anchor_price = (
            pending.bucket, pending.source_event_id, pending.snapshot, pending.kind, pending.episode_anchor_price
        )
        if bucket <= pending_bucket:
            return {
                "context_policy_id": self.context_policy.context_policy_id,
                "context_policy_sha256": self.context_policy.digest,
                "context_status": "DEGRADED", "decision_permission": "ABSTAIN",
                "reason_codes": ["CONTEXT_NON_MONOTONIC_OR_DUPLICATE_SAMPLE"], "values": {}, "unavailable": [],
            }
        # We cannot infer a missing logical second from a later event.  Reset
        # rather than treating the last quote before a multi-second silence as
        # continuity evidence.
        resilience_field = None
        if bucket != pending_bucket + 1:
            result = self.context.invalidate(
                available_at=datetime.fromtimestamp(bucket, tz=timezone.utc),
                reason="CONTEXT_GAP_EXCEEDED",
            ).to_dict()
        else:
            prior = self._last_closed_context_sample
            pressure = snapshot.values.get("D_directional_pressure")
            impact = resilience = None
            try:
                pressure_decimal = Decimal(str(pressure))
                if (
                    prior is not None and prior.bucket == pending_bucket - 1
                    and pressure_decimal.is_finite() and pressure_decimal != 0
                    and snapshot.book_health == BookHealth.VALID
                    and prior.snapshot.book_health == BookHealth.VALID
                ):
                    current_mid = Decimal(str(snapshot.values["mid_price"]))
                    prior_mid = Decimal(str(prior.snapshot.values["mid_price"]))
                    impact = Decimal(str(math.log(float(current_mid / prior_mid))))
                    if pressure_decimal < 0:
                        resilience_field = "R_sell_bid_resilience_1s"
                        current_depth, prior_depth = pending.bid_depth_notional, prior.bid_depth_notional
                    else:
                        resilience_field = "R_buy_ask_resilience_1s"
                        current_depth, prior_depth = pending.ask_depth_notional, prior.ask_depth_notional
                    if current_depth is not None and prior_depth is not None and current_depth > 0 and prior_depth > 0:
                        # End-of-UTC-second pressure-side visible depth response,
                        # net of absolute closed-bucket mid impact.  It is not
                        # the raw event-level FeatureEngine R proxy.
                        resilience = Decimal(str(math.log(float(current_depth / prior_depth)))) - abs(impact)
            except (KeyError, ValueError, ArithmeticError, OverflowError):
                impact = resilience = None
            result = self.context.observe(
            available_at=datetime.fromtimestamp(pending_bucket, tz=timezone.utc),
            mid_price=snapshot.values.get("mid_price"),
            availability_kind=kind,
            book_valid=snapshot.book_health == BookHealth.VALID,
            directional_pressure=pressure,
            price_impact=impact,
            directional_resilience=resilience,
            directional_resilience_feature=resilience_field,
            episode_anchor_price=episode_anchor_price,
            ).to_dict()
        self._last_closed_context_sample = pending
        result.update({
            # ``MarketContextEngine`` stores its logical measurement bucket
            # internally, but this artifact is released only now.  Never
            # expose the prior bucket timestamp as if it were available then.
            "available_at": available_at.isoformat(),
            "context_policy_id": self.context_policy.context_policy_id,
            "context_policy_sha256": self.context_policy.digest,
            # The selected source is evidence that R was pressure-side mapped,
            # rather than a generic/zero substituted resilience value.
            "directional_resilience_feature": resilience_field,
            "measurement_bucket_at": datetime.fromtimestamp(pending_bucket, tz=timezone.utc).isoformat(),
            "measurement_source_event_id": source_event_id,
            "published_at": available_at.isoformat(),
        })
        return result

    def _cache_context_sample(self, *, event_id: str, available_at: datetime, snapshot: FeatureSnapshot, kind: AvailabilityKind, episode_anchor_price: Optional[Decimal]) -> None:
        if self.context is None:
            return
        bucket = int(available_at.astimezone(timezone.utc).timestamp())
        try:
            bid_depth = self.book.depth_notional(Side.SELL) if snapshot.book_health == BookHealth.VALID else None
            ask_depth = self.book.depth_notional(Side.BUY) if snapshot.book_health == BookHealth.VALID else None
        except (BookGapError, ArithmeticError):
            bid_depth = ask_depth = None
        pending = self._pending_context_sample
        if pending is None or bucket >= pending.bucket:
            self._pending_context_sample = _ContextBucketSample(bucket, event_id, snapshot, kind, episode_anchor_price, bid_depth, ask_depth)

    def process(self, event_id: str, kind: AvailabilityKind, available_at, data: Dict[str, object]) -> Optional[FeatureRow]:
        record_kind = data.get("kind")
        try:
            if record_kind == "snapshot":
                self.synchronizer.apply_snapshot(data)
            elif record_kind == "delta":
                if self.book.last_update_id is None:
                    self.synchronizer.buffer_delta(data)
                else:
                    self.synchronizer.apply_live_delta(data)
            elif record_kind == "trade":
                self.features.add_trade(TradePrint(
                    available_at=available_at,
                    price=self._decimal(data["price"]),
                    quantity=self._decimal(data["quantity"]),
                    aggressor_side=Side(str(data["side"])),
                ))
            elif record_kind == "oi":
                self.features.update_open_interest(self._decimal(data["value"]))
            elif record_kind == "liquidation":
                self.features.add_liquidation(
                    available_at,
                    Side(str(data["side"])),
                    self._decimal(data["price"]),
                    self._decimal(data["quantity"]),
                    bool(data.get("censored", True)),
                )
            elif record_kind == "mark_price":
                self.features.update_crowding(
                    funding_rate=self._decimal(data.get("funding_rate", "0")),
                    premium=self._decimal(data["mark_price"]) - self._decimal(data["index_price"]),
                )
            else:
                return None
        except (BookGapError, KeyError, ValueError, ArithmeticError):
            self.book.invalidate("pipeline_normalization_error")

        snapshot = self.features.snapshot(
            available_at=available_at,
            book=self.book,
            availability_kind=kind,
            quality_flags=[self.book.invalid_reason] if self.book.invalid_reason else [],
        )
        if not snapshot.values:
            if self.context is not None and isinstance(available_at, datetime) and available_at.tzinfo is not None:
                # No action row is emitted for an invalid book, but that raw
                # event still breaks context continuity.  Do not let a later
                # valid update in the same/next bucket bridge across it.
                bucket_at = datetime.fromtimestamp(int(available_at.astimezone(timezone.utc).timestamp()), tz=timezone.utc)
                self.context.invalidate(available_at=bucket_at, reason="CONTEXT_BOOK_INVALID")
                self._pending_context_sample = None
                self._last_closed_context_sample = None
            return None
        decision_eligible = self._decision_eligible(available_at)
        # Context is the *closed prior UTC-second* measurement.  It is
        # published on this real event timestamp, never on a floored source
        # timestamp, so no action can see an event that arrived after it.
        context = self._closed_context_row(
            available_at=available_at,
            decision_eligible=decision_eligible,
        )
        episode = self.episodes.active
        if decision_eligible:
            if self.episode_policy is not None and (self.episodes.active is None or self.episodes.active.is_terminal):
                cooldown_elapsed = self._last_terminal_at is None or available_at - self._last_terminal_at >= self.episode_policy.min_seconds_between_episodes
                side = self.episode_policy.trigger_side(snapshot) if cooldown_elapsed else None
                if side is not None:
                    self.episodes.observe_extreme(now=available_at, price=snapshot.values["mid_price"], reversal_side=side)
            elif self.episode_policy is None and self.episodes.active is None:
                # Development-only compatibility path.  Frozen G1 feature bundles
                # must pass an EpisodePolicy and therefore never use this trigger.
                self.episodes.observe_extreme(now=available_at, price=snapshot.values["mid_price"], reversal_side=Side.BUY)
            if self.context is not None:
                raw_context_values = (context or {}).get("values") or {}
                try:
                    bucket_resilience = Decimal(str(raw_context_values["R_directional"]))
                    allow_absorption = bucket_resilience.is_finite()
                except (KeyError, ValueError, ArithmeticError):
                    bucket_resilience = None
                    allow_absorption = False
                episode = self.episodes.advance(snapshot, resilience_override=bucket_resilience, allow_absorption=allow_absorption)
            else:
                episode = self.episodes.advance(snapshot)
        if episode is not None and episode.is_terminal:
            # Emit the terminal state on this row exactly once, then release
            # it.  Keeping a terminal episode active would both attach its ID
            # to unrelated later features and continually push the cooldown
            # forward on every high-frequency event.
            self._last_terminal_at = available_at
            self.episodes.active = None
        # Cache after episode advancement so an episode created in this bucket
        # supplies its anchor to the next closed-bucket context measurement.
        active_for_context = self.episodes.active
        self._cache_context_sample(
            event_id=event_id,
            available_at=available_at,
            snapshot=snapshot,
            kind=kind,
            episode_anchor_price=active_for_context.anchor_price if active_for_context is not None and not active_for_context.is_terminal else None,
        )
        return FeatureRow(
            event_id=event_id,
            available_at=available_at.isoformat(),
            availability_kind=kind.value,
            feature_version=snapshot.feature_version,
            episode_id=episode.episode_id if episode else None,
            episode_state=episode.state.value if episode else None,
            episode_policy_id=self.episode_policy.policy_id if self.episode_policy else None,
            episode_policy_sha256=self.episode_policy.digest if self.episode_policy else None,
            episode_decision_eligible=decision_eligible if self.episode_policy and self.episode_policy.decision_interval else None,
            episode_reversal_side=episode.reversal_side.value if episode else None,
            quality_flags=snapshot.quality_flags,
            values={
                key: str(value)
                for key, value in snapshot.values.items()
            } | {
                key: str(value)
                for key, value in ((context or {}).get("values") or {}).items()
                if value is not None
            },
            context=context,
        )

    def replay_events(self, events: Iterable[ReplayEvent]) -> Iterator[FeatureRow]:
        for event in events:
            row = self.process(
                event.raw.event_id,
                event.availability.availability_kind,
                event.availability.available_at,
                event.availability.normalized,
            )
            if row is not None:
                yield row

    def replay(self, store: EventStore, *, allow_reconstructed: bool = False) -> Iterator[FeatureRow]:
        return self.replay_events(DeterministicReplay(store, allow_reconstructed=allow_reconstructed).events())

    def replay_collection(self, store: EventStore, collection_id: str, *, allow_reconstructed: bool = False) -> Iterator[FeatureRow]:
        prefix = collection_id + "-"
        events = (
            event for event in DeterministicReplay(store, allow_reconstructed=allow_reconstructed).events()
            if event.raw.connection_id.startswith(prefix)
        )
        return self.replay_events(events)


def write_feature_rows(path: Path, rows: Iterable[FeatureRow]) -> int:
    """Write a new artifact; callers must not point this at raw/availability logs."""
    path = Path(path)
    if path.name.endswith(".ndjson") and any(part in {"raw", "availability"} for part in path.parts):
        raise ValueError("feature artifacts must not overwrite raw or availability evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count
