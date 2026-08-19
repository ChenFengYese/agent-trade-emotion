"""Pure helpers shared by the 2026-08-08 V3.2 revision contracts.

The module deliberately owns no I/O.  Bindings are durable artifact identities;
the owning Store remains responsible for resolving ``relative_ref`` and replaying
the exact physical bytes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1.0.0"
SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)


class V32AuthorizedRevisionContractError(ValueError):
    """A common closed-shape or boundary invariant failed."""


def text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32AuthorizedRevisionContractError(code)
    return value


def digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32AuthorizedRevisionContractError(code)
    return value


def integer(
    value: Any, code: str, *, minimum: int = 0, maximum: int = 9_007_199_254_740_991
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise V32AuthorizedRevisionContractError(code)
    return value


def time(value: Any, code: str) -> str:
    candidate = text(value, code)
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32AuthorizedRevisionContractError(code) from exc
    if parsed.tzinfo is None:
        raise V32AuthorizedRevisionContractError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != candidate:
        raise V32AuthorizedRevisionContractError(code)
    return canonical


def moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(time(value, code).replace("Z", "+00:00"))


def sorted_unique_texts(
    value: Any,
    code: str,
    *,
    allow_empty: bool = False,
    maximum: int = 4096,
) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32AuthorizedRevisionContractError(code)
    rows = [text(item, code) for item in value]
    if (
        (not allow_empty and not rows)
        or len(rows) > maximum
        or rows != sorted(rows)
        or len(rows) != len(set(rows))
    ):
        raise V32AuthorizedRevisionContractError(code)
    return rows


def binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != BINDING_FIELDS:
        raise V32AuthorizedRevisionContractError(code)
    relative_ref = text(value.get("relative_ref"), code)
    path = PurePosixPath(relative_ref)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise V32AuthorizedRevisionContractError(code)
    return {
        "relative_ref": relative_ref,
        "schema_id": text(value.get("schema_id"), code),
        "digest_field": text(value.get("digest_field"), code),
        "semantic_digest": digest(value.get("semantic_digest"), code),
        "physical_sha256": digest(value.get("physical_sha256"), code),
    }


def boundary() -> dict[str, Any]:
    return {
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_use": False,
        "funds_access": False,
        "portfolio_mutation": False,
        "fill_claim": False,
        "pnl_claim": False,
        "executable": False,
    }


def verify_boundary(document: Mapping[str, Any], code: str) -> None:
    if any(document.get(key) != value for key, value in boundary().items()):
        raise V32AuthorizedRevisionContractError(code)


__all__ = [
    "BINDING_FIELDS",
    "EXTERNAL_EXECUTION_AUTHORITY",
    "SCHEMA_VERSION",
    "SOURCE_SCOPE",
    "V32AuthorizedRevisionContractError",
    "binding",
    "boundary",
    "digest",
    "integer",
    "moment",
    "sorted_unique_texts",
    "text",
    "time",
    "verify_boundary",
]
