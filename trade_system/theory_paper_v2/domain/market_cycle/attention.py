"""Durable V3.3.2 logical-Agent and self-managed attention contracts.

``AttentionRequest`` is the trading Goal's immutable next-check checkpoint.
The repository may append and replay it, but there is deliberately no domain
contract for a supervisor to approve, schedule, dispatch, or acknowledge it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from ..contracts.canonical import canonical_digest


class AttentionContractError(ValueError):
    """An attention or logical-Agent value violates the frozen contract."""


ATTENTION_MODES = frozenset({"CONTINUE_NOW", "WAKE_AFTER", "RELEASE", "OTHER"})
AGENT_REGISTRY_STATUSES = frozenset(
    {"ACTIVE", "IDLE", "UNAVAILABLE", "RECOVERING", "RELEASED"}
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-/]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PHYSICAL_GOAL_RE = re.compile(
    r"^codex-thread:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)

GOAL_ATTENTION_CHECKPOINT_SCHEMA_ID = (
    "agent-trade-emotion.v332-goal-attention-checkpoint"
)
GOAL_ATTENTION_CHECKPOINT_SCHEMA_VERSION = "1.0.0"


def _identifier(value: object, *, field_name: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise AttentionContractError(f"ATTENTION_{field_name.upper()}_INVALID")
    return value


def _optional_identifier(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field_name=field_name)


def _text(value: object, *, field_name: str, maximum: int = 16_384) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise AttentionContractError(f"ATTENTION_{field_name.upper()}_INVALID")
    return value


def _reference(value: object, *, field_name: str) -> str:
    reference = _text(value, field_name=field_name, maximum=2_048)
    if any(ord(character) < 32 for character in reference):
        raise AttentionContractError(f"ATTENTION_{field_name.upper()}_INVALID")
    return reference


def _optional_reference(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _reference(value, field_name=field_name)


def _positive_int(value: object, *, field_name: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise AttentionContractError(f"ATTENTION_{field_name.upper()}_INVALID")
    return value


def _timestamp(value: object, *, field_name: str) -> datetime:
    if type(value) is not str or not value or len(value) > 64:
        raise AttentionContractError(f"ATTENTION_{field_name.upper()}_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AttentionContractError(
            f"ATTENTION_{field_name.upper()}_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AttentionContractError(f"ATTENTION_{field_name.upper()}_INVALID")
    return parsed


def _exact_keys(
    value: object,
    *,
    required: frozenset[str],
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != required:
        raise AttentionContractError(f"ATTENTION_{context.upper()}_FIELDS_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class AgentRegistry:
    """Current physical binding for one durable logical trading Agent."""

    logical_agent_id: str
    symbol: str
    generation: int
    continuity_nonce: str
    physical_task_id: str | None
    status: str
    registered_at: str
    prior_continuity_nonce: str | None = None
    resume_capsule_ref: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.logical_agent_id, field_name="logical_agent_id")
        _identifier(self.symbol, field_name="symbol")
        _positive_int(self.generation, field_name="generation")
        _identifier(self.continuity_nonce, field_name="continuity_nonce")
        _optional_reference(self.physical_task_id, field_name="physical_task_id")
        _timestamp(self.registered_at, field_name="registered_at")
        if self.status not in AGENT_REGISTRY_STATUSES:
            raise AttentionContractError("ATTENTION_AGENT_STATUS_INVALID")
        if self.status in {"ACTIVE", "IDLE", "RECOVERING"} and self.physical_task_id is None:
            raise AttentionContractError("ATTENTION_AGENT_PHYSICAL_TASK_REQUIRED")
        prior = _optional_identifier(
            self.prior_continuity_nonce, field_name="prior_continuity_nonce"
        )
        capsule = _optional_reference(
            self.resume_capsule_ref, field_name="resume_capsule_ref"
        )
        if self.generation == 1 and (prior is not None or capsule is not None):
            raise AttentionContractError("ATTENTION_AGENT_GENESIS_LINEAGE_INVALID")
        if self.generation > 1 and (prior is None or capsule is None):
            raise AttentionContractError("ATTENTION_AGENT_RECOVERY_LINEAGE_REQUIRED")
        if prior == self.continuity_nonce:
            raise AttentionContractError("ATTENTION_AGENT_CONTINUITY_NOT_ROTATED")

    def to_dict(self) -> dict[str, object]:
        return {
            "logical_agent_id": self.logical_agent_id,
            "symbol": self.symbol,
            "generation": self.generation,
            "continuity_nonce": self.continuity_nonce,
            "physical_task_id": self.physical_task_id,
            "status": self.status,
            "registered_at": self.registered_at,
            "prior_continuity_nonce": self.prior_continuity_nonce,
            "resume_capsule_ref": self.resume_capsule_ref,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AgentRegistry":
        fields = frozenset(
            {
                "logical_agent_id",
                "symbol",
                "generation",
                "continuity_nonce",
                "physical_task_id",
                "status",
                "registered_at",
                "prior_continuity_nonce",
                "resume_capsule_ref",
            }
        )
        _exact_keys(value, required=fields, context="agent_registry")
        return cls(**{field: value[field] for field in fields})


@dataclass(frozen=True, slots=True)
class AttentionRequest:
    """Immutable trading-Goal choice of when and why it will check again.

    ``earliest_wake_at`` is retained as the frozen schema name for existing
    read-only projections.  It records the Goal's own intended resume time; it
    is not a request for repository code to perform a wake-up.
    """

    request_id: str
    logical_agent_id: str
    agent_generation: int
    continuity_nonce: str
    symbol: str
    mode: str
    issued_at: str
    continue_until: str | None
    earliest_wake_at: str | None
    latest_useful_at: str
    reason_summary: str
    requested_focus: str
    hypothesis_or_episode_ref: str | None
    position_and_open_order_ref: str | None
    data_cursor: str
    supersedes: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("request_id", "logical_agent_id", "continuity_nonce", "symbol"):
            _identifier(getattr(self, field_name), field_name=field_name)
        _positive_int(self.agent_generation, field_name="agent_generation")
        if self.mode not in ATTENTION_MODES:
            raise AttentionContractError("ATTENTION_MODE_INVALID")
        issued = _timestamp(self.issued_at, field_name="issued_at")
        latest = _timestamp(self.latest_useful_at, field_name="latest_useful_at")
        if latest <= issued:
            raise AttentionContractError("ATTENTION_LATEST_NOT_AFTER_ISSUED")
        continue_until = (
            None
            if self.continue_until is None
            else _timestamp(self.continue_until, field_name="continue_until")
        )
        earliest = (
            None
            if self.earliest_wake_at is None
            else _timestamp(self.earliest_wake_at, field_name="earliest_wake_at")
        )
        if (continue_until is None) == (earliest is None):
            raise AttentionContractError("ATTENTION_EARLIEST_OR_CONTINUE_REQUIRED")
        anchor = continue_until if continue_until is not None else earliest
        assert anchor is not None
        if anchor < issued or anchor > latest:
            raise AttentionContractError("ATTENTION_WINDOW_INVALID")
        if self.mode == "CONTINUE_NOW" and continue_until is None:
            raise AttentionContractError("ATTENTION_CONTINUE_UNTIL_REQUIRED")
        if self.mode in {"WAKE_AFTER", "RELEASE"} and earliest is None:
            raise AttentionContractError("ATTENTION_EARLIEST_WAKE_REQUIRED")
        _text(self.reason_summary, field_name="reason_summary")
        _text(self.requested_focus, field_name="requested_focus")
        _optional_reference(
            self.hypothesis_or_episode_ref,
            field_name="hypothesis_or_episode_ref",
        )
        _optional_reference(
            self.position_and_open_order_ref,
            field_name="position_and_open_order_ref",
        )
        _reference(self.data_cursor, field_name="data_cursor")
        supersedes = _optional_identifier(self.supersedes, field_name="supersedes")
        if supersedes == self.request_id:
            raise AttentionContractError("ATTENTION_REQUEST_SELF_SUPERSEDE")

    @property
    def earliest(self) -> str:
        value = self.continue_until or self.earliest_wake_at
        assert value is not None
        return value

    @property
    def latest(self) -> str:
        return self.latest_useful_at

    @property
    def generation(self) -> int:
        return self.agent_generation

    @property
    def agent_owned_sha256(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "logical_agent_id": self.logical_agent_id,
            "agent_generation": self.agent_generation,
            "continuity_nonce": self.continuity_nonce,
            "symbol": self.symbol,
            "mode": self.mode,
            "issued_at": self.issued_at,
            "continue_until": self.continue_until,
            "earliest_wake_at": self.earliest_wake_at,
            "latest_useful_at": self.latest_useful_at,
            "reason_summary": self.reason_summary,
            "requested_focus": self.requested_focus,
            "hypothesis_or_episode_ref": self.hypothesis_or_episode_ref,
            "position_and_open_order_ref": self.position_and_open_order_ref,
            "data_cursor": self.data_cursor,
            "supersedes": self.supersedes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AttentionRequest":
        fields = frozenset(
            {
                "request_id",
                "logical_agent_id",
                "agent_generation",
                "continuity_nonce",
                "symbol",
                "mode",
                "issued_at",
                "continue_until",
                "earliest_wake_at",
                "latest_useful_at",
                "reason_summary",
                "requested_focus",
                "hypothesis_or_episode_ref",
                "position_and_open_order_ref",
                "data_cursor",
                "supersedes",
            }
        )
        _exact_keys(value, required=fields, context="attention_request")
        return cls(**{field: value[field] for field in fields})


@dataclass(frozen=True, slots=True)
class GoalAttentionCheckpointV1:
    """Controller-authored provenance for one exact Agent attention fact."""

    schema_id: str
    schema_version: str
    run_id: str
    run_manifest_identity_sha256: str
    experiment_policy_sha256: str
    physical_goal_id: str
    physical_goal_source: str
    request_sha256: str
    accepted_at: str
    accepted_clock_source: str

    def __post_init__(self) -> None:
        if (
            self.schema_id != GOAL_ATTENTION_CHECKPOINT_SCHEMA_ID
            or self.schema_version != GOAL_ATTENTION_CHECKPOINT_SCHEMA_VERSION
        ):
            raise AttentionContractError("ATTENTION_GOAL_CHECKPOINT_SCHEMA_INVALID")
        _identifier(self.run_id, field_name="run_id")
        for field_name in (
            "run_manifest_identity_sha256",
            "experiment_policy_sha256",
            "request_sha256",
        ):
            value = getattr(self, field_name)
            if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
                raise AttentionContractError(
                    f"ATTENTION_{field_name.upper()}_INVALID"
                )
        if (
            type(self.physical_goal_id) is not str
            or _PHYSICAL_GOAL_RE.fullmatch(self.physical_goal_id) is None
        ):
            raise AttentionContractError(
                "ATTENTION_GOAL_CHECKPOINT_PHYSICAL_GOAL_INVALID"
            )
        if self.physical_goal_source != "CODEX_THREAD_ID":
            raise AttentionContractError(
                "ATTENTION_GOAL_CHECKPOINT_IDENTITY_SOURCE_INVALID"
            )
        if self.accepted_clock_source != "CONTROLLER_TRUSTED_CLOCK":
            raise AttentionContractError(
                "ATTENTION_GOAL_CHECKPOINT_CLOCK_SOURCE_INVALID"
            )
        _timestamp(self.accepted_at, field_name="accepted_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "run_manifest_identity_sha256": self.run_manifest_identity_sha256,
            "experiment_policy_sha256": self.experiment_policy_sha256,
            "physical_goal_id": self.physical_goal_id,
            "physical_goal_source": self.physical_goal_source,
            "request_sha256": self.request_sha256,
            "accepted_at": self.accepted_at,
            "accepted_clock_source": self.accepted_clock_source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GoalAttentionCheckpointV1":
        fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "run_id",
                "run_manifest_identity_sha256",
                "experiment_policy_sha256",
                "physical_goal_id",
                "physical_goal_source",
                "request_sha256",
                "accepted_at",
                "accepted_clock_source",
            }
        )
        _exact_keys(value, required=fields, context="goal_attention_checkpoint")
        return cls(**{field: value[field] for field in fields})


__all__ = [
    "AGENT_REGISTRY_STATUSES",
    "ATTENTION_MODES",
    "AgentRegistry",
    "AttentionContractError",
    "AttentionRequest",
    "GOAL_ATTENTION_CHECKPOINT_SCHEMA_ID",
    "GOAL_ATTENTION_CHECKPOINT_SCHEMA_VERSION",
    "GoalAttentionCheckpointV1",
]
