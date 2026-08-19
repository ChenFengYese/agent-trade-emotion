from __future__ import annotations

from pathlib import Path
import contextlib
import io
import json
import tempfile
import unittest

from tests.test_theory_paper_v2_v332_hype_data import _seal_core
from trade_system.theory_paper_v2.application.market_cycle.agent_session import (
    AgentSessionService,
)
from trade_system.theory_paper_v2.application.market_cycle.attention import (
    AttentionService,
)
from trade_system.theory_paper_v2.application.market_cycle.paper import (
    PaperTradingService,
)
from trade_system.theory_paper_v2.domain.market_cycle.attention import (
    AgentRegistry,
    AttentionRequest,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    InstrumentSpecV1,
    PaperCommandV1,
    PaperCostModelV1,
    PaperMarketSliceV1,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.attention_repository import (
    FileAttentionRepository,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_ledger import (
    FilePaperLedger,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.projections import (
    WorkbenchProjectionService,
)
from trade_system.theory_paper_v2.infrastructure.market_data.raw_capture import (
    FileRawCaptureStore,
)
from trade_system.theory_paper_v2.infrastructure.market_data.okx_profiles import (
    HYPE_OKX_DATA_PROFILE,
    build_hype_data_profile_service,
)
from trade_system.theory_paper_v2.infrastructure.market_data.paper_evidence import (
    AdmittedAssetSlicePaperMarketEvidence,
    PaperAssetEvidenceBinding,
)
from trade_system.theory_paper_v2.presentation.market_workbench import main


class _DecisionAuthority:
    def current_generation(self, logical_agent_id: str) -> int | None:
        return 1

    def verifies_decision(self, command: PaperCommandV1) -> bool:
        return command.decision_sha256 == "1" * 64


class _MarketEvidence:
    def verifies_market_slice(self, market: PaperMarketSliceV1) -> bool:
        return True

    def verifies_instrument_spec(
        self,
        spec: InstrumentSpecV1,
        *,
        available_by: str,
    ) -> bool:
        return (
            spec.parameter_status == "OBSERVED_RAW_BOUND"
            and spec.parameter_source_sha256 == "0" * 64
        )


def _instrument_spec(
    instrument_spec_id: str = "hype-workbench-contract-v1",
) -> InstrumentSpecV1:
    return InstrumentSpecV1(
        instrument_spec_id=instrument_spec_id,
        symbol="HYPE-USDT-SWAP",
        account_mode="LINEAR_PERP",
        quote_currency="USDT",
        contract_multiplier="1",
        quantity_basis="CONTRACTS",
        parameter_status="OBSERVED_RAW_BOUND",
        parameter_source_sha256="0" * 64,
    )


class V332WorkbenchTests(unittest.TestCase):
    def test_six_view_snapshot_is_rebuildable_and_does_not_append_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attention = FileAttentionRepository(root / "attention")
            paper = FilePaperLedger(root / "paper")
            AgentSessionService(attention).register(
                AgentRegistry(
                    logical_agent_id="hype-trader",
                    symbol="HYPE-USDT-SWAP",
                    generation=1,
                    continuity_nonce="hype-context-1",
                    physical_task_id="task-hype-1",
                    status="ACTIVE",
                    registered_at="2026-08-12T12:00:00+00:00",
                )
            )
            AttentionService(attention).submit_request(
                AttentionRequest(
                    request_id="hype-next-check-1",
                    logical_agent_id="hype-trader",
                    agent_generation=1,
                    continuity_nonce="hype-context-1",
                    symbol="HYPE-USDT-SWAP",
                    mode="WAKE_AFTER",
                    issued_at="2026-08-12T12:01:00+00:00",
                    continue_until=None,
                    earliest_wake_at="2026-08-12T12:05:00+00:00",
                    latest_useful_at="2026-08-12T12:10:00+00:00",
                    reason_summary="Agent selected a short rest window.",
                    requested_focus="Re-evaluate the current hypothesis.",
                    hypothesis_or_episode_ref="hype-episode-1",
                    position_and_open_order_ref="hype-paper",
                    data_cursor="hype-workbench-cursor-1",
                )
            )
            PaperTradingService(
                paper,
                cost_models=(
                    PaperCostModelV1(
                        model_id="public-stress-v1",
                        maker_fee_bps="1",
                        taker_fee_bps="2",
                        market_impact_bps="1",
                    ),
                ),
                market_evidence=_MarketEvidence(),
            ).open_account(
                account_id="hype-paper",
                account_mode="LINEAR_PERP",
                owner_logical_agent_id="hype-trader",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="5",
                initial_balance="10000",
                opened_at="2026-08-12T12:00:00+00:00",
                instrument_spec=_instrument_spec(),
            )
            attention_before = attention.replay("hype-trader")
            paper_before = paper.load_records("hype-paper")

            projector = WorkbenchProjectionService(
                attention_repository=attention,
                paper_ledger=paper,
            )
            first = projector.build(
                logical_agent_ids=("hype-trader",),
                account_ids=("hype-paper",),
            ).to_dict()
            second = projector.build(
                logical_agent_ids=("hype-trader",),
                account_ids=("hype-paper",),
            ).to_dict()

            self.assertEqual(first, second)
            self.assertEqual(
                set(first),
                {
                    "schema_id",
                    "schema_version",
                    "data_coverage",
                    "agent_states",
                    "paper_accounts",
                    "orders_and_fills",
                    "timeline",
                    "portfolio",
                },
            )
            self.assertEqual(first["agent_states"][0]["generation"], 1)
            self.assertEqual(
                first["agent_states"][0]["active_request_id"],
                "hype-next-check-1",
            )
            self.assertEqual(first["agent_states"][0]["request_status"], "PENDING")
            self.assertEqual(first["paper_accounts"][0]["available_balance"], "10000")
            self.assertEqual(
                first["paper_accounts"][0]["valuation"]["status"],
                "UNKNOWN_NO_EXPLICIT_MARK",
            )
            self.assertEqual(
                first["paper_accounts"][0]["cost_effect"]["coverage_status"],
                "INCOMPLETE_UNKNOWN_CARRY_COSTS",
            )
            self.assertEqual(first["portfolio"]["shared_risk_status"], "UNKNOWN_NOT_MODELED")
            self.assertEqual(attention.replay("hype-trader"), attention_before)
            self.assertEqual(paper.load_records("hype-paper"), paper_before)

    def test_cli_rebuilds_data_coverage_from_primary_sealed_raw(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "runtime"
            runtime_root.mkdir()
            cycle_id = "hype-workbench-cycle"
            _seal_core(FileRawCaptureStore(runtime_root), cycle_id=cycle_id)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(
                    (
                        "--attention-root",
                        str(root / "attention"),
                        "--paper-root",
                        str(root / "paper"),
                        "--runtime-root",
                        str(runtime_root),
                        "--hype-cycle-id",
                        cycle_id,
                    )
                )
            document = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(len(document["data_coverage"]), 1)
            self.assertEqual(
                document["data_coverage"][0]["instrument_key"],
                "OKX:HYPE-USDT-SWAP:SWAP:linear",
            )
            self.assertEqual(document["paper_accounts"], [])

    def test_admitted_data_mark_enters_valuation_through_public_evidence_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "runtime"
            runtime_root.mkdir()
            cycle_id = "hype-workbench-valuation"
            raw_store = FileRawCaptureStore(runtime_root)
            _seal_core(raw_store, cycle_id=cycle_id)
            profile_service = build_hype_data_profile_service(raw_store=raw_store)
            replay = profile_service.replay(
                HYPE_OKX_DATA_PROFILE.profile_id,
                cycle_id=cycle_id,
            )
            self.assertEqual(replay.status, "ADMITTED")
            self.assertIsNotNone(replay.data_slice)
            assert replay.data_slice is not None
            evidence = AdmittedAssetSlicePaperMarketEvidence(
                profiles=profile_service,
                bindings=(
                    PaperAssetEvidenceBinding(
                        symbol="HYPE-USDT-SWAP",
                        profile_id=HYPE_OKX_DATA_PROFILE.profile_id,
                        cycle_ids=(cycle_id,),
                    ),
                ),
            )
            paper = FilePaperLedger(root / "paper")
            PaperTradingService(
                paper,
                cost_models=(
                    PaperCostModelV1(
                        model_id="workbench-cost-v1",
                        maker_fee_bps="1",
                        taker_fee_bps="2",
                        market_impact_bps="1",
                    ),
                ),
                market_evidence=evidence,
            ).open_account(
                account_id="hype-paper",
                account_mode="LINEAR_PERP",
                owner_logical_agent_id="hype-trader",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="5",
                initial_balance="10000",
                opened_at=replay.data_slice.sealed_at,
                instrument_spec=evidence.latest_instrument_spec(
                    "HYPE-USDT-SWAP",
                    "LINEAR_PERP",
                    available_by=replay.data_slice.sealed_at,
                ),
            )

            document = WorkbenchProjectionService(
                attention_repository=FileAttentionRepository(root / "attention"),
                paper_ledger=paper,
                valuation_market_evidence=evidence,
            ).build(
                logical_agent_ids=(),
                account_ids=("hype-paper",),
                data_slices=(replay.data_slice,),
            ).to_dict()

            valuation = document["paper_accounts"][0]["valuation"]
            self.assertEqual(valuation["mark"], "43.125")
            self.assertEqual(valuation["equity_before_unknown_costs"], "10000")
            self.assertIsNone(valuation["complete_equity"])
            self.assertEqual(
                document["portfolio"]["valuation_status"], "VALUED_SYNCHRONIZED"
            )
            self.assertEqual(
                document["portfolio"]["valuation_observed_at"],
                valuation["observed_at"],
            )

    def test_cost_effect_reports_embedded_execution_cost_without_double_deduction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = FilePaperLedger(root / "paper")
            model = PaperCostModelV1(
                model_id="workbench-cost-v1",
                maker_fee_bps="1",
                taker_fee_bps="2",
                market_impact_bps="1",
            )
            paper = PaperTradingService(
                ledger,
                cost_models=(model,),
                decision_authority=_DecisionAuthority(),
                market_evidence=_MarketEvidence(),
            )
            paper.open_account(
                account_id="hype-paper",
                account_mode="LINEAR_PERP",
                owner_logical_agent_id="hype-trader",
                base_currency="USDT",
                permitted_symbol="HYPE-USDT-SWAP",
                max_leverage="5",
                initial_balance="1000",
                opened_at="2026-08-12T12:00:00+00:00",
                instrument_spec=_instrument_spec(),
            )
            state = paper.submit(
                PaperCommandV1(
                    command_id="open-long",
                    account_id="hype-paper",
                    logical_agent_id="hype-trader",
                    agent_generation=1,
                    decision_cycle_id="workbench-cost-cycle",
                    decision_sha256="1" * 64,
                    expected_account_version=1,
                    symbol="HYPE-USDT-SWAP",
                    command_type="MARKET",
                    side="BUY",
                    quantity="1",
                    limit_price=None,
                    trigger_price=None,
                    target_order_id=None,
                    reduce_only=False,
                    time_in_force="GTC",
                    submitted_at="2026-08-12T12:01:00+00:00",
                    expires_at=None,
                    cost_model_id=model.model_id,
                )
            )
            state = paper.observe(
                account_id="hype-paper",
                expected_account_version=state.version,
                market=PaperMarketSliceV1(
                    symbol="HYPE-USDT-SWAP",
                    observed_at="2026-08-12T12:01:01+00:00",
                    available_at="2026-08-12T12:01:01+00:00",
                    source_sha256="0" * 64,
                    granularity="QUOTE",
                    path_status="ORDERED",
                    bid="99",
                    ask="101",
                    available_quantity="10",
                ),
            )
            paper.observe(
                account_id="hype-paper",
                expected_account_version=state.version,
                market=PaperMarketSliceV1(
                    symbol="HYPE-USDT-SWAP",
                    observed_at="2026-08-12T12:02:00+00:00",
                    available_at="2026-08-12T12:02:00+00:00",
                    source_sha256="2" * 64,
                    granularity="MARK",
                    path_status="ORDERED",
                    mark="100",
                ),
            )

            document = WorkbenchProjectionService(
                attention_repository=FileAttentionRepository(root / "attention"),
                paper_ledger=ledger,
            ).build(
                logical_agent_ids=(), account_ids=("hype-paper",)
            ).to_dict()
            cost = document["paper_accounts"][0]["cost_effect"]
            self.assertEqual(cost["fill_count"], 1)
            self.assertEqual(cost["spread_embedded_in_fill_price"], "1")
            self.assertEqual(cost["impact_embedded_in_fill_price"], "0.0101")
            self.assertEqual(cost["spread_cash_deduction"], "0")
            self.assertEqual(cost["impact_cash_deduction"], "0")
            self.assertIsNone(cost["timing_cost"])
            self.assertEqual(
                cost["timing_cost_status"],
                "UNKNOWN_INCOMPLETE_ARRIVAL_BENCHMARK",
            )
            self.assertEqual(
                cost["paper_execution_statuses"],
                ["PAPER_MODELED_ARITHMETIC"],
            )
            self.assertEqual(
                cost["venue_feasibility_status"],
                "UNKNOWN_TICK_LOT_MINIMUM_NOT_ENFORCED",
            )
            self.assertEqual(cost["fee_cash_cost"], "0.02020202")
            self.assertEqual(
                cost["embedded_execution_cost_treatment"],
                "INFORMATIONAL_ALREADY_IN_EXECUTION_PRICE_NO_SECOND_DEDUCTION",
            )
            self.assertIsNone(cost["complete_cash_cost"])
            self.assertIsNone(cost["complete_realized_pnl_after_cash_costs"])
            self.assertEqual(
                cost["actual_execution_effect_status"], "UNKNOWN_NOT_EVALUATED"
            )
            valuation = document["paper_accounts"][0]["valuation"]
            self.assertEqual(valuation["mark"], "100")
            self.assertIsNone(valuation["complete_equity"])
            restarted = WorkbenchProjectionService(
                attention_repository=FileAttentionRepository(root / "attention"),
                paper_ledger=FilePaperLedger(root / "paper"),
            ).build(
                logical_agent_ids=(), account_ids=("hype-paper",)
            ).to_dict()
            self.assertEqual(restarted, document)

    def test_portfolio_drawdown_is_unknown_when_account_marks_are_unsynchronized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = FilePaperLedger(root / "paper")
            paper = PaperTradingService(
                ledger,
                cost_models=(
                    PaperCostModelV1(
                        model_id="workbench-cost-v1",
                        maker_fee_bps="1",
                        taker_fee_bps="2",
                        market_impact_bps="1",
                    ),
                ),
                market_evidence=_MarketEvidence(),
            )
            for account_id, owner in (
                ("paper-a", "agent-a"),
                ("paper-b", "agent-b"),
            ):
                paper.open_account(
                    account_id=account_id,
                    account_mode="LINEAR_PERP",
                    owner_logical_agent_id=owner,
                    base_currency="USDT",
                    permitted_symbol="HYPE-USDT-SWAP",
                    max_leverage="5",
                    initial_balance="1000",
                    opened_at="2026-08-12T12:00:00+00:00",
                    instrument_spec=_instrument_spec(
                        f"hype-{account_id}-contract-v1"
                    ),
                )
            for account_id, minute, source in (
                ("paper-a", 1, "0"),
                ("paper-b", 2, "1"),
            ):
                paper.observe(
                    account_id=account_id,
                    expected_account_version=1,
                    market=PaperMarketSliceV1(
                        symbol="HYPE-USDT-SWAP",
                        observed_at=f"2026-08-12T12:0{minute}:00+00:00",
                        available_at=f"2026-08-12T12:0{minute}:00+00:00",
                        source_sha256=source * 64,
                        granularity="MARK",
                        path_status="ORDERED",
                        mark="100",
                    ),
                )

            portfolio = WorkbenchProjectionService(
                attention_repository=FileAttentionRepository(root / "attention"),
                paper_ledger=ledger,
            ).build(
                logical_agent_ids=(), account_ids=("paper-a", "paper-b")
            ).to_dict()["portfolio"]

            self.assertEqual(
                portfolio["valuation_status"], "UNKNOWN_UNSYNCHRONIZED_MARKS"
            )
            self.assertIsNone(portfolio["total_equity_before_unknown_costs"])
            self.assertIsNone(portfolio["current_drawdown"])
            self.assertIsNone(portfolio["observed_max_drawdown"])
            self.assertEqual(
                portfolio["drawdown_status"], "UNKNOWN_UNSYNCHRONIZED_MARKS"
            )

            for account_id, source in (("paper-a", "2"), ("paper-b", "3")):
                paper.observe(
                    account_id=account_id,
                    expected_account_version=2,
                    market=PaperMarketSliceV1(
                        symbol="HYPE-USDT-SWAP",
                        observed_at="2026-08-12T12:03:00+00:00",
                        available_at="2026-08-12T12:03:00+00:00",
                        source_sha256=source * 64,
                        granularity="MARK",
                        path_status="ORDERED",
                        mark="100",
                    ),
                )
            synchronized = WorkbenchProjectionService(
                attention_repository=FileAttentionRepository(root / "attention"),
                paper_ledger=ledger,
            ).build(
                logical_agent_ids=(), account_ids=("paper-a", "paper-b")
            ).to_dict()["portfolio"]
            self.assertEqual(synchronized["valuation_status"], "VALUED_SYNCHRONIZED")
            self.assertIsNone(synchronized["current_drawdown"])
            self.assertIsNone(synchronized["observed_max_drawdown"])
            self.assertEqual(
                synchronized["drawdown_status"],
                "UNKNOWN_SYNCHRONIZED_EQUITY_CURVE_REQUIRED",
            )


if __name__ == "__main__":
    unittest.main()
