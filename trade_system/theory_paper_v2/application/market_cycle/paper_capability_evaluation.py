"""Pure builders for V3.3.2 pre-outcome paper capability assessment."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any, Mapping, Sequence

from ...domain.contracts.canonical import (
    canonical_bytes,
    canonical_decimal,
    canonical_digest,
    loads_json_strict,
)
from ...domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
    AttentionContractError,
    GoalAttentionCheckpointV1,
)
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
)
from ...domain.market_cycle.experiment import ExperimentPolicyV1
from ...domain.market_cycle.paper import (
    PAPER_BRACKET_ELIGIBLE_ACTIONS,
    PAPER_NON_EXECUTABLE_ACTIONS,
    FillEventV1,
    OrderTruthV1,
    PaperExecutionIntentV1,
    PaperLedgerRecordV1,
)
from ...domain.market_cycle.paper_capability_evaluation import (
    ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS,
    PAPER_ASSESSMENT_VECTOR_KEYS,
    PAPER_BLINDNESS_BASIS,
    PAPER_CAPABILITY_CRITERIA,
    PAPER_CAPABILITY_RUBRICS,
    PAPER_EVIDENCE_SOURCE_KINDS,
    BoundAttentionSchedulingPointV1,
    BoundPaperDecisionPointV1,
    PaperCapabilityEvaluationError,
    PaperCapabilityFindingV1,
    PaperEvidenceSpanV1,
    PositionMechanicalEvidenceV1,
    PreOutcomePaperCapabilityAssessmentV1,
    PreOutcomePaperCapabilityTaskV1,
    paper_capability_vector_for,
)


@dataclass(frozen=True, slots=True)
class PaperDecisionEvidenceInputV1:
    """Exact runtime-owned inputs for one Agent-authored paper decision point."""

    snapshot: InputSnapshot
    snapshot_ref: ArtifactRef
    request_document: Mapping[str, Any]
    paper_context: Mapping[str, Any]
    hypothesis: HypothesisRecord
    execution_intent_request_document: Mapping[str, Any]
    execution_intent: PaperExecutionIntentV1
    pre_ledger_head: PaperLedgerRecordV1
    post_ledger_head: PaperLedgerRecordV1
    current_agent: AgentRegistry
    cycle_stage: str = "BEHAVIOR_PLANNED"


@dataclass(frozen=True, slots=True)
class AttentionSchedulingEvidenceInputV1:
    """Exact facts for one self-managed checkpoint and its real next decision."""

    snapshot: InputSnapshot
    snapshot_ref: ArtifactRef
    request_document: Mapping[str, Any]
    paper_context: Mapping[str, Any]
    hypothesis: HypothesisRecord
    behavior_plan: BehaviorPlan
    pre_ledger_head: PaperLedgerRecordV1
    attention_request: AttentionRequest
    attention_checkpoint_event_document: Mapping[str, Any]
    attention_stream_head_document: Mapping[str, Any]
    current_agent: AgentRegistry


PaperCapabilityEvidenceInputV1 = (
    PaperDecisionEvidenceInputV1 | AttentionSchedulingEvidenceInputV1
)


_ATTENTION_CHECKPOINT_EVENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "logical_agent_id",
        "revision",
        "prior_event_sha256",
        "event_id",
        "event_type",
        "occurred_at",
        "payload",
        "event_sha256",
    }
)
_ATTENTION_STREAM_HEAD_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "logical_agent_id",
        "revision",
        "event_sha256",
    }
)


def build_paper_position_and_open_order_ref(
    *,
    account_id: str,
    ledger_revision: int,
    ledger_head_sha256: str,
) -> str:
    """Build the exact frozen paper state reference an Agent checkpoint binds."""

    if type(account_id) is not str or not account_id:
        raise PaperCapabilityEvaluationError(
            "paper position/open-order account identity is invalid"
        )
    if type(ledger_revision) is not int or ledger_revision < 1:
        raise PaperCapabilityEvaluationError(
            "paper position/open-order ledger revision is invalid"
        )
    if (
        type(ledger_head_sha256) is not str
        or len(ledger_head_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in ledger_head_sha256
        )
    ):
        raise PaperCapabilityEvaluationError(
            "paper position/open-order ledger head is invalid"
        )
    return (
        f"paper/{account_id}@version={ledger_revision}"
        f"#sha256={ledger_head_sha256}"
    )


def _time(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        raise PaperCapabilityEvaluationError(
            f"{field} must be an offset ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperCapabilityEvaluationError(
            f"{field} must be an offset ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperCapabilityEvaluationError(
            f"{field} must be an offset ISO-8601 timestamp"
        )
    return parsed


def _verify_snapshot_ref(snapshot: InputSnapshot, reference: ArtifactRef) -> None:
    if not isinstance(snapshot, InputSnapshot) or not isinstance(reference, ArtifactRef):
        raise PaperCapabilityEvaluationError(
            "snapshot and snapshot_ref must be sealed market-cycle contracts"
        )
    raw = canonical_bytes(snapshot.to_dict())
    if (
        reference.artifact_type != "InputSnapshot"
        or reference.artifact_id != snapshot.snapshot_id
        or reference.size_bytes != len(raw)
        or reference.sha256 != hashlib.sha256(raw).hexdigest()
    ):
        raise PaperCapabilityEvaluationError(
            "snapshot_ref does not bind the supplied InputSnapshot"
        )


def _verify_policy(
    policy: ExperimentPolicyV1, *, capability_id: str, snapshot: InputSnapshot
) -> Mapping[str, Any]:
    if not isinstance(policy, ExperimentPolicyV1):
        raise PaperCapabilityEvaluationError("policy must be ExperimentPolicyV1")
    if (
        policy.phase != "CAPABILITY_PILOT"
        or policy.capability_ids != (capability_id,)
        or capability_id not in PAPER_CAPABILITY_CRITERIA
    ):
        raise PaperCapabilityEvaluationError(
            "paper capability pilot requires one matching singleton policy"
        )
    if not policy.local_paper_authorized or policy.paper_account is None:
        raise PaperCapabilityEvaluationError(
            "paper capability pilot requires an isolated local paper account"
        )
    if (
        policy.venue_id != snapshot.venue_id
        or policy.instrument_id != snapshot.instrument_id
        or policy.market_contract_identity != snapshot.contract_identity
        or policy.data_profile != snapshot.data_profile
        or policy.decision_horizon_seconds != snapshot.outcome_horizon_seconds
        or policy.outcome_tolerance_seconds != snapshot.outcome_tolerance_seconds
    ):
        raise PaperCapabilityEvaluationError(
            "policy and InputSnapshot identity or horizon differ"
        )
    return policy.paper_account


def _verify_request_and_context(
    evidence: PaperCapabilityEvidenceInputV1,
    *,
    policy: ExperimentPolicyV1,
    paper_policy: Mapping[str, Any],
) -> tuple[str, str, tuple[str, ...]]:
    request = evidence.request_document
    context = evidence.paper_context
    if not isinstance(request, Mapping) or not isinstance(context, Mapping):
        raise PaperCapabilityEvaluationError(
            "request_document and paper_context must be objects"
        )
    packet = request.get("packet")
    packet_sha256 = request.get("packet_sha256")
    if (
        not isinstance(packet, Mapping)
        or packet.get("cycle_id") != evidence.snapshot.cycle_id
        or packet.get("paper_context") != context
        or packet_sha256 != canonical_digest(packet)
    ):
        raise PaperCapabilityEvaluationError(
            "Agent request does not bind the exact paper context"
        )
    context_sha256 = context.get("paper_context_sha256")
    candidate = dict(context)
    candidate.pop("paper_context_sha256", None)
    if (
        context.get("schema_id")
        != "agent-trade-emotion.v332-paper-decision-context"
        or context.get("schema_version") != "1.5.0"
        or context.get("status") != "OBSERVED"
        or context.get("cycle_id") != evidence.snapshot.cycle_id
        or context.get("snapshot_ref") != evidence.snapshot_ref.to_dict()
        or context.get("experiment_policy_sha256") != policy.policy_sha256
        or context_sha256 != canonical_digest(candidate)
    ):
        raise PaperCapabilityEvaluationError("paper context binding is invalid")
    action_space = context.get("paper_action_space")
    if (
        not isinstance(action_space, Mapping)
        or action_space.get("schema_id")
        != "agent-trade-emotion.paper-action-space"
        or action_space.get("schema_version") != "1.0.0"
    ):
        raise PaperCapabilityEvaluationError(
            "paper context lacks the published paper action space"
        )
    account = context.get("account")
    head = context.get("ledger_head")
    if not isinstance(account, Mapping) or not isinstance(head, Mapping):
        raise PaperCapabilityEvaluationError("paper context lacks account or ledger head")
    pre = evidence.pre_ledger_head
    if (
        head.get("revision") != pre.revision
        or head.get("record_sha256") != pre.record_sha256
        or account.get("account_id") != paper_policy["account_id"]
        or account.get("version") != pre.revision
        or account.get("owner_logical_agent_id") != paper_policy["logical_agent_id"]
        or account.get("owner_agent_generation") != paper_policy["agent_generation"]
        or account.get("permitted_symbol") != policy.instrument_id
        or account.get("account_mode") != paper_policy["account_mode"]
        or account.get("base_currency") != paper_policy["base_currency"]
    ):
        raise PaperCapabilityEvaluationError(
            "paper context account or pre-ledger binding is invalid"
        )
    context_policy = context.get("paper_account_policy")
    if not isinstance(context_policy, Mapping) or any(
        context_policy.get(field) != paper_policy[field]
        for field in (
            "account_id",
            "logical_agent_id",
            "agent_generation",
            "account_mode",
            "base_currency",
            "max_position_notional",
            "max_decision_loss",
            "max_observed_drawdown",
        )
    ):
        raise PaperCapabilityEvaluationError(
            "paper context does not bind the experiment account policy"
        )
    prior_values = context.get("prior_execution_intents")
    if not isinstance(prior_values, list):
        raise PaperCapabilityEvaluationError(
            "paper context prior_execution_intents must be an array"
        )
    try:
        prior_intents = tuple(
            PaperExecutionIntentV1.from_dict(item) for item in prior_values
        )
    except (TypeError, ValueError) as exc:
        raise PaperCapabilityEvaluationError(
            "paper context contains an invalid prior intent"
        ) from exc
    if any(
        item.account_id != paper_policy["account_id"]
        or item.logical_agent_id != paper_policy["logical_agent_id"]
        or item.agent_generation != paper_policy["agent_generation"]
        or item.symbol != policy.instrument_id
        for item in prior_intents
    ):
        raise PaperCapabilityEvaluationError(
            "paper context prior intent identity is inconsistent"
        )
    latest = context.get("latest_transition")
    if latest != (None if not prior_intents else prior_intents[-1].to_dict()):
        raise PaperCapabilityEvaluationError(
            "paper context latest transition does not bind its prior-intent tail"
        )
    _context_continuity_binding(context, prior_intents=prior_intents)
    return (
        str(packet_sha256),
        canonical_digest(request),
        tuple(item.intent_sha256 for item in prior_intents),
    )


def _expected_terminal_non_execution_suffix(
    prior_intents: Sequence[PaperExecutionIntentV1],
) -> Mapping[str, Any]:
    suffix: list[PaperExecutionIntentV1] = []
    if prior_intents:
        episode_id = prior_intents[-1].episode_id
        for intent in reversed(prior_intents):
            if intent.episode_id != episode_id or intent.action not in {
                "WAIT",
                "HOLD",
                "WATCH",
            }:
                break
            suffix.append(intent)
        suffix.reverse()
    return {
        "status": "EXACT" if prior_intents else "NO_PRIOR_INTENT",
        "episode_id": None if not suffix else suffix[-1].episode_id,
        "length": len(suffix),
        "wait_count": sum(item.action == "WAIT" for item in suffix),
        "hold_count": sum(item.action == "HOLD" for item in suffix),
        "watch_count": sum(item.action == "WATCH" for item in suffix),
        "actions": [item.action for item in suffix],
        "intent_sha256s": [item.intent_sha256 for item in suffix],
        "first_transition_id": None if not suffix else suffix[0].transition_id,
        "last_transition_id": None if not suffix else suffix[-1].transition_id,
    }


def _expected_episode_transition_tail(
    prior_intents: Sequence[PaperExecutionIntentV1],
) -> list[Mapping[str, Any]]:
    if not prior_intents:
        return []
    episode_id = prior_intents[-1].episode_id
    tail: list[PaperExecutionIntentV1] = []
    for intent in reversed(prior_intents):
        if intent.episode_id != episode_id:
            break
        tail.append(intent)
    tail.reverse()
    return [
        {
            "intent_sha256": item.intent_sha256,
            "decision_cycle_id": item.decision_cycle_id,
            "decision_sha256": item.decision_sha256,
            "episode_id": item.episode_id,
            "transition_id": item.transition_id,
            "action": item.action,
            "role": item.role,
            "target_state": loads_json_strict(canonical_bytes(item.target_state)),
        }
        for item in tail
    ]


def _expected_mechanical_state(context: Mapping[str, Any]) -> Mapping[str, Any]:
    account = context.get("account")
    orders_and_fills = context.get("orders_and_fills")
    if not isinstance(account, Mapping) or not isinstance(orders_and_fills, Mapping):
        raise PaperCapabilityEvaluationError(
            "paper context continuity lacks mechanical account facts"
        )
    positions = account.get("positions")
    orders = account.get("orders")
    if not isinstance(positions, list) or not isinstance(orders, list):
        raise PaperCapabilityEvaluationError(
            "paper context account lacks mechanical positions or orders"
        )
    symbol = account.get("permitted_symbol")
    matching = tuple(
        item
        for item in positions
        if isinstance(item, Mapping) and item.get("symbol") == symbol
    )
    signed_quantity = (
        "0"
        if not matching
        else matching[0].get("quantity")
        if len(matching) == 1
        else None
    )
    state_counts: dict[str, int] = {}
    for order in orders:
        if not isinstance(order, Mapping) or not isinstance(order.get("state"), str):
            raise PaperCapabilityEvaluationError(
                "paper context account contains an invalid order fact"
            )
        state = str(order["state"])
        state_counts[state] = state_counts.get(state, 0) + 1
    arrays = {}
    for field in ("open_orders", "order_history", "fills", "unresolved"):
        value = orders_and_fills.get(field)
        if not isinstance(value, list):
            raise PaperCapabilityEvaluationError(
                "paper context orders-and-fills projection is incomplete"
            )
        arrays[field] = value
    return {
        "status": (
            "EXACT_MECHANICAL_FACTS"
            if signed_quantity is not None
            else "AMBIGUOUS_MULTIPLE_POSITIONS"
        ),
        "source_refs": {
            "account_sha256": canonical_digest(account),
            "orders_and_fills_sha256": canonical_digest(orders_and_fills),
        },
        "account_version": account.get("version"),
        "position_count": len(matching),
        "account_signed_quantity": signed_quantity,
        "open_order_count": len(arrays["open_orders"]),
        "order_history_count": len(arrays["order_history"]),
        "fill_count": len(arrays["fills"]),
        "unresolved_order_count": len(arrays["unresolved"]),
        "order_state_counts": {
            key: state_counts[key] for key in sorted(state_counts)
        },
    }


def _verify_continuity_projection(
    context: Mapping[str, Any],
    *,
    prior_intents: Sequence[PaperExecutionIntentV1],
) -> None:
    projection = context.get("continuity_projection")
    expected_fields = frozenset(
        {
            "schema_id",
            "projection_version",
            "authority",
            "source_refs",
            "terminal_non_execution_suffix",
            "episode_transition_tail",
            "latest_attention_request",
            "mechanical_state",
            "subjective_assessments",
        }
    )
    if (
        not isinstance(projection, Mapping)
        or frozenset(projection) != expected_fields
        or projection.get("schema_id")
        != "agent-trade-emotion.v332-continuity-projection"
        or projection.get("projection_version") != "1.0.0"
        or projection.get("authority")
        != "NON_AUTHORITATIVE_READ_ONLY_FACT_PROJECTION"
    ):
        raise PaperCapabilityEvaluationError(
            "paper context continuity projection contract is invalid"
        )
    sources = projection.get("source_refs")
    expected_source_fields = frozenset(
        {
            "execution_intent_sha256s",
            "ledger_head_record_sha256",
            "snapshot_ref",
            "attention_stream_revision",
            "attention_stream_head_event_sha256",
            "prior_agent_texts",
        }
    )
    head = context.get("ledger_head")
    if (
        not isinstance(sources, Mapping)
        or frozenset(sources) != expected_source_fields
        or sources.get("execution_intent_sha256s")
        != [item.intent_sha256 for item in prior_intents]
        or not isinstance(head, Mapping)
        or sources.get("ledger_head_record_sha256") != head.get("record_sha256")
        or sources.get("snapshot_ref") != context.get("snapshot_ref")
        or type(sources.get("attention_stream_revision")) is not int
        or sources.get("attention_stream_revision", -1) < 0
        or not isinstance(sources.get("prior_agent_texts"), Mapping)
    ):
        raise PaperCapabilityEvaluationError(
            "paper context continuity source binding is invalid"
        )
    attention_revision = int(sources["attention_stream_revision"])
    attention_head = sources.get("attention_stream_head_event_sha256")
    if (attention_revision == 0) != (attention_head is None):
        raise PaperCapabilityEvaluationError(
            "paper context attention stream head is invalid"
        )
    if attention_head is not None and (
        not isinstance(attention_head, str)
        or len(attention_head) != 64
        or any(character not in "0123456789abcdef" for character in attention_head)
    ):
        raise PaperCapabilityEvaluationError(
            "paper context attention stream digest is invalid"
        )
    if projection.get(
        "terminal_non_execution_suffix"
    ) != _expected_terminal_non_execution_suffix(prior_intents):
        raise PaperCapabilityEvaluationError(
            "paper context terminal non-execution suffix is invalid"
        )
    if projection.get("episode_transition_tail") != _expected_episode_transition_tail(
        prior_intents
    ):
        raise PaperCapabilityEvaluationError(
            "paper context episode transition tail is invalid"
        )
    if projection.get("mechanical_state") != _expected_mechanical_state(context):
        raise PaperCapabilityEvaluationError(
            "paper context mechanical continuity facts are invalid"
        )

    latest_attention = projection.get("latest_attention_request")
    if not isinstance(latest_attention, Mapping) or frozenset(latest_attention) != {
        "status",
        "source_refs",
        "active_request_id",
        "request_status",
        "accepted_at",
        "request_sha256",
        "request",
    }:
        raise PaperCapabilityEvaluationError(
            "paper context latest attention request is invalid"
        )
    attention_sources = latest_attention.get("source_refs")
    if (
        not isinstance(attention_sources, Mapping)
        or attention_sources.get("stream_revision") != attention_revision
        or attention_sources.get("stream_head_event_sha256") != attention_head
    ):
        raise PaperCapabilityEvaluationError(
            "paper context attention source binding is invalid"
        )
    if latest_attention.get("status") == "NO_ATTENTION_REQUEST":
        if frozenset(attention_sources) != {
            "stream_revision",
            "stream_head_event_sha256",
        } or any(
            latest_attention.get(field) is not None
            for field in ("request_status", "accepted_at", "request_sha256", "request")
        ):
            raise PaperCapabilityEvaluationError(
                "paper context empty attention projection is invalid"
            )
    elif latest_attention.get("status") == "EXACT_AGENT_ATTENTION_REQUEST":
        try:
            attention_request = AttentionRequest.from_dict(
                latest_attention.get("request")
            )
        except (TypeError, ValueError) as exc:
            raise PaperCapabilityEvaluationError(
                "paper context exact attention request is invalid"
            ) from exc
        digest = attention_request.agent_owned_sha256
        if (
            frozenset(attention_sources)
            != {
                "stream_revision",
                "stream_head_event_sha256",
                "attention_request_sha256",
            }
            or attention_sources.get("attention_request_sha256") != digest
            or latest_attention.get("request_sha256") != digest
            or not isinstance(latest_attention.get("request_status"), str)
            or not isinstance(latest_attention.get("accepted_at"), str)
        ):
            raise PaperCapabilityEvaluationError(
                "paper context exact attention binding is invalid"
            )
    else:
        raise PaperCapabilityEvaluationError(
            "paper context attention projection status is invalid"
        )

    latest = None if not prior_intents else prior_intents[-1]
    subjective = projection.get("subjective_assessments")
    if not isinstance(subjective, Mapping) or frozenset(subjective) != {
        "trigger_capture",
        "geometry_deterioration",
        "opportunity_cost",
    }:
        raise PaperCapabilityEvaluationError(
            "paper context subjective assessment boundary is invalid"
        )
    if any(
        not isinstance(subjective.get(field), Mapping)
        or subjective[field].get("status") != "UNRESOLVED_AGENT_JUDGMENT"
        for field in subjective
    ):
        raise PaperCapabilityEvaluationError(
            "paper context must not infer Agent-owned continuity judgments"
        )
    trigger = subjective["trigger_capture"]
    geometry = subjective["geometry_deterioration"]
    if (
        trigger.get("prior_agent_declaration")
        != (None if latest is None else latest.activation)
        or geometry.get("prior_evidence_delta")
        != (None if latest is None else latest.evidence_delta)
        or geometry.get("prior_hard_invalidation")
        != (None if latest is None else latest.hard_invalidation)
    ):
        raise PaperCapabilityEvaluationError(
            "paper context subjective source text is invalid"
        )


def _context_continuity_binding(
    context: Mapping[str, Any],
    *,
    prior_intents: Sequence[PaperExecutionIntentV1],
) -> tuple[str, str | None, str | None, Mapping[str, str], str, str]:
    _verify_continuity_projection(context, prior_intents=prior_intents)
    status = context.get("prior_decision_status")
    latest = context.get("latest_prior_decision")
    projection = context.get("episode_exposure_projection")
    if not isinstance(projection, Mapping):
        raise PaperCapabilityEvaluationError(
            "paper context lacks an episode exposure projection"
        )
    projection_status = projection.get("status")
    if projection_status not in {
        "NO_PRIOR_INTENT",
        "DERIVED_UNAMBIGUOUS",
        "AMBIGUOUS",
        "UNKNOWN",
    }:
        raise PaperCapabilityEvaluationError(
            "paper context episode exposure projection status is invalid"
        )
    if projection.get("derivation") != "READ_ONLY_FACT_PROJECTION_NOT_AGENT_DECISION":
        raise PaperCapabilityEvaluationError(
            "paper context projection must remain a read-only fact projection"
        )
    projection_sources = projection.get("source_refs")
    head = context.get("ledger_head")
    if prior_intents:
        if (
            projection_status == "NO_PRIOR_INTENT"
            or not isinstance(projection_sources, Mapping)
            or not isinstance(head, Mapping)
            or projection_sources.get("execution_intent_sha256")
            != prior_intents[-1].intent_sha256
            or projection_sources.get("ledger_head_record_sha256")
            != head.get("record_sha256")
            or projection.get("episode_id") != prior_intents[-1].episode_id
            or projection.get("latest_transition_id")
            != prior_intents[-1].transition_id
            or projection.get("role") != prior_intents[-1].role
        ):
            raise PaperCapabilityEvaluationError(
                "paper context projection does not bind the latest intent and account head"
            )
    elif projection_status != "NO_PRIOR_INTENT" or projection_sources != {}:
        raise PaperCapabilityEvaluationError(
            "paper context empty intent history cannot project an episode"
        )
    projection_sha256 = canonical_digest(projection)
    if status == "PRIOR_COMPLETE_OBSERVED":
        if not isinstance(latest, Mapping) or frozenset(latest) != {
            "decision_cycle_id",
            "decision_sha256",
            "execution_intent_sha256",
            "cycle_stage",
            "authority",
            "retrieval_policy",
            "artifact_refs",
            "agent_decision_body",
            "agent_review_body",
        }:
            raise PaperCapabilityEvaluationError(
                "completed prior decision binding is incomplete"
            )
        matching_prior_intents = tuple(
            item
            for item in prior_intents
            if item.decision_cycle_id == latest.get("decision_cycle_id")
        )
        expected_intent_sha256 = (
            None
            if not matching_prior_intents
            else matching_prior_intents[-1].intent_sha256
        )
        if (
            latest.get("execution_intent_sha256") != expected_intent_sha256
            or latest.get("cycle_stage") != "COMPLETE"
            or latest.get("authority")
            != "NON_AUTHORITATIVE_CONTINUITY_CONTEXT"
            or latest.get("retrieval_policy")
            != "LATEST_COMPLETE_INCLUDED_BOUNDED"
        ):
            raise PaperCapabilityEvaluationError(
                "completed prior decision does not bind its optional exact intent"
            )
        raw_refs = latest.get("artifact_refs")
        expected_types = ("HypothesisRecord", "BehaviorPlan", "Outcome", "Review")
        if not isinstance(raw_refs, Mapping) or frozenset(raw_refs) != frozenset(
            expected_types
        ):
            raise PaperCapabilityEvaluationError(
                "completed prior decision artifact refs are incomplete"
            )
        try:
            refs = {
                artifact_type: ArtifactRef.from_dict(raw_refs[artifact_type])
                for artifact_type in expected_types
            }
        except (TypeError, ValueError) as exc:
            raise PaperCapabilityEvaluationError(
                "completed prior decision artifact ref is invalid"
            ) from exc
        if any(refs[kind].artifact_type != kind for kind in expected_types):
            raise PaperCapabilityEvaluationError(
                "completed prior decision artifact type is invalid"
            )
        body_specs = (
            (
                "agent_decision_body",
                refs["HypothesisRecord"],
                "/agent_decision_text",
                latest.get("decision_sha256"),
            ),
            (
                "agent_review_body",
                refs["Review"],
                "/agent_review_text",
                None,
            ),
        )
        for field, reference, pointer, expected_sha256 in body_specs:
            body = latest.get(field)
            if not isinstance(body, Mapping) or frozenset(body) != {
                "included_in_context",
                "verbatim_text",
                "size_bytes",
                "sha256",
                "artifact_ref",
                "source_json_pointer",
            }:
                raise PaperCapabilityEvaluationError(
                    "completed prior Agent text body is incomplete"
                )
            try:
                body_ref = ArtifactRef.from_dict(body.get("artifact_ref"))
            except (TypeError, ValueError) as exc:
                raise PaperCapabilityEvaluationError(
                    "completed prior Agent text body ref is invalid"
                ) from exc
            if (
                body.get("included_in_context") is not True
                or not isinstance(body.get("verbatim_text"), str)
                or not body.get("verbatim_text")
                or not isinstance(body.get("size_bytes"), int)
                or body.get("size_bytes") <= 0
                or body.get("size_bytes")
                != len(body.get("verbatim_text").encode("utf-8"))
                or not isinstance(body.get("sha256"), str)
                or len(body.get("sha256")) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in body.get("sha256")
                )
                or body.get("sha256")
                != hashlib.sha256(
                    body.get("verbatim_text").encode("utf-8")
                ).hexdigest()
                or body_ref != reference
                or body.get("source_json_pointer") != pointer
                or (
                    expected_sha256 is not None
                    and body.get("sha256") != expected_sha256
                )
            ):
                raise PaperCapabilityEvaluationError(
                    "completed prior Agent text body binding is invalid"
                )
        continuity = context["continuity_projection"]
        text_sources = continuity["source_refs"]["prior_agent_texts"]
        expected_text_sources = {
            field: {
                "sha256": latest[field]["sha256"],
                "artifact_ref": latest[field]["artifact_ref"],
            }
            for field in ("agent_decision_body", "agent_review_body")
        }
        if (
            text_sources != expected_text_sources
            or continuity["subjective_assessments"]["opportunity_cost"].get(
                "source_refs"
            )
            != expected_text_sources
        ):
            raise PaperCapabilityEvaluationError(
                "completed prior Agent texts do not bind continuity projection"
            )
        return (
            str(status),
            str(latest["decision_cycle_id"]),
            (
                None
                if latest["execution_intent_sha256"] is None
                else str(latest["execution_intent_sha256"])
            ),
            {kind: refs[kind].sha256 for kind in expected_types},
            str(projection_status),
            projection_sha256,
        )
    if status not in {
        "NO_PRIOR_INTENT",
        "UNAVAILABLE_CYCLE_REPOSITORY",
        "UNAVAILABLE_PRIOR_DECISION_ARTIFACT",
        "PRIOR_OUTCOME_REVIEW_PENDING",
    } or latest is not None:
        raise PaperCapabilityEvaluationError(
            "incomplete prior decision status cannot claim completed artifacts"
        )
    if not prior_intents and status != "NO_PRIOR_INTENT":
        raise PaperCapabilityEvaluationError(
            "paper context prior decision status conflicts with empty intent history"
        )
    continuity = context["continuity_projection"]
    if (
        continuity["source_refs"]["prior_agent_texts"] != {}
        or continuity["subjective_assessments"]["opportunity_cost"].get(
            "source_refs"
        )
        != {}
    ):
        raise PaperCapabilityEvaluationError(
            "incomplete prior decision cannot project Agent text bodies"
        )
    return (
        str(status),
        None,
        None,
        {},
        str(projection_status),
        projection_sha256,
    )


def _verify_hypothesis(
    evidence: PaperCapabilityEvidenceInputV1,
    *,
    request_sha256: str,
) -> None:
    hypothesis = evidence.hypothesis
    snapshot = evidence.snapshot
    if not isinstance(hypothesis, HypothesisRecord) or (
        hypothesis.cycle_id != snapshot.cycle_id
        or hypothesis.input_snapshot_ref != evidence.snapshot_ref
        or hypothesis.agent_request_sha256 != request_sha256
        or hypothesis.outcome_horizon_seconds != snapshot.outcome_horizon_seconds
        or hypothesis.outcome_tolerance_seconds != snapshot.outcome_tolerance_seconds
        or hypothesis.agent_decision_sha256
        != hashlib.sha256(hypothesis.agent_decision_text.encode("utf-8")).hexdigest()
    ):
        raise PaperCapabilityEvaluationError(
            "HypothesisRecord does not bind the exact request and snapshot"
        )


def _verify_behavior_plan(evidence: AttentionSchedulingEvidenceInputV1) -> None:
    plan = evidence.behavior_plan
    hypothesis = evidence.hypothesis
    if not isinstance(plan, BehaviorPlan):
        raise PaperCapabilityEvaluationError("behavior_plan must be BehaviorPlan")
    hypothesis_raw = canonical_bytes(hypothesis.to_dict())
    reference = plan.hypothesis_record_ref
    if (
        plan.cycle_id != evidence.snapshot.cycle_id
        or reference.artifact_type != "HypothesisRecord"
        or reference.artifact_id != hypothesis.record_id
        or reference.size_bytes != len(hypothesis_raw)
        or reference.sha256 != hashlib.sha256(hypothesis_raw).hexdigest()
        or plan.decision_at != hypothesis.decision_at
        or plan.agent_delivered_at != hypothesis.agent_delivered_at
        or plan.agent_request_sha256 != hypothesis.agent_request_sha256
        or plan.agent_delivery_path != hypothesis.agent_delivery_path
        or plan.agent_delivery_sha256 != hypothesis.agent_delivery_sha256
        or plan.agent_decision_text != hypothesis.agent_decision_text
        or plan.agent_decision_size_bytes != hypothesis.agent_decision_size_bytes
        or plan.agent_decision_sha256 != hypothesis.agent_decision_sha256
        or plan.projection_status != hypothesis.projection_status
        or plan.projection_reason != hypothesis.projection_reason
        or plan.hypothesis_index != hypothesis.hypothesis_index
        or plan.agent_action_text != hypothesis.agent_action_text
        or plan.agent_position_text != hypothesis.agent_position_text
        or plan.outcome_due_at != evidence.snapshot.outcome_due_at
        or plan.outcome_tolerance_seconds
        != evidence.snapshot.outcome_tolerance_seconds
        or plan.theory_identity != hypothesis.theory_identity
        or _time(plan.sealed_at, field="behavior_plan.sealed_at")
        < _time(hypothesis.sealed_at, field="hypothesis.sealed_at")
    ):
        raise PaperCapabilityEvaluationError(
            "BehaviorPlan does not bind the exact sealed hypothesis"
        )


def _attention_window(attention: AttentionRequest) -> tuple[str, str]:
    """Translate the Goal's own mode into the interval for its next decision."""

    if attention.continue_until is not None:
        return attention.issued_at, attention.continue_until
    assert attention.earliest_wake_at is not None
    return attention.earliest_wake_at, attention.latest_useful_at


def _followup_window_status(
    *, followup_decision_at: str, window_start_at: str, window_end_at: str
) -> str:
    followup = _time(followup_decision_at, field="followup_decision_at")
    start = _time(window_start_at, field="self_selected_window_start_at")
    end = _time(window_end_at, field="self_selected_window_end_at")
    if followup < start:
        return "BEFORE_SELF_SELECTED_WINDOW"
    if followup > end:
        return "AFTER_SELF_SELECTED_WINDOW"
    return "WITHIN_SELF_SELECTED_WINDOW"


def _verify_attention_checkpoint(
    evidence: AttentionSchedulingEvidenceInputV1,
    *,
    policy: ExperimentPolicyV1,
    paper_policy: Mapping[str, Any],
) -> tuple[str, str, str, str, str, str, str, str]:
    event = evidence.attention_checkpoint_event_document
    head = evidence.attention_stream_head_document
    attention = evidence.attention_request
    current = evidence.current_agent
    context = evidence.paper_context
    if (
        not isinstance(event, Mapping)
        or frozenset(event) != _ATTENTION_CHECKPOINT_EVENT_FIELDS
        or event.get("schema_id") != "agent-trade-emotion.v332-attention-event"
        or event.get("schema_version") != "1.0.0"
    ):
        raise PaperCapabilityEvaluationError(
            "durable attention checkpoint event is invalid"
        )
    if (
        not isinstance(head, Mapping)
        or frozenset(head) != _ATTENTION_STREAM_HEAD_FIELDS
        or head.get("schema_id") != "agent-trade-emotion.v332-attention-head"
        or head.get("schema_version") != "1.0.0"
    ):
        raise PaperCapabilityEvaluationError("durable attention stream head is invalid")
    if not isinstance(attention, AttentionRequest) or not isinstance(
        current, AgentRegistry
    ):
        raise PaperCapabilityEvaluationError(
            "attention request and current Agent registry are required"
        )
    if (
        current.physical_task_id is None
        or current.status not in {"ACTIVE", "IDLE"}
        or current.logical_agent_id != attention.logical_agent_id
        or current.generation != attention.agent_generation
        or current.continuity_nonce != attention.continuity_nonce
        or current.symbol != attention.symbol
        or current.logical_agent_id != paper_policy["logical_agent_id"]
        or current.generation != paper_policy["agent_generation"]
        or current.symbol != policy.instrument_id
    ):
        raise PaperCapabilityEvaluationError(
            "attention request does not bind the current physical Agent"
        )
    event_body = dict(event)
    event_sha256 = event_body.pop("event_sha256", None)
    payload = event.get("payload")
    accepted_at = payload.get("accepted_at") if isinstance(payload, Mapping) else None
    try:
        goal_checkpoint = GoalAttentionCheckpointV1.from_dict(
            payload.get("goal_checkpoint") if isinstance(payload, Mapping) else {}
        )
    except (AttentionContractError, TypeError) as exc:
        raise PaperCapabilityEvaluationError(
            "durable attention checkpoint lacks formal Goal provenance"
        ) from exc
    checkpoint_document_sha256 = canonical_digest(event)
    head_document_sha256 = canonical_digest(head)
    if (
        event_sha256 != canonical_digest(event_body)
        or event.get("logical_agent_id") != attention.logical_agent_id
        or type(event.get("revision")) is not int
        or event.get("revision", 0) < 2
        or event.get("event_id") != f"request:{attention.request_id}"
        or event.get("event_type") != "ATTENTION_REQUEST_SUBMITTED"
        or event.get("occurred_at") != accepted_at
        or not isinstance(payload, Mapping)
        or frozenset(payload) != {"request", "accepted_at", "goal_checkpoint"}
        or payload.get("request") != attention.to_dict()
        or not isinstance(accepted_at, str)
        or goal_checkpoint.run_id != policy.run_id
        or goal_checkpoint.experiment_policy_sha256 != policy.policy_sha256
        or goal_checkpoint.physical_goal_id != current.physical_task_id
        or goal_checkpoint.request_sha256 != attention.agent_owned_sha256
        or goal_checkpoint.accepted_at != accepted_at
    ):
        raise PaperCapabilityEvaluationError(
            "durable attention checkpoint does not bind exact Agent-owned bytes"
        )
    projection = context.get("continuity_projection")
    latest = (
        projection.get("latest_attention_request")
        if isinstance(projection, Mapping)
        else None
    )
    latest_sources = latest.get("source_refs") if isinstance(latest, Mapping) else None
    expected_position_ref = build_paper_position_and_open_order_ref(
        account_id=paper_policy["account_id"],
        ledger_revision=evidence.pre_ledger_head.revision,
        ledger_head_sha256=evidence.pre_ledger_head.record_sha256,
    )
    if attention.position_and_open_order_ref != expected_position_ref:
        raise PaperCapabilityEvaluationError(
            "attention request does not bind the exact frozen paper state ref"
        )
    if (
        attention.logical_agent_id != paper_policy["logical_agent_id"]
        or attention.agent_generation != paper_policy["agent_generation"]
        or attention.symbol != policy.instrument_id
        or attention.hypothesis_or_episode_ref is None
        or not isinstance(latest, Mapping)
        or latest.get("status") != "EXACT_AGENT_ATTENTION_REQUEST"
        or latest.get("active_request_id") != attention.request_id
        or latest.get("request_status") != "PENDING"
        or latest.get("accepted_at") != accepted_at
        or latest.get("request_sha256") != attention.agent_owned_sha256
        or latest.get("request") != attention.to_dict()
        or not isinstance(latest_sources, Mapping)
        or latest_sources.get("attention_request_sha256")
        != attention.agent_owned_sha256
        or head.get("logical_agent_id") != attention.logical_agent_id
        or head.get("revision") != event.get("revision")
        or head.get("event_sha256") != event_sha256
        or latest_sources.get("stream_revision") != head.get("revision")
        or latest_sources.get("stream_head_event_sha256") != event_sha256
    ):
        raise PaperCapabilityEvaluationError(
            "paper context does not bind the exact durable attention checkpoint head"
        )
    followup_decision_at = evidence.hypothesis.agent_delivered_at
    if not (
        _time(attention.issued_at, field="attention.issued_at")
        <= _time(accepted_at, field="attention_checkpoint.accepted_at")
        <= _time(followup_decision_at, field="followup_decision_at")
        < _time(evidence.snapshot.outcome_due_at, field="snapshot.outcome_due_at")
    ):
        raise PaperCapabilityEvaluationError(
            "attention checkpoint and real follow-up decision chronology is invalid"
        )
    window_start_at, window_end_at = _attention_window(attention)
    window_status = _followup_window_status(
        followup_decision_at=followup_decision_at,
        window_start_at=window_start_at,
        window_end_at=window_end_at,
    )
    return (
        checkpoint_document_sha256,
        str(event_sha256),
        head_document_sha256,
        str(accepted_at),
        window_start_at,
        window_end_at,
        followup_decision_at,
        window_status,
    )


def _verify_intent_request(
    evidence: PaperDecisionEvidenceInputV1,
    *,
    request_sha256: str,
) -> None:
    document = evidence.execution_intent_request_document
    intent = evidence.execution_intent
    if not isinstance(document, Mapping):
        raise PaperCapabilityEvaluationError(
            "execution_intent_request_document must be an object"
        )
    request_document_bytes = canonical_bytes(evidence.request_document) + b"\n"
    intent_request_bytes = canonical_bytes(document) + b"\n"
    output_contract = document.get("output_contract")
    readable_text_constraint = {
        "json_type": "STRING",
        "non_empty_after_strip": True,
        "maximum_characters": 16_384,
    }
    output_contract_fields = {
        "schema_id",
        "schema_version",
        "canonical_encoding",
        "write_semantics",
        "canonical_decimal_format",
        "output_relative_path",
        "exact_fields",
        "fixed_values",
        "dynamic_values",
        "allowed_values",
        "field_constraints",
        "paper_action_space",
        "context_values",
        "state_shapes",
        "command_shape",
        "bracket_shape",
        "action_constraints",
        "global_constraints",
    }
    field_constraints = (
        output_contract.get("field_constraints")
        if isinstance(output_contract, Mapping)
        else None
    )
    action_constraints = (
        output_contract.get("action_constraints")
        if isinstance(output_contract, Mapping)
        else None
    )
    expected_fixed_values = {
        "schema_id": "agent-trade-emotion.paper-execution-intent",
        "schema_version": "1.3.0",
        "decision_request_sha256": request_sha256,
        "paper_context_sha256": intent.paper_context_sha256,
        "ledger_head_record_sha256": intent.ledger_head_record_sha256,
        "decision_cycle_id": intent.decision_cycle_id,
        "decision_sha256": intent.decision_sha256,
        "account_id": intent.account_id,
        "logical_agent_id": intent.logical_agent_id,
        "agent_generation": intent.agent_generation,
        "expected_account_version": intent.expected_account_version,
        "symbol": intent.symbol,
    }
    fresh_output_contract_valid = (
        isinstance(output_contract, Mapping)
        and set(output_contract) == output_contract_fields
        and output_contract.get("schema_id")
        == "agent-trade-emotion.paper-execution-intent-output-contract"
        and output_contract.get("schema_version") == "1.3.0"
        and output_contract.get("canonical_encoding")
        == "RFC8259_CANONICAL_COMPACT_UTF8_SORTED_KEYS_PLUS_ONE_NEWLINE"
        and output_contract.get("output_relative_path")
        == "transport/paper-execution-intent.json"
        and output_contract.get("exact_fields") == sorted(intent.to_dict())
        and output_contract.get("fixed_values") == expected_fixed_values
        and isinstance(field_constraints, Mapping)
        and all(
            field_constraints.get(field_name) == readable_text_constraint
            for field_name in (
                "evidence_delta",
                "activation",
                "hard_invalidation",
            )
        )
        and canonical_bytes(output_contract.get("paper_action_space"))
        == canonical_bytes(evidence.paper_context.get("paper_action_space"))
        and isinstance(action_constraints, Mapping)
        and action_constraints.get("non_executable_actions")
        == sorted(PAPER_NON_EXECUTABLE_ACTIONS)
        and action_constraints.get("bracket_allowed_actions")
        == sorted(PAPER_BRACKET_ELIGIBLE_ACTIONS)
        and "EXACT_FIELDS_LISTS_ARE_CANONICAL_WIRE_ORDER_FOR_DECLARED_OBJECTS"
        in output_contract.get("global_constraints", ())
        and "ALL_OBJECT_KEYS_RECURSIVELY_ASCENDING_UTF16_CODE_UNITS"
        in output_contract.get("global_constraints", ())
    )
    if (
        document.get("schema_id")
        != "agent-trade-emotion.paper-execution-intent-request"
        or document.get("schema_version") != "1.0.0"
        or hashlib.sha256(intent_request_bytes).hexdigest()
        != intent.execution_intent_request_sha256
        or document.get("cycle_id") != intent.decision_cycle_id
        or document.get("decision_request_sha256") != request_sha256
        or document.get("agent_request_document_sha256")
        != hashlib.sha256(request_document_bytes).hexdigest()
        or document.get("paper_context_sha256") != intent.paper_context_sha256
        or document.get("ledger_head_record_sha256")
        != intent.ledger_head_record_sha256
        or document.get("expected_account_version")
        != intent.expected_account_version
        or document.get("account_id") != intent.account_id
        or document.get("logical_agent_id") != intent.logical_agent_id
        or document.get("agent_generation") != intent.agent_generation
        or not isinstance(document.get("physical_task_id"), str)
        or document.get("symbol") != intent.symbol
        or document.get("decision_sha256") != intent.decision_sha256
        or intent.action not in document.get("allowed_actions", ())
        or document.get("output_schema_id")
        != "agent-trade-emotion.paper-execution-intent"
        or document.get("output_schema_version")
        != intent.wire_schema_version
        or intent.wire_schema_version != "1.3.0"
        or not fresh_output_contract_valid
    ):
        raise PaperCapabilityEvaluationError(
            "execution intent request does not bind the Agent intent"
        )
    if not (
        _time(document.get("issued_at"), field="intent_request.issued_at")
        <= _time(intent.authored_at, field="intent.authored_at")
        < _time(intent.valid_until, field="intent.valid_until")
        <= _time(document.get("valid_until"), field="intent_request.valid_until")
    ):
        raise PaperCapabilityEvaluationError("execution intent request window is invalid")


def _verify_intent_and_heads(
    evidence: PaperDecisionEvidenceInputV1,
    *,
    policy: ExperimentPolicyV1,
    paper_policy: Mapping[str, Any],
    request_sha256: str,
) -> None:
    intent = evidence.execution_intent
    hypothesis = evidence.hypothesis
    pre = evidence.pre_ledger_head
    post = evidence.post_ledger_head
    context = evidence.paper_context
    if not isinstance(intent, PaperExecutionIntentV1):
        raise PaperCapabilityEvaluationError(
            "execution_intent must be PaperExecutionIntentV1"
        )
    if (
        intent.decision_cycle_id != evidence.snapshot.cycle_id
        or intent.decision_sha256 != hypothesis.agent_decision_sha256
        or intent.decision_request_sha256 != request_sha256
        or intent.paper_context_sha256 != context.get("paper_context_sha256")
        or intent.ledger_head_record_sha256 != pre.record_sha256
        or intent.expected_account_version != pre.revision
        or intent.account_id != paper_policy["account_id"]
        or intent.logical_agent_id != paper_policy["logical_agent_id"]
        or intent.agent_generation != paper_policy["agent_generation"]
        or intent.symbol != policy.instrument_id
    ):
        raise PaperCapabilityEvaluationError(
            "execution intent identity or pre-state binding is invalid"
        )
    account = context["account"]
    current_quantity = Decimal("0")
    try:
        for position in account.get("positions", ()):
            if position.get("symbol") == intent.symbol:
                current_quantity = Decimal(str(position["quantity"]))
        pre_quantity = Decimal(str(intent.pre_state["signed_quantity"]))
        maximum_loss = Decimal(str(intent.risk_budget["maximum_loss"]))
        notional_cap = Decimal(str(intent.risk_budget["notional_cap"]))
        drawdown_cap = Decimal(str(intent.risk_budget["max_observed_drawdown"]))
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise PaperCapabilityEvaluationError(
            "execution intent state or risk binding is invalid"
        ) from exc
    if (
        pre_quantity != current_quantity
        or maximum_loss > Decimal(str(paper_policy["max_decision_loss"]))
        or notional_cap > Decimal(str(paper_policy["max_position_notional"]))
        or drawdown_cap > Decimal(str(paper_policy["max_observed_drawdown"]))
    ):
        raise PaperCapabilityEvaluationError(
            "execution intent exceeds or disagrees with the paper account state"
        )
    commands = (
        ()
        if intent.command is None
        else (
            intent.bracket.commands
            if intent.bracket is not None
            else (intent.command,)
        )
    )
    if any(
        command.cost_model_id != paper_policy["cost_model"]["model_id"]
        for command in commands
    ):
        raise PaperCapabilityEvaluationError(
            "execution intent commands do not bind the frozen cost model"
        )
    if not isinstance(pre, PaperLedgerRecordV1) or not isinstance(
        post, PaperLedgerRecordV1
    ):
        raise PaperCapabilityEvaluationError(
            "pre and post ledger heads must be PaperLedgerRecordV1"
        )
    expected_event = "INTENT_RECORDED" if intent.command is None else "COMMAND_ACCEPTED"
    try:
        ledger_intent_matches = canonical_bytes(
            post.payload.get("execution_intent")
        ) == canonical_bytes(intent.to_dict())
    except (TypeError, ValueError):
        ledger_intent_matches = False
    if (
        pre.account_id != intent.account_id
        or post.account_id != intent.account_id
        or post.revision != pre.revision + 1
        or post.previous_record_sha256 != pre.record_sha256
        or post.event_type != expected_event
        or not ledger_intent_matches
        or post.occurred_at < pre.occurred_at
    ):
        raise PaperCapabilityEvaluationError(
            "post-ledger head does not record the exact Agent intent"
        )
    _verify_intent_request(evidence, request_sha256=request_sha256)


def _verify_current_goal_agent(
    evidence: PaperDecisionEvidenceInputV1,
    *,
    policy: ExperimentPolicyV1,
    paper_policy: Mapping[str, Any],
) -> None:
    current = evidence.current_agent
    physical_task_id = evidence.execution_intent_request_document.get(
        "physical_task_id"
    )
    intent = evidence.execution_intent
    if not isinstance(current, AgentRegistry) or (
        current.physical_task_id is None
        or physical_task_id != current.physical_task_id
        or current.logical_agent_id != intent.logical_agent_id
        or current.logical_agent_id != paper_policy["logical_agent_id"]
        or current.generation != intent.agent_generation
        or current.generation != paper_policy["agent_generation"]
        or current.symbol != intent.symbol
        or current.symbol != policy.instrument_id
    ):
        raise PaperCapabilityEvaluationError(
            "intent request does not bind the current long-lived Goal Agent"
        )


def _source_bytes(
    evidence: PaperCapabilityEvidenceInputV1, source_kind: str
) -> bytes:
    if not isinstance(
        evidence, (PaperDecisionEvidenceInputV1, AttentionSchedulingEvidenceInputV1)
    ):
        raise PaperCapabilityEvaluationError(
            "evidence must be a supported paper capability evidence input"
        )
    if source_kind == "DECISION_TEXT":
        return evidence.hypothesis.agent_decision_text.encode("utf-8", errors="strict")
    if source_kind == "EXECUTION_INTENT":
        if not isinstance(evidence, PaperDecisionEvidenceInputV1):
            raise PaperCapabilityEvaluationError(
                "attention scheduling has no execution-intent evidence source"
            )
        return canonical_bytes(evidence.execution_intent.to_dict())
    if source_kind == "ATTENTION_REQUEST":
        if not isinstance(evidence, AttentionSchedulingEvidenceInputV1):
            raise PaperCapabilityEvaluationError(
                "trading and position evidence has no attention source"
            )
        return canonical_bytes(evidence.attention_request.to_dict())
    raise PaperCapabilityEvaluationError("source_kind is unsupported")


def bind_paper_capability_span(
    evidence: PaperCapabilityEvidenceInputV1,
    *,
    source_kind: str,
    exact_excerpt: str,
) -> PaperEvidenceSpanV1:
    """Bind one unique human-selected excerpt to an exact Agent-owned source."""

    if type(exact_excerpt) is not str or not exact_excerpt:
        raise PaperCapabilityEvaluationError("exact_excerpt must be non-empty UTF-8 text")
    raw = _source_bytes(evidence, source_kind)
    selected = exact_excerpt.encode("utf-8", errors="strict")
    start = raw.find(selected)
    if start < 0 or raw.find(selected, start + 1) >= 0:
        raise PaperCapabilityEvaluationError(
            "exact_excerpt must occur exactly once in the selected source"
        )
    return PaperEvidenceSpanV1(
        cycle_id=evidence.snapshot.cycle_id,
        source_kind=source_kind,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        start_byte=start,
        end_byte=start + len(selected),
        selected_utf8_sha256=hashlib.sha256(selected).hexdigest(),
    )


def _bind_point(
    evidence: PaperDecisionEvidenceInputV1,
    *,
    policy: ExperimentPolicyV1,
    capability_id: str,
) -> BoundPaperDecisionPointV1:
    if not isinstance(evidence, PaperDecisionEvidenceInputV1):
        raise PaperCapabilityEvaluationError(
            "decision evidence must be PaperDecisionEvidenceInputV1"
        )
    _verify_snapshot_ref(evidence.snapshot, evidence.snapshot_ref)
    paper_policy = _verify_policy(
        policy, capability_id=capability_id, snapshot=evidence.snapshot
    )
    request_sha256, request_document_sha256, prior_intents = (
        _verify_request_and_context(
            evidence, policy=policy, paper_policy=paper_policy
        )
    )
    (
        prior_decision_status,
        prior_complete_cycle_id,
        prior_complete_intent_sha256,
        prior_complete_artifact_sha256s,
        episode_exposure_projection_status,
        episode_exposure_projection_sha256,
    ) = _context_continuity_binding(
        evidence.paper_context,
        prior_intents=tuple(
            PaperExecutionIntentV1.from_dict(item)
            for item in evidence.paper_context["prior_execution_intents"]
        ),
    )
    if evidence.cycle_stage == "COMPLETE":
        completion_status = "COMPLETE"
    elif evidence.cycle_stage in {
        "BEHAVIOR_PLANNED",
        "PLAN_SEALED",
        "ANALYZED",
    }:
        completion_status = "PRE_OUTCOME"
    else:
        raise PaperCapabilityEvaluationError(
            "paper capability cycle stage is neither complete nor pre-outcome"
        )
    _verify_hypothesis(evidence, request_sha256=request_sha256)
    _verify_intent_and_heads(
        evidence,
        policy=policy,
        paper_policy=paper_policy,
        request_sha256=request_sha256,
    )
    _verify_current_goal_agent(
        evidence, policy=policy, paper_policy=paper_policy
    )
    intent = evidence.execution_intent
    current_agent = evidence.current_agent
    return BoundPaperDecisionPointV1(
        cycle_id=evidence.snapshot.cycle_id,
        snapshot_id=evidence.snapshot.snapshot_id,
        snapshot_sha256=evidence.snapshot_ref.sha256,
        snapshot_sealed_at=evidence.snapshot.sealed_at,
        outcome_due_at=evidence.snapshot.outcome_due_at,
        request_sha256=request_sha256,
        request_document_sha256=request_document_sha256,
        decision_sha256=evidence.hypothesis.agent_decision_sha256,
        hypothesis_record_sha256=canonical_digest(evidence.hypothesis.to_dict()),
        decision_size_bytes=evidence.hypothesis.agent_decision_size_bytes,
        decision_sealed_at=evidence.hypothesis.sealed_at,
        intent_id=intent.intent_id,
        intent_sha256=intent.intent_sha256,
        intent_request_sha256=intent.execution_intent_request_sha256,
        paper_context_sha256=intent.paper_context_sha256,
        intent_authored_at=intent.authored_at,
        intent_valid_until=intent.valid_until,
        action=intent.action,
        account_id=intent.account_id,
        logical_agent_id=intent.logical_agent_id,
        physical_task_id=str(current_agent.physical_task_id),
        agent_generation=intent.agent_generation,
        symbol=intent.symbol,
        episode_id=intent.episode_id,
        transition_id=intent.transition_id,
        tranche_id=intent.tranche_id,
        role=intent.role,
        pre_ledger_revision=evidence.pre_ledger_head.revision,
        pre_ledger_head_sha256=evidence.pre_ledger_head.record_sha256,
        post_ledger_revision=evidence.post_ledger_head.revision,
        post_ledger_head_sha256=evidence.post_ledger_head.record_sha256,
        post_ledger_occurred_at=evidence.post_ledger_head.occurred_at,
        lawful_actions=evidence.snapshot.lawful_actions,
        prior_intent_sha256s=prior_intents,
        cycle_completion_status=completion_status,
        prior_decision_status=prior_decision_status,
        prior_complete_cycle_id=prior_complete_cycle_id,
        prior_complete_intent_sha256=prior_complete_intent_sha256,
        prior_complete_artifact_sha256s=prior_complete_artifact_sha256s,
        episode_exposure_projection_status=episode_exposure_projection_status,
        episode_exposure_projection_sha256=episode_exposure_projection_sha256,
        position_mechanical_evidence=None,
        source_sha256s={
            kind: hashlib.sha256(_source_bytes(evidence, kind)).hexdigest()
            for kind in PAPER_EVIDENCE_SOURCE_KINDS
        },
    )


def _bind_attention_point(
    evidence: AttentionSchedulingEvidenceInputV1,
    *,
    policy: ExperimentPolicyV1,
) -> BoundAttentionSchedulingPointV1:
    if not isinstance(evidence, AttentionSchedulingEvidenceInputV1):
        raise PaperCapabilityEvaluationError(
            "attention evidence must be AttentionSchedulingEvidenceInputV1"
        )
    _verify_snapshot_ref(evidence.snapshot, evidence.snapshot_ref)
    paper_policy = _verify_policy(
        policy, capability_id="ATTENTION_SCHEDULING", snapshot=evidence.snapshot
    )
    request_sha256, request_document_sha256, _ = _verify_request_and_context(
        evidence, policy=policy, paper_policy=paper_policy
    )
    _verify_hypothesis(evidence, request_sha256=request_sha256)
    _verify_behavior_plan(evidence)
    (
        checkpoint_document_sha256,
        checkpoint_event_sha256,
        stream_head_document_sha256,
        checkpoint_accepted_at,
        window_start_at,
        window_end_at,
        followup_decision_at,
        followup_window_status,
    ) = _verify_attention_checkpoint(
        evidence,
        policy=policy,
        paper_policy=paper_policy,
    )
    attention = evidence.attention_request
    event = evidence.attention_checkpoint_event_document
    head = evidence.attention_stream_head_document
    current = evidence.current_agent
    data_evidence = evidence.paper_context.get("data_evidence")
    if (
        not isinstance(data_evidence, Mapping)
        or not isinstance(data_evidence.get("slice_sha256"), str)
        or not isinstance(data_evidence.get("data_cursor"), str)
    ):
        raise PaperCapabilityEvaluationError(
            "paper context lacks exact current data evidence"
        )
    return BoundAttentionSchedulingPointV1(
        cycle_id=evidence.snapshot.cycle_id,
        snapshot_id=evidence.snapshot.snapshot_id,
        snapshot_sha256=evidence.snapshot_ref.sha256,
        snapshot_sealed_at=evidence.snapshot.sealed_at,
        outcome_due_at=evidence.snapshot.outcome_due_at,
        request_sha256=request_sha256,
        request_document_sha256=request_document_sha256,
        decision_sha256=evidence.hypothesis.agent_decision_sha256,
        decision_size_bytes=evidence.hypothesis.agent_decision_size_bytes,
        decision_sealed_at=evidence.hypothesis.sealed_at,
        behavior_plan_id=evidence.behavior_plan.plan_id,
        behavior_plan_sha256=canonical_digest(evidence.behavior_plan.to_dict()),
        behavior_plan_sealed_at=evidence.behavior_plan.sealed_at,
        paper_context_sha256=str(evidence.paper_context["paper_context_sha256"]),
        account_id=str(paper_policy["account_id"]),
        logical_agent_id=attention.logical_agent_id,
        physical_task_id=str(current.physical_task_id),
        agent_generation=attention.agent_generation,
        continuity_nonce=attention.continuity_nonce,
        symbol=attention.symbol,
        pre_ledger_revision=evidence.pre_ledger_head.revision,
        pre_ledger_head_sha256=evidence.pre_ledger_head.record_sha256,
        data_slice_sha256=str(data_evidence["slice_sha256"]),
        data_cursor=str(data_evidence["data_cursor"]),
        attention_request_id=attention.request_id,
        attention_sha256=attention.agent_owned_sha256,
        attention_mode=attention.mode,
        attention_issued_at=attention.issued_at,
        attention_checkpoint_document_sha256=checkpoint_document_sha256,
        attention_checkpoint_event_sha256=checkpoint_event_sha256,
        attention_checkpoint_revision=int(event["revision"]),
        attention_checkpoint_accepted_at=checkpoint_accepted_at,
        attention_stream_head_document_sha256=stream_head_document_sha256,
        attention_stream_head_event_sha256=str(head["event_sha256"]),
        attention_stream_head_revision=int(head["revision"]),
        self_selected_window_start_at=window_start_at,
        self_selected_window_end_at=window_end_at,
        followup_decision_at=followup_decision_at,
        followup_window_status=followup_window_status,
        source_sha256s={
            kind: hashlib.sha256(_source_bytes(evidence, kind)).hexdigest()
            for kind in ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS
        },
    )


def _bind_capability_point(
    evidence: PaperCapabilityEvidenceInputV1,
    *,
    policy: ExperimentPolicyV1,
    capability_id: str,
) -> BoundPaperDecisionPointV1 | BoundAttentionSchedulingPointV1:
    if capability_id == "ATTENTION_SCHEDULING":
        if not isinstance(evidence, AttentionSchedulingEvidenceInputV1):
            raise PaperCapabilityEvaluationError(
                "ATTENTION_SCHEDULING requires attention-only evidence"
            )
        return _bind_attention_point(evidence, policy=policy)
    if not isinstance(evidence, PaperDecisionEvidenceInputV1):
        raise PaperCapabilityEvaluationError(
            "trading and position capabilities require paper decision evidence"
        )
    return _bind_point(evidence, policy=policy, capability_id=capability_id)


def _position_mechanical_evidence(
    *,
    d0: PaperDecisionEvidenceInputV1,
    d1: PaperDecisionEvidenceInputV1,
    d0_point: BoundPaperDecisionPointV1,
    d1_point: BoundPaperDecisionPointV1,
) -> PositionMechanicalEvidenceV1:
    """Rebuild the minimum real-position qualification from exact D0/D1 facts."""

    bracket = d0.execution_intent.bracket
    if bracket is None:
        raise PaperCapabilityEvaluationError(
            "position evidence D0 must be an Agent-authored protected bracket"
        )
    context = d1.paper_context
    account = context.get("account")
    orders_and_fills = context.get("orders_and_fills")
    valuation = context.get("valuation")
    ledger_head = context.get("ledger_head")
    if not all(
        isinstance(item, Mapping)
        for item in (account, orders_and_fills, valuation, ledger_head)
    ):
        raise PaperCapabilityEvaluationError(
            "position D1 paper context lacks exact account, order, valuation or ledger facts"
        )
    assert isinstance(account, Mapping)
    assert isinstance(orders_and_fills, Mapping)
    assert isinstance(valuation, Mapping)
    assert isinstance(ledger_head, Mapping)
    if (
        account.get("account_id") != d1_point.account_id
        or account.get("version") != d1_point.pre_ledger_revision
        or ledger_head.get("revision") != d1_point.pre_ledger_revision
        or ledger_head.get("record_sha256") != d1_point.pre_ledger_head_sha256
        or orders_and_fills.get("account_id") != d1_point.account_id
        or d0.execution_intent.account_id != d1_point.account_id
        or d0.execution_intent.symbol != d1_point.symbol
        or d0.execution_intent.episode_id != d1_point.episode_id
    ):
        raise PaperCapabilityEvaluationError(
            "position mechanical sources do not bind one account, symbol, episode and D1 head"
        )
    raw_positions = account.get("positions")
    raw_orders = account.get("orders")
    raw_open_orders = orders_and_fills.get("open_orders")
    raw_fills = orders_and_fills.get("fills")
    if not all(
        isinstance(item, list)
        for item in (raw_positions, raw_orders, raw_open_orders, raw_fills)
    ):
        raise PaperCapabilityEvaluationError(
            "position D1 account and order projections are incomplete"
        )
    matching_positions = tuple(
        item
        for item in raw_positions
        if isinstance(item, Mapping) and item.get("symbol") == d1_point.symbol
    )
    if len(matching_positions) != 1:
        raise PaperCapabilityEvaluationError(
            "position evidence requires exactly one non-zero D1 symbol position"
        )
    try:
        signed_quantity = Decimal(str(matching_positions[0]["quantity"]))
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise PaperCapabilityEvaluationError(
            "position D1 signed quantity is invalid"
        ) from exc
    if not signed_quantity.is_finite() or signed_quantity == 0:
        raise PaperCapabilityEvaluationError(
            "position evidence requires a non-zero D1 symbol position"
        )
    try:
        orders = tuple(
            OrderTruthV1(**dict(item))
            for item in raw_orders
            if isinstance(item, Mapping)
        )
        open_orders = tuple(
            OrderTruthV1(**dict(item))
            for item in raw_open_orders
            if isinstance(item, Mapping)
        )
        fills = tuple(
            FillEventV1(**dict(item))
            for item in raw_fills
            if isinstance(item, Mapping)
        )
    except (TypeError, ValueError) as exc:
        raise PaperCapabilityEvaluationError(
            "position D1 order or fill truth is invalid"
        ) from exc
    if len(orders) != len(raw_orders) or len(open_orders) != len(raw_open_orders) or len(
        fills
    ) != len(raw_fills):
        raise PaperCapabilityEvaluationError(
            "position D1 order or fill truth contains a non-object"
        )
    entry = bracket.entry
    entry_fills = tuple(
        item
        for item in fills
        if item.order_id == entry.command_id
        and item.command_id == entry.command_id
        and item.account_id == d1_point.account_id
        and item.symbol == d1_point.symbol
        and item.side == entry.side
    )
    if not entry_fills:
        raise PaperCapabilityEvaluationError(
            "position evidence requires an actual D0 entry fill in D1 truth"
        )
    stop_command = bracket.protective_stop
    stop_matches = tuple(
        item
        for item in orders
        if item.order_id == stop_command.command_id
        and item.command_id == stop_command.command_id
    )
    open_stop_matches = tuple(
        item
        for item in open_orders
        if item.order_id == stop_command.command_id
        and item.command_id == stop_command.command_id
    )
    if (
        len(stop_matches) != 1
        or len(open_stop_matches) != 1
        or canonical_bytes(stop_matches[0].to_dict())
        != canonical_bytes(open_stop_matches[0].to_dict())
    ):
        raise PaperCapabilityEvaluationError(
            "position evidence requires the exact D0 protective stop as a D1 open order"
        )
    stop = stop_matches[0]
    if (
        stop.account_id != d1_point.account_id
        or stop.logical_agent_id != d1_point.logical_agent_id
        or stop.symbol != d1_point.symbol
        or stop.command_type != "STOP_LOSS"
        or stop.side != ("SELL" if signed_quantity > 0 else "BUY")
        or not stop.reduce_only
        or stop.state not in {"OPEN", "PARTIALLY_FILLED"}
        or Decimal(stop.remaining_quantity) < abs(signed_quantity)
        or stop.side != stop_command.side
        or stop.trigger_price != stop_command.trigger_price
    ):
        raise PaperCapabilityEvaluationError(
            "D1 position lacks an active sufficient opposite reduce-only STOP_LOSS"
        )
    mark_basis = valuation.get("mark_basis")
    data_evidence = context.get("data_evidence")
    if (
        not isinstance(mark_basis, Mapping)
        or frozenset(mark_basis)
        != {
            "status",
            "snapshot_ref",
            "market_fact_cutoff_at",
            "data_slice_sha256",
        }
        or mark_basis.get("status") != "DECISION_SNAPSHOT_MARK_ONLY"
        or mark_basis.get("snapshot_ref") != d1.snapshot_ref.to_dict()
        or mark_basis.get("market_fact_cutoff_at") != d1.snapshot.sealed_at
        or not isinstance(data_evidence, Mapping)
        or mark_basis.get("data_slice_sha256") != data_evidence.get("slice_sha256")
        or valuation.get("account_id") != d1_point.account_id
        or valuation.get("account_version") != d1_point.pre_ledger_revision
        or valuation.get("symbol") != d1_point.symbol
    ):
        raise PaperCapabilityEvaluationError(
            "position D1 valuation does not bind the exact decision snapshot and account head"
        )
    observed_at = valuation.get("observed_at")
    available_at = valuation.get("available_at")
    if isinstance(observed_at, str) and isinstance(available_at, str) and not (
        _time(observed_at, field="valuation.observed_at")
        <= _time(available_at, field="valuation.available_at")
        <= _time(d1.snapshot.sealed_at, field="snapshot.sealed_at")
    ):
        raise PaperCapabilityEvaluationError(
            "position D1 valuation mark chronology is not PIT-valid"
        )
    fresh = (
        valuation.get("status") in {"COMPLETE", "PARTIAL_UNKNOWN_CARRY_COSTS"}
        and isinstance(valuation.get("mark"), str)
        and isinstance(valuation.get("unrealized_pnl"), str)
        and isinstance(observed_at, str)
        and isinstance(available_at, str)
        and isinstance(valuation.get("source_sha256"), str)
    )
    if fresh:
        try:
            unrealized = Decimal(str(valuation["unrealized_pnl"]))
        except (InvalidOperation, KeyError) as exc:
            raise PaperCapabilityEvaluationError(
                "position D1 unrealized PnL is invalid"
            ) from exc
        if not unrealized.is_finite():
            raise PaperCapabilityEvaluationError(
                "position D1 unrealized PnL is invalid"
            )
        mark_binding_status = "FRESH_SNAPSHOT_BOUND"
        loss_status = (
            "LOSING_FRESH_MARK" if unrealized < 0 else "NON_LOSING_FRESH_MARK"
        )
    else:
        mark_binding_status = "UNKNOWN_NOT_FRESH_OR_COMPLETE"
        loss_status = "UNKNOWN_NOT_FRESH_OR_COMPLETE"
    return PositionMechanicalEvidenceV1(
        d0_cycle_id=d0_point.cycle_id,
        d1_cycle_id=d1_point.cycle_id,
        account_id=d1_point.account_id,
        symbol=d1_point.symbol,
        episode_id=d1_point.episode_id,
        d0_intent_sha256=d0_point.intent_sha256,
        d0_bracket_sha256=canonical_digest(bracket.to_dict()),
        d0_entry_order_id=entry.command_id,
        d0_protective_stop_order_id=stop_command.command_id,
        d1_snapshot_sha256=d1_point.snapshot_sha256,
        d1_paper_context_sha256=d1_point.paper_context_sha256,
        d1_account_sha256=canonical_digest(account),
        d1_orders_and_fills_sha256=canonical_digest(orders_and_fills),
        d1_valuation_sha256=canonical_digest(valuation),
        d1_ledger_revision=d1_point.pre_ledger_revision,
        d1_ledger_head_sha256=d1_point.pre_ledger_head_sha256,
        d1_account_version=int(account["version"]),
        entry_fill_ids=tuple(item.fill_id for item in entry_fills),
        entry_fill_sha256s=tuple(
            canonical_digest(item.to_dict()) for item in entry_fills
        ),
        entry_filled_quantity=canonical_decimal(
            sum((Decimal(item.quantity) for item in entry_fills), Decimal("0"))
        ),
        position_signed_quantity=canonical_decimal(signed_quantity),
        position_abs_quantity=canonical_decimal(abs(signed_quantity)),
        protective_stop_order_sha256=canonical_digest(stop.to_dict()),
        protective_stop_command_type=stop.command_type,
        protective_stop_state=stop.state,
        protective_stop_side=stop.side,
        protective_stop_reduce_only=stop.reduce_only,
        protective_stop_remaining_quantity=stop.remaining_quantity,
        valuation_status=str(valuation.get("status")),
        valuation_mark=(
            str(valuation["mark"]) if isinstance(valuation.get("mark"), str) else None
        ),
        valuation_unrealized_pnl=(
            str(valuation["unrealized_pnl"])
            if isinstance(valuation.get("unrealized_pnl"), str)
            else None
        ),
        valuation_observed_at=(str(observed_at) if isinstance(observed_at, str) else None),
        valuation_available_at=(
            str(available_at) if isinstance(available_at, str) else None
        ),
        valuation_source_sha256=(
            str(valuation["source_sha256"])
            if isinstance(valuation.get("source_sha256"), str)
            else None
        ),
        valuation_mark_binding_status=mark_binding_status,
        loss_observation_status=loss_status,
    )


def _bind_capability_points(
    evidence_points: Sequence[PaperCapabilityEvidenceInputV1],
    *,
    policy: ExperimentPolicyV1,
    capability_id: str,
) -> tuple[BoundPaperDecisionPointV1 | BoundAttentionSchedulingPointV1, ...]:
    points = tuple(
        _bind_capability_point(item, policy=policy, capability_id=capability_id)
        for item in evidence_points
    )
    if capability_id != "POSITION_MANAGEMENT":
        return points
    if len(points) < 2 or not all(
        isinstance(item, PaperDecisionEvidenceInputV1) for item in evidence_points
    ) or not all(isinstance(item, BoundPaperDecisionPointV1) for item in points):
        return points
    typed_evidence = tuple(evidence_points)
    typed_points = tuple(points)
    assert isinstance(typed_evidence[0], PaperDecisionEvidenceInputV1)
    assert isinstance(typed_evidence[-1], PaperDecisionEvidenceInputV1)
    assert isinstance(typed_points[0], BoundPaperDecisionPointV1)
    assert isinstance(typed_points[-1], BoundPaperDecisionPointV1)
    mechanical = _position_mechanical_evidence(
        d0=typed_evidence[0],
        d1=typed_evidence[-1],
        d0_point=typed_points[0],
        d1_point=typed_points[-1],
    )
    return (*typed_points[:-1], replace(typed_points[-1], position_mechanical_evidence=mechanical))


def build_pre_outcome_paper_capability_task(
    *,
    task_id: str,
    capability_id: str,
    policy: ExperimentPolicyV1,
    evidence_points: Sequence[PaperCapabilityEvidenceInputV1],
    subject_agent_id: str,
    assessor_id: str,
    created_at: str,
    assessment_due_at: str,
) -> PreOutcomePaperCapabilityTaskV1:
    """Freeze exact paper evidence and fixed criteria before every Outcome."""

    points = _bind_capability_points(
        evidence_points,
        policy=policy,
        capability_id=capability_id,
    )
    return PreOutcomePaperCapabilityTaskV1(
        task_id=task_id,
        capability_id=capability_id,
        policy_sha256=policy.policy_sha256,
        subject_agent_id=subject_agent_id,
        assessor_id=assessor_id,
        created_at=created_at,
        assessment_due_at=assessment_due_at,
        criteria=PAPER_CAPABILITY_CRITERIA[capability_id],
        rubric=PAPER_CAPABILITY_RUBRICS[capability_id],
        decision_points=points,
    )


def _verify_span(
    span: PaperEvidenceSpanV1,
    *,
    source_by_key: Mapping[tuple[str, str], bytes],
) -> None:
    raw = source_by_key.get((span.cycle_id, span.source_kind))
    if (
        raw is None
        or hashlib.sha256(raw).hexdigest() != span.source_sha256
        or span.end_byte > len(raw)
    ):
        raise PaperCapabilityEvaluationError(
            "finding span does not bind a task evidence source"
        )
    selected = raw[span.start_byte : span.end_byte]
    try:
        selected.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PaperCapabilityEvaluationError(
            "finding span splits a UTF-8 code point"
        ) from exc
    if hashlib.sha256(selected).hexdigest() != span.selected_utf8_sha256:
        raise PaperCapabilityEvaluationError(
            "finding span digest does not bind exact Agent-owned bytes"
        )


def build_pre_outcome_paper_capability_assessment(
    *,
    assessment_id: str,
    task: PreOutcomePaperCapabilityTaskV1,
    policy: ExperimentPolicyV1,
    evidence_points: Sequence[PaperCapabilityEvidenceInputV1],
    assessed_at: str,
    findings: Sequence[PaperCapabilityFindingV1],
) -> PreOutcomePaperCapabilityAssessmentV1:
    """Build one typed semantic assessment; no Outcome argument is accepted."""

    if not isinstance(task, PreOutcomePaperCapabilityTaskV1):
        raise PaperCapabilityEvaluationError(
            "task must be PreOutcomePaperCapabilityTaskV1"
        )
    bound = _bind_capability_points(
        evidence_points,
        policy=policy,
        capability_id=task.capability_id,
    )
    if (
        task.policy_sha256 != policy.policy_sha256
        or tuple(item.to_dict() for item in bound)
        != tuple(item.to_dict() for item in task.decision_points)
    ):
        raise PaperCapabilityEvaluationError(
            "task does not bind the supplied policy and paper evidence"
        )
    assessed = _time(assessed_at, field="assessed_at")
    if assessed < _time(task.created_at, field="task.created_at") or assessed > _time(
        task.assessment_due_at, field="task.assessment_due_at"
    ):
        raise PaperCapabilityEvaluationError(
            "assessment falls outside the preregistered assessor window"
        )
    exact_findings = tuple(findings)
    if tuple(item.criterion_id for item in exact_findings) != task.criteria:
        raise PaperCapabilityEvaluationError(
            "findings must cover the exact fixed criteria in order"
        )
    source_kinds = (
        ATTENTION_SCHEDULING_EVIDENCE_SOURCE_KINDS
        if task.capability_id == "ATTENTION_SCHEDULING"
        else PAPER_EVIDENCE_SOURCE_KINDS
    )
    source_by_key = {
        (item.snapshot.cycle_id, kind): _source_bytes(item, kind)
        for item in evidence_points
        for kind in source_kinds
    }
    for finding in exact_findings:
        if not isinstance(finding, PaperCapabilityFindingV1):
            raise PaperCapabilityEvaluationError(
                "findings must contain PaperCapabilityFindingV1"
            )
        for span in finding.evidence_spans:
            _verify_span(span, source_by_key=source_by_key)
    if (
        task.capability_id == "POSITION_MANAGEMENT"
        and isinstance(bound[-1], BoundPaperDecisionPointV1)
        and bound[-1].episode_exposure_projection_status
        != "DERIVED_UNAMBIGUOUS"
        and not any(item.status == "UNRESOLVED" for item in exact_findings)
    ):
        raise PaperCapabilityEvaluationError(
            "ambiguous episode exposure projection requires an UNRESOLVED finding"
        )
    if task.capability_id == "POSITION_MANAGEMENT":
        current = bound[-1]
        assert isinstance(current, BoundPaperDecisionPointV1)
        mechanical = current.position_mechanical_evidence
        if mechanical is None:
            raise PaperCapabilityEvaluationError(
                "position assessment lacks exact mechanical evidence"
            )
        no_loss = next(
            item
            for item in exact_findings
            if item.criterion_id == "NO_LOSS_AVERAGING"
        )
        if (
            mechanical.loss_observation_status != "LOSING_FRESH_MARK"
            and no_loss.status != "UNRESOLVED"
        ):
            raise PaperCapabilityEvaluationError(
                "NO_LOSS_AVERAGING must remain UNRESOLVED without an exact fresh losing position"
            )
    cutoff_points = (
        (task.decision_points[-1],)
        if task.capability_id == "POSITION_MANAGEMENT"
        else task.decision_points
    )
    outcome_cutoff = min(
        _time(item.outcome_due_at, field="outcome_due_at")
        for item in cutoff_points
    ).isoformat()
    return PreOutcomePaperCapabilityAssessmentV1(
        assessment_id=assessment_id,
        task_id=task.task_id,
        task_sha256=task.task_sha256,
        capability_id=task.capability_id,
        policy_sha256=policy.policy_sha256,
        subject_agent_id=task.subject_agent_id,
        assessor_id=task.assessor_id,
        assessed_at=assessed_at,
        outcome_cutoff_at=outcome_cutoff,
        blindness_basis=PAPER_BLINDNESS_BASIS,
        decision_point_sha256s=tuple(item.point_sha256 for item in bound),
        findings=exact_findings,
        assessment_vector=paper_capability_vector_for(exact_findings),
        limitations=(
            "SEMANTIC_JUDGMENTS_ARE_ASSESSOR_FINDINGS_NOT_SYSTEM_INFERENCE",
            "QUALITY_ASSESSMENT_IS_NOT_PREDICTIVE_ACCURACY",
            "ONE_EPISODE_IS_NOT_GENERALIZATION",
            "NO_OUTCOME_OR_COSTED_RETURN_WAS_EVALUATED",
            "IDENTITY_SEPARATION_IS_NOT_ORGANIZATIONAL_INDEPENDENCE_PROOF",
            "CONTRACT_DOES_NOT_ISOLATE_ASSESSOR_FROM_EXTERNAL_MARKET_INFORMATION",
        ),
        rubric=PAPER_CAPABILITY_RUBRICS[task.capability_id],
    )


__all__ = [
    "AttentionSchedulingEvidenceInputV1",
    "PaperDecisionEvidenceInputV1",
    "bind_paper_capability_span",
    "build_paper_position_and_open_order_ref",
    "build_pre_outcome_paper_capability_assessment",
    "build_pre_outcome_paper_capability_task",
]
