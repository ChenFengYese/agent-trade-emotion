"""Freeze and materialize the canonical Theory Agent V2 contract bundle.

There are deliberately two different modes:

* bootstrap freeze builds the catalog once and writes the immutable manifest;
* every ordinary invocation strictly loads that manifest and verifies its
  outer and nested self-digests before deriving portable schema files.

The frozen JSON manifest is therefore the authority.  The executable catalog
is only a bootstrap source and a deterministic schema renderer whose output is
checked against the schema byte digests frozen in the manifest.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)
from ...domain.contracts.catalog import (
    build_canonical_manifest,
    schema_documents_from_manifest,
    validate_catalog_manifest,
)


DEFAULT_MANIFEST_RELATIVE_PATH = Path(
    "config/theory_agent_v2.canonical_contract_manifest.v1.json"
)
DEFAULT_OUTPUT_RELATIVE_PATH = Path("agent-cluster/contracts")

_NESTED_REGISTRY_NAMES = (
    "schema_registry",
    "object_owner_registry",
    "closed_error_registry",
    "closed_event_registry",
    "constraint_registry",
    "plugin_policy_registry",
)
_DERIVED_MANIFEST_SECTION_NAMES = (
    "closed_enums",
    "reducer_transition_tables",
    "event_name_resolution",
    "authority_tuple",
)
_SCHEMA_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FrozenManifestError(CanonicalContractError):
    """A frozen-manifest or portable-bundle invariant failed closed."""


@dataclass(frozen=True)
class MaterializedBundle:
    """Deterministic result metadata for one portable bundle."""

    output_directory: Path
    source_manifest_digest: str
    bundle_index_digest: str
    file_count: int
    schema_count: int


def _verify_registry(
    registry_name: str,
    registry: Any,
) -> Mapping[str, Any]:
    if not isinstance(registry, Mapping):
        raise FrozenManifestError(f"REGISTRY_NOT_OBJECT:{registry_name}")
    try:
        verify_self_digest(registry, "registry_digest")
    except CanonicalContractError as exc:
        raise FrozenManifestError(
            f"NESTED_REGISTRY_DIGEST_INVALID:{registry_name}"
        ) from exc
    if registry.get("closed") is not True:
        raise FrozenManifestError(f"NESTED_REGISTRY_NOT_CLOSED:{registry_name}")
    entries = registry.get("entries")
    if not isinstance(entries, list):
        raise FrozenManifestError(f"NESTED_REGISTRY_ENTRIES_INVALID:{registry_name}")
    return registry


def verify_frozen_manifest(manifest: Mapping[str, Any]) -> str:
    """Verify frozen integrity without rebuilding the catalog."""

    try:
        digest = verify_self_digest(manifest, "manifest_digest")
    except CanonicalContractError as exc:
        raise FrozenManifestError("MANIFEST_SELF_DIGEST_INVALID") from exc

    for registry_name in _NESTED_REGISTRY_NAMES:
        if registry_name not in manifest:
            raise FrozenManifestError(f"NESTED_REGISTRY_MISSING:{registry_name}")
        _verify_registry(registry_name, manifest[registry_name])

    schema_registry = manifest["schema_registry"]
    entries = schema_registry["entries"]
    schema_ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise FrozenManifestError("SCHEMA_REGISTRY_ENTRY_NOT_OBJECT")
        schema_id = entry.get("schema_id")
        if not isinstance(schema_id, str) or _SCHEMA_ID_PATTERN.fullmatch(
            schema_id
        ) is None:
            raise FrozenManifestError("SCHEMA_ID_UNSAFE_OR_INVALID")
        schema_digest = entry.get("schema_bytes_digest")
        if not isinstance(schema_digest, str) or _DIGEST_PATTERN.fullmatch(
            schema_digest
        ) is None:
            raise FrozenManifestError(
                f"SCHEMA_BYTES_DIGEST_INVALID:{schema_id}"
            )
        schema_ids.append(schema_id)
    if len(schema_ids) != len(set(schema_ids)):
        raise FrozenManifestError("SCHEMA_ID_DUPLICATE")
    diagnostic_count = manifest.get("resolved_schema_identity_count_diagnostic_only")
    if diagnostic_count != len(schema_ids):
        raise FrozenManifestError("SCHEMA_IDENTITY_COUNT_DIAGNOSTIC_MISMATCH")

    owner_entries = manifest["object_owner_registry"]["entries"]
    owner_schema_ids: list[str] = []
    for entry in owner_entries:
        if not isinstance(entry, Mapping):
            raise FrozenManifestError("OBJECT_OWNER_ENTRY_NOT_OBJECT")
        schema_id = entry.get("object_schema_id")
        if not isinstance(schema_id, str):
            raise FrozenManifestError("OBJECT_OWNER_SCHEMA_ID_INVALID")
        owner_schema_ids.append(schema_id)
    if len(owner_schema_ids) != len(set(owner_schema_ids)):
        raise FrozenManifestError("OBJECT_OWNER_DUPLICATE")
    if not set(owner_schema_ids).issubset(schema_ids):
        raise FrozenManifestError("OBJECT_OWNER_SCHEMA_NOT_REGISTERED")

    plugin_registry = manifest["plugin_policy_registry"]
    if (
        plugin_registry.get("entries") != []
        or plugin_registry.get("required_plugin_ids") != []
        or plugin_registry.get("optional_plugin_ids") != []
    ):
        raise FrozenManifestError("E0_PLUGIN_REGISTRY_MUST_BE_EMPTY")

    event_entries = manifest["closed_event_registry"]["entries"]
    uow_entries = [
        entry
        for entry in event_entries
        if isinstance(entry, Mapping)
        and entry.get("event_type") == "UNIT_OF_WORK_COMMITTED"
    ]
    if len(uow_entries) != 1:
        raise FrozenManifestError("UNIT_OF_WORK_COMMITTED_EVENT_CARDINALITY")
    if (
        uow_entries[0].get("trigger_class") != "POST_COMMIT_NOTIFICATION"
        or uow_entries[0].get("same_batch_commit_receipt_reference") is not False
    ):
        raise FrozenManifestError("UNIT_OF_WORK_COMMITTED_PHASE_INVALID")

    for section_name in _DERIVED_MANIFEST_SECTION_NAMES:
        if section_name not in manifest:
            raise FrozenManifestError(f"MANIFEST_SECTION_MISSING:{section_name}")
    return digest


def load_and_verify_frozen_manifest(path: Path) -> dict[str, Any]:
    """Strictly load one previously frozen manifest and validate its digests."""

    try:
        manifest = load_json_strict(Path(path))
    except CanonicalContractError as exc:
        raise FrozenManifestError("MANIFEST_STRICT_LOAD_FAILED") from exc
    verify_frozen_manifest(manifest)
    return manifest


def freeze_or_load_manifest(
    path: Path,
    *,
    freeze_manifest: bool,
) -> tuple[dict[str, Any], str]:
    """Create the manifest only in explicit bootstrap mode, then read it back."""

    target = Path(path)
    write_status = "READ_ONLY_EXISTING"
    if freeze_manifest:
        candidate = build_canonical_manifest()
        validate_catalog_manifest(candidate)
        verify_frozen_manifest(candidate)
        write_status = write_once_json(target, candidate)
    manifest = load_and_verify_frozen_manifest(target)
    return manifest, write_status


def _relative_artifacts(
    manifest: Mapping[str, Any],
) -> dict[Path, Mapping[str, Any]]:
    artifacts: dict[Path, Mapping[str, Any]] = {
        Path("canonical_contract_manifest.v1.json"): manifest,
    }
    for registry_name in _NESTED_REGISTRY_NAMES:
        artifacts[
            Path("registries") / f"{registry_name}.registry.json"
        ] = manifest[registry_name]
    for section_name in _DERIVED_MANIFEST_SECTION_NAMES:
        artifacts[
            Path("registries") / f"{section_name}.json"
        ] = manifest[section_name]
    schema_count = 0
    for schema_id, document in schema_documents_from_manifest(manifest):
        if _SCHEMA_ID_PATTERN.fullmatch(schema_id) is None:
            raise FrozenManifestError(f"SCHEMA_ID_UNSAFE_OR_INVALID:{schema_id}")
        path = Path("schemas") / f"{schema_id}.schema.json"
        if path in artifacts:
            raise FrozenManifestError(f"BUNDLE_PATH_COLLISION:{path}")
        artifacts[path] = document
        schema_count += 1
    if schema_count != len(manifest["schema_registry"]["entries"]):
        raise FrozenManifestError("SCHEMA_DOCUMENT_COUNT_MISMATCH")
    return artifacts


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bundle_index(
    *,
    manifest: Mapping[str, Any],
    artifacts: Mapping[Path, Mapping[str, Any]],
) -> dict[str, Any]:
    file_entries = []
    for relative_path in sorted(artifacts, key=lambda item: item.as_posix()):
        payload = canonical_bytes(artifacts[relative_path]) + b"\n"
        file_entries.append(
            {
                "relative_path": relative_path.as_posix(),
                "sha256": _sha256_bytes(payload),
                "byte_length": len(payload),
            }
        )
    index: dict[str, Any] = {
        "bundle_id": "THEORY_AGENT_V2_PORTABLE_CONTRACT_BUNDLE",
        "bundle_version": str(manifest["manifest_version"]),
        "source_manifest_digest": str(manifest["manifest_digest"]),
        "canonicalization_policy": (
            "UTF8_JSON_JCS_RFC8785_SHA256_SUBSET_NO_FLOAT_TRAILING_LF"
        ),
        "file_entries": file_entries,
    }
    return self_digest(index, "bundle_index_digest")


def _existing_relative_files(output_directory: Path) -> set[Path]:
    if not output_directory.exists():
        return set()
    if not output_directory.is_dir():
        raise FrozenManifestError(
            f"BUNDLE_OUTPUT_NOT_DIRECTORY:{output_directory}"
        )
    return {
        path.relative_to(output_directory)
        for path in output_directory.rglob("*")
        if path.is_file()
    }


def materialize_contract_bundle(
    manifest: Mapping[str, Any],
    output_directory: Path,
) -> MaterializedBundle:
    """Write or verify a complete write-once portable bundle."""

    source_manifest_digest = verify_frozen_manifest(manifest)
    output = Path(output_directory)
    artifacts = _relative_artifacts(manifest)
    bundle_index = _bundle_index(manifest=manifest, artifacts=artifacts)
    artifacts_with_index = dict(artifacts)
    artifacts_with_index[Path("bundle.index.json")] = bundle_index

    expected_paths = set(artifacts_with_index)
    existing_paths = _existing_relative_files(output)
    unexpected = sorted(
        existing_paths - expected_paths,
        key=lambda item: item.as_posix(),
    )
    if unexpected:
        rendered = ",".join(path.as_posix() for path in unexpected)
        raise FrozenManifestError(f"BUNDLE_UNEXPECTED_FILES:{rendered}")

    for relative_path in sorted(
        artifacts_with_index,
        key=lambda item: item.as_posix(),
    ):
        write_once_json(output / relative_path, artifacts_with_index[relative_path])

    return MaterializedBundle(
        output_directory=output,
        source_manifest_digest=source_manifest_digest,
        bundle_index_digest=str(bundle_index["bundle_index_digest"]),
        file_count=len(artifacts_with_index),
        schema_count=len(manifest["schema_registry"]["entries"]),
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    directory = Path(root)
    if not directory.is_dir():
        raise FrozenManifestError(f"BUNDLE_TREE_MISSING:{directory}")
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def assert_byte_identical_trees(left: Path, right: Path) -> int:
    """Fail unless two materializations contain identical paths and bytes."""

    left_tree = _tree_bytes(left)
    right_tree = _tree_bytes(right)
    if left_tree.keys() != right_tree.keys():
        raise FrozenManifestError("BUNDLE_TREE_PATH_SET_MISMATCH")
    mismatched = [
        path
        for path in left_tree
        if left_tree[path] != right_tree[path]
    ]
    if mismatched:
        raise FrozenManifestError(
            f"BUNDLE_TREE_BYTE_MISMATCH:{','.join(mismatched)}"
        )
    return len(left_tree)


def verify_reproducible_materialization(
    manifest: Mapping[str, Any],
) -> int:
    """Materialize twice in isolation and compare every output byte."""

    with TemporaryDirectory(prefix="theory-agent-v2-contract-a-") as left_raw:
        with TemporaryDirectory(prefix="theory-agent-v2-contract-b-") as right_raw:
            left = Path(left_raw)
            right = Path(right_raw)
            materialize_contract_bundle(manifest, left)
            materialize_contract_bundle(manifest, right)
            return assert_byte_identical_trees(left, right)
