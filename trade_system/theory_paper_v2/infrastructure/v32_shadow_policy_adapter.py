"""Replay V3.2 shadow policies against fully verified public inputs.

The Domain shadow contract freezes policy identities and deterministic output
rules.  This adapter binds those rules to the actual public market bundle and
the exact sealed V3.2 action plan.  It contains no network, account, order,
fill, position, PnL, probability, or execution capability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from typing import Any, Mapping

from ..domain.contracts.canonical import canonical_bytes, canonical_digest
from ..domain.v32_agent_lifecycle import verify_v32_action_evaluation_v1
from ..domain.v32_cycle_source_admission import (
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    verify_v32_pit_evidence_registry,
)
from ..domain.v32_dynamic_action_plan import (
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    SCHEMA_ID as ACTION_PLAN_SCHEMA_ID,
    verify_v32_dynamic_action_plan_v1,
)
from ..domain.v32_dynamic_research import verify_v32_dynamic_research_state_v1
from ..domain.v32_shadow_evaluation import (
    MARKET_ANALYSIS_DIGEST_FIELD,
    MARKET_ANALYSIS_SCHEMA_ID,
    OPPORTUNITY_SET_DIGEST_FIELD,
    OPPORTUNITY_SET_SCHEMA_ID,
    POLICY_DESCRIPTORS,
    POLICY_DIGESTS,
    POLICY_VERSION,
    SELECTED_PLAN_DIGEST_FIELD,
    SELECTED_PLAN_SCHEMA_ID,
    SHADOW_ARM_IDS,
    build_v32_shadow_decision_bundle_v1,
    verify_v32_shadow_decision_bundle_v1,
)
from .v32_public_source_collector import (
    PIT_DATUM_DIGEST_FIELD,
    verify_v32_public_market_analysis_bundle,
)


class V32ShadowPolicyAdapterError(ValueError):
    """A frozen shadow policy could not be replayed from exact inputs."""


_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32ShadowPolicyAdapterError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ShadowPolicyAdapterError(code) from exc
    if parsed.tzinfo is None:
        raise V32ShadowPolicyAdapterError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V32ShadowPolicyAdapterError(code)
    return parsed.astimezone(UTC)


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _binding(
    *,
    document: Mapping[str, Any],
    binding: Mapping[str, Any],
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
    code: str,
) -> dict[str, str]:
    if (
        not isinstance(binding, Mapping)
        or set(binding) != _BINDING_FIELDS
        or binding.get("schema_id") != schema_id
        or binding.get("digest_field") != digest_field
        or binding.get("semantic_digest") != semantic_digest
        or binding.get("physical_sha256") != _physical(document)
        or not isinstance(binding.get("relative_ref"), str)
        or not binding["relative_ref"]
    ):
        raise V32ShadowPolicyAdapterError(code)
    return {key: str(binding[key]) for key in _BINDING_FIELDS}


def _selected_candidate(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        row
        for row in plan["candidates"]
        if row["candidate_id"] == plan["selected_candidate_id"]
    ]
    if len(matches) != 1:
        raise V32ShadowPolicyAdapterError(
            "V32_SHADOW_POLICY_SELECTED_CANDIDATE_INVALID"
        )
    return matches[0]


def _datum_by_id(bundle: Mapping[str, Any], datum_id: str) -> Mapping[str, Any]:
    matches = [row for row in bundle["datums"] if row["datum_id"] == datum_id]
    if len(matches) != 1:
        raise V32ShadowPolicyAdapterError("V32_SHADOW_POLICY_DATUM_INVALID")
    row = matches[0]
    if (
        row.get("status") not in {"OBSERVED", "DERIVED"}
        or row.get("value") is None
        or row.get("observed_at") is None
    ):
        raise V32ShadowPolicyAdapterError("V32_SHADOW_POLICY_DATUM_INVALID")
    return row


def _arm(
    *,
    arm_id: str,
    run_id: str,
    cycle_index: int,
    as_of: str,
    common_bindings: Mapping[str, Mapping[str, str]],
    derivation_status: str,
    derivation_inputs: Mapping[str, Any],
    derivation_input_refs: list[str],
    action_label: str,
    direction_label: str,
    evidence_refs: list[str],
    rationale: str,
    shadow_arm_ordinal_band: str = "UNKNOWN",
) -> dict[str, Any]:
    receipt_digest = canonical_digest(
        {
            "arm_id": arm_id,
            "policy_digest": POLICY_DIGESTS[arm_id],
            "derivation_status": derivation_status,
            "derivation_inputs": dict(derivation_inputs),
            "derivation_input_refs": derivation_input_refs,
            "action_label": action_label,
            "direction_label": direction_label,
        }
    )
    return {
        "arm_id": arm_id,
        "run_id": run_id,
        "cycle_index": cycle_index,
        "as_of": as_of,
        **{key: dict(value) for key, value in common_bindings.items()},
        "policy_id": POLICY_DESCRIPTORS[arm_id]["policy_id"],
        "policy_version": POLICY_VERSION,
        "policy_digest": POLICY_DIGESTS[arm_id],
        "derivation_status": derivation_status,
        "derivation_inputs": dict(derivation_inputs),
        "derivation_input_refs": list(derivation_input_refs),
        "derivation_receipt_digest": receipt_digest,
        "action_label": action_label,
        "direction_label": direction_label,
        "shadow_arm_ordinal_band": shadow_arm_ordinal_band,
        "ordinal_band_semantics": (
            "SHADOW_ARM_COMPARISON_ONLY_NOT_SUBJECTIVE_PLAUSIBILITY_TIER"
        ),
        "ordinal_rationale": rationale,
        "evidence_refs": list(evidence_refs),
        "research_role": (
            "SELECTED_NON_EXECUTABLE_RESEARCH_LABEL"
            if arm_id == "V32_SELECTED_PLAN"
            else "SHADOW_COUNTERFACTUAL_RESEARCH_LABEL"
        ),
        "outcome_fields_present": False,
        "fill_claim": False,
        "position_claim": False,
        "pnl_claim": False,
        "probability_claim": "NONE_ORDINAL_RATIONALE_NOT_PROBABILITY",
        "expected_value_allowed": False,
        "executable": False,
    }


def build_v32_replayable_shadow_decision_bundle_v1(
    *,
    bundle_id: str,
    decision_id: str,
    created_at: str,
    public_market_analysis_bundle: Mapping[str, Any],
    public_market_analysis_bundle_binding: Mapping[str, Any],
    pit_evidence_registry: Mapping[str, Any],
    pit_evidence_registry_binding: Mapping[str, Any],
    sealed_action_evaluation: Mapping[str, Any],
    sealed_action_evaluation_binding: Mapping[str, Any],
    dynamic_research_state: Mapping[str, Any],
    selected_plan: Mapping[str, Any],
    selected_plan_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute every available shadow arm from the exact sealed inputs."""

    try:
        market_digest = verify_v32_public_market_analysis_bundle(
            public_market_analysis_bundle
        )
        pit_digest = verify_v32_pit_evidence_registry(pit_evidence_registry)
        opportunity_digest = verify_v32_action_evaluation_v1(
            sealed_action_evaluation
        )
        dynamic_digest = verify_v32_dynamic_research_state_v1(
            dynamic_research_state
        )
        plan_digest = verify_v32_dynamic_action_plan_v1(
            selected_plan, dynamic_research_state=dynamic_research_state
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32ShadowPolicyAdapterError(
            "V32_SHADOW_POLICY_UPSTREAM_DOCUMENT_INVALID"
        ) from exc

    market_binding = _binding(
        document=public_market_analysis_bundle,
        binding=public_market_analysis_bundle_binding,
        schema_id=MARKET_ANALYSIS_SCHEMA_ID,
        digest_field=MARKET_ANALYSIS_DIGEST_FIELD,
        semantic_digest=market_digest,
        code="V32_SHADOW_POLICY_MARKET_BINDING_INVALID",
    )
    pit_binding = _binding(
        document=pit_evidence_registry,
        binding=pit_evidence_registry_binding,
        schema_id=PIT_REGISTRY_SCHEMA_ID,
        digest_field=PIT_REGISTRY_DIGEST_FIELD,
        semantic_digest=pit_digest,
        code="V32_SHADOW_POLICY_PIT_BINDING_INVALID",
    )
    opportunity_binding = _binding(
        document=sealed_action_evaluation,
        binding=sealed_action_evaluation_binding,
        schema_id=OPPORTUNITY_SET_SCHEMA_ID,
        digest_field=OPPORTUNITY_SET_DIGEST_FIELD,
        semantic_digest=opportunity_digest,
        code="V32_SHADOW_POLICY_OPPORTUNITY_BINDING_INVALID",
    )
    plan_binding = _binding(
        document=selected_plan,
        binding=selected_plan_binding,
        schema_id=SELECTED_PLAN_SCHEMA_ID,
        digest_field=SELECTED_PLAN_DIGEST_FIELD,
        semantic_digest=plan_digest,
        code="V32_SHADOW_POLICY_PLAN_BINDING_INVALID",
    )

    run_id = str(selected_plan["run_id"])
    cycle_index = selected_plan["cycle_index"]
    decision_as_of = str(selected_plan["as_of"])
    if (
        public_market_analysis_bundle.get("run_id") != run_id
        or pit_evidence_registry.get("run_id") != run_id
        or dynamic_research_state.get("run_id") != run_id
        or sealed_action_evaluation.get("run_id") != run_id
        or any(
            document.get("cycle_index") != cycle_index
            for document in (
                public_market_analysis_bundle,
                pit_evidence_registry,
                dynamic_research_state,
                sealed_action_evaluation,
            )
        )
        or dynamic_research_state.get("as_of") != decision_as_of
        or sealed_action_evaluation.get("compiled_dynamic_state_digest")
        != dynamic_digest
        or sealed_action_evaluation.get("reference_context")
        != selected_plan.get("reference_context")
        or _moment(pit_evidence_registry.get("as_of"), "V32_SHADOW_POLICY_TIME_INVALID")
        > _moment(decision_as_of, "V32_SHADOW_POLICY_TIME_INVALID")
        or _moment(public_market_analysis_bundle.get("available_at"), "V32_SHADOW_POLICY_TIME_INVALID")
        > _moment(decision_as_of, "V32_SHADOW_POLICY_TIME_INVALID")
        or _moment(sealed_action_evaluation.get("evaluated_at"), "V32_SHADOW_POLICY_TIME_INVALID")
        < _moment(decision_as_of, "V32_SHADOW_POLICY_TIME_INVALID")
        or _moment(sealed_action_evaluation.get("evaluated_at"), "V32_SHADOW_POLICY_TIME_INVALID")
        > _moment(created_at, "V32_SHADOW_POLICY_TIME_INVALID")
        or _moment(created_at, "V32_SHADOW_POLICY_TIME_INVALID")
        < _moment(decision_as_of, "V32_SHADOW_POLICY_TIME_INVALID")
    ):
        raise V32ShadowPolicyAdapterError("V32_SHADOW_POLICY_CROSS_BINDING_INVALID")

    pit_members = set(pit_evidence_registry["members"])
    expected_pit_members = set(public_market_analysis_bundle["pit_member_digests"])
    expected_pit_members.add(market_digest)
    if pit_members != expected_pit_members:
        raise V32ShadowPolicyAdapterError(
            "V32_SHADOW_POLICY_PIT_REGISTRY_MISMATCH"
        )
    mark = _datum_by_id(public_market_analysis_bundle, "mark-price")
    mark_digest = str(mark[PIT_DATUM_DIGEST_FIELD])
    bars = public_market_analysis_bundle["closed_bar_series"].get("15M")
    if not isinstance(bars, list) or len(bars) < 2:
        raise V32ShadowPolicyAdapterError("V32_SHADOW_POLICY_15M_BARS_INVALID")
    previous_bar, latest_bar = bars[-2], bars[-1]
    previous = _datum_by_id(
        public_market_analysis_bundle,
        f"bar-15m-{previous_bar['open_time_ms']}-close",
    )
    latest = _datum_by_id(
        public_market_analysis_bundle,
        f"bar-15m-{latest_bar['open_time_ms']}-close",
    )
    previous_digest = str(previous[PIT_DATUM_DIGEST_FIELD])
    latest_digest = str(latest[PIT_DATUM_DIGEST_FIELD])
    if (
        {mark_digest, previous_digest, latest_digest}.difference(pit_members)
        or previous.get("value") != previous_bar.get("close")
        or latest.get("value") != latest_bar.get("close")
        or not previous_bar.get("confirmed_closed")
        or not latest_bar.get("confirmed_closed")
    ):
        raise V32ShadowPolicyAdapterError("V32_SHADOW_POLICY_PIT_INPUT_INVALID")

    selected = _selected_candidate(selected_plan)
    selected_action = str(selected["action_kind"])
    selected_direction = str(selected["direction"])
    opportunity_matches = [
        row
        for row in sealed_action_evaluation["candidate_rows"]
        if row["action_kind"] == selected_action
        and row["direction"] == selected_direction
    ]
    if (
        len(opportunity_matches) != 1
        or opportunity_matches[0]["feasibility"] != "ELIGIBLE"
    ):
        raise V32ShadowPolicyAdapterError(
            "V32_SHADOW_POLICY_SELECTED_ACTION_NOT_ELIGIBLE"
        )
    common = {
        "pit_registry_binding": pit_binding,
        "market_analysis_binding": market_binding,
        "opportunity_set_binding": opportunity_binding,
        "selected_plan_binding": plan_binding,
    }
    trend_refs = sorted([previous_digest, latest_digest])
    arms = [
        _arm(
            arm_id="V32_SELECTED_PLAN",
            run_id=run_id,
            cycle_index=cycle_index,
            as_of=decision_as_of,
            common_bindings=common,
            derivation_status="COMPUTED_FROM_SELECTED_PLAN",
            derivation_inputs={
                "selected_candidate_id": selected["candidate_id"],
                "action_label": selected_action,
                "direction_label": selected_direction,
            },
            derivation_input_refs=[plan_digest],
            action_label=selected_action,
            direction_label=selected_direction,
            evidence_refs=[],
            rationale="Exact action and direction copied from the sealed V3.2 selected plan.",
        ),
        _arm(
            arm_id="V31_CONSERVATIVE_WAIT_BIASED_REFERENCE",
            run_id=run_id,
            cycle_index=cycle_index,
            as_of=decision_as_of,
            common_bindings=common,
            derivation_status="UNKNOWN_NOT_COMPUTED",
            derivation_inputs={},
            derivation_input_refs=[],
            action_label="UNKNOWN",
            direction_label="UNKNOWN",
            evidence_refs=[],
            rationale="No frozen replayable V3.1 policy is available on the identical PIT input.",
        ),
        _arm(
            arm_id="WAIT_ONLY",
            run_id=run_id,
            cycle_index=cycle_index,
            as_of=decision_as_of,
            common_bindings=common,
            derivation_status="COMPUTED_CONSTANT",
            derivation_inputs={},
            derivation_input_refs=[],
            action_label="WAIT",
            direction_label="NONE",
            evidence_refs=[],
            rationale="Frozen constant WAIT policy.",
        ),
        _arm(
            arm_id="SIMPLE_15M_TREND",
            run_id=run_id,
            cycle_index=cycle_index,
            as_of=decision_as_of,
            common_bindings=common,
            derivation_status="COMPUTED_FROM_TWO_CLOSED_15M_BARS",
            derivation_inputs={
                "previous_close": previous["value"],
                "latest_close": latest["value"],
                "previous_close_datum_digest": previous_digest,
                "latest_close_datum_digest": latest_digest,
            },
            derivation_input_refs=trend_refs,
            action_label=(
                "HOLD"
                if latest["value"] != previous["value"]
                else "WAIT"
            ),
            direction_label=(
                "LONG"
                if Decimal(latest["value"]) > Decimal(previous["value"])
                else "SHORT"
                if Decimal(latest["value"]) < Decimal(previous["value"])
                else "NONE"
            ),
            evidence_refs=trend_refs,
            rationale="Direction derived only from the latest two confirmed closed 15-minute closes.",
        ),
        _arm(
            arm_id="NO_RSI_REFERENCE",
            run_id=run_id,
            cycle_index=cycle_index,
            as_of=decision_as_of,
            common_bindings=common,
            derivation_status="UNKNOWN_NOT_COMPUTED",
            derivation_inputs={},
            derivation_input_refs=[],
            action_label="UNKNOWN",
            direction_label="UNKNOWN",
            evidence_refs=[],
            rationale="No frozen no-RSI decision policy is available on the identical PIT input.",
        ),
        _arm(
            arm_id="ALWAYS_LONG_PUBLIC_MARK_REFERENCE",
            run_id=run_id,
            cycle_index=cycle_index,
            as_of=decision_as_of,
            common_bindings=common,
            derivation_status="COMPUTED_CONSTANT",
            derivation_inputs={},
            derivation_input_refs=[],
            action_label="HOLD",
            direction_label="LONG",
            evidence_refs=[],
            rationale="Frozen always-long public-mark direction; no fill or position is asserted.",
        ),
    ]
    if [row["arm_id"] for row in arms] != list(SHADOW_ARM_IDS):
        raise V32ShadowPolicyAdapterError("V32_SHADOW_POLICY_ARM_ORDER_INVALID")
    return build_v32_shadow_decision_bundle_v1(
        bundle_id=bundle_id,
        run_id=run_id,
        decision_id=decision_id,
        cycle_index=cycle_index,
        as_of=decision_as_of,
        created_at=created_at,
        pit_registry_binding=pit_binding,
        market_analysis_binding=market_binding,
        opportunity_set_binding=opportunity_binding,
        selected_plan_binding=plan_binding,
        decision_mark_snapshot={
            "value": mark["value"],
            "datum_digest": mark_digest,
            "observed_at": mark["observed_at"],
            "available_at": mark["available_at"],
        },
        arms=arms,
    )


def verify_v32_replayable_shadow_decision_bundle_v1(
    document: Mapping[str, Any],
    **upstream: Any,
) -> str:
    """Rebuild a bundle from upstream documents; labels alone never verify."""

    try:
        supplied = verify_v32_shadow_decision_bundle_v1(document)
        rebuilt = build_v32_replayable_shadow_decision_bundle_v1(
            bundle_id=document["bundle_id"],
            decision_id=document["decision_id"],
            created_at=document["created_at"],
            **upstream,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ShadowPolicyAdapterError):
            raise
        raise V32ShadowPolicyAdapterError(
            "V32_SHADOW_POLICY_BUNDLE_REPLAY_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt["shadow_decision_bundle_digest"]:
        raise V32ShadowPolicyAdapterError(
            "V32_SHADOW_POLICY_BUNDLE_REPLAY_MISMATCH"
        )
    return supplied


__all__ = [
    "V32ShadowPolicyAdapterError",
    "build_v32_replayable_shadow_decision_bundle_v1",
    "verify_v32_replayable_shadow_decision_bundle_v1",
]
