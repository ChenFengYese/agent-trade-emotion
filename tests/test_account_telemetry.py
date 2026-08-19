import json
import tempfile
import unittest
from pathlib import Path

from trade_system.account_telemetry import (
    AccountTelemetryArtifactError,
    AccountTelemetryContract,
    AccountTelemetryContractError,
    audit_normalized_telemetry,
    write_recovery_telemetry_reconciliation_report,
)
from trade_system.account_telemetry_normalizer import (
    AccountTelemetryArtifactError as NormalizationError,
    normalize_sanitized_telemetry,
)
from trade_system.paper_audit import PaperAuditTrail, write_paper_recovery_report


class AccountTelemetryContractTests(unittest.TestCase):
    def _valid_contract(self):
        fields = {
            "order_update": ["local_receive_time", "source_event_time", "submit_time", "ack_time", "reject_reason", "client_order_id", "exchange_order_id", "status", "side", "order_type", "original_quantity", "executed_quantity", "raw_payload_sha256"],
            "execution_fill": ["local_receive_time", "source_event_time", "fill_time", "client_order_id", "exchange_order_id", "fill_id", "fill_quantity", "fill_price", "fee_amount", "fee_asset", "raw_payload_sha256"],
            "account_update": ["local_receive_time", "source_event_time", "asset", "wallet_balance", "available_balance", "instrument", "position_quantity", "entry_price", "raw_payload_sha256"],
            "funding_update": ["local_receive_time", "source_event_time", "funding_time", "asset", "funding_amount", "raw_payload_sha256"],
            "rest_recovery_snapshot": ["local_receive_time", "source_as_of", "open_orders", "positions", "balances", "commission_schedule", "income_history_cursor", "raw_payload_sha256"],
        }
        return {
            "contract_id": "telemetry.v1", "schema_version": "v1", "status": "FROZEN_ACCOUNT_TELEMETRY_CONTRACT", "frozen_at": "2026-01-01T00:00:00Z",
            "scope": {"venue": "TEST", "environment": "PAPER_OR_TESTNET_ONLY", "instrument_scope": ["BTCUSDT"]},
            "permissions": {"private_rest": "READ_ONLY_REQUIRED", "user_stream": "READ_ONLY_REQUIRED", "trading": "FORBIDDEN", "withdrawal": "FORBIDDEN"},
            "event_contracts": [{"name": name, "source_id": "SRC-TEST", "ordering": "source then local", "required_fields": value} for name, value in fields.items()],
            "reconciliation": {"required_before_new_risk": True, "max_unexplained_position_differences": 0, "required_snapshot_fields": ["open_orders", "positions", "balances", "commission_schedule", "income_history_cursor"]},
            "cost_calibration": {"required_fields": ["fee_amount", "fee_asset", "funding_amount", "fill_price", "fill_quantity", "submit_time", "ack_time", "fill_time", "reject_reason"], "may_calibrate_live_execution": False},
        }

    def test_frozen_read_only_contract_has_stable_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(self._valid_contract()), encoding="utf-8")
            summary = AccountTelemetryContract.load(path).summary()
            self.assertEqual("PAPER_OR_TESTNET_ONLY", summary["environment"])
            self.assertFalse(summary["credential_or_order_capability"])
            self.assertRegex(summary["sha256"], r"^[0-9a-f]{64}$")

    def test_contract_rejects_live_or_trading_permission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            contract = self._valid_contract()
            contract["permissions"]["trading"] = "ALLOWED"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(AccountTelemetryContractError, "forbid trading"):
                AccountTelemetryContract.load(path)

    @staticmethod
    def _telemetry_row(contract, **values):
        row = {
            "record_type": "normalized_account_telemetry",
            "contract_id": contract.contract_id,
            "contract_sha256": contract.sha256,
            "event_name": "rest_recovery_snapshot",
            "local_receive_time": "2026-07-22T00:00:01Z",
            "source_as_of": "2026-07-22T00:00:00Z",
            "open_orders": [],
            "positions": [{"instrument": "BTCUSDT", "position_quantity": "0"}],
            "balances": [{"asset": "USDT", "wallet_balance": "100", "available_balance": "100"}],
            "commission_schedule": {},
            "income_history_cursor": None,
            "raw_payload_sha256": "a" * 64,
        }
        row.update(values)
        return row

    def test_normalized_artifact_is_contract_bound_and_rejects_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path, telemetry_path = root / "contract.json", root / "telemetry.ndjson"
            contract_path.write_text(json.dumps(self._valid_contract()), encoding="utf-8")
            contract = AccountTelemetryContract.load(contract_path)
            telemetry_path.write_text(json.dumps(self._telemetry_row(contract)) + "\n", encoding="utf-8")
            report = audit_normalized_telemetry(telemetry_path, contract)
            self.assertEqual(1, report["event_counts"]["rest_recovery_snapshot"])
            self.assertIn("execution_fill", report["missing_event_types"])
            self.assertIn("funding_update", report["missing_event_types"])
            secret = self._telemetry_row(contract, api_secret="forbidden")
            telemetry_path.write_text(json.dumps(secret) + "\n", encoding="utf-8")
            with self.assertRaises(AccountTelemetryArtifactError):
                audit_normalized_telemetry(telemetry_path, contract)
            invalid_balance = self._telemetry_row(contract, positions=[{"instrument": "BTCUSDT", "position_quantity": "NaN"}])
            telemetry_path.write_text(json.dumps(invalid_balance) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(AccountTelemetryArtifactError, "finite decimal"):
                audit_normalized_telemetry(telemetry_path, contract)

    def test_funding_event_requires_time_and_finite_amount(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path, telemetry_path = root / "contract.json", root / "telemetry.ndjson"
            contract_path.write_text(json.dumps(self._valid_contract()), encoding="utf-8")
            contract = AccountTelemetryContract.load(contract_path)
            funding = self._telemetry_row(
                contract,
                event_name="funding_update",
                source_event_time="2026-07-22T00:00:00Z",
                funding_time="2026-07-22T00:00:00Z",
                asset="USDT",
                funding_amount="-0.01",
            )
            telemetry_path.write_text(json.dumps(funding) + "\n", encoding="utf-8")
            self.assertEqual(1, audit_normalized_telemetry(telemetry_path, contract)["event_counts"]["funding_update"])
            funding.pop("funding_time")
            telemetry_path.write_text(json.dumps(funding) + "\n", encoding="utf-8")
            with self.assertRaises(AccountTelemetryArtifactError):
                audit_normalized_telemetry(telemetry_path, contract)

    def test_recovery_snapshot_match_stays_manual_clear_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path, telemetry_path = root / "contract.json", root / "telemetry.ndjson"
            audit_path, recovery_path, output = root / "paper.ndjson", root / "recovery.json", root / "reconcile.json"
            contract_path.write_text(json.dumps(self._valid_contract()), encoding="utf-8")
            contract = AccountTelemetryContract.load(contract_path)
            trail = PaperAuditTrail(audit_path, run_id="telemetry-recovery", context={"scope": "TEST"})
            trail.append("INTENT_ACKNOWLEDGED", {"state": {
                "position_quantity": "1",
                "orders": {"intent": {"client_order_id": "paper-1", "status": "ACKNOWLEDGED"}},
            }})
            recovery = write_paper_recovery_report(audit_path, recovery_path, confirm_process_stopped=True)
            telemetry_path.write_text(json.dumps(self._telemetry_row(
                contract,
                open_orders=[{"client_order_id": "paper-1"}],
                positions=[{"instrument": "BTCUSDT", "position_quantity": "1"}],
            )) + "\n", encoding="utf-8")
            report = write_recovery_telemetry_reconciliation_report(
                output,
                recovery_report_path=recovery_path,
                recovery_report=recovery,
                telemetry_path=telemetry_path,
                contract=contract,
            )
            self.assertEqual("MATCHED_MANUAL_CLEAR_REQUIRED", report["reconciliation"]["reconciliation_status"])
            self.assertTrue(output.exists())

    def test_offline_normalizer_maps_pinned_source_events_without_raw_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path, source_path, output = root / "contract.json", root / "source.ndjson", root / "normalized.ndjson"
            contract_path.write_text(json.dumps(self._valid_contract()), encoding="utf-8")
            contract = AccountTelemetryContract.load(contract_path)
            base = {"record_type": "sanitized_private_source_event", "source_schema_version": "binance-usdm-private.v1", "local_receive_time": "2026-07-22T00:00:01Z"}
            rows = [
                {**base, "source_kind": "BINANCE_USDM_USER_STREAM", "payload": {
                    "e": "ORDER_TRADE_UPDATE", "E": 1784678400000, "T": 1784678400001,
                    "o": {"s": "BTCUSDT", "c": "paper-1", "S": "BUY", "o": "LIMIT", "q": "1", "z": "1", "T": 1784678400001, "i": 123, "X": "FILLED", "x": "TRADE", "l": "1", "t": 456, "L": "100", "n": "0.04", "N": "USDT"},
                }},
                {**base, "source_kind": "BINANCE_USDM_USER_STREAM", "payload": {
                    "e": "ACCOUNT_UPDATE", "E": 1784678400002,
                    "a": {"B": [{"a": "USDT", "wb": "99.96", "cw": "99.96"}], "P": [{"s": "BTCUSDT", "pa": "1", "ep": "100"}]},
                }},
                {**base, "source_kind": "BINANCE_USDM_PRIVATE_REST_INCOME", "payload": {
                    "incomeType": "FUNDING_FEE", "symbol": "BTCUSDT", "time": 1784678400003, "asset": "USDT", "income": "-0.01",
                }},
                {**base, "source_kind": "BINANCE_USDM_PRIVATE_REST_RECOVERY", "payload": {
                    "source_as_of": 1784678400004, "open_orders": [{"clientOrderId": "paper-1", "orderId": 123}],
                    "positions": [{"symbol": "BTCUSDT", "positionAmt": "1"}],
                    "balances": [{"asset": "USDT", "balance": "99.95", "availableBalance": "99.95"}],
                    "commission_schedule": {}, "income_history_cursor": "1784678400003",
                }},
            ]
            source_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            report = normalize_sanitized_telemetry(source_path, output, contract)
            self.assertEqual(4, report["source_row_count"])
            self.assertEqual(5, report["normalized_row_count"])
            normalized = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["order_update", "execution_fill", "account_update", "funding_update", "rest_recovery_snapshot"], [row["event_name"] for row in normalized])
            self.assertTrue(all("payload" not in row for row in normalized))
            self.assertEqual("2026-07-22T00:00:00Z", normalized[0]["source_event_time"])
            self.assertEqual(1, report["audit"]["event_counts"]["funding_update"])

    def test_offline_normalizer_rejects_credentials_and_unknown_source_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract_path, source_path, output = root / "contract.json", root / "source.ndjson", root / "normalized.ndjson"
            contract_path.write_text(json.dumps(self._valid_contract()), encoding="utf-8")
            contract = AccountTelemetryContract.load(contract_path)
            forbidden = {
                "record_type": "sanitized_private_source_event", "source_schema_version": "binance-usdm-private.v1",
                "source_kind": "BINANCE_USDM_USER_STREAM", "local_receive_time": "2026-07-22T00:00:01Z",
                "payload": {"e": "ACCOUNT_UPDATE", "apiKey": "must-not-be-here"},
            }
            source_path.write_text(json.dumps(forbidden) + "\n", encoding="utf-8")
            with self.assertRaises(NormalizationError):
                normalize_sanitized_telemetry(source_path, output, contract)
            self.assertFalse(output.exists())
            unknown = dict(forbidden, payload={"e": "MARGIN_CALL"})
            source_path.write_text(json.dumps(unknown) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(NormalizationError, "unsupported user-stream event"):
                normalize_sanitized_telemetry(source_path, output, contract)
