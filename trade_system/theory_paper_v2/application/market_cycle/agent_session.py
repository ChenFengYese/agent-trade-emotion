"""Persistent logical trading-Goal registration and generation recovery."""

from __future__ import annotations

from ...domain.market_cycle.attention import AgentRegistry
from .attention import (
    AttentionApplicationError,
    AttentionProjection,
    AttentionRepositoryPort,
    _replay_attention_projection,
)


class AgentSessionService:
    """Own physical-task bindings while preserving one logical Agent lineage."""

    def __init__(self, repository: AttentionRepositoryPort) -> None:
        if not all(
            callable(getattr(repository, name, None))
            for name in ("load", "compare_and_swap", "replay")
        ):
            raise AttentionApplicationError("ATTENTION_REPOSITORY_PORT_INVALID")
        self._repository = repository

    def status(self, logical_agent_id: str) -> AttentionProjection:
        return _replay_attention_projection(self._repository, logical_agent_id)

    def current(self, logical_agent_id: str) -> AgentRegistry:
        registry = self.status(logical_agent_id).registry
        if registry is None:
            raise AttentionApplicationError("ATTENTION_AGENT_NOT_REGISTERED")
        return registry

    def register(
        self,
        registry: AgentRegistry,
        *,
        expected_revision: int = 0,
    ) -> AgentRegistry:
        if not isinstance(registry, AgentRegistry) or registry.generation != 1:
            raise AttentionApplicationError("ATTENTION_AGENT_GENESIS_INVALID")
        state = self.status(registry.logical_agent_id)
        if state.registry is not None:
            if state.registry != registry:
                raise AttentionApplicationError("ATTENTION_AGENT_ALREADY_REGISTERED")
            return state.registry
        self._repository.compare_and_swap(
            registry.logical_agent_id,
            expected_revision=expected_revision,
            event_id=f"agent:{registry.logical_agent_id}:generation:1",
            event_type="AGENT_REGISTERED",
            occurred_at=registry.registered_at,
            payload={"registry": registry.to_dict()},
        )
        return registry

    def recover_generation(
        self,
        logical_agent_id: str,
        *,
        failed_generation: int,
        new_physical_task_id: str,
        new_continuity_nonce: str,
        resume_capsule_ref: str,
        recovered_at: str,
        expected_revision: int | None = None,
    ) -> AgentRegistry:
        """Create exactly ``generation+1`` from the durable current registry."""

        state = self.status(logical_agent_id)
        current = state.registry
        if current is None:
            raise AttentionApplicationError("ATTENTION_AGENT_NOT_REGISTERED")
        if current.generation == failed_generation + 1:
            if (
                current.physical_task_id == new_physical_task_id
                and current.continuity_nonce == new_continuity_nonce
                and current.resume_capsule_ref == resume_capsule_ref
            ):
                return current
            raise AttentionApplicationError("ATTENTION_AGENT_RECOVERY_ID_CONFLICT")
        if current.generation != failed_generation:
            raise AttentionApplicationError("ATTENTION_AGENT_GENERATION_STALE")
        if current.physical_task_id == new_physical_task_id:
            raise AttentionApplicationError("ATTENTION_AGENT_PHYSICAL_TASK_NOT_ROTATED")
        if expected_revision is None:
            expected_revision = state.revision
        recovered = AgentRegistry(
            logical_agent_id=current.logical_agent_id,
            symbol=current.symbol,
            generation=current.generation + 1,
            continuity_nonce=new_continuity_nonce,
            physical_task_id=new_physical_task_id,
            status="ACTIVE",
            registered_at=recovered_at,
            prior_continuity_nonce=current.continuity_nonce,
            resume_capsule_ref=resume_capsule_ref,
        )
        self._repository.compare_and_swap(
            logical_agent_id,
            expected_revision=expected_revision,
            event_id=f"agent:{logical_agent_id}:generation:{recovered.generation}",
            event_type="AGENT_GENERATION_RECOVERED",
            occurred_at=recovered_at,
            payload={"registry": recovered.to_dict()},
        )
        return recovered

AgentLifecycleService = AgentSessionService


__all__ = ["AgentLifecycleService", "AgentSessionService"]
