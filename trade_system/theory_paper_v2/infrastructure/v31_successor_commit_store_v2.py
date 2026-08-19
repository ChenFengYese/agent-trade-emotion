"""Write-once coordinator store for successor cross-owner commit material."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..domain.contracts.canonical import (
    canonical_bytes,
    load_json_strict,
    write_once_json,
)
from ..domain.v31_successor_cycle_commit_v2 import (
    COMMIT_ROOT,
    DIGEST_FIELD,
    verify_v31_successor_cycle_commit_material_v2,
)


class V31SuccessorCommitStoreV2Error(ValueError):
    """Commit material is missing, unsafe, or physically inconsistent."""


class LocalV31SuccessorCommitStoreV2:
    """Own only immutable commit material; own no research/monitor cursor."""

    def __init__(
        self, run_root: Path, *, experiment_contract: Mapping[str, Any]
    ) -> None:
        self.run_root = Path(run_root).resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.experiment_contract = dict(experiment_contract)

    def _safe_path(self, relative_ref: str) -> Path:
        if not isinstance(relative_ref, str) or not relative_ref:
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_REF_INVALID"
            )
        lexical = PurePosixPath(relative_ref)
        if (
            "\\" in relative_ref
            or lexical.as_posix() != relative_ref
            or lexical.is_absolute()
            or not lexical.parts
            or lexical.parts[0] != COMMIT_ROOT
            or any(part in {"", ".", ".."} for part in lexical.parts)
        ):
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_REF_INVALID"
            )
        cursor = self.run_root
        for part in lexical.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise V31SuccessorCommitStoreV2Error(
                    "V31_SUCCESSOR_COMMIT_SYMLINK_FORBIDDEN"
                )
        target = self.run_root.joinpath(*lexical.parts).resolve(strict=False)
        try:
            target.relative_to(self.run_root)
        except ValueError as exc:
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_REF_ESCAPE"
            ) from exc
        return target

    @staticmethod
    def _physical_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_material(
        self, *, relative_ref: str, document: Mapping[str, Any]
    ) -> Mapping[str, str]:
        semantic = verify_v31_successor_cycle_commit_material_v2(
            document, experiment_contract=self.experiment_contract
        )
        path = self._safe_path(relative_ref)
        try:
            write_once_json(path, document)
        except (OSError, TypeError, ValueError) as exc:
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_WRITE_ONCE_CONFLICT"
            ) from exc
        durable = self.read_material(
            relative_ref=relative_ref, expected_semantic_digest=semantic
        )
        if dict(durable) != dict(document):
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_READBACK_DRIFT"
            )
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": DIGEST_FIELD,
            "semantic_digest": semantic,
            "physical_sha256": self._physical_sha256(path),
        }

    def read_material(
        self,
        *,
        relative_ref: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        path = self._safe_path(relative_ref)
        try:
            if path.is_symlink() or not path.is_file():
                raise V31SuccessorCommitStoreV2Error(
                    "V31_SUCCESSOR_COMMIT_MISSING"
                )
            document = load_json_strict(path)
            semantic = verify_v31_successor_cycle_commit_material_v2(
                document, experiment_contract=self.experiment_contract
            )
        except V31SuccessorCommitStoreV2Error:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_INVALID"
            ) from exc
        if (
            expected_semantic_digest is not None
            and semantic != expected_semantic_digest
        ):
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_SEMANTIC_DRIFT"
            )
        if path.read_bytes() != canonical_bytes(dict(document)) + b"\n":
            raise V31SuccessorCommitStoreV2Error(
                "V31_SUCCESSOR_COMMIT_PHYSICAL_DRIFT"
            )
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        document = self.read_material(
            relative_ref=relative_ref,
            expected_semantic_digest=expected_semantic_digest,
        )
        path = self._safe_path(relative_ref)
        return {
            "relative_ref": relative_ref,
            "schema_id": str(document["schema_id"]),
            "digest_field": DIGEST_FIELD,
            "semantic_digest": str(document[DIGEST_FIELD]),
            "physical_sha256": self._physical_sha256(path),
        }

    def material_exists(self, *, relative_ref: str) -> bool:
        path = self._safe_path(relative_ref)
        return path.is_file() and not path.is_symlink()


__all__ = [
    "LocalV31SuccessorCommitStoreV2",
    "V31SuccessorCommitStoreV2Error",
]
