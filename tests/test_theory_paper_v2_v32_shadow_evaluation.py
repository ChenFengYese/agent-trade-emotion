from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    OUTCOME_RECEIPT_DIGEST_FIELD,
    OUTCOME_RECEIPT_SCHEMA_ID,
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
    build_v32_outcome_schedule_set,
)
from trade_system.theory_paper_v2.domain.v32_shadow_evaluation import (
    MARKET_ANALYSIS_DIGEST_FIELD,
    MARKET_ANALYSIS_SCHEMA_ID,
    OPPORTUNITY_SET_DIGEST_FIELD,
    OPPORTUNITY_SET_SCHEMA_ID,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    POLICY_DESCRIPTORS,
    POLICY_DIGESTS,
    POLICY_VERSION,
    SELECTED_PLAN_DIGEST_FIELD,
    SELECTED_PLAN_SCHEMA_ID,
    SHADOW_ARM_IDS,
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    SHADOW_DECISION_BUNDLE_SCHEMA_ID,
    SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD,
    SHADOW_OUTCOME_EVALUATION_SCHEMA_ID,
    V32ShadowEvaluationError,
    build_v32_shadow_decision_bundle_v1,
    build_v32_shadow_outcome_evaluation_v1,
    verify_v32_shadow_decision_bundle_v1,
    verify_v32_shadow_outcome_evaluation_v1,
)


RUN_ID = "run:v32:shadow-evaluation"
DECISION_ID = "decision:0001"
AS_OF = "2026-08-07T00:00:00Z"


def _binding(
    *,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
    suffix: str,
) -> dict[str, str]:
    return {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": suffix * 64,
        "physical_sha256": suffix * 64,
    }


def _embedded_binding(
    document: dict,
    *,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
) -> dict[str, str]:
    return {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }


def _common_bindings() -> dict[str, dict[str, str]]:
    return {
        "pit_registry_binding": _binding(
            relative_ref="cycle-0001/pit-registry.json",
            schema_id=PIT_REGISTRY_SCHEMA_ID,
            digest_field=PIT_REGISTRY_DIGEST_FIELD,
            suffix="1",
        ),
        "market_analysis_binding": _binding(
            relative_ref="cycle-0001/public-market-analysis.json",
            schema_id=MARKET_ANALYSIS_SCHEMA_ID,
            digest_field=MARKET_ANALYSIS_DIGEST_FIELD,
            suffix="2",
        ),
        "opportunity_set_binding": _binding(
            relative_ref="cycle-0001/action-evaluation.json",
            schema_id=OPPORTUNITY_SET_SCHEMA_ID,
            digest_field=OPPORTUNITY_SET_DIGEST_FIELD,
            suffix="3",
        ),
        "selected_plan_binding": _binding(
            relative_ref="cycle-0001/dynamic-action-plan.json",
            schema_id=SELECTED_PLAN_SCHEMA_ID,
            digest_field=SELECTED_PLAN_DIGEST_FIELD,
            suffix="4",
        ),
    }


def _arms(bindings: dict[str, dict[str, str]]) -> list[dict]:
    selected_plan_digest = bindings["selected_plan_binding"]["semantic_digest"]
    previous_close_digest = "a" * 64
    latest_close_digest = "b" * 64
    definitions = {
        "V32_SELECTED_PLAN": (
            "COMPUTED_FROM_SELECTED_PLAN",
            {
                "selected_candidate_id": "candidate:selected",
                "action_label": "OPEN_PROBE",
                "direction_label": "LONG",
            },
            [selected_plan_digest],
            "OPEN_PROBE",
            "LONG",
            "HIGH",
            ["c" * 64],
        ),
        "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE": (
            "UNKNOWN_NOT_COMPUTED", {}, [], "UNKNOWN", "UNKNOWN", "UNKNOWN", []
        ),
        "WAIT_ONLY": (
            "COMPUTED_CONSTANT", {}, [], "WAIT", "NONE", "UNKNOWN", []
        ),
        "SIMPLE_15M_TREND": (
            "COMPUTED_FROM_TWO_CLOSED_15M_BARS",
            {
                "previous_close": "65000",
                "latest_close": "64000",
                "previous_close_datum_digest": previous_close_digest,
                "latest_close_datum_digest": latest_close_digest,
            },
            sorted([previous_close_digest, latest_close_digest]),
            "HOLD",
            "SHORT",
            "UNKNOWN",
            sorted([previous_close_digest, latest_close_digest]),
        ),
        "NO_RSI_REFERENCE": (
            "UNKNOWN_NOT_COMPUTED", {}, [], "UNKNOWN", "UNKNOWN", "UNKNOWN", []
        ),
        "ALWAYS_LONG_PUBLIC_MARK_REFERENCE": (
            "COMPUTED_CONSTANT", {}, [], "HOLD", "LONG", "UNKNOWN", []
        ),
    }
    result = []
    for arm_id in SHADOW_ARM_IDS:
        (
            status,
            inputs,
            input_refs,
            action,
            direction,
            band,
            evidence_refs,
        ) = definitions[arm_id]
        derivation_receipt_digest = canonical_digest(
            {
                "arm_id": arm_id,
                "policy_digest": POLICY_DIGESTS[arm_id],
                "derivation_status": status,
                "derivation_inputs": inputs,
                "derivation_input_refs": input_refs,
                "action_label": action,
                "direction_label": direction,
            }
        )
        result.append(
            {
                "arm_id": arm_id,
                "run_id": RUN_ID,
                "cycle_index": 1,
                "as_of": AS_OF,
                **deepcopy(bindings),
                "policy_id": POLICY_DESCRIPTORS[arm_id]["policy_id"],
                "policy_version": POLICY_VERSION,
                "policy_digest": POLICY_DIGESTS[arm_id],
                "derivation_status": status,
                "derivation_inputs": inputs,
                "derivation_input_refs": input_refs,
                "derivation_receipt_digest": derivation_receipt_digest,
                "action_label": action,
                "direction_label": direction,
                "shadow_arm_ordinal_band": band,
                "ordinal_band_semantics": (
                    "SHADOW_ARM_COMPARISON_ONLY_NOT_SUBJECTIVE_PLAUSIBILITY_TIER"
                ),
                "ordinal_rationale": f"Frozen ordinal rationale for {arm_id}.",
                "evidence_refs": evidence_refs,
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
        )
    return result


def _decision_bundle() -> dict:
    bindings = _common_bindings()
    return build_v32_shadow_decision_bundle_v1(
        bundle_id="shadow-bundle:0001",
        run_id=RUN_ID,
        decision_id=DECISION_ID,
        cycle_index=1,
        as_of=AS_OF,
        created_at=AS_OF,
        decision_mark_snapshot={
            "value": "64000",
            "datum_digest": "d" * 64,
            "observed_at": AS_OF,
            "available_at": AS_OF,
        },
        arms=_arms(bindings),
        **bindings,
    )


def _schedule_set(bundle: dict) -> dict:
    return build_v32_outcome_schedule_set(
        run_id=RUN_ID,
        decision_id=DECISION_ID,
        cycle_index=1,
        decision_time=AS_OF,
        scheduled_at="2026-08-07T00:00:01Z",
        sealed_decision_digest=bundle["selected_plan_binding"]["semantic_digest"],
        evaluation_contract_digest="e" * 64,
    )


def _receipt(schedule_set: dict, *, coverage_loss: bool = False) -> dict:
    schedule = schedule_set["schedules"][0]
    return self_digest(
        {
            "schema_id": OUTCOME_RECEIPT_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "schedule_id": schedule["schedule_id"],
            "schedule_digest": schedule["schedule_digest"],
            "schedule_set_digest": schedule_set[SCHEDULE_SET_DIGEST_FIELD],
            "decision_id": DECISION_ID,
            "cycle_index": 1,
            "horizon": "15M",
            "outcome_not_before": schedule["outcome_not_before"],
            "batch_intent_digest": "5" * 64,
            "observation_tick_digest": "6" * 64,
            "raw_evidence_digest": "7" * 64,
            "resolved_at": "2026-08-07T00:15:02Z",
            "resolution_status": (
                "UNKNOWN_COVERAGE_LOSS"
                if coverage_loss
                else "OBSERVED_PUBLIC_MARK"
            ),
            "coverage_loss_reason": "PUBLIC_TIMEOUT" if coverage_loss else None,
            "observable_ref": schedule["observable_ref"],
            "value": None if coverage_loss else "65000",
            "provider_as_of": None if coverage_loss else "2026-08-07T00:15:00Z",
            "available_at": "2026-08-07T00:15:01Z",
            "quality": "UNKNOWN" if coverage_loss else "HIGH",
            "missingness": "UNKNOWN" if coverage_loss else "OBSERVED",
            "terminal": True,
            "attempt_count": 1,
            "retry_allowed": False,
            "shared_tick_request": True,
            "observation_scope": "PUBLIC_MARKET_PATH_ONLY_NO_EXECUTION_STATE",
            "stop_trigger_semantics": "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL",
            "trigger_is_fill": False,
            "fill_claim": False,
            "position_claim": False,
            "pnl_claim": False,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        OUTCOME_RECEIPT_DIGEST_FIELD,
    )


def _evaluation(
    bundle: dict,
    schedule_set: dict,
    receipt: dict,
    *,
    evaluated_at: str = "2026-08-07T00:15:03Z",
) -> dict:
    return build_v32_shadow_outcome_evaluation_v1(
        evaluation_id="shadow-evaluation:0001:15M",
        shadow_decision_bundle=bundle,
        shadow_decision_bundle_binding=_embedded_binding(
            bundle,
            relative_ref="cycle-0001/shadow-decision-bundle.json",
            schema_id=SHADOW_DECISION_BUNDLE_SCHEMA_ID,
            digest_field=SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
        ),
        outcome_schedule_set=schedule_set,
        outcome_schedule_set_binding=_embedded_binding(
            schedule_set,
            relative_ref="cycle-0001/outcome-schedule-set.json",
            schema_id=SCHEDULE_SET_SCHEMA_ID,
            digest_field=SCHEDULE_SET_DIGEST_FIELD,
        ),
        outcome_receipt=receipt,
        outcome_receipt_binding=_embedded_binding(
            receipt,
            relative_ref="cycle-0001/outcomes/15m-receipt.json",
            schema_id=OUTCOME_RECEIPT_SCHEMA_ID,
            digest_field=OUTCOME_RECEIPT_DIGEST_FIELD,
        ),
        horizon="15M",
        evaluated_at=evaluated_at,
    )


class V32ShadowEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = _decision_bundle()
        self.schedule_set = _schedule_set(self.bundle)
        self.receipt = _receipt(self.schedule_set)

    def test_exact_six_arm_bundle_and_outcome_round_trip(self) -> None:
        self.assertEqual(list(SHADOW_ARM_IDS), self.bundle["arm_ids"])
        self.assertEqual(
            list(SHADOW_ARM_IDS), [row["arm_id"] for row in self.bundle["arms"]]
        )
        self.assertEqual(
            self.bundle[SHADOW_DECISION_BUNDLE_DIGEST_FIELD],
            verify_v32_shadow_decision_bundle_v1(self.bundle),
        )
        evaluation = _evaluation(self.bundle, self.schedule_set, self.receipt)
        self.assertEqual(list(SHADOW_ARM_IDS), evaluation["arm_ids"])
        self.assertFalse(evaluation["numeric_market_values_copied_into_arm_results"])
        self.assertEqual(
            evaluation[SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD],
            verify_v32_shadow_outcome_evaluation_v1(
                evaluation,
                shadow_decision_bundle=self.bundle,
                outcome_schedule_set=self.schedule_set,
                outcome_receipt=self.receipt,
            ),
        )

    def test_missing_arm_fails_closed(self) -> None:
        bindings = _common_bindings()
        with self.assertRaisesRegex(V32ShadowEvaluationError, "ARM_SET_INVALID"):
            build_v32_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:missing",
                run_id=RUN_ID,
                decision_id=DECISION_ID,
                cycle_index=1,
                as_of=AS_OF,
                created_at=AS_OF,
                decision_mark_snapshot={
                    "value": "64000",
                    "datum_digest": "d" * 64,
                    "observed_at": AS_OF,
                    "available_at": AS_OF,
                },
                arms=_arms(bindings)[:-1],
                **bindings,
            )

    def test_cross_pit_arm_fails_closed(self) -> None:
        bindings = _common_bindings()
        arms = _arms(bindings)
        arms[3]["pit_registry_binding"] = _binding(
            relative_ref="cycle-0001/other-pit-registry.json",
            schema_id=PIT_REGISTRY_SCHEMA_ID,
            digest_field=PIT_REGISTRY_DIGEST_FIELD,
            suffix="9",
        )
        with self.assertRaisesRegex(V32ShadowEvaluationError, "ARM_INVALID"):
            build_v32_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:cross-pit",
                run_id=RUN_ID,
                decision_id=DECISION_ID,
                cycle_index=1,
                as_of=AS_OF,
                created_at=AS_OF,
                decision_mark_snapshot={
                    "value": "64000",
                    "datum_digest": "d" * 64,
                    "observed_at": AS_OF,
                    "available_at": AS_OF,
                },
                arms=arms,
                **bindings,
            )

    def test_tampered_bundle_and_evaluation_fail_verification(self) -> None:
        tampered_bundle = deepcopy(self.bundle)
        tampered_bundle["arms"][0]["ordinal_rationale"] = "Changed after seal."
        with self.assertRaises(V32ShadowEvaluationError):
            verify_v32_shadow_decision_bundle_v1(tampered_bundle)

        evaluation = _evaluation(self.bundle, self.schedule_set, self.receipt)
        tampered_evaluation = deepcopy(evaluation)
        tampered_evaluation["arm_results"][0]["mae_band"] = "HIGH"
        with self.assertRaises(V32ShadowEvaluationError):
            verify_v32_shadow_outcome_evaluation_v1(
                tampered_evaluation,
                shadow_decision_bundle=self.bundle,
                outcome_schedule_set=self.schedule_set,
                outcome_receipt=self.receipt,
            )

    def test_outcome_before_horizon_fails_closed(self) -> None:
        with self.assertRaisesRegex(V32ShadowEvaluationError, "OUTCOME_NOT_DUE"):
            _evaluation(
                self.bundle,
                self.schedule_set,
                self.receipt,
                evaluated_at="2026-08-07T00:14:59Z",
            )

    def test_self_signed_fill_or_pnl_claim_fails_closed(self) -> None:
        forged = deepcopy(self.receipt)
        forged["fill_claim"] = True
        forged["pnl_claim"] = True
        forged = self_digest(forged, OUTCOME_RECEIPT_DIGEST_FIELD)
        with self.assertRaisesRegex(V32ShadowEvaluationError, "RECEIPT_INVALID"):
            _evaluation(self.bundle, self.schedule_set, forged)

    def test_injected_fill_pnl_ev_or_probability_surface_is_rejected(self) -> None:
        bindings = _common_bindings()
        arms = _arms(bindings)
        arms[0]["fill_price"] = "65000"
        arms[0]["pnl"] = "10"
        arms[0]["expected_value"] = "1"
        arms[0]["probability_pct"] = "80"
        with self.assertRaisesRegex(V32ShadowEvaluationError, "ARM_INVALID"):
            build_v32_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:forged-claims",
                run_id=RUN_ID,
                decision_id=DECISION_ID,
                cycle_index=1,
                as_of=AS_OF,
                created_at=AS_OF,
                decision_mark_snapshot={
                    "value": "64000",
                    "datum_digest": "d" * 64,
                    "observed_at": AS_OF,
                    "available_at": AS_OF,
                },
                arms=arms,
                **bindings,
            )

    def test_caller_cannot_replace_unknown_or_trend_policy_with_arbitrary_action(
        self,
    ) -> None:
        bindings = _common_bindings()
        arms = _arms(bindings)
        unknown = next(
            row
            for row in arms
            if row["arm_id"] == "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE"
        )
        unknown["action_label"] = "REVERSE"
        unknown["direction_label"] = "SHORT"
        with self.assertRaisesRegex(
            V32ShadowEvaluationError, "POLICY_OUTPUT_MISMATCH"
        ):
            build_v32_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:forged-v31",
                run_id=RUN_ID,
                decision_id=DECISION_ID,
                cycle_index=1,
                as_of=AS_OF,
                created_at=AS_OF,
                decision_mark_snapshot={
                    "value": "64000",
                    "datum_digest": "d" * 64,
                    "observed_at": AS_OF,
                    "available_at": AS_OF,
                },
                arms=arms,
                **bindings,
            )

        arms = _arms(bindings)
        trend = next(row for row in arms if row["arm_id"] == "SIMPLE_15M_TREND")
        trend["action_label"] = "WAIT"
        trend["direction_label"] = "NONE"
        with self.assertRaisesRegex(
            V32ShadowEvaluationError, "POLICY_OUTPUT_MISMATCH"
        ):
            build_v32_shadow_decision_bundle_v1(
                bundle_id="shadow-bundle:forged-trend",
                run_id=RUN_ID,
                decision_id=DECISION_ID,
                cycle_index=1,
                as_of=AS_OF,
                created_at=AS_OF,
                decision_mark_snapshot={
                    "value": "64000",
                    "datum_digest": "d" * 64,
                    "observed_at": AS_OF,
                    "available_at": AS_OF,
                },
                arms=arms,
                **bindings,
            )

    def test_terminal_mark_derives_direction_but_never_invents_path_or_excursion(
        self,
    ) -> None:
        evaluation = _evaluation(self.bundle, self.schedule_set, self.receipt)
        by_id = {row["arm_id"]: row for row in evaluation["arm_results"]}
        self.assertEqual("ALIGNED", by_id["V32_SELECTED_PLAN"]["directional_alignment"])
        self.assertEqual(
            "OPPOSED", by_id["SIMPLE_15M_TREND"]["directional_alignment"]
        )
        self.assertEqual(
            "ALIGNED",
            by_id["ALWAYS_LONG_PUBLIC_MARK_REFERENCE"]["directional_alignment"],
        )
        self.assertEqual(
            "UNKNOWN",
            by_id["V31_CONSERVATIVE_WAIT_BIASED_REFERENCE"][
                "directional_alignment"
            ],
        )
        for row in evaluation["arm_results"]:
            self.assertEqual("UNKNOWN", row["path_alignment"])
            self.assertEqual("UNKNOWN", row["mfe_band"])
            self.assertEqual("UNKNOWN", row["mae_band"])
            self.assertEqual("UNKNOWN", row["opportunity_miss_band"])

    def test_coverage_loss_requires_every_outcome_field_to_be_unknown(self) -> None:
        missing_receipt = _receipt(self.schedule_set, coverage_loss=True)
        evaluation = _evaluation(self.bundle, self.schedule_set, missing_receipt)
        self.assertEqual("UNKNOWN_COVERAGE_LOSS", evaluation["outcome_resolution_status"])
        self.assertTrue(
            all(
                row["comparison_status"] == "UNKNOWN_COVERAGE_LOSS"
                and len(row["unknown_fields"]) == 5
                for row in evaluation["arm_results"]
            )
        )


if __name__ == "__main__":
    unittest.main()
