"""Write-once final-holdout opening records for frozen research protocols."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from .protocol import ResearchProtocol, V2_SCHEMA_VERSION
from .research_report import sha256_file
from .types import iso_utc, parse_utc, utc_now


class HoldoutLedgerError(ValueError):
    pass


_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load_json(path: Path, context: str) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HoldoutLedgerError("cannot load %s" % context) from exc
    if not isinstance(value, dict):
        raise HoldoutLedgerError("%s must be an object" % context)
    return value


def _holdout(protocol: ResearchProtocol) -> Dict[str, Any]:
    protocol.assert_frozen_for_research()
    holdout = protocol.raw["split_policy"]["final_holdout"]
    if not isinstance(holdout, dict) or holdout.get("opened_at") is not None or holdout.get("reuse_policy") != "ONE_TIME_ONLY":
        raise HoldoutLedgerError("frozen protocol does not contain an unopened one-time final holdout")
    holdout_id = holdout.get("holdout_id")
    if not isinstance(holdout_id, str) or not _SAFE_ID.fullmatch(holdout_id):
        raise HoldoutLedgerError("final holdout ID must be a safe identifier")
    start, end = parse_utc(str(holdout["start"])), parse_utc(str(holdout["end"]))
    if end <= start:
        raise HoldoutLedgerError("final holdout end must follow start")
    return {"holdout_id": holdout_id, "start": iso_utc(start), "end": iso_utc(end)}


def _registry_path(registry_dir: Path, protocol: ResearchProtocol, holdout_id: str) -> Path:
    return Path(registry_dir) / ("%s.%s.final-holdout.json" % (protocol.digest, holdout_id))


def _consumption_path(registry_dir: Path, protocol: ResearchProtocol, holdout_id: str) -> Path:
    return Path(registry_dir) / ("%s.%s.final-holdout-evaluation.json" % (protocol.digest, holdout_id))


def _v2_admission(protocol: ResearchProtocol, evidence_admission: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Return a verified-by-caller v2 admission binding or keep v1 unchanged."""
    if protocol.raw.get("schema_version") != V2_SCHEMA_VERSION:
        return None
    if not isinstance(evidence_admission, dict) or evidence_admission.get("status") != "ADMITTED" or evidence_admission.get("role") != "HOLDOUT":
        raise HoldoutLedgerError("protocol v2 final holdout requires a verified HOLDOUT evidence admission")
    digest = evidence_admission.get("manifest_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise HoldoutLedgerError("HOLDOUT evidence admission digest is invalid")
    if evidence_admission.get("protocol") != {"id": protocol.protocol_id, "sha256": protocol.digest}:
        raise HoldoutLedgerError("HOLDOUT evidence admission protocol binding is invalid")
    return evidence_admission


def _eligible_counts(labels_path: Path, *, start, end) -> Dict[str, int]:
    input_rows = eligible_rows = pre_holdout = released_rows = outside_rows = 0
    try:
        handle = Path(labels_path).open("r", encoding="utf-8")
    except OSError as exc:
        raise HoldoutLedgerError("cannot read final-holdout labels") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise HoldoutLedgerError("final-holdout labels contain a blank line")
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("row is not an object")
                input_rows += 1
                if row.get("censored") or row.get("outcome") is None:
                    continue
                decision_at = parse_utc(str(row["decision_at"]))
                label_end_at = parse_utc(str(row["label_end_at"]))
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise HoldoutLedgerError("invalid final-holdout label row %d" % line_number) from exc
            eligible_rows += 1
            if label_end_at <= start:
                pre_holdout += 1
            elif decision_at >= start and label_end_at <= end:
                released_rows += 1
            else:
                outside_rows += 1
    return {
        "input_rows": input_rows,
        "eligible_rows": eligible_rows,
        "pre_holdout_eligible_rows": pre_holdout,
        "released_eligible_rows": released_rows,
        "overlap_or_post_holdout_eligible_rows": outside_rows,
    }


def _write_once(path: Path, value: Dict[str, Any], error: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with Path(path).open("x", encoding="utf-8") as handle:
            handle.write(_canonical(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise HoldoutLedgerError(error) from exc
    except OSError as exc:
        raise HoldoutLedgerError("cannot write final-holdout record") from exc


def open_final_holdout(
    *,
    protocol: ResearchProtocol,
    labels_path: Path,
    registry_dir: Path,
    output_path: Path,
    confirm_release_candidate: bool,
    confirm_no_other_writers: bool,
    evidence_admission: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Commit a one-time release receipt; this does not evaluate or trade."""
    if not confirm_release_candidate or not confirm_no_other_writers:
        raise HoldoutLedgerError("opening final holdout requires both explicit confirmations")
    holdout = _holdout(protocol)
    admission = _v2_admission(protocol, evidence_admission)
    registry = _registry_path(Path(registry_dir), protocol, holdout["holdout_id"])
    if registry.exists():
        raise HoldoutLedgerError("final holdout is already opened in this controlled registry")
    counts = _eligible_counts(Path(labels_path), start=parse_utc(holdout["start"]), end=parse_utc(holdout["end"]))
    if counts["released_eligible_rows"] < 1:
        raise HoldoutLedgerError("final holdout has no eligible labeled observations; it remains unopened")
    release = {
        "record_type": "final_holdout_release",
        "schema_version": "final-holdout-release.v1",
        "release_status": "FINAL_HOLDOUT_OPENED_ONCE",
        "opened_at": iso_utc(utc_now()),
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.digest,
        "holdout": holdout,
        "labels_path": str(labels_path),
        "labels_sha256": sha256_file(Path(labels_path)),
        "counts": counts,
        "registry_path": str(registry),
        "limitation": "This is a local one-time opening receipt only. It does not evaluate a model, authorize parameter changes, prove out-of-sample quality, clear a trading gate, or permit orders.",
    }
    if admission is not None:
        release["holdout_evidence_admission_sha256"] = admission["manifest_sha256"]
    release["release_sha256"] = _digest(release)
    _write_once(Path(output_path), release, "final-holdout release output already exists")
    registry_record = {
        "record_type": "final_holdout_registry_entry",
        "schema_version": "final-holdout-registry.v1",
        "protocol_sha256": protocol.digest,
        "holdout_id": holdout["holdout_id"],
        "release_path": str(output_path),
        "release_sha256": release["release_sha256"],
    }
    _write_once(registry, registry_record, "final holdout is already opened in this controlled registry")
    return release


def verify_final_holdout_release(
    *, protocol: ResearchProtocol,
    labels_path: Path,
    registry_dir: Path,
    release_path: Path,
    evidence_admission: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    holdout = _holdout(protocol)
    admission = _v2_admission(protocol, evidence_admission)
    release = _load_json(Path(release_path), "final-holdout release")
    registry = _registry_path(Path(registry_dir), protocol, holdout["holdout_id"])
    entry = _load_json(registry, "final-holdout registry entry")
    without_digest = dict(release)
    declared_digest = without_digest.pop("release_sha256", None)
    valid = (
        release.get("record_type") == "final_holdout_release"
        and declared_digest == _digest(without_digest)
        and release.get("protocol_id") == protocol.protocol_id
        and release.get("protocol_sha256") == protocol.digest
        and release.get("holdout") == holdout
        and release.get("labels_sha256") == sha256_file(Path(labels_path))
        and entry.get("protocol_sha256") == protocol.digest
        and entry.get("holdout_id") == holdout["holdout_id"]
        and entry.get("release_sha256") == declared_digest
        and entry.get("release_path") == str(release_path)
    )
    if admission is not None:
        valid = valid and release.get("holdout_evidence_admission_sha256") == admission["manifest_sha256"]
    return {
        "record_type": "final_holdout_release_verification",
        "valid": valid,
        "release_path": str(release_path),
        "registry_path": str(registry),
        "protocol_sha256": protocol.digest,
        "holdout_id": holdout["holdout_id"],
        "limitation": "Verification binds one local release receipt to its controlled registry and exact labels file; it does not score a model or establish trading readiness.",
    }


def consume_final_holdout_release(
    *,
    protocol: ResearchProtocol,
    labels_path: Path,
    registry_dir: Path,
    release_path: Path,
    evaluation_report_path: Path,
    evaluation_report_sha256: str,
    evidence_admission: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Bind a successful or inconclusive final evaluation to the only receipt.

    The receipt is consumed even for a valid inconclusive evaluation: once the
    holdout labels have been read, tuning and re-opening it would be invalid.
    """
    verification = verify_final_holdout_release(
        protocol=protocol, labels_path=labels_path, registry_dir=registry_dir, release_path=release_path, evidence_admission=evidence_admission,
    )
    if not verification["valid"]:
        raise HoldoutLedgerError("cannot consume an invalid final-holdout release")
    if not isinstance(evaluation_report_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", evaluation_report_sha256):
        raise HoldoutLedgerError("evaluation report must have a lowercase SHA-256")
    if sha256_file(Path(evaluation_report_path)) != evaluation_report_sha256:
        raise HoldoutLedgerError("evaluation report SHA-256 does not match its exact file")
    holdout = _holdout(protocol)
    release = _load_json(Path(release_path), "final-holdout release")
    target = _consumption_path(Path(registry_dir), protocol, holdout["holdout_id"])
    consumption = {
        "record_type": "final_holdout_evaluation_consumption",
        "schema_version": "final-holdout-evaluation-consumption.v1",
        "protocol_sha256": protocol.digest,
        "holdout_id": holdout["holdout_id"],
        "release_path": str(release_path),
        "release_sha256": release["release_sha256"],
        "evaluation_report_path": str(evaluation_report_path),
        "evaluation_report_sha256": evaluation_report_sha256,
        "labels_sha256": sha256_file(Path(labels_path)),
    }
    admission = _v2_admission(protocol, evidence_admission)
    if admission is not None:
        consumption["holdout_evidence_admission_sha256"] = admission["manifest_sha256"]
    consumption["consumption_sha256"] = _digest(consumption)
    _write_once(target, consumption, "final holdout receipt is already consumed by an evaluation")
    return consumption
