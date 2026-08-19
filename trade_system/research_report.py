"""Write-once research-run reports and their reproducibility bindings."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

from .types import iso_utc, utc_now


class ResearchReportError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise ResearchReportError("cannot hash research input") from exc
    return digest.hexdigest()


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_research_report(path: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, dict) or not report.get("research_status"):
        raise ResearchReportError("research report requires research_status")
    output = dict(report)
    output.update({
        "record_type": "research_baseline_report",
        "written_at": iso_utc(utc_now()),
    })
    output["report_sha256"] = hashlib.sha256(_canonical(output).encode("utf-8")).hexdigest()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ResearchReportError("research report already exists: %s" % target)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ResearchReportError("cannot write research report") from exc
    return output
