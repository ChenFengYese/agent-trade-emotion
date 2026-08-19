"""Strict canonical JSON, digest, and write-once primitives.

The V2 contract deliberately accepts a smaller value domain than general JSON:
binary floating-point values are forbidden and Decimal values are serialized as
canonical decimal strings.  This keeps financial values out of the JSON number
model while retaining deterministic RFC-8785-compatible bytes for the admitted
types.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


class CanonicalContractError(ValueError):
    """A fail-closed canonical-contract violation."""


class _DuplicateKey(ValueError):
    pass


def _reject_float(_: str) -> None:
    raise CanonicalContractError("BINARY_FLOAT_FORBIDDEN")


def _reject_constant(_: str) -> None:
    raise CanonicalContractError("NONFINITE_NUMBER_FORBIDDEN")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def loads_json_strict(raw: str | bytes) -> dict[str, Any]:
    """Load one JSON object, rejecting duplicates and all binary floats."""

    if isinstance(raw, bytes):
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonicalContractError("JSON_UTF8_INVALID") from exc
    elif isinstance(raw, str):
        source = raw
    else:
        raise CanonicalContractError("JSON_INPUT_NOT_BYTES_OR_TEXT")
    try:
        value = json.loads(
            source,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (_DuplicateKey, UnicodeError, json.JSONDecodeError) as exc:
        raise CanonicalContractError("JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise CanonicalContractError("JSON_ROOT_NOT_OBJECT")
    _normalize(value)
    return value


def load_json_strict(path: Path) -> dict[str, Any]:
    """Load one UTF-8 JSON file through :func:`loads_json_strict`."""

    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise CanonicalContractError(f"JSON_FILE_MISSING:{path}") from exc
    try:
        return loads_json_strict(raw)
    except CanonicalContractError as exc:
        raise CanonicalContractError(f"JSON_INVALID:{path}:{exc}") from exc


def canonical_decimal(value: Decimal) -> str:
    """Return a finite, non-exponent canonical base-10 decimal string."""

    if not value.is_finite():
        raise CanonicalContractError("NONFINITE_DECIMAL_FORBIDDEN")
    if value == 0:
        return "0"
    normalized = value.normalize()
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered == "-0":
        return "0"
    if _DECIMAL_RE.fullmatch(rendered) is None:
        raise CanonicalContractError("DECIMAL_NOT_CANONICAL")
    return rendered


def _utf16_sort_key(value: str) -> bytes:
    # RFC 8785/ECMAScript property sorting is based on UTF-16 code units.
    return value.encode("utf-16be", "surrogatepass")


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, float):
        raise CanonicalContractError("BINARY_FLOAT_FORBIDDEN")
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise CanonicalContractError("INTEGER_OUTSIDE_IJSON_SAFE_RANGE")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalContractError("JSON_OBJECT_KEY_NOT_STRING")
        normalized: dict[str, Any] = {}
        for key in sorted(value, key=_utf16_sort_key):
            normalized[key] = _normalize(value[key])
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise CanonicalContractError(f"JSON_VALUE_TYPE_FORBIDDEN:{type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 bytes for the admitted deterministic JSON subset."""

    normalized = _normalize(value)
    try:
        return json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalContractError("CANONICAL_JSON_ENCODING_FAILED") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def self_digest(value: Mapping[str, Any], digest_field: str) -> dict[str, Any]:
    """Return a copy with exactly one omit-then-insert SHA-256 self digest."""

    if not isinstance(digest_field, str) or not digest_field:
        raise CanonicalContractError("SELF_DIGEST_FIELD_INVALID")
    candidate = dict(value)
    candidate.pop(digest_field, None)
    candidate[digest_field] = canonical_digest(candidate)
    return candidate


def verify_self_digest(value: Mapping[str, Any], digest_field: str) -> str:
    supplied = value.get(digest_field)
    if not isinstance(supplied, str) or re.fullmatch(r"[0-9a-f]{64}", supplied) is None:
        raise CanonicalContractError("SELF_DIGEST_MISSING_OR_INVALID")
    candidate = dict(value)
    candidate.pop(digest_field, None)
    if canonical_digest(candidate) != supplied:
        raise CanonicalContractError("SELF_DIGEST_MISMATCH")
    return supplied


def write_once_json(path: Path, value: Mapping[str, Any]) -> str:
    """Create canonical JSON once, or verify that an existing file is identical."""

    target = Path(path)
    payload = canonical_bytes(dict(value)) + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or target.read_bytes() != payload:
            raise CanonicalContractError(f"WRITE_ONCE_CONFLICT:{target}")
        return "EXISTING_IDENTICAL"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        if target.is_file() and target.read_bytes() == payload:
            return "EXISTING_IDENTICAL"
        raise CanonicalContractError(f"WRITE_ONCE_RACE:{target}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return "CREATED"
