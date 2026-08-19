"""Successor-v2 shadow inference framework.

This package is deliberately separate from the active theory-paper v1 runtime.
It can read frozen v1 cycles and create non-authoritative sidecars, but it
cannot mutate v1 artifacts or authorize a paper/live action.
"""

from .application import replay_cycles
from .domain import (
    FRAMEWORK_ID,
    HISTORICAL_MODE,
    LIVE_MODE,
    InferenceV2Error,
    build_cycle_sidecar,
    derive_revision_state,
    validate_sidecar,
)

__all__ = [
    "FRAMEWORK_ID",
    "HISTORICAL_MODE",
    "LIVE_MODE",
    "InferenceV2Error",
    "build_cycle_sidecar",
    "derive_revision_state",
    "replay_cycles",
    "validate_sidecar",
]
