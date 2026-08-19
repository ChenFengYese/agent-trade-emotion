"""Frozen theory identity contracts for the shared market-cycle core.

This module contains no file-system access.  Infrastructure is responsible for
reading raw bytes and calculating digests; the domain only decides whether an
observed manifest is one of the explicitly supported frozen packages.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


THEORY_VERSION = "3.3.1"
THEORY_REVISION = "3.3.1-agent-first-trader-candidate.1"
THEORY_MANIFEST_ALGORITHM = "SHA-256"
THEORY_MANIFEST_SIZE_BYTES = 3035
THEORY_MANIFEST_DIGEST = (
    "f34257994438dbbcc1500d09da3f8dfe6d96adaca6bf65abb1fe6499d1148061"
)
THEORY_MANIFEST_SCHEMA_ID = "agent_trade_emotion_theory_manifest"
THEORY_MANIFEST_SCHEMA_VERSION = "1.0.0"

V332_THEORY_VERSION = "3.3.2"
V332_THEORY_REVISION = "3.3.2-complete-market-analysis-candidate.3"
V332_THEORY_MANIFEST_SIZE_BYTES = 6111
V332_THEORY_MANIFEST_DIGEST = (
    "a6487a1bcad4a06c9d0c26d82f925da1754f36c435bcc2c504907967e0efdd24"
)

LEGACY_V32_REVISION = "V3.2.6-five-trap-hardening-candidate"
LEGACY_V32_SOURCE_SIZE_BYTES = 99647
LEGACY_V32_SOURCE_SHA256 = (
    "eea31863e8e32f0999d91d587113be227be32b705c799455c386660fadb01061"
)


class TheoryIdentityError(ValueError):
    """The requested or observed package is not an explicitly frozen theory."""


def _require_exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], *, context: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise TheoryIdentityError(
            f"{context} fields mismatch: missing={missing!r}, extra={extra!r}"
        )


def _require_sha256(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise TheoryIdentityError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


_SUPPORTED_THEORY_PACKAGES = {
    (THEORY_VERSION, THEORY_REVISION): (
        THEORY_MANIFEST_SIZE_BYTES,
        THEORY_MANIFEST_DIGEST,
    ),
    (V332_THEORY_VERSION, V332_THEORY_REVISION): (
        V332_THEORY_MANIFEST_SIZE_BYTES,
        V332_THEORY_MANIFEST_DIGEST,
    ),
}


@dataclass(frozen=True, slots=True)
class TheoryIdentity:
    """Human-readable version plus the content-addressed package authority."""

    theory_version: str
    theory_revision: str
    manifest_algorithm: str
    manifest_size_bytes: int
    manifest_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.theory_version, str) or not self.theory_version:
            raise TheoryIdentityError("theory_version must be a non-empty string")
        if not isinstance(self.theory_revision, str) or not self.theory_revision:
            raise TheoryIdentityError("theory_revision must be a non-empty string")
        if self.manifest_algorithm != THEORY_MANIFEST_ALGORITHM:
            raise TheoryIdentityError("manifest_algorithm must be SHA-256")
        if type(self.manifest_size_bytes) is not int or self.manifest_size_bytes <= 0:
            raise TheoryIdentityError("manifest_size_bytes must be a positive integer")
        _require_sha256(self.manifest_digest, field_name="manifest_digest")
        try:
            expected_size, expected_digest = _SUPPORTED_THEORY_PACKAGES[
                (self.theory_version, self.theory_revision)
            ]
        except KeyError as exc:
            raise TheoryIdentityError(
                "theory version/revision does not identify a supported frozen package"
            ) from exc
        if self.manifest_size_bytes != expected_size:
            raise TheoryIdentityError("manifest size does not match the frozen package")
        if self.manifest_digest != expected_digest:
            raise TheoryIdentityError("manifest digest does not match the frozen package")

    @property
    def identity_key(self) -> str:
        return f"sha256:{self.manifest_digest}"

    def to_dict(self) -> dict[str, object]:
        return {
            "theory_version": self.theory_version,
            "theory_revision": self.theory_revision,
            "manifest_algorithm": self.manifest_algorithm,
            "manifest_size_bytes": self.manifest_size_bytes,
            "manifest_digest": self.manifest_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TheoryIdentity":
        if not isinstance(value, Mapping):
            raise TheoryIdentityError("theory_identity must be an object")
        _require_exact_keys(
            value,
            frozenset(
                {
                    "theory_version",
                    "theory_revision",
                    "manifest_algorithm",
                    "manifest_size_bytes",
                    "manifest_digest",
                }
            ),
            context="theory_identity",
        )
        for field_name in (
            "theory_version",
            "theory_revision",
            "manifest_algorithm",
            "manifest_digest",
        ):
            if not isinstance(value[field_name], str):
                raise TheoryIdentityError(f"{field_name} must be a string")
        if type(value["manifest_size_bytes"]) is not int:
            raise TheoryIdentityError("manifest_size_bytes must be an integer")
        return cls(
            theory_version=value["theory_version"],
            theory_revision=value["theory_revision"],
            manifest_algorithm=value["manifest_algorithm"],
            manifest_size_bytes=value["manifest_size_bytes"],
            manifest_digest=value["manifest_digest"],
        )


CURRENT_THEORY_IDENTITY = TheoryIdentity(
    theory_version=THEORY_VERSION,
    theory_revision=THEORY_REVISION,
    manifest_algorithm=THEORY_MANIFEST_ALGORITHM,
    manifest_size_bytes=THEORY_MANIFEST_SIZE_BYTES,
    manifest_digest=THEORY_MANIFEST_DIGEST,
)

V332_THEORY_IDENTITY = TheoryIdentity(
    theory_version=V332_THEORY_VERSION,
    theory_revision=V332_THEORY_REVISION,
    manifest_algorithm=THEORY_MANIFEST_ALGORITHM,
    manifest_size_bytes=V332_THEORY_MANIFEST_SIZE_BYTES,
    manifest_digest=V332_THEORY_MANIFEST_DIGEST,
)


def require_supported_theory_identity(identity: TheoryIdentity) -> TheoryIdentity:
    """Return *identity* only when it is one of the exact frozen packages."""

    if not isinstance(identity, TheoryIdentity) or identity not in {
        CURRENT_THEORY_IDENTITY,
        V332_THEORY_IDENTITY,
    }:
        raise TheoryIdentityError(
            "market-cycle artifacts must bind an explicitly supported theory identity"
        )
    return identity


def require_current_theory_identity(identity: TheoryIdentity) -> TheoryIdentity:
    """Compatibility guard for callers still pinned to frozen V3.3.1."""

    if identity != CURRENT_THEORY_IDENTITY:
        raise TheoryIdentityError("market-cycle artifacts must bind the frozen V3.3.1 identity")
    return identity


def validate_manifest_contract(
    manifest: Mapping[str, Any],
    *,
    raw_size_bytes: int,
    raw_sha256: str,
    expected: TheoryIdentity = CURRENT_THEORY_IDENTITY,
) -> None:
    """Validate manifest identity and its closed document index without doing IO.

    Infrastructure must independently reject symlinks, unsafe paths, extra
    Markdown, and file size/digest mismatches before returning a verified
    package.  This function prevents a structurally different manifest from
    being accepted under the frozen raw-byte digest.
    """

    identity = require_supported_theory_identity(expected)
    if type(raw_size_bytes) is not int or raw_size_bytes != identity.manifest_size_bytes:
        raise TheoryIdentityError("raw manifest size does not match the frozen package")
    if _require_sha256(raw_sha256, field_name="raw_sha256") != identity.manifest_digest:
        raise TheoryIdentityError("raw manifest digest does not match the frozen package")
    if not isinstance(manifest, Mapping):
        raise TheoryIdentityError("manifest must be an object")
    if manifest.get("schema_id") != THEORY_MANIFEST_SCHEMA_ID:
        raise TheoryIdentityError("unexpected manifest schema_id")
    if manifest.get("schema_version") != THEORY_MANIFEST_SCHEMA_VERSION:
        raise TheoryIdentityError("unexpected manifest schema_version")
    if manifest.get("theory_version") != identity.theory_version:
        raise TheoryIdentityError("manifest theory_version mismatch")
    if manifest.get("theory_revision") != identity.theory_revision:
        raise TheoryIdentityError("manifest theory_revision mismatch")
    if manifest.get("digest_algorithm") != THEORY_MANIFEST_ALGORITHM:
        raise TheoryIdentityError("manifest digest_algorithm mismatch")

    document_count = manifest.get("document_count")
    if type(document_count) is not int or document_count <= 0:
        raise TheoryIdentityError("manifest document_count must be a positive integer")
    documents = manifest.get("documents")
    if not isinstance(documents, list) or len(documents) != document_count:
        raise TheoryIdentityError("documents must match manifest document_count")
    expected_orders = list(range(document_count))
    actual_orders = [document.get("order") for document in documents if isinstance(document, Mapping)]
    if len(actual_orders) != document_count or actual_orders != expected_orders:
        raise TheoryIdentityError("manifest document order must be contiguous from zero")
    paths = [document.get("path") for document in documents if isinstance(document, Mapping)]
    if (
        len(paths) != document_count
        or not all(isinstance(path, str) for path in paths)
        or len(set(paths)) != document_count
        or paths[0] != "README.md"
    ):
        raise TheoryIdentityError("manifest paths must be unique and start with README.md")
    for index, document in enumerate(documents):
        if not isinstance(document, Mapping):
            raise TheoryIdentityError(f"documents[{index}] must be an object")
        path = document.get("path")
        size = document.get("size_bytes")
        digest = document.get("sha256")
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise TheoryIdentityError(f"documents[{index}].path is unsafe")
        if type(size) is not int or size <= 0:
            raise TheoryIdentityError(f"documents[{index}].size_bytes must be positive")
        _require_sha256(digest, field_name=f"documents[{index}].sha256")

    policy = manifest.get("manifest_digest_policy")
    if not isinstance(policy, Mapping):
        raise TheoryIdentityError("manifest_digest_policy is required")
    if policy.get("scope") != "EXACT_MANIFEST_JSON_BYTES":
        raise TheoryIdentityError("manifest digest must cover exact raw JSON bytes")
    if policy.get("self_digest_embedded") is not False:
        raise TheoryIdentityError("manifest must not embed a self-referential digest")

    boundary = manifest.get("authority_boundary")
    if not isinstance(boundary, Mapping):
        raise TheoryIdentityError("authority_boundary is required")
    for denied in ("runtime_implemented", "market_evaluated", "executable", "paper_authority", "live_authority"):
        if boundary.get(denied) is not False:
            raise TheoryIdentityError(f"frozen manifest must keep {denied}=false")

    if identity == CURRENT_THEORY_IDENTITY:
        if document_count != 8:
            raise TheoryIdentityError("the frozen V3.3.1 manifest must bind eight documents")
        legacy = manifest.get("legacy_runtime_compatibility")
        if not isinstance(legacy, Mapping):
            raise TheoryIdentityError("legacy_runtime_compatibility is required")
        if legacy.get("status") != "NOT_COMPATIBLE_READ_ONLY_LEGACY_ROUTE":
            raise TheoryIdentityError("legacy runtime must remain incompatible and read-only")
        if legacy.get("size_bytes") != LEGACY_V32_SOURCE_SIZE_BYTES:
            raise TheoryIdentityError("legacy V3.2.6 size mismatch")
        if legacy.get("sha256") != LEGACY_V32_SOURCE_SHA256:
            raise TheoryIdentityError("legacy V3.2.6 digest mismatch")
    else:
        if document_count != 9:
            raise TheoryIdentityError("the frozen V3.3.2 manifest must bind nine documents")
        predecessor = manifest.get("frozen_predecessor")
        if not isinstance(predecessor, Mapping):
            raise TheoryIdentityError("frozen_predecessor is required")
        if (
            predecessor.get("theory_version") != THEORY_VERSION
            or predecessor.get("status") != "READ_ONLY_NOT_MODIFIED"
            or predecessor.get("manifest_sha256") != THEORY_MANIFEST_DIGEST
        ):
            raise TheoryIdentityError("V3.3.2 frozen predecessor identity mismatch")
