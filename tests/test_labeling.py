import json
import tempfile
import unittest
from pathlib import Path

from trade_system.labeling import EpisodePathContext, generate_labels, load_actions, load_feature_prices
from trade_system.types import parse_utc


class LabelingTests(unittest.TestCase):
    def _write_jsonl(self, path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def _action(self, execution="FILLED"):
        return {
            "decision_id": "decision-1",
            "episode_id": "episode-1",
            "decision_at": "2026-01-01T00:00:00Z",
            "filled_at": "2026-01-01T00:00:00Z",
            "side": "BUY",
            "stage": "ENTER_PROBE",
            "entry_price": "100",
            "take_profit": "102",
            "stop_loss": "98",
            "horizon_seconds": 60,
            "execution_outcome": execution,
            "fill_fraction": "1" if execution != "NO_FILL" else "0",
            "features": {"D_directional_pressure": -0.1},
        }

    def _feature(self, time, mid, kind="ACTUAL"):
        return {"event_id": time, "available_at": time, "availability_kind": kind, "values": {"mid_price": mid}}

    def test_tp_is_labeled_from_future_feature_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._action()])
            self._write_jsonl(features_path, [
                self._feature("2026-01-01T00:00:00Z", "100"),
                self._feature("2026-01-01T00:00:01Z", "102"),
            ])
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path))
            self.assertEqual("TP", rows[0]["market_outcome"])
            self.assertEqual("FILLED", rows[0]["execution_outcome"])

    def test_no_fill_is_not_forced_into_market_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._action("NO_FILL")])
            self._write_jsonl(features_path, [self._feature("2026-01-01T00:00:01Z", "102")])
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path))
            self.assertIsNone(rows[0]["market_outcome"])
            self.assertIsNone(rows[0]["outcome"])

    def test_reconstructed_features_are_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            features_path = Path(temp_dir) / "features.ndjson"
            self._write_jsonl(features_path, [self._feature("2026-01-01T00:00:01Z", "100", "RECONSTRUCTED")])
            with self.assertRaises(ValueError):
                load_feature_prices(features_path)

    def test_override_censors_at_first_feature_after_its_own_clock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            action = self._action()
            action["operational_override_at"] = "2026-01-01T00:00:00.500000Z"
            action["operational_override"] = "DATA_UNHEALTHY"
            self._write_jsonl(actions_path, [action])
            self._write_jsonl(features_path, [
                self._feature("2026-01-01T00:00:00Z", "100"),
                self._feature("2026-01-01T00:00:01Z", "101"),
            ])
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path))
            self.assertTrue(rows[0]["censored"])
            self.assertEqual("2026-01-01T00:00:01+00:00", rows[0]["label_end_at"])

    def _v2_action(self):
        return {
            "action_schema_version": "research-action-v2", "decision_id": "decision-v2", "episode_id": "episode-1",
            "decision_at": "2026-01-01T00:00:00Z", "market_path_entry_at": "2026-01-01T00:00:00Z",
            "feature_event_id": "feature-decision-v2",
            "market_path_entry_assumption": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "execution_evidence": False,
            "side": "BUY", "stage": "ENTER_PROBE", "entry_price": "100", "take_profit": "102", "stop_loss": "98", "horizon_seconds": 60,
            "features": {"D_directional_pressure": -1}, "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"},
        }

    def test_v2_structure_exit_uses_same_episode_decision_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._v2_action()])
            self._write_jsonl(features_path, [
                self._feature("2026-01-01T00:00:00Z", "100"),
                self._feature("2026-01-01T00:00:01Z", "100"),
            ])
            contexts = [
                EpisodePathContext(parse_utc("2026-01-01T00:00:00Z"), "episode-1", "RESPONDING", True, ()),
                EpisodePathContext(parse_utc("2026-01-01T00:00:01Z"), "episode-1", "FAILED", True, ()),
            ]
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path), episode_contexts=contexts)
            self.assertEqual("STRUCTURE_EXIT", rows[0]["outcome"])
            self.assertFalse(rows[0]["execution_evidence"])
            self.assertNotIn("execution_outcome", rows[0])
            self.assertEqual("100", rows[0]["exit_price"])
            self.assertEqual("0", rows[0]["gross_return_bps"])
            self.assertEqual("1.0", rows[0]["time_to_event_seconds"])

    def test_v2_same_timestamp_barrier_conflict_is_conservatively_stop_loss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._v2_action()])
            self._write_jsonl(features_path, [
                self._feature("2026-01-01T00:00:01Z", "103"),
                self._feature("2026-01-01T00:00:01Z", "97"),
            ])
            contexts = [EpisodePathContext(parse_utc("2026-01-01T00:00:01Z"), "episode-1", "FAILED", True, ())]
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path), episode_contexts=contexts)
            self.assertEqual("SL", rows[0]["outcome"])

    def test_v2_unknown_episode_censors_instead_of_creating_structure_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._v2_action()])
            self._write_jsonl(features_path, [self._feature("2026-01-01T00:00:01Z", "100")])
            contexts = [EpisodePathContext(parse_utc("2026-01-01T00:00:01Z"), "episode-1", "UNKNOWN", True, ())]
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path), episode_contexts=contexts)
            self.assertTrue(rows[0]["censored"])
            self.assertIsNone(rows[0]["outcome"])
            self.assertEqual("DATA_EXECUTION_HALT", rows[0]["operational_override"])

    def test_v2_requires_healthy_path_coverage_before_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._v2_action()])
            self._write_jsonl(features_path, [self._feature("2026-01-01T00:00:01Z", "100")])
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path))
            self.assertTrue(rows[0]["censored"])
            self.assertIsNone(rows[0]["outcome"])
            self.assertEqual("DATA_COVERAGE_GAP", rows[0]["operational_override"])
            self.assertEqual("2026-01-01T00:00:01+00:00", rows[0]["label_end_at"])
            no_point_rows = generate_labels(load_actions(actions_path), [])
            self.assertEqual("2026-01-01T00:00:00+00:00", no_point_rows[0]["label_end_at"])

    def test_v2_deadline_price_is_a_barrier_before_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._v2_action()])
            self._write_jsonl(features_path, [self._feature("2026-01-01T00:01:00Z", "98")])
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path))
            self.assertEqual("SL", rows[0]["outcome"])
            self.assertFalse(rows[0]["censored"])
            self.assertEqual("98", rows[0]["exit_price"])
            self.assertEqual("-200.00", rows[0]["gross_return_bps"])
            self.assertEqual("60.0", rows[0]["time_to_event_seconds"])

    def test_v2_sell_barrier_reports_directional_gross_return(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            action = self._v2_action()
            action.update({"side": "SELL", "take_profit": "98", "stop_loss": "102"})
            self._write_jsonl(actions_path, [action])
            self._write_jsonl(features_path, [self._feature("2026-01-01T00:00:01Z", "98")])
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path))
            self.assertEqual("TP", rows[0]["outcome"])
            self.assertEqual("98", rows[0]["exit_price"])
            self.assertEqual("200.00", rows[0]["gross_return_bps"])

    def test_v2_structure_exit_uses_conservative_same_timestamp_mid_by_side(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            action = self._v2_action()
            action.update({"side": "SELL", "take_profit": "98", "stop_loss": "102"})
            self._write_jsonl(actions_path, [action])
            self._write_jsonl(features_path, [
                self._feature("2026-01-01T00:00:01Z", "99"),
                self._feature("2026-01-01T00:00:01Z", "101"),
            ])
            contexts = [EpisodePathContext(parse_utc("2026-01-01T00:00:01Z"), "episode-1", "FAILED", True, ())]
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path), episode_contexts=contexts)
            self.assertEqual("STRUCTURE_EXIT", rows[0]["outcome"])
            self.assertEqual("101", rows[0]["exit_price"])
            self.assertEqual("-100.00", rows[0]["gross_return_bps"])

    def test_v2_timeout_reports_path_extremes_without_execution_pnl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._v2_action()])
            self._write_jsonl(features_path, [
                self._feature("2026-01-01T00:00:01Z", "101"),
                self._feature("2026-01-01T00:01:00Z", "100"),
            ])
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path))
            self.assertEqual("TIMEOUT", rows[0]["outcome"])
            self.assertEqual("100", rows[0]["exit_price"])
            self.assertEqual("0", rows[0]["gross_return_bps"])
            self.assertEqual("100.00", rows[0]["mfe_bps"])
            self.assertEqual("0", rows[0]["mae_bps"])
            self.assertNotIn("execution_pnl", rows[0])

    def test_v2_global_quality_failure_censors_before_same_timestamp_barrier(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path, features_path = Path(temp_dir) / "actions.ndjson", Path(temp_dir) / "features.ndjson"
            self._write_jsonl(actions_path, [self._v2_action()])
            self._write_jsonl(features_path, [
                self._feature("2026-01-01T00:00:01Z", "98"),
                self._feature("2026-01-01T00:05:00Z", "100"),
            ])
            contexts = [EpisodePathContext(parse_utc("2026-01-01T00:00:01Z"), None, None, None, ("gap",))]
            rows = generate_labels(load_actions(actions_path), load_feature_prices(features_path), episode_contexts=contexts)
            self.assertTrue(rows[0]["censored"])
            self.assertIsNone(rows[0]["outcome"])
            self.assertEqual("DATA_EXECUTION_HALT", rows[0]["operational_override"])

    def test_v2_rejects_decision_and_market_entry_clock_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            actions_path = Path(temp_dir) / "actions.ndjson"
            action = self._v2_action()
            action["market_path_entry_at"] = "2026-01-01T00:00:01Z"
            self._write_jsonl(actions_path, [action])
            with self.assertRaises(ValueError):
                load_actions(actions_path)
