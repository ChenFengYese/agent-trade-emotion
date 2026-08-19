"""Application boundary for compiling a V3.1 Agent authoring envelope.

No default compiler is provided.  That omission is deliberate: until a real
compiler maps the Agent's open specifications to the existing typed Domain
objects, this service fails closed and cannot produce a selectable cycle.
When supplied, a compiler is treated as untrusted.  Its complete output is
replayed through ``assemble_v31_cycle_evaluation`` before a compilation receipt
is sealed.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from .v31_research_cycle import (
    V31ResearchCycleError,
    assemble_v31_cycle_evaluation,
    verify_v31_cycle_evaluation,
)
from ..domain.agent_research_contract import (
    AgentResearchContractError,
    verify_v31_agent_proposal,
    verify_v31_inputs_receipt,
)
from ..domain.behavior_planning import (
    BehaviorPlanningError,
    verify_complete_action_evaluation,
)
from ..domain.v31_cycle_authoring import (
    V31CycleAuthoringError,
    seal_v31_authoring_compilation_receipt,
    validate_v31_agent_open_analysis_envelope,
    validate_v31_authoring_compilation_receipt,
    validate_v31_proposal_authoring_packet,
)


class V31CycleAuthoringWorkflowError(ValueError):
    """An Agent authoring envelope could not be safely compiled."""


class V31CycleAuthoringCompilerPort(Protocol):
    """Untrusted semantic compiler implemented outside Application.

    The compiler may translate Agent-authored specifications, but it cannot
    select an action or grant execution authority.  Application replays every
    typed output before accepting it.
    """

    compiler_id: str

    def compile(
        self,
        *,
        authoring_packet: Mapping[str, Any],
        authoring_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


_COMPILED_RESULT_FIELDS = frozenset(
    {"inputs_receipt", "agent_proposal", "assembly_inputs"}
)
_FORBIDDEN_SELECTION_KEYS = frozenset(
    {
        "selection",
        "selected",
        "selected_action",
        "selected_candidate_id",
        "action_selection",
        "action_selection_digest",
        "authorized_action",
        "order",
        "order_payload",
    }
)


def _contains_selection(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key.casefold() in _FORBIDDEN_SELECTION_KEYS:
                return True
            if _contains_selection(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_selection(row) for row in value)
    return False


def compile_v31_agent_open_analysis(
    *,
    authoring_packet: Mapping[str, Any],
    authoring_envelope: Mapping[str, Any],
    compiled_at: str,
    compiler: V31CycleAuthoringCompilerPort | None,
) -> dict[str, Any]:
    """Compile, replay, and seal preselection; never perform selection.

    Without an explicit production compiler this function always fails closed.
    A compiler cannot gain authority by returning self-consistent hashes: the
    full existing V3.1 assembly is replayed from the returned typed inputs.
    """

    try:
        packet_digest = validate_v31_proposal_authoring_packet(authoring_packet)
        envelope_digest = validate_v31_agent_open_analysis_envelope(
            authoring_envelope, authoring_packet=authoring_packet
        )
    except V31CycleAuthoringError as exc:
        raise V31CycleAuthoringWorkflowError(
            f"V31_AUTHORING_INPUT_INVALID:{exc}"
        ) from exc
    if compiler is None:
        raise V31CycleAuthoringWorkflowError(
            "V31_AUTHORING_COMPILER_REQUIRED_FAIL_CLOSED"
        )
    compiler_id = getattr(compiler, "compiler_id", None)
    if not isinstance(compiler_id, str) or not compiler_id.strip():
        raise V31CycleAuthoringWorkflowError("V31_AUTHORING_COMPILER_ID_INVALID")
    try:
        raw = compiler.compile(
            authoring_packet=authoring_packet,
            authoring_envelope=authoring_envelope,
        )
    except BaseException as exc:
        raise V31CycleAuthoringWorkflowError(
            "V31_AUTHORING_COMPILER_FAILED_CLOSED"
        ) from exc
    if not isinstance(raw, Mapping) or set(raw) != _COMPILED_RESULT_FIELDS:
        raise V31CycleAuthoringWorkflowError(
            "V31_AUTHORING_COMPILER_RESULT_SCHEMA_INVALID"
        )
    inputs_receipt = raw["inputs_receipt"]
    agent_proposal = raw["agent_proposal"]
    assembly_inputs = raw["assembly_inputs"]
    if (
        not isinstance(inputs_receipt, Mapping)
        or not isinstance(agent_proposal, Mapping)
        or not isinstance(assembly_inputs, Mapping)
        or _contains_selection(assembly_inputs)
    ):
        raise V31CycleAuthoringWorkflowError(
            "V31_AUTHORING_COMPILER_SELECTION_OR_SCHEMA_INVALID"
        )
    try:
        inputs_digest = verify_v31_inputs_receipt(inputs_receipt)
        proposal_digest = verify_v31_agent_proposal(
            agent_proposal, inputs_receipt=inputs_receipt
        )
        if (
            assembly_inputs.get("inputs_receipt") != dict(inputs_receipt)
            or assembly_inputs.get("agent_proposal") != dict(agent_proposal)
            or assembly_inputs.get("run_id") != authoring_packet["run_id"]
            or assembly_inputs.get("cycle_index")
            != authoring_packet["cycle_index"]
            or assembly_inputs.get("decision_at")
            != authoring_packet["decision_at"]
            or assembly_inputs.get("symbol") != authoring_packet["symbol"]
        ):
            raise V31CycleAuthoringWorkflowError(
                "V31_AUTHORING_COMPILER_IDENTITY_BINDING_MISMATCH"
            )
        # Narrative authorship must survive compilation exactly.  The typed
        # artifact digests may be generated by the compiler, but Application
        # cannot silently replace what the Agent said or knew was missing.
        for field in (
            "information_interpretations",
            "competing_explanations",
            "unknowns",
            "requested_observations",
            "hypothesis_novelty_rationales",
            "limitations",
        ):
            if agent_proposal.get(field) != authoring_envelope.get(field):
                raise V31CycleAuthoringWorkflowError(
                    "V31_AUTHORING_AGENT_NARRATIVE_BINDING_MISMATCH"
                )
        preselection = assemble_v31_cycle_evaluation(**dict(assembly_inputs))
        preselection_digest = verify_v31_cycle_evaluation(preselection)
        action_evaluation = assembly_inputs.get("action_evaluation")
        if not isinstance(action_evaluation, Mapping):
            raise V31CycleAuthoringWorkflowError(
                "V31_AUTHORING_ACTION_EVALUATION_MISSING"
            )
        action_evaluation_digest = verify_complete_action_evaluation(
            action_evaluation
        )
        if (
            preselection.get("selection_fields_admitted") is not False
            or preselection.get("executable") is not False
        ):
            raise V31CycleAuthoringWorkflowError(
                "V31_AUTHORING_PRESELECTION_BOUNDARY_INVALID"
            )
        compilation_receipt = seal_v31_authoring_compilation_receipt(
            authoring_packet=authoring_packet,
            authoring_envelope=authoring_envelope,
            inputs_receipt_digest=inputs_digest,
            agent_proposal_digest=proposal_digest,
            action_evaluation_digest=action_evaluation_digest,
            preselection_digest=preselection_digest,
            compiler_id=compiler_id,
            compiled_at=compiled_at,
        )
        validate_v31_authoring_compilation_receipt(
            compilation_receipt,
            authoring_packet=authoring_packet,
            authoring_envelope=authoring_envelope,
        )
    except V31CycleAuthoringWorkflowError:
        raise
    except (
        AgentResearchContractError,
        BehaviorPlanningError,
        V31CycleAuthoringError,
        V31ResearchCycleError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise V31CycleAuthoringWorkflowError(
            "V31_AUTHORING_DETERMINISTIC_REPLAY_FAILED_CLOSED"
        ) from exc
    return {
        "status": "COMPILED_PRESELECTION_NOT_SELECTED",
        "authoring_packet_digest": packet_digest,
        "agent_authoring_envelope_digest": envelope_digest,
        "inputs_receipt": dict(inputs_receipt),
        "agent_proposal": dict(agent_proposal),
        "action_evaluation": dict(action_evaluation),
        "preselection": preselection,
        "assembly_inputs": dict(assembly_inputs),
        "compilation_receipt": compilation_receipt,
        "selection_fields_admitted": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }


__all__ = [
    "V31CycleAuthoringCompilerPort",
    "V31CycleAuthoringWorkflowError",
    "compile_v31_agent_open_analysis",
]
