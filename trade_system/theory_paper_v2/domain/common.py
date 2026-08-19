"""Shared pure-domain result and authority primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar


SYSTEM_MODE = "E0_OFFLINE_COUNTERFACTUAL"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_E0"


class ReducerStatus(StrEnum):
    APPLIED = "APPLIED"
    NO_CHANGE = "NO_CHANGE"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DomainError:
    code: str
    category: str
    retryability: str
    message: str


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class DomainResult(Generic[T]):
    status: ReducerStatus
    value: T | None = None
    error: DomainError | None = None
    evaluated_event_id: str | None = None

    def __post_init__(self) -> None:
        has_value = self.value is not None
        has_error = self.error is not None
        if self.status is ReducerStatus.APPLIED and (not has_value or has_error):
            raise ValueError("APPLIED_REQUIRES_VALUE_ONLY")
        if self.status is ReducerStatus.NO_CHANGE and (has_value or has_error):
            raise ValueError("NO_CHANGE_FORBIDS_VALUE_AND_ERROR")
        if self.status in {ReducerStatus.REJECTED, ReducerStatus.UNKNOWN} and (
            has_value or not has_error
        ):
            raise ValueError("FAILED_RESULT_REQUIRES_ERROR_ONLY")


def rejected(code: str, category: str, message: str) -> DomainResult[object]:
    return DomainResult(
        status=ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category=category,
            retryability="NEVER",
            message=message,
        ),
    )


def unknown(code: str, category: str, message: str) -> DomainResult[object]:
    return DomainResult(
        status=ReducerStatus.UNKNOWN,
        error=DomainError(
            code=code,
            category=category,
            retryability="AFTER_INPUT_REPAIR",
            message=message,
        ),
    )

