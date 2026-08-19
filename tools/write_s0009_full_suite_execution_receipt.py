"""Write the post-hoc, write-once execution fact for the S0-009 full suite."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/supplemental-full-suite-execution-receipt.v1.json"
TEST_REPORT = ROOT / ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/subordinate-guard-test-report.v1.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    args = parser.parse_args()
    if args.exit_code != 0 or args.duration_seconds <= 0:
        raise SystemExit("supplemental receipt only records a successful measured full suite")
    log = Path(args.log)
    content = log.read_bytes()
    if b"Ran 282 tests" not in content or not content.rstrip().endswith(b"OK"):
        raise SystemExit("full-suite log does not prove 282 passing tests")
    prior = json.loads(TEST_REPORT.read_text(encoding="utf-8"))
    prior_claim_has_exit_fact = all(key in prior.get("full_suite", {}) for key in ("exit_code", "duration_seconds", "log_sha256"))
    receipt = {
        "record_type": "s0_009_supplemental_full_suite_execution_receipt.v1",
        "status": "EXECUTED_EXIT_0",
        "command": "python3 -m unittest discover -q",
        "tests_discovered": 282,
        "exit_code": 0,
        "duration_seconds": args.duration_seconds,
        "log_sha256": hashlib.sha256(content).hexdigest(),
        "prior_test_report": {
            "path": str(TEST_REPORT.relative_to(ROOT)),
            "sha256": hashlib.sha256(TEST_REPORT.read_bytes()).hexdigest(),
            "passed_claim": prior.get("full_suite", {}).get("passed"),
            "had_exit_code_duration_log_evidence": prior_claim_has_exit_fact,
        },
        "notice": "The prior report recorded count 282 but not an independently captured exit code, duration, and log digest. This supplemental receipt supplies those facts without changing it.",
        "eligible_for_binance_g2": False,
        "trading_authorization": "DENIED",
    }
    encoded = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        descriptor = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SystemExit("write-once supplemental receipt already exists") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
    print(hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    main()
