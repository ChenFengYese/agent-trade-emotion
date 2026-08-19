"""Append-only V3.3.2 journal for Agent-owned attention checkpoints.

The persistent trading Goal chooses its own next-check window.  This module
only binds that immutable choice to the current logical-Agent generation and
replays the append-only stream.  It does not approve, schedule, dispatch,
acknowledge, complete, or recover wake-ups.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from ...domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
    GoalAttentionCheckpointV1,
)


class AttentionApplicationError(RuntimeError):
    """An append or replay violates the logical-Agent checkpoint contract."""


_EVENT_AGENT_REGISTERED = "AGENT_REGISTERED"
_EVENT_AGENT_RECOVERED = "AGENT_GENERATION_RECOVERED"
_EVENT_REQUEST_SUBMITTED = "ATTENTION_REQUEST_SUBMITTED"
_LEGACY_REQUEST_PAYLOAD_FIELDS = frozenset({"request", "accepted_at"})
_GOAL_REQUEST_PAYLOAD_FIELDS = frozenset(
    {"request", "accepted_at", "goal_checkpoint"}
)


class AttentionEvent(Protocol):
    revision: int
    event_id: str
    event_type: str
    occurred_at: str
    payload: Mapping[str, Any]


class AttentionRepositoryPort(Protocol):
    def load(self, logical_agent_id: str) -> Any: ...

    def compare_and_swap(
        self,
        logical_agent_id: str,
        *,
        expected_revision: int,
        event_id: str,
        event_type: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> AttentionEvent: ...

    def replay(self, logical_agent_id: str) -> tuple[AttentionEvent, ...]: ...


def _timestamp(value: str, *, code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise AttentionApplicationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AttentionApplicationError(code)
    return parsed


@dataclass(frozen=True, slots=True)
class AttentionProjection:
    """Rebuildable view of one persistent Goal's registry and checkpoints."""

    logical_agent_id: str
    revision: int
    registry: AgentRegistry | None
    requests: Mapping[str, AttentionRequest]
    request_accepted_ats: Mapping[str, str]
    request_goal_checkpoints: Mapping[str, GoalAttentionCheckpointV1 | None]
    request_statuses: Mapping[str, str]
    active_request_id: str | None

    def request(self, request_id: str) -> AttentionRequest:
        try:
            return self.requests[request_id]
        except KeyError as exc:
            raise AttentionApplicationError("ATTENTION_REQUEST_NOT_FOUND") from exc


def _empty_projection(logical_agent_id: str) -> AttentionProjection:
    empty: Mapping[str, Any] = MappingProxyType({})
    return AttentionProjection(
        logical_agent_id=logical_agent_id,
        revision=0,
        registry=None,
        requests=empty,
        request_accepted_ats=empty,
        request_goal_checkpoints=empty,
        request_statuses=empty,
        active_request_id=None,
    )


def _replay_attention_projection(
    repository: AttentionRepositoryPort, logical_agent_id: str
) -> AttentionProjection:
    """Replay registry and Agent-authored checkpoints; reject all other events."""

    events = repository.replay(logical_agent_id)
    if not events:
        return _empty_projection(logical_agent_id)

    registry: AgentRegistry | None = None
    requests: dict[str, AttentionRequest] = {}
    request_accepted_ats: dict[str, str] = {}
    request_goal_checkpoints: dict[str, GoalAttentionCheckpointV1 | None] = {}
    statuses: dict[str, str] = {}
    active_request_id: str | None = None
    revision = 0

    for event in events:
        if event.revision != revision + 1:
            raise AttentionApplicationError("ATTENTION_REPLAY_REVISION_INVALID")
        revision = event.revision
        payload = event.payload

        if event.event_type == _EVENT_AGENT_REGISTERED:
            if registry is not None or frozenset(payload) != {"registry"}:
                raise AttentionApplicationError(
                    "ATTENTION_AGENT_REGISTER_REPLAY_INVALID"
                )
            candidate = AgentRegistry.from_dict(payload["registry"])
            if (
                candidate.logical_agent_id != logical_agent_id
                or candidate.generation != 1
                or event.occurred_at != candidate.registered_at
            ):
                raise AttentionApplicationError(
                    "ATTENTION_AGENT_REGISTER_REPLAY_INVALID"
                )
            registry = candidate
            continue

        if event.event_type == _EVENT_AGENT_RECOVERED:
            if registry is None or frozenset(payload) != {"registry"}:
                raise AttentionApplicationError(
                    "ATTENTION_AGENT_RECOVERY_REPLAY_INVALID"
                )
            candidate = AgentRegistry.from_dict(payload["registry"])
            if (
                candidate.logical_agent_id != registry.logical_agent_id
                or candidate.symbol != registry.symbol
                or candidate.generation != registry.generation + 1
                or candidate.prior_continuity_nonce != registry.continuity_nonce
                or event.occurred_at != candidate.registered_at
            ):
                raise AttentionApplicationError(
                    "ATTENTION_AGENT_RECOVERY_REPLAY_INVALID"
                )
            registry = candidate
            continue

        if registry is None:
            raise AttentionApplicationError("ATTENTION_AGENT_REGISTRY_REQUIRED")

        payload_fields = frozenset(payload)
        if event.event_type != _EVENT_REQUEST_SUBMITTED or payload_fields not in {
            _LEGACY_REQUEST_PAYLOAD_FIELDS,
            _GOAL_REQUEST_PAYLOAD_FIELDS,
        }:
            raise AttentionApplicationError(
                f"ATTENTION_EVENT_TYPE_UNKNOWN:{event.event_type}"
            )

        request = AttentionRequest.from_dict(payload["request"])
        accepted_at = payload["accepted_at"]
        goal_checkpoint = (
            None
            if payload_fields == _LEGACY_REQUEST_PAYLOAD_FIELDS
            else GoalAttentionCheckpointV1.from_dict(payload["goal_checkpoint"])
        )
        accepted = _timestamp(
            accepted_at, code="ATTENTION_REQUEST_ACCEPTED_AT_INVALID"
        )
        issued = _timestamp(request.issued_at, code="ATTENTION_ISSUED_AT_INVALID")
        latest = _timestamp(request.latest, code="ATTENTION_LATEST_TIME_INVALID")
        if (
            event.occurred_at != accepted_at
            or accepted < issued
            or accepted > latest
        ):
            raise AttentionApplicationError("ATTENTION_REQUEST_RECEIPT_TIME_INVALID")
        if goal_checkpoint is not None and (
            goal_checkpoint.request_sha256 != request.agent_owned_sha256
            or goal_checkpoint.accepted_at != accepted_at
            or goal_checkpoint.physical_goal_id != registry.physical_task_id
        ):
            raise AttentionApplicationError(
                "ATTENTION_GOAL_CHECKPOINT_BINDING_INVALID"
            )
        if (
            request.logical_agent_id != logical_agent_id
            or request.symbol != registry.symbol
            or request.agent_generation != registry.generation
            or request.continuity_nonce != registry.continuity_nonce
            or request.request_id in requests
        ):
            raise AttentionApplicationError(
                "ATTENTION_REQUEST_AGENT_BINDING_INVALID"
            )
        if active_request_id is None:
            if request.supersedes is not None:
                raise AttentionApplicationError(
                    "ATTENTION_SUPERSEDES_NO_ACTIVE_REQUEST"
                )
        else:
            if request.supersedes != active_request_id:
                raise AttentionApplicationError(
                    "ATTENTION_ACTIVE_REQUEST_REQUIRES_SUPERSEDES"
                )
            statuses[active_request_id] = "SUPERSEDED"
        requests[request.request_id] = request
        request_accepted_ats[request.request_id] = accepted_at
        request_goal_checkpoints[request.request_id] = goal_checkpoint
        statuses[request.request_id] = "PENDING"
        active_request_id = request.request_id

    return AttentionProjection(
        logical_agent_id=logical_agent_id,
        revision=revision,
        registry=registry,
        requests=MappingProxyType(dict(requests)),
        request_accepted_ats=MappingProxyType(dict(request_accepted_ats)),
        request_goal_checkpoints=MappingProxyType(dict(request_goal_checkpoints)),
        request_statuses=MappingProxyType(dict(statuses)),
        active_request_id=active_request_id,
    )


class AttentionService:
    """CAS-backed journal for the persistent trading Goal's own checkpoints."""

    def __init__(self, repository: AttentionRepositoryPort) -> None:
        if not all(
            callable(getattr(repository, name, None))
            for name in ("load", "compare_and_swap", "replay")
        ):
            raise AttentionApplicationError("ATTENTION_REPOSITORY_PORT_INVALID")
        self._repository = repository

    def status(self, logical_agent_id: str) -> AttentionProjection:
        return _replay_attention_projection(self._repository, logical_agent_id)

    @staticmethod
    def _expected(state: AttentionProjection, supplied: int | None) -> int:
        if supplied is None:
            return state.revision
        if type(supplied) is not int or supplied < 0:
            raise AttentionApplicationError(
                "ATTENTION_EXPECTED_REVISION_INVALID"
            )
        return supplied

    def submit_request(
        self,
        request: AttentionRequest,
        *,
        received_at: str | None = None,
        expected_revision: int | None = None,
    ) -> AttentionRequest:
        """Append one checkpoint or return its exact idempotent replay."""

        if not isinstance(request, AttentionRequest):
            raise AttentionApplicationError("ATTENTION_REQUEST_INVALID")
        state = self.status(request.logical_agent_id)
        trusted_received_at = request.issued_at if received_at is None else received_at
        accepted = _timestamp(
            trusted_received_at, code="ATTENTION_REQUEST_ACCEPTED_AT_INVALID"
        )
        issued = _timestamp(request.issued_at, code="ATTENTION_ISSUED_AT_INVALID")
        latest = _timestamp(request.latest, code="ATTENTION_LATEST_TIME_INVALID")
        if accepted < issued:
            raise AttentionApplicationError(
                "ATTENTION_REQUEST_RECEIPT_BEFORE_ISSUED"
            )
        if accepted > latest:
            raise AttentionApplicationError("ATTENTION_REQUEST_EXPIRED")
        existing = state.requests.get(request.request_id)
        if existing is not None:
            if existing != request:
                raise AttentionApplicationError("ATTENTION_REQUEST_ID_CONFLICT")
            if state.request_accepted_ats[request.request_id] != trusted_received_at:
                raise AttentionApplicationError(
                    "ATTENTION_REQUEST_RECEIPT_TIME_CONFLICT"
                )
            return existing
        if state.registry is None:
            raise AttentionApplicationError("ATTENTION_AGENT_REGISTRY_REQUIRED")
        if (
            request.symbol != state.registry.symbol
            or request.agent_generation != state.registry.generation
            or request.continuity_nonce != state.registry.continuity_nonce
        ):
            raise AttentionApplicationError(
                "ATTENTION_REQUEST_AGENT_BINDING_INVALID"
            )
        if state.active_request_id is None:
            if request.supersedes is not None:
                raise AttentionApplicationError(
                    "ATTENTION_SUPERSEDES_NO_ACTIVE_REQUEST"
                )
        elif request.supersedes != state.active_request_id:
            raise AttentionApplicationError(
                "ATTENTION_ACTIVE_REQUEST_REQUIRES_SUPERSEDES"
            )

        self._repository.compare_and_swap(
            request.logical_agent_id,
            expected_revision=self._expected(state, expected_revision),
            event_id=f"request:{request.request_id}",
            event_type=_EVENT_REQUEST_SUBMITTED,
            occurred_at=trusted_received_at,
            payload={
                "request": request.to_dict(),
                "accepted_at": trusted_received_at,
            },
        )
        return request

__all__ = [
    "AttentionApplicationError",
    "AttentionProjection",
    "AttentionRepositoryPort",
    "AttentionService",
]
