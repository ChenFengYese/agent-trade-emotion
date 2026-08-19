"""Frozen, collection-local market-context measurements for ``Z_t``.

The engine deliberately has no EventStore or pipeline dependency.  A caller
must feed one ACTUAL, UTC-aligned mid price per declared decision second.  It
never carries history across a collection boundary: create one engine for one
collection and discard it at the terminal boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, Optional, Tuple

from .types import AvailabilityKind, parse_utc


FROZEN_FEATURE_CONTEXT_POLICY = "FROZEN_FEATURE_CONTEXT_POLICY"


class FeatureContextError(ValueError):
    """A frozen context policy or context input is invalid."""


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _number(value: Any, name: str, *, positive: bool = False, non_negative: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise FeatureContextError("%s must be numeric" % name) from exc
    if not result.is_finite():
        raise FeatureContextError("%s must be finite" % name)
    if positive and result <= 0:
        raise FeatureContextError("%s must be positive" % name)
    if non_negative and result < 0:
        raise FeatureContextError("%s must be non-negative" % name)
    return result


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise FeatureContextError("%s must be a positive integer" % name)
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FeatureContextError("%s must be a positive integer" % name) from exc
    if result <= 0 or result != value:
        raise FeatureContextError("%s must be a positive integer" % name)
    return result


@dataclass(frozen=True)
class TrendContinuationVeto:
    min_abs_trend_score: Decimal
    min_abs_directional_pressure: Decimal
    min_abs_price_impact: Decimal
    max_directional_resilience: Decimal


@dataclass(frozen=True)
class FeatureContextPolicy:
    context_policy_id: str
    frozen_at: str
    instrument: str
    feature_version: str
    allowed_availability: str
    sampling_seconds: int
    warmup_seconds: int
    max_gap_seconds: int
    lookbacks_seconds: Tuple[int, ...]
    trend_lookback_seconds: int
    volatility_floor: Decimal
    trend_veto: TrendContinuationVeto
    digest: str

    @classmethod
    def load(cls, path: Path) -> "FeatureContextPolicy":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FeatureContextError("cannot load feature context policy") from exc
        if not isinstance(raw, dict) or raw.get("status") != FROZEN_FEATURE_CONTEXT_POLICY:
            raise FeatureContextError("feature context policy must have status %s" % FROZEN_FEATURE_CONTEXT_POLICY)
        for field in ("context_policy_id", "frozen_at", "instrument", "feature_version"):
            if not isinstance(raw.get(field), str) or not raw[field]:
                raise FeatureContextError("%s must be a non-empty string" % field)
        if raw.get("allowed_availability") != "ACTUAL_ONLY":
            raise FeatureContextError("feature context policy requires allowed_availability ACTUAL_ONLY")
        try:
            parse_utc(raw["frozen_at"])
        except ValueError as exc:
            raise FeatureContextError("frozen_at must be UTC ISO-8601") from exc
        sampling = raw.get("sampling")
        if not isinstance(sampling, dict):
            raise FeatureContextError("sampling must be an object")
        sampling_seconds = _positive_integer(sampling.get("decision_frequency_seconds"), "sampling.decision_frequency_seconds")
        if sampling_seconds != 1:
            raise FeatureContextError("context policy requires UTC one-second samples")
        warmup_seconds = _positive_integer(sampling.get("warmup_seconds"), "sampling.warmup_seconds")
        max_gap_seconds = _positive_integer(sampling.get("max_gap_seconds"), "sampling.max_gap_seconds")
        if max_gap_seconds != sampling_seconds:
            raise FeatureContextError("sampling.max_gap_seconds must equal the exact one-second sample interval")
        lookbacks = raw.get("lookbacks_seconds")
        if not isinstance(lookbacks, list) or not lookbacks:
            raise FeatureContextError("lookbacks_seconds must be a non-empty list")
        parsed_lookbacks = tuple(_positive_integer(item, "lookbacks_seconds") for item in lookbacks)
        if tuple(sorted(set(parsed_lookbacks))) != parsed_lookbacks:
            raise FeatureContextError("lookbacks_seconds must be sorted and unique")
        if warmup_seconds < parsed_lookbacks[-1]:
            raise FeatureContextError("warmup_seconds must cover the longest lookback")
        trend = raw.get("trend")
        if not isinstance(trend, dict):
            raise FeatureContextError("trend must be an object")
        trend_lookback = _positive_integer(trend.get("lookback_seconds"), "trend.lookback_seconds")
        if trend_lookback not in parsed_lookbacks:
            raise FeatureContextError("trend.lookback_seconds must be a declared lookback")
        volatility_floor = _number(trend.get("volatility_floor"), "trend.volatility_floor", positive=True)
        veto = raw.get("trend_continuation_veto")
        if not isinstance(veto, dict):
            raise FeatureContextError("trend_continuation_veto must be an object")
        trend_veto = TrendContinuationVeto(
            min_abs_trend_score=_number(veto.get("min_abs_trend_score"), "trend_continuation_veto.min_abs_trend_score", positive=True),
            min_abs_directional_pressure=_number(veto.get("min_abs_directional_pressure"), "trend_continuation_veto.min_abs_directional_pressure", positive=True),
            min_abs_price_impact=_number(veto.get("min_abs_price_impact"), "trend_continuation_veto.min_abs_price_impact", positive=True),
            max_directional_resilience=_number(veto.get("max_directional_resilience"), "trend_continuation_veto.max_directional_resilience"),
        )
        return cls(
            context_policy_id=raw["context_policy_id"], frozen_at=raw["frozen_at"],
            instrument=raw["instrument"].upper(), feature_version=raw["feature_version"], allowed_availability=raw["allowed_availability"],
            sampling_seconds=sampling_seconds, warmup_seconds=warmup_seconds,
            max_gap_seconds=max_gap_seconds, lookbacks_seconds=parsed_lookbacks,
            trend_lookback_seconds=trend_lookback, volatility_floor=volatility_floor,
            trend_veto=trend_veto,
            digest=hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True)
class MarketContextSnapshot:
    """A point-in-time context result; ``None`` values are explicitly unavailable."""

    available_at: datetime
    status: str
    decision_permission: str
    reason_codes: Tuple[str, ...]
    values: Dict[str, Optional[Decimal]]
    unavailable: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available_at": self.available_at.isoformat(),
            "context_status": self.status,
            "decision_permission": self.decision_permission,
            "reason_codes": list(self.reason_codes),
            "values": {key: (str(value) if value is not None else None) for key, value in self.values.items()},
            "unavailable": list(self.unavailable),
        }


class MarketContextEngine:
    """Compute collection-local Z features from one ACTUAL mid per UTC second.

    ``Z_log_return_<n>s`` is ``log(mid_t / mid_(t-n))`` on exact UTC-second
    samples. ``Z_realized_volatility_<n>s`` is the unannualized
    ``sqrt(sum(r_1s^2))`` over those exact samples. The input contract does not
    interpolate missing seconds.  A
    gap, invalid book or non-ACTUAL observation clears continuity and forces a
    fresh warmup, which prevents a stale context from being treated as ready.
    """

    def __init__(self, policy: FeatureContextPolicy) -> None:
        self.policy = policy
        self._samples: Deque[Tuple[datetime, Decimal]] = deque()
        self._prices: Dict[datetime, Decimal] = {}
        self._cum_sq_returns: Dict[datetime, Decimal] = {}
        self._highs: Deque[Tuple[datetime, Decimal]] = deque()
        self._lows: Deque[Tuple[datetime, Decimal]] = deque()
        self._continuous_start: Optional[datetime] = None
        self._last_at: Optional[datetime] = None
        self._last_directional_resilience: Optional[Tuple[datetime, str, Decimal]] = None

    @property
    def _longest_lookback(self) -> int:
        return self.policy.lookbacks_seconds[-1]

    def _empty_values(self) -> Dict[str, Optional[Decimal]]:
        values: Dict[str, Optional[Decimal]] = {}
        for lookback in self.policy.lookbacks_seconds:
            values["Z_log_return_%ds" % lookback] = None
            values["Z_realized_volatility_%ds" % lookback] = None
        trend = self.policy.trend_lookback_seconds
        values.update({
            "Z_trend_score_%ds" % trend: None,
            "Z_distance_to_rolling_high_vol_%ds" % trend: None,
            "Z_distance_to_rolling_low_vol_%ds" % trend: None,
            "Z_position_in_rolling_range_%ds" % trend: None,
            "Z_episode_anchor_distance_bps": None,
            # Explicitly directional (BUY uses sell-pressure/bid resilience;
            # SELL uses buy-pressure/ask resilience).  Never synthesize a
            # generic R or replace an unavailable value with zero.
            "R_directional": None,
            "R_directional_improvement": None,
            "price_impact_1s": None,
        })
        return values

    def _clear_continuity(self) -> None:
        self._samples.clear()
        self._prices.clear()
        self._cum_sq_returns.clear()
        self._highs.clear()
        self._lows.clear()
        self._continuous_start = None
        self._last_at = None
        self._last_directional_resilience = None

    def invalidate(self, *, available_at: datetime, reason: str) -> MarketContextSnapshot:
        """Explicitly reset when the caller knows a UTC bucket is missing.

        It is intentionally separate from ``observe``: fabricating a price
        for a missing second would violate the point-in-time evidence rule.
        """
        self._clear_continuity()
        return self._snapshot(available_at, status="DEGRADED", reasons=(reason,))

    def _snapshot(self, available_at: datetime, *, status: str, reasons: Iterable[str], values: Optional[Dict[str, Optional[Decimal]]] = None) -> MarketContextSnapshot:
        rendered = values if values is not None else self._empty_values()
        unavailable = tuple(sorted(key for key, value in rendered.items() if value is None))
        return MarketContextSnapshot(
            available_at=available_at, status=status, decision_permission="ABSTAIN",
            reason_codes=tuple(sorted(set(reasons))), values=rendered, unavailable=unavailable,
        )

    @staticmethod
    def _as_actual(kind: Any) -> bool:
        return kind == AvailabilityKind.ACTUAL or kind == AvailabilityKind.ACTUAL.value

    @staticmethod
    def _finite_decimal(value: Any) -> Optional[Decimal]:
        try:
            result = Decimal(str(value))
        except Exception:
            return None
        return result if result.is_finite() and result > 0 else None

    @staticmethod
    def _finite_signal(value: Any) -> Optional[Decimal]:
        try:
            result = Decimal(str(value))
        except Exception:
            return None
        return result if result.is_finite() else None

    def _validate_timestamp(self, available_at: datetime) -> Optional[str]:
        if not isinstance(available_at, datetime) or available_at.tzinfo is None:
            return "CONTEXT_TIMESTAMP_NOT_TIMEZONE_AWARE"
        if available_at.utcoffset() != timedelta(0):
            return "CONTEXT_TIMESTAMP_NOT_UTC"
        if available_at.microsecond:
            return "CONTEXT_TIMESTAMP_NOT_UTC_SECOND"
        return None

    @staticmethod
    def _log_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
        value = math.log(float(numerator / denominator))
        if not math.isfinite(value):
            raise FeatureContextError("non-finite log return")
        return Decimal(str(value))

    def _append(self, available_at: datetime, mid: Decimal) -> None:
        previous = self._last_at
        previous_price = self._prices.get(previous) if previous is not None else None
        cumulative = Decimal("0")
        if previous is not None:
            cumulative = self._cum_sq_returns[previous]
            log_return = self._log_ratio(mid, previous_price)
            cumulative += log_return * log_return
        self._samples.append((available_at, mid))
        self._prices[available_at] = mid
        self._cum_sq_returns[available_at] = cumulative
        self._last_at = available_at
        if self._continuous_start is None:
            self._continuous_start = available_at
        while self._highs and self._highs[-1][1] <= mid:
            self._highs.pop()
        self._highs.append((available_at, mid))
        while self._lows and self._lows[-1][1] >= mid:
            self._lows.pop()
        self._lows.append((available_at, mid))
        keep_after = available_at - timedelta(seconds=self._longest_lookback + self.policy.max_gap_seconds + 1)
        while self._samples and self._samples[0][0] < keep_after:
            expired, _ = self._samples.popleft()
            self._prices.pop(expired, None)
            self._cum_sq_returns.pop(expired, None)
        trend_cutoff = available_at - timedelta(seconds=self.policy.trend_lookback_seconds)
        while self._highs and self._highs[0][0] < trend_cutoff:
            self._highs.popleft()
        while self._lows and self._lows[0][0] < trend_cutoff:
            self._lows.popleft()

    def observe(
        self,
        *,
        available_at: datetime,
        mid_price: Any,
        availability_kind: Any,
        book_valid: bool,
        directional_pressure: Any = None,
        price_impact: Any = None,
        directional_resilience: Any = None,
        directional_resilience_feature: Any = None,
        episode_anchor_price: Any = None,
    ) -> MarketContextSnapshot:
        """Consume exactly one declared decision-second observation.

        A non-ACTUAL, invalid-book, malformed or discontinuous observation is
        not a harmless no-op: it invalidates the rolling context and returns a
        fail-closed snapshot.  This makes future pipeline integration explicit.
        """
        timestamp_issue = self._validate_timestamp(available_at)
        if timestamp_issue:
            self._clear_continuity()
            return self._snapshot(available_at, status="DEGRADED", reasons=(timestamp_issue,))
        if not self._as_actual(availability_kind):
            self._clear_continuity()
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_NON_ACTUAL",))
        if not book_valid:
            self._clear_continuity()
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_BOOK_INVALID",))
        mid = self._finite_decimal(mid_price)
        if mid is None:
            self._clear_continuity()
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_MID_INVALID",))
        if self._last_at is not None:
            elapsed = int((available_at - self._last_at).total_seconds())
            if elapsed <= 0:
                self._clear_continuity()
                return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_NON_MONOTONIC_OR_DUPLICATE_SAMPLE",))
            if elapsed > self.policy.max_gap_seconds:
                self._clear_continuity()
                self._append(available_at, mid)
                return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_GAP_EXCEEDED", "CONTEXT_WARMUP"))
            if elapsed != self.policy.sampling_seconds:
                # No interpolation is permitted.  A different cadence is a
                # declared coverage failure even if it is below max_gap.
                self._clear_continuity()
                self._append(available_at, mid)
                return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_SAMPLE_CADENCE_MISMATCH", "CONTEXT_WARMUP"))
        self._append(available_at, mid)
        directional_value = self._finite_signal(directional_resilience)
        directional_feature = directional_resilience_feature if isinstance(directional_resilience_feature, str) else None
        directional_values = self._empty_values()
        impact_value = self._finite_signal(price_impact)
        if impact_value is not None:
            directional_values["price_impact_1s"] = impact_value
        if directional_value is not None and directional_feature in {"R_sell_bid_resilience_1s", "R_buy_ask_resilience_1s"}:
            directional_values["R_directional"] = directional_value
            previous = self._last_directional_resilience
            # The difference is only valid for a contiguous, same-side,
            # one-second pair inside this engine/collection.  A side change
            # deliberately has no synthetic comparison baseline.
            if previous is not None and previous[0] == available_at - timedelta(seconds=self.policy.sampling_seconds) and previous[1] == directional_feature:
                directional_values["R_directional_improvement"] = directional_value - previous[2]
            self._last_directional_resilience = (available_at, directional_feature, directional_value)
        else:
            self._last_directional_resilience = None
        if self._continuous_start is None or (available_at - self._continuous_start).total_seconds() < self.policy.warmup_seconds:
            return self._snapshot(available_at, status="WARMUP", reasons=("CONTEXT_WARMUP",), values=directional_values)
        values = directional_values
        missing = []
        for lookback in self.policy.lookbacks_seconds:
            reference_at = available_at - timedelta(seconds=lookback)
            reference = self._prices.get(reference_at)
            reference_cum = self._cum_sq_returns.get(reference_at)
            current_cum = self._cum_sq_returns.get(available_at)
            if reference is None or reference_cum is None or current_cum is None:
                missing.append("%ds" % lookback)
                continue
            log_return = self._log_ratio(mid, reference)
            rv = (current_cum - reference_cum).sqrt()
            values["Z_log_return_%ds" % lookback] = log_return
            values["Z_realized_volatility_%ds" % lookback] = rv
        trend = self.policy.trend_lookback_seconds
        trend_return = values["Z_log_return_%ds" % trend]
        trend_rv = values["Z_realized_volatility_%ds" % trend]
        if trend_return is None or trend_rv is None or not self._highs or not self._lows:
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_LOOKBACK_UNAVAILABLE",) + tuple(missing), values=values)
        denominator = max(trend_rv, self.policy.volatility_floor)
        values["Z_trend_score_%ds" % trend] = trend_return / denominator
        rolling_high, rolling_low = self._highs[0][1], self._lows[0][1]
        values["Z_distance_to_rolling_high_vol_%ds" % trend] = self._log_ratio(mid, rolling_high) / denominator
        values["Z_distance_to_rolling_low_vol_%ds" % trend] = self._log_ratio(mid, rolling_low) / denominator
        if rolling_high == rolling_low:
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_ZERO_ROLLING_RANGE",), values=values)
        values["Z_position_in_rolling_range_%ds" % trend] = (mid - rolling_low) / (rolling_high - rolling_low)
        anchor = self._finite_decimal(episode_anchor_price)
        if anchor is not None:
            values["Z_episode_anchor_distance_bps"] = self._log_ratio(mid, anchor) * Decimal("10000")

        trend_score = values["Z_trend_score_%ds" % trend]
        pressure = self._finite_signal(directional_pressure)
        impact = self._finite_signal(price_impact)
        resilience = directional_value
        if pressure is None or impact is None or resilience is None:
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_TREND_VETO_INPUT_UNAVAILABLE",), values=values)
        # ``price_impact`` and resilience may legitimately be zero, unlike a
        # price.  Parse them separately after the strict mid/anchor validation.
        try:
            impact_signed = Decimal(str(price_impact))
            resilience_signed = Decimal(str(directional_resilience))
        except Exception:
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_TREND_VETO_INPUT_UNAVAILABLE",), values=values)
        if not impact_signed.is_finite() or not resilience_signed.is_finite():
            return self._snapshot(available_at, status="DEGRADED", reasons=("CONTEXT_TREND_VETO_INPUT_UNAVAILABLE",), values=values)
        veto = self.policy.trend_veto
        same_direction = (trend_score > 0 and pressure > 0 and impact_signed > 0) or (trend_score < 0 and pressure < 0 and impact_signed < 0)
        if (
            abs(trend_score) >= veto.min_abs_trend_score
            and abs(pressure) >= veto.min_abs_directional_pressure
            and abs(impact_signed) >= veto.min_abs_price_impact
            and resilience_signed <= veto.max_directional_resilience
            and same_direction
        ):
            return self._snapshot(available_at, status="READY", reasons=("TREND_CONTINUATION_OR_CONTEXT_UNAVAILABLE",), values=values)
        unavailable = tuple(sorted(key for key, value in values.items() if value is None))
        return MarketContextSnapshot(
            available_at=available_at, status="READY", decision_permission="ELIGIBLE",
            reason_codes=(), values=values, unavailable=unavailable,
        )
