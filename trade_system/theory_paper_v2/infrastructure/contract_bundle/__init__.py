"""Portable materialization of the frozen Theory Agent V2 contracts."""

from .materialize import (
    DEFAULT_MANIFEST_RELATIVE_PATH,
    DEFAULT_OUTPUT_RELATIVE_PATH,
    FrozenManifestError,
    MaterializedBundle,
    assert_byte_identical_trees,
    freeze_or_load_manifest,
    load_and_verify_frozen_manifest,
    materialize_contract_bundle,
)

__all__ = [
    "DEFAULT_MANIFEST_RELATIVE_PATH",
    "DEFAULT_OUTPUT_RELATIVE_PATH",
    "FrozenManifestError",
    "MaterializedBundle",
    "assert_byte_identical_trees",
    "freeze_or_load_manifest",
    "load_and_verify_frozen_manifest",
    "materialize_contract_bundle",
]

