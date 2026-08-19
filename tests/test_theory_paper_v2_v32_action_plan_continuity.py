from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest

from tests import test_theory_paper_v2_v32_dynamic_action_plan as action_fixture
from trade_system.theory_paper_v2.application.v32_action_plan_continuity import (
    DIGEST_FIELD as CONTINUITY_DIGEST_FIELD,
    V32ActionPlanContinuityError,
    _none_reference_tranche_state,
    _resulting_reference_tranche_state,
    _selected_counted_instrument_churn_reference_risk,
    _verify_reentry_budget_continuity,
    compose_v32_action_plan_continuity_v1,
    verify_v32_action_plan_continuity_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_dynamic_action_plan import (
    DIGEST_FIELD as ACTION_PLAN_DIGEST_FIELD,
    V32DynamicActionPlanError,
    build_v32_dynamic_action_plan_v1,
)
from trade_system.theory_paper_v2.domain.v32_dynamic_research import (
    DIGEST_FIELD as DYNAMIC_STATE_DIGEST_FIELD,
    build_v32_dynamic_research_state_v1,
)


RUN_ID = "v32-test-run"
START = datetime(2026, 8, 7, tzinfo=UTC)


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _genesis_state(*, run_id: str = RUN_ID, long_tier: str = "HIGH") -> dict:
    base = action_fixture._dynamic_state(long_tier=long_tier)
    if run_id == base["run_id"]:
        return base
    return build_v32_dynamic_research_state_v1(
        run_id=run_id,
        cycle_index=1,
        as_of=base["as_of"],
        frame_mode="FULL_CONTEXT",
        previous_state_digest=None,
        market_regime_state=base["market_regime_state"],
        unknowns=base["unknowns"],
        zones=base["zones"],
        hypotheses=base["hypotheses"],
        path_modifiers=base["path_modifiers"],
        dependency_clusters=base["dependency_clusters"],
    )


def _next_state(
    previous: dict,
    *,
    cycle_index: int,
    as_of: datetime,
    material_change: bool = False,
    laundered_change: bool = False,
    initial_failure_ref: str | None = None,
    initial_failure_hypothesis_id: str = "h-long",
    fresh_supporting_ref: str | None = None,
) -> dict:
    hypotheses = deepcopy(previous["hypotheses"])
    for hypothesis in hypotheses:
        hypothesis["parent_revision_digest"] = previous[
            DYNAMIC_STATE_DIGEST_FIELD
        ]
        hypothesis["previous_subjective_plausibility_tier"] = hypothesis[
            "subjective_plausibility_tier"
        ]
        hypothesis["previous_expires_at"] = hypothesis["expires_at"]
        hypothesis["tier_update_refs"] = []
        hypothesis["renewal_evidence_refs"] = []
    clusters = deepcopy(previous["dependency_clusters"])
    zones = deepcopy(previous["zones"])
    if material_change:
        long_hypothesis = next(
            row for row in hypotheses if row["hypothesis_id"] == "h-long"
        )
        long_hypothesis["subjective_plausibility_tier"] = "LOW"
        long_hypothesis["tier_update_refs"] = ["fresh-pit:material-long-shift"]
        next(row for row in clusters if row["cluster_id"] == "c-long")[
            "aggregate_tier"
        ] = "LOW"
    if laundered_change:
        zones[0]["quality"] = "MEDIUM"
        next(
            row for row in hypotheses if row["hypothesis_id"] == "h-neutral"
        )["supporting_refs"].append("fresh-pit:unrelated-to-zone-change")
    if initial_failure_ref is not None:
        next(
            row
            for row in hypotheses
            if row["hypothesis_id"] == initial_failure_hypothesis_id
        )["opposing_refs"].append(initial_failure_ref)
    if fresh_supporting_ref is not None:
        next(
            row for row in hypotheses if row["hypothesis_id"] == "h-long"
        )["supporting_refs"].append(fresh_supporting_ref)
    return build_v32_dynamic_research_state_v1(
        run_id=previous["run_id"],
        cycle_index=cycle_index,
        as_of=_time(as_of),
        frame_mode="DELTA_UPDATE",
        previous_state_digest=previous[DYNAMIC_STATE_DIGEST_FIELD],
        market_regime_state={
            **deepcopy(previous["market_regime_state"]),
            "previous_regime": previous["market_regime_state"]["regime"],
            "transition_evidence_refs": [],
        },
        unknowns=deepcopy(previous["unknowns"]),
        zones=zones,
        hypotheses=hypotheses,
        path_modifiers=deepcopy(previous["path_modifiers"]),
        dependency_clusters=clusters,
    )


def _wait_comparisons() -> list[dict]:
    return [
        {
            "candidate_id": candidate_id,
            "dominance_reason": "INFORMATION_VALUE_DOMINATES_UNTIL_DEADLINE",
            "evidence_refs": [f"distinguishing-observation:{candidate_id}"],
            "rationale": "one bounded observation dominates immediate reference risk",
        }
        for candidate_id in ("open-long", "open-short")
    ]


def _build_plan(
    state: dict,
    *,
    action_kind: str,
    inactivity_since: str,
    consecutive_wait_cycles: int,
    model_adaptation_inactivity_since: str | None = None,
    consecutive_model_stale_cycles: int | None = None,
    max_wait_cycles_before_review: int = 8,
    max_inactivity_seconds: int = 7200,
    reentry_budget_state: dict | None = None,
    selected_parent_tranche_id: str | None = None,
    reference_tranche_state: dict | None = None,
) -> dict:
    if action_kind in {"HOLD", "ADD", "REVERSE"}:
        args = action_fixture._long_intent_args()
        if action_kind == "HOLD":
            args["selected_candidate_id"] = "hold-long"
            args["alternative_candidate_rank"] = [
                "add-long",
                "reduce-long",
                "close-long",
                "reverse-short",
            ]
        elif action_kind == "ADD":
            args["selected_candidate_id"] = "add-long"
            args["alternative_candidate_rank"] = [
                "hold-long",
                "reduce-long",
                "close-long",
                "reverse-short",
            ]
            if selected_parent_tranche_id is not None:
                next(
                    row
                    for row in args["candidates"]
                    if row["candidate_id"] == "add-long"
                )["parent_tranche_id"] = selected_parent_tranche_id
        else:
            args["selected_candidate_id"] = "reverse-short"
            args["alternative_candidate_rank"] = [
                "add-long",
                "hold-long",
                "reduce-long",
                "close-long",
            ]
        risk_shadow_ids = ["add-long", "reverse-short"]
    else:
        args = action_fixture._flat_args()
        risk_shadow_ids = ["open-long", "open-short"]
        if action_kind == "WAIT":
            args["selected_candidate_id"] = "wait"
            args["alternative_candidate_rank"] = ["open-long", "open-short"]
            args["wait_assessment"] = action_fixture._wait(_wait_comparisons())
        elif action_kind != "OPEN_PROBE":
            raise AssertionError(action_kind)

    args["dynamic_research_state"] = state
    if reference_tranche_state is not None:
        args["reference_tranche_state"] = deepcopy(reference_tranche_state)
        if reference_tranche_state["status"] == "ACTIVE":
            for candidate in args["candidates"]:
                if candidate["parent_tranche_id"] is not None:
                    candidate["parent_tranche_id"] = reference_tranche_state[
                        "tranche_id"
                    ]
            for tranche in args["risk_tranches"]:
                if tranche["candidate_id"] == "add-long":
                    tranche["parent_entry_reference"] = (
                        reference_tranche_state["entry_reference"]
                    )
                    tranche["previous_stop_reference"] = (
                        reference_tranche_state["protective_stop_reference"]
                    )
    if reentry_budget_state is not None:
        args["reentry_budget_state"] = deepcopy(reentry_budget_state)
    instrument = state["zones"][0]["instrument"]
    args["reentry_budget_state"]["budget_id"] = (
        f"instrument-churn::{state['run_id']}::{instrument}"
    )
    args["plan_id"] = f"plan-cycle-{state['cycle_index']}-{action_kind.lower()}"
    review_at = _time(
        datetime.fromisoformat(state["as_of"].replace("Z", "+00:00"))
        + timedelta(minutes=4)
    )
    args["wait_assessment"]["review_deadline"] = review_at
    as_of = datetime.fromisoformat(state["as_of"].replace("Z", "+00:00"))
    since = datetime.fromisoformat(inactivity_since.replace("Z", "+00:00"))
    due = (
        consecutive_wait_cycles >= max_wait_cycles_before_review
        or (as_of - since).total_seconds() >= max_inactivity_seconds
    )
    model_since_text = model_adaptation_inactivity_since or inactivity_since
    model_count = (
        consecutive_wait_cycles
        if consecutive_model_stale_cycles is None
        else consecutive_model_stale_cycles
    )
    model_since = datetime.fromisoformat(model_since_text.replace("Z", "+00:00"))
    risk_due = due
    model_due = (
        model_count >= max_wait_cycles_before_review
        or (as_of - model_since).total_seconds() >= max_inactivity_seconds
    )
    due = risk_due or model_due
    args["inactivity_opportunity_watchdog"] = {
        "inactivity_since": inactivity_since,
        "consecutive_wait_cycles": consecutive_wait_cycles,
        "testable_risk_plan_review_due": risk_due,
        "model_adaptation_inactivity_since": model_since_text,
        "consecutive_model_stale_cycles": model_count,
        "model_adaptation_review_due": model_due,
        "max_wait_cycles_before_review": max_wait_cycles_before_review,
        "max_inactivity_seconds": max_inactivity_seconds,
        "forced_review_due": due,
        "required_responses": (
            [
                "BASELINE_COMPARISON",
                "FULL_OPPORTUNITY_REVIEW",
                "SHADOW_PLAN_REFRESH",
            ]
            if due
            else []
        ),
        "baseline_comparison_refs": (
            ["wait-only-baseline", "simple-trend-baseline"] if due else []
        ),
        "shadow_plan_candidate_ids": risk_shadow_ids if due else [],
        "next_watchdog_review_at": review_at,
        "forces_action": False,
        "shadow_plan_scope": (
            "CONDITIONAL_RESEARCH_COMPARISON_NO_FILL_OR_FORCED_ENTRY"
        ),
        "clock_semantics": (
            "DUAL_DURABLE_CLOCKS_TESTABLE_RISK_PLAN_AND_MODEL_ADAPTATION_"
            "NEITHER_IS_REAL_EXPOSURE"
        ),
        "real_exposure_claim": "NONE_RESEARCH_PLAN_ONLY",
    }
    return build_v32_dynamic_action_plan_v1(**args)


def _initial_probe_used_budget(*, selected_at: str, direction: str = "LONG") -> dict:
    budget = action_fixture._inactive_reentry_budget()
    selected = datetime.fromisoformat(selected_at.replace("Z", "+00:00"))
    budget.update(
        {
            "direction": direction,
            "rolling_window_started_at": selected_at,
            "rolling_window_expires_at": _time(selected + timedelta(days=1)),
            "max_cumulative_reference_risk": "2",
            "status": "INITIAL_PROBE_USED",
        }
    )
    return budget


def _chain() -> tuple[list[dict], list[dict], list[dict]]:
    actions = [
        "WAIT",
        "WAIT",
        "WAIT",
        "WAIT",
        "WAIT",
        "WAIT",
        "WAIT",
        "WAIT",
        "WAIT",
        "OPEN_PROBE",
        "HOLD",
    ]
    expected_counts = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
    expected_model_counts = [0, 1, 2, 3, 4, 5, 6, 7, 8, 0, 0]
    states: list[dict] = []
    plans: list[dict] = []
    receipts: list[dict] = []
    inactivity_since = _time(START)
    model_inactivity_since = _time(START)
    for offset, (action, count, model_count) in enumerate(
        zip(actions, expected_counts, expected_model_counts)
    ):
        cycle = offset + 1
        if cycle == 1:
            state = _genesis_state()
        else:
            state = _next_state(
                states[-1],
                cycle_index=cycle,
                as_of=START + timedelta(minutes=4 * offset),
            )
        if cycle == 11:
            # Cycle 10 selected a qualified OPEN_PROBE, so the next cycle starts
            # a new inactivity interval at cycle 10's exact decision time.
            inactivity_since = states[-1]["as_of"]
        if cycle in {10, 11}:
            model_inactivity_since = state["as_of"]
        reentry_budget = (
            _initial_probe_used_budget(selected_at=states[-1]["as_of"])
            if cycle == 11
            else None
        )
        plan = _build_plan(
            state,
            action_kind=action,
            inactivity_since=inactivity_since,
            consecutive_wait_cycles=count,
            model_adaptation_inactivity_since=model_inactivity_since,
            consecutive_model_stale_cycles=model_count,
            reentry_budget_state=reentry_budget,
            reference_tranche_state=(
                _resulting_reference_tranche_state(plans[-1])
                if cycle == 11
                else None
            ),
        )
        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=state,
            current_action_plan=plan,
            durable_previous_dynamic_state=None if cycle == 1 else states[-1],
            durable_previous_dynamic_state_digest=(
                None
                if cycle == 1
                else states[-1][DYNAMIC_STATE_DIGEST_FIELD]
            ),
            durable_previous_action_plan=None if cycle == 1 else plans[-1],
            durable_previous_action_plan_digest=(
                None if cycle == 1 else plans[-1][ACTION_PLAN_DIGEST_FIELD]
            ),
        )
        states.append(state)
        plans.append(plan)
        receipts.append(receipt)
    return states, plans, receipts


def _reset_transition(
    *, current_as_of: datetime
) -> tuple[dict, dict, dict, dict]:
    previous_state = _genesis_state()
    current_state = deepcopy(previous_state)
    current_state["as_of"] = _time(current_as_of)
    current_state["market_regime_state"].update(
        {
            "regime": "RANGE",
            "previous_regime": "TREND_UP",
            "transition_evidence_refs": ["fresh-pit:qualified-reset"],
        }
    )
    previous_budget = action_fixture._available_reentry_budget()
    previous_budget.update(
        {
            "attempts_used": 2,
            "cumulative_reference_risk": "1",
            "consecutive_failures": 2,
            "cooldown_until": action_fixture.REENTRY_WINDOW_EXPIRES,
            "status": "EXHAUSTED",
        }
    )
    current_budget = deepcopy(previous_budget)
    current_budget.update(
        {
            "rolling_window_started_at": current_state["as_of"],
            "rolling_window_expires_at": _time(
                current_as_of + timedelta(hours=24)
            ),
            "attempts_used": 0,
            "cumulative_reference_risk": "0",
            "consecutive_failures": 0,
            "cooldown_until": None,
            "reset_independent_cluster_id": "c-zone-long",
            "reset_previous_regime": "TREND_UP",
            "reset_current_regime": "RANGE",
            "reset_new_tranche_id": "reset-tranche",
            "reset_evidence_refs": ["fresh-pit:qualified-reset"],
            "status": "RESET",
        }
    )
    return (
        previous_state,
        current_state,
        {"reentry_budget_state": previous_budget},
        {
            "reentry_budget_state": current_budget,
            "risk_tranches": [
                {
                    "tranche_id": "reset-tranche",
                    "supporting_cluster_ids": ["c-zone-long"],
                }
            ],
        },
    )


class V32ActionPlanContinuityTests(unittest.TestCase):
    def test_only_selected_eligible_positive_risk_instrument_churn_is_counted(
        self,
    ) -> None:
        plan = {
            "reentry_budget_state": {"status": "AVAILABLE"},
            "selected_candidate_id": "selected",
            "selected_candidate_reference_risk_budget": "0.2",
            "candidates": [
                {
                    "candidate_id": "selected",
                    "action_kind": "REENTER",
                    "feasibility": "ELIGIBLE",
                },
                {
                    "candidate_id": "unselected",
                    "action_kind": "REENTER",
                    "feasibility": "ELIGIBLE",
                },
            ],
        }
        self.assertEqual(
            Decimal("0.2"),
            _selected_counted_instrument_churn_reference_risk(plan),
        )
        for action_kind in ("OPEN_PROBE", "REVERSE"):
            with self.subTest(action_kind=action_kind, status="AVAILABLE"):
                counted = deepcopy(plan)
                counted["candidates"][0]["action_kind"] = action_kind
                self.assertEqual(
                    Decimal("0.2"),
                    _selected_counted_instrument_churn_reference_risk(counted),
                )
        for action_kind, status, feasibility, risk in (
            ("OPEN_PROBE", "INACTIVE", "ELIGIBLE", "0.2"),
            ("REVERSE", "INACTIVE", "ELIGIBLE", "0.2"),
            ("ADD", "AVAILABLE", "ELIGIBLE", "0.2"),
            ("REENTER", "AVAILABLE", "BLOCKED", "0.2"),
            ("REENTER", "AVAILABLE", "ELIGIBLE", "0"),
        ):
            with self.subTest(
                action_kind=action_kind,
                status=status,
                feasibility=feasibility,
                risk=risk,
            ):
                not_counted = deepcopy(plan)
                candidate = not_counted["candidates"][0]
                candidate["action_kind"] = action_kind
                candidate["feasibility"] = feasibility
                not_counted["reentry_budget_state"]["status"] = status
                not_counted["selected_candidate_reference_risk_budget"] = risk
                self.assertEqual(
                    Decimal("0"),
                    _selected_counted_instrument_churn_reference_risk(
                        not_counted
                    ),
                )

    def test_active_long_ledger_counts_short_open_probe_and_reverse_next_cycle(
        self,
    ) -> None:
        previous_state = _genesis_state()
        current_state = _next_state(
            previous_state,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
        )
        for action_kind in ("OPEN_PROBE", "REVERSE"):
            with self.subTest(action_kind=action_kind):
                previous_budget = action_fixture._available_reentry_budget()
                previous_budget.update(
                    {
                        "attempts_used": 0,
                        "cumulative_reference_risk": "0",
                        "consecutive_failures": 0,
                        "cooldown_until": None,
                    }
                )
                current_budget = deepcopy(previous_budget)
                current_budget.update(
                    {
                        "attempts_used": 1,
                        "cumulative_reference_risk": "0.2",
                    }
                )
                previous_plan = {
                    "reentry_budget_state": previous_budget,
                    "selected_candidate_id": "selected-short",
                    "selected_candidate_reference_risk_budget": "0.2",
                    "candidates": [
                        {
                            "candidate_id": "selected-short",
                            "action_kind": action_kind,
                            "direction": "SHORT",
                            "feasibility": "ELIGIBLE",
                        }
                    ],
                }
                current_plan = {"reentry_budget_state": current_budget}
                _verify_reentry_budget_continuity(
                    previous_state=previous_state,
                    current_state=current_state,
                    previous_plan=previous_plan,
                    current_plan=current_plan,
                )

                undercounted = deepcopy(current_plan)
                undercounted["reentry_budget_state"].update(
                    {
                        "attempts_used": 0,
                        "cumulative_reference_risk": "0",
                    }
                )
                with self.assertRaisesRegex(
                    V32ActionPlanContinuityError,
                    "REENTRY_COUNTER_TRANSITION_INVALID",
                ):
                    _verify_reentry_budget_continuity(
                        previous_state=previous_state,
                        current_state=current_state,
                        previous_plan=previous_plan,
                        current_plan=undercounted,
                    )

    def test_instrument_churn_reset_waits_for_absolute_window_and_cannot_rotate_identity(self) -> None:
        before_expiry = _reset_transition(
            current_as_of=START + timedelta(minutes=15)
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REENTRY_RESET_QUALIFICATION_INVALID",
        ):
            _verify_reentry_budget_continuity(
                previous_state=before_expiry[0],
                current_state=before_expiry[1],
                previous_plan=before_expiry[2],
                current_plan=before_expiry[3],
            )

        after_expiry = _reset_transition(
            current_as_of=START + timedelta(days=1)
        )
        _verify_reentry_budget_continuity(
            previous_state=after_expiry[0],
            current_state=after_expiry[1],
            previous_plan=after_expiry[2],
            current_plan=after_expiry[3],
        )

        for label, mutate, error in (
            (
                "budget-id",
                lambda budget: budget.update({"budget_id": "rotated-budget-id"}),
                "REENTRY_BUDGET_ID_MUTATED",
            ),
            (
                "failure-cluster",
                lambda budget: budget.update({"failure_cluster_id": "c-short"}),
                "REENTRY_RESET_QUALIFICATION_INVALID",
            ),
            (
                "regime",
                lambda budget: budget.update({"reset_current_regime": "TREND_UP"}),
                "REENTRY_RESET_QUALIFICATION_INVALID",
            ),
        ):
            with self.subTest(label=label):
                changed = deepcopy(after_expiry[3])
                mutate(changed["reentry_budget_state"])
                with self.assertRaisesRegex(V32ActionPlanContinuityError, error):
                    _verify_reentry_budget_continuity(
                        previous_state=after_expiry[0],
                        current_state=after_expiry[1],
                        previous_plan=after_expiry[2],
                        current_plan=changed,
                    )

    def test_failure_evidence_is_append_only_within_instrument_window(self) -> None:
        previous_state = _genesis_state()
        fresh_ref = "fresh-pit:new-reentry-failure"
        current_state = _next_state(
            previous_state,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
            initial_failure_ref=fresh_ref,
        )
        previous_budget = action_fixture._available_reentry_budget()
        previous_budget.update(
            {
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 1,
                "cooldown_until": None,
            }
        )
        current_budget = deepcopy(previous_budget)
        current_budget.update(
            {
                "attempts_used": 1,
                "cumulative_reference_risk": "0.4",
                "consecutive_failures": 2,
                "failure_evidence_refs": [fresh_ref],
            }
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REENTRY_COUNTER_TRANSITION_INVALID",
        ):
            _verify_reentry_budget_continuity(
                previous_state=previous_state,
                current_state=current_state,
                previous_plan={
                    "reentry_budget_state": previous_budget,
                    "selected_candidate_id": "reenter-long",
                    "selected_candidate_reference_risk_budget": "0.4",
                    "candidates": [
                        {
                            "candidate_id": "reenter-long",
                            "action_kind": "REENTER",
                            "feasibility": "ELIGIBLE",
                        }
                    ],
                },
                current_plan={"reentry_budget_state": current_budget},
            )

    def test_selected_reentry_is_counted_exactly_and_needs_fresh_failure_ref(self) -> None:
        previous_state = _genesis_state()
        fresh_ref = "fresh-pit:reentry-failure"
        current_state = _next_state(
            previous_state,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
            initial_failure_ref=fresh_ref,
        )
        previous_budget = action_fixture._available_reentry_budget()
        previous_budget.update(
            {
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 1,
                "cooldown_until": None,
            }
        )
        current_budget = deepcopy(previous_budget)
        current_budget.update(
            {
                "attempts_used": 1,
                "cumulative_reference_risk": "0.4",
                "consecutive_failures": 2,
                "failure_evidence_refs": ["source:h-long", fresh_ref],
            }
        )
        previous_plan = {
            "reentry_budget_state": previous_budget,
            "selected_candidate_id": "reenter-long",
            "selected_candidate_reference_risk_budget": "0.4",
            "candidates": [
                {
                    "candidate_id": "reenter-long",
                    "action_kind": "REENTER",
                    "feasibility": "ELIGIBLE",
                }
            ],
        }
        current_plan = {"reentry_budget_state": current_budget}
        _verify_reentry_budget_continuity(
            previous_state=previous_state,
            current_state=current_state,
            previous_plan=previous_plan,
            current_plan=current_plan,
        )

        not_counted = deepcopy(current_plan)
        not_counted["reentry_budget_state"].update(
            {
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 1,
            }
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REENTRY_COUNTER_TRANSITION_INVALID",
        ):
            _verify_reentry_budget_continuity(
                previous_state=previous_state,
                current_state=current_state,
                previous_plan=previous_plan,
                current_plan=not_counted,
            )

        no_fresh_failure = deepcopy(current_plan)
        no_fresh_failure["reentry_budget_state"]["failure_evidence_refs"] = [
            "source:h-long"
        ]
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REENTRY_COUNTER_TRANSITION_INVALID",
        ):
            _verify_reentry_budget_continuity(
                previous_state=previous_state,
                current_state=current_state,
                previous_plan=previous_plan,
                current_plan=no_fresh_failure,
            )

        not_churn = deepcopy(previous_plan)
        not_churn["candidates"][0]["action_kind"] = "ADD"
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REENTRY_COUNTER_TRANSITION_INVALID",
        ):
            _verify_reentry_budget_continuity(
                previous_state=previous_state,
                current_state=current_state,
                previous_plan=not_churn,
                current_plan=current_plan,
            )

    def test_initial_exit_creates_zero_attempt_available_reentry_budget(self) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        failure_ref = "fresh-pit:initial-stop-exit"
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
            initial_failure_ref=failure_ref,
        )
        budget = action_fixture._available_reentry_budget()
        budget.update(
            {
                "rolling_window_started_at": previous["as_of"],
                "rolling_window_expires_at": _time(
                    datetime.fromisoformat(previous["as_of"].replace("Z", "+00:00"))
                    + timedelta(hours=24)
                ),
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 1,
                "cooldown_until": None,
                "failure_evidence_refs": [failure_ref],
            }
        )
        current_plan = _build_plan(
            current,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=budget,
        )
        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=current_plan,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[DYNAMIC_STATE_DIGEST_FIELD],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[ACTION_PLAN_DIGEST_FIELD],
        )
        self.assertEqual(
            receipt[CONTINUITY_DIGEST_FIELD],
            verify_v32_action_plan_continuity_v1(
                receipt,
                current_dynamic_state=current,
                current_action_plan=current_plan,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[DYNAMIC_STATE_DIGEST_FIELD],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[ACTION_PLAN_DIGEST_FIELD],
            ),
        )
        self.assertEqual(0, current_plan["reentry_budget_state"]["attempts_used"])
        self.assertFalse(
            current_plan["reentry_budget_state"]["obligation_forces_entry"]
        )

    def test_initial_probe_arms_single_use_lock_and_rejects_second_free_probe(
        self,
    ) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
        )

        replayed_free_probe = _build_plan(
            current,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REFERENCE_TRANCHE_TRANSITION_INVALID",
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=current,
                current_action_plan=replayed_free_probe,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

        locked_plan = _build_plan(
            current,
            action_kind="HOLD",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=_initial_probe_used_budget(
                selected_at=previous["as_of"]
            ),
            reference_tranche_state=_resulting_reference_tranche_state(
                previous_plan
            ),
        )
        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=locked_plan,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )
        self.assertEqual(
            receipt[CONTINUITY_DIGEST_FIELD],
            verify_v32_action_plan_continuity_v1(
                receipt,
                current_dynamic_state=current,
                current_action_plan=locked_plan,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            ),
        )

    def test_wait_cannot_invent_an_initial_failure_budget(self) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        failure_ref = "fresh-pit:invented-exit"
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
            initial_failure_ref=failure_ref,
        )
        invented = action_fixture._available_reentry_budget()
        invented.update(
            {
                "rolling_window_started_at": previous["as_of"],
                "rolling_window_expires_at": _time(START + timedelta(days=1)),
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 1,
                "cooldown_until": None,
                "failure_evidence_refs": [failure_ref],
            }
        )
        current_plan = _build_plan(
            current,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=invented,
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "FAILURE_NOT_BOUND_TO_REFERENCE_TRANCHE",
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=current,
                current_action_plan=current_plan,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

    def test_supporting_evidence_cannot_be_relabelled_as_parent_failure(
        self,
    ) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        supporting_ref = "fresh-pit:bullish-confirmation"
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
            fresh_supporting_ref=supporting_ref,
        )
        budget = action_fixture._available_reentry_budget()
        budget.update(
            {
                "rolling_window_started_at": previous["as_of"],
                "rolling_window_expires_at": _time(START + timedelta(days=1)),
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 1,
                "cooldown_until": None,
                "failure_evidence_refs": [supporting_ref],
            }
        )
        current_plan = _build_plan(
            current,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=budget,
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "FAILURE_NOT_BOUND_TO_REFERENCE_TRANCHE",
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=current,
                current_action_plan=current_plan,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

    def test_expired_selected_tranche_is_retired_before_next_plan(self) -> None:
        previous = _genesis_state()
        previous_args = action_fixture._flat_args(dynamic_state=previous)
        next(
            row
            for row in previous_args["risk_tranches"]
            if row["candidate_id"] == "open-long"
        )["time_stop_at"] = _time(START + timedelta(minutes=4))
        previous_plan = build_v32_dynamic_action_plan_v1(**previous_args)
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
        )
        self.assertEqual(
            _none_reference_tranche_state(),
            _resulting_reference_tranche_state(
                previous_plan, next_as_of=current["as_of"]
            ),
        )
        current_plan = _build_plan(
            current,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=_initial_probe_used_budget(
                selected_at=previous["as_of"]
            ),
        )
        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=current_plan,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )
        self.assertEqual(
            receipt[CONTINUITY_DIGEST_FIELD],
            verify_v32_action_plan_continuity_v1(
                receipt,
                current_dynamic_state=current,
                current_action_plan=current_plan,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            ),
        )

    def test_initial_probe_lock_allows_counted_reverse_not_free_replay(
        self,
    ) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
        )
        locked_budget = _initial_probe_used_budget(
            selected_at=previous["as_of"]
        )
        reverse_plan = _build_plan(
            current,
            action_kind="REVERSE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=locked_budget,
            reference_tranche_state=_resulting_reference_tranche_state(
                previous_plan
            ),
        )
        compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=reverse_plan,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )
        next_state = _next_state(
            current,
            cycle_index=3,
            as_of=START + timedelta(minutes=10),
        )
        next_budget = deepcopy(reverse_plan["reentry_budget_state"])
        next_budget.update(
            {
                "direction": "SHORT",
                "attempts_used": 1,
                "cumulative_reference_risk": reverse_plan[
                    "selected_candidate_reference_risk_budget"
                ],
            }
        )
        _verify_reentry_budget_continuity(
            previous_state=current,
            current_state=next_state,
            previous_plan=reverse_plan,
            current_plan={"reentry_budget_state": next_budget},
        )

    def test_selected_add_requires_exact_prior_selected_funded_tranche(
        self,
    ) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
        )
        locked = _initial_probe_used_budget(selected_at=previous["as_of"])
        unproven = _build_plan(
            current,
            action_kind="ADD",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=locked,
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REFERENCE_TRANCHE_TRANSITION_INVALID",
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=current,
                current_action_plan=unproven,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

        proven = _build_plan(
            current,
            action_kind="ADD",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=locked,
            selected_parent_tranche_id="t-long",
            reference_tranche_state=_resulting_reference_tranche_state(
                previous_plan
            ),
        )
        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=proven,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )
        self.assertEqual(
            "t-long",
            next(
                row
                for row in proven["candidates"]
                if row["candidate_id"] == proven["selected_candidate_id"]
            )["parent_tranche_id"],
        )
        self.assertEqual(
            receipt[CONTINUITY_DIGEST_FIELD],
            verify_v32_action_plan_continuity_v1(
                receipt,
                current_dynamic_state=current,
                current_action_plan=proven,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_plan,
                durable_previous_action_plan_digest=previous_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            ),
        )

    def test_parent_lineage_rejects_direction_and_geometry_aliases(self) -> None:
        previous = _genesis_state()
        short_args = action_fixture._flat_args(dynamic_state=previous)
        short_args["selected_candidate_id"] = "open-short"
        short_args["alternative_candidate_rank"] = ["open-long", "wait"]
        previous_short = build_v32_dynamic_action_plan_v1(**short_args)
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
        )
        false_long_parent = _resulting_reference_tranche_state(previous_short)
        false_long_parent.update(
            {
                "direction": "LONG",
                "entry_reference": "100",
                "protective_stop_reference": "95",
                "supporting_hypothesis_ids": ["h-long"],
                "supporting_cluster_ids": ["c-long"],
            }
        )
        direction_alias = _build_plan(
            current,
            action_kind="ADD",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=_initial_probe_used_budget(
                selected_at=previous["as_of"], direction="SHORT"
            ),
            reference_tranche_state=false_long_parent,
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REFERENCE_TRANCHE_TRANSITION_INVALID",
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=current,
                current_action_plan=direction_alias,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_short,
                durable_previous_action_plan_digest=previous_short[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

        previous_long = _build_plan(
            previous,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        false_geometry = _resulting_reference_tranche_state(previous_long)
        false_geometry.update(
            {
                "entry_reference": "90",
                "protective_stop_reference": "85",
            }
        )
        geometry_alias = _build_plan(
            current,
            action_kind="ADD",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=_initial_probe_used_budget(
                selected_at=previous["as_of"]
            ),
            reference_tranche_state=false_geometry,
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError,
            "REFERENCE_TRANCHE_TRANSITION_INVALID",
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=current,
                current_action_plan=geometry_alias,
                durable_previous_dynamic_state=previous,
                durable_previous_dynamic_state_digest=previous[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=previous_long,
                durable_previous_action_plan_digest=previous_long[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

    def test_hold_carries_exact_parent_and_later_add_remains_legal(self) -> None:
        first = _genesis_state()
        first_plan = _build_plan(
            first,
            action_kind="OPEN_PROBE",
            inactivity_since=first["as_of"],
            consecutive_wait_cycles=0,
        )
        second = _next_state(
            first,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
        )
        locked = _initial_probe_used_budget(selected_at=first["as_of"])
        second_plan = _build_plan(
            second,
            action_kind="HOLD",
            inactivity_since=first["as_of"],
            consecutive_wait_cycles=0,
            model_adaptation_inactivity_since=second["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=locked,
            reference_tranche_state=_resulting_reference_tranche_state(
                first_plan
            ),
        )
        compose_v32_action_plan_continuity_v1(
            current_dynamic_state=second,
            current_action_plan=second_plan,
            durable_previous_dynamic_state=first,
            durable_previous_dynamic_state_digest=first[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=first_plan,
            durable_previous_action_plan_digest=first_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )

        third = _next_state(
            second,
            cycle_index=3,
            as_of=START + timedelta(minutes=10),
        )
        third_plan = _build_plan(
            third,
            action_kind="ADD",
            inactivity_since=first["as_of"],
            consecutive_wait_cycles=1,
            model_adaptation_inactivity_since=third["as_of"],
            consecutive_model_stale_cycles=0,
            reentry_budget_state=locked,
            reference_tranche_state=_resulting_reference_tranche_state(
                second_plan
            ),
        )
        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=third,
            current_action_plan=third_plan,
            durable_previous_dynamic_state=second,
            durable_previous_dynamic_state_digest=second[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=second_plan,
            durable_previous_action_plan_digest=second_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )
        self.assertEqual(
            second_plan["reference_tranche_state"],
            third_plan["reference_tranche_state"],
        )
        self.assertEqual(
            receipt[CONTINUITY_DIGEST_FIELD],
            verify_v32_action_plan_continuity_v1(
                receipt,
                current_dynamic_state=third,
                current_action_plan=third_plan,
                durable_previous_dynamic_state=second,
                durable_previous_dynamic_state_digest=second[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=second_plan,
                durable_previous_action_plan_digest=second_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            ),
        )

    def test_failure_must_bind_to_exact_carried_parent_path(self) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="OPEN_PROBE",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        for hypothesis_id, cluster_id in (
            ("h-short", "c-long"),
            ("h-zone-long", "c-zone-long"),
        ):
            with self.subTest(
                hypothesis_id=hypothesis_id, cluster_id=cluster_id
            ):
                failure_ref = f"fresh-pit:unbound:{hypothesis_id}"
                current = _next_state(
                    previous,
                    cycle_index=2,
                    as_of=START + timedelta(minutes=5),
                    initial_failure_ref=failure_ref,
                    initial_failure_hypothesis_id=hypothesis_id,
                )
                budget = action_fixture._available_reentry_budget()
                budget.update(
                    {
                        "failure_cluster_id": cluster_id,
                        "rolling_window_started_at": previous["as_of"],
                        "rolling_window_expires_at": _time(
                            START + timedelta(days=1)
                        ),
                        "attempts_used": 0,
                        "cumulative_reference_risk": "0",
                        "consecutive_failures": 1,
                        "cooldown_until": None,
                        "failure_evidence_refs": [failure_ref],
                    }
                )
                current_plan = _build_plan(
                    current,
                    action_kind="WAIT",
                    inactivity_since=previous["as_of"],
                    consecutive_wait_cycles=0,
                    model_adaptation_inactivity_since=current["as_of"],
                    consecutive_model_stale_cycles=0,
                    reentry_budget_state=budget,
                )
                with self.assertRaisesRegex(
                    V32ActionPlanContinuityError,
                    "FAILURE_NOT_BOUND_TO_REFERENCE_TRANCHE",
                ):
                    compose_v32_action_plan_continuity_v1(
                        current_dynamic_state=current,
                        current_action_plan=current_plan,
                        durable_previous_dynamic_state=previous,
                        durable_previous_dynamic_state_digest=previous[
                            DYNAMIC_STATE_DIGEST_FIELD
                        ],
                        durable_previous_action_plan=previous_plan,
                        durable_previous_action_plan_digest=previous_plan[
                            ACTION_PLAN_DIGEST_FIELD
                        ],
                    )

    def test_genesis_wait_accumulation_due_and_probe_reset(self) -> None:
        states, plans, receipts = _chain()
        self.assertEqual(0, receipts[0]["expected_consecutive_wait_cycles"])
        self.assertIsNone(receipts[0]["previous_action_plan_digest"])
        self.assertEqual(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0],
            [receipt["expected_consecutive_wait_cycles"] for receipt in receipts],
        )
        self.assertEqual(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 0, 0],
            [
                receipt["expected_consecutive_model_stale_cycles"]
                for receipt in receipts
            ],
        )
        self.assertEqual(
            [[], [], [], [], [], [], [], [], [], [], ["open-long"]],
            [
                receipt["previous_qualified_probe_candidate_ids"]
                for receipt in receipts
            ],
        )
        self.assertTrue(
            all(
                "previous_selected_action_kind" not in receipt
                for receipt in receipts
            )
        )
        self.assertTrue(receipts[8]["forced_review_due"])
        self.assertTrue(receipts[8]["testable_risk_plan_review_due"])
        self.assertTrue(receipts[8]["model_adaptation_review_due"])
        self.assertEqual(
            "COMPLETE_BASELINE_OPPORTUNITY_AND_SHADOW_REVIEW",
            receipts[8]["required_response_status"],
        )
        self.assertFalse(receipts[8]["forces_action"])
        due_watchdog = plans[8]["inactivity_opportunity_watchdog"]
        self.assertEqual(
            {
                "BASELINE_COMPARISON",
                "FULL_OPPORTUNITY_REVIEW",
                "SHADOW_PLAN_REFRESH",
            },
            set(due_watchdog["required_responses"]),
        )
        self.assertTrue(due_watchdog["baseline_comparison_refs"])
        self.assertTrue(due_watchdog["shadow_plan_candidate_ids"])
        self.assertFalse(due_watchdog["forces_action"])
        selected_due = next(
            row
            for row in plans[8]["candidates"]
            if row["candidate_id"] == plans[8]["selected_candidate_id"]
        )
        self.assertEqual("WAIT", selected_due["action_kind"])
        self.assertEqual(states[9]["as_of"], receipts[10]["expected_inactivity_since"])
        self.assertFalse(receipts[10]["forced_review_due"])
        self.assertEqual("NONE_RESEARCH_PLAN_ONLY", receipts[10]["real_exposure_claim"])
        self.assertEqual("0", plans[9]["current_executable_reference_risk_budget"])
        for state, plan, receipt in zip(states, plans, receipts):
            self.assertEqual(
                receipt[CONTINUITY_DIGEST_FIELD],
                verify_v32_action_plan_continuity_v1(
                    receipt,
                    current_dynamic_state=state,
                    current_action_plan=plan,
                    durable_previous_dynamic_state=(
                        None if state["cycle_index"] == 1 else states[state["cycle_index"] - 2]
                    ),
                    durable_previous_dynamic_state_digest=(
                        None
                        if state["cycle_index"] == 1
                        else states[state["cycle_index"] - 2][
                            DYNAMIC_STATE_DIGEST_FIELD
                        ]
                    ),
                    durable_previous_action_plan=(
                        None if state["cycle_index"] == 1 else plans[state["cycle_index"] - 2]
                    ),
                    durable_previous_action_plan_digest=(
                        None
                        if state["cycle_index"] == 1
                        else plans[state["cycle_index"] - 2][
                            ACTION_PLAN_DIGEST_FIELD
                        ]
                    ),
                ),
            )

    def test_non_probe_selected_action_cannot_reset_activity_watchdog(self) -> None:
        previous = _genesis_state()
        previous_args = action_fixture._long_intent_args()
        previous_args["dynamic_research_state"] = previous
        previous_args["plan_id"] = "plan-cycle-1-close"
        previous_args["selected_candidate_id"] = "close-long"
        previous_args["alternative_candidate_rank"] = [
            "add-long",
            "hold-long",
            "reduce-long",
            "reverse-short",
        ]
        previous_plan = build_v32_dynamic_action_plan_v1(**previous_args)
        current = _next_state(
            previous, cycle_index=2, as_of=START + timedelta(minutes=5)
        )
        current_plan = _build_plan(
            current,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=1,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
        )

        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=current_plan,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )

        self.assertEqual([], receipt["previous_qualified_probe_candidate_ids"])
        self.assertEqual(1, receipt["expected_consecutive_wait_cycles"])
        self.assertEqual(
            "NO_QUALIFIED_TESTABLE_RISK_PLAN",
            receipt["activity_basis"],
        )
        self.assertEqual("MATERIAL_PLAN_CHANGE", receipt["model_adaptation_basis"])

    def test_fresh_pit_backed_material_change_resets_without_probe_label(self) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
            material_change=True,
        )
        current_plan = _build_plan(
            current,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=1,
            model_adaptation_inactivity_since=current["as_of"],
            consecutive_model_stale_cycles=0,
        )

        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=current_plan,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )

        self.assertTrue(receipt["material_market_change_detected"])
        self.assertEqual(
            ["fresh-pit:material-long-shift"],
            receipt["material_change_evidence_refs"],
        )
        self.assertEqual("NO_QUALIFIED_TESTABLE_RISK_PLAN", receipt["activity_basis"])
        self.assertEqual(1, receipt["expected_consecutive_wait_cycles"])
        self.assertEqual(previous["as_of"], receipt["expected_inactivity_since"])
        self.assertEqual(0, receipt["expected_consecutive_model_stale_cycles"])
        self.assertEqual(
            current["as_of"], receipt["expected_model_adaptation_inactivity_since"]
        )

    def test_unrelated_fresh_ref_cannot_launder_a_material_change(self) -> None:
        previous = _genesis_state()
        previous_plan = _build_plan(
            previous,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=0,
        )
        current = _next_state(
            previous,
            cycle_index=2,
            as_of=START + timedelta(minutes=5),
            laundered_change=True,
        )
        current_plan = _build_plan(
            current,
            action_kind="WAIT",
            inactivity_since=previous["as_of"],
            consecutive_wait_cycles=1,
        )

        receipt = compose_v32_action_plan_continuity_v1(
            current_dynamic_state=current,
            current_action_plan=current_plan,
            durable_previous_dynamic_state=previous,
            durable_previous_dynamic_state_digest=previous[
                DYNAMIC_STATE_DIGEST_FIELD
            ],
            durable_previous_action_plan=previous_plan,
            durable_previous_action_plan_digest=previous_plan[
                ACTION_PLAN_DIGEST_FIELD
            ],
        )

        self.assertFalse(receipt["material_market_change_detected"])
        self.assertEqual([], receipt["material_change_evidence_refs"])
        self.assertEqual(1, receipt["expected_consecutive_wait_cycles"])

    def test_genesis_forbids_any_previous_state_or_plan(self) -> None:
        states, plans, _ = _chain()
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError, "GENESIS_PREVIOUS_FORBIDDEN"
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=states[0],
                current_action_plan=plans[0],
                durable_previous_dynamic_state=states[0],
                durable_previous_dynamic_state_digest=states[0][
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=plans[0],
                durable_previous_action_plan_digest=plans[0][
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

    def test_agent_cannot_reset_or_inflate_watchdog_with_self_consistent_plan(self) -> None:
        states, plans, _ = _chain()
        for since, count in (
            (states[2]["as_of"], 0),
            (states[0]["as_of"], 3),
        ):
            with self.subTest(since=since, count=count):
                self_consistent = _build_plan(
                    states[2],
                    action_kind="WAIT",
                    inactivity_since=since,
                    consecutive_wait_cycles=count,
                )
                with self.assertRaisesRegex(
                    V32ActionPlanContinuityError,
                    "WATCHDOG_RESET_OR_FORCE_INVALID",
                ):
                    compose_v32_action_plan_continuity_v1(
                        current_dynamic_state=states[2],
                        current_action_plan=self_consistent,
                        durable_previous_dynamic_state=states[1],
                        durable_previous_dynamic_state_digest=states[1][
                            DYNAMIC_STATE_DIGEST_FIELD
                        ],
                        durable_previous_action_plan=plans[1],
                        durable_previous_action_plan_digest=plans[1][
                            ACTION_PLAN_DIGEST_FIELD
                        ],
                    )

    def test_watchdog_threshold_drift_fails_closed(self) -> None:
        states, plans, _ = _chain()
        for cycles, seconds in ((5, 7200), (8, 3600)):
            with self.subTest(cycles=cycles, seconds=seconds):
                with self.assertRaisesRegex(
                    V32DynamicActionPlanError,
                    "WATCHDOG_PILOT_THRESHOLD_INVALID",
                ):
                    _build_plan(
                        states[1],
                        action_kind="WAIT",
                        inactivity_since=states[0]["as_of"],
                        consecutive_wait_cycles=1,
                        max_wait_cycles_before_review=cycles,
                        max_inactivity_seconds=seconds,
                    )

    def test_wrong_exact_prior_run_or_cycle_fails_closed(self) -> None:
        states, plans, _ = _chain()
        alternate = _genesis_state(long_tier="LOW")
        alternate_plan = _build_plan(
            alternate,
            action_kind="WAIT",
            inactivity_since=alternate["as_of"],
            consecutive_wait_cycles=0,
        )
        # Same run/cycle/time, but not the state digest explicitly named by
        # current_state.previous_state_digest.
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError, "PREVIOUS_IDENTITY_INVALID"
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=states[1],
                current_action_plan=plans[1],
                durable_previous_dynamic_state=alternate,
                durable_previous_dynamic_state_digest=states[0][
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=alternate_plan,
                durable_previous_action_plan_digest=plans[0][
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

    def test_alternate_valid_prior_plan_and_wrong_checkpoint_heads_fail(self) -> None:
        states, plans, _ = _chain()
        alternate_plan = _build_plan(
            states[0],
            action_kind="OPEN_PROBE",
            inactivity_since=states[0]["as_of"],
            consecutive_wait_cycles=0,
        )
        self_consistent_with_alternate = _build_plan(
            states[1],
            action_kind="WAIT",
            inactivity_since=states[0]["as_of"],
            consecutive_wait_cycles=0,
        )

        # A schema-valid alternate plan for the exact durable state cannot
        # impersonate the plan named by the checkpoint head.
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError, "PREVIOUS_IDENTITY_INVALID"
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=states[1],
                current_action_plan=self_consistent_with_alternate,
                durable_previous_dynamic_state=states[0],
                durable_previous_dynamic_state_digest=states[0][
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=alternate_plan,
                durable_previous_action_plan_digest=plans[0][
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

        # Conversely, a forged checkpoint-head digest cannot replace the
        # verified bytes of the actual durable plan or state.
        for state_head, plan_head in (
            (
                "0" * 64,
                plans[0][ACTION_PLAN_DIGEST_FIELD],
            ),
            (
                states[0][DYNAMIC_STATE_DIGEST_FIELD],
                alternate_plan[ACTION_PLAN_DIGEST_FIELD],
            ),
        ):
            with self.subTest(state_head=state_head, plan_head=plan_head):
                with self.assertRaisesRegex(
                    V32ActionPlanContinuityError, "PREVIOUS_IDENTITY_INVALID"
                ):
                    compose_v32_action_plan_continuity_v1(
                        current_dynamic_state=states[1],
                        current_action_plan=plans[1],
                        durable_previous_dynamic_state=states[0],
                        durable_previous_dynamic_state_digest=state_head,
                        durable_previous_action_plan=plans[0],
                        durable_previous_action_plan_digest=plan_head,
                    )

        for state_head, plan_head in (
            (None, plans[0][ACTION_PLAN_DIGEST_FIELD]),
            (states[0][DYNAMIC_STATE_DIGEST_FIELD], None),
        ):
            with self.subTest(missing_state_head=state_head is None):
                with self.assertRaisesRegex(
                    V32ActionPlanContinuityError, "PREVIOUS_REQUIRED"
                ):
                    compose_v32_action_plan_continuity_v1(
                        current_dynamic_state=states[1],
                        current_action_plan=plans[1],
                        durable_previous_dynamic_state=states[0],
                        durable_previous_dynamic_state_digest=state_head,
                        durable_previous_action_plan=plans[0],
                        durable_previous_action_plan_digest=plan_head,
                    )

        wrong_run = _genesis_state(run_id="other-v32-run")
        wrong_run_plan = _build_plan(
            wrong_run,
            action_kind="WAIT",
            inactivity_since=wrong_run["as_of"],
            consecutive_wait_cycles=0,
        )
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError, "PREVIOUS_IDENTITY_INVALID"
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=states[1],
                current_action_plan=plans[1],
                durable_previous_dynamic_state=wrong_run,
                durable_previous_dynamic_state_digest=wrong_run[
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=wrong_run_plan,
                durable_previous_action_plan_digest=wrong_run_plan[
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

        with self.assertRaisesRegex(
            V32ActionPlanContinuityError, "PREVIOUS_IDENTITY_INVALID"
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=states[2],
                current_action_plan=plans[2],
                durable_previous_dynamic_state=states[0],
                durable_previous_dynamic_state_digest=states[0][
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=plans[0],
                durable_previous_action_plan_digest=plans[0][
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

    def test_forced_action_and_self_digest_laundering_fail_closed(self) -> None:
        states, plans, receipts = _chain()
        forced = deepcopy(plans[4])
        forced["inactivity_opportunity_watchdog"]["forces_action"] = True
        forced = self_digest(forced, ACTION_PLAN_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError, "CURRENT_INVALID"
        ):
            compose_v32_action_plan_continuity_v1(
                current_dynamic_state=states[4],
                current_action_plan=forced,
                durable_previous_dynamic_state=states[3],
                durable_previous_dynamic_state_digest=states[3][
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=plans[3],
                durable_previous_action_plan_digest=plans[3][
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )

        laundered = deepcopy(receipts[4])
        laundered["required_response_status"] = "FORCE_MARKET_ENTRY"
        laundered["forces_action"] = True
        laundered = self_digest(laundered, CONTINUITY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32ActionPlanContinuityError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_action_plan_continuity_v1(
                laundered,
                current_dynamic_state=states[4],
                current_action_plan=plans[4],
                durable_previous_dynamic_state=states[3],
                durable_previous_dynamic_state_digest=states[3][
                    DYNAMIC_STATE_DIGEST_FIELD
                ],
                durable_previous_action_plan=plans[3],
                durable_previous_action_plan_digest=plans[3][
                    ACTION_PLAN_DIGEST_FIELD
                ],
            )


if __name__ == "__main__":
    unittest.main()
