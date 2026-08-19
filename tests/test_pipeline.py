import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.cli import _append_actual
from trade_system.event_store import EventStore
from trade_system.pipeline import FeaturePipeline, write_feature_rows
from trade_system.episode_policy import EpisodePolicy
from trade_system.feature_context import FeatureContextPolicy
from trade_system.types import AvailabilityKind


class PipelineTests(unittest.TestCase):
    def test_replay_builds_features_and_writes_new_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventStore(Path(temp_dir) / "runtime")
            connection = "pipeline-test"
            events = [
                {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]},
                {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"},
                {"kind": "delta", "U": 11, "u": 11, "pu": 10, "bids": [["99", "3"]], "asks": []},
            ]
            for index, event in enumerate(events, start=1):
                _append_actual(store, connection, index, event)
            rows = list(FeaturePipeline().replay(store))
            self.assertGreaterEqual(len(rows), 1)
            output = Path(temp_dir) / "artifacts" / "features.ndjson"
            self.assertEqual(len(rows), write_feature_rows(output, rows))
            with self.assertRaises(FileExistsError):
                write_feature_rows(output, rows)

    def test_context_uses_closed_utc_buckets_without_flooring_microsecond_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            episode_path = root / "episode.json"
            episode_path.write_text(json.dumps({
                "policy_id": "episode.ctx", "status": "FROZEN_EPISODE_POLICY", "frozen_at": "2026-07-22T00:00:00Z", "feature_version": "ctx.v1",
                "trigger_feature": "D_directional_pressure", "trigger_threshold": "0.01", "min_seconds_between_episodes": 0,
                "decision_frequency_seconds": 1, "derived_semantics_version": "closed-utc-second.v1",
                "state_machine": {"pressure_threshold": "0.01", "resilience_threshold": "0", "response_fraction": "0.001", "max_observation_seconds": 20000, "confirmation_updates": 2},
            }), encoding="utf-8")
            context_path = root / "context.json"
            context_path.write_text(json.dumps({
                "context_policy_id": "context.ctx", "status": "FROZEN_FEATURE_CONTEXT_POLICY", "frozen_at": "2026-07-22T00:00:00Z", "instrument": "BTCUSDT", "feature_version": "ctx.v1",
                "allowed_availability": "ACTUAL_ONLY", "sampling": {"decision_frequency_seconds": 1, "warmup_seconds": 14400, "max_gap_seconds": 1},
                "lookbacks_seconds": [1, 14400], "trend": {"lookback_seconds": 14400, "volatility_floor": "0.000001"},
                "trend_continuation_veto": {"min_abs_trend_score": "9", "min_abs_directional_pressure": "9", "min_abs_price_impact": "9", "max_directional_resilience": "0"},
            }), encoding="utf-8")
            pipeline = FeaturePipeline(EpisodePolicy.load(episode_path), FeatureContextPolicy.load(context_path))
            start = datetime(2026, 7, 22, tzinfo=timezone.utc)
            rows = []
            for second in range(14402):
                midpoint = 100 + second
                row = pipeline.process("snapshot-%d" % second, AvailabilityKind.ACTUAL, start + timedelta(seconds=second, microseconds=100000), {"kind": "snapshot", "last_update_id": second + 1, "bids": [[str(midpoint - 1), "100"]], "asks": [[str(midpoint + 1), "100"]]})
                if row is not None:
                    rows.append(row)
                row = pipeline.process("trade-%d" % second, AvailabilityKind.ACTUAL, start + timedelta(seconds=second, microseconds=250000), {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"})
                if row is not None:
                    rows.append(row)
            ready = [row for row in rows if row.event_id == "snapshot-14401"][0]
            self.assertEqual(start + timedelta(seconds=14401, microseconds=100000), datetime.fromisoformat(ready.available_at))
            self.assertEqual("READY", ready.context["context_status"])
            self.assertEqual("ELIGIBLE", ready.context["decision_permission"])
            self.assertEqual(ready.available_at, ready.context["available_at"])
            self.assertEqual((start + timedelta(seconds=14400)).isoformat(), ready.context["measurement_bucket_at"])
            self.assertIsNotNone(ready.context["values"]["Z_episode_anchor_distance_bps"])
            self.assertIsNotNone(ready.context["values"]["R_directional"])
            self.assertIsNotNone(ready.context["values"]["R_directional_improvement"])
            warmup = [row for row in rows if row.event_id == "snapshot-4"][0]
            self.assertEqual("WARMUP", warmup.context["context_status"])
            self.assertEqual("ABSTAIN", warmup.context["decision_permission"])
            # Only the first event in a UTC second can advance the episode;
            # the later same-second trade cannot move it with raw cadence.
            first_decision = [row for row in rows if row.event_id == "snapshot-1"][0]
            same_second_extra = [row for row in rows if row.event_id == "trade-1"][0]
            self.assertEqual(first_decision.episode_state, same_second_extra.episode_state)
            # A gap is known at the next real event and invalidates context;
            # no synthetic floor timestamp is published.
            gap = pipeline.process("trade-gap", AvailabilityKind.ACTUAL, start + timedelta(seconds=14404, microseconds=250000), {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"})
            self.assertEqual("DEGRADED", gap.context["context_status"])
            self.assertIn("CONTEXT_GAP_EXCEEDED", gap.context["reason_codes"])
