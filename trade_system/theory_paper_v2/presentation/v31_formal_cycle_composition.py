"""Local production composition for the authorized V3.1 formal cycle.

The preparation entry point loads the frozen active chain, derives the next
cycle from the run checkpoint, persists its authoring packet, and initializes
the one-attempt transport cursor.  It does not call an Agent.  The completion
entry point can be called only after the independent two-stage transport is
durably complete; it persists the accepted research chronology and schedules
the absolute public mark-price monitor without collecting its future outcome.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from ..application.v31_agent_transport import initialize_v31_agent_transport
from ..application.v31_formal_cycle import (
    complete_v31_formal_authoring_cycle,
    prepare_v31_formal_authoring_cycle,
)
from ..domain.v31_experiment_contracts import FrozenMonitorRule
from ..infrastructure.authority.v31_current_research import (
    load_v31_active_authorization_chain,
)
from ..infrastructure.v31_agent_transport_store import (
    LocalV31AgentTransportStore,
)
from ..infrastructure.v31_monitor_store import LocalV31MonitorStore
from ..infrastructure.v31_research_store import LocalV31ResearchStore


def prepare_local_v31_formal_cycle(
    *,
    project_root: Path,
    run_root: Path,
    transport_created_at: str,
    owner_id: str,
    lease_expires_at: str,
) -> Mapping[str, Any]:
    """Prepare the checkpoint-derived packet and cursor; invoke no Agent."""

    active_chain = load_v31_active_authorization_chain(project_root)
    research_store = LocalV31ResearchStore(run_root)
    prepared = prepare_v31_formal_authoring_cycle(
        store=research_store, active_chain=active_chain
    )
    transport_checkpoint = initialize_v31_agent_transport(
        store=LocalV31AgentTransportStore(run_root),
        run_id=str(prepared["run_id"]),
        cycle_index=int(prepared["cycle_index"]),
        created_at=transport_created_at,
        owner_id=owner_id,
        lease_expires_at=lease_expires_at,
    )
    return {
        **dict(prepared),
        "transport_checkpoint": dict(transport_checkpoint),
        "agent_invoked": False,
        "outcome_collection_performed": False,
    }


def complete_local_v31_formal_cycle(
    *,
    project_root: Path,
    run_root: Path,
    completed_at: str,
    recorded_at: str,
    monitor_runtime_created_at: str,
    monitor_rules: Sequence[FrozenMonitorRule],
) -> Mapping[str, Any]:
    """Replay a completed local transport, accept it, and schedule only."""

    active_chain = load_v31_active_authorization_chain(project_root)
    return complete_v31_formal_authoring_cycle(
        research_store=LocalV31ResearchStore(run_root),
        transport_store=LocalV31AgentTransportStore(run_root),
        monitor_store=LocalV31MonitorStore(run_root),
        active_chain=active_chain,
        completed_at=completed_at,
        recorded_at=recorded_at,
        monitor_runtime_created_at=monitor_runtime_created_at,
        monitor_rules=monitor_rules,
    )


__all__ = [
    "complete_local_v31_formal_cycle",
    "prepare_local_v31_formal_cycle",
]
