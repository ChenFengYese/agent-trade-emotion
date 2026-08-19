"""Immutable value and canonical identity primitives for the v0.2.2 kernel.

This module deliberately has no filesystem, clock, environment, network or
randomness capability.  It is the sole owner of the kernel error carrier and
of the canonical JSON/decimal rules used by :mod:`kernel`.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any, TypeAlias


KERNEL_ERROR_CODES = (
    "E_KERNEL_CONTRACT_INVALID",
    "E_KERNEL_ARGUMENT_INVALID",
    "E_KERNEL_SCHEMA_INVALID",
    "E_KERNEL_DIGEST_INVALID",
    "E_KERNEL_BINDING_INVALID",
    "E_C01_MIXED_SOURCE_KIND",
    "E_C02_SCOPE_MISMATCH",
    "E_C03_COVERAGE_SET_INVALID",
    "E_C04_BAR_CAUSALITY_INVALID",
    "E_C05_BOOK_GRID_DEDUP_INVALID",
    "E_C06_VENUE_RULE_MAPPING_INVALID",
    "E_C07_ACCOUNT_ASOF_CONFLICT",
    "E_C08_EV_STATS_INCONSISTENT",
    "E_C09_TARGET_EVIDENCE_INCOMPLETE",
    "E_C10_TARGET_ARTIFACT_ID_INVALID",
    "E_C11_OI_SEAL_INCOMPLETE",
    "E_C12_DECISION_PROOF_INVALID",
    "E_C13_POLICY_DIGEST_MISMATCH",
    "E_C14_U_RECEIPT_EVENT_FORBIDDEN",
    "E_C15_PRIORITY_TABLE_INVALID",
    "E_C16_DESCENDANT_CAUSALITY_INVALID",
    "E_C17_ARTIFACT_SCOPE_MISMATCH",
    "E_C18_ROLE_NOT_SYNTHETIC",
    "E_C19_GENERATION_CLOSURE_INVALID",
    "E_C20_SELECTOR_BINDING_MISMATCH",
    "E_C21_AUTHORITY_LINEAGE_INVALID",
)
_KERNEL_ERROR_CODE_SET = frozenset(KERNEL_ERROR_CODES)
_SAFE_INTEGER = 9_007_199_254_740_991
_DECIMAL_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DECIMAL_CONTEXT = Context(prec=34, rounding=ROUND_HALF_EVEN)

FrozenJSON: TypeAlias = Any


class KernelValidationError(ValueError):
    """The one exception carrier permitted at non-bundle kernel boundaries."""

    def __init__(self, error_code: str) -> None:
        if error_code not in _KERNEL_ERROR_CODE_SET:
            raise ValueError("invalid KernelErrorCodeV0_2_2 member")
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True, slots=True)
class FrozenMapping(Mapping[str, FrozenJSON]):
    """Insertion-order-preserving, recursively immutable JSON object."""

    _pairs: tuple[tuple[str, FrozenJSON], ...]

    def __post_init__(self) -> None:
        if not isinstance(self._pairs, tuple):
            raise TypeError("FrozenMapping pairs must be a tuple")
        seen: set[str] = set()
        for pair in self._pairs:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError("FrozenMapping pair is malformed")
            key, child = pair
            if not isinstance(key, str) or key in seen:
                raise TypeError("FrozenMapping key is invalid or duplicated")
            key.encode("utf-8")
            seen.add(key)
            _validate_frozen_child(child)

    def __getitem__(self, key: str) -> FrozenJSON:
        for candidate, value in self._pairs:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._pairs)

    def __len__(self) -> int:
        return len(self._pairs)


@dataclass(frozen=True, slots=True)
class ValidatedBundle(Mapping[str, Any]):
    status: str
    bundle: FrozenMapping
    bundle_sha256: str
    validated_as_of_us: int
    role: str

    def __post_init__(self) -> None:
        if (
            self.status != "VALID"
            or not isinstance(self.bundle, FrozenMapping)
            or not is_sha256(self.bundle_sha256)
            or not is_safe_integer(self.validated_as_of_us, nonnegative=True)
            or self.role != "SYNTHETIC"
        ):
            raise ValueError("invalid ValidatedBundleV0_2_2")

    def __getitem__(self, key: str) -> Any:
        if key not in ("status", "bundle", "bundle_sha256", "validated_as_of_us", "role"):
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(("status", "bundle", "bundle_sha256", "validated_as_of_us", "role"))

    def __len__(self) -> int:
        return 5


@dataclass(frozen=True, slots=True)
class BundleValidationFailure(Mapping[str, str]):
    status: str
    error_code: str

    def __post_init__(self) -> None:
        if self.status != "INVALID" or self.error_code not in _KERNEL_ERROR_CODE_SET:
            raise ValueError("invalid BundleValidationFailureV0_2_2")

    def __getitem__(self, key: str) -> str:
        if key not in ("status", "error_code"):
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(("status", "error_code"))

    def __len__(self) -> int:
        return 2


@dataclass(frozen=True, slots=True)
class ArtifactTuple(Mapping[str, tuple[FrozenMapping, ...]]):
    artifacts: tuple[FrozenMapping, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.artifacts, tuple) or not all(
            isinstance(item, FrozenMapping) for item in self.artifacts
        ):
            raise TypeError("invalid artifact tuple")

    def __getitem__(self, key: str) -> tuple[FrozenMapping, ...]:
        if key != "artifacts":
            raise KeyError(key)
        return self.artifacts

    def __iter__(self) -> Iterator[str]:
        return iter(("artifacts",))

    def __len__(self) -> int:
        return 1


@dataclass(frozen=True, slots=True)
class OIEndpointSelection(Mapping[str, FrozenMapping]):
    coverage_seal_artifact: FrozenMapping
    oi_now_artifact: FrozenMapping
    oi_prev_artifact: FrozenMapping

    def __post_init__(self) -> None:
        if not all(
            isinstance(item, FrozenMapping)
            for item in (
                self.coverage_seal_artifact,
                self.oi_now_artifact,
                self.oi_prev_artifact,
            )
        ):
            raise TypeError("invalid OI endpoint selection")

    def __getitem__(self, key: str) -> FrozenMapping:
        if key not in (
            "coverage_seal_artifact",
            "oi_now_artifact",
            "oi_prev_artifact",
        ):
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(
            (
                "coverage_seal_artifact",
                "oi_now_artifact",
                "oi_prev_artifact",
            )
        )

    def __len__(self) -> int:
        return 3


def is_safe_integer(value: Any, *, nonnegative: bool = False) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and (-_SAFE_INTEGER <= value <= _SAFE_INTEGER)
        and (not nonnegative or value >= 0)
    )


def _validate_frozen_child(value: Any) -> None:
    if isinstance(value, FrozenMapping):
        value.__post_init__()
        return
    if isinstance(value, tuple):
        for child in value:
            _validate_frozen_child(child)
        return
    if isinstance(value, float):
        raise TypeError("JSON float is forbidden")
    if isinstance(value, int) and not isinstance(value, bool):
        if not is_safe_integer(value):
            raise ValueError("JSON integer is outside the safe range")
        return
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            value.encode("utf-8")
        return
    raise TypeError("value is not recursively frozen JSON")


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def validate_decimal(kind: str, value: Any) -> bool:
    """Validate the closed DecimalString family without performing coercion."""

    if not isinstance(kind, str) or not isinstance(value, str):
        return False
    if _DECIMAL_PATTERN.fullmatch(value) is None or value == "-0":
        return False
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    if not number.is_finite():
        return False
    if kind in {"Price", "PositiveDecimal"}:
        return number > 0
    if kind in {"QtyBase", "Money", "Bps", "NonNegativeDecimal"}:
        return number >= 0
    return kind in {"DecimalString", "SignedDecimal"}


def parse_decimal(value: str, kind: str = "DecimalString") -> Decimal:
    if not validate_decimal(kind, value):
        raise ValueError("invalid canonical decimal")
    return Decimal(value)


def decimal_value(value: Decimal) -> str:
    """Return the unique non-exponent canonical spelling of a Decimal result."""

    with localcontext(DECIMAL_CONTEXT):
        rounded = +value
    if rounded.is_zero():
        return "0"
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    if _DECIMAL_PATTERN.fullmatch(text) is None:
        raise ValueError("decimal result is outside canonical spelling")
    return text


def decimal_sum(values: Sequence[str]) -> str:
    with localcontext(DECIMAL_CONTEXT):
        total = Decimal(0)
        for value in values:
            total += parse_decimal(value)
        return decimal_value(total)


def freeze(value: Any) -> FrozenJSON:
    if isinstance(value, FrozenMapping):
        value.__post_init__()
        return value
    if isinstance(value, Mapping):
        pairs: list[tuple[str, FrozenJSON]] = []
        seen: set[str] = set()
        for key, child in value.items():
            if not isinstance(key, str) or key in seen:
                raise TypeError("JSON object key is invalid or duplicated")
            key.encode("utf-8")
            seen.add(key)
            pairs.append((key, freeze(child)))
        return FrozenMapping(tuple(pairs))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(child) for child in value)
    if isinstance(value, float):
        raise TypeError("JSON float is forbidden")
    if isinstance(value, int) and not isinstance(value, bool):
        if not is_safe_integer(value):
            raise ValueError("JSON integer is outside the safe range")
        return value
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            value.encode("utf-8")
        return value
    raise TypeError("value is not a canonical JSON value")


def materialize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: materialize(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [materialize(child) for child in value]
    return value


def canonical_json(value: Any) -> bytes:
    """RFC8785-compatible subset frozen by the Route-B contract."""

    immutable = freeze(value)
    try:
        return json.dumps(
            materialize(immutable),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("canonical JSON validation failed") from None


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def stable_id(domain: str, preimage: Any) -> str:
    if not isinstance(domain, str) or not domain or not domain.isascii():
        raise ValueError("identity domain must be nonempty ASCII")
    return sha256_bytes(domain.encode("utf-8") + b"\x00" + canonical_json(preimage))


def exact_keys(value: Any, keys: tuple[str, ...]) -> bool:
    return isinstance(value, Mapping) and set(value) == set(keys)
