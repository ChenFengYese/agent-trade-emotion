import unittest
from decimal import Decimal

from trade_system.v4_decision.risk_engine import RiskInputs, size_from_risk
from trade_system.v4_decision.scenario_ev import Scenario, net_ev
from trade_system.v4_decision.trade_plan import TradePlan, validate_trade_plan


class V4DecisionArchitectureTests(unittest.TestCase):
    def test_risk_size_is_derived_from_structural_stop(self):
        result = size_from_risk(RiskInputs(
            equity=Decimal("1000"),
            trade_risk_budget=Decimal("25"),
            entry_price=Decimal("100"),
            structural_stop=Decimal("105"),
        ))
        self.assertEqual(result.max_notional_structural, Decimal("500"))
        self.assertEqual(result.selected_notional, Decimal("500"))
        self.assertEqual(result.structural_loss, Decimal("25"))

    def test_stress_buffer_reduces_notional(self):
        result = size_from_risk(RiskInputs(
            equity=Decimal("1000"),
            trade_risk_budget=Decimal("25"),
            entry_price=Decimal("100"),
            structural_stop=Decimal("105"),
            stress_buffer_pct=Decimal("0.01"),
            stress_risk_limit=Decimal("25"),
        ))
        self.assertLess(result.selected_notional, Decimal("500"))
        self.assertLessEqual(result.stress_loss, Decimal("25"))

    def test_net_ev_includes_costs(self):
        result = net_ev([
            Scenario("up", Decimal("0.4"), Decimal("60"), fees=Decimal("2")),
            Scenario("flat", Decimal("0.3"), Decimal("5"), fees=Decimal("1")),
            Scenario("down", Decimal("0.3"), Decimal("-20"), fees=Decimal("2")),
        ])
        self.assertEqual(result.probability_sum, Decimal("1"))
        self.assertEqual(result.gross_ev, Decimal("19.5"))
        self.assertEqual(result.net_ev, Decimal("17.8"))

    def test_directional_plan_requires_new_evidence_and_remains_non_executable(self):
        plan = TradePlan(
            instrument="BTCUSDT-SWAP",
            venue="PUBLIC_RESEARCH",
            action="SHORT",
            horizon="4H",
            entry_condition="confirmed rejection and reclaim failure",
            invalidation="structural acceptance above resistance",
            structural_stop=Decimal("105"),
            notional=Decimal("500"),
            order_type="PASSIVE_LIMIT",
            time_in_force="GTC",
            max_slippage_pct=Decimal("0.002"),
            expected_cost=Decimal("2"),
            stress_cost=Decimal("5"),
            evidence_id="E-17",
        )
        self.assertEqual(validate_trade_plan(plan), [])

    def test_executable_flag_is_rejected(self):
        plan = TradePlan(
            instrument="BTCUSDT-SWAP", venue="PUBLIC_RESEARCH", action="WAIT", horizon="4H",
            entry_condition="await event", invalidation="thesis absent", structural_stop=None,
            notional=None, order_type="NONE", time_in_force="NONE", max_slippage_pct=None,
            expected_cost=None, stress_cost=None, executable=True,
        )
        self.assertIn("V4 decision plans are non-executable; execution authority is separate", validate_trade_plan(plan))


if __name__ == "__main__":
    unittest.main()
