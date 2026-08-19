import unittest
from datetime import timedelta
from decimal import Decimal

from trade_system.decision import (
    ActionContract,
    ConservativePolicy,
    ExecutionForecast,
    MarketOutcome,
    OutcomeForecast,
    PathPoint,
    label_market_path,
)
from trade_system.types import GateLevel, PositionStage, Side, utc_now


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.contract = ActionContract(
            side=Side.BUY,
            stage=PositionStage.ENTER_PROBE,
            entry_price=Decimal("100"),
            take_profit=Decimal("102"),
            stop_loss=Decimal("98"),
            horizon=timedelta(minutes=1),
            structure_exit_fraction=Decimal("0.001"),
        )

    def test_operational_override_censors_market_label(self):
        now = utc_now()
        result = label_market_path(
            self.contract,
            now,
            [PathPoint(now + timedelta(seconds=1), Decimal("99"), operational_override="DATA_EXECUTION_HALT")],
        )
        self.assertTrue(result.is_censored)
        self.assertIsNone(result.market_outcome)

    def test_first_market_barrier_wins(self):
        now = utc_now()
        result = label_market_path(
            self.contract,
            now,
            [PathPoint(now + timedelta(seconds=1), Decimal("102")), PathPoint(now + timedelta(seconds=2), Decimal("98"))],
        )
        self.assertEqual(MarketOutcome.TP, result.market_outcome)

    def test_policy_separates_fill_and_market_ev(self):
        outcome = OutcomeForecast(Decimal("0.6"), Decimal("0.2"), Decimal("0.1"), Decimal("0.1"))
        execution = ExecutionForecast(Decimal("0.8"), Decimal("0.75"), Decimal("0"), Decimal("0"))
        decision = ConservativePolicy(Decimal("0.1")).evaluate(
            outcome=outcome,
            execution=execution,
            gain_if_tp=Decimal("2"),
            loss_if_sl=Decimal("1"),
            expected_structure_return=Decimal("0"),
            expected_timeout_return=Decimal("0"),
            trade_cost=Decimal("0.1"),
            gate_level=GateLevel.OPEN,
            data_healthy=True,
            model_applicable=True,
        )
        self.assertTrue(decision.trade)
        self.assertGreater(decision.ev_fill, decision.ev_submit)
