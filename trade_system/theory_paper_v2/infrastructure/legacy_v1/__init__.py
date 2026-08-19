"""Digest-bound, read-only V1 compatibility adapter."""

from .adapter import (
    LegacyAdapterError,
    LegacyCycleEnvelope,
    LegacyV1Adapter,
    legacy_tree_digest,
)

__all__ = [
    "LegacyAdapterError",
    "LegacyCycleEnvelope",
    "LegacyV1Adapter",
    "legacy_tree_digest",
]
