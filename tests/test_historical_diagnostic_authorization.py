import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from trade_system.historical_diagnostic_authorization import (
    HistoricalDiagnosticAuthorizationError,
    _audit_archive_csv,
    build_input_acquisition_receipt,
    build_pre_download_absence_inventory,
    canonical_sha256,
    consume_fresh_scoring_authorization,
    get_authorization_registry_entry,
    register_ready_to_score,
    register_wait_data_not_scored,
    sha256_file,
    verify_acquisition_receipt,
    verify_pre_download_absence_inventory,
    verify_pre_download_authorization_receipt,
)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


class HistoricalDiagnosticAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan_path = self.root / "config/plan.json"
        source_plan = Path(__file__).resolve().parents[1] / "config/binance_cm_historical_diagnostic.v2.frozen_before_download.json"
        self.plan = json.loads(source_plan.read_text(encoding="utf-8"))
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_path.write_bytes(source_plan.read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def _binding(self, path):
        return {"path": str(path.relative_to(self.root)), "sha256": sha256_file(path)}

    def _authorization_fixture(self):
        inventory = build_pre_download_absence_inventory(self.plan_path, workspace_root=self.root, download_root="inputs/february")
        for filename in ("ledger.json", "ledger-verification.json", "jan-v2-rows.json", "jan-v2-model.json", "runner.py", "evaluator.py", "package.py", "tests.txt"):
            path = self.root / "evidence" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(filename, encoding="utf-8")
        model_path = self.root / "evidence/jan-v2-model.json"
        def model(names): return {"feature_names": names, "scaler":{"means":[0.0]*len(names),"scales":[1.0]*len(names)}, "weights":[[0.0]*(len(names)+1) for _ in range(3)]}
        model_path.write_text(json.dumps({"models":{"BUY":{"candidate":model(["D","R","response_persistent","price_decelerates"]),"control":model(["D"]),"timeout_payoff_bps_fit_only":0.0},"SELL":{"candidate":model(["D","R","response_persistent","price_decelerates"]),"control":model(["D"]),"timeout_payoff_bps_fit_only":0.0}}}),encoding="utf-8")
        policy = {key: {"id": key, "path": "evidence/%s" % filename, "sha256": sha256_file(self.root / "evidence" / filename)} for key, filename in (("candidate_model", "runner.py"), ("control_model", "runner.py"), ("calibration", "runner.py"), ("payoff_policy", "runner.py"), ("selection_policy", "runner.py"), ("evaluation_policy", "runner.py"), ("runner", "runner.py"), ("evaluator", "evaluator.py"), ("package", "package.py"), ("test_report", "tests.txt"))}
        project = Path(__file__).resolve().parents[1]
        artifact_paths = [".runtime/historical-experiments/binance-cm-2025-01-v4-final.rows.ndjson", ".runtime/historical-experiments/binance-cm-2025-01-v4-final.model.json", ".runtime/historical-experiments/binance-cm-2025-01-v4-final.manifest.json"]
        for relative in artifact_paths:
            target = self.root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.symlink_to(project / relative)
        rows_path, model_path, manifest_path = (self.root / relative for relative in artifact_paths)
        rows_binding, model_binding, manifest_binding = self._binding(rows_path), self._binding(model_path), self._binding(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        receipt = {"record_type": "pre_download_authorization_receipt.v1", "status": "AUTHORIZED", "receipt_id": "fixture-receipt", "sol_decision_id": "SOL-S0-009-FEB2025-FRESH-FALSIFICATION-85A95D08-R1", "frozen_design": self._binding(self.plan_path), "frozen_design_canonical_sha256": "85a95d0845ca0c78b9bc3be12d8dcafd051625fab5be318398ace2f92531087b", "absence_inventory": inventory, "v1_ledger": self._binding(self.root / "evidence/ledger.json"), "v1_ledger_verification_report": self._binding(self.root / "evidence/ledger-verification.json"), "january_v2_development_evidence": {"manifest_id": manifest["manifest_id"], "row_count": manifest["row_count"], "manifest": manifest_binding, "rows_artifact": rows_binding, "model":model_binding}, "model_and_policy": policy, "authorized_targets": inventory["targets"], "download_limits": {"max_archive_bytes_each": 1024 * 1024, "max_total_archive_bytes": 84 * 1024 * 1024}, "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}
        receipt["receipt_scope_sha256"] = canonical_sha256(receipt)
        contract = {"record_type": "authorized_execution_contract.v2", "status": "AUTHORIZED_RECEIPT_BOUND", "contract_id": "fixture-contract", "frozen_design": self._binding(self.plan_path), "authorization_receipt": {"path": "evidence/receipt.json", "receipt_id": receipt["receipt_id"], "receipt_scope_sha256": receipt["receipt_scope_sha256"]}, "eligible_for_binance_g2": False, "trading_authorization": "DENIED"}
        contract_path = self.root / "evidence/contract.json"; _write(contract_path, contract)
        receipt["authorized_execution_contract"] = dict(self._binding(contract_path), contract_id="fixture-contract")
        receipt_path = self.root / "evidence/receipt.json"; _write(receipt_path, receipt)
        return receipt_path, receipt

    def _acquisition_fixture(self, receipt_path, receipt):
        for target in receipt["authorized_targets"]:
            archive = self.root / target["archive_path"]; archive.parent.mkdir(parents=True, exist_ok=True)
            day = int(target["date"][-2:]); start_ms = int(datetime(2025, 2, day, tzinfo=timezone.utc).timestamp() * 1000); end_ms = start_ms + 86400000 - 1
            def utc_text(timestamp): return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if target["kind"] == "aggTrades":
                header = "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker"
                # One real post-pressure candidate per day: a prior trade,
                # concentrated BUY pressure, a response trade, and a complete
                # five-minute entry/path cadence.  The remaining daily gap is
                # intentional event sparsity, not an acquisition-cadence gap.
                observations = [(299000, 100.0, 1.0), (330000, 100.0, 50000.0), (630000, 100.0, 1.0)]
                observations += [(second * 1000, 100.0, 1.0) for second in range(690, 991, 30)]
                observations.append((86400000 - 5000, 100.0, 1.0))
                rows = ["%d,%s,%s,%d,%d,%d,false" % (index, price, quantity, index, index, start_ms + offset) for index, (offset, price, quantity) in enumerate(observations, 1)]
            elif target["kind"] == "bookDepth":
                header = "timestamp,percentage,depth,notional"
                # The frozen response window needs two strictly post-pressure
                # snapshots.  Thirty-second cadence supplies them without
                # relying on a synthetic scorer patch.
                rows = ["%s,%d,1000000,1" % (utc_text(timestamp), level) for timestamp in list(range(start_ms, start_ms + 86400000, 30000)) + [end_ms] for level in (-1, 1)]
            else:
                header = "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio"
                rows = ["%s,BTCUSD_PERP,1,1,1,1,1,1" % utc_text(timestamp) for timestamp in list(range(start_ms, start_ms + 86400000, 300000)) + [end_ms]]
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
                handle.writestr(archive.with_suffix(".csv").name, header + "\n" + "\n".join(rows) + "\n")
            checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        path = self.root / "evidence/acquisition.json"
        build_input_acquisition_receipt(self.plan_path, receipt_path, path, workspace_root=self.root)
        return path

    def test_exact_absence_inventory_refuses_existing_target_and_summary_drift(self):
        inventory = build_pre_download_absence_inventory(self.plan_path, workspace_root=self.root, download_root="inputs/february")
        self.assertEqual(84, inventory["target_count"])
        self.assertEqual(168, len(inventory["targets"]) * 2)
        self.assertTrue(verify_pre_download_absence_inventory(inventory, plan_path=self.plan_path, workspace_root=self.root)["verified"])
        bad = dict(inventory); bad["target_count"] = 83
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            verify_pre_download_absence_inventory(bad, plan_path=self.plan_path, workspace_root=self.root)
        present = self.root / inventory["targets"][0]["archive_path"]; present.parent.mkdir(parents=True); present.write_bytes(b"x")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            build_pre_download_absence_inventory(self.plan_path, workspace_root=self.root, download_root="inputs/february")

    def test_wait_data_is_terminal_and_ready_to_score_consumes_once(self):
        receipt_path, receipt = self._authorization_fixture()
        self.assertTrue(verify_pre_download_authorization_receipt(receipt_path, plan_path=self.plan_path, workspace_root=self.root)["verified"])
        acquisition_path = self._acquisition_fixture(receipt_path, receipt)
        self.assertEqual(84, verify_acquisition_receipt(acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root)["archive_count"])
        registry = self.root / "evidence/registry.json"; summary = hashlib.sha256(b"frozen scoring summary").hexdigest()
        waiting = register_wait_data_not_scored(registry, receipt_id=receipt["receipt_id"], receipt_scope_sha256=receipt["receipt_scope_sha256"], summary_sha256=summary)
        self.assertEqual("WAIT_DATA_NOT_SCORED", waiting["status"])
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            consume_fresh_scoring_authorization(registry, acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root, summary_sha256=summary, scoring_attempt_id="must-not-score-wait")
        self.assertEqual("WAIT_DATA_NOT_SCORED", get_authorization_registry_entry(registry, receipt_id=receipt["receipt_id"], receipt_scope_sha256=receipt["receipt_scope_sha256"])["status"])
        ready_registry = self.root / "evidence/ready-registry.json"
        ready = register_ready_to_score(ready_registry, acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root, summary_sha256=summary)
        self.assertEqual("READY_TO_SCORE", ready["status"])
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            consume_fresh_scoring_authorization(ready_registry, acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root, summary_sha256="f" * 64, scoring_attempt_id="summary-drift")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            register_ready_to_score(ready_registry, acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root, summary_sha256="0" * 64)
        consumed = consume_fresh_scoring_authorization(ready_registry, acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root, summary_sha256=summary, scoring_attempt_id="fresh-score-001")
        self.assertEqual("CONSUMED_SCORING_STARTED", consumed["status"])
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            consume_fresh_scoring_authorization(ready_registry, acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root, summary_sha256=summary, scoring_attempt_id="fresh-score-002")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            register_wait_data_not_scored(registry, receipt_id=receipt["receipt_id"], receipt_scope_sha256=receipt["receipt_scope_sha256"], summary_sha256="0" * 64)

    def test_contract_and_acquisition_fail_closed_on_path_or_policy_drift(self):
        receipt_path, receipt = self._authorization_fixture()
        acquisition_path = self._acquisition_fixture(receipt_path, receipt)
        acquisition = json.loads(acquisition_path.read_text(encoding="utf-8")); acquisition["inputs"][0]["archive_path"] = "../escape.zip"; _write(acquisition_path, acquisition)
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            verify_acquisition_receipt(acquisition_path, receipt_path, plan_path=self.plan_path, workspace_root=self.root)
        receipt["model_and_policy"]["candidate_model"]["id"] = "drifted"; _write(receipt_path, receipt)
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            verify_pre_download_authorization_receipt(receipt_path, plan_path=self.plan_path, workspace_root=self.root)

    def test_january_v2_manifest_must_remain_nonzero_and_bound_to_rows_artifact(self):
        receipt_path, receipt = self._authorization_fixture()
        receipt["january_v2_development_evidence"]["row_count"] = 0; _write(receipt_path, receipt)
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            verify_pre_download_authorization_receipt(receipt_path, plan_path=self.plan_path, workspace_root=self.root)

    def test_receipt_rejects_wrong_sol_decision_id_and_old_v3_model_artifact(self):
        receipt_path, receipt = self._authorization_fixture()
        receipt["sol_decision_id"] = "SOL-WRONG"; _write(receipt_path, receipt)
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            verify_pre_download_authorization_receipt(receipt_path, plan_path=self.plan_path, workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture()
        project = Path(__file__).resolve().parents[1]
        relative = ".runtime/historical-experiments/binance-cm-2025-01-v3-contrarian.model.json"
        target = self.root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.symlink_to(project / relative)
        receipt["january_v2_development_evidence"]["model"] = self._binding(target); _write(receipt_path, receipt)
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            verify_pre_download_authorization_receipt(receipt_path, plan_path=self.plan_path, workspace_root=self.root)

    def test_builder_rejects_missing_archive_checksum_mismatch_wrong_date_and_cadence_gap(self):
        receipt_path, receipt = self._authorization_fixture()
        self._acquisition_fixture(receipt_path, receipt)
        target = receipt["authorized_targets"][0]
        archive = self.root / target["archive_path"]
        archive.write_bytes(archive.read_bytes() + b"tamper")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/tampered.json", workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        missing = self.root / receipt["authorized_targets"][1]["checksum_path"]; missing.unlink()
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/missing.json", workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        target = receipt["authorized_targets"][0]; archive = self.root / target["archive_path"]
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            handle.writestr(archive.with_suffix(".csv").name, "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n1,1,1,1,1,1740787200000,false\n")
        checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/wrong-date.json", workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        target = next(item for item in receipt["authorized_targets"] if item["kind"] == "bookDepth"); archive = self.root / target["archive_path"]
        start_ms = int(datetime(2025, 2, int(target["date"][-2:]), tzinfo=timezone.utc).timestamp() * 1000)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            handle.writestr(archive.with_suffix(".csv").name, "timestamp,percentage,depth,notional\n%d,-1,1,1\n%d,0,1,1\n%d,1,1,1\n%d,-1,1,1\n%d,0,1,1\n%d,1,1,1\n" % (start_ms, start_ms, start_ms, start_ms + 61000, start_ms + 61000, start_ms + 61000))
        checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/gap.json", workspace_root=self.root)

    def test_builder_rejects_member_schema_snapshot_symbol_and_trade_order_drift(self):
        receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        target = receipt["authorized_targets"][0]; archive = self.root / target["archive_path"]
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle: handle.writestr("other.csv", "x\n1\n")
        checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError): build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/wrong-member.json", workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        target = next(item for item in receipt["authorized_targets"] if item["kind"] == "metrics"); archive = self.root / target["archive_path"]
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle: handle.writestr(archive.with_suffix(".csv").name, "create_time,symbol,sum_open_interest,sum_open_interest_value,count\n1738368000000,BTCUSD_PERP,1,1,1\n")
        checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError): build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/schema-drift.json", workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        target = next(item for item in receipt["authorized_targets"] if item["kind"] == "bookDepth"); archive = self.root / target["archive_path"]; start_ms = int(datetime(2025, 2, int(target["date"][-2:]), tzinfo=timezone.utc).timestamp() * 1000)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle: handle.writestr(archive.with_suffix(".csv").name, "timestamp,percentage,depth,notional\n%d,-1,1,1\n%d,0,1,1\n" % (start_ms, start_ms))
        checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError): build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/missing-pm1.json", workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        target = next(item for item in receipt["authorized_targets"] if item["kind"] == "metrics"); archive = self.root / target["archive_path"]; start_ms = int(datetime(2025, 2, int(target["date"][-2:]), tzinfo=timezone.utc).timestamp() * 1000)
        header = "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle: handle.writestr(archive.with_suffix(".csv").name, header + "\n%d,WRONG,1,1,1,1,1,1\n" % start_ms)
        checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError): build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/wrong-symbol.json", workspace_root=self.root)

        self.tearDown(); self.setUp(); receipt_path, receipt = self._authorization_fixture(); self._acquisition_fixture(receipt_path, receipt)
        target = receipt["authorized_targets"][0]; archive = self.root / target["archive_path"]; start_ms = int(datetime(2025, 2, int(target["date"][-2:]), tzinfo=timezone.utc).timestamp() * 1000)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle: handle.writestr(archive.with_suffix(".csv").name, "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n2,1,1,2,2,%d,false\n1,1,1,1,1,%d,false\n" % (start_ms, start_ms))
        checksum = self.root / target["checksum_path"]; checksum.write_text(sha256_file(archive) + "  " + archive.name, encoding="utf-8")
        with self.assertRaises(HistoricalDiagnosticAuthorizationError): build_input_acquisition_receipt(self.plan_path, receipt_path, self.root / "evidence/order-drift.json", workspace_root=self.root)

    def test_book_snapshot_allows_no_zero_but_rejects_duplicate_pm1(self):
        archive = self.root / "book.zip"; start = 1738368000000; end = start + 86399999
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("book.csv", "timestamp,percentage,depth,notional\n%d,-1,1,1\n%d,1,1,1\n%d,-1,1,1\n%d,1,1,1\n" % (start, start, end, end))
        permissive = dict(self.plan); permissive["timing_policy"] = dict(self.plan["timing_policy"], max_book_gap_seconds=86400)
        self.assertEqual(4, _audit_archive_csv(archive, kind="bookDepth", day="2025-02-01", plan=permissive)["row_count"])
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("book.csv", "timestamp,percentage,depth,notional\n%d,-1,1,1\n%d,-1,1,1\n%d,1,1,1\n" % (start, start, start))
        with self.assertRaises(HistoricalDiagnosticAuthorizationError):
            _audit_archive_csv(archive, kind="bookDepth", day="2025-02-01", plan=permissive)
