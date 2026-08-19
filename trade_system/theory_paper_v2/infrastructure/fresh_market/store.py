"""Write-once filesystem store for fresh-market freeze bundles."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from ...domain.contracts.canonical import write_once_json
from .model import require_id


class FreshMarketStoreError(ValueError):
    pass


class FreshMarketWriteOnceStore:
    """Materialize one explicit bundle without mutable aliases."""

    def __init__(self, *, output_root: Path, bundle_id: str) -> None:
        require_id(bundle_id)
        root = Path(output_root).expanduser().resolve()
        if root.exists() and not root.is_dir():
            raise FreshMarketStoreError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
        root.mkdir(parents=True, exist_ok=True)
        bundle_root = root / "bundles" / bundle_id
        if bundle_root.exists() and (
            bundle_root.is_symlink() or not bundle_root.is_dir()
        ):
            raise FreshMarketStoreError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
        bundle_root.mkdir(parents=True, exist_ok=True)
        resolved_bundle = bundle_root.resolve()
        bundles_root = (root / "bundles").resolve()
        if (
            resolved_bundle.parent != bundles_root
            or resolved_bundle.name != bundle_id
        ):
            raise FreshMarketStoreError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
        self.root = root
        self.bundle_id = bundle_id
        self.bundle_root = resolved_bundle

    def _target(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if (
            candidate.is_absolute()
            or not candidate.parts
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise FreshMarketStoreError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
        target = self.bundle_root.joinpath(*candidate.parts)
        cursor = self.bundle_root
        for part in candidate.parts[:-1]:
            cursor = cursor / part
            if cursor.exists() and cursor.is_symlink():
                raise FreshMarketStoreError(
                    "OFFLINE_REPLAY_FAILED_NO_COMMIT"
                )
        resolved_parent = target.parent.resolve()
        if (
            resolved_parent != self.bundle_root
            and self.bundle_root not in resolved_parent.parents
        ):
            raise FreshMarketStoreError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
        if target.exists() and target.is_symlink():
            raise FreshMarketStoreError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
        return target

    def write_raw(self, relative_path: str, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise FreshMarketStoreError("EVIDENCE_LINEAGE_INVALID")
        target = self._target(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.read_bytes() != payload:
                raise FreshMarketStoreError(
                    f"WRITE_ONCE_CONFLICT:{target}"
                )
            return "EXISTING_IDENTICAL"
        try:
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError as exc:
            if target.is_file() and target.read_bytes() == payload:
                return "EXISTING_IDENTICAL"
            raise FreshMarketStoreError(
                f"WRITE_ONCE_RACE:{target}"
            ) from exc
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return "CREATED"

    def write_json(
        self, relative_path: str, value: Mapping[str, object]
    ) -> str:
        return write_once_json(self._target(relative_path), value)


__all__ = ["FreshMarketStoreError", "FreshMarketWriteOnceStore"]
