#!/usr/bin/env python3
"""Read-only integrity verifier for the S0-009 February A2 terminal hold."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


TERMINAL_PATH = Path(
    ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/"
    "february-terminal-wait-data-not-scored.a2f1.json"
)
CONFIG_PATH = Path("config/sol_decision.s0-009-r1-acquisition-gap-censoring.a2f1.json")
SUPERSESSION_PATH = Path(
    ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/"
    "acquisition-gap-censoring-a2f1-supersession-record.json"
)
EXPECTED_TERMINAL_SHA256 = "2a66f1b47c4ca319c3ce36c47fd6b295b683569fd1d9429f41b85d3729c7d266"
EXPECTED_SUPERSESSION_SHA256 = "86e905cd35c589e2ce2540160f8e32b1497be7a0c8e921ddeeb82189f60d01e4"
EXPECTED_ARTIFACTS = {
    "r1_decision": {
        "path": "config/sol_decision.s0-009-feb-falsification.v1.json",
        "sha256": "d9e11df2e533266568b642409e15db566035f8126152a4b5c70992440d8210f3",
    },
    "a1_addendum": {
        "path": ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/final-sol-resource-attenuation-addendum.a1.json",
        "sha256": "66e30feaa971abdd2d1452420102527bc7318ebf13c2a46bd2e40ed82ac20f50",
    },
    "guarded_production_manifest": {
        "path": ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/guarded-download-manifest.a1.json",
        "sha256": "4ffd62d9eaeaa468fb836b3a767c063e518f545cb17fd5f001f6fefbd78e0522",
    },
    "read_only_gap_diagnostic": {
        "path": ".runtime/historical-diagnostic-s0-009-subordinate-resource-guard-v1/read-only-acquisition-gap-diagnostic.a1.json",
        "sha256": "cbec50a19de1607a19f5740dd21ceb86c47ead9cad1ef2c2d21a78862448eb0c",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"cannot read JSON {path}: {exc}") from exc


def expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.workspace_root.resolve()
    config = load(root / CONFIG_PATH)
    terminal = load(root / TERMINAL_PATH)
    supersession = load(root / SUPERSESSION_PATH)

    expect(config["decision_id"], "SOL-S0-009-R1-ACQUISITION-GAP-CENSORING-A2", "config decision")
    expect(config["artifact_revision"], "A2F1", "config artifact revision")
    expect(config["serialization_boundary"]["authoritative"], True, "config authority")
    expect(config["serialization_boundary"]["external_session_dependency"], "NONE", "external-session dependency")
    expect(config["execution_state"], "FEB2025_TERMINAL_WAIT_DATA_NOT_SCORED", "config state")
    expect(config["execution_gate"], "HOLD_BEFORE_ANY_NEW_ACQUISITION_OR_SCORING", "config gate")
    expect(
        config["decision"],
        "CONDITIONAL_AUTHORIZE_VALIDATOR_SEMANTIC_REPAIR_FOR_FUTURE_UNSEEN_INPUTS_ONLY",
        "config repair authority",
    )
    expect(config["g2_eligibility"], False, "config G2")
    expect(config["trading_authorization"], "DENIED", "config trading")

    expect(sha256(root / TERMINAL_PATH), EXPECTED_TERMINAL_SHA256, "terminal record SHA")
    expect(sha256(root / SUPERSESSION_PATH), EXPECTED_SUPERSESSION_SHA256, "supersession record SHA")
    expect(terminal["record_type"], "s0_009_february_terminal_hold.a2f1", "terminal record type")
    expect(terminal["state"], "FEB2025_TERMINAL_WAIT_DATA_NOT_SCORED", "terminal state")
    expect(terminal["input_role"], "SEEN", "terminal input role")
    expect(terminal["independent_evaluation_role"], "PERMANENTLY_CONSUMED", "terminal role")
    expect(terminal["score_executed"], False, "terminal score execution")
    expect(terminal["g2_eligibility"], False, "terminal G2")
    expect(terminal["trading_authorization"], "DENIED", "terminal trading")
    expect(terminal["gap_fact"], {
        "kind": "bookDepth",
        "date": "2025-02-26",
        "internal_gap_ms": 1380000,
        "human_duration": "23 minutes",
        "left_at": "2025-02-26T06:26:30+00:00",
        "right_at": "2025-02-26T06:49:30+00:00",
        "frozen_max_gap_ms": 60000,
        "classification": "OFFICIAL_SNAPSHOT_OR_METRIC_CADENCE",
    }, "terminal gap fact")
    expect(
        supersession["supersession_kind"],
        "SUPERSEDED_BEFORE_ADOPTION_NON_AUTHORITATIVE_SERIALIZATION",
        "supersession kind",
    )
    expect(supersession["decision_unchanged"], True, "supersession decision continuity")
    expect(supersession["new_authorization_created"], False, "supersession authorization")
    expect(
        supersession["future_repair_implementation_or_validation_accepted"],
        False,
        "supersession repair acceptance",
    )
    expect(
        supersession["old_serialization"]["config_sha256"],
        "f4b098d4ca485b4df66132205a51d4b12be9e3f35e6c9ca6453ae955a2a5fbcc",
        "old config SHA",
    )
    expect(
        supersession["old_serialization"]["terminal_sha256"],
        "f878470e86245ddfdc7eab922e22d15dc75d228b64e9158eaa0e5cc14013344c",
        "old terminal SHA",
    )
    expect(
        supersession["authoritative_serialization"]["config_sha256"],
        "9ef2ca7d75ca714cb85a8afa76f1115c7ff37e0b520a6bc983736441c895095d",
        "A2F1 config SHA",
    )

    for name, expected_binding in EXPECTED_ARTIFACTS.items():
        expect(terminal["artifact_bindings"][name], expected_binding, f"terminal binding {name}")
        expect(config["exact_bindings"][name], expected_binding, f"config binding {name}")
    for name, binding in terminal["artifact_bindings"].items():
        path = root / binding["path"]
        if not path.is_file():
            raise AssertionError(f"missing bound artifact {name}: {path}")
        expect(sha256(path), binding["sha256"], f"SHA drift for {name}")

    expect(terminal["artifact_bindings"]["a2_decision"]["sha256"], sha256(root / CONFIG_PATH), "A2 config binding")
    manifest = load(root / terminal["artifact_bindings"]["guarded_production_manifest"]["path"])
    expect(manifest["status"], "ACQUIRED_GUARDED_NOT_SCORED", "guarded manifest status")
    expect(manifest["archive_count"], 84, "archive count")
    expect(manifest["checksum_count"], 84, "checksum count")
    expect(manifest["total_archive_bytes"], 82583505, "archive total")
    expect(manifest["no_extra_targets"], True, "manifest no extra targets")
    expect(manifest["eligible_for_binance_g2"], False, "manifest G2")
    expect(manifest["trading_authorization"], "DENIED", "manifest trading")

    diagnostic = load(root / terminal["artifact_bindings"]["read_only_gap_diagnostic"]["path"])
    expect(diagnostic["status"], "READ_ONLY_NOT_ACQUISITION_RECEIPT/NOT_SCORED", "diagnostic status")
    expect(diagnostic["acquisition_receipt_exists"], False, "diagnostic receipt")
    expect(diagnostic["partial_paths"], [], "diagnostic partial paths")
    expect(diagnostic["file_checksum_binding_recomputed"], True, "diagnostic checksum binding")
    expect(diagnostic["violation_count"], 1, "diagnostic violation count")
    violation = diagnostic["violations"][0]
    for key, expected in {
        "kind": "bookDepth",
        "date": "2025-02-26",
        "frozen_max_gap_ms": 60000,
        "exceeds_frozen_gap": True,
        "ordering_violation_count": 0,
    }.items():
        expect(violation[key], expected, f"gap diagnostic {key}")
    expect(violation["max_internal_gap"]["gap_ms"], 1380000, "gap duration")
    expect(violation["max_internal_gap"]["left_at"], "2025-02-26T06:26:30+00:00", "gap left")
    expect(violation["max_internal_gap"]["right_at"], "2025-02-26T06:49:30+00:00", "gap right")

    for absence in terminal["absence_assertions"]:
        if (root / absence["path"]).exists():
            raise AssertionError(f"must remain absent: {absence['path']}")

    print(json.dumps({
        "verified": True,
        "decision_id": config["decision_id"],
        "state": terminal["state"],
        "g2_eligibility": False,
        "trading_authorization": "DENIED",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
