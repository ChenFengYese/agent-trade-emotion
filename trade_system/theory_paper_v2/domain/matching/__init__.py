"""Point-in-time, closed-bar counterfactual matching."""

from .engine import match_closed_bar
from .model import (
    BarrierOrder,
    BarrierType,
    ClosedBar,
    LimitTouchPolicy,
    MatchResult,
    MatchingPolicy,
    OrderSide,
    PartialFillPolicy,
)

__all__ = [
    "BarrierOrder",
    "BarrierType",
    "ClosedBar",
    "LimitTouchPolicy",
    "MatchResult",
    "MatchingPolicy",
    "OrderSide",
    "PartialFillPolicy",
    "match_closed_bar",
]
