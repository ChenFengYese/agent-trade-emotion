from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import inspect
import unittest

from trade_system.theory_paper_v2.application.market_cycle.paper_capability_evaluation import (
    AttentionSchedulingEvidenceInputV1,
    PaperDecisionEvidenceInputV1,
    bind_paper_capability_span,
    build_paper_position_and_open_order_ref,
    build_pre_outcome_paper_capability_assessment,
    build_pre_outcome_paper_capability_task,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
    GOAL_ATTENTION_CHECKPOINT_SCHEMA_ID,
    GOAL_ATTENTION_CHECKPOINT_SCHEMA_VERSION,
    GoalAttentionCheckpointV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.contracts import (
    ArtifactRef,
    BehaviorPlan,
    HypothesisRecord,
    InputSnapshot,
)
from trade_system.theory_paper_v2.domain.market_cycle.experiment import (
    EXPERIMENT_MISSING_DATA_POLICY,
    ExperimentPolicyV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    PAPER_AGENT_ACTIONS,
    FillEventV1,
    OrderTruthV1,
    PaperBracketV1,
    PaperCommandV1,
    PaperExecutionIntentV1,
    PaperLedgerRecordV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper_capability_evaluation import (
    PAPER_CAPABILITY_CRITERIA,
    PAPER_CAPABILITY_RUBRICS,
    PaperCapabilityEvaluationError,
    PaperCapabilityFindingV1,
    PaperEvidenceSpanV1,
    PreOutcomePaperCapabilityAssessmentV1,
    PreOutcomePaperCapabilityTaskV1,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_intent_mailbox import (
    _paper_context_values,
    _paper_output_contract,
    paper_action_space_contract,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
)


_AGENT = "HYPE_CAPABILITY_TRADER"
_PHYSICAL_TASK = "codex-thread:11111111-1111-1111-1111-111111111111"
_ASSESSOR_TASK = "codex-thread:22222222-2222-2222-2222-222222222222"
_OTHER_PHYSICAL_TASK = "codex-thread:33333333-3333-3333-3333-333333333333"
_ACCOUNT = "hype-paper-capability-account"
_EPISODE = "hype-episode-001"


def _attention_checkpoint_event(
    attention: AttentionRequest, *, policy: ExperimentPolicyV1
) -> dict[str, object]:
    checkpoint = GoalAttentionCheckpointV1(
        schema_id=GOAL_ATTENTION_CHECKPOINT_SCHEMA_ID,
        schema_version=GOAL_ATTENTION_CHECKPOINT_SCHEMA_VERSION,
        run_id=policy.run_id,
        run_manifest_identity_sha256="b" * 64,
        experiment_policy_sha256=policy.policy_sha256,
        physical_goal_id=_PHYSICAL_TASK,
        physical_goal_source="CODEX_THREAD_ID",
        request_sha256=attention.agent_owned_sha256,
        accepted_at=attention.issued_at,
        accepted_clock_source="CONTROLLER_TRUSTED_CLOCK",
    )
    body: dict[str, object] = {
        "schema_id": "agent-trade-emotion.v332-attention-event",
        "schema_version": "1.0.0",
        "logical_agent_id": attention.logical_agent_id,
        "revision": 2,
        "prior_event_sha256": "a" * 64,
        "event_id": f"request:{attention.request_id}",
        "event_type": "ATTENTION_REQUEST_SUBMITTED",
        "occurred_at": attention.issued_at,
        "payload": {
            "request": attention.to_dict(),
            "accepted_at": attention.issued_at,
            "goal_checkpoint": checkpoint.to_dict(),
        },
    }
    return {**body, "event_sha256": canonical_digest(body)}


def _iso(base_minute: int, second: int) -> str:
    return datetime(
        2026, 8, 13, 12, base_minute, second, tzinfo=timezone.utc
    ).isoformat()


def _policy(capability_id: str) -> ExperimentPolicyV1:
    return ExperimentPolicyV1(
        experiment_id=f"paper-{capability_id.lower()}-pilot",
        run_id=f"paper-{capability_id.lower()}-run",
        phase="CAPABILITY_PILOT",
        venue_id="OKX",
        instrument_id="HYPE-USDT-SWAP",
        market_contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        starts_at="2026-08-13T11:59:00+00:00",
        duration_seconds=3600,
        decision_horizon_seconds=600,
        outcome_tolerance_seconds=60,
        base_sampling_seconds=300,
        active_sampling_seconds=60,
        capability_ids=(capability_id,),
        public_data_authorized=True,
        local_paper_authorized=True,
        testnet_authorized=False,
        live_authorized=False,
        private_credentials_authorized=False,
        external_orders_authorized=False,
        funds_authorized=False,
        paper_account={
            "account_id": _ACCOUNT,
            "setup_cycle_id": "hype-paper-setup",
            "logical_agent_id": _AGENT,
            "agent_generation": 1,
            "account_mode": "LINEAR_PERP",
            "base_currency": "USDT",
            "initial_balance": "10000",
            "max_leverage": "2",
            "max_position_notional": "10000",
            "max_decision_loss": "100",
            "max_observed_drawdown": "500",
            "cost_model": {
                "model_id": "paper-cost-v1",
                "maker_fee_bps": "2",
                "taker_fee_bps": "5",
                "market_impact_bps": "3",
                "funding_status": "UNKNOWN",
                "borrow_status": "NOT_APPLICABLE",
                "effective_from": "2026-08-13T11:00:00+00:00",
                "effective_to": "2026-08-13T14:00:00+00:00",
            },
        },
        evaluation={
            "mode": "INDEPENDENT_CAPABILITY_PILOT",
            "total_score_enabled": False,
            "actual_execution_status": "NOT_APPLICABLE_NOT_AUTHORIZED",
            "predictive_claim": "NOT_EVALUATED",
            "continuity_claim": "NOT_TESTED",
        },
        missing_data_policy=EXPERIMENT_MISSING_DATA_POLICY,
        restart_if=("FUTURE_DATA_LEAKAGE",),
        continue_if=("OPTIONAL_DATA_TYPED_UNKNOWN",),
    )


def _snapshot(cycle_id: str, minute: int) -> tuple[InputSnapshot, ArtifactRef]:
    raw_ref = ArtifactRef(
        artifact_type="RawCapture",
        artifact_id=f"{cycle_id}.raw",
        path="raw/input/body.bin",
        size_bytes=1,
        sha256=hashlib.sha256(cycle_id.encode()).hexdigest(),
    )

    def observed(value: object) -> dict[str, object]:
        return {
            "value": value,
            "available_at": _iso(minute, 0),
            "raw_sha256": raw_ref.sha256,
        }

    bars = observed([])
    bars["last_closed_at"] = _iso(minute, 0)
    snapshot = InputSnapshot(
        snapshot_id=f"{cycle_id}.snapshot",
        cycle_id=cycle_id,
        request_id=f"{cycle_id}.request",
        source_cutoff_at=_iso(minute, 0),
        decision_at=_iso(minute, 1),
        sealed_at=_iso(minute, 2),
        venue_id="OKX",
        instrument_id="HYPE-USDT-SWAP",
        contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        analysis_profile="DELTA" if minute else "COLD",
        data_profile=HYPE_OKX_DATA_PROFILE.market_data_profile,
        outcome_horizon_seconds=600,
        outcome_tolerance_seconds=60,
        lawful_actions=(
            "LONG_REFERENCE",
            "SHORT_REFERENCE",
            "WAIT",
            "OTHER_INFORMATION_ACTION",
        ),
        core_observations={
            "server_time": observed(_iso(minute, 0)),
            "instrument": observed("HYPE-USDT-SWAP"),
            "mark_price": observed("40" if minute == 0 else "40.2"),
            "closed_15m_bars": bars,
        },
        optional_observations={},
        unknowns=("CONTINUOUS_ORDER_FLOW_UNKNOWN",),
        raw_refs=(raw_ref,),
        source_health=(),
        theory_identity=V332_THEORY_IDENTITY,
    )
    raw = canonical_bytes(snapshot.to_dict())
    reference = ArtifactRef(
        artifact_type="InputSnapshot",
        artifact_id=snapshot.snapshot_id,
        path="artifacts/input-snapshot.json",
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    return snapshot, reference


def _decision(minute: int) -> str:
    prefix = (
        "D0：比较LONG_REFERENCE、SHORT_REFERENCE与WAIT；WAIT的机会成本是错过短线突破。"
        if minute == 0
        else "D1：延续同一episode，只因新鲜价格事实更新状态，不因亏损摊平。"
    )
    return (
        f"{prefix}\n"
        "假说A：40上方吸收持续则反弹；若跌破40则失效。\n"
        "假说B：卖压增强则支撑失效；成交量和OI扩张用于区分。\n"
        "WAIT必须等到新证据越过重入阈值才解除，未满足时保持迟滞。\n"
        "ACTION=WAIT\n"
        "POSITION=flat\n"
    )


def _hypothesis(
    snapshot: InputSnapshot,
    reference: ArtifactRef,
    *,
    request_sha256: str,
    minute: int,
) -> HypothesisRecord:
    text = _decision(minute)
    raw = text.encode("utf-8")
    return HypothesisRecord(
        record_id=f"{snapshot.cycle_id}.hypotheses",
        cycle_id=snapshot.cycle_id,
        input_snapshot_ref=reference,
        decision_at=snapshot.decision_at,
        agent_delivered_at=_iso(minute, 4),
        sealed_at=_iso(minute, 5),
        outcome_horizon_seconds=600,
        outcome_tolerance_seconds=60,
        agent_request_sha256=request_sha256,
        agent_delivery_path="transport/agent-delivery.json",
        agent_delivery_sha256=hashlib.sha256(
            f"delivery-{minute}".encode()
        ).hexdigest(),
        agent_decision_text=text,
        agent_decision_size_bytes=len(raw),
        agent_decision_sha256=hashlib.sha256(raw).hexdigest(),
        projection_status="AVAILABLE",
        projection_reason=None,
        hypothesis_index=(
            "假说A：40上方吸收持续则反弹；若跌破40则失效。",
            "假说B：卖压增强则支撑失效；成交量和OI扩张用于区分。",
        ),
        agent_action_text="ACTION=WAIT",
        agent_position_text="POSITION=flat",
        lawful_actions=snapshot.lawful_actions,
        unresolved_unknowns=snapshot.unknowns,
        theory_identity=V332_THEORY_IDENTITY,
    )


def _account(
    version: int,
    *,
    positions: tuple[dict[str, object], ...] = (),
    orders: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    return {
        "account_id": _ACCOUNT,
        "version": version,
        "account_mode": "LINEAR_PERP",
        "owner_logical_agent_id": _AGENT,
        "owner_agent_generation": 1,
        "base_currency": "USDT",
        "permitted_symbol": "HYPE-USDT-SWAP",
        "positions": list(positions),
        "orders": list(orders),
    }


def _context(
    *,
    policy: ExperimentPolicyV1,
    snapshot: InputSnapshot,
    snapshot_ref: ArtifactRef,
    pre_head: PaperLedgerRecordV1,
    prior_intents: tuple[PaperExecutionIntentV1, ...],
    prior_hypothesis: HypothesisRecord | None = None,
    prior_attention_request: AttentionRequest | None = None,
    exposure_projection_status: str = "DERIVED_UNAMBIGUOUS",
    account: dict[str, object] | None = None,
    orders_and_fills: dict[str, object] | None = None,
    unrealized_pnl: str = "0",
) -> dict[str, object]:
    assert policy.paper_account is not None
    selected_account = _account(pre_head.revision) if account is None else account
    selected_orders_and_fills = (
        {
            "account_id": _ACCOUNT,
            "open_orders": [],
            "order_history": [],
            "fills": [],
            "unresolved": [],
        }
        if orders_and_fills is None
        else orders_and_fills
    )
    symbol_positions = [
        item
        for item in selected_account["positions"]
        if item.get("symbol") == snapshot.instrument_id
    ]
    actual_quantity = "0" if not symbol_positions else symbol_positions[0]["quantity"]
    base = {
        "schema_id": "agent-trade-emotion.v332-paper-decision-context",
        "schema_version": "1.5.0",
        "status": "OBSERVED",
        "cycle_id": snapshot.cycle_id,
        "snapshot_ref": snapshot_ref.to_dict(),
        "snapshot_sealed_at": snapshot.sealed_at,
        "experiment_policy_sha256": policy.policy_sha256,
        "paper_account_policy": {
            **{
                key: policy.paper_account[key]
                for key in policy.paper_account
                if key != "cost_model"
            },
            "cost_model": dict(policy.paper_account["cost_model"]),
        },
        "ledger_head": {
            "revision": pre_head.revision,
            "record_sha256": pre_head.record_sha256,
        },
        "data_evidence": {
            "status": "BOUND",
            "profile_id": HYPE_OKX_DATA_PROFILE.profile_id,
            "data_cursor": f"{snapshot.cycle_id}-cursor",
            "slice_sha256": canonical_digest(
                {"cycle_id": snapshot.cycle_id, "snapshot": snapshot.snapshot_id}
            ),
        },
        "account": selected_account,
        "orders_and_fills": selected_orders_and_fills,
        "valuation": {
            "account_id": _ACCOUNT,
            "account_version": pre_head.revision,
            "symbol": "HYPE-USDT-SWAP",
            "status": "PARTIAL_UNKNOWN_CARRY_COSTS",
            "observed_at": snapshot.source_cutoff_at,
            "available_at": snapshot.decision_at,
            "source_sha256": snapshot.raw_refs[0].sha256,
            "mark": "40" if snapshot.analysis_profile == "COLD" else "40.2",
            "unrealized_pnl": unrealized_pnl,
            "mark_basis": {
                "status": "DECISION_SNAPSHOT_MARK_ONLY",
                "snapshot_ref": snapshot_ref.to_dict(),
                "market_fact_cutoff_at": snapshot.sealed_at,
                "data_slice_sha256": canonical_digest(
                    {"cycle_id": snapshot.cycle_id, "snapshot": snapshot.snapshot_id}
                ),
            },
        },
        "cost_effect": {"status": "MODELED"},
        "prior_execution_intents": [item.to_dict() for item in prior_intents],
        "latest_transition": (
            None if not prior_intents else prior_intents[-1].to_dict()
        ),
        "prior_decision_status": (
            "NO_PRIOR_INTENT" if not prior_intents else "PRIOR_COMPLETE_OBSERVED"
        ),
        "latest_prior_decision": None,
        "episode_exposure_projection": {
            "status": (
                "NO_PRIOR_INTENT" if not prior_intents else exposure_projection_status
            ),
            "derivation": "READ_ONLY_FACT_PROJECTION_NOT_AGENT_DECISION",
            "source_refs": (
                {}
                if not prior_intents
                else {
                    "execution_intent_sha256": prior_intents[-1].intent_sha256,
                    "ledger_head_record_sha256": pre_head.record_sha256,
                }
            ),
            "episode_id": None if not prior_intents else prior_intents[-1].episode_id,
            "latest_transition_id": (
                None if not prior_intents else prior_intents[-1].transition_id
            ),
            "role": None if not prior_intents else prior_intents[-1].role,
            "intended_target_signed_quantity": (
                None
                if not prior_intents
                else prior_intents[-1].target_state["signed_quantity"]
            ),
            "account_signed_quantity": (
                None
                if not prior_intents or exposure_projection_status != "DERIVED_UNAMBIGUOUS"
                else actual_quantity
            ),
            "open_order_count": None if not prior_intents else 0,
            "target_reconciliation": (
                "UNKNOWN"
                if not prior_intents or exposure_projection_status != "DERIVED_UNAMBIGUOUS"
                else (
                    "MATCHES_INTENT_TARGET"
                    if actual_quantity
                    == prior_intents[-1].target_state["signed_quantity"]
                    else "EXECUTION_DIFFERS"
                )
            ),
            "ambiguity_reason": (
                "NO_PRIOR_INTENT"
                if not prior_intents
                else "TEST_AMBIGUITY"
                if exposure_projection_status == "AMBIGUOUS"
                else None
            ),
        },
    }
    prior_text_sources: dict[str, object] = {}
    if prior_intents:
        if prior_hypothesis is None:
            raise AssertionError("prior_hypothesis is required with prior_intents")
        latest = prior_intents[-1]
        review_text = "Exact prior Agent review fixture text."
        review_raw = review_text.encode("utf-8")
        artifact_hashes = {
            "HypothesisRecord": canonical_digest(prior_hypothesis.to_dict()),
            "BehaviorPlan": "1" * 64,
            "Outcome": "2" * 64,
            "Review": "3" * 64,
        }
        base["latest_prior_decision"] = {
            "decision_cycle_id": latest.decision_cycle_id,
            "decision_sha256": latest.decision_sha256,
            "execution_intent_sha256": latest.intent_sha256,
            "cycle_stage": "COMPLETE",
            "authority": "NON_AUTHORITATIVE_CONTINUITY_CONTEXT",
            "retrieval_policy": "LATEST_COMPLETE_INCLUDED_BOUNDED",
            "artifact_refs": {
                artifact_type: ArtifactRef(
                    artifact_type=artifact_type,
                    artifact_id=f"{latest.decision_cycle_id}.{artifact_type.lower()}",
                    path=f"artifacts/{artifact_type}.json",
                    size_bytes=1,
                    sha256=sha256,
                ).to_dict()
                for artifact_type, sha256 in artifact_hashes.items()
            },
            "agent_decision_body": {
                "included_in_context": True,
                "verbatim_text": prior_hypothesis.agent_decision_text,
                "size_bytes": prior_hypothesis.agent_decision_size_bytes,
                "sha256": prior_hypothesis.agent_decision_sha256,
                "artifact_ref": None,
                "source_json_pointer": "/agent_decision_text",
            },
            "agent_review_body": {
                "included_in_context": True,
                "verbatim_text": review_text,
                "size_bytes": len(review_raw),
                "sha256": hashlib.sha256(review_raw).hexdigest(),
                "artifact_ref": None,
                "source_json_pointer": "/agent_review_text",
            },
        }
        prior = base["latest_prior_decision"]
        prior["agent_decision_body"]["artifact_ref"] = prior["artifact_refs"][
            "HypothesisRecord"
        ]
        prior["agent_review_body"]["artifact_ref"] = prior["artifact_refs"][
            "Review"
        ]
        prior_text_sources = {
            field: {
                "sha256": prior[field]["sha256"],
                "artifact_ref": prior[field]["artifact_ref"],
            }
            for field in ("agent_decision_body", "agent_review_body")
        }
    exact_suffix: list[PaperExecutionIntentV1] = []
    if prior_intents:
        for item in reversed(prior_intents):
            if (
                item.episode_id != prior_intents[-1].episode_id
                or item.action not in {"WAIT", "HOLD", "WATCH"}
            ):
                break
            exact_suffix.append(item)
        exact_suffix.reverse()
    episode_tail = []
    if prior_intents:
        for item in reversed(prior_intents):
            if item.episode_id != prior_intents[-1].episode_id:
                break
            episode_tail.append(item)
        episode_tail.reverse()
    checkpoint = (
        None
        if prior_attention_request is None
        else _attention_checkpoint_event(prior_attention_request, policy=policy)
    )
    attention_revision = 1 if checkpoint is None else int(checkpoint["revision"])
    attention_head = (
        "a" * 64 if checkpoint is None else str(checkpoint["event_sha256"])
    )
    latest_attention = {
        "status": (
            "NO_ATTENTION_REQUEST"
            if prior_attention_request is None
            else "EXACT_AGENT_ATTENTION_REQUEST"
        ),
        "source_refs": {
            "stream_revision": attention_revision,
            "stream_head_event_sha256": attention_head,
            **(
                {}
                if prior_attention_request is None
                else {
                    "attention_request_sha256": (
                        prior_attention_request.agent_owned_sha256
                    )
                }
            ),
        },
        "active_request_id": (
            None
            if prior_attention_request is None
            else prior_attention_request.request_id
        ),
        "request_status": None if prior_attention_request is None else "PENDING",
        "accepted_at": (
            None
            if prior_attention_request is None
            else checkpoint["payload"]["accepted_at"]
        ),
        "request_sha256": (
            None
            if prior_attention_request is None
            else prior_attention_request.agent_owned_sha256
        ),
        "request": (
            None
            if prior_attention_request is None
            else prior_attention_request.to_dict()
        ),
    }
    state_counts: dict[str, int] = {}
    for order in selected_account["orders"]:
        state = str(order["state"])
        state_counts[state] = state_counts.get(state, 0) + 1
    base["continuity_projection"] = {
        "schema_id": "agent-trade-emotion.v332-continuity-projection",
        "projection_version": "1.0.0",
        "authority": "NON_AUTHORITATIVE_READ_ONLY_FACT_PROJECTION",
        "source_refs": {
            "execution_intent_sha256s": [
                item.intent_sha256 for item in prior_intents
            ],
            "ledger_head_record_sha256": pre_head.record_sha256,
            "snapshot_ref": snapshot_ref.to_dict(),
            "attention_stream_revision": attention_revision,
            "attention_stream_head_event_sha256": attention_head,
            "prior_agent_texts": prior_text_sources,
        },
        "terminal_non_execution_suffix": {
            "status": "EXACT" if prior_intents else "NO_PRIOR_INTENT",
            "episode_id": None if not exact_suffix else exact_suffix[-1].episode_id,
            "length": len(exact_suffix),
            "wait_count": sum(item.action == "WAIT" for item in exact_suffix),
            "hold_count": sum(item.action == "HOLD" for item in exact_suffix),
            "watch_count": sum(item.action == "WATCH" for item in exact_suffix),
            "actions": [item.action for item in exact_suffix],
            "intent_sha256s": [item.intent_sha256 for item in exact_suffix],
            "first_transition_id": (
                None if not exact_suffix else exact_suffix[0].transition_id
            ),
            "last_transition_id": (
                None if not exact_suffix else exact_suffix[-1].transition_id
            ),
        },
        "episode_transition_tail": [
            {
                "intent_sha256": item.intent_sha256,
                "decision_cycle_id": item.decision_cycle_id,
                "decision_sha256": item.decision_sha256,
                "episode_id": item.episode_id,
                "transition_id": item.transition_id,
                "action": item.action,
                "role": item.role,
                "target_state": dict(item.target_state),
            }
            for item in episode_tail
        ],
        "latest_attention_request": latest_attention,
        "mechanical_state": {
            "status": "EXACT_MECHANICAL_FACTS",
            "source_refs": {
                "account_sha256": canonical_digest(base["account"]),
                "orders_and_fills_sha256": canonical_digest(
                    base["orders_and_fills"]
                ),
            },
            "account_version": pre_head.revision,
            "position_count": len(symbol_positions),
            "account_signed_quantity": actual_quantity,
            "open_order_count": len(selected_orders_and_fills["open_orders"]),
            "order_history_count": len(selected_orders_and_fills["order_history"]),
            "fill_count": len(selected_orders_and_fills["fills"]),
            "unresolved_order_count": len(selected_orders_and_fills["unresolved"]),
            "order_state_counts": {
                key: state_counts[key] for key in sorted(state_counts)
            },
        },
        "subjective_assessments": {
            "trigger_capture": {
                "status": "UNRESOLVED_AGENT_JUDGMENT",
                "prior_agent_declaration": (
                    None if not prior_intents else prior_intents[-1].activation
                ),
                "source_refs": (
                    {}
                    if not prior_intents
                    else {
                        "intent_sha256": prior_intents[-1].intent_sha256,
                        "source_json_pointer": "/activation",
                    }
                ),
            },
            "geometry_deterioration": {
                "status": "UNRESOLVED_AGENT_JUDGMENT",
                "prior_evidence_delta": (
                    None if not prior_intents else prior_intents[-1].evidence_delta
                ),
                "prior_hard_invalidation": (
                    None
                    if not prior_intents
                    else prior_intents[-1].hard_invalidation
                ),
                "source_refs": (
                    {}
                    if not prior_intents
                    else {
                        "intent_sha256": prior_intents[-1].intent_sha256,
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
                "source_refs": prior_text_sources,
            },
        },
    }
    base["paper_action_space"] = paper_action_space_contract(
        base, symbol=snapshot.instrument_id
    )
    return self_digest(base, "paper_context_sha256")


def _intent_request(
    *,
    request_document: dict[str, object],
    context: dict[str, object],
    hypothesis: HypothesisRecord,
    pre_head: PaperLedgerRecordV1,
    minute: int,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_id": "agent-trade-emotion.paper-execution-intent-request",
        "schema_version": "1.0.0",
        "cycle_id": hypothesis.cycle_id,
        "logical_agent_id": _AGENT,
        "agent_generation": 1,
        "physical_task_id": _PHYSICAL_TASK,
        "decision_request_sha256": request_document["packet_sha256"],
        "agent_request_document_sha256": hashlib.sha256(
            canonical_bytes(request_document) + b"\n"
        ).hexdigest(),
        "paper_context_sha256": context["paper_context_sha256"],
        "ledger_head_record_sha256": pre_head.record_sha256,
        "expected_account_version": pre_head.revision,
        "account_id": _ACCOUNT,
        "symbol": "HYPE-USDT-SWAP",
        "decision_sha256": hypothesis.agent_decision_sha256,
        "issued_at": _iso(minute, 6),
        "valid_until": _iso(minute, 30),
        "allowed_actions": sorted(PAPER_AGENT_ACTIONS),
        "output_schema_id": "agent-trade-emotion.paper-execution-intent",
        "output_schema_version": "1.3.0",
        "output_relative_path": "transport/paper-execution-intent.json",
        "instructions": "Return one Agent-owned local-paper intent.",
    }
    document["output_contract"] = _paper_output_contract(
        request=document,
        context_values=_paper_context_values(
            context, symbol="HYPE-USDT-SWAP"
        ),
    )
    return document


def _evidence(
    *,
    policy: ExperimentPolicyV1,
    minute: int,
    pre_head: PaperLedgerRecordV1,
    prior_intents: tuple[PaperExecutionIntentV1, ...],
    prior_hypothesis: HypothesisRecord | None = None,
    prior_attention_request: AttentionRequest | None = None,
    cycle_stage: str = "BEHAVIOR_PLANNED",
    exposure_projection_status: str = "DERIVED_UNAMBIGUOUS",
    account: dict[str, object] | None = None,
    orders_and_fills: dict[str, object] | None = None,
    unrealized_pnl: str = "0",
    pre_quantity: str = "0",
    target_quantity: str = "0",
    action: str | None = None,
) -> PaperDecisionEvidenceInputV1:
    cycle_id = f"hype-decision-{minute}"
    snapshot, snapshot_ref = _snapshot(cycle_id, minute)
    context = _context(
        policy=policy,
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
        pre_head=pre_head,
        prior_intents=prior_intents,
        prior_hypothesis=prior_hypothesis,
        prior_attention_request=prior_attention_request,
        exposure_projection_status=exposure_projection_status,
        account=account,
        orders_and_fills=orders_and_fills,
        unrealized_pnl=unrealized_pnl,
    )
    packet = {"cycle_id": cycle_id, "paper_context": context}
    request_document = {"packet": packet, "packet_sha256": canonical_digest(packet)}
    hypothesis = _hypothesis(
        snapshot,
        snapshot_ref,
        request_sha256=request_document["packet_sha256"],
        minute=minute,
    )
    intent_request = _intent_request(
        request_document=request_document,
        context=context,
        hypothesis=hypothesis,
        pre_head=pre_head,
        minute=minute,
    )
    selected_action = ("WAIT" if minute == 0 else "HOLD") if action is None else action
    intent = PaperExecutionIntentV1(
        intent_id=f"hype-intent-{minute}",
        execution_intent_request_sha256=hashlib.sha256(
            canonical_bytes(intent_request) + b"\n"
        ).hexdigest(),
        decision_request_sha256=request_document["packet_sha256"],
        paper_context_sha256=context["paper_context_sha256"],
        ledger_head_record_sha256=pre_head.record_sha256,
        decision_cycle_id=cycle_id,
        decision_sha256=hypothesis.agent_decision_sha256,
        account_id=_ACCOUNT,
        logical_agent_id=_AGENT,
        agent_generation=1,
        expected_account_version=pre_head.revision,
        symbol="HYPE-USDT-SWAP",
        authored_at=_iso(minute, 7),
        valid_until=_iso(minute, 20),
        action=selected_action,
        episode_id=_EPISODE,
        transition_id=f"hype-transition-{minute}",
        tranche_id="core-1",
        role="CORE",
        pre_state={
            "status": "FLAT" if pre_quantity == "0" else "ACTIVE",
            "signed_quantity": pre_quantity,
        },
        target_state={
            "status": "FLAT" if target_quantity == "0" else "ACTIVE",
            "signed_quantity": target_quantity,
        },
        position_delta={
            "action": selected_action,
            "signed_quantity_change": str(
                Decimal(target_quantity) - Decimal(pre_quantity)
            ),
        },
        evidence_delta=(
            "Initial WAIT while activation remains incomplete."
            if minute == 0
            else "Fresh mark changed, but no activation threshold was crossed."
        ),
        activation="Activate only after price and order-flow confirmation align.",
        hard_invalidation="Expire this intent at its exact valid_until boundary.",
        risk_budget={
            "maximum_loss": "50",
            "notional_cap": "500",
            "max_observed_drawdown": "100",
            "stress_note": "Modeled spread, impact and fee; funding remains UNKNOWN.",
        },
        command=None,
        wire_schema_version="1.3.0",
    )
    post_head = PaperLedgerRecordV1.create(
        account_id=_ACCOUNT,
        revision=pre_head.revision + 1,
        previous_record_sha256=pre_head.record_sha256,
        event_id=f"intent-recorded-{minute}",
        event_type="INTENT_RECORDED",
        occurred_at=_iso(minute, 8),
        payload={"execution_intent": intent.to_dict()},
    )
    return PaperDecisionEvidenceInputV1(
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
        request_document=request_document,
        paper_context=context,
        hypothesis=hypothesis,
        execution_intent_request_document=intent_request,
        execution_intent=intent,
        pre_ledger_head=pre_head,
        post_ledger_head=post_head,
        current_agent=AgentRegistry(
            logical_agent_id=_AGENT,
            symbol="HYPE-USDT-SWAP",
            generation=1,
            continuity_nonce="hype-continuity-g1",
            physical_task_id=_PHYSICAL_TASK,
            status="ACTIVE",
            registered_at="2026-08-13T11:59:00+00:00",
        ),
        cycle_stage=cycle_stage,
    )


def _opening_head() -> PaperLedgerRecordV1:
    return PaperLedgerRecordV1.create(
        account_id=_ACCOUNT,
        revision=1,
        previous_record_sha256=None,
        event_id="account-opened",
        event_type="ACCOUNT_OPENED",
        occurred_at="2026-08-13T11:59:00+00:00",
        payload={"account_id": _ACCOUNT},
    )


def _protected_position_evidence_points(
    *, unrealized_pnl: str = "-1",
    position_quantity: str = "1",
    stop_state: str = "OPEN",
    stop_remaining_quantity: str = "1",
    include_entry_fill: bool = True,
) -> tuple[
    ExperimentPolicyV1,
    tuple[PaperDecisionEvidenceInputV1, PaperDecisionEvidenceInputV1],
]:
    policy = _policy("POSITION_MANAGEMENT")
    base = _evidence(
        policy=policy,
        minute=0,
        pre_head=_opening_head(),
        prior_intents=(),
    )
    original = base.execution_intent
    entry = PaperCommandV1(
        command_id="position-entry-0",
        account_id=_ACCOUNT,
        logical_agent_id=_AGENT,
        agent_generation=1,
        decision_cycle_id=base.snapshot.cycle_id,
        decision_sha256=base.hypothesis.agent_decision_sha256,
        expected_account_version=base.pre_ledger_head.revision,
        symbol="HYPE-USDT-SWAP",
        command_type="LIMIT",
        side="BUY",
        quantity="1",
        limit_price="40",
        trigger_price=None,
        target_order_id=None,
        reduce_only=False,
        time_in_force="GTC",
        submitted_at=_iso(0, 7),
        expires_at=_iso(0, 20),
        cost_model_id="paper-cost-v1",
    )
    stop_command = replace(
        entry,
        command_id="position-stop-0",
        command_type="STOP_LOSS",
        side="SELL",
        limit_price=None,
        trigger_price="39",
        reduce_only=True,
    )
    bracket = PaperBracketV1(
        bracket_id=entry.command_id,
        entry=entry,
        protective_stop=stop_command,
        take_profits=(),
    )
    intent = replace(
        original,
        intent_id=entry.command_id,
        action="OPEN",
        target_state={"status": "ACTIVE", "signed_quantity": "1"},
        position_delta={"action": "OPEN", "signed_quantity_change": "1"},
        evidence_delta="Protected D0 bracket admitted before the actual entry fill.",
        command=entry,
        bracket=bracket,
    )
    command_head = PaperLedgerRecordV1.create(
        account_id=_ACCOUNT,
        revision=2,
        previous_record_sha256=base.pre_ledger_head.record_sha256,
        event_id="position-command-accepted",
        event_type="COMMAND_ACCEPTED",
        occurred_at=_iso(0, 8),
        payload={
            "command": entry.to_dict(),
            "commands": tuple(item.to_dict() for item in bracket.commands),
            "execution_intent": intent.to_dict(),
            "accepted_at": _iso(0, 8),
        },
    )
    d0 = replace(
        base,
        execution_intent=intent,
        post_ledger_head=command_head,
        cycle_stage="COMPLETE",
    )
    fill = FillEventV1(
        fill_id="position-entry-fill-0",
        order_id=entry.command_id,
        command_id=entry.command_id,
        account_id=_ACCOUNT,
        symbol="HYPE-USDT-SWAP",
        side="BUY",
        quantity="1",
        price="40",
        fee="0.02",
        spread_cost="0",
        impact_cost="0",
        funding_cost=None,
        funding_cost_status="UNKNOWN",
        borrow_cost=None,
        borrow_cost_status="NOT_APPLICABLE",
        realized_pnl="0",
        observed_at=_iso(1, 0),
        source_sha256="6" * 64,
        cost_model_id="paper-cost-v1",
        instrument_spec_id="hype-spec-v1",
        quantity_basis="BASE_UNITS",
        contract_multiplier="1",
        notional="40",
    )
    fill_head = PaperLedgerRecordV1.create(
        account_id=_ACCOUNT,
        revision=3,
        previous_record_sha256=command_head.record_sha256,
        event_id="position-entry-filled",
        event_type="FILL_RECORDED",
        occurred_at=_iso(1, 1),
        payload={"fill": fill.to_dict()},
    )
    stop_order = OrderTruthV1(
        order_id=stop_command.command_id,
        command_id=stop_command.command_id,
        account_id=_ACCOUNT,
        logical_agent_id=_AGENT,
        symbol="HYPE-USDT-SWAP",
        command_type="STOP_LOSS",
        side="SELL",
        original_quantity="1",
        filled_quantity=(
            "0" if stop_state == "OPEN" else str(Decimal("1") - Decimal(stop_remaining_quantity))
        ),
        remaining_quantity=stop_remaining_quantity,
        limit_price=None,
        trigger_price="39",
        reduce_only=True,
        time_in_force="GTC",
        expires_at=None,
        cost_model_id="paper-cost-v1",
        state=stop_state,
        created_at=_iso(1, 1),
        updated_at=_iso(1, 1),
        cost_model_digest="0" * 64,
    )
    account = _account(
        fill_head.revision,
        positions=(
            {
                "symbol": "HYPE-USDT-SWAP",
                "quantity": position_quantity,
                "average_entry_price": "40",
                "margin_allocated": "20",
                "realized_pnl": "0",
            },
        )
        if position_quantity != "0"
        else (),
        orders=(stop_order.to_dict(),),
    )
    orders_and_fills = {
        "account_id": _ACCOUNT,
        "open_orders": (
            [stop_order.to_dict()]
            if stop_state in {"OPEN", "PARTIALLY_FILLED"}
            else []
        ),
        "order_history": (
            []
            if stop_state in {"OPEN", "PARTIALLY_FILLED"}
            else [stop_order.to_dict()]
        ),
        "fills": [fill.to_dict()] if include_entry_fill else [],
        "unresolved": [],
    }
    d1 = _evidence(
        policy=policy,
        minute=12,
        pre_head=fill_head,
        prior_intents=(intent,),
        prior_hypothesis=d0.hypothesis,
        account=account,
        orders_and_fills=orders_and_fills,
        unrealized_pnl=unrealized_pnl,
        pre_quantity=position_quantity,
        target_quantity=position_quantity,
        action="HOLD",
    )
    return policy, (d0, d1)


def _attention_evidence(
    *,
    policy: ExperimentPolicyV1,
    position_and_open_order_ref: str | None = None,
) -> AttentionSchedulingEvidenceInputV1:
    pre_head = _opening_head()
    paper_state_ref = (
        build_paper_position_and_open_order_ref(
            account_id=_ACCOUNT,
            ledger_revision=pre_head.revision,
            ledger_head_sha256=pre_head.record_sha256,
        )
        if position_and_open_order_ref is None
        else position_and_open_order_ref
    )
    attention = AttentionRequest(
        request_id="attention-0",
        logical_agent_id=_AGENT,
        agent_generation=1,
        continuity_nonce="hype-continuity-g1",
        symbol="HYPE-USDT-SWAP",
        mode="WAKE_AFTER",
        issued_at=_iso(0, 6),
        continue_until=None,
        earliest_wake_at=_iso(0, 40),
        latest_useful_at=_iso(1, 30),
        reason_summary=(
            "WAKE_AFTER is chosen because hypothesis A remains live until the 40 "
            "invalidation; CONTINUE_NOW wastes attention before activation, STOP "
            "fits invalidation, and ESCALATE fits conflicting risk evidence."
        ),
        requested_focus=(
            "At the earliest review check activation and invalidation; by the latest "
            "useful time review opportunity cost and choose the next review."
        ),
        hypothesis_or_episode_ref="hype-decision-0",
        position_and_open_order_ref=paper_state_ref,
        data_cursor="hype-decision-0-cursor",
    )
    base = _evidence(
        policy=policy,
        minute=1,
        pre_head=pre_head,
        prior_intents=(),
        prior_attention_request=attention,
    )
    hypothesis_raw = canonical_bytes(base.hypothesis.to_dict())
    plan = BehaviorPlan(
        plan_id=f"{base.snapshot.cycle_id}.plan",
        cycle_id=base.snapshot.cycle_id,
        hypothesis_record_ref=ArtifactRef(
            artifact_type="HypothesisRecord",
            artifact_id=base.hypothesis.record_id,
            path="artifacts/hypothesis-record.json",
            size_bytes=len(hypothesis_raw),
            sha256=hashlib.sha256(hypothesis_raw).hexdigest(),
        ),
        decision_at=base.hypothesis.decision_at,
        agent_delivered_at=base.hypothesis.agent_delivered_at,
        sealed_at=base.hypothesis.sealed_at,
        risk_mode="REFERENCE",
        execution_mapping="NOT_READY",
        executable_quantity=None,
        agent_request_sha256=base.hypothesis.agent_request_sha256,
        agent_delivery_path=base.hypothesis.agent_delivery_path,
        agent_delivery_sha256=base.hypothesis.agent_delivery_sha256,
        agent_decision_text=base.hypothesis.agent_decision_text,
        agent_decision_size_bytes=base.hypothesis.agent_decision_size_bytes,
        agent_decision_sha256=base.hypothesis.agent_decision_sha256,
        projection_status=base.hypothesis.projection_status,
        projection_reason=base.hypothesis.projection_reason,
        hypothesis_index=base.hypothesis.hypothesis_index,
        agent_action_text=base.hypothesis.agent_action_text,
        agent_position_text=base.hypothesis.agent_position_text,
        outcome_due_at=base.snapshot.outcome_due_at,
        outcome_tolerance_seconds=base.snapshot.outcome_tolerance_seconds,
        theory_identity=base.hypothesis.theory_identity,
    )
    checkpoint = _attention_checkpoint_event(attention, policy=policy)
    stream_head = {
        "schema_id": "agent-trade-emotion.v332-attention-head",
        "schema_version": "1.0.0",
        "logical_agent_id": attention.logical_agent_id,
        "revision": checkpoint["revision"],
        "event_sha256": checkpoint["event_sha256"],
    }
    return AttentionSchedulingEvidenceInputV1(
        snapshot=base.snapshot,
        snapshot_ref=base.snapshot_ref,
        request_document=base.request_document,
        paper_context=base.paper_context,
        hypothesis=base.hypothesis,
        behavior_plan=plan,
        pre_ledger_head=base.pre_ledger_head,
        attention_request=attention,
        attention_checkpoint_event_document=checkpoint,
        attention_stream_head_document=stream_head,
        current_agent=AgentRegistry(
            logical_agent_id=_AGENT,
            symbol=attention.symbol,
            generation=1,
            continuity_nonce=attention.continuity_nonce,
            physical_task_id=_PHYSICAL_TASK,
            status="ACTIVE",
            registered_at="2026-08-13T11:59:00+00:00",
        ),
    )


def _finding(
    criterion: str,
    evidence: PaperDecisionEvidenceInputV1 | AttentionSchedulingEvidenceInputV1,
    *,
    source_kind: str,
    excerpt: str,
) -> PaperCapabilityFindingV1:
    return PaperCapabilityFindingV1(
        criterion_id=criterion,
        status="DEMONSTRATED",
        rationale=f"exact Agent-owned evidence for {criterion}",
        evidence_spans=(
            bind_paper_capability_span(
                evidence, source_kind=source_kind, exact_excerpt=excerpt
            ),
        ),
    )


class V332PaperCapabilityEvaluationTests(unittest.TestCase):
    def test_attention_scheduling_binds_goal_checkpoint_and_real_followup(self) -> None:
        policy = _policy("ATTENTION_SCHEDULING")
        evidence = _attention_evidence(policy=policy)
        self.assertEqual(
            build_paper_position_and_open_order_ref(
                account_id=_ACCOUNT,
                ledger_revision=evidence.pre_ledger_head.revision,
                ledger_head_sha256=evidence.pre_ledger_head.record_sha256,
            ),
            evidence.attention_request.position_and_open_order_ref,
        )
        task = build_pre_outcome_paper_capability_task(
            task_id="attention-task-001",
            capability_id="ATTENTION_SCHEDULING",
            policy=policy,
            evidence_points=(evidence,),
            subject_agent_id=_PHYSICAL_TASK,
            assessor_id=_ASSESSOR_TASK,
            created_at=_iso(1, 8),
            assessment_due_at=_iso(9, 0),
        )
        excerpts = (
            "hypothesis A remains live until the 40 invalidation",
            "At the earliest review check activation and invalidation",
            "CONTINUE_NOW wastes attention before activation, STOP fits invalidation, and ESCALATE fits conflicting risk evidence",
            "review opportunity cost and choose the next review",
        )
        findings = tuple(
            _finding(
                criterion,
                evidence,
                source_kind="ATTENTION_REQUEST",
                excerpt=excerpt,
            )
            for criterion, excerpt in zip(
                PAPER_CAPABILITY_CRITERIA["ATTENTION_SCHEDULING"], excerpts
            )
        )
        assessment = build_pre_outcome_paper_capability_assessment(
            assessment_id="attention-assessment-001",
            task=task,
            policy=policy,
            evidence_points=(evidence,),
            assessed_at=_iso(1, 9),
            findings=findings,
        )
        point = task.decision_points[0]
        self.assertEqual(_PHYSICAL_TASK, point.physical_task_id)
        self.assertEqual(
            evidence.paper_context["data_evidence"]["data_cursor"],
            point.data_cursor,
        )
        self.assertEqual(2, point.attention_checkpoint_revision)
        self.assertEqual(
            point.attention_checkpoint_event_sha256,
            point.attention_stream_head_event_sha256,
        )
        self.assertEqual(
            "WITHIN_SELF_SELECTED_WINDOW", point.followup_window_status
        )
        self.assertEqual(
            evidence.hypothesis.agent_delivered_at, point.followup_decision_at
        )
        self.assertNotIn("intent_id", point.to_dict())
        self.assertNotIn("attention_receipt_sha256", point.to_dict())
        self.assertNotIn("attention_decision_request_sha256", point.to_dict())
        self.assertNotIn("total_score", assessment.to_dict())
        self.assertIn(
            "CONTRACT_DOES_NOT_ISOLATE_ASSESSOR_FROM_EXTERNAL_MARKET_INFORMATION",
            assessment.limitations,
        )
        self.assertEqual(
            task, PreOutcomePaperCapabilityTaskV1.from_dict(task.to_dict())
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "physical Codex Goal identity"
        ):
            replace(task, subject_agent_id="logical-agent:not-physical")
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "physical Codex Goal identity"
        ):
            replace(task, assessor_id="logical-agent:not-physical")
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "physical Codex Goal identity"
        ):
            replace(assessment, assessor_id="logical-agent:not-physical")
        stale_head = dict(evidence.attention_stream_head_document)
        stale_head["event_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "checkpoint head"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="attention-stale-head",
                capability_id="ATTENTION_SCHEDULING",
                policy=policy,
                evidence_points=(
                    replace(
                        evidence,
                        attention_stream_head_document=stale_head,
                    ),
                ),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(1, 8),
                assessment_due_at=_iso(9, 0),
            )

    def test_attention_scheduling_requires_exact_frozen_paper_state_ref(self) -> None:
        policy = _policy("ATTENTION_SCHEDULING")
        head = _opening_head()
        invalid_refs = (
            build_paper_position_and_open_order_ref(
                account_id="wrong-paper-account",
                ledger_revision=head.revision,
                ledger_head_sha256=head.record_sha256,
            ),
            build_paper_position_and_open_order_ref(
                account_id=_ACCOUNT,
                ledger_revision=head.revision + 1,
                ledger_head_sha256=head.record_sha256,
            ),
            build_paper_position_and_open_order_ref(
                account_id=_ACCOUNT,
                ledger_revision=head.revision,
                ledger_head_sha256="f" * 64,
            ),
        )
        for index, invalid_ref in enumerate(invalid_refs):
            with (
                self.subTest(index=index),
                self.assertRaisesRegex(
                    PaperCapabilityEvaluationError,
                    "exact frozen paper state ref",
                ),
            ):
                build_pre_outcome_paper_capability_task(
                    task_id=f"attention-paper-state-tamper-{index}",
                    capability_id="ATTENTION_SCHEDULING",
                    policy=policy,
                    evidence_points=(
                        _attention_evidence(
                            policy=policy,
                            position_and_open_order_ref=invalid_ref,
                        ),
                    ),
                    subject_agent_id=_PHYSICAL_TASK,
                    assessor_id=_ASSESSOR_TASK,
                    created_at=_iso(1, 8),
                    assessment_due_at=_iso(9, 0),
                )

    def test_attention_scheduling_rejects_checkpoint_or_physical_agent_tamper(self) -> None:
        policy = _policy("ATTENTION_SCHEDULING")
        evidence = _attention_evidence(policy=policy)
        bad_event = dict(evidence.attention_checkpoint_event_document)
        bad_payload = dict(bad_event["payload"])
        bad_payload["accepted_at"] = _iso(0, 7)
        bad_event["payload"] = bad_payload
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "durable attention checkpoint"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="attention-bad-checkpoint",
                capability_id="ATTENTION_SCHEDULING",
                policy=policy,
                evidence_points=(
                    replace(
                        evidence,
                        attention_checkpoint_event_document=bad_event,
                    ),
                ),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(1, 8),
                assessment_due_at=_iso(9, 0),
            )

        legacy_event = dict(evidence.attention_checkpoint_event_document)
        legacy_body = dict(legacy_event)
        legacy_payload = dict(legacy_event["payload"])
        legacy_payload.pop("goal_checkpoint")
        legacy_body["payload"] = legacy_payload
        legacy_body.pop("event_sha256")
        legacy_event = {**legacy_body, "event_sha256": canonical_digest(legacy_body)}
        legacy_head = dict(evidence.attention_stream_head_document)
        legacy_head["event_sha256"] = legacy_event["event_sha256"]
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "formal Goal provenance"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="attention-legacy-checkpoint",
                capability_id="ATTENTION_SCHEDULING",
                policy=policy,
                evidence_points=(
                    replace(
                        evidence,
                        attention_checkpoint_event_document=legacy_event,
                        attention_stream_head_document=legacy_head,
                    ),
                ),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(1, 8),
                assessment_due_at=_iso(9, 0),
            )
        forged_agent = replace(
            evidence.current_agent, physical_task_id=_OTHER_PHYSICAL_TASK
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "durable attention checkpoint"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="attention-bad-agent",
                capability_id="ATTENTION_SCHEDULING",
                policy=policy,
                evidence_points=(replace(evidence, current_agent=forged_agent),),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(1, 8),
                assessment_due_at=_iso(9, 0),
            )

    def test_attention_scheduling_records_late_followup_without_rejecting_facts(self) -> None:
        policy = _policy("ATTENTION_SCHEDULING")
        evidence = _attention_evidence(policy=policy)
        late_hypothesis = replace(
            evidence.hypothesis,
            agent_delivered_at=_iso(1, 40),
            sealed_at=_iso(1, 41),
        )
        hypothesis_raw = canonical_bytes(late_hypothesis.to_dict())
        late_plan = replace(
            evidence.behavior_plan,
            hypothesis_record_ref=replace(
                evidence.behavior_plan.hypothesis_record_ref,
                size_bytes=len(hypothesis_raw),
                sha256=hashlib.sha256(hypothesis_raw).hexdigest(),
            ),
            agent_delivered_at=late_hypothesis.agent_delivered_at,
            sealed_at=_iso(1, 42),
        )
        task = build_pre_outcome_paper_capability_task(
            task_id="attention-late-followup",
            capability_id="ATTENTION_SCHEDULING",
            policy=policy,
            evidence_points=(
                replace(
                    evidence,
                    hypothesis=late_hypothesis,
                    behavior_plan=late_plan,
                ),
            ),
            subject_agent_id=_PHYSICAL_TASK,
            assessor_id=_ASSESSOR_TASK,
            created_at=_iso(1, 45),
            assessment_due_at=_iso(9, 0),
        )
        self.assertEqual(
            "AFTER_SELF_SELECTED_WINDOW",
            task.decision_points[0].followup_window_status,
        )

    def test_trading_decision_binds_one_point_without_outcome_or_total_score(self) -> None:
        policy = _policy("TRADING_DECISION")
        evidence = _evidence(
            policy=policy, minute=0, pre_head=_opening_head(), prior_intents=()
        )
        task = build_pre_outcome_paper_capability_task(
            task_id="trading-task-001",
            capability_id="TRADING_DECISION",
            policy=policy,
            evidence_points=(evidence,),
            subject_agent_id=_PHYSICAL_TASK,
            assessor_id=_ASSESSOR_TASK,
            created_at=_iso(0, 9),
            assessment_due_at=_iso(9, 0),
        )
        self.assertNotIn("attention_request_id", task.decision_points[0].to_dict())
        incomplete_request = dict(evidence.execution_intent_request_document)
        incomplete_contract = dict(incomplete_request["output_contract"])
        incomplete_constraints = dict(incomplete_contract["field_constraints"])
        incomplete_constraints.pop("activation")
        incomplete_contract["field_constraints"] = incomplete_constraints
        incomplete_request["output_contract"] = incomplete_contract
        incomplete_intent = replace(
            evidence.execution_intent,
            execution_intent_request_sha256=hashlib.sha256(
                canonical_bytes(incomplete_request) + b"\n"
            ).hexdigest(),
        )
        incomplete_post_head = PaperLedgerRecordV1.create(
            account_id=evidence.post_ledger_head.account_id,
            revision=evidence.post_ledger_head.revision,
            previous_record_sha256=(
                evidence.post_ledger_head.previous_record_sha256
            ),
            event_id=evidence.post_ledger_head.event_id,
            event_type=evidence.post_ledger_head.event_type,
            occurred_at=evidence.post_ledger_head.occurred_at,
            payload={"execution_intent": incomplete_intent.to_dict()},
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "execution intent request"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="trading-task-incomplete-output-contract",
                capability_id="TRADING_DECISION",
                policy=policy,
                evidence_points=(
                    replace(
                        evidence,
                        execution_intent_request_document=incomplete_request,
                        execution_intent=incomplete_intent,
                        post_ledger_head=incomplete_post_head,
                    ),
                ),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(0, 9),
                assessment_due_at=_iso(9, 0),
            )
        stale_request = dict(evidence.execution_intent_request_document)
        stale_contract = dict(stale_request["output_contract"])
        stale_contract["schema_version"] = "1.2.0"
        stale_request["output_contract"] = stale_contract
        stale_intent = replace(
            evidence.execution_intent,
            execution_intent_request_sha256=hashlib.sha256(
                canonical_bytes(stale_request) + b"\n"
            ).hexdigest(),
        )
        stale_post_head = PaperLedgerRecordV1.create(
            account_id=evidence.post_ledger_head.account_id,
            revision=evidence.post_ledger_head.revision,
            previous_record_sha256=(
                evidence.post_ledger_head.previous_record_sha256
            ),
            event_id=evidence.post_ledger_head.event_id,
            event_type=evidence.post_ledger_head.event_type,
            occurred_at=evidence.post_ledger_head.occurred_at,
            payload={"execution_intent": stale_intent.to_dict()},
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "execution intent request"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="trading-task-stale-output-contract",
                capability_id="TRADING_DECISION",
                policy=policy,
                evidence_points=(
                    replace(
                        evidence,
                        execution_intent_request_document=stale_request,
                        execution_intent=stale_intent,
                        post_ledger_head=stale_post_head,
                    ),
                ),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(0, 9),
                assessment_due_at=_iso(9, 0),
            )
        findings = (
            _finding(
                PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"][0],
                evidence,
                source_kind="DECISION_TEXT",
                excerpt="比较LONG_REFERENCE、SHORT_REFERENCE与WAIT；WAIT的机会成本是错过短线突破",
            ),
            _finding(
                PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"][1],
                evidence,
                source_kind="EXECUTION_INTENT",
                excerpt="Expire this intent at its exact valid_until boundary.",
            ),
            _finding(
                PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"][2],
                evidence,
                source_kind="EXECUTION_INTENT",
                excerpt='"position_delta":{"action":"WAIT","signed_quantity_change":"0"}',
            ),
            _finding(
                PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"][3],
                evidence,
                source_kind="EXECUTION_INTENT",
                excerpt="Modeled spread, impact and fee; funding remains UNKNOWN.",
            ),
            _finding(
                PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"][4],
                evidence,
                source_kind="EXECUTION_INTENT",
                excerpt="Activate only after price and order-flow confirmation align.",
            ),
        )
        assessment = build_pre_outcome_paper_capability_assessment(
            assessment_id="trading-assessment-001",
            task=task,
            policy=policy,
            evidence_points=(evidence,),
            assessed_at=_iso(0, 10),
            findings=findings,
        )
        document = assessment.to_dict()
        self.assertEqual(
            "DEMONSTRATED_ON_THIS_SAMPLE",
            document["assessment_vector"]["capability"],
        )
        self.assertTrue(
            all(
                document["assessment_vector"][key].startswith("NOT_EVALUATED")
                for key in ("prediction", "generalization", "profitability")
            )
        )
        self.assertNotIn("score", document)
        self.assertNotIn("total_score", document)
        self.assertNotIn(
            "outcome",
            inspect.signature(
                build_pre_outcome_paper_capability_assessment
            ).parameters,
        )
        self.assertEqual(
            task,
            PreOutcomePaperCapabilityTaskV1.from_dict(task.to_dict()),
        )
        self.assertEqual(
            assessment,
            PreOutcomePaperCapabilityAssessmentV1.from_dict(document),
        )
        self.assertEqual(
            PAPER_CAPABILITY_RUBRICS["TRADING_DECISION"]["rubric_sha256"],
            task.rubric["rubric_sha256"],
        )
        tampered = task.to_dict()
        tampered["rubric"]["criteria"][0]["assessment_instruction"] = "tampered"
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "frozen paper capability rubric"
        ):
            PreOutcomePaperCapabilityTaskV1.from_dict(tampered)
        tampered_assessment = document.copy()
        tampered_assessment["rubric"] = {
            **document["rubric"],
            "rubric_sha256": "0" * 64,
        }
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "frozen paper capability rubric"
        ):
            PreOutcomePaperCapabilityAssessmentV1.from_dict(tampered_assessment)

    def test_trading_decision_requires_intent_request_and_registry_same_goal_agent(
        self,
    ) -> None:
        policy = _policy("TRADING_DECISION")
        evidence = _evidence(
            policy=policy, minute=0, pre_head=_opening_head(), prior_intents=()
        )
        forged = replace(
            evidence,
            current_agent=replace(
                evidence.current_agent,
                physical_task_id=_OTHER_PHYSICAL_TASK,
            ),
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError,
            "intent request does not bind the current long-lived Goal Agent",
        ):
            build_pre_outcome_paper_capability_task(
                task_id="trading-goal-agent-mismatch",
                capability_id="TRADING_DECISION",
                policy=policy,
                evidence_points=(forged,),
                subject_agent_id=_OTHER_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(0, 9),
                assessment_due_at=_iso(9, 0),
            )

    def test_position_management_requires_fresh_same_episode_and_prior_intent(self) -> None:
        policy, (first, second) = _protected_position_evidence_points()
        task = build_pre_outcome_paper_capability_task(
            task_id="position-task-001",
            capability_id="POSITION_MANAGEMENT",
            policy=policy,
            evidence_points=(first, second),
            subject_agent_id=_PHYSICAL_TASK,
            assessor_id=_ASSESSOR_TASK,
            created_at=_iso(12, 9),
            assessment_due_at=_iso(19, 0),
        )
        review_only_latest = replace(
            task.decision_points[1],
            prior_complete_cycle_id="newer-complete-review-cycle",
            prior_complete_intent_sha256=None,
        )
        review_continuity_task = replace(
            task,
            task_id="position-task-review-only-latest",
            decision_points=(task.decision_points[0], review_only_latest),
        )
        self.assertIsNone(
            review_continuity_task.decision_points[1].prior_complete_intent_sha256
        )
        excerpts = (
            "延续同一episode",
            "Fresh mark changed, but no activation threshold was crossed.",
            '"role":"CORE"',
            "不因亏损摊平",
            "WAIT必须等到新证据越过重入阈值才解除",
        )
        kinds = (
            "DECISION_TEXT",
            "EXECUTION_INTENT",
            "EXECUTION_INTENT",
            "DECISION_TEXT",
            "DECISION_TEXT",
        )
        findings = tuple(
            _finding(
                criterion,
                second,
                source_kind=kind,
                excerpt=excerpt,
            )
            for criterion, kind, excerpt in zip(
                PAPER_CAPABILITY_CRITERIA["POSITION_MANAGEMENT"], kinds, excerpts
            )
        )
        assessment = build_pre_outcome_paper_capability_assessment(
            assessment_id="position-assessment-001",
            task=task,
            policy=policy,
            evidence_points=(first, second),
            assessed_at=_iso(12, 10),
            findings=findings,
        )
        self.assertEqual(2, len(task.decision_points))
        self.assertEqual(
            first.execution_intent.intent_sha256,
            task.decision_points[1].prior_intent_sha256s[-1],
        )
        self.assertEqual(
            "DEMONSTRATED_ON_THIS_SAMPLE",
            assessment.assessment_vector["capability"],
        )
        mechanical = task.decision_points[-1].position_mechanical_evidence
        self.assertIsNotNone(mechanical)
        self.assertEqual("LOSING_FRESH_MARK", mechanical.loss_observation_status)
        self.assertEqual("1", mechanical.entry_filled_quantity)
        self.assertEqual("1", mechanical.position_signed_quantity)
        self.assertTrue(mechanical.protective_stop_reduce_only)
        tampered_task = task.to_dict()
        tampered_task["decision_points"][-1]["position_mechanical_evidence"][
            "d1_account_sha256"
        ] = "0" * 64
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError,
            "position mechanical facts|task does not bind",
        ):
            forged = PreOutcomePaperCapabilityTaskV1.from_dict(tampered_task)
            build_pre_outcome_paper_capability_assessment(
                assessment_id="position-mechanical-tamper",
                task=forged,
                policy=policy,
                evidence_points=(first, second),
                assessed_at=_iso(12, 10),
                findings=findings,
            )

    def test_position_management_rejects_single_point_or_missing_prior_intent(self) -> None:
        policy = _policy("POSITION_MANAGEMENT")
        first = _evidence(
            policy=policy,
            minute=0,
            pre_head=_opening_head(),
            prior_intents=(),
            cycle_stage="COMPLETE",
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "at least two"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="position-too-short",
                capability_id="POSITION_MANAGEMENT",
                policy=policy,
                evidence_points=(first,),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(0, 9),
                assessment_due_at=_iso(9, 0),
            )
        second_without_prior = _evidence(
            policy=policy,
            minute=12,
            pre_head=first.post_ledger_head,
            prior_intents=(),
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError,
            "prior exact intent|Agent-authored protected bracket",
        ):
            build_pre_outcome_paper_capability_task(
                task_id="position-no-prior",
                capability_id="POSITION_MANAGEMENT",
                policy=policy,
                evidence_points=(first, second_without_prior),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(12, 9),
                assessment_due_at=_iso(19, 0),
            )

    def test_position_management_rejects_unfilled_flat_or_unprotected_state(self) -> None:
        cases = (
            ({"include_entry_fill": False}, "actual D0 entry fill"),
            ({"position_quantity": "0"}, "non-zero D1 symbol position"),
            ({"stop_state": "CANCELLED"}, "protective stop"),
            (
                {"stop_state": "PARTIALLY_FILLED", "stop_remaining_quantity": "0.5"},
                "sufficient opposite reduce-only STOP_LOSS",
            ),
        )
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs):
                policy, facts = _protected_position_evidence_points(**kwargs)
                with self.assertRaisesRegex(PaperCapabilityEvaluationError, message):
                    build_pre_outcome_paper_capability_task(
                        task_id="position-mechanical-reject",
                        capability_id="POSITION_MANAGEMENT",
                        policy=policy,
                        evidence_points=facts,
                        subject_agent_id=_PHYSICAL_TASK,
                        assessor_id=_ASSESSOR_TASK,
                        created_at=_iso(12, 9),
                        assessment_due_at=_iso(19, 0),
                    )

    def test_position_no_loss_averaging_requires_fresh_losing_state(self) -> None:
        policy, facts = _protected_position_evidence_points(unrealized_pnl="0")
        task = build_pre_outcome_paper_capability_task(
            task_id="position-nonloss-task",
            capability_id="POSITION_MANAGEMENT",
            policy=policy,
            evidence_points=facts,
            subject_agent_id=_PHYSICAL_TASK,
            assessor_id=_ASSESSOR_TASK,
            created_at=_iso(12, 9),
            assessment_due_at=_iso(19, 0),
        )
        findings = tuple(
            _finding(
                criterion,
                facts[-1],
                source_kind="DECISION_TEXT",
                excerpt="延续同一episode",
            )
            for criterion in PAPER_CAPABILITY_CRITERIA["POSITION_MANAGEMENT"]
        )
        with self.assertRaisesRegex(PaperCapabilityEvaluationError, "must remain UNRESOLVED"):
            build_pre_outcome_paper_capability_assessment(
                assessment_id="position-nonloss-assessment",
                task=task,
                policy=policy,
                evidence_points=facts,
                assessed_at=_iso(12, 10),
                findings=findings,
            )
        unresolved = tuple(
            replace(item, status="UNRESOLVED", evidence_spans=())
            if item.criterion_id == "NO_LOSS_AVERAGING"
            else item
            for item in findings
        )
        assessment = build_pre_outcome_paper_capability_assessment(
            assessment_id="position-nonloss-unresolved",
            task=task,
            policy=policy,
            evidence_points=facts,
            assessed_at=_iso(12, 10),
            findings=unresolved,
        )
        self.assertEqual(
            "UNRESOLVED_ON_THIS_SAMPLE", assessment.assessment_vector["capability"]
        )

    def test_tampered_span_head_and_non_singleton_policy_fail_closed(self) -> None:
        policy = _policy("TRADING_DECISION")
        evidence = _evidence(
            policy=policy, minute=0, pre_head=_opening_head(), prior_intents=()
        )
        task = build_pre_outcome_paper_capability_task(
            task_id="trading-task-tamper",
            capability_id="TRADING_DECISION",
            policy=policy,
            evidence_points=(evidence,),
            subject_agent_id=_PHYSICAL_TASK,
            assessor_id=_ASSESSOR_TASK,
            created_at=_iso(0, 9),
            assessment_due_at=_iso(9, 0),
        )
        valid_span = bind_paper_capability_span(
            evidence,
            source_kind="DECISION_TEXT",
            exact_excerpt="机会成本",
        )
        forged = replace(valid_span, selected_utf8_sha256="0" * 64)
        findings = tuple(
            PaperCapabilityFindingV1(
                criterion_id=criterion,
                status="DEMONSTRATED",
                rationale="forged binding fixture",
                evidence_spans=(forged,),
            )
            for criterion in PAPER_CAPABILITY_CRITERIA["TRADING_DECISION"]
        )
        with self.assertRaisesRegex(PaperCapabilityEvaluationError, "span digest"):
            build_pre_outcome_paper_capability_assessment(
                assessment_id="forged-assessment",
                task=task,
                policy=policy,
                evidence_points=(evidence,),
                assessed_at=_iso(0, 10),
                findings=findings,
            )

        forged_post = PaperLedgerRecordV1.create(
            account_id=_ACCOUNT,
            revision=evidence.pre_ledger_head.revision + 1,
            previous_record_sha256=evidence.pre_ledger_head.record_sha256,
            event_id="unrelated-market-observation",
            event_type="MARKET_OBSERVED",
            occurred_at=_iso(0, 8),
            payload={"unrelated": True},
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "post-ledger head"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="forged-head-task",
                capability_id="TRADING_DECISION",
                policy=policy,
                evidence_points=(replace(evidence, post_ledger_head=forged_post),),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(0, 9),
                assessment_due_at=_iso(9, 0),
            )

        multi_policy = replace(
            policy, capability_ids=("TRADING_DECISION", "POSITION_MANAGEMENT")
        )
        with self.assertRaisesRegex(
            PaperCapabilityEvaluationError, "singleton policy"
        ):
            build_pre_outcome_paper_capability_task(
                task_id="multi-policy-task",
                capability_id="TRADING_DECISION",
                policy=multi_policy,
                evidence_points=(evidence,),
                subject_agent_id=_PHYSICAL_TASK,
                assessor_id=_ASSESSOR_TASK,
                created_at=_iso(0, 9),
                assessment_due_at=_iso(9, 0),
            )


if __name__ == "__main__":
    unittest.main()
