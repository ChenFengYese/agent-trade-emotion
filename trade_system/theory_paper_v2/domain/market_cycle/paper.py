"""Immutable contracts for the V3.3.2 isolated paper-trading ledger.

These objects record Agent-authored commands and deterministic paper facts.  They
do not select trades, infer market intent, or authorize an external order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from types import MappingProxyType
from typing import Any, Mapping

from ..contracts.canonical import canonical_decimal, canonical_digest


class PaperContractError(ValueError):
    """A paper-trading value violates the frozen V3.3.2 contract."""


PAPER_COMMAND_TYPES = frozenset(
    {
        "MARKET",
        "LIMIT",
        "STOP_LOSS",
        "TAKE_PROFIT",
        "REDUCE",
        "LIMIT_REDUCE",
        "CANCEL",
    }
)
PAPER_ORDER_STATES = frozenset(
    {
        "HELD",
        "OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
        "UNRESOLVED",
    }
)
PAPER_TERMINAL_ORDER_STATES = frozenset(
    {"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "UNRESOLVED"}
)
PAPER_EVENT_TYPES = frozenset(
    {
        "ACCOUNT_OPENED",
        "INTENT_RECORDED",
        "COMMAND_ACCEPTED",
        "STATIC_NO_TRANSITION_PREREGISTERED",
        "ORDER_OPENED",
        "ORDER_HELD",
        "ORDER_ACTIVATED",
        "ORDER_UPDATED",
        "ORDER_CANCELLED",
        "ORDER_REJECTED",
        "ORDER_EXPIRED",
        "ORDER_UNRESOLVED",
        "FILL_RECORDED",
        "MARKET_OBSERVED",
        "CARRY_ACCRUED",
        "FUNDING_COVERAGE_ADVANCED",
    }
)
PAPER_ACCOUNT_MODES = frozenset({"LINEAR_PERP", "CASH_SPOT"})
PAPER_SIDES = frozenset({"BUY", "SELL"})
PAPER_TIME_IN_FORCE = frozenset({"GTC", "IOC"})
PAPER_COST_STATUSES = frozenset({"MODELED", "OBSERVED", "UNKNOWN", "NOT_APPLICABLE"})
PAPER_UNSOURCED_COST_STATUSES = frozenset({"UNKNOWN", "NOT_APPLICABLE"})
PAPER_CARRY_COVERAGE_STATUSES = frozenset({"COMPLETE", "PARTIAL", "UNKNOWN", "NOT_APPLICABLE"})
PAPER_QUANTITY_BASES = frozenset({"BASE_UNITS", "CONTRACTS"})
PAPER_AGENT_ACTIONS = frozenset(
    {
        "WATCH",
        "WAIT",
        "CONDITIONAL",
        "PROBE",
        "OPEN",
        "HOLD",
        "ADD",
        "REDUCE",
        "HARVEST",
        "CLOSE",
        "REENTRY_PENDING",
        "REENTER",
        "HEDGE",
        "PROTECT",
        "CANCEL",
        "OTHER",
    }
)
PAPER_NON_EXECUTABLE_ACTIONS = frozenset(
    {"WATCH", "WAIT", "CONDITIONAL", "HOLD", "REENTRY_PENDING", "OTHER"}
)
PAPER_BRACKET_ELIGIBLE_ACTIONS = frozenset({"OPEN", "PROBE"})
PAPER_POSITION_ROLES = frozenset(
    {"CORE", "TACTICAL", "HEDGE", "PROBE", "RUNNER", "CASH_FLAT", "OTHER"}
)

STATIC_NO_TRANSITION_POLICY_ID = "STATIC_NO_TRANSITION_V1"


def _static_no_transition_policy_document() -> dict[str, Any]:
    return {
        "schema_id": "agent-trade-emotion.static-no-transition-policy",
        "schema_version": "1.1.0",
        "purpose": "IDEALIZED_STATIC_REFERENCE_DIAGNOSTIC_ONLY",
        "eligibility": "FIRST_FLAT_TO_PROTECTED_BRACKET_PER_EPISODE",
        "path_requirement": "ORDERED_CLOSED_15M_FULLY_AFTER_PREREGISTRATION",
        "entry_reference": "LIMIT_BAR_TOUCH_NOT_EXECUTION_TRUTH",
        "intrabar_order": "UNRESOLVED_WITHIN_BAR",
        "position_reference": (
            "HYPOTHETICAL_FULL_INITIAL_EXPOSURE_UNCHANGED_TO_ENDPOINT"
        ),
        "endpoint_reference": "LAST_ORDERED_CLOSE",
        "cost_policy": "MODELED_COMPONENTS_EXPLICIT_UNKNOWN_NEVER_IMPUTED",
        "episode_policy": (
            "ONE_ROOT_COMPARATOR_LATER_SEGMENTS_ONGOING_NOT_INDEPENDENT"
        ),
        "comparison_admissibility": "NOT_COMPARABLE_WITH_ACTUAL_PAPER_EPISODE",
        "prohibited_interpretation": "NO_ACTUAL_VS_STATIC_SUPERIORITY_CONCLUSION",
    }


STATIC_NO_TRANSITION_POLICY_SHA256 = canonical_digest(
    _static_no_transition_policy_document()
)
STATIC_NO_TRANSITION_SCHEMA_SHA256 = canonical_digest(
    {
        "schema_id": "agent-trade-emotion.static-no-transition-comparator",
        "schema_version": "1.0.0",
        "fields": [
            "comparator_id",
            "policy_id",
            "policy_sha256",
            "schema_sha256",
            "preregistered_at",
            "account_pre_version",
            "account_pre_head_record_sha256",
            "intent_sha256",
            "bracket_sha256",
            "execution_intent",
            "reference",
            "instrument_spec",
            "cost_model",
            "cost_model_sha256",
        ],
    }
)

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SYMBOL_RE = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,63}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PaperContractError(f"{field} must be a safe identifier")
    return value


def _symbol(value: object) -> str:
    if not isinstance(value, str) or _SYMBOL_RE.fullmatch(value) is None:
        raise PaperContractError("symbol must be a canonical uppercase instrument key")
    return value


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PaperContractError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperContractError(f"{field} must include an explicit UTC offset")
    return value


def _decimal_text(
    value: object,
    *,
    field: str,
    positive: bool = False,
    nonnegative: bool = False,
) -> str:
    if not isinstance(value, str):
        raise PaperContractError(f"{field} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PaperContractError(f"{field} must be a canonical decimal string") from exc
    if not parsed.is_finite() or canonical_decimal(parsed) != value:
        raise PaperContractError(f"{field} must be a canonical decimal string")
    if positive and parsed <= 0:
        raise PaperContractError(f"{field} must be greater than zero")
    if nonnegative and parsed < 0:
        raise PaperContractError(f"{field} must be nonnegative")
    return value


def _optional_decimal(
    value: object,
    *,
    field: str,
    positive: bool = False,
) -> str | None:
    if value is None:
        return None
    return _decimal_text(value, field=field, positive=positive)


def _sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PaperContractError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _freeze_json(value: Any, *, field: str) -> Any:
    if value is None or isinstance(value, (str, bool)) or type(value) is int:
        return value
    if isinstance(value, float) or isinstance(value, Decimal):
        raise PaperContractError(f"{field} must use decimal strings, not numeric decimals")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) or not key for key in value):
            raise PaperContractError(f"{field} has an invalid object key")
        return MappingProxyType(
            {
                key: _freeze_json(value[key], field=f"{field}.{key}")
                for key in sorted(value)
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, field=f"{field}[{index}]")
            for index, item in enumerate(value)
        )
    raise PaperContractError(f"{field} contains unsupported type {type(value).__name__}")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class PaperCommandV1:
    command_id: str
    account_id: str
    logical_agent_id: str
    agent_generation: int
    decision_cycle_id: str
    decision_sha256: str
    expected_account_version: int
    symbol: str
    command_type: str
    side: str | None
    quantity: str | None
    limit_price: str | None
    trigger_price: str | None
    target_order_id: str | None
    reduce_only: bool
    time_in_force: str
    submitted_at: str
    expires_at: str | None
    cost_model_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _identifier(self.command_id, field="command_id"))
        object.__setattr__(self, "account_id", _identifier(self.account_id, field="account_id"))
        object.__setattr__(
            self,
            "logical_agent_id",
            _identifier(self.logical_agent_id, field="logical_agent_id"),
        )
        if type(self.agent_generation) is not int or self.agent_generation < 1:
            raise PaperContractError("agent_generation must be an integer >= 1")
        object.__setattr__(
            self,
            "decision_cycle_id",
            _identifier(self.decision_cycle_id, field="decision_cycle_id"),
        )
        object.__setattr__(
            self,
            "decision_sha256",
            _sha256(self.decision_sha256, field="decision_sha256"),
        )
        if type(self.expected_account_version) is not int or self.expected_account_version < 0:
            raise PaperContractError("expected_account_version must be an integer >= 0")
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        if self.command_type not in PAPER_COMMAND_TYPES:
            raise PaperContractError("command_type is unsupported")
        if self.side is not None and self.side not in PAPER_SIDES:
            raise PaperContractError("side must be BUY or SELL")
        object.__setattr__(
            self,
            "quantity",
            _optional_decimal(self.quantity, field="quantity", positive=True),
        )
        object.__setattr__(
            self,
            "limit_price",
            _optional_decimal(self.limit_price, field="limit_price", positive=True),
        )
        object.__setattr__(
            self,
            "trigger_price",
            _optional_decimal(self.trigger_price, field="trigger_price", positive=True),
        )
        if self.target_order_id is not None:
            object.__setattr__(
                self,
                "target_order_id",
                _identifier(self.target_order_id, field="target_order_id"),
            )
        if type(self.reduce_only) is not bool:
            raise PaperContractError("reduce_only must be boolean")
        if self.time_in_force not in PAPER_TIME_IN_FORCE:
            raise PaperContractError("time_in_force must be GTC or IOC")
        object.__setattr__(
            self, "submitted_at", _timestamp(self.submitted_at, field="submitted_at")
        )
        if self.expires_at is not None:
            object.__setattr__(
                self, "expires_at", _timestamp(self.expires_at, field="expires_at")
            )
            if datetime.fromisoformat(self.expires_at.replace("Z", "+00:00")) <= datetime.fromisoformat(
                self.submitted_at.replace("Z", "+00:00")
            ):
                raise PaperContractError("expires_at must be after submitted_at")
        object.__setattr__(
            self, "cost_model_id", _identifier(self.cost_model_id, field="cost_model_id")
        )
        self._validate_shape()

    def _validate_shape(self) -> None:
        if self.command_type == "CANCEL":
            if (
                self.target_order_id is None
                or self.side is not None
                or self.quantity is not None
                or self.limit_price is not None
                or self.trigger_price is not None
                or self.reduce_only
            ):
                raise PaperContractError("CANCEL requires only target_order_id")
            return
        if self.target_order_id is not None or self.side is None or self.quantity is None:
            raise PaperContractError("non-CANCEL commands require side and quantity")
        if self.command_type in {"LIMIT", "LIMIT_REDUCE"}:
            if self.limit_price is None or self.trigger_price is not None:
                raise PaperContractError("limit command requires only limit_price")
        elif self.command_type in {"STOP_LOSS", "TAKE_PROFIT"}:
            if self.trigger_price is None or self.limit_price is not None:
                raise PaperContractError("protective command requires only trigger_price")
        elif self.limit_price is not None or self.trigger_price is not None:
            raise PaperContractError("market/reduce command must not carry a price")
        must_reduce = self.command_type in {
            "STOP_LOSS",
            "TAKE_PROFIT",
            "REDUCE",
            "LIMIT_REDUCE",
        }
        if self.reduce_only != must_reduce:
            raise PaperContractError("reduce_only does not match command_type")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.paper-command",
            # 1.1.0 makes the cycle binding mandatory.  Legacy 1.0.0 commands
            # are deliberately not upgraded because a digest alone cannot
            # identify which cycle authorized the action.
            "schema_version": "1.1.0",
            "command_id": self.command_id,
            "account_id": self.account_id,
            "logical_agent_id": self.logical_agent_id,
            "agent_generation": self.agent_generation,
            "decision_cycle_id": self.decision_cycle_id,
            "decision_sha256": self.decision_sha256,
            "expected_account_version": self.expected_account_version,
            "symbol": self.symbol,
            "command_type": self.command_type,
            "side": self.side,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "trigger_price": self.trigger_price,
            "target_order_id": self.target_order_id,
            "reduce_only": self.reduce_only,
            "time_in_force": self.time_in_force,
            "submitted_at": self.submitted_at,
            "expires_at": self.expires_at,
            "cost_model_id": self.cost_model_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PaperCommandV1":
        """Restore only the exact cycle-bound command schema.

        There is intentionally no compatibility inference for 1.0.0 payloads:
        choosing a cycle by scanning for the same decision digest would weaken
        the authority boundary.  Callers must create a new 1.1.0 command with
        an explicit ``decision_cycle_id``.
        """

        expected = {
            "schema_id",
            "schema_version",
            "command_id",
            "account_id",
            "logical_agent_id",
            "agent_generation",
            "decision_cycle_id",
            "decision_sha256",
            "expected_account_version",
            "symbol",
            "command_type",
            "side",
            "quantity",
            "limit_price",
            "trigger_price",
            "target_order_id",
            "reduce_only",
            "time_in_force",
            "submitted_at",
            "expires_at",
            "cost_model_id",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PaperContractError("paper command fields mismatch")
        if (
            value["schema_id"] != "agent-trade-emotion.paper-command"
            or value["schema_version"] != "1.1.0"
        ):
            raise PaperContractError("paper command schema mismatch")
        return cls(
            **{
                key: value[key]
                for key in expected
                if key not in {"schema_id", "schema_version"}
            }
        )


BRACKET_ACTIVATION_POLICY = "AFTER_FIRST_ENTRY_FILL_NEXT_FORWARD_SLICE"
BRACKET_EXIT_POLICY = "STOP_CANCELS_ENTRY_AND_TARGETS_TARGETS_SHARE_REMAINING_EXPOSURE"
PAPER_BRACKET_ENTRY_COMMAND_TYPES = frozenset({"LIMIT"})


@dataclass(frozen=True, slots=True)
class PaperBracketV1:
    """One entry and its contingent reduce-only exits, authored as one intent."""

    bracket_id: str
    entry: PaperCommandV1
    protective_stop: PaperCommandV1
    take_profits: tuple[PaperCommandV1, ...]
    activation_policy: str = BRACKET_ACTIVATION_POLICY
    exit_policy: str = BRACKET_EXIT_POLICY

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "bracket_id", _identifier(self.bracket_id, field="bracket_id")
        )
        if not isinstance(self.entry, PaperCommandV1) or not isinstance(
            self.protective_stop, PaperCommandV1
        ):
            raise PaperContractError("bracket entry and stop must be paper commands")
        profits = tuple(self.take_profits)
        if not all(isinstance(item, PaperCommandV1) for item in profits):
            raise PaperContractError("bracket take profits must be paper commands")
        object.__setattr__(self, "take_profits", profits)
        if self.activation_policy != BRACKET_ACTIVATION_POLICY:
            raise PaperContractError("bracket activation policy is unsupported")
        if self.exit_policy != BRACKET_EXIT_POLICY:
            raise PaperContractError("bracket exit policy is unsupported")
        entry = self.entry
        exits = (self.protective_stop, *profits)
        commands = (entry, *exits)
        if (
            entry.command_type not in PAPER_BRACKET_ENTRY_COMMAND_TYPES
            or entry.reduce_only
        ):
            raise PaperContractError("bracket entry must be a non-reduce LIMIT")
        if self.protective_stop.command_type != "STOP_LOSS":
            raise PaperContractError("bracket protective stop must be STOP_LOSS")
        if any(item.command_type != "TAKE_PROFIT" for item in profits):
            raise PaperContractError("bracket targets must be TAKE_PROFIT commands")
        if any(not item.reduce_only for item in exits):
            raise PaperContractError("bracket exits must be reduce-only")
        if len({item.command_id for item in commands}) != len(commands):
            raise PaperContractError("bracket command ids must be unique")
        identity_fields = (
            "account_id",
            "logical_agent_id",
            "agent_generation",
            "decision_cycle_id",
            "decision_sha256",
            "expected_account_version",
            "symbol",
            "submitted_at",
            "cost_model_id",
        )
        if any(
            any(getattr(item, field) != getattr(entry, field) for field in identity_fields)
            for item in exits
        ):
            raise PaperContractError(
                "bracket commands must share one decision, context head and receipt time"
            )
        opposite = "BUY" if entry.side == "SELL" else "SELL"
        if any(item.side != opposite for item in exits):
            raise PaperContractError("bracket exits must oppose the entry side")
        entry_quantity = Decimal(entry.quantity or "0")
        if Decimal(self.protective_stop.quantity or "0") != entry_quantity:
            raise PaperContractError("bracket stop must protect the full entry quantity")
        target_quantity = sum(
            (Decimal(item.quantity or "0") for item in profits), Decimal("0")
        )
        if target_quantity > entry_quantity:
            raise PaperContractError("bracket targets exceed the entry quantity")
        entry_price = Decimal(entry.limit_price or "0")
        stop_price = Decimal(self.protective_stop.trigger_price or "0")
        target_prices = tuple(Decimal(item.trigger_price or "0") for item in profits)
        if entry.side == "SELL":
            geometry_valid = stop_price > entry_price and all(
                value < entry_price for value in target_prices
            )
        else:
            geometry_valid = stop_price < entry_price and all(
                value > entry_price for value in target_prices
            )
        if not geometry_valid or len(target_prices) != len(set(target_prices)):
            raise PaperContractError("bracket stop/target price geometry is invalid")

    @property
    def commands(self) -> tuple[PaperCommandV1, ...]:
        return (self.entry, self.protective_stop, *self.take_profits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.paper-bracket",
            "schema_version": "1.0.0",
            "bracket_id": self.bracket_id,
            "entry": self.entry.to_dict(),
            "protective_stop": self.protective_stop.to_dict(),
            "take_profits": [item.to_dict() for item in self.take_profits],
            "activation_policy": self.activation_policy,
            "exit_policy": self.exit_policy,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PaperBracketV1":
        fields = {
            "schema_id",
            "schema_version",
            "bracket_id",
            "entry",
            "protective_stop",
            "take_profits",
            "activation_policy",
            "exit_policy",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise PaperContractError("paper bracket fields mismatch")
        profits = value["take_profits"]
        if (
            value["schema_id"] != "agent-trade-emotion.paper-bracket"
            or value["schema_version"] != "1.0.0"
            or not isinstance(profits, (list, tuple))
        ):
            raise PaperContractError("paper bracket schema mismatch")
        return cls(
            bracket_id=value["bracket_id"],
            entry=PaperCommandV1.from_dict(value["entry"]),
            protective_stop=PaperCommandV1.from_dict(value["protective_stop"]),
            take_profits=tuple(PaperCommandV1.from_dict(item) for item in profits),
            activation_policy=value["activation_policy"],
            exit_policy=value["exit_policy"],
        )


@dataclass(frozen=True, slots=True)
class PaperExecutionIntentV1:
    """Agent-owned transition semantics plus an optional exact paper command.

    A research decision may be valid but non-executable.  In that case
    ``command`` remains ``None`` and the system records the absence rather than
    manufacturing order fields.  An executable intent binds every command
    field, account head and transition description before the paper service
    may apply it.
    """

    intent_id: str
    execution_intent_request_sha256: str
    decision_request_sha256: str
    paper_context_sha256: str
    ledger_head_record_sha256: str
    decision_cycle_id: str
    decision_sha256: str
    account_id: str
    logical_agent_id: str
    agent_generation: int
    expected_account_version: int
    symbol: str
    authored_at: str
    valid_until: str
    action: str
    episode_id: str
    transition_id: str
    tranche_id: str | None
    role: str
    pre_state: Mapping[str, Any]
    target_state: Mapping[str, Any]
    position_delta: Mapping[str, Any]
    evidence_delta: str
    activation: str
    hard_invalidation: str
    risk_budget: Mapping[str, Any]
    command: PaperCommandV1 | None
    bracket: PaperBracketV1 | None = None
    wire_schema_version: str = "1.3.0"

    def __post_init__(self) -> None:
        if self.wire_schema_version not in {"1.2.0", "1.3.0"}:
            raise PaperContractError("paper execution intent schema mismatch")
        if self.wire_schema_version == "1.2.0" and self.bracket is not None:
            raise PaperContractError("paper execution intent 1.2 cannot carry a bracket")
        for field_name in (
            "intent_id",
            "decision_cycle_id",
            "account_id",
            "logical_agent_id",
            "episode_id",
            "transition_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "execution_intent_request_sha256",
            _sha256(
                self.execution_intent_request_sha256,
                field="execution_intent_request_sha256",
            ),
        )
        object.__setattr__(
            self,
            "decision_request_sha256",
            _sha256(
                self.decision_request_sha256, field="decision_request_sha256"
            ),
        )
        object.__setattr__(
            self,
            "paper_context_sha256",
            _sha256(self.paper_context_sha256, field="paper_context_sha256"),
        )
        object.__setattr__(
            self,
            "ledger_head_record_sha256",
            _sha256(
                self.ledger_head_record_sha256,
                field="ledger_head_record_sha256",
            ),
        )
        object.__setattr__(
            self,
            "decision_sha256",
            _sha256(self.decision_sha256, field="decision_sha256"),
        )
        if type(self.agent_generation) is not int or self.agent_generation < 1:
            raise PaperContractError("intent agent_generation must be >= 1")
        if (
            type(self.expected_account_version) is not int
            or self.expected_account_version < 1
        ):
            raise PaperContractError("intent expected_account_version must be >= 1")
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        authored_at = _timestamp(self.authored_at, field="intent.authored_at")
        valid_until = _timestamp(self.valid_until, field="intent.valid_until")
        if datetime.fromisoformat(valid_until.replace("Z", "+00:00")) <= datetime.fromisoformat(
            authored_at.replace("Z", "+00:00")
        ):
            raise PaperContractError("intent valid_until must be after authored_at")
        if self.action not in PAPER_AGENT_ACTIONS:
            raise PaperContractError("intent action is unsupported")
        if self.tranche_id is not None:
            object.__setattr__(
                self,
                "tranche_id",
                _identifier(self.tranche_id, field="tranche_id"),
            )
        if self.role not in PAPER_POSITION_ROLES:
            raise PaperContractError("intent role is unsupported")
        for field_name in (
            "pre_state",
            "target_state",
            "position_delta",
            "risk_budget",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping) or not value:
                raise PaperContractError(f"intent {field_name} must be a non-empty object")
            object.__setattr__(
                self,
                field_name,
                _freeze_json(value, field=f"intent.{field_name}"),
            )
        try:
            raw_values = (
                self.pre_state["signed_quantity"],
                self.target_state["signed_quantity"],
                self.position_delta["signed_quantity_change"],
                self.risk_budget["maximum_loss"],
                self.risk_budget["notional_cap"],
                self.risk_budget["max_observed_drawdown"],
            )
            if not all(isinstance(value, str) for value in raw_values):
                raise ValueError
            (
                pre_quantity,
                target_quantity,
                quantity_change,
                maximum_loss,
                notional_cap,
                drawdown_cap,
            ) = (Decimal(value) for value in raw_values)
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise PaperContractError(
                "intent state and risk quantities must be canonical decimals"
            ) from exc
        for value, field_name in (
            (pre_quantity, "pre_state.signed_quantity"),
            (target_quantity, "target_state.signed_quantity"),
            (quantity_change, "position_delta.signed_quantity_change"),
            (maximum_loss, "risk_budget.maximum_loss"),
            (notional_cap, "risk_budget.notional_cap"),
            (drawdown_cap, "risk_budget.max_observed_drawdown"),
        ):
            if canonical_decimal(value) != str(
                self.pre_state["signed_quantity"]
                if field_name == "pre_state.signed_quantity"
                else self.target_state["signed_quantity"]
                if field_name == "target_state.signed_quantity"
                else self.position_delta["signed_quantity_change"]
                if field_name == "position_delta.signed_quantity_change"
                else self.risk_budget[field_name.split(".", 1)[1]]
            ):
                raise PaperContractError(f"intent {field_name} is not canonical")
        if target_quantity - pre_quantity != quantity_change:
            raise PaperContractError("intent position delta does not reconcile")
        if maximum_loss <= 0 or notional_cap <= 0 or drawdown_cap <= 0:
            raise PaperContractError("intent risk budgets must be positive")
        for field_name in (
            "evidence_delta",
            "activation",
            "hard_invalidation",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or len(value) > 16_384:
                raise PaperContractError(f"intent {field_name} must be readable text")
        if self.command is not None:
            if self.action in PAPER_NON_EXECUTABLE_ACTIONS:
                raise PaperContractError(
                    "non-executable action cannot carry a paper command"
                )
            if not isinstance(self.command, PaperCommandV1):
                raise PaperContractError("intent command must be PaperCommandV1")
            command = self.command
            if (
                command.command_id != self.intent_id
                or command.decision_cycle_id != self.decision_cycle_id
                or command.decision_sha256 != self.decision_sha256
                or command.account_id != self.account_id
                or command.logical_agent_id != self.logical_agent_id
                or command.agent_generation != self.agent_generation
                or command.expected_account_version != self.expected_account_version
                or command.symbol != self.symbol
                or command.submitted_at != self.authored_at
                or (
                    command.expires_at is not None
                    and datetime.fromisoformat(
                        command.expires_at.replace("Z", "+00:00")
                    )
                    > datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                )
            ):
                raise PaperContractError("intent command binding mismatch")
            if self.bracket is not None:
                if not isinstance(self.bracket, PaperBracketV1):
                    raise PaperContractError("intent bracket must be PaperBracketV1")
                if (
                    self.wire_schema_version != "1.3.0"
                    or self.bracket.bracket_id != self.intent_id
                    or self.bracket.entry != command
                    or self.action not in PAPER_BRACKET_ELIGIBLE_ACTIONS
                ):
                    raise PaperContractError("intent bracket binding mismatch")
                if any(
                    item.expires_at is not None
                    and datetime.fromisoformat(item.expires_at.replace("Z", "+00:00"))
                    > datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                    for item in self.bracket.commands
                ):
                    raise PaperContractError("intent bracket expires after intent validity")
                if pre_quantity != 0:
                    raise PaperContractError(
                        "paper bracket 1.3 requires a flat pre-state"
                    )
            if self.command.command_type == "CANCEL":
                if self.action != "CANCEL" or quantity_change != 0:
                    raise PaperContractError(
                        "cancel intent cannot change target position"
                    )
            else:
                signed_command_quantity = Decimal(self.command.quantity or "0") * (
                    Decimal("1") if self.command.side == "BUY" else Decimal("-1")
                )
                if signed_command_quantity != quantity_change:
                    raise PaperContractError(
                        "intent command quantity does not match position delta"
                    )
        elif self.bracket is not None:
            raise PaperContractError("paper bracket requires an exact entry command")
        elif self.action not in PAPER_NON_EXECUTABLE_ACTIONS:
            raise PaperContractError("action requires an exact paper command")
        elif quantity_change != 0 or target_quantity != pre_quantity:
            raise PaperContractError(
                "non-executable action cannot change target position"
            )

    @property
    def intent_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = {
            "schema_id": "agent-trade-emotion.paper-execution-intent",
            "schema_version": self.wire_schema_version,
            "intent_id": self.intent_id,
            "execution_intent_request_sha256": (
                self.execution_intent_request_sha256
            ),
            "decision_request_sha256": self.decision_request_sha256,
            "paper_context_sha256": self.paper_context_sha256,
            "ledger_head_record_sha256": self.ledger_head_record_sha256,
            "decision_cycle_id": self.decision_cycle_id,
            "decision_sha256": self.decision_sha256,
            "account_id": self.account_id,
            "logical_agent_id": self.logical_agent_id,
            "agent_generation": self.agent_generation,
            "expected_account_version": self.expected_account_version,
            "symbol": self.symbol,
            "authored_at": self.authored_at,
            "valid_until": self.valid_until,
            "action": self.action,
            "episode_id": self.episode_id,
            "transition_id": self.transition_id,
            "tranche_id": self.tranche_id,
            "role": self.role,
            "pre_state": _thaw_json(self.pre_state),
            "target_state": _thaw_json(self.target_state),
            "position_delta": _thaw_json(self.position_delta),
            "evidence_delta": self.evidence_delta,
            "activation": self.activation,
            "hard_invalidation": self.hard_invalidation,
            "risk_budget": _thaw_json(self.risk_budget),
            "command": None if self.command is None else self.command.to_dict(),
        }
        if self.wire_schema_version == "1.3.0":
            value["bracket"] = None if self.bracket is None else self.bracket.to_dict()
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PaperExecutionIntentV1":
        legacy_fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "intent_id",
                "execution_intent_request_sha256",
                "decision_request_sha256",
                "paper_context_sha256",
                "ledger_head_record_sha256",
                "decision_cycle_id",
                "decision_sha256",
                "account_id",
                "logical_agent_id",
                "agent_generation",
                "expected_account_version",
                "symbol",
                "authored_at",
                "valid_until",
                "action",
                "episode_id",
                "transition_id",
                "tranche_id",
                "role",
                "pre_state",
                "target_state",
                "position_delta",
                "evidence_delta",
                "activation",
                "hard_invalidation",
                "risk_budget",
                "command",
            }
        )
        if not isinstance(value, Mapping):
            raise PaperContractError("paper execution intent fields mismatch")
        version = value.get("schema_version")
        fields = legacy_fields if version == "1.2.0" else legacy_fields | {"bracket"}
        if frozenset(value) != fields:
            raise PaperContractError("paper execution intent fields mismatch")
        if (
            value["schema_id"] != "agent-trade-emotion.paper-execution-intent"
            or version not in {"1.2.0", "1.3.0"}
        ):
            raise PaperContractError("paper execution intent schema mismatch")
        return cls(
            **{
                **{
                    key: value[key]
                    for key in legacy_fields
                    - {"schema_id", "schema_version", "command"}
                },
                "command": (
                    None
                    if value["command"] is None
                    else PaperCommandV1.from_dict(value["command"])
                ),
                "bracket": (
                    None
                    if version == "1.2.0" or value["bracket"] is None
                    else PaperBracketV1.from_dict(value["bracket"])
                ),
                "wire_schema_version": version,
            }
        )


@dataclass(frozen=True, slots=True)
class PaperCostModelV1:
    model_id: str
    maker_fee_bps: str
    taker_fee_bps: str
    market_impact_bps: str
    funding_status: str = "UNKNOWN"
    borrow_status: str = "UNKNOWN"
    effective_from: str | None = None
    effective_to: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _identifier(self.model_id, field="model_id"))
        for field_name in ("maker_fee_bps", "taker_fee_bps", "market_impact_bps"):
            object.__setattr__(
                self,
                field_name,
                _decimal_text(getattr(self, field_name), field=field_name, nonnegative=True),
            )
        if Decimal(self.market_impact_bps) >= Decimal("10000"):
            raise PaperContractError("market_impact_bps must be less than 10000")
        if (
            self.funding_status not in PAPER_UNSOURCED_COST_STATUSES
            or self.borrow_status not in PAPER_UNSOURCED_COST_STATUSES
        ):
            raise PaperContractError(
                "funding/borrow without an amount source must remain UNKNOWN or NOT_APPLICABLE"
            )
        if self.effective_from is not None:
            object.__setattr__(
                self,
                "effective_from",
                _timestamp(self.effective_from, field="cost_model.effective_from"),
            )
        if self.effective_to is not None:
            object.__setattr__(
                self,
                "effective_to",
                _timestamp(self.effective_to, field="cost_model.effective_to"),
            )
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and datetime.fromisoformat(self.effective_to.replace("Z", "+00:00"))
            <= datetime.fromisoformat(self.effective_from.replace("Z", "+00:00"))
        ):
            raise PaperContractError("cost model effective window must be forward")

    @property
    def model_digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "maker_fee_bps": self.maker_fee_bps,
            "taker_fee_bps": self.taker_fee_bps,
            "market_impact_bps": self.market_impact_bps,
            "funding_status": self.funding_status,
            "borrow_status": self.borrow_status,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
        }


@dataclass(frozen=True, slots=True)
class PaperMarketSliceV1:
    symbol: str
    observed_at: str
    available_at: str
    source_sha256: str
    granularity: str
    path_status: str
    bid: str | None = None
    ask: str | None = None
    last: str | None = None
    low: str | None = None
    high: str | None = None
    available_quantity: str | None = None
    mark: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, field="observed_at"))
        object.__setattr__(self, "available_at", _timestamp(self.available_at, field="available_at"))
        if datetime.fromisoformat(self.available_at.replace("Z", "+00:00")) < datetime.fromisoformat(
            self.observed_at.replace("Z", "+00:00")
        ):
            raise PaperContractError("available_at must not precede observed_at")
        object.__setattr__(self, "source_sha256", _sha256(self.source_sha256, field="source_sha256"))
        if self.granularity not in {"QUOTE", "TRADE", "BAR", "MARK"}:
            raise PaperContractError("granularity is unsupported")
        if self.path_status not in {"ORDERED", "UNORDERED"}:
            raise PaperContractError("path_status is unsupported")
        for field_name in ("bid", "ask", "last", "low", "high", "available_quantity", "mark"):
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(getattr(self, field_name), field=field_name, positive=True),
            )
        if self.bid is not None and self.ask is not None and Decimal(self.bid) > Decimal(self.ask):
            raise PaperContractError("bid must not exceed ask")
        if self.low is not None and self.high is not None and Decimal(self.low) > Decimal(self.high):
            raise PaperContractError("low must not exceed high")
        if self.granularity == "QUOTE" and (self.bid is None or self.ask is None):
            raise PaperContractError("QUOTE slice requires bid and ask")
        if self.granularity == "BAR" and (self.low is None or self.high is None):
            raise PaperContractError("BAR slice requires low and high")
        if self.granularity == "MARK" and self.mark is None:
            raise PaperContractError("MARK slice requires mark")

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class OrderTruthV1:
    order_id: str
    command_id: str
    account_id: str
    logical_agent_id: str
    symbol: str
    command_type: str
    side: str
    original_quantity: str
    filled_quantity: str
    remaining_quantity: str
    limit_price: str | None
    trigger_price: str | None
    reduce_only: bool
    time_in_force: str
    expires_at: str | None
    cost_model_id: str
    state: str
    created_at: str
    updated_at: str
    resolution_reason: str | None = None
    cost_model_digest: str = "0" * 64

    def __post_init__(self) -> None:
        for field_name in ("order_id", "command_id", "account_id", "logical_agent_id"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field=field_name))
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        if self.command_type not in PAPER_COMMAND_TYPES - {"CANCEL"}:
            raise PaperContractError("order command_type is unsupported")
        if self.side not in PAPER_SIDES:
            raise PaperContractError("order side must be BUY or SELL")
        original = Decimal(_decimal_text(self.original_quantity, field="original_quantity", positive=True))
        filled = Decimal(_decimal_text(self.filled_quantity, field="filled_quantity", nonnegative=True))
        remaining = Decimal(_decimal_text(self.remaining_quantity, field="remaining_quantity", nonnegative=True))
        if filled + remaining != original:
            raise PaperContractError("filled_quantity + remaining_quantity must equal original_quantity")
        object.__setattr__(self, "limit_price", _optional_decimal(self.limit_price, field="limit_price", positive=True))
        object.__setattr__(self, "trigger_price", _optional_decimal(self.trigger_price, field="trigger_price", positive=True))
        if type(self.reduce_only) is not bool:
            raise PaperContractError("order reduce_only must be boolean")
        if self.time_in_force not in PAPER_TIME_IN_FORCE:
            raise PaperContractError("order time_in_force must be GTC or IOC")
        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", _timestamp(self.expires_at, field="expires_at"))
        object.__setattr__(self, "cost_model_id", _identifier(self.cost_model_id, field="cost_model_id"))
        object.__setattr__(
            self,
            "cost_model_digest",
            _sha256(self.cost_model_digest, field="order.cost_model_digest"),
        )
        if self.state not in PAPER_ORDER_STATES:
            raise PaperContractError("order state is unsupported")
        object.__setattr__(self, "created_at", _timestamp(self.created_at, field="created_at"))
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at, field="updated_at"))
        if self.resolution_reason is not None and (
            not isinstance(self.resolution_reason, str) or not self.resolution_reason.strip()
        ):
            raise PaperContractError("resolution_reason must be non-empty when present")

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "command_id": self.command_id,
            "account_id": self.account_id,
            "logical_agent_id": self.logical_agent_id,
            "symbol": self.symbol,
            "command_type": self.command_type,
            "side": self.side,
            "original_quantity": self.original_quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "limit_price": self.limit_price,
            "trigger_price": self.trigger_price,
            "reduce_only": self.reduce_only,
            "time_in_force": self.time_in_force,
            "expires_at": self.expires_at,
            "cost_model_id": self.cost_model_id,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolution_reason": self.resolution_reason,
            "cost_model_digest": self.cost_model_digest,
        }


@dataclass(frozen=True, slots=True)
class FillEventV1:
    fill_id: str
    order_id: str
    command_id: str
    account_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    fee: str
    spread_cost: str
    impact_cost: str
    funding_cost: str | None
    funding_cost_status: str
    borrow_cost: str | None
    borrow_cost_status: str
    realized_pnl: str
    observed_at: str
    source_sha256: str
    cost_model_id: str
    instrument_spec_id: str
    quantity_basis: str
    contract_multiplier: str
    notional: str
    execution_status: str = "PAPER_MODELED_LEGACY"
    cost_model_digest: str = "0" * 64
    execution_mid_price: str | None = None
    touch_price: str | None = None
    fee_status: str = "MODELED_LEGACY"
    spread_cost_status: str = "MODELED_LEGACY"
    impact_cost_status: str = "MODELED_LEGACY"
    arrival_mid_price: str | None = None
    timing_cost: str | None = None
    timing_cost_status: str = "UNKNOWN"

    def __post_init__(self) -> None:
        for field_name in ("fill_id", "order_id", "command_id", "account_id", "cost_model_id"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field=field_name))
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        if self.side not in PAPER_SIDES:
            raise PaperContractError("fill side must be BUY or SELL")
        object.__setattr__(self, "quantity", _decimal_text(self.quantity, field="quantity", positive=True))
        object.__setattr__(self, "price", _decimal_text(self.price, field="price", positive=True))
        for field_name in ("fee", "spread_cost", "impact_cost"):
            object.__setattr__(
                self,
                field_name,
                _decimal_text(getattr(self, field_name), field=field_name, nonnegative=True),
            )
        for field_name in ("funding_cost", "borrow_cost"):
            status = getattr(self, f"{field_name}_status")
            if status not in PAPER_UNSOURCED_COST_STATUSES:
                raise PaperContractError(
                    f"{field_name} without source must remain UNKNOWN or NOT_APPLICABLE"
                )
            if getattr(self, field_name) is not None:
                raise PaperContractError(
                    f"unknown or N/A {field_name} must be null, not an assumed zero"
                )
        object.__setattr__(self, "realized_pnl", _decimal_text(self.realized_pnl, field="realized_pnl"))
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, field="observed_at"))
        object.__setattr__(self, "source_sha256", _sha256(self.source_sha256, field="source_sha256"))
        object.__setattr__(
            self,
            "instrument_spec_id",
            _identifier(self.instrument_spec_id, field="instrument_spec_id"),
        )
        if self.quantity_basis not in PAPER_QUANTITY_BASES:
            raise PaperContractError("fill quantity_basis is unsupported")
        object.__setattr__(
            self,
            "contract_multiplier",
            _decimal_text(
                self.contract_multiplier,
                field="fill.contract_multiplier",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "notional",
            _decimal_text(self.notional, field="fill.notional", positive=True),
        )
        if Decimal(self.notional) != (
            Decimal(self.price) * Decimal(self.quantity) * Decimal(self.contract_multiplier)
        ):
            raise PaperContractError("fill notional must bind price, quantity, and multiplier")
        if self.execution_status not in {
            "PAPER_MODELED_ARITHMETIC",
            "PAPER_MODELED_LEGACY",
        }:
            raise PaperContractError("paper fill execution_status is unsupported")
        object.__setattr__(
            self,
            "cost_model_digest",
            _sha256(self.cost_model_digest, field="fill.cost_model_digest"),
        )
        object.__setattr__(
            self,
            "execution_mid_price",
            _optional_decimal(
                self.execution_mid_price,
                field="fill.execution_mid_price",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "touch_price",
            _optional_decimal(self.touch_price, field="fill.touch_price", positive=True),
        )
        if self.execution_status == "PAPER_MODELED_ARITHMETIC" and self.touch_price is None:
            raise PaperContractError("modeled paper fill requires touch_price")
        expected_status = "MODELED" if self.execution_status == "PAPER_MODELED_ARITHMETIC" else "MODELED_LEGACY"
        for field_name in ("fee_status", "spread_cost_status", "impact_cost_status"):
            if getattr(self, field_name) != expected_status:
                raise PaperContractError(f"{field_name} does not match execution status")
        object.__setattr__(
            self,
            "arrival_mid_price",
            _optional_decimal(
                self.arrival_mid_price,
                field="fill.arrival_mid_price",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "timing_cost",
            _optional_decimal(self.timing_cost, field="fill.timing_cost"),
        )
        if self.timing_cost_status not in {"MODELED", "UNKNOWN"}:
            raise PaperContractError("timing_cost_status is unsupported")
        if self.timing_cost_status == "UNKNOWN" and (
            self.arrival_mid_price is not None or self.timing_cost is not None
        ):
            raise PaperContractError("unknown timing cost cannot carry an amount")
        if self.timing_cost_status == "MODELED" and (
            self.arrival_mid_price is None or self.timing_cost is None
        ):
            raise PaperContractError("modeled timing cost requires arrival price and amount")

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class PaperPositionV1:
    symbol: str
    quantity: str
    average_entry_price: str
    margin_allocated: str
    realized_pnl: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        quantity = _decimal_text(self.quantity, field="position.quantity")
        average = _decimal_text(
            self.average_entry_price,
            field="position.average_entry_price",
            nonnegative=True,
        )
        if Decimal(quantity) == 0 and Decimal(average) != 0:
            raise PaperContractError("flat position average_entry_price must be zero")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "average_entry_price", average)
        object.__setattr__(
            self,
            "margin_allocated",
            _decimal_text(
                self.margin_allocated,
                field="position.margin_allocated",
                nonnegative=True,
            ),
        )
        if Decimal(quantity) == 0 and Decimal(self.margin_allocated) != 0:
            raise PaperContractError("flat position margin_allocated must be zero")
        object.__setattr__(self, "realized_pnl", _decimal_text(self.realized_pnl, field="position.realized_pnl"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_entry_price": self.average_entry_price,
            "margin_allocated": self.margin_allocated,
            "realized_pnl": self.realized_pnl,
        }


@dataclass(frozen=True, slots=True)
class InstrumentSpecV1:
    """Frozen product economics used by every paper calculation.

    ``quantity_basis`` says whether order quantity is already expressed in base
    units or in venue contracts.  ``contract_multiplier`` converts either unit
    into the base exposure used for notional, PnL, fees, and margin.  A venue
    product whose multiplier is not known must therefore not open an account.
    Liquidation-risk inputs are a separately identified modeled parameter set;
    they never inherit the raw-bound status of the product economics.
    """

    instrument_spec_id: str
    symbol: str
    account_mode: str
    quote_currency: str
    contract_multiplier: str
    quantity_basis: str
    maintenance_margin_rate: str | None = None
    maintenance_margin_deduction: str | None = None
    liquidation_fee_reserve: str | None = None
    risk_parameter_status: str = "UNKNOWN"
    risk_parameter_set_id: str | None = None
    parameter_status: str = "MODELED_UNVERIFIED"
    parameter_source_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_spec_id",
            _identifier(self.instrument_spec_id, field="instrument_spec_id"),
        )
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        if self.account_mode not in PAPER_ACCOUNT_MODES:
            raise PaperContractError("instrument account_mode is unsupported")
        object.__setattr__(self, "quote_currency", _symbol(self.quote_currency))
        object.__setattr__(
            self,
            "contract_multiplier",
            _decimal_text(
                self.contract_multiplier,
                field="contract_multiplier",
                positive=True,
            ),
        )
        if self.quantity_basis not in PAPER_QUANTITY_BASES:
            raise PaperContractError("quantity_basis is unsupported")
        if self.quantity_basis == "BASE_UNITS" and Decimal(self.contract_multiplier) != 1:
            raise PaperContractError(
                "BASE_UNITS quantity_basis requires contract_multiplier equal to one"
            )
        for field_name in (
            "maintenance_margin_rate",
            "maintenance_margin_deduction",
            "liquidation_fee_reserve",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(getattr(self, field_name), field=field_name, positive=False),
            )
            if getattr(self, field_name) is not None and Decimal(getattr(self, field_name)) < 0:
                raise PaperContractError(f"{field_name} must be nonnegative")
        risk_values = (
            self.maintenance_margin_rate,
            self.maintenance_margin_deduction,
            self.liquidation_fee_reserve,
        )
        if (
            self.maintenance_margin_rate is not None
            and Decimal(self.maintenance_margin_rate) > 1
        ):
            raise PaperContractError("maintenance_margin_rate must not exceed one")
        if self.risk_parameter_status not in {"UNKNOWN", "MODELED_EXPLICIT_PARAMETERS"}:
            raise PaperContractError("risk_parameter_status is unsupported")
        if self.risk_parameter_status == "UNKNOWN" and any(item is not None for item in risk_values):
            raise PaperContractError("unknown risk parameters cannot carry amounts")
        if self.risk_parameter_status == "UNKNOWN" and self.risk_parameter_set_id is not None:
            raise PaperContractError("unknown risk parameters cannot claim a parameter set")
        if self.risk_parameter_status == "MODELED_EXPLICIT_PARAMETERS" and any(
            item is None for item in risk_values
        ):
            raise PaperContractError("modeled risk parameters require all amounts")
        if self.risk_parameter_status == "MODELED_EXPLICIT_PARAMETERS":
            object.__setattr__(
                self,
                "risk_parameter_set_id",
                _identifier(
                    self.risk_parameter_set_id,
                    field="risk_parameter_set_id",
                ),
            )
        if self.parameter_status not in {"OBSERVED_RAW_BOUND", "MODELED_UNVERIFIED"}:
            raise PaperContractError("instrument parameter_status is unsupported")
        if self.parameter_status == "OBSERVED_RAW_BOUND":
            object.__setattr__(
                self,
                "parameter_source_sha256",
                _sha256(
                    self.parameter_source_sha256,
                    field="instrument.parameter_source_sha256",
                ),
            )
        elif self.parameter_source_sha256 is not None:
            raise PaperContractError("unverified instrument parameters cannot claim a raw source")

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_spec_id": self.instrument_spec_id,
            "symbol": self.symbol,
            "account_mode": self.account_mode,
            "quote_currency": self.quote_currency,
            "contract_multiplier": self.contract_multiplier,
            "quantity_basis": self.quantity_basis,
            "maintenance_margin_rate": self.maintenance_margin_rate,
            "maintenance_margin_deduction": self.maintenance_margin_deduction,
            "liquidation_fee_reserve": self.liquidation_fee_reserve,
            "risk_parameter_status": self.risk_parameter_status,
            "risk_parameter_set_id": self.risk_parameter_set_id,
            "parameter_status": self.parameter_status,
            "parameter_source_sha256": self.parameter_source_sha256,
        }


def _static_no_transition_reference(
    intent: PaperExecutionIntentV1,
    instrument_spec: InstrumentSpecV1,
    cost_model: PaperCostModelV1,
) -> dict[str, Any]:
    bracket = intent.bracket
    if bracket is None:
        raise PaperContractError("static comparator requires a protected bracket")
    entry = bracket.entry
    stop = bracket.protective_stop
    return {
        "episode_id": intent.episode_id,
        "decision_cycle_id": intent.decision_cycle_id,
        "entry_order_id": entry.command_id,
        "entry_side": entry.side,
        "entry_price": entry.limit_price,
        "initial_quantity": entry.quantity,
        "entry_expires_at": entry.expires_at,
        "intent_valid_until": intent.valid_until,
        "protective_stop": {
            "order_id": stop.command_id,
            "price": stop.trigger_price,
            "quantity": stop.quantity,
        },
        "take_profits": [
            {
                "order_id": target.command_id,
                "price": target.trigger_price,
                "quantity": target.quantity,
            }
            for target in bracket.take_profits
        ],
        "contract_multiplier": instrument_spec.contract_multiplier,
        "quantity_basis": instrument_spec.quantity_basis,
        "cost_model_id": cost_model.model_id,
        "cost_model_sha256": cost_model.model_digest,
    }


@dataclass(frozen=True, slots=True)
class StaticNoTransitionComparatorV1:
    """Pre-outcome idealized diagnostic frozen beside the first episode bracket.

    This is neither a paper command nor execution truth.  Its hypothetical
    full-size hold has no matched same-fill/cost actual arm, so it cannot
    support an actual-versus-static superiority conclusion.  Later intents in
    the same episode link back to this one root and are not independent samples.
    """

    comparator_id: str
    policy_id: str
    policy_sha256: str
    schema_sha256: str
    preregistered_at: str
    account_pre_version: int
    account_pre_head_record_sha256: str
    intent_sha256: str
    bracket_sha256: str
    execution_intent: Mapping[str, Any]
    reference: Mapping[str, Any]
    instrument_spec: Mapping[str, Any]
    cost_model: Mapping[str, Any]
    cost_model_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "comparator_id",
            _identifier(self.comparator_id, field="comparator_id"),
        )
        if self.policy_id != STATIC_NO_TRANSITION_POLICY_ID:
            raise PaperContractError("static comparator policy mismatch")
        if self.policy_sha256 != STATIC_NO_TRANSITION_POLICY_SHA256:
            raise PaperContractError("static comparator policy digest mismatch")
        if self.schema_sha256 != STATIC_NO_TRANSITION_SCHEMA_SHA256:
            raise PaperContractError("static comparator schema digest mismatch")
        preregistered_at = _timestamp(
            self.preregistered_at, field="comparator.preregistered_at"
        )
        if type(self.account_pre_version) is not int or self.account_pre_version < 1:
            raise PaperContractError("static comparator account_pre_version must be >= 1")
        object.__setattr__(
            self,
            "account_pre_head_record_sha256",
            _sha256(
                self.account_pre_head_record_sha256,
                field="comparator.account_pre_head_record_sha256",
            ),
        )
        object.__setattr__(
            self,
            "intent_sha256",
            _sha256(self.intent_sha256, field="comparator.intent_sha256"),
        )
        object.__setattr__(
            self,
            "bracket_sha256",
            _sha256(self.bracket_sha256, field="comparator.bracket_sha256"),
        )
        object.__setattr__(
            self,
            "cost_model_sha256",
            _sha256(
                self.cost_model_sha256,
                field="comparator.cost_model_sha256",
            ),
        )
        if not isinstance(self.execution_intent, Mapping):
            raise PaperContractError("static comparator intent must be an object")
        intent = PaperExecutionIntentV1.from_dict(self.execution_intent)
        bracket = intent.bracket
        if (
            bracket is None
            or intent.action not in PAPER_BRACKET_ELIGIBLE_ACTIONS
            or Decimal(intent.pre_state["signed_quantity"]) != 0
        ):
            raise PaperContractError(
                "static comparator requires a flat protected bracket"
            )
        if self.comparator_id != f"static-{intent.intent_sha256[:32]}":
            raise PaperContractError("static comparator id mismatch")
        if self.intent_sha256 != intent.intent_sha256:
            raise PaperContractError("static comparator intent digest mismatch")
        if self.bracket_sha256 != canonical_digest(bracket.to_dict()):
            raise PaperContractError("static comparator bracket digest mismatch")
        if (
            self.account_pre_version != intent.expected_account_version
            or self.account_pre_head_record_sha256
            != intent.ledger_head_record_sha256
        ):
            raise PaperContractError("static comparator account head mismatch")
        preregistered = datetime.fromisoformat(
            preregistered_at.replace("Z", "+00:00")
        )
        if not (
            datetime.fromisoformat(intent.authored_at.replace("Z", "+00:00"))
            <= preregistered
            <= datetime.fromisoformat(intent.valid_until.replace("Z", "+00:00"))
        ):
            raise PaperContractError("static comparator registration time mismatch")
        if not isinstance(self.instrument_spec, Mapping):
            raise PaperContractError("static comparator instrument must be an object")
        instrument_spec = InstrumentSpecV1(**dict(self.instrument_spec))
        if instrument_spec.symbol != intent.symbol:
            raise PaperContractError("static comparator instrument mismatch")
        if not isinstance(self.cost_model, Mapping):
            raise PaperContractError("static comparator cost model must be an object")
        cost_model = PaperCostModelV1(**dict(self.cost_model))
        if (
            cost_model.model_id != bracket.entry.cost_model_id
            or cost_model.model_digest != self.cost_model_sha256
        ):
            raise PaperContractError("static comparator cost model mismatch")
        expected_reference = _static_no_transition_reference(
            intent, instrument_spec, cost_model
        )
        if (
            not isinstance(self.reference, Mapping)
            or _thaw_json(self.reference) != expected_reference
        ):
            raise PaperContractError("static comparator reference mismatch")
        for field_name in (
            "execution_intent",
            "reference",
            "instrument_spec",
            "cost_model",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_json(getattr(self, field_name), field=f"comparator.{field_name}"),
            )

    @property
    def comparator_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def create(
        cls,
        *,
        execution_intent: PaperExecutionIntentV1,
        preregistered_at: str,
        account_pre_version: int,
        account_pre_head_record_sha256: str,
        instrument_spec: InstrumentSpecV1,
        cost_model: PaperCostModelV1,
    ) -> "StaticNoTransitionComparatorV1":
        bracket = execution_intent.bracket
        if bracket is None:
            raise PaperContractError("static comparator requires a protected bracket")
        return cls(
            comparator_id=f"static-{execution_intent.intent_sha256[:32]}",
            policy_id=STATIC_NO_TRANSITION_POLICY_ID,
            policy_sha256=STATIC_NO_TRANSITION_POLICY_SHA256,
            schema_sha256=STATIC_NO_TRANSITION_SCHEMA_SHA256,
            preregistered_at=preregistered_at,
            account_pre_version=account_pre_version,
            account_pre_head_record_sha256=account_pre_head_record_sha256,
            intent_sha256=execution_intent.intent_sha256,
            bracket_sha256=canonical_digest(bracket.to_dict()),
            execution_intent=execution_intent.to_dict(),
            reference=_static_no_transition_reference(
                execution_intent, instrument_spec, cost_model
            ),
            instrument_spec=instrument_spec.to_dict(),
            cost_model=cost_model.to_dict(),
            cost_model_sha256=cost_model.model_digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.static-no-transition-comparator",
            "schema_version": "1.0.0",
            "comparator_id": self.comparator_id,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "schema_sha256": self.schema_sha256,
            "preregistered_at": self.preregistered_at,
            "account_pre_version": self.account_pre_version,
            "account_pre_head_record_sha256": self.account_pre_head_record_sha256,
            "intent_sha256": self.intent_sha256,
            "bracket_sha256": self.bracket_sha256,
            "execution_intent": _thaw_json(self.execution_intent),
            "reference": _thaw_json(self.reference),
            "instrument_spec": _thaw_json(self.instrument_spec),
            "cost_model": _thaw_json(self.cost_model),
            "cost_model_sha256": self.cost_model_sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "StaticNoTransitionComparatorV1":
        expected = {
            "schema_id",
            "schema_version",
            "comparator_id",
            "policy_id",
            "policy_sha256",
            "schema_sha256",
            "preregistered_at",
            "account_pre_version",
            "account_pre_head_record_sha256",
            "intent_sha256",
            "bracket_sha256",
            "execution_intent",
            "reference",
            "instrument_spec",
            "cost_model",
            "cost_model_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PaperContractError("static comparator fields mismatch")
        if (
            value["schema_id"]
            != "agent-trade-emotion.static-no-transition-comparator"
            or value["schema_version"] != "1.0.0"
        ):
            raise PaperContractError("static comparator schema mismatch")
        return cls(
            **{
                key: value[key]
                for key in expected - {"schema_id", "schema_version"}
            }
        )


@dataclass(frozen=True, slots=True)
class StaticNoTransitionEpisodeLinkV1:
    """Bind a later episode intent to its single non-independent root reference."""

    status: str
    episode_id: str
    continuation_index: int
    root_comparator_id: str
    root_comparator_sha256: str
    root_intent_sha256: str
    current_intent_sha256: str
    comparison_status: str
    comparison_reason: str

    def __post_init__(self) -> None:
        if self.status != "ONGOING_NOT_INDEPENDENT":
            raise PaperContractError("static comparator linkage status mismatch")
        object.__setattr__(
            self, "episode_id", _identifier(self.episode_id, field="episode_id")
        )
        if type(self.continuation_index) is not int or self.continuation_index < 1:
            raise PaperContractError(
                "static comparator continuation_index must be >= 1"
            )
        object.__setattr__(
            self,
            "root_comparator_id",
            _identifier(self.root_comparator_id, field="root_comparator_id"),
        )
        for field_name in (
            "root_comparator_sha256",
            "root_intent_sha256",
            "current_intent_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field=field_name),
            )
        if self.root_intent_sha256 == self.current_intent_sha256:
            raise PaperContractError(
                "static comparator linkage cannot relabel the root intent"
            )
        if self.comparison_status != "NOT_COMPARABLE":
            raise PaperContractError(
                "static comparator linkage must remain NOT_COMPARABLE"
            )
        if self.comparison_reason != "OVERLAPPING_EPISODE_SEGMENT_NOT_INDEPENDENT":
            raise PaperContractError("static comparator linkage reason mismatch")

    @classmethod
    def create(
        cls,
        *,
        root_comparator: StaticNoTransitionComparatorV1,
        current_intent: PaperExecutionIntentV1,
        continuation_index: int,
    ) -> "StaticNoTransitionEpisodeLinkV1":
        root_intent = PaperExecutionIntentV1.from_dict(
            root_comparator.execution_intent
        )
        if root_intent.episode_id != current_intent.episode_id:
            raise PaperContractError("static comparator linkage episode mismatch")
        return cls(
            status="ONGOING_NOT_INDEPENDENT",
            episode_id=current_intent.episode_id,
            continuation_index=continuation_index,
            root_comparator_id=root_comparator.comparator_id,
            root_comparator_sha256=root_comparator.comparator_sha256,
            root_intent_sha256=root_comparator.intent_sha256,
            current_intent_sha256=current_intent.intent_sha256,
            comparison_status="NOT_COMPARABLE",
            comparison_reason="OVERLAPPING_EPISODE_SEGMENT_NOT_INDEPENDENT",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.static-no-transition-episode-link",
            "schema_version": "1.0.0",
            "status": self.status,
            "episode_id": self.episode_id,
            "continuation_index": self.continuation_index,
            "root_comparator_id": self.root_comparator_id,
            "root_comparator_sha256": self.root_comparator_sha256,
            "root_intent_sha256": self.root_intent_sha256,
            "current_intent_sha256": self.current_intent_sha256,
            "comparison_status": self.comparison_status,
            "comparison_reason": self.comparison_reason,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "StaticNoTransitionEpisodeLinkV1":
        expected = {
            "schema_id",
            "schema_version",
            "status",
            "episode_id",
            "continuation_index",
            "root_comparator_id",
            "root_comparator_sha256",
            "root_intent_sha256",
            "current_intent_sha256",
            "comparison_status",
            "comparison_reason",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PaperContractError("static comparator linkage fields mismatch")
        if (
            value["schema_id"]
            != "agent-trade-emotion.static-no-transition-episode-link"
            or value["schema_version"] != "1.0.0"
        ):
            raise PaperContractError("static comparator linkage schema mismatch")
        return cls(
            **{
                key: value[key]
                for key in expected - {"schema_id", "schema_version"}
            }
        )

    def verifies(
        self,
        *,
        root_comparator: StaticNoTransitionComparatorV1,
        current_intent: PaperExecutionIntentV1,
        continuation_index: int,
    ) -> bool:
        try:
            expected = self.create(
                root_comparator=root_comparator,
                current_intent=current_intent,
                continuation_index=continuation_index,
            )
        except PaperContractError:
            return False
        return self == expected


@dataclass(frozen=True, slots=True)
class CarryAccrualV1:
    accrual_id: str
    account_id: str
    symbol: str
    kind: str
    status: str
    amount: str | None
    rate: str | None
    reference_price: str | None
    position_quantity: str
    effective_at: str
    available_at: str
    rate_source_sha256: str | None
    price_source_sha256: str | None
    reason: str
    coverage_status: str
    coverage_start_at: str
    coverage_end_at: str
    settlement_model: "FundingSettlementModelV1 | Mapping[str, Any] | None" = None
    price_proxy_observed_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "accrual_id", _identifier(self.accrual_id, field="accrual_id"))
        object.__setattr__(self, "account_id", _identifier(self.account_id, field="account_id"))
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        if self.kind not in {"FUNDING", "BORROW"}:
            raise PaperContractError("carry kind is unsupported")
        if self.status not in PAPER_COST_STATUSES:
            raise PaperContractError("carry status is unsupported")
        object.__setattr__(self, "effective_at", _timestamp(self.effective_at, field="carry.effective_at"))
        object.__setattr__(self, "available_at", _timestamp(self.available_at, field="carry.available_at"))
        if datetime.fromisoformat(self.available_at.replace("Z", "+00:00")) < datetime.fromisoformat(
            self.effective_at.replace("Z", "+00:00")
        ):
            raise PaperContractError("carry available_at must not precede effective_at")
        object.__setattr__(self, "amount", _optional_decimal(self.amount, field="carry.amount"))
        object.__setattr__(self, "rate", _optional_decimal(self.rate, field="carry.rate"))
        object.__setattr__(
            self,
            "reference_price",
            _optional_decimal(self.reference_price, field="carry.reference_price", positive=True),
        )
        object.__setattr__(
            self,
            "position_quantity",
            _decimal_text(self.position_quantity, field="carry.position_quantity"),
        )
        for field_name in ("rate_source_sha256", "price_source_sha256"):
            value = getattr(self, field_name)
            if value is None:
                continue
            object.__setattr__(
                self,
                field_name,
                _sha256(value, field=f"carry.{field_name}"),
            )
        if self.status in {"UNKNOWN", "NOT_APPLICABLE"}:
            if any(
                item is not None
                for item in (
                    self.amount,
                    self.rate,
                    self.reference_price,
                    self.rate_source_sha256,
                    self.price_source_sha256,
                )
            ):
                raise PaperContractError("unknown or N/A carry cannot carry sourced amounts")
        elif any(
            item is None
            for item in (
                self.amount,
                self.rate,
                self.reference_price,
                self.rate_source_sha256,
                self.price_source_sha256,
            )
        ):
            raise PaperContractError("modeled or observed carry requires amount and source")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise PaperContractError("carry reason must be non-empty")
        if self.coverage_status not in PAPER_CARRY_COVERAGE_STATUSES:
            raise PaperContractError("carry coverage_status is unsupported")
        if (self.status == "NOT_APPLICABLE") != (
            self.coverage_status == "NOT_APPLICABLE"
        ):
            raise PaperContractError(
                "carry status and coverage_status must agree on NOT_APPLICABLE"
            )
        object.__setattr__(
            self,
            "coverage_start_at",
            _timestamp(self.coverage_start_at, field="carry.coverage_start_at"),
        )
        object.__setattr__(
            self,
            "coverage_end_at",
            _timestamp(self.coverage_end_at, field="carry.coverage_end_at"),
        )
        if datetime.fromisoformat(self.coverage_end_at.replace("Z", "+00:00")) < datetime.fromisoformat(
            self.coverage_start_at.replace("Z", "+00:00")
        ):
            raise PaperContractError("carry coverage window must be forward")
        effective_at = datetime.fromisoformat(self.effective_at.replace("Z", "+00:00"))
        coverage_start_at = datetime.fromisoformat(
            self.coverage_start_at.replace("Z", "+00:00")
        )
        coverage_end_at = datetime.fromisoformat(
            self.coverage_end_at.replace("Z", "+00:00")
        )
        if not coverage_start_at <= effective_at <= coverage_end_at:
            raise PaperContractError(
                "carry coverage window must contain effective_at"
            )
        if self.coverage_status == "COMPLETE" and self.status not in {"MODELED", "OBSERVED"}:
            raise PaperContractError("complete carry coverage requires a sourced amount")
        model = self.settlement_model
        if isinstance(model, Mapping):
            model = FundingSettlementModelV1.from_dict(model)
            object.__setattr__(self, "settlement_model", model)
        if model is None:
            if self.price_proxy_observed_at is not None:
                raise PaperContractError(
                    "carry price proxy time requires a settlement model"
                )
        else:
            if not isinstance(model, FundingSettlementModelV1):
                raise PaperContractError("carry settlement_model is invalid")
            if self.kind != "FUNDING" or self.status != "OBSERVED":
                raise PaperContractError(
                    "settlement model is only valid for observed funding"
                )
            object.__setattr__(
                self,
                "price_proxy_observed_at",
                _timestamp(
                    self.price_proxy_observed_at,
                    field="carry.price_proxy_observed_at",
                ),
            )
            proxy_at = datetime.fromisoformat(
                self.price_proxy_observed_at.replace("Z", "+00:00")
            )
            if proxy_at > effective_at:
                raise PaperContractError(
                    "funding price proxy must be observable by effective_at"
                )
            if not (
                datetime.fromisoformat(model.effective_from.replace("Z", "+00:00"))
                <= effective_at
                <= datetime.fromisoformat(model.effective_to.replace("Z", "+00:00"))
            ):
                raise PaperContractError(
                    "funding settlement model is not effective at accrual"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            field: (
                self.settlement_model.to_dict()
                if field == "settlement_model" and self.settlement_model is not None
                else getattr(self, field)
            )
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class FundingSettlementModelV1:
    """Frozen method used to turn an observed funding row into paper cashflow."""

    model_id: str
    model_version: str
    price_proxy_method: str
    cost_model_id: str
    cost_model_digest: str
    effective_from: str
    effective_to: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _identifier(self.model_id, field="funding_model.model_id"))
        object.__setattr__(
            self,
            "model_version",
            _identifier(self.model_version, field="funding_model.model_version"),
        )
        if self.price_proxy_method != "LAST_CONFIRMED_15M_CLOSE_NOT_AFTER_EFFECTIVE_AT":
            raise PaperContractError("funding price_proxy_method is unsupported")
        object.__setattr__(
            self,
            "cost_model_id",
            _identifier(self.cost_model_id, field="funding_model.cost_model_id"),
        )
        object.__setattr__(
            self,
            "cost_model_digest",
            _sha256(
                self.cost_model_digest, field="funding_model.cost_model_digest"
            ),
        )
        object.__setattr__(
            self,
            "effective_from",
            _timestamp(self.effective_from, field="funding_model.effective_from"),
        )
        object.__setattr__(
            self,
            "effective_to",
            _timestamp(self.effective_to, field="funding_model.effective_to"),
        )
        if datetime.fromisoformat(self.effective_to.replace("Z", "+00:00")) <= datetime.fromisoformat(
            self.effective_from.replace("Z", "+00:00")
        ):
            raise PaperContractError("funding model effective window must be forward")

    @property
    def model_digest(self) -> str:
        return canonical_digest(self._digest_payload())

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "price_proxy_method": self.price_proxy_method,
            "cost_model_id": self.cost_model_id,
            "cost_model_digest": self.cost_model_digest,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._digest_payload(), "model_digest": self.model_digest}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FundingSettlementModelV1":
        expected = {
            "model_id",
            "model_version",
            "price_proxy_method",
            "cost_model_id",
            "cost_model_digest",
            "effective_from",
            "effective_to",
            "model_digest",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PaperContractError("funding settlement model fields mismatch")
        model = cls(**{key: value[key] for key in expected - {"model_digest"}})
        if value["model_digest"] != model.model_digest:
            raise PaperContractError("funding settlement model digest mismatch")
        return model


@dataclass(frozen=True, slots=True)
class FundingCoverageAdvanceV1:
    """Non-cash proof that every settled funding event in a window is booked."""

    advance_id: str
    account_id: str
    symbol: str
    coverage_start_at: str
    coverage_end_at: str
    available_at: str
    settlement_model: FundingSettlementModelV1 | Mapping[str, Any]
    funding_history_source_sha256: str
    price_proxy_source_sha256: str
    history_boundary_before_at: str
    history_boundary_after_at: str
    event_effective_ats: tuple[str, ...]
    event_accrual_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "advance_id", _identifier(self.advance_id, field="advance_id"))
        object.__setattr__(self, "account_id", _identifier(self.account_id, field="account_id"))
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        for field_name in (
            "coverage_start_at",
            "coverage_end_at",
            "available_at",
            "history_boundary_before_at",
            "history_boundary_after_at",
        ):
            object.__setattr__(
                self,
                field_name,
                _timestamp(getattr(self, field_name), field=f"funding_coverage.{field_name}"),
            )
        start = datetime.fromisoformat(self.coverage_start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(self.coverage_end_at.replace("Z", "+00:00"))
        available = datetime.fromisoformat(self.available_at.replace("Z", "+00:00"))
        before = datetime.fromisoformat(self.history_boundary_before_at.replace("Z", "+00:00"))
        after = datetime.fromisoformat(self.history_boundary_after_at.replace("Z", "+00:00"))
        if not before < start < end < after <= available:
            raise PaperContractError(
                "funding coverage requires strict before/after history boundaries"
            )
        model = self.settlement_model
        if isinstance(model, Mapping):
            model = FundingSettlementModelV1.from_dict(model)
            object.__setattr__(self, "settlement_model", model)
        if not isinstance(model, FundingSettlementModelV1):
            raise PaperContractError("funding coverage settlement_model is invalid")
        if not (
            datetime.fromisoformat(model.effective_from.replace("Z", "+00:00"))
            <= start
            and end
            <= datetime.fromisoformat(model.effective_to.replace("Z", "+00:00"))
        ):
            raise PaperContractError("funding model does not cover the coverage window")
        for field_name in (
            "funding_history_source_sha256",
            "price_proxy_source_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field=f"funding_coverage.{field_name}"),
            )
        effective_ats = tuple(
            _timestamp(value, field="funding_coverage.event_effective_ats")
            for value in self.event_effective_ats
        )
        if effective_ats != tuple(sorted(effective_ats, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))):
            raise PaperContractError("funding coverage event times must be ordered")
        if len(effective_ats) != len(set(effective_ats)):
            raise PaperContractError("funding coverage event times must be unique")
        if any(
            not start <= datetime.fromisoformat(value.replace("Z", "+00:00")) <= end
            for value in effective_ats
        ):
            raise PaperContractError("funding coverage event time is outside window")
        accrual_hashes = tuple(
            _sha256(value, field="funding_coverage.event_accrual_sha256s")
            for value in self.event_accrual_sha256s
        )
        if len(effective_ats) != len(accrual_hashes):
            raise PaperContractError("funding coverage event binding lengths differ")
        object.__setattr__(self, "event_effective_ats", effective_ats)
        object.__setattr__(self, "event_accrual_sha256s", accrual_hashes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "advance_id": self.advance_id,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "coverage_start_at": self.coverage_start_at,
            "coverage_end_at": self.coverage_end_at,
            "available_at": self.available_at,
            "settlement_model": self.settlement_model.to_dict(),
            "funding_history_source_sha256": self.funding_history_source_sha256,
            "price_proxy_source_sha256": self.price_proxy_source_sha256,
            "history_boundary_before_at": self.history_boundary_before_at,
            "history_boundary_after_at": self.history_boundary_after_at,
            "event_effective_ats": list(self.event_effective_ats),
            "event_accrual_sha256s": list(self.event_accrual_sha256s),
        }


@dataclass(frozen=True, slots=True)
class PaperAccountVersionV1:
    account_id: str
    version: int
    account_mode: str
    owner_logical_agent_id: str
    base_currency: str
    permitted_symbol: str
    max_leverage: str
    instrument_spec: InstrumentSpecV1
    owner_agent_generation: int
    initial_balance: str
    cash_balance: str
    reserved_margin: str
    realized_pnl: str
    fees_paid: str
    funding_paid: str
    borrow_paid: str
    carry_coverage_status: str
    funding_coverage_status: str
    borrow_coverage_status: str
    funding_coverage_start_at: str | None
    funding_coverage_end_at: str | None
    borrow_coverage_start_at: str | None
    borrow_coverage_end_at: str | None
    positions: tuple[PaperPositionV1, ...]
    orders: tuple[OrderTruthV1, ...]
    applied_command_ids: tuple[str, ...]
    last_event_id: str
    last_fact_at: str
    last_market_observed_at: str | None
    last_market_available_at: str | None
    last_market_source_sha256: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_id", _identifier(self.account_id, field="account_id"))
        if type(self.version) is not int or self.version < 0:
            raise PaperContractError("account version must be an integer >= 0")
        if self.account_mode not in PAPER_ACCOUNT_MODES:
            raise PaperContractError("account_mode is unsupported")
        object.__setattr__(
            self,
            "owner_logical_agent_id",
            _identifier(self.owner_logical_agent_id, field="owner_logical_agent_id"),
        )
        object.__setattr__(self, "base_currency", _symbol(self.base_currency))
        object.__setattr__(self, "permitted_symbol", _symbol(self.permitted_symbol))
        object.__setattr__(self, "max_leverage", _decimal_text(self.max_leverage, field="max_leverage", positive=True))
        if not isinstance(self.instrument_spec, InstrumentSpecV1):
            raise PaperContractError("instrument_spec must be InstrumentSpecV1")
        if self.instrument_spec.symbol != self.permitted_symbol:
            raise PaperContractError("instrument_spec symbol must match permitted_symbol")
        if self.instrument_spec.account_mode != self.account_mode:
            raise PaperContractError("instrument_spec account_mode must match account_mode")
        if self.instrument_spec.quote_currency != self.base_currency:
            raise PaperContractError("instrument_spec quote_currency must match base_currency")
        if (
            self.account_mode == "LINEAR_PERP"
            and self.instrument_spec.parameter_status != "OBSERVED_RAW_BOUND"
        ):
            raise PaperContractError(
                "LINEAR_PERP instrument_spec must be bound to admitted raw metadata"
            )
        if type(self.owner_agent_generation) is not int or self.owner_agent_generation < 1:
            raise PaperContractError("owner_agent_generation must be an integer >= 1")
        object.__setattr__(self, "initial_balance", _decimal_text(self.initial_balance, field="initial_balance", positive=True))
        object.__setattr__(self, "cash_balance", _decimal_text(self.cash_balance, field="cash_balance"))
        object.__setattr__(self, "reserved_margin", _decimal_text(self.reserved_margin, field="reserved_margin", nonnegative=True))
        object.__setattr__(self, "realized_pnl", _decimal_text(self.realized_pnl, field="realized_pnl"))
        object.__setattr__(self, "fees_paid", _decimal_text(self.fees_paid, field="fees_paid", nonnegative=True))
        object.__setattr__(self, "funding_paid", _decimal_text(self.funding_paid, field="funding_paid"))
        object.__setattr__(self, "borrow_paid", _decimal_text(self.borrow_paid, field="borrow_paid"))
        if self.carry_coverage_status not in PAPER_CARRY_COVERAGE_STATUSES:
            raise PaperContractError("carry_coverage_status is unsupported")
        if self.funding_coverage_status not in PAPER_CARRY_COVERAGE_STATUSES:
            raise PaperContractError("funding_coverage_status is unsupported")
        if self.borrow_coverage_status not in PAPER_CARRY_COVERAGE_STATUSES:
            raise PaperContractError("borrow_coverage_status is unsupported")
        for prefix in ("funding", "borrow"):
            status = getattr(self, f"{prefix}_coverage_status")
            start = getattr(self, f"{prefix}_coverage_start_at")
            end = getattr(self, f"{prefix}_coverage_end_at")
            if (start is None) != (end is None):
                raise PaperContractError(
                    f"{prefix} coverage timestamps must share presence"
                )
            if status == "NOT_APPLICABLE" and start is not None:
                raise PaperContractError(
                    f"N/A {prefix} coverage cannot carry a time window"
                )
            if status in {"COMPLETE", "PARTIAL"} and start is None:
                raise PaperContractError(
                    f"{prefix} {status.lower()} coverage requires a time window"
                )
            if start is not None:
                normalized_start = _timestamp(
                    start, field=f"{prefix}_coverage_start_at"
                )
                normalized_end = _timestamp(
                    end, field=f"{prefix}_coverage_end_at"
                )
                if datetime.fromisoformat(
                    normalized_end.replace("Z", "+00:00")
                ) < datetime.fromisoformat(
                    normalized_start.replace("Z", "+00:00")
                ):
                    raise PaperContractError(
                        f"{prefix} coverage window must be forward"
                    )
                object.__setattr__(
                    self, f"{prefix}_coverage_start_at", normalized_start
                )
                object.__setattr__(
                    self, f"{prefix}_coverage_end_at", normalized_end
                )
        expected_carry = (
            "NOT_APPLICABLE"
            if self.funding_coverage_status == self.borrow_coverage_status == "NOT_APPLICABLE"
            else "COMPLETE"
            if self.funding_coverage_status in {"COMPLETE", "NOT_APPLICABLE"}
            and self.borrow_coverage_status in {"COMPLETE", "NOT_APPLICABLE"}
            else "PARTIAL"
            if "PARTIAL" in {self.funding_coverage_status, self.borrow_coverage_status}
            else "UNKNOWN"
        )
        if self.carry_coverage_status != expected_carry:
            raise PaperContractError("carry_coverage_status must summarize component coverage")
        if len({position.symbol for position in self.positions}) != len(self.positions):
            raise PaperContractError("positions must have unique symbols")
        if sum((Decimal(position.margin_allocated) for position in self.positions), Decimal("0")) != Decimal(self.reserved_margin):
            raise PaperContractError("reserved_margin must equal position margin")
        if len({order.order_id for order in self.orders}) != len(self.orders):
            raise PaperContractError("orders must have unique order ids")
        commands = tuple(
            _identifier(value, field="applied_command_ids") for value in self.applied_command_ids
        )
        if len(commands) != len(set(commands)):
            raise PaperContractError("applied_command_ids must be unique")
        object.__setattr__(self, "applied_command_ids", commands)
        object.__setattr__(self, "last_event_id", _identifier(self.last_event_id, field="last_event_id"))
        object.__setattr__(self, "last_fact_at", _timestamp(self.last_fact_at, field="last_fact_at"))
        if (self.last_market_observed_at is None) != (self.last_market_available_at is None):
            raise PaperContractError("market cursor timestamps must be both present or both absent")
        if (self.last_market_observed_at is None) != (self.last_market_source_sha256 is None):
            raise PaperContractError("market cursor digest and timestamps must share presence")
        if self.last_market_observed_at is not None:
            object.__setattr__(
                self,
                "last_market_observed_at",
                _timestamp(self.last_market_observed_at, field="last_market_observed_at"),
            )
            object.__setattr__(
                self,
                "last_market_available_at",
                _timestamp(self.last_market_available_at, field="last_market_available_at"),
            )
            object.__setattr__(
                self,
                "last_market_source_sha256",
                _sha256(self.last_market_source_sha256, field="last_market_source_sha256"),
            )
            if datetime.fromisoformat(
                self.last_market_available_at.replace("Z", "+00:00")
            ) < datetime.fromisoformat(
                self.last_market_observed_at.replace("Z", "+00:00")
            ):
                raise PaperContractError(
                    "last_market_available_at must not precede last_market_observed_at"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.paper-account-version",
            "schema_version": "1.0.0",
            "account_id": self.account_id,
            "version": self.version,
            "account_mode": self.account_mode,
            "owner_logical_agent_id": self.owner_logical_agent_id,
            "base_currency": self.base_currency,
            "permitted_symbol": self.permitted_symbol,
            "max_leverage": self.max_leverage,
            "instrument_spec": self.instrument_spec.to_dict(),
            "owner_agent_generation": self.owner_agent_generation,
            "initial_balance": self.initial_balance,
            "cash_balance": self.cash_balance,
            "reserved_margin": self.reserved_margin,
            "available_balance": self.available_balance,
            "collateral_deficit": self.collateral_deficit,
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
            "funding_paid": self.funding_paid,
            "borrow_paid": self.borrow_paid,
            "carry_coverage_status": self.carry_coverage_status,
            "funding_coverage_status": self.funding_coverage_status,
            "borrow_coverage_status": self.borrow_coverage_status,
            "funding_coverage_start_at": self.funding_coverage_start_at,
            "funding_coverage_end_at": self.funding_coverage_end_at,
            "borrow_coverage_start_at": self.borrow_coverage_start_at,
            "borrow_coverage_end_at": self.borrow_coverage_end_at,
            "positions": [position.to_dict() for position in self.positions],
            "orders": [order.to_dict() for order in self.orders],
            "applied_command_ids": list(self.applied_command_ids),
            "last_event_id": self.last_event_id,
            "last_fact_at": self.last_fact_at,
            "last_market_observed_at": self.last_market_observed_at,
            "last_market_available_at": self.last_market_available_at,
            "last_market_source_sha256": self.last_market_source_sha256,
        }

    @property
    def available_balance(self) -> str:
        return canonical_decimal(Decimal(self.cash_balance) - Decimal(self.reserved_margin))

    @property
    def collateral_deficit(self) -> str:
        return canonical_decimal(
            max(Decimal("0"), Decimal(self.reserved_margin) - Decimal(self.cash_balance))
        )


@dataclass(frozen=True, slots=True)
class PaperLedgerRecordV1:
    account_id: str
    revision: int
    previous_record_sha256: str | None
    event_id: str
    event_type: str
    occurred_at: str
    payload: Mapping[str, Any]
    record_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_id", _identifier(self.account_id, field="account_id"))
        if type(self.revision) is not int or self.revision < 1:
            raise PaperContractError("revision must be an integer >= 1")
        if self.previous_record_sha256 is not None:
            object.__setattr__(
                self,
                "previous_record_sha256",
                _sha256(self.previous_record_sha256, field="previous_record_sha256"),
            )
        if (self.revision == 1) != (self.previous_record_sha256 is None):
            raise PaperContractError("only revision one may omit previous_record_sha256")
        object.__setattr__(self, "event_id", _identifier(self.event_id, field="event_id"))
        if self.event_type not in PAPER_EVENT_TYPES:
            raise PaperContractError("event_type is unsupported")
        object.__setattr__(self, "occurred_at", _timestamp(self.occurred_at, field="occurred_at"))
        object.__setattr__(self, "payload", _freeze_json(self.payload, field="payload"))
        if self.event_type == "COMMAND_ACCEPTED":
            payload_fields = set(self.payload)
            linkage_present = "static_comparator_linkage" in payload_fields
            payload_fields.discard("static_comparator_linkage")
            if (
                payload_fields not in (
                    {"command"},
                    {"command", "execution_intent", "accepted_at"},
                    {"command", "commands", "execution_intent", "accepted_at"},
                )
                or not isinstance(self.payload.get("command"), Mapping)
            ):
                raise PaperContractError("paper command event payload mismatch")
            command = PaperCommandV1.from_dict(self.payload["command"])
            if command.account_id != self.account_id:
                raise PaperContractError("paper command event account mismatch")
            if "execution_intent" in self.payload:
                value = self.payload["execution_intent"]
                if not isinstance(value, Mapping):
                    raise PaperContractError("paper execution intent payload mismatch")
                intent = PaperExecutionIntentV1.from_dict(value)
                if intent.command is None or intent.command != command:
                    raise PaperContractError("paper execution intent command mismatch")
                if "commands" in self.payload:
                    commands_value = self.payload["commands"]
                    if not isinstance(commands_value, tuple) or intent.bracket is None:
                        raise PaperContractError("paper bracket command payload mismatch")
                    commands = tuple(
                        PaperCommandV1.from_dict(item) for item in commands_value
                    )
                    if commands != intent.bracket.commands:
                        raise PaperContractError("paper bracket command payload mismatch")
                elif intent.bracket is not None:
                    raise PaperContractError("paper bracket command payload missing")
                accepted_at = _timestamp(
                    self.payload.get("accepted_at"), field="accepted_at"
                )
                if (
                    accepted_at != self.occurred_at
                    or datetime.fromisoformat(
                        accepted_at.replace("Z", "+00:00")
                    )
                    < datetime.fromisoformat(
                        command.submitted_at.replace("Z", "+00:00")
                    )
                ):
                    raise PaperContractError(
                        "paper command event receipt time mismatch"
                    )
                if linkage_present:
                    linkage_value = self.payload["static_comparator_linkage"]
                    if not isinstance(linkage_value, Mapping):
                        raise PaperContractError(
                            "static comparator linkage payload mismatch"
                        )
                    linkage = StaticNoTransitionEpisodeLinkV1.from_dict(
                        linkage_value
                    )
                    if (
                        linkage.episode_id != intent.episode_id
                        or linkage.current_intent_sha256 != intent.intent_sha256
                    ):
                        raise PaperContractError(
                            "static comparator linkage intent mismatch"
                        )
            elif linkage_present:
                raise PaperContractError(
                    "direct paper command cannot carry comparator linkage"
                )
            elif command.submitted_at != self.occurred_at:
                raise PaperContractError("paper command event time mismatch")
        if self.event_type == "INTENT_RECORDED":
            payload_fields = set(self.payload)
            linkage_present = "static_comparator_linkage" in payload_fields
            payload_fields.discard("static_comparator_linkage")
            if (
                payload_fields != {"execution_intent"}
                or not isinstance(self.payload.get("execution_intent"), Mapping)
            ):
                raise PaperContractError("paper intent event payload mismatch")
            intent = PaperExecutionIntentV1.from_dict(
                self.payload["execution_intent"]
            )
            if intent.command is not None:
                raise PaperContractError(
                    "paper intent event must be non-executable"
                )
            if intent.account_id != self.account_id:
                raise PaperContractError("paper intent event account mismatch")
            if linkage_present:
                linkage_value = self.payload["static_comparator_linkage"]
                if not isinstance(linkage_value, Mapping):
                    raise PaperContractError(
                        "static comparator linkage payload mismatch"
                    )
                linkage = StaticNoTransitionEpisodeLinkV1.from_dict(
                    linkage_value
                )
                if (
                    linkage.episode_id != intent.episode_id
                    or linkage.current_intent_sha256 != intent.intent_sha256
                ):
                    raise PaperContractError(
                        "static comparator linkage intent mismatch"
                    )
            received_at = datetime.fromisoformat(
                self.occurred_at.replace("Z", "+00:00")
            )
            if not (
                datetime.fromisoformat(
                    intent.authored_at.replace("Z", "+00:00")
                )
                <= received_at
                <= datetime.fromisoformat(
                    intent.valid_until.replace("Z", "+00:00")
                )
            ):
                raise PaperContractError("paper intent event receipt time mismatch")
        if self.event_type == "STATIC_NO_TRANSITION_PREREGISTERED":
            if (
                set(self.payload) != {"comparator"}
                or not isinstance(self.payload.get("comparator"), Mapping)
            ):
                raise PaperContractError("static comparator event payload mismatch")
            comparator = StaticNoTransitionComparatorV1.from_dict(
                self.payload["comparator"]
            )
            intent = PaperExecutionIntentV1.from_dict(
                comparator.execution_intent
            )
            if (
                intent.account_id != self.account_id
                or comparator.preregistered_at != self.occurred_at
            ):
                raise PaperContractError("static comparator event binding mismatch")
        object.__setattr__(self, "record_sha256", _sha256(self.record_sha256, field="record_sha256"))
        if canonical_digest(self._digest_payload()) != self.record_sha256:
            raise PaperContractError("record_sha256 does not bind the record")

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        revision: int,
        previous_record_sha256: str | None,
        event_id: str,
        event_type: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> "PaperLedgerRecordV1":
        digest_payload = {
            "schema_id": "agent-trade-emotion.paper-ledger-record",
            "schema_version": "1.0.0",
            "account_id": account_id,
            "revision": revision,
            "previous_record_sha256": previous_record_sha256,
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "payload": _thaw_json(_freeze_json(payload, field="payload")),
        }
        return cls(record_sha256=canonical_digest(digest_payload), **{
            "account_id": account_id,
            "revision": revision,
            "previous_record_sha256": previous_record_sha256,
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "payload": payload,
        })

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-trade-emotion.paper-ledger-record",
            "schema_version": "1.0.0",
            "account_id": self.account_id,
            "revision": self.revision,
            "previous_record_sha256": self.previous_record_sha256,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "payload": _thaw_json(self.payload),
        }

    def to_dict(self) -> dict[str, Any]:
        value = self._digest_payload()
        value["record_sha256"] = self.record_sha256
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PaperLedgerRecordV1":
        expected = {
            "schema_id",
            "schema_version",
            "account_id",
            "revision",
            "previous_record_sha256",
            "event_id",
            "event_type",
            "occurred_at",
            "payload",
            "record_sha256",
        }
        if set(value) != expected:
            raise PaperContractError("paper ledger record fields mismatch")
        if value["schema_id"] != "agent-trade-emotion.paper-ledger-record" or value["schema_version"] != "1.0.0":
            raise PaperContractError("paper ledger record schema mismatch")
        return cls(
            account_id=value["account_id"],
            revision=value["revision"],
            previous_record_sha256=value["previous_record_sha256"],
            event_id=value["event_id"],
            event_type=value["event_type"],
            occurred_at=value["occurred_at"],
            payload=value["payload"],
            record_sha256=value["record_sha256"],
        )
