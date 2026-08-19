"""Paper-only risk gates, order idempotency and protection invariants."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from .types import (
    GateLevel,
    ManagedOrder,
    OrderIntent,
    OrderStatus,
    PaperFill,
    PositionStage,
    Side,
    SystemHealth,
    UTC,
    utc_now,
)
from .instrument_rules import BinanceInstrumentRules
from .risk_gate_profile import RiskGateProfile

if TYPE_CHECKING:
    from .paper_audit import PaperAuditTrail


@dataclass(frozen=True)
class RiskLimits:
    max_episode_loss: Decimal
    max_total_notional: Decimal
    max_single_order_quantity: Decimal
    tail_cost_per_unit: Decimal
    max_unprotected_duration: timedelta
    # These gates deliberately use only local, realized paper PnL. They do
    # not stand in for account equity, mark-to-market drawdown or a signed
    # production risk budget.
    max_daily_realized_loss: Optional[Decimal] = None
    max_session_realized_drawdown: Optional[Decimal] = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.max_daily_realized_loss, "max_daily_realized_loss"),
            (self.max_session_realized_drawdown, "max_session_realized_drawdown"),
        ):
            if value is not None and value <= 0:
                raise ValueError("%s must be positive when configured" % field_name)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    worst_case_loss: Decimal = Decimal("0")


@dataclass(frozen=True)
class AccountReconciliation:
    matched: bool
    reasons: Tuple[str, ...]
    expected_open_client_order_ids: Tuple[str, ...]
    observed_open_client_order_ids: Tuple[str, ...]


class RiskGate:
    """Keeps every active cause; a less restrictive cause can never reopen risk."""

    def __init__(self, profile: Optional[RiskGateProfile] = None) -> None:
        self.profile = profile
        self._reasons: Dict[str, GateLevel] = {}
        self._recovery_started: Dict[str, datetime] = {}

    def set(self, reason: str, level: GateLevel, now: Optional[datetime] = None) -> None:
        if level == GateLevel.OPEN:
            self.clear(reason, now=now)
            return
        if self.profile is not None:
            policy = self.profile.policy_for(reason)
            if policy.level != level:
                raise ValueError("gate level does not match frozen reason policy")
        self._reasons[reason] = level
        self._recovery_started.pop(reason, None)

    def mark_recovered(self, reason: str, now: datetime) -> None:
        if reason not in self._reasons:
            raise ValueError("cannot recover an inactive gate reason")
        self._recovery_started.setdefault(reason, now)

    def clear(self, reason: str, *, now: Optional[datetime] = None, manual_acknowledged: bool = False) -> None:
        if self.profile is not None and reason in self._reasons:
            policy = self.profile.policy_for(reason)
            if policy.manual_clear_required and not manual_acknowledged:
                raise ValueError("manual acknowledgement is required to clear this gate reason")
            recovered_at = self._recovery_started.get(reason)
            if recovered_at is None:
                raise ValueError("gate reason must first satisfy its recovery condition")
            current = now or datetime.now(tz=recovered_at.tzinfo)
            if current - recovered_at < policy.recovery_hysteresis:
                raise ValueError("gate recovery hysteresis has not elapsed")
        self._reasons.pop(reason, None)
        self._recovery_started.pop(reason, None)

    @property
    def level(self) -> GateLevel:
        return max(self._reasons.values(), default=GateLevel.OPEN)

    @property
    def reasons(self) -> Dict[str, GateLevel]:
        return dict(self._reasons)


class RiskEngine:
    def __init__(self, limits: RiskLimits, gate_profile: Optional[RiskGateProfile] = None) -> None:
        self.limits = limits
        self.gate = RiskGate(gate_profile)
        self.system_health = SystemHealth.WARMUP
        self.current_notional = Decimal("0")
        self.episode_losses: Dict[str, Decimal] = {}
        self.daily_realized_pnl: Dict[str, Decimal] = {}
        self.session_realized_pnl = Decimal("0")
        self.session_realized_peak = Decimal("0")

    def set_health(self, health: SystemHealth) -> None:
        self.system_health = health

    @staticmethod
    def _utc_day(now: datetime) -> str:
        if now.tzinfo is None:
            raise ValueError("realized PnL timestamp must be timezone aware")
        return now.astimezone(UTC).date().isoformat()

    @property
    def session_realized_drawdown(self) -> Decimal:
        return self.session_realized_peak - self.session_realized_pnl

    def realized_limit_breaches(self, now: datetime) -> Tuple[str, ...]:
        day_pnl = self.daily_realized_pnl.get(self._utc_day(now), Decimal("0"))
        reasons = []
        if self.limits.max_daily_realized_loss is not None and day_pnl <= -self.limits.max_daily_realized_loss:
            reasons.append("DAILY_REALIZED_LOSS_LIMIT")
        if (
            self.limits.max_session_realized_drawdown is not None
            and self.session_realized_drawdown >= self.limits.max_session_realized_drawdown
        ):
            reasons.append("MAX_REALIZED_DRAWDOWN_LIMIT")
        return tuple(reasons)

    def record_realized_pnl(self, pnl: Decimal, now: datetime) -> Tuple[str, ...]:
        """Record a local paper PnL delta and return any newly active limits."""
        day = self._utc_day(now)
        self.daily_realized_pnl[day] = self.daily_realized_pnl.get(day, Decimal("0")) + pnl
        self.session_realized_pnl += pnl
        self.session_realized_peak = max(self.session_realized_peak, self.session_realized_pnl)
        return self.realized_limit_breaches(now)

    def realized_budget_state(self) -> Dict[str, object]:
        return {
            "daily_realized_pnl": {day: str(value) for day, value in sorted(self.daily_realized_pnl.items())},
            "session_realized_pnl": str(self.session_realized_pnl),
            "session_realized_peak": str(self.session_realized_peak),
            "session_realized_drawdown": str(self.session_realized_drawdown),
            "max_daily_realized_loss": str(self.limits.max_daily_realized_loss) if self.limits.max_daily_realized_loss is not None else None,
            "max_session_realized_drawdown": str(self.limits.max_session_realized_drawdown) if self.limits.max_session_realized_drawdown is not None else None,
        }

    def approve(self, intent: OrderIntent, *, reduces_risk: bool = False) -> RiskDecision:
        # A caller may invoke this bypass only after proving the intent is a
        # bounded, opposite-side reduce-only order against the local position.
        # That lets a paper position be flattened while an entry gate is
        # restrictive; it must never be used to add or flip exposure.
        if reduces_risk:
            if intent.quantity <= 0:
                return RiskDecision(False, "ORDER_QUANTITY_LIMIT")
            return RiskDecision(True, "APPROVED_REDUCE_ONLY")
        if self.system_health == SystemHealth.HALTED:
            return RiskDecision(False, "SYSTEM_HALTED")
        if self.system_health in (SystemHealth.WARMUP, SystemHealth.DEGRADED):
            return RiskDecision(False, "SYSTEM_NOT_READY")
        if self.gate.level != GateLevel.OPEN:
            return RiskDecision(False, "RISK_GATE_%s" % self.gate.level.name)
        breaches = self.realized_limit_breaches(intent.created_at)
        if breaches:
            return RiskDecision(False, breaches[0])
        if intent.quantity <= 0 or intent.quantity > self.limits.max_single_order_quantity:
            return RiskDecision(False, "ORDER_QUANTITY_LIMIT")
        stop_distance = abs(intent.limit_price - intent.stop_price)
        worst_case = intent.quantity * (stop_distance + self.limits.tail_cost_per_unit)
        if worst_case + self.episode_losses.get(intent.episode_id, Decimal("0")) > self.limits.max_episode_loss:
            return RiskDecision(False, "EPISODE_LOSS_LIMIT", worst_case)
        projected_notional = self.current_notional + intent.quantity * intent.limit_price
        if projected_notional > self.limits.max_total_notional:
            return RiskDecision(False, "TOTAL_NOTIONAL_LIMIT", worst_case)
        return RiskDecision(True, "APPROVED", worst_case)


class OrderManager:
    """In-memory paper OMS. It has no exchange connectivity or credentials."""

    def __init__(
        self,
        risk: RiskEngine,
        instrument_rules: Optional[BinanceInstrumentRules] = None,
        audit_trail: Optional["PaperAuditTrail"] = None,
    ) -> None:
        self.risk = risk
        self.instrument_rules = instrument_rules
        self.audit_trail = audit_trail
        self.orders_by_intent: Dict[str, ManagedOrder] = {}
        self.position_quantity = Decimal("0")
        # Cost basis and net realized PnL make paper exits auditable.  They
        # are local simulation state, not exchange/account truth.
        self.position_cost_basis = Decimal("0")
        self.realized_pnl = Decimal("0")
        self.protection_last_updated: Optional[datetime] = None
        self.halt_reasons: Set[str] = set()

    def _audit(self, event_type: str, now: datetime, payload: Dict[str, object]) -> None:
        if self.audit_trail is not None:
            self.audit_trail.append(event_type, payload, observed_at=now)

    def audit_state(self) -> Dict[str, object]:
        return {
            "position_quantity": str(self.position_quantity),
            "position_cost_basis": str(self.position_cost_basis),
            "realized_pnl": str(self.realized_pnl),
            "current_notional": str(self.risk.current_notional),
            "realized_budget": self.risk.realized_budget_state(),
            "gate_level": self.risk.gate.level.name,
            "system_health": self.risk.system_health.value,
            "effective_protected_quantity": str(self.effective_protected_quantity),
            "halt_reasons": sorted(self.halt_reasons),
            "orders": {
                intent_id: {
                    "client_order_id": order.client_order_id,
                    "status": order.status.value,
                    "filled_quantity": str(order.filled_quantity),
                    "protection_quantity": str(order.protection_quantity),
                    "reduce_only": order.intent.reduce_only,
                    "rejection_reason": order.rejection_reason,
                }
                for intent_id, order in sorted(self.orders_by_intent.items())
            },
        }

    @staticmethod
    def client_order_id(intent: OrderIntent) -> str:
        basis = "%s|%s|%s|%s|%s" % (
            intent.episode_id,
            intent.intent_id,
            intent.stage.value,
            intent.model_version,
            intent.policy_version,
        )
        return "paper-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]

    def submit_intent(self, intent: OrderIntent) -> ManagedOrder:
        existing = self.orders_by_intent.get(intent.intent_id)
        if existing is not None:
            self._audit("INTENT_DUPLICATE", intent.created_at, {"intent_id": intent.intent_id, "client_order_id": existing.client_order_id})
            return existing
        managed = ManagedOrder(client_order_id=self.client_order_id(intent), intent=intent)
        self._audit("INTENT_RECEIVED", intent.created_at, {
            "intent_id": intent.intent_id,
            "client_order_id": managed.client_order_id,
            "episode_id": intent.episode_id,
            "side": intent.side.value,
            "stage": intent.stage.value,
            "quantity": intent.quantity,
            "limit_price": intent.limit_price,
            "stop_price": intent.stop_price,
            "model_version": intent.model_version,
            "policy_version": intent.policy_version,
            "reduce_only": intent.reduce_only,
        })
        if intent.reduce_only:
            current = self.position_quantity
            expected_exit_side = Side.SELL if current > 0 else Side.BUY
            if current == 0:
                managed.rejection_reason = "NO_POSITION_TO_REDUCE"
                managed.transition(OrderStatus.RISK_REJECTED)
                self.orders_by_intent[intent.intent_id] = managed
                self._audit("INTENT_REJECTED", intent.created_at, {"intent_id": intent.intent_id, "reason": managed.rejection_reason})
                return managed
            if intent.side != expected_exit_side:
                managed.rejection_reason = "REDUCE_ONLY_SIDE_MISMATCH"
                managed.transition(OrderStatus.RISK_REJECTED)
                self.orders_by_intent[intent.intent_id] = managed
                self._audit("INTENT_REJECTED", intent.created_at, {"intent_id": intent.intent_id, "reason": managed.rejection_reason})
                return managed
            if intent.quantity > abs(current):
                managed.rejection_reason = "REDUCE_ONLY_QUANTITY_EXCEEDS_POSITION"
                managed.transition(OrderStatus.RISK_REJECTED)
                self.orders_by_intent[intent.intent_id] = managed
                self._audit("INTENT_REJECTED", intent.created_at, {"intent_id": intent.intent_id, "reason": managed.rejection_reason})
                return managed
        elif self.position_quantity != 0 and (
            (self.position_quantity > 0 and intent.side == Side.SELL)
            or (self.position_quantity < 0 and intent.side == Side.BUY)
        ):
            managed.rejection_reason = "OPPOSITE_SIDE_REQUIRES_REDUCE_ONLY"
            managed.transition(OrderStatus.RISK_REJECTED)
            self.orders_by_intent[intent.intent_id] = managed
            self._audit("INTENT_REJECTED", intent.created_at, {"intent_id": intent.intent_id, "reason": managed.rejection_reason})
            return managed
        if not intent.reduce_only and intent.stage == PositionStage.ADD_POSITION_CONFIRMED and not self.verify_protection(intent.created_at):
            managed.rejection_reason = "PROTECTION_NOT_CONFIRMED"
            managed.transition(OrderStatus.RISK_REJECTED)
            self.orders_by_intent[intent.intent_id] = managed
            self._audit("INTENT_REJECTED", intent.created_at, {"intent_id": intent.intent_id, "reason": managed.rejection_reason})
            return managed
        if self.instrument_rules is not None:
            rule_result = self.instrument_rules.validate_limit_ioc(intent.quantity, intent.limit_price)
            if not rule_result.allowed:
                managed.rejection_reason = "INSTRUMENT_RULES:" + ",".join(rule_result.reasons)
                managed.transition(OrderStatus.RISK_REJECTED)
                self.orders_by_intent[intent.intent_id] = managed
                self._audit("INTENT_REJECTED", intent.created_at, {"intent_id": intent.intent_id, "reason": managed.rejection_reason})
                return managed
        decision = self.risk.approve(intent, reduces_risk=intent.reduce_only)
        if not decision.approved:
            managed.rejection_reason = decision.reason
            managed.transition(OrderStatus.RISK_REJECTED)
            self.orders_by_intent[intent.intent_id] = managed
            self._audit("INTENT_REJECTED", intent.created_at, {"intent_id": intent.intent_id, "reason": managed.rejection_reason})
            return managed
        managed.transition(OrderStatus.RISK_APPROVED)
        managed.transition(OrderStatus.SUBMITTED)
        managed.transition(OrderStatus.ACKNOWLEDGED)
        self.orders_by_intent[intent.intent_id] = managed
        self._audit("INTENT_ACKNOWLEDGED", intent.created_at, {"intent_id": intent.intent_id, "approval": decision.reason, "reduce_only": intent.reduce_only})
        return managed

    def apply_fill(self, intent_id: str, fill: PaperFill, terminal: bool = False) -> ManagedOrder:
        order = self.orders_by_intent[intent_id]
        if order.status in (OrderStatus.RISK_REJECTED, OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.UNKNOWN):
            raise RuntimeError("cannot fill terminal or unknown order")
        if fill.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if order.filled_quantity + fill.quantity > order.intent.quantity:
            raise ValueError("fill exceeds intended quantity")
        prior_position = self.position_quantity
        prior_absolute_quantity = abs(prior_position)
        if order.intent.reduce_only:
            expected_exit_side = Side.SELL if prior_position > 0 else Side.BUY
            if prior_absolute_quantity == 0 or order.intent.side != expected_exit_side:
                raise RuntimeError("reduce-only fill does not reduce the current position")
            if fill.quantity > prior_absolute_quantity:
                raise RuntimeError("reduce-only fill exceeds current position")
        order.fills.append(fill)
        signed = fill.quantity if order.intent.side == Side.BUY else -fill.quantity
        self.position_quantity += signed
        if order.intent.reduce_only:
            average_entry = self.position_cost_basis / prior_absolute_quantity
            gross_pnl = (
                (fill.price - average_entry) * fill.quantity
                if prior_position > 0
                else (average_entry - fill.price) * fill.quantity
            )
            realized_delta = gross_pnl - fill.fee
            self.realized_pnl += realized_delta
            self.position_cost_basis -= average_entry * fill.quantity
            if self.position_quantity == 0:
                self.position_cost_basis = Decimal("0")
                for managed in self.orders_by_intent.values():
                    managed.protection_quantity = Decimal("0")
            elif self.effective_protected_quantity > abs(self.position_quantity):
                # An exit may shrink confirmed protection, but can never
                # manufacture it.  Keep exactly the remaining local exposure.
                protected_order = max(self.orders_by_intent.values(), key=lambda item: item.protection_quantity)
                for managed in self.orders_by_intent.values():
                    managed.protection_quantity = Decimal("0")
                protected_order.protection_quantity = abs(self.position_quantity)
            self.risk.current_notional = self.position_cost_basis
            order.transition(OrderStatus.FILLED if terminal or order.filled_quantity == order.intent.quantity else OrderStatus.PARTIAL)
        else:
            self.position_cost_basis += fill.quantity * fill.price
            realized_delta = -fill.fee
            self.realized_pnl += realized_delta
            self.risk.current_notional = self.position_cost_basis
            order.transition(OrderStatus.FILLED if terminal or order.filled_quantity == order.intent.quantity else OrderStatus.PARTIAL)
            order.transition(OrderStatus.PROTECTION_REQUIRED)
            self.protection_last_updated = fill.filled_at
        realized_limit_breaches = self.risk.record_realized_pnl(realized_delta, fill.filled_at)
        self._audit("FILL_APPLIED", fill.filled_at, {
            "intent_id": intent_id,
            "quantity": fill.quantity,
            "price": fill.price,
            "fee": fill.fee,
            "order_status": order.status.value,
            "reduce_only": order.intent.reduce_only,
            "realized_pnl_delta": realized_delta,
            "realized_limit_breaches": list(realized_limit_breaches),
            "state": self.audit_state(),
        })
        if realized_limit_breaches:
            self.halt(realized_limit_breaches[0], now=fill.filled_at)
        return order

    def finalize_ioc(self, intent_id: str, *, now: Optional[datetime] = None) -> ManagedOrder:
        order = self.orders_by_intent[intent_id]
        if order.filled_quantity == 0:
            order.transition(OrderStatus.CANCELED)
        elif order.filled_quantity < order.intent.quantity:
            order.transition(OrderStatus.CANCELED)
        elif order.status != OrderStatus.FILLED:
            order.transition(OrderStatus.FILLED)
        self._audit("IOC_FINALIZED", now or utc_now(), {"intent_id": intent_id, "order_status": order.status.value, "filled_quantity": order.filled_quantity})
        return order

    @property
    def effective_protected_quantity(self) -> Decimal:
        # V1 models one account-level protection plan. Do not add overlapping
        # reduce-only orders, which could overstate executable protection.
        return max((order.protection_quantity for order in self.orders_by_intent.values()), default=Decimal("0"))

    def confirm_protection(self, intent_id: str, quantity: Decimal, now: datetime) -> ManagedOrder:
        if quantity < 0:
            raise ValueError("protection quantity cannot be negative")
        order = self.orders_by_intent[intent_id]
        if order.intent.reduce_only:
            raise ValueError("reduce-only intents cannot establish position protection")
        for other in self.orders_by_intent.values():
            if other is not order:
                other.protection_quantity = Decimal("0")
        order.protection_quantity = quantity
        self.protection_last_updated = now
        if self.verify_protection(now):
            order.transition(OrderStatus.PROTECTED)
        self._audit("PROTECTION_CONFIRMED", now, {"intent_id": intent_id, "quantity": quantity, "state": self.audit_state()})
        return order

    def verify_protection(self, now: datetime) -> bool:
        required = abs(self.position_quantity)
        protected = self.effective_protected_quantity
        if protected >= required:
            return True
        if self.protection_last_updated is None or now - self.protection_last_updated > self.risk.limits.max_unprotected_duration:
            self.halt("UNPROTECTED_POSITION")
        return False

    def reconcile_position(self, exchange_position_quantity: Decimal, now: datetime) -> bool:
        if exchange_position_quantity != self.position_quantity:
            self.halt("POSITION_MISMATCH")
            self._audit("POSITION_RECONCILIATION_FAILED", now, {"observed_position_quantity": exchange_position_quantity, "state": self.audit_state()})
            return False
        matched = self.verify_protection(now)
        self._audit("POSITION_RECONCILED", now, {"matched": matched, "observed_position_quantity": exchange_position_quantity, "state": self.audit_state()})
        return matched

    def reconcile_account(
        self,
        *,
        exchange_position_quantity: Decimal,
        observed_open_client_order_ids: Set[str],
        now: datetime,
    ) -> AccountReconciliation:
        """Compare the paper OMS view with a future read-only account snapshot.

        This method is deliberately transport-free. It defines the invariant a
        future User Stream/REST adapter must satisfy before it may permit new
        risk; unknown and foreign orders are safety events, not retry hints.
        """
        open_statuses = {OrderStatus.SUBMITTED, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIAL}
        expected = {
            order.client_order_id for order in self.orders_by_intent.values()
            if order.status in open_statuses
        }
        observed = set(observed_open_client_order_ids)
        foreign = observed - expected
        missing = expected - observed
        reasons = []
        if foreign:
            self.halt("FOREIGN_ORDER")
            reasons.append("FOREIGN_ORDER")
        for order in self.orders_by_intent.values():
            if order.client_order_id in missing:
                self.mark_unknown(order.intent.intent_id)
        if missing:
            reasons.append("UNKNOWN_ORDER")
        if exchange_position_quantity != self.position_quantity:
            self.halt("POSITION_MISMATCH")
            reasons.append("POSITION_MISMATCH")
        elif not self.verify_protection(now):
            reasons.append("UNPROTECTED_POSITION")
        result = AccountReconciliation(
            matched=not reasons,
            reasons=tuple(sorted(set(reasons))),
            expected_open_client_order_ids=tuple(sorted(expected)),
            observed_open_client_order_ids=tuple(sorted(observed)),
        )
        self._audit("ACCOUNT_RECONCILED", now, {"matched": result.matched, "reasons": list(result.reasons), "state": self.audit_state()})
        return result

    def mark_unknown(self, intent_id: str) -> None:
        order = self.orders_by_intent[intent_id]
        order.transition(OrderStatus.UNKNOWN)
        self.halt("UNKNOWN_ORDER")

    def halt(self, reason: str, *, now: Optional[datetime] = None) -> None:
        self.halt_reasons.add(reason)
        # HALT_AND_RECONCILE must not leave a local entry intent eligible for
        # execution. Filled legs have already moved to PROTECTION_REQUIRED or
        # later, so only truly pending entry states are canceled here.
        for order in self.orders_by_intent.values():
            if order.status in {OrderStatus.SUBMITTED, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIAL}:
                order.transition(OrderStatus.CANCELED)
        gate_reason = reason
        if self.risk.gate.profile is not None:
            # The OMS keeps its precise operational reason for audit, while a
            # frozen profile controls the coarser reason family used by the
            # resolver. Never let an undeclared diagnostic reason turn a
            # safety halt into an exception or an implicit OPEN state.
            gate_reason = "ACCOUNT_MISMATCH" if reason in {"POSITION_MISMATCH", "FOREIGN_ORDER"} else "DATA_EXECUTION_HALT"
        self.risk.gate.set(gate_reason, GateLevel.HALT_AND_RECONCILE)
        self.risk.set_health(SystemHealth.HALTED)
        self._audit("HALT", now or utc_now(), {"reason": reason, "gate_reason": gate_reason, "state": self.audit_state()})

    def reconcile_complete(self, intent_id: str) -> ManagedOrder:
        order = self.orders_by_intent[intent_id]
        order.transition(OrderStatus.RECONCILED)
        return order
