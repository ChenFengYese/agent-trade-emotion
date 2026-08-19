import unittest
from datetime import timedelta

from trade_system.quality import DataQualityEngine, HealthPolicy
from trade_system.types import BookHealth, SystemHealth, utc_now


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.policy = HealthPolicy({"depth", "trade"}, timedelta(seconds=5), timedelta(seconds=1))

    def test_missing_or_invalid_critical_stream_halts(self):
        quality = DataQualityEngine(self.policy)
        now = utc_now()
        self.assertEqual(SystemHealth.HALTED, quality.evaluate(now))
        quality.observe_book(now, BookHealth.INVALID, "gap")
        quality.observe("trade", now)
        self.assertEqual(SystemHealth.HALTED, quality.evaluate(now))

    def test_fresh_data_requires_cooldown_then_becomes_ready(self):
        quality = DataQualityEngine(self.policy)
        now = utc_now()
        quality.observe_book(now, BookHealth.VALID)
        quality.observe("trade", now)
        self.assertEqual(SystemHealth.WARMUP, quality.evaluate(now))
        self.assertEqual(SystemHealth.READY, quality.evaluate(now + timedelta(seconds=2)))
        self.assertEqual(SystemHealth.DEGRADED, quality.evaluate(now + timedelta(seconds=10)))
