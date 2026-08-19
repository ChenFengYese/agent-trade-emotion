"""Atomic raw-first store dedicated to the future V3.3.2 interface."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping
import urllib.parse
import uuid

from ..application.ports import HttpRequest, TransportRequest, TransportResponse
from ..domain.contracts import SCHEMA_VERSION, SourceDefinition


_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,180}\Z")
_MAX_MANUAL_BYTES = 64 * 1024 * 1024


class RawStoreError(ValueError):
    pass


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _moment(value: str, *, code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise RawStoreError(code) from exc
    if parsed.tzinfo is None:
        raise RawStoreError(code)
    return parsed.astimezone(UTC)


def _write_new(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _request_summary(request: TransportRequest) -> dict[str, Any]:
    if isinstance(request, HttpRequest):
        return {
            "transport": "HTTP",
            "method": request.method,
            "url": request.stored_url,
            "headers": dict(sorted(request.stored_headers.items())),
            "request_body_sha256": (
                None if request.body is None else hashlib.sha256(request.body).hexdigest()
            ),
            "request_body_size_bytes": 0 if request.body is None else len(request.body),
            "response_limit_bytes": request.max_bytes,
            "retry_allowed": False,
        }
    return {
        "transport": "WEBSOCKET",
        "url": request.stored_url,
        "initial_message_sha256": [
            hashlib.sha256(message).hexdigest() for message in request.initial_messages
        ],
        "duration_seconds": request.duration_seconds,
        "max_messages": request.max_messages,
        "response_limit_bytes": request.max_bytes,
        "retry_allowed": False,
    }


class FileRawStore:
    """Write finite immutable capture windows outside the active V3.3.1 store."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)

    @property
    def _captures(self) -> Path:
        return self.root / "captures"

    def _capture_id(self, source_id: str, captured_at: str) -> str:
        if _SAFE_ID.fullmatch(source_id) is None:
            raise RawStoreError("V332_CAPTURE_SOURCE_ID_INVALID")
        moment = _moment(captured_at, code="V332_CAPTURE_TIME_INVALID")
        stamp = moment.strftime("%Y%m%dT%H%M%S%fZ")
        return f"{source_id}-{stamp}-{uuid.uuid4().hex[:8]}"

    def _publish(
        self,
        *,
        capture_id: str,
        body: bytes,
        summary: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if _SAFE_ID.fullmatch(capture_id) is None:
            raise RawStoreError("V332_CAPTURE_ID_INVALID")
        self._captures.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{capture_id}.", dir=self._captures)
        )
        target = self._captures / capture_id
        try:
            _write_new(temporary / "body.bin", body)
            _write_new(temporary / "capture.json", _canonical_bytes(dict(summary)))
            os.replace(temporary, target)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        digest = hashlib.sha256(body).hexdigest()
        return {
            "artifact_type": "V332ExternalRawCapture",
            "capture_id": capture_id,
            "capture_dir": str(target),
            "body_path": str(target / "body.bin"),
            "capture_path": str(target / "capture.json"),
            "size_bytes": len(body),
            "sha256": digest,
            "payload_present": bool(body),
        }

    def seal_transport(
        self,
        *,
        definition: SourceDefinition,
        request: TransportRequest,
        response: TransportResponse,
    ) -> Mapping[str, Any]:
        capture_id = self._capture_id(
            definition.source_id, response.capture_completed_at
        )
        body_digest = hashlib.sha256(response.body).hexdigest()
        summary = {
            "schema_id": "agent_trade_emotion_v332_external_raw_capture",
            "schema_version": SCHEMA_VERSION,
            "capture_id": capture_id,
            "source": definition.to_dict(),
            "request": _request_summary(request),
            "response": {
                "protocol": response.protocol,
                "status_code": response.status_code,
                "final_url": response.stored_url,
                "headers": dict(sorted(response.headers.items())),
                "request_started_at": response.request_started_at,
                "response_received_at": response.response_received_at,
                "capture_completed_at": response.capture_completed_at,
                "error_code": response.error_code,
                "transport_backend": response.backend,
                "body_sha256": body_digest,
                "body_size_bytes": len(response.body),
                "body_present": bool(response.body),
            },
        }
        return self._publish(capture_id=capture_id, body=response.body, summary=summary)

    def _checked_body_path(self, reference: Mapping[str, Any]) -> Path:
        body_path = reference.get("body_path")
        digest = reference.get("sha256")
        size = reference.get("size_bytes")
        if (
            not isinstance(body_path, str)
            or not isinstance(digest, str)
            or type(size) is not int
        ):
            raise RawStoreError("V332_RAW_REFERENCE_INVALID")
        path = Path(body_path).resolve(strict=True)
        captures = self._captures.resolve(strict=True)
        if path.parent.parent != captures or path.name != "body.bin":
            raise RawStoreError("V332_RAW_REFERENCE_OUTSIDE_STORE")
        return path

    def load_raw(self, reference: Mapping[str, Any]) -> bytes:
        path = self._checked_body_path(reference)
        payload = path.read_bytes()
        if len(payload) != reference["size_bytes"]:
            raise RawStoreError("V332_RAW_SIZE_MISMATCH")
        if hashlib.sha256(payload).hexdigest() != reference["sha256"]:
            raise RawStoreError("V332_RAW_SHA256_MISMATCH")
        return payload

    def seal_observation(
        self,
        *,
        reference: Mapping[str, Any],
        observation: Mapping[str, Any],
    ) -> str:
        body_path = self._checked_body_path(reference)
        target = body_path.parent / "observation.json"
        document = {
            "schema_id": "agent_trade_emotion_v332_external_observation",
            "schema_version": SCHEMA_VERSION,
            "capture_id": reference["capture_id"],
            "raw_sha256": reference["sha256"],
            **dict(observation),
        }
        _write_new(target, _canonical_bytes(document))
        return str(target)

    def import_manual_file(
        self,
        *,
        definition: SourceDefinition,
        source_file: Path,
        observed_at: str,
        available_at: str,
        captured_at: str,
        source_url: str | None,
    ) -> tuple[Mapping[str, Any], bytes]:
        observed = _moment(observed_at, code="V332_MANUAL_OBSERVED_AT_INVALID")
        available = _moment(available_at, code="V332_MANUAL_AVAILABLE_AT_INVALID")
        captured = _moment(captured_at, code="V332_MANUAL_CAPTURED_AT_INVALID")
        if available > captured:
            raise RawStoreError("V332_MANUAL_FUTURE_AVAILABILITY")
        path = Path(source_file).expanduser().resolve(strict=True)
        if not path.is_file() or path.is_symlink():
            raise RawStoreError("V332_MANUAL_FILE_INVALID")
        size = path.stat().st_size
        if size <= 0 or size > _MAX_MANUAL_BYTES:
            raise RawStoreError("V332_MANUAL_FILE_SIZE_INVALID")
        origin = source_url or definition.endpoint
        parsed = urllib.parse.urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise RawStoreError("V332_MANUAL_SOURCE_URL_INVALID")
        payload = path.read_bytes()
        capture_id = self._capture_id(definition.source_id, captured_at)
        summary = {
            "schema_id": "agent_trade_emotion_v332_external_raw_capture",
            "schema_version": SCHEMA_VERSION,
            "capture_id": capture_id,
            "source": definition.to_dict(),
            "request": {
                "transport": "MANUAL_FILE",
                "source_filename": path.name,
                "retry_allowed": False,
            },
            "response": {
                "protocol": "MANUAL_FILE",
                "status_code": None,
                "final_url": origin,
                "headers": {},
                "request_started_at": captured_at,
                "response_received_at": captured_at,
                "capture_completed_at": captured_at,
                "error_code": None,
                "transport_backend": "manual-file",
                "body_sha256": hashlib.sha256(payload).hexdigest(),
                "body_size_bytes": len(payload),
                "body_present": True,
                "observed_at": observed.isoformat().replace("+00:00", "Z"),
                "available_at": available.isoformat().replace("+00:00", "Z"),
            },
        }
        reference = self._publish(
            capture_id=capture_id, body=payload, summary=summary
        )
        return reference, payload

    def audit(self) -> Mapping[str, Any]:
        """Verify every published capture without mutating the store."""

        items: list[dict[str, Any]] = []
        if not self._captures.exists():
            return {
                "schema_id": "agent_trade_emotion_v332_external_store_audit",
                "capture_count": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "observation_count": 0,
                "items": [],
            }
        for directory in sorted(self._captures.iterdir()):
            if not directory.is_dir() or directory.is_symlink() or directory.name.startswith("."):
                continue
            errors: list[str] = []
            capture_path = directory / "capture.json"
            body_path = directory / "body.bin"
            observation_path = directory / "observation.json"
            capture: Mapping[str, Any] = {}
            observation: Mapping[str, Any] = {}
            body = b""
            try:
                capture_value = json.loads(capture_path.read_text(encoding="utf-8"))
                if not isinstance(capture_value, Mapping):
                    raise ValueError
                capture = capture_value
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                errors.append("CAPTURE_JSON_INVALID")
            try:
                if body_path.is_symlink():
                    raise OSError
                body = body_path.read_bytes()
            except OSError:
                errors.append("BODY_INVALID")
            response = capture.get("response") if isinstance(capture, Mapping) else None
            expected_digest = response.get("body_sha256") if isinstance(response, Mapping) else None
            expected_size = response.get("body_size_bytes") if isinstance(response, Mapping) else None
            digest = hashlib.sha256(body).hexdigest()
            if capture and capture.get("capture_id") != directory.name:
                errors.append("CAPTURE_ID_MISMATCH")
            if expected_digest != digest:
                errors.append("BODY_SHA256_MISMATCH")
            if expected_size != len(body):
                errors.append("BODY_SIZE_MISMATCH")
            if observation_path.exists():
                try:
                    observation_value = json.loads(observation_path.read_text(encoding="utf-8"))
                    if not isinstance(observation_value, Mapping):
                        raise ValueError
                    observation = observation_value
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    errors.append("OBSERVATION_JSON_INVALID")
                if observation and observation.get("capture_id") != directory.name:
                    errors.append("OBSERVATION_CAPTURE_ID_MISMATCH")
                if observation and observation.get("raw_sha256") != digest:
                    errors.append("OBSERVATION_SHA256_MISMATCH")
            else:
                errors.append("OBSERVATION_MISSING")
            items.append(
                {
                    "capture_id": directory.name,
                    "source_id": (
                        observation.get("source_id")
                        if isinstance(observation, Mapping)
                        else None
                    ),
                    "status": (
                        observation.get("status")
                        if isinstance(observation, Mapping)
                        else None
                    ),
                    "observation_present": observation_path.exists(),
                    "completion_status": (
                        "COMPLETE" if observation_path.exists() and not errors else "INCOMPLETE"
                    ),
                    "valid": not errors,
                    "errors": errors,
                }
            )
        return {
            "schema_id": "agent_trade_emotion_v332_external_store_audit",
            "capture_count": len(items),
            "valid_count": sum(bool(item["valid"]) for item in items),
            "invalid_count": sum(not bool(item["valid"]) for item in items),
            "observation_count": sum(bool(item["observation_present"]) for item in items),
            "items": items,
        }


__all__ = ["FileRawStore", "RawStoreError"]
