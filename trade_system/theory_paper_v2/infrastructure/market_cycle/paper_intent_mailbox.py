"""Write-once local transport for an Agent-authored paper execution intent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping

from ...domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from ...domain.market_cycle.paper import (
    BRACKET_ACTIVATION_POLICY,
    BRACKET_EXIT_POLICY,
    PAPER_AGENT_ACTIONS,
    PAPER_BRACKET_ENTRY_COMMAND_TYPES,
    PAPER_BRACKET_ELIGIBLE_ACTIONS,
    PAPER_COMMAND_TYPES,
    PAPER_NON_EXECUTABLE_ACTIONS,
    PAPER_POSITION_ROLES,
    PAPER_SIDES,
    PAPER_TIME_IN_FORCE,
    PaperContractError,
    PaperExecutionIntentV1,
)
from ...v32_durable_json import write_once_json


_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SAFE_TASK_REF = re.compile(r"[A-Za-z0-9/][A-Za-z0-9._:@+\-/]{0,255}\Z")
_AGENT_REQUEST_PATH = Path("transport/agent-request.json")
_INTENT_REQUEST_PATH = Path("transport/paper-execution-intent-request.json")
_INTENT_PATH = Path("transport/paper-execution-intent.json")
_RECEIPT_PATH = Path("transport/paper-execution-intent-receipt.json")
_REQUEST_SCHEMA_ID = "agent-trade-emotion.paper-execution-intent-request"
_REQUEST_SCHEMA_VERSION = "1.0.0"
_OUTPUT_SCHEMA_ID = "agent-trade-emotion.paper-execution-intent"
_FRESH_OUTPUT_SCHEMA_VERSION = "1.3.0"
_LEGACY_OUTPUT_SCHEMA_VERSION = "1.2.0"
_OUTPUT_CONTRACT_SCHEMA_ID = (
    "agent-trade-emotion.paper-execution-intent-output-contract"
)
_OUTPUT_CONTRACT_SCHEMA_VERSION = "1.3.0"
PAPER_ACTION_SPACE_SCHEMA_ID = "agent-trade-emotion.paper-action-space"
PAPER_ACTION_SPACE_SCHEMA_VERSION = "1.0.0"
_CANONICAL_ENCODING = (
    "RFC8259_CANONICAL_COMPACT_UTF8_SORTED_KEYS_PLUS_ONE_NEWLINE"
)
_INTENT_FIELDS_13 = (
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
    "bracket",
)
_COMMAND_FIELDS = (
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
)
_BRACKET_FIELDS = (
    "schema_id",
    "schema_version",
    "bracket_id",
    "entry",
    "protective_stop",
    "take_profits",
    "activation_policy",
    "exit_policy",
)
_REQUEST_FIELDS_LEGACY = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "logical_agent_id",
        "agent_generation",
        "physical_task_id",
        "decision_request_sha256",
        "agent_request_document_sha256",
        "paper_context_sha256",
        "ledger_head_record_sha256",
        "expected_account_version",
        "account_id",
        "symbol",
        "decision_sha256",
        "issued_at",
        "valid_until",
        "allowed_actions",
        "output_schema_id",
        "output_schema_version",
        "output_relative_path",
        "instructions",
    }
)
_REQUEST_FIELDS_FRESH = _REQUEST_FIELDS_LEGACY | {"output_contract"}


class PaperExecutionIntentMailboxError(ValueError):
    """The local Agent intent transport is absent, unsafe, or inconsistent."""


def _paper_context_values(
    context: Mapping[str, Any], *, symbol: object
) -> dict[str, Any]:
    """Select the execution facts the persistent trading Goal needs."""

    account = context.get("account")
    policy = context.get("paper_account_policy")
    cost = policy.get("cost_model") if isinstance(policy, Mapping) else None
    current_quantity: str | None = None
    if isinstance(account, Mapping):
        positions = account.get("positions")
        if isinstance(positions, (list, tuple)):
            for position in positions:
                if (
                    isinstance(position, Mapping)
                    and position.get("symbol") == symbol
                    and isinstance(position.get("quantity"), str)
                ):
                    current_quantity = str(position["quantity"])
                    break
    if current_quantity is None and isinstance(account, Mapping):
        # A valid account may omit a zero position from its projection.
        current_quantity = "0"
    return {
        "current_signed_quantity": current_quantity,
        "cost_model_id": (
            cost.get("model_id")
            if isinstance(cost, Mapping)
            and isinstance(cost.get("model_id"), str)
            else None
        ),
        "policy_maximum_loss": (
            policy.get("max_decision_loss")
            if isinstance(policy, Mapping)
            else None
        ),
        "policy_notional_cap": (
            policy.get("max_position_notional")
            if isinstance(policy, Mapping)
            else None
        ),
        "policy_max_observed_drawdown": (
            policy.get("max_observed_drawdown")
            if isinstance(policy, Mapping)
            else None
        ),
    }


def _paper_action_space_from_values(
    context_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish execution capabilities without choosing an Agent action."""

    required = (
        "current_signed_quantity",
        "cost_model_id",
        "policy_maximum_loss",
        "policy_notional_cap",
        "policy_max_observed_drawdown",
    )
    execution_status = (
        "AVAILABLE_WITHIN_PUBLISHED_CONTRACT"
        if all(context_values.get(field) is not None for field in required)
        else "ACCOUNT_OR_POLICY_NOT_READY"
    )
    return {
        "schema_id": PAPER_ACTION_SPACE_SCHEMA_ID,
        "schema_version": PAPER_ACTION_SPACE_SCHEMA_VERSION,
        "execution_status": execution_status,
        "agent_ownership": (
            "AGENT_CHOOSES_ACTION_SIDE_QUANTITY_PRICE_TIMING_OR_NON_EXECUTION"
        ),
        "reference_action_boundary": (
            "A lawful market reference action may be unsupported for local paper; "
            "the system blocks rather than rewrites it."
        ),
        "standalone_command_types": sorted(PAPER_COMMAND_TYPES),
        "non_executable_actions": sorted(PAPER_NON_EXECUTABLE_ACTIONS),
        "protected_flat_entry": {
            "eligible_actions": sorted(PAPER_BRACKET_ELIGIBLE_ACTIONS),
            "required_pre_state_signed_quantity": "0",
            "entry_command_types": sorted(PAPER_BRACKET_ENTRY_COMMAND_TYPES),
            "entry_must_equal_top_level_command": True,
            "entry_reduce_only": False,
            "protective_stop_required": True,
            "protective_stop_must_cover_full_entry_quantity": True,
            "take_profit_total_quantity_must_not_exceed_entry": True,
            "activation_policy": BRACKET_ACTIVATION_POLICY,
            "exit_policy": BRACKET_EXIT_POLICY,
            "market_with_bracket_status": "UNSUPPORTED_USE_BOUNDED_LIMIT_OR_NON_EXECUTABLE_REFERENCE",
        },
        "current_signed_quantity": context_values.get(
            "current_signed_quantity"
        ),
        "cost_model_id": context_values.get("cost_model_id"),
        "policy_limits": {
            "maximum_loss": context_values.get("policy_maximum_loss"),
            "notional_cap": context_values.get("policy_notional_cap"),
            "max_observed_drawdown": context_values.get(
                "policy_max_observed_drawdown"
            ),
        },
        "binding_stages": {
            "available_in_predecision_context": [
                "paper_context_sha256",
                "ledger_head_record_sha256",
                "current_signed_quantity",
                "cost_model_id",
                "policy_limits",
            ],
            "bound_in_postdecision_request": [
                "request.decision_request_sha256",
                "request.decision_sha256",
                "request.issued_at",
                "request.valid_until_ceiling",
            ],
            "bound_after_request_is_sealed": [
                "execution_intent_request_sha256"
            ],
            "agent_authored_in_intent": [
                "intent_id",
                "episode_id",
                "transition_id",
                "tranche_id",
                "action",
                "role",
                "pre_state",
                "target_state",
                "position_delta",
                "evidence_delta",
                "activation",
                "hard_invalidation",
                "risk_budget",
                "command",
                "bracket",
                "intent.authored_at",
                "intent.valid_until",
            ],
        },
    }


def paper_action_space_contract(
    context: Mapping[str, Any], *, symbol: object
) -> dict[str, Any]:
    """Derive the same static action space for decision and action packets."""

    return _paper_action_space_from_values(
        _paper_context_values(context, symbol=symbol)
    )


def _paper_output_contract(
    *, request: Mapping[str, Any], context_values: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the self-contained 1.3 JSON and bracket contract."""

    command_fixed = {
        "schema_id": "agent-trade-emotion.paper-command",
        "schema_version": "1.1.0",
        "account_id": request["account_id"],
        "logical_agent_id": request["logical_agent_id"],
        "agent_generation": request["agent_generation"],
        "decision_cycle_id": request["cycle_id"],
        "decision_sha256": request["decision_sha256"],
        "expected_account_version": request["expected_account_version"],
        "symbol": request["symbol"],
        "cost_model_id": context_values.get("cost_model_id"),
    }
    action_space = _paper_action_space_from_values(context_values)
    return {
        "schema_id": _OUTPUT_CONTRACT_SCHEMA_ID,
        "schema_version": _OUTPUT_CONTRACT_SCHEMA_VERSION,
        "canonical_encoding": _CANONICAL_ENCODING,
        "write_semantics": {
            "mode": "CREATE_ONCE_NO_REWRITE",
            "instruction": (
                "Build and validate the complete canonical bytes before "
                "creating output_relative_path; create it exclusively once "
                "and never truncate, replace, append to, or rewrite it."
            ),
        },
        "canonical_decimal_format": {
            "json_type": "STRING_NOT_JSON_NUMBER",
            "algorithm": (
                "Parse a finite base-10 decimal, render fixed-point without "
                "an exponent, strip trailing fractional zeros and then a "
                "trailing decimal point, and normalize every zero including "
                "negative zero to exactly 0; the rendered value must equal "
                "the input string."
            ),
            "valid_examples": ["0", "56.06", "-80", "0.1"],
            "invalid_examples": [
                "56.060",
                "56.0",
                "056.06",
                "+56.06",
                "5.606E1",
                "-0",
            ],
        },
        "output_relative_path": _INTENT_PATH.as_posix(),
        "exact_fields": sorted(_INTENT_FIELDS_13),
        "fixed_values": {
            "schema_id": _OUTPUT_SCHEMA_ID,
            "schema_version": _FRESH_OUTPUT_SCHEMA_VERSION,
            "decision_request_sha256": request["decision_request_sha256"],
            "paper_context_sha256": request["paper_context_sha256"],
            "ledger_head_record_sha256": request[
                "ledger_head_record_sha256"
            ],
            "decision_cycle_id": request["cycle_id"],
            "decision_sha256": request["decision_sha256"],
            "account_id": request["account_id"],
            "logical_agent_id": request["logical_agent_id"],
            "agent_generation": request["agent_generation"],
            "expected_account_version": request[
                "expected_account_version"
            ],
            "symbol": request["symbol"],
        },
        "dynamic_values": {
            "execution_intent_request_sha256": (
                "SHA256_OF_THIS_CANONICAL_REQUEST_DOCUMENT_WITH_ONE_TRAILING_LF"
            ),
            "intent_id": "AGENT_SAFE_IDENTIFIER_AND_EQUAL_TO_COMMAND_ID_IF_COMMAND_EXISTS",
            "authored_at": {
                "type": "ISO8601_WITH_EXPLICIT_OFFSET",
                "minimum_inclusive": request["issued_at"],
                "maximum_exclusive": request["valid_until"],
            },
            "valid_until": {
                "type": "ISO8601_WITH_EXPLICIT_OFFSET",
                "after": "authored_at",
                "maximum_inclusive": request["valid_until"],
            },
        },
        "allowed_values": {
            "action": sorted(PAPER_AGENT_ACTIONS),
            "role": sorted(PAPER_POSITION_ROLES),
            "command.command_type": sorted(PAPER_COMMAND_TYPES),
            "command.side": sorted(PAPER_SIDES),
            "command.time_in_force": sorted(PAPER_TIME_IN_FORCE),
        },
        "field_constraints": {
            "intent_id": {
                "json_type": "STRING",
                "format": "SAFE_IDENTIFIER",
                "minimum_length": 1,
                "maximum_length": 128,
            },
            "episode_id": {
                "json_type": "STRING",
                "format": "SAFE_IDENTIFIER",
                "minimum_length": 1,
                "maximum_length": 128,
            },
            "transition_id": {
                "json_type": "STRING",
                "format": "SAFE_IDENTIFIER",
                "minimum_length": 1,
                "maximum_length": 128,
            },
            "tranche_id": {
                "json_type": "STRING_OR_NULL",
                "format_when_string": "SAFE_IDENTIFIER",
                "minimum_length_when_string": 1,
                "maximum_length_when_string": 128,
            },
            "action": {
                "json_type": "STRING",
                "allowed_values_from": "allowed_values.action",
            },
            "role": {
                "json_type": "STRING",
                "allowed_values_from": "allowed_values.role",
            },
            "pre_state": {"json_type": "OBJECT"},
            "target_state": {"json_type": "OBJECT"},
            "position_delta": {"json_type": "OBJECT"},
            "risk_budget": {"json_type": "OBJECT"},
            "evidence_delta": {
                "json_type": "STRING",
                "non_empty_after_strip": True,
                "maximum_characters": 16384,
            },
            "activation": {
                "json_type": "STRING",
                "non_empty_after_strip": True,
                "maximum_characters": 16384,
            },
            "hard_invalidation": {
                "json_type": "STRING",
                "non_empty_after_strip": True,
                "maximum_characters": 16384,
            },
            "command": {"json_type": "OBJECT_OR_NULL"},
            "bracket": {"json_type": "OBJECT_OR_NULL"},
        },
        "paper_action_space": action_space,
        "context_values": dict(context_values),
        "state_shapes": {
            "pre_state": {
                "required_fields": ["signed_quantity"],
                "signed_quantity_fixed_value": context_values.get(
                    "current_signed_quantity"
                ),
                "additional_canonical_json_fields_allowed": True,
            },
            "target_state": {
                "required_fields": ["signed_quantity"],
                "additional_canonical_json_fields_allowed": True,
            },
            "position_delta": {
                "required_fields": ["signed_quantity_change"],
                "equation": (
                    "target_state.signed_quantity-pre_state.signed_quantity"
                ),
                "additional_canonical_json_fields_allowed": True,
            },
            "risk_budget": {
                "required_fields": [
                    "maximum_loss",
                    "notional_cap",
                    "max_observed_drawdown",
                ],
                "value_type": "POSITIVE_CANONICAL_DECIMAL_STRING",
                "upper_bounds": {
                    "maximum_loss": context_values.get(
                        "policy_maximum_loss"
                    ),
                    "notional_cap": context_values.get(
                        "policy_notional_cap"
                    ),
                    "max_observed_drawdown": context_values.get(
                        "policy_max_observed_drawdown"
                    ),
                },
                "additional_canonical_json_fields_allowed": True,
            },
        },
        "command_shape": {
            "nullable": True,
            "exact_fields": sorted(_COMMAND_FIELDS),
            "fixed_values": command_fixed,
            "dynamic_bindings": {
                "command_id": (
                    "SAFE_IDENTIFIER; TOP_LEVEL_COMMAND_AND_BRACKET_ENTRY_EQUAL_"
                    "INTENT_ID; EXIT_LEGS_USE_DISTINCT_IDS"
                ),
                "submitted_at": "authored_at",
                "expires_at": "NULL_OR_AT_MOST_INTENT_VALID_UNTIL",
            },
            "type_constraints": {
                "CANCEL": (
                    "target_order_id non-null; side, quantity, limit_price, "
                    "trigger_price null; reduce_only false"
                ),
                "LIMIT_OR_LIMIT_REDUCE": (
                    "limit_price non-null and trigger_price null"
                ),
                "STOP_LOSS_OR_TAKE_PROFIT": (
                    "trigger_price non-null and limit_price null"
                ),
                "MARKET_OR_REDUCE": (
                    "limit_price and trigger_price null"
                ),
                "REDUCE_ONLY_TRUE_FOR": [
                    "STOP_LOSS",
                    "TAKE_PROFIT",
                    "REDUCE",
                    "LIMIT_REDUCE",
                ],
            },
        },
        "bracket_shape": {
            "nullable": True,
            "exact_fields": sorted(_BRACKET_FIELDS),
            "fixed_values": {
                "schema_id": "agent-trade-emotion.paper-bracket",
                "schema_version": "1.0.0",
                "activation_policy": BRACKET_ACTIVATION_POLICY,
                "exit_policy": BRACKET_EXIT_POLICY,
            },
            "dynamic_bindings": {
                "bracket_id": "intent_id",
                "entry": "EXACTLY_EQUAL_TO_COMMAND",
            },
            "entry": {
                "shape": "command_shape",
                "command_type": next(
                    iter(sorted(PAPER_BRACKET_ENTRY_COMMAND_TYPES))
                ),
                "allowed_command_types": sorted(
                    PAPER_BRACKET_ENTRY_COMMAND_TYPES
                ),
                "reduce_only": False,
            },
            "protective_stop": {
                "shape": "command_shape",
                "command_type": "STOP_LOSS",
                "reduce_only": True,
                "quantity": "EXACTLY_ENTRY_QUANTITY",
                "command_id": "UNIQUE_SAFE_IDENTIFIER_NOT_EQUAL_TO_INTENT_ID",
            },
            "take_profits": {
                "cardinality": "ZERO_OR_MORE",
                "item_shape": "command_shape",
                "command_type": "TAKE_PROFIT",
                "reduce_only": True,
                "sum_quantity_maximum": "ENTRY_QUANTITY",
                "trigger_prices_must_be_unique": True,
                "command_id": (
                    "EACH_IS_A_UNIQUE_SAFE_IDENTIFIER_NOT_EQUAL_TO_INTENT_ID"
                ),
            },
            "cross_leg_constraints": [
                "ALL_COMMAND_IDS_UNIQUE",
                "ALL_LEGS_SHARE_COMMAND_FIXED_VALUES_AND_SUBMITTED_AT",
                "ALL_EXITS_OPPOSE_ENTRY_SIDE",
                "SHORT_ENTRY_STOP_ABOVE_ENTRY_AND_TARGETS_BELOW_ENTRY",
                "LONG_ENTRY_STOP_BELOW_ENTRY_AND_TARGETS_ABOVE_ENTRY",
            ],
        },
        "action_constraints": {
            "non_executable_actions": action_space[
                "non_executable_actions"
            ],
            "non_executable_shape": (
                "command=null; bracket=null; position delta zero"
            ),
            "all_other_actions_require_command": True,
            "bracket_allowed_actions": action_space[
                "protected_flat_entry"
            ]["eligible_actions"],
            "bracket_requires_flat_pre_state": True,
        },
        "global_constraints": [
            "EXACT_FIELDS_LISTS_ARE_CANONICAL_WIRE_ORDER_FOR_DECLARED_OBJECTS",
            "ALL_OBJECT_KEYS_RECURSIVELY_ASCENDING_UTF16_CODE_UNITS",
            "ALL_DECIMALS_ARE_CANONICAL_STRINGS_NOT_JSON_NUMBERS",
            "READABLE_TEXT_FIELDS_ARE_NON_EMPTY_AND_AT_MOST_16384_CHARS",
            "COMMAND_REQUIRES_NON_NULL_CONTEXT_VALUES.COST_MODEL_ID",
            "AGENT_ALONE_CHOOSES_ACTION_SIZE_TRANSITION_AND_RISK_WITHIN_POLICY",
        ],
    }


@dataclass(frozen=True, slots=True)
class ReceivedPaperExecutionIntent:
    intent: PaperExecutionIntentV1
    received_at: str
    intent_document_sha256: str
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class IssuedPaperExecutionIntentRequest:
    document: Mapping[str, Any]
    request_sha256: str


class LocalPaperExecutionIntentMailbox:
    """Read Agent bytes and create one immutable, trusted-time receipt."""

    def __init__(self, cycles_root: Path, *, clock: Callable[[], str]) -> None:
        if not callable(clock):
            raise PaperExecutionIntentMailboxError("PAPER_INTENT_CLOCK_INVALID")
        self._root = Path(cycles_root)
        self._clock = clock

    @staticmethod
    def _cycle(value: str) -> str:
        if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
            raise PaperExecutionIntentMailboxError("PAPER_INTENT_CYCLE_ID_INVALID")
        return value

    def intent_path(self, cycle_id: str) -> Path:
        return self._root / self._cycle(cycle_id) / _INTENT_PATH

    def intent_request_path(self, cycle_id: str) -> Path:
        return self._root / self._cycle(cycle_id) / _INTENT_REQUEST_PATH

    def receipt_path(self, cycle_id: str) -> Path:
        return self._root / self._cycle(cycle_id) / _RECEIPT_PATH

    @staticmethod
    def _read_document(path: Path) -> tuple[dict[str, object], bytes]:
        try:
            metadata = path.lstat()
        except FileNotFoundError as exc:
            raise PaperExecutionIntentMailboxError(
                "PAPER_EXECUTION_INTENT_PENDING"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise PaperExecutionIntentMailboxError("PAPER_INTENT_DOCUMENT_UNSAFE")
        raw = path.read_bytes()
        try:
            document = loads_json_strict(raw)
        except ValueError as exc:
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_DOCUMENT_INVALID"
            ) from exc
        if canonical_bytes(document) + b"\n" != raw:
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_DOCUMENT_NOT_CANONICAL"
            )
        return document, raw

    @staticmethod
    def _moment(value: object, *, code: str) -> datetime:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise PaperExecutionIntentMailboxError(code) from exc
        if result.tzinfo is None or result.utcoffset() is None:
            raise PaperExecutionIntentMailboxError(code)
        return result

    def issue_request(
        self,
        cycle_id: str,
        *,
        logical_agent_id: str,
        agent_generation: int,
        physical_task_id: str,
        decision_sha256: str,
        issued_at: str,
        valid_until: str,
    ) -> IssuedPaperExecutionIntentRequest:
        """Freeze the exact Agent output request before accepting an intent."""

        safe_cycle = self._cycle(cycle_id)
        if (
            not isinstance(logical_agent_id, str)
            or _SAFE_ID.fullmatch(logical_agent_id) is None
            or type(agent_generation) is not int
            or agent_generation < 1
            or not isinstance(physical_task_id, str)
            or _SAFE_TASK_REF.fullmatch(physical_task_id) is None
            or not isinstance(decision_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", decision_sha256) is None
            or self._moment(valid_until, code="PAPER_INTENT_REQUEST_TIME_INVALID")
            <= self._moment(issued_at, code="PAPER_INTENT_REQUEST_TIME_INVALID")
        ):
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_REQUEST_BINDING_INVALID"
            )
        agent_request, agent_request_raw = self._read_document(
            self._root / safe_cycle / _AGENT_REQUEST_PATH
        )
        packet = agent_request.get("packet")
        paper_context = (
            packet.get("paper_context") if isinstance(packet, Mapping) else None
        )
        head = (
            paper_context.get("ledger_head")
            if isinstance(paper_context, Mapping)
            else None
        )
        account = (
            paper_context.get("account")
            if isinstance(paper_context, Mapping)
            else None
        )
        packet_sha256 = agent_request.get("packet_sha256")
        if (
            not isinstance(packet, Mapping)
            or hashlib.sha256(canonical_bytes(packet)).hexdigest()
            != packet_sha256
            or packet.get("cycle_id") != safe_cycle
            or not isinstance(paper_context, Mapping)
            or not isinstance(head, Mapping)
            or not isinstance(account, Mapping)
            or head.get("record_sha256") is None
            or type(head.get("revision")) is not int
            or head.get("revision", 0) < 1
            or account.get("account_id") is None
            or account.get("owner_logical_agent_id") != logical_agent_id
            or account.get("owner_agent_generation") != agent_generation
            or paper_context.get("paper_context_sha256") is None
        ):
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_REQUEST_CONTEXT_INVALID"
            )
        document = {
            "schema_id": _REQUEST_SCHEMA_ID,
            "schema_version": _REQUEST_SCHEMA_VERSION,
            "cycle_id": safe_cycle,
            "logical_agent_id": logical_agent_id,
            "agent_generation": agent_generation,
            "physical_task_id": physical_task_id,
            "decision_request_sha256": packet_sha256,
            "agent_request_document_sha256": hashlib.sha256(
                agent_request_raw
            ).hexdigest(),
            "paper_context_sha256": paper_context["paper_context_sha256"],
            "ledger_head_record_sha256": head["record_sha256"],
            "expected_account_version": head["revision"],
            "account_id": account["account_id"],
            "symbol": account.get("permitted_symbol"),
            "decision_sha256": decision_sha256,
            "issued_at": issued_at,
            "valid_until": valid_until,
            "allowed_actions": sorted(PAPER_AGENT_ACTIONS),
            "output_schema_id": _OUTPUT_SCHEMA_ID,
            "output_schema_version": _FRESH_OUTPUT_SCHEMA_VERSION,
            "output_relative_path": _INTENT_PATH.as_posix(),
            "instructions": (
                "Read output_contract, construct and validate all final bytes "
                "before creating the target, and treat every exact_fields list "
                "as that object's canonical wire order. Recursively order all "
                "JSON object keys by ascending UTF-16 code units, use compact "
                "UTF-8, and write exactly one trailing LF. Create exactly one "
                "Agent-owned intent and never rewrite it. The system may permit "
                "or block it but must not choose its action or size."
            ),
        }
        document["output_contract"] = _paper_output_contract(
            request=document,
            context_values=_paper_context_values(
                paper_context, symbol=document["symbol"]
            ),
        )
        path = self.intent_request_path(safe_cycle)
        write_once_json(path, document)
        sealed, raw = self._read_document(path)
        if sealed != document:
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_REQUEST_WRITE_ONCE_CONFLICT"
            )
        return IssuedPaperExecutionIntentRequest(
            document=sealed,
            request_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def receive(self, cycle_id: str) -> ReceivedPaperExecutionIntent:
        safe_cycle = self._cycle(cycle_id)
        intent_request, intent_request_raw = self._read_document(
            self.intent_request_path(safe_cycle)
        )
        request_fields = frozenset(intent_request)
        fresh_request = request_fields == _REQUEST_FIELDS_FRESH
        legacy_request = request_fields == _REQUEST_FIELDS_LEGACY
        if not fresh_request and not legacy_request:
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_REQUEST_BINDING_INVALID"
            )
        if fresh_request:
            agent_request, agent_request_raw = self._read_document(
                self._root / safe_cycle / _AGENT_REQUEST_PATH
            )
            packet = agent_request.get("packet")
            context = (
                packet.get("paper_context")
                if isinstance(packet, Mapping)
                else None
            )
            head = (
                context.get("ledger_head")
                if isinstance(context, Mapping)
                else None
            )
            account = (
                context.get("account")
                if isinstance(context, Mapping)
                else None
            )
            if (
                not isinstance(packet, Mapping)
                or not isinstance(context, Mapping)
                or not isinstance(head, Mapping)
                or not isinstance(account, Mapping)
                or agent_request.get("packet_sha256")
                != hashlib.sha256(canonical_bytes(packet)).hexdigest()
                or intent_request.get("decision_request_sha256")
                != agent_request.get("packet_sha256")
                or intent_request.get("agent_request_document_sha256")
                != hashlib.sha256(agent_request_raw).hexdigest()
                or intent_request.get("paper_context_sha256")
                != context.get("paper_context_sha256")
                or intent_request.get("ledger_head_record_sha256")
                != head.get("record_sha256")
                or intent_request.get("expected_account_version")
                != head.get("revision")
                or intent_request.get("account_id")
                != account.get("account_id")
                or intent_request.get("logical_agent_id")
                != account.get("owner_logical_agent_id")
                or intent_request.get("agent_generation")
                != account.get("owner_agent_generation")
                or intent_request.get("symbol")
                != account.get("permitted_symbol")
            ):
                raise PaperExecutionIntentMailboxError(
                    "PAPER_INTENT_REQUEST_CONTEXT_INVALID"
                )
            expected_output_contract = _paper_output_contract(
                request=intent_request,
                context_values=_paper_context_values(
                    context, symbol=intent_request.get("symbol")
                ),
            )
            if intent_request.get("output_contract") != expected_output_contract:
                raise PaperExecutionIntentMailboxError(
                    "PAPER_INTENT_OUTPUT_CONTRACT_INVALID"
                )
        document, raw = self._read_document(self.intent_path(safe_cycle))
        try:
            intent = PaperExecutionIntentV1.from_dict(document)
        except PaperContractError as exc:
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_CONTRACT_INVALID"
            ) from exc
        if intent.decision_cycle_id != safe_cycle:
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_CYCLE_BINDING_MISMATCH"
            )
        try:
            request_valid_until = self._moment(
                intent_request["valid_until"],
                code="PAPER_INTENT_REQUEST_TIME_INVALID",
            )
            authored_at = self._moment(
                intent.authored_at, code="PAPER_INTENT_REQUEST_TIME_INVALID"
            )
            intent_valid_until = self._moment(
                intent.valid_until, code="PAPER_INTENT_REQUEST_TIME_INVALID"
            )
        except KeyError as exc:
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_REQUEST_BINDING_INVALID"
            ) from exc
        if (
            intent_request.get("schema_id")
            != _REQUEST_SCHEMA_ID
            or intent_request.get("schema_version") != _REQUEST_SCHEMA_VERSION
            or intent_request.get("allowed_actions")
            != sorted(PAPER_AGENT_ACTIONS)
            or intent_request.get("output_schema_id") != _OUTPUT_SCHEMA_ID
            or intent_request.get("output_schema_version")
            != (
                _FRESH_OUTPUT_SCHEMA_VERSION
                if fresh_request
                else _LEGACY_OUTPUT_SCHEMA_VERSION
            )
            or intent.wire_schema_version
            != intent_request.get("output_schema_version")
            or intent_request.get("output_relative_path")
            != _INTENT_PATH.as_posix()
            or not isinstance(intent_request.get("instructions"), str)
            or not str(intent_request["instructions"]).strip()
            or intent.execution_intent_request_sha256
            != hashlib.sha256(intent_request_raw).hexdigest()
            or intent.decision_request_sha256
            != intent_request.get("decision_request_sha256")
            or intent.paper_context_sha256
            != intent_request.get("paper_context_sha256")
            or intent.ledger_head_record_sha256
            != intent_request.get("ledger_head_record_sha256")
            or intent.decision_sha256
            != intent_request.get("decision_sha256")
            or intent.account_id != intent_request.get("account_id")
            or intent.logical_agent_id
            != intent_request.get("logical_agent_id")
            or intent.agent_generation
            != intent_request.get("agent_generation")
            or intent.expected_account_version
            != intent_request.get("expected_account_version")
            or intent.symbol != intent_request.get("symbol")
            or intent.action not in intent_request.get("allowed_actions", ())
            or authored_at
            < self._moment(
                intent_request.get("issued_at"),
                code="PAPER_INTENT_REQUEST_TIME_INVALID",
            )
            or intent_valid_until > request_valid_until
        ):
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_REQUEST_BINDING_MISMATCH"
            )
        document_sha256 = hashlib.sha256(raw).hexdigest()
        receipt_path = self.receipt_path(safe_cycle)
        try:
            receipt, receipt_raw = self._read_document(receipt_path)
        except PaperExecutionIntentMailboxError as exc:
            if str(exc) != "PAPER_EXECUTION_INTENT_PENDING":
                raise
            receipt = {
                "schema_id": "agent-trade-emotion.paper-execution-intent-receipt",
                "schema_version": "1.0.0",
                "cycle_id": safe_cycle,
                "intent_sha256": intent.intent_sha256,
                "intent_document_sha256": document_sha256,
                "received_at": self._clock(),
            }
            write_once_json(receipt_path, receipt)
            receipt, receipt_raw = self._read_document(receipt_path)
        if (
            frozenset(receipt)
            != {
                "schema_id",
                "schema_version",
                "cycle_id",
                "intent_sha256",
                "intent_document_sha256",
                "received_at",
            }
            or receipt.get("schema_id")
            != "agent-trade-emotion.paper-execution-intent-receipt"
            or receipt.get("schema_version") != "1.0.0"
            or receipt.get("cycle_id") != safe_cycle
            or receipt.get("intent_sha256") != intent.intent_sha256
            or receipt.get("intent_document_sha256") != document_sha256
            or not isinstance(receipt.get("received_at"), str)
        ):
            raise PaperExecutionIntentMailboxError(
                "PAPER_INTENT_RECEIPT_BINDING_INVALID"
            )
        return ReceivedPaperExecutionIntent(
            intent=intent,
            received_at=str(receipt["received_at"]),
            intent_document_sha256=document_sha256,
            receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
        )


__all__ = [
    "LocalPaperExecutionIntentMailbox",
    "IssuedPaperExecutionIntentRequest",
    "PaperExecutionIntentMailboxError",
    "ReceivedPaperExecutionIntent",
]
