"""Pure V3.3.2 position-reference calculations outside the decision path.

The reducer in this module evaluates a preregistered static benchmark against
an already sealed ordered path.  It never selects an Agent action, mutates the
paper ledger, or creates a market-cycle business artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Mapping

from ...domain.contracts.canonical import canonical_decimal, canonical_digest
from ...domain.market_cycle.paper import StaticNoTransitionComparatorV1


class PositionPathEvaluationError(ValueError):
    """A purported ordered path is semantically invalid or has been tampered."""


def _moment(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PositionPathEvaluationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PositionPathEvaluationError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PositionPathEvaluationError(f"{field} must include a UTC offset")
    return parsed


def _decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, str):
        raise PositionPathEvaluationError(f"{field} must be a canonical decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PositionPathEvaluationError(
            f"{field} must be a canonical decimal"
        ) from exc
    if (
        not parsed.is_finite()
        or parsed <= 0
        or canonical_decimal(parsed) != value
    ):
        raise PositionPathEvaluationError(f"{field} must be a positive canonical decimal")
    return parsed


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _c(value: Decimal) -> str:
    return canonical_decimal(value)


@dataclass(frozen=True, slots=True)
class StaticNoTransitionPathResultV1:
    comparator_id: str
    comparator_sha256: str
    episode_id: str
    reference_kind: str
    comparison_status: str
    comparison_reason: str
    path_sha256: str
    status: str
    reason: str | None
    eligible_point_count: int
    entry: Mapping[str, Any]
    mae: Mapping[str, Any]
    mfe: Mapping[str, Any]
    first_touch: Mapping[str, Any]
    static_endpoint: Mapping[str, Any]
    costs: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.status not in {
            "OBSERVED",
            "CENSORED",
            "UNRESOLVED_WITHIN_BAR",
        }:
            raise PositionPathEvaluationError("static path result status is invalid")
        if self.reference_kind != "IDEALIZED_STATIC_REFERENCE":
            raise PositionPathEvaluationError("static reference kind is invalid")
        if (
            self.comparison_status != "NOT_COMPARABLE"
            or self.comparison_reason
            != "NO_MATCHED_ACTUAL_SAME_FILL_COST_ARM"
        ):
            raise PositionPathEvaluationError(
                "static diagnostic cannot assert comparative superiority"
            )
        if type(self.eligible_point_count) is not int or self.eligible_point_count < 0:
            raise PositionPathEvaluationError("eligible_point_count must be nonnegative")
        for field_name in (
            "entry",
            "mae",
            "mfe",
            "first_touch",
            "static_endpoint",
            "costs",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping):
                raise PositionPathEvaluationError(f"{field_name} must be an object")
            object.__setattr__(self, field_name, _freeze(value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.static-no-transition-path-result",
            "schema_version": "1.1.0",
            "comparator_id": self.comparator_id,
            "comparator_sha256": self.comparator_sha256,
            "episode_id": self.episode_id,
            "reference_kind": self.reference_kind,
            "comparison_status": self.comparison_status,
            "comparison_reason": self.comparison_reason,
            "path_sha256": self.path_sha256,
            "status": self.status,
            "reason": self.reason,
            "eligible_point_count": self.eligible_point_count,
            "entry": _thaw(self.entry),
            "mae": _thaw(self.mae),
            "mfe": _thaw(self.mfe),
            "first_touch": _thaw(self.first_touch),
            "static_endpoint": _thaw(self.static_endpoint),
            "costs": _thaw(self.costs),
        }


def _empty_measure(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "price_excursion": None,
        "quote_value": None,
        "r_multiple": None,
    }


def _empty_costs(comparator: StaticNoTransitionComparatorV1) -> dict[str, Any]:
    model = comparator.cost_model
    return {
        "transaction_fee_status": "NOT_EVALUATED",
        "transaction_fees": None,
        "market_impact_status": "NOT_EVALUATED",
        "market_impact": None,
        "funding_status": model["funding_status"],
        "funding_cost": None,
        "borrow_status": model["borrow_status"],
        "borrow_cost": None,
        "net_pnl_status": "NOT_EVALUATED",
        "net_pnl": None,
    }


def _censored(
    comparator: StaticNoTransitionComparatorV1,
    *,
    path_sha256: str,
    reason: str,
    eligible_point_count: int = 0,
) -> StaticNoTransitionPathResultV1:
    return StaticNoTransitionPathResultV1(
        comparator_id=comparator.comparator_id,
        comparator_sha256=comparator.comparator_sha256,
        episode_id=str(comparator.reference["episode_id"]),
        reference_kind="IDEALIZED_STATIC_REFERENCE",
        comparison_status="NOT_COMPARABLE",
        comparison_reason="NO_MATCHED_ACTUAL_SAME_FILL_COST_ARM",
        path_sha256=path_sha256,
        status="CENSORED",
        reason=reason,
        eligible_point_count=eligible_point_count,
        entry={"status": "CENSORED", "touched_at": None, "sequence_index": None},
        mae=_empty_measure("CENSORED"),
        mfe=_empty_measure("CENSORED"),
        first_touch={
            "status": "CENSORED",
            "kind": None,
            "at": None,
            "sequence_index": None,
            "order_ids": [],
        },
        static_endpoint={
            "status": "CENSORED",
            "price": None,
            "gross_pnl": None,
            "gross_r_multiple": None,
        },
        costs=_empty_costs(comparator),
    )


def _unresolved(
    comparator: StaticNoTransitionComparatorV1,
    *,
    path_sha256: str,
    reason: str,
    eligible_point_count: int,
    point: Mapping[str, Any],
    entry_status: str,
    touch_kind: str,
    order_ids: list[str],
) -> StaticNoTransitionPathResultV1:
    return StaticNoTransitionPathResultV1(
        comparator_id=comparator.comparator_id,
        comparator_sha256=comparator.comparator_sha256,
        episode_id=str(comparator.reference["episode_id"]),
        reference_kind="IDEALIZED_STATIC_REFERENCE",
        comparison_status="NOT_COMPARABLE",
        comparison_reason="NO_MATCHED_ACTUAL_SAME_FILL_COST_ARM",
        path_sha256=path_sha256,
        status="UNRESOLVED_WITHIN_BAR",
        reason=reason,
        eligible_point_count=eligible_point_count,
        entry={
            "status": entry_status,
            "touched_at": point["closed_at"],
            "sequence_index": point["sequence_index"],
        },
        mae=_empty_measure("UNRESOLVED_WITHIN_BAR"),
        mfe=_empty_measure("UNRESOLVED_WITHIN_BAR"),
        first_touch={
            "status": "UNRESOLVED_WITHIN_BAR",
            "kind": touch_kind,
            "at": point["closed_at"],
            "sequence_index": point["sequence_index"],
            "order_ids": order_ids,
        },
        static_endpoint={
            "status": "NOT_EVALUATED",
            "price": None,
            "gross_pnl": None,
            "gross_r_multiple": None,
        },
        costs=_empty_costs(comparator),
    )


def _ordered_points(path: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if (
        path.get("schema_id")
        != "agent_trade_emotion_v332_ordered_outcome_path"
        or path.get("schema_version") != "1.0.0"
        or path.get("interval") != "15m"
        or path.get("intrabar_order") != "UNRESOLVED_WITHIN_BAR"
    ):
        raise PositionPathEvaluationError("ordered path schema mismatch")
    values = path.get("points")
    if not isinstance(values, (list, tuple)):
        raise PositionPathEvaluationError("ordered path points must be a sequence")
    result: list[dict[str, Any]] = []
    previous_closed: datetime | None = None
    for expected_index, value in enumerate(values):
        if not isinstance(value, Mapping):
            raise PositionPathEvaluationError("ordered path point must be an object")
        required = {
            "sequence_index",
            "opened_at",
            "closed_at",
            "open",
            "high",
            "low",
            "close",
            "confirmed_closed",
            "available_at",
            "raw_sha256",
        }
        if set(value) != required or value.get("sequence_index") != expected_index:
            raise PositionPathEvaluationError("ordered path point fields mismatch")
        opened = _moment(value["opened_at"], field="point.opened_at")
        closed = _moment(value["closed_at"], field="point.closed_at")
        available = _moment(value["available_at"], field="point.available_at")
        if (
            opened >= closed
            or available < closed
            or (previous_closed is not None and opened != previous_closed)
            or value["confirmed_closed"] is not True
        ):
            raise PositionPathEvaluationError("ordered path time sequence is invalid")
        open_price = _decimal(value["open"], field="point.open")
        high = _decimal(value["high"], field="point.high")
        low = _decimal(value["low"], field="point.low")
        close = _decimal(value["close"], field="point.close")
        if low > min(open_price, close) or high < max(open_price, close) or low > high:
            raise PositionPathEvaluationError("ordered path price geometry is invalid")
        raw_sha256 = value["raw_sha256"]
        if (
            not isinstance(raw_sha256, str)
            or len(raw_sha256) != 64
            or any(character not in "0123456789abcdef" for character in raw_sha256)
        ):
            raise PositionPathEvaluationError("ordered path raw digest is invalid")
        result.append(
            {
                **dict(value),
                "_opened": opened,
                "_closed": closed,
                "_open": open_price,
                "_high": high,
                "_low": low,
                "_close": close,
            }
        )
        previous_closed = closed
    coverage = path.get("coverage")
    if not isinstance(coverage, Mapping):
        raise PositionPathEvaluationError("ordered path coverage is missing")
    if (
        type(coverage.get("expected_point_count")) is not int
        or type(coverage.get("observed_point_count")) is not int
        or type(coverage.get("gap_count")) is not int
        or type(coverage.get("covers_all_closed_intervals")) is not bool
        or coverage["observed_point_count"] != len(result)
    ):
        raise PositionPathEvaluationError("ordered path coverage is invalid")
    return tuple(result)


def evaluate_static_no_transition_path(
    comparator_value: StaticNoTransitionComparatorV1 | Mapping[str, Any],
    ordered_path: Mapping[str, Any],
) -> StaticNoTransitionPathResultV1:
    """Evaluate one frozen static reference without inferring intrabar order."""

    comparator = (
        comparator_value
        if isinstance(comparator_value, StaticNoTransitionComparatorV1)
        else StaticNoTransitionComparatorV1.from_dict(comparator_value)
    )
    if not isinstance(ordered_path, Mapping):
        raise PositionPathEvaluationError("ordered path must be an object")
    path_sha256 = canonical_digest(ordered_path)
    if ordered_path.get("status") != "ORDERED":
        return _censored(
            comparator,
            path_sha256=path_sha256,
            reason=str(ordered_path.get("missing_reason") or "ORDERED_PATH_UNAVAILABLE"),
        )
    points = _ordered_points(ordered_path)
    coverage = ordered_path["coverage"]
    if (
        not coverage["covers_all_closed_intervals"]
        or coverage["gap_count"] != 0
        or coverage["expected_point_count"] != len(points)
        or not points
    ):
        return _censored(
            comparator,
            path_sha256=path_sha256,
            reason="ORDERED_PATH_COVERAGE_INCOMPLETE",
        )

    preregistered_at = _moment(
        comparator.preregistered_at, field="comparator.preregistered_at"
    )
    # A 15m bar that opened before registration contains an unknowable
    # pre-registration prefix.  It is never eligible for a forward benchmark.
    eligible = tuple(point for point in points if point["_opened"] >= preregistered_at)
    if not eligible:
        return _censored(
            comparator,
            path_sha256=path_sha256,
            reason="NO_FULLY_POST_REGISTRATION_CLOSED_BAR",
        )

    reference = comparator.reference
    entry_price = Decimal(reference["entry_price"])
    quantity = Decimal(reference["initial_quantity"])
    multiplier = Decimal(reference["contract_multiplier"])
    side = reference["entry_side"]
    stop = reference["protective_stop"]
    stop_price = Decimal(stop["price"])
    target_values = tuple(reference["take_profits"])
    expiry_text = reference["entry_expires_at"] or reference["intent_valid_until"]
    expiry = _moment(expiry_text, field="reference.entry_expiry")
    entry_eligible = tuple(point for point in eligible if point["_closed"] <= expiry)
    expiry_crossing = next(
        (
            point
            for point in eligible
            if point["_opened"] < expiry < point["_closed"]
        ),
        None,
    )
    if not entry_eligible and expiry_crossing is None:
        return _censored(
            comparator,
            path_sha256=path_sha256,
            reason="NO_FULLY_FORWARD_BAR_BEFORE_ENTRY_EXPIRY",
            eligible_point_count=len(eligible),
        )

    def entry_touched(point: Mapping[str, Any]) -> bool:
        return (
            point["_low"] <= entry_price
            if side == "BUY"
            else point["_high"] >= entry_price
        )

    def exit_touches(
        point: Mapping[str, Any],
    ) -> tuple[bool, list[Mapping[str, Any]]]:
        stop_touched = (
            point["_low"] <= stop_price
            if side == "BUY"
            else point["_high"] >= stop_price
        )
        touched_targets = [
            target
            for target in target_values
            if (
                point["_high"] >= Decimal(target["price"])
                if side == "BUY"
                else point["_low"] <= Decimal(target["price"])
            )
        ]
        return stop_touched, touched_targets

    entry_index = next(
        (
            index
            for index, point in enumerate(eligible)
            if point in entry_eligible and entry_touched(point)
        ),
        None,
    )
    if entry_index is None:
        if expiry_crossing is not None and entry_touched(expiry_crossing):
            return _unresolved(
                comparator,
                path_sha256=path_sha256,
                reason="ENTRY_TOUCH_TIME_VS_EXPIRY_UNKNOWN",
                eligible_point_count=len(eligible),
                point=expiry_crossing,
                entry_status="UNRESOLVED_WITHIN_BAR",
                touch_kind="ENTRY_VS_EXPIRY",
                order_ids=[str(reference["entry_order_id"])],
            )
        return StaticNoTransitionPathResultV1(
            comparator_id=comparator.comparator_id,
            comparator_sha256=comparator.comparator_sha256,
            episode_id=str(comparator.reference["episode_id"]),
            reference_kind="IDEALIZED_STATIC_REFERENCE",
            comparison_status="NOT_COMPARABLE",
            comparison_reason="NO_MATCHED_ACTUAL_SAME_FILL_COST_ARM",
            path_sha256=path_sha256,
            status="OBSERVED",
            reason=None,
            eligible_point_count=len(eligible),
            entry={"status": "NOT_TOUCHED", "touched_at": None, "sequence_index": None},
            mae=_empty_measure("NOT_APPLICABLE"),
            mfe=_empty_measure("NOT_APPLICABLE"),
            first_touch={
                "status": "NOT_APPLICABLE",
                "kind": None,
                "at": None,
                "sequence_index": None,
                "order_ids": [],
            },
            static_endpoint={
                "status": "NOT_APPLICABLE",
                "price": eligible[-1]["close"],
                "gross_pnl": None,
                "gross_r_multiple": None,
            },
            costs=_empty_costs(comparator),
        )

    entry_point = eligible[entry_index]
    entry_bar_stop, entry_bar_targets = exit_touches(entry_point)
    if entry_bar_stop or entry_bar_targets:
        return _unresolved(
            comparator,
            path_sha256=path_sha256,
            reason="ENTRY_EXIT_ORDER_UNKNOWN",
            eligible_point_count=len(eligible),
            point=entry_point,
            entry_status="BAR_TOUCH_REFERENCE",
            touch_kind=(
                "ENTRY_STOP_AND_TAKE_PROFIT"
                if entry_bar_stop and entry_bar_targets
                else "ENTRY_AND_PROTECTIVE_STOP"
                if entry_bar_stop
                else "ENTRY_AND_TAKE_PROFIT_SET"
            ),
            order_ids=(
                [str(reference["entry_order_id"])]
                + ([str(stop["order_id"])] if entry_bar_stop else [])
                + [str(target["order_id"]) for target in entry_bar_targets]
            ),
        )

    # OHLC cannot order entry and an exit touch inside the entry bar.  Exclude
    # that bar from post-entry MAE/MFE and begin the static arm at the next
    # fully forward bar.  Preserve the entry touch itself as a reference fact.
    active = eligible[entry_index + 1 :]
    if not active:
        return StaticNoTransitionPathResultV1(
            comparator_id=comparator.comparator_id,
            comparator_sha256=comparator.comparator_sha256,
            episode_id=str(comparator.reference["episode_id"]),
            reference_kind="IDEALIZED_STATIC_REFERENCE",
            comparison_status="NOT_COMPARABLE",
            comparison_reason="NO_MATCHED_ACTUAL_SAME_FILL_COST_ARM",
            path_sha256=path_sha256,
            status="CENSORED",
            reason="NO_FULLY_POST_ENTRY_CLOSED_BAR",
            eligible_point_count=len(eligible),
            entry={
                "status": "BAR_TOUCH_REFERENCE",
                "touched_at": eligible[entry_index]["closed_at"],
                "sequence_index": eligible[entry_index]["sequence_index"],
            },
            mae=_empty_measure("CENSORED"),
            mfe=_empty_measure("CENSORED"),
            first_touch={
                "status": "CENSORED",
                "kind": None,
                "at": None,
                "sequence_index": None,
                "order_ids": [],
            },
            static_endpoint={
                "status": "CENSORED",
                "price": None,
                "gross_pnl": None,
                "gross_r_multiple": None,
            },
            costs=_empty_costs(comparator),
        )
    risk_per_unit = abs(entry_price - stop_price)
    if side == "BUY":
        favorable = max(point["_high"] for point in active) - entry_price
        adverse = entry_price - min(point["_low"] for point in active)
    else:
        favorable = entry_price - min(point["_low"] for point in active)
        adverse = max(point["_high"] for point in active) - entry_price
    favorable = max(Decimal("0"), favorable)
    adverse = max(Decimal("0"), adverse)

    first_touch: dict[str, Any] = {
        "status": "NOT_TOUCHED",
        "kind": None,
        "at": None,
        "sequence_index": None,
        "order_ids": [],
    }
    unresolved = False
    for point in active:
        stop_touched, touched_targets = exit_touches(point)
        if not stop_touched and not touched_targets:
            continue
        mixed = stop_touched and bool(touched_targets)
        unresolved = mixed
        first_touch = {
            "status": "UNRESOLVED_WITHIN_BAR" if unresolved else "OBSERVED",
            "kind": (
                "STOP_AND_TAKE_PROFIT"
                if mixed
                else "PROTECTIVE_STOP"
                if stop_touched
                else "TAKE_PROFIT_SET"
            ),
            "at": point["closed_at"],
            "sequence_index": point["sequence_index"],
            "order_ids": (
                ([stop["order_id"]] if stop_touched else [])
                + [target["order_id"] for target in touched_targets]
            ),
        }
        break

    endpoint_price = active[-1]["_close"]
    direction = Decimal("1") if side == "BUY" else Decimal("-1")
    gross_pnl = (endpoint_price - entry_price) * direction * quantity * multiplier
    gross_r = gross_pnl / (risk_per_unit * quantity * multiplier)
    model = comparator.cost_model
    maker_rate = Decimal(model["maker_fee_bps"]) / Decimal("10000")
    taker_rate = Decimal(model["taker_fee_bps"]) / Decimal("10000")
    impact_rate = Decimal(model["market_impact_bps"]) / Decimal("10000")
    endpoint_execution_price = endpoint_price * (
        Decimal("1") - impact_rate
        if side == "BUY"
        else Decimal("1") + impact_rate
    )
    entry_notional = entry_price * quantity * multiplier
    endpoint_notional = endpoint_execution_price * quantity * multiplier
    transaction_fees = entry_notional * maker_rate + endpoint_notional * taker_rate
    market_impact = abs(endpoint_price - endpoint_execution_price) * quantity * multiplier
    modeled_pre_carry_pnl = (
        (endpoint_execution_price - entry_price)
        * direction
        * quantity
        * multiplier
        - transaction_fees
    )
    carry_known = model["funding_status"] == model["borrow_status"] == "NOT_APPLICABLE"
    costs = {
        "transaction_fee_status": "MODELED",
        "transaction_fees": _c(transaction_fees),
        "market_impact_status": "MODELED",
        "market_impact": _c(market_impact),
        "funding_status": model["funding_status"],
        "funding_cost": None,
        "borrow_status": model["borrow_status"],
        "borrow_cost": None,
        "modeled_pre_carry_pnl": _c(modeled_pre_carry_pnl),
        "net_pnl_status": "MODELED" if carry_known else "UNKNOWN",
        "net_pnl": _c(modeled_pre_carry_pnl) if carry_known else None,
    }
    return StaticNoTransitionPathResultV1(
        comparator_id=comparator.comparator_id,
        comparator_sha256=comparator.comparator_sha256,
        episode_id=str(comparator.reference["episode_id"]),
        reference_kind="IDEALIZED_STATIC_REFERENCE",
        comparison_status="NOT_COMPARABLE",
        comparison_reason="NO_MATCHED_ACTUAL_SAME_FILL_COST_ARM",
        path_sha256=path_sha256,
        status="UNRESOLVED_WITHIN_BAR" if unresolved else "OBSERVED",
        reason="STOP_TARGET_ORDER_UNKNOWN" if unresolved else None,
        eligible_point_count=len(eligible),
        entry={
            "status": "BAR_TOUCH_REFERENCE",
            "touched_at": eligible[entry_index]["closed_at"],
            "sequence_index": eligible[entry_index]["sequence_index"],
        },
        mae={
            "status": "OBSERVED_AFTER_ENTRY_BAR_ONLY",
            "price_excursion": _c(adverse),
            "quote_value": _c(adverse * quantity * multiplier),
            "r_multiple": _c(adverse / risk_per_unit),
        },
        mfe={
            "status": "OBSERVED_AFTER_ENTRY_BAR_ONLY",
            "price_excursion": _c(favorable),
            "quote_value": _c(favorable * quantity * multiplier),
            "r_multiple": _c(favorable / risk_per_unit),
        },
        first_touch=first_touch,
        static_endpoint={
            "status": "IDEALIZED_STATIC_REFERENCE",
            "price": _c(endpoint_price),
            "gross_pnl": _c(gross_pnl),
            "gross_r_multiple": _c(gross_r),
        },
        costs=costs,
    )


__all__ = [
    "PositionPathEvaluationError",
    "StaticNoTransitionPathResultV1",
    "evaluate_static_no_transition_path",
]
