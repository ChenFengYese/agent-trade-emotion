"""Canonical contract primitives for the Theory Agent V2 E0 boundary."""

from .canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    loads_json_strict,
    self_digest,
    verify_self_digest,
    write_once_json,
)

__all__ = [
    "CanonicalContractError",
    "canonical_bytes",
    "canonical_digest",
    "load_json_strict",
    "loads_json_strict",
    "self_digest",
    "verify_self_digest",
    "write_once_json",
]
