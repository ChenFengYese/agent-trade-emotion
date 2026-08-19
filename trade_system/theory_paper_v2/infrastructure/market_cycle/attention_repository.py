"""Generic append-only durability for V3.3.2 attention lifecycle events.

This adapter deliberately has only four responsibilities: append, load the
stream head, compare-and-swap append, and replay/verify the immutable journal.
It does not know which requests are admissible or choose any market action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Any, Mapping

from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from ...v32_durable_json import (
    atomic_replace_json,
    exclusive_lock_file,
    write_once_json,
)


_EVENT_SCHEMA_ID = "agent-trade-emotion.v332-attention-event"
_EVENT_SCHEMA_VERSION = "1.0.0"
_HEAD_SCHEMA_ID = "agent-trade-emotion.v332-attention-head"
_HEAD_SCHEMA_VERSION = "1.0.0"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVENT_FILE_RE = re.compile(r"^[0-9]{8}\.json$")
_MAX_DOCUMENT_BYTES = 8 * 1024 * 1024


class AttentionRepositoryError(RuntimeError):
    """The durable attention journal is missing, corrupt, or conflicting."""


class AttentionRepositoryCASConflict(AttentionRepositoryError):
    """A caller attempted to append from a stale stream revision."""


def _safe_id(value: object, *, code: str) -> str:
    if type(value) is not str or _SAFE_ID_RE.fullmatch(value) is None:
        raise AttentionRepositoryError(code)
    return value


def _timestamp(value: object) -> str:
    if type(value) is not str or not value or len(value) > 64:
        raise AttentionRepositoryError("ATTENTION_EVENT_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AttentionRepositoryError("ATTENTION_EVENT_TIME_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AttentionRepositoryError("ATTENTION_EVENT_TIME_INVALID")
    return value


def _canonical_mapping(value: object, *, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AttentionRepositoryError(code)
    try:
        return loads_json_strict(canonical_bytes(dict(value)))
    except CanonicalContractError as exc:
        raise AttentionRepositoryError(code) from exc


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], *, code: str) -> None:
    if frozenset(value) != expected:
        raise AttentionRepositoryError(code)


def _read_document(path: Path, *, missing_code: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise AttentionRepositoryError(missing_code) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > _MAX_DOCUMENT_BYTES
    ):
        raise AttentionRepositoryError("ATTENTION_REPOSITORY_FILE_UNSAFE")
    try:
        raw = path.read_bytes()
        document = loads_json_strict(raw)
        if canonical_bytes(document) + b"\n" != raw:
            raise AttentionRepositoryError("ATTENTION_REPOSITORY_JSON_NONCANONICAL")
        return document
    except (OSError, CanonicalContractError) as exc:
        raise AttentionRepositoryError("ATTENTION_REPOSITORY_JSON_INVALID") from exc


@dataclass(frozen=True, slots=True)
class DurableAttentionEvent:
    logical_agent_id: str
    revision: int
    prior_event_sha256: str | None
    event_id: str
    event_type: str
    occurred_at: str
    payload: Mapping[str, Any]
    event_sha256: str

    def __post_init__(self) -> None:
        _safe_id(self.logical_agent_id, code="ATTENTION_STREAM_ID_INVALID")
        if type(self.revision) is not int or self.revision < 1:
            raise AttentionRepositoryError("ATTENTION_EVENT_REVISION_INVALID")
        if self.revision == 1:
            if self.prior_event_sha256 is not None:
                raise AttentionRepositoryError("ATTENTION_EVENT_PRIOR_HASH_INVALID")
        elif type(self.prior_event_sha256) is not str or _SHA256_RE.fullmatch(
            self.prior_event_sha256
        ) is None:
            raise AttentionRepositoryError("ATTENTION_EVENT_PRIOR_HASH_INVALID")
        _safe_id(self.event_id, code="ATTENTION_EVENT_ID_INVALID")
        _safe_id(self.event_type, code="ATTENTION_EVENT_TYPE_INVALID")
        _timestamp(self.occurred_at)
        payload = _canonical_mapping(
            self.payload, code="ATTENTION_EVENT_PAYLOAD_INVALID"
        )
        if type(self.event_sha256) is not str or _SHA256_RE.fullmatch(
            self.event_sha256
        ) is None:
            raise AttentionRepositoryError("ATTENTION_EVENT_SHA256_INVALID")
        if canonical_digest(self.body_dict(payload=payload)) != self.event_sha256:
            raise AttentionRepositoryError("ATTENTION_EVENT_SHA256_MISMATCH")
        object.__setattr__(self, "payload", _freeze(payload))

    def body_dict(self, *, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {
            "schema_id": _EVENT_SCHEMA_ID,
            "schema_version": _EVENT_SCHEMA_VERSION,
            "logical_agent_id": self.logical_agent_id,
            "revision": self.revision,
            "prior_event_sha256": self.prior_event_sha256,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "payload": _plain(self.payload if payload is None else payload),
        }

    def to_dict(self) -> dict[str, Any]:
        value = self.body_dict()
        value["event_sha256"] = self.event_sha256
        return value

    @classmethod
    def create(
        cls,
        *,
        logical_agent_id: str,
        revision: int,
        prior_event_sha256: str | None,
        event_id: str,
        event_type: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> "DurableAttentionEvent":
        canonical_payload = _canonical_mapping(
            payload, code="ATTENTION_EVENT_PAYLOAD_INVALID"
        )
        body = {
            "schema_id": _EVENT_SCHEMA_ID,
            "schema_version": _EVENT_SCHEMA_VERSION,
            "logical_agent_id": logical_agent_id,
            "revision": revision,
            "prior_event_sha256": prior_event_sha256,
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "payload": canonical_payload,
        }
        return cls(
            logical_agent_id=logical_agent_id,
            revision=revision,
            prior_event_sha256=prior_event_sha256,
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            payload=canonical_payload,
            event_sha256=canonical_digest(body),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DurableAttentionEvent":
        expected = frozenset(
            {
                "schema_id",
                "schema_version",
                "logical_agent_id",
                "revision",
                "prior_event_sha256",
                "event_id",
                "event_type",
                "occurred_at",
                "payload",
                "event_sha256",
            }
        )
        _exact_keys(value, expected, code="ATTENTION_EVENT_FIELDS_INVALID")
        if (
            value["schema_id"] != _EVENT_SCHEMA_ID
            or value["schema_version"] != _EVENT_SCHEMA_VERSION
        ):
            raise AttentionRepositoryError("ATTENTION_EVENT_SCHEMA_INVALID")
        return cls(
            logical_agent_id=value["logical_agent_id"],
            revision=value["revision"],
            prior_event_sha256=value["prior_event_sha256"],
            event_id=value["event_id"],
            event_type=value["event_type"],
            occurred_at=value["occurred_at"],
            payload=value["payload"],
            event_sha256=value["event_sha256"],
        )


@dataclass(frozen=True, slots=True)
class AttentionStreamHead:
    logical_agent_id: str
    revision: int
    event_sha256: str | None

    def __post_init__(self) -> None:
        _safe_id(self.logical_agent_id, code="ATTENTION_STREAM_ID_INVALID")
        if type(self.revision) is not int or self.revision < 0:
            raise AttentionRepositoryError("ATTENTION_HEAD_REVISION_INVALID")
        if self.revision == 0:
            if self.event_sha256 is not None:
                raise AttentionRepositoryError("ATTENTION_HEAD_SHA256_INVALID")
        elif type(self.event_sha256) is not str or _SHA256_RE.fullmatch(
            self.event_sha256
        ) is None:
            raise AttentionRepositoryError("ATTENTION_HEAD_SHA256_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": _HEAD_SCHEMA_ID,
            "schema_version": _HEAD_SCHEMA_VERSION,
            "logical_agent_id": self.logical_agent_id,
            "revision": self.revision,
            "event_sha256": self.event_sha256,
        }


class FileAttentionRepository:
    """Append-only, hash-chained attention journal split by logical Agent."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).absolute()

    def _stream_root(self, logical_agent_id: str) -> Path:
        safe = _safe_id(logical_agent_id, code="ATTENTION_STREAM_ID_INVALID")
        return self.root / "streams" / safe

    def _lock_path(self, logical_agent_id: str) -> Path:
        safe = _safe_id(logical_agent_id, code="ATTENTION_STREAM_ID_INVALID")
        return self.root / ".locks" / f"{safe}.lock"

    def _head_path(self, logical_agent_id: str) -> Path:
        return self._stream_root(logical_agent_id) / "head.json"

    def _event_path(self, logical_agent_id: str, revision: int) -> Path:
        return self._stream_root(logical_agent_id) / "events" / f"{revision:08d}.json"

    def _read_head_document(self, logical_agent_id: str) -> AttentionStreamHead | None:
        path = self._head_path(logical_agent_id)
        try:
            path.lstat()
        except FileNotFoundError:
            return None
        value = _read_document(path, missing_code="ATTENTION_HEAD_MISSING")
        expected = frozenset(
            {
                "schema_id",
                "schema_version",
                "logical_agent_id",
                "revision",
                "event_sha256",
            }
        )
        _exact_keys(value, expected, code="ATTENTION_HEAD_FIELDS_INVALID")
        if (
            value["schema_id"] != _HEAD_SCHEMA_ID
            or value["schema_version"] != _HEAD_SCHEMA_VERSION
            or value["logical_agent_id"] != logical_agent_id
        ):
            raise AttentionRepositoryError("ATTENTION_HEAD_IDENTITY_INVALID")
        return AttentionStreamHead(
            logical_agent_id=value["logical_agent_id"],
            revision=value["revision"],
            event_sha256=value["event_sha256"],
        )

    def _replay_locked(self, logical_agent_id: str) -> tuple[DurableAttentionEvent, ...]:
        events_directory = self._stream_root(logical_agent_id) / "events"
        try:
            metadata = events_directory.lstat()
        except FileNotFoundError:
            paths: list[Path] = []
        else:
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise AttentionRepositoryError("ATTENTION_EVENTS_DIRECTORY_UNSAFE")
            paths = sorted(events_directory.iterdir())
            if any(
                path.is_symlink()
                or not path.is_file()
                or _EVENT_FILE_RE.fullmatch(path.name) is None
                for path in paths
            ):
                raise AttentionRepositoryError("ATTENTION_EVENT_FILE_UNSAFE")

        events: list[DurableAttentionEvent] = []
        prior: str | None = None
        event_ids: set[str] = set()
        for revision, path in enumerate(paths, start=1):
            if path.name != f"{revision:08d}.json":
                raise AttentionRepositoryError("ATTENTION_EVENT_SEQUENCE_GAP")
            event = DurableAttentionEvent.from_dict(
                _read_document(path, missing_code="ATTENTION_EVENT_MISSING")
            )
            if (
                event.logical_agent_id != logical_agent_id
                or event.revision != revision
                or event.prior_event_sha256 != prior
            ):
                raise AttentionRepositoryError("ATTENTION_EVENT_CHAIN_INVALID")
            if event.event_id in event_ids:
                raise AttentionRepositoryError("ATTENTION_EVENT_ID_DUPLICATE")
            event_ids.add(event.event_id)
            events.append(event)
            prior = event.event_sha256

        durable_head = self._read_head_document(logical_agent_id)
        if durable_head is not None:
            if durable_head.revision > len(events):
                raise AttentionRepositoryError("ATTENTION_HEAD_AHEAD_OF_JOURNAL")
            if durable_head.revision:
                expected_sha = events[durable_head.revision - 1].event_sha256
                if durable_head.event_sha256 != expected_sha:
                    raise AttentionRepositoryError("ATTENTION_HEAD_CHAIN_MISMATCH")
        return tuple(events)

    def _publish_head(self, event: DurableAttentionEvent) -> None:
        atomic_replace_json(
            self._head_path(event.logical_agent_id),
            AttentionStreamHead(
                logical_agent_id=event.logical_agent_id,
                revision=event.revision,
                event_sha256=event.event_sha256,
            ).to_dict(),
        )

    def _append(
        self,
        logical_agent_id: str,
        *,
        expected_revision: int | None,
        event_id: str,
        event_type: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> DurableAttentionEvent:
        safe = _safe_id(logical_agent_id, code="ATTENTION_STREAM_ID_INVALID")
        _safe_id(event_id, code="ATTENTION_EVENT_ID_INVALID")
        _safe_id(event_type, code="ATTENTION_EVENT_TYPE_INVALID")
        _timestamp(occurred_at)
        canonical_payload = _canonical_mapping(
            payload, code="ATTENTION_EVENT_PAYLOAD_INVALID"
        )
        if expected_revision is not None and (
            type(expected_revision) is not int or expected_revision < 0
        ):
            raise AttentionRepositoryError("ATTENTION_EXPECTED_REVISION_INVALID")

        with exclusive_lock_file(self._lock_path(safe)):
            events = self._replay_locked(safe)
            for event in events:
                if event.event_id != event_id:
                    continue
                if (
                    event.event_type != event_type
                    or event.occurred_at != occurred_at
                    or _plain(event.payload) != canonical_payload
                ):
                    raise AttentionRepositoryError("ATTENTION_EVENT_ID_CONFLICT")
                # Repair a head publication interrupted after the immutable
                # event reached disk, then return the exactly-once winner.
                self._publish_head(events[-1])
                return event

            current_revision = len(events)
            if expected_revision is not None and expected_revision != current_revision:
                raise AttentionRepositoryCASConflict(
                    f"ATTENTION_CAS_CONFLICT:{expected_revision}:{current_revision}"
                )
            event = DurableAttentionEvent.create(
                logical_agent_id=safe,
                revision=current_revision + 1,
                prior_event_sha256=(events[-1].event_sha256 if events else None),
                event_id=event_id,
                event_type=event_type,
                occurred_at=occurred_at,
                payload=canonical_payload,
            )
            try:
                write_once_json(self._event_path(safe, event.revision), event.to_dict())
                self._publish_head(event)
            except CanonicalContractError as exc:
                raise AttentionRepositoryError("ATTENTION_EVENT_WRITE_FAILED") from exc
            return event

    def append(
        self,
        logical_agent_id: str,
        *,
        event_id: str,
        event_type: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> DurableAttentionEvent:
        """Append from the current head after serializing concurrent writers."""

        return self._append(
            logical_agent_id,
            expected_revision=None,
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            payload=payload,
        )

    def load(self, logical_agent_id: str) -> AttentionStreamHead:
        """Load the verified effective head; revision zero means no stream yet."""

        safe = _safe_id(logical_agent_id, code="ATTENTION_STREAM_ID_INVALID")
        with exclusive_lock_file(self._lock_path(safe)):
            events = self._replay_locked(safe)
            if not events:
                return AttentionStreamHead(safe, 0, None)
            return AttentionStreamHead(safe, len(events), events[-1].event_sha256)

    def compare_and_swap(
        self,
        logical_agent_id: str,
        *,
        expected_revision: int,
        event_id: str,
        event_type: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> DurableAttentionEvent:
        """Atomically append only when the supplied revision is still current."""

        return self._append(
            logical_agent_id,
            expected_revision=expected_revision,
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            payload=payload,
        )

    def replay(self, logical_agent_id: str) -> tuple[DurableAttentionEvent, ...]:
        """Verify and return the immutable journal without projecting policy."""

        safe = _safe_id(logical_agent_id, code="ATTENTION_STREAM_ID_INVALID")
        with exclusive_lock_file(self._lock_path(safe)):
            return self._replay_locked(safe)


__all__ = [
    "AttentionRepositoryCASConflict",
    "AttentionRepositoryError",
    "AttentionStreamHead",
    "DurableAttentionEvent",
    "FileAttentionRepository",
]
