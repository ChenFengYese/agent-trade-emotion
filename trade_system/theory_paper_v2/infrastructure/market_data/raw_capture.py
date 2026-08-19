"""Atomic write-once capture of public response bytes and their summary.

The raw body and capture summary are published as one finite directory bundle.
Parsers receive a reference only after that publication succeeds, so no
semantic result can exist without the exact response bytes that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, Protocol

from ...domain.contracts.canonical import canonical_bytes, loads_json_strict
from ...v32_durable_json import write_once_bytes, write_once_directory


RAW_CAPTURE_SCHEMA_ID = "agent_trade_emotion_market_cycle_raw_capture"
RAW_CAPTURE_SCHEMA_VERSION = "1.0.0"
RAW_ATTEMPT_SCHEMA_ID = "agent_trade_emotion_market_cycle_public_attempt"
RAW_ATTEMPT_SCHEMA_VERSION = "1.0.0"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


class RawCaptureError(ValueError):
    """A public response could not be sealed under the raw-first contract."""


@dataclass(frozen=True, slots=True)
class RawCaptureRef:
    """Content binding returned after an atomic raw capture publication."""

    artifact_type: str
    artifact_id: str
    path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class LoadedRawCapture:
    """One verified immutable response bundle loaded without creating paths."""

    payload: bytes
    summary: Mapping[str, Any]
    raw_ref: Mapping[str, Any]


class RawCaptureSink(Protocol):
    """Minimal sink required by the public transport."""

    def seal_response(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        payload: bytes,
        summary: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class RecoverableRawCaptureSink(RawCaptureSink, Protocol):
    def load_response(
        self, *, cycle_id: str, capture_id: str
    ) -> LoadedRawCapture | None: ...


class RawCaptureReferenceVerifier(Protocol):
    """Verify that a persisted ``ArtifactRef`` still binds one raw bundle."""

    def verify_reference(
        self, *, cycle_id: str, reference: Mapping[str, Any]
    ) -> LoadedRawCapture: ...


class DurableAttemptRawCaptureSink(RecoverableRawCaptureSink, Protocol):
    def claim_attempt(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        binding: Mapping[str, Any],
    ) -> bool: ...


def _safe_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise RawCaptureError(f"RAW_CAPTURE_{field}_INVALID")
    return value


def _relative_ref(cycle_id: str, capture_id: str, name: str) -> str:
    _safe_id(cycle_id, field="CYCLE_ID")
    relative = PurePosixPath("raw", capture_id, name)
    return relative.as_posix()


def _raw_ref(cycle_id: str, capture_id: str, payload: bytes) -> dict[str, Any]:
    return RawCaptureRef(
        artifact_type="RawCapture",
        artifact_id=f"{cycle_id}.{capture_id}.raw",
        path=_relative_ref(cycle_id, capture_id, "body.bin"),
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    ).to_dict()


def _absolute_lexical(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    if len(absolute.parts) > 1:
        first = Path(os.path.sep) / absolute.parts[1]
        try:
            metadata = first.lstat()
        except FileNotFoundError:
            metadata = None
        if metadata is not None and stat.S_ISLNK(metadata.st_mode):
            if metadata.st_uid != 0:
                raise RawCaptureError("RAW_CAPTURE_ROOT_ALIAS_UNSAFE")
            absolute = first.resolve(strict=True).joinpath(*absolute.parts[2:])
    return absolute


def _open_directory(path: Path) -> int:
    absolute = _absolute_lexical(path)
    descriptor = os.open(os.path.sep, _DIRECTORY_FLAGS)
    try:
        for part in absolute.parts[1:]:
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                raise
            except OSError as exc:
                raise RawCaptureError("RAW_CAPTURE_DIRECTORY_UNSAFE") from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_file(directory_fd: int, name: str) -> bytes:
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    except (FileNotFoundError, OSError) as exc:
        raise RawCaptureError("RAW_CAPTURE_BUNDLE_INCOMPLETE_OR_UNSAFE") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RawCaptureError("RAW_CAPTURE_BUNDLE_FILE_UNSAFE")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class FileRawCaptureStore:
    """Publish one immutable response bundle below a caller-owned runtime root."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def claim_attempt(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        binding: Mapping[str, Any],
    ) -> bool:
        """Durably claim one exact public request before any dispatch.

        ``True`` means this call created the claim. ``False`` means an
        identical prior claim already exists and its request outcome is not
        safe to repeat. A different binding fails write-once.
        """

        cycle = _safe_id(cycle_id, field="CYCLE_ID")
        capture = _safe_id(capture_id, field="CAPTURE_ID")
        if not isinstance(binding, Mapping):
            raise RawCaptureError("RAW_ATTEMPT_BINDING_OBJECT_REQUIRED")
        candidate = dict(binding)
        query = candidate.get("query")
        if (
            set(candidate)
            != {
                "component_id",
                "method",
                "path",
                "query",
                "route_policy_id",
                "response_limit_bytes",
                "attempt_number",
                "retry_allowed",
            }
            or not isinstance(candidate.get("component_id"), str)
            or not candidate["component_id"]
            or candidate.get("method") != "GET"
            or not isinstance(candidate.get("path"), str)
            or not candidate["path"].startswith("/")
            or not isinstance(query, Mapping)
            or any(
                not isinstance(key, str)
                or not key
                or not isinstance(value, str)
                or not value
                for key, value in query.items()
            )
            or not isinstance(candidate.get("route_policy_id"), str)
            or not candidate["route_policy_id"]
            or type(candidate.get("response_limit_bytes")) is not int
            or candidate["response_limit_bytes"] <= 0
            or type(candidate.get("attempt_number")) is not int
            or candidate["attempt_number"] != 1
            or candidate.get("retry_allowed") is not False
        ):
            raise RawCaptureError("RAW_ATTEMPT_BINDING_INVALID")
        candidate["query"] = dict(query)
        document = {
            "schema_id": RAW_ATTEMPT_SCHEMA_ID,
            "schema_version": RAW_ATTEMPT_SCHEMA_VERSION,
            "cycle_id": cycle,
            "capture_id": capture,
            "binding": candidate,
        }
        target = (
            self._root
            / "cycles"
            / cycle
            / "raw-attempts"
            / f"{capture}.json"
        )
        try:
            result = write_once_bytes(
                target, canonical_bytes(document) + b"\n"
            )
        except (OSError, TypeError, ValueError) as exc:
            raise RawCaptureError(
                "RAW_ATTEMPT_CLAIM_WRITE_ONCE_FAILED"
            ) from exc
        if result == "CREATED":
            return True
        if result == "EXISTING_IDENTICAL":
            return False
        raise RawCaptureError("RAW_ATTEMPT_CLAIM_RESULT_INVALID")

    def load_response(
        self, *, cycle_id: str, capture_id: str
    ) -> LoadedRawCapture | None:
        """Load and verify one exact bundle without creating any path."""

        cycle = _safe_id(cycle_id, field="CYCLE_ID")
        capture = _safe_id(capture_id, field="CAPTURE_ID")
        target = self._root / "cycles" / cycle / "raw" / capture
        try:
            directory_fd = _open_directory(target)
        except FileNotFoundError:
            return None
        try:
            try:
                names = set(os.listdir(directory_fd))
            except OSError as exc:
                raise RawCaptureError("RAW_CAPTURE_BUNDLE_UNREADABLE") from exc
            if names != {"body.bin", "capture.json"}:
                raise RawCaptureError("RAW_CAPTURE_BUNDLE_FILE_SET_INVALID")
            payload = _read_regular_file(directory_fd, "body.bin")
            summary_raw = _read_regular_file(directory_fd, "capture.json")
        finally:
            os.close(directory_fd)

        try:
            document = loads_json_strict(summary_raw)
        except ValueError as exc:
            raise RawCaptureError("RAW_CAPTURE_SUMMARY_INVALID") from exc
        if not isinstance(document, Mapping):
            raise RawCaptureError("RAW_CAPTURE_SUMMARY_INVALID")
        if canonical_bytes(document) + b"\n" != summary_raw:
            raise RawCaptureError("RAW_CAPTURE_SUMMARY_NONCANONICAL")
        if (
            set(document)
            != {
                "schema_id",
                "schema_version",
                "cycle_id",
                "capture_id",
                "body_file",
                "body_size_bytes",
                "body_sha256",
                "capture",
            }
            or document.get("schema_id") != RAW_CAPTURE_SCHEMA_ID
            or document.get("schema_version") != RAW_CAPTURE_SCHEMA_VERSION
            or document.get("cycle_id") != cycle
            or document.get("capture_id") != capture
            or document.get("body_file") != "body.bin"
            or document.get("body_size_bytes") != len(payload)
            or document.get("body_sha256")
            != hashlib.sha256(payload).hexdigest()
            or not isinstance(document.get("capture"), Mapping)
        ):
            raise RawCaptureError("RAW_CAPTURE_BUNDLE_BINDING_INVALID")
        return LoadedRawCapture(
            payload=payload,
            summary=dict(document["capture"]),
            raw_ref=_raw_ref(cycle, capture, payload),
        )

    def verify_reference(
        self, *, cycle_id: str, reference: Mapping[str, Any]
    ) -> LoadedRawCapture:
        """Load one bundle and verify every persisted reference field.

        The capture id is derived from the canonical cycle-relative body path;
        both the artifact id and the bundle summary must independently bind it
        to ``cycle_id``.  This keeps repository recovery on the same parser and
        file-safety boundary as transport replay.
        """

        cycle = _safe_id(cycle_id, field="CYCLE_ID")
        if not isinstance(reference, Mapping):
            raise RawCaptureError("RAW_CAPTURE_REFERENCE_INVALID")
        candidate = dict(reference)
        if set(candidate) != {
            "artifact_type",
            "artifact_id",
            "path",
            "size_bytes",
            "sha256",
        }:
            raise RawCaptureError("RAW_CAPTURE_REFERENCE_INVALID")
        path = candidate.get("path")
        if not isinstance(path, str):
            raise RawCaptureError("RAW_CAPTURE_REFERENCE_INVALID")
        parts = PurePosixPath(path).parts
        if (
            len(parts) != 3
            or parts[0] != "raw"
            or parts[2] != "body.bin"
        ):
            raise RawCaptureError("RAW_CAPTURE_REFERENCE_INVALID")
        capture = _safe_id(parts[1], field="CAPTURE_ID")
        if (
            candidate.get("artifact_type") != "RawCapture"
            or candidate.get("artifact_id") != f"{cycle}.{capture}.raw"
            or candidate.get("path") != _relative_ref(cycle, capture, "body.bin")
        ):
            raise RawCaptureError("RAW_CAPTURE_REFERENCE_BINDING_INVALID")

        loaded = self.load_response(cycle_id=cycle, capture_id=capture)
        if loaded is None:
            raise RawCaptureError("RAW_CAPTURE_REFERENCE_MISSING")
        if dict(loaded.raw_ref) != candidate:
            raise RawCaptureError("RAW_CAPTURE_REFERENCE_CONTENT_MISMATCH")
        return loaded

    def seal_response(
        self,
        *,
        cycle_id: str,
        capture_id: str,
        payload: bytes,
        summary: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        cycle = _safe_id(cycle_id, field="CYCLE_ID")
        capture = _safe_id(capture_id, field="CAPTURE_ID")
        if not isinstance(payload, bytes):
            raise RawCaptureError("RAW_CAPTURE_PAYLOAD_BYTES_REQUIRED")
        if not isinstance(summary, Mapping):
            raise RawCaptureError("RAW_CAPTURE_SUMMARY_OBJECT_REQUIRED")

        body_sha256 = hashlib.sha256(payload).hexdigest()
        document = {
            "schema_id": RAW_CAPTURE_SCHEMA_ID,
            "schema_version": RAW_CAPTURE_SCHEMA_VERSION,
            "cycle_id": cycle,
            "capture_id": capture,
            "body_file": "body.bin",
            "body_size_bytes": len(payload),
            "body_sha256": body_sha256,
            "capture": dict(summary),
        }
        summary_bytes = canonical_bytes(document) + b"\n"
        target = self._root / "cycles" / cycle / "raw" / capture

        # One atomic directory publication prevents a visible body without its
        # summary (or a visible summary without its exact body).
        try:
            write_once_directory(
                target,
                {"body.bin": payload, "capture.json": summary_bytes},
            )
        except (OSError, TypeError, ValueError) as exc:
            raise RawCaptureError("RAW_CAPTURE_WRITE_ONCE_FAILED") from exc

        return _raw_ref(cycle, capture, payload)


__all__ = [
    "DurableAttemptRawCaptureSink",
    "FileRawCaptureStore",
    "LoadedRawCapture",
    "RAW_CAPTURE_SCHEMA_ID",
    "RAW_CAPTURE_SCHEMA_VERSION",
    "RAW_ATTEMPT_SCHEMA_ID",
    "RAW_ATTEMPT_SCHEMA_VERSION",
    "RawCaptureError",
    "RawCaptureRef",
    "RawCaptureReferenceVerifier",
    "RawCaptureSink",
    "RecoverableRawCaptureSink",
]
