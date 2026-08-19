"""Strict file-system loader for an explicitly selected frozen theory package.

The loader verifies raw bytes before it returns any content.  It deliberately
returns the README and every individually named fragment; building an Agent
packet belongs to the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from types import MappingProxyType
from typing import Any, Mapping

from ...domain.contracts.canonical import CanonicalContractError, loads_json_strict
from ...domain.market_cycle.theory import (
    CURRENT_THEORY_IDENTITY,
    TheoryIdentity,
    TheoryIdentityError,
    V332_THEORY_IDENTITY,
    require_supported_theory_identity,
    validate_manifest_contract,
)


_MANIFEST_NAME = "MANIFEST.json"
_README_NAME = "README.md"
_NON_HOT_PATH_ROLES = frozenset({"maintenance_only"})


class TheoryPackageError(ValueError):
    """The package on disk does not exactly match its expected identity."""


@dataclass(frozen=True, slots=True)
class VerifiedTheoryPackage:
    """All verified content plus the bounded Agent hot-path projection."""

    identity: TheoryIdentity
    manifest_raw_bytes: bytes
    manifest: Mapping[str, Any]
    readme: str
    fragments: Mapping[str, str]
    hot_path_fragments: Mapping[str, str]
    ordered_paths: tuple[str, ...]

    def fragment(self, name: str) -> str:
        """Return one verified owner document by its manifest-relative name."""

        try:
            return self.fragments[name]
        except KeyError as exc:
            raise TheoryPackageError(f"THEORY_FRAGMENT_UNKNOWN:{name}") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_document_path(value: object, *, index: int) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise TheoryPackageError(f"THEORY_DOCUMENT_PATH_UNSAFE:{index}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or value != relative.as_posix():
        raise TheoryPackageError(f"THEORY_DOCUMENT_PATH_UNSAFE:{index}")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise TheoryPackageError(f"THEORY_DOCUMENT_PATH_UNSAFE:{index}")
    if any(":" in part for part in relative.parts):
        raise TheoryPackageError(f"THEORY_DOCUMENT_PATH_UNSAFE:{index}")
    return value


def _assert_no_symlink_chain(package_directory: Path, relative_path: str) -> Path:
    candidate = package_directory
    for part in PurePosixPath(relative_path).parts:
        candidate = candidate / part
        try:
            metadata = candidate.lstat()
        except FileNotFoundError as exc:
            raise TheoryPackageError(
                f"THEORY_DOCUMENT_MISSING:{relative_path}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise TheoryPackageError(f"THEORY_DOCUMENT_SYMLINK:{relative_path}")
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise TheoryPackageError(f"THEORY_DOCUMENT_NOT_REGULAR:{relative_path}")
    return candidate


def _markdown_paths_and_reject_symlinks(package_directory: Path) -> set[str]:
    markdown_paths: set[str] = set()
    for root, directory_names, file_names in os.walk(
        package_directory, followlinks=False
    ):
        root_path = Path(root)
        for name in tuple(directory_names) + tuple(file_names):
            candidate = root_path / name
            if candidate.is_symlink():
                relative = candidate.relative_to(package_directory).as_posix()
                raise TheoryPackageError(f"THEORY_PACKAGE_SYMLINK:{relative}")
        for name in file_names:
            candidate = root_path / name
            if candidate.suffix.lower() == ".md":
                markdown_paths.add(
                    candidate.relative_to(package_directory).as_posix()
                )
    return markdown_paths


def _decode_document(raw: bytes, *, relative_path: str) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise TheoryPackageError(f"THEORY_DOCUMENT_BOM_FORBIDDEN:{relative_path}")
    if b"\r" in raw:
        raise TheoryPackageError(f"THEORY_DOCUMENT_NON_LF_LINE_ENDING:{relative_path}")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TheoryPackageError(
            f"THEORY_DOCUMENT_UTF8_INVALID:{relative_path}"
        ) from exc


def _validate_manifest_policy(
    manifest: Mapping[str, Any], *, expected: TheoryIdentity
) -> None:
    expected_status = {
        CURRENT_THEORY_IDENTITY: "FROZEN_VERSION_CANDIDATE",
        V332_THEORY_IDENTITY: (
            "FROZEN_THEORY_REVIEW_CANDIDATE_USER_REVIEW_REQUIRED_NON_EXECUTABLE"
        ),
    }[expected]
    if manifest.get("status") != expected_status:
        raise TheoryPackageError("THEORY_MANIFEST_STATUS_INVALID")
    if manifest.get("entrypoint") != _README_NAME:
        raise TheoryPackageError("THEORY_MANIFEST_ENTRYPOINT_INVALID")
    if manifest.get("encoding") != "UTF-8_STRICT_NO_BOM":
        raise TheoryPackageError("THEORY_MANIFEST_ENCODING_INVALID")
    if manifest.get("line_endings") != "LF":
        raise TheoryPackageError("THEORY_MANIFEST_LINE_ENDINGS_INVALID")

    policy = manifest.get("path_policy")
    if not isinstance(policy, Mapping):
        raise TheoryPackageError("THEORY_MANIFEST_PATH_POLICY_MISSING")
    required_policy = {
        "scope": "documents[].path",
        "base_directory": "MANIFEST_PARENT",
        "allow_absolute_paths": False,
        "allow_dot_segments": False,
        "allow_symlinks": False,
        "allow_unlisted_markdown": False,
        "verify_raw_bytes_without_normalization": True,
    }
    if dict(policy) != required_policy:
        raise TheoryPackageError("THEORY_MANIFEST_PATH_POLICY_INVALID")


def load_theory_package(
    package_directory: Path | str, *, expected: TheoryIdentity
) -> VerifiedTheoryPackage:
    """Load one exact frozen package without consulting mutable current pointers."""

    try:
        identity = require_supported_theory_identity(expected)
    except TheoryIdentityError as exc:
        raise TheoryPackageError("THEORY_IDENTITY_UNSUPPORTED") from exc

    package_path = Path(package_directory)
    if package_path.is_symlink() or not package_path.is_dir():
        raise TheoryPackageError("THEORY_PACKAGE_DIRECTORY_INVALID")

    manifest_path = package_path / _MANIFEST_NAME
    try:
        manifest_metadata = manifest_path.lstat()
    except FileNotFoundError as exc:
        raise TheoryPackageError("THEORY_MANIFEST_MISSING") from exc
    if not stat.S_ISREG(manifest_metadata.st_mode):
        raise TheoryPackageError("THEORY_MANIFEST_NOT_REGULAR")

    manifest_raw = manifest_path.read_bytes()
    manifest_digest = _sha256(manifest_raw)
    if len(manifest_raw) != identity.manifest_size_bytes:
        raise TheoryPackageError("THEORY_MANIFEST_SIZE_MISMATCH")
    if manifest_digest != identity.manifest_digest:
        raise TheoryPackageError("THEORY_MANIFEST_DIGEST_MISMATCH")

    try:
        manifest = loads_json_strict(manifest_raw)
        validate_manifest_contract(
            manifest,
            raw_size_bytes=len(manifest_raw),
            raw_sha256=manifest_digest,
            expected=identity,
        )
    except (CanonicalContractError, TheoryIdentityError) as exc:
        raise TheoryPackageError("THEORY_MANIFEST_CONTRACT_INVALID") from exc
    _validate_manifest_policy(manifest, expected=identity)

    documents = manifest["documents"]
    if not isinstance(documents, list):
        raise TheoryPackageError("THEORY_MANIFEST_DOCUMENTS_INVALID")

    ordered_paths: list[str] = []
    seen_paths: set[str] = set()
    verified_text: dict[str, str] = {}
    for index, binding in enumerate(documents):
        if not isinstance(binding, Mapping) or binding.get("order") != index:
            raise TheoryPackageError(f"THEORY_DOCUMENT_ORDER_INVALID:{index}")
        relative_path = _safe_document_path(binding.get("path"), index=index)
        if relative_path in seen_paths:
            raise TheoryPackageError(f"THEORY_DOCUMENT_PATH_DUPLICATE:{relative_path}")
        seen_paths.add(relative_path)
        ordered_paths.append(relative_path)

        target = _assert_no_symlink_chain(package_path, relative_path)
        raw = target.read_bytes()
        if len(raw) != binding.get("size_bytes"):
            raise TheoryPackageError(f"THEORY_DOCUMENT_SIZE_MISMATCH:{relative_path}")
        if _sha256(raw) != binding.get("sha256"):
            raise TheoryPackageError(f"THEORY_DOCUMENT_DIGEST_MISMATCH:{relative_path}")
        verified_text[relative_path] = _decode_document(
            raw, relative_path=relative_path
        )

    if (
        tuple(ordered_paths[:1]) != (_README_NAME,)
        or len(ordered_paths) != manifest["document_count"]
    ):
        raise TheoryPackageError("THEORY_DOCUMENT_SET_INVALID")
    markdown_paths = _markdown_paths_and_reject_symlinks(package_path)
    if markdown_paths != seen_paths:
        extras = sorted(markdown_paths - seen_paths)
        missing = sorted(seen_paths - markdown_paths)
        raise TheoryPackageError(
            f"THEORY_MARKDOWN_SET_MISMATCH:extra={extras!r}:missing={missing!r}"
        )

    fragments = {path: verified_text[path] for path in ordered_paths[1:]}
    hot_path_fragments: dict[str, str] = {}
    for index, binding in enumerate(documents):
        role = binding.get("role")
        if not isinstance(role, str) or not role:
            raise TheoryPackageError(f"THEORY_DOCUMENT_ROLE_INVALID:{index}")
        path = ordered_paths[index]
        if role not in _NON_HOT_PATH_ROLES:
            hot_path_fragments[path] = verified_text[path]
    return VerifiedTheoryPackage(
        identity=identity,
        manifest_raw_bytes=manifest_raw,
        manifest=MappingProxyType(dict(manifest)),
        readme=verified_text[_README_NAME],
        fragments=MappingProxyType(fragments),
        hot_path_fragments=MappingProxyType(hot_path_fragments),
        ordered_paths=tuple(ordered_paths),
    )


@dataclass(frozen=True, slots=True)
class FileTheoryPackageLoader:
    """Static adapter suitable for a ``TheoryPackagePort`` composition."""

    package_directory: Path

    def __init__(self, package_directory: Path | str) -> None:
        object.__setattr__(self, "package_directory", Path(package_directory))

    def load(self, expected: TheoryIdentity) -> VerifiedTheoryPackage:
        return load_theory_package(self.package_directory, expected=expected)


__all__ = [
    "FileTheoryPackageLoader",
    "TheoryPackageError",
    "VerifiedTheoryPackage",
    "load_theory_package",
]
