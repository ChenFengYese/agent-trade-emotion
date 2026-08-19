"""Compatibility exports for the package-owned V3.2 durability primitives.

The implementation lives at ``theory_paper_v2.v32_durable_json`` so domain-
independent application code does not depend on the infrastructure layer.
Existing infrastructure imports remain source-compatible through this module.
"""

from ..v32_durable_json import (
    atomic_replace_bytes,
    atomic_replace_json,
    confirm_existing_bytes,
    confirm_existing_directory,
    confirm_existing_json,
    ensure_directory_tree,
    exclusive_lock_file,
    rename_directory_noreplace_at,
    write_once_bytes,
    write_once_directory,
    write_once_json,
)


__all__ = [
    "atomic_replace_bytes",
    "atomic_replace_json",
    "confirm_existing_bytes",
    "confirm_existing_directory",
    "confirm_existing_json",
    "ensure_directory_tree",
    "exclusive_lock_file",
    "rename_directory_noreplace_at",
    "write_once_bytes",
    "write_once_directory",
    "write_once_json",
]
