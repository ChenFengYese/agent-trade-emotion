"""Read-only, point-in-time paper context for one Agent decision.

The paper ledger and admitted market-data slice remain the fact owners.  This
adapter freezes an exact ledger prefix into the Agent packet and can later
rebuild that prefix even after newer paper events have been appended.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from ...application.market_cycle.attention import (
    AttentionApplicationError,
    AttentionProjection,
    AttentionService,
)
from ...application.market_cycle.data_profiles import (
    AssetDataProfileService,
)
from ...application.market_cycle.paper import replay_paper_account
from ...application.market_cycle.paper_valuation import project_paper_valuation
from ...application.market_cycle.position import (
    PositionPathEvaluationError,
    evaluate_static_no_transition_path,
)
from ...application.market_cycle.read_models import (
    project_orders_and_fills,
    project_paper_cost_effect,
)
from ...domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
    self_digest,
)
from ...domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
    Outcome,
    Review,
)
from ...domain.market_cycle.paper import (
    PaperExecutionIntentV1,
    PaperLedgerRecordV1,
    PaperMarketSliceV1,
    StaticNoTransitionComparatorV1,
)
from ..market_data.paper_evidence import (
    AdmittedAssetSlicePaperMarketEvidence,
    PaperAssetEvidenceBinding,
)
from .attention_repository import (
    DurableAttentionEvent,
    FileAttentionRepository,
)
from .paper_ledger import FilePaperLedger
from .paper_intent_mailbox import paper_action_space_contract
from .repository import FileCycleRepository, MarketCycleRepositoryError


PAPER_DECISION_CONTEXT_SCHEMA_ID = (
    "agent-trade-emotion.v332-paper-decision-context"
)
PAPER_DECISION_CONTEXT_SCHEMA_VERSION = "1.5.0"
PAPER_REVIEW_CONTEXT_SCHEMA_ID = (
    "agent-trade-emotion.v332-paper-review-context"
)
PAPER_REVIEW_CONTEXT_SCHEMA_VERSION = "1.0.0"


class PaperDecisionContextError(ValueError):
    """The requested decision-time paper view is not reproducible."""


def _moment(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise PaperDecisionContextError("PAPER_CONTEXT_TIME_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperDecisionContextError("PAPER_CONTEXT_TIME_INVALID")
    return parsed


def _plain(value: Mapping[str, Any]) -> dict[str, Any]:
    return loads_json_strict(canonical_bytes(value))


class _AttentionPrefixRepository:
    """Read-only event prefix adapter for the public AttentionService reducer."""

    def __init__(self, events: Sequence[DurableAttentionEvent]) -> None:
        self._events = tuple(events)

    def replay(self, logical_agent_id: str) -> tuple[DurableAttentionEvent, ...]:
        if any(item.logical_agent_id != logical_agent_id for item in self._events):
            raise PaperDecisionContextError("PAPER_CONTEXT_ATTENTION_IDENTITY_MISMATCH")
        return self._events

    def load(self, logical_agent_id: str) -> object:
        del logical_agent_id
        raise PaperDecisionContextError("PAPER_CONTEXT_ATTENTION_PREFIX_READ_ONLY")

    def compare_and_swap(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise PaperDecisionContextError("PAPER_CONTEXT_ATTENTION_PREFIX_READ_ONLY")


class PaperDecisionContextProvider:
    """Project and verify one immutable paper-ledger prefix for an Agent."""

    def __init__(
        self,
        *,
        ledger: FilePaperLedger,
        profiles: AssetDataProfileService,
        profile_id: str,
        account_id: str,
        paper_account_policy: Mapping[str, Any],
        experiment_policy_sha256: str,
        attention_repository: FileAttentionRepository,
        attention_service: AttentionService,
        cycle_repository: FileCycleRepository | None = None,
    ) -> None:
        if not isinstance(ledger, FilePaperLedger):
            raise PaperDecisionContextError("PAPER_CONTEXT_LEDGER_INVALID")
        if not isinstance(profiles, AssetDataProfileService):
            raise PaperDecisionContextError("PAPER_CONTEXT_PROFILES_INVALID")
        profile = profiles.require_profile(profile_id)
        policy = _plain(paper_account_policy)
        if (
            not isinstance(account_id, str)
            or not account_id
            or policy.get("account_id") != account_id
            or not isinstance(experiment_policy_sha256, str)
            or len(experiment_policy_sha256) != 64
            or any(character not in "0123456789abcdef" for character in experiment_policy_sha256)
        ):
            raise PaperDecisionContextError("PAPER_CONTEXT_POLICY_INVALID")
        self._ledger = ledger
        self._profiles = profiles
        self._profile_id = profile.profile_id
        self._instrument_id = profile.instrument_id
        self._account_id = account_id
        self._paper_account_policy = policy
        self._experiment_policy_sha256 = experiment_policy_sha256
        if (
            not isinstance(attention_repository, FileAttentionRepository)
            or not isinstance(attention_service, AttentionService)
            or getattr(attention_service, "_repository", None)
            is not attention_repository
        ):
            raise PaperDecisionContextError("PAPER_CONTEXT_ATTENTION_SERVICE_INVALID")
        self._attention_repository = attention_repository
        self._attention_service = attention_service
        if cycle_repository is not None and not isinstance(
            cycle_repository, FileCycleRepository
        ):
            raise PaperDecisionContextError("PAPER_CONTEXT_CYCLE_REPOSITORY_INVALID")
        self._cycle_repository = cycle_repository

    @staticmethod
    def _artifact_ref(state: Any, artifact_type: str) -> ArtifactRef:
        matches = tuple(
            item
            for item in getattr(state, "artifact_refs", ())
            if isinstance(item, ArtifactRef) and item.artifact_type == artifact_type
        )
        if len(matches) != 1:
            raise PaperDecisionContextError(
                "PAPER_CONTEXT_PRIOR_COMPLETE_ARTIFACT_REF_INVALID"
            )
        return matches[0]

    def _latest_prior_decision(
        self,
        snapshot: InputSnapshot,
        intents: Sequence[Mapping[str, Any]],
    ) -> tuple[str, Mapping[str, Any] | None]:
        if self._cycle_repository is None:
            return (
                "NO_PRIOR_INTENT"
                if not intents
                else "UNAVAILABLE_CYCLE_REPOSITORY",
                None,
            )
        exact_intents = tuple(
            PaperExecutionIntentV1.from_dict(item) for item in intents
        )
        try:
            cycle_ids = self._cycle_repository.list_cycle_ids()
        except MarketCycleRepositoryError:
            return "UNAVAILABLE_CYCLE_REPOSITORY", None
        current_decision_at = _moment(snapshot.decision_at)
        current_fact_cutoff = _moment(snapshot.sealed_at)
        pending_intent_cycle_ids = {
            item.decision_cycle_id for item in exact_intents
        }
        pending_review = False
        candidates: list[
            tuple[
                tuple[datetime, datetime, str],
                Any,
                HypothesisRecord,
                BehaviorPlan,
                Outcome,
                Review,
                Mapping[str, Mapping[str, Any]],
                PaperExecutionIntentV1 | None,
            ]
        ] = []
        for cycle_id in cycle_ids:
            if cycle_id == snapshot.cycle_id:
                continue
            try:
                state = self._cycle_repository.load_state(cycle_id)
            except MarketCycleRepositoryError as exc:
                raise PaperDecisionContextError(
                    "PAPER_CONTEXT_PRIOR_CYCLE_STATE_INVALID"
                ) from exc
            if state.stage != "COMPLETE":
                if cycle_id in pending_intent_cycle_ids:
                    pending_review = True
                continue
            try:
                hypothesis = HypothesisRecord.from_dict(
                    self._cycle_repository.load_artifact(
                        cycle_id, "HypothesisRecord"
                    )
                )
                plan = BehaviorPlan.from_dict(
                    self._cycle_repository.load_artifact(cycle_id, "BehaviorPlan")
                )
                outcome = Outcome.from_dict(
                    self._cycle_repository.load_artifact(cycle_id, "Outcome")
                )
                review = Review.from_dict(
                    self._cycle_repository.load_artifact(cycle_id, "Review")
                )
                refs = {
                    artifact_type: self._artifact_ref(
                        state, artifact_type
                    ).to_dict()
                    for artifact_type in (
                        "HypothesisRecord",
                        "BehaviorPlan",
                        "Outcome",
                        "Review",
                    )
                }
            except (MarketCycleRepositoryError, TypeError, ValueError):
                raise PaperDecisionContextError(
                    "PAPER_CONTEXT_PRIOR_COMPLETE_ARTIFACT_MISSING"
                )
            decision_at = _moment(hypothesis.decision_at)
            reviewed_at = _moment(review.reviewed_at)
            if decision_at >= current_decision_at or reviewed_at > current_fact_cutoff:
                continue
            matching_intents = tuple(
                item
                for item in exact_intents
                if item.decision_cycle_id == cycle_id
            )
            if matching_intents and any(
                item.decision_sha256 != hypothesis.agent_decision_sha256
                for item in matching_intents
            ):
                raise PaperDecisionContextError(
                    "PAPER_CONTEXT_PRIOR_DECISION_BINDING_MISMATCH"
                )
            matching_intent = None if not matching_intents else matching_intents[-1]
            if (
                hypothesis.cycle_id != cycle_id
                or plan.cycle_id != cycle_id
                or outcome.cycle_id != cycle_id
                or review.cycle_id != cycle_id
                or plan.agent_decision_sha256
                != hypothesis.agent_decision_sha256
                or review.agent_decision_sha256
                != hypothesis.agent_decision_sha256
                or canonical_digest(hypothesis.to_dict())
                != refs["HypothesisRecord"]["sha256"]
                or canonical_digest(plan.to_dict())
                != refs["BehaviorPlan"]["sha256"]
                or canonical_digest(outcome.to_dict()) != refs["Outcome"]["sha256"]
                or canonical_digest(review.to_dict()) != refs["Review"]["sha256"]
            ):
                raise PaperDecisionContextError(
                    "PAPER_CONTEXT_PRIOR_COMPLETE_ARTIFACT_BINDING_MISMATCH"
                )
            candidates.append(
                (
                    (reviewed_at, decision_at, cycle_id),
                    state,
                    hypothesis,
                    plan,
                    outcome,
                    review,
                    refs,
                    matching_intent,
                )
            )
        if not candidates:
            if pending_review:
                return "PRIOR_OUTCOME_REVIEW_PENDING", None
            if exact_intents:
                return "UNAVAILABLE_PRIOR_DECISION_ARTIFACT", None
            return "NO_PRIOR_INTENT", None
        (
            _,
            state,
            hypothesis,
            _,
            _,
            review,
            refs,
            matching_intent,
        ) = max(candidates, key=lambda item: item[0])
        return (
            "PRIOR_COMPLETE_OBSERVED",
            {
                "decision_cycle_id": hypothesis.cycle_id,
                "decision_sha256": hypothesis.agent_decision_sha256,
                "execution_intent_sha256": (
                    None if matching_intent is None else matching_intent.intent_sha256
                ),
                "cycle_stage": state.stage,
                "authority": "NON_AUTHORITATIVE_CONTINUITY_CONTEXT",
                "retrieval_policy": "LATEST_COMPLETE_INCLUDED_BOUNDED",
                "artifact_refs": refs,
                "agent_decision_body": {
                    "included_in_context": True,
                    "verbatim_text": hypothesis.agent_decision_text,
                    "size_bytes": hypothesis.agent_decision_size_bytes,
                    "sha256": hypothesis.agent_decision_sha256,
                    "artifact_ref": refs["HypothesisRecord"],
                    "source_json_pointer": "/agent_decision_text",
                },
                "agent_review_body": {
                    "included_in_context": True,
                    "verbatim_text": review.agent_review_text,
                    "size_bytes": review.agent_review_size_bytes,
                    "sha256": review.agent_review_sha256,
                    "artifact_ref": refs["Review"],
                    "source_json_pointer": "/agent_review_text",
                },
            },
        )

    def _attention_prefix_available_at(
        self, cutoff_at: str
    ) -> tuple[DurableAttentionEvent, ...]:
        cutoff = _moment(cutoff_at)
        events = self._attention_repository.replay(
            str(self._paper_account_policy["logical_agent_id"])
        )
        prefix: list[DurableAttentionEvent] = []
        after_cutoff = False
        for event in events:
            available = _moment(event.occurred_at)
            if available <= cutoff:
                if after_cutoff:
                    raise PaperDecisionContextError(
                        "PAPER_CONTEXT_ATTENTION_TIME_ORDER_INVALID"
                    )
                prefix.append(event)
            else:
                after_cutoff = True
        return tuple(prefix)

    def _attention_projection(
        self, events: Sequence[DurableAttentionEvent]
    ) -> AttentionProjection:
        logical_agent_id = str(
            self._paper_account_policy["logical_agent_id"]
        )
        try:
            current = self._attention_service.status(logical_agent_id)
            if current.revision == len(events):
                return current
            return AttentionService(_AttentionPrefixRepository(events)).status(
                logical_agent_id
            )
        except AttentionApplicationError as exc:
            raise PaperDecisionContextError(
                "PAPER_CONTEXT_ATTENTION_PROJECTION_INVALID"
            ) from exc

    def _latest_attention_request(
        self,
        events: Sequence[DurableAttentionEvent],
        *,
        behavior_plan_binding: str | None = None,
        data_cursor: str | None = None,
        same_cycle: bool = False,
    ) -> Mapping[str, Any]:
        projection = self._attention_projection(events)
        source_refs: dict[str, Any] = {
            "stream_revision": len(events),
            "stream_head_event_sha256": (
                None if not events else events[-1].event_sha256
            ),
        }
        request_ids = tuple(
            request_id
            for request_id, request in projection.requests.items()
            if (
                not same_cycle
                or (
                    request.hypothesis_or_episode_ref == behavior_plan_binding
                    and request.data_cursor == data_cursor
                )
            )
        )
        if not request_ids:
            return {
                "status": (
                    "NO_ATTENTION_REQUEST"
                    if not same_cycle
                    else "NO_SAME_CYCLE_ATTENTION_REQUEST"
                ),
                "source_refs": source_refs,
                "active_request_id": projection.active_request_id,
                "request_status": None,
                "accepted_at": None,
                "request_sha256": None,
                "request": None,
            }
        request_id = request_ids[-1]
        request = projection.requests[request_id]
        source_refs["attention_request_sha256"] = request.agent_owned_sha256
        return {
            "status": "EXACT_AGENT_ATTENTION_REQUEST",
            "source_refs": source_refs,
            "active_request_id": projection.active_request_id,
            "request_status": projection.request_statuses[request_id],
            "accepted_at": projection.request_accepted_ats[request_id],
            "request_sha256": request.agent_owned_sha256,
            "request": request.to_dict(),
        }

    def _review_behavior_plan_binding(self, cycle_id: str) -> str | None:
        if self._cycle_repository is None:
            return None
        try:
            outcome = Outcome.from_dict(
                self._cycle_repository.load_artifact(cycle_id, "Outcome")
            )
            plan_ref = outcome.behavior_plan_ref
        except (MarketCycleRepositoryError, TypeError, ValueError):
            return None
        return f"{plan_ref.artifact_id}:{plan_ref.sha256}"

    @staticmethod
    def _agent_facing_prior_intents(
        *,
        account: object,
        intents: Sequence[dict[str, Any]],
        orders_and_fills: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        has_exposure = any(
            position.quantity != "0" for position in account.positions
        )
        has_active_orders = bool(
            orders_and_fills["open_orders"] or orders_and_fills["unresolved"]
        )
        return list(intents) if has_exposure or has_active_orders else []

    @staticmethod
    def _terminal_non_execution_suffix(
        intents: Sequence[PaperExecutionIntentV1],
    ) -> Mapping[str, Any]:
        allowed = frozenset({"WAIT", "HOLD", "WATCH"})
        suffix: list[PaperExecutionIntentV1] = []
        if intents:
            episode_id = intents[-1].episode_id
            for intent in reversed(intents):
                if intent.episode_id != episode_id or intent.action not in allowed:
                    break
                suffix.append(intent)
            suffix.reverse()
        return {
            "status": "EXACT" if intents else "NO_PRIOR_INTENT",
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

    @staticmethod
    def _episode_transition_tail(
        intents: Sequence[PaperExecutionIntentV1],
    ) -> list[Mapping[str, Any]]:
        if not intents:
            return []
        episode_id = intents[-1].episode_id
        tail: list[PaperExecutionIntentV1] = []
        for intent in reversed(intents):
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
                "target_state": _plain(item.target_state),
            }
            for item in tail
        ]

    @staticmethod
    def _mechanical_state(account: Any, orders_and_fills: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if account is None or orders_and_fills is None:
            return {
                "status": "UNKNOWN_ACCOUNT_NOT_OPENED",
                "source_refs": {},
                "account_version": None,
                "position_count": None,
                "account_signed_quantity": None,
                "open_order_count": None,
                "order_history_count": None,
                "fill_count": None,
                "unresolved_order_count": None,
                "order_state_counts": {},
            }
        positions = tuple(
            item for item in account.positions if item.symbol == account.permitted_symbol
        )
        signed_quantity = (
            "0"
            if not positions
            else positions[0].quantity
            if len(positions) == 1
            else None
        )
        state_counts: dict[str, int] = {}
        for order in account.orders:
            state_counts[order.state] = state_counts.get(order.state, 0) + 1
        return {
            "status": (
                "EXACT_MECHANICAL_FACTS"
                if signed_quantity is not None
                else "AMBIGUOUS_MULTIPLE_POSITIONS"
            ),
            "source_refs": {
                "account_sha256": canonical_digest(account.to_dict()),
                "orders_and_fills_sha256": canonical_digest(orders_and_fills),
            },
            "account_version": account.version,
            "position_count": len(positions),
            "account_signed_quantity": signed_quantity,
            "open_order_count": len(orders_and_fills["open_orders"]),
            "order_history_count": len(orders_and_fills["order_history"]),
            "fill_count": len(orders_and_fills["fills"]),
            "unresolved_order_count": len(orders_and_fills["unresolved"]),
            "order_state_counts": {
                key: state_counts[key] for key in sorted(state_counts)
            },
        }

    @classmethod
    def _continuity_projection(
        cls,
        *,
        account: Any,
        ledger_head: Mapping[str, Any],
        intents: Sequence[Mapping[str, Any]],
        orders_and_fills: Mapping[str, Any] | None,
        latest_prior_decision: Mapping[str, Any] | None,
        latest_attention_request: Mapping[str, Any],
        snapshot_ref: ArtifactRef,
    ) -> Mapping[str, Any]:
        exact_intents = tuple(PaperExecutionIntentV1.from_dict(item) for item in intents)
        latest = None if not exact_intents else exact_intents[-1]
        attention_sources = latest_attention_request["source_refs"]
        text_sources: dict[str, Any] = {}
        if latest_prior_decision is not None:
            text_sources = {
                "agent_decision_body": {
                    "sha256": latest_prior_decision["agent_decision_body"]["sha256"],
                    "artifact_ref": latest_prior_decision["agent_decision_body"][
                        "artifact_ref"
                    ],
                },
                "agent_review_body": {
                    "sha256": latest_prior_decision["agent_review_body"]["sha256"],
                    "artifact_ref": latest_prior_decision["agent_review_body"][
                        "artifact_ref"
                    ],
                },
            }
        return {
            "schema_id": "agent-trade-emotion.v332-continuity-projection",
            "projection_version": "1.0.0",
            "authority": "NON_AUTHORITATIVE_READ_ONLY_FACT_PROJECTION",
            "source_refs": {
                "execution_intent_sha256s": [
                    item.intent_sha256 for item in exact_intents
                ],
                "ledger_head_record_sha256": ledger_head["record_sha256"],
                "snapshot_ref": snapshot_ref.to_dict(),
                "attention_stream_revision": attention_sources["stream_revision"],
                "attention_stream_head_event_sha256": attention_sources[
                    "stream_head_event_sha256"
                ],
                "prior_agent_texts": text_sources,
            },
            "terminal_non_execution_suffix": cls._terminal_non_execution_suffix(
                exact_intents
            ),
            "episode_transition_tail": cls._episode_transition_tail(exact_intents),
            "latest_attention_request": latest_attention_request,
            "mechanical_state": cls._mechanical_state(account, orders_and_fills),
            "subjective_assessments": {
                "trigger_capture": {
                    "status": "UNRESOLVED_AGENT_JUDGMENT",
                    "prior_agent_declaration": None if latest is None else latest.activation,
                    "source_refs": (
                        {}
                        if latest is None
                        else {
                            "intent_sha256": latest.intent_sha256,
                            "source_json_pointer": "/activation",
                        }
                    ),
                },
                "geometry_deterioration": {
                    "status": "UNRESOLVED_AGENT_JUDGMENT",
                    "prior_evidence_delta": None if latest is None else latest.evidence_delta,
                    "prior_hard_invalidation": (
                        None if latest is None else latest.hard_invalidation
                    ),
                    "source_refs": (
                        {}
                        if latest is None
                        else {
                            "intent_sha256": latest.intent_sha256,
                            "source_json_pointers": [
                                "/evidence_delta",
                                "/hard_invalidation",
                            ],
                            "current_snapshot_ref": snapshot_ref.to_dict(),
                        }
                    ),
                },
                "opportunity_cost": {
                    "status": "UNRESOLVED_AGENT_JUDGMENT",
                    "source_refs": text_sources,
                },
            },
        }

    @staticmethod
    def _episode_exposure_projection(
        *,
        account: Any,
        ledger_head: Mapping[str, Any],
        intents: Sequence[Mapping[str, Any]],
        orders_and_fills: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not intents:
            return {
                "status": "NO_PRIOR_INTENT",
                "derivation": "READ_ONLY_FACT_PROJECTION_NOT_AGENT_DECISION",
                "source_refs": {},
                "episode_id": None,
                "latest_transition_id": None,
                "role": None,
                "intended_target_signed_quantity": None,
                "account_signed_quantity": None,
                "open_order_count": None,
                "target_reconciliation": "UNKNOWN",
                "ambiguity_reason": "NO_PRIOR_INTENT",
            }
        latest = PaperExecutionIntentV1.from_dict(intents[-1])
        positions = tuple(
            item for item in account.positions if item.symbol == latest.symbol
        )
        if len(positions) > 1:
            return {
                "status": "AMBIGUOUS",
                "derivation": "READ_ONLY_FACT_PROJECTION_NOT_AGENT_DECISION",
                "source_refs": {
                    "execution_intent_sha256": latest.intent_sha256,
                    "ledger_head_record_sha256": ledger_head["record_sha256"],
                },
                "episode_id": latest.episode_id,
                "latest_transition_id": latest.transition_id,
                "role": latest.role,
                "intended_target_signed_quantity": latest.target_state[
                    "signed_quantity"
                ],
                "account_signed_quantity": None,
                "open_order_count": None,
                "target_reconciliation": "UNKNOWN",
                "ambiguity_reason": "MULTIPLE_POSITIONS_FOR_SYMBOL",
            }
        actual = "0" if not positions else positions[0].quantity
        target = str(latest.target_state["signed_quantity"])
        return {
            "status": "DERIVED_UNAMBIGUOUS",
            "derivation": "READ_ONLY_FACT_PROJECTION_NOT_AGENT_DECISION",
            "source_refs": {
                "execution_intent_sha256": latest.intent_sha256,
                "ledger_head_record_sha256": ledger_head["record_sha256"],
            },
            "episode_id": latest.episode_id,
            "latest_transition_id": latest.transition_id,
            "role": latest.role,
            "intended_target_signed_quantity": target,
            "account_signed_quantity": actual,
            "open_order_count": len(orders_and_fills["open_orders"]),
            "target_reconciliation": (
                "MATCHES_INTENT_TARGET" if actual == target else "EXECUTION_DIFFERS"
            ),
            "ambiguity_reason": None,
        }

    def _data_slice(self, snapshot: InputSnapshot):
        if snapshot.instrument_id != self._instrument_id:
            raise PaperDecisionContextError("PAPER_CONTEXT_INSTRUMENT_MISMATCH")
        replay = self._profiles.replay(
            self._profile_id,
            cycle_id=snapshot.cycle_id,
            cutoff_at=snapshot.source_cutoff_at,
        )
        data_slice = replay.data_slice
        if replay.status != "ADMITTED" or data_slice is None:
            raise PaperDecisionContextError("PAPER_CONTEXT_DATA_NOT_ADMITTED")
        document = data_slice.to_dict()
        expected_unknowns = tuple(
            f"{item['component_id']}:{item['missing_reason']}"
            for item in document["typed_unknowns"]
        )
        if (
            data_slice.instrument_identity.venue_symbol != snapshot.instrument_id
            or data_slice.cutoff_at != snapshot.source_cutoff_at
            or data_slice.sealed_at != snapshot.decision_at
            or _moment(data_slice.sealed_at) > _moment(snapshot.sealed_at)
            or canonical_bytes(document["core_observations"])
            != canonical_bytes(snapshot.core_observations)
            or canonical_bytes(document["optional_observations"])
            != canonical_bytes(snapshot.optional_observations)
            or tuple(data_slice.raw_refs) != tuple(snapshot.raw_refs)
            or canonical_bytes(document["source_health"])
            != canonical_bytes(snapshot.source_health)
            or expected_unknowns != tuple(snapshot.unknowns)
        ):
            raise PaperDecisionContextError("PAPER_CONTEXT_SNAPSHOT_MISMATCH")
        return data_slice

    @staticmethod
    def _prefix_available_at(
        records: Sequence[PaperLedgerRecordV1], cutoff_at: str
    ) -> tuple[PaperLedgerRecordV1, ...]:
        cutoff = _moment(cutoff_at)
        prefix: list[PaperLedgerRecordV1] = []
        stopped = False
        for record in records:
            if _moment(record.occurred_at) <= cutoff:
                if stopped:
                    raise PaperDecisionContextError(
                        "PAPER_CONTEXT_LEDGER_TIME_NOT_MONOTONIC"
                    )
                prefix.append(record)
            else:
                stopped = True
        return tuple(prefix)

    @staticmethod
    def _recorded_market_slices(
        records: Sequence[PaperLedgerRecordV1],
    ) -> tuple[PaperMarketSliceV1, ...]:
        slices: list[PaperMarketSliceV1] = []
        for record in records:
            if record.event_type != "MARKET_OBSERVED":
                continue
            payload = record.payload.get("market")
            if not isinstance(payload, Mapping):
                raise PaperDecisionContextError(
                    "PAPER_CONTEXT_MARKET_FACT_INCOMPLETE"
                )
            slices.append(PaperMarketSliceV1(**dict(payload)))
        return tuple(slices)

    def _static_no_transition_evaluation(
        self,
        *,
        cycle_id: str,
        records: Sequence[PaperLedgerRecordV1],
        review_cutoff_at: str,
    ) -> Mapping[str, Any]:
        comparators: list[
            tuple[PaperLedgerRecordV1, StaticNoTransitionComparatorV1]
        ] = []
        try:
            for record in records:
                if record.event_type != "STATIC_NO_TRANSITION_PREREGISTERED":
                    continue
                comparator_value = record.payload.get("comparator")
                if not isinstance(comparator_value, Mapping):
                    raise PaperDecisionContextError(
                        "PAPER_REVIEW_STATIC_COMPARATOR_INVALID"
                    )
                comparator = StaticNoTransitionComparatorV1.from_dict(
                    comparator_value
                )
                intent = PaperExecutionIntentV1.from_dict(
                    comparator.execution_intent
                )
                if intent.decision_cycle_id == cycle_id:
                    comparators.append((record, comparator))
        except (TypeError, ValueError) as exc:
            raise PaperDecisionContextError(
                "PAPER_REVIEW_STATIC_COMPARATOR_INVALID"
            ) from exc
        comparator_sources = [
            {
                "ledger_revision": record.revision,
                "ledger_record_sha256": record.record_sha256,
                "comparator_id": comparator.comparator_id,
                "comparator_sha256": comparator.comparator_sha256,
            }
            for record, comparator in comparators
        ]
        if not comparators:
            return {
                "status": "NOT_EVALUATED",
                "reason": "NO_SAME_CYCLE_STATIC_NO_TRANSITION_COMPARATOR",
                "source_refs": {
                    "comparator_records": [],
                    "outcome_sha256": None,
                    "path_sha256": None,
                },
                "results": [],
            }
        if self._cycle_repository is None:
            return {
                "status": "CENSORED",
                "reason": "SEALED_OUTCOME_PATH_UNAVAILABLE",
                "source_refs": {
                    "comparator_records": comparator_sources,
                    "outcome_sha256": None,
                    "path_sha256": None,
                },
                "results": [],
            }
        try:
            outcome = Outcome.from_dict(
                self._cycle_repository.load_artifact(cycle_id, "Outcome")
            )
        except (MarketCycleRepositoryError, TypeError, ValueError) as exc:
            return {
                "status": "CENSORED",
                "reason": "SEALED_OUTCOME_PATH_UNAVAILABLE",
                "source_refs": {
                    "comparator_records": comparator_sources,
                    "outcome_sha256": None,
                    "path_sha256": None,
                },
                "results": [],
            }
        if (
            outcome.cycle_id != cycle_id
            or _moment(outcome.sealed_at) > _moment(review_cutoff_at)
        ):
            raise PaperDecisionContextError(
                "PAPER_REVIEW_OUTCOME_BINDING_INVALID"
            )
        path = loads_json_strict(canonical_bytes(outcome.path_observations))
        try:
            results = [
                evaluate_static_no_transition_path(comparator, path).to_dict()
                for _, comparator in comparators
            ]
        except PositionPathEvaluationError as exc:
            raise PaperDecisionContextError(
                "PAPER_REVIEW_STATIC_PATH_INVALID"
            ) from exc
        statuses = {str(item["status"]) for item in results}
        return {
            "status": (
                "CENSORED"
                if statuses == {"CENSORED"}
                else next(iter(statuses))
                if len(statuses) == 1
                else "MIXED_OBSERVED_AND_CENSORED"
            ),
            "reason": (
                "OUTCOME_PATH_CENSORED"
                if statuses == {"CENSORED"}
                else None
            ),
            "source_refs": {
                "comparator_records": comparator_sources,
                "outcome_sha256": canonical_digest(outcome.to_dict()),
                "path_sha256": canonical_digest(path),
            },
            "results": results,
        }

    def _build(
        self,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        records: Sequence[PaperLedgerRecordV1],
        attention_events: Sequence[DurableAttentionEvent],
        *,
        fact_cutoff_at: str,
    ) -> dict[str, Any]:
        if (
            not isinstance(snapshot, InputSnapshot)
            or not isinstance(snapshot_ref, ArtifactRef)
            or snapshot_ref.artifact_type != "InputSnapshot"
            or snapshot_ref.artifact_id != snapshot.snapshot_id
        ):
            raise PaperDecisionContextError("PAPER_CONTEXT_SNAPSHOT_REF_INVALID")
        fact_cutoff = _moment(fact_cutoff_at)
        snapshot_cutoff = _moment(snapshot.sealed_at)
        if fact_cutoff < snapshot_cutoff:
            raise PaperDecisionContextError("PAPER_CONTEXT_FACT_CUTOFF_INVALID")
        data_slice = self._data_slice(snapshot)
        prefix = tuple(records)
        if prefix and (
            prefix[0].revision != 1
            or prefix[-1].revision != len(prefix)
            or _moment(prefix[-1].occurred_at) > fact_cutoff
        ):
            raise PaperDecisionContextError("PAPER_CONTEXT_LEDGER_PREFIX_INVALID")
        if any(_moment(item.occurred_at) > fact_cutoff for item in attention_events):
            raise PaperDecisionContextError(
                "PAPER_CONTEXT_ATTENTION_PREFIX_INVALID"
            )
        head = {
            "revision": len(prefix),
            "record_sha256": None if not prefix else prefix[-1].record_sha256,
        }
        latest_attention_request = self._latest_attention_request(attention_events)
        base: dict[str, Any] = {
            "schema_id": PAPER_DECISION_CONTEXT_SCHEMA_ID,
            "schema_version": PAPER_DECISION_CONTEXT_SCHEMA_VERSION,
            "status": "ACCOUNT_NOT_OPENED" if not prefix else "OBSERVED",
            "cycle_id": snapshot.cycle_id,
            "snapshot_ref": snapshot_ref.to_dict(),
            "snapshot_sealed_at": snapshot.sealed_at,
            "paper_fact_cutoff_at": fact_cutoff_at,
            "experiment_policy_sha256": self._experiment_policy_sha256,
            "paper_account_policy": self._paper_account_policy,
            "ledger_head": head,
            "data_evidence": {
                "profile_id": self._profile_id,
                "data_cursor": data_slice.data_cursor,
                "market_fact_basis": "DECISION_INPUT_SNAPSHOT",
                "market_fact_cutoff_at": snapshot.sealed_at,
                "slice_sha256": canonical_digest(data_slice.to_dict()),
                "slice_sealed_at": data_slice.sealed_at,
                "raw_refs": [item.to_dict() for item in data_slice.raw_refs],
            },
            "account": None,
            "orders_and_fills": None,
            "valuation": None,
            "cost_effect": None,
            "prior_execution_intents": [],
            "latest_transition": None,
            "prior_decision_status": "NO_PRIOR_INTENT",
            "latest_prior_decision": None,
            "episode_exposure_projection": {
                "status": "NO_PRIOR_INTENT",
                "derivation": "READ_ONLY_FACT_PROJECTION_NOT_AGENT_DECISION",
                "source_refs": {},
                "episode_id": None,
                "latest_transition_id": None,
                "role": None,
                "intended_target_signed_quantity": None,
                "account_signed_quantity": None,
                "open_order_count": None,
                "target_reconciliation": "UNKNOWN",
                "ambiguity_reason": "NO_PRIOR_INTENT",
            },
            "continuity_projection": self._continuity_projection(
                account=None,
                ledger_head=head,
                intents=(),
                orders_and_fills=None,
                latest_prior_decision=None,
                latest_attention_request=latest_attention_request,
                snapshot_ref=snapshot_ref,
            ),
            "paper_action_space": None,
        }
        if prefix:
            account = replay_paper_account(prefix)
            current_evidence = AdmittedAssetSlicePaperMarketEvidence(
                profiles=self._profiles,
                bindings=(
                    PaperAssetEvidenceBinding(
                        symbol=snapshot.instrument_id,
                        profile_id=self._profile_id,
                        cycle_ids=(snapshot.cycle_id,),
                    ),
                ),
            )
            setup_evidence = AdmittedAssetSlicePaperMarketEvidence(
                profiles=self._profiles,
                bindings=(
                    PaperAssetEvidenceBinding(
                        symbol=snapshot.instrument_id,
                        profile_id=self._profile_id,
                        cycle_ids=(
                            str(self._paper_account_policy["setup_cycle_id"]),
                        ),
                    ),
                ),
            )
            expected_spec = setup_evidence.latest_instrument_spec(
                snapshot.instrument_id,
                "LINEAR_PERP",
                available_by=snapshot.sealed_at,
            )
            if (
                account.account_id != self._account_id
                or account.permitted_symbol != snapshot.instrument_id
                or account.owner_logical_agent_id
                != self._paper_account_policy["logical_agent_id"]
                or account.owner_agent_generation
                != self._paper_account_policy["agent_generation"]
                or account.account_mode != self._paper_account_policy["account_mode"]
                or account.base_currency != self._paper_account_policy["base_currency"]
                or account.max_leverage != self._paper_account_policy["max_leverage"]
                or account.initial_balance
                != self._paper_account_policy["initial_balance"]
                or expected_spec is None
                or not setup_evidence.verifies_instrument_spec(
                    account.instrument_spec,
                    available_by=snapshot.sealed_at,
                )
            ):
                raise PaperDecisionContextError(
                    "PAPER_CONTEXT_ACCOUNT_POLICY_MISMATCH"
                )
            histories = tuple(
                replay_paper_account(prefix[:revision])
                for revision in range(1, len(prefix) + 1)
            )
            all_intents: list[dict[str, Any]] = []
            for record in prefix:
                if record.event_type not in {
                    "INTENT_RECORDED",
                    "COMMAND_ACCEPTED",
                }:
                    continue
                intent_document = record.payload.get("execution_intent")
                if not isinstance(intent_document, Mapping):
                    raise PaperDecisionContextError(
                        "PAPER_CONTEXT_COMMAND_WITHOUT_EXECUTION_INTENT"
                    )
                intent = PaperExecutionIntentV1.from_dict(intent_document)
                if (
                    intent.account_id != account.account_id
                    or intent.logical_agent_id != account.owner_logical_agent_id
                    or intent.symbol != account.permitted_symbol
                ):
                    raise PaperDecisionContextError(
                        "PAPER_CONTEXT_EXECUTION_INTENT_IDENTITY_MISMATCH"
                    )
                all_intents.append(intent.to_dict())
            current_marks = tuple(
                item
                for item in current_evidence.derive_slices(snapshot.instrument_id)
                if item.granularity == "MARK"
            )
            if len(current_marks) != 1:
                raise PaperDecisionContextError(
                    "PAPER_CONTEXT_CURRENT_MARK_AMBIGUOUS"
                )
            decision_market_prefix = self._prefix_available_at(
                prefix, snapshot.sealed_at
            )
            valuation = project_paper_valuation(
                account,
                self._recorded_market_slices(decision_market_prefix)
                + current_marks,
                account_history=histories,
            )
            valuation_document = valuation.to_dict()
            valuation_document["mark_basis"] = {
                "status": "DECISION_SNAPSHOT_MARK_ONLY",
                "snapshot_ref": snapshot_ref.to_dict(),
                "market_fact_cutoff_at": snapshot.sealed_at,
                "data_slice_sha256": canonical_digest(data_slice.to_dict()),
            }
            prior_decision_status, latest_prior_decision = (
                self._latest_prior_decision(snapshot, all_intents)
            )
            orders_and_fills = project_orders_and_fills(account, prefix).to_dict()
            # While exposure or an order is live, preserve the complete
            # Agent-authored transition history needed to manage it.  Once
            # mechanically flat, remove terminal order parameters and prose
            # from the next packet instead of replaying a trading template.
            prior_intents = self._agent_facing_prior_intents(
                account=account,
                intents=all_intents,
                orders_and_fills=orders_and_fills,
            )
            base.update(
                {
                    "account": account.to_dict(),
                    "orders_and_fills": orders_and_fills,
                    "valuation": valuation_document,
                    "cost_effect": project_paper_cost_effect(
                        account, prefix
                    ).to_dict(),
                    "prior_execution_intents": prior_intents,
                    "latest_transition": (
                        None if not prior_intents else prior_intents[-1]
                    ),
                    "prior_decision_status": prior_decision_status,
                    "latest_prior_decision": latest_prior_decision,
                    "episode_exposure_projection": (
                        self._episode_exposure_projection(
                            account=account,
                            ledger_head=head,
                            intents=prior_intents,
                            orders_and_fills=orders_and_fills,
                        )
                    ),
                    "continuity_projection": self._continuity_projection(
                        account=account,
                        ledger_head=head,
                        intents=prior_intents,
                        orders_and_fills=orders_and_fills,
                        latest_prior_decision=latest_prior_decision,
                        latest_attention_request=latest_attention_request,
                        snapshot_ref=snapshot_ref,
                    ),
                }
            )
        base["paper_action_space"] = paper_action_space_contract(
            base, symbol=snapshot.instrument_id
        )
        return self_digest(base, "paper_context_sha256")

    def context(
        self, snapshot: InputSnapshot, snapshot_ref: ArtifactRef
    ) -> Mapping[str, Any]:
        records = self._ledger.load_records(self._account_id)
        prefix = self._prefix_available_at(records, snapshot.sealed_at)
        attention_prefix = self._attention_prefix_available_at(snapshot.sealed_at)
        return self._build(
            snapshot,
            snapshot_ref,
            prefix,
            attention_prefix,
            fact_cutoff_at=snapshot.sealed_at,
        )

    def review_context(
        self,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        *,
        review_cutoff_at: str,
    ) -> Mapping[str, Any]:
        """Freeze same-cycle paper and attention facts for Agent Review."""

        if _moment(review_cutoff_at) < _moment(snapshot.sealed_at):
            raise PaperDecisionContextError("PAPER_REVIEW_CONTEXT_CUTOFF_INVALID")
        records = self._prefix_available_at(
            self._ledger.load_records(self._account_id), review_cutoff_at
        )
        attention_events = self._attention_prefix_available_at(review_cutoff_at)
        decision_context = self._build(
            snapshot,
            snapshot_ref,
            records,
            attention_events,
            fact_cutoff_at=review_cutoff_at,
        )
        same_cycle_intents: list[dict[str, Any]] = []
        for record in records:
            if record.event_type not in {"INTENT_RECORDED", "COMMAND_ACCEPTED"}:
                continue
            value = record.payload.get("execution_intent")
            if not isinstance(value, Mapping):
                continue
            intent = PaperExecutionIntentV1.from_dict(value)
            if intent.decision_cycle_id == snapshot.cycle_id:
                same_cycle_intents.append(intent.to_dict())
        behavior_plan_binding = self._review_behavior_plan_binding(
            snapshot.cycle_id
        )
        latest_attention = self._latest_attention_request(
            attention_events,
            behavior_plan_binding=behavior_plan_binding,
            data_cursor=decision_context["data_evidence"]["data_cursor"],
            same_cycle=True,
        )
        document = {
            "schema_id": PAPER_REVIEW_CONTEXT_SCHEMA_ID,
            "schema_version": PAPER_REVIEW_CONTEXT_SCHEMA_VERSION,
            "authority": "READ_ONLY_PAPER_FACTS_NOT_ACTUAL_EXECUTION",
            "cycle_id": snapshot.cycle_id,
            "review_cutoff_at": review_cutoff_at,
            "paper_fact_cutoff_at": decision_context["paper_fact_cutoff_at"],
            "snapshot_ref": snapshot_ref.to_dict(),
            "data_evidence": decision_context["data_evidence"],
            "ledger_head": decision_context["ledger_head"],
            "same_cycle_execution_intents": same_cycle_intents,
            "same_cycle_attention": latest_attention,
            "account": decision_context["account"],
            "orders_and_fills": decision_context["orders_and_fills"],
            "valuation": decision_context["valuation"],
            "cost_effect": decision_context["cost_effect"],
            "static_no_transition_evaluation": (
                self._static_no_transition_evaluation(
                    cycle_id=snapshot.cycle_id,
                    records=records,
                    review_cutoff_at=review_cutoff_at,
                )
            ),
            "limitations": [
                "LOCAL_PAPER_MODELED_NOT_ACTUAL_EXECUTION",
                "SUBJECTIVE_TRIGGER_AND_OPPORTUNITY_COST_REMAIN_AGENT_JUDGMENT",
            ],
        }
        return self_digest(document, "paper_review_context_sha256")

    def verifies_review_context(
        self,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        context: Mapping[str, Any],
        *,
        review_cutoff_at: str,
    ) -> bool:
        try:
            expected = self.review_context(
                snapshot,
                snapshot_ref,
                review_cutoff_at=review_cutoff_at,
            )
            return canonical_bytes(expected) == canonical_bytes(context)
        except (KeyError, TypeError, ValueError):
            return False

    def verifies_context(
        self,
        snapshot: InputSnapshot,
        snapshot_ref: ArtifactRef,
        context: Mapping[str, Any],
    ) -> bool:
        try:
            if (
                not isinstance(context, Mapping)
                or context.get("schema_id") != PAPER_DECISION_CONTEXT_SCHEMA_ID
                or context.get("schema_version")
                != PAPER_DECISION_CONTEXT_SCHEMA_VERSION
                or context.get("paper_context_sha256")
                != canonical_digest(
                    {
                        key: context[key]
                        for key in context
                        if key != "paper_context_sha256"
                    }
                )
            ):
                return False
            head = context.get("ledger_head")
            if not isinstance(head, Mapping):
                return False
            revision = head.get("revision")
            if type(revision) is not int or revision < 0:
                return False
            all_records = self._ledger.load_records(self._account_id)
            if revision > len(all_records):
                return False
            prefix = all_records[:revision]
            if (
                (not prefix and head.get("record_sha256") is not None)
                or (
                    prefix
                    and head.get("record_sha256") != prefix[-1].record_sha256
                )
            ):
                return False
            projection = context.get("continuity_projection")
            projection_sources = (
                projection.get("source_refs")
                if isinstance(projection, Mapping)
                else None
            )
            attention_revision = (
                projection_sources.get("attention_stream_revision")
                if isinstance(projection_sources, Mapping)
                else None
            )
            if type(attention_revision) is not int or attention_revision < 0:
                return False
            all_attention_events = self._attention_repository.replay(
                str(self._paper_account_policy["logical_agent_id"])
            )
            if attention_revision > len(all_attention_events):
                return False
            attention_prefix = all_attention_events[:attention_revision]
            cutoff = _moment(snapshot.sealed_at)
            if any(_moment(item.occurred_at) > cutoff for item in attention_prefix):
                return False
            if (
                attention_revision < len(all_attention_events)
                and _moment(all_attention_events[attention_revision].occurred_at) <= cutoff
            ):
                return False
            if projection_sources.get(
                "attention_stream_head_event_sha256"
            ) != (
                None if not attention_prefix else attention_prefix[-1].event_sha256
            ):
                return False
            expected = self._build(
                snapshot,
                snapshot_ref,
                prefix,
                attention_prefix,
                fact_cutoff_at=snapshot.sealed_at,
            )
            return canonical_bytes(expected) == canonical_bytes(context)
        except (KeyError, TypeError, ValueError):
            return False


__all__ = [
    "PAPER_DECISION_CONTEXT_SCHEMA_ID",
    "PAPER_DECISION_CONTEXT_SCHEMA_VERSION",
    "PAPER_REVIEW_CONTEXT_SCHEMA_ID",
    "PAPER_REVIEW_CONTEXT_SCHEMA_VERSION",
    "PaperDecisionContextError",
    "PaperDecisionContextProvider",
]
