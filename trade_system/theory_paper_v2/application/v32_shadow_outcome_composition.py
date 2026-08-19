"""Deterministic local tail for one completed V3.2 shadow outcome.

This Application service accepts only already-sealed local documents and their
exact semantic/physical bindings.  It proves that the terminal receipt belongs
to the completed batch, invokes the pure Domain evaluator, and commits the
result through a write-once CAS store.  There is no network, Agent, account,
order, fill, position, PnL, probability, or EV surface.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from ..domain.contracts.canonical import canonical_digest, verify_self_digest
from ..domain.v32_outcome_tick import (
    BATCH_COMPLETION_DIGEST_FIELD,
    BATCH_COMPLETION_SCHEMA_ID,
    OUTCOME_RECEIPT_DIGEST_FIELD,
)
from ..domain.v32_shadow_evaluation import (
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    V32ShadowEvaluationError,
    build_v32_shadow_outcome_evaluation_v1,
)
from .v32_shadow_evaluation_port import (
    CHECKPOINT_DIGEST_FIELD,
    V32ShadowEvaluationPersistenceError,
    V32ShadowEvaluationStorePort,
)


SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_BATCH_COMPLETION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "batch_id",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "completed_at",
        "resolved_schedule_ids",
        "outcome_receipt_digests",
        "network_requests_during_tail",
        "all_due_schedules_terminal",
        "source_scope",
        "external_execution_authority",
        "executable",
        BATCH_COMPLETION_DIGEST_FIELD,
    }
)


class V32ShadowOutcomeCompositionError(ValueError):
    """The deterministic V3.2 shadow-outcome tail failed closed."""


def _time(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ShadowOutcomeCompositionError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ShadowOutcomeCompositionError(code) from exc
    if parsed.tzinfo is None:
        raise V32ShadowOutcomeCompositionError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        raise V32ShadowOutcomeCompositionError(code)
    return value


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _logical_successor_time(value: Any) -> str:
    """Return a stable local-tail time strictly after batch completion.

    This is a logical state-machine timestamp, not a wall-clock or provider
    observation.  Deriving it from the sealed completion makes crash replay
    byte-identical while preserving strict completion-before-evaluation order.
    """

    completed = _moment(value, "V32_SHADOW_OUTCOME_BATCH_COMPLETION_TIME_INVALID")
    return (completed + timedelta(microseconds=1)).isoformat().replace(
        "+00:00", "Z"
    )


def _verify_completed_batch(
    *,
    outcome_batch_completion: Mapping[str, Any],
    outcome_receipt: Mapping[str, Any],
) -> str:
    code = "V32_SHADOW_OUTCOME_BATCH_COMPLETION_INVALID"
    if (
        not isinstance(outcome_batch_completion, Mapping)
        or set(outcome_batch_completion) != _BATCH_COMPLETION_FIELDS
    ):
        raise V32ShadowOutcomeCompositionError(code)
    try:
        digest = verify_self_digest(
            outcome_batch_completion, BATCH_COMPLETION_DIGEST_FIELD
        )
    except (TypeError, ValueError) as exc:
        raise V32ShadowOutcomeCompositionError(code) from exc
    schedule_ids = outcome_batch_completion.get("resolved_schedule_ids")
    receipt_digests = outcome_batch_completion.get("outcome_receipt_digests")
    if (
        outcome_batch_completion.get("schema_id")
        != BATCH_COMPLETION_SCHEMA_ID
        or outcome_batch_completion.get("schema_version") != "1.0.0"
        or not isinstance(schedule_ids, list)
        or not isinstance(receipt_digests, list)
        or schedule_ids != sorted(set(schedule_ids))
        or len(schedule_ids) != len(receipt_digests)
        or len(receipt_digests) != len(set(receipt_digests))
        or outcome_batch_completion.get("network_requests_during_tail") != 0
        or outcome_batch_completion.get("all_due_schedules_terminal") is not True
        or outcome_batch_completion.get("source_scope") != SOURCE_SCOPE
        or outcome_batch_completion.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or outcome_batch_completion.get("executable") is not False
        or outcome_batch_completion.get("run_id") != outcome_receipt.get("run_id")
        or outcome_batch_completion.get("batch_intent_digest")
        != outcome_receipt.get("batch_intent_digest")
        or outcome_batch_completion.get("observation_tick_digest")
        != outcome_receipt.get("observation_tick_digest")
        or outcome_batch_completion.get("raw_evidence_digest")
        != outcome_receipt.get("raw_evidence_digest")
        or outcome_receipt.get("schedule_id") not in schedule_ids
        or outcome_receipt.get(OUTCOME_RECEIPT_DIGEST_FIELD) not in receipt_digests
        or _moment(
            outcome_batch_completion.get("completed_at"), code
        )
        < _moment(outcome_receipt.get("resolved_at"), code)
    ):
        raise V32ShadowOutcomeCompositionError(code)
    return digest


def _evaluation_id(
    *,
    shadow_decision_bundle: Mapping[str, Any],
    outcome_schedule_set: Mapping[str, Any],
    outcome_receipt: Mapping[str, Any],
    outcome_batch_completion: Mapping[str, Any],
) -> str:
    identity = canonical_digest(
        {
            "schema_id": "theory_paper_v32_shadow_outcome_evaluation_identity_v1",
            "run_id": shadow_decision_bundle["run_id"],
            "decision_id": shadow_decision_bundle["decision_id"],
            "cycle_index": shadow_decision_bundle["cycle_index"],
            "horizon": outcome_receipt["horizon"],
            "shadow_decision_bundle_digest": shadow_decision_bundle[
                SHADOW_DECISION_BUNDLE_DIGEST_FIELD
            ],
            "outcome_schedule_set_digest": outcome_receipt[
                "schedule_set_digest"
            ],
            "outcome_schedule_digest": outcome_receipt["schedule_digest"],
            "outcome_receipt_digest": outcome_receipt[
                OUTCOME_RECEIPT_DIGEST_FIELD
            ],
            "outcome_batch_completion_digest": outcome_batch_completion[
                BATCH_COMPLETION_DIGEST_FIELD
            ],
        }
    )
    return f"shadow-outcome-evaluation:{identity}"


def complete_v32_shadow_outcome_tail(
    *,
    store: V32ShadowEvaluationStorePort,
    shadow_decision_bundle: Mapping[str, Any],
    shadow_decision_bundle_binding: Mapping[str, Any],
    outcome_schedule_set: Mapping[str, Any],
    outcome_schedule_set_binding: Mapping[str, Any],
    outcome_receipt: Mapping[str, Any],
    outcome_receipt_binding: Mapping[str, Any],
    outcome_batch_completion: Mapping[str, Any],
    outcome_batch_completion_binding: Mapping[str, Any],
    expected_checkpoint_digest: str | None = None,
) -> Mapping[str, Any]:
    """Persist one deterministic shadow evaluation after batch completion.

    No arm result is accepted from the caller.  Domain reconstruction owns the
    complete result surface, including every UNKNOWN field.
    """

    try:
        run_id = shadow_decision_bundle["run_id"]
        if (
            not isinstance(run_id, str)
            or not run_id
            or run_id != run_id.strip()
        ):
            raise V32ShadowOutcomeCompositionError(
                "V32_SHADOW_OUTCOME_RUN_ID_INVALID"
            )
        with store.evaluation_guard(run_id=run_id):
            store.verify_bound_document(
                document=shadow_decision_bundle,
                binding=shadow_decision_bundle_binding,
            )
            store.verify_bound_document(
                document=outcome_schedule_set,
                binding=outcome_schedule_set_binding,
            )
            store.verify_bound_document(
                document=outcome_receipt,
                binding=outcome_receipt_binding,
            )
            store.verify_bound_document(
                document=outcome_batch_completion,
                binding=outcome_batch_completion_binding,
            )
            _verify_completed_batch(
                outcome_batch_completion=outcome_batch_completion,
                outcome_receipt=outcome_receipt,
            )
            evaluation = build_v32_shadow_outcome_evaluation_v1(
                evaluation_id=_evaluation_id(
                    shadow_decision_bundle=shadow_decision_bundle,
                    outcome_schedule_set=outcome_schedule_set,
                    outcome_receipt=outcome_receipt,
                    outcome_batch_completion=outcome_batch_completion,
                ),
                shadow_decision_bundle=shadow_decision_bundle,
                shadow_decision_bundle_binding=shadow_decision_bundle_binding,
                outcome_schedule_set=outcome_schedule_set,
                outcome_schedule_set_binding=outcome_schedule_set_binding,
                outcome_receipt=outcome_receipt,
                outcome_receipt_binding=outcome_receipt_binding,
                horizon=outcome_receipt["horizon"],
                evaluated_at=_logical_successor_time(
                    outcome_batch_completion["completed_at"]
                ),
            )
            # No mutable shadow state is created until every input and the
            # complete deterministic Domain result have verified.
            checkpoint = store.initialize_checkpoint(
                run_id=run_id, created_at=shadow_decision_bundle["created_at"]
            )
            if (
                expected_checkpoint_digest is not None
                and checkpoint[CHECKPOINT_DIGEST_FIELD]
                != expected_checkpoint_digest
            ):
                # Preserve idempotent same-schedule replay: the store, which can
                # inspect the durable slot, decides whether a stale CAS token is
                # an exact replay or a conflict.
                commit_expected = expected_checkpoint_digest
            else:
                commit_expected = checkpoint[CHECKPOINT_DIGEST_FIELD]
            committed = store.commit_evaluation(
                evaluation=evaluation,
                shadow_decision_bundle=shadow_decision_bundle,
                outcome_schedule_set=outcome_schedule_set,
                outcome_receipt=outcome_receipt,
                outcome_batch_completion=outcome_batch_completion,
                outcome_batch_completion_binding=outcome_batch_completion_binding,
                expected_checkpoint_digest=commit_expected,
            )
    except (
        KeyError,
        TypeError,
        V32ShadowEvaluationError,
        V32ShadowEvaluationPersistenceError,
    ) as exc:
        if isinstance(exc, V32ShadowOutcomeCompositionError):
            raise
        raise V32ShadowOutcomeCompositionError(
            "V32_SHADOW_OUTCOME_TAIL_FAILED_CLOSED"
        ) from exc
    return {
        "status": committed["status"],
        "run_id": run_id,
        "decision_id": evaluation["decision_id"],
        "cycle_index": evaluation["cycle_index"],
        "horizon": evaluation["horizon"],
        "outcome_schedule_id": evaluation["outcome_schedule_id"],
        "evaluation_binding": committed["evaluation_binding"],
        "checkpoint_digest": committed["checkpoint"][CHECKPOINT_DIGEST_FIELD],
        "outcome_resolution_status": evaluation["outcome_resolution_status"],
        "outcome_batch_completed_at": outcome_batch_completion["completed_at"],
        "shadow_evaluated_at": evaluation["evaluated_at"],
        "batch_completion_precedes_local_tail": True,
        "directional_alignment_only": True,
        "path_metrics_evaluated": False,
        "fill_claim": False,
        "position_claim": False,
        "pnl_claim": False,
        "probability_claim": "NONE",
        "expected_value_allowed": False,
        "network_requests": 0,
        "agent_calls": 0,
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
    }


__all__ = [
    "V32ShadowOutcomeCompositionError",
    "complete_v32_shadow_outcome_tail",
]
