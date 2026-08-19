"""Public, auditable inference contracts for dynamic market research.

The Strategy Agent owns interpretation.  Deterministic code only verifies that
the published justification is point-in-time, source-linked, epistemically
typed, financially explicit, falsifiable, and connected to admitted research
state.  This artifact is deliberately not a private chain-of-thought record.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest
from .research_integrity import ACTION_CLASSES


class EpistemicInferenceError(ValueError):
    """A public inference contract failed closed."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

CLAIM_TYPES = frozenset(
    {
        "STATE_INFERENCE",
        "MECHANISM_INFERENCE",
        "SCENARIO_INFERENCE",
        "ACTION_IMPLICATION",
    }
)
EPISTEMIC_STATUSES = frozenset(
    {"SUPPORTED", "CONTESTED", "CONDITIONAL", "INSUFFICIENT"}
)
DIRECTIONAL_BIASES = frozenset(
    {"LONG", "SHORT", "BIDIRECTIONAL", "NEUTRAL", "UNKNOWN"}
)
HYPOTHESIS_EFFECTS = frozenset(
    {
        "CREATE_CANDIDATE",
        "SUPPORT",
        "OPPOSE",
        "REVISE",
        "PROMOTE",
        "DEMOTE",
        "INVALIDATE",
        "NO_CHANGE",
    }
)
EXPECTATION_EFFECTS = frozenset(
    {
        "CREATE",
        "REVISE",
        "PARTIAL",
        "FULFILL",
        "FALSIFY",
        "EXPIRE",
        "NO_CHANGE",
    }
)
ACTION_EFFECTS = frozenset(
    {"FAVORS", "OPPOSES", "CONDITIONAL", "NO_CONCLUSION"}
)

_CLAIM_FIELDS = frozenset(
    {
        "claim_id",
        "claim_type",
        "statement",
        "epistemic_status",
        "directional_bias",
        "timeframe_scope",
        "supporting_fact_ids",
        "contradicting_fact_ids",
        "unknown_fact_ids",
        "prior_claim_ids",
        "financial_mechanism",
        "hypothesis_effects",
        "expectation_effects",
        "action_implications",
        "falsification_conditions",
        "limitations",
        "next_discriminating_observations",
        "valid_until",
    }
)
_HYPOTHESIS_EFFECT_FIELDS = frozenset(
    {"hypothesis_id", "effect", "rationale"}
)
_EXPECTATION_EFFECT_FIELDS = frozenset(
    {"expectation_id", "effect", "rationale"}
)
_ACTION_IMPLICATION_FIELDS = frozenset(
    {"action_class", "effect", "rationale"}
)
_PRIVATE_REASONING_FIELDS = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "internal_monologue",
        "private_reasoning",
        "scratchpad",
    }
)
_UNCALIBRATED_QUANTIFICATION_FIELDS = frozenset(
    {
        "probability_pct",
        "path_probability_pct",
        "probabilities",
        "sum_to_100",
        "expected_value",
        "ev",
        "entropy",
        "confidence_margin",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicInferenceError(code)
    return value.strip()


def _strings(
    value: Any, code: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise EpistemicInferenceError(code)
    result = tuple(value)
    if (
        (not allow_empty and not result)
        or any(not isinstance(item, str) or not item.strip() for item in result)
        or len(result) != len(set(result))
    ):
        raise EpistemicInferenceError(code)
    return result


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EpistemicInferenceError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpistemicInferenceError(code) from exc
    if parsed.tzinfo is None:
        raise EpistemicInferenceError(code)
    return parsed.astimezone(UTC)


def _verified_digest(document: Mapping[str, Any], field: str, code: str) -> str:
    try:
        return verify_self_digest(document, field)
    except ValueError as exc:
        raise EpistemicInferenceError(code) from exc


def _contains_field(value: Any, forbidden: frozenset[str]) -> bool:
    if isinstance(value, Mapping):
        return bool(set(value) & forbidden) or any(
            _contains_field(item, forbidden) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_field(item, forbidden) for item in value)
    return False


def _normalize_hypothesis_effects(
    value: Any, *, known_hypothesis_ids: set[str]
) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        raise EpistemicInferenceError("INFERENCE_HYPOTHESIS_EFFECTS_INVALID")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _HYPOTHESIS_EFFECT_FIELDS:
            raise EpistemicInferenceError("INFERENCE_HYPOTHESIS_EFFECT_SCHEMA_INVALID")
        hypothesis_id = _text(
            raw.get("hypothesis_id"), "INFERENCE_HYPOTHESIS_EFFECT_ID_INVALID"
        )
        effect = str(raw.get("effect") or "")
        if (
            hypothesis_id not in known_hypothesis_ids
            or hypothesis_id in seen
            or effect not in HYPOTHESIS_EFFECTS
        ):
            raise EpistemicInferenceError("INFERENCE_HYPOTHESIS_EFFECT_INVALID")
        result.append(
            {
                "hypothesis_id": hypothesis_id,
                "effect": effect,
                "rationale": _text(
                    raw.get("rationale"),
                    "INFERENCE_HYPOTHESIS_EFFECT_RATIONALE_INVALID",
                ),
            }
        )
        seen.add(hypothesis_id)
    return result


def _normalize_expectation_effects(
    value: Any, *, known_expectation_ids: set[str]
) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        raise EpistemicInferenceError("INFERENCE_EXPECTATION_EFFECTS_INVALID")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _EXPECTATION_EFFECT_FIELDS:
            raise EpistemicInferenceError("INFERENCE_EXPECTATION_EFFECT_SCHEMA_INVALID")
        expectation_id = _text(
            raw.get("expectation_id"), "INFERENCE_EXPECTATION_EFFECT_ID_INVALID"
        )
        effect = str(raw.get("effect") or "")
        if (
            expectation_id not in known_expectation_ids
            or expectation_id in seen
            or effect not in EXPECTATION_EFFECTS
        ):
            raise EpistemicInferenceError("INFERENCE_EXPECTATION_EFFECT_INVALID")
        result.append(
            {
                "expectation_id": expectation_id,
                "effect": effect,
                "rationale": _text(
                    raw.get("rationale"),
                    "INFERENCE_EXPECTATION_EFFECT_RATIONALE_INVALID",
                ),
            }
        )
        seen.add(expectation_id)
    return result


def _normalize_action_implications(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        raise EpistemicInferenceError("INFERENCE_ACTION_IMPLICATIONS_INVALID")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _ACTION_IMPLICATION_FIELDS:
            raise EpistemicInferenceError("INFERENCE_ACTION_IMPLICATION_SCHEMA_INVALID")
        action_class = str(raw.get("action_class") or "")
        effect = str(raw.get("effect") or "")
        if (
            action_class not in ACTION_CLASSES
            or action_class in seen
            or effect not in ACTION_EFFECTS
        ):
            raise EpistemicInferenceError("INFERENCE_ACTION_IMPLICATION_INVALID")
        result.append(
            {
                "action_class": action_class,
                "effect": effect,
                "rationale": _text(
                    raw.get("rationale"),
                    "INFERENCE_ACTION_IMPLICATION_RATIONALE_INVALID",
                ),
            }
        )
        seen.add(action_class)
    return result


def build_public_inference_trace(
    *,
    market_snapshot: Mapping[str, Any],
    sentiment_state: Mapping[str, Any],
    hypothesis_registry: Mapping[str, Any],
    expectation_ledger: Mapping[str, Any],
    agent_context: Mapping[str, Any],
    agent_proposal: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
    decision_at: str,
) -> dict[str, Any]:
    """Validate an Agent-authored public justification without capturing private CoT."""

    cutoff = _timestamp(decision_at, "INFERENCE_DECISION_TIME_INVALID")
    snapshot_digest = _verified_digest(
        market_snapshot,
        "market_information_snapshot_digest",
        "INFERENCE_MARKET_SNAPSHOT_DIGEST_INVALID",
    )
    sentiment_digest = _verified_digest(
        sentiment_state,
        "sentiment_state_digest",
        "INFERENCE_SENTIMENT_DIGEST_INVALID",
    )
    registry_digest = _verified_digest(
        hypothesis_registry,
        "hypothesis_registry_digest",
        "INFERENCE_HYPOTHESIS_REGISTRY_DIGEST_INVALID",
    )
    ledger_digest = _verified_digest(
        expectation_ledger,
        "expectation_ledger_digest",
        "INFERENCE_EXPECTATION_LEDGER_DIGEST_INVALID",
    )
    context_digest = _verified_digest(
        agent_context,
        "agent_context_digest",
        "INFERENCE_AGENT_CONTEXT_DIGEST_INVALID",
    )
    proposal_digest = _verified_digest(
        agent_proposal,
        "agent_proposal_digest",
        "INFERENCE_AGENT_PROPOSAL_DIGEST_INVALID",
    )
    run_id = _text(market_snapshot.get("run_id"), "INFERENCE_IDENTITY_INVALID")
    cycle_index = market_snapshot.get("cycle_index")
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or cycle_index < 1:
        raise EpistemicInferenceError("INFERENCE_IDENTITY_INVALID")
    identity_documents = (
        sentiment_state,
        agent_context,
        agent_proposal,
    )
    if (
        market_snapshot.get("as_of") != decision_at
        or hypothesis_registry.get("decision_at") != decision_at
        or expectation_ledger.get("decision_at") != decision_at
        or sentiment_state.get("market_information_snapshot_digest")
        != snapshot_digest
        or agent_proposal.get("agent_context_digest") != context_digest
        or any(
            document.get("run_id") != run_id
            or document.get("cycle_index") != cycle_index
            for document in identity_documents
        )
    ):
        raise EpistemicInferenceError("INFERENCE_SOURCE_IDENTITY_MISMATCH")
    context_snapshot = agent_context.get("market_information_snapshot")
    if (
        not isinstance(context_snapshot, Mapping)
        or context_snapshot.get("market_information_snapshot_digest")
        != snapshot_digest
    ):
        raise EpistemicInferenceError("INFERENCE_AGENT_CONTEXT_SOURCE_UNBOUND")
    legal_action_contract = agent_context.get("legal_action_contract")
    capability_contract = agent_context.get("research_capability_contract")
    action_contract_classes = (
        legal_action_contract.get("action_classes")
        if isinstance(legal_action_contract, Mapping)
        else None
    )
    if (
        agent_context.get("context_payload_mode")
        != "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE"
        or not isinstance(agent_context.get("portfolio_truth"), Mapping)
        or not isinstance(agent_context.get("risk_policy"), Mapping)
        or not isinstance(legal_action_contract, Mapping)
        or not isinstance(action_contract_classes, (list, tuple))
        or any(not isinstance(item, str) for item in action_contract_classes)
        or set(action_contract_classes) != ACTION_CLASSES
        or not isinstance(capability_contract, Mapping)
        or capability_contract.get("semantic_family_whitelist") is not None
        or capability_contract.get("private_chain_of_thought_requested") is not False
        or capability_contract.get("public_structured_justification_required")
        is not True
        or capability_contract.get("uncalibrated_probability_forbidden") is not True
    ):
        raise EpistemicInferenceError("INFERENCE_AGENT_CAPABILITY_CONTEXT_INVALID")
    proposal_claims = agent_proposal.get("public_inference_claims")
    if _contains_field(agent_proposal, _PRIVATE_REASONING_FIELDS):
        raise EpistemicInferenceError("INFERENCE_PRIVATE_REASONING_FORBIDDEN")
    if _contains_field(agent_proposal, _UNCALIBRATED_QUANTIFICATION_FIELDS):
        raise EpistemicInferenceError(
            "INFERENCE_UNCALIBRATED_QUANTIFICATION_FORBIDDEN"
        )
    if not isinstance(proposal_claims, (list, tuple)) or list(proposal_claims) != list(
        claims
    ):
        raise EpistemicInferenceError("INFERENCE_CLAIMS_NOT_PROPOSAL_BOUND")

    facts: dict[str, Mapping[str, Any]] = {}
    for raw_fact in market_snapshot.get("facts", []):
        if not isinstance(raw_fact, Mapping):
            raise EpistemicInferenceError("INFERENCE_MARKET_FACT_INVALID")
        fact_id = _text(raw_fact.get("fact_id"), "INFERENCE_MARKET_FACT_INVALID")
        if fact_id in facts or _timestamp(
            raw_fact.get("available_at"), "INFERENCE_MARKET_FACT_TIME_INVALID"
        ) > cutoff:
            raise EpistemicInferenceError("INFERENCE_MARKET_FACT_INVALID")
        facts[fact_id] = raw_fact
    if not facts:
        raise EpistemicInferenceError("INFERENCE_MARKET_FACT_INVALID")

    known_hypothesis_ids = set(
        _strings(
            hypothesis_registry.get("known_hypothesis_ids"),
            "INFERENCE_HYPOTHESIS_SET_INVALID",
        )
    )
    known_expectation_ids = set(
        _strings(
            expectation_ledger.get("known_expectation_ids"),
            "INFERENCE_EXPECTATION_SET_INVALID",
            allow_empty=True,
        )
    )
    if not isinstance(claims, (list, tuple)) or not claims:
        raise EpistemicInferenceError("INFERENCE_CLAIMS_INVALID")

    normalized_claims: list[dict[str, Any]] = []
    seen_claim_ids: set[str] = set()
    cited_support: set[str] = set()
    cited_contradiction: set[str] = set()
    cited_unknown: set[str] = set()
    for raw in claims:
        if not isinstance(raw, Mapping) or set(raw) != _CLAIM_FIELDS:
            raise EpistemicInferenceError("INFERENCE_CLAIM_SCHEMA_INVALID")
        claim_id = _text(raw.get("claim_id"), "INFERENCE_CLAIM_ID_INVALID")
        if claim_id in seen_claim_ids:
            raise EpistemicInferenceError("INFERENCE_CLAIM_ID_INVALID")
        claim_type = str(raw.get("claim_type") or "")
        epistemic_status = str(raw.get("epistemic_status") or "")
        directional_bias = str(raw.get("directional_bias") or "")
        if (
            claim_type not in CLAIM_TYPES
            or epistemic_status not in EPISTEMIC_STATUSES
            or directional_bias not in DIRECTIONAL_BIASES
        ):
            raise EpistemicInferenceError("INFERENCE_CLAIM_ENUM_INVALID")
        support_ids = _strings(
            raw.get("supporting_fact_ids"), "INFERENCE_SUPPORT_REFS_INVALID"
        )
        contradiction_ids = _strings(
            raw.get("contradicting_fact_ids"),
            "INFERENCE_CONTRADICTION_REFS_INVALID",
            allow_empty=True,
        )
        unknown_ids = _strings(
            raw.get("unknown_fact_ids"),
            "INFERENCE_UNKNOWN_REFS_INVALID",
            allow_empty=True,
        )
        if (
            not (set(support_ids) | set(contradiction_ids) | set(unknown_ids)).issubset(
                facts
            )
            or set(support_ids) & set(contradiction_ids)
            or set(support_ids) & set(unknown_ids)
            or set(contradiction_ids) & set(unknown_ids)
            or any(facts[fact_id].get("value") is None for fact_id in support_ids)
            or any(
                facts[fact_id].get("value") is None for fact_id in contradiction_ids
            )
            or any(facts[fact_id].get("value") is not None for fact_id in unknown_ids)
        ):
            raise EpistemicInferenceError("INFERENCE_FACT_ROLE_INVALID")
        if epistemic_status == "CONTESTED" and not contradiction_ids:
            raise EpistemicInferenceError("INFERENCE_CONTESTED_WITHOUT_COUNTEREVIDENCE")
        if epistemic_status == "INSUFFICIENT" and not unknown_ids:
            raise EpistemicInferenceError("INFERENCE_INSUFFICIENT_WITHOUT_UNKNOWN")
        prior_claim_ids = _strings(
            raw.get("prior_claim_ids"),
            "INFERENCE_PRIOR_CLAIMS_INVALID",
            allow_empty=True,
        )
        if not set(prior_claim_ids).issubset(seen_claim_ids):
            raise EpistemicInferenceError("INFERENCE_PRIOR_CLAIMS_INVALID")
        valid_until = _timestamp(
            raw.get("valid_until"), "INFERENCE_VALID_UNTIL_INVALID"
        )
        if valid_until <= cutoff:
            raise EpistemicInferenceError("INFERENCE_VALID_UNTIL_INVALID")

        hypothesis_effects = _normalize_hypothesis_effects(
            raw.get("hypothesis_effects"),
            known_hypothesis_ids=known_hypothesis_ids,
        )
        expectation_effects = _normalize_expectation_effects(
            raw.get("expectation_effects"),
            known_expectation_ids=known_expectation_ids,
        )
        action_implications = _normalize_action_implications(
            raw.get("action_implications")
        )
        if not (hypothesis_effects or expectation_effects or action_implications):
            raise EpistemicInferenceError("INFERENCE_RESEARCH_EFFECT_MISSING")
        normalized_claims.append(
            {
                "claim_id": claim_id,
                "claim_type": claim_type,
                "statement": _text(
                    raw.get("statement"), "INFERENCE_CLAIM_STATEMENT_INVALID"
                ),
                "epistemic_status": epistemic_status,
                "directional_bias": directional_bias,
                "timeframe_scope": list(
                    _strings(
                        raw.get("timeframe_scope"),
                        "INFERENCE_TIMEFRAME_SCOPE_INVALID",
                    )
                ),
                "supporting_fact_ids": list(support_ids),
                "contradicting_fact_ids": list(contradiction_ids),
                "unknown_fact_ids": list(unknown_ids),
                "prior_claim_ids": list(prior_claim_ids),
                "financial_mechanism": _text(
                    raw.get("financial_mechanism"),
                    "INFERENCE_FINANCIAL_MECHANISM_INVALID",
                ),
                "hypothesis_effects": hypothesis_effects,
                "expectation_effects": expectation_effects,
                "action_implications": action_implications,
                "falsification_conditions": list(
                    _strings(
                        raw.get("falsification_conditions"),
                        "INFERENCE_FALSIFIERS_INVALID",
                    )
                ),
                "limitations": list(
                    _strings(raw.get("limitations"), "INFERENCE_LIMITATIONS_INVALID")
                ),
                "next_discriminating_observations": list(
                    _strings(
                        raw.get("next_discriminating_observations"),
                        "INFERENCE_NEXT_OBSERVATIONS_INVALID",
                    )
                ),
                "valid_until": raw["valid_until"],
            }
        )
        seen_claim_ids.add(claim_id)
        cited_support.update(support_ids)
        cited_contradiction.update(contradiction_ids)
        cited_unknown.update(unknown_ids)

    trace = {
        "schema_id": "public_epistemic_inference_trace",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "cycle_index": cycle_index,
        "decision_at": decision_at,
        "market_information_snapshot_digest": snapshot_digest,
        "sentiment_state_digest": sentiment_digest,
        "hypothesis_registry_digest": registry_digest,
        "expectation_ledger_digest": ledger_digest,
        "agent_context_digest": context_digest,
        "agent_proposal_digest": proposal_digest,
        "authoring_owner": "SINGLE_STRATEGY_AGENT",
        "validation_owner": "DETERMINISTIC_EPISTEMIC_CONTRACT",
        "claims": normalized_claims,
        "root_claim_ids": [
            claim["claim_id"]
            for claim in normalized_claims
            if not claim["prior_claim_ids"]
        ],
        "evidence_balance": {
            "distinct_supporting_fact_count": len(cited_support),
            "distinct_contradicting_fact_count": len(cited_contradiction),
            "distinct_unknown_fact_count": len(cited_unknown),
            "contradiction_absence_is_support": False,
            "unknown_is_neutral": False,
        },
        "epistemic_chain": [
            "OBSERVATION",
            "DERIVED_MEASURE",
            "INFERENCE",
            "HYPOTHESIS_OR_FORECAST",
            "POLICY_OR_ACTION_CONSIDERATION",
            "RISK_AND_PERMISSION_GATE",
        ],
        "semantic_research_space": "OPEN_CANDIDATE_REGISTRY_FINITE_OPERATIONAL_WINDOW",
        "private_chain_of_thought_recorded": False,
        "trace_scope": "PUBLIC_AUDITABLE_JUSTIFICATION_ONLY",
        "uncalibrated_probability_emitted": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(trace, "public_inference_trace_digest")
