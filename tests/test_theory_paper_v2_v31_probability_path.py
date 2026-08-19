from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

from trade_system.theory_paper_v2.domain.probability_cloud import (
    CloudComponent,
    CloudUpdateEvidence,
    EvidenceEffect,
    FrozenPredictionOutcome,
    FrozenPredictiveForecast,
    PlausibilityLevel,
    PredictiveValidationReceipt,
    ProbabilityCloud,
    ProbabilityCloudError,
    ProbabilityMode,
    ProperScoringRule,
    seal_probability_cloud_update,
    seal_probability_cloud_repartition,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_digest
from trade_system.theory_paper_v2.domain.scenario_path import (
    ActionImplication,
    EpistemicStage,
    EpistemicTransition,
    ExpectedObservation,
    ImplicationEffect,
    PathPredicate,
    PathFactSnapshot,
    PredicateOperator,
    PredicateQuality,
    PredicateTiming,
    PredicateTruth,
    ScenarioPathError,
    ScenarioPathRule,
    ScenarioPathSet,
    evaluate_path_conditions,
)
from trade_system.theory_paper_v2.domain.behavior_planning import ActionType


DECISION_AT = "2026-08-06T10:00:00Z"


def subjective_cloud(*, level: PlausibilityLevel = PlausibilityLevel.HIGH) -> ProbabilityCloud:
    return ProbabilityCloud(
        cloud_id="cloud-1",
        mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
        decision_at=DECISION_AT,
        available_at="2026-08-06T09:59:00Z",
        horizon="4H",
        components=(
            CloudComponent(
                "liquidity-recovery",
                plausibility=level,
                lower=Decimal("0.45"),
                upper=Decimal("0.75"),
                evidence_refs=("fact-1",),
                opposition_refs=("counter-fact-1",),
                dependency_groups=("book-lineage",),
                model_uncertainty=("single-venue",),
                sensitivity_notes=("falls to medium without independent depth evidence",),
            ),
            CloudComponent(
                "OTHER",
                plausibility=PlausibilityLevel.MEDIUM,
                lower=Decimal("0.1"),
                upper=Decimal("0.6"),
                evidence_refs=("residual-1",),
            ),
            CloudComponent("UNKNOWN", plausibility=PlausibilityLevel.UNKNOWN),
        ),
        unknown_refs=("liquidations-unavailable",),
        limitations=("not-calibrated",),
    )


def event_contract() -> dict[str, object]:
    return {
        "schema_id": "theory_paper_v2_v31_predictive_event_contract",
        "schema_version": "1.0.0",
        "event_contract_ref": "mutually-exclusive-event",
        "horizon": "4H",
        "outcome_ids": ["OTHER", "UP"],
        "mutually_exclusive": True,
        "exhaustive": True,
        "resolution_rule": "UP if the frozen close is above the reference; OTHER otherwise.",
    }


def model_contract(*, probability_up: str = "0.5") -> dict[str, object]:
    contract = event_contract()
    return {
        "schema_id": "theory_paper_v2_v31_frozen_predictive_model",
        "schema_version": "1.0.0",
        "model_ref": "model-v1",
        "event_contract_ref": "mutually-exclusive-event",
        "event_contract_digest": canonical_digest(contract),
        "horizon": "4H",
        "outcome_ids": ["OTHER", "UP"],
        "frozen_at": "2026-07-31T00:00:00Z",
        "training_data_cutoff": "2026-07-30T00:00:00Z",
        "model_kind": "CONSTANT_CATEGORICAL_DISTRIBUTION_V1",
        "frozen_probabilities": [
            {
                "outcome_id": "OTHER",
                "probability": str(Decimal("1") - Decimal(probability_up)),
            },
            {"outcome_id": "UP", "probability": probability_up},
        ],
        "implementation_digest": canonical_digest(
            {
                "algorithm": "CONSTANT_CATEGORICAL_DISTRIBUTION",
                "version": "1.0.0",
                "input_usage": "IGNORED_BY_DESIGN",
            }
        ),
    }


def frozen_sample(
    split: str,
    *,
    start_at: datetime,
    probability_up: str = "0.5",
    outcome_override: str | None = None,
) -> tuple[FrozenPredictionOutcome, ...]:
    rows = []
    for index in range(100):
        predicted = start_at + timedelta(minutes=index * 10)
        outcome = predicted + timedelta(minutes=5)
        observed = outcome_override or ("UP" if index % 2 == 0 else "OTHER")
        rows.append(
            FrozenPredictionOutcome(
                forecast=FrozenPredictiveForecast(
                    forecast_id=f"{split.lower()}-{index}",
                    prediction_at=predicted.isoformat().replace("+00:00", "Z"),
                    model_input_digest=canonical_digest(
                        {"split": split, "observation_index": index}
                    ),
                    probabilities=(
                        ("UP", probability_up),
                        ("OTHER", str(Decimal("1") - Decimal(probability_up))),
                    ),
                ),
                observed_outcome=observed,
                outcome_available_at=outcome.isoformat().replace("+00:00", "Z"),
            )
        )
    return tuple(rows)


def validation_receipt() -> PredictiveValidationReceipt:
    return PredictiveValidationReceipt(
        receipt_id="validation-1",
        event_contract_ref="mutually-exclusive-event",
        event_contract=event_contract(),
        horizon="4H",
        model_ref="model-v1",
        model_contract=model_contract(),
        development_sample=frozen_sample(
            "DEVELOPMENT", start_at=datetime(2026, 8, 1, tzinfo=UTC)
        ),
        calibration_sample=frozen_sample(
            "CALIBRATION", start_at=datetime(2026, 8, 2, tzinfo=UTC)
        ),
        oos_sample=frozen_sample(
            "OOS", start_at=datetime(2026, 8, 3, tzinfo=UTC)
        ),
        deployment_forecast=FrozenPredictiveForecast(
            forecast_id="deployment-1",
            prediction_at="2026-08-06T09:59:00Z",
            model_input_digest=canonical_digest(
                {"deployment": "2026-08-06T09:59:00Z"}
            ),
            probabilities=(("UP", "0.5"), ("OTHER", "0.5")),
        ),
        scoring_rule=ProperScoringRule.BRIER,
        available_at="2026-08-04T00:00:00Z",
        invalidation_conditions=("fixed drift limit is exceeded",),
        limitations=("local fixture does not prove external source provenance",),
    )


def predicate(
    predicate_id: str,
    fact_ref: str,
    expected: object,
    *,
    operator: PredicateOperator = PredicateOperator.EQ,
    timing: PredicateTiming = PredicateTiming.DECISION_INPUT,
    available_at: str = "2026-08-06T09:59:00Z",
) -> PathPredicate:
    return PathPredicate(
        predicate_id=predicate_id,
        fact_ref=fact_ref,
        fact_digest=("a" * 64 if timing is PredicateTiming.DECISION_INPUT else None),
        timing=timing,
        operator=operator,
        expected=expected,
        available_at=available_at,
        minimum_quality=PredicateQuality.MEDIUM,
        minimum_coverage="0.8",
        allowed_conflict_states=("NONE",),
    )


def fact(fact_ref: str, value: object, *, available_at: str = "2026-08-06T09:59:00Z") -> PathFactSnapshot:
    return PathFactSnapshot(
        fact_ref=fact_ref,
        fact_digest="a" * 64,
        value=value,
        available_at=available_at,
        missingness="OBSERVED",
        quality=PredicateQuality.HIGH,
        coverage="1",
        conflict_state="NONE",
    )


def valid_path(path_id: str = "path-a") -> ScenarioPathRule:
    return ScenarioPathRule(
        path_id=path_id,
        decision_at=DECISION_AT,
        triggers=(predicate(f"{path_id}-t", "spread_state", "WIDE"),),
        guards=(predicate(f"{path_id}-g", "book_quality", "MEDIUM"),),
        unless=(predicate(f"{path_id}-u", "venue_outage", True),),
        transition=EpistemicTransition(
            from_stage=EpistemicStage.ASSOCIATION,
            to_stage=EpistemicStage.INFERENCE,
            target_ref=f"{path_id}-inference",
            update_type="ADD",
        ),
        mechanism="Funding constraints may amplify a loss of displayed depth.",
        mechanism_hypothesis_refs=("funding-liquidity-loop",),
        expectations=(
            ExpectedObservation(
                observation_id=f"{path_id}-e",
                hypothesis_id="funding-liquidity-loop",
                expectation_revision_digest="9" * 64,
                observable_ref="depth_recovery",
                horizon_at="2026-08-06T14:00:00Z",
                direction_or_state="WEAK",
                confirms_when="depth stays below pre-shock band",
                contradicts_when="depth and spread fully recover",
            ),
        ),
        falsifiers=(
            predicate(
                f"{path_id}-f",
                "depth_recovered",
                True,
                timing=PredicateTiming.FUTURE_MONITOR,
                available_at="2026-08-06T11:00:00Z",
            ),
        ),
        else_path_refs=("delayed-recovery",),
        preserves_other_unknown=True,
        action_implications=(
            ActionImplication(
                action=ActionType.WAIT,
                effect=ImplicationEffect.FAVORS,
                rationale="The inference is not yet a calibrated forecast.",
                risk_refs=("risk-liquidity",),
                opportunity_cost="May miss an early recovery move.",
            ),
        ),
        expires_at="2026-08-07T10:00:00Z",
        next_review_at="2026-08-06T11:00:00Z",
        next_observation="Collect a second independent depth window.",
        regime_refs=("stress-regime-candidate",),
        probability_cloud_refs=("cloud-1",),
    )


class ProbabilityCloudTests(unittest.TestCase):
    def test_subjective_cloud_is_not_normalized_and_forbids_ev(self) -> None:
        cloud = subjective_cloud()
        document = cloud.to_document()
        self.assertEqual("SUBJECTIVE_PLAUSIBILITY", document["mode"])
        self.assertFalse(document["expected_value_allowed"])
        with self.assertRaisesRegex(
            ProbabilityCloudError,
            "EXPECTED_VALUE_REQUIRES_CALIBRATED_DISTRIBUTION",
        ):
            cloud.assert_expected_value_allowed()

    def test_subjective_point_probability_and_future_information_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            ProbabilityCloudError, "UNCALIBRATED_POINT_PROBABILITY_FORBIDDEN"
        ):
            ProbabilityCloud(
                cloud_id="bad",
                mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
                decision_at=DECISION_AT,
                available_at=DECISION_AT,
                horizon="1H",
                components=(
                    CloudComponent(
                        "h", plausibility=PlausibilityLevel.HIGH, probability="0.7"
                    ),
                    CloudComponent("OTHER", plausibility=PlausibilityLevel.LOW),
                    CloudComponent("UNKNOWN", plausibility=PlausibilityLevel.UNKNOWN),
                ),
            )
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CLOUD_FUTURE_INFORMATION_FORBIDDEN"
        ):
            ProbabilityCloud(
                cloud_id="future",
                mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
                decision_at=DECISION_AT,
                available_at="2026-08-06T10:00:01Z",
                horizon="1H",
                components=subjective_cloud().components,
            )

    def test_model_and_market_objects_require_distinct_contracts(self) -> None:
        components = (
            CloudComponent("h", lower="0.2", upper="0.5"),
            CloudComponent("OTHER", lower="0.1", upper="0.7"),
            CloudComponent("UNKNOWN"),
        )
        model_cloud = ProbabilityCloud(
            cloud_id="model",
            mode=ProbabilityMode.EMPIRICAL_OR_MODEL_CONDITIONAL,
            decision_at=DECISION_AT,
            available_at=DECISION_AT,
            horizon="1D",
            components=components,
            event_contract_ref="event-contract-v1",
            event_contract_digest="a" * 64,
            sample_contract_refs=("walk-forward-1",),
            model_refs=("model-1", "model-2"),
        )
        self.assertFalse(model_cloud.allows_expected_value)
        with self.assertRaisesRegex(
            ProbabilityCloudError, "MARKET_IMPLIED_BOUNDARY_REQUIRED"
        ):
            ProbabilityCloud(
                cloud_id="market",
                mode=ProbabilityMode.MARKET_IMPLIED_BELIEF,
                decision_at=DECISION_AT,
                available_at=DECISION_AT,
                horizon="1D",
                components=components,
                event_contract_ref="option-expiry-event",
                event_contract_digest="b" * 64,
                market_contract_refs=("option-chain",),
            )

    def test_only_oos_calibrated_complete_partition_allows_ev(self) -> None:
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CALIBRATED_DISTRIBUTION_GATE_FAILED"
        ):
            ProbabilityCloud(
                cloud_id="not-calibrated",
                mode=ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION,
                decision_at=DECISION_AT,
                available_at=DECISION_AT,
                horizon="4H",
                event_contract_ref="mutually-exclusive-event",
                event_contract_digest=canonical_digest(event_contract()),
                components=(
                    CloudComponent("UP", probability="0.5"),
                    CloudComponent("OTHER", probability="0.5"),
                ),
                mutually_exclusive=True,
                exhaustive=True,
            )
        receipt = validation_receipt()
        cloud = ProbabilityCloud(
            cloud_id="calibrated",
            mode=ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION,
            decision_at=DECISION_AT,
            available_at=DECISION_AT,
            horizon="4H",
            event_contract_ref="mutually-exclusive-event",
            event_contract_digest=canonical_digest(event_contract()),
            sample_contract_refs=(receipt.receipt_id,),
            model_refs=(receipt.model_ref,),
            components=(
                CloudComponent("UP", probability="0.5"),
                CloudComponent("OTHER", probability="0.5"),
            ),
            validation_receipts=(receipt,),
            mutually_exclusive=True,
            exhaustive=True,
        )
        cloud.assert_expected_value_allowed()
        self.assertTrue(cloud.to_document()["expected_value_allowed"])

    def test_cloud_update_is_append_only_and_explains_no_change(self) -> None:
        prior = subjective_cloud(level=PlausibilityLevel.MEDIUM)
        updated = subjective_cloud(level=PlausibilityLevel.HIGH)
        receipt = seal_probability_cloud_update(
            prior_cloud=prior,
            updated_cloud=updated,
            evidence=(
                CloudUpdateEvidence(
                    evidence_ref="fact-new",
                    evidence_digest="9" * 64,
                    available_at="2026-08-06T10:00:00Z",
                    quality="HIGH",
                    effect=EvidenceEffect.SUPPORT,
                    dependency_group="venue-price",
                    regime_ref="regime-candidate",
                ),
            ),
            dependency_adjustments=("deduplicated-source",),
            conflict_refs=("conflict-1",),
            update_method="ordinal-envelope-revision",
            model_version="v3.1",
            sensitivity_notes=("falls to medium if venue data are removed",),
            updated_at="2026-08-06T10:01:00Z",
        )
        self.assertNotEqual(receipt["prior_cloud_digest"], receipt["updated_cloud_digest"])
        self.assertEqual(64, len(receipt["update_receipt_digest"]))
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CLOUD_NO_CHANGE_REASON_REQUIRED"
        ):
            seal_probability_cloud_update(
                prior_cloud=prior,
                updated_cloud=prior,
                evidence=(
                    CloudUpdateEvidence(
                        evidence_ref="fact-new",
                        evidence_digest="9" * 64,
                        available_at="2026-08-06T10:00:00Z",
                        quality="HIGH",
                        effect=EvidenceEffect.CONTEXT,
                        dependency_group="venue-price",
                        regime_ref="regime-candidate",
                    ),
                ),
                dependency_adjustments=(),
                conflict_refs=(),
                update_method="no-op",
                model_version="v3.1",
                sensitivity_notes=(),
                updated_at="2026-08-06T10:01:00Z",
            )

    def test_cloud_update_identity_and_interval_partition_fail_closed(self) -> None:
        prior = subjective_cloud()
        unrelated = ProbabilityCloud(
            cloud_id="unrelated-cloud",
            mode=prior.mode,
            decision_at=prior.decision_at,
            available_at=prior.available_at,
            horizon="1Y",
            components=prior.components,
            unknown_refs=prior.unknown_refs,
            limitations=prior.limitations,
        )
        evidence = (
            CloudUpdateEvidence(
                evidence_ref="fact-new",
                evidence_digest="9" * 64,
                available_at=DECISION_AT,
                quality="HIGH",
                effect=EvidenceEffect.CONTEXT,
                dependency_group="venue-price",
                regime_ref="regime-candidate",
            ),
        )
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CLOUD_UPDATE_IDENTITY_OR_PARTITION_CHANGED"
        ):
            seal_probability_cloud_update(
                prior_cloud=prior,
                updated_cloud=unrelated,
                evidence=evidence,
                dependency_adjustments=(),
                conflict_refs=(),
                update_method="invalid-cross-cloud-update",
                model_version="v3.1",
                sensitivity_notes=("identity must remain frozen",),
                updated_at="2026-08-06T10:01:00Z",
            )
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CLOUD_INTERVAL_PARTITION_INCOHERENT"
        ):
            ProbabilityCloud(
                cloud_id="incoherent-model",
                mode=ProbabilityMode.EMPIRICAL_OR_MODEL_CONDITIONAL,
                decision_at=DECISION_AT,
                available_at=DECISION_AT,
                horizon="4H",
                event_contract_ref="event",
                event_contract_digest="a" * 64,
                sample_contract_refs=("sample",),
                components=(
                    CloudComponent("H1", lower="0.8", upper="0.9"),
                    CloudComponent("OTHER", lower="0.8", upper="0.9"),
                    CloudComponent("UNKNOWN", lower="0.8", upper="0.9"),
                ),
                mutually_exclusive=True,
                exhaustive=True,
            )

    def test_cloud_repartition_cannot_regress_available_at(self) -> None:
        prior = subjective_cloud()
        added_component = CloudComponent(
            "new-direction",
            plausibility=PlausibilityLevel.LOW,
            lower="0.1",
            upper="0.2",
            evidence_refs=("fact-new",),
            opposition_refs=("counter-fact-1",),
            sensitivity_notes=("retire if the new fact is revised",),
        )
        repartitioned = replace(
            prior,
            cloud_id="cloud-2",
            decision_at="2026-08-06T11:00:00Z",
            available_at="2026-08-06T10:30:00Z",
            components=(*prior.components, added_component),
        )
        evidence = (
            CloudUpdateEvidence(
                evidence_ref="fact-new",
                evidence_digest="9" * 64,
                available_at="2026-08-06T10:00:00Z",
                quality="HIGH",
                effect=EvidenceEffect.SUPPORT,
                dependency_group="venue-price",
                regime_ref="regime-candidate",
            ),
        )
        receipt = seal_probability_cloud_repartition(
            prior_cloud=prior,
            repartitioned_cloud=repartitioned,
            evidence=evidence,
            added_hypothesis_reasons={
                "new-direction": "new admitted evidence opens a distinct path"
            },
            retired_hypothesis_reasons={},
            sensitivity_notes=("membership changes only under explicit evidence",),
            repartitioned_at="2026-08-06T11:00:00Z",
        )
        self.assertEqual(
            repartitioned.to_document()["cloud_digest"],
            receipt["repartitioned_cloud_digest"],
        )

        regressed = replace(repartitioned, available_at="2026-08-06T09:00:00Z")
        with self.assertRaisesRegex(
            ProbabilityCloudError,
            "CLOUD_REPARTITION_AVAILABILITY_REGRESSION",
        ):
            seal_probability_cloud_repartition(
                prior_cloud=prior,
                repartitioned_cloud=regressed,
                evidence=evidence,
                added_hypothesis_reasons={
                    "new-direction": "new admitted evidence opens a distinct path"
                },
                retired_hypothesis_reasons={},
                sensitivity_notes=(
                    "membership changes only under explicit evidence",
                ),
                repartitioned_at="2026-08-06T11:00:00Z",
            )

    def test_placeholder_digest_and_caller_tampering_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CALIBRATION_PLACEHOLDER_DIGEST_FORBIDDEN"
        ):
            FrozenPredictiveForecast(
                forecast_id="placeholder",
                prediction_at="2026-08-01T00:00:00Z",
                model_input_digest="1" * 64,
                probabilities=(("UP", "0.5"), ("OTHER", "0.5")),
            )

        receipt = validation_receipt()
        object.__setattr__(receipt, "score_value", Decimal("0"))
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CALIBRATION_RECEIPT_RECOMPUTATION_MISMATCH"
        ):
            receipt.to_document()

        mutable_receipt = validation_receipt()
        cloud = ProbabilityCloud(
            cloud_id="tamper-after-admission",
            mode=ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION,
            decision_at=DECISION_AT,
            available_at=DECISION_AT,
            horizon="4H",
            event_contract_ref=mutable_receipt.event_contract_ref,
            event_contract_digest=mutable_receipt.event_contract_digest,
            sample_contract_refs=(mutable_receipt.receipt_id,),
            model_refs=(mutable_receipt.model_ref,),
            components=(
                CloudComponent("UP", probability="0.5"),
                CloudComponent("OTHER", probability="0.5"),
            ),
            validation_receipts=(mutable_receipt,),
            mutually_exclusive=True,
            exhaustive=True,
        )
        mutable_receipt.event_contract["resolution_rule"] = "tampered after admission"
        self.assertFalse(cloud.allows_expected_value)
        with self.assertRaisesRegex(
            ProbabilityCloudError,
            "EXPECTED_VALUE_REQUIRES_CALIBRATED_DISTRIBUTION",
        ):
            cloud.assert_expected_value_allowed()

    def test_frozen_split_overlap_and_bad_calibration_fail_closed(self) -> None:
        development = frozen_sample(
            "DEVELOPMENT", start_at=datetime(2026, 8, 1, tzinfo=UTC)
        )
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CALIBRATION_SAMPLE_OVERLAP_FORBIDDEN"
        ):
            PredictiveValidationReceipt(
                receipt_id="overlap",
                event_contract_ref="mutually-exclusive-event",
                event_contract=event_contract(),
                horizon="4H",
                model_ref="model-v1",
                model_contract=model_contract(),
                development_sample=development,
                calibration_sample=development,
                oos_sample=frozen_sample(
                    "OOS", start_at=datetime(2026, 8, 3, tzinfo=UTC)
                ),
                deployment_forecast=validation_receipt().deployment_forecast,
                scoring_rule=ProperScoringRule.BRIER,
                available_at="2026-08-04T00:00:00Z",
                invalidation_conditions=("drift",),
                limitations=("local-only",),
            )

        with self.assertRaisesRegex(
            ProbabilityCloudError, "CALIBRATION_ERROR_LIMIT_EXCEEDED"
        ):
            PredictiveValidationReceipt(
                receipt_id="miscalibrated",
                event_contract_ref="mutually-exclusive-event",
                event_contract=event_contract(),
                horizon="4H",
                model_ref="model-v1",
                model_contract=model_contract(probability_up="0.9"),
                development_sample=frozen_sample(
                    "DEVELOPMENT",
                    start_at=datetime(2026, 8, 1, tzinfo=UTC),
                    probability_up="0.9",
                ),
                calibration_sample=frozen_sample(
                    "CALIBRATION",
                    start_at=datetime(2026, 8, 2, tzinfo=UTC),
                    probability_up="0.9",
                ),
                oos_sample=frozen_sample(
                    "OOS",
                    start_at=datetime(2026, 8, 3, tzinfo=UTC),
                    probability_up="0.9",
                ),
                deployment_forecast=FrozenPredictiveForecast(
                    forecast_id="miscalibrated-deployment",
                    prediction_at="2026-08-06T09:59:00Z",
                    model_input_digest=canonical_digest(
                        {"deployment": "miscalibrated"}
                    ),
                    probabilities=(("UP", "0.9"), ("OTHER", "0.1")),
                ),
                scoring_rule=ProperScoringRule.BRIER,
                available_at="2026-08-04T00:00:00Z",
                invalidation_conditions=("drift",),
                limitations=("local-only",),
            )

    def test_cloud_must_match_recomputed_deployment_forecast(self) -> None:
        receipt = validation_receipt()
        with self.assertRaisesRegex(
            ProbabilityCloudError, "CALIBRATION_RECEIPT_CLOUD_BINDING_INVALID"
        ):
            ProbabilityCloud(
                cloud_id="forged-current-vector",
                mode=ProbabilityMode.CALIBRATED_PREDICTIVE_DISTRIBUTION,
                decision_at=DECISION_AT,
                available_at=DECISION_AT,
                horizon="4H",
                event_contract_ref=receipt.event_contract_ref,
                event_contract_digest=receipt.event_contract_digest,
                sample_contract_refs=(receipt.receipt_id,),
                model_refs=(receipt.model_ref,),
                components=(
                    CloudComponent("UP", probability="0.9"),
                    CloudComponent("OTHER", probability="0.1"),
                ),
                validation_receipts=(receipt,),
                mutually_exclusive=True,
                exhaustive=True,
            )

    def test_validation_replay_is_independent_of_caller_decimal_context(self) -> None:
        expected = validation_receipt().to_document()["validation_receipt_digest"]
        with localcontext() as context:
            context.prec = 6
            actual = validation_receipt().to_document()["validation_receipt_digest"]
        self.assertEqual(expected, actual)


class ScenarioPathTests(unittest.TestCase):
    def test_strict_path_is_non_executable_and_preserves_other(self) -> None:
        rule = valid_path()
        document = rule.to_document()
        self.assertFalse(document["executable"])
        self.assertTrue(document["preserves_other_unknown"])
        self.assertFalse(document["action_implications"][0]["authorized"])
        path_set = ScenarioPathSet(
            set_id="set-1",
            decision_at=DECISION_AT,
            paths=(rule, valid_path("path-b")),
            lead_path_id="path-a",
            runner_up_path_id="path-b",
        )
        self.assertEqual("OTHER", path_set.to_document()["residual_path_id"])

    def test_information_cannot_jump_directly_to_action(self) -> None:
        with self.assertRaisesRegex(
            ScenarioPathError, "PATH_EPISTEMIC_JUMP_FORBIDDEN"
        ):
            EpistemicTransition(
                from_stage=EpistemicStage.OBSERVED_INFORMATION,
                to_stage=EpistemicStage.POLICY_CANDIDATE,
                target_ref="open-long",
                update_type="FAVOR",
            )
        with self.assertRaisesRegex(
            ScenarioPathError, "PATH_EPISTEMIC_JUMP_FORBIDDEN"
        ):
            EpistemicTransition(
                from_stage=EpistemicStage.POLICY_CANDIDATE,
                to_stage=EpistemicStage.AUTHORIZED_ACTION,
                target_ref="order",
                update_type="AUTHORIZE",
            )

    def test_path_requires_guards_falsifier_else_and_review(self) -> None:
        source = valid_path()
        values = {
            field: getattr(source, field)
            for field in source.__dataclass_fields__
        }
        values["else_path_refs"] = ()
        values["preserves_other_unknown"] = False
        with self.assertRaisesRegex(ScenarioPathError, "PATH_ELSE_OR_OTHER_REQUIRED"):
            ScenarioPathRule(**values)

    def test_three_valued_evaluation_never_turns_missing_into_false(self) -> None:
        rule = valid_path()
        self.assertEqual(
            PredicateTruth.UNKNOWN,
            evaluate_path_conditions(
                rule,
                {
                    "spread_state": fact("spread_state", "WIDE"),
                    "book_quality": fact("book_quality", "MEDIUM"),
                },
                evaluated_at=DECISION_AT,
            ),
        )
        self.assertEqual(
            PredicateTruth.TRUE,
            evaluate_path_conditions(
                rule,
                {
                    "spread_state": fact("spread_state", "WIDE"),
                    "book_quality": fact("book_quality", "MEDIUM"),
                    "venue_outage": fact("venue_outage", False),
                },
                evaluated_at=DECISION_AT,
            ),
        )

    def test_due_hard_falsifier_and_future_fact_fail_closed(self) -> None:
        rule = valid_path()
        rows = {
            "spread_state": fact("spread_state", "WIDE"),
            "book_quality": fact("book_quality", "MEDIUM"),
            "venue_outage": fact("venue_outage", False),
            "depth_recovered": PathFactSnapshot(
                fact_ref="depth_recovered",
                fact_digest="b" * 64,
                value=True,
                available_at="2026-08-06T11:00:00Z",
                missingness="OBSERVED",
                quality=PredicateQuality.HIGH,
                coverage="1",
                conflict_state="NONE",
            ),
        }
        self.assertEqual(
            PredicateTruth.FALSE,
            evaluate_path_conditions(
                rule, rows, evaluated_at="2026-08-06T11:00:00Z"
            ),
        )
        future_entry = dict(rows)
        future_entry["spread_state"] = fact(
            "spread_state", "WIDE", available_at="2026-08-06T10:00:01Z"
        )
        with self.assertRaisesRegex(ScenarioPathError, "PATH_FACT_DIGEST_MISMATCH"):
            evaluate_path_conditions(
                rule,
                {**rows, "spread_state": PathFactSnapshot(
                    fact_ref="spread_state",
                    fact_digest="b" * 64,
                    value="WIDE",
                    available_at="2026-08-06T09:59:00Z",
                    missingness="OBSERVED",
                    quality=PredicateQuality.HIGH,
                    coverage="1",
                    conflict_state="NONE",
                )},
                evaluated_at=DECISION_AT,
            )
        self.assertEqual(
            PredicateTruth.UNKNOWN,
            evaluate_path_conditions(rule, future_entry, evaluated_at=DECISION_AT),
        )

    def test_string_in_and_mismatched_path_set_time_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            ScenarioPathError, "PATH_IN_EXPECTED_COLLECTION_REQUIRED"
        ):
            predicate(
                "bad-in", "narrative", "ABCDE", operator=PredicateOperator.IN
            )
        later = valid_path("later")
        values = {field: getattr(later, field) for field in later.__dataclass_fields__}
        values["decision_at"] = "2026-08-06T10:01:00Z"
        values["expires_at"] = "2026-08-07T10:01:00Z"
        values["next_review_at"] = "2026-08-06T11:01:00Z"
        values["triggers"] = (
            predicate("later-t", "spread_state", "WIDE"),
        )
        values["guards"] = (
            predicate("later-g", "book_quality", "MEDIUM"),
        )
        values["unless"] = (
            predicate("later-u", "venue_outage", True),
        )
        values["falsifiers"] = (
            predicate(
                "later-f",
                "depth_recovered",
                True,
                timing=PredicateTiming.FUTURE_MONITOR,
                available_at="2026-08-06T11:01:00Z",
            ),
        )
        later = ScenarioPathRule(**values)
        with self.assertRaisesRegex(ScenarioPathError, "PATH_SET_DECISION_TIME_MISMATCH"):
            ScenarioPathSet(
                set_id="bad-time",
                decision_at=DECISION_AT,
                paths=(valid_path(), later),
                lead_path_id="path-a",
                runner_up_path_id="later",
            )


if __name__ == "__main__":
    unittest.main()
