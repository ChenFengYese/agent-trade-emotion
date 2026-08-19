"""Point-in-time Binance instrument-rule validation for paper intents.

Rules are derived from a captured ``exchangeInfo`` availability record.  They
are not a substitute for exchange acknowledgement and deliberately have no
network, credentials or order-submission capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List


class InstrumentRuleError(ValueError):
    pass


@dataclass(frozen=True)
class RuleValidation:
    allowed: bool
    reasons: List[str]


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InstrumentRuleError("invalid %s" % name) from exc
    if result < 0:
        raise InstrumentRuleError("%s cannot be negative" % name)
    return result


def _step_aligned(value: Decimal, step: Decimal) -> bool:
    return step > 0 and value % step == 0


@dataclass(frozen=True)
class BinanceInstrumentRules:
    source_event_id: str
    symbol: str
    status: str
    tick_size: Decimal
    min_price: Decimal
    max_price: Decimal
    step_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal

    @classmethod
    def from_exchange_info(cls, event_id: str, normalized: Dict[str, Any]) -> "BinanceInstrumentRules":
        if normalized.get("kind") != "exchange_info":
            raise InstrumentRuleError("rules require exchange_info availability record")
        filters = normalized.get("filters")
        if not isinstance(filters, list):
            raise InstrumentRuleError("exchangeInfo filters are missing")
        by_type = {item.get("filterType"): item for item in filters if isinstance(item, dict) and isinstance(item.get("filterType"), str)}
        price, lot = by_type.get("PRICE_FILTER"), by_type.get("LOT_SIZE")
        notional = by_type.get("MIN_NOTIONAL") or by_type.get("NOTIONAL")
        if not isinstance(price, dict) or not isinstance(lot, dict) or not isinstance(notional, dict):
            raise InstrumentRuleError("exchangeInfo lacks PRICE_FILTER, LOT_SIZE or MIN_NOTIONAL")
        min_notional = notional.get("notional", notional.get("minNotional"))
        if min_notional is None:
            raise InstrumentRuleError("MIN_NOTIONAL value is missing")
        result = cls(
            source_event_id=event_id,
            symbol=str(normalized.get("symbol", "")),
            status=str(normalized.get("status", "")),
            tick_size=_decimal(price.get("tickSize"), "tickSize"),
            min_price=_decimal(price.get("minPrice"), "minPrice"),
            max_price=_decimal(price.get("maxPrice"), "maxPrice"),
            step_size=_decimal(lot.get("stepSize"), "stepSize"),
            min_quantity=_decimal(lot.get("minQty"), "minQty"),
            max_quantity=_decimal(lot.get("maxQty"), "maxQty"),
            min_notional=_decimal(min_notional, "minNotional"),
        )
        if not result.symbol or result.tick_size <= 0 or result.step_size <= 0:
            raise InstrumentRuleError("exchangeInfo rule increments must be positive")
        return result

    def validate_limit_ioc(self, quantity: Decimal, limit_price: Decimal) -> RuleValidation:
        reasons: List[str] = []
        if self.status != "TRADING":
            reasons.append("INSTRUMENT_NOT_TRADING")
        if quantity <= 0 or quantity < self.min_quantity or (self.max_quantity > 0 and quantity > self.max_quantity):
            reasons.append("QUANTITY_FILTER")
        if not _step_aligned(quantity, self.step_size):
            reasons.append("QUANTITY_STEP_FILTER")
        if limit_price <= 0 or limit_price < self.min_price or (self.max_price > 0 and limit_price > self.max_price):
            reasons.append("PRICE_FILTER")
        if not _step_aligned(limit_price, self.tick_size):
            reasons.append("PRICE_TICK_FILTER")
        if quantity * limit_price < self.min_notional:
            reasons.append("MIN_NOTIONAL_FILTER")
        return RuleValidation(not reasons, reasons)
