from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from tests import test_theory_paper_v2_v32_agent_lifecycle as lifecycle_fixture
from tests import test_theory_paper_v2_v32_dynamic_action_plan as action_fixture
from trade_system.theory_paper_v2.application.v32_agent_semantic_compiler import (
    PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD,
    PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD,
    SELECTION_COMPILE_RECEIPT_DIGEST_FIELD,
    SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD,
    V32AgentSemanticCompilerError,
    _validate_candidate_new_evidence_binding,
    _validate_evaluation_plan_binding,
    _validate_packet_owned_fact_and_max_loss_blocks,
    _validate_zero_eligible_risk_causes,
    build_v32_proposal_semantic_output_v1,
    build_v32_selection_semantic_output_v1,
    canonical_v32_agent_semantic_json_v1,
    compile_v32_proposal_delivery_v1,
    compile_v32_selection_delivery_v1,
    verify_v32_final_action_plan_exact_match_v1,
    verify_v32_proposal_semantic_compile_receipt_v1,
    verify_v32_selection_semantic_compile_receipt_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_agent_lifecycle import (
    ACTION_EVALUATION_DIGEST_FIELD,
    ACTION_EVALUATION_SCHEMA_ID,
    AGENT_CONSUMPTION_DIGEST_FIELD,
    AGENT_CONSUMPTION_SCHEMA_ID,
    AGENT_DELIVERY_DIGEST_FIELD,
    AGENT_DELIVERY_SCHEMA_ID,
    AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    AGENT_INPUT_CONTEXT_SCHEMA_ID,
    PROPOSAL_PACKET_DIGEST_FIELD,
    PROPOSAL_PACKET_SCHEMA_ID,
    SELECTION_PACKET_DIGEST_FIELD,
    SELECTION_PACKET_SCHEMA_ID,
    build_v32_action_evaluation_v1,
    build_v32_agent_consumption_v1,
    build_v32_agent_delivery_v1,
    build_v32_agent_input_context_v1,
    build_v32_proposal_canonical_packet_v1,
    build_v32_selection_canonical_packet_v1,
)
from trade_system.theory_paper_v2.domain.v32_agent_market_graph_view import (
    seal_v32_agent_market_graph_view_v1,
)
from trade_system.theory_paper_v2.domain.v32_dynamic_action_plan import (
    NO_NEW_CURRENT_PIT_EVIDENCE_REF,
    RISK_INCREASING_ACTIONS,
    build_v32_dynamic_action_plan_v1,
)
from trade_system.theory_paper_v2.domain import v32_dynamic_research as dynamic_domain
from trade_system.theory_paper_v2.domain.v32_dynamic_research import (
    build_v32_dynamic_research_state_v1,
)


def _context(stage: str, packet: dict, *, created_at: str) -> tuple[dict, dict]:
    schema_id = (
        PROPOSAL_PACKET_SCHEMA_ID if stage == "PROPOSAL" else SELECTION_PACKET_SCHEMA_ID
    )
    digest_field = (
        PROPOSAL_PACKET_DIGEST_FIELD
        if stage == "PROPOSAL"
        else SELECTION_PACKET_DIGEST_FIELD
    )
    packet_binding = lifecycle_fixture._embedded(
        f"semantic-{stage.lower()}-packet", packet, schema_id, digest_field
    )
    context = build_v32_agent_input_context_v1(
        agent_stage=stage,
        canonical_packet=packet,
        canonical_packet_binding=packet_binding,
        created_at=created_at,
    )
    binding = lifecycle_fixture._embedded(
        f"semantic-{stage.lower()}-context",
        context,
        AGENT_INPUT_CONTEXT_SCHEMA_ID,
        AGENT_INPUT_CONTEXT_DIGEST_FIELD,
    )
    return context, binding


def _delivery_chain(
    context: dict,
    context_binding: dict,
    payload: str,
    *,
    reserved_at: str,
    delivered_at: str,
    consumed_at: str,
) -> tuple[dict, dict, dict, dict]:
    stage = context["agent_stage"].lower()
    delivery = build_v32_agent_delivery_v1(
        agent_input_context=context,
        agent_input_context_binding=context_binding,
        reserved_at=reserved_at,
        delivered_at=delivered_at,
        payload_utf8=payload,
    )
    delivery_binding = lifecycle_fixture._embedded(
        f"semantic-{stage}-delivery",
        delivery,
        AGENT_DELIVERY_SCHEMA_ID,
        AGENT_DELIVERY_DIGEST_FIELD,
    )
    consumption = build_v32_agent_consumption_v1(
        agent_input_context=context,
        agent_input_context_binding=context_binding,
        agent_delivery=delivery,
        agent_delivery_binding=delivery_binding,
        consumed_at=consumed_at,
    )
    consumption_binding = lifecycle_fixture._embedded(
        f"semantic-{stage}-consumption",
        consumption,
        AGENT_CONSUMPTION_SCHEMA_ID,
        AGENT_CONSUMPTION_DIGEST_FIELD,
    )
    return delivery, delivery_binding, consumption, consumption_binding


def _risk_arithmetic() -> dict[str, str]:
    return {
        "reference_risk_upper_bound": "1",
        "subjective_plausibility_tier": "HIGH",
        "residual_uncertainty_tier": "EXTREME_UNCERTAINTY",
        "agent_reference_risk_ceiling": "1",
        "calculation_policy": (
            "AGENT_CEILING_ONLY_UPPER_BOUND_TIMES_MIN_SUBJECTIVE_TIER_CAP_"
            "AND_COMPLEMENT_OF_RESIDUAL_UNCERTAINTY_TIER_DERIVED_BY_"
            "SEALED_PLAN"
        ),
    }


def _candidate_rows(
    plan: dict | None = None,
    *,
    risk_arithmetic: dict[str, str] | None = None,
) -> list[dict]:
    risk_digest = canonical_digest(risk_arithmetic or _risk_arithmetic())
    rows = [
        {
            "candidate_id": "open-long",
            "action_kind": "OPEN_PROBE",
            "direction": "LONG",
            "action_key": "OPEN_PROBE:LONG",
            "feasibility": "ELIGIBLE",
            "block_reasons": ["NONE"],
            "evidence_refs": ["c-long", "h-long", "z-main"],
            "risk_reference_units": "0.36",
            "risk_arithmetic_digest": risk_digest,
        },
        {
            "candidate_id": "open-short",
            "action_kind": "OPEN_PROBE",
            "direction": "SHORT",
            "action_key": "OPEN_PROBE:SHORT",
            "feasibility": "ELIGIBLE",
            "block_reasons": ["NONE"],
            "evidence_refs": ["c-short", "h-short", "z-main"],
            "risk_reference_units": "0.24",
            "risk_arithmetic_digest": risk_digest,
        },
        {
            "candidate_id": "wait",
            "action_kind": "WAIT",
            "direction": "NONE",
            "action_key": "WAIT:NONE",
            "feasibility": "ELIGIBLE",
            "block_reasons": ["NONE"],
            "evidence_refs": [],
            "risk_reference_units": "0",
            "risk_arithmetic_digest": risk_digest,
        },
    ]
    if plan is not None:
        plan_candidates = {
            row["candidate_id"]: row for row in plan["candidates"]
        }
        allocations = {
            row["cluster_id"]: row["reference_risk"]
            for row in plan["cluster_risk_allocations"]
        }
        for row in rows:
            candidate = plan_candidates[row["candidate_id"]]
            row["feasibility"] = candidate["feasibility"]
            row["block_reasons"] = [candidate["block_reason"]]
            row["evidence_refs"] = sorted(
                set(candidate["cluster_ids"])
                | set(candidate["hypothesis_ids"])
                | set(candidate["zone_ids"])
            )
            row["risk_reference_units"] = (
                str(
                    sum(
                        (
                            __import__("decimal").Decimal(
                                allocations.get(cluster_id, "0")
                            )
                            for cluster_id in candidate["cluster_ids"]
                        ),
                        __import__("decimal").Decimal("0"),
                    )
                )
                if candidate["cluster_ids"]
                else "0"
            )
    return rows


def _market_bound_dynamic_state(proposal_packet: dict) -> dict:
    """Bind the Agent fixture to exact citable PIT evidence and graph closure."""

    chain = lifecycle_fixture._formal_market_chain(
        run_id=proposal_packet["run_id"],
        cycle=proposal_packet["cycle_index"],
        decision_time=proposal_packet["decision_time"],
        authority_projection=proposal_packet["support_documents"][
            "active_authority_projection"
        ],
    )
    original = deepcopy(action_fixture._dynamic_state())
    closure_rows = [
        row
        for row in chain["graph_registry"]["evidence_dependency_closure"]
        if row["evidence_digest"]
        in chain["pit_registry"]["members"]
        and not any(
            group.startswith("AXIS:") for group in row["dependency_group_ids"]
        )
    ]
    if len(closure_rows) < 8:
        raise AssertionError("formal fixture lacks enough citable evidence")
    closure_by_digest = {
        row["evidence_digest"]: row for row in closure_rows
    }
    cursor = 0

    def evidence(count: int) -> tuple[list[str], set[str]]:
        nonlocal cursor
        selected = [closure_rows[(cursor + index) % len(closure_rows)] for index in range(count)]
        cursor += count
        return (
            sorted({row["evidence_digest"] for row in selected}),
            set().union(*(set(row["dependency_group_ids"]) for row in selected)),
        )

    common_group = closure_rows[0]["dependency_group_ids"][0]
    unknown_groups = sorted(
        group
        for group in chain["graph_registry"]["members"]
        if group.startswith("AXIS:")
    )
    unknowns = deepcopy(original["unknowns"])
    for index, row in enumerate(unknowns):
        row["dependency_refs"] = [unknown_groups[index]]

    zones = deepcopy(original["zones"])
    zone_fields = (
        "evidence_refs",
        "touch_refs",
        "reaction_refs",
        "volume_at_price_refs",
        "dwell_time_refs",
        "round_number_refs",
        "orderbook_flow_refs",
        "leverage_refs",
        "options_refs",
    )
    for row in zones:
        groups = {common_group}
        for field in zone_fields:
            refs, required = evidence(len(row[field])) if row[field] else ([], set())
            row[field] = refs
            groups.update(required)
        row["dependency_groups"] = sorted(groups)
        row["semantic_fingerprint"] = dynamic_domain._zone_fingerprint(row)

    hypotheses = deepcopy(original["hypotheses"])
    hypothesis_fields = (
        "source_refs",
        "supporting_refs",
        "opposing_refs",
        "tier_update_refs",
        "renewal_evidence_refs",
    )
    for row in hypotheses:
        groups = {common_group}
        for field in hypothesis_fields:
            refs, required = evidence(len(row[field])) if row[field] else ([], set())
            row[field] = refs
            groups.update(required)
        if row["hypothesis_id"] == "h-long":
            # This is the sole HIGH fixture.  Bind it to genuinely different
            # material observables rather than treating two timeframes from the
            # same price-candle process as independent evidence.
            admitted_datums = [
                datum
                for datum in chain["analysis_bundle"]["datums"]
                if datum["status"] != "UNKNOWN"
                and datum["pit_datum_digest"] in closure_by_digest
            ]

            def datum_for_family(family: str) -> str:
                family_group = f"OBSERVABLE_FAMILY:{family}"
                matches = sorted(
                    datum["pit_datum_digest"]
                    for datum in admitted_datums
                    if family_group
                    in closure_by_digest[datum["pit_datum_digest"]][
                        "dependency_group_ids"
                    ]
                )
                if not matches:
                    raise AssertionError(
                        f"formal fixture lacks admitted {family} evidence"
                    )
                return matches[0]

            row["source_refs"] = sorted(
                [
                    datum_for_family("PRICE_ACTION"),
                    datum_for_family("FUNDING_CROWDING"),
                ]
            )
            row["supporting_refs"] = sorted(
                [
                    datum_for_family("POSITIONING"),
                    datum_for_family("ORDERBOOK_LIQUIDITY"),
                ]
            )
            row["opposing_refs"] = [datum_for_family("TRADE_FLOW")]
            groups = {
                common_group,
                *(
                    dependency
                    for field in hypothesis_fields
                    for evidence_ref in row[field]
                    for dependency in closure_by_digest[evidence_ref][
                        "dependency_group_ids"
                    ]
                ),
            }
        row["dependency_groups"] = sorted(groups)
        row["semantic_fingerprint"] = dynamic_domain._hypothesis_fingerprint(row)

    clusters = []
    for direction, cluster_id in (
        ("LONG", "c-long"),
        ("SHORT", "c-short"),
        ("NEUTRAL", "c-neutral"),
    ):
        members = sorted(
            row["hypothesis_id"]
            for row in hypotheses
            if row["direction"] == direction
        )
        clusters.append(
            {
                "cluster_id": cluster_id,
                "member_hypothesis_ids": members,
                "direction": direction,
                "shared_dependency_groups": [common_group],
                "aggregate_tier": max(
                    (
                        row["subjective_plausibility_tier"]
                        for row in hypotheses
                        if row["hypothesis_id"] in members
                    ),
                    key={"EXTREME_UNCERTAINTY": 0, "LOW": 1, "HIGH": 2}.__getitem__,
                ),
                "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
            }
        )
    return build_v32_dynamic_research_state_v1(
        run_id=proposal_packet["run_id"],
        cycle_index=proposal_packet["cycle_index"],
        as_of=proposal_packet["decision_time"],
        frame_mode="FULL_CONTEXT",
        previous_state_digest=None,
        market_regime_state={
            "regime": "TREND_UP",
            "evidence_refs": [
                next(row for row in hypotheses if row["hypothesis_id"] == "h-long")[
                    "source_refs"
                ][0]
            ],
            "counter_evidence_refs": [
                next(row for row in hypotheses if row["hypothesis_id"] == "h-long")[
                    "opposing_refs"
                ][0]
            ],
            "regime_feature_assessments": [],
            "expires_at": original["market_regime_state"]["expires_at"],
            "previous_regime": None,
            "transition_evidence_refs": [],
        },
        unknowns=unknowns,
        zones=zones,
        hypotheses=hypotheses,
        path_modifiers=original["path_modifiers"],
        dependency_clusters=clusters,
    )


def _choppy_dynamic_state(dynamic_state: dict) -> dict:
    citable_refs = sorted(
        {
            evidence_ref
            for hypothesis in dynamic_state["hypotheses"]
            for field in ("source_refs", "supporting_refs", "opposing_refs")
            for evidence_ref in hypothesis[field]
        }
    )
    if len(citable_refs) < 4:
        raise AssertionError("fixture lacks choppy regime evidence")
    evidence_refs = citable_refs[:3]
    return build_v32_dynamic_research_state_v1(
        run_id=dynamic_state["run_id"],
        cycle_index=dynamic_state["cycle_index"],
        as_of=dynamic_state["as_of"],
        frame_mode=dynamic_state["frame_mode"],
        previous_state_digest=dynamic_state["previous_state_digest"],
        market_regime_state={
            "regime": "CHOPPY",
            "evidence_refs": evidence_refs,
            "counter_evidence_refs": [citable_refs[3]],
            "regime_feature_assessments": [
                {
                    "feature_type": "DIRECTIONAL_PERSISTENCE",
                    "feature_state": "LOW",
                    "evidence_refs": [evidence_refs[0]],
                },
                {
                    "feature_type": "REVERSAL_FREQUENCY",
                    "feature_state": "HIGH",
                    "evidence_refs": [evidence_refs[1]],
                },
                {
                    "feature_type": "EXECUTION_CHURN_PRESSURE",
                    "feature_state": "HIGH",
                    "evidence_refs": [evidence_refs[2]],
                },
            ],
            "expires_at": dynamic_state["market_regime_state"]["expires_at"],
            "previous_regime": None,
            "transition_evidence_refs": [],
        },
        unknowns=dynamic_state["unknowns"],
        zones=dynamic_state["zones"],
        hypotheses=dynamic_state["hypotheses"],
        path_modifiers=dynamic_state["path_modifiers"],
        dependency_clusters=dynamic_state["dependency_clusters"],
    )


def _residual_zero_dynamic_state(dynamic_state: dict) -> dict:
    hypotheses = deepcopy(dynamic_state["hypotheses"])
    changed = 0
    for hypothesis in hypotheses:
        if hypothesis["direction"] not in {"OTHER", "UNKNOWN"}:
            continue
        hypothesis["subjective_plausibility_tier"] = "HIGH"
        hypothesis["semantic_fingerprint"] = dynamic_domain._hypothesis_fingerprint(
            hypothesis
        )
        changed += 1
    if changed != 2:
        raise AssertionError("fixture requires exactly two residual hypotheses")
    return build_v32_dynamic_research_state_v1(
        run_id=dynamic_state["run_id"],
        cycle_index=dynamic_state["cycle_index"],
        as_of=dynamic_state["as_of"],
        frame_mode=dynamic_state["frame_mode"],
        previous_state_digest=dynamic_state["previous_state_digest"],
        market_regime_state=dynamic_state["market_regime_state"],
        unknowns=dynamic_state["unknowns"],
        zones=dynamic_state["zones"],
        hypotheses=hypotheses,
        path_modifiers=dynamic_state["path_modifiers"],
        dependency_clusters=dynamic_state["dependency_clusters"],
    )


def _plan_variants(
    dynamic_state: dict,
    *,
    max_wait_cycles_before_review: int = 8,
    max_inactivity_seconds: int = 7200,
    reference_input_overrides: dict[str, str] | None = None,
    tranche_field_overrides: dict | None = None,
) -> list[dict]:
    variants: list[dict] = []
    candidate_order = ["open-long", "open-short", "wait"]
    for selected in candidate_order:
        args = deepcopy(action_fixture._flat_args(dynamic_state=dynamic_state))
        for tranche in args["risk_tranches"]:
            tranche.update(tranche_field_overrides or {})
            entry = Decimal(tranche["conditional_entry_reference"])
            exposure = Decimal("0.01")
            objective_inputs = {
                "multiplier_reference": "0.01",
                "fee_stress_reference": canonical_decimal(
                    exposure * entry * Decimal("0.002")
                ),
                "slippage_stress_reference": canonical_decimal(
                    exposure * entry * Decimal("0.001")
                ),
                "funding_bound_reference": canonical_decimal(
                    exposure * entry * Decimal("0.001")
                ),
                "tail_gap_reference": canonical_decimal(
                    exposure * entry * Decimal("0.005")
                ),
                "reference_scale_quantum": "0.01",
            }
            objective_inputs.update(reference_input_overrides or {})
            tranche.update(objective_inputs)
        args["wait_assessment"]["review_deadline"] = "2026-08-07T00:30:00Z"
        args["inactivity_opportunity_watchdog"][
            "next_watchdog_review_at"
        ] = "2026-08-07T00:30:00Z"
        args["inactivity_opportunity_watchdog"]["inactivity_since"] = (
            dynamic_state["as_of"]
        )
        args["inactivity_opportunity_watchdog"][
            "model_adaptation_inactivity_since"
        ] = dynamic_state["as_of"]
        clusters = {
            row["cluster_id"]: row for row in dynamic_state["dependency_clusters"]
        }
        pit_refs = sorted(
            {
                ref
                for row in dynamic_state["hypotheses"]
                for field in ("source_refs", "supporting_refs", "opposing_refs")
                for ref in row[field]
            }
            | {
                ref
                for row in dynamic_state["zones"]
                for field in (
                    "evidence_refs",
                    "touch_refs",
                    "reaction_refs",
                    "volume_at_price_refs",
                    "dwell_time_refs",
                    "round_number_refs",
                    "orderbook_flow_refs",
                    "leverage_refs",
                    "options_refs",
                )
                for ref in row[field]
            }
        )
        for candidate in args["candidates"]:
            if candidate["cluster_ids"]:
                candidate["hypothesis_ids"] = sorted(
                    {
                        hypothesis_id
                        for cluster_id in candidate["cluster_ids"]
                        for hypothesis_id in clusters[cluster_id][
                            "member_hypothesis_ids"
                        ]
                    }
                )
        for obligation in args["reentry_obligations"]:
            obligation["parent_hypothesis_ids"] = sorted(
                {
                    hypothesis_id
                    for cluster_id in obligation["supporting_cluster_ids"]
                    for hypothesis_id in clusters[cluster_id][
                        "member_hypothesis_ids"
                    ]
                }
            )
        args["inactivity_opportunity_watchdog"][
            "max_wait_cycles_before_review"
        ] = max_wait_cycles_before_review
        args["inactivity_opportunity_watchdog"][
            "max_inactivity_seconds"
        ] = max_inactivity_seconds
        args["selected_candidate_id"] = selected
        args["alternative_candidate_rank"] = [
            candidate_id for candidate_id in candidate_order if candidate_id != selected
        ]
        if selected == "wait":
            args["wait_assessment"] = action_fixture._wait(
                [
                    {
                        "candidate_id": candidate_id,
                        "dominance_reason": (
                            "INFORMATION_VALUE_DOMINATES_UNTIL_DEADLINE"
                        ),
                        "evidence_refs": [
                            f"distinguishing-observation:{candidate_id}"
                        ],
                        "rationale": (
                            "one bounded observation dominates immediate reference risk"
                        ),
                    }
                    for candidate_id in ("open-long", "open-short")
                ]
            )
            args["wait_assessment"]["review_deadline"] = (
                "2026-08-07T00:30:00Z"
            )
        plan = build_v32_dynamic_action_plan_v1(**args)
        variants.append(
            {
                "variant_id": f"variant::{selected}",
                "candidate_id": selected,
                "dynamic_action_plan": plan,
                "dynamic_action_plan_digest": plan["dynamic_action_plan_digest"],
            }
        )
    return sorted(variants, key=lambda row: row["candidate_id"])


def _zero_risk_variants(
    dynamic_state: dict,
    *,
    block_reason: str = "COST_OR_LIQUIDITY",
    blocking_evidence_refs: list[str] | None = None,
) -> list[dict]:
    args = deepcopy(action_fixture._flat_args(dynamic_state=dynamic_state))
    clusters = {
        row["cluster_id"]: row for row in dynamic_state["dependency_clusters"]
    }
    for candidate in args["candidates"]:
        if candidate["cluster_ids"]:
            candidate["hypothesis_ids"] = sorted(
                {
                    hypothesis_id
                    for cluster_id in candidate["cluster_ids"]
                    for hypothesis_id in clusters[cluster_id][
                        "member_hypothesis_ids"
                    ]
                }
            )
        if candidate["action_kind"] == "OPEN_PROBE":
            candidate.update(
                {
                    "feasibility": "BLOCKED",
                    "block_reason": block_reason,
                    "blocking_evidence_refs": sorted(
                        blocking_evidence_refs
                        or ["objective-reference-risk-inputs-unavailable"]
                    ),
                    "risk_tranche_id": None,
                }
            )
    args["risk_tranches"] = []
    args["reentry_obligations"] = []
    args["selected_candidate_id"] = "wait"
    args["alternative_candidate_rank"] = ["open-long", "open-short"]
    args["wait_assessment"]["review_deadline"] = "2026-08-07T00:30:00Z"
    args["inactivity_opportunity_watchdog"]["next_watchdog_review_at"] = (
        "2026-08-07T00:30:00Z"
    )
    args["inactivity_opportunity_watchdog"]["inactivity_since"] = dynamic_state[
        "as_of"
    ]
    args["inactivity_opportunity_watchdog"][
        "model_adaptation_inactivity_since"
    ] = dynamic_state["as_of"]
    plan = build_v32_dynamic_action_plan_v1(**args)
    return [
        {
            "variant_id": "variant::wait",
            "candidate_id": "wait",
            "dynamic_action_plan": plan,
            "dynamic_action_plan_digest": plan["dynamic_action_plan_digest"],
        }
    ]


def _packet_without_contract_datum(packet: dict, datum_id: str) -> dict:
    documents = deepcopy(packet["support_documents"])
    view = deepcopy(documents["agent_market_graph_view"])
    before = len(view["current_non_bar_datums"])
    view["current_non_bar_datums"] = [
        row
        for row in view["current_non_bar_datums"]
        if row["datum_id"] != datum_id
    ]
    if len(view["current_non_bar_datums"]) != before - 1:
        raise AssertionError(f"fixture datum not found: {datum_id}")
    view["content_counts"]["current_non_bar_datum_count"] -= 1
    view = seal_v32_agent_market_graph_view_v1(view)
    documents["agent_market_graph_view"] = view
    bindings = deepcopy(packet["support_bindings"])
    bindings["agent_market_graph_view"] = lifecycle_fixture._embedded(
        "semantic-agent-market-view-missing-contract-spec",
        view,
        "theory_paper_v32_agent_market_graph_view_v1",
        "agent_market_graph_view_digest",
    )
    return build_v32_proposal_canonical_packet_v1(
        run_id=packet["run_id"],
        cycle_index=packet["cycle_index"],
        context_profile=packet["context_profile"],
        context_mode=packet["context_mode"],
        prepared_at=packet["prepared_at"],
        decision_time=packet["decision_time"],
        authority_document=packet["authority_document"],
        authority_binding=packet["authority_binding"],
        theory_semantic_document=packet["theory_semantic_document"],
        theory_semantic_document_binding=packet[
            "theory_semantic_document_binding"
        ],
        support_documents=documents,
        support_bindings=bindings,
        previous_dynamic_research_state=packet[
            "previous_dynamic_research_state"
        ],
        previous_dynamic_research_state_binding=packet[
            "previous_dynamic_research_state_binding"
        ],
        previous_dynamic_action_plan=packet["previous_dynamic_action_plan"],
        previous_dynamic_action_plan_binding=packet[
            "previous_dynamic_action_plan_binding"
        ],
        previous_timeframe_context_state=packet[
            "previous_timeframe_context_state"
        ],
        previous_timeframe_context_state_binding=packet[
            "previous_timeframe_context_state_binding"
        ],
        matured_outcome_receipts=packet["matured_outcome_receipts"],
        matured_outcome_receipt_bindings=packet[
            "matured_outcome_receipt_bindings"
        ],
    )


def _selection_fixture_for_proposal(
    *,
    proposal_context: dict,
    proposal_context_binding: dict,
    proposal_output: dict,
    selected_candidate_id: str,
) -> dict:
    proposal_payload = canonical_v32_agent_semantic_json_v1(proposal_output)
    (
        proposal_delivery,
        proposal_delivery_binding,
        proposal_consumption,
        proposal_consumption_binding,
    ) = _delivery_chain(
        proposal_context,
        proposal_context_binding,
        proposal_payload,
        reserved_at="2026-08-07T00:16:10Z",
        delivered_at="2026-08-07T00:16:20Z",
        consumed_at="2026-08-07T00:16:30Z",
    )
    proposal_receipt = compile_v32_proposal_delivery_v1(
        proposal_input_context=proposal_context,
        proposal_delivery=proposal_delivery,
        proposal_consumption=proposal_consumption,
        compiled_at="2026-08-07T00:16:40Z",
    )
    dynamic_binding = lifecycle_fixture._embedded(
        "semantic-zero-risk-compiled-dynamic",
        proposal_receipt["compiled_dynamic_research_state"],
        "theory_paper_v32_dynamic_research_state_v1",
        "dynamic_research_state_digest",
    )
    evaluation_binding = lifecycle_fixture._embedded(
        "semantic-zero-risk-sealed-evaluation",
        proposal_receipt["sealed_action_evaluation"],
        ACTION_EVALUATION_SCHEMA_ID,
        ACTION_EVALUATION_DIGEST_FIELD,
    )
    selection_packet = build_v32_selection_canonical_packet_v1(
        proposal_input_context=proposal_context,
        proposal_input_context_binding=proposal_context_binding,
        proposal_delivery=proposal_delivery,
        proposal_delivery_binding=proposal_delivery_binding,
        proposal_consumption=proposal_consumption,
        proposal_consumption_binding=proposal_consumption_binding,
        compiled_dynamic_research_state=proposal_receipt[
            "compiled_dynamic_research_state"
        ],
        compiled_dynamic_research_state_binding=dynamic_binding,
        sealed_action_evaluation=proposal_receipt["sealed_action_evaluation"],
        sealed_action_evaluation_binding=evaluation_binding,
        prepared_at="2026-08-07T00:16:45Z",
    )
    selection_context, selection_context_binding = _context(
        "SELECTION", selection_packet, created_at="2026-08-07T00:16:50Z"
    )
    selection_output = build_v32_selection_semantic_output_v1(
        selection_input_context=selection_context,
        selected_candidate_id=selected_candidate_id,
    )
    selection_payload = canonical_v32_agent_semantic_json_v1(selection_output)
    (
        selection_delivery,
        selection_delivery_binding,
        selection_consumption,
        selection_consumption_binding,
    ) = _delivery_chain(
        selection_context,
        selection_context_binding,
        selection_payload,
        reserved_at="2026-08-07T00:17:00Z",
        delivered_at="2026-08-07T00:17:10Z",
        consumed_at="2026-08-07T00:17:20Z",
    )
    selection_receipt = compile_v32_selection_delivery_v1(
        proposal_compile_receipt=proposal_receipt,
        selection_input_context=selection_context,
        selection_delivery=selection_delivery,
        selection_consumption=selection_consumption,
        compiled_at="2026-08-07T00:17:30Z",
    )
    return locals()


_DEFAULT_FULL_FIXTURE_TEMPLATE: dict | None = None


def _build_full_fixture(
    *,
    max_wait_cycles_before_review: int = 8,
    max_inactivity_seconds: int = 7200,
) -> dict:
    proposal_packet = lifecycle_fixture._proposal_packet()
    proposal_context, proposal_context_binding = _context(
        "PROPOSAL", proposal_packet, created_at="2026-08-07T00:16:00Z"
    )
    dynamic = _market_bound_dynamic_state(proposal_packet)
    variants = _plan_variants(
        dynamic,
        max_wait_cycles_before_review=max_wait_cycles_before_review,
        max_inactivity_seconds=max_inactivity_seconds,
    )
    proposal_output = build_v32_proposal_semantic_output_v1(
        proposal_input_context=proposal_context,
        current_dynamic_research_state=dynamic,
        reference_context="FLAT_RESEARCH_INTENT",
        risk_arithmetic=_risk_arithmetic(),
        candidate_rows=_candidate_rows(variants[0]["dynamic_action_plan"]),
        sealed_plan_variants=variants,
    )
    proposal_payload = canonical_v32_agent_semantic_json_v1(proposal_output)
    (
        proposal_delivery,
        proposal_delivery_binding,
        proposal_consumption,
        proposal_consumption_binding,
    ) = _delivery_chain(
        proposal_context,
        proposal_context_binding,
        proposal_payload,
        reserved_at="2026-08-07T00:16:10Z",
        delivered_at="2026-08-07T00:16:20Z",
        consumed_at="2026-08-07T00:16:30Z",
    )
    proposal_receipt = compile_v32_proposal_delivery_v1(
        proposal_input_context=proposal_context,
        proposal_delivery=proposal_delivery,
        proposal_consumption=proposal_consumption,
        compiled_at="2026-08-07T00:16:40Z",
    )
    dynamic_binding = lifecycle_fixture._embedded(
        "semantic-compiled-dynamic",
        proposal_receipt["compiled_dynamic_research_state"],
        "theory_paper_v32_dynamic_research_state_v1",
        "dynamic_research_state_digest",
    )
    evaluation_binding = lifecycle_fixture._embedded(
        "semantic-sealed-evaluation",
        proposal_receipt["sealed_action_evaluation"],
        ACTION_EVALUATION_SCHEMA_ID,
        ACTION_EVALUATION_DIGEST_FIELD,
    )
    selection_packet = build_v32_selection_canonical_packet_v1(
        proposal_input_context=proposal_context,
        proposal_input_context_binding=proposal_context_binding,
        proposal_delivery=proposal_delivery,
        proposal_delivery_binding=proposal_delivery_binding,
        proposal_consumption=proposal_consumption,
        proposal_consumption_binding=proposal_consumption_binding,
        compiled_dynamic_research_state=proposal_receipt[
            "compiled_dynamic_research_state"
        ],
        compiled_dynamic_research_state_binding=dynamic_binding,
        sealed_action_evaluation=proposal_receipt["sealed_action_evaluation"],
        sealed_action_evaluation_binding=evaluation_binding,
        prepared_at="2026-08-07T00:16:45Z",
    )
    selection_context, selection_context_binding = _context(
        "SELECTION", selection_packet, created_at="2026-08-07T00:16:50Z"
    )
    selection_output = build_v32_selection_semantic_output_v1(
        selection_input_context=selection_context,
        selected_candidate_id="open-short",
    )
    selection_payload = canonical_v32_agent_semantic_json_v1(selection_output)
    (
        selection_delivery,
        selection_delivery_binding,
        selection_consumption,
        selection_consumption_binding,
    ) = _delivery_chain(
        selection_context,
        selection_context_binding,
        selection_payload,
        reserved_at="2026-08-07T00:17:00Z",
        delivered_at="2026-08-07T00:17:10Z",
        consumed_at="2026-08-07T00:17:20Z",
    )
    selection_receipt = compile_v32_selection_delivery_v1(
        proposal_compile_receipt=proposal_receipt,
        selection_input_context=selection_context,
        selection_delivery=selection_delivery,
        selection_consumption=selection_consumption,
        compiled_at="2026-08-07T00:17:30Z",
    )
    return locals()


def _full_fixture(
    *,
    max_wait_cycles_before_review: int = 8,
    max_inactivity_seconds: int = 7200,
) -> dict:
    """Reuse only the default fixture shape and never expose mutable state."""
    global _DEFAULT_FULL_FIXTURE_TEMPLATE
    if (
        max_wait_cycles_before_review != 8
        or max_inactivity_seconds != 7200
    ):
        return _build_full_fixture(
            max_wait_cycles_before_review=max_wait_cycles_before_review,
            max_inactivity_seconds=max_inactivity_seconds,
        )
    if _DEFAULT_FULL_FIXTURE_TEMPLATE is None:
        built = _build_full_fixture(
            max_wait_cycles_before_review=8,
            max_inactivity_seconds=7200,
        )
        _DEFAULT_FULL_FIXTURE_TEMPLATE = deepcopy(built)
    return deepcopy(_DEFAULT_FULL_FIXTURE_TEMPLATE)


class V32AgentSemanticFixtureCacheTests(unittest.TestCase):
    def test_default_fixture_is_cached_and_cloned_while_variants_build_fresh(
        self,
    ) -> None:
        global _DEFAULT_FULL_FIXTURE_TEMPLATE
        saved = deepcopy(_DEFAULT_FULL_FIXTURE_TEMPLATE)
        _DEFAULT_FULL_FIXTURE_TEMPLATE = None

        def fake_builder(
            *, max_wait_cycles_before_review, max_inactivity_seconds
        ):
            return {
                "wait": max_wait_cycles_before_review,
                "inactivity": max_inactivity_seconds,
                "nested": {"value": "original"},
            }

        try:
            with unittest.mock.patch(
                f"{__name__}._build_full_fixture", side_effect=fake_builder
            ) as builder:
                first = _full_fixture()
                first["nested"]["value"] = "mutated"
                second = _full_fixture()
                variant_first = _full_fixture(max_wait_cycles_before_review=9)
                variant_second = _full_fixture(max_wait_cycles_before_review=9)

            self.assertEqual("original", second["nested"]["value"])
            self.assertIsNot(first, second)
            self.assertIsNot(variant_first, variant_second)
            self.assertEqual(3, builder.call_count)
        finally:
            _DEFAULT_FULL_FIXTURE_TEMPLATE = saved


class V32AgentSemanticRiskBindingUnitTests(unittest.TestCase):
    def test_compiler_binds_residual_tier_and_its_deterministic_complement(
        self,
    ) -> None:
        plan = build_v32_dynamic_action_plan_v1(**action_fixture._flat_args())
        evaluation = {
            "risk_arithmetic": _risk_arithmetic(),
            "candidate_rows": _candidate_rows(plan),
        }
        _validate_evaluation_plan_binding(evaluation=evaluation, plan=plan)
        self.assertEqual(
            100,
            plan["residual_uncertainty_cap_units"],
        )

        drifted = deepcopy(evaluation)
        drifted["risk_arithmetic"]["residual_uncertainty_tier"] = "LOW"
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_RISK_ARITHMETIC_BINDING_INVALID",
        ):
            _validate_evaluation_plan_binding(evaluation=drifted, plan=plan)

    def test_new_risk_evidence_uses_sealed_availability_not_prior_citation(self) -> None:
        old_digest = "1" * 64
        fresh_digest = "2" * 64
        opposing_only_digest = "3" * 64
        invented_digest = "4" * 64
        packet = {
            "decision_time": "2026-08-07T00:30:00Z",
            "previous_dynamic_research_state": {
                "as_of": "2026-08-07T00:15:00Z"
            },
            "support_documents": {
                "agent_market_graph_view": {
                    "citable_evidence_records": [
                        {
                            "evidence_digest": old_digest,
                            "available_at": "2026-08-07T00:14:00Z",
                        },
                        {
                            "evidence_digest": fresh_digest,
                            "available_at": "2026-08-07T00:16:00Z",
                        },
                        {
                            "evidence_digest": opposing_only_digest,
                            "available_at": "2026-08-07T00:17:00Z",
                        },
                    ]
                }
            },
        }

        def state(
            *, supporting_refs: list[str], opposing_refs: list[str] | None = None
        ) -> dict:
            return {
                "as_of": "2026-08-07T00:30:00Z",
                "hypotheses": [
                    {
                        "hypothesis_id": "h-long",
                        "source_refs": [],
                        "supporting_refs": supporting_refs,
                        "opposing_refs": opposing_refs or [],
                        "tier_update_refs": [],
                        "renewal_evidence_refs": [],
                    }
                ]
            }

        def variants(
            *,
            new_evidence_refs: list[str],
            feasibility: str = "ELIGIBLE",
            block_reason: str = "NONE",
            blocking_evidence_refs: list[str] | None = None,
        ) -> list[dict]:
            return [
                {
                    "dynamic_action_plan": {
                        "candidates": [
                            {
                                "action_kind": "ADD",
                                "hypothesis_ids": ["h-long"],
                                "new_evidence_refs": new_evidence_refs,
                                "feasibility": feasibility,
                                "block_reason": block_reason,
                                "blocking_evidence_refs": (
                                    blocking_evidence_refs or []
                                ),
                            }
                        ]
                    }
                }
            ]

        # An old datum remains old even when the predecessor Agent omitted it.
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_NEW_EVIDENCE_BINDING_INVALID",
        ):
            _validate_candidate_new_evidence_binding(
                proposal_packet=packet,
                dynamic_state=state(supporting_refs=[old_digest]),
                variants=variants(new_evidence_refs=[old_digest]),
            )

        # An arbitrary string and fresh counter-evidence cannot authorize more risk.
        for supplied, current_state in (
            (
                invented_digest,
                state(supporting_refs=[invented_digest]),
            ),
            (
                opposing_only_digest,
                state(
                    supporting_refs=[old_digest],
                    opposing_refs=[opposing_only_digest],
                ),
            ),
        ):
            with self.subTest(supplied=supplied), self.assertRaisesRegex(
                V32AgentSemanticCompilerError,
                "V32_AGENT_NEW_EVIDENCE_BINDING_INVALID",
            ):
                _validate_candidate_new_evidence_binding(
                    proposal_packet=packet,
                    dynamic_state=current_state,
                    variants=variants(new_evidence_refs=[supplied]),
                )

        _validate_candidate_new_evidence_binding(
            proposal_packet=packet,
            dynamic_state=state(supporting_refs=[fresh_digest]),
            variants=variants(new_evidence_refs=[fresh_digest]),
        )
        _validate_candidate_new_evidence_binding(
            proposal_packet=packet,
            dynamic_state=state(supporting_refs=[old_digest]),
            variants=variants(
                new_evidence_refs=[],
                feasibility="BLOCKED",
                block_reason="NO_NEW_EVIDENCE",
                blocking_evidence_refs=[NO_NEW_CURRENT_PIT_EVIDENCE_REF],
            ),
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_NEW_EVIDENCE_BINDING_INVALID",
        ):
            _validate_candidate_new_evidence_binding(
                proposal_packet=packet,
                dynamic_state=state(supporting_refs=[fresh_digest]),
                variants=variants(
                    new_evidence_refs=[],
                    feasibility="BLOCKED",
                    block_reason="NO_NEW_EVIDENCE",
                    blocking_evidence_refs=[NO_NEW_CURRENT_PIT_EVIDENCE_REF],
                ),
            )

    def test_candidate_fact_and_max_loss_blocks_require_packet_owner(self) -> None:
        packet = lifecycle_fixture._proposal_packet()
        dynamic = _market_bound_dynamic_state(packet)
        long_candidate = deepcopy(action_fixture._flat_args()["candidates"][0])
        long_candidate["hypothesis_ids"] = ["h-long"]
        fake_unknown = next(
            row
            for row in dynamic["unknowns"]
            if row["unknown_type"] == "UNKNOWN_FACT_INTEGRITY"
        )
        fake_unknown["dependency_refs"] = ["REQUEST:FUNDING_RATE"]
        long_candidate.update(
            {
                "block_reason": "FACT_INTEGRITY",
                "blocking_unknown_ids": [fake_unknown["unknown_id"]],
            }
        )

        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_RISK_BLOCK_CAUSE_INVALID",
        ):
            _validate_packet_owned_fact_and_max_loss_blocks(
                proposal_packet=packet,
                dynamic_state=dynamic,
                candidate=long_candidate,
                error_code="V32_AGENT_RISK_BLOCK_CAUSE_INVALID",
            )

        max_loss_candidate = deepcopy(long_candidate)
        max_loss_candidate["block_reason"] = "MAX_LOSS"
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_RISK_BLOCK_CAUSE_INVALID",
        ):
            _validate_packet_owned_fact_and_max_loss_blocks(
                proposal_packet=packet,
                dynamic_state=dynamic,
                candidate=max_loss_candidate,
                error_code="V32_AGENT_RISK_BLOCK_CAUSE_INVALID",
            )

        unknown_datum = self_digest(
            {
                "schema_id": "theory_paper_v32_minimal_pit_datum_v1",
                "schema_version": "1.1.0",
                "instrument_id": "BTC-USDT-SWAP",
                "source_component_id": "FUNDING_RATE",
                "source_event_id": "okx-public-request:funding_rate",
                "metric_kind": "FUNDING_RATE",
                "status": "UNKNOWN",
                "value": None,
                "unit": None,
                "provider_observed_at": None,
                "observed_at": None,
                "available_at": "2026-08-07T00:14:00Z",
                "effective_at": None,
                "provider_clock_ahead_milliseconds": None,
                "clock_uncertainty_status": "UNKNOWN",
                "raw_binding": None,
                "reason_code": "PUBLIC_SOURCE_UNAVAILABLE",
                "derivation": "NOT_DERIVED_SOURCE_UNKNOWN",
                "point_in_time": True,
                "missing_is_zero": False,
                "dependency_group_ids": ["REQUEST:FUNDING_RATE"],
            },
            "pit_datum_digest",
        )
        unknown_digest = unknown_datum["pit_datum_digest"]
        owned_packet = {
            "decision_time": "2026-08-07T00:15:00Z",
            "support_documents": {
                "agent_market_graph_view": {
                    "instrument": {"instrument_id": "BTC-USDT-SWAP"},
                    "current_non_bar_datums": [unknown_datum],
                    "source_event_claim_ceilings": [
                        {"component_id": "FUNDING_RATE", "status": "UNKNOWN"}
                    ],
                    "citable_evidence_records": [
                        {
                            "evidence_digest": unknown_digest,
                            "closure_status": "VERIFIED_COMPLETE_GRAPH_CLOSURE",
                            "dependency_group_ids": ["REQUEST:FUNDING_RATE"],
                        }
                    ],
                }
            },
        }
        owned_state = {
            "unknowns": [
                {
                    "unknown_id": "u-funding",
                    "unknown_type": "UNKNOWN_FACT_INTEGRITY",
                    "dependency_refs": ["REQUEST:FUNDING_RATE"],
                }
            ],
            "hypotheses": [
                {
                    "hypothesis_id": "h-long",
                    "source_refs": [unknown_digest],
                    "supporting_refs": [],
                    "opposing_refs": [],
                    "tier_update_refs": [],
                    "renewal_evidence_refs": [],
                }
            ],
            "zones": [],
        }
        owned_candidate = {
            "block_reason": "FACT_INTEGRITY",
            "blocking_unknown_ids": ["u-funding"],
            "hypothesis_ids": ["h-long"],
            "zone_ids": [],
        }
        self.assertTrue(
            _validate_packet_owned_fact_and_max_loss_blocks(
                proposal_packet=owned_packet,
                dynamic_state=owned_state,
                candidate=owned_candidate,
                error_code="V32_AGENT_RISK_BLOCK_CAUSE_INVALID",
            )
        )


class V32AgentSemanticCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = _full_fixture()

    def _proposal_chain_for_payload(self, payload: str):
        return _delivery_chain(
            self.fx["proposal_context"],
            self.fx["proposal_context_binding"],
            payload,
            reserved_at="2026-08-07T00:16:10Z",
            delivered_at="2026-08-07T00:16:20Z",
            consumed_at="2026-08-07T00:16:30Z",
        )

    def _selection_chain_for_payload(self, payload: str):
        return _delivery_chain(
            self.fx["selection_context"],
            self.fx["selection_context_binding"],
            payload,
            reserved_at="2026-08-07T00:17:00Z",
            delivered_at="2026-08-07T00:17:10Z",
            consumed_at="2026-08-07T00:17:20Z",
        )

    def test_two_stage_round_trip_binds_exact_bytes_and_consumptions(self) -> None:
        proposal_receipt = self.fx["proposal_receipt"]
        selection_receipt = self.fx["selection_receipt"]
        self.assertEqual(
            proposal_receipt["proposal_semantic_output_digest"],
            self.fx["proposal_output"][PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD],
        )
        self.assertEqual(
            proposal_receipt["proposal_consumption_digest"],
            self.fx["proposal_consumption"][AGENT_CONSUMPTION_DIGEST_FIELD],
        )
        self.assertEqual(selection_receipt["selected_candidate_id"], "open-short")
        self.assertEqual(
            selection_receipt["selection_consumption_digest"],
            self.fx["selection_consumption"][AGENT_CONSUMPTION_DIGEST_FIELD],
        )
        self.assertEqual(
            verify_v32_proposal_semantic_compile_receipt_v1(
                proposal_receipt,
                proposal_input_context=self.fx["proposal_context"],
                proposal_delivery=self.fx["proposal_delivery"],
                proposal_consumption=self.fx["proposal_consumption"],
            ),
            proposal_receipt[PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD],
        )
        self.assertEqual(
            verify_v32_selection_semantic_compile_receipt_v1(
                selection_receipt,
                proposal_compile_receipt=proposal_receipt,
                selection_input_context=self.fx["selection_context"],
                selection_delivery=self.fx["selection_delivery"],
                selection_consumption=self.fx["selection_consumption"],
            ),
            selection_receipt[SELECTION_COMPILE_RECEIPT_DIGEST_FIELD],
        )

    def test_every_eligible_candidate_has_exactly_one_variant(self) -> None:
        receipt = self.fx["proposal_receipt"]
        self.assertEqual(
            sorted(row["candidate_id"] for row in receipt["sealed_plan_variants"]),
            receipt["eligible_candidate_ids"],
        )
        self.assertEqual(len(receipt["sealed_plan_variants"]), 3)

    def test_evaluation_and_plan_share_one_post_modifier_risk_truth(self) -> None:
        evaluation_rows = {
            row["candidate_id"]: row
            for row in self.fx["proposal_receipt"]["sealed_action_evaluation"][
                "candidate_rows"
            ]
        }
        for variant in self.fx["proposal_receipt"]["sealed_plan_variants"]:
            with self.subTest(candidate_id=variant["candidate_id"]):
                plan = variant["dynamic_action_plan"]
                self.assertEqual(
                    plan["selected_candidate_reference_risk_budget"],
                    evaluation_rows[variant["candidate_id"]][
                        "risk_reference_units"
                    ],
                )
                self.assertEqual(
                    plan["current_executable_reference_risk_budget"], "0"
                )

    def test_objective_reference_inputs_are_derived_per_tranche(self) -> None:
        rates = {
            "fee_stress_reference": Decimal("0.002"),
            "slippage_stress_reference": Decimal("0.001"),
            "funding_bound_reference": Decimal("0.001"),
            "tail_gap_reference": Decimal("0.005"),
        }
        for variant in self.fx["proposal_receipt"]["sealed_plan_variants"]:
            for tranche in variant["dynamic_action_plan"]["risk_tranches"]:
                with self.subTest(tranche_id=tranche["tranche_id"]):
                    exposure = Decimal("0.01")
                    entry = Decimal(tranche["conditional_entry_reference"])
                    self.assertEqual("0.01", tranche["multiplier_reference"])
                    self.assertEqual("0.01", tranche["reference_scale_quantum"])
                    self.assertGreaterEqual(
                        Decimal(tranche["derived_reference_scale"]),
                        Decimal("0.01"),
                    )
                    for field, rate in rates.items():
                        self.assertEqual(
                            canonical_decimal(exposure * entry * rate),
                            tranche[field],
                        )
                    prices = [
                        tranche["conditional_entry_reference"],
                        tranche["protective_stop_reference"],
                        tranche["minimum_noise_execution_buffer"],
                        *[
                            target["reference_price"]
                            for target in tranche["take_profit_targets"]
                        ],
                    ]
                    self.assertTrue(
                        all(Decimal(price) % Decimal("0.1") == 0 for price in prices)
                    )

    def test_evaluation_candidate_risk_cannot_drift_from_plan_allocations(
        self,
    ) -> None:
        state = self.fx["proposal_output"]["current_dynamic_research_state"]
        candidate_rows = deepcopy(_candidate_rows())
        next(
            row for row in candidate_rows if row["candidate_id"] == "open-long"
        )["risk_reference_units"] = "0.35"

        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_CANDIDATE_BINDING_INVALID",
        ):
            build_v32_proposal_semantic_output_v1(
                proposal_input_context=self.fx["proposal_context"],
                current_dynamic_research_state=state,
                reference_context="FLAT_RESEARCH_INTENT",
                risk_arithmetic=_risk_arithmetic(),
                candidate_rows=candidate_rows,
                sealed_plan_variants=_plan_variants(state),
            )

    def test_self_resigned_objective_reference_inputs_cannot_be_agent_selected(
        self,
    ) -> None:
        state = self.fx["proposal_output"]["current_dynamic_research_state"]
        cases = {
            "multiplier_reference": "0.02",
            "fee_stress_reference": "0.003",
            "slippage_stress_reference": "0.002",
            "funding_bound_reference": "0.002",
            "tail_gap_reference": "0.006",
            "reference_scale_quantum": "0.02",
        }
        for field, value in cases.items():
            variants = _plan_variants(
                state, reference_input_overrides={field: value}
            )
            output = deepcopy(self.fx["proposal_output"])
            output["sealed_plan_variants"] = variants
            output = self_digest(
                output, PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD
            )
            delivery, _, consumption, _ = self._proposal_chain_for_payload(
                canonical_v32_agent_semantic_json_v1(output)
            )
            with self.subTest(field=field), self.assertRaisesRegex(
                V32AgentSemanticCompilerError,
                "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_BINDING_INVALID",
            ):
                compile_v32_proposal_delivery_v1(
                    proposal_input_context=self.fx["proposal_context"],
                    proposal_delivery=delivery,
                    proposal_consumption=consumption,
                    compiled_at="2026-08-07T00:16:40Z",
                )

    def test_positive_risk_prices_must_align_to_observed_tick(self) -> None:
        state = self.fx["proposal_output"]["current_dynamic_research_state"]
        variants = _plan_variants(
            state,
            tranche_field_overrides={"conditional_entry_reference": "100.05"},
        )
        output = deepcopy(self.fx["proposal_output"])
        output["sealed_plan_variants"] = variants
        output = self_digest(output, PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD)
        delivery, _, consumption, _ = self._proposal_chain_for_payload(
            canonical_v32_agent_semantic_json_v1(output)
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_OBJECTIVE_REFERENCE_INPUT_BINDING_INVALID",
        ):
            compile_v32_proposal_delivery_v1(
                proposal_input_context=self.fx["proposal_context"],
                proposal_delivery=delivery,
                proposal_consumption=consumption,
                compiled_at="2026-08-07T00:16:40Z",
            )

    def test_missing_contract_spec_allows_zero_risk_only(self) -> None:
        for datum_id in (
            "contract-value",
            "contract-multiplier",
            "price-tick",
            "quantity-step",
            "minimum-quantity",
        ):
            packet = _packet_without_contract_datum(
                self.fx["proposal_packet"], datum_id
            )
            context, _ = _context(
                "PROPOSAL", packet, created_at="2026-08-07T00:16:00Z"
            )
            state = _market_bound_dynamic_state(packet)
            positive_variants = _plan_variants(state)
            with self.subTest(datum_id=datum_id), self.assertRaisesRegex(
                V32AgentSemanticCompilerError,
                "V32_AGENT_OBJECTIVE_REFERENCE_INPUTS_UNAVAILABLE",
            ):
                build_v32_proposal_semantic_output_v1(
                    proposal_input_context=context,
                    current_dynamic_research_state=state,
                    reference_context="FLAT_RESEARCH_INTENT",
                    risk_arithmetic=_risk_arithmetic(),
                    candidate_rows=_candidate_rows(
                        positive_variants[0]["dynamic_action_plan"]
                    ),
                    sealed_plan_variants=positive_variants,
                )

        packet = _packet_without_contract_datum(
            self.fx["proposal_packet"], "contract-multiplier"
        )
        context, _ = _context(
            "PROPOSAL", packet, created_at="2026-08-07T00:16:00Z"
        )
        state = _market_bound_dynamic_state(packet)
        zero_risk_variants = _zero_risk_variants(state)
        zero_risk_arithmetic = _risk_arithmetic()
        zero_risk_arithmetic["subjective_plausibility_tier"] = (
            "EXTREME_UNCERTAINTY"
        )
        zero_risk_arithmetic["agent_reference_risk_ceiling"] = "0"
        output = build_v32_proposal_semantic_output_v1(
            proposal_input_context=context,
            current_dynamic_research_state=state,
            reference_context="FLAT_RESEARCH_INTENT",
            risk_arithmetic=zero_risk_arithmetic,
            candidate_rows=_candidate_rows(
                zero_risk_variants[0]["dynamic_action_plan"],
                risk_arithmetic=zero_risk_arithmetic,
            ),
            sealed_plan_variants=zero_risk_variants,
        )
        self.assertEqual(["wait"], output["eligible_candidate_ids"])
        self.assertEqual(
            [],
            output["sealed_plan_variants"][0]["dynamic_action_plan"][
                "risk_tranches"
            ],
        )

    def test_domain_derived_residual_zero_budget_compiles_to_wait(self) -> None:
        state = _residual_zero_dynamic_state(
            self.fx["proposal_output"]["current_dynamic_research_state"]
        )
        args = deepcopy(action_fixture._flat_args(dynamic_state=state))
        clusters = {
            row["cluster_id"]: row for row in state["dependency_clusters"]
        }
        for candidate in args["candidates"]:
            if candidate["cluster_ids"]:
                candidate["hypothesis_ids"] = sorted(
                    {
                        hypothesis_id
                        for cluster_id in candidate["cluster_ids"]
                        for hypothesis_id in clusters[cluster_id][
                            "member_hypothesis_ids"
                        ]
                    }
                )
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]
        args["wait_assessment"]["review_deadline"] = "2026-08-07T00:30:00Z"
        args["inactivity_opportunity_watchdog"][
            "next_watchdog_review_at"
        ] = "2026-08-07T00:30:00Z"
        args["inactivity_opportunity_watchdog"]["inactivity_since"] = state[
            "as_of"
        ]
        args["inactivity_opportunity_watchdog"][
            "model_adaptation_inactivity_since"
        ] = state["as_of"]
        plan = build_v32_dynamic_action_plan_v1(**args)
        variant = {
            "variant_id": "variant::wait",
            "candidate_id": "wait",
            "dynamic_action_plan": plan,
            "dynamic_action_plan_digest": plan["dynamic_action_plan_digest"],
        }
        risk_arithmetic = _risk_arithmetic()
        risk_arithmetic.update(
            {
                "subjective_plausibility_tier": "EXTREME_UNCERTAINTY",
                "residual_uncertainty_tier": "HIGH",
                "agent_reference_risk_ceiling": "0",
            }
        )

        output = build_v32_proposal_semantic_output_v1(
            proposal_input_context=self.fx["proposal_context"],
            current_dynamic_research_state=state,
            reference_context="FLAT_RESEARCH_INTENT",
            risk_arithmetic=risk_arithmetic,
            candidate_rows=_candidate_rows(
                plan,
                risk_arithmetic=risk_arithmetic,
            ),
            sealed_plan_variants=[variant],
        )

        self.assertEqual(["wait"], output["eligible_candidate_ids"])
        self.assertEqual(0, plan["residual_uncertainty_cap_units"])
        self.assertEqual(
            {"RISK_BUDGET_BELOW_CLUSTER_QUANTUM"},
            {
                row["block_reason"]
                for row in plan["candidates"]
                if row["action_kind"] in RISK_INCREASING_ACTIONS
            },
        )

    def test_exhausted_instrument_churn_blocks_every_direction_and_selects_wait(
        self,
    ) -> None:
        state = self.fx["proposal_output"]["current_dynamic_research_state"]
        args = deepcopy(action_fixture._flat_args(dynamic_state=state))
        clusters = {
            row["cluster_id"]: row for row in state["dependency_clusters"]
        }
        for candidate in args["candidates"]:
            if candidate["cluster_ids"]:
                candidate["hypothesis_ids"] = sorted(
                    {
                        hypothesis_id
                        for cluster_id in candidate["cluster_ids"]
                        for hypothesis_id in clusters[cluster_id][
                            "member_hypothesis_ids"
                        ]
                    }
                )
        failure_ref = next(
            row
            for row in state["hypotheses"]
            if row["hypothesis_id"] == "h-long"
        )["source_refs"][0]
        budget_id = args["reentry_budget_state"]["budget_id"]
        args["reentry_budget_state"] = action_fixture._available_reentry_budget()
        args["reentry_budget_state"].update(
            {
                "budget_id": budget_id,
                "attempts_used": 2,
                "cumulative_reference_risk": "1",
                "consecutive_failures": 2,
                "cooldown_until": action_fixture.REENTRY_WINDOW_EXPIRES,
                "failure_evidence_refs": [failure_ref],
                "status": "EXHAUSTED",
            }
        )
        for candidate in args["candidates"]:
            if candidate["action_kind"] in RISK_INCREASING_ACTIONS:
                candidate.update(
                    {
                        "feasibility": "BLOCKED",
                        "block_reason": "REENTRY_COOLDOWN_OR_BUDGET",
                        "blocking_evidence_refs": [failure_ref],
                        "risk_tranche_id": None,
                    }
                )
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]
        args["wait_assessment"]["review_deadline"] = "2026-08-07T00:30:00Z"
        args["inactivity_opportunity_watchdog"][
            "next_watchdog_review_at"
        ] = "2026-08-07T00:30:00Z"
        args["inactivity_opportunity_watchdog"]["inactivity_since"] = state[
            "as_of"
        ]
        args["inactivity_opportunity_watchdog"][
            "model_adaptation_inactivity_since"
        ] = state["as_of"]
        plan = build_v32_dynamic_action_plan_v1(**args)
        risk_arithmetic = _risk_arithmetic()
        risk_arithmetic.update(
            {
                "subjective_plausibility_tier": "EXTREME_UNCERTAINTY",
                "agent_reference_risk_ceiling": "0",
            }
        )
        proposal_output = build_v32_proposal_semantic_output_v1(
            proposal_input_context=self.fx["proposal_context"],
            current_dynamic_research_state=state,
            reference_context="FLAT_RESEARCH_INTENT",
            risk_arithmetic=risk_arithmetic,
            candidate_rows=_candidate_rows(
                plan,
                risk_arithmetic=risk_arithmetic,
            ),
            sealed_plan_variants=[
                {
                    "variant_id": "variant::wait",
                    "candidate_id": "wait",
                    "dynamic_action_plan": plan,
                    "dynamic_action_plan_digest": plan[
                        "dynamic_action_plan_digest"
                    ],
                }
            ],
        )
        flow = _selection_fixture_for_proposal(
            proposal_context=self.fx["proposal_context"],
            proposal_context_binding=self.fx["proposal_context_binding"],
            proposal_output=proposal_output,
            selected_candidate_id="wait",
        )

        self.assertEqual(["wait"], proposal_output["eligible_candidate_ids"])
        self.assertEqual(
            "WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION",
            flow["selection_output"]["selection_reason_code"],
        )
        self.assertEqual(
            "wait", flow["selection_receipt"]["selected_candidate_id"]
        )

    def test_wait_selection_round_trip_with_no_eligible_risk_candidates(self) -> None:
        base_state = self.fx["proposal_output"][
            "current_dynamic_research_state"
        ]
        objective_packet = _packet_without_contract_datum(
            self.fx["proposal_packet"], "contract-multiplier"
        )
        objective_context, objective_context_binding = _context(
            "PROPOSAL",
            objective_packet,
            created_at="2026-08-07T00:16:00Z",
        )
        objective_state = _market_bound_dynamic_state(objective_packet)
        choppy_state = _choppy_dynamic_state(base_state)
        choppy_regime = choppy_state["market_regime_state"]
        cases = (
            {
                "case_name": "objective-zero-risk",
                "context": objective_context,
                "context_binding": objective_context_binding,
                "state": objective_state,
                "block_reason": "COST_OR_LIQUIDITY",
                "blocking_refs": [
                    "objective-reference-risk-inputs-unavailable"
                ],
            },
            {
                "case_name": "choppy-zero-direction",
                "context": self.fx["proposal_context"],
                "context_binding": self.fx["proposal_context_binding"],
                "state": choppy_state,
                "block_reason": "MARKET_REGIME_NON_DIRECTIONAL",
                "blocking_refs": sorted(
                    set(
                        choppy_regime["evidence_refs"]
                        + choppy_regime["counter_evidence_refs"]
                    )
                ),
            },
        )
        for case in cases:
            case_name = case["case_name"]
            state = case["state"]
            with self.subTest(case_name=case_name):
                variants = _zero_risk_variants(
                    state,
                    block_reason=case["block_reason"],
                    blocking_evidence_refs=case["blocking_refs"],
                )
                risk_arithmetic = _risk_arithmetic()
                risk_arithmetic["subjective_plausibility_tier"] = (
                    "EXTREME_UNCERTAINTY"
                )
                risk_arithmetic["agent_reference_risk_ceiling"] = "0"
                proposal_output = build_v32_proposal_semantic_output_v1(
                    proposal_input_context=case["context"],
                    current_dynamic_research_state=state,
                    reference_context="FLAT_RESEARCH_INTENT",
                    risk_arithmetic=risk_arithmetic,
                    candidate_rows=_candidate_rows(
                        variants[0]["dynamic_action_plan"],
                        risk_arithmetic=risk_arithmetic,
                    ),
                    sealed_plan_variants=variants,
                )
                flow = _selection_fixture_for_proposal(
                    proposal_context=case["context"],
                    proposal_context_binding=case["context_binding"],
                    proposal_output=proposal_output,
                    selected_candidate_id="wait",
                )
                selection = flow["selection_output"]
                plan = variants[0]["dynamic_action_plan"]
                evaluation = flow["proposal_receipt"][
                    "sealed_action_evaluation"
                ]
                expected_refs = set()
                for candidate in evaluation["candidate_rows"]:
                    if (
                        candidate["action_kind"] in RISK_INCREASING_ACTIONS
                        and candidate["feasibility"] == "BLOCKED"
                    ):
                        expected_refs.update(candidate["evidence_refs"])
                for candidate in plan["candidates"]:
                    if (
                        candidate["action_kind"] in RISK_INCREASING_ACTIONS
                        and candidate["feasibility"] == "BLOCKED"
                    ):
                        expected_refs.update(
                            candidate["blocking_evidence_refs"]
                        )
                regime = state["market_regime_state"]
                for field in (
                    "evidence_refs",
                    "counter_evidence_refs",
                    "transition_evidence_refs",
                ):
                    expected_refs.update(regime[field])
                self.assertEqual(
                    "WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION",
                    selection["selection_reason_code"],
                )
                self.assertEqual(
                    sorted(expected_refs), selection["selection_reason_refs"]
                )
                self.assertEqual(
                    "wait", flow["selection_receipt"]["selected_candidate_id"]
                )
                self.assertEqual(
                    "wait",
                    flow["selection_receipt"]["final_dynamic_action_plan"][
                        "selected_candidate_id"
                    ],
                )

                # Both cases above prove the two distinct WAIT derivations.
                # One reconstructed-code tamper is enough here; unsealed
                # reason refs have their own focused test below.
                if case_name == "objective-zero-risk":
                    tampered = deepcopy(selection)
                    tampered["selection_reason_code"] = (
                        "WAIT_DOMINANCE_PROVEN_BY_SEALED_VARIANT"
                    )
                    tampered = self_digest(
                        tampered, SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD
                    )
                    delivery, _, consumption, _ = _delivery_chain(
                        flow["selection_context"],
                        flow["selection_context_binding"],
                        canonical_v32_agent_semantic_json_v1(tampered),
                        reserved_at="2026-08-07T00:17:00Z",
                        delivered_at="2026-08-07T00:17:10Z",
                        consumed_at="2026-08-07T00:17:20Z",
                    )
                    with self.assertRaisesRegex(
                        V32AgentSemanticCompilerError,
                        "RECONSTRUCTION_MISMATCH",
                    ):
                        compile_v32_selection_delivery_v1(
                            proposal_compile_receipt=flow["proposal_receipt"],
                            selection_input_context=flow["selection_context"],
                            selection_delivery=delivery,
                            selection_consumption=consumption,
                            compiled_at="2026-08-07T00:17:30Z",
                        )

    def test_complete_objective_inputs_reject_agent_claimed_zero_risk(self) -> None:
        state = self.fx["proposal_output"][
            "current_dynamic_research_state"
        ]
        variants = _zero_risk_variants(
            state,
            block_reason="COST_OR_LIQUIDITY",
            blocking_evidence_refs=[
                "objective-reference-risk-inputs-unavailable"
            ],
        )
        risk_arithmetic = _risk_arithmetic()
        risk_arithmetic["subjective_plausibility_tier"] = (
            "EXTREME_UNCERTAINTY"
        )
        risk_arithmetic["agent_reference_risk_ceiling"] = "0"
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_ZERO_ELIGIBLE_RISK_CAUSE_INVALID",
        ):
            build_v32_proposal_semantic_output_v1(
                proposal_input_context=self.fx["proposal_context"],
                current_dynamic_research_state=state,
                reference_context="FLAT_RESEARCH_INTENT",
                risk_arithmetic=risk_arithmetic,
                candidate_rows=_candidate_rows(
                    variants[0]["dynamic_action_plan"],
                    risk_arithmetic=risk_arithmetic,
                ),
                sealed_plan_variants=variants,
            )

    def test_complete_objective_inputs_reject_one_sided_soft_block(self) -> None:
        state = self.fx["proposal_output"]["current_dynamic_research_state"]
        clusters = {
            row["cluster_id"]: row for row in state["dependency_clusters"]
        }
        base = deepcopy(action_fixture._flat_args(dynamic_state=state))
        for candidate in base["candidates"]:
            if candidate["cluster_ids"]:
                candidate["hypothesis_ids"] = sorted(
                    {
                        hypothesis_id
                        for cluster_id in candidate["cluster_ids"]
                        for hypothesis_id in clusters[cluster_id][
                            "member_hypothesis_ids"
                        ]
                    }
                )
        for obligation in base["reentry_obligations"]:
            obligation["parent_hypothesis_ids"] = sorted(
                {
                    hypothesis_id
                    for cluster_id in obligation["supporting_cluster_ids"]
                    for hypothesis_id in clusters[cluster_id][
                        "member_hypothesis_ids"
                    ]
                }
            )
        short = next(
            row
            for row in base["candidates"]
            if row["candidate_id"] == "open-short"
        )
        short.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "COST_OR_LIQUIDITY",
                "blocking_evidence_refs": [
                    "objective-reference-risk-inputs-unavailable"
                ],
                "risk_tranche_id": None,
            }
        )
        base["risk_tranches"] = [
            row
            for row in base["risk_tranches"]
            if row["candidate_id"] != "open-short"
        ]
        base["reentry_obligations"] = [
            row
            for row in base["reentry_obligations"]
            if row["obligation_id"] != "o-short"
        ]
        base["wait_assessment"]["review_deadline"] = "2026-08-07T00:30:00Z"
        base["inactivity_opportunity_watchdog"][
            "next_watchdog_review_at"
        ] = "2026-08-07T00:30:00Z"
        base["inactivity_opportunity_watchdog"]["inactivity_since"] = state[
            "as_of"
        ]
        base["inactivity_opportunity_watchdog"][
            "model_adaptation_inactivity_since"
        ] = state["as_of"]

        variants = []
        for selected in ("open-long", "wait"):
            args = deepcopy(base)
            args["selected_candidate_id"] = selected
            args["alternative_candidate_rank"] = [
                candidate_id
                for candidate_id in ("open-long", "open-short", "wait")
                if candidate_id != selected
            ]
            if selected == "wait":
                args["wait_assessment"] = action_fixture._wait(
                    [
                        {
                            "candidate_id": "open-long",
                            "dominance_reason": "INFORMATION_VALUE_DOMINATES_UNTIL_DEADLINE",
                            "evidence_refs": [
                                "distinguishing-observation:open-long"
                            ],
                            "rationale": "one bounded observation dominates immediate reference risk",
                        }
                    ]
                )
                args["wait_assessment"]["review_deadline"] = (
                    "2026-08-07T00:30:00Z"
                )
            plan = build_v32_dynamic_action_plan_v1(**args)
            variants.append(
                {
                    "variant_id": f"variant::{selected}",
                    "candidate_id": selected,
                    "dynamic_action_plan": plan,
                    "dynamic_action_plan_digest": plan[
                        "dynamic_action_plan_digest"
                    ],
                }
            )

        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_RISK_BLOCK_CAUSE_INVALID",
        ):
            build_v32_proposal_semantic_output_v1(
                proposal_input_context=self.fx["proposal_context"],
                current_dynamic_research_state=state,
                reference_context="FLAT_RESEARCH_INTENT",
                risk_arithmetic=_risk_arithmetic(),
                candidate_rows=_candidate_rows(
                    variants[0]["dynamic_action_plan"]
                ),
                sealed_plan_variants=variants,
            )

    def test_zero_eligible_reentry_requires_a_real_bound_ledger_block(self) -> None:
        state = self.fx["proposal_output"]["current_dynamic_research_state"]
        evaluation = {
            "candidate_rows": [
                {
                    "candidate_id": "reenter-long",
                    "action_kind": "REENTER",
                    "feasibility": "BLOCKED",
                }
            ]
        }
        candidate = {
            "candidate_id": "reenter-long",
            "action_kind": "REENTER",
            "feasibility": "BLOCKED",
            "block_reason": "REENTRY_COOLDOWN_OR_BUDGET",
            "blocking_evidence_refs": ["source:h-long"],
        }
        budget = action_fixture._available_reentry_budget()
        variants = [
            {
                "dynamic_action_plan": {
                    "candidates": [candidate],
                    "reentry_budget_state": budget,
                }
            }
        ]
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_ZERO_ELIGIBLE_RISK_CAUSE_INVALID",
        ):
            _validate_zero_eligible_risk_causes(
                proposal_packet=self.fx["proposal_packet"],
                dynamic_state=state,
                evaluation=evaluation,
                variants=variants,
            )

        budget["status"] = "EXHAUSTED"
        budget["attempts_used"] = 2
        budget["cumulative_reference_risk"] = "1"
        budget["consecutive_failures"] = 2
        budget["cooldown_until"] = action_fixture.REENTRY_WINDOW_EXPIRES
        _validate_zero_eligible_risk_causes(
            proposal_packet=self.fx["proposal_packet"],
            dynamic_state=state,
            evaluation=evaluation,
            variants=variants,
        )

        candidate["blocking_evidence_refs"] = [
            "source:h-long",
            "source:h-short",
        ]
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_ZERO_ELIGIBLE_RISK_CAUSE_INVALID",
        ):
            _validate_zero_eligible_risk_causes(
                proposal_packet=self.fx["proposal_packet"],
                dynamic_state=state,
                evaluation=evaluation,
                variants=variants,
            )

    def test_directional_wait_keeps_sealed_dominance_reason(self) -> None:
        flow = _selection_fixture_for_proposal(
            proposal_context=self.fx["proposal_context"],
            proposal_context_binding=self.fx["proposal_context_binding"],
            proposal_output=self.fx["proposal_output"],
            selected_candidate_id="wait",
        )
        wait_variant = next(
            row
            for row in self.fx["proposal_output"]["sealed_plan_variants"]
            if row["candidate_id"] == "wait"
        )
        expected_refs = sorted(
            {
                ref
                for comparison in wait_variant["dynamic_action_plan"][
                    "wait_assessment"
                ]["dominance_comparisons"]
                for ref in comparison["evidence_refs"]
            }
        )
        self.assertEqual(
            "WAIT_DOMINANCE_PROVEN_BY_SEALED_VARIANT",
            flow["selection_output"]["selection_reason_code"],
        )
        self.assertEqual(
            expected_refs,
            flow["selection_output"]["selection_reason_refs"],
        )
        self.assertEqual(
            "wait", flow["selection_receipt"]["selected_candidate_id"]
        )

    def test_resigned_state_cannot_exceed_contract_hypothesis_ttl(self) -> None:
        state = deepcopy(
            self.fx["proposal_output"]["current_dynamic_research_state"]
        )
        action_thesis = next(
            row
            for row in state["hypotheses"]
            if row["hypothesis_id"] == "h-action-long"
        )
        action_thesis["expires_at"] = "2026-08-07T02:00:00Z"
        state = self_digest(state, "dynamic_research_state_digest")

        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_HYPOTHESIS_TTL_POLICY_INVALID",
        ):
            build_v32_proposal_semantic_output_v1(
                proposal_input_context=self.fx["proposal_context"],
                current_dynamic_research_state=state,
                reference_context="FLAT_RESEARCH_INTENT",
                risk_arithmetic=_risk_arithmetic(),
                candidate_rows=_candidate_rows(),
                sealed_plan_variants=_plan_variants(state),
            )

    def test_noncanonical_proposal_json_is_rejected(self) -> None:
        payload = " " + self.fx["proposal_payload"]
        delivery, _, consumption, _ = self._proposal_chain_for_payload(payload)
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_SEMANTIC_PAYLOAD_NOT_CANONICAL",
        ):
            compile_v32_proposal_delivery_v1(
                proposal_input_context=self.fx["proposal_context"],
                proposal_delivery=delivery,
                proposal_consumption=consumption,
                compiled_at="2026-08-07T00:16:40Z",
            )

    def test_duplicate_key_proposal_json_is_rejected(self) -> None:
        payload = '{"schema_id":"duplicate",' + self.fx["proposal_payload"][1:]
        delivery, _, consumption, _ = self._proposal_chain_for_payload(payload)
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError, "V32_AGENT_SEMANTIC_PAYLOAD_INVALID"
        ):
            compile_v32_proposal_delivery_v1(
                proposal_input_context=self.fx["proposal_context"],
                proposal_delivery=delivery,
                proposal_consumption=consumption,
                compiled_at="2026-08-07T00:16:40Z",
            )

    def test_future_outcome_or_account_field_cannot_be_laundered(self) -> None:
        for field in ("future_outcome", "account_state", "fill", "pnl"):
            output = deepcopy(self.fx["proposal_output"])
            output[field] = {"claimed": True}
            output = self_digest(output, PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD)
            payload = canonical_v32_agent_semantic_json_v1(output)
            delivery, _, consumption, _ = self._proposal_chain_for_payload(payload)
            with self.subTest(field=field), self.assertRaisesRegex(
                V32AgentSemanticCompilerError, "V32_AGENT_PROPOSAL_OUTPUT_INVALID"
            ):
                compile_v32_proposal_delivery_v1(
                    proposal_input_context=self.fx["proposal_context"],
                    proposal_delivery=delivery,
                    proposal_consumption=consumption,
                    compiled_at="2026-08-07T00:16:40Z",
                )

    def test_missing_eligible_variant_fails_closed(self) -> None:
        output = deepcopy(self.fx["proposal_output"])
        output["sealed_plan_variants"].pop()
        output = self_digest(output, PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD)
        delivery, _, consumption, _ = self._proposal_chain_for_payload(
            canonical_v32_agent_semantic_json_v1(output)
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_PLAN_VARIANT_COVERAGE_INVALID",
        ):
            compile_v32_proposal_delivery_v1(
                proposal_input_context=self.fx["proposal_context"],
                proposal_delivery=delivery,
                proposal_consumption=consumption,
                compiled_at="2026-08-07T00:16:40Z",
            )

    def test_valid_variant_with_different_plan_material_is_rejected(self) -> None:
        output = deepcopy(self.fx["proposal_output"])
        target = next(
            row
            for row in output["sealed_plan_variants"]
            if row["candidate_id"] == "open-short"
        )
        # Keep the alternative intrinsically valid under the exact proposal
        # state, then prove that semantic compilation still rejects different
        # sealed material.  Reusing the generic action fixture here would now
        # fail earlier (correctly) because its cluster/hypothesis lineage is a
        # different state.
        drifted = deepcopy(target["dynamic_action_plan"])
        drifted["plan_id"] = "drifted-plan-id"
        drifted = self_digest(drifted, "dynamic_action_plan_digest")
        target["dynamic_action_plan"] = drifted
        target["dynamic_action_plan_digest"] = drifted[
            "dynamic_action_plan_digest"
        ]
        output = self_digest(output, PROPOSAL_SEMANTIC_OUTPUT_DIGEST_FIELD)
        delivery, _, consumption, _ = self._proposal_chain_for_payload(
            canonical_v32_agent_semantic_json_v1(output)
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_PLAN_VARIANT_MATERIAL_DRIFT",
        ):
            compile_v32_proposal_delivery_v1(
                proposal_input_context=self.fx["proposal_context"],
                proposal_delivery=delivery,
                proposal_consumption=consumption,
                compiled_at="2026-08-07T00:16:40Z",
            )

    def test_selection_packet_cannot_replace_sealed_risk_material(self) -> None:
        changed_risk = deepcopy(_risk_arithmetic())
        changed_risk.update(
            {
                "subjective_plausibility_tier": "LOW",
                "agent_reference_risk_ceiling": "0.5",
            }
        )
        changed_rows = deepcopy(_candidate_rows())
        changed_risk_digest = canonical_digest(changed_risk)
        for row in changed_rows:
            row["risk_arithmetic_digest"] = changed_risk_digest
            if row["candidate_id"] == "open-long":
                row["risk_reference_units"] = "0.3"
            elif row["candidate_id"] == "open-short":
                row["risk_reference_units"] = "0.2"
        changed_evaluation = build_v32_action_evaluation_v1(
            run_id=self.fx["proposal_context"]["run_id"],
            cycle_index=1,
            evaluated_at="2026-08-07T00:16:40Z",
            proposal_consumption_digest=self.fx["proposal_consumption"][
                AGENT_CONSUMPTION_DIGEST_FIELD
            ],
            compiled_dynamic_state_digest=self.fx["proposal_receipt"][
                "compiled_dynamic_research_state_digest"
            ],
            reference_context="FLAT_RESEARCH_INTENT",
            risk_arithmetic=changed_risk,
            candidate_rows=changed_rows,
        )
        dynamic_binding = lifecycle_fixture._embedded(
            "semantic-risk-drift-dynamic",
            self.fx["proposal_receipt"]["compiled_dynamic_research_state"],
            "theory_paper_v32_dynamic_research_state_v1",
            "dynamic_research_state_digest",
        )
        evaluation_binding = lifecycle_fixture._embedded(
            "semantic-risk-drift-evaluation",
            changed_evaluation,
            ACTION_EVALUATION_SCHEMA_ID,
            ACTION_EVALUATION_DIGEST_FIELD,
        )
        selection_packet = build_v32_selection_canonical_packet_v1(
            proposal_input_context=self.fx["proposal_context"],
            proposal_input_context_binding=self.fx["proposal_context_binding"],
            proposal_delivery=self.fx["proposal_delivery"],
            proposal_delivery_binding=self.fx["proposal_delivery_binding"],
            proposal_consumption=self.fx["proposal_consumption"],
            proposal_consumption_binding=self.fx["proposal_consumption_binding"],
            compiled_dynamic_research_state=self.fx["proposal_receipt"][
                "compiled_dynamic_research_state"
            ],
            compiled_dynamic_research_state_binding=dynamic_binding,
            sealed_action_evaluation=changed_evaluation,
            sealed_action_evaluation_binding=evaluation_binding,
            prepared_at="2026-08-07T00:16:45Z",
        )
        selection_context, _ = _context(
            "SELECTION", selection_packet, created_at="2026-08-07T00:16:50Z"
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_SELECTION_PACKET_MATERIAL_DRIFT",
        ):
            build_v32_selection_semantic_output_v1(
                selection_input_context=selection_context,
                selected_candidate_id="open-short",
            )

    def test_proposal_compile_receipt_self_digest_laundering_is_rejected(self) -> None:
        receipt = deepcopy(self.fx["proposal_receipt"])
        receipt["eligible_candidate_ids"].reverse()
        receipt = self_digest(receipt, PROPOSAL_COMPILE_RECEIPT_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_proposal_semantic_compile_receipt_v1(
                receipt,
                proposal_input_context=self.fx["proposal_context"],
                proposal_delivery=self.fx["proposal_delivery"],
                proposal_consumption=self.fx["proposal_consumption"],
            )

    def test_selection_cannot_supply_rank_plan_weight_or_risk(self) -> None:
        forbidden = {
            "alternative_candidate_rank",
            "dynamic_action_plan",
            "weight",
            "risk_arithmetic",
        }
        self.assertTrue(forbidden.isdisjoint(self.fx["selection_output"]))

        # Unknown selection-owned material follows one exact-schema rejection
        # path. Exercise that path once with the most consequential field
        # instead of rebuilding the same large receipt four times.
        output = deepcopy(self.fx["selection_output"])
        output["dynamic_action_plan"] = {}
        output = self_digest(output, SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD)
        delivery, _, consumption, _ = self._selection_chain_for_payload(
            canonical_v32_agent_semantic_json_v1(output)
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError, "V32_AGENT_SELECTION_OUTPUT_INVALID"
        ):
            compile_v32_selection_delivery_v1(
                proposal_compile_receipt=self.fx["proposal_receipt"],
                selection_input_context=self.fx["selection_context"],
                selection_delivery=delivery,
                selection_consumption=consumption,
                compiled_at="2026-08-07T00:17:30Z",
            )

    def test_selection_reason_is_derived_only_from_sealed_refs(self) -> None:
        output = deepcopy(self.fx["selection_output"])
        output["selection_reason_refs"].append("new-unsealed-evidence")
        output["selection_reason_refs"].sort()
        output = self_digest(output, SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD)
        delivery, _, consumption, _ = self._selection_chain_for_payload(
            canonical_v32_agent_semantic_json_v1(output)
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_SELECTION_OUTPUT_RECONSTRUCTION_MISMATCH",
        ):
            compile_v32_selection_delivery_v1(
                proposal_compile_receipt=self.fx["proposal_receipt"],
                selection_input_context=self.fx["selection_context"],
                selection_delivery=delivery,
                selection_consumption=consumption,
                compiled_at="2026-08-07T00:17:30Z",
            )

    def test_selection_of_unknown_candidate_fails_closed(self) -> None:
        output = deepcopy(self.fx["selection_output"])
        output["selected_candidate_id"] = "invented-candidate"
        output["selected_variant_id"] = "variant::invented-candidate"
        output = self_digest(output, SELECTION_SEMANTIC_OUTPUT_DIGEST_FIELD)
        delivery, _, consumption, _ = self._selection_chain_for_payload(
            canonical_v32_agent_semantic_json_v1(output)
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_SELECTION_CANDIDATE_NOT_ELIGIBLE",
        ):
            compile_v32_selection_delivery_v1(
                proposal_compile_receipt=self.fx["proposal_receipt"],
                selection_input_context=self.fx["selection_context"],
                selection_delivery=delivery,
                selection_consumption=consumption,
                compiled_at="2026-08-07T00:17:30Z",
            )

    def test_noncanonical_selection_json_is_rejected(self) -> None:
        delivery, _, consumption, _ = self._selection_chain_for_payload(
            self.fx["selection_payload"] + "\n"
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_SEMANTIC_PAYLOAD_NOT_CANONICAL",
        ):
            compile_v32_selection_delivery_v1(
                proposal_compile_receipt=self.fx["proposal_receipt"],
                selection_input_context=self.fx["selection_context"],
                selection_delivery=delivery,
                selection_consumption=consumption,
                compiled_at="2026-08-07T00:17:30Z",
            )

    def test_final_plan_is_exact_selected_variant_and_binds_consumption(self) -> None:
        receipt = self.fx["selection_receipt"]
        final_plan = receipt["final_dynamic_action_plan"]
        digest = verify_v32_final_action_plan_exact_match_v1(
            final_plan,
            selection_consumption_digest=self.fx["selection_consumption"][
                AGENT_CONSUMPTION_DIGEST_FIELD
            ],
            proposal_compile_receipt=self.fx["proposal_receipt"],
            selection_compile_receipt=receipt,
            selection_input_context=self.fx["selection_context"],
            selection_delivery=self.fx["selection_delivery"],
            selection_consumption=self.fx["selection_consumption"],
        )
        self.assertEqual(digest, final_plan["dynamic_action_plan_digest"])

        other_plan = next(
            row["dynamic_action_plan"]
            for row in self.fx["proposal_receipt"]["sealed_plan_variants"]
            if row["candidate_id"] == "open-long"
        )
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_FINAL_PLAN_NOT_EXACT_SELECTED_VARIANT",
        ):
            verify_v32_final_action_plan_exact_match_v1(
                other_plan,
                selection_consumption_digest=self.fx["selection_consumption"][
                    AGENT_CONSUMPTION_DIGEST_FIELD
                ],
                proposal_compile_receipt=self.fx["proposal_receipt"],
                selection_compile_receipt=receipt,
                selection_input_context=self.fx["selection_context"],
                selection_delivery=self.fx["selection_delivery"],
                selection_consumption=self.fx["selection_consumption"],
            )

    def test_wrong_selection_consumption_digest_fails_final_match(self) -> None:
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError,
            "V32_AGENT_FINAL_PLAN_NOT_EXACT_SELECTED_VARIANT",
        ):
            verify_v32_final_action_plan_exact_match_v1(
                self.fx["selection_receipt"]["final_dynamic_action_plan"],
                selection_consumption_digest="f" * 64,
                proposal_compile_receipt=self.fx["proposal_receipt"],
                selection_compile_receipt=self.fx["selection_receipt"],
                selection_input_context=self.fx["selection_context"],
                selection_delivery=self.fx["selection_delivery"],
                selection_consumption=self.fx["selection_consumption"],
            )

    def test_selection_receipt_self_digest_laundering_is_rejected(self) -> None:
        receipt = deepcopy(self.fx["selection_receipt"])
        receipt["selected_candidate_id"] = "open-long"
        receipt = self_digest(receipt, SELECTION_COMPILE_RECEIPT_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32AgentSemanticCompilerError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_selection_semantic_compile_receipt_v1(
                receipt,
                proposal_compile_receipt=self.fx["proposal_receipt"],
                selection_input_context=self.fx["selection_context"],
                selection_delivery=self.fx["selection_delivery"],
                selection_consumption=self.fx["selection_consumption"],
            )


if __name__ == "__main__":
    unittest.main()
