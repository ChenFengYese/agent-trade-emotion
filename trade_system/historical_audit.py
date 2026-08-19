"""Read-only audit for downloaded historical market-data samples.

The auditor does not download data, infer missing dates or treat an external
venue as evidence for Binance execution.  It turns a declared local file plan
into a write-once report containing the evidence needed before an OKX L2 sample
can be used for replay engineering or external-mechanism experiments.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


FROZEN_OKX_AUDIT_PLAN = "FROZEN_OKX_HISTORICAL_AUDIT_PLAN"


class HistoricalAuditError(ValueError):
    pass


def _canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (OSError, TypeError, ValueError):
        return None


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _open_text(path: Path):
    suffixes = path.suffixes
    if suffixes[-1:] == [".gz"]:
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    if suffixes[-1:] == [".zip"]:
        archive = zipfile.ZipFile(path)
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            archive.close()
            raise HistoricalAuditError("zip file must contain exactly one data file")
        handle = archive.open(names[0], "r")
        return __import__("io").TextIOWrapper(handle, encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _format_for(path: Path, requested: str) -> str:
    if requested != "AUTO":
        return requested
    name = path.name.lower()
    for suffix in (".csv.gz", ".csv.zip", ".csv", ".jsonl.gz", ".jsonl.zip", ".jsonl", ".ndjson.gz", ".ndjson"):
        if name.endswith(suffix):
            return "CSV" if ".csv" in suffix else "JSONL"
    return "UNKNOWN"


@dataclass(frozen=True)
class HistoricalFilePlan:
    date: str
    path: str
    instrument: str
    stream: str
    format: str
    timestamp_path: str
    bids_path: str
    asks_path: str


@dataclass(frozen=True)
class HistoricalAuditPlan:
    audit_id: str
    status: str
    source_id: str
    venue: str
    purpose: str
    files: Tuple[HistoricalFilePlan, ...]
    sha256: str

    @classmethod
    def load(cls, path: Path) -> "HistoricalAuditPlan":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HistoricalAuditError("cannot load historical audit plan") from exc
        if not isinstance(raw, dict):
            raise HistoricalAuditError("historical audit plan must be an object")
        for key in ("audit_id", "status", "source_id", "venue", "purpose"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                raise HistoricalAuditError("historical audit plan requires %s" % key)
        if raw["source_id"] != "SRC-OKX-HIST" or raw["venue"] != "OKX":
            raise HistoricalAuditError("this auditor is restricted to SRC-OKX-HIST / OKX")
        if raw["purpose"] != "REPLAY_AND_EXTERNAL_MECHANISM_ONLY":
            raise HistoricalAuditError("OKX audit must remain replay and external-mechanism only")
        entries = raw.get("files", [])
        if not isinstance(entries, list):
            raise HistoricalAuditError("files must be a list")
        plans = []
        seen_dates = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise HistoricalAuditError("file entry must be an object")
            required = ("date", "path", "instrument", "stream", "timestamp_path", "bids_path", "asks_path")
            if any(not isinstance(entry.get(field), str) or not entry[field] for field in required):
                raise HistoricalAuditError("file entry has incomplete schema paths")
            if raw["status"] == FROZEN_OKX_AUDIT_PLAN:
                try:
                    datetime.fromisoformat(entry["date"] + "T00:00:00+00:00")
                except ValueError as exc:
                    raise HistoricalAuditError("frozen audit plan requires ISO YYYY-MM-DD dates") from exc
            if entry["date"] in seen_dates:
                raise HistoricalAuditError("audit plan may contain one entry per date")
            seen_dates.add(entry["date"])
            file_format = str(entry.get("format", "AUTO")).upper()
            if file_format not in {"AUTO", "JSONL", "CSV"}:
                raise HistoricalAuditError("unsupported file format")
            plans.append(HistoricalFilePlan(
                date=entry["date"], path=entry["path"], instrument=entry["instrument"], stream=entry["stream"],
                format=file_format, timestamp_path=entry["timestamp_path"], bids_path=entry["bids_path"], asks_path=entry["asks_path"],
            ))
        if raw["status"] == FROZEN_OKX_AUDIT_PLAN and not plans:
            raise HistoricalAuditError("frozen audit plan requires at least one file")
        return cls(raw["audit_id"], raw["status"], raw["source_id"], raw["venue"], raw["purpose"], tuple(plans), hashlib.sha256(_canonical_json(raw).encode("utf-8")).hexdigest())


def _rows(path: Path, file_format: str, limit: int) -> Iterable[Dict[str, Any]]:
    with _open_text(path) as handle:
        if file_format == "JSONL":
            for count, line in enumerate(handle):
                if count >= limit:
                    break
                if line.strip():
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise HistoricalAuditError("JSONL row must be an object")
                    yield value
        elif file_format == "CSV":
            reader = csv.DictReader(handle)
            for count, row in enumerate(reader):
                if count >= limit:
                    break
                yield dict(row)
        else:
            raise HistoricalAuditError("cannot inspect unknown data format")


def audit_plan(plan: HistoricalAuditPlan, *, base_dir: Path, sample_limit: int = 1000) -> Dict[str, Any]:
    if sample_limit <= 0:
        raise HistoricalAuditError("sample_limit must be positive")
    results: List[Dict[str, Any]] = []
    complete = True
    for item in plan.files:
        path = (base_dir / item.path).resolve() if not Path(item.path).is_absolute() else Path(item.path)
        row: Dict[str, Any] = {"date": item.date, "path": str(path), "instrument": item.instrument, "stream": item.stream}
        if not path.is_file():
            row.update({"status": "MISSING", "reason": "declared historical file is not present"})
            complete = False
            results.append(row)
            continue
        file_format = _format_for(path, item.format)
        row.update({"status": "PRESENT", "format": file_format, "byte_count": path.stat().st_size, "sha256": _sha256_bytes(path)})
        try:
            sampled = list(_rows(path, file_format, sample_limit))
            timestamps = [_parse_time(_path_value(value, item.timestamp_path)) for value in sampled]
            timestamps = [value for value in timestamps if value is not None]
            bid_depths = [_path_value(value, item.bids_path) for value in sampled]
            ask_depths = [_path_value(value, item.asks_path) for value in sampled]
            if not sampled or not timestamps or not all(isinstance(value, list) for value in bid_depths + ask_depths):
                raise HistoricalAuditError("sample does not satisfy declared timestamp/book paths")
            dates = sorted({value.date().isoformat() for value in timestamps})
            row.update({
                "sampled_rows": len(sampled),
                "observed_dates": dates,
                "requested_date_observed": item.date in dates,
                "first_event_time": min(timestamps).isoformat().replace("+00:00", "Z"),
                "last_event_time": max(timestamps).isoformat().replace("+00:00", "Z"),
                "max_bid_levels_in_sample": max(len(value) for value in bid_depths),
                "max_ask_levels_in_sample": max(len(value) for value in ask_depths),
            })
            if item.date not in dates:
                row.update({"status": "DATE_MISMATCH", "reason": "sample timestamps do not cover declared date"})
                complete = False
        except (OSError, UnicodeDecodeError, csv.Error, json.JSONDecodeError, HistoricalAuditError) as exc:
            row.update({"status": "UNREADABLE_OR_SCHEMA_MISMATCH", "reason": str(exc)})
            complete = False
        results.append(row)
    return {
        "audit_id": plan.audit_id,
        "audit_plan_status": plan.status,
        "audit_plan_sha256": plan.sha256,
        "source_id": plan.source_id,
        "venue": plan.venue,
        "purpose": plan.purpose,
        "eligible_for_binance_g2": False,
        "files": results,
        "complete": complete and bool(results),
        "limitation": "This is a local file/sample audit. It does not prove full-day completeness, exchange capture completeness, Binance equivalence, execution cost, or Binance G2 eligibility.",
    }


def write_audit_report(path: Path, report: Dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(_canonical_json(report) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path
