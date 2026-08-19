"""Atomic E0 UnitOfWork and append-only event chain."""

from .compatibility import (
    EventCompatibilityError,
    EventReplayCompatibilityManifest,
    ProjectionCursorEntry,
    UpcasterEntry,
    build_event_replay_compatibility_manifest,
    require_authoritative_command_head,
    verify_event_replay_compatibility,
)
from .models import (
    AggregatePrecondition,
    AggregateUpdate,
    CommitReceipt,
    E0CommitPlan,
    EventDraft,
)
from .store import EventStoreError, FileUnitOfWork

__all__ = [
    "AggregatePrecondition",
    "AggregateUpdate",
    "CommitReceipt",
    "E0CommitPlan",
    "EventCompatibilityError",
    "EventDraft",
    "EventReplayCompatibilityManifest",
    "EventStoreError",
    "FileUnitOfWork",
    "ProjectionCursorEntry",
    "UpcasterEntry",
    "build_event_replay_compatibility_manifest",
    "require_authoritative_command_head",
    "verify_event_replay_compatibility",
]
