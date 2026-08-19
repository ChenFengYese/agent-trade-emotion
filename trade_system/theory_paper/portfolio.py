"""Credential-free, one-way paper portfolio for the theory experiment.

The module is deliberately a local JSON state machine.  It has no exchange
client, account identifier, credential field, or order-routing capability.
All amounts named ``notional_usdt`` are converted to quantity at the supplied
paper fill price (one-times notional sizing); they are not leverage settings.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from .common import TheoryPaperError, canonical_bytes, iso_utc, parse_utc


SCHEMA_VERSION = "theory-paper-portfolio.v1"
PAPER_ONLY_MODE = "LOCAL_PAPER_SIMULATION_NO_ACCOUNT_NO_CREDENTIALS"

DEFAULT_INITIAL_POSITIONS: tuple[dict[str, Any], ...] = (
    {"symbol": "SNDKUSDT", "side": "LONG", "entry_price": 1125.0, "notional_usdt": 500.0},
    {"symbol": "ETHUSDT", "side": "LONG", "entry_price": 1920.0, "notional_usdt": 1000.0},
    {"symbol": "SOLUSDT", "side": "LONG", "entry_price": 75.0, "notional_usdt": 800.0},
    {"symbol": "BTCUSDT", "side": "LONG", "entry_price": 64000.0, "notional_usdt": 1000.0},
    {"symbol": "HYPEUSDT", "side": "LONG", "entry_price": 55.0, "notional_usdt": 800.0},
)

DEFAULT_INITIAL_ORDERS: tuple[dict[str, Any], ...] = (
    {"symbol": "SNDKUSDT", "side": "BUY", "limit_price": 1006.0, "notional_usdt": 300.0},
    {"symbol": "SNDKUSDT", "side": "BUY", "limit_price": 920.0, "notional_usdt": 300.0},
    {"symbol": "SNDKUSDT", "side": "BUY", "limit_price": 860.0, "notional_usdt": 500.0},
    {"symbol": "ETHUSDT", "side": "BUY", "limit_price": 1850.0, "notional_usdt": 300.0},
    {"symbol": "ETHUSDT", "side": "SELL", "limit_price": 1965.0, "notional_usdt": 1000.0},
    {"symbol": "SOLUSDT", "side": "BUY", "limit_price": 68.0, "notional_usdt": 1200.0},
    {"symbol": "SOLUSDT", "side": "SELL", "limit_price": 83.0, "notional_usdt": 1000.0},
    {"symbol": "BTCUSDT", "side": "BUY", "limit_price": 60200.0, "notional_usdt": 1000.0},
    {"symbol": "BTCUSDT", "side": "SELL", "limit_price": 66000.0, "notional_usdt": 1000.0},
    {"symbol": "HYPEUSDT", "side": "BUY", "limit_price": 51.0, "notional_usdt": 800.0},
    {"symbol": "HYPEUSDT", "side": "SELL", "limit_price": 73.0, "notional_usdt": 1000.0},
)

DEFAULT_RISK_LIMITS: dict[str, float] = {
    "max_gross_leverage": 1.5,
    "max_symbol_equity_fraction": 0.35,
    "max_symbol_open_risk_equity_fraction": 0.01,
    "max_trade_risk_equity_fraction": 0.015,
    "exploration_probe_risk_fraction": 0.0015,
    "max_portfolio_risk_equity_fraction": 0.06,
    "daily_realized_loss_fraction": 0.02,
    "max_drawdown_fraction": 0.12,
    "minimum_reward_risk": 1.5,
    "minimum_order_notional_usdt": 50.0,
    "maximum_order_notional_usdt": 1500.0,
    "maker_fee_rate": 0.0002,
    "taker_fee_rate": 0.0005,
    "market_slippage_bps": 2.0,
    "stop_slippage_bps": 3.0,
}

ORDER_STATES = {
    "REVIEW_REQUIRED",
    "ACTIVE",
    "CANCELED",
    "REPLACED",
    "FILLED",
    "PARTIALLY_FILLED_REDUCE_ONLY_CANCELED",
    "PARTIALLY_FILLED_RISK_BLOCKED",
    "RISK_REJECTED_AT_TRIGGER",
}


def _round(value: float, digits: int = 8) -> float:
    return round(float(value), digits)


def _positive(value: Any, name: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool):
        raise TheoryPaperError(f"{name} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise TheoryPaperError(f"{name} must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0 or (parsed == 0 and not allow_zero):
        raise TheoryPaperError(f"{name} must be {'nonnegative' if allow_zero else 'positive'}")
    return parsed


def _side(value: Any, *, position: bool = False) -> str:
    normalized = str(value).upper()
    allowed = {"LONG", "SHORT"} if position else {"BUY", "SELL"}
    if normalized not in allowed:
        raise TheoryPaperError(f"side must be one of {sorted(allowed)}")
    return normalized


def _symbol(value: Any) -> str:
    normalized = str(value).upper().strip()
    if not normalized or not normalized.endswith("USDT") or not normalized.replace("_", "").isalnum():
        raise TheoryPaperError("symbol must be a USDT instrument")
    return normalized


def _time(value: str | datetime | None) -> str:
    if value is None:
        return iso_utc()
    if isinstance(value, datetime):
        return iso_utc(value)
    parse_utc(value)
    return value


def _epoch_ms(value: str) -> int:
    return int(parse_utc(value).timestamp() * 1000)


def _counter_id(state: MutableMapping[str, Any], kind: str) -> str:
    counters = state["counters"]
    counters[kind] = int(counters.get(kind, 0)) + 1
    return f"{kind}-{counters[kind]:06d}"


def _risk_authorization(value: Any, *, default_authority: str | None = None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            "approved": value.get("approved") is True,
            "authority": str(value.get("authority") or default_authority or "UNSPECIFIED"),
            "reason": str(value.get("reason") or ""),
        }
    return {
        "approved": value is True,
        "authority": default_authority or ("AGENT_DECISION" if value is True else "NONE"),
        "reason": "",
    }


def _authorization_from_action(action: Mapping[str, Any], attribution: str) -> dict[str, Any]:
    supplied = action.get("risk_authorization", action.get("authorize_new_risk", False))
    default = "SEALED_CHAOS_SCHEDULE" if attribution == "CHAOS_AUTO" else (
        "EXPLICIT_MANUAL_CHAOS" if attribution == "CHAOS_MANUAL" else "AGENT_DECISION"
    )
    return _risk_authorization(supplied, default_authority=default)


def _copy_rows(value: Any, default: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = default if value is None else value
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TheoryPaperError("positions/orders must be arrays")
    if not all(isinstance(row, Mapping) for row in rows):
        raise TheoryPaperError("positions/orders entries must be objects")
    return [dict(row) for row in rows]


def _merged_risk_limits(config: Mapping[str, Any], portfolio: Mapping[str, Any]) -> dict[str, float]:
    raw = config.get("risk_limits", portfolio.get("risk_limits", {}))
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise TheoryPaperError("risk_limits must be an object")
    merged = dict(DEFAULT_RISK_LIMITS)
    aliases = {
        "gross_cap_multiple": "max_gross_leverage",
        "max_gross_notional_multiple": "max_gross_leverage",
        "max_symbol_fraction": "max_symbol_equity_fraction",
        "max_trade_risk_fraction": "max_trade_risk_equity_fraction",
        "max_portfolio_risk_fraction": "max_portfolio_risk_equity_fraction",
        "min_reward_risk": "minimum_reward_risk",
    }
    for key, value in raw.items():
        target = aliases.get(str(key), str(key))
        if target in merged:
            merged[target] = _positive(value, f"risk_limits.{target}", allow_zero=target.endswith(("fee_rate", "slippage_bps")))
    policy = config.get("risk_policy", {})
    if policy is None:
        policy = {}
    if not isinstance(policy, Mapping):
        raise TheoryPaperError("risk_policy must be an object")
    policy_mapping = {
        "standard_thesis_risk_fraction": "max_trade_risk_equity_fraction",
        "exploration_probe_risk_fraction": "exploration_probe_risk_fraction",
        "per_instrument_open_pending_risk_fraction": "max_symbol_open_risk_equity_fraction",
        "portfolio_open_pending_risk_fraction": "max_portfolio_risk_equity_fraction",
        "daily_realized_loss_fraction": "daily_realized_loss_fraction",
        "drawdown_no_new_risk_fraction": "max_drawdown_fraction",
        "gross_notional_equity_multiple": "max_gross_leverage",
        "minimum_reward_risk": "minimum_reward_risk",
        "default_taker_fee_rate": "taker_fee_rate",
        "default_maker_fee_rate": "maker_fee_rate",
        "default_market_slippage_bps": "market_slippage_bps",
        "default_stop_slippage_bps": "stop_slippage_bps",
    }
    for key, target in policy_mapping.items():
        if key in policy:
            merged[target] = _positive(
                policy[key],
                f"risk_policy.{key}",
                allow_zero=target.endswith(("fee_rate", "slippage_bps")),
            )
    if merged["max_gross_leverage"] <= 0:
        raise TheoryPaperError("max_gross_leverage must be positive")
    return {key: _round(value) for key, value in merged.items()}


def _stop_fill_price(
    position_side: str,
    stop_price: float,
    stop_slippage_bps: float,
) -> float:
    exit_side = "SELL" if position_side == "LONG" else "BUY"
    multiplier = 1.0 + (
        stop_slippage_bps / 10000.0
        if exit_side == "BUY"
        else -stop_slippage_bps / 10000.0
    )
    return stop_price * multiplier


def _protection_terms(
    limits: Mapping[str, Any],
    position_side: str,
    reference_price: float,
    stop_price: Any,
    target_price: Any,
    *,
    entry_fee_rate: float,
) -> dict[str, Any]:
    """Return gross and cost-aware per-unit geometry under frozen assumptions."""

    side = _side(position_side, position=True)
    reference = _positive(reference_price, "reference_price")
    stop = _positive(stop_price, "stop_price")
    target = _positive(target_price, "target_price")
    if side == "LONG":
        gross_risk = reference - stop
        gross_reward = target - reference
    else:
        gross_risk = stop - reference
        gross_reward = reference - target
    if gross_risk <= 0 or gross_reward <= 0:
        raise TheoryPaperError("STOP_TARGET_GEOMETRY_INVALID")

    stop_slippage_bps = float(limits["stop_slippage_bps"])
    maker_fee_rate = float(limits["maker_fee_rate"])
    taker_fee_rate = float(limits["taker_fee_rate"])
    stopped_at = _stop_fill_price(side, stop, stop_slippage_bps)
    stop_price_loss = (
        reference - stopped_at if side == "LONG" else stopped_at - reference
    )
    target_price_gain = (
        target - reference if side == "LONG" else reference - target
    )
    entry_fee_per_unit = reference * float(entry_fee_rate)
    stop_exit_fee_per_unit = stopped_at * taker_fee_rate
    target_exit_fee_per_unit = target * maker_fee_rate
    net_risk = stop_price_loss + entry_fee_per_unit + stop_exit_fee_per_unit
    net_reward = target_price_gain - entry_fee_per_unit - target_exit_fee_per_unit
    if net_risk <= 0 or net_reward <= 0:
        raise TheoryPaperError("NET_STOP_TARGET_GEOMETRY_INVALID")
    return {
        "reference_price": _round(reference),
        "stop_trigger_price": _round(stop),
        "stop_fill_price": _round(stopped_at),
        "target_fill_price": _round(target),
        "gross_risk_per_unit": _round(gross_risk),
        "gross_reward_per_unit": _round(gross_reward),
        "entry_fee_per_unit": _round(entry_fee_per_unit),
        "stop_exit_fee_per_unit": _round(stop_exit_fee_per_unit),
        "target_exit_fee_per_unit": _round(target_exit_fee_per_unit),
        "net_risk_per_unit": _round(net_risk),
        "net_reward_per_unit": _round(net_reward),
        "gross_reward_risk": _round(gross_reward / gross_risk, 6),
        "net_reward_risk": _round(net_reward / net_risk, 6),
        "assumptions": {
            "entry_fee_rate": _round(float(entry_fee_rate), 8),
            "target_exit_fee_rate": _round(maker_fee_rate, 8),
            "stop_exit_fee_rate": _round(taker_fee_rate, 8),
            "stop_slippage_bps": _round(stop_slippage_bps, 6),
            "target_slippage_bps": 0.0,
        },
    }


def _forward_stop_risk(
    limits: Mapping[str, Any],
    position_side: str,
    mark_price: float,
    stop_price: float,
    quantity: float,
) -> tuple[float, float]:
    """Return mark-to-stop risk and the assumed stopped fill price."""

    stopped_at = _stop_fill_price(
        position_side,
        float(stop_price),
        float(limits["stop_slippage_bps"]),
    )
    price_loss = (
        float(mark_price) - stopped_at
        if position_side == "LONG"
        else stopped_at - float(mark_price)
    )
    exit_fee = stopped_at * float(limits["taker_fee_rate"])
    return max(0.0, price_loss) * quantity + exit_fee * quantity, stopped_at


def initialize_portfolio(
    config: Mapping[str, Any] | None = None,
    observed_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable paper state with user-supplied initial exposure.

    Initial positions are explicitly exogenous and have a one-cycle protection
    grace.  Initial orders are *not* active: the first agent decision must KEEP,
    REPLACE, or CANCEL each order.  This prevents pre-initialization bars from
    manufacturing fills.
    """

    source = dict(config or {})
    nested = source.get("initial_portfolio", source)
    if not isinstance(nested, Mapping):
        raise TheoryPaperError("initial_portfolio must be an object")
    activated_at = _time(observed_at or source.get("activated_at"))
    initial_equity = _positive(
        nested.get("initial_equity_usdt", nested.get("initial_cash_usdt", nested.get("cash_usdt", 10000.0))),
        "initial_equity_usdt",
    )
    positions = _copy_rows(nested.get("positions"), DEFAULT_INITIAL_POSITIONS)
    orders = _copy_rows(nested.get("orders"), DEFAULT_INITIAL_ORDERS)
    risk_limits = _merged_risk_limits(source, nested)
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": PAPER_ONLY_MODE,
        "paper_only": True,
        "activated_at": activated_at,
        "updated_at": activated_at,
        "initial_equity_usdt": _round(initial_equity),
        "cash_balance_usdt": _round(initial_equity),
        "realized_pnl_usdt": 0.0,
        "daily_realized_pnl_usdt": {},
        "daily_net_realized_pnl_usdt": {},
        "fees_paid_usdt": 0.0,
        "cycle_count": 0,
        "notional_interpretation": "ONE_TIMES_USDT_NOTIONAL_CONVERTED_TO_QUANTITY_AT_FILL_PRICE",
        "risk_limits": risk_limits,
        "risk_state": {"new_risk_allowed": False, "reasons": ["INITIAL_PROTECTION_REVIEW_REQUIRED"]},
        "lots": [],
        "orders": [],
        "fills": [],
        "last_processed_close_time_ms": {},
        "counters": {"lot": 0, "order": 0, "fill": 0},
        "chaos": {
            "schedule": [],
            "manual_injection_count": 0,
            "boundary": "LOCAL_PAPER_ATTRIBUTION_ONLY",
        },
    }
    for row in positions:
        symbol = _symbol(row.get("symbol"))
        side = _side(row.get("side"), position=True)
        entry = _positive(row.get("entry_price"), "position.entry_price")
        notional = _positive(row.get("notional_usdt"), "position.notional_usdt")
        stop = row.get("stop_price")
        target = row.get("target_price")
        if (stop is None) != (target is None):
            raise TheoryPaperError("initial position protection needs both stop and target")
        quantity = _round(notional / entry, 12)
        protection_terms = None
        if stop is not None:
            try:
                protection_terms = _protection_terms(
                    state["risk_limits"],
                    side,
                    entry,
                    stop,
                    target,
                    entry_fee_rate=0.0,
                )
            except TheoryPaperError as exc:
                raise TheoryPaperError(
                    f"initial position protection invalid: {exc}"
                ) from exc
        lot = {
            "lot_id": _counter_id(state, "lot"),
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "initial_quantity": quantity,
            "entry_price": _round(entry),
            "entry_notional_usdt": _round(notional),
            "entry_fee_usdt": 0.0,
            "remaining_entry_fee_usdt": 0.0,
            "exit_fees_usdt": 0.0,
            "opened_at": str(row.get("opened_at") or activated_at),
            "origin": str(row.get("origin") or "EXOGENOUS_INITIAL_POSITION"),
            "attribution": "EXOGENOUS",
            "hypothesis_id": row.get("hypothesis_id"),
            "stop_price": None if stop is None else _round(_positive(stop, "position.stop_price")),
            "target_price": None if target is None else _round(_positive(target, "position.target_price")),
            "protection_activated_at": activated_at if stop is not None and target is not None else None,
            "initial_stop_price": None if stop is None else _round(_positive(stop, "position.stop_price")),
            "initial_net_risk_usdt": (
                None
                if protection_terms is None
                else _round(
                    float(protection_terms["net_risk_per_unit"]) * quantity
                )
            ),
            "entry_reward_risk_gross": (
                None
                if protection_terms is None
                else protection_terms["gross_reward_risk"]
            ),
            "entry_reward_risk_net": (
                None
                if protection_terms is None
                else protection_terms["net_reward_risk"]
            ),
            "entry_cost_assumptions": (
                None
                if protection_terms is None
                else protection_terms["assumptions"]
            ),
            "current_protection_terms": protection_terms,
            "legacy_protection_grace_through_cycle": 1,
            "mfe_usdt": 0.0,
            "mae_usdt": 0.0,
            "risk_authorization": {
                "approved": True,
                "authority": "USER_INITIAL_CONDITIONS",
                "reason": "Imported initial exposure; not an agent-created trade.",
            },
            "status": "OPEN",
            "closed_at": None,
            "realized_pnl_usdt": 0.0,
            "net_realized_pnl_usdt": 0.0,
        }
        state["lots"].append(lot)
    initial_sides: dict[str, set[str]] = {}
    for lot in state["lots"]:
        initial_sides.setdefault(lot["symbol"], set()).add(lot["side"])
    if any(len(sides) > 1 for sides in initial_sides.values()):
        raise TheoryPaperError("initial portfolio violates one-way netting")
    for row in orders:
        symbol = _symbol(row.get("symbol"))
        side = _side(row.get("side"))
        price = _positive(row.get("limit_price"), "order.limit_price")
        notional = _positive(row.get("notional_usdt"), "order.notional_usdt")
        state["orders"].append(
            {
                "order_id": _counter_id(state, "order"),
                "symbol": symbol,
                "side": side,
                "order_type": "LIMIT",
                "limit_price": _round(price),
                "notional_usdt": _round(notional),
                "quantity": _round(notional / price, 12),
                "remaining_quantity": _round(notional / price, 12),
                "state": "REVIEW_REQUIRED",
                "created_at": str(row.get("created_at") or activated_at),
                "activated_at": None,
                "origin": "USER_INITIAL_PLAN",
                "attribution": "EXOGENOUS",
                "hypothesis_id": None,
                "reduce_only": False,
                "allow_reverse": True,
                "stop_price": None,
                "target_price": None,
                "risk_authorization": {
                    "approved": True,
                    "authority": "USER_INITIAL_CONDITIONS",
                    "reason": "Must be reviewed and protected before activation.",
                },
                "review_note": "Agent must KEEP with explicit protection/reduce-only, REPLACE, or CANCEL.",
            }
        )
    schedule = source.get("chaos_schedule", nested.get("chaos_schedule", []))
    if schedule is None:
        schedule = []
    if not isinstance(schedule, Sequence) or isinstance(schedule, (str, bytes)):
        raise TheoryPaperError("chaos_schedule must be an array")
    for index, row in enumerate(schedule, start=1):
        if not isinstance(row, Mapping):
            raise TheoryPaperError("chaos schedule entries must be objects")
        due_at = _time(row.get("due_at"))
        state["chaos"]["schedule"].append(
            {
                "chaos_id": str(row.get("chaos_id") or f"chaos-auto-{index:03d}"),
                "due_at": due_at,
                "symbol": _symbol(row.get("symbol")),
                "side": _side(row.get("side")),
                "notional_usdt": _round(_positive(row.get("notional_usdt"), "chaos.notional_usdt")),
                "stop_distance_fraction": _round(_positive(row.get("stop_distance_fraction", 0.02), "chaos.stop_distance_fraction")),
                "target_distance_fraction": _round(_positive(row.get("target_distance_fraction", 0.04), "chaos.target_distance_fraction")),
                "state": "SEALED",
                "attribution": "CHAOS_AUTO",
            }
        )
    _refresh_risk_state(state, {})
    validate_portfolio_state(state)
    return state


def validate_portfolio_state(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise TheoryPaperError("portfolio schema version is invalid")
    if state.get("mode") != PAPER_ONLY_MODE or state.get("paper_only") is not True:
        raise TheoryPaperError("portfolio must remain local paper only")
    forbidden = {
        "apikey",
        "apisecret",
        "secretkey",
        "credential",
        "credentials",
        "accountid",
        "privatekey",
        "token",
        "accesstoken",
        "refreshtoken",
        "signature",
        "listenkey",
        "passphrase",
        "mnemonic",
        "seedphrase",
    }
    stack: list[Any] = [state]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key, value in current.items():
                normalized_key = "".join(
                    character
                    for character in str(key).lower()
                    if character.isalnum()
                )
                if normalized_key in forbidden:
                    raise TheoryPaperError("portfolio state must not contain account or credential fields")
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)
    canonical_bytes(state)

    def rows(name: str) -> list[Mapping[str, Any]]:
        value = state.get(name)
        if not isinstance(value, list) or not all(
            isinstance(item, Mapping) for item in value
        ):
            raise TheoryPaperError(f"portfolio {name} must be an array of objects")
        return value

    def finite(
        value: Any,
        name: str,
        *,
        positive: bool = False,
        nonnegative: bool = False,
    ) -> float:
        if isinstance(value, bool):
            raise TheoryPaperError(f"{name} must be numeric")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise TheoryPaperError(f"{name} must be numeric") from exc
        if not math.isfinite(parsed):
            raise TheoryPaperError(f"{name} must be finite")
        if positive and parsed <= 0:
            raise TheoryPaperError(f"{name} must be positive")
        if nonnegative and parsed < 0:
            raise TheoryPaperError(f"{name} must be nonnegative")
        return parsed

    def close_enough(left: float, right: float) -> bool:
        return math.isclose(left, right, rel_tol=1e-8, abs_tol=1e-6)

    def timestamp(value: Any, name: str) -> datetime:
        try:
            return parse_utc(str(value))
        except TheoryPaperError as exc:
            raise TheoryPaperError(f"{name} must be canonical UTC") from exc

    lots = rows("lots")
    orders = rows("orders")
    fills = rows("fills")
    counters = state.get("counters")
    if not isinstance(counters, Mapping):
        raise TheoryPaperError("portfolio counters must be an object")

    id_sets: dict[str, set[str]] = {"lot": set(), "order": set(), "fill": set()}
    max_id = {"lot": 0, "order": 0, "fill": 0}

    def register_id(kind: str, value: Any) -> str:
        identifier = str(value or "")
        prefix = f"{kind}-"
        if not identifier.startswith(prefix) or not identifier[len(prefix) :].isdigit():
            raise TheoryPaperError(f"{kind} id is invalid")
        if identifier in id_sets[kind]:
            raise TheoryPaperError(f"duplicate {kind} id")
        id_sets[kind].add(identifier)
        max_id[kind] = max(max_id[kind], int(identifier[len(prefix) :]))
        return identifier

    open_sides: dict[str, set[str]] = {}
    lot_by_id: dict[str, Mapping[str, Any]] = {}
    for lot in lots:
        lot_id = register_id("lot", lot.get("lot_id"))
        lot_by_id[lot_id] = lot
        symbol = _symbol(lot.get("symbol"))
        side = _side(lot.get("side"), position=True)
        quantity = finite(lot.get("quantity"), f"{lot_id}.quantity", nonnegative=True)
        initial_quantity = finite(
            lot.get("initial_quantity"),
            f"{lot_id}.initial_quantity",
            positive=True,
        )
        if quantity > initial_quantity + 1e-8:
            raise TheoryPaperError("lot quantity exceeds its initial quantity")
        finite(lot.get("entry_price"), f"{lot_id}.entry_price", positive=True)
        finite(
            lot.get("entry_notional_usdt"),
            f"{lot_id}.entry_notional_usdt",
            positive=True,
        )
        for field in (
            "entry_fee_usdt",
            "remaining_entry_fee_usdt",
            "exit_fees_usdt",
            "mfe_usdt",
            "mae_usdt",
        ):
            finite(lot.get(field), f"{lot_id}.{field}", nonnegative=True)
        finite(lot.get("realized_pnl_usdt"), f"{lot_id}.realized_pnl_usdt")
        finite(
            lot.get("net_realized_pnl_usdt"),
            f"{lot_id}.net_realized_pnl_usdt",
        )
        opened_at = timestamp(lot.get("opened_at"), f"{lot_id}.opened_at")
        status = lot.get("status")
        if status == "OPEN":
            if quantity <= 1e-12 or lot.get("closed_at") is not None:
                raise TheoryPaperError("open lot has invalid quantity or closed_at")
            open_sides.setdefault(symbol, set()).add(side)
        elif status == "CLOSED":
            if quantity > 1e-12 or lot.get("closed_at") is None:
                raise TheoryPaperError("closed lot has residual quantity or no closed_at")
            if timestamp(lot.get("closed_at"), f"{lot_id}.closed_at") < opened_at:
                raise TheoryPaperError("lot closed_at precedes opened_at")
            if float(lot.get("remaining_entry_fee_usdt", 0.0)) > 1e-6:
                raise TheoryPaperError("closed lot retains unallocated entry fee")
        else:
            raise TheoryPaperError("lot status is invalid")
        stop, target = lot.get("stop_price"), lot.get("target_price")
        if (stop is None) != (target is None):
            raise TheoryPaperError("lot protection must contain both stop and target")
        if stop is not None:
            stop_value = finite(stop, f"{lot_id}.stop_price", positive=True)
            target_value = finite(target, f"{lot_id}.target_price", positive=True)
            if (side == "LONG" and stop_value >= target_value) or (
                side == "SHORT" and target_value >= stop_value
            ):
                raise TheoryPaperError("lot stop and target ordering is invalid")
        if lot.get("protection_activated_at") is not None:
            timestamp(
                lot.get("protection_activated_at"),
                f"{lot_id}.protection_activated_at",
            )
    if any(len(sides) > 1 for sides in open_sides.values()):
        raise TheoryPaperError("portfolio violates one-way netting")

    order_by_id: dict[str, Mapping[str, Any]] = {}
    for order in orders:
        order_id = register_id("order", order.get("order_id"))
        order_by_id[order_id] = order
        _symbol(order.get("symbol"))
        _side(order.get("side"))
        quantity = finite(
            order.get("quantity"),
            f"{order_id}.quantity",
            positive=True,
        )
        remaining = finite(
            order.get("remaining_quantity"),
            f"{order_id}.remaining_quantity",
            nonnegative=True,
        )
        if remaining > quantity + 1e-8:
            raise TheoryPaperError("order remaining quantity exceeds original quantity")
        finite(order.get("limit_price"), f"{order_id}.limit_price", positive=True)
        finite(
            order.get("notional_usdt"),
            f"{order_id}.notional_usdt",
            positive=True,
        )
        timestamp(order.get("created_at"), f"{order_id}.created_at")
        if order.get("activated_at") is not None:
            timestamp(order.get("activated_at"), f"{order_id}.activated_at")
        order_state = order.get("state")
        if order_state not in ORDER_STATES:
            raise TheoryPaperError("order state is invalid")
        if order_state in {"REVIEW_REQUIRED", "ACTIVE"} and remaining <= 1e-12:
            raise TheoryPaperError("live order has no remaining quantity")
        if order_state in {"FILLED", "PARTIALLY_FILLED_REDUCE_ONLY_CANCELED"} and (
            remaining > 1e-12
        ):
            raise TheoryPaperError("terminal filled order retains quantity")
        stop, target = order.get("stop_price"), order.get("target_price")
        if (stop is None) != (target is None):
            raise TheoryPaperError("order protection must contain both stop and target")
        if order_state == "ACTIVE" and order.get("reduce_only") is not True:
            if stop is None:
                raise TheoryPaperError("active new-risk order is unprotected")
            stop_value = finite(stop, f"{order_id}.stop_price", positive=True)
            target_value = finite(target, f"{order_id}.target_price", positive=True)
            if (
                order.get("side") == "BUY"
                and not stop_value < float(order["limit_price"]) < target_value
            ) or (
                order.get("side") == "SELL"
                and not target_value < float(order["limit_price"]) < stop_value
            ):
                raise TheoryPaperError("active order protection geometry is invalid")

    opened_quantities: dict[str, float] = {}
    closed_quantities: dict[str, float] = {}
    closed_gross_by_lot: dict[str, float] = {}
    closed_net_by_lot: dict[str, float] = {}
    allocated_entry_fee_by_lot: dict[str, float] = {}
    exit_fee_by_lot: dict[str, float] = {}
    total_fill_fees = 0.0
    exit_slice_count = 0
    for fill in fills:
        fill_id = register_id("fill", fill.get("fill_id"))
        _symbol(fill.get("symbol"))
        _side(fill.get("side"))
        quantity = finite(fill.get("quantity"), f"{fill_id}.quantity", positive=True)
        price = finite(fill.get("price"), f"{fill_id}.price", positive=True)
        notional = finite(
            fill.get("notional_usdt"),
            f"{fill_id}.notional_usdt",
            positive=True,
        )
        if not close_enough(notional, quantity * price):
            raise TheoryPaperError("fill notional does not equal quantity times price")
        fee = finite(fill.get("fee_usdt"), f"{fill_id}.fee_usdt", nonnegative=True)
        total_fill_fees += fee
        timestamp(fill.get("observed_at"), f"{fill_id}.observed_at")
        order_id = fill.get("order_id")
        if order_id is not None and order_id not in order_by_id:
            raise TheoryPaperError("fill references an unknown order")
        closed_rows = fill.get("closed_lots")
        if not isinstance(closed_rows, list) or not all(
            isinstance(item, Mapping) for item in closed_rows
        ):
            raise TheoryPaperError("fill closed_lots must be an array of objects")
        closed_in_fill = 0.0
        expected_fill_fee = 0.0
        for closed in closed_rows:
            exit_slice_count += 1
            lot_id = str(closed.get("lot_id") or "")
            if lot_id not in lot_by_id:
                raise TheoryPaperError("fill references an unknown closed lot")
            closed_quantity = finite(
                closed.get("quantity"),
                f"{fill_id}.closed_quantity",
                positive=True,
            )
            gross_pnl = finite(
                closed.get("realized_pnl_usdt"),
                f"{fill_id}.closed_gross_pnl",
            )
            entry_fee = finite(
                closed.get("allocated_entry_fee_usdt"),
                f"{fill_id}.allocated_entry_fee",
                nonnegative=True,
            )
            exit_fee = finite(
                closed.get("exit_fee_usdt"),
                f"{fill_id}.exit_fee",
                nonnegative=True,
            )
            net_pnl = finite(
                closed.get("net_realized_pnl_usdt"),
                f"{fill_id}.closed_net_pnl",
            )
            if not close_enough(net_pnl, gross_pnl - entry_fee - exit_fee):
                raise TheoryPaperError("closed lot net PnL does not reconcile")
            closed_in_fill += closed_quantity
            expected_fill_fee += exit_fee
            closed_quantities[lot_id] = (
                closed_quantities.get(lot_id, 0.0) + closed_quantity
            )
            closed_gross_by_lot[lot_id] = (
                closed_gross_by_lot.get(lot_id, 0.0) + gross_pnl
            )
            closed_net_by_lot[lot_id] = (
                closed_net_by_lot.get(lot_id, 0.0) + net_pnl
            )
            allocated_entry_fee_by_lot[lot_id] = (
                allocated_entry_fee_by_lot.get(lot_id, 0.0) + entry_fee
            )
            exit_fee_by_lot[lot_id] = (
                exit_fee_by_lot.get(lot_id, 0.0) + exit_fee
            )
        opened_lot_id = fill.get("opened_lot_id")
        if opened_lot_id is not None:
            opened_lot_id = str(opened_lot_id)
            if opened_lot_id not in lot_by_id:
                raise TheoryPaperError("fill references an unknown opened lot")
            opened_quantity = quantity - closed_in_fill
            if opened_quantity <= 1e-12 or opened_lot_id in opened_quantities:
                raise TheoryPaperError("opened lot fill quantity is invalid or duplicated")
            opened_quantities[opened_lot_id] = opened_quantity
            expected_fill_fee += float(
                lot_by_id[opened_lot_id].get("entry_fee_usdt", 0.0)
            )
        elif not close_enough(closed_in_fill, quantity):
            raise TheoryPaperError("fill quantity is not conserved")
        if not close_enough(expected_fill_fee, fee):
            raise TheoryPaperError("fill fee does not reconcile to entry and exit fees")

    gross_lot_realized = 0.0
    net_lot_realized = 0.0
    for lot_id, lot in lot_by_id.items():
        initial_quantity = float(lot["initial_quantity"])
        current_quantity = float(lot["quantity"])
        closed_quantity = closed_quantities.get(lot_id, 0.0)
        if not close_enough(initial_quantity, current_quantity + closed_quantity):
            raise TheoryPaperError("lot quantity history does not reconcile")
        if lot_id in opened_quantities:
            if not close_enough(initial_quantity, opened_quantities[lot_id]):
                raise TheoryPaperError("opened lot quantity disagrees with its fill")
        elif lot.get("attribution") != "EXOGENOUS":
            raise TheoryPaperError("non-exogenous lot has no opening fill")
        entry_fee = float(lot["entry_fee_usdt"])
        remaining_entry_fee = float(lot["remaining_entry_fee_usdt"])
        if remaining_entry_fee > entry_fee + 1e-8:
            raise TheoryPaperError("lot remaining entry fee exceeds original entry fee")
        if not close_enough(
            float(lot["realized_pnl_usdt"]),
            closed_gross_by_lot.get(lot_id, 0.0),
        ):
            raise TheoryPaperError("lot gross realized PnL disagrees with fills")
        if not close_enough(
            float(lot["net_realized_pnl_usdt"]),
            closed_net_by_lot.get(lot_id, 0.0),
        ):
            raise TheoryPaperError("lot net realized PnL disagrees with fills")
        if not close_enough(
            float(lot["exit_fees_usdt"]),
            exit_fee_by_lot.get(lot_id, 0.0),
        ):
            raise TheoryPaperError("lot exit fees disagree with fills")
        if not close_enough(
            entry_fee - remaining_entry_fee,
            allocated_entry_fee_by_lot.get(lot_id, 0.0),
        ):
            raise TheoryPaperError("lot entry-fee allocation disagrees with fills")
        gross_lot_realized += float(lot["realized_pnl_usdt"])
        net_lot_realized += float(lot["net_realized_pnl_usdt"])

    for kind in ("lot", "order", "fill"):
        counter = counters.get(kind)
        if isinstance(counter, bool) or not isinstance(counter, int) or counter < max_id[kind]:
            raise TheoryPaperError(f"{kind} counter is behind persisted ids")

    initial_equity = finite(
        state.get("initial_equity_usdt"),
        "initial_equity_usdt",
        positive=True,
    )
    gross_realized = finite(state.get("realized_pnl_usdt"), "realized_pnl_usdt")
    fees_paid = finite(
        state.get("fees_paid_usdt"),
        "fees_paid_usdt",
        nonnegative=True,
    )
    cash = finite(state.get("cash_balance_usdt"), "cash_balance_usdt")
    if not close_enough(gross_realized, gross_lot_realized):
        raise TheoryPaperError("state and lot realized PnL disagree")
    if not close_enough(fees_paid, total_fill_fees):
        raise TheoryPaperError("state and fill fees disagree")
    if not close_enough(cash, initial_equity + gross_realized - fees_paid):
        raise TheoryPaperError("cash, realized PnL, and fees do not reconcile")
    daily = state.get("daily_realized_pnl_usdt")
    if not isinstance(daily, Mapping):
        raise TheoryPaperError("daily realized PnL must be an object")
    daily_total = 0.0
    for day, value in daily.items():
        try:
            datetime.fromisoformat(str(day))
        except ValueError as exc:
            raise TheoryPaperError("daily realized PnL date is invalid") from exc
        daily_total += finite(value, f"daily_realized_pnl_usdt.{day}")
    if not close_enough(daily_total, gross_realized):
        raise TheoryPaperError("daily and total realized PnL disagree")
    daily_net = state.get("daily_net_realized_pnl_usdt")
    if not isinstance(daily_net, Mapping):
        raise TheoryPaperError("daily net realized PnL must be an object")
    daily_net_total = 0.0
    for day, value in daily_net.items():
        try:
            datetime.fromisoformat(str(day))
        except ValueError as exc:
            raise TheoryPaperError(
                "daily net realized PnL date is invalid"
            ) from exc
        daily_net_total += finite(
            value,
            f"daily_net_realized_pnl_usdt.{day}",
        )
    if not close_enough(daily_net_total, net_lot_realized):
        raise TheoryPaperError("daily and lot net realized PnL disagree")
    return {
        "valid": True,
        "schema_version": SCHEMA_VERSION,
        "paper_only": True,
        "lot_count": len(lots),
        "order_count": len(orders),
        "fill_count": len(fills),
        "exit_slice_count": exit_slice_count,
    }


def _open_lots(state: Mapping[str, Any], symbol: str | None = None) -> list[dict[str, Any]]:
    return [
        lot
        for lot in state.get("lots", [])
        if isinstance(lot, dict)
        and lot.get("status") == "OPEN"
        and (symbol is None or lot.get("symbol") == symbol)
        and float(lot.get("quantity", 0.0)) > 1e-12
    ]


def _marks_from_market(market: Mapping[str, Any] | None) -> dict[str, float]:
    if not market:
        return {}
    views = _market_views(market)
    return {symbol: view["price"] for symbol, view in views.items() if view.get("price") is not None}


def portfolio_metrics(
    state: Mapping[str, Any],
    marks: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    prices: dict[str, float] = {}
    for symbol, value in (marks or {}).items():
        if isinstance(value, Mapping):
            candidate = value.get("price", value.get("mark_price", value.get("close")))
        else:
            candidate = value
        try:
            if candidate is not None:
                prices[_symbol(symbol)] = _positive(candidate, f"marks.{symbol}")
        except TheoryPaperError:
            continue
    limits = state["risk_limits"]
    unrealized = 0.0
    gross = 0.0
    by_symbol: dict[str, float] = {}
    open_risk = 0.0
    open_cost_to_stop = 0.0
    open_risk_by_symbol: dict[str, float] = {}
    open_cost_to_stop_by_symbol: dict[str, float] = {}
    unprotected: list[str] = []
    for lot in _open_lots(state):
        symbol = lot["symbol"]
        mark = prices.get(symbol, float(lot["entry_price"]))
        quantity = float(lot["quantity"])
        direction = 1.0 if lot["side"] == "LONG" else -1.0
        unrealized += direction * quantity * (mark - float(lot["entry_price"]))
        notional = quantity * mark
        gross += notional
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + notional
        stop = lot.get("stop_price")
        if stop is None or lot.get("target_price") is None:
            unprotected.append(lot["lot_id"])
        else:
            forward_risk, stopped_at = _forward_stop_risk(
                limits,
                str(lot["side"]),
                mark,
                float(stop),
                quantity,
            )
            entry_to_stop = (
                float(lot["entry_price"]) - stopped_at
                if lot["side"] == "LONG"
                else stopped_at - float(lot["entry_price"])
            ) * quantity
            total_cost_to_stop = (
                entry_to_stop
                + float(lot.get("remaining_entry_fee_usdt", 0.0))
                + stopped_at * quantity * float(limits["taker_fee_rate"])
            )
            open_risk += forward_risk
            open_cost_to_stop += total_cost_to_stop
            open_risk_by_symbol[symbol] = (
                open_risk_by_symbol.get(symbol, 0.0) + forward_risk
            )
            open_cost_to_stop_by_symbol[symbol] = (
                open_cost_to_stop_by_symbol.get(symbol, 0.0)
                + total_cost_to_stop
            )
    pending_notional = 0.0
    pending_risk = 0.0
    pending_by_symbol: dict[str, float] = {}
    pending_risk_by_symbol: dict[str, float] = {}
    for order in state.get("orders", []):
        if (
            not isinstance(order, Mapping)
            or order.get("state") != "ACTIVE"
            or order.get("reduce_only") is True
        ):
            continue
        quantity = float(order.get("remaining_quantity", 0.0))
        price = float(order.get("limit_price", 0.0))
        notional = quantity * price
        symbol = str(order.get("symbol"))
        pending_notional += notional
        pending_by_symbol[symbol] = pending_by_symbol.get(symbol, 0.0) + notional
        if order.get("stop_price") is not None and order.get("target_price") is not None:
            try:
                terms = _protection_terms(
                    limits,
                    "LONG" if order.get("side") == "BUY" else "SHORT",
                    price,
                    order["stop_price"],
                    order["target_price"],
                    entry_fee_rate=float(limits["maker_fee_rate"]),
                )
                risk = quantity * float(terms["net_risk_per_unit"])
            except TheoryPaperError:
                # Persisted active orders should already be valid.  If a legacy
                # or externally corrupted row reaches metrics, charge the full
                # pending notional instead of emitting non-canonical infinity.
                risk = notional
            pending_risk += risk
            pending_risk_by_symbol[symbol] = (
                pending_risk_by_symbol.get(symbol, 0.0) + risk
            )
    equity = float(state["cash_balance_usdt"]) + unrealized
    initial = float(state["initial_equity_usdt"])
    peak = max(initial, float(state.get("peak_equity_usdt", initial)), equity)
    drawdown = 0.0 if peak <= 0 else max(0.0, (peak - equity) / peak)
    closed_trade_outcomes: list[dict[str, Any]] = []
    for lot in state.get("lots", []):
        if not isinstance(lot, Mapping) or lot.get("status") != "CLOSED":
            continue
        net_pnl = float(lot.get("net_realized_pnl_usdt", 0.0))
        gross_pnl = float(lot.get("realized_pnl_usdt", 0.0))
        risk = lot.get("initial_net_risk_usdt")
        risk_value = (
            None
            if risk is None or float(risk) <= 0
            else float(risk)
        )
        holding_seconds = max(
            0.0,
            (
                parse_utc(str(lot["closed_at"]))
                - parse_utc(str(lot["opened_at"]))
            ).total_seconds(),
        )
        closed_trade_outcomes.append(
            {
                "lot_id": lot.get("lot_id"),
                "symbol": lot.get("symbol"),
                "side": lot.get("side"),
                "gross_price_pnl_usdt": _round(gross_pnl),
                "net_pnl_usdt": _round(net_pnl),
                "entry_fee_usdt": _round(float(lot.get("entry_fee_usdt", 0.0))),
                "exit_fees_usdt": _round(float(lot.get("exit_fees_usdt", 0.0))),
                "initial_net_risk_usdt": (
                    None if risk_value is None else _round(risk_value)
                ),
                "r_multiple": (
                    None
                    if risk_value is None
                    else _round(net_pnl / risk_value, 6)
                ),
                "holding_seconds": _round(holding_seconds, 3),
            }
        )
    realized_outcomes = [
        float(item["net_pnl_usdt"]) for item in closed_trade_outcomes
    ]
    gross_price_outcomes = [
        float(item["gross_price_pnl_usdt"]) for item in closed_trade_outcomes
    ]
    wins = [value for value in realized_outcomes if value > 1e-12]
    losses = [value for value in realized_outcomes if value < -1e-12]
    breakeven = [
        value for value in realized_outcomes if abs(value) <= 1e-12
    ]
    net_profit = sum(wins)
    net_loss = -sum(losses)
    gross_price_profit = sum(value for value in gross_price_outcomes if value > 0)
    gross_price_loss = -sum(value for value in gross_price_outcomes if value < 0)
    average_win = sum(wins) / len(wins) if wins else None
    average_loss = net_loss / len(losses) if losses else None
    r_values = [
        float(item["r_multiple"])
        for item in closed_trade_outcomes
        if item.get("r_multiple") is not None
    ]
    holding_values = [
        float(item["holding_seconds"]) for item in closed_trade_outcomes
    ]
    attribution: dict[str, dict[str, float | int]] = {}
    for fill in state.get("fills", []):
        if not isinstance(fill, Mapping):
            continue
        key = str(fill.get("attribution") or "UNKNOWN")
        row = attribution.setdefault(
            key,
            {
                "fill_count": 0,
                "notional_usdt": 0.0,
                "fees_usdt": 0.0,
                "estimated_slippage_cost_usdt": 0.0,
                "realized_pnl_usdt": 0.0,
                "net_realized_pnl_usdt": 0.0,
            },
        )
        row["fill_count"] = int(row["fill_count"]) + 1
        row["notional_usdt"] = float(row["notional_usdt"]) + float(fill.get("notional_usdt", 0.0))
        row["fees_usdt"] = float(row["fees_usdt"]) + float(fill.get("fee_usdt", 0.0))
        row["estimated_slippage_cost_usdt"] = float(
            row["estimated_slippage_cost_usdt"]
        ) + float(fill.get("estimated_slippage_cost_usdt", 0.0))
        row["realized_pnl_usdt"] = float(row["realized_pnl_usdt"]) + sum(
            float(item.get("realized_pnl_usdt", 0.0))
            for item in fill.get("closed_lots", [])
            if isinstance(item, Mapping)
        )
        row["net_realized_pnl_usdt"] = float(
            row["net_realized_pnl_usdt"]
        ) + sum(
            float(item.get("net_realized_pnl_usdt", 0.0))
            for item in fill.get("closed_lots", [])
            if isinstance(item, Mapping)
        )
    excursion_lots = [
        lot for lot in state.get("lots", []) if isinstance(lot, Mapping)
    ]
    net_realized = sum(
        float(lot.get("net_realized_pnl_usdt", 0.0))
        for lot in state.get("lots", [])
        if isinstance(lot, Mapping)
    )
    return {
        "equity_usdt": _round(equity),
        "total_net_pnl_usdt": _round(equity - initial),
        "cash_balance_usdt": _round(float(state["cash_balance_usdt"])),
        "realized_pnl_usdt": _round(float(state["realized_pnl_usdt"])),
        "gross_realized_pnl_usdt": _round(float(state["realized_pnl_usdt"])),
        "net_realized_pnl_usdt": _round(net_realized),
        "daily_net_realized_pnl_usdt": {
            str(day): _round(float(value))
            for day, value in sorted(
                state.get("daily_net_realized_pnl_usdt", {}).items()
            )
        },
        "unrealized_pnl_usdt": _round(unrealized),
        "fees_paid_usdt": _round(float(state["fees_paid_usdt"])),
        "gross_notional_usdt": _round(gross),
        "pending_new_risk_notional_usdt": _round(pending_notional),
        "gross_plus_pending_notional_usdt": _round(gross + pending_notional),
        "gross_leverage": _round(0.0 if equity <= 0 else gross / equity),
        "symbol_notional_usdt": {key: _round(value) for key, value in sorted(by_symbol.items())},
        "pending_symbol_notional_usdt": {key: _round(value) for key, value in sorted(pending_by_symbol.items())},
        "open_risk_usdt": _round(open_risk),
        "open_cost_to_stop_usdt": _round(open_cost_to_stop),
        "open_symbol_risk_usdt": {
            key: _round(value) for key, value in sorted(open_risk_by_symbol.items())
        },
        "open_symbol_cost_to_stop_usdt": {
            key: _round(value)
            for key, value in sorted(open_cost_to_stop_by_symbol.items())
        },
        "pending_risk_usdt": _round(pending_risk),
        "open_pending_risk_usdt": _round(open_risk + pending_risk),
        "pending_symbol_risk_usdt": {key: _round(value) for key, value in sorted(pending_risk_by_symbol.items())},
        "unprotected_lot_ids": sorted(unprotected),
        "drawdown_fraction": _round(drawdown),
        "peak_equity_usdt": _round(peak),
        "closed_trade_count": len(realized_outcomes),
        "winning_trade_count": len(wins),
        "losing_trade_count": len(losses),
        "breakeven_trade_count": len(breakeven),
        "win_rate": None if not realized_outcomes else _round(len(wins) / len(realized_outcomes), 6),
        "net_profit_usdt": _round(net_profit),
        "net_loss_usdt": _round(net_loss),
        "gross_price_profit_usdt": _round(gross_price_profit),
        "gross_price_loss_usdt": _round(gross_price_loss),
        "gross_profit_usdt": _round(gross_price_profit),
        "gross_loss_usdt": _round(gross_price_loss),
        "profit_factor": None if net_loss <= 0 else _round(net_profit / net_loss, 6),
        "average_win_usdt": None if average_win is None else _round(average_win),
        "average_loss_usdt": None if average_loss is None else _round(average_loss),
        "payoff_ratio": (
            None
            if average_win is None or average_loss in (None, 0)
            else _round(average_win / average_loss, 6)
        ),
        "average_r_multiple": (
            None if not r_values else _round(sum(r_values) / len(r_values), 6)
        ),
        "total_r_multiple": (
            None if not r_values else _round(sum(r_values), 6)
        ),
        "average_holding_seconds": (
            None
            if not holding_values
            else _round(sum(holding_values) / len(holding_values), 3)
        ),
        "closed_trade_outcomes": closed_trade_outcomes,
        "exit_slice_count": sum(
            1
            for fill in state.get("fills", [])
            if isinstance(fill, Mapping)
            for item in fill.get("closed_lots", [])
            if isinstance(item, Mapping)
        ),
        "average_mfe_usdt": (
            None
            if not excursion_lots
            else _round(
                sum(float(lot.get("mfe_usdt", 0.0)) for lot in excursion_lots)
                / len(excursion_lots)
            )
        ),
        "average_mae_usdt": (
            None
            if not excursion_lots
            else _round(
                sum(float(lot.get("mae_usdt", 0.0)) for lot in excursion_lots)
                / len(excursion_lots)
            )
        ),
        "attribution": {
            key: {
                field: (
                    int(value)
                    if field == "fill_count"
                    else _round(float(value))
                )
                for field, value in row.items()
            }
            for key, row in sorted(attribution.items())
        },
        "funding_accrual_status": "NOT_SIMULATED_V0_1",
        "risk_measurement_boundary": (
            "OPEN_RISK_IS_MARK_TO_ASSUMED_STOP_FILL_PLUS_EXIT_FEE; "
            "OPEN_COST_TO_STOP_INCLUDES_ENTRY_TO_STOP_PRICE_RESULT_REMAINING_"
            "ENTRY_FEE_AND_EXIT_FEE"
        ),
        "performance_measurement_boundary": (
            "WIN_RATE_PROFIT_FACTOR_AND_R_USE_FULLY_CLOSED_LOT_NET_PNL_AFTER_"
            "ALLOCATED_ENTRY_AND_EXIT_FEES; PARTIAL_EXITS_ARE_EXIT_SLICES"
        ),
    }


def _refresh_risk_state(state: MutableMapping[str, Any], marks: Mapping[str, Any]) -> dict[str, Any]:
    metrics = portfolio_metrics(state, marks)
    state["peak_equity_usdt"] = metrics["peak_equity_usdt"]
    limits = state["risk_limits"]
    reasons: list[str] = []
    if metrics["unprotected_lot_ids"]:
        reasons.append("UNPROTECTED_OPEN_LOTS")
    if metrics["drawdown_fraction"] >= float(limits["max_drawdown_fraction"]):
        reasons.append("MAX_DRAWDOWN_REACHED")
    equity = float(metrics["equity_usdt"])
    if float(metrics["gross_plus_pending_notional_usdt"]) > equity * float(limits["max_gross_leverage"]) + 1e-8:
        reasons.append("MAX_GROSS_NOTIONAL")
    if float(metrics["open_pending_risk_usdt"]) > equity * float(limits["max_portfolio_risk_equity_fraction"]) + 1e-8:
        reasons.append("MAX_PORTFOLIO_OPEN_RISK")
    today = parse_utc(str(state.get("updated_at", state["activated_at"]))).date().isoformat()
    daily_realized = float(
        state.get("daily_net_realized_pnl_usdt", {}).get(today, 0.0)
    )
    if daily_realized <= -float(state["initial_equity_usdt"]) * float(limits["daily_realized_loss_fraction"]):
        reasons.append("DAILY_REALIZED_LOSS_LIMIT")
    if metrics["equity_usdt"] <= 0:
        reasons.append("NONPOSITIVE_EQUITY")
    state["risk_state"] = {
        "new_risk_allowed": not reasons,
        "reasons": reasons,
        "metrics": metrics,
    }
    return metrics


def _protection_error(
    state: Mapping[str, Any],
    side: str,
    entry: float,
    stop: Any,
    target: Any,
    minimum_rr: float,
    *,
    entry_fee_kind: str,
) -> tuple[str | None, dict[str, Any] | None]:
    if stop is None or target is None:
        return "NEW_RISK_REQUIRES_STOP_AND_TARGET", None
    try:
        terms = _protection_terms(
            state["risk_limits"],
            side,
            entry,
            stop,
            target,
            entry_fee_rate=_fee(state, entry_fee_kind),
        )
    except TheoryPaperError as exc:
        return str(exc), None
    if float(terms["net_reward_risk"]) + 1e-12 < minimum_rr:
        return "MINIMUM_NET_REWARD_RISK_NOT_MET", terms
    return None, terms


def _new_risk_reasons(
    state: MutableMapping[str, Any],
    *,
    symbol: str,
    position_side: str,
    quantity: float,
    entry_price: float,
    stop_price: Any,
    target_price: Any,
    authorization: Mapping[str, Any],
    hypothesis_id: Any,
    attribution: str,
    marks: Mapping[str, float],
    risk_fraction_cap: float | None = None,
    entry_fee_kind: str = "TAKER",
) -> tuple[list[str], dict[str, Any] | None]:
    limits = state["risk_limits"]
    reasons: list[str] = []
    if authorization.get("approved") is not True:
        reasons.append("NEW_RISK_NOT_AUTHORIZED")
    if attribution == "STRATEGY" and not str(hypothesis_id or "").strip():
        reasons.append("NEW_RISK_REQUIRES_HYPOTHESIS")
    error, protection_terms = _protection_error(
        state,
        position_side,
        entry_price,
        stop_price,
        target_price,
        float(limits["minimum_reward_risk"]),
        entry_fee_kind=entry_fee_kind,
    )
    if error:
        reasons.append(error)
    metrics = _refresh_risk_state(state, marks)
    if metrics["unprotected_lot_ids"]:
        reasons.append("EXISTING_UNPROTECTED_LOTS")
    equity = float(metrics["equity_usdt"])
    if metrics["drawdown_fraction"] >= float(limits["max_drawdown_fraction"]):
        reasons.append("MAX_DRAWDOWN_REACHED")
    today = parse_utc(str(state.get("updated_at", state["activated_at"]))).date().isoformat()
    daily_realized = float(
        state.get("daily_net_realized_pnl_usdt", {}).get(today, 0.0)
    )
    if daily_realized <= -float(state["initial_equity_usdt"]) * float(limits["daily_realized_loss_fraction"]):
        reasons.append("DAILY_REALIZED_LOSS_LIMIT")
    added_notional = quantity * entry_price
    max_gross = equity * float(limits["max_gross_leverage"])
    if float(metrics["gross_plus_pending_notional_usdt"]) + added_notional > max_gross + 1e-8:
        reasons.append("MAX_GROSS_NOTIONAL")
    projected_symbol = (
        float(metrics["symbol_notional_usdt"].get(symbol, 0.0))
        + float(metrics["pending_symbol_notional_usdt"].get(symbol, 0.0))
        + added_notional
    )
    if projected_symbol > equity * float(limits["max_symbol_equity_fraction"]) + 1e-8:
        reasons.append("MAX_SYMBOL_NOTIONAL")
    if protection_terms is not None:
        trade_risk = quantity * float(protection_terms["net_risk_per_unit"])
        trade_risk_fraction = float(limits["max_trade_risk_equity_fraction"])
        if risk_fraction_cap is not None:
            trade_risk_fraction = min(
                trade_risk_fraction,
                _positive(risk_fraction_cap, "risk_fraction_cap"),
            )
        if trade_risk > equity * trade_risk_fraction + 1e-8:
            reasons.append("MAX_TRADE_RISK")
        if float(metrics["open_pending_risk_usdt"]) + trade_risk > equity * float(limits["max_portfolio_risk_equity_fraction"]) + 1e-8:
            reasons.append("MAX_PORTFOLIO_OPEN_RISK")
        symbol_open_risk = float(
            metrics["open_symbol_risk_usdt"].get(symbol, 0.0)
        )
        symbol_pending_risk = float(metrics["pending_symbol_risk_usdt"].get(symbol, 0.0))
        if symbol_open_risk + symbol_pending_risk + trade_risk > equity * float(limits["max_symbol_open_risk_equity_fraction"]) + 1e-8:
            reasons.append("MAX_SYMBOL_OPEN_RISK")
    return sorted(set(reasons)), protection_terms


def _market_views(market: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    views: dict[str, dict[str, Any]] = {}
    rows = market.get("symbols") if isinstance(market, Mapping) else None
    if isinstance(rows, list):
        iterable: Iterable[tuple[str, Mapping[str, Any]]] = (
            (str(row.get("symbol")), row) for row in rows if isinstance(row, Mapping)
        )
        snapshot_observed = market.get("observed_at")
    else:
        iterable = (
            (str(key), value)
            for key, value in market.items()
            if isinstance(value, Mapping) and str(key).upper().endswith("USDT")
        )
        snapshot_observed = market.get("observed_at") if isinstance(market, Mapping) else None
    for raw_symbol, row in iterable:
        try:
            symbol = _symbol(raw_symbol or row.get("symbol"))
        except TheoryPaperError:
            continue
        measures = row.get("measures") if isinstance(row.get("measures"), Mapping) else row
        price = measures.get("price", row.get("price"))
        timeframes = measures.get("timeframes", {})
        hourly = timeframes.get("1h", {}) if isinstance(timeframes, Mapping) else {}
        bar = hourly.get("last_closed_bar") if isinstance(hourly, Mapping) else None
        if not isinstance(bar, Mapping):
            candidate = row.get("bar", row.get("last_closed_bar"))
            bar = candidate if isinstance(candidate, Mapping) else row
        try:
            parsed_price = _positive(price if price is not None else bar.get("close"), f"{symbol}.price")
        except TheoryPaperError:
            continue
        normalized_bar: dict[str, Any] | None = None
        if all(key in bar for key in ("open", "high", "low", "close")):
            try:
                normalized_bar = {
                    "open": _positive(bar["open"], f"{symbol}.bar.open"),
                    "high": _positive(bar["high"], f"{symbol}.bar.high"),
                    "low": _positive(bar["low"], f"{symbol}.bar.low"),
                    "close": _positive(bar["close"], f"{symbol}.bar.close"),
                    "close_time": None if bar.get("close_time") is None else int(float(bar["close_time"])),
                }
            except (TheoryPaperError, TypeError, ValueError):
                normalized_bar = None
        views[symbol] = {
            "price": parsed_price,
            "bar": normalized_bar,
            "observed_at": row.get("observed_at", snapshot_observed),
        }
    return views


def _fee(state: Mapping[str, Any], kind: str) -> float:
    return float(state["risk_limits"]["maker_fee_rate" if kind == "MAKER" else "taker_fee_rate"])


def _slipped_price(reference: float, side: str, bps: float) -> float:
    multiplier = 1.0 + (bps / 10000.0 if side == "BUY" else -bps / 10000.0)
    return _round(reference * multiplier)


def _record_fill(
    state: MutableMapping[str, Any],
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    fee_rate: float,
    observed_at: str,
    reason: str,
    attribution: str,
    origin: str,
    hypothesis_id: Any,
    order_id: str | None,
    ambiguous: bool,
    closed_lots: Sequence[Mapping[str, Any]],
    opened_lot_id: str | None,
    rejected_excess_quantity: float,
    same_bar_entry_and_exit: bool = False,
) -> dict[str, Any]:
    notional = quantity * price
    fee_value = notional * fee_rate
    slippage_bps = (
        float(state["risk_limits"]["stop_slippage_bps"])
        if reason == "STOP"
        else (
            float(state["risk_limits"]["market_slippage_bps"])
            if reason == "MARKET"
            else 0.0
        )
    )
    state["fees_paid_usdt"] = _round(float(state["fees_paid_usdt"]) + fee_value)
    state["cash_balance_usdt"] = _round(float(state["cash_balance_usdt"]) - fee_value)
    fill = {
        "fill_id": _counter_id(state, "fill"),
        "observed_at": observed_at,
        "symbol": symbol,
        "side": side,
        "quantity": _round(quantity, 12),
        "price": _round(price),
        "notional_usdt": _round(notional),
        "fee_usdt": _round(fee_value),
        "slippage_bps_assumption": _round(slippage_bps, 6),
        "estimated_slippage_cost_usdt": _round(notional * slippage_bps / 10000.0),
        "reason": reason,
        "attribution": attribution,
        "origin": origin,
        "hypothesis_id": hypothesis_id,
        "order_id": order_id,
        "ambiguous_same_bar": bool(ambiguous),
        "same_bar_entry_and_exit": bool(same_bar_entry_and_exit),
        "barrier_precedence": "STOP_FIRST" if ambiguous else None,
        "closed_lots": [dict(value) for value in closed_lots],
        "opened_lot_id": opened_lot_id,
        "rejected_excess_quantity": _round(rejected_excess_quantity, 12),
    }
    state["fills"].append(fill)
    return fill


def _book_realized_pnl(state: MutableMapping[str, Any], value: float, observed_at: str) -> None:
    if abs(value) <= 1e-15:
        return
    state["realized_pnl_usdt"] = _round(float(state["realized_pnl_usdt"]) + value)
    state["cash_balance_usdt"] = _round(float(state["cash_balance_usdt"]) + value)
    day = parse_utc(observed_at).date().isoformat()
    daily = state.setdefault("daily_realized_pnl_usdt", {})
    daily[day] = _round(float(daily.get(day, 0.0)) + value)


def _book_net_realized_pnl(
    state: MutableMapping[str, Any],
    value: float,
    observed_at: str,
) -> None:
    if abs(value) <= 1e-15:
        return
    day = parse_utc(observed_at).date().isoformat()
    daily = state.setdefault("daily_net_realized_pnl_usdt", {})
    daily[day] = _round(float(daily.get(day, 0.0)) + value)


def _apply_lot_close_accounting(
    state: MutableMapping[str, Any],
    lot: MutableMapping[str, Any],
    *,
    closed_quantity: float,
    price: float,
    observed_at: str,
    exit_fee_rate: float,
) -> dict[str, Any]:
    before_quantity = float(lot["quantity"])
    if closed_quantity <= 0 or closed_quantity > before_quantity + 1e-12:
        raise TheoryPaperError("closed lot quantity is invalid")
    direction = 1.0 if lot["side"] == "LONG" else -1.0
    gross_pnl = (
        direction
        * closed_quantity
        * (float(price) - float(lot["entry_price"]))
    )
    remaining_entry_fee = float(lot.get("remaining_entry_fee_usdt", 0.0))
    if closed_quantity >= before_quantity - 1e-12:
        allocated_entry_fee = remaining_entry_fee
    else:
        allocated_entry_fee = remaining_entry_fee * (
            closed_quantity / before_quantity
        )
    exit_fee = closed_quantity * float(price) * float(exit_fee_rate)
    net_pnl = gross_pnl - allocated_entry_fee - exit_fee
    initial_quantity = float(lot["initial_quantity"])
    initial_net_risk = lot.get("initial_net_risk_usdt")
    allocated_risk = (
        None
        if initial_net_risk is None
        else float(initial_net_risk) * closed_quantity / initial_quantity
    )
    holding_seconds = max(
        0.0,
        (
            parse_utc(observed_at) - parse_utc(str(lot["opened_at"]))
        ).total_seconds(),
    )

    lot["quantity"] = _round(before_quantity - closed_quantity, 12)
    lot["realized_pnl_usdt"] = _round(
        float(lot["realized_pnl_usdt"]) + gross_pnl
    )
    lot["net_realized_pnl_usdt"] = _round(
        float(lot.get("net_realized_pnl_usdt", 0.0)) + net_pnl
    )
    lot["remaining_entry_fee_usdt"] = _round(
        max(0.0, remaining_entry_fee - allocated_entry_fee)
    )
    lot["exit_fees_usdt"] = _round(
        float(lot.get("exit_fees_usdt", 0.0)) + exit_fee
    )
    if float(lot["quantity"]) <= 1e-12:
        lot["quantity"] = 0.0
        lot["remaining_entry_fee_usdt"] = 0.0
        lot["status"] = "CLOSED"
        lot["closed_at"] = observed_at
    _book_realized_pnl(state, gross_pnl, observed_at)
    _book_net_realized_pnl(state, net_pnl, observed_at)
    return {
        "lot_id": lot["lot_id"],
        "quantity": _round(closed_quantity, 12),
        "realized_pnl_usdt": _round(gross_pnl),
        "allocated_entry_fee_usdt": _round(allocated_entry_fee),
        "exit_fee_usdt": _round(exit_fee),
        "net_realized_pnl_usdt": _round(net_pnl),
        "allocated_initial_net_risk_usdt": (
            None if allocated_risk is None else _round(allocated_risk)
        ),
        "r_multiple": (
            None
            if allocated_risk is None or allocated_risk <= 0
            else _round(net_pnl / allocated_risk, 6)
        ),
        "holding_seconds": _round(holding_seconds, 3),
    }


def _execute_quantity(
    state: MutableMapping[str, Any],
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    observed_at: str,
    reason: str,
    attribution: str,
    origin: str,
    hypothesis_id: Any = None,
    stop_price: Any = None,
    target_price: Any = None,
    authorization: Mapping[str, Any] | None = None,
    allow_new_risk: bool = False,
    reduce_only: bool = False,
    fee_kind: str = "TAKER",
    order_id: str | None = None,
    ambiguous: bool = False,
    marks: Mapping[str, float] | None = None,
    risk_fraction_cap: float | None = None,
) -> dict[str, Any]:
    position_side = "LONG" if side == "BUY" else "SHORT"
    opposite = "SHORT" if position_side == "LONG" else "LONG"
    remaining = quantity
    closed: list[dict[str, Any]] = []
    for lot in sorted(_open_lots(state, symbol), key=lambda value: (value["opened_at"], value["lot_id"])):
        if lot["side"] != opposite or remaining <= 1e-12:
            continue
        closed_quantity = min(remaining, float(lot["quantity"]))
        closed.append(
            _apply_lot_close_accounting(
                state,
                lot,
                closed_quantity=closed_quantity,
                price=price,
                observed_at=observed_at,
                exit_fee_rate=_fee(state, fee_kind),
            )
        )
        remaining -= closed_quantity

    rejected_reasons: list[str] = []
    opened_lot_id: str | None = None
    opening_quantity = 0.0
    if remaining > 1e-12 and not reduce_only:
        if not allow_new_risk:
            rejected_reasons.append("REVERSAL_EXCESS_NOT_AUTHORIZED")
        else:
            auth = authorization or {"approved": False}
            rejected_reasons, protection_terms = _new_risk_reasons(
                state,
                symbol=symbol,
                position_side=position_side,
                quantity=remaining,
                entry_price=price,
                stop_price=stop_price,
                target_price=target_price,
                authorization=auth,
                hypothesis_id=hypothesis_id,
                attribution=attribution,
                marks=dict(marks or {}),
                risk_fraction_cap=risk_fraction_cap,
                entry_fee_kind=fee_kind,
            )
            if not rejected_reasons:
                if protection_terms is None:
                    raise TheoryPaperError("new-risk protection terms are missing")
                entry_fee = remaining * price * _fee(state, fee_kind)
                lot = {
                    "lot_id": _counter_id(state, "lot"),
                    "symbol": symbol,
                    "side": position_side,
                    "quantity": _round(remaining, 12),
                    "initial_quantity": _round(remaining, 12),
                    "entry_price": _round(price),
                    "entry_notional_usdt": _round(remaining * price),
                    "entry_fee_usdt": _round(entry_fee),
                    "remaining_entry_fee_usdt": _round(entry_fee),
                    "exit_fees_usdt": 0.0,
                    "opened_at": observed_at,
                    "origin": origin,
                    "attribution": attribution,
                    "hypothesis_id": hypothesis_id,
                    "stop_price": _round(float(stop_price)),
                    "target_price": _round(float(target_price)),
                    "protection_activated_at": observed_at,
                    "initial_stop_price": _round(float(stop_price)),
                    "initial_net_risk_usdt": _round(
                        remaining
                        * float(protection_terms["net_risk_per_unit"])
                    ),
                    "entry_reward_risk": protection_terms[
                        "net_reward_risk"
                    ],
                    "entry_reward_risk_gross": protection_terms[
                        "gross_reward_risk"
                    ],
                    "entry_reward_risk_net": protection_terms[
                        "net_reward_risk"
                    ],
                    "entry_cost_assumptions": protection_terms["assumptions"],
                    "current_protection_terms": protection_terms,
                    "legacy_protection_grace_through_cycle": None,
                    "mfe_usdt": 0.0,
                    "mae_usdt": 0.0,
                    "risk_authorization": dict(auth),
                    "probe": risk_fraction_cap is not None,
                    "status": "OPEN",
                    "closed_at": None,
                    "realized_pnl_usdt": 0.0,
                    "net_realized_pnl_usdt": 0.0,
                }
                state["lots"].append(lot)
                opened_lot_id = lot["lot_id"]
                opening_quantity = remaining
                remaining = 0.0
    if remaining > 1e-12 and reduce_only:
        rejected_reasons.append("REDUCE_ONLY_REMAINDER_CANCELED")
    executed_quantity = quantity - remaining
    fill = None
    if executed_quantity > 1e-12:
        fill = _record_fill(
            state,
            symbol=symbol,
            side=side,
            quantity=executed_quantity,
            price=price,
            fee_rate=_fee(state, fee_kind),
            observed_at=observed_at,
            reason=reason,
            attribution=attribution,
            origin=origin,
            hypothesis_id=hypothesis_id,
            order_id=order_id,
            ambiguous=ambiguous,
            closed_lots=closed,
            opened_lot_id=opened_lot_id,
            rejected_excess_quantity=remaining,
        )
    if remaining <= 1e-12:
        status = "FILLED"
    elif executed_quantity > 1e-12 and reduce_only:
        status = "PARTIALLY_FILLED_REDUCE_ONLY"
    elif executed_quantity > 1e-12:
        status = "PARTIALLY_FILLED_RISK_BLOCKED"
    else:
        status = "REDUCE_ONLY_CANCELED" if reduce_only else "RISK_REJECTED"
    return {
        "status": status,
        "fill": fill,
        "closed_quantity": _round(executed_quantity - opening_quantity, 12),
        "opened_quantity": _round(opening_quantity, 12),
        "rejected_quantity": _round(remaining, 12),
        "rejection_reasons": sorted(set(rejected_reasons)),
    }


def _close_specific_lot(
    state: MutableMapping[str, Any],
    lot: MutableMapping[str, Any],
    *,
    price: float,
    observed_at: str,
    reason: str,
    ambiguous: bool,
    same_bar_entry_and_exit: bool = False,
) -> dict[str, Any]:
    quantity = float(lot["quantity"])
    side = "SELL" if lot["side"] == "LONG" else "BUY"
    fee_kind = "TAKER" if reason == "STOP" else "MAKER"
    closed = _apply_lot_close_accounting(
        state,
        lot,
        closed_quantity=quantity,
        price=price,
        observed_at=observed_at,
        exit_fee_rate=_fee(state, fee_kind),
    )
    fill = _record_fill(
        state,
        symbol=lot["symbol"],
        side=side,
        quantity=quantity,
        price=price,
        fee_rate=_fee(state, fee_kind),
        observed_at=observed_at,
        reason=reason,
        attribution=lot["attribution"],
        origin="PROTECTIVE_EXIT",
        hypothesis_id=lot.get("hypothesis_id"),
        order_id=None,
        ambiguous=ambiguous,
        closed_lots=[closed],
        opened_lot_id=None,
        rejected_excess_quantity=0.0,
        same_bar_entry_and_exit=same_bar_entry_and_exit,
    )
    return {"status": "FILLED", "fill": fill}


def _resolve_lot_barrier_on_bar(
    state: MutableMapping[str, Any],
    lot: MutableMapping[str, Any],
    bar: Mapping[str, Any],
    *,
    observed_at: str,
    close_time: int,
    allow_activation_bar: bool,
) -> dict[str, Any] | None:
    quantity = float(lot["quantity"])
    entry = float(lot["entry_price"])
    if lot["side"] == "LONG":
        favorable = quantity * (float(bar["high"]) - entry)
        adverse_loss = quantity * (entry - float(bar["low"]))
    else:
        favorable = quantity * (entry - float(bar["low"]))
        adverse_loss = quantity * (float(bar["high"]) - entry)
    lot["mfe_usdt"] = _round(
        max(float(lot.get("mfe_usdt", 0.0)), favorable, 0.0)
    )
    lot["mae_usdt"] = _round(
        max(float(lot.get("mae_usdt", 0.0)), adverse_loss, 0.0)
    )
    if lot.get("stop_price") is None or lot.get("target_price") is None:
        return None
    protected_at = lot.get("protection_activated_at")
    if (
        not allow_activation_bar
        and protected_at
        and close_time <= _epoch_ms(str(protected_at))
    ):
        return None
    stop = float(lot["stop_price"])
    target = float(lot["target_price"])
    if lot["side"] == "LONG":
        stop_hit = float(bar["low"]) <= stop
        target_hit = float(bar["high"]) >= target
    else:
        stop_hit = float(bar["high"]) >= stop
        target_hit = float(bar["low"]) <= target
    if not stop_hit and not target_hit:
        return None
    ambiguous = stop_hit and target_hit
    reason = "STOP" if stop_hit else "TARGET"
    reference = stop if stop_hit else target
    if stop_hit:
        if lot["side"] == "LONG":
            reference = min(reference, float(bar["open"]))
        else:
            reference = max(reference, float(bar["open"]))
        exit_side = "SELL" if lot["side"] == "LONG" else "BUY"
        price = _slipped_price(
            reference,
            exit_side,
            float(state["risk_limits"]["stop_slippage_bps"]),
        )
    else:
        price = _round(reference)
    result = _close_specific_lot(
        state,
        lot,
        price=price,
        observed_at=observed_at,
        reason=reason,
        ambiguous=ambiguous,
        same_bar_entry_and_exit=allow_activation_bar,
    )
    result["same_bar_entry_and_exit"] = bool(allow_activation_bar)
    return result


def process_market_bars(
    state: MutableMapping[str, Any],
    market: Mapping[str, Any],
    observed_at: str | datetime | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one set of closed 1h bars without replaying pre-activation data."""

    validate_portfolio_state(state)
    views = _market_views(market)
    now = _time(observed_at or market.get("observed_at"))
    state["cycle_count"] = int(state.get("cycle_count", 0)) + 1
    fills: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    activation_ms = _epoch_ms(state["activated_at"])
    for symbol in sorted(views):
        view = views[symbol]
        bar = view.get("bar")
        if not isinstance(bar, Mapping) or bar.get("close_time") is None:
            skipped.append({"symbol": symbol, "reason": "NO_CLOSED_1H_BAR"})
            continue
        close_time = int(bar["close_time"])
        available_ms = _epoch_ms(now)
        if view.get("observed_at"):
            try:
                available_ms = min(available_ms, _epoch_ms(str(view["observed_at"])))
            except TheoryPaperError:
                skipped.append({"symbol": symbol, "reason": "INVALID_MARKET_OBSERVED_AT"})
                continue
        if close_time > available_ms:
            skipped.append({"symbol": symbol, "reason": "BAR_NOT_AVAILABLE_AT_OBSERVATION"})
            continue
        if close_time <= activation_ms:
            skipped.append({"symbol": symbol, "reason": "BAR_NOT_AFTER_PORTFOLIO_ACTIVATION"})
            continue
        prior = int(state["last_processed_close_time_ms"].get(symbol, 0))
        if close_time <= prior:
            skipped.append({"symbol": symbol, "reason": "BAR_ALREADY_PROCESSED"})
            continue
        state["last_processed_close_time_ms"][symbol] = close_time

        # Existing protective barriers are resolved first.  If both are visible
        # in one aggregate bar, the adverse stop is selected and flagged.
        for lot in list(_open_lots(state, symbol)):
            result = _resolve_lot_barrier_on_bar(
                state,
                lot,
                observed_at=now,
                bar=bar,
                close_time=close_time,
                allow_activation_bar=False,
            )
            if result is not None:
                fills.append(result["fill"])

        for order in state["orders"]:
            if order.get("symbol") != symbol or order.get("state") != "ACTIVE":
                continue
            order_activation = order.get("activated_at")
            if not order_activation or close_time <= _epoch_ms(order_activation):
                continue
            trigger = (
                order["side"] == "BUY" and float(bar["low"]) <= float(order["limit_price"])
            ) or (
                order["side"] == "SELL" and float(bar["high"]) >= float(order["limit_price"])
            )
            if not trigger:
                continue
            order["state"] = "TRIGGERING"
            result = _execute_quantity(
                state,
                symbol=symbol,
                side=order["side"],
                quantity=float(order["remaining_quantity"]),
                price=float(order["limit_price"]),
                observed_at=now,
                reason="LIMIT",
                attribution=order["attribution"],
                origin=order["origin"],
                hypothesis_id=order.get("hypothesis_id"),
                stop_price=order.get("stop_price"),
                target_price=order.get("target_price"),
                authorization=order.get("risk_authorization"),
                allow_new_risk=bool(order.get("allow_reverse")),
                reduce_only=bool(order.get("reduce_only")),
                fee_kind="MAKER",
                order_id=order["order_id"],
                marks={key: value["price"] for key, value in views.items()},
                risk_fraction_cap=(
                    float(state["risk_limits"]["exploration_probe_risk_fraction"])
                    if order.get("probe") is True
                    else None
                ),
            )
            if result["fill"]:
                fills.append(result["fill"])
                order["remaining_quantity"] = _round(result["rejected_quantity"], 12)
                opened_lot_id = result.get("fill", {}).get("opened_lot_id")
                if opened_lot_id is not None:
                    opened_lot = next(
                        (
                            lot
                            for lot in _open_lots(state, symbol)
                            if lot.get("lot_id") == opened_lot_id
                        ),
                        None,
                    )
                    if opened_lot is not None:
                        protective = _resolve_lot_barrier_on_bar(
                            state,
                            opened_lot,
                            bar,
                            observed_at=now,
                            close_time=close_time,
                            allow_activation_bar=True,
                        )
                        if protective is not None:
                            fills.append(protective["fill"])
            if result["status"] == "FILLED":
                order["state"] = "FILLED"
                order["remaining_quantity"] = 0.0
            elif result["status"] == "PARTIALLY_FILLED_REDUCE_ONLY":
                order["state"] = "PARTIALLY_FILLED_REDUCE_ONLY_CANCELED"
                order["remaining_quantity"] = 0.0
                order["cancel_reason"] = "REDUCE_ONLY_REMAINDER_CANCELED"
            elif result["status"] == "PARTIALLY_FILLED_RISK_BLOCKED":
                order["state"] = "PARTIALLY_FILLED_RISK_BLOCKED"
                order["risk_rejection_reasons"] = result["rejection_reasons"]
            else:
                order["state"] = "RISK_REJECTED_AT_TRIGGER"
                order["risk_rejection_reasons"] = result["rejection_reasons"]
    marks = {symbol: view["price"] for symbol, view in views.items()}
    state["updated_at"] = now
    metrics = _refresh_risk_state(state, marks)
    validate_portfolio_state(state)
    return {
        "observed_at": now,
        "cycle_count": state["cycle_count"],
        "fills": fills,
        "skipped": skipped,
        "metrics": metrics,
        "sequence_assumption": "EXISTING_PROTECTIVE_BARRIERS_THEN_PREVIOUSLY_ACTIVE_LIMITS",
        "same_bar_policy": "STOP_FIRST_AND_AMBIGUOUS_TRUE",
    }


def _find_order(state: Mapping[str, Any], order_id: Any) -> dict[str, Any]:
    matches = [order for order in state.get("orders", []) if order.get("order_id") == order_id]
    if len(matches) != 1:
        raise TheoryPaperError("order_id does not identify exactly one order")
    return matches[0]


def _update_protection(
    state: MutableMapping[str, Any],
    action: Mapping[str, Any],
    views: Mapping[str, Mapping[str, Any]],
    now: str,
) -> dict[str, Any]:
    lot_id = action.get("lot_id")
    symbol = _symbol(action.get("symbol")) if action.get("symbol") else None
    lots = [
        lot for lot in _open_lots(state, symbol)
        if lot_id is None or lot["lot_id"] == lot_id
    ]
    if not lots:
        raise TheoryPaperError("no open lot matches protection update")
    changes: list[tuple[dict[str, Any], float, float, dict[str, Any]]] = []
    for lot in lots:
        old_stop = lot.get("stop_price")
        old_target = lot.get("target_price")
        new_stop = _positive(action.get("stop_price", old_stop), "stop_price")
        new_target = _positive(action.get("target_price", old_target), "target_price")
        mark = views.get(lot["symbol"], {}).get("price")
        reference = float(mark) if mark is not None else float(lot["entry_price"])
        if lot["side"] == "LONG":
            if old_stop is not None and new_stop + 1e-12 < float(old_stop):
                raise TheoryPaperError("LONG_STOP_CANNOT_WIDEN")
            if old_target is not None and new_target + 1e-12 < float(old_target):
                raise TheoryPaperError("LONG_TARGET_CANNOT_MOVE_ADVERSE")
            if not new_stop < reference < new_target:
                raise TheoryPaperError("LONG_PROTECTION_MUST_STRADDLE_CURRENT_PRICE")
        else:
            if old_stop is not None and new_stop - 1e-12 > float(old_stop):
                raise TheoryPaperError("SHORT_STOP_CANNOT_WIDEN")
            if old_target is not None and new_target - 1e-12 > float(old_target):
                raise TheoryPaperError("SHORT_TARGET_CANNOT_MOVE_ADVERSE")
            if not new_target < reference < new_stop:
                raise TheoryPaperError("SHORT_PROTECTION_MUST_STRADDLE_CURRENT_PRICE")
        try:
            terms = _protection_terms(
                state["risk_limits"],
                str(lot["side"]),
                reference,
                new_stop,
                new_target,
                entry_fee_rate=0.0,
            )
        except TheoryPaperError as exc:
            raise TheoryPaperError(
                f"UPDATED_PROTECTION_INVALID:{exc}"
            ) from exc
        if (
            float(terms["net_reward_risk"])
            + 1e-12
            < float(state["risk_limits"]["minimum_reward_risk"])
        ):
            raise TheoryPaperError("UPDATED_PROTECTION_MINIMUM_NET_RR_NOT_MET")
        changes.append((lot, new_stop, new_target, terms))
    for lot, stop, target, terms in changes:
        lot["stop_price"] = _round(stop)
        lot["target_price"] = _round(target)
        lot["initial_stop_price"] = lot.get("initial_stop_price") or _round(stop)
        if lot.get("initial_net_risk_usdt") is None:
            lot["initial_net_risk_usdt"] = _round(
                float(lot["quantity"]) * float(terms["net_risk_per_unit"])
            )
            lot["entry_reward_risk"] = terms["net_reward_risk"]
            lot["entry_reward_risk_gross"] = terms["gross_reward_risk"]
            lot["entry_reward_risk_net"] = terms["net_reward_risk"]
            lot["entry_cost_assumptions"] = terms["assumptions"]
        lot["current_protection_terms"] = terms
        lot["protection_activated_at"] = now
    return {
        "status": "ACCEPTED",
        "updated_lot_ids": [lot["lot_id"] for lot, _, _, _ in changes],
        "net_reward_risk_after": {
            lot["lot_id"]: terms["net_reward_risk"]
            for lot, _, _, terms in changes
        },
    }


def _activate_reviewed_order(
    state: MutableMapping[str, Any],
    action: Mapping[str, Any],
    now: str,
    views: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    order = _find_order(state, action.get("order_id"))
    if order["state"] != "REVIEW_REQUIRED":
        raise TheoryPaperError("only REVIEW_REQUIRED orders can be kept")
    if action.get("symbol") is not None and _symbol(action.get("symbol")) != order["symbol"]:
        raise TheoryPaperError("reviewed order symbol mismatch")
    if action.get("side") is not None and _side(action.get("side")) != order["side"]:
        raise TheoryPaperError("reviewed order side mismatch")
    if (
        action.get("limit_price") is not None
        and not math.isclose(
            _positive(action.get("limit_price"), "limit_price"),
            float(order["limit_price"]),
            rel_tol=1e-8,
            abs_tol=1e-8,
        )
    ):
        raise TheoryPaperError("reviewed order limit price mismatch")
    if (
        action.get("notional_usdt") is not None
        and not math.isclose(
            _positive(action.get("notional_usdt"), "notional_usdt"),
            float(order["notional_usdt"]),
            rel_tol=1e-8,
            abs_tol=1e-8,
        )
    ):
        raise TheoryPaperError("reviewed order notional mismatch")
    reduce_only = bool(action.get("reduce_only", False))
    stop = action.get("stop_price")
    target = action.get("target_price")
    hypothesis_id = action.get("hypothesis_id")
    attribution = str(action.get("attribution") or "STRATEGY").upper()
    authorization = _authorization_from_action(action, attribution)
    protection_terms = None
    if not reduce_only:
        error, protection_terms = _protection_error(
            state,
            "LONG" if order["side"] == "BUY" else "SHORT",
            float(order["limit_price"]),
            stop,
            target,
            float(state["risk_limits"]["minimum_reward_risk"]),
            entry_fee_kind="MAKER",
        )
        if error:
            raise TheoryPaperError(error)
        if not authorization["approved"]:
            raise TheoryPaperError("NEW_RISK_NOT_AUTHORIZED")
        if attribution == "STRATEGY" and not str(hypothesis_id or "").strip():
            raise TheoryPaperError("NEW_RISK_REQUIRES_HYPOTHESIS")
        reasons, _ = _new_risk_reasons(
            state,
            symbol=order["symbol"],
            position_side="LONG" if order["side"] == "BUY" else "SHORT",
            quantity=float(order["remaining_quantity"]),
            entry_price=float(order["limit_price"]),
            stop_price=stop,
            target_price=target,
            authorization=authorization,
            hypothesis_id=hypothesis_id,
            attribution=attribution,
            marks={key: float(value["price"]) for key, value in views.items()},
            risk_fraction_cap=(
                float(state["risk_limits"]["exploration_probe_risk_fraction"])
                if action.get("probe") is True
                else None
            ),
            entry_fee_kind="MAKER",
        )
        if reasons:
            raise TheoryPaperError(",".join(reasons))
    order.update(
        {
            "state": "ACTIVE",
            "activated_at": now,
            "reduce_only": reduce_only,
            "allow_reverse": not reduce_only,
            "stop_price": None if reduce_only else _round(_positive(stop, "stop_price")),
            "target_price": None if reduce_only else _round(_positive(target, "target_price")),
            "hypothesis_id": hypothesis_id,
            "geometry_candidate_id": action.get("geometry_candidate_id"),
            "attribution": attribution,
            "risk_authorization": authorization,
            "probe": action.get("probe") is True,
            "protection_terms": protection_terms,
            "review_note": str(action.get("reason") or "Explicitly reviewed by agent."),
        }
    )
    return {"status": "ACCEPTED", "order_id": order["order_id"], "order_state": "ACTIVE"}


def _place_limit(
    state: MutableMapping[str, Any],
    action: Mapping[str, Any],
    now: str,
    views: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    symbol = _symbol(action.get("symbol"))
    side = _side(action.get("side"))
    price = _positive(action.get("limit_price"), "limit_price")
    notional = _positive(action.get("notional_usdt"), "notional_usdt")
    limits = state["risk_limits"]
    if notional < float(limits["minimum_order_notional_usdt"]):
        raise TheoryPaperError("MINIMUM_ORDER_NOTIONAL")
    if notional > float(limits["maximum_order_notional_usdt"]):
        raise TheoryPaperError("MAXIMUM_ORDER_NOTIONAL")
    reduce_only = bool(action.get("reduce_only", False))
    attribution = str(action.get("attribution") or "STRATEGY").upper()
    authorization = _authorization_from_action(action, attribution)
    stop = action.get("stop_price")
    target = action.get("target_price")
    hypothesis_id = action.get("hypothesis_id")
    protection_terms = None
    if not reduce_only:
        error, protection_terms = _protection_error(
            state,
            "LONG" if side == "BUY" else "SHORT",
            price,
            stop,
            target,
            float(limits["minimum_reward_risk"]),
            entry_fee_kind="MAKER",
        )
        if error:
            raise TheoryPaperError(error)
        if not authorization["approved"]:
            raise TheoryPaperError("NEW_RISK_NOT_AUTHORIZED")
        if attribution == "STRATEGY" and not str(hypothesis_id or "").strip():
            raise TheoryPaperError("NEW_RISK_REQUIRES_HYPOTHESIS")
        reasons, _ = _new_risk_reasons(
            state,
            symbol=symbol,
            position_side="LONG" if side == "BUY" else "SHORT",
            quantity=notional / price,
            entry_price=price,
            stop_price=stop,
            target_price=target,
            authorization=authorization,
            hypothesis_id=hypothesis_id,
            attribution=attribution,
            marks={key: float(value["price"]) for key, value in views.items()},
            risk_fraction_cap=(
                float(limits["exploration_probe_risk_fraction"])
                if action.get("probe") is True
                else None
            ),
            entry_fee_kind="MAKER",
        )
        if reasons:
            raise TheoryPaperError(",".join(reasons))
    order = {
        "order_id": _counter_id(state, "order"),
        "symbol": symbol,
        "side": side,
        "order_type": "LIMIT",
        "limit_price": _round(price),
        "notional_usdt": _round(notional),
        "quantity": _round(notional / price, 12),
        "remaining_quantity": _round(notional / price, 12),
        "state": "ACTIVE",
        "created_at": now,
        "activated_at": now,
        "origin": "AGENT_LIMIT_ORDER",
        "attribution": attribution,
        "hypothesis_id": hypothesis_id,
        "geometry_candidate_id": action.get("geometry_candidate_id"),
        "reduce_only": reduce_only,
        "allow_reverse": not reduce_only,
        "stop_price": None if reduce_only else _round(_positive(stop, "stop_price")),
        "target_price": None if reduce_only else _round(_positive(target, "target_price")),
        "risk_authorization": authorization,
        "probe": action.get("probe") is True,
        "protection_terms": protection_terms,
        "review_note": str(action.get("reason") or ""),
    }
    state["orders"].append(order)
    return {"status": "ACCEPTED", "order_id": order["order_id"], "order_state": "ACTIVE"}


def _market_action(
    state: MutableMapping[str, Any],
    action: Mapping[str, Any],
    views: Mapping[str, Mapping[str, Any]],
    now: str,
    *,
    force_reduce_only: bool = False,
) -> dict[str, Any]:
    symbol = _symbol(action.get("symbol"))
    if symbol not in views:
        raise TheoryPaperError(f"{symbol} has no current paper price")
    side = _side(action.get("side"))
    reference = float(views[symbol]["price"])
    reduce_only = force_reduce_only or bool(action.get("reduce_only", False))
    if force_reduce_only and action.get("notional_usdt") is None:
        opposite_side = "LONG" if side == "SELL" else "SHORT"
        quantity = sum(float(lot["quantity"]) for lot in _open_lots(state, symbol) if lot["side"] == opposite_side)
        if quantity <= 1e-12:
            raise TheoryPaperError("no opposing position to close")
    else:
        notional = _positive(action.get("notional_usdt"), "notional_usdt")
        if notional < float(state["risk_limits"]["minimum_order_notional_usdt"]) and not reduce_only:
            raise TheoryPaperError("MINIMUM_ORDER_NOTIONAL")
        if notional > float(state["risk_limits"]["maximum_order_notional_usdt"]) and not reduce_only:
            raise TheoryPaperError("MAXIMUM_ORDER_NOTIONAL")
        quantity = notional / reference
    price = _slipped_price(reference, side, float(state["risk_limits"]["market_slippage_bps"]))
    attribution = str(action.get("attribution") or "STRATEGY").upper()
    authorization = _authorization_from_action(action, attribution)
    return _execute_quantity(
        state,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        observed_at=now,
        reason="MARKET",
        attribution=attribution,
        origin=str(action.get("origin") or "AGENT_MARKET_ACTION"),
        hypothesis_id=action.get("hypothesis_id"),
        stop_price=action.get("stop_price"),
        target_price=action.get("target_price"),
        authorization=authorization,
        allow_new_risk=not reduce_only,
        reduce_only=reduce_only,
        fee_kind="TAKER",
        marks={key: float(value["price"]) for key, value in views.items()},
        risk_fraction_cap=(
            float(state["risk_limits"]["exploration_probe_risk_fraction"])
            if action.get("probe") is True
            else None
        ),
    )


def _translate_high_level_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Translate the original theory decision vocabulary without granting risk.

    A translated OPEN/ADD still needs an explicit ``risk_authorization`` in the
    supplied object.  Translation alone is never an authorization boundary.
    """

    high_level = str(action.get("action", "")).upper()
    if high_level in {"KEEP", "ABSTAIN"}:
        return {"type": "HOLD", **dict(action)}
    order = action.get("order")
    order_fields = dict(order) if isinstance(order, Mapping) else {}
    if high_level in {"OPEN_LONG", "ADD_LONG", "OPEN_SHORT", "ADD_SHORT"}:
        order_type = str(order_fields.get("order_type", "MARKET")).upper()
        translated = {
            "type": "PLACE_LIMIT" if order_type == "LIMIT" else "MARKET",
            "symbol": action.get("symbol"),
            "side": "BUY" if high_level.endswith("LONG") else "SELL",
            "notional_usdt": order_fields.get("notional_usdt"),
            "limit_price": order_fields.get("limit_price"),
            "stop_price": order_fields.get("stop_loss", order_fields.get("stop_price")),
            "target_price": order_fields.get("take_profit", order_fields.get("target_price")),
            "hypothesis_id": action.get("selected_phi_id"),
            "attribution": "STRATEGY",
            "risk_authorization": action.get(
                "risk_authorization",
                order_fields.get("risk_authorization"),
            ),
        }
        return translated
    if high_level == "REDUCE":
        order_type = str(order_fields.get("order_type", "MARKET")).upper()
        return {
            "type": "PLACE_LIMIT" if order_type == "LIMIT" else "MARKET",
            "symbol": action.get("symbol"),
            "side": order_fields.get("side"),
            "notional_usdt": order_fields.get("notional_usdt"),
            "limit_price": order_fields.get("limit_price"),
            "reduce_only": True,
            "attribution": "STRATEGY",
            "hypothesis_id": action.get("selected_phi_id"),
        }
    if high_level == "EXIT":
        return {
            "type": "CLOSE",
            "symbol": action.get("symbol"),
            "notional_usdt": order_fields.get("notional_usdt"),
            "attribution": "STRATEGY",
            "hypothesis_id": action.get("selected_phi_id"),
        }
    if high_level == "CANCEL_ORDER":
        return {
            "type": "CANCEL_ORDER",
            "order_id": order_fields.get("order_id", action.get("order_id")),
            "reason": action.get("thesis"),
        }
    return dict(action)


def submit_actions(
    state: MutableMapping[str, Any],
    actions: Sequence[Mapping[str, Any]],
    market: Mapping[str, Any],
    observed_at: str | datetime | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and apply an agent decision as independent paper actions."""

    validate_portfolio_state(state)
    if not isinstance(actions, Sequence) or isinstance(actions, (str, bytes)):
        raise TheoryPaperError("actions must be an array")
    views = _market_views(market)
    now = _time(observed_at or market.get("observed_at"))
    results: list[dict[str, Any]] = []
    for index, supplied in enumerate(actions):
        if not isinstance(supplied, Mapping):
            results.append({"index": index, "status": "REJECTED", "reason": "ACTION_MUST_BE_OBJECT"})
            continue
        action = dict(supplied)
        if "type" not in action and str(action.get("action", "")).upper() in {
            "OPEN_LONG",
            "OPEN_SHORT",
            "ADD_LONG",
            "ADD_SHORT",
            "REDUCE",
            "EXIT",
            "CANCEL_ORDER",
            "KEEP",
            "ABSTAIN",
        }:
            action = _translate_high_level_action(action)
        kind = str(action.get("type", action.get("action_type", action.get("action", "")))).upper()
        try:
            if kind in {"HOLD", "NO_ACTION"}:
                result = {"status": "ACCEPTED", "effect": "NO_CHANGE"}
            elif kind in {"UPDATE_PROTECTION", "SET_PROTECTION"}:
                result = _update_protection(state, action, views, now)
            elif kind in {"KEEP_ORDER", "ACTIVATE_ORDER"}:
                result = _activate_reviewed_order(state, action, now, views)
            elif kind == "CANCEL_ORDER":
                order = _find_order(state, action.get("order_id"))
                if order["state"] not in {"ACTIVE", "REVIEW_REQUIRED"}:
                    raise TheoryPaperError("order is not cancelable")
                order["state"] = "CANCELED"
                order["canceled_at"] = now
                order["cancel_reason"] = str(action.get("reason") or "AGENT_DECISION")
                result = {"status": "ACCEPTED", "order_id": order["order_id"], "order_state": "CANCELED"}
            elif kind == "PLACE_LIMIT":
                result = _place_limit(state, action, now, views)
            elif kind == "REPLACE_ORDER":
                old = _find_order(state, action.get("order_id"))
                replacement = dict(action.get("replacement") or {})
                replacement.update({"type": "PLACE_LIMIT"})
                placed = _place_limit(state, replacement, now, views)
                old["state"] = "REPLACED"
                old["replaced_at"] = now
                old["replacement_order_id"] = placed["order_id"]
                result = {"status": "ACCEPTED", "replaced_order_id": old["order_id"], **placed}
            elif kind in {"MARKET", "MARKET_ORDER"}:
                result = _market_action(state, action, views, now)
            elif kind in {"CLOSE", "CLOSE_POSITION"}:
                closing = dict(action)
                symbol = _symbol(closing.get("symbol"))
                long_quantity = sum(float(lot["quantity"]) for lot in _open_lots(state, symbol) if lot["side"] == "LONG")
                short_quantity = sum(float(lot["quantity"]) for lot in _open_lots(state, symbol) if lot["side"] == "SHORT")
                if long_quantity and short_quantity:
                    raise TheoryPaperError("one-way portfolio invariant is violated")
                closing["side"] = "SELL" if long_quantity else "BUY"
                closing["reduce_only"] = True
                result = _market_action(state, closing, views, now, force_reduce_only=True)
            else:
                raise TheoryPaperError("unsupported action type")
            results.append({"index": index, "type": kind, **result})
        except TheoryPaperError as exc:
            results.append({"index": index, "type": kind, "status": "REJECTED", "reason": str(exc)})
    marks = {symbol: float(view["price"]) for symbol, view in views.items()}
    state["updated_at"] = now
    metrics = _refresh_risk_state(state, marks)
    validate_portfolio_state(state)
    strategy_fill_count = sum(
        1
        for result in results
        if result.get("status") in {"FILLED", "PARTIALLY_FILLED_RISK_BLOCKED", "PARTIALLY_FILLED_REDUCE_ONLY"}
        and any(
            fill.get("fill_id") == (result.get("fill") or {}).get("fill_id")
            and fill.get("attribution") == "STRATEGY"
            for fill in state.get("fills", [])
        )
    )
    return {
        "observed_at": now,
        "results": results,
        "metrics": metrics,
        "strategy_fill_count": strategy_fill_count,
    }


def inject_due_chaos(
    state: MutableMapping[str, Any],
    schedule_or_market: Mapping[str, Any],
    market_or_observed_at: Mapping[str, Any] | str | datetime | None = None,
    observed_at: str | datetime | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attempt each sealed, due chaos event exactly once under normal risk caps."""

    if isinstance(market_or_observed_at, Mapping):
        schedule = schedule_or_market
        market = market_or_observed_at
        raw_events = schedule.get("events", [])
    else:
        market = schedule_or_market
        if market_or_observed_at is not None:
            observed_at = market_or_observed_at
        raw_events = state.get("chaos", {}).get("schedule", [])
    views = _market_views(market)
    now = _time(observed_at or market.get("observed_at"))
    now_dt = parse_utc(now)
    results: list[dict[str, Any]] = []
    attempted = state.setdefault("chaos", {}).setdefault("attempted_event_ids", [])
    if not isinstance(raw_events, list):
        raise TheoryPaperError("chaos schedule events must be an array")
    for source_event in raw_events:
        if not isinstance(source_event, Mapping):
            continue
        event = source_event if isinstance(source_event, dict) else dict(source_event)
        chaos_id = str(event.get("chaos_id") or "")
        if (
            not chaos_id
            or chaos_id in attempted
            or event.get("state") not in {"SEALED", "SEALED_PENDING"}
            or parse_utc(str(event["due_at"])) > now_dt
        ):
            continue
        symbol = event["symbol"]
        attempted.append(chaos_id)
        if isinstance(source_event, dict):
            source_event["attempted_at"] = now
        if symbol not in views:
            if isinstance(source_event, dict):
                source_event["state"] = "REJECTED"
                source_event["rejection_reason"] = "NO_CURRENT_PRICE"
            results.append({"chaos_id": chaos_id, "status": "REJECTED", "reason": "NO_CURRENT_PRICE"})
            continue
        price = float(views[symbol]["price"])
        stop_fraction = float(event.get("stop_distance_fraction", 0.02))
        target_fraction = float(event.get("target_distance_fraction", 0.04))
        if event["side"] == "BUY":
            stop, target = price * (1.0 - stop_fraction), price * (1.0 + target_fraction)
        else:
            stop, target = price * (1.0 + stop_fraction), price * (1.0 - target_fraction)
        action = {
            "type": "MARKET",
            "symbol": symbol,
            "side": event["side"],
            "notional_usdt": event["notional_usdt"],
            "stop_price": stop,
            "target_price": target,
            "hypothesis_id": f"controlled-chaos:{chaos_id}",
            "attribution": "CHAOS_AUTO",
            "risk_authorization": {
                "approved": True,
                "authority": "SEALED_CHAOS_SCHEDULE",
                "reason": "Deterministic controlled-noise methodology test.",
            },
            "origin": str(event.get("origin") or "SEALED_CHAOS_INJECTION"),
        }
        report = submit_actions(state, [action], market, now, config)
        result = report["results"][0]
        final_state = "EXECUTED" if result["status"] in {"FILLED", "PARTIALLY_FILLED_RISK_BLOCKED"} else "REJECTED"
        if isinstance(source_event, dict):
            source_event["state"] = final_state
            source_event["execution_result"] = result
        results.append({"chaos_id": chaos_id, **result})
    state["updated_at"] = now
    return {"observed_at": now, "results": results}


def inject_manual_chaos(
    state: MutableMapping[str, Any],
    *args: Any,
    symbol: str | None = None,
    side: str | None = None,
    notional_usdt: float | None = None,
    market: Mapping[str, Any] | None = None,
    observed_at: str | datetime | None = None,
    stop_distance_fraction: float = 0.02,
    target_distance_fraction: float = 0.04,
    note: str = "",
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a user-requested unplanned paper trade with separate attribution."""

    # Compatibility with experiment.py's positional orchestration contract:
    # (state, symbol, side, notional, reason, market, observed_at, config).
    if args and isinstance(args[0], Mapping):
        market = args[0]
    elif args:
        if len(args) < 5:
            raise TheoryPaperError("manual chaos positional call is incomplete")
        symbol = str(args[0])
        side = str(args[1])
        notional_usdt = float(args[2])
        note = str(args[3])
        if not isinstance(args[4], Mapping):
            raise TheoryPaperError("manual chaos market must be an object")
        market = args[4]
        if len(args) > 5:
            observed_at = args[5]
        if len(args) > 6 and isinstance(args[6], Mapping):
            config = args[6]
    if market is None or symbol is None or side is None or notional_usdt is None:
        raise TheoryPaperError("manual chaos needs market, symbol, side, and notional")
    views = _market_views(market)
    normalized_symbol = _symbol(symbol)
    normalized_side = _side(side)
    if normalized_symbol not in views:
        raise TheoryPaperError(f"{normalized_symbol} has no current paper price")
    price = float(views[normalized_symbol]["price"])
    stop_fraction = _positive(stop_distance_fraction, "stop_distance_fraction")
    target_fraction = _positive(target_distance_fraction, "target_distance_fraction")
    if normalized_side == "BUY":
        stop, target = price * (1.0 - stop_fraction), price * (1.0 + target_fraction)
    else:
        stop, target = price * (1.0 + stop_fraction), price * (1.0 - target_fraction)
    state["chaos"]["manual_injection_count"] = int(state["chaos"].get("manual_injection_count", 0)) + 1
    chaos_id = f"chaos-manual-{state['chaos']['manual_injection_count']:03d}"
    action = {
        "type": "MARKET",
        "symbol": normalized_symbol,
        "side": normalized_side,
        "notional_usdt": notional_usdt,
        "stop_price": stop,
        "target_price": target,
        "hypothesis_id": f"controlled-chaos:{chaos_id}",
        "attribution": "CHAOS_MANUAL",
        "risk_authorization": {
            "approved": True,
            "authority": "EXPLICIT_MANUAL_CHAOS",
            "reason": note or "Explicit unplanned paper input.",
        },
        "origin": "MANUAL_CHAOS_INJECTION",
    }
    report = submit_actions(state, [action], market, observed_at, config)
    result = report["results"][0]
    return {"chaos_id": chaos_id, "attribution": "CHAOS_MANUAL", **result}


def deterministic_chaos_schedule(
    *,
    activated_at: str | datetime,
    symbols: Sequence[str],
    seed: str,
    hour_offsets: Sequence[int] = (13, 29, 47),
    notionals_usdt: Sequence[float] = (100.0, 150.0, 200.0),
) -> list[dict[str, Any]]:
    """Create a reproducible schedule for experiment.py to seal at initialization."""

    base = parse_utc(_time(activated_at))
    normalized = sorted({_symbol(symbol) for symbol in symbols})
    if not normalized:
        raise TheoryPaperError("chaos schedule requires symbols")
    if not hour_offsets or not notionals_usdt:
        return []
    output: list[dict[str, Any]] = []
    for index, offset in enumerate(hour_offsets):
        if int(offset) <= 0:
            raise TheoryPaperError("chaos hour offsets must be positive")
        digest = hashlib.sha256(f"{seed}:{index}".encode("utf-8")).digest()
        symbol = normalized[int.from_bytes(digest[:4], "big") % len(normalized)]
        side = "BUY" if digest[4] % 2 == 0 else "SELL"
        notional = _positive(notionals_usdt[index % len(notionals_usdt)], "chaos.notional_usdt")
        output.append(
            {
                "chaos_id": f"chaos-auto-{index + 1:03d}",
                "due_at": iso_utc(base + timedelta(hours=int(offset))),
                "symbol": symbol,
                "side": side,
                "notional_usdt": _round(notional),
                "stop_distance_fraction": 0.02,
                "target_distance_fraction": 0.04,
            }
        )
    return output
