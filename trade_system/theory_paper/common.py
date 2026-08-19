"""Canonical files, timestamps, locking, and append-only receipts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


class TheoryPaperError(ValueError):
    """A fail-closed paper-experiment validation error."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    current = value or utc_now()
    if current.tzinfo is None:
        raise TheoryPaperError("timestamp must be timezone aware")
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TheoryPaperError("timestamp must be canonical UTC with Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TheoryPaperError("timestamp is invalid") from exc
    return parsed.astimezone(timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TheoryPaperError("value is not canonical JSON") from exc


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TheoryPaperError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise TheoryPaperError(f"JSON root must be an object: {path}")
    return value


def write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(dict(value)) + b"\n"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise TheoryPaperError(f"write-once artifact already exists: {target}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def write_atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(dict(value)) + b"\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".partial",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def experiment_lock(root: Path) -> Iterator[None]:
    lock_path = Path(root) / ".experiment.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(lock_path.parent, 0o700)
    with lock_path.open("a+b") as handle:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise TheoryPaperError("another experiment process holds the lock") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ledger_tip(path: Path) -> tuple[int, str]:
    if not path.exists():
        return 0, "0" * 64
    count = 0
    tip = "0" * 64
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TheoryPaperError("ledger contains invalid JSON") from exc
            if not isinstance(event, dict):
                raise TheoryPaperError("ledger event must be an object")
            count += 1
            if event.get("sequence") != count or event.get("previous_digest") != tip:
                raise TheoryPaperError("ledger sequence or prior digest is invalid")
            supplied = event.get("event_digest")
            candidate = dict(event)
            candidate.pop("event_digest", None)
            if supplied != digest_json(candidate):
                raise TheoryPaperError("ledger digest chain is invalid")
            tip = supplied
    return count, tip


def append_ledger_event(
    root: Path,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    observed_at: str | None = None,
) -> dict[str, Any]:
    if not event_type or not isinstance(event_type, str):
        raise TheoryPaperError("event_type is required")
    ledger = Path(root) / "ledger.ndjson"
    sequence, previous = _ledger_tip(ledger)
    event: dict[str, Any] = {
        "sequence": sequence + 1,
        "event_type": event_type,
        "observed_at": observed_at or iso_utc(),
        "payload": dict(payload),
        "previous_digest": previous,
    }
    event["event_digest"] = digest_json(event)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(ledger, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.chmod(ledger, 0o600)
    with os.fdopen(descriptor, "ab") as handle:
        handle.write(canonical_bytes(event) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def verify_ledger(root: Path) -> dict[str, Any]:
    count, tip = _ledger_tip(Path(root) / "ledger.ndjson")
    return {"valid": True, "event_count": count, "tip_digest": tip}
