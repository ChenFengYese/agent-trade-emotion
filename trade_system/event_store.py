"""Append-only capture and availability storage with point-in-time invariants."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .types import (
    AvailabilityKind,
    AvailabilityRecord,
    RawCapture,
    iso_utc,
    parse_utc,
    utc_now,
)


class EventStoreError(RuntimeError):
    """Raised when append-only or point-in-time evidence is violated."""


def _canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _payload_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class EventStore:
    """Single-writer NDJSON store.

    A raw record is never rewritten. Availability records are independently
    appended so a newer parser cannot alter the historical raw evidence.
    """

    def __init__(self, root: Path, *, create: bool = True) -> None:
        self.root = Path(root)
        self.raw_root = self.root / "raw"
        self.availability_root = self.root / "availability"
        self.manifest_root = self.root / "manifests" / "raw"
        self.collection_manifest_root = self.root / "manifests" / "collection"
        self.lock_path = self.root / ".writer.lock"
        if create:
            self.raw_root.mkdir(parents=True, exist_ok=True)
            self.availability_root.mkdir(parents=True, exist_ok=True)
            self.manifest_root.mkdir(parents=True, exist_ok=True)
            self.collection_manifest_root.mkdir(parents=True, exist_ok=True)
            self.lock_path.touch(exist_ok=True)
        elif not self.root.exists():
            raise EventStoreError("evidence store does not exist: %s" % self.root)
        self._capture_seq_cache: Optional[int] = None
        self._event_id_cache: Optional[set] = None

    @contextmanager
    def _writer_lock(self) -> Iterator[None]:
        with self.lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _segment_for(root: Path, timestamp: datetime) -> Path:
        return root / (timestamp.strftime("%Y-%m-%d") + ".ndjson")

    def _max_capture_seq(self) -> int:
        max_seq = 0
        for path in self.raw_root.glob("*.ndjson"):
            with path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    try:
                        max_seq = max(max_seq, int(json.loads(raw_line)["capture_seq"]))
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise EventStoreError("cannot determine capture sequence from %s" % path) from exc
        return max_seq

    def _next_capture_seq(self) -> int:
        if self._capture_seq_cache is None:
            self._capture_seq_cache = self._max_capture_seq()
        self._capture_seq_cache += 1
        return self._capture_seq_cache

    def _event_ids(self) -> set:
        if self._event_id_cache is None:
            self._event_id_cache = {raw.event_id for raw in self.iter_raw()}
        return self._event_id_cache

    @staticmethod
    def _append_line(path: Path, data: Dict[str, Any]) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = _canonical_json(data) + "\n"
        with path.open("a+", encoding="utf-8") as handle:
            handle.seek(0, os.SEEK_END)
            offset = handle.tell()
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        return offset

    @staticmethod
    def _segment_checksum(path: Path) -> Tuple[str, int, int]:
        digest = hashlib.sha256()
        byte_count = 0
        record_count = 0
        with path.open("rb") as handle:
            for line in handle:
                digest.update(line)
                byte_count += len(line)
                if line.strip():
                    record_count += 1
        return digest.hexdigest(), byte_count, record_count

    @staticmethod
    def _validate_segment_name(segment: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", segment):
            raise ValueError("segment must be YYYY-MM-DD")
        return segment

    def seal_raw_segment(self, segment: str) -> Path:
        """Seal a completed raw segment once; sealed segments cannot be appended."""
        segment = self._validate_segment_name(segment)
        raw_path = self.raw_root / (segment + ".ndjson")
        manifest_path = self.manifest_root / (segment + ".json")
        if not raw_path.exists():
            raise EventStoreError("raw segment does not exist: %s" % segment)
        with self._writer_lock():
            if manifest_path.exists():
                raise EventStoreError("raw segment already sealed: %s" % segment)
            checksum, byte_count, record_count = self._segment_checksum(raw_path)
            manifest = {
                "segment": segment,
                "sha256": checksum,
                "byte_count": byte_count,
                "record_count": record_count,
                "sealed_at": iso_utc(utc_now()),
            }
            serialized = _canonical_json(manifest) + "\n"
            with manifest_path.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
        return manifest_path

    def write_collection_manifest(self, collection_id: str, payload: Dict[str, Any]) -> Path:
        """Persist one terminal collection summary without overwriting evidence."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", collection_id):
            raise ValueError("collection_id contains unsupported characters")
        if not isinstance(payload, dict):
            raise ValueError("collection manifest payload must be an object")
        manifest_path = self.collection_manifest_root / (collection_id + ".json")
        manifest = dict(payload)
        manifest.update({
            "record_type": "collection_manifest",
            "collection_id": collection_id,
            "written_at": iso_utc(utc_now()),
        })
        with self._writer_lock():
            if manifest_path.exists():
                raise EventStoreError("collection manifest already exists: %s" % collection_id)
            serialized = _canonical_json(manifest) + "\n"
            with manifest_path.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
        return manifest_path

    def append_raw(
        self,
        *,
        source: str,
        venue: str,
        instrument: str,
        stream: str,
        connection_id: str,
        ingest_seq: int,
        payload: Dict[str, Any],
        receive_time: Optional[datetime] = None,
        exchange_event_time: Optional[datetime] = None,
        venue_trade_date: Optional[str] = None,
        source_as_of: Optional[datetime] = None,
        publish_time: Optional[datetime] = None,
    ) -> RawCapture:
        if ingest_seq <= 0:
            raise ValueError("ingest_seq must be positive")
        received = receive_time or utc_now()
        if received.tzinfo is None:
            raise ValueError("receive_time must be timezone aware")
        payload_hash = _payload_hash(payload)
        event_id = "%s/%s/%s" % (source, connection_id, ingest_seq)
        segment = self._segment_for(self.raw_root, received)

        with self._writer_lock():
            if (self.manifest_root / (segment.stem + ".json")).exists():
                raise EventStoreError("cannot append to sealed raw segment: %s" % segment.stem)
            if event_id in self._event_ids():
                raise EventStoreError("duplicate source/connection/ingest event_id: %s" % event_id)
            capture_seq = self._next_capture_seq()
            with segment.open("a+", encoding="utf-8") as handle:
                handle.seek(0, os.SEEK_END)
                offset = handle.tell()
                raw = RawCapture(
                    event_id=event_id,
                    source=source,
                    venue=venue,
                    instrument=instrument,
                    stream=stream,
                    connection_id=connection_id,
                    ingest_seq=ingest_seq,
                    capture_seq=capture_seq,
                    receive_time=received,
                    receive_monotonic_ns=time.monotonic_ns(),
                    payload=payload,
                    payload_hash=payload_hash,
                    raw_segment=str(segment.relative_to(self.root)),
                    raw_offset=offset,
                    exchange_event_time=exchange_event_time,
                    venue_trade_date=venue_trade_date,
                    source_as_of=source_as_of,
                    publish_time=publish_time,
                )
                handle.write(_canonical_json(raw.to_dict()) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._event_ids().add(event_id)
        return raw

    def append_availability(self, raw: RawCapture, record: AvailabilityRecord) -> None:
        if raw.event_id != record.event_id:
            raise EventStoreError("availability record must reference its raw event")
        if record.available_at < raw.receive_time:
            raise EventStoreError("available_at cannot predate raw receive_time")
        if record.availability_kind == AvailabilityKind.ACTUAL and record.derived_at < raw.receive_time:
            raise EventStoreError("ACTUAL derived_at cannot predate raw receive_time")
        segment = self._segment_for(self.availability_root, record.derived_at)
        with self._writer_lock():
            self._append_line(segment, record.to_dict())

    @staticmethod
    def _raw_from_dict(value: Dict[str, Any]) -> RawCapture:
        return RawCapture(
            event_id=value["event_id"],
            source=value["source"],
            venue=value["venue"],
            instrument=value["instrument"],
            stream=value["stream"],
            connection_id=value["connection_id"],
            ingest_seq=int(value["ingest_seq"]),
            capture_seq=int(value["capture_seq"]),
            receive_time=parse_utc(value["receive_time"]),
            receive_monotonic_ns=int(value["receive_monotonic_ns"]),
            payload=value["payload"],
            payload_hash=value["payload_hash"],
            raw_segment=value["raw_segment"],
            raw_offset=int(value["raw_offset"]),
            exchange_event_time=parse_utc(value["exchange_event_time"]) if value.get("exchange_event_time") else None,
            venue_trade_date=value.get("venue_trade_date"),
            source_as_of=parse_utc(value["source_as_of"]) if value.get("source_as_of") else None,
            publish_time=parse_utc(value["publish_time"]) if value.get("publish_time") else None,
        )

    @staticmethod
    def _availability_from_dict(value: Dict[str, Any]) -> AvailabilityRecord:
        return AvailabilityRecord(
            event_id=value["event_id"],
            schema_version=value["schema_version"],
            derived_at=parse_utc(value["derived_at"]),
            available_at=parse_utc(value["available_at"]),
            availability_kind=AvailabilityKind(value["availability_kind"]),
            quality_flags=list(value.get("quality_flags", [])),
            sequence_start=value.get("sequence_start"),
            sequence_end=value.get("sequence_end"),
            normalized=dict(value.get("normalized", {})),
            reconstruction_basis=value.get("reconstruction_basis"),
        )

    @staticmethod
    def _iter_records(root: Path) -> Iterator[Dict[str, Any]]:
        for path in sorted(root.glob("*.ndjson")):
            with path.open("r", encoding="utf-8") as handle:
                for line_number, raw_line in enumerate(handle, start=1):
                    if not raw_line.strip():
                        continue
                    try:
                        yield json.loads(raw_line)
                    except json.JSONDecodeError as exc:
                        raise EventStoreError("invalid JSON in %s:%d" % (path, line_number)) from exc

    def iter_raw(self) -> Iterator[RawCapture]:
        items = [self._raw_from_dict(value) for value in self._iter_records(self.raw_root)]
        for item in sorted(items, key=lambda item: item.capture_seq):
            yield item

    def iter_availability(self) -> Iterator[AvailabilityRecord]:
        items = [self._availability_from_dict(value) for value in self._iter_records(self.availability_root)]
        for item in sorted(items, key=lambda item: (item.available_at, item.derived_at, item.event_id, item.schema_version)):
            yield item

    def _raw_records_with_offset_issues(self) -> Tuple[List[RawCapture], List[str]]:
        """Parse raw records once while checking their recorded text offsets."""
        items: List[RawCapture] = []
        issues: List[str] = []
        for path in sorted(self.raw_root.glob("*.ndjson")):
            with path.open("r", encoding="utf-8") as handle:
                while True:
                    byte_offset = handle.tell()
                    line = handle.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue
                    try:
                        serialized = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise EventStoreError("invalid JSON in %s" % path) from exc
                    try:
                        raw = self._raw_from_dict(serialized)
                    except (KeyError, TypeError, ValueError) as exc:
                        raise EventStoreError("invalid raw record in %s" % path) from exc
                    if raw.raw_offset != byte_offset:
                        issues.append("raw_offset mismatch: %s" % raw.event_id)
                    items.append(raw)
        return sorted(items, key=lambda item: item.capture_seq), issues

    def audit_with_records(self) -> Tuple[bool, List[str], str, List[RawCapture], List[AvailabilityRecord]]:
        """Audit once and return the exact parsed evidence used by that audit.

        Callers that need a deterministic replay digest immediately after the
        audit can reuse these records.  This preserves the full offset,
        payload-hash and segment-manifest checks while avoiding a second parse
        of immutable evidence files.
        """
        issues: List[str] = []
        raws, offset_issues = self._raw_records_with_offset_issues()
        issues.extend(offset_issues)
        availability = list(self.iter_availability())
        event_index: Dict[str, RawCapture] = {}
        previous_seq = 0
        for raw in raws:
            if raw.event_id in event_index:
                issues.append("duplicate event_id: %s" % raw.event_id)
            event_index[raw.event_id] = raw
            if raw.capture_seq != previous_seq + 1:
                issues.append("capture_seq not contiguous at %s" % raw.event_id)
            previous_seq = raw.capture_seq
            if raw.payload_hash != _payload_hash(raw.payload):
                issues.append("payload hash mismatch: %s" % raw.event_id)

        for record in availability:
            raw = event_index.get(record.event_id)
            if raw is None:
                issues.append("availability references missing raw: %s" % record.event_id)
                continue
            if record.available_at < raw.receive_time:
                issues.append("availability precedes receive_time: %s" % record.event_id)
            if record.availability_kind == AvailabilityKind.ACTUAL and record.derived_at < raw.receive_time:
                issues.append("ACTUAL derived_at precedes receive_time: %s" % record.event_id)
            if record.availability_kind == AvailabilityKind.RECONSTRUCTED and not record.reconstruction_basis:
                issues.append("RECONSTRUCTED missing basis: %s" % record.event_id)

        for manifest_path in sorted(self.manifest_root.glob("*.json")):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                segment = self._validate_segment_name(str(manifest["segment"]))
                raw_path = self.raw_root / (segment + ".ndjson")
                if not raw_path.exists():
                    issues.append("sealed segment missing raw file: %s" % segment)
                    continue
                checksum, byte_count, record_count = self._segment_checksum(raw_path)
                if checksum != manifest["sha256"] or byte_count != manifest["byte_count"] or record_count != manifest["record_count"]:
                    issues.append("sealed segment checksum mismatch: %s" % segment)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
                issues.append("invalid raw manifest: %s" % manifest_path.name)

        digest = hashlib.sha256()
        for raw in raws:
            digest.update(_canonical_json(raw.to_dict()).encode("utf-8"))
        for record in availability:
            digest.update(_canonical_json(record.to_dict()).encode("utf-8"))
        return (not issues, issues, digest.hexdigest(), raws, availability)

    def audit(self) -> Tuple[bool, List[str], str]:
        valid, issues, digest, _raws, _availability = self.audit_with_records()
        return valid, issues, digest
