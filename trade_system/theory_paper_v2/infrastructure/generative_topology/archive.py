"""Exclusive-create archive for paired generative topology runs."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ...domain.contracts.canonical import canonical_bytes


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MUTABLE_ALIASES = {"current", "latest"}


class PairedRunArchiveError(ValueError):
    pass


class WriteOncePairedRunArchive:
    """Own one new run directory; every contained file is exclusive-create."""

    def __init__(self, archive_root: Path, paired_session_id: str) -> None:
        if (
            _SAFE_TOKEN.fullmatch(paired_session_id) is None
            or paired_session_id.casefold() in _MUTABLE_ALIASES
        ):
            raise PairedRunArchiveError("PAIRED_SESSION_ID_PATH_INVALID")
        base = Path(archive_root).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self._root = base / paired_session_id
        try:
            self._root.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise PairedRunArchiveError(
                "PAIRED_RUN_DIRECTORY_ALREADY_EXISTS"
            ) from exc
        root_binding = hashlib.sha256(
            f"{paired_session_id}\0{self._root}".encode("utf-8")
        ).hexdigest()
        self._run_ref = (
            f"paired-generative-run:{paired_session_id}:{root_binding}"
        )

    @property
    def run_ref(self) -> str:
        return self._run_ref

    @property
    def root_path(self) -> Path:
        return self._root

    def _path(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path:
            raise PairedRunArchiveError("RUN_ARTIFACT_PATH_INVALID")
        relative = PurePosixPath(relative_path)
        if (
            relative.is_absolute()
            or any(
                part in {"", ".", ".."}
                or part.casefold() in _MUTABLE_ALIASES
                or _SAFE_TOKEN.fullmatch(part) is None
                for part in relative.parts
            )
        ):
            raise PairedRunArchiveError("RUN_ARTIFACT_PATH_INVALID")
        target = self._root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.resolve() != self._root and self._root not in (
            target.parent.resolve().parents
        ):
            raise PairedRunArchiveError("RUN_ARTIFACT_PATH_ESCAPE")
        if any(path.is_symlink() for path in target.parents if path != self._root.parent):
            raise PairedRunArchiveError("RUN_ARTIFACT_SYMLINK_FORBIDDEN")
        return target

    def write_bytes(self, relative_path: str, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise PairedRunArchiveError("RUN_ARTIFACT_BYTES_REQUIRED")
        target = self._path(relative_path)
        try:
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as exc:
            raise PairedRunArchiveError(
                "WRITE_ONCE_RUN_ARTIFACT_CONFLICT"
            ) from exc
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return hashlib.sha256(payload).hexdigest()

    def write_json(
        self, relative_path: str, value: Mapping[str, Any]
    ) -> str:
        return self.write_bytes(
            relative_path, canonical_bytes(dict(value)) + b"\n"
        )

    def artifact_ref(self, relative_path: str, digest: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise PairedRunArchiveError("RUN_ARTIFACT_DIGEST_INVALID")
        target = self._path(relative_path)
        try:
            relative = target.relative_to(self._root).as_posix()
        except ValueError as exc:
            raise PairedRunArchiveError("RUN_ARTIFACT_PATH_ESCAPE") from exc
        return f"{self._run_ref}:{relative}:{digest}"


__all__ = ["PairedRunArchiveError", "WriteOncePairedRunArchive"]
