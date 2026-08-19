from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_system.theory_paper_v2.domain.matching import (
    ClosedBar,
    MatchingPolicy,
)
from trade_system.theory_paper_v2.domain.position import LotRole
from trade_system.theory_paper_v2.infrastructure.offline_portfolio import (
    Attribution,
    LotSide,
    OfflineLot,
    PortfolioState,
    mark_portfolio,
    open_lot,
    replay_protective_bar,
)


class OfflinePortfolioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 1, tzinfo=UTC)
        self.state = PortfolioState(
            portfolio_id="portfolio-1",
            revision=0,
            initial_equity=Decimal("10000"),
            realized_pnl_before_cost=Decimal("0"),
            total_fees=Decimal("0"),
            lots=(),
            fills=(),
        )
        self.lot = OfflineLot(
            lot_id="lot-1",
            instrument_id="TESTUSDT",
            side=LotSide.LONG,
            role=LotRole.CORE,
            attribution=Attribution.STRATEGY,
            quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            entry_price=Decimal("100"),
            stop_price=Decimal("90"),
            target_price=Decimal("130"),
            opened_at=self.now,
            episode_id="episode-1",
            stage_id="stage-1",
            geometry_id="geometry-1",
        )
        self.policy = MatchingPolicy(
            policy_id="policy-1",
            instrument_id="TESTUSDT",
            venue_id="TEST",
            price_tick=Decimal("1"),
            quantity_step=Decimal("1"),
            contract_multiplier=Decimal("1"),
            fee_rate=Decimal("0.001"),
            adverse_slippage_bps=Decimal("0"),
        )

    def bar(self, low: str, high: str, close: str = "100") -> ClosedBar:
        return ClosedBar(
            bar_id=f"bar-{low}-{high}",
            instrument_id="TESTUSDT",
            venue_id="TEST",
            open_time=self.now,
            close_time=self.now + timedelta(hours=1),
            open=Decimal("100"),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=Decimal("1000"),
            observed_at=self.now + timedelta(hours=1),
            available_at=self.now + timedelta(hours=1),
            ingested_at=self.now + timedelta(hours=1),
            source_committed_at=self.now + timedelta(hours=1),
            source_commit_receipt_valid=True,
            lineage_digest_valid=True,
        )

    def test_exogenous_initial_lot_has_no_fabricated_entry_fee(self) -> None:
        exogenous = OfflineLot(
            **{
                **{
                    field: getattr(self.lot, field)
                    for field in self.lot.__dataclass_fields__
                },
                "attribution": Attribution.EXOGENOUS,
                "episode_id": None,
                "stage_id": None,
                "geometry_id": None,
            }
        )
        state = open_lot(
            self.state,
            lot=exogenous,
            fee_rate=Decimal("0.001"),
            fill_id="genesis",
            charge_entry_fee=False,
        )
        self.assertEqual(Decimal("0"), state.total_fees)
        self.assertEqual(
            "EXOGENOUS_INITIAL_POSITION_NO_ENTRY_FILL", state.fills[0].reason
        )

    def test_strategy_entry_and_stop_are_costed(self) -> None:
        state = open_lot(
            self.state,
            lot=self.lot,
            fee_rate=Decimal("0.001"),
            fill_id="entry-1",
            charge_entry_fee=True,
        )
        stopped = replay_protective_bar(
            state,
            bar=self.bar("89", "101", "91"),
            policy=self.policy,
            decision_cutoff=self.now + timedelta(hours=1),
        )
        snapshot = mark_portfolio(
            stopped,
            marks={"TESTUSDT": Decimal("91")},
            marked_at=self.now + timedelta(hours=1),
        )
        self.assertEqual(Decimal("-10"), snapshot.realized_pnl_before_cost)
        self.assertEqual(Decimal("0"), snapshot.unrealized_pnl)
        self.assertEqual(Decimal("0.19"), snapshot.total_fees)
        self.assertEqual(Decimal("-10.19"), snapshot.net_pnl)

    def test_same_bar_stop_and_target_uses_stop_first(self) -> None:
        state = open_lot(
            self.state,
            lot=self.lot,
            fee_rate=Decimal("0"),
            fill_id="entry-1",
            charge_entry_fee=True,
        )
        closed = replay_protective_bar(
            state,
            bar=self.bar("89", "131"),
            policy=self.policy,
            decision_cutoff=self.now + timedelta(hours=1),
        )
        self.assertEqual("STOP_MARKET", closed.fills[-1].reason)
        self.assertEqual(Decimal("-10"), closed.realized_pnl_before_cost)

    def test_unprotected_risk_is_unknown_not_zero(self) -> None:
        unprotected = OfflineLot(
            **{
                **{
                    field: getattr(self.lot, field)
                    for field in self.lot.__dataclass_fields__
                },
                "stop_price": None,
            }
        )
        state = open_lot(
            self.state,
            lot=unprotected,
            fee_rate=Decimal("0"),
            fill_id="entry",
            charge_entry_fee=False,
        )
        snapshot = mark_portfolio(
            state, marks={"TESTUSDT": Decimal("110")}, marked_at=self.now
        )
        self.assertIsNone(snapshot.open_risk_to_stop)
        self.assertEqual(("lot-1",), snapshot.unprotected_lot_ids)


if __name__ == "__main__":
    unittest.main()
