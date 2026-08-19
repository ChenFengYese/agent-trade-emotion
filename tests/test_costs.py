from decimal import Decimal
import unittest

from trade_system.costs import CostScenario, estimate_round_trip_cost, evaluate_cost_pressure
from trade_system.decision import ConservativePolicy, ExecutionForecast, OutcomeForecast
from trade_system.types import GateLevel


class CostPressureTests(unittest.TestCase):
    def _scenario(self, scenario_id, fee="0.001", spread="2", slip="3", funding="1", tail="4"):
        return CostScenario(
            scenario_id=scenario_id,
            entry_fee_rate=Decimal(fee),
            exit_fee_rate=Decimal(fee),
            spread_bps=Decimal(spread),
            conditional_slippage_bps=Decimal(slip),
            funding_bps=Decimal(funding),
            tail_execution_bps=Decimal(tail),
        )

    def test_cost_is_explicitly_decomposed(self):
        cost = estimate_round_trip_cost(entry_price=Decimal("100"), quantity=Decimal("2"), scenario=self._scenario("normal"))
        self.assertEqual(Decimal("0.4"), cost.fee)
        self.assertEqual(Decimal("0.04"), cost.spread)
        self.assertEqual(Decimal("0.06"), cost.conditional_slippage)
        self.assertEqual(Decimal("0.02"), cost.funding)
        self.assertEqual(Decimal("0.08"), cost.tail_execution)
        self.assertEqual(Decimal("0.60"), cost.total)

    def test_pressure_scenario_can_turn_positive_ev_into_abstain(self):
        result = evaluate_cost_pressure(
            scenarios=(self._scenario("normal", fee="0", spread="0", slip="0", funding="0", tail="0"), self._scenario("stress", fee="0.01", spread="10", slip="10", funding="10", tail="10")),
            policy=ConservativePolicy(Decimal("0")),
            entry_price=Decimal("100"),
            quantity=Decimal("1"),
            outcome=OutcomeForecast(Decimal("0.55"), Decimal("0.35"), Decimal("0.05"), Decimal("0.05")),
            execution=ExecutionForecast(Decimal("1"), Decimal("1"), Decimal("0"), Decimal("0")),
            gain_if_tp=Decimal("3"),
            loss_if_sl=Decimal("2"),
            expected_structure_return=Decimal("0"),
            expected_timeout_return=Decimal("0"),
            gate_level=GateLevel.OPEN,
            data_healthy=True,
            model_applicable=True,
        )
        self.assertTrue(result[0].decision.trade)
        self.assertFalse(result[1].decision.trade)
        self.assertEqual("NEGATIVE_OR_INSUFFICIENT_EV", result[1].decision.reason)
