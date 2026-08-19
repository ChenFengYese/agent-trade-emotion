"""Application use case for a fresh four-cycle synthetic chronology."""

from __future__ import annotations

from typing import Any, Mapping

from ..domain.contracts.canonical import self_digest, verify_self_digest
from ..domain.dynamic_research import (
    EXPECTATION_OPERATIONS,
    HYPOTHESIS_OPERATIONS,
    build_market_information_snapshot,
    build_sentiment_state,
    reduce_expectation_ledger,
    reduce_hypothesis_registry,
)
from ..domain.epistemic_inference import build_public_inference_trace
from ..domain.window_reliability import (
    WindowReliabilityError,
    build_agent_input_plan,
    build_bounded_prior_state_view,
    build_current_cycle_grounding_receipt,
    build_preaccept_validation_receipt,
    build_resume_capsule,
    classify_reliability_failure,
    validate_agent_delivery,
)
from ..domain.research_integrity import (
    ACTION_CLASSES,
    build_action_evaluation_set,
    make_agent_invocation_receipt,
    reduce_path_beliefs,
    select_from_evaluation_set,
)
from .continuous_cycle import (
    ContinuousResearchCycleCoordinator,
    build_source_bound_four_cycle_review,
)
from .ports import (
    ContinuousArtifactPort,
    ContinuousCheckpointPort,
    ContinuousCycleStoreFactoryPort,
    FixtureComparatorPort,
    FixtureMarketCollectorPort,
    FixtureStrategyAgentPort,
    FourCycleReviewSourcePort,
)


class ContinuousFixtureError(ValueError):
    pass


_ACTORS = {
    "RESUME_CAPSULE_SEALED": "DETERMINISTIC_WINDOW_RECOVERY_GATE",
    "CYCLE_DUE": "DETERMINISTIC_SCHEDULER",
    "COLLECTION_STARTED": "DATA_ACQUISITION_COORDINATOR",
    "COLLECTION_ATTEMPTS_SEALED": "DATA_ACQUISITION_COORDINATOR",
    "COLLECTION_SEALED": "DATA_ACQUISITION_COORDINATOR",
    "PIT_ADMITTED": "PIT_ADMISSION_GATE",
    "MARKET_INFORMATION_SEALED": "DETERMINISTIC_MARKET_INFORMATION_BUILDER",
    "REPLAY_SEALED": "DETERMINISTIC_STATE_REDUCER",
    "PRE_DECISION_STATE_SEALED": "DETERMINISTIC_STATE_REDUCER",
    "AGENT_CONTEXT_SEALED": "AGENT_CONTEXT_BUILDER",
    "AGENT_INPUT_PLAN_SEALED": "DETERMINISTIC_CONTEXT_BUDGET_GATE",
    "AGENT_PROPOSAL_ATTEMPT_SEALED": "PLATFORM_INVOCATION_ADAPTER",
    "AGENT_PROPOSAL_SEALED": "SINGLE_STRATEGY_AGENT",
    "SENTIMENT_STATE_SEALED": "DETERMINISTIC_SENTIMENT_REDUCER",
    "HYPOTHESIS_DELTA_SEALED": "SINGLE_STRATEGY_AGENT",
    "HYPOTHESIS_REGISTRY_SEALED": "DETERMINISTIC_HYPOTHESIS_REDUCER",
    "EXPECTATION_DELTA_SEALED": "SINGLE_STRATEGY_AGENT",
    "EXPECTATION_LEDGER_SEALED": "DETERMINISTIC_EXPECTATION_REDUCER",
    "PUBLIC_INFERENCE_TRACE_SEALED": "DETERMINISTIC_EPISTEMIC_CONTRACT",
    "BELIEF_UPDATE_SEALED": "DETERMINISTIC_BELIEF_REDUCER",
    "ACTION_EVALUATION_SEALED": "DETERMINISTIC_ACTION_EVALUATOR",
    "DELIBERATION_SEALED": "SINGLE_STRATEGY_AGENT",
    "ACTION_SELECTION_SEALED": "SINGLE_STRATEGY_AGENT",
    "RISK_DECISION_SEALED": "DETERMINISTIC_RISK_KERNEL",
    "DECISION_SEALED": "DETERMINISTIC_DECISION_BUILDER",
    "CURRENT_CYCLE_GROUNDING_SEALED": "DETERMINISTIC_CURRENT_CYCLE_GROUNDER",
    "PREACCEPT_VALIDATION_SEALED": "DETERMINISTIC_PREACCEPT_GATE",
    "STATE_ACCEPTED": "DETERMINISTIC_STATE_REDUCER",
    "ACTION_RECEIPT_SEALED": "DETERMINISTIC_ACTION_RECEIPT_BUILDER",
    "COMPARATOR_SEALED": "DETERMINISTIC_COMPARATOR",
    "REVIEW_SOURCE_SEALED": "DETERMINISTIC_REVIEW_SOURCE_BUILDER",
    "REPORT_SEALED": "DETERMINISTIC_REPORT_BUILDER",
    "REVIEW_SEALED": "DETERMINISTIC_REVIEW",
}


def _position_truth() -> dict[str, Any]:
    return {
        "intended_side": "LONG",
        "mark_price": "100",
        "contract_multiplier": "1",
        "reentry_contract_active": False,
        "account": {
            "equity_usdt": "10000",
            "margin_used_usdt": "250",
            "margin_available_usdt": "9750",
            "max_gross_leverage": "2",
        },
        "lots": [
            {
                "lot_id": "lot:SYNTHUSDT:core",
                "symbol": "SYNTHUSDT",
                "side": "LONG",
                "role": "CORE",
                "quantity": "1",
                "entry_price": "100",
                "mark_price": "100",
                "stop_price": "90",
                "contract_multiplier": "1",
                "margin_used_usdt": "50",
            },
            {
                "lot_id": "lot:BALLASTUSDT:core",
                "symbol": "BALLASTUSDT",
                "side": "LONG",
                "role": "CORE",
                "quantity": "400",
                "entry_price": "1",
                "mark_price": "1",
                "stop_price": "0.9",
                "contract_multiplier": "1",
                "margin_used_usdt": "200",
            },
        ],
        "pending_orders": [],
    }


def _risk_policy() -> dict[str, str]:
    return {
        "fee_rate": "0.0005",
        "slippage_rate": "0.001",
        "initial_margin_rate": "0.5",
        "max_gross_leverage": "2",
        "portfolio_risk_cap_usdt": "300",
        "symbol_risk_cap_usdt": "100",
        "gross_notional_cap_usdt": "2000",
        "symbol_notional_cap_usdt": "1000",
    }


def _legal_action_contract() -> dict[str, Any]:
    return {
        "action_classes": sorted(ACTION_CLASSES),
        "required_reduction_sizing_ids": [
            "REDUCE_25",
            "REDUCE_50",
            "REDUCE_75",
            "EXIT_100",
        ],
        "candidate_generation_owner": "SINGLE_STRATEGY_AGENT",
        "financial_evaluation_owner": "DETERMINISTIC_ACTION_EVALUATOR",
        "selection_stage": "ONLY_AFTER_SEALED_EVALUATION_SET",
        "wait_requires_reason_opportunity_cost_and_next_review": True,
    }


def _research_capability_contract() -> dict[str, Any]:
    return {
        "semantic_hypothesis_space": "OPEN_CANDIDATE_AND_WATCH_REGISTRY",
        "semantic_family_whitelist": None,
        "registry_total_history_limit": None,
        "active_attention_budget": 5,
        "operational_window": {
            "lead_count": 1,
            "runner_up_count": 1,
            "residual_other_or_unknown_required": True,
        },
        "hypothesis_operations": sorted(HYPOTHESIS_OPERATIONS),
        "expectation_operations": sorted(EXPECTATION_OPERATIONS),
        "agent_owns": [
            "MECHANISM_DISCOVERY",
            "HYPOTHESIS_AND_EXPECTATION_PROPOSAL",
            "MULTITIMEFRAME_INTERPRETATION",
            "PUBLIC_EVIDENCE_LINKED_INFERENCE",
            "FEASIBLE_SET_SELECTION",
        ],
        "deterministic_kernel_owns": [
            "POINT_IN_TIME_ADMISSION",
            "SOURCE_AND_NUMERIC_VALIDATION",
            "PORTFOLIO_FINANCIAL_CALCULATION",
            "RISK_AND_PERMISSION",
            "STATE_REDUCTION_EVENT_ORDER_AND_COMMIT",
        ],
        "private_chain_of_thought_requested": False,
        "public_structured_justification_required": True,
        "uncalibrated_probability_forbidden": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
    }


def _binding_from_receipt(
    receipt: Mapping[str, Any], artifact_name: str
) -> dict[str, str]:
    return {
        "relative_ref": str(receipt["artifact_refs"][artifact_name]),
        "semantic_digest": str(receipt["artifact_bindings"][artifact_name]),
        "physical_sha256": str(receipt["artifact_sha256s"][artifact_name]),
    }


def _load_previous_cycle_state(
    *,
    run_id: str,
    completed_cycle: int,
    artifacts: ContinuousArtifactPort,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    dict[str, Mapping[str, str]],
    Mapping[str, Any],
]:
    receipt_ref = f"evidence-receipts/cycle-{completed_cycle:04d}.json"
    receipt = artifacts.read_document(
        relative_ref=receipt_ref,
        digest_field="cycle_evidence_receipt_digest",
    )
    names_and_fields = {
        "hypothesis_registry": (
            "hypothesis_registry_digest",
            "hypothesis_registry_digest",
        ),
        "expectation_ledger": (
            "expectation_ledger_digest",
            "expectation_ledger_digest",
        ),
        "belief_state": ("belief_state_digest", "belief_state_digest"),
        "accepted_state": ("accepted_state_digest", "accepted_state_digest"),
    }
    documents: dict[str, Mapping[str, Any]] = {}
    prior_refs: dict[str, Mapping[str, str]] = {}
    for name, (artifact_name, digest_field) in names_and_fields.items():
        binding = _binding_from_receipt(receipt, artifact_name)
        documents[name] = artifacts.read_document(
            relative_ref=binding["relative_ref"],
            digest_field=digest_field,
            expected_semantic_digest=binding["semantic_digest"],
        )
        prior_refs[name] = binding
    completion_ref = f"completion-receipts/cycle-{completed_cycle:04d}.json"
    completion = artifacts.read_document(
        relative_ref=completion_ref,
        digest_field="completion_receipt_digest",
    )
    prior_refs["cycle_evidence_receipt"] = artifacts.artifact_binding(
        relative_ref=receipt_ref,
        digest_field="cycle_evidence_receipt_digest",
    )
    prior_refs["completion_receipt"] = artifacts.artifact_binding(
        relative_ref=completion_ref,
        digest_field="completion_receipt_digest",
    )
    if completion.get("run_id") != run_id or completion.get("cycle_index") != completed_cycle:
        raise ContinuousFixtureError("FIXTURE_RESUME_COMPLETION_IDENTITY_INVALID")
    return (
        documents["hypothesis_registry"],
        documents["expectation_ledger"],
        documents["belief_state"],
        documents["accepted_state"],
        prior_refs,
        receipt,
    )


def _build_and_store_resume_capsule(
    *,
    run_id: str,
    created_at: str,
    manifest_ref: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    checkpoints: ContinuousCheckpointPort,
    artifacts: ContinuousArtifactPort,
    prior_state_refs: Mapping[str, Mapping[str, Any]],
    current_cycle_stage_refs: Mapping[str, Mapping[str, Any]] | None = None,
    relative_ref: str | None = None,
) -> tuple[dict[str, Any], Mapping[str, str]]:
    accepted_ref = (
        None
        if checkpoint.get("accepted_state_path") is None
        else artifacts.artifact_binding(
            relative_ref=str(checkpoint["accepted_state_path"]),
            digest_field="accepted_state_digest",
            expected_semantic_digest=str(checkpoint["accepted_state_digest"]),
        )
    )
    completion_ref = (
        None
        if checkpoint.get("last_completion_receipt_digest") is None
        else artifacts.artifact_binding(
            relative_ref=(
                f"completion-receipts/cycle-{checkpoint['completed_cycles']:04d}.json"
            ),
            digest_field="completion_receipt_digest",
            expected_semantic_digest=str(
                checkpoint["last_completion_receipt_digest"]
            ),
        )
    )
    pending_accepted_ref = (
        None
        if checkpoint.get("pending_accepted_state_path") is None
        else artifacts.artifact_binding(
            relative_ref=str(checkpoint["pending_accepted_state_path"]),
            digest_field="accepted_state_digest",
            expected_semantic_digest=str(
                checkpoint["pending_accepted_state_digest"]
            ),
        )
    )
    allowed = {
        str(manifest_ref["relative_ref"]),
        "checkpoint.json",
        *(str(row["relative_ref"]) for row in prior_state_refs.values()),
        *(
            str(row["relative_ref"])
            for row in (current_cycle_stage_refs or {}).values()
        ),
    }
    if accepted_ref is not None:
        allowed.add(str(accepted_ref["relative_ref"]))
    if completion_ref is not None:
        allowed.add(str(completion_ref["relative_ref"]))
    if pending_accepted_ref is not None:
        allowed.add(str(pending_accepted_ref["relative_ref"]))
    next_cycle = int(checkpoint["next_cycle_index"])
    allowed.update(
        {
            f"process-events/cycle-{next_cycle:04d}/",
            f"artifacts/cycle-{next_cycle:04d}/",
            f"raw/cycle-{next_cycle:04d}/",
            f"deliveries/cycle-{next_cycle:04d}/",
            f"transport/cycle-{next_cycle:04d}/",
            f"failures/cycle-{next_cycle:04d}/",
            f"states/state-{next_cycle:04d}.json",
            f"evidence-receipts/cycle-{next_cycle:04d}.json",
            f"completion-receipts/cycle-{next_cycle:04d}.json",
            f"reports/cycle-{next_cycle:04d}.json",
        }
    )
    capsule = build_resume_capsule(
        run_id=run_id,
        created_at=created_at,
        manifest_ref=manifest_ref,
        checkpoint=checkpoint,
        checkpoint_ref=checkpoints.binding(run_id=run_id),
        accepted_state_ref=accepted_ref,
        completion_receipt_ref=completion_ref,
        prior_state_refs=prior_state_refs,
        current_cycle_stage_refs=current_cycle_stage_refs,
        pending_accepted_state_ref=pending_accepted_ref,
        allowed_read_refs=sorted(allowed),
        forbidden_read_prefixes=[
            "outcomes/",
            "future/",
            "accounts/",
            "orders/",
            "credentials/",
        ],
        authority_status="LOCAL_SYNTHETIC_NO_EXTERNAL_AUTHORITY",
    )
    binding = artifacts.write_document(
        relative_ref=(
            relative_ref
            or f"resume/to-cycle-{int(checkpoint['next_cycle_index']):04d}.json"
        ),
        document=capsule,
        digest_field="resume_capsule_digest",
    )
    return capsule, binding


def _current_cycle_stage_refs(
    store: Any,
) -> dict[str, Mapping[str, str]]:
    """Project the verified event chain into capsule-bindable artifact refs."""

    return {
        str(event["event_type"]): {
            "relative_ref": str(event["payload_ref"]),
            "semantic_digest": str(event["payload_digest"]),
            "physical_sha256": str(event["payload_sha256"]),
        }
        for event in store.read_events()
    }


def run_four_cycle_synthetic_fixture(
    *,
    run_id: str,
    artifacts: ContinuousArtifactPort,
    checkpoints: ContinuousCheckpointPort,
    cycle_stores: ContinuousCycleStoreFactoryPort,
    collector: FixtureMarketCollectorPort,
    strategy_agent: FixtureStrategyAgentPort,
    comparator: FixtureComparatorPort,
    review_sources: FourCycleReviewSourcePort,
    resume_existing: bool = False,
    through_cycle: int = 4,
    max_agent_input_bytes: int = 196_608,
    max_agent_output_bytes: int = 196_608,
) -> dict[str, Any]:
    """Exercise the real continuous core with no external data or model calls."""

    if (
        not run_id
        or isinstance(through_cycle, bool)
        or not isinstance(through_cycle, int)
        or not 1 <= through_cycle <= 4
    ):
        raise ContinuousFixtureError("FIXTURE_RUN_ID_INVALID")
    if resume_existing:
        manifest = artifacts.read_document(
            relative_ref="manifest.json", digest_field="manifest_digest"
        )
        if manifest.get("run_id") != run_id:
            raise ContinuousFixtureError("FIXTURE_RESUME_MANIFEST_MISMATCH")
        manifest_binding = artifacts.artifact_binding(
            relative_ref="manifest.json", digest_field="manifest_digest"
        )
        checkpoint = checkpoints.load(run_id=run_id)
    else:
        manifest_binding = artifacts.write_document(
            relative_ref="manifest.json",
            document={
            "schema_id": "continuous_synthetic_fixture_manifest",
            "schema_version": "1.1.0",
            "run_id": run_id,
            "cycle_count": 4,
            "collector_id": "SYNTHETIC_TEN_CATEGORY_COLLECTOR_V1",
            "agent_adapter_id": "SYNTHETIC_OPEN_HYPOTHESIS_AGENT_V1",
            "comparator_id": "SYNTHETIC_SOURCE_BOUND_COMPARATOR_V1",
            "registered_implementations_only": True,
            "cross_window_resume_authority": "DIGEST_BOUND_RESUME_CAPSULE_ONLY",
            "agent_input_delivery": "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE",
            "implicit_truncation_allowed": False,
            "network_access": False,
            "model_invocation": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
            },
            digest_field="manifest_digest",
        )
        checkpoint = checkpoints.initialize(run_id=run_id)
    completed_cycles = int(checkpoint["completed_cycles"])
    if through_cycle < completed_cycles:
        raise ContinuousFixtureError("FIXTURE_THROUGH_CYCLE_BEHIND_CHECKPOINT")
    previous_registry: Mapping[str, Any] | None
    previous_ledger: Mapping[str, Any] | None
    previous_beliefs: Mapping[str, Any] | None
    previous_accepted_state: Mapping[str, Any] | None
    prior_state_refs: dict[str, Mapping[str, str]]
    if completed_cycles == 0:
        previous_registry = None
        previous_ledger = None
        previous_beliefs = None
        previous_accepted_state = None
        prior_state_refs = {}
    else:
        (
            previous_registry,
            previous_ledger,
            previous_beliefs,
            previous_accepted_state,
            prior_state_refs,
            _,
        ) = _load_previous_cycle_state(
            run_id=run_id,
            completed_cycle=completed_cycles,
            artifacts=artifacts,
        )
    boundary_capsule_ref = (
        f"resume/to-cycle-{int(checkpoint['next_cycle_index']):04d}.json"
    )
    if resume_existing:
        checkpoint_status = str(checkpoint.get("status") or "")
        boundary_statuses = {
            "READY_FOR_CYCLE",
            "RUNNING_OUTCOMES_SEALED",
            "AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED",
        }
        recovery_statuses = {
            "PRE_ACCEPT_RECOVERABLE_FAILURE",
            "PRE_ACCEPT_FAILED_CLOSED",
            "POST_ACCEPT_FINALIZATION",
            "POST_ACCEPT_RECOVERABLE_FAILURE",
            "POST_ACCEPT_FAILED_CLOSED",
        }
        if checkpoint_status in boundary_statuses:
            authority_capsule_ref = boundary_capsule_ref
            live_stage_refs: Mapping[str, Mapping[str, str]] = {}
        elif checkpoint_status in recovery_statuses:
            authority_capsule_ref = (
                f"resume/recovery-cycle-{int(checkpoint['next_cycle_index']):04d}-"
                f"{checkpoint['checkpoint_digest']}.json"
            )
            current_store = cycle_stores.open_cycle(
                run_id=run_id,
                cycle_index=int(checkpoint["next_cycle_index"]),
            )
            live_stage_refs = _current_cycle_stage_refs(current_store)
            if checkpoint.get("last_failure_ref") is not None:
                live_stage_refs = {
                    **live_stage_refs,
                    "LAST_RELIABILITY_FAILURE": artifacts.artifact_binding(
                        relative_ref=str(checkpoint["last_failure_ref"]),
                        digest_field="reliability_failure_digest",
                        expected_semantic_digest=str(
                            checkpoint["last_failure_digest"]
                        ),
                    ),
                }
        else:
            raise ContinuousFixtureError("FIXTURE_CHECKPOINT_STATUS_UNSUPPORTED")
        authority_capsule = artifacts.read_document(
            relative_ref=authority_capsule_ref,
            digest_field="resume_capsule_digest",
        )
        capsule_stage_refs = authority_capsule.get("current_cycle_stage_refs")
        if not isinstance(capsule_stage_refs, Mapping) or any(
            name not in live_stage_refs or live_stage_refs[name] != binding
            for name, binding in capsule_stage_refs.items()
        ):
            raise ContinuousFixtureError("FIXTURE_RESUME_STAGE_BINDING_MISMATCH")
        expected_capsule, _ = _build_and_store_resume_capsule(
            run_id=run_id,
            created_at=str(authority_capsule["created_at"]),
            manifest_ref=manifest_binding,
            checkpoint=checkpoint,
            checkpoints=checkpoints,
            artifacts=artifacts,
            prior_state_refs=prior_state_refs,
            current_cycle_stage_refs=capsule_stage_refs,
            relative_ref=authority_capsule_ref,
        )
        if expected_capsule != authority_capsule:
            raise ContinuousFixtureError("FIXTURE_RESUME_CAPSULE_MISMATCH")
        if authority_capsule.get("resume_allowed") is not True:
            raise ContinuousFixtureError("FIXTURE_FAILURE_CLOSED_NO_RESUME")
        current_store = cycle_stores.open_cycle(
            run_id=run_id,
            cycle_index=int(checkpoint["next_cycle_index"]),
        )
        existing_events = current_store.read_events()
        if existing_events:
            if existing_events[0]["event_type"] != "RESUME_CAPSULE_SEALED":
                raise ContinuousFixtureError("FIXTURE_CYCLE_ORIGIN_CAPSULE_MISSING")
            resume_capsule = artifacts.read_document(
                relative_ref=str(existing_events[0]["payload_ref"]),
                digest_field="resume_capsule_digest",
                expected_semantic_digest=str(existing_events[0]["payload_digest"]),
            )
        else:
            resume_capsule = authority_capsule
    else:
        resume_capsule, _ = _build_and_store_resume_capsule(
            run_id=run_id,
            created_at="2026-08-06T00:00:00Z",
            manifest_ref=manifest_binding,
            checkpoint=checkpoint,
            checkpoints=checkpoints,
            artifacts=artifacts,
            prior_state_refs=prior_state_refs,
        )
    cycle_summaries: list[dict[str, Any]] = []
    review_digest: str | None = None
    for prior_cycle in range(1, completed_cycles + 1):
        prior_receipt = artifacts.read_document(
            relative_ref=f"evidence-receipts/cycle-{prior_cycle:04d}.json",
            digest_field="cycle_evidence_receipt_digest",
        )
        prior_completion = artifacts.read_document(
            relative_ref=f"completion-receipts/cycle-{prior_cycle:04d}.json",
            digest_field="completion_receipt_digest",
        )
        prior_inference = artifacts.read_document(
            relative_ref=str(
                prior_receipt["artifact_refs"]["public_inference_trace_digest"]
            ),
            digest_field="public_inference_trace_digest",
            expected_semantic_digest=str(
                prior_receipt["artifact_bindings"][
                    "public_inference_trace_digest"
                ]
            ),
        )
        prior_plan = artifacts.read_document(
            relative_ref=str(
                prior_receipt["artifact_refs"]["agent_input_plan_digest"]
            ),
            digest_field="agent_input_plan_digest",
            expected_semantic_digest=str(
                prior_receipt["artifact_bindings"]["agent_input_plan_digest"]
            ),
        )
        cycle_summaries.append(
            {
                "cycle_index": prior_cycle,
                "market_information_snapshot_digest": prior_receipt[
                    "artifact_bindings"
                ]["market_information_snapshot_digest"],
                "sentiment_state_digest": prior_receipt["artifact_bindings"][
                    "sentiment_state_digest"
                ],
                "hypothesis_registry_digest": prior_receipt["artifact_bindings"][
                    "hypothesis_registry_digest"
                ],
                "expectation_ledger_digest": prior_receipt["artifact_bindings"][
                    "expectation_ledger_digest"
                ],
                "public_inference_trace_digest": prior_receipt["artifact_bindings"][
                    "public_inference_trace_digest"
                ],
                "public_inference_claim_count": len(prior_inference["claims"]),
                "public_inference_evidence_balance": dict(
                    prior_inference["evidence_balance"]
                ),
                "cycle_evidence_receipt_digest": prior_receipt[
                    "cycle_evidence_receipt_digest"
                ],
                "completion_receipt_digest": prior_completion[
                    "completion_receipt_digest"
                ],
                "resume_capsule_digest": prior_receipt["artifact_bindings"][
                    "resume_capsule_digest"
                ],
                "agent_input_plan_digest": prior_plan["agent_input_plan_digest"],
                "agent_input_canonical_bytes": prior_plan[
                    "context_canonical_byte_length"
                ],
                "current_cycle_grounding_digest": prior_receipt[
                    "artifact_bindings"
                ]["current_cycle_grounding_digest"],
                "preaccept_validation_receipt_digest": prior_receipt[
                    "artifact_bindings"
                ]["preaccept_validation_receipt_digest"],
                "unknown_market_category_count": None,
            }
        )
    if completed_cycles >= 4:
        review = artifacts.read_document(
            relative_ref="reviews/through-cycle-0004.json",
            digest_field="review_digest",
        )
        review_digest = str(review["review_digest"])

    for cycle_index in range(completed_cycles + 1, through_cycle + 1):
        decision_at = f"2026-08-06T0{cycle_index}:00:00Z"
        checkpoints.open_cycle(run_id=run_id, cycle_index=cycle_index)
        store = cycle_stores.open_cycle(run_id=run_id, cycle_index=cycle_index)
        coordinator = ContinuousResearchCycleCoordinator(
            store, run_id=run_id, cycle_index=cycle_index
        )
        evidence_bindings: dict[str, str] = {}
        artifact_refs: dict[str, str] = {}

        def record_reliability_failure(
            *, phase: str, reason_code: str, accepted_state_exists: bool = False
        ) -> Mapping[str, Any]:
            failure = classify_reliability_failure(
                run_id=run_id,
                cycle_index=cycle_index,
                phase=phase,
                reason_code=reason_code,
                accepted_state_exists=accepted_state_exists,
            )
            current_checkpoint = checkpoints.load(run_id=run_id)
            failure_number = int(current_checkpoint.get("failure_count", 0)) + 1
            binding = artifacts.write_document(
                relative_ref=(
                    f"failures/cycle-{cycle_index:04d}/"
                    f"failure-{failure_number:04d}.json"
                ),
                document=failure,
                digest_field="reliability_failure_digest",
            )
            failed_checkpoint = checkpoints.record_failure(
                run_id=run_id,
                cycle_index=cycle_index,
                failure_ref=str(binding["relative_ref"]),
                failure_digest=str(binding["semantic_digest"]),
                resume_allowed=bool(failure["resume_allowed"]),
                accepted_state_exists=accepted_state_exists,
            )
            failure_stage_refs = {
                **_current_cycle_stage_refs(store),
                "LAST_RELIABILITY_FAILURE": binding,
            }
            _build_and_store_resume_capsule(
                run_id=run_id,
                created_at=decision_at,
                manifest_ref=manifest_binding,
                checkpoint=failed_checkpoint,
                checkpoints=checkpoints,
                artifacts=artifacts,
                prior_state_refs=prior_state_refs,
                current_cycle_stage_refs=failure_stage_refs,
                relative_ref=(
                    f"resume/recovery-cycle-{cycle_index:04d}-"
                    f"{failed_checkpoint['checkpoint_digest']}.json"
                ),
            )
            return failure

        def stage(
            event_type: str,
            document: Mapping[str, Any],
            digest_field: str,
            *,
            binding_name: str | None = None,
            relative_ref: str | None = None,
            use_physical_digest: bool = False,
        ) -> Mapping[str, str]:
            ref = relative_ref or f"artifacts/cycle-{cycle_index:04d}/{event_type}.json"
            binding = artifacts.write_document(
                relative_ref=ref,
                document=document,
                digest_field=digest_field,
            )
            event_digest = (
                binding["physical_sha256"]
                if use_physical_digest
                else binding["semantic_digest"]
            )
            existing = {
                row["event_type"]: row for row in store.read_events()
            }.get(event_type)
            if existing is None:
                coordinator.record_stage(
                    event_type=event_type,
                    payload_ref=binding["relative_ref"],
                    payload_digest=event_digest,
                    actor=_ACTORS[event_type],
                    recorded_at=decision_at,
                    evidence_boundary=f"SYNTHETIC_CYCLE_{cycle_index}_POINT_IN_TIME",
                )
            elif (
                existing["payload_ref"] != binding["relative_ref"]
                or existing["payload_digest"] != event_digest
                or existing["actor"] != _ACTORS[event_type]
            ):
                raise ContinuousFixtureError(
                    f"FIXTURE_RESUME_STAGE_CONFLICT:{event_type}"
                )
            if binding_name:
                evidence_bindings[binding_name] = event_digest
                artifact_refs[binding_name] = binding["relative_ref"]
            return binding

        def load_staged_document(
            event_type: str, digest_field: str
        ) -> Mapping[str, Any]:
            events = {
                event["event_type"]: event for event in store.read_events()
            }
            event = events.get(event_type)
            if event is None:
                raise ContinuousFixtureError(
                    f"FIXTURE_SEALED_STAGE_MISSING:{event_type}"
                )
            return artifacts.read_document(
                relative_ref=str(event["payload_ref"]),
                digest_field=digest_field,
                expected_semantic_digest=str(event["payload_digest"]),
            )

        def verify_transport_delivery(
            delivery: Mapping[str, Any],
        ) -> None:
            try:
                record = artifacts.read_document(
                    relative_ref=str(delivery["transport_record_ref"]),
                    digest_field="transport_delivery_record_digest",
                    expected_semantic_digest=str(
                        delivery["transport_record_digest"]
                    ),
                )
                binding = artifacts.artifact_binding(
                    relative_ref=str(delivery["transport_record_ref"]),
                    digest_field="transport_delivery_record_digest",
                    expected_semantic_digest=str(
                        delivery["transport_record_digest"]
                    ),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise WindowReliabilityError(
                    "AGENT_DELIVERY_TRANSPORT_RECORD_INVALID"
                ) from exc
            delivery_core = {
                key: value
                for key, value in delivery.items()
                if key
                not in {
                    "transport_record_ref",
                    "transport_record_digest",
                    "transport_record_sha256",
                    "durable_before_adapter_return",
                }
            }
            if (
                binding["physical_sha256"]
                != delivery.get("transport_record_sha256")
                or record.get("delivery") != delivery_core
                or record.get("durable_before_adapter_return") is not True
            ):
                raise WindowReliabilityError(
                    "AGENT_DELIVERY_TRANSPORT_RECORD_MISMATCH"
                )

        def verify_transport_receipt(
            receipt: Mapping[str, Any],
        ) -> None:
            try:
                record = artifacts.read_document(
                    relative_ref=str(receipt["transport_record_ref"]),
                    digest_field="transport_delivery_record_digest",
                    expected_semantic_digest=str(
                        receipt["transport_record_digest"]
                    ),
                )
                binding = artifacts.artifact_binding(
                    relative_ref=str(receipt["transport_record_ref"]),
                    digest_field="transport_delivery_record_digest",
                    expected_semantic_digest=str(
                        receipt["transport_record_digest"]
                    ),
                )
                delivery = record["delivery"]
            except (KeyError, TypeError, ValueError) as exc:
                raise WindowReliabilityError(
                    "AGENT_DELIVERY_TRANSPORT_RECEIPT_INVALID"
                ) from exc
            if (
                not isinstance(delivery, Mapping)
                or binding["physical_sha256"]
                != receipt.get("transport_record_sha256")
                or delivery.get("run_id") != receipt.get("run_id")
                or delivery.get("cycle_index") != receipt.get("cycle_index")
                or delivery.get("input_digest") != receipt.get("input_digest")
                or delivery.get("expected_schema_id")
                != receipt.get("expected_schema_id")
                or delivery.get("payload_digest") != receipt.get("payload_digest")
                or delivery.get("payload_canonical_bytes")
                != receipt.get("payload_canonical_bytes")
                or delivery.get("adapter_receipt_id")
                != receipt.get("adapter_receipt_id")
                or receipt.get("durable_before_adapter_return") is not True
            ):
                raise WindowReliabilityError(
                    "AGENT_DELIVERY_TRANSPORT_RECEIPT_MISMATCH"
                )

        stage(
            "RESUME_CAPSULE_SEALED",
            resume_capsule,
            "resume_capsule_digest",
            binding_name="resume_capsule_digest",
            relative_ref=(
                f"resume/to-cycle-{cycle_index:04d}.json"
            ),
        )
        stage(
            "CYCLE_DUE",
            {
                "schema_id": "synthetic_cycle_due",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "due_at": decision_at,
            },
            "cycle_due_digest",
        )
        stage(
            "COLLECTION_STARTED",
            {
                "schema_id": "synthetic_collection_started",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "started_at": decision_at,
            },
            "collection_started_digest",
        )
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if "MARKET_INFORMATION_SEALED" in sealed_event_types:
            collection_attempts = load_staged_document(
                "COLLECTION_ATTEMPTS_SEALED", "collection_attempts_digest"
            )
            market_context = load_staged_document(
                "COLLECTION_SEALED", "market_context_digest"
            )
            pit_admission = load_staged_document(
                "PIT_ADMITTED", "pit_admission_digest"
            )
            market_snapshot = load_staged_document(
                "MARKET_INFORMATION_SEALED",
                "market_information_snapshot_digest",
            )
            collection = {
                "facts": market_snapshot["facts"],
                "attempt_count": collection_attempts["attempt_count"],
                "observed_count": collection_attempts["observed_count"],
                "unknown_count": collection_attempts["unknown_count"],
                "derived_feature_count": sum(
                    row["kind"] == "DERIVED_FEATURE"
                    for row in market_snapshot["facts"]
                ),
                "collector_id": market_context["collector_id"],
            }
        else:
            collection = collector.collect(
                run_id=run_id, cycle_index=cycle_index, as_of=decision_at
            )
            collection_attempts = {
                "schema_id": "synthetic_collection_attempts",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "attempt_count": collection["attempt_count"],
                "observed_count": collection["observed_count"],
                "unknown_count": collection["unknown_count"],
            }
            market_context = {
                "schema_id": "synthetic_market_context",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "as_of": decision_at,
                "collector_id": collection["collector_id"],
                "fact_ids": [row["fact_id"] for row in collection["facts"]],
                "observed_count": collection["observed_count"],
                "unknown_count": collection["unknown_count"],
                "synthetic": True,
            }
            pit_admission = {
                "schema_id": "synthetic_pit_admission",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "cutoff": decision_at,
                "all_facts_available_by_cutoff": True,
                "future_outcome_access": False,
            }
            market_snapshot = build_market_information_snapshot(
                run_id=run_id,
                cycle_index=cycle_index,
                symbol="SYNTHUSDT",
                as_of=decision_at,
                facts=collection["facts"],
            )
        stage(
            "COLLECTION_ATTEMPTS_SEALED",
            collection_attempts,
            "collection_attempts_digest",
        )
        stage(
            "COLLECTION_SEALED",
            market_context,
            "market_context_digest",
            binding_name="market_context_digest",
        )
        stage(
            "PIT_ADMITTED",
            pit_admission,
            "pit_admission_digest",
        )
        stage(
            "MARKET_INFORMATION_SEALED",
            market_snapshot,
            "market_information_snapshot_digest",
            binding_name="market_information_snapshot_digest",
        )
        stage(
            "REPLAY_SEALED",
            {
                "schema_id": "synthetic_prior_state_replay",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "previous_registry_digest": (
                    None
                    if previous_registry is None
                    else previous_registry["hypothesis_registry_digest"]
                ),
                "previous_expectation_ledger_digest": (
                    None
                    if previous_ledger is None
                    else previous_ledger["expectation_ledger_digest"]
                ),
                "previous_belief_state_digest": (
                    None
                    if previous_beliefs is None
                    else previous_beliefs["belief_state_digest"]
                ),
            },
            "replay_digest",
        )
        position_truth = _position_truth()
        risk_policy = _risk_policy()
        legal_action_contract = _legal_action_contract()
        research_capability_contract = _research_capability_contract()
        pre_state = {
            "schema_id": "synthetic_pre_decision_state",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "previous_accepted_state_digest": (
                None
                if previous_accepted_state is None
                else previous_accepted_state["accepted_state_digest"]
            ),
            "atomic_position_truth": position_truth,
        }
        stage(
            "PRE_DECISION_STATE_SEALED",
            pre_state,
            "pre_decision_state_digest",
            binding_name="pre_decision_state_digest",
        )
        prior_view_refs = {
            name: value
            for name, value in prior_state_refs.items()
            if name
            in {
                "hypothesis_registry",
                "expectation_ledger",
                "belief_state",
                "accepted_state",
            }
        }
        prior_state_view = build_bounded_prior_state_view(
            previous_registry=previous_registry,
            previous_ledger=previous_ledger,
            previous_beliefs=previous_beliefs,
            previous_accepted_state=previous_accepted_state,
            prior_state_refs=prior_view_refs,
        )
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if "AGENT_CONTEXT_SEALED" in sealed_event_types:
            agent_context = load_staged_document(
                "AGENT_CONTEXT_SEALED", "agent_context_digest"
            )
        else:
            agent_context = self_digest(
                {
                    "schema_id": "synthetic_strategy_agent_context",
                    "schema_version": "3.0.0",
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "decision_at": decision_at,
                    "context_payload_mode": "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE",
                    "resume_capsule_ref": f"resume/to-cycle-{cycle_index:04d}.json",
                    "resume_capsule_digest": resume_capsule[
                        "resume_capsule_digest"
                    ],
                    "market_information_snapshot": market_snapshot,
                    "previous_research_state_view": prior_state_view,
                    "previous_research_state_refs": prior_view_refs,
                    "portfolio_truth": position_truth,
                    "risk_policy": risk_policy,
                    "legal_action_contract": legal_action_contract,
                    "research_capability_contract": research_capability_contract,
                    "unknown_market_categories": [
                        category
                        for category, status in market_snapshot[
                            "category_status"
                        ].items()
                        if status["status"] != "OBSERVED"
                    ],
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "agent_context_digest",
            )
        stage(
            "AGENT_CONTEXT_SEALED",
            agent_context,
            "agent_context_digest",
            binding_name="agent_context_digest",
        )
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if "AGENT_INPUT_PLAN_SEALED" in sealed_event_types:
            input_plan = load_staged_document(
                "AGENT_INPUT_PLAN_SEALED", "agent_input_plan_digest"
            )
            if (
                input_plan.get("agent_context_digest")
                != agent_context["agent_context_digest"]
                or input_plan.get("preflight_verdict") != "PASS"
                or input_plan.get("max_input_bytes") != max_agent_input_bytes
                or input_plan.get("reserved_max_output_bytes")
                != max_agent_output_bytes
            ):
                record_reliability_failure(
                    phase="AGENT_INPUT_PREFLIGHT",
                    reason_code="PREACCEPT_SEALED_INPUT_PLAN_INVALID",
                )
                raise ContinuousFixtureError("FIXTURE_SEALED_INPUT_PLAN_INVALID")
        else:
            try:
                input_plan = build_agent_input_plan(
                    agent_context=agent_context,
                    max_input_bytes=max_agent_input_bytes,
                    max_output_bytes=max_agent_output_bytes,
                    model_invocation_expected=False,
                )
            except WindowReliabilityError as exc:
                record_reliability_failure(
                    phase="AGENT_INPUT_PREFLIGHT",
                    reason_code=str(exc),
                )
                raise
        stage(
            "AGENT_INPUT_PLAN_SEALED",
            input_plan,
            "agent_input_plan_digest",
            binding_name="agent_input_plan_digest",
        )
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if (
            "AGENT_PROPOSAL_ATTEMPT_SEALED" in sealed_event_types
            and "AGENT_PROPOSAL_SEALED" not in sealed_event_types
        ):
            record_reliability_failure(
                phase="PROPOSAL_COMMIT",
                reason_code="PREACCEPT_PARTIAL_PROPOSAL_COMMIT",
            )
            raise ContinuousFixtureError("FIXTURE_PARTIAL_PROPOSAL_COMMIT")
        if "AGENT_PROPOSAL_SEALED" in sealed_event_types:
            proposal = load_staged_document(
                "AGENT_PROPOSAL_SEALED", "agent_proposal_digest"
            )
            invocation = load_staged_document(
                "AGENT_PROPOSAL_ATTEMPT_SEALED", "invocation_receipt_digest"
            )
            proposal_delivery_receipt = artifacts.read_document(
                relative_ref=str(proposal["agent_delivery_receipt_ref"]),
                digest_field="agent_delivery_receipt_digest",
                expected_semantic_digest=str(
                    proposal["agent_delivery_receipt_digest"]
                ),
            )
            if proposal.get("agent_delivery_receipt") != proposal_delivery_receipt:
                raise ContinuousFixtureError(
                    "FIXTURE_PROPOSAL_DELIVERY_RECEIPT_BINDING_INVALID"
                )
            verify_transport_receipt(proposal_delivery_receipt)
        else:
            try:
                proposal_delivery = strategy_agent.propose(context=agent_context)
                (
                    proposal_payload,
                    proposal_delivery_receipt,
                ) = validate_agent_delivery(
                    delivery=proposal_delivery,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    input_digest=agent_context["agent_context_digest"],
                    expected_schema_id="synthetic_open_research_agent_payload",
                    max_output_bytes=max_agent_output_bytes,
                )
                verify_transport_delivery(proposal_delivery)
            except WindowReliabilityError as exc:
                record_reliability_failure(
                    phase="PROPOSAL_DELIVERY",
                    reason_code=str(exc),
                )
                raise
            proposal_delivery_binding = artifacts.write_document(
                relative_ref=(
                    f"deliveries/cycle-{cycle_index:04d}/proposal-receipt.json"
                ),
                document=proposal_delivery_receipt,
                digest_field="agent_delivery_receipt_digest",
            )
            proposal = self_digest(
                {
                    "schema_id": "synthetic_open_research_agent_proposal",
                    "schema_version": "1.2.0",
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "agent_context_digest": agent_context["agent_context_digest"],
                    "agent_delivery_receipt_ref": proposal_delivery_binding[
                        "relative_ref"
                    ],
                    "agent_delivery_receipt_digest": proposal_delivery_receipt[
                        "agent_delivery_receipt_digest"
                    ],
                    "agent_delivery_receipt": proposal_delivery_receipt,
                    **dict(proposal_payload),
                    "selection_present_before_evaluation": False,
                    "external_execution_authority": "NONE_LOCAL_SIMULATION",
                    "executable": False,
                },
                "agent_proposal_digest",
            )
            invocation = make_agent_invocation_receipt(
                run_id=run_id,
                cycle_index=cycle_index,
                attempt_id=f"synthetic-attempt-{cycle_index}",
                input_context_digest=agent_context["agent_context_digest"],
                proposal_digest=proposal["agent_proposal_digest"],
                started_at=decision_at,
                ended_at=decision_at,
                automation_id=None,
                thread_id=None,
                authoring_mode="SYNTHETIC_STRATEGY_AGENT_ADAPTER",
                platform_model_receipt=None,
                input_plan_digest=input_plan["agent_input_plan_digest"],
                delivery_receipt_digest=proposal_delivery_receipt[
                    "agent_delivery_receipt_digest"
                ],
            )
        try:
            stage(
                "AGENT_PROPOSAL_ATTEMPT_SEALED",
                invocation,
                "invocation_receipt_digest",
                binding_name="agent_invocation_receipt_digest",
            )
            stage(
                "AGENT_PROPOSAL_SEALED",
                proposal,
                "agent_proposal_digest",
                binding_name="agent_proposal_digest",
            )
        except Exception as exc:
            record_reliability_failure(
                phase="PROPOSAL_COMMIT",
                reason_code=(
                    "PREACCEPT_PARTIAL_PROPOSAL_COMMIT:"
                    f"{type(exc).__name__}:{exc}"
                ),
            )
            raise
        sentiment = build_sentiment_state(
            market_snapshot=market_snapshot,
            dimension_inputs=proposal["sentiment_dimension_inputs"],
            operational_synthesis=proposal["operational_synthesis"],
        )
        stage(
            "SENTIMENT_STATE_SEALED",
            sentiment,
            "sentiment_state_digest",
            binding_name="sentiment_state_digest",
        )
        hypothesis_delta_artifact = self_digest(
            {
                "schema_id": "hypothesis_registry_delta_set",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "prior_registry_digest": (
                    None
                    if previous_registry is None
                    else previous_registry["hypothesis_registry_digest"]
                ),
                "deltas": proposal["hypothesis_deltas"],
            },
            "hypothesis_registry_delta_digest",
        )
        stage(
            "HYPOTHESIS_DELTA_SEALED",
            hypothesis_delta_artifact,
            "hypothesis_registry_delta_digest",
            binding_name="hypothesis_registry_delta_digest",
        )
        registry = reduce_hypothesis_registry(
            previous_registry=previous_registry,
            deltas=proposal["hypothesis_deltas"],
            decision_at=decision_at,
            max_active_hypotheses=5,
        )
        stage(
            "HYPOTHESIS_REGISTRY_SEALED",
            registry,
            "hypothesis_registry_digest",
            binding_name="hypothesis_registry_digest",
        )
        expectation_delta_artifact = self_digest(
            {
                "schema_id": "expectation_ledger_delta_set",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "prior_ledger_digest": (
                    None
                    if previous_ledger is None
                    else previous_ledger["expectation_ledger_digest"]
                ),
                "deltas": proposal["expectation_deltas"],
            },
            "expectation_ledger_delta_digest",
        )
        stage(
            "EXPECTATION_DELTA_SEALED",
            expectation_delta_artifact,
            "expectation_ledger_delta_digest",
            binding_name="expectation_ledger_delta_digest",
        )
        ledger = reduce_expectation_ledger(
            previous_ledger=previous_ledger,
            deltas=proposal["expectation_deltas"],
            decision_at=decision_at,
            valid_hypothesis_ids=registry["known_hypothesis_ids"],
        )
        stage(
            "EXPECTATION_LEDGER_SEALED",
            ledger,
            "expectation_ledger_digest",
            binding_name="expectation_ledger_digest",
        )
        public_inference_trace = build_public_inference_trace(
            market_snapshot=market_snapshot,
            sentiment_state=sentiment,
            hypothesis_registry=registry,
            expectation_ledger=ledger,
            agent_context=agent_context,
            agent_proposal=proposal,
            claims=proposal["public_inference_claims"],
            decision_at=decision_at,
        )
        stage(
            "PUBLIC_INFERENCE_TRACE_SEALED",
            public_inference_trace,
            "public_inference_trace_digest",
            binding_name="public_inference_trace_digest",
        )
        path_ids = [
            row["hypothesis_id"]
            for row in registry["hypotheses"]
            if row["hypothesis_type"] == "PATH"
        ]
        beliefs = reduce_path_beliefs(
            previous_state=previous_beliefs,
            belief_events=proposal["belief_events"],
            path_ids=path_ids,
            decision_at=decision_at,
        )
        stage(
            "BELIEF_UPDATE_SEALED",
            beliefs,
            "belief_state_digest",
            binding_name="belief_state_digest",
        )
        valid_failure_triggers = [
            f"trigger:{proposal['operational_lead_path_id']}",
            f"trigger:{proposal['runner_up_path_id']}",
            f"trigger:{proposal['residual_path_id']}",
        ]
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if "ACTION_EVALUATION_SEALED" in sealed_event_types:
            evaluation = load_staged_document(
                "ACTION_EVALUATION_SEALED", "action_evaluation_digest"
            )
        else:
            try:
                evaluation = build_action_evaluation_set(
                run_id=run_id,
                cycle_index=cycle_index,
                decision_at=decision_at,
                symbol="SYNTHUSDT",
                belief_state_digest=beliefs["belief_state_digest"],
                operational_lead_path_id=proposal["operational_lead_path_id"],
                runner_up_path_id=proposal["runner_up_path_id"],
                residual_path_id=proposal["residual_path_id"],
                position_truth=position_truth,
                risk_policy=risk_policy,
                valid_evidence_refs=[f"fact:c{cycle_index}:0"],
                valid_failure_trigger_refs=valid_failure_triggers,
                required_sizing_ids=[
                    "REDUCE_25",
                    "REDUCE_50",
                    "REDUCE_75",
                    "EXIT_100",
                ],
                    candidate_proposals=proposal["candidate_proposals"],
                )
            except ValueError as exc:
                record_reliability_failure(
                    phase="ACTION_EVALUATION",
                    reason_code=f"CURRENT_CYCLE_ACTION_EVALUATION:{exc}",
                )
                raise
        stage(
            "ACTION_EVALUATION_SEALED",
            evaluation,
            "action_evaluation_digest",
            binding_name="action_evaluation_digest",
        )
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if "DELIBERATION_SEALED" in sealed_event_types:
            deliberation = load_staged_document(
                "DELIBERATION_SEALED", "deliberation_digest"
            )
            deliberation_delivery_receipt = artifacts.read_document(
                relative_ref=str(deliberation["agent_delivery_receipt_ref"]),
                digest_field="agent_delivery_receipt_digest",
                expected_semantic_digest=str(
                    deliberation["agent_delivery_receipt_digest"]
                ),
            )
            if (
                deliberation.get("agent_delivery_receipt")
                != deliberation_delivery_receipt
            ):
                raise ContinuousFixtureError(
                    "FIXTURE_DELIBERATION_DELIVERY_RECEIPT_BINDING_INVALID"
                )
            verify_transport_receipt(deliberation_delivery_receipt)
        else:
            try:
                deliberation_delivery = strategy_agent.deliberate(
                    evaluation_set=evaluation
                )
                (
                    deliberation_payload,
                    deliberation_delivery_receipt,
                ) = validate_agent_delivery(
                    delivery=deliberation_delivery,
                    run_id=run_id,
                    cycle_index=cycle_index,
                    input_digest=evaluation["action_evaluation_digest"],
                    expected_schema_id="synthetic_agent_deliberation_payload",
                    max_output_bytes=max_agent_output_bytes,
                )
                verify_transport_delivery(deliberation_delivery)
            except WindowReliabilityError as exc:
                record_reliability_failure(
                    phase="DELIBERATION_DELIVERY",
                    reason_code=str(exc),
                )
                raise
            deliberation_delivery_binding = artifacts.write_document(
                relative_ref=(
                    f"deliveries/cycle-{cycle_index:04d}/"
                    "deliberation-receipt.json"
                ),
                document=deliberation_delivery_receipt,
                digest_field="agent_delivery_receipt_digest",
            )
            deliberation = self_digest(
                {
                    "schema_id": "synthetic_agent_deliberation",
                    "schema_version": "1.2.0",
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "action_evaluation_digest": evaluation[
                        "action_evaluation_digest"
                    ],
                    "agent_delivery_receipt_ref": deliberation_delivery_binding[
                        "relative_ref"
                    ],
                    "agent_delivery_receipt_digest": deliberation_delivery_receipt[
                        "agent_delivery_receipt_digest"
                    ],
                    "agent_delivery_receipt": deliberation_delivery_receipt,
                    **dict(deliberation_payload),
                },
                "deliberation_digest",
            )
        stage(
            "DELIBERATION_SEALED",
            deliberation,
            "deliberation_digest",
            binding_name="deliberation_digest",
        )
        selection = select_from_evaluation_set(
            evaluation_set=evaluation,
            selected_candidate_id=deliberation["selected_candidate_id"],
            ranked_alternative_ids=deliberation["ranked_alternative_ids"],
            why_not_selected=deliberation["why_not_selected"],
            selection_rationale=deliberation["selection_rationale"],
            agent_proposal_digest=proposal["agent_proposal_digest"],
        )
        stage(
            "ACTION_SELECTION_SEALED",
            selection,
            "action_selection_digest",
            binding_name="action_selection_digest",
        )
        selected_evaluation = next(
            row
            for row in evaluation["candidates"]
            if row["candidate_id"] == selection["selected_candidate_id"]
        )
        risk_decision = self_digest(
            {
                "schema_id": "synthetic_deterministic_risk_decision",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "action_selection_digest": selection["action_selection_digest"],
                "selected_candidate_evaluation_digest": selected_evaluation[
                    "candidate_evaluation_digest"
                ],
                "approved": selected_evaluation["feasible"],
                "hard_vetoes": selected_evaluation["hard_vetoes"],
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
            },
            "risk_decision_digest",
        )
        stage(
            "RISK_DECISION_SEALED",
            risk_decision,
            "risk_decision_digest",
            binding_name="risk_decision_digest",
        )
        decision = self_digest(
            {
                "schema_id": "synthetic_continuous_decision",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "action_selection_digest": selection["action_selection_digest"],
                "risk_decision_digest": risk_decision["risk_decision_digest"],
                "selected_candidate_id": selection["selected_candidate_id"],
                "action_class": selected_evaluation["action_class"],
                "executable": False,
            },
            "decision_digest",
        )
        stage(
            "DECISION_SEALED",
            decision,
            "decision_digest",
            binding_name="decision_digest",
        )
        try:
            grounding_receipt = build_current_cycle_grounding_receipt(
                agent_context=agent_context,
                agent_proposal=proposal,
                public_inference_trace=public_inference_trace,
                action_evaluation=evaluation,
                deliberation=deliberation,
                selection=selection,
            )
        except WindowReliabilityError as exc:
            record_reliability_failure(
                phase="CURRENT_CYCLE_GROUNDING",
                reason_code=str(exc),
            )
            raise
        stage(
            "CURRENT_CYCLE_GROUNDING_SEALED",
            grounding_receipt,
            "current_cycle_grounding_digest",
            binding_name="current_cycle_grounding_digest",
        )
        try:
            preaccept_validation = build_preaccept_validation_receipt(
                resume_capsule=resume_capsule,
                input_plan=input_plan,
                agent_context=agent_context,
                proposal_delivery_receipt=proposal_delivery_receipt,
                agent_proposal=proposal,
                public_inference_trace=public_inference_trace,
                action_evaluation=evaluation,
                deliberation_delivery_receipt=deliberation_delivery_receipt,
                deliberation=deliberation,
                selection=selection,
                risk_decision=risk_decision,
                decision=decision,
                grounding_receipt=grounding_receipt,
            )
        except WindowReliabilityError as exc:
            record_reliability_failure(
                phase="PREACCEPT_ATOMIC_GATE",
                reason_code=str(exc),
            )
            raise
        stage(
            "PREACCEPT_VALIDATION_SEALED",
            preaccept_validation,
            "preaccept_validation_receipt_digest",
            binding_name="preaccept_validation_receipt_digest",
        )
        accepted_state = self_digest(
            {
                "schema_id": "synthetic_continuous_accepted_state",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "decision_digest": decision["decision_digest"],
                "market_information_snapshot_digest": market_snapshot[
                    "market_information_snapshot_digest"
                ],
                "sentiment_state_digest": sentiment["sentiment_state_digest"],
                "hypothesis_registry_digest": registry[
                    "hypothesis_registry_digest"
                ],
                "expectation_ledger_digest": ledger["expectation_ledger_digest"],
                "public_inference_trace_digest": public_inference_trace[
                    "public_inference_trace_digest"
                ],
                "belief_state_digest": beliefs["belief_state_digest"],
                "resume_capsule_digest": resume_capsule[
                    "resume_capsule_digest"
                ],
                "agent_input_plan_digest": input_plan[
                    "agent_input_plan_digest"
                ],
                "current_cycle_grounding_digest": grounding_receipt[
                    "current_cycle_grounding_digest"
                ],
                "preaccept_validation_receipt_digest": preaccept_validation[
                    "preaccept_validation_receipt_digest"
                ],
                "selected_candidate_id": selection["selected_candidate_id"],
                "operational_lead_path_id": proposal[
                    "operational_lead_path_id"
                ],
                "position_truth": evaluation["position_truth"],
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "accepted_state_digest",
        )
        accepted_binding = stage(
            "STATE_ACCEPTED",
            accepted_state,
            "accepted_state_digest",
            binding_name="accepted_state_digest",
            relative_ref=f"states/state-{cycle_index:04d}.json",
        )
        action_receipt = self_digest(
            {
                "schema_id": "synthetic_nonexecution_action_receipt",
                "run_id": run_id,
                "cycle_index": cycle_index,
                "decision_digest": decision["decision_digest"],
                "accepted_state_digest": accepted_state["accepted_state_digest"],
                "selected_candidate_id": selection["selected_candidate_id"],
                "applied_candidate_id": selection["selected_candidate_id"],
                "action_class": selected_evaluation["action_class"],
                "simulation_only": True,
                "order_sent": False,
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "action_receipt_digest",
        )
        stage(
            "ACTION_RECEIPT_SEALED",
            action_receipt,
            "action_receipt_digest",
            binding_name="action_receipt_digest",
        )
        post_accept_checkpoint = coordinator.enter_post_accept_finalization(
            checkpoint_path=artifacts.checkpoint_path(),
            accepted_state_path=accepted_binding["relative_ref"],
            accepted_state_digest=accepted_state["accepted_state_digest"],
        )
        _build_and_store_resume_capsule(
            run_id=run_id,
            created_at=decision_at,
            manifest_ref=manifest_binding,
            checkpoint=post_accept_checkpoint,
            checkpoints=checkpoints,
            artifacts=artifacts,
            prior_state_refs=prior_state_refs,
            current_cycle_stage_refs=_current_cycle_stage_refs(store),
            relative_ref=(
                f"resume/recovery-cycle-{cycle_index:04d}-"
                f"{post_accept_checkpoint['checkpoint_digest']}.json"
            ),
        )
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if "COMPARATOR_SEALED" in sealed_event_types:
            comparator_document = load_staged_document(
                "COMPARATOR_SEALED", "comparator_digest"
            )
            comparator_row = comparator_document["review_row"]
        else:
            try:
                comparator_row = comparator.compare(
                    cycle_index=cycle_index, accepted_state=accepted_state
                )
            except Exception as exc:
                record_reliability_failure(
                    phase="POST_ACCEPT_COMPARATOR",
                    reason_code=(
                        "POST_ACCEPT_DETERMINISTIC_TAIL:"
                        f"{type(exc).__name__}:{exc}"
                    ),
                    accepted_state_exists=True,
                )
                raise
            comparator_document = self_digest(
                {
                    "schema_id": "synthetic_cycle_comparator",
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "accepted_state_digest": accepted_state[
                        "accepted_state_digest"
                    ],
                    "review_row": dict(comparator_row),
                },
                "comparator_digest",
            )
        stage(
            "COMPARATOR_SEALED",
            comparator_document,
            "comparator_digest",
            binding_name="comparator_digest",
        )
        sealed_event_types = {
            event["event_type"] for event in store.read_events()
        }
        if "REVIEW_SOURCE_SEALED" in sealed_event_types:
            review_source = load_staged_document(
                "REVIEW_SOURCE_SEALED", "cycle_review_source_digest"
            )
        else:
            review_source = self_digest(
                {
                    "schema_id": "receipt_bound_cycle_review_source",
                    "schema_version": "1.0.0",
                    "run_id": run_id,
                    "cycle_index": cycle_index,
                    "accepted_state_digest": accepted_state[
                        "accepted_state_digest"
                    ],
                    "comparator_digest": comparator_document[
                        "comparator_digest"
                    ],
                    "market_information_snapshot_digest": market_snapshot[
                        "market_information_snapshot_digest"
                    ],
                    "sentiment_state_digest": sentiment["sentiment_state_digest"],
                    "hypothesis_registry_digest": registry[
                        "hypothesis_registry_digest"
                    ],
                    "expectation_ledger_digest": ledger[
                        "expectation_ledger_digest"
                    ],
                    "public_inference_trace_digest": public_inference_trace[
                        "public_inference_trace_digest"
                    ],
                    "review_row": dict(comparator_row),
                },
                "cycle_review_source_digest",
            )
        stage(
            "REVIEW_SOURCE_SEALED",
            review_source,
            "cycle_review_source_digest",
            binding_name="cycle_review_source_digest",
        )
        evidence_receipt = coordinator.seal_cycle_evidence(
            artifact_bindings=evidence_bindings,
            recorded_at=decision_at,
        )
        report = {
            "schema_id": "synthetic_continuous_cycle_report",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "cycle_evidence_receipt_digest": evidence_receipt[
                "cycle_evidence_receipt_digest"
            ],
            "market_information_snapshot_digest": market_snapshot[
                "market_information_snapshot_digest"
            ],
            "sentiment_state_digest": sentiment["sentiment_state_digest"],
            "hypothesis_registry_digest": registry[
                "hypothesis_registry_digest"
            ],
            "expectation_ledger_digest": ledger["expectation_ledger_digest"],
            "public_inference_trace_digest": public_inference_trace[
                "public_inference_trace_digest"
            ],
            "selected_candidate_id": selection["selected_candidate_id"],
            "unknown_category_count": collection["unknown_count"],
            "interpretation_boundary": "SYNTHETIC_PROCESS_PROOF_NOT_MARKET_VALIDATION",
        }
        report_binding = stage(
            "REPORT_SEALED",
            report,
            "report_digest",
            relative_ref=f"reports/cycle-{cycle_index:04d}.json",
            use_physical_digest=True,
        )
        completion_bindings = {
            **evidence_bindings,
            "cycle_evidence_receipt_digest": evidence_receipt[
                "cycle_evidence_receipt_digest"
            ],
            "report_sha256": report_binding["physical_sha256"],
        }
        review_digest: str | None = None
        if cycle_index == 4:
            review = build_source_bound_four_cycle_review(
                review_sources=review_sources,
                run_id=run_id,
                through_cycle=4,
            )
            review_binding = stage(
                "REVIEW_SEALED",
                review,
                "review_digest",
                relative_ref="reviews/through-cycle-0004.json",
            )
            review_digest = review_binding["semantic_digest"]
        completed = coordinator.complete_cycle(
            checkpoint_path=artifacts.checkpoint_path(),
            artifact_bindings=completion_bindings,
            accepted_state_path=accepted_binding["relative_ref"],
            recorded_at=decision_at,
            review_digest=review_digest,
        )
        prior_state_refs = {
            "hypothesis_registry": _binding_from_receipt(
                evidence_receipt, "hypothesis_registry_digest"
            ),
            "expectation_ledger": _binding_from_receipt(
                evidence_receipt, "expectation_ledger_digest"
            ),
            "belief_state": _binding_from_receipt(
                evidence_receipt, "belief_state_digest"
            ),
            "accepted_state": _binding_from_receipt(
                evidence_receipt, "accepted_state_digest"
            ),
            "cycle_evidence_receipt": artifacts.artifact_binding(
                relative_ref=f"evidence-receipts/cycle-{cycle_index:04d}.json",
                digest_field="cycle_evidence_receipt_digest",
                expected_semantic_digest=evidence_receipt[
                    "cycle_evidence_receipt_digest"
                ],
            ),
            "completion_receipt": artifacts.artifact_binding(
                relative_ref=f"completion-receipts/cycle-{cycle_index:04d}.json",
                digest_field="completion_receipt_digest",
                expected_semantic_digest=completed["completion_receipt"][
                    "completion_receipt_digest"
                ],
            ),
        }
        resume_capsule, _ = _build_and_store_resume_capsule(
            run_id=run_id,
            created_at=decision_at,
            manifest_ref=manifest_binding,
            checkpoint=completed["checkpoint"],
            checkpoints=checkpoints,
            artifacts=artifacts,
            prior_state_refs=prior_state_refs,
        )
        cycle_summaries.append(
            {
                "cycle_index": cycle_index,
                "market_information_snapshot_digest": market_snapshot[
                    "market_information_snapshot_digest"
                ],
                "sentiment_state_digest": sentiment["sentiment_state_digest"],
                "hypothesis_registry_digest": registry[
                    "hypothesis_registry_digest"
                ],
                "expectation_ledger_digest": ledger["expectation_ledger_digest"],
                "public_inference_trace_digest": public_inference_trace[
                    "public_inference_trace_digest"
                ],
                "public_inference_claim_count": len(
                    public_inference_trace["claims"]
                ),
                "public_inference_evidence_balance": dict(
                    public_inference_trace["evidence_balance"]
                ),
                "cycle_evidence_receipt_digest": evidence_receipt[
                    "cycle_evidence_receipt_digest"
                ],
                "completion_receipt_digest": completed["completion_receipt"][
                    "completion_receipt_digest"
                ],
                "resume_capsule_digest": evidence_bindings[
                    "resume_capsule_digest"
                ],
                "agent_input_plan_digest": input_plan[
                    "agent_input_plan_digest"
                ],
                "agent_input_canonical_bytes": input_plan[
                    "context_canonical_byte_length"
                ],
                "current_cycle_grounding_digest": grounding_receipt[
                    "current_cycle_grounding_digest"
                ],
                "preaccept_validation_receipt_digest": preaccept_validation[
                    "preaccept_validation_receipt_digest"
                ],
                "unknown_market_category_count": collection["unknown_count"],
            }
        )
        previous_registry = registry
        previous_ledger = ledger
        previous_beliefs = beliefs
        previous_accepted_state = accepted_state

    if through_cycle < 4:
        return {
            "schema_id": "continuous_four_cycle_synthetic_fixture_result",
            "schema_version": "1.1.0",
            "run_id": run_id,
            "status": "PAUSED_AT_DURABLE_CYCLE_BOUNDARY",
            "completed_cycles": through_cycle,
            "next_cycle_index": through_cycle + 1,
            "resume_capsule_digest": resume_capsule["resume_capsule_digest"],
            "resume_capsule_ref": f"resume/to-cycle-{through_cycle + 1:04d}.json",
            "chat_history_is_authority": False,
            "agent_context_payload_mode": "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE",
            "cycle_summaries": cycle_summaries,
            "network_access": False,
            "model_invocation": False,
            "order_sent": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "evidence_boundary": "CONTRACT_AND_PROCESS_EVIDENCE_ONLY_NOT_PREDICTION_OR_PROFIT",
        }

    known_hypotheses = previous_registry["known_hypothesis_ids"]
    expectations = {
        row["expectation_id"]: row["status"]
        for row in previous_ledger["expectations"]
    }
    if (
        "hypothesis:event-liquidity-vacuum-reversal" not in known_hypotheses
        or expectations.get("expectation:base-sequence") != "FULFILLED"
        or previous_accepted_state.get("operational_lead_path_id")
        != "hypothesis:event-liquidity-vacuum-reversal"
        or not any(
            row["public_inference_evidence_balance"][
                "distinct_contradicting_fact_count"
            ]
            > 0
            and row["public_inference_evidence_balance"][
                "distinct_unknown_fact_count"
            ]
            > 0
            for row in cycle_summaries
        )
    ):
        raise ContinuousFixtureError("FIXTURE_DYNAMIC_ACCEPTANCE_NOT_MET")
    return {
        "schema_id": "continuous_four_cycle_synthetic_fixture_result",
        "schema_version": "1.1.0",
        "run_id": run_id,
        "status": "COMPLETED_LOCAL_SYNTHETIC_FIXTURE",
        "completed_cycles": 4,
        "next_cycle_index": 5,
        "novel_hypothesis_id": "hypothesis:event-liquidity-vacuum-reversal",
        "closed_expectation_id": "expectation:base-sequence",
        "closed_expectation_status": "FULFILLED",
        "novel_hypothesis_became_operational_lead_cycle": 3,
        "agent_context_payload_mode": "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE",
        "cross_window_resume_verified": True,
        "chat_history_is_authority": False,
        "latest_resume_capsule_digest": resume_capsule[
            "resume_capsule_digest"
        ],
        "public_inference_trace_bound": True,
        "private_chain_of_thought_recorded": False,
        "cycle_summaries": cycle_summaries,
        "final_hypothesis_registry_digest": previous_registry[
            "hypothesis_registry_digest"
        ],
        "final_expectation_ledger_digest": previous_ledger[
            "expectation_ledger_digest"
        ],
        "review_digest": review_digest,
        "network_access": False,
        "model_invocation": False,
        "order_sent": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "evidence_boundary": "CONTRACT_AND_PROCESS_EVIDENCE_ONLY_NOT_PREDICTION_OR_PROFIT",
    }
