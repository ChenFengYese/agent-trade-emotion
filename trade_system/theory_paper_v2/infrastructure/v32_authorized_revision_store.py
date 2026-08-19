"""Local write-once storage for the authorized V3.2 revision artifacts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, Sequence

from ..application.v32_authorized_revision_orchestration import (
    CYCLE_REGISTRY_DIGEST_FIELD,
    CYCLE_REGISTRY_SCHEMA_ID,
    SUPPORT_BUNDLE_DIGEST_FIELD,
    SUPPORT_BUNDLE_SCHEMA_ID,
    verify_v32_authorized_revision_cycle_registry_receipt_v1,
)
from ..domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    load_json_strict,
    verify_self_digest,
)
from ..v32_durable_json import (
    confirm_existing_directory,
    confirm_existing_json,
    write_once_directory,
    write_once_json,
)
from ..domain.v32_authorized_revision_common import verify_boundary
from ..domain.v32_context_compaction import (
    MANIFEST_DIGEST_FIELD,
    MANIFEST_SCHEMA_ID,
    POLICY_DIGEST_FIELD as CONTEXT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as CONTEXT_POLICY_SCHEMA_ID,
    SELECTION_DIGEST_FIELD,
    SELECTION_SCHEMA_ID,
    SHARD_DIGEST_FIELD as CONTEXT_SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID as CONTEXT_SHARD_SCHEMA_ID,
    verify_v32_context_compaction_bundle_v1,
)
from ..domain.v32_cycle_audit_narrative import (
    BOUNDARY_TYPES,
    DIRECTORY_DIGEST_FIELD,
    DIRECTORY_SCHEMA_ID,
    POLICY_DIGEST_FIELD as AUDIT_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as AUDIT_POLICY_SCHEMA_ID,
    SHARD_DIGEST_FIELD as AUDIT_SHARD_DIGEST_FIELD,
    SHARD_SCHEMA_ID as AUDIT_SHARD_SCHEMA_ID,
    verify_v32_cycle_audit_narrative_bundle_v1,
)
from ..domain.v32_data_gap_escalation import (
    ESCALATION_DIGEST_FIELD,
    ESCALATION_SCHEMA_ID,
    MANUAL_REVISION_DIGEST_FIELD,
    MANUAL_REVISION_SCHEMA_ID,
    POLICY_DIGEST_FIELD as DATA_GAP_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as DATA_GAP_POLICY_SCHEMA_ID,
)
from ..domain.v32_environment_capability import (
    DIGEST_FIELD as ENVIRONMENT_DIGEST_FIELD,
    SCHEMA_ID as ENVIRONMENT_SCHEMA_ID,
)
from ..domain.v32_unknown_assessment import (
    ASSESSMENT_DIGEST_FIELD,
    ASSESSMENT_SCHEMA_ID,
    EVIDENCE_REGISTRY_DIGEST_FIELD,
    EVIDENCE_REGISTRY_SCHEMA_ID,
    OBJECTIVE_DIGEST_FIELD,
    OBJECTIVE_SCHEMA_ID,
    POLICY_DIGEST_FIELD as UNKNOWN_POLICY_DIGEST_FIELD,
    POLICY_SCHEMA_ID as UNKNOWN_POLICY_SCHEMA_ID,
)


STORE_ROOT = "v32-authorized-revisions-v1"
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._:-]+$")
_ROLE_SPECS = {
    "context_compaction_policy": (
        CONTEXT_POLICY_SCHEMA_ID,
        CONTEXT_POLICY_DIGEST_FIELD,
    ),
    "unknown_subjective_policy": (
        UNKNOWN_POLICY_SCHEMA_ID,
        UNKNOWN_POLICY_DIGEST_FIELD,
    ),
    "data_gap_manual_policy": (
        DATA_GAP_POLICY_SCHEMA_ID,
        DATA_GAP_POLICY_DIGEST_FIELD,
    ),
    "cycle_audit_policy": (
        AUDIT_POLICY_SCHEMA_ID,
        AUDIT_POLICY_DIGEST_FIELD,
    ),
    "context_shard_selection": (SELECTION_SCHEMA_ID, SELECTION_DIGEST_FIELD),
    "objective_unknown": (OBJECTIVE_SCHEMA_ID, OBJECTIVE_DIGEST_FIELD),
    "unknown_evidence_registry": (
        EVIDENCE_REGISTRY_SCHEMA_ID,
        EVIDENCE_REGISTRY_DIGEST_FIELD,
    ),
    "unknown_subjective_assessment": (
        ASSESSMENT_SCHEMA_ID,
        ASSESSMENT_DIGEST_FIELD,
    ),
    "data_gap_escalation": (ESCALATION_SCHEMA_ID, ESCALATION_DIGEST_FIELD),
    "manual_public_evidence_revision": (
        MANUAL_REVISION_SCHEMA_ID,
        MANUAL_REVISION_DIGEST_FIELD,
    ),
    "environment_capability_profile": (
        ENVIRONMENT_SCHEMA_ID,
        ENVIRONMENT_DIGEST_FIELD,
    ),
    "authorized_revision_support_bundle": (
        SUPPORT_BUNDLE_SCHEMA_ID,
        SUPPORT_BUNDLE_DIGEST_FIELD,
    ),
    "authorized_revision_cycle_registry": (
        CYCLE_REGISTRY_SCHEMA_ID,
        CYCLE_REGISTRY_DIGEST_FIELD,
    ),
}


class V32AuthorizedRevisionStoreError(ValueError):
    """A write-once artifact conflicted or failed exact readback."""


def _segment(value: Any, code: str) -> str:
    if not isinstance(value, str) or _SAFE_SEGMENT.fullmatch(value) is None:
        raise V32AuthorizedRevisionStoreError(code)
    return value


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _absolute_lexical(path: Path) -> Path:
    """Return an absolute lexical path without resolving user symlinks."""

    try:
        return Path(os.path.abspath(os.fspath(path)))
    except (OSError, TypeError, ValueError) as exc:
        raise V32AuthorizedRevisionStoreError(
            "V32_REVISION_STORE_ROOT_INVALID"
        ) from exc


def _assert_no_symlink_components(
    path: Path, *, leaf_must_be_directory: bool
) -> None:
    """Reject aliases in the lexical namespace before any path operation.

    macOS exposes system locations such as ``/var`` through a root-owned first
    component alias.  That privileged platform alias is the sole exception;
    every user-controlled component, including the configured root and target
    leaf, must retain its lexical identity.
    """

    if not path.is_absolute():
        raise V32AuthorizedRevisionStoreError(
            "V32_REVISION_STORE_PATH_INVALID"
        )
    current = Path(path.anchor)
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        try:
            observed = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_PATH_INVALID"
            ) from exc
        if stat.S_ISLNK(observed.st_mode):
            if index == 0 and observed.st_uid == 0 and len(parts) > 1:
                continue
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_PATH_SYMLINK_FORBIDDEN"
            )
        is_leaf = index == len(parts) - 1
        if (not is_leaf or leaf_must_be_directory) and not stat.S_ISDIR(
            observed.st_mode
        ):
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_PATH_INVALID"
            )


class LocalV32AuthorizedRevisionStore:
    """A local append-only adapter; it has no network or authority capability."""

    def __init__(self, root: Path) -> None:
        self.root = _absolute_lexical(Path(root))
        _assert_no_symlink_components(
            self.root, leaf_must_be_directory=True
        )

    def _path(self, relative_ref: str) -> Path:
        if (
            not isinstance(relative_ref, str)
            or not relative_ref
            or relative_ref != relative_ref.strip()
            or "\\" in relative_ref
        ):
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_PATH_INVALID"
            )
        lexical = PurePosixPath(relative_ref)
        if (
            lexical.is_absolute()
            or lexical.as_posix() != relative_ref
            or any(part in {"", ".", ".."} for part in lexical.parts)
            or len(lexical.parts) < 2
            or lexical.parts[0] != STORE_ROOT
            or any(
                _SAFE_SEGMENT.fullmatch(part) is None
                for part in lexical.parts
            )
        ):
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_PATH_INVALID"
            )
        target = self.root.joinpath(*lexical.parts)
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_PATH_ESCAPE"
            ) from exc
        _assert_no_symlink_components(
            target, leaf_must_be_directory=False
        )
        return target

    def _write(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        schema_id: str,
        digest_field: str,
    ) -> dict[str, str]:
        try:
            supplied = verify_self_digest(document, digest_field)
            verify_boundary(document, "V32_REVISION_STORE_BOUNDARY_INVALID")
        except (CanonicalContractError, TypeError, ValueError) as exc:
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_DOCUMENT_INVALID"
            ) from exc
        if document.get("schema_id") != schema_id:
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_SCHEMA_INVALID"
            )
        target = self._path(relative_ref)
        try:
            write_once_json(target, document)
            # Re-enter the lexical namespace and ask the anchored write-once
            # adapter to confirm the exact winner.  This retains readback
            # semantics without following a leaf alias via Path.read_bytes().
            target = self._path(relative_ref)
            confirm_existing_json(target, document)
        except (CanonicalContractError, OSError) as exc:
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_WRITE_ONCE_FAILED"
            ) from exc
        return {
            "relative_ref": relative_ref,
            "schema_id": schema_id,
            "digest_field": digest_field,
            "semantic_digest": supplied,
            "physical_sha256": _physical(document),
        }

    def persist_document(
        self, *, role: str, document: Mapping[str, Any]
    ) -> Mapping[str, str]:
        if role not in _ROLE_SPECS:
            raise V32AuthorizedRevisionStoreError("V32_REVISION_STORE_ROLE_INVALID")
        schema_id, digest_field = _ROLE_SPECS[role]
        run_id = _segment(
            document.get("run_id", document.get("run_scope_id")),
            "V32_REVISION_STORE_RUN_INVALID",
        )
        cycle = document.get("cycle_index", document.get("future_cycle_index", 0))
        if isinstance(cycle, bool) or not isinstance(cycle, int) or not 0 <= cycle <= 16:
            raise V32AuthorizedRevisionStoreError("V32_REVISION_STORE_CYCLE_INVALID")
        try:
            digest_value = verify_self_digest(document, digest_field)
            if role == "authorized_revision_cycle_registry":
                verify_v32_authorized_revision_cycle_registry_receipt_v1(
                    document
                )
        except (CanonicalContractError, TypeError, ValueError) as exc:
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_DOCUMENT_INVALID"
            ) from exc
        relative_ref = (
            f"{STORE_ROOT}/{run_id}/cycles/{cycle:04d}/{role}/"
            f"{digest_value}.json"
        )
        return self._write(
            relative_ref=relative_ref,
            document=document,
            schema_id=schema_id,
            digest_field=digest_field,
        )

    def persist_context_bundle(
        self,
        *,
        manifest: Mapping[str, Any],
        shards: Sequence[Mapping[str, Any]],
        original_documents: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        verify_v32_context_compaction_bundle_v1(
            manifest, shards, original_documents=original_documents
        )
        run_id = _segment(manifest["run_id"], "V32_REVISION_STORE_RUN_INVALID")
        cycle = manifest["cycle_index"]
        shard_bindings = [
            self._write(
                relative_ref=(
                    f"{STORE_ROOT}/{run_id}/cycles/{cycle:04d}/context-shards/"
                    f"{shard['shard_id']}.json"
                ),
                document=shard,
                schema_id=CONTEXT_SHARD_SCHEMA_ID,
                digest_field=CONTEXT_SHARD_DIGEST_FIELD,
            )
            for shard in shards
        ]
        manifest_binding = self._write(
            relative_ref=(
                f"{STORE_ROOT}/{run_id}/cycles/{cycle:04d}/context-compaction/"
                f"{manifest[MANIFEST_DIGEST_FIELD]}.json"
            ),
            document=manifest,
            schema_id=MANIFEST_SCHEMA_ID,
            digest_field=MANIFEST_DIGEST_FIELD,
        )
        return {
            "manifest_binding": manifest_binding,
            "shard_bindings": shard_bindings,
        }

    def persist_audit_bundle(
        self,
        *,
        directory: Mapping[str, Any],
        shards: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        verify_v32_cycle_audit_narrative_bundle_v1(directory, shards)
        run_id = _segment(directory["run_id"], "V32_REVISION_STORE_RUN_INVALID")
        cycle = directory["cycle_index"]
        boundary = directory["boundary_type"].lower()
        existing = self._load_audit_bundle_record(
            run_id=run_id,
            cycle_index=cycle,
            boundary_type=str(directory["boundary_type"]),
        )
        if existing is not None:
            if (
                existing["directory"] != dict(directory)
                or existing["shards"] != [dict(shard) for shard in shards]
            ):
                raise V32AuthorizedRevisionStoreError(
                    "V32_REVISION_STORE_WRITE_ONCE_FAILED"
                )
            return {
                "directory_binding": existing["directory_binding"],
                "shard_bindings": existing["shard_bindings"],
            }
        base_ref = (
            f"{STORE_ROOT}/{run_id}/cycles/{cycle:04d}/audit/{boundary}"
        )
        files = {"directory.json": canonical_bytes(dict(directory)) + b"\n"}
        files.update(
            {
                f"shard-{index:04d}.json": canonical_bytes(dict(shard)) + b"\n"
                for index, shard in enumerate(shards)
            }
        )
        base = self._path(base_ref)
        try:
            # The complete narrative is one publication boundary.  A crash
            # before rename exposes no boundary; a crash after rename exposes
            # the exact complete bundle and is replayed without a new clock.
            write_once_directory(base, files)
            base = self._path(base_ref)
            confirm_existing_directory(base, files)
        except (CanonicalContractError, OSError) as exc:
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_WRITE_ONCE_FAILED"
            ) from exc

        def binding(
            *,
            relative_ref: str,
            document: Mapping[str, Any],
            schema_id: str,
            digest_field: str,
        ) -> dict[str, str]:
            return {
                "relative_ref": relative_ref,
                "schema_id": schema_id,
                "digest_field": digest_field,
                "semantic_digest": str(document[digest_field]),
                "physical_sha256": _physical(document),
            }

        directory_binding = binding(
            relative_ref=f"{base_ref}/directory.json",
            document=directory,
            schema_id=DIRECTORY_SCHEMA_ID,
            digest_field=DIRECTORY_DIGEST_FIELD,
        )
        shard_bindings = [
            binding(
                relative_ref=f"{base_ref}/shard-{index:04d}.json",
                document=shard,
                schema_id=AUDIT_SHARD_SCHEMA_ID,
                digest_field=AUDIT_SHARD_DIGEST_FIELD,
            )
            for index, shard in enumerate(shards)
        ]
        return {
            "directory_binding": directory_binding,
            "shard_bindings": shard_bindings,
        }

    def _load_audit_bundle_record(
        self, *, run_id: str, cycle_index: int, boundary_type: str
    ) -> Mapping[str, Any] | None:
        """Reopen one exact narrative plus store-owned replay metadata."""

        run = _segment(run_id, "V32_REVISION_STORE_RUN_INVALID")
        if (
            isinstance(cycle_index, bool)
            or not isinstance(cycle_index, int)
            or not 0 <= cycle_index <= 16
            or boundary_type not in BOUNDARY_TYPES
            or (boundary_type == "QUALIFICATION" and cycle_index != 0)
            or (boundary_type != "QUALIFICATION" and cycle_index == 0)
        ):
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_AUDIT_IDENTITY_INVALID"
            )
        base_ref = (
            f"{STORE_ROOT}/{run}/cycles/{cycle_index:04d}/audit/"
            f"{boundary_type.lower()}"
        )
        base = self._path(base_ref)
        if not base.exists():
            return None
        if not base.is_dir() or base.is_symlink():
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_AUDIT_PATH_INVALID"
            )
        # Successor bundles use a flat exact directory so every shard and the
        # directory document appear atomically.  Fully materialized legacy
        # bundles remain replayable; partial legacy tails remain fail closed.
        successor_directory = base / "directory.json"
        if successor_directory.exists():
            layout = "SUCCESSOR_ATOMIC"
            directory_paths = [successor_directory]
            try:
                directory_preview = load_json_strict(successor_directory)
                shard_count = directory_preview.get("shard_count")
            except (OSError, TypeError, ValueError) as exc:
                raise V32AuthorizedRevisionStoreError(
                    "V32_REVISION_STORE_AUDIT_LAYOUT_INVALID"
                ) from exc
            if (
                isinstance(shard_count, bool)
                or not isinstance(shard_count, int)
                or shard_count < 1
            ):
                raise V32AuthorizedRevisionStoreError(
                    "V32_REVISION_STORE_AUDIT_LAYOUT_INVALID"
                )
            shard_paths = [
                base / f"shard-{index:04d}.json"
                for index in range(shard_count)
            ]
            expected_names = {
                "directory.json",
                *(path.name for path in shard_paths),
            }
            if set(path.name for path in base.iterdir()) != expected_names:
                raise V32AuthorizedRevisionStoreError(
                    "V32_REVISION_STORE_AUDIT_LAYOUT_INVALID"
                )
        else:
            layout = "LEGACY_EXACT"
            shard_root = base / "shards"
            directory_paths = sorted(
                path for path in base.iterdir() if path.name != "shards"
            )
            if (
                len(directory_paths) != 1
                or not shard_root.is_dir()
                or shard_root.is_symlink()
            ):
                raise V32AuthorizedRevisionStoreError(
                    "V32_REVISION_STORE_AUDIT_LAYOUT_INVALID"
                )
            shard_paths = sorted(shard_root.iterdir(), key=lambda path: path.name)
        if (
            len(directory_paths) != 1
            or not directory_paths[0].is_file()
            or directory_paths[0].is_symlink()
            or not shard_paths
            or any(
                not path.is_file() or path.is_symlink()
                for path in shard_paths
            )
        ):
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_AUDIT_LAYOUT_INVALID"
            )
        try:
            directory = load_json_strict(directory_paths[0])
            shards = [load_json_strict(path) for path in shard_paths]
            if any(
                path.read_bytes() != canonical_bytes(document) + b"\n"
                for path, document in [
                    (directory_paths[0], directory),
                    *zip(shard_paths, shards),
                ]
            ):
                raise V32AuthorizedRevisionStoreError(
                    "V32_REVISION_STORE_AUDIT_NONCANONICAL"
                )
            confirm_existing_json(directory_paths[0], directory)
            for path, document in zip(shard_paths, shards):
                confirm_existing_json(path, document)
            verify_v32_cycle_audit_narrative_bundle_v1(directory, shards)
        except (CanonicalContractError, OSError, TypeError, ValueError) as exc:
            if isinstance(exc, V32AuthorizedRevisionStoreError):
                raise
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_AUDIT_REPLAY_INVALID"
            ) from exc
        if (
            directory.get("run_id") != run
            or directory.get("cycle_index") != cycle_index
            or directory.get("boundary_type") != boundary_type
            or directory_paths[0].name
            not in {
                "directory.json",
                f"{directory[DIRECTORY_DIGEST_FIELD]}.json",
            }
            or len(shards) != directory.get("shard_count")
        ):
            raise V32AuthorizedRevisionStoreError(
                "V32_REVISION_STORE_AUDIT_REPLAY_INVALID"
            )
        def binding(
            *,
            path: Path,
            document: Mapping[str, Any],
            schema_id: str,
            digest_field: str,
        ) -> dict[str, str]:
            return {
                "relative_ref": path.relative_to(self.root).as_posix(),
                "schema_id": schema_id,
                "digest_field": digest_field,
                "semantic_digest": str(document[digest_field]),
                "physical_sha256": _physical(document),
            }

        return {
            "directory": directory,
            "shards": shards,
            "layout": layout,
            "directory_binding": binding(
                path=directory_paths[0],
                document=directory,
                schema_id=DIRECTORY_SCHEMA_ID,
                digest_field=DIRECTORY_DIGEST_FIELD,
            ),
            "shard_bindings": [
                binding(
                    path=path,
                    document=document,
                    schema_id=AUDIT_SHARD_SCHEMA_ID,
                    digest_field=AUDIT_SHARD_DIGEST_FIELD,
                )
                for path, document in zip(shard_paths, shards)
            ],
        }

    def load_audit_bundle(
        self, *, run_id: str, cycle_index: int, boundary_type: str
    ) -> Mapping[str, Any] | None:
        """Replay the original public bundle without store-owned metadata."""

        record = self._load_audit_bundle_record(
            run_id=run_id,
            cycle_index=cycle_index,
            boundary_type=boundary_type,
        )
        if record is None:
            return None
        return {
            "directory": record["directory"],
            "shards": record["shards"],
        }


__all__ = [
    "LocalV32AuthorizedRevisionStore",
    "STORE_ROOT",
    "V32AuthorizedRevisionStoreError",
]
