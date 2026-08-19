"""V3.1 input and Strategy-Agent proposal receipts.

The Agent may propose interpretations, graph changes, hypotheses, paths and a
finite action candidate set.  It may not select an action, fabricate source
facts, or grant execution authority.  These pure contracts bind the proposal
to the exact point-in-time inputs and to the deterministic objects that were
admitted from it.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import self_digest, verify_self_digest


class AgentResearchContractError(ValueError):
    """An input or Agent proposal receipt violated the V3.1 boundary."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_PROPOSAL_KEYS = frozenset(
    {
        "selected",
        "selected_action",
        "selected_candidate_id",
        "action_selection",
        "action_selection_digest",
        "authorized_action",
        "execution_authority",
        "order",
        "order_payload",
    }
)
_INPUT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "information_event_digests",
        "information_revision_registry_digest",
        "association_estimation_receipt_digests",
        "pit_dataset_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "prior_graph_digest",
        "previous_accepted_state_digest",
        "previous_information_revision_registry_digest",
        "previous_pit_dataset_digest",
        "previous_datum_revision_registry_digest",
        "previous_sentiment_state_digest",
        "previous_hypothesis_registry_digest",
        "previous_expectation_ledger_digest",
        "previous_probability_cloud_digest",
        "authority_snapshot_sha256",
        "source_boundary",
        "external_execution_authority",
        "executable",
        "inputs_receipt_digest",
    }
)
_PROPOSAL_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "inputs_receipt_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "graph_delta_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "probability_cloud_digest",
        "scenario_path_set_digest",
        "candidate_bindings",
        "information_interpretations",
        "competing_explanations",
        "unknowns",
        "requested_observations",
        "hypothesis_novelty_rationales",
        "limitations",
        "proposal_phase",
        "selection_fields_admitted",
        "external_execution_authority",
        "executable",
        "agent_proposal_digest",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentResearchContractError(code)
    return value.strip()


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise AgentResearchContractError(code)
    return value


def _optional_digest(value: Any, code: str) -> str | None:
    return None if value is None else _digest(value, code)


def _time(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise AgentResearchContractError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgentResearchContractError(code) from exc
    if parsed.tzinfo is None:
        raise AgentResearchContractError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise AgentResearchContractError(f"{code}_NOT_CANONICAL")
    return canonical


def _strings(
    values: Sequence[str], code: str, *, allow_empty: bool = False
) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise AgentResearchContractError(code)
    result = list(values)
    if (
        (not allow_empty and not result)
        or any(not isinstance(value, str) or not value.strip() for value in result)
        or len(result) != len(set(result))
    ):
        raise AgentResearchContractError(code)
    return sorted(value.strip() for value in result)


def _identity(run_id: Any, cycle_index: Any, decision_at: Any, symbol: Any) -> tuple[str, int, str, str]:
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or cycle_index < 1:
        raise AgentResearchContractError("V31_AGENT_CYCLE_INDEX_INVALID")
    return (
        _text(run_id, "V31_AGENT_RUN_ID_INVALID"),
        cycle_index,
        _time(decision_at, "V31_AGENT_DECISION_AT_INVALID"),
        _text(symbol, "V31_AGENT_SYMBOL_INVALID"),
    )


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key.casefold() in _FORBIDDEN_PROPOSAL_KEYS:
                return True
            if _contains_forbidden_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def seal_v31_inputs_receipt(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    symbol: str,
    information_event_digests: Sequence[str],
    information_revision_registry_digest: str,
    association_estimation_receipt_digests: Sequence[str] = (),
    pit_dataset_digest: str,
    datum_revision_registry_digest: str,
    sentiment_state_digest: str,
    sentiment_change_digest: str,
    prior_graph_digest: str,
    previous_accepted_state_digest: str | None,
    previous_information_revision_registry_digest: str | None = None,
    previous_pit_dataset_digest: str | None = None,
    previous_datum_revision_registry_digest: str | None = None,
    previous_sentiment_state_digest: str | None = None,
    previous_hypothesis_registry_digest: str | None = None,
    previous_expectation_ledger_digest: str | None = None,
    previous_probability_cloud_digest: str | None = None,
    authority_snapshot_sha256: str,
) -> dict[str, Any]:
    """Seal the exact point-in-time boundary available before Agent proposal."""

    identity_run, identity_cycle, identity_time, identity_symbol = _identity(
        run_id, cycle_index, decision_at, symbol
    )
    events = _strings(
        information_event_digests, "V31_AGENT_INFORMATION_DIGESTS_INVALID"
    )
    if any(_HEX_64.fullmatch(value) is None for value in events):
        raise AgentResearchContractError("V31_AGENT_INFORMATION_DIGESTS_INVALID")
    association_receipts = _strings(
        association_estimation_receipt_digests,
        "V31_AGENT_ASSOCIATION_RECEIPTS_INVALID",
        allow_empty=True,
    )
    if any(_HEX_64.fullmatch(value) is None for value in association_receipts):
        raise AgentResearchContractError("V31_AGENT_ASSOCIATION_RECEIPTS_INVALID")
    previous_heads = (
        previous_accepted_state_digest,
        previous_information_revision_registry_digest,
        previous_pit_dataset_digest,
        previous_datum_revision_registry_digest,
        previous_sentiment_state_digest,
        previous_hypothesis_registry_digest,
        previous_expectation_ledger_digest,
        previous_probability_cloud_digest,
    )
    if identity_cycle == 1 and any(value is not None for value in previous_heads):
        raise AgentResearchContractError("V31_AGENT_GENESIS_PREVIOUS_HEAD_FORBIDDEN")
    if identity_cycle > 1 and any(value is None for value in previous_heads):
        raise AgentResearchContractError("V31_AGENT_PREVIOUS_HEADS_REQUIRED")
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_inputs_receipt",
            "schema_version": "1.0.0",
            "run_id": identity_run,
            "cycle_index": identity_cycle,
            "decision_at": identity_time,
            "symbol": identity_symbol,
            "information_event_digests": events,
            "information_revision_registry_digest": _digest(
                information_revision_registry_digest,
                "V31_AGENT_INFORMATION_REGISTRY_DIGEST_INVALID",
            ),
            "association_estimation_receipt_digests": association_receipts,
            "pit_dataset_digest": _digest(
                pit_dataset_digest, "V31_AGENT_DATASET_DIGEST_INVALID"
            ),
            "datum_revision_registry_digest": _digest(
                datum_revision_registry_digest,
                "V31_AGENT_DATUM_REGISTRY_DIGEST_INVALID",
            ),
            "sentiment_state_digest": _digest(
                sentiment_state_digest,
                "V31_AGENT_SENTIMENT_STATE_DIGEST_INVALID",
            ),
            "sentiment_change_digest": _digest(
                sentiment_change_digest,
                "V31_AGENT_SENTIMENT_CHANGE_DIGEST_INVALID",
            ),
            "prior_graph_digest": _digest(
                prior_graph_digest, "V31_AGENT_GRAPH_DIGEST_INVALID"
            ),
            "previous_accepted_state_digest": _optional_digest(
                previous_accepted_state_digest,
                "V31_AGENT_PREVIOUS_STATE_DIGEST_INVALID",
            ),
            "previous_information_revision_registry_digest": _optional_digest(
                previous_information_revision_registry_digest,
                "V31_AGENT_PREVIOUS_INFORMATION_REGISTRY_DIGEST_INVALID",
            ),
            "previous_pit_dataset_digest": _optional_digest(
                previous_pit_dataset_digest,
                "V31_AGENT_PREVIOUS_DATASET_DIGEST_INVALID",
            ),
            "previous_datum_revision_registry_digest": _optional_digest(
                previous_datum_revision_registry_digest,
                "V31_AGENT_PREVIOUS_DATUM_REGISTRY_DIGEST_INVALID",
            ),
            "previous_sentiment_state_digest": _optional_digest(
                previous_sentiment_state_digest,
                "V31_AGENT_PREVIOUS_SENTIMENT_DIGEST_INVALID",
            ),
            "previous_hypothesis_registry_digest": _optional_digest(
                previous_hypothesis_registry_digest,
                "V31_AGENT_PREVIOUS_HYPOTHESIS_DIGEST_INVALID",
            ),
            "previous_expectation_ledger_digest": _optional_digest(
                previous_expectation_ledger_digest,
                "V31_AGENT_PREVIOUS_EXPECTATION_DIGEST_INVALID",
            ),
            "previous_probability_cloud_digest": _optional_digest(
                previous_probability_cloud_digest,
                "V31_AGENT_PREVIOUS_CLOUD_DIGEST_INVALID",
            ),
            "authority_snapshot_sha256": _digest(
                authority_snapshot_sha256, "V31_AGENT_AUTHORITY_DIGEST_INVALID"
            ),
            "source_boundary": "PUBLIC_OR_LOCAL_NON_ACCOUNT_POINT_IN_TIME",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "inputs_receipt_digest",
    )


def verify_v31_inputs_receipt(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _INPUT_FIELDS:
        raise AgentResearchContractError("V31_AGENT_INPUTS_SCHEMA_INVALID")
    rebuilt = seal_v31_inputs_receipt(
        run_id=document["run_id"],
        cycle_index=document["cycle_index"],
        decision_at=document["decision_at"],
        symbol=document["symbol"],
        information_event_digests=document["information_event_digests"],
        information_revision_registry_digest=document[
            "information_revision_registry_digest"
        ],
        association_estimation_receipt_digests=document[
            "association_estimation_receipt_digests"
        ],
        pit_dataset_digest=document["pit_dataset_digest"],
        datum_revision_registry_digest=document[
            "datum_revision_registry_digest"
        ],
        sentiment_state_digest=document["sentiment_state_digest"],
        sentiment_change_digest=document["sentiment_change_digest"],
        prior_graph_digest=document["prior_graph_digest"],
        previous_accepted_state_digest=document["previous_accepted_state_digest"],
        previous_information_revision_registry_digest=document[
            "previous_information_revision_registry_digest"
        ],
        previous_pit_dataset_digest=document["previous_pit_dataset_digest"],
        previous_datum_revision_registry_digest=document[
            "previous_datum_revision_registry_digest"
        ],
        previous_sentiment_state_digest=document[
            "previous_sentiment_state_digest"
        ],
        previous_hypothesis_registry_digest=document[
            "previous_hypothesis_registry_digest"
        ],
        previous_expectation_ledger_digest=document[
            "previous_expectation_ledger_digest"
        ],
        previous_probability_cloud_digest=document[
            "previous_probability_cloud_digest"
        ],
        authority_snapshot_sha256=document["authority_snapshot_sha256"],
    )
    try:
        supplied = verify_self_digest(document, "inputs_receipt_digest")
    except ValueError as exc:
        raise AgentResearchContractError("V31_AGENT_INPUTS_DIGEST_INVALID") from exc
    if rebuilt != dict(document) or supplied != rebuilt["inputs_receipt_digest"]:
        raise AgentResearchContractError("V31_AGENT_INPUTS_CANONICAL_FORM_INVALID")
    return supplied


def seal_v31_agent_proposal(
    *,
    inputs_receipt: Mapping[str, Any],
    sentiment_state_digest: str,
    sentiment_change_digest: str,
    graph_delta_digest: str,
    hypothesis_registry_digest: str,
    expectation_ledger_digest: str,
    probability_cloud_digest: str,
    scenario_path_set_digest: str,
    candidate_bindings: Mapping[str, str],
    information_interpretations: Sequence[str],
    competing_explanations: Sequence[str],
    unknowns: Sequence[str],
    requested_observations: Sequence[str],
    hypothesis_novelty_rationales: Mapping[str, str],
    limitations: Sequence[str],
) -> dict[str, Any]:
    """Seal an admitted proposal with no selection or execution semantics."""

    inputs_digest = verify_v31_inputs_receipt(inputs_receipt)
    bound_sentiment_state_digest = _digest(
        sentiment_state_digest,
        "V31_AGENT_SENTIMENT_STATE_DIGEST_INVALID",
    )
    bound_sentiment_change_digest = _digest(
        sentiment_change_digest,
        "V31_AGENT_SENTIMENT_CHANGE_DIGEST_INVALID",
    )
    if (
        bound_sentiment_state_digest
        != inputs_receipt["sentiment_state_digest"]
        or bound_sentiment_change_digest
        != inputs_receipt["sentiment_change_digest"]
    ):
        raise AgentResearchContractError("V31_AGENT_SENTIMENT_INPUT_MISMATCH")
    if (
        not isinstance(candidate_bindings, Mapping)
        or not candidate_bindings
        or any(
            not isinstance(candidate_id, str)
            or not candidate_id.strip()
            or not isinstance(digest, str)
            or _HEX_64.fullmatch(digest) is None
            for candidate_id, digest in candidate_bindings.items()
        )
    ):
        raise AgentResearchContractError("V31_AGENT_CANDIDATE_BINDINGS_INVALID")
    novelty = dict(hypothesis_novelty_rationales)
    if (
        not novelty
        or any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
            for key, value in novelty.items()
        )
    ):
        raise AgentResearchContractError("V31_AGENT_NOVELTY_RATIONALES_INVALID")
    narrative = {
        "information_interpretations": _strings(
            information_interpretations,
            "V31_AGENT_INTERPRETATIONS_INVALID",
        ),
        "competing_explanations": _strings(
            competing_explanations,
            "V31_AGENT_COMPETING_EXPLANATIONS_INVALID",
        ),
        "unknowns": _strings(unknowns, "V31_AGENT_UNKNOWNS_INVALID"),
        "requested_observations": _strings(
            requested_observations,
            "V31_AGENT_REQUESTED_OBSERVATIONS_INVALID",
        ),
        "limitations": _strings(limitations, "V31_AGENT_LIMITATIONS_INVALID"),
    }
    candidate_document = dict(sorted(candidate_bindings.items()))
    novelty_document = dict(sorted((key.strip(), value.strip()) for key, value in novelty.items()))
    if _contains_forbidden_key(
        {**narrative, "candidate_bindings": candidate_document, "novelty": novelty_document}
    ):
        raise AgentResearchContractError("V31_AGENT_SELECTION_FIELD_FORBIDDEN")
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_agent_proposal",
            "schema_version": "1.0.0",
            "run_id": inputs_receipt["run_id"],
            "cycle_index": inputs_receipt["cycle_index"],
            "decision_at": inputs_receipt["decision_at"],
            "symbol": inputs_receipt["symbol"],
            "inputs_receipt_digest": inputs_digest,
            "sentiment_state_digest": bound_sentiment_state_digest,
            "sentiment_change_digest": bound_sentiment_change_digest,
            "graph_delta_digest": _digest(
                graph_delta_digest, "V31_AGENT_GRAPH_DELTA_DIGEST_INVALID"
            ),
            "hypothesis_registry_digest": _digest(
                hypothesis_registry_digest,
                "V31_AGENT_HYPOTHESIS_REGISTRY_DIGEST_INVALID",
            ),
            "expectation_ledger_digest": _digest(
                expectation_ledger_digest,
                "V31_AGENT_EXPECTATION_LEDGER_DIGEST_INVALID",
            ),
            "probability_cloud_digest": _digest(
                probability_cloud_digest, "V31_AGENT_CLOUD_DIGEST_INVALID"
            ),
            "scenario_path_set_digest": _digest(
                scenario_path_set_digest, "V31_AGENT_PATH_SET_DIGEST_INVALID"
            ),
            "candidate_bindings": candidate_document,
            **narrative,
            "hypothesis_novelty_rationales": novelty_document,
            "proposal_phase": "PROPOSAL_ONLY_NO_SELECTION",
            "selection_fields_admitted": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "agent_proposal_digest",
    )


def verify_v31_agent_proposal(
    document: Mapping[str, Any], *, inputs_receipt: Mapping[str, Any]
) -> str:
    if not isinstance(document, Mapping) or set(document) != _PROPOSAL_FIELDS:
        raise AgentResearchContractError("V31_AGENT_PROPOSAL_SCHEMA_INVALID")
    if _contains_forbidden_key(
        {
            key: value
            for key, value in document.items()
            if key not in {"schema_id", "agent_proposal_digest"}
        }
    ):
        raise AgentResearchContractError("V31_AGENT_SELECTION_FIELD_FORBIDDEN")
    rebuilt = seal_v31_agent_proposal(
        inputs_receipt=inputs_receipt,
        sentiment_state_digest=document["sentiment_state_digest"],
        sentiment_change_digest=document["sentiment_change_digest"],
        graph_delta_digest=document["graph_delta_digest"],
        hypothesis_registry_digest=document["hypothesis_registry_digest"],
        expectation_ledger_digest=document["expectation_ledger_digest"],
        probability_cloud_digest=document["probability_cloud_digest"],
        scenario_path_set_digest=document["scenario_path_set_digest"],
        candidate_bindings=document["candidate_bindings"],
        information_interpretations=document["information_interpretations"],
        competing_explanations=document["competing_explanations"],
        unknowns=document["unknowns"],
        requested_observations=document["requested_observations"],
        hypothesis_novelty_rationales=document["hypothesis_novelty_rationales"],
        limitations=document["limitations"],
    )
    try:
        supplied = verify_self_digest(document, "agent_proposal_digest")
    except ValueError as exc:
        raise AgentResearchContractError("V31_AGENT_PROPOSAL_DIGEST_INVALID") from exc
    if rebuilt != dict(document) or supplied != rebuilt["agent_proposal_digest"]:
        raise AgentResearchContractError("V31_AGENT_PROPOSAL_CANONICAL_FORM_INVALID")
    return supplied


__all__ = [
    "AgentResearchContractError",
    "seal_v31_agent_proposal",
    "seal_v31_inputs_receipt",
    "verify_v31_agent_proposal",
    "verify_v31_inputs_receipt",
]
