import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from trade_system.feature_context import FeatureContextPolicy, MarketContextEngine
from trade_system.types import AvailabilityKind


class FeatureContextTests(unittest.TestCase):
    def _policy(self, root: Path, *, warmup=4, lookbacks=(1, 4), max_gap=1):
        path = root / "context.json"
        path.write_text(json.dumps({
            "context_policy_id": "context.test.v1", "status": "FROZEN_FEATURE_CONTEXT_POLICY",
            "frozen_at": "2026-07-22T00:00:00Z", "instrument": "BTCUSDT", "feature_version": "z-test-v1",
            "allowed_availability": "ACTUAL_ONLY",
            "sampling": {"decision_frequency_seconds": 1, "warmup_seconds": warmup, "max_gap_seconds": max_gap},
            "lookbacks_seconds": list(lookbacks),
            "trend": {"lookback_seconds": lookbacks[-1], "volatility_floor": "0.000000001"},
            "trend_continuation_veto": {
                "min_abs_trend_score": "0.1", "min_abs_directional_pressure": "1",
                "min_abs_price_impact": "0.000001", "max_directional_resilience": "0"
            }
        }), encoding="utf-8")
        return FeatureContextPolicy.load(path)

    @staticmethod
    def _observe(engine, timestamp, price, **extra):
        return engine.observe(
            available_at=timestamp, mid_price=price, availability_kind=AvailabilityKind.ACTUAL,
            book_valid=True, directional_pressure="2", price_impact="0.00001",
            directional_resilience="0", **extra
        )

    def test_known_path_computes_context_and_trend_veto(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = self._policy(Path(temp_dir))
            engine = MarketContextEngine(policy)
            start = datetime(2026, 7, 22, tzinfo=timezone.utc)
            for second in range(5):
                snapshot = self._observe(engine, start + timedelta(seconds=second), Decimal("100") + Decimal(second))
            self.assertEqual("READY", snapshot.status)
            self.assertEqual("ABSTAIN", snapshot.decision_permission)
            self.assertIn("TREND_CONTINUATION_OR_CONTEXT_UNAVAILABLE", snapshot.reason_codes)
            self.assertGreater(snapshot.values["Z_log_return_1s"], Decimal("0"))
            self.assertGreater(snapshot.values["Z_realized_volatility_4s"], Decimal("0"))
            self.assertGreater(snapshot.values["Z_trend_score_4s"], Decimal("0"))
            self.assertEqual(Decimal("1"), snapshot.values["Z_position_in_rolling_range_4s"])
            self.assertIsNone(snapshot.values["Z_episode_anchor_distance_bps"])

    def test_four_hour_warmup_cannot_emit_eligible_decision_early(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = self._policy(Path(temp_dir), warmup=14400, lookbacks=(60, 900, 3600, 14400))
            engine = MarketContextEngine(policy)
            start = datetime(2026, 7, 22, tzinfo=timezone.utc)
            for second in range(14400):
                snapshot = self._observe(engine, start + timedelta(seconds=second), Decimal("100") + Decimal(second) / Decimal("10000"))
            self.assertEqual("WARMUP", snapshot.status)
            self.assertEqual("ABSTAIN", snapshot.decision_permission)
            snapshot = self._observe(engine, start + timedelta(seconds=14400), Decimal("101.44"))
            self.assertEqual("READY", snapshot.status)

    def test_gap_non_actual_and_book_invalid_reset_continuity_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = self._policy(Path(temp_dir))
            engine = MarketContextEngine(policy)
            start = datetime(2026, 7, 22, tzinfo=timezone.utc)
            for second in range(5):
                self._observe(engine, start + timedelta(seconds=second), Decimal("100") + Decimal(second))
            gap = self._observe(engine, start + timedelta(seconds=7), Decimal("107"))
            self.assertEqual("DEGRADED", gap.status)
            self.assertIn("CONTEXT_GAP_EXCEEDED", gap.reason_codes)
            non_actual = engine.observe(
                available_at=start + timedelta(seconds=8), mid_price="108", availability_kind=AvailabilityKind.RECONSTRUCTED,
                book_valid=True, directional_pressure="2", price_impact="0.00001", directional_resilience="0",
            )
            self.assertEqual("DEGRADED", non_actual.status)
            self.assertIn("CONTEXT_NON_ACTUAL", non_actual.reason_codes)
            invalid_book = engine.observe(
                available_at=start + timedelta(seconds=9), mid_price="109", availability_kind=AvailabilityKind.ACTUAL,
                book_valid=False, directional_pressure="2", price_impact="0.00001", directional_resilience="0",
            )
            self.assertEqual("DEGRADED", invalid_book.status)
            self.assertIn("CONTEXT_BOOK_INVALID", invalid_book.reason_codes)
            restart = self._observe(engine, start + timedelta(seconds=10), Decimal("110"))
            self.assertEqual("WARMUP", restart.status)
            self.assertEqual("ABSTAIN", restart.decision_permission)

    def test_context_history_is_collection_local(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = self._policy(Path(temp_dir))
            first_collection = MarketContextEngine(policy)
            start = datetime(2026, 7, 22, tzinfo=timezone.utc)
            for second in range(5):
                self._observe(first_collection, start + timedelta(seconds=second), Decimal("900") + Decimal(second))
            # A second collection receives an entirely different history.  Its
            # result is identical to a fresh replay of that collection alone.
            second_collection = MarketContextEngine(policy)
            fresh_replay = MarketContextEngine(policy)
            for second in range(5):
                point = start + timedelta(hours=1, seconds=second)
                observed = self._observe(second_collection, point, Decimal("100") + Decimal(second))
                expected = self._observe(fresh_replay, point, Decimal("100") + Decimal(second))
            self.assertEqual(observed.to_dict(), expected.to_dict())
            self.assertNotEqual(first_collection._last_at, second_collection._last_at)

    def test_directional_resilience_is_pressure_side_and_improvement_is_point_in_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = self._policy(Path(temp_dir))
            engine = MarketContextEngine(policy)
            start = datetime(2026, 7, 22, tzinfo=timezone.utc)
            # BUY-side candidate: sell pressure must use bid resilience.
            for second in range(5):
                snapshot = engine.observe(
                    available_at=start + timedelta(seconds=second), mid_price=Decimal("100") + Decimal(second),
                    availability_kind=AvailabilityKind.ACTUAL, book_valid=True,
                    directional_pressure="-2", price_impact="-0.00001", directional_resilience=str(second),
                    directional_resilience_feature="R_sell_bid_resilience_1s",
                )
            self.assertEqual(Decimal("4"), snapshot.values["R_directional"])
            self.assertEqual(Decimal("1"), snapshot.values["R_directional_improvement"])
            # A pressure-side change does not compare bid and ask resilience.
            changed = engine.observe(
                available_at=start + timedelta(seconds=5), mid_price="105", availability_kind=AvailabilityKind.ACTUAL,
                book_valid=True, directional_pressure="2", price_impact="0.00001", directional_resilience="9",
                directional_resilience_feature="R_buy_ask_resilience_1s",
            )
            self.assertEqual(Decimal("9"), changed.values["R_directional"])
            self.assertIsNone(changed.values["R_directional_improvement"])
            # A continuity reset makes the comparison unavailable, never zero.
            after_gap = engine.observe(
                available_at=start + timedelta(seconds=7), mid_price="107", availability_kind=AvailabilityKind.ACTUAL,
                book_valid=True, directional_pressure="2", price_impact="0.00001", directional_resilience="10",
                directional_resilience_feature="R_buy_ask_resilience_1s",
            )
            self.assertIn("CONTEXT_GAP_EXCEEDED", after_gap.reason_codes)
            self.assertIsNone(after_gap.values["R_directional_improvement"])
