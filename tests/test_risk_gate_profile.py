import json
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from trade_system.risk import RiskEngine, RiskGate, RiskLimits
from trade_system.risk import OrderManager
from trade_system.risk_gate_profile import RiskGateProfile, RiskGateProfileError
from trade_system.types import GateLevel, utc_now


class RiskGateProfileTests(unittest.TestCase):
    def _profile(self):
        return RiskGateProfile.load(Path(__file__).parents[1] / "config" / "risk_gate_profile.paper.v1.json")

    def test_frozen_profile_enforces_recovery_hysteresis_and_manual_clear(self):
        profile = self._profile()
        gate = RiskGate(profile)
        now = utc_now()
        gate.set("MODEL_INPUT_STALE", GateLevel.NO_NEW_RISK, now)
        with self.assertRaises(ValueError):
            gate.clear("MODEL_INPUT_STALE", now=now)
        gate.mark_recovered("MODEL_INPUT_STALE", now)
        with self.assertRaises(ValueError):
            gate.clear("MODEL_INPUT_STALE", now=now + timedelta(seconds=4))
        gate.clear("MODEL_INPUT_STALE", now=now + timedelta(seconds=5))
        self.assertEqual(GateLevel.OPEN, gate.level)

        gate.set("ACCOUNT_MISMATCH", GateLevel.HALT_AND_RECONCILE, now)
        gate.mark_recovered("ACCOUNT_MISMATCH", now)
        with self.assertRaises(ValueError):
            gate.clear("ACCOUNT_MISMATCH", now=now + timedelta(seconds=5))
        gate.clear("ACCOUNT_MISMATCH", now=now + timedelta(seconds=5), manual_acknowledged=True)
        self.assertEqual(GateLevel.OPEN, gate.level)

    def test_less_restrictive_clear_cannot_override_another_active_reason(self):
        profile = self._profile()
        gate = RiskGate(profile)
        now = utc_now()
        gate.set("MODEL_INPUT_STALE", GateLevel.NO_NEW_RISK, now)
        gate.set("DATA_EXECUTION_HALT", GateLevel.HALT_AND_RECONCILE, now)
        gate.mark_recovered("MODEL_INPUT_STALE", now)
        gate.clear("MODEL_INPUT_STALE", now=now + timedelta(seconds=5))
        self.assertEqual(GateLevel.HALT_AND_RECONCILE, gate.level)

    def test_engine_rejects_reason_level_that_conflicts_with_frozen_contract(self):
        profile = self._profile()
        engine = RiskEngine(RiskLimits(
            max_episode_loss=Decimal("1"), max_total_notional=Decimal("1"),
            max_single_order_quantity=Decimal("1"), tail_cost_per_unit=Decimal("0"),
            max_unprotected_duration=timedelta(seconds=1),
        ), gate_profile=profile)
        with self.assertRaises(ValueError):
            engine.gate.set("MODEL_INPUT_STALE", GateLevel.HALT_AND_RECONCILE, utc_now())

    def test_oms_halt_maps_diagnostic_reason_to_frozen_halt_family(self):
        profile = self._profile()
        engine = RiskEngine(RiskLimits(
            max_episode_loss=Decimal("1"), max_total_notional=Decimal("1"),
            max_single_order_quantity=Decimal("1"), tail_cost_per_unit=Decimal("0"),
            max_unprotected_duration=timedelta(seconds=1),
        ), gate_profile=profile)
        manager = OrderManager(engine)
        manager.halt("UNPROTECTED_POSITION")
        self.assertIn("UNPROTECTED_POSITION", manager.halt_reasons)
        self.assertEqual(GateLevel.HALT_AND_RECONCILE, engine.gate.level)
        self.assertIn("DATA_EXECUTION_HALT", engine.gate.reasons)

    def test_profile_rejects_missing_resolver_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps({
                "profile_id": "x", "status": "FROZEN_PAPER_RISK_GATE_PROFILE", "frozen_at": "2026-01-01T00:00:00Z",
                "reason_policies": [],
            }), encoding="utf-8")
            with self.assertRaises(RiskGateProfileError):
                RiskGateProfile.load(path)
