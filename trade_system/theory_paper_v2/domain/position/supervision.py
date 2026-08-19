"""Offline/sleep supervision windows as risk permissions, not market views."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common import DomainError, DomainResult, ReducerStatus


class SupervisionMode(StrEnum):
    SUPERVISED = "SUPERVISED"
    UNATTENDED_PROTECTED = "UNATTENDED_PROTECTED"
    NO_NEW_RISK = "NO_NEW_RISK"


@dataclass(frozen=True, slots=True)
class SupervisionWindow:
    start_at: datetime
    end_at: datetime
    mode: SupervisionMode

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("CLOCK_TIME_INVALID")
        if self.end_at <= self.start_at:
            raise ValueError("SUPERVISION_WINDOW_OVERLAP")


@dataclass(frozen=True, slots=True)
class SupervisionContract:
    contract_id: str
    revision: int
    windows: tuple[SupervisionWindow, ...]

    def __post_init__(self) -> None:
        if not self.windows:
            raise ValueError("SUPERVISION_WINDOW_MISSING")
        ordered = sorted(self.windows, key=lambda item: item.start_at)
        if tuple(ordered) != self.windows:
            raise ValueError("SUPERVISION_WINDOW_OVERLAP")
        for prior, current in zip(ordered, ordered[1:], strict=False):
            if current.start_at < prior.end_at:
                raise ValueError("SUPERVISION_WINDOW_OVERLAP")


@dataclass(frozen=True, slots=True)
class SupervisionAssessment:
    effective_at: datetime
    mode: SupervisionMode
    resulting_permission: str
    reason_codes: tuple[str, ...]


def assess_supervision(
    contract: SupervisionContract,
    *,
    effective_at: datetime,
    protection_pass: bool | None,
    ack_freshness_pass: bool | None,
    data_freshness_pass: bool | None,
    account_consistency_pass: bool | None,
    worst_case_loss_pass: bool | None,
) -> DomainResult[SupervisionAssessment]:
    if effective_at.tzinfo is None:
        return DomainResult(
            status=ReducerStatus.UNKNOWN,
            error=DomainError(
                "CLOCK_TIME_INVALID",
                "SUPERVISION",
                "AFTER_INPUT_REPAIR",
                "effective time is not authoritative",
            ),
        )
    window = next(
        (
            item
            for item in contract.windows
            if item.start_at <= effective_at < item.end_at
        ),
        None,
    )
    if window is None:
        return DomainResult(
            status=ReducerStatus.APPLIED,
            value=SupervisionAssessment(
                effective_at,
                SupervisionMode.NO_NEW_RISK,
                "NO_NEW_RISK",
                ("SUPERVISION_WINDOW_MISSING",),
            ),
        )
    if window.mode is SupervisionMode.SUPERVISED:
        if account_consistency_pass is True and data_freshness_pass is True:
            return DomainResult(
                status=ReducerStatus.APPLIED,
                value=SupervisionAssessment(
                    effective_at,
                    SupervisionMode.SUPERVISED,
                    "NORMAL_E0",
                    ("SUPERVISED_WINDOW",),
                ),
            )
        return DomainResult(
            status=ReducerStatus.APPLIED,
            value=SupervisionAssessment(
                effective_at,
                SupervisionMode.NO_NEW_RISK,
                "NO_NEW_RISK",
                ("SUPERVISION_ACCOUNT_OR_DATA_UNPROVEN",),
            ),
        )
    if window.mode is SupervisionMode.NO_NEW_RISK:
        return DomainResult(
            status=ReducerStatus.APPLIED,
            value=SupervisionAssessment(
                effective_at,
                SupervisionMode.NO_NEW_RISK,
                "NO_NEW_RISK",
                ("FROZEN_NO_NEW_RISK_WINDOW",),
            ),
        )
    predicates = (
        protection_pass,
        ack_freshness_pass,
        data_freshness_pass,
        account_consistency_pass,
        worst_case_loss_pass,
    )
    if all(value is True for value in predicates):
        return DomainResult(
            status=ReducerStatus.APPLIED,
            value=SupervisionAssessment(
                effective_at,
                SupervisionMode.UNATTENDED_PROTECTED,
                "PREREGISTERED_PROTECTED_ONLY_E0",
                ("ALL_UNATTENDED_GATES_PASS",),
            ),
        )
    failed = tuple(
        name
        for name, value in zip(
            (
                "PROTECTION",
                "ACK_FRESHNESS",
                "DATA_FRESHNESS",
                "ACCOUNT_CONSISTENCY",
                "WORST_CASE_LOSS",
            ),
            predicates,
            strict=True,
        )
        if value is not True
    )
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=SupervisionAssessment(
            effective_at,
            SupervisionMode.NO_NEW_RISK,
            "NO_NEW_RISK",
            failed,
        ),
    )

