from __future__ import annotations

import copy
import unittest
from datetime import UTC, datetime, timedelta

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.association_estimation import (
    PairedNumericObservation,
    estimate_pearson_association,
)
from trade_system.theory_paper_v2.domain.v31_experiment_contracts import (
    APPROVED_THEORY_SHA256,
    ClosedHourCycleBinding,
    FrozenMonitorRule,
    MonitorOperator,
    MonitorRuleRole,
    ObservationMissingness,
    ObservationQuality,
    OutcomeObservation,
    V31ExperimentContractError,
    build_minimal_experiment_contract,
    build_path_outcome_receipt,
    build_typed_path_monitor_plan,
    verify_minimal_experiment_contract,
    verify_eight_closed_hour_cycles,
    verify_frozen_association_receipt,
    verify_path_outcome_receipt,
    verify_typed_path_monitor_plan,
)


ASSOCIATION_BASE = datetime(2026, 8, 5, tzinfo=UTC)


def origins(*, digest_character: str = "a") -> dict[str, dict[str, str]]:
    return {
        "accepted_state": {"ref": "accepted:1", "digest": digest_character * 64},
        "path_set": {"ref": "path-set:1", "digest": "b" * 64},
        "path": {"ref": "path:lead", "digest": "c" * 64},
        "hypothesis_revision": {"ref": "hypothesis:1:r1", "digest": "d" * 64},
        "expectation_revision": {"ref": "expectation:1:r1", "digest": "e" * 64},
    }


def rules() -> tuple[FrozenMonitorRule, ...]:
    observable = "metric:next-closed-1h-return-pct"
    return (
        FrozenMonitorRule(
            rule_id="confirm-positive",
            role=MonitorRuleRole.CONFIRMATION,
            observable_ref=observable,
            operator=MonitorOperator.GT,
            expected="0",
            unit="PERCENT",
        ),
        FrozenMonitorRule(
            rule_id="contradict-negative",
            role=MonitorRuleRole.CONTRADICTION,
            observable_ref=observable,
            operator=MonitorOperator.LT,
            expected="0",
            unit="PERCENT",
        ),
        FrozenMonitorRule(
            rule_id="falsify-large-loss",
            role=MonitorRuleRole.FALSIFIER,
            observable_ref=observable,
            operator=MonitorOperator.LTE,
            expected="-5",
            unit="PERCENT",
        ),
    )


def accepted_cycles() -> tuple[ClosedHourCycleBinding, ...]:
    result = []
    for index in range(8):
        as_of = ASSOCIATION_BASE + timedelta(hours=index)
        result.append(
            ClosedHourCycleBinding(
                cycle_index=index + 1,
                cycle_id=f"cycle:{index + 1}",
                pair_universe_id=(
                    "OKX:BTC-USDT-SWAP:"
                    "1H_RETURN__VOLUME_VS_20BAR_MEDIAN"
                ),
                pair_id=f"association-pair:{index + 1}",
                bar_as_of=as_of.isoformat().replace("+00:00", "Z"),
                pair_available_at=(as_of + timedelta(hours=1, minutes=1))
                .isoformat()
                .replace("+00:00", "Z"),
                source_datum_digest="12345678"[index] * 64,
                target_datum_digest="9abcdef0"[index] * 64,
                accepted_state_digest="f" * 64,
            )
        )
    return tuple(result)


def frozen_association_receipt(*, multiplicity: str | None = None) -> dict:
    cycles = accepted_cycles()
    observations = tuple(
        PairedNumericObservation(
            pair_id=cycle.pair_id,
            as_of=cycle.bar_as_of,
            available_at=cycle.pair_available_at,
            source_value=str(index + 1),
            target_value=str((index + 1) * 2),
            source_datum_digest=cycle.source_datum_digest,
            target_datum_digest=cycle.target_datum_digest,
        )
        for index, cycle in enumerate(cycles)
    )
    return estimate_pearson_association(
        association_id="association:btc-swap-return-volume",
        source_node_id="metric:candle-1h-return-pct",
        target_node_id="metric:candle-1h-volume-vs-20bar-median",
        decision_at="2026-08-05T08:02:00Z",
        timeframe="1H",
        observations=observations,
        multiple_testing_control=(
            multiplicity
            or "SINGLE_PRE_REGISTERED_PAIR_FAMILY_SIZE_1_NO_CORRECTION"
        ),
        limitations=("Descriptive end-of-run diagnostic only.",),
    )


class V31ExperimentContractsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_minimal_experiment_contract(
            contract_id="v31-minimal-contract",
            run_id="v31-fresh-btc-swap-001",
            frozen_at="2026-08-06T09:00:00Z",
        )
        self.origins = origins()
        self.plan = self._plan(cycle_index=1, decision_at="2026-08-06T10:00:00Z")

    def _plan(self, *, cycle_index: int, decision_at: str) -> dict:
        return build_typed_path_monitor_plan(
            experiment_contract=self.contract,
            monitor_plan_id=f"monitor:{cycle_index}",
            cycle_id=f"cycle:{cycle_index}",
            cycle_index=cycle_index,
            origin_bindings=self.origins,
            decision_at=decision_at,
            observable_ref="metric:next-closed-1h-return-pct",
            source_request_id=f"okx-public-outcome:{cycle_index}",
            rules=rules(),
        )

    def _observation(
        self,
        *,
        value: str | None = "1.25",
        as_of: str = "2026-08-06T11:00:00Z",
        available_at: str = "2026-08-06T11:01:00Z",
        missingness: ObservationMissingness = ObservationMissingness.OBSERVED,
        quality: ObservationQuality = ObservationQuality.HIGH,
        coverage: str = "1",
        conflict_state: str = "NONE",
        request_id: str = "okx-public-outcome:1",
    ) -> OutcomeObservation:
        return OutcomeObservation(
            observable_ref="metric:next-closed-1h-return-pct",
            value=value,
            as_of=as_of,
            available_at=available_at,
            missingness=missingness,
            quality=quality,
            coverage=coverage,
            conflict_state=conflict_state,
            source_request_id=request_id,
            source_record_digest="1" * 64,
            raw_capture_digest="2" * 64,
            datum_digest="3" * 64,
        )

    def _receipt(
        self,
        *,
        plan: dict | None = None,
        observation: OutcomeObservation | None = None,
        evaluated_at: str = "2026-08-06T11:02:00Z",
        previous: dict | None = None,
        expected_previous_digest: str | None = None,
    ) -> dict:
        return build_path_outcome_receipt(
            experiment_contract=self.contract,
            monitor_plan=plan or self.plan,
            expected_origin_bindings=self.origins,
            outcome_receipt_id=f"outcome:{(plan or self.plan)['cycle_index']}",
            evaluated_at=evaluated_at,
            evaluator_version="V3_1_TYPED_MONITOR_EVALUATOR_1_0_0",
            observation=observation or self._observation(),
            previous_outcome_receipt=previous,
            expected_previous_outcome_receipt_digest=expected_previous_digest,
        )

    def test_contract_freezes_exact_instrument_cycles_portfolio_and_authority(self) -> None:
        self.assertEqual(
            self.contract["experiment_contract_digest"],
            verify_minimal_experiment_contract(self.contract),
        )
        self.assertEqual(APPROVED_THEORY_SHA256, self.contract["approved_theory_sha256"])
        self.assertEqual("BTC-USDT-SWAP", self.contract["instrument"]["instrument_id"])
        self.assertEqual("PERPETUAL_SWAP", self.contract["instrument"]["market_type"])
        self.assertFalse(self.contract["instrument"]["spot_claim"])
        self.assertEqual(8, self.contract["cycle_protocol"]["accepted_cycle_count"])
        self.assertEqual("CLOSED_ONLY", self.contract["cycle_protocol"]["bar_state"])
        self.assertEqual("1H", self.contract["cycle_protocol"]["outcome_horizon"])
        self.assertEqual(
            "STATIC_COUNTERFACTUAL_FLAT_SHADOW",
            self.contract["portfolio_scope"]["mode"],
        )
        self.assertEqual(
            ["OPEN_LONG", "OPEN_SHORT", "WAIT"],
            self.contract["portfolio_scope"]["legal_research_labels"],
        )
        financial = self.contract["portfolio_scope"]["financial_shadow"]
        self.assertEqual(
            "10000", financial["initial_shadow_account"]["equity_usdt"]
        )
        self.assertEqual(
            "0.01",
            financial["market_economics_policy"]["contract_multiplier"],
        )
        self.assertEqual(
            [25], financial["candidate_grid"]["entry_scale_grid_pct"]
        )
        self.assertIs(
            financial["market_economics_policy"]["funding_cost_included"],
            False,
        )
        boundary = self.contract["authority_boundary"]
        for field in (
            "executable",
            "account_access",
            "paper_trading",
            "live_trading",
            "order_submission",
            "credential_use",
            "funds_access",
            "portfolio_mutation",
        ):
            self.assertIs(boundary[field], False)

    def test_association_universe_window_lag_and_multiplicity_are_exact(self) -> None:
        scope = self.contract["association_scope"]
        self.assertEqual(1, scope["candidate_pair_count"])
        self.assertEqual("FORBIDDEN", scope["candidate_search"])
        self.assertFalse(scope["action_or_probability_input"])
        pair = scope["pair_universe"][0]
        self.assertEqual("candle-1h-return-pct", pair["source_metric"])
        self.assertEqual("candle-1h-volume-vs-20bar-median", pair["target_metric"])
        self.assertEqual(
            {"value": 0, "unit": "1H", "direction": "SYNCHRONOUS"}, pair["lag"]
        )
        self.assertEqual(8, scope["window"]["sample_count"])
        self.assertEqual(1, scope["multiplicity"]["family_size"])
        self.assertEqual(
            "SINGLE_PRE_REGISTERED_PAIR_FAMILY_SIZE_1_NO_CORRECTION",
            scope["multiplicity"]["policy"],
        )
        self.assertEqual("DESCRIPTIVE_END_OF_RUN_DIAGNOSTIC_ONLY", scope["use"])

    def test_pearson_receipt_is_bound_to_exactly_eight_accepted_closed_hours(self) -> None:
        cycles = accepted_cycles()
        sequence_digest = verify_eight_closed_hour_cycles(
            experiment_contract=self.contract,
            cycles=cycles,
            completed_at="2026-08-05T08:02:00Z",
        )
        binding_digest = verify_frozen_association_receipt(
            experiment_contract=self.contract,
            receipt=frozen_association_receipt(),
            accepted_cycles=cycles,
        )
        self.assertEqual(64, len(sequence_digest))
        self.assertEqual(64, len(binding_digest))

    def test_duplicate_cycle_and_nonfrozen_multiplicity_fail_closed(self) -> None:
        cycles = list(accepted_cycles())
        cycles[7] = ClosedHourCycleBinding(
            cycle_index=8,
            cycle_id="cycle:8",
            pair_universe_id=cycles[7].pair_universe_id,
            pair_id="association-pair:8",
            bar_as_of=cycles[6].bar_as_of,
            pair_available_at=cycles[7].pair_available_at,
            source_datum_digest=cycles[7].source_datum_digest,
            target_datum_digest=cycles[7].target_datum_digest,
            accepted_state_digest=cycles[7].accepted_state_digest,
        )
        with self.assertRaisesRegex(V31ExperimentContractError, "BAR_SEQUENCE_INVALID"):
            verify_eight_closed_hour_cycles(
                experiment_contract=self.contract,
                cycles=cycles,
                completed_at="2026-08-05T08:02:00Z",
            )
        with self.assertRaisesRegex(V31ExperimentContractError, "SCOPE_MISMATCH"):
            verify_frozen_association_receipt(
                experiment_contract=self.contract,
                receipt=frozen_association_receipt(
                    multiplicity="SINGLE_PRE_REGISTERED_PAIR"
                ),
                accepted_cycles=accepted_cycles(),
            )

    def test_cycle_sequence_binds_one_preregistered_pair_universe_and_hourly_cadence(self) -> None:
        wrong_universe = list(accepted_cycles())
        wrong_universe[7] = ClosedHourCycleBinding(
            cycle_index=8,
            cycle_id="cycle:8",
            pair_universe_id="UNREGISTERED_PAIR_UNIVERSE",
            pair_id="association-pair:8",
            bar_as_of=wrong_universe[7].bar_as_of,
            pair_available_at=wrong_universe[7].pair_available_at,
            source_datum_digest=wrong_universe[7].source_datum_digest,
            target_datum_digest=wrong_universe[7].target_datum_digest,
            accepted_state_digest=wrong_universe[7].accepted_state_digest,
        )
        with self.assertRaisesRegex(
            V31ExperimentContractError, "PAIR_UNIVERSE_MISMATCH"
        ):
            verify_eight_closed_hour_cycles(
                experiment_contract=self.contract,
                cycles=wrong_universe,
                completed_at="2026-08-05T08:02:00Z",
            )

        skipped_hour = list(accepted_cycles())
        skipped_hour[7] = ClosedHourCycleBinding(
            cycle_index=8,
            cycle_id="cycle:8",
            pair_universe_id=skipped_hour[7].pair_universe_id,
            pair_id="association-pair:8",
            bar_as_of="2026-08-05T08:00:00Z",
            pair_available_at="2026-08-05T09:01:00Z",
            source_datum_digest=skipped_hour[7].source_datum_digest,
            target_datum_digest=skipped_hour[7].target_datum_digest,
            accepted_state_digest=skipped_hour[7].accepted_state_digest,
        )
        with self.assertRaisesRegex(
            V31ExperimentContractError, "BAR_SEQUENCE_INVALID"
        ):
            verify_eight_closed_hour_cycles(
                experiment_contract=self.contract,
                cycles=skipped_hour,
                completed_at="2026-08-05T09:02:00Z",
            )

    def test_capability_matrix_never_uses_an_excluded_capability(self) -> None:
        matrix = self.contract["capability_matrix"]
        self.assertTrue(any(row["status"] == "EXCLUDED_NO_CLAIM" for row in matrix))
        self.assertFalse(
            any(
                row["status"] == "EXCLUDED_NO_CLAIM" and row["used_or_evaluated"]
                for row in matrix
            )
        )
        durable_monitor = next(
            row
            for row in matrix
            if row["capability_id"] == "DURABLE_CROSS_CYCLE_MONITOR_RUNTIME"
        )
        self.assertEqual("IMPLEMENTED_AND_VERIFIED", durable_monitor["status"])
        self.assertTrue(durable_monitor["used_or_evaluated"])
        self.assertEqual("LOCAL_DURABLE_RUNTIME", durable_monitor["evidence_scope"])
        self.assertEqual("CONTRACT_ONLY_NOT_RUN_READY", self.contract["readiness_status"])

    def test_resigned_contract_scope_drift_fails_reconstruction(self) -> None:
        forged = copy.deepcopy(self.contract)
        forged["instrument"]["instrument_id"] = "BTC-USDT"
        forged = self_digest(forged, "experiment_contract_digest")
        with self.assertRaisesRegex(
            V31ExperimentContractError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_minimal_experiment_contract(forged)

    def test_monitor_plan_is_typed_one_hour_and_exactly_origin_bound(self) -> None:
        self.assertEqual(
            self.plan["monitor_plan_digest"],
            verify_typed_path_monitor_plan(
                self.plan,
                experiment_contract=self.contract,
                expected_origin_bindings=self.origins,
            ),
        )
        self.assertEqual("2026-08-06T11:00:00Z", self.plan["outcome_not_before"])
        self.assertEqual("2026-08-06T11:15:00Z", self.plan["expires_at"])
        self.assertEqual(
            "FIRST_PUBLIC_MARK_OBSERVATION_AT_OR_AFTER_1H_HORIZON",
            self.plan["observable"]["window"],
        )
        self.assertEqual("GET", self.plan["observable"]["request_method"])
        self.assertEqual(
            "https://www.okx.com/api/v5/public/mark-price",
            self.plan["observable"]["source_endpoint"],
        )
        self.assertEqual(
            {"CONFIRMATION", "CONTRADICTION", "FALSIFIER"},
            {item["role"] for item in self.plan["rules"]},
        )

    def test_wrong_origin_digest_is_rejected_even_when_plan_is_unchanged(self) -> None:
        wrong = copy.deepcopy(self.origins)
        wrong["expectation_revision"]["digest"] = "f" * 64
        with self.assertRaisesRegex(
            V31ExperimentContractError, "ORIGIN_BINDINGS_MISMATCH"
        ):
            verify_typed_path_monitor_plan(
                self.plan,
                experiment_contract=self.contract,
                expected_origin_bindings=wrong,
            )

    def test_monitor_plan_resigned_semantic_drift_fails_reconstruction(self) -> None:
        forged = copy.deepcopy(self.plan)
        forged["outcome_horizon"] = "4H"
        forged = self_digest(forged, "monitor_plan_digest")
        with self.assertRaisesRegex(
            V31ExperimentContractError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_typed_path_monitor_plan(
                forged,
                experiment_contract=self.contract,
                expected_origin_bindings=self.origins,
            )

    def test_outcome_cannot_be_read_before_frozen_horizon(self) -> None:
        observation = self._observation(available_at="2026-08-06T11:00:00Z")
        with self.assertRaisesRegex(
            V31ExperimentContractError, "READ_BEFORE_NOT_BEFORE"
        ):
            self._receipt(
                observation=observation, evaluated_at="2026-08-06T10:59:59Z"
            )

    def test_future_non_pit_and_wrong_window_observations_fail_closed(self) -> None:
        with self.assertRaisesRegex(V31ExperimentContractError, "NOT_POINT_IN_TIME"):
            self._observation(
                as_of="2026-08-06T11:01:00Z",
                available_at="2026-08-06T11:00:00Z",
            )
        with self.assertRaisesRegex(V31ExperimentContractError, "FUTURE_DATA"):
            self._receipt(
                observation=self._observation(available_at="2026-08-06T11:03:00Z")
            )
        with self.assertRaisesRegex(V31ExperimentContractError, "WRONG_1H_WINDOW"):
            self._receipt(
                observation=self._observation(
                    as_of="2026-08-06T10:59:00Z",
                    available_at="2026-08-06T11:00:00Z",
                )
            )

    def test_unknown_cannot_be_coerced_to_zero(self) -> None:
        with self.assertRaisesRegex(
            V31ExperimentContractError, "UNKNOWN_VALUE_IMPUTATION_FORBIDDEN"
        ):
            self._observation(
                value="0",
                missingness=ObservationMissingness.UNKNOWN,
                quality=ObservationQuality.UNKNOWN,
                coverage="0",
            )

    def test_fulfilled_falsified_other_and_unknown_are_distinct(self) -> None:
        fulfilled = self._receipt()
        self.assertEqual("FULFILLED", fulfilled["expectation_outcome"])
        self.assertEqual("SUPPORTED", fulfilled["path_outcome"])
        for document in (self.plan, fulfilled):
            boundary = document["authority_boundary"]
            self.assertTrue(
                all(
                    boundary[field] is False
                    for field in (
                        "executable",
                        "account_access",
                        "paper_trading",
                        "live_trading",
                        "order_submission",
                        "credential_use",
                        "funds_access",
                        "portfolio_mutation",
                    )
                )
            )

        falsified = self._receipt(observation=self._observation(value="-6"))
        self.assertEqual("FALSIFIED", falsified["expectation_outcome"])
        self.assertEqual("FALSIFIED", falsified["path_outcome"])

        other = self._receipt(observation=self._observation(value="0"))
        self.assertEqual("PARTIAL", other["expectation_outcome"])
        self.assertEqual("OTHER", other["path_outcome"])

        unknown = self._receipt(
            observation=self._observation(
                value=None,
                missingness=ObservationMissingness.UNKNOWN,
                quality=ObservationQuality.UNKNOWN,
                coverage="0",
            )
        )
        self.assertEqual("UNKNOWN", unknown["expectation_outcome"])
        self.assertEqual("UNRESOLVED", unknown["path_outcome"])
        self.assertTrue(unknown["coverage_loss"])

    def test_missing_at_exact_expiry_is_expired_not_falsified(self) -> None:
        expired = self._receipt(
            observation=self._observation(
                value=None,
                available_at="2026-08-06T11:15:00Z",
                missingness=ObservationMissingness.MISSING,
                quality=ObservationQuality.UNKNOWN,
                coverage="0",
            ),
            evaluated_at="2026-08-06T11:15:00Z",
        )
        self.assertEqual("EXPIRED", expired["expectation_outcome"])
        self.assertEqual("UNRESOLVED", expired["path_outcome"])
        self.assertNotEqual("FALSIFIED", expired["expectation_outcome"])

    def test_outcome_receipt_tampering_and_resigned_result_drift_are_rejected(self) -> None:
        receipt = self._receipt()
        tampered = copy.deepcopy(receipt)
        tampered["path_outcome"] = "FALSIFIED"
        with self.assertRaisesRegex(V31ExperimentContractError, "OUTCOME_RECEIPT_INVALID"):
            verify_path_outcome_receipt(
                tampered,
                experiment_contract=self.contract,
                monitor_plan=self.plan,
                expected_origin_bindings=self.origins,
            )

        resigned = self_digest(tampered, "outcome_receipt_digest")
        with self.assertRaisesRegex(
            V31ExperimentContractError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_path_outcome_receipt(
                resigned,
                experiment_contract=self.contract,
                monitor_plan=self.plan,
                expected_origin_bindings=self.origins,
            )

    def test_outcome_receipt_chain_requires_exact_immediate_predecessor(self) -> None:
        first = self._receipt()
        second_plan = self._plan(cycle_index=2, decision_at="2026-08-06T11:00:00Z")
        second_observation = self._observation(
            value="2",
            as_of="2026-08-06T12:00:00Z",
            available_at="2026-08-06T12:01:00Z",
            request_id="okx-public-outcome:2",
        )
        with self.assertRaisesRegex(
            V31ExperimentContractError, "PREVIOUS_RECEIPT_REQUIRED"
        ):
            self._receipt(
                plan=second_plan,
                observation=second_observation,
                evaluated_at="2026-08-06T12:02:00Z",
            )
        second = self._receipt(
            plan=second_plan,
            observation=second_observation,
            evaluated_at="2026-08-06T12:02:00Z",
            previous=first,
            expected_previous_digest=first["outcome_receipt_digest"],
        )
        self.assertEqual(
            first["outcome_receipt_digest"], second["previous_outcome_receipt_digest"]
        )
        self.assertEqual(
            second["outcome_receipt_digest"],
            verify_path_outcome_receipt(
                second,
                experiment_contract=self.contract,
                monitor_plan=second_plan,
                expected_origin_bindings=self.origins,
                previous_outcome_receipt=first,
                expected_previous_outcome_receipt_digest=first[
                    "outcome_receipt_digest"
                ],
            ),
        )

        tampered_first = copy.deepcopy(first)
        tampered_first["expectation_outcome"] = "FALSIFIED"
        with self.assertRaisesRegex(V31ExperimentContractError, "TAMPERED"):
            self._receipt(
                plan=second_plan,
                observation=second_observation,
                evaluated_at="2026-08-06T12:02:00Z",
                previous=tampered_first,
                expected_previous_digest=first["outcome_receipt_digest"],
            )

        resigned_first = self_digest(tampered_first, "outcome_receipt_digest")
        with self.assertRaisesRegex(
            V31ExperimentContractError, "PREVIOUS_ACCEPTED_HEAD_MISMATCH"
        ):
            self._receipt(
                plan=second_plan,
                observation=second_observation,
                evaluated_at="2026-08-06T12:02:00Z",
                previous=resigned_first,
                expected_previous_digest=first["outcome_receipt_digest"],
            )

    def test_stale_old_receipt_cannot_skip_a_cycle_in_chain(self) -> None:
        first = self._receipt()
        third_plan = self._plan(cycle_index=3, decision_at="2026-08-06T12:00:00Z")
        third_observation = self._observation(
            as_of="2026-08-06T13:00:00Z",
            available_at="2026-08-06T13:01:00Z",
            request_id="okx-public-outcome:3",
        )
        with self.assertRaisesRegex(
            V31ExperimentContractError, "PREVIOUS_RECEIPT_CHAIN_MISMATCH"
        ):
            self._receipt(
                plan=third_plan,
                observation=third_observation,
                evaluated_at="2026-08-06T13:02:00Z",
                previous=first,
                expected_previous_digest=first["outcome_receipt_digest"],
            )


if __name__ == "__main__":
    unittest.main()
