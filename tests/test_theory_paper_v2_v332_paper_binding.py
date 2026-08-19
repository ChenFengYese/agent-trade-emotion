from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    CarryAccrualV1,
    PaperCommandV1,
    PaperMarketSliceV1,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_authority import (
    SealedCyclePaperDecisionAuthority,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.repository import (
    FileCycleRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_DATA_PROFILE,
    HYPE_OKX_INSTRUMENT_ID,
    build_hype_data_profile_service,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_snapshot import (
    OkxSnapshotError,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    FUNDING_RATE_HISTORY_PATH,
    ORDER_BOOK_PATH,
)
from trade_system.theory_paper_v2.infrastructure.market_data.paper_evidence import (
    AdmittedAssetSlicePaperMarketEvidence,
    PaperAssetEvidenceBinding,
    PaperMarketEvidenceConfigurationError,
    derive_paper_market_slices,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)

from tests.test_theory_paper_v2_market_cycle_repository import (
    _behavior_plan,
    _hypothesis_record,
    _request,
    _seal_raw_reference,
    _snapshot,
)
from tests.test_theory_paper_v2_v332_hype_data import (
    _BASE,
    _json,
    _ms,
    _seal,
    _seal_core,
)


class V332PaperDecisionAuthorityBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        runtime = root / "runtime"
        self.raw_store = FileRawCaptureStore(runtime)
        self.cycles = FileCycleRepository(
            runtime / "cycles", raw_capture_verifier=self.raw_store
        )
        self.cycle_id = "cycle-btc-001"
        state = self.cycles.create(_request())
        raw_ref = _seal_raw_reference(
            self.raw_store,
            capture_id="paper-binding-input",
            payload=b"paper-binding-sealed-input",
        )
        state = self.cycles.transition(
            expected=state,
            artifacts=(_snapshot(raw_ref=raw_ref),),
            next_stage="INPUT_SEALED",
            next_action="ANALYZE",
        )
        record = _hypothesis_record(state.artifact_refs[-1])
        state = self.cycles.transition(
            expected=state,
            artifacts=(record,),
            next_stage="ANALYZED",
            next_action="COPY_AGENT_DECISION_TO_PLAN",
        )
        plan = _behavior_plan(state.artifact_refs[-1])
        self.cycles.transition(
            expected=state,
            artifacts=(plan,),
            next_stage="PLAN_SEALED",
            next_action="WAIT_FOR_OUTCOME",
        )
        self.decision_sha256 = record.agent_decision_sha256

        attention_repository = FileAttentionRepository(root / "attention")
        self.sessions = AgentSessionService(attention_repository)
        self.sessions.register(
            AgentRegistry(
                logical_agent_id="btc-trader",
                symbol="BTC-USDT-SWAP",
                generation=1,
                continuity_nonce="btc-trader-generation-1",
                physical_task_id="btc-task-generation-1",
                status="ACTIVE",
                registered_at="2026-08-11T00:00:00+00:00",
            )
        )
        self.authority = SealedCyclePaperDecisionAuthority(
            sessions=self.sessions,
            cycle_repository=self.cycles,
            agent_cycle_bindings={"btc-trader": (self.cycle_id,)},
        )

    def _command(self, **changes: object) -> PaperCommandV1:
        values: dict[str, object] = {
            "command_id": "paper-command-001",
            "account_id": "paper-btc-account",
            "logical_agent_id": "btc-trader",
            "agent_generation": 1,
            "decision_cycle_id": self.cycle_id,
            "decision_sha256": self.decision_sha256,
            "expected_account_version": 1,
            "symbol": "BTC-USDT-SWAP",
            "command_type": "LIMIT",
            "side": "BUY",
            "quantity": "0.001",
            "limit_price": "100000",
            "trigger_price": None,
            "target_order_id": None,
            "reduce_only": False,
            "time_in_force": "GTC",
            "submitted_at": "2026-08-11T00:00:06+00:00",
            "expires_at": None,
            "cost_model_id": "paper-cost-v1",
        }
        values.update(changes)
        return PaperCommandV1(**values)  # type: ignore[arg-type]

    def test_current_generation_and_exact_sealed_decision_are_verified(self) -> None:
        self.assertEqual(1, self.authority.current_generation("btc-trader"))
        self.assertTrue(self.authority.verifies_decision(self._command()))

    def test_command_cannot_borrow_a_matching_digest_from_another_cycle(self) -> None:
        multi_cycle_authority = SealedCyclePaperDecisionAuthority(
            sessions=self.sessions,
            cycle_repository=self.cycles,
            agent_cycle_bindings={
                "btc-trader": (self.cycle_id, "another-cycle"),
            },
        )

        self.assertFalse(
            multi_cycle_authority.verifies_decision(
                self._command(decision_cycle_id="another-cycle")
            )
        )

    def test_constant_unbound_and_stale_generation_decisions_fail_closed(self) -> None:
        self.assertFalse(
            self.authority.verifies_decision(
                self._command(decision_sha256="0" * 64)
            )
        )
        unbound = SealedCyclePaperDecisionAuthority(
            sessions=self.sessions,
            cycle_repository=self.cycles,
            agent_cycle_bindings={"btc-trader": ("another-cycle",)},
        )
        self.assertFalse(unbound.verifies_decision(self._command()))

        self.sessions.recover_generation(
            "btc-trader",
            failed_generation=1,
            new_physical_task_id="btc-task-generation-2",
            new_continuity_nonce="btc-trader-generation-2",
            resume_capsule_ref="btc-resume-capsule-generation-2",
            recovered_at="2026-08-11T00:00:05+00:00",
        )
        self.assertEqual(2, self.authority.current_generation("btc-trader"))
        self.assertFalse(self.authority.verifies_decision(self._command()))


class V332PaperMarketEvidenceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.raw_store = FileRawCaptureStore(Path(self.temporary.name) / "runtime")

    def _evidence(self, *cycle_ids: str) -> AdmittedAssetSlicePaperMarketEvidence:
        return AdmittedAssetSlicePaperMarketEvidence(
            profiles=build_hype_data_profile_service(raw_store=self.raw_store),
            bindings=(
                PaperAssetEvidenceBinding(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                    cycle_ids=tuple(cycle_ids),
                ),
            ),
        )

    def _seal_funding_history(
        self,
        *,
        cycle_id: str,
        effective_offset: int = 7,
        include_prior_record: bool = False,
    ) -> None:
        current_effective = _BASE + timedelta(seconds=effective_offset)
        rows = [
            {
                "instType": "SWAP",
                "instId": HYPE_OKX_INSTRUMENT_ID,
                "fundingRate": "0.0001",
                "fundingTime": _ms(current_effective),
                "realizedRate": "0.0001",
            }
        ]
        if include_prior_record:
            rows.append(
                {
                    "instType": "SWAP",
                    "instId": HYPE_OKX_INSTRUMENT_ID,
                    "fundingRate": "0.0002",
                    "fundingTime": _ms(current_effective - timedelta(hours=8)),
                    "realizedRate": "0.0002",
                }
            )
        _seal(
            self.raw_store,
            cycle_id=cycle_id,
            capture_id="funding-rate-history",
            component_id="FUNDING_RATE_HISTORY",
            path=FUNDING_RATE_HISTORY_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "limit": "10"},
            body=_json(
                {
                    "code": "0",
                    "msg": "",
                    "data": rows,
                }
            ),
            start_offset=12,
        )

    def _observed_funding_accrual(self, *, cycle_id: str) -> CarryAccrualV1:
        replay = build_hype_data_profile_service(
            raw_store=self.raw_store
        ).replay(HYPE_OKX_DATA_PROFILE.profile_id, cycle_id=cycle_id)
        self.assertEqual("ADMITTED", replay.status)
        assert replay.data_slice is not None
        funding = replay.data_slice.optional_observations[
            "okx_funding_rate_history"
        ]
        mark = replay.data_slice.core_observations["mark_price"]
        record = funding["value"][0]
        return CarryAccrualV1(
            accrual_id=f"{cycle_id}-funding",
            account_id="paper-hype-account",
            symbol=HYPE_OKX_INSTRUMENT_ID,
            kind="FUNDING",
            status="OBSERVED",
            amount="0.0043125",
            rate=record.get("realized_rate", record["funding_rate"]),
            reference_price=mark["value"],
            position_quantity="1",
            effective_at=record["provider_as_of"],
            available_at=max(
                (funding["available_at"], mark["available_at"], replay.data_slice.sealed_at),
                key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
            ),
            rate_source_sha256=funding["raw_sha256"],
            price_source_sha256=mark["raw_sha256"],
            reason="Raw-observed realized funding with a timestamp-matched mark.",
            coverage_status="PARTIAL",
            coverage_start_at=record["provider_as_of"],
            coverage_end_at=record["provider_as_of"],
        )

    def test_exact_order_book_slice_is_derived_and_fabricated_quote_is_rejected(self) -> None:
        cycle_id = "hype-paper-book-001"
        _seal_core(self.raw_store, cycle_id=cycle_id)
        _seal(
            self.raw_store,
            cycle_id=cycle_id,
            capture_id="order-book",
            component_id="ORDER_BOOK",
            path=ORDER_BOOK_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "sz": "20"},
            body=_json(
                {
                    "code": "0",
                    "msg": "",
                    "data": [
                        {
                            "asks": [["43.200", "5", "0", "3"]],
                            "bids": [["43.100", "7", "0", "2"]],
                            "ts": _ms(_BASE + timedelta(seconds=13)),
                        }
                    ],
                }
            ),
            start_offset=12,
        )
        evidence = self._evidence(cycle_id)

        quote = evidence.latest_order_book_slice(HYPE_OKX_INSTRUMENT_ID)

        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual("43.1", quote.bid)
        self.assertEqual("43.2", quote.ask)
        self.assertEqual("5", quote.available_quantity)
        self.assertEqual("UNORDERED", quote.path_status)
        self.assertTrue(evidence.verifies_market_slice(quote))
        self.assertFalse(
            evidence.verifies_market_slice(replace(quote, ask="43.3"))
        )
        self.assertFalse(
            evidence.verifies_market_slice(replace(quote, source_sha256="0" * 64))
        )

    def test_core_only_slice_yields_non_executable_bar_not_a_fabricated_quote(self) -> None:
        cycle_id = "hype-paper-core-001"
        _seal_core(self.raw_store, cycle_id=cycle_id)
        evidence = self._evidence(cycle_id)

        derived = evidence.derive_slices(HYPE_OKX_INSTRUMENT_ID)
        replay = build_hype_data_profile_service(
            raw_store=self.raw_store
        ).replay(HYPE_OKX_DATA_PROFILE.profile_id, cycle_id=cycle_id)
        assert replay.data_slice is not None

        self.assertEqual(derived, derive_paper_market_slices(replay.data_slice))
        self.assertEqual({"MARK", "BAR"}, {item.granularity for item in derived})
        by_granularity = {item.granularity: item for item in derived}
        mark = by_granularity["MARK"]
        bar = by_granularity["BAR"]
        self.assertEqual("43.125", mark.mark)
        self.assertEqual("ORDERED", mark.path_status)
        self.assertEqual(
            replay.data_slice.core_observations["mark_price"]["raw_sha256"],
            mark.source_sha256,
        )
        self.assertEqual("UNORDERED", bar.path_status)
        self.assertTrue(evidence.verifies_market_slice(mark))
        self.assertTrue(evidence.verifies_market_slice(bar))
        self.assertFalse(evidence.verifies_market_slice(replace(mark, mark="43.126")))
        self.assertIsNone(evidence.latest_order_book_slice(HYPE_OKX_INSTRUMENT_ID))
        self.assertFalse(
            evidence.verifies_market_slice(
                PaperMarketSliceV1(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    observed_at=bar.observed_at,
                    available_at=bar.available_at,
                    source_sha256=bar.source_sha256,
                    granularity="QUOTE",
                    path_status="UNORDERED",
                    bid="43.1",
                    ask="43.2",
                    available_quantity="5",
                )
            )
        )

    def test_instrument_spec_is_raw_bound_and_forged_multiplier_is_rejected(self) -> None:
        cycle_id = "hype-paper-instrument-001"
        _seal_core(self.raw_store, cycle_id=cycle_id)
        evidence = self._evidence(cycle_id)
        before_instrument_available = (
            _BASE + timedelta(seconds=4)
        ).isoformat()
        instrument_available = (_BASE + timedelta(seconds=5)).isoformat()
        replay = build_hype_data_profile_service(
            raw_store=self.raw_store
        ).replay(HYPE_OKX_DATA_PROFILE.profile_id, cycle_id=cycle_id)
        assert replay.data_slice is not None
        slice_sealed_at = replay.data_slice.sealed_at

        self.assertIsNone(
            evidence.latest_instrument_spec(
                HYPE_OKX_INSTRUMENT_ID,
                "LINEAR_PERP",
                available_by=before_instrument_available,
            )
        )
        self.assertIsNone(
            evidence.latest_instrument_spec(
                HYPE_OKX_INSTRUMENT_ID,
                "LINEAR_PERP",
                available_by=instrument_available,
            )
        )
        instrument_spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=slice_sealed_at,
        )

        self.assertIsNotNone(instrument_spec)
        assert instrument_spec is not None
        self.assertEqual("0.1", instrument_spec.contract_multiplier)
        self.assertEqual("CONTRACTS", instrument_spec.quantity_basis)
        self.assertEqual("OBSERVED_RAW_BOUND", instrument_spec.parameter_status)
        self.assertEqual(
            replay.data_slice.core_observations["instrument"]["raw_sha256"],
            instrument_spec.parameter_source_sha256,
        )
        self.assertFalse(
            evidence.verifies_instrument_spec(
                instrument_spec,
                available_by=instrument_available,
            )
        )
        self.assertTrue(
            evidence.verifies_instrument_spec(
                instrument_spec,
                available_by=slice_sealed_at,
            )
        )
        self.assertTrue(
            evidence.verifies_instrument_spec(
                replace(
                    instrument_spec,
                    maintenance_margin_rate="0.05",
                    maintenance_margin_deduction="0",
                    liquidation_fee_reserve="1",
                    risk_parameter_status="MODELED_EXPLICIT_PARAMETERS",
                    risk_parameter_set_id="paper-risk-parameters-v1",
                ),
                available_by=slice_sealed_at,
            )
        )
        self.assertFalse(
            evidence.verifies_instrument_spec(
                replace(instrument_spec, contract_multiplier="2"),
                available_by=slice_sealed_at,
            )
        )
        self.assertFalse(
            evidence.verifies_instrument_spec(
                replace(instrument_spec, parameter_source_sha256="0" * 64),
                available_by=slice_sealed_at,
            )
        )
        with self.assertRaisesRegex(
            PaperMarketEvidenceConfigurationError,
            "PAPER_INSTRUMENT_ACCOUNT_MODE_UNSUPPORTED",
        ):
            evidence.latest_instrument_spec(HYPE_OKX_INSTRUMENT_ID, "CASH_SPOT")

    def test_instrument_missing_contract_value_fails_before_spec_derivation(self) -> None:
        cycle_id = "hype-paper-instrument-missing-value-001"
        _seal_core(
            self.raw_store,
            cycle_id=cycle_id,
            instrument_body=_json(
                {
                    "code": "0",
                    "msg": "",
                    "data": [
                        {
                            "instType": "SWAP",
                            "instId": HYPE_OKX_INSTRUMENT_ID,
                            "state": "live",
                            "ctType": "linear",
                            "ctValCcy": "HYPE",
                            "settleCcy": "USDT",
                            "ctMult": "1",
                            "lotSz": "1",
                            "minSz": "1",
                            "tickSz": "0.001",
                        }
                    ],
                }
            ),
        )
        evidence = self._evidence(cycle_id)

        with self.assertRaisesRegex(
            OkxSnapshotError,
            "OKX_INSTRUMENT_SCHEMA_INVALID",
        ):
            evidence.latest_instrument_spec(
                HYPE_OKX_INSTRUMENT_ID,
                "LINEAR_PERP",
            )

    def test_observed_funding_requires_exact_same_cycle_rate_and_mark_evidence(self) -> None:
        cycle_id = "hype-paper-funding-001"
        _seal_core(self.raw_store, cycle_id=cycle_id)
        self._seal_funding_history(cycle_id=cycle_id)
        evidence = self._evidence(cycle_id)
        accrual = self._observed_funding_accrual(cycle_id=cycle_id)

        self.assertTrue(evidence.verifies_carry_accrual(accrual))
        self.assertFalse(
            evidence.verifies_carry_accrual(
                replace(accrual, available_at="2026-08-13T12:00:13+00:00")
            )
        )
        self.assertFalse(
            evidence.verifies_carry_accrual(
                replace(accrual, coverage_status="COMPLETE")
            )
        )
        self.assertFalse(
            evidence.verifies_carry_accrual(replace(accrual, rate="0.0002"))
        )
        self.assertFalse(
            evidence.verifies_carry_accrual(
                replace(accrual, reference_price="43.126")
            )
        )
        self.assertFalse(
            evidence.verifies_carry_accrual(
                replace(accrual, rate_source_sha256="0" * 64)
            )
        )
        self.assertFalse(
            evidence.verifies_carry_accrual(
                replace(accrual, price_source_sha256="0" * 64)
            )
        )

    def test_funding_history_without_timestamp_matched_mark_fails_closed(self) -> None:
        cycle_id = "hype-paper-funding-time-mismatch-001"
        _seal_core(self.raw_store, cycle_id=cycle_id)
        self._seal_funding_history(cycle_id=cycle_id, effective_offset=6)
        evidence = self._evidence(cycle_id)
        accrual = self._observed_funding_accrual(cycle_id=cycle_id)

        self.assertFalse(evidence.verifies_carry_accrual(accrual))

    def test_one_matched_funding_row_cannot_claim_complete_multirow_window(self) -> None:
        cycle_id = "hype-paper-funding-incomplete-window-001"
        _seal_core(self.raw_store, cycle_id=cycle_id)
        self._seal_funding_history(
            cycle_id=cycle_id,
            include_prior_record=True,
        )
        evidence = self._evidence(cycle_id)
        point = self._observed_funding_accrual(cycle_id=cycle_id)

        self.assertTrue(evidence.verifies_carry_accrual(point))
        self.assertFalse(
            evidence.verifies_carry_accrual(
                replace(
                    point,
                    coverage_status="COMPLETE",
                    coverage_start_at="2026-08-13T04:00:07+00:00",
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
