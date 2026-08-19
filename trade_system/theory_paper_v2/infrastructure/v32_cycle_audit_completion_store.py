"""Write-once local store for V3.2 post-acceptance audit completions."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from ..application.v32_cycle_audit_completion import (
    DIGEST_FIELD,
    verify_v32_cycle_audit_completion_receipt_v1,
)
from ..domain.contracts.canonical import canonical_bytes, load_json_strict
from ..v32_durable_json import (
    confirm_existing_json,
    ensure_directory_tree,
    write_once_json,
)


class V32CycleAuditCompletionStoreError(ValueError):
    """A durable post-acceptance audit completion is missing or conflicting."""


STORE_ROOT = "v32-cycle-audit-completion-v1"


class LocalV32CycleAuditCompletionStore:
    def __init__(self, run_root: Path) -> None:
        supplied = Path(run_root).absolute()
        ensure_directory_tree(supplied)
        if supplied.is_symlink() or not supplied.is_dir():
            raise V32CycleAuditCompletionStoreError(
                "V32_AUDIT_COMPLETION_STORE_ROOT_INVALID"
            )
        self.run_root = supplied
        self._physical_root = supplied.resolve(strict=True)

    def _path(self, run_id: str, cycle_index: int) -> Path:
        if (
            not isinstance(run_id, str)
            or not run_id
            or "/" in run_id
            or "\\" in run_id
            or isinstance(cycle_index, bool)
            or not isinstance(cycle_index, int)
            or not 1 <= cycle_index <= 16
        ):
            raise V32CycleAuditCompletionStoreError(
                "V32_AUDIT_COMPLETION_STORE_IDENTITY_INVALID"
            )
        relative = Path(STORE_ROOT) / run_id / f"cycle-{cycle_index:04d}.json"
        path = self.run_root / relative
        try:
            current = self.run_root
            for part in relative.parts:
                current = current / part
                if current.exists() and current.is_symlink():
                    raise V32CycleAuditCompletionStoreError(
                        "V32_AUDIT_COMPLETION_STORE_SYMLINK_FORBIDDEN"
                    )
            path.resolve(strict=False).relative_to(self._physical_root)
        except V32CycleAuditCompletionStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise V32CycleAuditCompletionStoreError(
                "V32_AUDIT_COMPLETION_STORE_PATH_INVALID"
            ) from exc
        return path

    def persist_completion(
        self,
        *,
        completion: Mapping[str, Any],
        cycle_audit_policy: Mapping[str, Any],
        analysis_acceptance: Mapping[str, Any],
        narrative_directory: Mapping[str, Any],
        narrative_shards: list[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        try:
            digest = verify_v32_cycle_audit_completion_receipt_v1(
                completion,
                cycle_audit_policy=cycle_audit_policy,
                analysis_acceptance=analysis_acceptance,
                narrative_directory=narrative_directory,
                narrative_shards=narrative_shards,
            )
        except (TypeError, ValueError) as exc:
            raise V32CycleAuditCompletionStoreError(
                "V32_AUDIT_COMPLETION_STORE_DOCUMENT_INVALID"
            ) from exc
        path = self._path(str(completion["run_id"]), int(completion["cycle_index"]))
        try:
            write_once_json(path, completion)
            confirm_existing_json(path, completion)
        except (OSError, TypeError, ValueError) as exc:
            raise V32CycleAuditCompletionStoreError(
                "V32_AUDIT_COMPLETION_STORE_WRITE_CONFLICT"
            ) from exc
        return {
            "relative_ref": path.relative_to(self.run_root).as_posix(),
            "schema_id": completion["schema_id"],
            "digest_field": DIGEST_FIELD,
            "semantic_digest": digest,
            "physical_sha256": hashlib.sha256(
                canonical_bytes(dict(completion)) + b"\n"
            ).hexdigest(),
        }

    def load_completion(
        self, *, run_id: str, cycle_index: int
    ) -> Mapping[str, Any] | None:
        path = self._path(run_id, cycle_index)
        if not path.exists():
            return None
        try:
            document = load_json_strict(path)
            confirm_existing_json(path, document)
            return document
        except (OSError, TypeError, ValueError) as exc:
            raise V32CycleAuditCompletionStoreError(
                "V32_AUDIT_COMPLETION_STORE_DOCUMENT_INVALID"
            ) from exc


__all__ = [
    "LocalV32CycleAuditCompletionStore",
    "STORE_ROOT",
    "V32CycleAuditCompletionStoreError",
]
