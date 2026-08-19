from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.market_cycle.paper import (
    PaperTradingError,
    PaperTradingService,
    replay_paper_account,
)
from trade_system.theory_paper_v2.application.market_cycle.paper_valuation import (
    project_paper_valuation,
)
from trade_system.theory_paper_v2.application.market_cycle.read_models import (
    project_paper_cost_effect,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    CarryAccrualV1,
    FundingCoverageAdvanceV1,
    FundingSettlementModelV1,
    PaperCostModelV1,
    PaperMarketSliceV1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.funding_scheduler import (
    AdmittedSliceFundingScheduler,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_ledger import (
    FilePaperLedger,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_DATA_PROFILE,
    HYPE_OKX_INSTRUMENT_ID,
    build_hype_data_profile_service,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_transport import (
    FUNDING_RATE_HISTORY_PATH,
)
from trade_system.theory_paper_v2.infrastructure.market_data.paper_evidence import (
    AdmittedAssetSlicePaperMarketEvidence,
    PaperAssetEvidenceBinding,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)

from tests.test_theory_paper_v2_v332_hype_data import (
    _BASE,
    _json,
    _ms,
    _seal,
    _seal_core,
    _time,
)


class _RawInstrumentEvidence:
    def verifies_instrument_spec(self, spec, *, available_by):  # noqa: ANN001, ANN201
        del available_by
        return spec.parameter_status == "OBSERVED_RAW_BOUND"

    def verifies_market_slice(self, market):  # noqa: ANN001, ANN201
        del market
        return False


class _FailOnceFundingBatchLedger:
    """Inject one pre-commit failure while preserving the real ledger owner."""

    def __init__(self, delegate: FilePaperLedger) -> None:
        self.delegate = delegate
        self.failed = False
        self.batch_sizes: list[int] = []

    def load_records(self, account_id):  # noqa: ANN001, ANN201
        return self.delegate.load_records(account_id)

    def append_many(  # noqa: ANN201
        self,
        *,
        account_id,
        expected_revision,
        events,
    ):
        frozen = tuple(events)
        self.batch_sizes.append(len(frozen))
        if not self.failed and len(frozen) > 1:
            self.failed = True
            raise RuntimeError("INJECTED_BEFORE_ATOMIC_FUNDING_APPEND")
        return self.delegate.append_many(
            account_id=account_id,
            expected_revision=expected_revision,
            events=frozen,
        )


class _PermissiveCarryEvidence:
    def verifies_carry_accrual(self, accrual):  # noqa: ANN001, ANN201
        del accrual
        return True

    def verifies_funding_coverage(self, advance):  # noqa: ANN001, ANN201
        del advance
        return True


class V332FundingSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.root = root
        self.raw = FileRawCaptureStore(root / "raw")
        self.ledger = FilePaperLedger(root / "paper")
        self.model = PaperCostModelV1(
            model_id="cost-v1",
            maker_fee_bps="1",
            taker_fee_bps="2",
            market_impact_bps="1",
            funding_status="UNKNOWN",
            borrow_status="UNKNOWN",
        )

    def _slice(self, cycle_id: str, *, offsets: tuple[int, ...]):
        _seal_core(self.raw, cycle_id=cycle_id)
        rows = [
            {
                "instType": "SWAP",
                "instId": HYPE_OKX_INSTRUMENT_ID,
                "fundingRate": "0.0001",
                "fundingTime": _ms(_BASE + timedelta(hours=offset)),
                "realizedRate": "0.0001",
            }
            for offset in offsets
        ]
        _seal(
            self.raw,
            cycle_id=cycle_id,
            capture_id="funding-rate-history",
            component_id="FUNDING_RATE_HISTORY",
            path=FUNDING_RATE_HISTORY_PATH,
            query={"instId": HYPE_OKX_INSTRUMENT_ID, "limit": "10"},
            body=_json({"code": "0", "msg": "", "data": rows}),
            start_offset=12,
        )
        replay = build_hype_data_profile_service(raw_store=self.raw).replay(
            HYPE_OKX_DATA_PROFILE.profile_id,
            cycle_id=cycle_id,
            cutoff_at=_time(14),
        )
        self.assertEqual("ADMITTED", replay.status)
        assert replay.data_slice is not None
        return replay.data_slice

    def _runtime(self, cycle_id: str, *, opened_at: str):
        profiles = build_hype_data_profile_service(raw_store=self.raw)
        evidence = AdmittedAssetSlicePaperMarketEvidence(
            profiles=profiles,
            bindings=(
                PaperAssetEvidenceBinding(
                    symbol=HYPE_OKX_INSTRUMENT_ID,
                    profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                    cycle_ids=(cycle_id,),
                ),
            ),
        )
        service = PaperTradingService(
            self.ledger,
            cost_models=(self.model,),
            market_evidence=_RawInstrumentEvidence(),
            carry_evidence=evidence,
        )
        spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=_time(14),
        )
        assert spec is not None
        service.open_account(
            account_id="hype-paper",
            account_mode="LINEAR_PERP",
            owner_logical_agent_id="hype-trader",
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage="5",
            initial_balance="10000",
            opened_at=opened_at,
            instrument_spec=spec,
        )
        model = FundingSettlementModelV1(
            model_id="funding-settlement-v1",
            model_version="v1",
            price_proxy_method="LAST_CONFIRMED_15M_CLOSE_NOT_AFTER_EFFECTIVE_AT",
            cost_model_id=self.model.model_id,
            cost_model_digest=self.model.model_digest,
            effective_from=(
                datetime.fromisoformat(opened_at) - timedelta(hours=1)
            ).isoformat(),
            effective_to=(_BASE + timedelta(hours=1)).isoformat(),
        )
        return service, evidence, model

    def test_complete_requires_bracketing_history_and_is_replay_idempotent(self) -> None:
        cycle_id = "funding-complete"
        data_slice = self._slice(cycle_id, offsets=(-4, -2, 0))
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        service, _evidence, model = self._runtime(
            cycle_id, opened_at=opened_at
        )
        scheduler = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=service
        )
        end_at = (_BASE - timedelta(hours=1)).isoformat()

        first = scheduler.run(
            account_id="hype-paper",
            coverage_end_at=end_at,
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("COMPLETE", first.status)
        state = service.load_account("hype-paper")
        self.assertEqual("COMPLETE", state.funding_coverage_status)
        self.assertEqual("NOT_APPLICABLE", state.borrow_coverage_status)
        self.assertEqual("COMPLETE", state.carry_coverage_status)
        self.assertEqual("0", state.funding_paid)  # flat at effective_at
        mark = PaperMarketSliceV1(
            symbol=HYPE_OKX_INSTRUMENT_ID,
            observed_at=end_at,
            available_at=end_at,
            source_sha256="f" * 64,
            granularity="MARK",
            path_status="ORDERED",
            mark="43.125",
        )
        history = tuple(
            replay_paper_account(
                self.ledger.load_records("hype-paper")[:revision]
            )
            for revision in range(1, state.version + 1)
        )
        valuation = project_paper_valuation(
            state, (mark,), account_history=history
        )
        self.assertEqual("10000", valuation.complete_equity)
        self.assertEqual(
            "COMPLETE_AT_MARK", valuation.carry_coverage_at_mark_status
        )
        cost = project_paper_cost_effect(
            state, self.ledger.load_records("hype-paper")
        )
        self.assertEqual("0", cost.complete_cash_cost)
        self.assertEqual(
            "COMPLETE_RECORDED_CASH_COSTS", cost.coverage_status
        )
        version = state.version

        replay = scheduler.run(
            account_id="hype-paper",
            coverage_end_at=end_at,
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("COMPLETE", replay.status)
        self.assertEqual(version, replay.account_version)
        self.assertEqual(version, service.load_account("hype-paper").version)

    def test_three_incremental_windows_use_durable_cursor_and_new_sources(
        self,
    ) -> None:
        opened_at = (_BASE - timedelta(hours=5)).isoformat()
        cases = (
            (
                "funding-incremental-1",
                (-6, -4, -3),
                (_BASE - timedelta(hours=3, minutes=30)).isoformat(),
            ),
            (
                "funding-incremental-2",
                (-6, -4, -3, -2),
                (_BASE - timedelta(hours=2, minutes=30)).isoformat(),
            ),
            (
                "funding-incremental-3",
                (-6, -4, -3, -2, -1),
                (_BASE - timedelta(hours=1, minutes=30)).isoformat(),
            ),
        )
        slices = tuple(
            self._slice(cycle_id, offsets=offsets)
            for cycle_id, offsets, _end in cases
        )
        service, _evidence, model = self._runtime(
            cases[0][0], opened_at=opened_at
        )
        results = []
        for index, ((cycle_id, _offsets, end_at), data_slice) in enumerate(
            zip(cases, slices, strict=True)
        ):
            if index:
                profiles = build_hype_data_profile_service(raw_store=self.raw)
                evidence = AdmittedAssetSlicePaperMarketEvidence(
                    profiles=profiles,
                    bindings=(
                        PaperAssetEvidenceBinding(
                            symbol=HYPE_OKX_INSTRUMENT_ID,
                            profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                            cycle_ids=(cycle_id,),
                        ),
                    ),
                )
                service = PaperTradingService(
                    self.ledger,
                    cost_models=(self.model,),
                    market_evidence=_RawInstrumentEvidence(),
                    carry_evidence=evidence,
                )
            results.append(
                AdmittedSliceFundingScheduler(
                    ledger=self.ledger, service=service
                ).run(
                    account_id="hype-paper",
                    coverage_end_at=end_at,
                    data_slice=data_slice,
                    settlement_model=model,
                )
            )

        self.assertEqual(["COMPLETE"] * 3, [item.status for item in results])
        records = self.ledger.load_records("hype-paper")
        advances = [
            FundingCoverageAdvanceV1(**dict(record.payload["advance"]))
            for record in records
            if record.event_type == "FUNDING_COVERAGE_ADVANCED"
        ]
        accruals = [
            CarryAccrualV1(**dict(record.payload["accrual"]))
            for record in records
            if record.event_type == "CARRY_ACCRUED"
        ]
        self.assertEqual(3, len(advances))
        self.assertEqual(3, len(accruals))
        self.assertEqual(
            [opened_at, cases[0][2], cases[1][2]],
            [item.coverage_start_at for item in advances],
        )
        self.assertEqual(
            [cases[0][2], cases[1][2], cases[2][2]],
            [item.coverage_end_at for item in advances],
        )
        self.assertEqual(
            3, len({item.funding_history_source_sha256 for item in advances})
        )
        self.assertEqual(
            [
                (_BASE - timedelta(hours=4)).isoformat().replace("+00:00", "Z"),
                (_BASE - timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
                (_BASE - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            ],
            [item.effective_at for item in accruals],
        )
        state = service.load_account("hype-paper")
        self.assertEqual("COMPLETE", state.funding_coverage_status)
        self.assertEqual(opened_at, state.funding_coverage_start_at)
        self.assertEqual(cases[2][2], state.funding_coverage_end_at)

    def test_history_truncation_or_missing_after_boundary_stays_partial(self) -> None:
        cycle_id = "funding-truncated"
        data_slice = self._slice(cycle_id, offsets=(-4, -2))
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        service, _evidence, model = self._runtime(
            cycle_id, opened_at=opened_at
        )
        scheduler = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=service
        )
        result = scheduler.run(
            account_id="hype-paper",
            coverage_end_at=(_BASE - timedelta(hours=1)).isoformat(),
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("PARTIAL", result.status)
        state = service.load_account("hype-paper")
        self.assertEqual("UNKNOWN", state.funding_coverage_status)
        self.assertEqual("0", state.funding_paid)

    def test_zero_event_window_needs_both_history_boundaries(self) -> None:
        cycle_id = "funding-zero-event"
        data_slice = self._slice(cycle_id, offsets=(-4, 0))
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        service, _evidence, model = self._runtime(
            cycle_id, opened_at=opened_at
        )
        result = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=service
        ).run(
            account_id="hype-paper",
            coverage_end_at=(_BASE - timedelta(hours=1)).isoformat(),
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("COMPLETE", result.status)
        self.assertEqual(0, result.observed_event_count)
        self.assertEqual(
            "COMPLETE",
            service.load_account("hype-paper").funding_coverage_status,
        )

    def test_after_window_raw_not_yet_available_stays_partial(self) -> None:
        cycle_id = "funding-pit"
        data_slice = self._slice(cycle_id, offsets=(-4, -2, 0))
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        service, _evidence, model = self._runtime(
            cycle_id, opened_at=opened_at
        )
        result = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=service
        ).run(
            account_id="hype-paper",
            coverage_end_at=(_BASE + timedelta(minutes=1)).isoformat(),
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("PARTIAL", result.status)
        self.assertEqual("UNKNOWN", service.load_account("hype-paper").funding_coverage_status)

    def test_duplicate_official_settlement_time_is_not_admitted(self) -> None:
        cycle_id = "funding-duplicate"
        data_slice = self._slice(cycle_id, offsets=(-4, -2, -2, 0))
        self.assertNotIn(
            "okx_funding_rate_history", data_slice.optional_observations
        )
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        service, _evidence, model = self._runtime(
            cycle_id, opened_at=opened_at
        )
        result = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=service
        ).run(
            account_id="hype-paper",
            coverage_end_at=(_BASE - timedelta(hours=1)).isoformat(),
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("UNKNOWN", result.status)
        self.assertEqual("0", service.load_account("hype-paper").funding_paid)

    def test_missing_pre_event_closed_bar_keeps_window_partial(self) -> None:
        cycle_id = "funding-price-proxy-missing"
        data_slice = self._slice(cycle_id, offsets=(-32, -26, 0))
        opened_at = (_BASE - timedelta(hours=30)).isoformat()
        service, _evidence, model = self._runtime(
            cycle_id, opened_at=opened_at
        )
        result = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=service
        ).run(
            account_id="hype-paper",
            coverage_end_at=(_BASE - timedelta(hours=25)).isoformat(),
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("PARTIAL", result.status)
        self.assertEqual(
            "PRICE_PROXY_MISSING_FOR_SETTLEMENT_EVENT", result.reason
        )
        self.assertEqual("0", service.load_account("hype-paper").funding_paid)

    def test_coverage_advance_rejects_one_missing_ledger_settlement(self) -> None:
        cycle_id = "funding-ledger-missing-one"
        data_slice = self._slice(cycle_id, offsets=(-4, -2, -1, 0))
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        donor, evidence, model = self._runtime(cycle_id, opened_at=opened_at)
        result = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=donor
        ).run(
            account_id="hype-paper",
            coverage_end_at=(_BASE - timedelta(minutes=30)).isoformat(),
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("COMPLETE", result.status)
        donor_records = self.ledger.load_records("hype-paper")
        accruals = [
            CarryAccrualV1(**dict(record.payload["accrual"]))
            for record in donor_records
            if record.event_type == "CARRY_ACCRUED"
        ]
        advance = next(
            FundingCoverageAdvanceV1(**dict(record.payload["advance"]))
            for record in donor_records
            if record.event_type == "FUNDING_COVERAGE_ADVANCED"
        )
        self.assertEqual(2, len(accruals))

        missing_ledger = FilePaperLedger(self.root / "missing-ledger")
        incomplete = PaperTradingService(
            missing_ledger,
            cost_models=(self.model,),
            market_evidence=_RawInstrumentEvidence(),
            carry_evidence=evidence,
        )
        spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=_time(14),
        )
        assert spec is not None
        state = incomplete.open_account(
            account_id="hype-paper",
            account_mode="LINEAR_PERP",
            owner_logical_agent_id="hype-trader",
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage="5",
            initial_balance="10000",
            opened_at=opened_at,
            instrument_spec=spec,
        )
        state = incomplete.accrue_carry(
            account_id="hype-paper",
            expected_account_version=state.version,
            accrual=accruals[0],
        )
        with self.assertRaisesRegex(
            PaperTradingError, "FUNDING_COVERAGE_LEDGER_BINDING_MISMATCH"
        ):
            incomplete.advance_funding_coverage(
                account_id="hype-paper",
                expected_account_version=state.version,
                advance=advance,
            )
        self.assertEqual(
            "PARTIAL", incomplete.load_account("hype-paper").funding_coverage_status
        )

    def test_failed_atomic_batch_leaves_no_partial_window_and_recovers(self) -> None:
        cycle_id = "funding-atomic-recovery"
        data_slice = self._slice(cycle_id, offsets=(-4, -2, -1, 0))
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        _service, evidence, model = self._runtime(
            cycle_id, opened_at=opened_at
        )
        failing_ledger = _FailOnceFundingBatchLedger(self.ledger)
        failing_service = PaperTradingService(
            failing_ledger,
            cost_models=(self.model,),
            market_evidence=_RawInstrumentEvidence(),
            carry_evidence=evidence,
        )
        scheduler = AdmittedSliceFundingScheduler(
            ledger=failing_ledger,
            service=failing_service,
        )
        end_at = (_BASE - timedelta(minutes=30)).isoformat()

        with self.assertRaisesRegex(
            RuntimeError, "INJECTED_BEFORE_ATOMIC_FUNDING_APPEND"
        ):
            scheduler.run(
                account_id="hype-paper",
                coverage_end_at=end_at,
                data_slice=data_slice,
                settlement_model=model,
            )
        after_failure = self.ledger.load_records("hype-paper")
        self.assertEqual((3,), tuple(failing_ledger.batch_sizes))
        self.assertEqual(1, len(after_failure))
        self.assertFalse(
            any(
                record.event_type
                in {"CARRY_ACCRUED", "FUNDING_COVERAGE_ADVANCED"}
                for record in after_failure
            )
        )

        # A later valid paper fact changes last_fact_at.  Because no half-window
        # escaped, a retry may freeze the later receipt time without conflicting
        # with an earlier accrual.
        self.ledger.append_many(
            account_id="hype-paper",
            expected_revision=1,
            events=(
                {
                    "event_id": "later-paper-market-fact",
                    "event_type": "MARKET_OBSERVED",
                    "occurred_at": _time(20),
                    "payload": {
                        "symbol": HYPE_OKX_INSTRUMENT_ID,
                        "observed_at": _time(19),
                        "available_at": _time(20),
                        "source_sha256": "a" * 64,
                    },
                },
            ),
        )
        recovered = scheduler.run(
            account_id="hype-paper",
            coverage_end_at=end_at,
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("COMPLETE", recovered.status)
        records = self.ledger.load_records("hype-paper")
        self.assertEqual(
            2,
            sum(record.event_type == "CARRY_ACCRUED" for record in records),
        )
        self.assertEqual(
            1,
            sum(
                record.event_type == "FUNDING_COVERAGE_ADVANCED"
                for record in records
            ),
        )
        self.assertEqual((3, 3), tuple(failing_ledger.batch_sizes))
        version = recovered.account_version
        duplicate = scheduler.run(
            account_id="hype-paper",
            coverage_end_at=end_at,
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("COMPLETE", duplicate.status)
        self.assertEqual(version, duplicate.account_version)
        self.assertEqual((3, 3), tuple(failing_ledger.batch_sizes))

    def test_invalid_later_accrual_is_rejected_before_any_window_write(self) -> None:
        cycle_id = "funding-atomic-prevalidation"
        data_slice = self._slice(cycle_id, offsets=(-4, -2, -1, 0))
        opened_at = (_BASE - timedelta(hours=3)).isoformat()
        donor, evidence, model = self._runtime(cycle_id, opened_at=opened_at)
        complete = AdmittedSliceFundingScheduler(
            ledger=self.ledger, service=donor
        ).run(
            account_id="hype-paper",
            coverage_end_at=(_BASE - timedelta(minutes=30)).isoformat(),
            data_slice=data_slice,
            settlement_model=model,
        )
        self.assertEqual("COMPLETE", complete.status)
        donor_records = self.ledger.load_records("hype-paper")
        accruals = tuple(
            CarryAccrualV1(**dict(record.payload["accrual"]))
            for record in donor_records
            if record.event_type == "CARRY_ACCRUED"
        )
        advance = next(
            FundingCoverageAdvanceV1(**dict(record.payload["advance"]))
            for record in donor_records
            if record.event_type == "FUNDING_COVERAGE_ADVANCED"
        )
        invalid_later = CarryAccrualV1(
            **{**accruals[1].to_dict(), "amount": "1"}
        )
        supplied = (accruals[0], invalid_later)
        invalid_advance = FundingCoverageAdvanceV1(
            **{
                **advance.to_dict(),
                "event_accrual_sha256s": [
                    canonical_digest(item.to_dict()) for item in supplied
                ],
            }
        )

        isolated_ledger = FilePaperLedger(self.root / "invalid-window-ledger")
        service = PaperTradingService(
            isolated_ledger,
            cost_models=(self.model,),
            market_evidence=_RawInstrumentEvidence(),
            carry_evidence=_PermissiveCarryEvidence(),
        )
        spec = evidence.latest_instrument_spec(
            HYPE_OKX_INSTRUMENT_ID,
            "LINEAR_PERP",
            available_by=_time(14),
        )
        assert spec is not None
        state = service.open_account(
            account_id="hype-paper",
            account_mode="LINEAR_PERP",
            owner_logical_agent_id="hype-trader",
            base_currency="USDT",
            permitted_symbol=HYPE_OKX_INSTRUMENT_ID,
            max_leverage="5",
            initial_balance="10000",
            opened_at=opened_at,
            instrument_spec=spec,
        )
        with self.assertRaisesRegex(
            PaperTradingError, "PAPER_FUNDING_AMOUNT_MISMATCH"
        ):
            service.settle_funding_window(
                account_id="hype-paper",
                expected_account_version=state.version,
                accruals=supplied,
                advance=invalid_advance,
            )
        records = isolated_ledger.load_records("hype-paper")
        self.assertEqual(1, len(records))
        self.assertFalse(
            any(
                record.event_type
                in {"CARRY_ACCRUED", "FUNDING_COVERAGE_ADVANCED"}
                for record in records
            )
        )


if __name__ == "__main__":
    unittest.main()
