"""Write-once G1 validation reports for binding later research protocols."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

from .types import iso_utc, utc_now


class G1ReportError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_g1_report(path: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    """Persist one validation result without allowing a later overwrite."""
    if not isinstance(report, dict) or "policy_id" not in report or "status" not in report:
        raise G1ReportError("invalid G1 validation report")
    output = dict(report)
    output.update({
        "record_type": "g1_validation_report",
        "written_at": iso_utc(utc_now()),
    })
    output["report_sha256"] = hashlib.sha256(_canonical(output).encode("utf-8")).hexdigest()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise G1ReportError("G1 report already exists: %s" % target)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise G1ReportError("cannot write G1 report") from exc
    return output


def load_verified_g1_report(path: Path, *, require_pass: bool = True) -> Dict[str, Any]:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise G1ReportError("cannot load G1 report") from exc
    if not isinstance(report, dict) or report.get("record_type") != "g1_validation_report":
        raise G1ReportError("invalid G1 report record type")
    digest = report.get("report_sha256")
    if not isinstance(digest, str):
        raise G1ReportError("G1 report digest is missing")
    body = dict(report)
    body.pop("report_sha256", None)
    actual = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    if digest != actual:
        raise G1ReportError("G1 report digest does not match content")
    if require_pass and (report.get("status") != "PASS" or report.get("passed") is not True):
        raise G1ReportError("G1 report is not a PASS")
    return report


def load_passed_g1_report(
    path: Path,
    *,
    policy_id: str,
    expected_sha256: str,
    expected_policy_sha256: str = "",
) -> Dict[str, Any]:
    report = load_verified_g1_report(path, require_pass=True)
    if report["report_sha256"] != expected_sha256:
        raise G1ReportError("G1 report digest does not match frozen protocol")
    if report.get("policy_id") != policy_id:
        raise G1ReportError("G1 report policy ID does not match frozen protocol")
    if expected_policy_sha256 and report.get("policy_sha256") != expected_policy_sha256:
        raise G1ReportError("G1 report policy digest does not match frozen protocol")
    return report
