"""Filesystem-backed write-once artifact store."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ContentStoreError(ValueError):
    pass


class ContentAddressedStore:
    def __init__(self, run_root: Path) -> None:
        self._root = Path(run_root).resolve() / "work"
        self._root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_token(value: str) -> None:
        if _SAFE_TOKEN.fullmatch(value) is None or value in {".", ".."}:
            raise ContentStoreError("CONTENT_KEY_INVALID")

    def _path(self, namespace: str, artifact_id: str, digest: str) -> Path:
        namespace_path = PurePosixPath(namespace)
        if (
            namespace_path.is_absolute()
            or not namespace_path.parts
            or any(
                part in {".", ".."} or _SAFE_TOKEN.fullmatch(part) is None
                for part in namespace_path.parts
            )
        ):
            raise ContentStoreError("CONTENT_KEY_INVALID")
        for value in (artifact_id, digest):
            self._validate_token(value)
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ContentStoreError("CONTENT_DIGEST_INVALID")
        return self._root.joinpath(*namespace_path.parts) / artifact_id / f"{digest}.blob"

    def put(self, namespace: str, artifact_id: str, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise ContentStoreError("CONTENT_BYTES_REQUIRED")
        digest = hashlib.sha256(payload).hexdigest()
        target = self._path(namespace, artifact_id, digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != payload:
                raise ContentStoreError("CONTENT_KEY_COLLISION")
            return digest
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return digest

    def get(self, namespace: str, artifact_id: str, digest: str) -> bytes:
        target = self._path(namespace, artifact_id, digest)
        try:
            payload = target.read_bytes()
        except FileNotFoundError as exc:
            raise ContentStoreError("CONTENT_BLOB_MISSING") from exc
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ContentStoreError("CONTENT_BLOB_DIGEST_MISMATCH")
        return payload
