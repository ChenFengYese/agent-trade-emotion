"""Cross-cycle V3.2 action-plan continuity without files, clocks, or execution.

The action-plan domain validates one inactivity watchdog in isolation.  This
composition proves that an Agent cannot erase inactivity by changing the
selected action label or resetting a durable counter.  The testable-risk-plan
clock resets only after a fully qualified, selected, risk-funded OPEN_PROBE or
REENTER plan.  A separate model-adaptation clock resets on material state or
plan change.  Neither clock claims a fill, position, or real exposure.  A due
review still produces analysis, baselines, and shadow plans only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.v32_dynamic_action_plan import (
    CURRENT_PILOT_REENTRY_WINDOW_SECONDS,
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    REENTRY_MAX_ATTEMPTS,
    REENTRY_MAX_CUMULATIVE_REFERENCE_RISK,
    V32DynamicActionPlanError,
    v32_action_consumes_instrument_churn_budget_v1,
    verify_v32_dynamic_action_plan_v1,
)
from ..domain.v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    V32DynamicResearchError,
    verify_v32_dynamic_research_state_v1,
)


class V32ActionPlanContinuityError(ValueError):
    """A durable inactivity/watchdog transition failed closed."""


SCHEMA_ID = "theory_paper_v32_action_plan_continuity_receipt_v1"
SCHEMA_VERSION = "1.0.0"
DIGEST_FIELD = "action_plan_continuity_receipt_digest"


_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "current_dynamic_state_digest",
        "current_action_plan_digest",
        "previous_dynamic_state_digest",
        "previous_action_plan_digest",
        "previous_qualified_probe_candidate_ids",
        "material_market_change_detected",
        "material_change_evidence_refs",
        "material_action_plan_change_detected",
        "activity_basis",
        "model_adaptation_basis",
        "watchdog_activity_policy",
        "expected_inactivity_since",
        "expected_consecutive_wait_cycles",
        "expected_model_adaptation_inactivity_since",
        "expected_consecutive_model_stale_cycles",
        "max_wait_cycles_before_review",
        "max_inactivity_seconds",
        "testable_risk_plan_review_due",
        "model_adaptation_review_due",
        "forced_review_due",
        "required_response_status",
        "forces_action",
        "real_exposure_claim",
        "continuity_status",
        "source_scope",
        "external_execution_authority",
        "executable",
        DIGEST_FIELD,
    }
)


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32ActionPlanContinuityError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ActionPlanContinuityError(code) from exc
    if parsed.tzinfo is None:
        raise V32ActionPlanContinuityError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V32ActionPlanContinuityError(code)
    return parsed.astimezone(UTC)


def _selected_candidate(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    selected_id = plan["selected_candidate_id"]
    matches = [
        row
        for row in plan["candidates"]
        if row["candidate_id"] == selected_id
    ]
    if len(matches) != 1:
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_SELECTED_CANDIDATE_INVALID"
        )
    return matches[0]


def _qualified_probe_candidate_ids(plan: Mapping[str, Any]) -> list[str]:
    """Return the emitted probe only when its full bounded-risk contract exists."""

    candidate = _selected_candidate(plan)
    if (
        candidate["action_kind"] not in {"OPEN_PROBE", "REENTER"}
        or candidate["feasibility"] != "ELIGIBLE"
        or candidate["plan_state"] not in {"PLANNED", "CONDITIONAL"}
        or candidate["risk_tranche_id"] is None
        or not candidate["hypothesis_ids"]
        or not candidate["cluster_ids"]
        or _moment(candidate["horizon_at"], "V32_PLAN_CONTINUITY_PROBE_TIME_INVALID")
        <= _moment(plan["as_of"], "V32_PLAN_CONTINUITY_PROBE_TIME_INVALID")
        or Decimal(plan["selected_candidate_reference_risk_budget"]) <= 0
    ):
        return []
    tranches = [
        row
        for row in plan["risk_tranches"]
        if row["candidate_id"] == candidate["candidate_id"]
        and row["tranche_id"] == candidate["risk_tranche_id"]
        and Decimal(row["reference_risk_budget"]) > 0
        and Decimal(row["derived_reference_scale"]) > 0
    ]
    return [str(candidate["candidate_id"])] if len(tranches) == 1 else []


def _state_pit_refs(state: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    regime = state["market_regime_state"]
    refs.update(str(item) for item in regime["evidence_refs"])
    refs.update(str(item) for item in regime["counter_evidence_refs"])
    refs.update(str(item) for item in regime["transition_evidence_refs"])
    for assessment in regime["regime_feature_assessments"]:
        refs.update(str(item) for item in assessment["evidence_refs"])
    for hypothesis in state["hypotheses"]:
        for field in (
            "source_refs",
            "supporting_refs",
            "opposing_refs",
            "tier_update_refs",
            "renewal_evidence_refs",
        ):
            refs.update(str(item) for item in hypothesis[field])
    for zone in state["zones"]:
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
        ):
            refs.update(str(item) for item in zone[field])
    for modifier in state["path_modifiers"]:
        refs.update(str(item) for item in modifier["source_refs"])
    return refs


def _reference_tranche_failure_refs(
    state: Mapping[str, Any], reference: Mapping[str, Any]
) -> set[str]:
    """Collect only typed contradiction/invalidation refs for the parent.

    Generic source, support, renewal, tier-update, and zone-observation refs
    are intentionally excluded: path relevance alone cannot prove failure.
    """

    refs: set[str] = set()
    hypothesis_ids = set(reference["supporting_hypothesis_ids"])
    zone_ids = set(reference["zone_ids"])
    for hypothesis in state["hypotheses"]:
        if hypothesis["hypothesis_id"] not in hypothesis_ids:
            continue
        refs.update(str(item) for item in hypothesis["opposing_refs"])
    modifier_ids = {
        str(modifier_id)
        for hypothesis in state["hypotheses"]
        if hypothesis["hypothesis_id"] in hypothesis_ids
        for modifier_id in hypothesis["path_modifier_ids"]
    } | {
        str(modifier_id)
        for zone in state["zones"]
        if zone["zone_id"] in zone_ids
        for modifier_id in zone["path_modifier_ids"]
    }
    for modifier in state["path_modifiers"]:
        if (
            modifier["modifier_id"] in modifier_ids
            and modifier["status"] == "ACTIVE"
            and modifier["effect"] == "INVALIDATES_PATH"
        ):
            refs.update(str(item) for item in modifier["source_refs"])
    return refs


def _material_market_change(
    *, previous_state: Mapping[str, Any], current_state: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    """Detect a semantic market change only when it carries a fresh PIT ref."""

    previous_refs = _state_pit_refs(previous_state)
    changed_refs: set[str] = set()
    previous_hypotheses = {
        row["hypothesis_id"]: row for row in previous_state["hypotheses"]
    }
    current_hypotheses = {
        row["hypothesis_id"]: row for row in current_state["hypotheses"]
    }
    for hypothesis_id, hypothesis in current_hypotheses.items():
        old = previous_hypotheses.get(hypothesis_id)
        if old is None or any(
            hypothesis.get(field) != old.get(field)
            for field in (
                "status",
                "subjective_plausibility_tier",
                "expires_at",
                "mechanism",
            )
        ):
            for field in (
                "source_refs",
                "supporting_refs",
                "opposing_refs",
                "tier_update_refs",
                "renewal_evidence_refs",
            ):
                changed_refs.update(str(item) for item in hypothesis[field])

    previous_zones = {row["zone_id"]: row for row in previous_state["zones"]}
    current_zones = {row["zone_id"]: row for row in current_state["zones"]}
    for zone_id, zone in current_zones.items():
        old = previous_zones.get(zone_id)
        if old is None or any(
            zone.get(field) != old.get(field)
            for field in (
                "lower_bound",
                "upper_bound",
                "quality",
                "touch_count",
                "touch_refs",
                "reaction_refs",
                "volume_at_price_refs",
                "dwell_time_refs",
                "orderbook_flow_refs",
                "leverage_refs",
                "options_refs",
            )
        ):
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
            ):
                changed_refs.update(str(item) for item in zone[field])

    previous_modifiers = {
        row["modifier_id"]: row for row in previous_state["path_modifiers"]
    }
    current_modifiers = {
        row["modifier_id"]: row for row in current_state["path_modifiers"]
    }
    for modifier_id, modifier in current_modifiers.items():
        old = previous_modifiers.get(modifier_id)
        if old is None or any(
            modifier.get(field) != old.get(field)
            for field in ("status", "effect", "source_refs", "affected_hypothesis_ids")
        ):
            changed_refs.update(str(item) for item in modifier["source_refs"])
    previous_regime = previous_state["market_regime_state"]
    current_regime = current_state["market_regime_state"]
    if (
        current_regime["regime"] != previous_regime["regime"]
        or current_regime["regime_feature_assessments"]
        != previous_regime["regime_feature_assessments"]
    ):
        changed_refs.update(
            str(item) for item in current_regime["transition_evidence_refs"]
        )
        for assessment in current_regime["regime_feature_assessments"]:
            changed_refs.update(str(item) for item in assessment["evidence_refs"])
    fresh_refs = sorted(changed_refs - previous_refs)
    return bool(fresh_refs), fresh_refs


_PLAN_TIME_ONLY_FIELDS = frozenset(
    {
        "as_of",
        "expires_at",
        "horizon_at",
        "review_deadline",
        "time_stop_at",
        "max_wait_until",
        "next_watchdog_review_at",
    }
)


def _without_plan_clock_noise(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_plan_clock_noise(item)
            for key, item in value.items()
            if key not in _PLAN_TIME_ONLY_FIELDS
        }
    if isinstance(value, list):
        return [_without_plan_clock_noise(item) for item in value]
    return value


def _material_plan_signature(plan: Mapping[str, Any]) -> str:
    """Hash semantic planning content while excluding advancing wall clocks."""

    selected = _selected_candidate(plan)
    selected_tranche = next(
        (
            row
            for row in plan["risk_tranches"]
            if row["candidate_id"] == selected["candidate_id"]
        ),
        None,
    )
    selected_modifier = next(
        (
            row
            for row in plan["path_modifier_candidate_assessments"]
            if row["candidate_id"] == selected["candidate_id"]
        ),
        None,
    )
    material = {
        "reference_context": plan["reference_context"],
        "reference_tranche_state": plan["reference_tranche_state"],
        "plan_state": plan["plan_state"],
        "selected_candidate": selected,
        "selected_tranche": selected_tranche,
        "selected_modifier_assessment": selected_modifier,
        "alternative_candidate_rank": plan["alternative_candidate_rank"],
        "wait_assessment": plan["wait_assessment"],
        "risk_availability_assessment": plan["risk_availability_assessment"],
        "reference_risk_unit_budget": plan["reference_risk_unit_budget"],
        "selected_candidate_reference_risk_budget": plan[
            "selected_candidate_reference_risk_budget"
        ],
        "reentry_budget_state": plan["reentry_budget_state"],
    }
    return canonical_digest(_without_plan_clock_noise(material))


def _cluster_dependencies(
    state: Mapping[str, Any], cluster_id: str
) -> set[str]:
    hypotheses = {
        str(row["hypothesis_id"]): row for row in state["hypotheses"]
    }
    clusters = {
        str(row["cluster_id"]): row for row in state["dependency_clusters"]
    }
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_REENTRY_CLUSTER_MISSING"
        )
    return {
        str(group)
        for hypothesis_id in cluster["member_hypothesis_ids"]
        for group in hypotheses[hypothesis_id]["dependency_groups"]
    }


def _selected_counted_instrument_churn_reference_risk(
    plan: Mapping[str, Any],
) -> Decimal:
    """Return risk consumed by the selected action on the sole instrument ledger."""

    selected = next(
        row
        for row in plan["candidates"]
        if row["candidate_id"] == plan["selected_candidate_id"]
    )
    if (
        not v32_action_consumes_instrument_churn_budget_v1(
            action_kind=selected["action_kind"],
            reentry_budget_status=plan["reentry_budget_state"]["status"],
        )
        or selected["feasibility"] != "ELIGIBLE"
    ):
        return Decimal("0")
    consumed = Decimal(plan["selected_candidate_reference_risk_budget"])
    return consumed if consumed > 0 else Decimal("0")


def _selected_counted_reentry_reference_risk(
    plan: Mapping[str, Any],
) -> Decimal:
    """Compatibility alias for the instrument-wide churn calculation."""

    return _selected_counted_instrument_churn_reference_risk(plan)


def _selected_initial_probe_reference_risk(
    plan: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, Decimal]:
    """Identify the sole free initial probe that must arm a durable lock."""

    selected = _selected_candidate(plan)
    risk = Decimal(plan["selected_candidate_reference_risk_budget"])
    if (
        plan["reentry_budget_state"]["status"] == "INACTIVE"
        and selected["action_kind"] == "OPEN_PROBE"
        and selected["feasibility"] == "ELIGIBLE"
        and risk > 0
    ):
        return selected, risk
    return None, Decimal("0")


def _none_reference_tranche_state() -> dict[str, Any]:
    return {
        "status": "NONE",
        "tranche_id": None,
        "direction": "NONE",
        "entry_reference": None,
        "protective_stop_reference": None,
        "valid_until": None,
        "supporting_hypothesis_ids": [],
        "supporting_cluster_ids": [],
        "zone_ids": [],
    }


def _resulting_reference_tranche_state(
    plan: Mapping[str, Any], *, next_as_of: str | None = None
) -> dict[str, Any]:
    """Derive the next research-only parent from the selected sealed plan.

    This is plan lineage, not a fill or position claim. OPEN_PROBE, ADD,
    REENTER, and REVERSE promote their exact selected research tranche; HOLD
    and REDUCE retain the current parent; CLOSE retires it.
    """

    selected = _selected_candidate(plan)
    action = selected["action_kind"]
    if action == "CLOSE":
        return _none_reference_tranche_state()
    if action in {"OPEN_PROBE", "ADD", "REENTER", "REVERSE"}:
        selected_risk = Decimal(
            plan["selected_candidate_reference_risk_budget"]
        )
        tranche = next(
            (
                row
                for row in plan["risk_tranches"]
                if row["candidate_id"] == selected["candidate_id"]
                and row["tranche_id"] == selected["risk_tranche_id"]
            ),
            None,
        )
        if (
            selected["feasibility"] != "ELIGIBLE"
            or selected_risk <= 0
            or tranche is None
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_SELECTED_RISK_TRANCHE_INVALID"
            )
        valid_until_moment = min(
            _moment(
                plan["expires_at"],
                "V32_PLAN_CONTINUITY_REFERENCE_TRANCHE_TIME_INVALID",
            ),
            _moment(
                selected["horizon_at"],
                "V32_PLAN_CONTINUITY_REFERENCE_TRANCHE_TIME_INVALID",
            ),
            _moment(
                tranche["time_stop_at"],
                "V32_PLAN_CONTINUITY_REFERENCE_TRANCHE_TIME_INVALID",
            ),
        )
        valid_until = valid_until_moment.isoformat().replace("+00:00", "Z")
        if next_as_of is not None and valid_until_moment <= _moment(
            next_as_of,
            "V32_PLAN_CONTINUITY_REFERENCE_TRANCHE_TIME_INVALID",
        ):
            return _none_reference_tranche_state()
        return {
            "status": "ACTIVE",
            "tranche_id": tranche["tranche_id"],
            "direction": selected["direction"],
            "entry_reference": tranche["conditional_entry_reference"],
            "protective_stop_reference": tranche[
                "protective_stop_reference"
            ],
            "valid_until": valid_until,
            "supporting_hypothesis_ids": list(selected["hypothesis_ids"]),
            "supporting_cluster_ids": list(selected["cluster_ids"]),
            "zone_ids": list(selected["zone_ids"]),
        }
    carried = dict(plan["reference_tranche_state"])
    if (
        carried["status"] == "ACTIVE"
        and next_as_of is not None
        and _moment(
            carried["valid_until"],
            "V32_PLAN_CONTINUITY_REFERENCE_TRANCHE_TIME_INVALID",
        )
        <= _moment(
            next_as_of,
            "V32_PLAN_CONTINUITY_REFERENCE_TRANCHE_TIME_INVALID",
        )
    ):
        return _none_reference_tranche_state()
    return carried


def _verify_reference_tranche_continuity(
    *,
    previous_state: Mapping[str, Any],
    current_state: Mapping[str, Any],
    previous_plan: Mapping[str, Any],
    current_plan: Mapping[str, Any],
) -> None:
    previous_failure_refs = set(
        previous_plan["reentry_budget_state"]["failure_evidence_refs"]
    )
    current_failure_refs = set(
        current_plan["reentry_budget_state"]["failure_evidence_refs"]
    )
    new_failure_refs = current_failure_refs - previous_failure_refs
    resulting = _resulting_reference_tranche_state(
        previous_plan, next_as_of=current_state["as_of"]
    )
    if new_failure_refs:
        fresh_relevant_refs = _reference_tranche_failure_refs(
            current_state, resulting
        ) - _reference_tranche_failure_refs(previous_state, resulting)
        if (
            resulting["status"] != "ACTIVE"
            or current_plan["reentry_budget_state"]["failure_cluster_id"]
            not in resulting["supporting_cluster_ids"]
            or not new_failure_refs.issubset(fresh_relevant_refs)
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_FAILURE_NOT_BOUND_TO_REFERENCE_TRANCHE"
            )
        expected = _none_reference_tranche_state()
    else:
        expected = resulting
    if dict(current_plan["reference_tranche_state"]) != expected:
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_REFERENCE_TRANCHE_TRANSITION_INVALID"
        )


def _verify_reentry_budget_continuity(
    *,
    previous_state: Mapping[str, Any],
    current_state: Mapping[str, Any],
    previous_plan: Mapping[str, Any],
    current_plan: Mapping[str, Any],
) -> None:
    """Prevent counter resets and allow reset only on the three hard gates.

    Canonical REENTER keeps its original counted behavior.  While the sole
    instrument ledger is active, a selected eligible positive-risk OPEN_PROBE
    or REVERSE also consumes one attempt and its exact reference risk,
    regardless of direction.  An initial OPEN_PROBE on INACTIVE remains free,
    but its exact durable successor must arm the single-use lock or record a
    fresh initial-failure transition.  An unrelated WAIT cannot invent one.
    """

    previous = previous_plan["reentry_budget_state"]
    current = current_plan["reentry_budget_state"]
    if current["budget_id"] != previous["budget_id"]:
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_REENTRY_BUDGET_ID_MUTATED"
        )
    if any(
        current[field] != previous[field]
        for field in ("churn_scope", "instrument", "window_policy")
    ):
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_REENTRY_INSTRUMENT_SCOPE_MUTATED"
        )
    current_reset = current["status"] == "RESET"
    if current_reset:
        previous_cluster_id = previous["failure_cluster_id"]
        retained_failure_cluster_id = current["failure_cluster_id"]
        new_cluster_id = current["reset_independent_cluster_id"]
        previous_regime = previous_state["market_regime_state"]["regime"]
        current_regime = current_state["market_regime_state"]["regime"]
        current_refs = _state_pit_refs(current_state)
        previous_refs = _state_pit_refs(previous_state)
        reset_refs = set(current["reset_evidence_refs"])
        previous_failure_refs = set(previous["failure_evidence_refs"])
        current_failure_refs = set(current["failure_evidence_refs"])
        current_as_of = _moment(
            current_state["as_of"],
            "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID",
        )
        previous_window_expired = False
        if (
            previous["status"] == "EXHAUSTED"
            and previous["rolling_window_expires_at"] is not None
        ):
            previous_window_expired = (
                _moment(
                    previous["rolling_window_expires_at"],
                    "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID",
                )
                <= current_as_of
            )
        reset_tranche = next(
            (
                row
                for row in current_plan["risk_tranches"]
                if row["tranche_id"] == current["reset_new_tranche_id"]
                and new_cluster_id in row["supporting_cluster_ids"]
            ),
            None,
        )
        if (
            not previous_window_expired
            or previous_cluster_id is None
            or retained_failure_cluster_id != previous_cluster_id
            or new_cluster_id is None
            or new_cluster_id == previous_cluster_id
            or _cluster_dependencies(previous_state, previous_cluster_id)
            .intersection(_cluster_dependencies(current_state, new_cluster_id))
            or current["reset_previous_regime"] != previous_regime
            or current["reset_current_regime"] != current_regime
            or current_regime == previous_regime
            or current_state["market_regime_state"]["previous_regime"]
            != previous_regime
            or not reset_refs
            or not reset_refs.issubset(current_refs - previous_refs)
            or not previous_failure_refs.issubset(current_failure_refs)
            or current["rolling_window_started_at"] != current_state["as_of"]
            or reset_tranche is None
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_REENTRY_RESET_QUALIFICATION_INVALID"
            )
        return

    if previous["status"] == "RESET":
        consumed = _selected_counted_instrument_churn_reference_risk(
            previous_plan
        )
        failure_delta = (
            current["consecutive_failures"] - previous["consecutive_failures"]
        )
        previous_failure_refs = set(previous["failure_evidence_refs"])
        current_failure_refs = set(current["failure_evidence_refs"])
        new_failure_refs = current_failure_refs - previous_failure_refs
        fresh_state_refs = _state_pit_refs(current_state) - _state_pit_refs(
            previous_state
        )
        if (
            current["status"] == "INACTIVE"
            or current["failure_cluster_id"]
            != previous["reset_independent_cluster_id"]
            or current["direction"] != previous["direction"]
            or current["rolling_window_started_at"]
            != previous["rolling_window_started_at"]
            or current["rolling_window_expires_at"]
            != previous["rolling_window_expires_at"]
            or current["max_cumulative_reference_risk"]
            != previous["max_cumulative_reference_risk"]
            or current["attempts_used"]
            != previous["attempts_used"] + (1 if consumed > 0 else 0)
            or not previous_failure_refs.issubset(current_failure_refs)
            or not new_failure_refs.issubset(fresh_state_refs)
            or failure_delta != (1 if new_failure_refs else 0)
            or (consumed <= 0 and new_failure_refs)
            or Decimal(current["cumulative_reference_risk"])
            != Decimal(previous["cumulative_reference_risk"]) + consumed
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_REENTRY_RESET_COMMIT_INVALID"
            )
        return

    if previous["status"] == "INACTIVE":
        initial_candidate, initial_risk = _selected_initial_probe_reference_risk(
            previous_plan
        )
        if initial_risk > 0:
            previous_as_of = _moment(
                previous_state["as_of"],
                "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID",
            )
            expected_end = (
                previous_as_of
                + timedelta(seconds=CURRENT_PILOT_REENTRY_WINDOW_SECONDS)
            ).isoformat().replace("+00:00", "Z")
            common_transition_invalid = (
                initial_candidate is None
                or current["direction"] != initial_candidate["direction"]
                or current["rolling_window_started_at"]
                != previous_state["as_of"]
                or current["rolling_window_expires_at"] != expected_end
                or current["attempts_used"] != 0
                or current["max_attempts"] != REENTRY_MAX_ATTEMPTS
                or Decimal(current["cumulative_reference_risk"]) != 0
                or Decimal(current["max_cumulative_reference_risk"])
                != REENTRY_MAX_CUMULATIVE_REFERENCE_RISK
            )
            if current["status"] == "INITIAL_PROBE_USED":
                invalid = (
                    common_transition_invalid
                    or current["consecutive_failures"] != 0
                    or current["failure_cluster_id"] is not None
                    or current["failure_evidence_refs"]
                )
            elif current["status"] == "AVAILABLE":
                fresh_failure_refs = set(
                    current["failure_evidence_refs"]
                ).intersection(
                    _state_pit_refs(current_state)
                    - _state_pit_refs(previous_state)
                )
                invalid = (
                    common_transition_invalid
                    or current["consecutive_failures"] != 1
                    or current["failure_cluster_id"]
                    not in initial_candidate["cluster_ids"]
                    or not fresh_failure_refs
                )
            else:
                invalid = True
            if invalid:
                raise V32ActionPlanContinuityError(
                    "V32_PLAN_CONTINUITY_INITIAL_PROBE_LOCK_REQUIRED"
                )
            return
        if current["status"] != "INACTIVE":
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_INITIAL_FAILURE_WITHOUT_PROBE_FORBIDDEN"
            )
        return

    if previous["status"] == "INITIAL_PROBE_USED":
        previous_expiry = _moment(
            previous["rolling_window_expires_at"],
            "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID",
        )
        current_as_of = _moment(
            current_state["as_of"],
            "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID",
        )
        if current_as_of >= previous_expiry:
            if current["status"] != "INACTIVE":
                raise V32ActionPlanContinuityError(
                    "V32_PLAN_CONTINUITY_INITIAL_PROBE_LOCK_EXPIRY_INVALID"
                )
            return
        consumed = _selected_counted_instrument_churn_reference_risk(
            previous_plan
        )
        selected = _selected_candidate(previous_plan)
        expected_attempts = previous["attempts_used"] + (
            1 if consumed > 0 else 0
        )
        expected_cumulative = (
            Decimal(previous["cumulative_reference_risk"]) + consumed
        )
        expected_direction = (
            selected["direction"] if consumed > 0 else previous["direction"]
        )
        exhausted_without_failure = (
            expected_attempts >= previous["max_attempts"]
            or expected_cumulative
            >= Decimal(previous["max_cumulative_reference_risk"])
        )
        common_invalid = (
            current["direction"] != expected_direction
            or current["rolling_window_started_at"]
            != previous["rolling_window_started_at"]
            or current["rolling_window_expires_at"]
            != previous["rolling_window_expires_at"]
            or current["max_cumulative_reference_risk"]
            != previous["max_cumulative_reference_risk"]
            or current["attempts_used"] != expected_attempts
            or Decimal(current["cumulative_reference_risk"])
            != expected_cumulative
        )
        if current["status"] == "INITIAL_PROBE_USED":
            expected_cooldown = (
                previous["rolling_window_expires_at"]
                if exhausted_without_failure
                else None
            )
            if (
                common_invalid
                or current["consecutive_failures"] != 0
                or current["failure_cluster_id"] is not None
                or current["failure_evidence_refs"]
                or current["cooldown_until"] != expected_cooldown
            ):
                raise V32ActionPlanContinuityError(
                    "V32_PLAN_CONTINUITY_INITIAL_PROBE_LOCK_MUTATED"
                )
            return
        fresh_failure_refs = set(current["failure_evidence_refs"]).intersection(
            _state_pit_refs(current_state) - _state_pit_refs(previous_state)
        )
        failure_exhausted = exhausted_without_failure or (
            current["consecutive_failures"] >= 2
        )
        expected_status = "EXHAUSTED" if failure_exhausted else "AVAILABLE"
        expected_cooldown = (
            previous["rolling_window_expires_at"]
            if failure_exhausted
            else None
        )
        if (
            common_invalid
            or current["status"] != expected_status
            or current["consecutive_failures"] != 1
            or current["failure_cluster_id"]
            not in selected.get("cluster_ids", [])
            or not fresh_failure_refs
            or current["cooldown_until"] != expected_cooldown
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_INITIAL_PROBE_FAILURE_INVALID"
            )
        return

    consumed = _selected_counted_instrument_churn_reference_risk(previous_plan)
    failure_delta = (
        current["consecutive_failures"] - previous["consecutive_failures"]
    )
    previous_failure_refs = set(previous["failure_evidence_refs"])
    current_failure_refs = set(current["failure_evidence_refs"])
    new_failure_refs = current_failure_refs - previous_failure_refs
    fresh_state_refs = _state_pit_refs(current_state) - _state_pit_refs(
        previous_state
    )
    if (
        current["status"] == "INACTIVE"
        or current["failure_cluster_id"] != previous["failure_cluster_id"]
        or current["direction"] != previous["direction"]
        or current["rolling_window_started_at"]
        != previous["rolling_window_started_at"]
        or current["rolling_window_expires_at"]
        != previous["rolling_window_expires_at"]
        or current["max_cumulative_reference_risk"]
        != previous["max_cumulative_reference_risk"]
        or current["attempts_used"]
        != previous["attempts_used"] + (1 if consumed > 0 else 0)
        or not previous_failure_refs.issubset(current_failure_refs)
        or not new_failure_refs.issubset(fresh_state_refs)
        or failure_delta != (1 if new_failure_refs else 0)
        or (consumed <= 0 and new_failure_refs)
        or Decimal(current["cumulative_reference_risk"])
        != Decimal(previous["cumulative_reference_risk"]) + consumed
    ):
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_REENTRY_COUNTER_TRANSITION_INVALID"
        )
    previous_cooldown = previous["cooldown_until"]
    current_cooldown = current["cooldown_until"]
    if (
        previous_cooldown is not None
        and _moment(previous_cooldown, "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID")
        > _moment(current_state["as_of"], "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID")
        and (
            current_cooldown is None
            or _moment(current_cooldown, "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID")
            < _moment(previous_cooldown, "V32_PLAN_CONTINUITY_REENTRY_TIME_INVALID")
        )
    ):
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_REENTRY_COOLDOWN_SHORTENED"
        )




def compose_v32_action_plan_continuity_v1(
    *,
    current_dynamic_state: Mapping[str, Any],
    current_action_plan: Mapping[str, Any],
    durable_previous_dynamic_state: Mapping[str, Any] | None,
    durable_previous_dynamic_state_digest: str | None,
    durable_previous_action_plan: Mapping[str, Any] | None,
    durable_previous_action_plan_digest: str | None,
) -> dict[str, Any]:
    """Bind one watchdog to the exact durable predecessor plan."""

    try:
        current_state_digest = verify_v32_dynamic_research_state_v1(
            current_dynamic_state
        )
        current_plan_digest = verify_v32_dynamic_action_plan_v1(
            current_action_plan, dynamic_research_state=current_dynamic_state
        )
    except (V32DynamicResearchError, V32DynamicActionPlanError) as exc:
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_CURRENT_INVALID"
        ) from exc

    run_id = current_dynamic_state["run_id"]
    cycle_index = current_dynamic_state["cycle_index"]
    as_of = current_dynamic_state["as_of"]
    current_watchdog = current_action_plan["inactivity_opportunity_watchdog"]
    previous_state_digest: str | None = None
    previous_plan_digest: str | None = None
    qualified_probe_ids: list[str] = []
    material_change = False
    material_change_refs: list[str] = []
    material_plan_change = False
    activity_basis = "GENESIS"
    model_adaptation_basis = "GENESIS"

    if cycle_index == 1:
        if (
            durable_previous_dynamic_state is not None
            or durable_previous_dynamic_state_digest is not None
            or durable_previous_action_plan is not None
            or durable_previous_action_plan_digest is not None
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_GENESIS_PREVIOUS_FORBIDDEN"
            )
        if current_action_plan["reentry_budget_state"]["status"] != "INACTIVE":
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_GENESIS_REENTRY_BUDGET_NOT_INACTIVE"
            )
        if dict(current_action_plan["reference_tranche_state"]) != (
            _none_reference_tranche_state()
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_GENESIS_REFERENCE_TRANCHE_FORBIDDEN"
            )
        expected_since = as_of
        expected_consecutive = 0
        expected_model_since = as_of
        expected_model_consecutive = 0
    else:
        if (
            durable_previous_dynamic_state is None
            or durable_previous_dynamic_state_digest is None
            or durable_previous_action_plan is None
            or durable_previous_action_plan_digest is None
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_PREVIOUS_REQUIRED"
            )
        try:
            previous_state_digest = verify_v32_dynamic_research_state_v1(
                durable_previous_dynamic_state
            )
            previous_plan_digest = verify_v32_dynamic_action_plan_v1(
                durable_previous_action_plan,
                dynamic_research_state=durable_previous_dynamic_state,
            )
        except (V32DynamicResearchError, V32DynamicActionPlanError) as exc:
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_PREVIOUS_INVALID"
            ) from exc
        if (
            durable_previous_dynamic_state.get("run_id") != run_id
            or durable_previous_action_plan.get("run_id") != run_id
            or previous_state_digest != durable_previous_dynamic_state_digest
            or current_dynamic_state.get("previous_state_digest")
            != durable_previous_dynamic_state_digest
            or previous_plan_digest != durable_previous_action_plan_digest
            or durable_previous_dynamic_state.get("cycle_index")
            != cycle_index - 1
            or durable_previous_action_plan.get("cycle_index") != cycle_index - 1
            or _moment(durable_previous_dynamic_state.get("as_of"), "V32_PLAN_CONTINUITY_TIME_INVALID")
            >= _moment(as_of, "V32_PLAN_CONTINUITY_TIME_INVALID")
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_PREVIOUS_IDENTITY_INVALID"
            )
        _verify_reference_tranche_continuity(
            previous_state=durable_previous_dynamic_state,
            current_state=current_dynamic_state,
            previous_plan=durable_previous_action_plan,
            current_plan=current_action_plan,
        )
        previous_watchdog = durable_previous_action_plan[
            "inactivity_opportunity_watchdog"
        ]
        if (
            current_watchdog["max_wait_cycles_before_review"]
            != previous_watchdog["max_wait_cycles_before_review"]
            or current_watchdog["max_inactivity_seconds"]
            != previous_watchdog["max_inactivity_seconds"]
        ):
            raise V32ActionPlanContinuityError(
                "V32_PLAN_CONTINUITY_WATCHDOG_POLICY_DRIFT"
            )
        _verify_reentry_budget_continuity(
            previous_state=durable_previous_dynamic_state,
            current_state=current_dynamic_state,
            previous_plan=durable_previous_action_plan,
            current_plan=current_action_plan,
        )
        qualified_probe_ids = _qualified_probe_candidate_ids(
            durable_previous_action_plan
        )
        material_change, material_change_refs = _material_market_change(
            previous_state=durable_previous_dynamic_state,
            current_state=current_dynamic_state,
        )
        material_plan_change = (
            _material_plan_signature(durable_previous_action_plan)
            != _material_plan_signature(current_action_plan)
        )
        if qualified_probe_ids:
            expected_since = durable_previous_dynamic_state["as_of"]
            expected_consecutive = 0
            activity_basis = "QUALIFIED_TESTABLE_RISK_PLAN"
        else:
            expected_since = previous_watchdog["inactivity_since"]
            expected_consecutive = previous_watchdog[
                "consecutive_wait_cycles"
            ] + 1
            activity_basis = "NO_QUALIFIED_TESTABLE_RISK_PLAN"

        if material_change or material_plan_change:
            expected_model_since = as_of
            expected_model_consecutive = 0
            if material_change and material_plan_change:
                model_adaptation_basis = "MATERIAL_STATE_AND_PLAN_CHANGE"
            elif material_change:
                model_adaptation_basis = "MATERIAL_STATE_CHANGE"
            else:
                model_adaptation_basis = "MATERIAL_PLAN_CHANGE"
        else:
            expected_model_since = previous_watchdog[
                "model_adaptation_inactivity_since"
            ]
            expected_model_consecutive = previous_watchdog[
                "consecutive_model_stale_cycles"
            ] + 1
            model_adaptation_basis = "NO_MATERIAL_STATE_OR_PLAN_CHANGE"

    if (
        current_watchdog["inactivity_since"] != expected_since
        or current_watchdog["consecutive_wait_cycles"] != expected_consecutive
        or current_watchdog["model_adaptation_inactivity_since"]
        != expected_model_since
        or current_watchdog["consecutive_model_stale_cycles"]
        != expected_model_consecutive
        or current_watchdog["forces_action"] is not False
    ):
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_WATCHDOG_RESET_OR_FORCE_INVALID"
        )

    due = current_watchdog["forced_review_due"]
    risk_due = current_watchdog["testable_risk_plan_review_due"]
    model_due = current_watchdog["model_adaptation_review_due"]
    if due is not (risk_due or model_due):
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_DUAL_CLOCK_DUE_INVALID"
        )
    required_status = (
        "COMPLETE_BASELINE_OPPORTUNITY_AND_SHADOW_REVIEW"
        if due
        else "NOT_DUE_NO_PREMATURE_REVIEW_MATERIAL"
    )
    return self_digest(
        {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "as_of": as_of,
            "current_dynamic_state_digest": current_state_digest,
            "current_action_plan_digest": current_plan_digest,
            "previous_dynamic_state_digest": previous_state_digest,
            "previous_action_plan_digest": previous_plan_digest,
            "previous_qualified_probe_candidate_ids": qualified_probe_ids,
            "material_market_change_detected": material_change,
            "material_change_evidence_refs": material_change_refs,
            "material_action_plan_change_detected": material_plan_change,
            "activity_basis": activity_basis,
            "model_adaptation_basis": model_adaptation_basis,
            "watchdog_activity_policy": (
                "TESTABLE_RISK_PLAN_CLOCK_RESETS_ONLY_AFTER_SELECTED_FUNDED_"
                "OPEN_PROBE_OR_REENTER_MODEL_ADAPTATION_CLOCK_RESETS_ON_"
                "MATERIAL_STATE_OR_PLAN_CHANGE_NEITHER_CLOCK_IS_REAL_EXPOSURE"
            ),
            "expected_inactivity_since": expected_since,
            "expected_consecutive_wait_cycles": expected_consecutive,
            "expected_model_adaptation_inactivity_since": expected_model_since,
            "expected_consecutive_model_stale_cycles": expected_model_consecutive,
            "max_wait_cycles_before_review": current_watchdog[
                "max_wait_cycles_before_review"
            ],
            "max_inactivity_seconds": current_watchdog[
                "max_inactivity_seconds"
            ],
            "testable_risk_plan_review_due": risk_due,
            "model_adaptation_review_due": model_due,
            "forced_review_due": due,
            "required_response_status": required_status,
            "forces_action": False,
            "real_exposure_claim": "NONE_RESEARCH_PLAN_ONLY",
            "continuity_status": (
                "VERIFIED_DURABLE_DUAL_CLOCKS_NO_LABEL_SUBSTITUTION_OR_"
                "MATERIAL_CHANGE_RESET_OF_TESTABLE_RISK_PLAN_CLOCK"
            ),
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        DIGEST_FIELD,
    )


def verify_v32_action_plan_continuity_v1(
    document: Mapping[str, Any],
    *,
    current_dynamic_state: Mapping[str, Any],
    current_action_plan: Mapping[str, Any],
    durable_previous_dynamic_state: Mapping[str, Any] | None,
    durable_previous_dynamic_state_digest: str | None,
    durable_previous_action_plan: Mapping[str, Any] | None,
    durable_previous_action_plan_digest: str | None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _FIELDS:
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        rebuilt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current_dynamic_state,
            current_action_plan=current_action_plan,
            durable_previous_dynamic_state=durable_previous_dynamic_state,
            durable_previous_dynamic_state_digest=(
                durable_previous_dynamic_state_digest
            ),
            durable_previous_action_plan=durable_previous_action_plan,
            durable_previous_action_plan_digest=(
                durable_previous_action_plan_digest
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ActionPlanContinuityError):
            raise
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_RECEIPT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32ActionPlanContinuityError(
            "V32_PLAN_CONTINUITY_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "DIGEST_FIELD",
    "SCHEMA_ID",
    "V32ActionPlanContinuityError",
    "compose_v32_action_plan_continuity_v1",
    "verify_v32_action_plan_continuity_v1",
]
