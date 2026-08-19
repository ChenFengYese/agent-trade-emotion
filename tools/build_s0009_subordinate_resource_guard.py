"""Write the unsigned S0-009 subordinate resource-guard package.

It has no downloader invocation and cannot issue a second receipt.  Every
artifact is write-once and deliberately remains a HOLD until a later Sol
addendum binds the existing parent receipt, this policy, and its downloader.
"""
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
    build_pre_download_absence_inventory,
    sha256_file,
    verify_authorized_execution_contract,
    verify_pre_download_authorization_receipt,
)
from trade_system.historical_diagnostic_guarded_download import (
    GUARD_POLICY_RECORD,
    HOLD_STATE,
    MAX_ARCHIVE_BYTES,
    MAX_CHECKSUM_BYTES,
    MAX_TOTAL_ARCHIVE_BYTES,
    MIN_ARCHIVE_BUDGET_EACH,
    MIN_FREE_AFTER_BYTES,
    OLD_RELEASE_STATE,
    PARENT_RELEASE_PATH,
    PARENT_RELEASE_SHA256,
    SOL_R1_PATH,
    SOL_R1_SHA256,
)
from trade_system.historical_evidence_ledger import verify_historical_evidence_ledger


OUT = Path(".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1")
PLAN = Path("config/binance_cm_historical_diagnostic.v2.frozen_before_download.json")
LEDGER = Path("config/binance_cm_historical_evidence_ledger.v1.json")
RELEASE = Path(".runtime/historical-diagnostic-s0-009-release")
RECEIPT = RELEASE / "authorization-receipt.v1.json"
CONTRACT = RELEASE / "authorized-execution-contract.v2.json"
PARENT_INVENTORY = RELEASE / "all-targets-absent-inventory.v1.json"
EXPECTED = {
    SOL_R1_PATH: SOL_R1_SHA256,
    str(RELEASE / "release-report.v1.json"): PARENT_RELEASE_SHA256,
    str(RECEIPT): "1a0e62aa9bea6bc1903720de4d113aadc0c86200e05b82923d782d027e6646eb",
    str(CONTRACT): "431ed9984baf090a4d4651b5d31f08ba36c3b512bd09e5087af27514d1ecd431",
    str(PARENT_INVENTORY): "85e86fcbbf4bfed60daa2bea04c11a266f0ed95531ed724c2a4ddad68e0c4049",
}


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(ROOT / path)}


def write_once(path: Path, value: dict) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SystemExit("write-once subordinate guard artifact already exists: %s" % target) from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-test-count", type=int, required=True)
    args = parser.parse_args()
    if args.full_test_count < 1:
        raise SystemExit("full test count must be positive")
    for path, expected in EXPECTED.items():
        if sha256_file(ROOT / path) != expected:
            raise SystemExit("exact parent artifact digest drifted: %s" % path)
    if sha256_file(ROOT / PLAN) != "75ee48cb7abb9374ebae65929ac5eec6148f21bdfc2a13eea19607a931c9d6fb":
        raise SystemExit("frozen February plan digest drifted")

    receipt_result = verify_pre_download_authorization_receipt(ROOT / RECEIPT, plan_path=ROOT / PLAN, workspace_root=ROOT)
    contract_result = verify_authorized_execution_contract(ROOT / CONTRACT, ROOT / RECEIPT, plan_path=ROOT / PLAN, workspace_root=ROOT)
    ledger_result = verify_historical_evidence_ledger(ROOT / LEDGER, workspace_root=ROOT)
    receipt = json.loads((ROOT / RECEIPT).read_text(encoding="utf-8"))
    parent_authorization = {
        "receipt_id": receipt["receipt_id"], "receipt_scope_sha256": receipt["receipt_scope_sha256"],
        "receipt_sha256": sha256_file(ROOT / RECEIPT), "contract_sha256": sha256_file(ROOT / CONTRACT),
    }
    if parent_authorization["receipt_id"] != "S0-009-FEB2025-FRESH-FALSIFICATION-85A95D08-R1-ONE-TIME":
        raise SystemExit("parent receipt identity drifted")

    inventory_path = OUT / "current-absence-revalidation.v1.json"
    policy_path = OUT / "subordinate-resource-guard-policy.v1.json"
    suspension_path = OUT / "parent-release-suspension.v1.json"
    package_path = OUT / "source-package-manifest.v1.json"
    test_path = OUT / "subordinate-guard-test-report.v1.json"
    addendum_inputs_path = OUT / "proposed-sol-addendum-inputs.v1.json"
    release_path = OUT / "guarded-release-draft.v1.json"
    inventory = build_pre_download_absence_inventory(ROOT / PLAN, workspace_root=ROOT, download_root=receipt["absence_inventory"]["download_root"])
    write_once(inventory_path, inventory)
    policy = {
        "record_type": GUARD_POLICY_RECORD,
        "policy_id": "S0-009-SUBORDINATE-RESOURCE-GUARD-v1",
        "status": HOLD_STATE,
        "parent_release_state": OLD_RELEASE_STATE,
        "parent_release": binding(Path(PARENT_RELEASE_PATH)),
        "sol_r1": binding(Path(SOL_R1_PATH)),
        "parent_inventory": binding(PARENT_INVENTORY),
        "current_absence_revalidation": binding(inventory_path),
        "parent_authorization": parent_authorization,
        "guarded_downloader": binding(Path("trade_system/historical_diagnostic_guarded_download.py")),
        "resource_limits": {
            "max_archive_bytes_each": MAX_ARCHIVE_BYTES,
            "max_total_archive_bytes": MAX_TOTAL_ARCHIVE_BYTES,
            "max_checksum_bytes_each": MAX_CHECKSUM_BYTES,
            "minimum_free_bytes_after_maximum_download": MIN_FREE_AFTER_BYTES,
            "minimum_archive_budget_each": MIN_ARCHIVE_BUDGET_EACH,
        },
        "effective_limit_rule": "min(parent_receipt_limit, subordinate_guard_limit)",
        "disk_gate": "free_bytes - (remaining_archive_bytes + remaining_checksum_bytes) >= 8589934592 before every archive/checksum transport",
        "forbidden": ["network invocation before final Sol binding", "second authorization receipt", "limit increase", "active G1 mutation", "G2 eligibility", "trading authorization"],
        "eligible_for_binance_g2": False,
        "trading_authorization": "DENIED",
    }
    write_once(policy_path, policy)
    suspension = {
        "record_type": "s0_009_parent_release_suspension.v1", "status": OLD_RELEASE_STATE,
        "reason": "Parent receipt limits exceed current bounded-diagnostic storage gate; parent files are retained unmodified.",
        "parent_release": binding(Path(PARENT_RELEASE_PATH)), "parent_authorization": parent_authorization,
        "successor_policy": binding(policy_path), "current_absence_revalidation": binding(inventory_path),
        "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
    }
    write_once(suspension_path, suspension)
    package = {
        "record_type": "s0_009_subordinate_resource_guard_package.v1", "package_id": "S0-009-SUBORDINATE-RESOURCE-GUARD-v1",
        "guarded_downloader": binding(Path("trade_system/historical_diagnostic_guarded_download.py")),
        "builder": binding(Path("tools/build_s0009_subordinate_resource_guard.py")),
        "tests": binding(Path("tests/test_historical_diagnostic_guarded_download.py")),
        "parent_authorization": parent_authorization, "parent_release": binding(Path(PARENT_RELEASE_PATH)),
        "policy": binding(policy_path), "current_absence_revalidation": binding(inventory_path), "suspension": binding(suspension_path),
        "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
    }
    write_once(package_path, package)
    tests = {
        "record_type": "s0_009_subordinate_resource_guard_test_report.v1", "status": "MECHANICALLY_VERIFIED_AWAITING_FINAL_SOL_BINDING",
        "full_suite": {"command": "python3 -m unittest discover -q", "passed": args.full_test_count},
        "targeted": {"command": "python3 -m unittest -v tests.test_historical_diagnostic_guarded_download", "passed": 15},
        "high_risk_coverage": ["parent release suspension", "wrong receipt/scope/downloader/addendum bindings", "disk-before-body and per-archive recheck including remaining checksums", "content-length and stream limits", "aggregate limit", "final/temp refusal and pre-reservation race", "URL/redirect refusal", "checksum-before-archive-publish", "atomic publish and fsync failure", "new-directory fsync before descent", "dirfd symlink-swap containment", "test-only manifest production rejection", "one-time execution", "84 target acquisition cross-verification"],
        "policy": binding(policy_path), "source_package": binding(package_path),
        "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
    }
    write_once(test_path, tests)
    addendum_inputs = {
        "record_type": "s0_009_proposed_subordinate_resource_addendum_inputs.v1", "status": HOLD_STATE,
        "notice": "This is an unsigned input set, not a Sol addendum and not download permission.",
        "required_final_record_type": "sol_s0_009_subordinate_resource_addendum.v1", "required_final_status": "FINAL_SOL_BOUND_RESOURCE_GUARD", "required_addendum_id": "SOL-S0-009-R1-RESOURCE-ATTENUATION-A1",
        "parent_authorization": parent_authorization, "resource_policy": binding(policy_path),
        "guarded_downloader": binding(Path("trade_system/historical_diagnostic_guarded_download.py")), "source_package": binding(package_path), "test_report": binding(test_path), "transport_mode": "OFFICIAL_NETWORK_ONLY",
        "authorization_receipt_limit": 1, "new_authorization_receipt": False,
        "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
    }
    write_once(addendum_inputs_path, addendum_inputs)
    release = {
        "record_type": "s0_009_guarded_release_draft.v1", "status": HOLD_STATE,
        "notice": "No final Sol addendum is present. This draft cannot download, read February inputs, score, grant G2, or authorize trading.",
        "parent_release_suspension": binding(suspension_path), "current_absence_revalidation": binding(inventory_path),
        "resource_policy": binding(policy_path), "source_package": binding(package_path), "test_report": binding(test_path),
        "proposed_addendum_inputs": binding(addendum_inputs_path),
        "parent_verification": {"receipt": receipt_result, "contract": contract_result, "ledger": ledger_result},
        "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
    }
    write_once(release_path, release)
    print(json.dumps({"status": HOLD_STATE, "release": str(release_path), "release_sha256": sha256_file(ROOT / release_path), "policy_sha256": sha256_file(ROOT / policy_path), "package_sha256": sha256_file(ROOT / package_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
