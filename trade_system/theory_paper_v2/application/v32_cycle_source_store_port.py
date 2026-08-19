"""Application-owned persistence port for V3.2 source artifacts."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class V32CycleSourcePersistenceError(ValueError):
    """A source-artifact persistence boundary failed closed."""


class V32CycleSourceStorePort(Protocol):
    def write_raw(
        self, *, relative_ref: str, payload: bytes
    ) -> Mapping[str, str]: ...

    def artifact_exists(self, *, relative_ref: str) -> bool: ...

    def read_raw(
        self, *, relative_ref: str, expected_sha256: str | None = None
    ) -> bytes: ...

    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
        expected_physical_sha256: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...


__all__ = [
    "V32CycleSourcePersistenceError",
    "V32CycleSourceStorePort",
]
