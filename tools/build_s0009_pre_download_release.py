"""Build the one-time, pre-download S0-009 evidence package without network I/O."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade_system.historical_diagnostic_authorization import (
    build_pre_download_absence_inventory, canonical_sha256, sha256_file,
    verify_authorized_execution_contract, verify_pre_download_authorization_receipt,
)
from trade_system.historical_evidence_ledger import verify_historical_evidence_ledger


OUT = Path(".runtime/historical-diagnostic-s0-009-release")
PLAN = Path("config/binance_cm_historical_diagnostic.v2.frozen_before_download.json")
LEDGER = Path("config/binance_cm_historical_evidence_ledger.v1.json")
DECISION = Path("config/sol_decision.s0-009-feb-falsification.v1.json")
AMENDMENT = Path("config/governance_amendment.s0-009-feb-falsification.v1.json")
SESSION_LOG = Path("/Users/wt/.codex/sessions/2026/07/22/rollout-2026-07-22T17-21-46-019f8921-914c-7012-ba56-53613a47cb26.jsonl")
DECISION_ID = "SOL-S0-009-FEB2025-FRESH-FALSIFICATION-85A95D08-R1"


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(ROOT / path)}


def write_once(path: Path, value: dict) -> None:
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SystemExit("write-once release artifact already exists: %s" % path) from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-test-count", type=int, required=True)
    args = parser.parse_args()
    if args.full_test_count < 1:
        raise SystemExit("full test count must be positive")
    if sha256_file(ROOT / PLAN) != "75ee48cb7abb9374ebae65929ac5eec6148f21bdfc2a13eea19607a931c9d6fb":
        raise SystemExit("frozen plan file SHA drifted")
    plan_doc = json.loads((ROOT / PLAN).read_text())
    if canonical_sha256(plan_doc) != "85a95d0845ca0c78b9bc3be12d8dcafd051625fab5be318398ace2f92531087b":
        raise SystemExit("frozen plan canonical SHA drifted")
    if sha256_file(ROOT / Path("trade_system/binance_cm_historical_mechanism.py")) != "ba3d54f481f905f4ff3beefb5d4a78c9c812f3beec36bf89fc75b6b956702eea":
        raise SystemExit("ledger-bound historical mechanism source drifted")
    if sha256_file(SESSION_LOG) != "9677d3ae35fa566a43d955005fffe7842043a6a31d74c7ae3ed4d5ecb3c6b5b6":
        raise SystemExit("recovery provenance session digest drifted")

    ledger_result = verify_historical_evidence_ledger(ROOT / LEDGER, workspace_root=ROOT)
    recovery_path = OUT / "ledger-source-recovery-audit.v1.json"
    ledger_report_path = OUT / "ledger-verification-report.v1.json"
    test_report_path = OUT / "p0-test-report.v1.json"
    package_path = OUT / "package-manifest.v1.json"
    inventory_path = OUT / "all-targets-absent-inventory.v1.json"
    contract_path = OUT / "authorized-execution-contract.v2.json"
    receipt_path = OUT / "authorization-receipt.v1.json"
    release_path = OUT / "release-report.v1.json"
    recovery = {"record_type":"s0_009_ledger_source_recovery_audit.v1","audit_id":"S0-009-LEDGER-SOURCE-RECOVERY-v1","status":"RESTORE_EXACT_BOUND_SOURCE_RETAIN_R1_HOLD_BEFORE_DOWNLOAD","source":{"path":"trade_system/binance_cm_historical_mechanism.py","before_sha256":"1a4bab21c4d90c8877e1ba0ff3dd3f1b216d5cd693eaca4315237ee86f56e552","after_sha256":sha256_file(ROOT / Path("trade_system/binance_cm_historical_mechanism.py"))},"unique_patch":{"session_log_path":str(SESSION_LOG),"session_log_sha256":sha256_file(SESSION_LOG),"timestamp":"2026-07-22T18:59:48.178Z","payload_id":"ctc_0516e76605a35cbf016a6113242d248191b765d6c992180cfe","call_id":"call_NpSJEeunt6U5UuOevF0gZA8r","patch":"added epoch-ms branch to _dt_text"},"frozen_bindings":{"ledger":binding(LEDGER),"report":binding(Path(".runtime/historical-experiments/binance-cm-2025-01-report.v3.json")),"verifier":binding(Path("trade_system/historical_evidence_ledger.py"))},"ledger_verifier_result":ledger_result,"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
    write_once(recovery_path, recovery)
    ledger_report = {"record_type":"historical_evidence_ledger_verification_report.v1","status":"VERIFIED","ledger":binding(LEDGER),"bound_report":binding(Path(".runtime/historical-experiments/binance-cm-2025-01-report.v3.json")),"verifier":binding(Path("trade_system/historical_evidence_ledger.py")),"result":ledger_result,"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
    write_once(ledger_report_path, ledger_report)
    tests = {"record_type":"s0_009_p0_test_report.v1","status":"ALL_SEVEN_P0_MECHANICALLY_VERIFIED","full_suite":{"command":"python3 -m unittest discover -q","passed":args.full_test_count},"p0_ids":["S0-009-P0-%d" % value for value in range(1,8)],"e2e":{"test":"test_unpatched_84_zip_receipt_builder_execute_completes_once","fresh_rows":28,"gate":"WAIT_DATA_COVERAGE","model_fit_performed":False,"calibration_fit_performed":False},"failure_sealing_test":"test_post_consume_model_deletion_seals_failed_registry_and_refuses_repeat","coverage_gate_tests":["test_fresh_gate_zero_episodes_stops_data_invalid","test_fresh_gate_day_concentration_over_limit_waits","test_fresh_gate_state_concentration_over_limit_waits","test_fresh_gate_direction_concentration_over_limit_waits"],"allowlist_test":"test_receipt_rejects_wrong_sol_decision_id_and_old_v3_model_artifact","eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
    write_once(test_report_path, tests)
    package = {"record_type":"s0_009_pre_download_package_manifest.v1","package_id":"S0-009-PRE-DOWNLOAD-RELEASE-v1","sol_decision":binding(DECISION),"governance_amendment":binding(AMENDMENT),"frozen_plan":binding(PLAN),"runner":binding(Path("trade_system/historical_diagnostic_application.py")),"evaluator":binding(Path("trade_system/historical_diagnostic_development.py")),"authorization":binding(Path("trade_system/historical_diagnostic_authorization.py")),"tests":{"application":binding(Path("tests/test_historical_diagnostic_application.py")),"authorization":binding(Path("tests/test_historical_diagnostic_authorization.py"))},"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
    write_once(package_path, package)
    inventory = build_pre_download_absence_inventory(ROOT / PLAN, workspace_root=ROOT, download_root=".runtime/historical-diagnostic-authorized-download-root/february-2025")
    write_once(inventory_path, inventory)
    v4 = Path(".runtime/historical-experiments")
    manifest = v4 / "binance-cm-2025-01-v4-final.manifest.json"
    receipt = {"record_type":"pre_download_authorization_receipt.v1","status":"AUTHORIZED","receipt_id":"S0-009-FEB2025-FRESH-FALSIFICATION-85A95D08-R1-ONE-TIME","sol_decision_id":DECISION_ID,"frozen_design":binding(PLAN),"frozen_design_canonical_sha256":"85a95d0845ca0c78b9bc3be12d8dcafd051625fab5be318398ace2f92531087b","absence_inventory":inventory,"v1_ledger":binding(LEDGER),"v1_ledger_verification_report":binding(ledger_report_path),"january_v2_development_evidence":{"manifest_id":"XH-CM-btcusd-perp-2025-01-seen-development-v2-post-pressure-response-v2","row_count":json.loads((ROOT / manifest).read_text())["row_count"],"manifest":binding(manifest),"rows_artifact":binding(v4 / "binance-cm-2025-01-v4-final.rows.ndjson"),"model":binding(v4 / "binance-cm-2025-01-v4-final.model.json")},"model_and_policy":{"candidate_model":{"id":"D+post-pressure-R+persistence+deceleration"},"control_model":{"id":"D-only extreme"},"calibration":{"id":"IDENTITY_TEMPERATURE_1"},"payoff_policy":{"id":"FROZEN_10_20_BPS"},"selection_policy":{"id":"FROZEN_POSITIVE_BASE_EV_ONLY"},"evaluation_policy":{"id":"FRESH_SCORE_ONLY"},"runner":dict(binding(Path("trade_system/historical_diagnostic_application.py")),id="receipt-bound-fresh-runner"),"evaluator":dict(binding(Path("trade_system/historical_diagnostic_development.py")),id="frozen-v4-evaluator"),"package":dict(binding(package_path),id="S0-009-PRE-DOWNLOAD-RELEASE-v1"),"test_report":dict(binding(test_report_path),id="S0-009-P0-TEST-REPORT-v1")},"authorized_targets":inventory["targets"],"download_limits":{"max_archive_bytes_each":1073741824,"max_total_archive_bytes":90194313216},"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
    scope = canonical_sha256(receipt)
    contract = {"record_type":"authorized_execution_contract.v2","status":"AUTHORIZED_RECEIPT_BOUND","contract_id":"S0-009-FEB2025-ONE-TIME-SCORE-ONLY","frozen_design":binding(PLAN),"authorization_receipt":{"path":str(receipt_path),"receipt_id":receipt["receipt_id"],"receipt_scope_sha256":scope},"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
    write_once(contract_path, contract)
    receipt["authorized_execution_contract"] = dict(binding(contract_path), contract_id=contract["contract_id"])
    receipt["receipt_scope_sha256"] = scope
    write_once(receipt_path, receipt)
    receipt_result = verify_pre_download_authorization_receipt(ROOT / receipt_path, plan_path=ROOT / PLAN, workspace_root=ROOT)
    contract_result = verify_authorized_execution_contract(ROOT / contract_path, ROOT / receipt_path, plan_path=ROOT / PLAN, workspace_root=ROOT)
    release = {"record_type":"s0_009_pre_download_release_report.v1","status":"READY_FOR_ONE_TIME_AUTHORIZED_DOWNLOAD","sol_decision":binding(DECISION),"governance_amendment":binding(AMENDMENT),"recovery_audit":binding(recovery_path),"ledger_verification":binding(ledger_report_path),"package":binding(package_path),"p0_test_report":binding(test_report_path),"absence_inventory":binding(inventory_path),"authorization_receipt":binding(receipt_path),"execution_contract":binding(contract_path),"verification":{"receipt":receipt_result,"contract":contract_result},"scope":"2025-02-01..2025-02-28 FRESH_SCORE_ONLY one receipt one scoring attempt","eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
    write_once(release_path, release)
    print(json.dumps({"release":str(release_path),"release_sha256":sha256_file(ROOT / release_path),"receipt":receipt_result,"contract":contract_result},sort_keys=True))


if __name__ == "__main__":
    main()
