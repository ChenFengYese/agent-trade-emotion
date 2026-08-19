from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from trade_system.bar_resampler import BarResamplerError, FinalizedMinuteBar, SUPPORTED_TARGET_INTERVALS, resample_closed_bars


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def minute_bars(start: datetime, count: int, *, offset: Decimal = Decimal("0")):
    rows = []
    for index in range(count):
        opened = start + timedelta(minutes=index)
        opening = Decimal("100") + offset + Decimal(index)
        rows.append(FinalizedMinuteBar(
            source_id="m-%04d" % index, instrument_id="BTCUSDT", open_at=opened, close_at=opened + timedelta(minutes=1),
            open=opening, high=opening + Decimal("2"), low=opening - Decimal("1"), close=opening + Decimal("1"),
            volume=Decimal(index + 1), available_at=opened + timedelta(minutes=1),
        ))
    return rows


class BarResamplerTests(unittest.TestCase):
    def test_supported_targets_are_exact_route_set(self):
        self.assertEqual(("15m", "1h", "4h", "1d"), SUPPORTED_TARGET_INTERVALS)

    def test_ohlcv_for_each_supported_target(self):
        start = at("2026-01-01T00:00:00Z")
        for interval, minutes in (("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440)):
            with self.subTest(interval=interval):
                output = resample_closed_bars(minute_bars(start, minutes), interval)
                self.assertEqual(1, len(output))
                bar = output[0]
                self.assertEqual(start, bar.open_at)
                self.assertEqual(start + timedelta(minutes=minutes), bar.close_at)
                self.assertEqual(Decimal("100"), bar.open)
                self.assertEqual(Decimal(99), bar.low)
                self.assertEqual(Decimal(minutes + 100), bar.close)
                self.assertEqual(Decimal(minutes + 101), bar.high)
                self.assertEqual(sum(Decimal(item) for item in range(1, minutes + 1)), bar.volume)
                self.assertEqual(bar.close_at, bar.available_at)

    def test_utc_boundaries_and_two_windows(self):
        rows = minute_bars(at("2026-01-01T03:45:00Z"), 30)
        bars = resample_closed_bars(rows, "15m")
        self.assertEqual(["2026-01-01T03:45:00Z", "2026-01-01T04:00:00Z"], [item.to_dict()["open_at"] for item in bars])
        days = resample_closed_bars(minute_bars(at("2026-01-01T00:00:00Z"), 2880), "1d")
        self.assertEqual(2, len(days))
        self.assertEqual("2026-01-02T00:00:00Z", days[1].to_dict()["open_at"])

    def test_rejects_partial_gap_duplicate_and_out_of_order(self):
        start = at("2026-01-01T00:00:00Z")
        with self.assertRaises(BarResamplerError):
            resample_closed_bars(minute_bars(start, 14), "15m")
        gapped = minute_bars(start, 15)
        gapped[7] = minute_bars(start + timedelta(minutes=8), 1)[0]
        with self.assertRaises(BarResamplerError):
            resample_closed_bars(gapped, "15m")
        duplicate = minute_bars(start, 15)
        duplicate[8] = duplicate[7]
        with self.assertRaises(BarResamplerError):
            resample_closed_bars(duplicate, "15m")
        backwards = minute_bars(start, 15)
        backwards[8], backwards[9] = backwards[9], backwards[8]
        with self.assertRaises(BarResamplerError):
            resample_closed_bars(backwards, "15m")

    def test_rejects_unclosed_malformed_and_binary_float_source(self):
        row = minute_bars(at("2026-01-01T00:00:00Z"), 1)[0]
        premature = FinalizedMinuteBar(**{**row.__dict__, "available_at": row.open_at})
        with self.assertRaises(BarResamplerError):
            resample_closed_bars([premature], "15m")
        floating = FinalizedMinuteBar(**{**row.__dict__, "open": 100.0})
        with self.assertRaises(BarResamplerError):
            floating.validated()
        with self.assertRaises(BarResamplerError):
            resample_closed_bars(minute_bars(row.open_at, 15), "1w")

    def test_repeat_output_is_canonical_and_deterministic(self):
        rows = minute_bars(at("2026-01-01T00:00:00Z"), 15)
        rows[-1] = FinalizedMinuteBar(**{**rows[-1].__dict__, "available_at": at("2026-01-01T00:20:00Z")})
        first = resample_closed_bars(rows, "15m")
        second = resample_closed_bars(rows, "15m")
        self.assertEqual([item.to_dict() for item in first], [item.to_dict() for item in second])
        self.assertEqual(first[0].canonical_sha256(), second[0].canonical_sha256())
        self.assertEqual("2026-01-01T00:20:00Z", first[0].to_dict()["available_at"])

    def test_static_route_and_dataset_plan_are_frozen_and_self_hashed(self):
        route = json.loads((ROOT / "config/sol_decision.fast-slow-har1-research-p0-static-route.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(["15m", "1h", "4h", "1d"], route["bar_resampler_contract"]["supported_target_intervals"])
        plan = json.loads((ROOT / "config/har1_btcusdt_dataset_plan.v1.json").read_text(encoding="utf-8"))
        self.assertEqual("BINANCE", plan["venue"])
        self.assertEqual("USD_M_FUTURES", plan["product_family"])
        self.assertEqual("BTCUSDT", plan["instrument_id"])
        self.assertEqual({
            "start_inclusive": "2020-07-01T00:00:00Z", "end_exclusive": "2025-07-01T00:00:00Z",
            "interval": "4h", "role": "SEEN_LONG_CONTEXT_REFERENCE_ONLY",
        }, plan["long_context"])
        self.assertEqual([
            {"start_inclusive": "2025-07-01T00:00:00Z", "end_exclusive": "2026-01-01T00:00:00Z", "role": "DEVELOPMENT"},
            {"start_inclusive": "2026-01-01T00:00:00Z", "end_exclusive": "2026-04-01T00:00:00Z", "role": "CALIBRATION"},
            {"start_inclusive": "2026-04-01T00:00:00Z", "end_exclusive": "2026-07-01T00:00:00Z", "role": "LOCKED_HISTORICAL_HOLDOUT"},
        ], plan["role_windows_before_purge"])
        self.assertEqual([], plan["requests"])
        self.assertEqual([], plan["object_urls"])
        self.assertEqual([], plan["checksum_expectations"])
        self.assertTrue(all(value == "DENIED" for value in plan["data_permissions"].values()))
        self.assertEqual("UNSET_BLOCKS_DATA_GATE", plan["purge_contract"]["maximum_lookback"])
        self.assertEqual({
            "actor": "NATURAL_PERSON", "jurisdiction": "JP",
            "purpose": "INTERNAL_RESEARCH_AND_DERIVED_ANALYSIS", "redistribution": "NOT_REQUESTED",
        }, plan["user_scope"])
        body = dict(plan)
        digest = body.pop("plan_sha256")
        expected = hashlib.sha256(b"msta-hed/har1-btcusdt-dataset-plan/v1\x00" + json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(expected, digest)


if __name__ == "__main__":
    unittest.main()
