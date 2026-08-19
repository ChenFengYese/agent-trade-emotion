"""Offline audit of a Binance USD-M aggTrade archive against forward evidence.

The archive is only a second representation of a limited observed interval. It
does not contain L2 state, cannot restore a disconnected forward capture, and
is deliberately kept outside all G1/G2 eligibility decisions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Tuple

from .collection_inventory import inventory_collections
from .event_store import EventStore
from .replay import DeterministicReplay
from .source_registry import SourceRegistry


FROZEN_BINANCE_ARCHIVE_OVERLAP_PLAN = "FROZEN_BINANCE_ARCHIVE_OVERLAP_PLAN"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REQUIRED_COLUMNS = (
    "agg_trade_id",
    "price",
    "qty",
    "first_trade_id",
    "last_trade_id",
    "transact_time",
    "is_buyer_maker",
)


class BinanceArchiveOverlapError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BinanceArchiveOverlapError("%s must be a non-empty string" % field)
    return value


def _utc_day(value: str) -> str:
    try:
        return datetime.fromisoformat(value + "T00:00:00+00:00").date().isoformat()
    except ValueError as exc:
        raise BinanceArchiveOverlapError("archive.date must be ISO YYYY-MM-DD") from exc


def _integer(value: Any, field: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise BinanceArchiveOverlapError("%s must be an integer" % field) from exc
    if parsed < 0:
        raise BinanceArchiveOverlapError("%s must be non-negative" % field)
    return parsed


def _decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BinanceArchiveOverlapError("%s must be a decimal" % field) from exc
    if not parsed.is_finite() or parsed <= 0:
        raise BinanceArchiveOverlapError("%s must be a positive finite decimal" % field)
    return parsed


def _bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise BinanceArchiveOverlapError("%s must be true or false" % field)


def _timestamp_ms(value: Any, field: str) -> int:
    parsed = _integer(value, field)
    if parsed < 10_000_000_000:
        raise BinanceArchiveOverlapError("%s must be Unix milliseconds" % field)
    return parsed


def _datetime_ms(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


@dataclass(frozen=True)
class BinanceArchiveOverlapPlan:
    audit_id: str
    source_registry_id: str
    source_registry_sha256: str
    instrument: str
    archive_date: str
    archive_source_id: str
    archive_source_url: str
    archive_path: str
    archive_checksum_source_url: str
    archive_checksum_path: str
    archive_sha256: str
    data_dir: str
    collection_id: str
    digest: str

    @classmethod
    def load(cls, path: Path) -> "BinanceArchiveOverlapPlan":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BinanceArchiveOverlapError("cannot load Binance archive overlap plan") from exc
        if not isinstance(raw, dict):
            raise BinanceArchiveOverlapError("Binance archive overlap plan must be an object")
        if raw.get("status") != FROZEN_BINANCE_ARCHIVE_OVERLAP_PLAN:
            raise BinanceArchiveOverlapError("plan must use status %s" % FROZEN_BINANCE_ARCHIVE_OVERLAP_PLAN)
        audit_id = _required_string(raw.get("audit_id"), "audit_id")
        registry = raw.get("source_registry")
        if not isinstance(registry, dict):
            raise BinanceArchiveOverlapError("source_registry must be an object")
        registry_id = _required_string(registry.get("registry_id"), "source_registry.registry_id")
        registry_sha = _required_string(registry.get("sha256"), "source_registry.sha256")
        if not _SHA256.fullmatch(registry_sha):
            raise BinanceArchiveOverlapError("source_registry.sha256 must be lowercase SHA-256")
        archive = raw.get("archive")
        if not isinstance(archive, dict):
            raise BinanceArchiveOverlapError("archive must be an object")
        archive_date = _utc_day(_required_string(archive.get("date"), "archive.date"))
        archive_source_id = _required_string(archive.get("source_id"), "archive.source_id")
        if archive_source_id != "SRC-BIN-ARCHIVE":
            raise BinanceArchiveOverlapError("archive.source_id must be SRC-BIN-ARCHIVE")
        archive_source_url = _required_string(archive.get("source_url"), "archive.source_url")
        if not archive_source_url.startswith("https://data.binance.vision/data/futures/um/"):
            raise BinanceArchiveOverlapError("archive.source_url must point to the official Binance USD-M archive")
        archive_path = _required_string(archive.get("path"), "archive.path")
        checksum_source_url = _required_string(archive.get("checksum_source_url"), "archive.checksum_source_url")
        if not checksum_source_url.startswith("https://data.binance.vision/data/futures/um/") or not checksum_source_url.endswith(".CHECKSUM"):
            raise BinanceArchiveOverlapError("archive.checksum_source_url must point to the official archive .CHECKSUM")
        checksum_path = _required_string(archive.get("checksum_path"), "archive.checksum_path")
        archive_sha = _required_string(archive.get("sha256"), "archive.sha256")
        if not _SHA256.fullmatch(archive_sha):
            raise BinanceArchiveOverlapError("archive.sha256 must be lowercase SHA-256")
        if tuple(archive.get("columns", ())) != _REQUIRED_COLUMNS:
            raise BinanceArchiveOverlapError("archive.columns must equal the official USD-M aggTrade CSV schema")
        forward = raw.get("forward_collection")
        if not isinstance(forward, dict):
            raise BinanceArchiveOverlapError("forward_collection must be an object")
        return cls(
            audit_id=audit_id,
            source_registry_id=registry_id,
            source_registry_sha256=registry_sha,
            instrument=_required_string(raw.get("instrument"), "instrument").upper(),
            archive_date=archive_date,
            archive_source_id=archive_source_id,
            archive_source_url=archive_source_url,
            archive_path=archive_path,
            archive_checksum_source_url=checksum_source_url,
            archive_checksum_path=checksum_path,
            archive_sha256=archive_sha,
            data_dir=_required_string(forward.get("data_dir"), "forward_collection.data_dir"),
            collection_id=_required_string(forward.get("collection_id"), "forward_collection.collection_id"),
            digest=hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest(),
        )


def _archive_rows(path: Path) -> Iterator[Dict[str, str]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            if len(names) != 1:
                raise BinanceArchiveOverlapError("archive zip must contain exactly one CSV data file")
            with archive.open(names[0], "r") as binary:
                yield from _csv_rows(binary)
        return
    with path.open("rb") as binary:
        yield from _csv_rows(binary)


def _csv_rows(binary: Any) -> Iterator[Dict[str, str]]:
    import io

    with io.TextIOWrapper(binary, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _REQUIRED_COLUMNS:
            raise BinanceArchiveOverlapError("archive CSV header does not match declared official aggTrade schema")
        for row in reader:
            yield dict(row)


def _resolved(path: str, base_dir: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else (base_dir / candidate).resolve()


def _official_checksum(path: Path, archive_name: str) -> str:
    if not path.is_file():
        raise BinanceArchiveOverlapError("declared official .CHECKSUM file is missing")
    try:
        parts = path.read_text(encoding="utf-8").strip().split()
    except (OSError, UnicodeDecodeError) as exc:
        raise BinanceArchiveOverlapError("cannot read declared official .CHECKSUM file") from exc
    if len(parts) != 2 or not _SHA256.fullmatch(parts[0]) or parts[1].lstrip("*") != archive_name:
        raise BinanceArchiveOverlapError("official .CHECKSUM must contain the exact archive filename and one SHA-256")
    return parts[0]


def _current_collection(plan: BinanceArchiveOverlapPlan, data_dir: Path) -> Dict[str, Any]:
    inventory = inventory_collections((data_dir,))
    matching = [item for item in inventory["collections"] if item.get("collection_id") == plan.collection_id and Path(item.get("data_dir", "")).resolve() == data_dir.resolve()]
    if len(matching) != 1:
        raise BinanceArchiveOverlapError("exactly one terminal manifest is required for the declared collection")
    row = matching[0]
    if row.get("status") != "SEALED_CURRENT":
        raise BinanceArchiveOverlapError("forward collection must be SEALED_CURRENT")
    binding = row.get("source_registry")
    if not isinstance(binding, dict) or binding.get("registry_id") != plan.source_registry_id or binding.get("sha256") != plan.source_registry_sha256:
        raise BinanceArchiveOverlapError("forward collection source registry binding differs from plan")
    return row


def _forward_trades(plan: BinanceArchiveOverlapPlan, store: EventStore) -> Tuple[Dict[int, Dict[str, Any]], int]:
    trades: Dict[int, Dict[str, Any]] = {}
    duplicate_ids = 0
    prefix = plan.collection_id + "-"
    for event in DeterministicReplay(store).events():
        if not event.raw.connection_id.startswith(prefix) or event.availability.normalized.get("kind") != "trade":
            continue
        if event.raw.instrument.upper() != plan.instrument or event.availability.availability_kind.value != "ACTUAL":
            continue
        normalized = event.availability.normalized
        trade_id = _integer(normalized.get("exchange_trade_id"), "forward exchange_trade_id")
        item = {
            "price": _decimal(normalized.get("price"), "forward price"),
            "qty": _decimal(normalized.get("quantity"), "forward quantity"),
            "buyer_maker": str(normalized.get("side")) == "SELL",
            "timestamp_ms": _datetime_ms(event.raw.exchange_event_time) if event.raw.exchange_event_time else None,
        }
        if item["timestamp_ms"] is None:
            raise BinanceArchiveOverlapError("forward aggTrade is missing exchange event time")
        if trade_id in trades:
            duplicate_ids += 1
            continue
        trades[trade_id] = item
    if not trades:
        raise BinanceArchiveOverlapError("forward collection has no ACTUAL aggTrade records")
    return trades, duplicate_ids


def audit_binance_aggtrade_overlap(
    plan: BinanceArchiveOverlapPlan,
    *,
    base_dir: Path,
    source_registry_path: Path,
) -> Dict[str, Any]:
    """Validate exact matching aggTrade records without claiming full coverage."""
    registry = SourceRegistry.load(source_registry_path)
    if registry.registry_id != plan.source_registry_id or registry.sha256 != plan.source_registry_sha256:
        raise BinanceArchiveOverlapError("supplied source registry differs from frozen plan")
    if not any(source.source_id == "SRC-BIN-FUT-WS" and source.venue == "BINANCE_USDM" and source.supports_instrument(plan.instrument) for source in registry.sources):
        raise BinanceArchiveOverlapError("source registry lacks a Binance USD-M websocket contract for the instrument")
    data_dir = _resolved(plan.data_dir, base_dir)
    collection = _current_collection(plan, data_dir)
    archive_path = _resolved(plan.archive_path, base_dir)
    if not archive_path.is_file():
        raise BinanceArchiveOverlapError("declared archive file is missing")
    checksum_path = _resolved(plan.archive_checksum_path, base_dir)
    official_sha = _official_checksum(checksum_path, archive_path.name)
    if official_sha != plan.archive_sha256:
        raise BinanceArchiveOverlapError("official .CHECKSUM differs from frozen archive SHA-256")
    observed_sha = _sha256_file(archive_path)
    if observed_sha != plan.archive_sha256:
        raise BinanceArchiveOverlapError("archive SHA-256 differs from frozen plan")
    forward, duplicate_forward_ids = _forward_trades(plan, EventStore(data_dir, create=False))
    archive_records = archive_duplicate_ids = archive_date_mismatches = matching_records = payload_mismatches = 0
    archive_ids = set()
    first_time = last_time = None
    for row in _archive_rows(archive_path):
        trade_id = _integer(row.get("agg_trade_id"), "archive agg_trade_id")
        price = _decimal(row.get("price"), "archive price")
        quantity = _decimal(row.get("qty"), "archive qty")
        timestamp_ms = _timestamp_ms(row.get("transact_time"), "archive transact_time")
        buyer_maker = _bool(row.get("is_buyer_maker"), "archive is_buyer_maker")
        archive_records += 1
        archive_duplicate_ids += int(trade_id in archive_ids)
        archive_ids.add(trade_id)
        event_date = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()
        archive_date_mismatches += int(event_date != plan.archive_date)
        first_time = timestamp_ms if first_time is None else min(first_time, timestamp_ms)
        last_time = timestamp_ms if last_time is None else max(last_time, timestamp_ms)
        candidate = forward.get(trade_id)
        if candidate is not None:
            matching_records += 1
            if candidate != {"price": price, "qty": quantity, "buyer_maker": buyer_maker, "timestamp_ms": timestamp_ms}:
                payload_mismatches += 1
    archive_ok = bool(archive_records) and archive_duplicate_ids == 0 and archive_date_mismatches == 0
    overlap_verified = archive_ok and matching_records > 0 and payload_mismatches == 0
    return {
        "record_type": "binance_usdm_aggtrade_archive_overlap_audit",
        "audit_id": plan.audit_id,
        "audit_plan_sha256": plan.digest,
        "source_registry": {"registry_id": registry.registry_id, "sha256": registry.sha256},
        "instrument": plan.instrument,
        "archive": {
            "source_id": plan.archive_source_id, "source_url": plan.archive_source_url,
            "checksum_source_url": plan.archive_checksum_source_url, "checksum_path": str(checksum_path),
            "path": str(archive_path), "sha256": observed_sha, "declared_date": plan.archive_date,
            "records": archive_records, "duplicate_trade_ids": archive_duplicate_ids,
            "date_mismatches": archive_date_mismatches, "first_event_time_ms": first_time, "last_event_time_ms": last_time,
        },
        "forward_collection": {
            "data_dir": str(data_dir), "collection_id": plan.collection_id,
            "audit_digest": collection["current_audit_digest"], "replay_digest": collection["current_replay_digest"],
            "unique_actual_aggtrades": len(forward), "duplicate_actual_aggtrade_ids": duplicate_forward_ids,
        },
        "overlap": {"matching_aggregate_trade_ids": matching_records, "payload_mismatches": payload_mismatches, "verified": overlap_verified},
        "complete": overlap_verified,
        "limitation": "This validates exact agreement for only aggregate-trade IDs observed by the forward collector and present in one pinned archive file. It does not prove the archive is complete, prove the collector saw every trade, repair outages, validate L2/OI/funding, establish G1/G2/G3, estimate execution costs, or authorize trading.",
    }
