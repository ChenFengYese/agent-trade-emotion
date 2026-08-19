"""Append-only, replayable paper ledger for isolated V3.3.2 subaccounts."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import secrets
import stat
import threading
from typing import Any, Iterator, Mapping, Sequence

from ...domain.contracts.canonical import canonical_bytes, loads_json_strict
from ...domain.market_cycle.paper import PaperContractError, PaperLedgerRecordV1


class PaperLedgerError(RuntimeError):
    """The durable paper ledger could not satisfy an append/replay invariant."""


_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _safe_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise PaperLedgerError(f"PAPER_LEDGER_{field.upper()}_UNSAFE")
    return value


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise PaperLedgerError(f"PAPER_LEDGER_DIRECTORY_UNSAFE:{path}")


def _atomic_replace(path: Path, payload: bytes) -> None:
    _ensure_directory(path.parent)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(8)}.tmp"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class FilePaperLedger:
    """One append-only event chain per paper subaccount.

    The event file is the fact owner. ``head.json`` is a replaceable projection
    and is rebuilt after every append; replay never trusts it over the chain.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        _ensure_directory(self.root)

    def _account_root(self, account_id: str) -> Path:
        return self.root / "accounts" / _safe_id(account_id, field="account_id")

    def _events_path(self, account_id: str) -> Path:
        return self._account_root(account_id) / "events.jsonl"

    def _head_path(self, account_id: str) -> Path:
        return self._account_root(account_id) / "head.json"

    @contextmanager
    def _locked(self, account_id: str) -> Iterator[None]:
        account_root = self._account_root(account_id)
        _ensure_directory(account_root)
        lock_path = account_root / ".append.lock"
        key = str(lock_path.resolve(strict=False))
        with _LOCKS_GUARD:
            process_lock = _LOCKS.setdefault(key, threading.RLock())
        with process_lock:
            descriptor = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def load_records(self, account_id: str) -> tuple[PaperLedgerRecordV1, ...]:
        events_path = self._events_path(account_id)
        try:
            metadata = events_path.lstat()
        except FileNotFoundError:
            return ()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise PaperLedgerError("PAPER_LEDGER_EVENTS_UNSAFE")
        raw = events_path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise PaperLedgerError("PAPER_LEDGER_PARTIAL_TRAILING_RECORD")
        records: list[PaperLedgerRecordV1] = []
        previous_sha: str | None = None
        seen_event_ids: set[str] = set()
        for index, line in enumerate(raw.splitlines(), start=1):
            try:
                value = loads_json_strict(line)
                if canonical_bytes(value) != line:
                    raise PaperLedgerError("PAPER_LEDGER_RECORD_NONCANONICAL")
                record = PaperLedgerRecordV1.from_dict(value)
            except (PaperContractError, ValueError) as exc:
                raise PaperLedgerError(f"PAPER_LEDGER_RECORD_INVALID:{index}") from exc
            if record.account_id != account_id:
                raise PaperLedgerError("PAPER_LEDGER_ACCOUNT_CROSSOVER")
            if record.revision != index or record.previous_record_sha256 != previous_sha:
                raise PaperLedgerError("PAPER_LEDGER_CHAIN_BROKEN")
            if record.event_id in seen_event_ids:
                raise PaperLedgerError("PAPER_LEDGER_EVENT_ID_DUPLICATE")
            seen_event_ids.add(record.event_id)
            records.append(record)
            previous_sha = record.record_sha256
        return tuple(records)

    def append(
        self,
        *,
        account_id: str,
        expected_revision: int,
        event_id: str,
        event_type: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> PaperLedgerRecordV1:
        return self.append_many(
            account_id=account_id,
            expected_revision=expected_revision,
            events=(
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "occurred_at": occurred_at,
                    "payload": payload,
                },
            ),
        )[0]

    def append_many(
        self,
        *,
        account_id: str,
        expected_revision: int,
        events: Sequence[Mapping[str, Any]],
    ) -> tuple[PaperLedgerRecordV1, ...]:
        if type(expected_revision) is not int or expected_revision < 0:
            raise PaperLedgerError("PAPER_LEDGER_EXPECTED_REVISION_INVALID")
        if not events:
            raise PaperLedgerError("PAPER_LEDGER_EMPTY_APPEND")
        account_id = _safe_id(account_id, field="account_id")
        with self._locked(account_id):
            records = self.load_records(account_id)
            supplied_ids = tuple(
                _safe_id(event.get("event_id"), field="event_id") for event in events
            )
            if len(supplied_ids) != len(set(supplied_ids)):
                raise PaperLedgerError("PAPER_LEDGER_BATCH_EVENT_ID_DUPLICATE")
            existing_by_id = {record.event_id: record for record in records}
            existing_batch: list[PaperLedgerRecordV1] = []
            for offset, event in enumerate(events, start=1):
                event_id = supplied_ids[offset - 1]
                existing_record = existing_by_id.get(event_id)
                if existing_record is None:
                    if existing_batch:
                        raise PaperLedgerError("PAPER_LEDGER_PARTIAL_IDEMPOTENT_BATCH")
                    continue
                candidate = PaperLedgerRecordV1.create(
                    account_id=account_id,
                    revision=expected_revision + offset,
                    previous_record_sha256=(
                        records[expected_revision + offset - 2].record_sha256
                        if expected_revision + offset > 1
                        and expected_revision + offset - 2 < len(records)
                        else None
                    ),
                    event_id=event_id,
                    event_type=event.get("event_type"),
                    occurred_at=event.get("occurred_at"),
                    payload=event.get("payload"),
                )
                if candidate.record_sha256 != existing_record.record_sha256:
                    raise PaperLedgerError("PAPER_LEDGER_EVENT_ID_CONFLICT")
                existing_batch.append(existing_record)
            if len(existing_batch) == len(events):
                return tuple(existing_batch)
            if len(records) != expected_revision:
                raise PaperLedgerError("PAPER_LEDGER_VERSION_CONFLICT")
            previous_sha = records[-1].record_sha256 if records else None
            appended: list[PaperLedgerRecordV1] = []
            for offset, event in enumerate(events, start=1):
                record = PaperLedgerRecordV1.create(
                    account_id=account_id,
                    revision=expected_revision + offset,
                    previous_record_sha256=previous_sha,
                    event_id=supplied_ids[offset - 1],
                    event_type=event.get("event_type"),
                    occurred_at=event.get("occurred_at"),
                    payload=event.get("payload"),
                )
                appended.append(record)
                previous_sha = record.record_sha256
            events_path = self._events_path(account_id)
            existing = b"".join(
                canonical_bytes(item.to_dict()) + b"\n" for item in records
            )
            _atomic_replace(
                events_path,
                existing
                + b"".join(canonical_bytes(record.to_dict()) + b"\n" for record in appended),
            )
            record = appended[-1]
            _atomic_replace(
                self._head_path(account_id),
                canonical_bytes(
                    {
                        "account_id": account_id,
                        "revision": record.revision,
                        "record_sha256": record.record_sha256,
                    }
                ),
            )
            return tuple(appended)

    def current_revision(self, account_id: str) -> int:
        return len(self.load_records(account_id))

    def event_by_id(self, account_id: str, event_id: str) -> PaperLedgerRecordV1 | None:
        event_id = _safe_id(event_id, field="event_id")
        return next(
            (record for record in self.load_records(account_id) if record.event_id == event_id),
            None,
        )
