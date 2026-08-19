"""Application workflow and native-role packets for action E0A."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..domain.action_discrimination.evaluation import (
    evaluate_case_actions,
    terminal_result,
)
from ..domain.action_discrimination.model import (
    E0B_FINANCIAL_CONTRACT,
    EXECUTION_AUTHORITY,
    OUTPUT_SPECS,
    SEMANTIC_OUTPUT_SCHEMA,
    SYSTEM_MODE,
    ActionDiscriminationError,
)
from ..domain.contracts.canonical import (
    canonical_digest,
    load_json_strict,
    loads_json_strict,
    write_once_json,
)
from ..infrastructure.action_discrimination_store import (
    EXPECTED_ROLE_KEYS,
    FrozenOutcomeDatasetAdapter,
    load_frozen_action_context,
    verify_action_experiment,
)


SINGLE_BUNDLE_KEYS = (
    "single-proposal",
    "single-self-review",
    "single-selection",
)


_COMMON_ROLE_RULES_E0A = (
    "Use only the supplied frozen point-in-time context. Do not use tools, "
    "files, network, memory, later prices or outside facts. The objects are "
    "offline research candidates, never orders. Do not invent numeric "
    "probabilities, expected value or Kelly sizing. Preserve typed UNKNOWN. "
    "Assess every action in selector_choice_set exactly once. Evidence refs "
    "must come from allowed_evidence_ids. Treat action_transition_contract, "
    "terminal_policy, accounting_scope, review deadlines and typed UNKNOWN as "
    "binding; never infer an unmodeled same-bar trail fill or future reentry. "
    "Return JSON only, with no markdown."
)


_COMMON_ROLE_RULES_E0B = (
    "Use only the supplied frozen point-in-time context. Do not use tools, "
    "files, network, memory, later prices or outside facts. The objects are "
    "offline research candidates, never orders. Do not invent numeric "
    "probabilities, expected value or Kelly sizing. Preserve typed UNKNOWN. "
    "Assess every action in selector_choice_set exactly once. Evidence refs "
    "must come from allowed_evidence_ids. Treat action_transition_contract, "
    "terminal_policy, accounting_scope, review deadlines and typed UNKNOWN as "
    "binding. PRIMARY, ALTERNATIVE and NULL must use three distinct known "
    "path_ids; hard_falsifier_refs may only use state.hard_invalidator_refs. "
    "Use ordinal order PREFERRED, VIABLE, UNKNOWN, AVOID. A Selector must rank "
    "actions in that order and select a PREFERRED action. Never infer an "
    "unmodeled same-bar trail fill or future reentry. "
    "Return JSON only, with no markdown."
)


_ROLE_RULES = {
    "cluster-proposal": (
        "Act as Proposer. Build four ordered path slots, compare every admitted "
        "action, and expose assumptions. You have no selection authority: "
        "selected_action=null and ranked_action_ids=[]."
    ),
    "cluster-challenge": (
        "Act as blind Challenger. You have not seen the Proposer. Seek material "
        "state, time-scale, risk, opportunity-cost, supervision and reentry "
        "defects. You have no selection authority: selected_action=null and "
        "ranked_action_ids=[]."
    ),
    "cluster-selection": (
        "Act as bounded Selector. Reconcile the attached proposal and blind "
        "challenge. Rank every selector_choice_set action exactly once; the "
        "first ranked action must equal selected_action. Never alter the hard "
        "feasible set or state."
    ),
}


def load_context(run_root: Path, sample_index: int) -> dict[str, Any]:
    return load_frozen_action_context(Path(run_root), sample_index)


def role_packet(
    *,
    run_root: Path,
    sample_index: int,
    role: str,
    proposal: Mapping[str, Any] | None = None,
    challenge: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an allowlisted native-subagent packet without outcome access."""

    context = load_context(run_root, sample_index)
    return build_role_packet_from_context(
        context=context,
        role=role,
        proposal=proposal,
        challenge=challenge,
    )


def build_role_packet_from_context(
    *,
    context: Mapping[str, Any],
    role: str,
    proposal: Mapping[str, Any] | None = None,
    challenge: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a role packet from one already manifest-bound context."""

    sample_index = context.get("sample_index")
    if type(sample_index) is not int:
        raise ActionDiscriminationError("ROLE_PACKET_SAMPLE_INVALID")
    if role == "single-strong-bundle":
        task = (
            "Act as one Single-Strong identity. First produce single-proposal, "
            "then critique it in single-self-review, then produce "
            "single-selection. Return one object whose exact keys are "
            "single-proposal, single-self-review and single-selection. The "
            "proposal and self-review have selected_action=null and empty "
            "ranking. The selection ranks the complete choice set. Each nested "
            "object independently follows semantic_output_schema."
        )
        upstream: dict[str, Any] = {}
    elif role in _ROLE_RULES:
        task = _ROLE_RULES[role]
        upstream = {}
        if role == "cluster-selection":
            if proposal is None or challenge is None:
                raise ActionDiscriminationError(
                    "SELECTOR_UPSTREAM_OUTPUTS_REQUIRED"
                )
            upstream = {
                "blind_proposal": dict(proposal),
                "blind_challenge": dict(challenge),
            }
        elif proposal is not None or challenge is not None:
            raise ActionDiscriminationError("BLIND_ROLE_UPSTREAM_FORBIDDEN")
    else:
        raise ActionDiscriminationError("ROLE_PACKET_ROLE_UNKNOWN")
    packet = {
        "schema_id": "native_action_role_packet",
        "schema_version": "1.0.0",
        "sample_index": sample_index,
        "role": role,
        "common_rules": (
            _COMMON_ROLE_RULES_E0B
            if context.get("financial_contract_version")
            == E0B_FINANCIAL_CONTRACT
            else _COMMON_ROLE_RULES_E0A
        ),
        "role_task": task,
        "context": context,
        "upstream_outputs": upstream,
        "semantic_output_schema": SEMANTIC_OUTPUT_SCHEMA,
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    packet["packet_digest"] = canonical_digest(packet)
    return packet


def parse_single_bundle(raw: str | bytes) -> dict[str, dict[str, Any]]:
    value = loads_json_strict(raw)
    if frozenset(value) != frozenset(SINGLE_BUNDLE_KEYS):
        raise ActionDiscriminationError("SINGLE_BUNDLE_KEYS_INVALID")
    if any(not isinstance(value[key], dict) for key in SINGLE_BUNDLE_KEYS):
        raise ActionDiscriminationError("SINGLE_BUNDLE_OUTPUT_INVALID")
    return {key: value[key] for key in SINGLE_BUNDLE_KEYS}


def parse_role_output(raw: str | bytes, *, role_key: str) -> dict[str, Any]:
    if role_key not in OUTPUT_SPECS:
        raise ActionDiscriminationError("ROLE_KEY_UNKNOWN")
    return loads_json_strict(raw)


def evaluate_completed_action_experiment(
    *,
    run_root: Path,
    source_run_root: Path,
) -> dict[str, Any]:
    """Open future bars only after all 192 role outputs are verified frozen."""

    run_root = Path(run_root).resolve()
    status = verify_action_experiment(run_root)
    manifest = load_json_strict(run_root / "frozen" / "manifest.json")
    bounds = manifest.get("decision_indices_inclusive")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or any(type(item) is not int for item in bounds)
        or bounds[1] - bounds[0] != 31
    ):
        raise ActionDiscriminationError("FROZEN_SAMPLE_WINDOW_INVALID")
    sample_indices = tuple(range(bounds[0], bounds[1] + 1))
    if status["completed_count"] != len(sample_indices) or not status["terminal"]:
        raise ActionDiscriminationError("OUTCOME_EVALUATION_BEFORE_OUTPUT_FREEZE")
    adapter = FrozenOutcomeDatasetAdapter(source_run_root, run_root)
    events: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for sample_index in sample_indices:
        event = load_json_strict(
            run_root / "events" / f"sample-{sample_index:03d}.json"
        )
        context = load_context(run_root, sample_index)
        outcome = adapter.outcome_bars(sample_index)
        diagnostic = evaluate_case_actions(
            context=context,
            single_action_id=event["selected_actions"]["single"],
            cluster_action_id=event["selected_actions"]["cluster"],
            outcome_bars=outcome,
        )
        write_once_json(
            run_root
            / "evaluation"
            / "cases"
            / f"sample-{sample_index:03d}.json",
            diagnostic,
        )
        events.append(event)
        diagnostics.append(diagnostic)
    result = terminal_result(
        run_id=manifest["run_id"],
        manifest_digest=manifest["manifest_digest"],
        event_head_digest=status["event_head_digest"],
        events=events,
        diagnostics=diagnostics,
    )
    write_once_json(run_root / "evaluation" / "result.json", result)
    return result


__all__ = [
    "SINGLE_BUNDLE_KEYS",
    "build_role_packet_from_context",
    "evaluate_completed_action_experiment",
    "load_context",
    "parse_role_output",
    "parse_single_bundle",
    "role_packet",
]
