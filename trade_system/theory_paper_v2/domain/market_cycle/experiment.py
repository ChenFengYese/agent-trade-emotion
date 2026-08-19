"""Frozen, no-external-side-effect experiment policy for V3.3.2 runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from types import MappingProxyType
from typing import Any, Mapping

from ..contracts.canonical import canonical_decimal, canonical_digest
from .paper import PaperCostModelV1, PaperContractError


EXPERIMENT_POLICY_SCHEMA_ID = "agent-trade-emotion.v332-experiment-policy"
EXPERIMENT_POLICY_SCHEMA_VERSION = "1.0.0"
EXPERIMENT_PHASES = frozenset({"CAPABILITY_PILOT", "CONTINUITY_24H"})
EXPERIMENT_CAPABILITIES = frozenset(
    {
        "DATA_ADMISSION",
        "SYSTEM_EXECUTION",
        "MARKET_ANALYSIS",
        "HYPOTHESIS_GENERATION",
        "TRADING_DECISION",
        "POSITION_MANAGEMENT",
        "ATTENTION_SCHEDULING",
        "RECOVERY_REPLAY",
        "OPERATIONAL_EVALUATION",
    }
)
EXPERIMENT_MISSING_DATA_POLICY = "TYPED_UNKNOWN_NO_BACKFILL_NO_WINDOW_EXTENSION"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,255}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ExperimentPolicyError(ValueError):
    """The experiment policy is ambiguous, unsafe, or internally inconsistent."""


def _identifier(value: object, *, field: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    return value


def _text(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 4096
        or any(ord(character) < 0x20 for character in value)
    ):
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    return value


def _timestamp(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    return text


def _positive_int(value: object, *, field: str, maximum: int) -> int:
    if type(value) is not int or value <= 0 or value > maximum:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    return value


def _decimal(value: object, *, field: str, positive: bool = True) -> str:
    if type(value) is not str:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID") from exc
    if (
        not number.is_finite()
        or canonical_decimal(number) != value
        or (positive and number <= 0)
    ):
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    return value


def _string_tuple(
    value: object, *, field: str, allowed: frozenset[str] | None = None
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    result = tuple(_text(item, field=field) for item in value)
    if len(result) != len(set(result)) or (allowed is not None and not set(result) <= allowed):
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    return result


def _exact_mapping(
    value: object, *, fields: frozenset[str], field: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != fields:
        raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class ExperimentPolicyV1:
    """One create-once policy whose digest is the run's experiment identity."""

    experiment_id: str
    run_id: str
    phase: str
    venue_id: str
    instrument_id: str
    market_contract_identity: str
    data_profile: str
    starts_at: str
    duration_seconds: int
    decision_horizon_seconds: int
    outcome_tolerance_seconds: int
    base_sampling_seconds: int
    active_sampling_seconds: int
    capability_ids: tuple[str, ...]
    public_data_authorized: bool
    local_paper_authorized: bool
    testnet_authorized: bool
    live_authorized: bool
    private_credentials_authorized: bool
    external_orders_authorized: bool
    funds_authorized: bool
    paper_account: Mapping[str, Any] | None
    evaluation: Mapping[str, Any]
    missing_data_policy: str
    restart_if: tuple[str, ...]
    continue_if: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in (
            "experiment_id",
            "run_id",
            "venue_id",
            "instrument_id",
            "market_contract_identity",
            "data_profile",
        ):
            object.__setattr__(
                self, field, _identifier(getattr(self, field), field=field)
            )
        if self.phase not in EXPERIMENT_PHASES:
            raise ExperimentPolicyError("EXPERIMENT_PHASE_INVALID")
        object.__setattr__(self, "starts_at", _timestamp(self.starts_at, field="starts_at"))
        duration = _positive_int(
            self.duration_seconds, field="duration_seconds", maximum=172800
        )
        if (self.phase == "CONTINUITY_24H") != (duration == 86400):
            raise ExperimentPolicyError("EXPERIMENT_PHASE_DURATION_MISMATCH")
        for field, maximum in (
            ("decision_horizon_seconds", 86400),
            ("outcome_tolerance_seconds", 3600),
            ("base_sampling_seconds", 3600),
            ("active_sampling_seconds", 3600),
        ):
            _positive_int(getattr(self, field), field=field, maximum=maximum)
        if self.active_sampling_seconds > self.base_sampling_seconds:
            raise ExperimentPolicyError("EXPERIMENT_ACTIVE_SAMPLING_SLOWER_THAN_BASE")
        capabilities = _string_tuple(
            self.capability_ids,
            field="capability_ids",
            allowed=EXPERIMENT_CAPABILITIES,
        )
        object.__setattr__(self, "capability_ids", capabilities)
        for field in (
            "public_data_authorized",
            "local_paper_authorized",
            "testnet_authorized",
            "live_authorized",
            "private_credentials_authorized",
            "external_orders_authorized",
            "funds_authorized",
        ):
            if type(getattr(self, field)) is not bool:
                raise ExperimentPolicyError(f"EXPERIMENT_{field.upper()}_INVALID")
        if any(
            (
                self.testnet_authorized,
                self.live_authorized,
                self.private_credentials_authorized,
                self.external_orders_authorized,
                self.funds_authorized,
            )
        ):
            raise ExperimentPolicyError("EXPERIMENT_EXTERNAL_SIDE_EFFECT_AUTHORITY_FORBIDDEN")
        paper = self._validate_paper_account(self.paper_account)
        if self.local_paper_authorized != (paper is not None):
            raise ExperimentPolicyError("EXPERIMENT_PAPER_AUTHORITY_CONFIGURATION_MISMATCH")
        object.__setattr__(self, "paper_account", paper)
        evaluation = self._validate_evaluation(self.evaluation)
        object.__setattr__(self, "evaluation", evaluation)
        if self.missing_data_policy != EXPERIMENT_MISSING_DATA_POLICY:
            raise ExperimentPolicyError("EXPERIMENT_MISSING_DATA_POLICY_INVALID")
        restart = _string_tuple(self.restart_if, field="restart_if")
        continuable = _string_tuple(self.continue_if, field="continue_if")
        if set(restart) & set(continuable):
            raise ExperimentPolicyError("EXPERIMENT_ISSUE_POLICY_OVERLAP")
        object.__setattr__(self, "restart_if", restart)
        object.__setattr__(self, "continue_if", continuable)

    @staticmethod
    def _validate_paper_account(value: object) -> Mapping[str, Any] | None:
        if value is None:
            return None
        document = _exact_mapping(
            value,
            fields=frozenset(
                {
                    "account_id",
                    "setup_cycle_id",
                    "logical_agent_id",
                    "agent_generation",
                    "account_mode",
                    "base_currency",
                    "initial_balance",
                    "max_leverage",
                    "max_position_notional",
                    "max_decision_loss",
                    "max_observed_drawdown",
                    "cost_model",
                }
            ),
            field="paper_account",
        )
        cost_document = _exact_mapping(
            document["cost_model"],
            fields=frozenset(
                {
                    "model_id",
                    "maker_fee_bps",
                    "taker_fee_bps",
                    "market_impact_bps",
                    "funding_status",
                    "borrow_status",
                    "effective_from",
                    "effective_to",
                }
            ),
            field="paper_cost_model",
        )
        try:
            cost_model = PaperCostModelV1(**dict(cost_document))
        except PaperContractError as exc:
            raise ExperimentPolicyError("EXPERIMENT_PAPER_COST_MODEL_INVALID") from exc
        result = {
            "account_id": _identifier(document["account_id"], field="paper_account_id"),
            "setup_cycle_id": _identifier(
                document["setup_cycle_id"], field="paper_setup_cycle_id"
            ),
            "logical_agent_id": _identifier(
                document["logical_agent_id"], field="paper_logical_agent_id"
            ),
            "agent_generation": _positive_int(
                document["agent_generation"],
                field="paper_agent_generation",
                maximum=1_000_000,
            ),
            "account_mode": _identifier(
                document["account_mode"], field="paper_account_mode"
            ),
            "base_currency": _identifier(
                document["base_currency"], field="paper_base_currency"
            ),
            "initial_balance": _decimal(
                document["initial_balance"], field="paper_initial_balance"
            ),
            "max_leverage": _decimal(
                document["max_leverage"], field="paper_max_leverage"
            ),
            "max_position_notional": _decimal(
                document["max_position_notional"], field="paper_max_position_notional"
            ),
            "max_decision_loss": _decimal(
                document["max_decision_loss"], field="paper_max_decision_loss"
            ),
            "max_observed_drawdown": _decimal(
                document["max_observed_drawdown"], field="paper_max_observed_drawdown"
            ),
            "cost_model": cost_model.to_dict(),
        }
        if result["account_mode"] != "LINEAR_PERP" or result["base_currency"] != "USDT":
            raise ExperimentPolicyError("EXPERIMENT_PAPER_PRODUCT_SCOPE_INVALID")
        if Decimal(result["max_position_notional"]) > (
            Decimal(result["initial_balance"]) * Decimal(result["max_leverage"])
        ):
            raise ExperimentPolicyError("EXPERIMENT_PAPER_NOTIONAL_EXCEEDS_LEVERAGE_CAP")
        if Decimal(result["max_decision_loss"]) > Decimal(result["initial_balance"]):
            raise ExperimentPolicyError("EXPERIMENT_PAPER_DECISION_LOSS_EXCEEDS_BALANCE")
        if Decimal(result["max_observed_drawdown"]) > Decimal(result["initial_balance"]):
            raise ExperimentPolicyError("EXPERIMENT_PAPER_DRAWDOWN_EXCEEDS_BALANCE")
        return MappingProxyType(result)

    def _validate_evaluation(self, value: object) -> Mapping[str, Any]:
        document = _exact_mapping(
            value,
            fields=frozenset(
                {
                    "mode",
                    "total_score_enabled",
                    "actual_execution_status",
                    "predictive_claim",
                    "continuity_claim",
                }
            ),
            field="evaluation",
        )
        expected_mode = (
            "INDEPENDENT_CAPABILITY_PILOT"
            if self.phase == "CAPABILITY_PILOT"
            else "CONTINUITY_FORWARD_PAPER"
        )
        expected_continuity = "NOT_TESTED" if self.phase == "CAPABILITY_PILOT" else "PRIMARY"
        if (
            document["mode"] != expected_mode
            or document["total_score_enabled"] is not False
            or document["actual_execution_status"]
            != "NOT_APPLICABLE_NOT_AUTHORIZED"
            or document["continuity_claim"] != expected_continuity
        ):
            raise ExperimentPolicyError("EXPERIMENT_EVALUATION_BOUNDARY_INVALID")
        return MappingProxyType(
            {
                "mode": expected_mode,
                "total_score_enabled": False,
                "actual_execution_status": "NOT_APPLICABLE_NOT_AUTHORIZED",
                "predictive_claim": _text(
                    document["predictive_claim"], field="predictive_claim"
                ),
                "continuity_claim": expected_continuity,
            }
        )

    @property
    def policy_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": EXPERIMENT_POLICY_SCHEMA_ID,
            "schema_version": EXPERIMENT_POLICY_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "phase": self.phase,
            "venue_id": self.venue_id,
            "instrument_id": self.instrument_id,
            "market_contract_identity": self.market_contract_identity,
            "data_profile": self.data_profile,
            "starts_at": self.starts_at,
            "duration_seconds": self.duration_seconds,
            "decision_horizon_seconds": self.decision_horizon_seconds,
            "outcome_tolerance_seconds": self.outcome_tolerance_seconds,
            "base_sampling_seconds": self.base_sampling_seconds,
            "active_sampling_seconds": self.active_sampling_seconds,
            "capability_ids": list(self.capability_ids),
            "public_data_authorized": self.public_data_authorized,
            "local_paper_authorized": self.local_paper_authorized,
            "testnet_authorized": self.testnet_authorized,
            "live_authorized": self.live_authorized,
            "private_credentials_authorized": self.private_credentials_authorized,
            "external_orders_authorized": self.external_orders_authorized,
            "funds_authorized": self.funds_authorized,
            "paper_account": None
            if self.paper_account is None
            else {
                **{
                    key: self.paper_account[key]
                    for key in self.paper_account
                    if key != "cost_model"
                },
                "cost_model": dict(self.paper_account["cost_model"]),
            },
            "evaluation": dict(self.evaluation),
            "missing_data_policy": self.missing_data_policy,
            "restart_if": list(self.restart_if),
            "continue_if": list(self.continue_if),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExperimentPolicyV1":
        fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "experiment_id",
                "run_id",
                "phase",
                "venue_id",
                "instrument_id",
                "market_contract_identity",
                "data_profile",
                "starts_at",
                "duration_seconds",
                "decision_horizon_seconds",
                "outcome_tolerance_seconds",
                "base_sampling_seconds",
                "active_sampling_seconds",
                "capability_ids",
                "public_data_authorized",
                "local_paper_authorized",
                "testnet_authorized",
                "live_authorized",
                "private_credentials_authorized",
                "external_orders_authorized",
                "funds_authorized",
                "paper_account",
                "evaluation",
                "missing_data_policy",
                "restart_if",
                "continue_if",
            }
        )
        if not isinstance(value, Mapping) or frozenset(value) != fields:
            raise ExperimentPolicyError("EXPERIMENT_POLICY_FIELDS_INVALID")
        if (
            value["schema_id"] != EXPERIMENT_POLICY_SCHEMA_ID
            or value["schema_version"] != EXPERIMENT_POLICY_SCHEMA_VERSION
        ):
            raise ExperimentPolicyError("EXPERIMENT_POLICY_SCHEMA_INVALID")
        return cls(
            **{
                key: value[key]
                for key in fields - {"schema_id", "schema_version"}
            }
        )


__all__ = [
    "EXPERIMENT_CAPABILITIES",
    "EXPERIMENT_MISSING_DATA_POLICY",
    "EXPERIMENT_PHASES",
    "EXPERIMENT_POLICY_SCHEMA_ID",
    "EXPERIMENT_POLICY_SCHEMA_VERSION",
    "ExperimentPolicyError",
    "ExperimentPolicyV1",
]
