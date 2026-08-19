from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from trade_system.cli import main
from trade_system.event_store import EventStore
from trade_system.market_runtime import MarketRuntimeStats
from trade_system.account_telemetry import AccountTelemetryContract
from trade_system.paper_audit import PaperAuditTrail
from trade_system.source_registry import SourceRegistry
from trade_system.state_classifier import StateClassifier
from trade_system.types import AvailabilityKind, AvailabilityRecord, BookHealth, SystemHealth


class CliTests(unittest.TestCase):
    def _write_jsonl(self, path: Path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_label_command_writes_new_artifact_and_preserves_no_fill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            actions, features, output = root / "actions.ndjson", root / "features.ndjson", root / "labels.ndjson"
            self._write_jsonl(actions, [{
                "decision_id": "d-1", "episode_id": "e-1", "decision_at": "2026-01-01T00:00:00Z", "filled_at": "2026-01-01T00:00:00Z",
                "side": "BUY", "stage": "ENTER_PROBE", "entry_price": "100", "take_profit": "102", "stop_loss": "98", "horizon_seconds": 60,
                "execution_outcome": "NO_FILL", "fill_fraction": "0", "features": {"x": 1}, "state_id": "CALM",
            }])
            self._write_jsonl(features, [{
                "event_id": "f-1", "available_at": "2026-01-01T00:00:01Z", "availability_kind": "ACTUAL", "values": {"mid_price": "102"},
            }])
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["label-actions", "--actions", str(actions), "--features", str(features), "--output", str(output)])
            self.assertEqual(0, result)
            self.assertEqual(1, json.loads(stdout.getvalue())["no_fill"])
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertIsNone(written["outcome"])
            self.assertEqual("FEATURE_MID_PRICE", written["market_path_source"])
            self.assertEqual("CALM", written["state_id"])

    def test_label_command_accepts_v2_counterfactual_rows_without_execution_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            actions, features, output = root / "actions.ndjson", root / "features.ndjson", root / "labels.ndjson"
            self._write_jsonl(actions, [{
                "action_schema_version": "research-action-v2", "decision_id": "d-v2", "episode_id": "e-v2",
                "decision_at": "2026-01-01T00:00:00Z", "market_path_entry_at": "2026-01-01T00:00:00Z", "feature_event_id": "f-v2",
                "market_path_entry_assumption": "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY", "execution_evidence": False,
                "side": "BUY", "stage": "ENTER_PROBE", "entry_price": "100", "take_profit": "102", "stop_loss": "98", "horizon_seconds": 60,
                "features": {"x": 1}, "structure_exit_rule": {"episode_states": ["FAILED"], "require_decision_eligible": True, "unknown_or_data_failure": "OPERATIONAL_CENSOR"},
            }])
            self._write_jsonl(features, [{
                "event_id": "f-v2", "available_at": "2026-01-01T00:01:00Z", "availability_kind": "ACTUAL", "values": {"mid_price": "100"},
            }])
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["label-actions", "--actions", str(actions), "--features", str(features), "--output", str(output)])
            self.assertEqual(0, result)
            self.assertEqual(0, json.loads(stdout.getvalue())["no_fill"])
            self.assertEqual("TIMEOUT", json.loads(output.read_text(encoding="utf-8"))["outcome"])

    def test_demo_can_write_and_verify_a_finalized_paper_audit_trail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "paper-audit.ndjson"
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["demo", "--data-dir", str(root / "demo"), "--paper-audit", str(audit_path)])
            self.assertEqual(0, result)
            demo = json.loads(stdout.getvalue())
            self.assertEqual(str(audit_path), demo["paper"]["audit"]["path"])
            self.assertGreater(demo["paper"]["audit"]["event_count"], 1)
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["audit-paper-run", "--input", str(audit_path)])
            self.assertEqual(0, result)
            self.assertTrue(json.loads(stdout.getvalue())["valid"])

    def test_decision_shadow_command_requires_full_matching_binding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            offline, online = root / "offline.ndjson", root / "online.ndjson"
            row = {
                "event_id": "e-1", "decision_at": "2026-07-22T00:00:00Z", "feature_version": "f1",
                "model_version": "m1", "policy_version": "p1", "risk_profile_digest": "a" * 64,
                "decision": {"trade": False, "reason": "NEGATIVE_OR_INSUFFICIENT_EV", "ev_fill": "-1", "ev_submit": "-1.2"},
            }
            self._write_jsonl(offline, [row])
            self._write_jsonl(online, [row])
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["compare-shadow-decisions", "--offline", str(offline), "--online", str(online)])
            self.assertEqual(0, result)
            self.assertTrue(json.loads(stdout.getvalue())["passed"])
            changed = dict(row, model_version="m2")
            self._write_jsonl(online, [changed])
            with redirect_stdout(StringIO()):
                result = main(["compare-shadow-decisions", "--offline", str(offline), "--online", str(online)])
            self.assertEqual(1, result)

    def test_paper_recovery_command_is_fail_closed_and_verifiable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path, recovery_path = root / "paper.ndjson", root / "recovery.json"
            trail = PaperAuditTrail(audit_path, run_id="paper-cli-recovery", context={"scope": "TEST"})
            trail.append("HALT", {"state": {"orders": {}}})
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main([
                    "recover-paper-run", "--input", str(audit_path), "--output", str(recovery_path),
                    "--confirm-process-stopped",
                ])
            self.assertEqual(1, result)
            self.assertEqual("HALT_AND_RECONCILE_REQUIRED", json.loads(stdout.getvalue())["recovery_status"])
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["verify-paper-recovery", "--input", str(recovery_path), "--audit", str(audit_path)])
            self.assertEqual(0, result)
            self.assertTrue(json.loads(stdout.getvalue())["valid"])

    def test_account_telemetry_audit_command_is_offline_and_contract_bound(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path = Path(__file__).resolve().parents[1] / "config" / "account_telemetry_contract.v1.json"
            contract = AccountTelemetryContract.load(contract_path)
            telemetry_path = root / "telemetry.ndjson"
            telemetry_path.write_text(json.dumps({
                "record_type": "normalized_account_telemetry", "contract_id": contract.contract_id,
                "contract_sha256": contract.sha256, "event_name": "rest_recovery_snapshot",
                "local_receive_time": "2026-07-22T00:00:01Z", "source_as_of": "2026-07-22T00:00:00Z",
                "open_orders": [], "positions": [{"instrument": "BTCUSDT", "position_quantity": "0"}],
                "balances": [], "commission_schedule": {}, "income_history_cursor": None,
                "raw_payload_sha256": "a" * 64,
            }) + "\n", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["audit-account-telemetry", "--input", str(telemetry_path), "--contract", str(contract_path)])
            self.assertEqual(0, result)
            self.assertEqual(1, json.loads(stdout.getvalue())["event_counts"]["rest_recovery_snapshot"])

    def test_normalize_account_telemetry_command_never_needs_network_or_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path = Path(__file__).resolve().parents[1] / "config" / "account_telemetry_contract.v1.json"
            source, output = root / "source.ndjson", root / "normalized.ndjson"
            source.write_text(json.dumps({
                "record_type": "sanitized_private_source_event", "source_schema_version": "binance-usdm-private.v1",
                "source_kind": "BINANCE_USDM_PRIVATE_REST_RECOVERY", "local_receive_time": "2026-07-22T00:00:01Z",
                "payload": {"source_as_of": 1784678400000, "open_orders": [],
                    "positions": [{"symbol": "BTCUSDT", "positionAmt": "0"}],
                    "balances": [{"asset": "USDT", "balance": "100", "availableBalance": "100"}],
                    "commission_schedule": {}, "income_history_cursor": None},
            }) + "\n", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["normalize-account-telemetry", "--input", str(source), "--output", str(output), "--contract", str(contract_path)])
            self.assertEqual(0, result)
            report = json.loads(stdout.getvalue())
            self.assertEqual(1, report["normalized_row_count"])
            self.assertTrue(output.exists())

    def test_research_command_rejects_label_set_without_eligible_market_outcome(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            labels = Path(temp_dir) / "labels.ndjson"
            self._write_jsonl(labels, [{"episode_id": "e", "decision_at": "2026-01-01T00:00:00Z", "label_end_at": None, "features": {}, "outcome": None, "censored": False}])
            self.assertEqual(2, main(["research-baseline", "--input", str(labels)]))

    def test_frozen_research_stops_for_insufficient_state_coverage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            labels, protocol, classifier_path = root / "labels.ndjson", root / "protocol.json", root / "classifier.json"
            classifier_path.write_text(json.dumps({
                "classifier_id": "regime-v1", "status": "FROZEN_STATE_CLASSIFIER", "fallback_state_id": "STRESSED",
                "rules": [{"state_id": "CALM", "all": [{"feature": "pressure", "min": 0}]}],
            }), encoding="utf-8")
            classifier = StateClassifier.load(classifier_path)
            self._write_jsonl(labels, [{
                "episode_id": "e-1", "decision_at": "2026-01-01T00:00:00Z", "label_end_at": "2026-01-01T00:01:00Z",
                "features": {"pressure": 1}, "outcome": "TP", "censored": False, "state_id": "CALM",
                "state_classifier_id": classifier.classifier_id, "state_classifier_sha256": classifier.digest,
            }])
            protocol.write_text(json.dumps({
                "protocol_id": "frozen-v1", "status": "FROZEN_RESEARCH_PROTOCOL", "notice": "fixed", "frozen_at": "2026-01-01T00:00:00Z",
                "availability_policy": {"allow_actual": True, "allow_reconstructed_for_g2": False},
                "source_registry": {"registry_id": "source-registry.v3", "sha256": "a" * 64},
                "risk_gate_profile": {"profile_id": "paper-risk-gate-profile.v1", "digest": "b" * 64},
                "data_eligibility": {"required_g1_policy_id": "g1.v1", "required_g1_report_sha256": "c" * 64, "require_g1_pass": True},
                "action_contract": {"labels": ["TP", "SL", "STRUCTURE_EXIT", "TIMEOUT"]},
                "execution_priors": {"latency_ms": 10, "fee_rate": 0, "funding_policy": "recorded", "cost_scenarios": ["normal"]},
                "data_sources": [{"source_id": "SRC", "endpoint_or_channel": "x", "schema_version": "v1", "instrument": "BTCUSDT", "allowed_availability": "ACTUAL_ONLY"}],
                "episode_policy": {"trigger": "x", "decision_frequency_seconds": 1, "max_holding_seconds": 60, "overlap_policy": "no overlap"},
                "label_policy": {"barrier_rules": "fixed", "same_timestamp_rule": "worst case", "operational_override_rule": "censor"},
                "evaluation_policy": {"primary_metrics": ["log_loss"], "min_effective_episodes": 2, "calibration_rule": "fixed", "cost_after_utility_rule": "fixed", "confidence_interval_rule": "fixed", "concentration_limits": "fixed"},
                "state_coverage_policy": {"classifier_id": classifier.classifier_id, "classifier_digest": classifier.digest, "required_state_ids": ["CALM", "STRESSED"], "min_effective_episodes_per_state": 2, "insufficient_coverage_result": "INCONCLUSIVE/WAIT_DATA"},
                "split_policy": {"folds": 1, "embargo_seconds": 60, "training_calibration_policy": "walk-forward", "final_holdout": {"holdout_id": "h1", "start": "2026-04-01T00:00:00Z", "end": "2026-06-01T00:00:00Z", "opened_at": None, "reuse_policy": "ONE_TIME_ONLY"}},
                "hypotheses": [{"hypothesis_id": "H-001", "pass_condition": "fixed", "failure_condition": "fixed"}],
            }), encoding="utf-8")
            state_bundle = {
                "manifest_sha256": "f" * 64,
                "label_bundle_manifest_sha256": "g" * 64,
                "g1_policy_id": "g1.v1",
                "g1_report_sha256": "e" * 64,
                "state_classifier_id": classifier.classifier_id,
                "state_classifier_sha256": classifier.digest,
            }
            self._write_jsonl(labels, [{
                "episode_id": "holdout-row", "decision_at": "2026-04-02T00:00:00Z", "label_end_at": "2026-04-02T00:01:00Z",
                "features": {"pressure": 1}, "outcome": "TP", "censored": False, "state_id": "CALM",
                "state_classifier_id": classifier.classifier_id, "state_classifier_sha256": classifier.digest,
            }])
            with patch("trade_system.cli.load_passed_g1_report", return_value={"report_sha256": "e" * 64}), patch("trade_system.cli.load_verified_state_label_bundle_manifest", return_value=state_bundle), redirect_stderr(StringIO()):
                holdout_rejected = main([
                    "research-baseline", "--input", str(labels), "--protocol", str(protocol),
                    "--require-frozen-protocol", "--g1-report", str(root / "g1-pass.json"), "--state-classifier", str(classifier_path), "--labels-manifest", str(root / "state-labels.manifest.json"), "--output", str(root / "holdout-rejected.json"),
                ])
            self.assertEqual(2, holdout_rejected)
            self._write_jsonl(labels, [{
                "episode_id": "e-1", "decision_at": "2026-01-01T00:00:00Z", "label_end_at": "2026-01-01T00:01:00Z",
                "features": {"pressure": 1}, "outcome": "TP", "censored": False, "state_id": "CALM",
                "state_classifier_id": classifier.classifier_id, "state_classifier_sha256": classifier.digest,
            }])
            with patch("trade_system.cli.load_passed_g1_report", return_value={"report_sha256": "e" * 64}), redirect_stderr(StringIO()):
                missing_manifest = main([
                    "research-baseline", "--input", str(labels), "--protocol", str(protocol),
                    "--require-frozen-protocol", "--g1-report", str(root / "g1-pass.json"),
                    "--state-classifier", str(classifier_path), "--output", str(root / "missing-manifest-report.json"),
                ])
            self.assertEqual(2, missing_manifest)
            stdout = StringIO()
            with patch("trade_system.cli.load_passed_g1_report", return_value={"report_sha256": "e" * 64}), patch("trade_system.cli.load_verified_state_label_bundle_manifest", return_value=state_bundle), redirect_stdout(stdout):
                result = main([
                    "research-baseline", "--input", str(labels), "--protocol", str(protocol),
                    "--require-frozen-protocol", "--g1-report", str(root / "g1-pass.json"), "--state-classifier", str(classifier_path), "--labels-manifest", str(root / "state-labels.manifest.json"), "--output", str(root / "coverage-report.json"),
                ])
            self.assertEqual(1, result)
            output = json.loads(stdout.getvalue())
            self.assertEqual("INCONCLUSIVE/WAIT_DATA", output["research_status"])
            self.assertEqual(["CALM", "STRESSED"], output["state_coverage"]["missing_state_ids"])
            self.assertNotIn("mean_log_loss", output)
            self.assertTrue((root / "coverage-report.json").exists())

            # Once every frozen state has enough rows, the separate global
            # effective-episode floor still blocks training before folds run.
            self._write_jsonl(labels, [
                {
                    "episode_id": "e-1", "decision_at": "2026-01-01T00:00:00Z", "label_end_at": "2026-01-01T00:01:00Z",
                    "features": {"pressure": 1}, "outcome": "TP", "censored": False, "state_id": "CALM",
                    "state_classifier_id": classifier.classifier_id, "state_classifier_sha256": classifier.digest,
                },
                {
                    "episode_id": "e-2", "decision_at": "2026-01-01T00:02:00Z", "label_end_at": "2026-01-01T00:03:00Z",
                    "features": {"pressure": -1}, "outcome": "SL", "censored": False, "state_id": "STRESSED",
                    "state_classifier_id": classifier.classifier_id, "state_classifier_sha256": classifier.digest,
                },
            ])
            frozen = json.loads(protocol.read_text(encoding="utf-8"))
            frozen["state_coverage_policy"]["min_effective_episodes_per_state"] = 1
            frozen["evaluation_policy"]["min_effective_episodes"] = 3
            protocol.write_text(json.dumps(frozen), encoding="utf-8")
            stdout = StringIO()
            with patch("trade_system.cli.load_passed_g1_report", return_value={"report_sha256": "e" * 64}), patch("trade_system.cli.load_verified_state_label_bundle_manifest", return_value=state_bundle), redirect_stdout(stdout):
                result = main([
                    "research-baseline", "--input", str(labels), "--protocol", str(protocol),
                    "--require-frozen-protocol", "--g1-report", str(root / "g1-pass.json"), "--state-classifier", str(classifier_path), "--labels-manifest", str(root / "state-labels.manifest.json"), "--output", str(root / "episode-report.json"),
                ])
            self.assertEqual(1, result)
            output = json.loads(stdout.getvalue())
            self.assertEqual("effective episode count below frozen protocol minimum", output["reason"])
            self.assertTrue(output["state_coverage"]["passed"])
            self.assertNotIn("mean_log_loss", output)

            with patch("trade_system.cli.load_passed_g1_report", return_value={"report_sha256": "e" * 64}), patch("trade_system.cli.load_verified_state_label_bundle_manifest", return_value=state_bundle):
                mismatch = main([
                    "research-baseline", "--input", str(labels), "--protocol", str(protocol),
                    "--require-frozen-protocol", "--g1-report", str(root / "g1-pass.json"),
                    "--state-classifier", str(classifier_path), "--labels-manifest", str(root / "state-labels.manifest.json"), "--folds", "2", "--output", str(root / "mismatch-report.json"),
                ])
            self.assertEqual(2, mismatch)

    def test_frozen_v2_research_uses_nested_g1_qualification_without_v1_shape_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = Path(__file__).resolve().parents[1]
            classifier_path = workspace / "config" / "state_classifier.v1.json"
            classifier = StateClassifier.load(classifier_path)
            raw = json.loads((workspace / "config" / "research_protocol.v2.draft.json").read_text(encoding="utf-8"))
            raw["status"] = "FROZEN_RESEARCH_PROTOCOL"
            raw["frozen_at"] = "2026-07-30T00:00:00Z"
            raw["data_eligibility"]["g1_qualification"]["required_g1_report_sha256"] = "e" * 64
            for role in raw["data_eligibility"]["admitted_collection_roles"]:
                role["capture_plan"] = {"id": role["role"].lower() + "-plan", "sha256": "a" * 64}
                role["acceptance_policy"] = {"id": role["role"].lower() + "-policy", "sha256": "b" * 64}
                role["quality_equivalence"]["comparison_rule"] = "EQUAL_OR_STRICTER_THAN_G1"
            raw["context_evidence"] = {"policy": {"id": "test-context", "sha256": "d" * 64}, "artifact": {"sha256": "e" * 64, "manifest_sha256": "f" * 64}, "role_window": {"id": "test-window", "sha256": "a" * 64}, "archive_receipts": {"schema_version": "evidence-archive-receipt.v1", "require_verified_per_collection": True}}
            raw["data_eligibility"]["admitted_collection_roles"][0]["time_window"] = {
                "decision_start": "2026-08-01T00:00:00Z", "decision_end": "2026-08-31T00:00:00Z", "label_horizon_seconds": 300,
            }
            for binding in raw["software_bindings"].values():
                binding["component_id"] = "component.v2"
                binding["source_sha256"] = "c" * 64
            protocol_path = root / "frozen-v2.json"
            protocol_path.write_text(json.dumps(raw), encoding="utf-8")
            labels_path = root / "labels.ndjson"
            features = {"visible_depth_notional": 1000000}
            self._write_jsonl(labels_path, [{
                "episode_id": "v2-e1", "decision_at": "2026-01-01T00:00:00Z", "label_end_at": "2026-01-01T00:01:00Z",
                "features": features, "outcome": "TP", "censored": False, "state_id": classifier.classify(features),
                "state_classifier_id": classifier.classifier_id, "state_classifier_sha256": classifier.digest,
            }])
            state_bundle = {
                "manifest_sha256": "f" * 64, "label_bundle_manifest_sha256": "g" * 64,
                "g1_policy_id": raw["data_eligibility"]["g1_qualification"]["required_g1_policy_id"],
                "g1_report_sha256": "e" * 64,
            }
            stdout = StringIO()
            with patch("trade_system.cli.load_passed_g1_report", return_value={"report_sha256": "e" * 64}), patch("trade_system.cli.load_verified_state_label_bundle_manifest", return_value=state_bundle), patch("trade_system.cli.load_verified_research_evidence_admission", return_value={"manifest_sha256": "h" * 64}), redirect_stdout(stdout):
                result = main([
                    "research-baseline", "--input", str(labels_path), "--protocol", str(protocol_path),
                    "--require-frozen-protocol", "--g1-report", str(root / "g1.json"), "--state-classifier", str(classifier_path),
                    "--labels-manifest", str(root / "labels.manifest.json"), "--evidence-admission", str(root / "development-admission.json"), "--output", str(root / "report.json"),
                ])
            self.assertEqual(1, result)
            self.assertEqual("INCONCLUSIVE/WAIT_DATA", json.loads(stdout.getvalue())["research_status"])

    def test_assign_states_writes_new_classifier_bound_label_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            labels, classifier, output = root / "labels.ndjson", root / "classifier.json", root / "state-labels.ndjson"
            self._write_jsonl(labels, [{"episode_id": "e", "features": {"price_impact": -0.0001}, "outcome": "TP"}])
            classifier.write_text(json.dumps({
                "classifier_id": "impact-regime.v1", "status": "FROZEN_STATE_CLASSIFIER", "fallback_state_id": "STRESSED",
                "rules": [{"state_id": "CALM", "all": [{"feature": "price_impact", "max": 0.001, "absolute": True}]}],
            }), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["assign-states", "--input", str(labels), "--classifier", str(classifier), "--output", str(output)])
            self.assertEqual(0, result)
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("CALM", row["state_id"])
            self.assertEqual("impact-regime.v1", row["state_classifier_id"])
            self.assertEqual(json.loads(stdout.getvalue())["classifier_sha256"], row["state_classifier_sha256"])

    def test_interrupted_public_capture_writes_unqualified_terminal_manifest(self):
        class InterruptedRuntime:
            def __init__(self, **_kwargs):
                self.stats = MarketRuntimeStats()
                self.book = SimpleNamespace(health=BookHealth.INVALID)
                self.quality = SimpleNamespace(evaluate=lambda _now: SystemHealth.HALTED)

            async def run(self, **_kwargs):
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stdout = StringIO()
            with patch("trade_system.cli.BinancePublicMarketRuntime", InterruptedRuntime), redirect_stdout(stdout):
                result = main([
                    "collect-public", "--data-dir", str(root / "data"), "--connection-id", "interrupted-1",
                    "--duration-seconds", "60", "--live-feature-output", "derived/live.ndjson",
                ])
            self.assertEqual(130, result)
            output = json.loads(stdout.getvalue())
            manifest = json.loads(Path(output["collection_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual("UNQUALIFIED", manifest["collection_result"])
            self.assertTrue(any("interrupted" in item for item in manifest["errors"]))
            self.assertEqual("PARTIAL_EXCLUDED", manifest["live_feature_artifact"]["status"])
            self.assertTrue(Path(manifest["live_feature_artifact"]["partial_path"]).exists())
            self.assertFalse((root / "data" / "derived" / "live.ndjson").exists())

    def test_public_capture_binds_a_predeclared_forward_slot_into_manifest(self):
        class InterruptedRuntime:
            def __init__(self, **_kwargs):
                self.stats = MarketRuntimeStats()
                self.book = SimpleNamespace(health=BookHealth.INVALID)
                self.quality = SimpleNamespace(evaluate=lambda _now: SystemHealth.HALTED)

            async def run(self, **_kwargs):
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = SourceRegistry.load(Path(__file__).resolve().parents[1] / "config" / "source_registry.v3.json")
            now = datetime.now(timezone.utc)
            plan = root / "forward-plan.json"
            plan.write_text(json.dumps({
                "plan_id": "forward-plan.v1",
                "status": "FROZEN_FORWARD_CAPTURE_PLAN",
                "frozen_at": (now - timedelta(minutes=1)).isoformat(),
                "instrument": "BTCUSDT",
                "source_registry": {"registry_id": registry.registry_id, "sha256": registry.sha256},
                "slots": [{
                    "slot_id": "current-slot",
                    "start": (now - timedelta(minutes=1)).isoformat(),
                    "end": (now + timedelta(minutes=2)).isoformat(),
                    "min_duration_seconds": 60,
                    "coverage_intent": ["UTC_SCHEDULED", "FORWARD_ONLY"],
                }],
            }), encoding="utf-8")
            stdout = StringIO()
            with patch("trade_system.cli.BinancePublicMarketRuntime", InterruptedRuntime), redirect_stdout(stdout):
                result = main([
                    "collect-public", "--data-dir", str(root / "data"), "--connection-id", "planned-1",
                    "--duration-seconds", "60", "--capture-plan", str(plan), "--capture-slot", "current-slot",
                ])
            self.assertEqual(130, result)
            manifest = json.loads(Path(json.loads(stdout.getvalue())["collection_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual("forward-plan.v1", manifest["capture_plan"]["plan_id"])
            self.assertEqual("current-slot", manifest["capture_plan"]["slot_id"])

    def test_planned_public_capture_reserves_isolated_store_and_seals_on_success(self):
        def successful_collect(args):
            store = EventStore(Path(args.data_dir))
            received = datetime.now(timezone.utc)
            raw = store.append_raw(
                source="TEST", venue="BINANCE_USDM", instrument="BTCUSDT", stream="test",
                connection_id=args.connection_id + "-market", ingest_seq=1, payload={"ok": True}, receive_time=received,
            )
            store.append_availability(raw, AvailabilityRecord(
                event_id=raw.event_id, schema_version="test", derived_at=received, available_at=received,
                availability_kind=AvailabilityKind.ACTUAL, normalized={"kind": "test"},
            ))
            audit_valid, audit_issues, audit_digest = store.audit()
            manifest = store.write_collection_manifest(args.connection_id, {
                "collection_result": "QUALIFIED_SMOKE", "instrument": "BTCUSDT", "raw_captured": 1,
                "availability_written": 1, "parse_errors": 0, "book_gaps": 0, "errors": [], "reconnects": {},
                "audit_valid": audit_valid, "audit_issues": audit_issues, "audit_digest": audit_digest,
            })
            return {"collection_manifest": str(manifest), "raw_captured": 1}, 0

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = SourceRegistry.load(Path(__file__).resolve().parents[1] / "config" / "source_registry.v3.json")
            now = datetime.now(timezone.utc)
            plan = root / "forward-plan.json"
            plan.write_text(json.dumps({
                "plan_id": "automatic-plan.v1", "status": "FROZEN_FORWARD_CAPTURE_PLAN",
                "frozen_at": (now - timedelta(minutes=2)).isoformat(), "instrument": "BTCUSDT",
                "source_registry": {"registry_id": registry.registry_id, "sha256": registry.sha256},
                "slots": [{
                    "slot_id": "slot-now", "start": (now - timedelta(minutes=1)).isoformat(),
                    "end": (now + timedelta(minutes=2)).isoformat(), "min_duration_seconds": 60,
                    "coverage_intent": ["UTC_SCHEDULED", "FORWARD_ONLY"],
                }],
            }), encoding="utf-8")
            stdout = StringIO()
            with patch("trade_system.cli._collect_public", successful_collect), redirect_stdout(stdout):
                result = main([
                    "collect-planned-public", "--capture-plan", str(plan), "--capture-slot", "slot-now",
                    "--data-root", str(root / "runtime"),
                ])
            self.assertEqual(0, result)
            output = json.loads(stdout.getvalue())
            self.assertEqual("QUALIFIED_SMOKE_SEALED", output["status"])
            target = root / "runtime" / "automatic-plan.v1" / "slot-now"
            self.assertEqual(1, len(list((target / "manifests" / "raw").glob("*.json"))))
            self.assertTrue((target / "manifests" / "collection" / "automatic-plan.v1-slot-now.json").exists())
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                rerun = main([
                    "collect-planned-public", "--capture-plan", str(plan), "--capture-slot", "slot-now",
                    "--data-root", str(root / "runtime"),
                ])
            self.assertEqual(2, rerun)

    def test_planned_public_capture_never_seals_an_interrupted_slot(self):
        class InterruptedRuntime:
            def __init__(self, **_kwargs):
                self.stats = MarketRuntimeStats()
                self.book = SimpleNamespace(health=BookHealth.INVALID)
                self.quality = SimpleNamespace(evaluate=lambda _now: SystemHealth.HALTED)

            async def run(self, **_kwargs):
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = SourceRegistry.load(Path(__file__).resolve().parents[1] / "config" / "source_registry.v3.json")
            now = datetime.now(timezone.utc)
            plan = root / "forward-plan.json"
            plan.write_text(json.dumps({
                "plan_id": "interrupted-plan.v1", "status": "FROZEN_FORWARD_CAPTURE_PLAN",
                "frozen_at": (now - timedelta(minutes=2)).isoformat(), "instrument": "BTCUSDT",
                "source_registry": {"registry_id": registry.registry_id, "sha256": registry.sha256},
                "slots": [{
                    "slot_id": "slot-now", "start": (now - timedelta(minutes=1)).isoformat(),
                    "end": (now + timedelta(minutes=2)).isoformat(), "min_duration_seconds": 60,
                    "coverage_intent": ["UTC_SCHEDULED", "FORWARD_ONLY"],
                }],
            }), encoding="utf-8")
            stdout = StringIO()
            with patch("trade_system.cli.BinancePublicMarketRuntime", InterruptedRuntime), redirect_stdout(stdout):
                result = main([
                    "collect-planned-public", "--capture-plan", str(plan), "--capture-slot", "slot-now",
                    "--data-root", str(root / "runtime"),
                ])
            self.assertEqual(130, result)
            output = json.loads(stdout.getvalue())
            self.assertEqual("UNQUALIFIED_NOT_SEALED", output["status"])
            target = root / "runtime" / "interrupted-plan.v1" / "slot-now"
            self.assertFalse(list((target / "manifests" / "raw").glob("*.json")))

    def test_planned_public_capture_records_setup_failure_after_reserving_slot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = SourceRegistry.load(Path(__file__).resolve().parents[1] / "config" / "source_registry.v3.json")
            now = datetime.now(timezone.utc)
            plan = root / "forward-plan.json"
            plan.write_text(json.dumps({
                "plan_id": "setup-failure-plan.v1", "status": "FROZEN_FORWARD_CAPTURE_PLAN",
                "frozen_at": (now - timedelta(minutes=2)).isoformat(), "instrument": "BTCUSDT",
                "source_registry": {"registry_id": registry.registry_id, "sha256": registry.sha256},
                "slots": [{
                    "slot_id": "slot-now", "start": (now - timedelta(minutes=1)).isoformat(),
                    "end": (now + timedelta(minutes=2)).isoformat(), "min_duration_seconds": 60,
                    "coverage_intent": ["UTC_SCHEDULED", "FORWARD_ONLY"],
                }],
            }), encoding="utf-8")
            stdout = StringIO()
            with patch("trade_system.cli._collect_public", side_effect=RuntimeError("local setup failure")), redirect_stdout(stdout):
                result = main([
                    "collect-planned-public", "--capture-plan", str(plan), "--capture-slot", "slot-now",
                    "--data-root", str(root / "runtime"),
                ])
            self.assertEqual(1, result)
            output = json.loads(stdout.getvalue())
            self.assertEqual("UNQUALIFIED_NOT_SEALED", output["status"])
            manifest = json.loads(Path(output["collection_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual("UNQUALIFIED", manifest["collection_result"])
            self.assertIn("planned collector setup failure", manifest["errors"][0])

    def test_orphan_capture_recovery_requires_confirmation_and_stays_unqualified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            store = EventStore(data_dir)
            store.append_raw(
                source="BINANCE_USDM", venue="BINANCE_USDM", instrument="BTCUSDT", stream="btcusdt@depth@100ms",
                connection_id="orphan-1-depth", ingest_seq=1, payload={"orphan": True},
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main([
                    "recover-interrupted-collection", "--data-dir", str(data_dir), "--connection-id", "orphan-1",
                    "--reason", "supervisor lost terminal process", "--confirm-stopped",
                ])
            self.assertEqual(1, result)
            output = json.loads(stdout.getvalue())
            manifest = json.loads(Path(output["collection_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual("UNQUALIFIED", manifest["collection_result"])
            self.assertEqual("RECOVERED_UNQUALIFIED", manifest["recovery"]["status"])

    def test_seal_collection_seals_all_utc_date_segments_after_terminal_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = EventStore(root / "data")
            for index, received in enumerate((
                datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc),
                datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc),
            ), start=1):
                store.append_raw(
                    source="TEST", venue="TEST", instrument="BTCUSDT", stream="test",
                    connection_id="midnight-1-depth", ingest_seq=index, payload={"n": index}, receive_time=received,
                )
            store.write_collection_manifest("midnight-1", {"collection_result": "UNQUALIFIED"})
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main([
                    "seal-collection", "--data-dir", str(root / "data"), "--collection-id", "midnight-1",
                    "--confirm-no-other-writers",
                ])
            self.assertEqual(0, result)
            output = json.loads(stdout.getvalue())
            self.assertEqual(["2026-01-01", "2026-01-02"], output["segments"])
            self.assertTrue((store.manifest_root / "2026-01-01.json").exists())
            self.assertTrue((store.manifest_root / "2026-01-02.json").exists())
