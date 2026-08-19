import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.cli import _append_actual
from trade_system.episode_policy import EpisodePolicy, EpisodePolicyError
from trade_system.event_store import EventStore
from trade_system.pipeline import FeaturePipeline
from trade_system.types import AvailabilityKind, EpisodeState, Side


class EpisodePolicyTests(unittest.TestCase):
    def _policy(self, path: Path):
        path.write_text(json.dumps({
            "policy_id": "episode.v1", "status": "FROZEN_EPISODE_POLICY", "frozen_at": "2026-07-22T00:00:00Z",
            "feature_version": "five-factor-proxy-v1", "trigger_feature": "D_directional_pressure",
            "trigger_threshold": "0.00001", "min_seconds_between_episodes": 1,
            "state_machine": {"pressure_threshold": "0.00001", "resilience_threshold": "0", "response_fraction": "0.0001", "max_observation_seconds": 60, "confirmation_updates": 2},
        }), encoding="utf-8")

    def test_frozen_policy_opens_only_after_declared_extreme(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policy_path = root / "episode.json"
            self._policy(policy_path)
            store = EventStore(root / "runtime")
            _append_actual(store, "episode", 1, {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]})
            _append_actual(store, "episode", 2, {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"})
            rows = list(FeaturePipeline(EpisodePolicy.load(policy_path)).replay(store))
            self.assertIsNone(rows[0].episode_id)
            self.assertIsNotNone(rows[-1].episode_id)
            self.assertEqual("episode.v1", rows[-1].episode_policy_id)

    def test_policy_rejects_non_integer_confirmation_updates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "episode.json"
            self._policy(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["state_machine"]["confirmation_updates"] = "1.5"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(EpisodePolicyError):
                EpisodePolicy.load(path)

    def test_clocked_policy_requires_positive_frequency_and_semantics_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "episode.json"
            raw = json.loads(Path("config/episode_policy.v2.json").read_text(encoding="utf-8"))
            raw["decision_frequency_seconds"] = 0
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(EpisodePolicyError):
                EpisodePolicy.load(path)
            raw["decision_frequency_seconds"] = 1
            raw.pop("derived_semantics_version")
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(EpisodePolicyError):
                EpisodePolicy.load(path)

    def test_terminal_episode_cooldown_uses_seconds_duration(self):
        """A frozen policy must be replayable on the row after a terminal episode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "episode.json"
            self._policy(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["state_machine"]["max_observation_seconds"] = 1
            path.write_text(json.dumps(raw), encoding="utf-8")
            pipeline = FeaturePipeline(EpisodePolicy.load(path))
            started_at = datetime(2026, 7, 22, tzinfo=timezone.utc)

            pipeline.process(
                "snapshot", AvailabilityKind.ACTUAL, started_at,
                {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]},
            )
            opened = pipeline.process(
                "sell-pressure", AvailabilityKind.ACTUAL, started_at + timedelta(seconds=1),
                {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"},
            )
            self.assertIsNotNone(opened)
            self.assertIsNotNone(pipeline.episodes.active)
            self.assertFalse(pipeline.episodes.active.is_terminal)

            timed_out = pipeline.process(
                "timeout", AvailabilityKind.ACTUAL, started_at + timedelta(seconds=3),
                {"kind": "delta", "U": 11, "u": 11, "pu": 10, "bids": [["99", "3"]], "asks": []},
            )
            self.assertEqual("TIMED_OUT", timed_out.episode_state)

            after_terminal = pipeline.process(
                "after-terminal", AvailabilityKind.ACTUAL, started_at + timedelta(seconds=5),
                {"kind": "delta", "U": 12, "u": 12, "pu": 11, "bids": [["99", "4"]], "asks": []},
            )
            self.assertIsNotNone(after_terminal)

    def test_terminal_episode_is_released_once_and_cooldown_allows_next_episode(self):
        """Terminal rows are emitted once; later rows must not extend cooldown or reuse their episode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "episode.json"
            self._policy(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["min_seconds_between_episodes"] = 30
            raw["state_machine"]["max_observation_seconds"] = 1
            path.write_text(json.dumps(raw), encoding="utf-8")
            pipeline = FeaturePipeline(EpisodePolicy.load(path))
            started_at = datetime(2026, 7, 22, tzinfo=timezone.utc)

            pipeline.process(
                "snapshot", AvailabilityKind.ACTUAL, started_at,
                {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]},
            )
            first = pipeline.process(
                "sell-pressure", AvailabilityKind.ACTUAL, started_at + timedelta(seconds=1),
                {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"},
            )
            self.assertEqual("episode-000001", first.episode_id)
            terminal = pipeline.process(
                "timeout", AvailabilityKind.ACTUAL, started_at + timedelta(seconds=3),
                {"kind": "delta", "U": 11, "u": 11, "pu": 10, "bids": [["99", "3"]], "asks": []},
            )
            self.assertEqual("episode-000001", terminal.episode_id)
            self.assertEqual("TIMED_OUT", terminal.episode_state)
            self.assertIsNone(pipeline.episodes.active)

            during_cooldown = pipeline.process(
                "cooldown", AvailabilityKind.ACTUAL, started_at + timedelta(seconds=4),
                {"kind": "delta", "U": 12, "u": 12, "pu": 11, "bids": [["99", "4"]], "asks": []},
            )
            self.assertIsNone(during_cooldown.episode_id)
            self.assertIsNone(during_cooldown.episode_state)
            self.assertEqual(started_at + timedelta(seconds=3), pipeline._last_terminal_at)

            second = pipeline.process(
                "second-pressure", AvailabilityKind.ACTUAL, started_at + timedelta(seconds=33),
                {"kind": "trade", "price": "100", "quantity": "1", "side": "SELL"},
            )
            self.assertEqual("episode-000002", second.episode_id)
            self.assertEqual("EXPANDING", second.episode_state)

    def test_v1_policy_keeps_event_driven_episode_advancement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "episode.json"
            self._policy(path)
            pipeline = FeaturePipeline(EpisodePolicy.load(path))
            self.assertIsNone(pipeline.episode_policy.decision_interval)
            started_at = datetime(2026, 7, 22, tzinfo=timezone.utc)
            pipeline.process(
                "snapshot", AvailabilityKind.ACTUAL, started_at,
                {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]},
            )
            active = pipeline.episodes.observe_extreme(now=started_at, price=pipeline.book.mid_price, reversal_side=Side.BUY)
            active.state = EpisodeState.RESPONDING
            pipeline.process(
                "first", AvailabilityKind.ACTUAL, started_at + timedelta(milliseconds=100),
                {"kind": "delta", "U": 11, "u": 11, "pu": 10, "bids": [["100", "2"]], "asks": []},
            )
            terminal = pipeline.process(
                "second", AvailabilityKind.ACTUAL, started_at + timedelta(milliseconds=200),
                {"kind": "delta", "U": 12, "u": 12, "pu": 11, "bids": [["100", "2"]], "asks": []},
            )
            self.assertEqual("REVERSAL_CONFIRMED", terminal.episode_state)

    def test_v2_policy_decision_clock_limits_advancement_to_one_per_second(self):
        policy = EpisodePolicy.load(Path("config/episode_policy.v2.json"))
        self.assertEqual(timedelta(seconds=1), policy.decision_interval)
        started_at = datetime(2026, 7, 22, tzinfo=timezone.utc)

        def replay_rows():
            pipeline = FeaturePipeline(policy)
            pipeline.process(
                "snapshot", AvailabilityKind.ACTUAL, started_at,
                {"kind": "snapshot", "last_update_id": 10, "bids": [["99", "2"]], "asks": [["101", "2"]]},
            )
            active = pipeline.episodes.observe_extreme(now=started_at, price=pipeline.book.mid_price, reversal_side=Side.BUY)
            active.state = EpisodeState.RESPONDING
            rows = []
            for event_id, offset in (("within-100ms", 100), ("within-900ms", 900), ("boundary-1s", 1000), ("within-1100ms", 1100), ("boundary-2s", 2000), ("boundary-3s", 3000)):
                rows.append(pipeline.process(
                    event_id, AvailabilityKind.ACTUAL, started_at + timedelta(milliseconds=offset),
                    {"kind": "delta", "U": 10 + len(rows) + 1, "u": 10 + len(rows) + 1, "pu": 10 + len(rows), "bids": [["100", "2"]], "asks": []},
                ))
            return pipeline, rows

        pipeline, rows = replay_rows()
        self.assertEqual("RESPONDING", rows[0].episode_state)
        self.assertEqual("RESPONDING", rows[1].episode_state)
        self.assertEqual([False, False, True, False, True, True], [row.episode_decision_eligible for row in rows])
        self.assertEqual("RESPONDING", rows[2].episode_state)
        self.assertEqual("RESPONDING", rows[3].episode_state)
        self.assertEqual("RESPONDING", rows[4].episode_state)
        self.assertEqual("REVERSAL_CONFIRMED", rows[5].episode_state)
        self.assertIsNone(pipeline.episodes.active)
        _, repeat = replay_rows()
        self.assertEqual([row.to_dict() for row in rows], [row.to_dict() for row in repeat])
