"""Bound one Agent call to one sealed market snapshot."""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any, Mapping, Sequence

from ...domain.contracts.canonical import canonical_bytes
from ...domain.market_cycle.analysis import record_agent_decision
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    HypothesisRecord,
    InputSnapshot,
    MarketCycleContractError,
    VerifiedMemoryItem,
    snapshot_bound_memory_context,
)
from ...domain.market_cycle.evidence import calculate_multitimeframe_context
from ...domain.market_cycle.theory import (
    CURRENT_THEORY_IDENTITY,
    TheoryIdentity,
    V332_THEORY_IDENTITY,
    require_supported_theory_identity,
)
from .ports import (
    AgentAnalysisPending,
    AgentDecision,
    AgentPacket,
    AgentPort,
    ClockPort,
    DecisionContextPort,
)


_AGENT_HOT_PATH_THEORY_FILES = (
    "README.md",
    "01_MARKET_COGNITION.md",
    "02_DYNAMIC_POSITION_MANAGEMENT.md",
    "03_HYPOTHESIS_SYSTEM.md",
    "04_EXECUTION_AND_AGENT.md",
    "05_RISK_AND_BOUNDARIES.md",
)
_V332_AGENT_HOT_PATH_THEORY_FILES = (
    "README.md",
    "00_USER_DIRECTED_EXPERIMENTAL_SCOPE.md",
    "01_MARKET_COGNITION.md",
    "02_DYNAMIC_POSITION_MANAGEMENT.md",
    "03_HYPOTHESIS_SYSTEM.md",
    "04_EXECUTION_AND_AGENT.md",
    "05_RISK_AND_BOUNDARIES.md",
    "08_SANDISK_USDT_TEACHING_CASE.md",
    "09_STATE_TRANSITION_AND_EVALUATION.md",
)
_HOT_PATH_BY_IDENTITY = {
    CURRENT_THEORY_IDENTITY: _AGENT_HOT_PATH_THEORY_FILES,
    V332_THEORY_IDENTITY: _V332_AGENT_HOT_PATH_THEORY_FILES,
}


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise MarketCycleContractError("clock must return an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketCycleContractError("clock timestamp must include a UTC offset")
    return parsed


def select_analysis_theory_fragments(
    fragments: Mapping[str, str],
    *,
    analysis_profile: str = "COLD",
    theory_identity: TheoryIdentity = CURRENT_THEORY_IDENTITY,
) -> Mapping[str, str]:
    """Return the complete verified COLD package without semantic filtering."""

    if analysis_profile != "COLD":
        raise ValueError(f"unsupported analysis profile: {analysis_profile}")
    try:
        identity = require_supported_theory_identity(theory_identity)
    except ValueError as exc:
        raise ValueError("unsupported theory identity") from exc
    expected_files = _HOT_PATH_BY_IDENTITY[identity]
    if tuple(fragments) != expected_files or not all(
        isinstance(name, str)
        and name
        and isinstance(content, str)
        and content.strip()
        for name, content in fragments.items()
    ):
        raise ValueError(
            "verified theory hot-path documents are required in manifest order"
        )
    return dict(fragments)


def analyze_snapshot(
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
    *,
    agent: AgentPort,
    clock: ClockPort,
    theory_fragments: Mapping[str, str],
    verified_memory: Sequence[VerifiedMemoryItem | Mapping[str, Any]] = (),
    decision_context: DecisionContextPort | None = None,
    token_budget: int = 16_000,
    time_budget_seconds: int = 600,
) -> HypothesisRecord:
    """Request and seal one verbatim, Agent-owned reference decision."""

    available_seconds = int(
        (
            _timestamp(snapshot.outcome_due_at)
            - _timestamp(snapshot.sealed_at)
        ).total_seconds()
    )
    if available_seconds < 1:
        raise MarketCycleContractError(
            "Agent decision window has less than one complete second"
        )
    if type(time_budget_seconds) is not int or time_budget_seconds < 1:
        raise MarketCycleContractError("Agent time budget must be a positive integer")
    effective_time_budget_seconds = min(time_budget_seconds, available_seconds)

    memory_context = snapshot_bound_memory_context(snapshot, verified_memory)
    calculations = calculate_multitimeframe_context(snapshot, snapshot_ref)
    paper_context = (
        None
        if decision_context is None
        else decision_context.context(snapshot, snapshot_ref)
    )
    packet = AgentPacket(
        cycle_id=snapshot.cycle_id,
        request_id=snapshot.request_id,
        theory_identity=snapshot.theory_identity.to_dict(),
        theory_fragments=select_analysis_theory_fragments(
            theory_fragments,
            analysis_profile=snapshot.analysis_profile,
            theory_identity=snapshot.theory_identity,
        ),
        input_snapshot_ref=snapshot_ref.to_dict(),
        input_snapshot=snapshot.to_dict(),
        lawful_actions=snapshot.lawful_actions,
        memory_context=memory_context,
        deterministic_calculations=calculations.to_dict(),
        decision_deadline_at=snapshot.outcome_due_at,
        token_budget=token_budget,
        time_budget_seconds=effective_time_budget_seconds,
        paper_context=paper_context,
    )
    expected_request_sha256 = hashlib.sha256(
        canonical_bytes(packet.to_dict())
    ).hexdigest()
    try:
        decision = agent.analyze(packet)
    except AgentAnalysisPending:
        if _timestamp(clock()) >= _timestamp(snapshot.outcome_due_at):
            raise MarketCycleContractError(
                "MARKET_CYCLE_AGENT_DECISION_WINDOW_EXPIRED"
            )
        raise
    if not isinstance(decision, AgentDecision):
        raise MarketCycleContractError("AgentPort must return AgentDecision")
    if (
        decision.cycle_id != snapshot.cycle_id
        or decision.theory_identity != snapshot.theory_identity.to_dict()
        or decision.request_sha256 != expected_request_sha256
        or decision.delivery_path != "transport/agent-delivery.json"
    ):
        raise MarketCycleContractError("AgentDecision binding does not match snapshot")
    delivered_at = _timestamp(decision.delivered_at)
    if not _timestamp(snapshot.sealed_at) <= delivered_at < _timestamp(
        snapshot.outcome_due_at
    ):
        raise MarketCycleContractError(
            "AgentDecision must be delivered after snapshot sealing and before outcome"
        )
    return record_agent_decision(
        snapshot,
        snapshot_ref,
        record_id=f"{snapshot.cycle_id}.hypotheses",
        sealed_at=decision.delivered_at,
        agent_delivered_at=decision.delivered_at,
        agent_request_sha256=decision.request_sha256,
        agent_delivery_path=decision.delivery_path,
        agent_delivery_sha256=decision.delivery_sha256,
        agent_decision_text=decision.decision_text,
        agent_decision_size_bytes=decision.decision_size_bytes,
        agent_decision_sha256=decision.decision_sha256,
        unresolved_unknowns=snapshot.unknowns,
    )


__all__ = ["analyze_snapshot", "select_analysis_theory_fragments"]
