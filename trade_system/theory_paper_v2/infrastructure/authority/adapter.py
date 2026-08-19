"""Fail-closed adapter for explicit E0 authority and trusted time.

There is deliberately no call to ``datetime.now`` or an operating-system clock.
The caller supplies an immutable trusted-time input and the adapter binds that
exact timestamp to the run, manifest, authorization envelope, and decision
session expected by the application.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ...domain.contracts.canonical import canonical_digest


class AuthorityAdapterError(ValueError):
    pass


class ClockSourceKind(StrEnum):
    FROZEN_LOCAL_AUTHORITY = "FROZEN_LOCAL_AUTHORITY"
    PUBLIC_OFFICIAL_TIME = "PUBLIC_OFFICIAL_TIME"


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MUTABLE_ALIASES = {"current", "latest"}


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise AuthorityAdapterError("CLOCK_TIME_INVALID")


def _require_explicit_id(value: str) -> None:
    if not value or value.casefold() in _MUTABLE_ALIASES:
        raise AuthorityAdapterError("AUTHORITY_STATUS_MISMATCH")


@dataclass(frozen=True, slots=True)
class TrustedTimestampInput:
    timestamp: datetime
    source_id: str
    source_kind: ClockSourceKind
    source_available_at: datetime
    source_committed_at: datetime
    source_commit_receipt_digest: str
    source_commit_receipt_valid: bool
    authoritative: bool

    def __post_init__(self) -> None:
        for value in (
            self.timestamp,
            self.source_available_at,
            self.source_committed_at,
        ):
            _require_utc(value)
        if (
            not self.source_id
            or _SHA256.fullmatch(self.source_commit_receipt_digest) is None
        ):
            raise AuthorityAdapterError("CLOCK_UNTRUSTED")


@dataclass(frozen=True, slots=True)
class AuthorityExpectation:
    offline_run_id: str
    runtime_id: str
    manifest_id: str
    authorization_envelope_id: str
    decision_session_id: str

    def __post_init__(self) -> None:
        for value in (
            self.offline_run_id,
            self.runtime_id,
            self.manifest_id,
            self.authorization_envelope_id,
            self.decision_session_id,
        ):
            _require_explicit_id(value)


@dataclass(frozen=True, slots=True)
class E0AuthorityReceipt:
    authority_receipt_id: str
    offline_run_id: str
    runtime_id: str
    manifest_id: str
    authorization_envelope_id: str
    decision_session_id: str
    decision_cutoff: datetime
    issued_at: datetime
    clock_source_id: str
    clock_source_kind: ClockSourceKind
    clock_source_commit_receipt_digest: str
    paper_action_authority: str
    live_action_authority: str
    system_mode: str
    external_execution_authority: str
    executable: bool
    receipt_digest: str

    def __post_init__(self) -> None:
        for value in (self.decision_cutoff, self.issued_at):
            _require_utc(value)
        for value in (
            self.authority_receipt_id,
            self.offline_run_id,
            self.runtime_id,
            self.manifest_id,
            self.authorization_envelope_id,
            self.decision_session_id,
            self.clock_source_id,
        ):
            _require_explicit_id(value)
        if (
            _SHA256.fullmatch(self.clock_source_commit_receipt_digest) is None
            or _SHA256.fullmatch(self.receipt_digest) is None
        ):
            raise AuthorityAdapterError("AUTHORITY_STATUS_MISMATCH")


def _receipt_payload(receipt: E0AuthorityReceipt) -> dict[str, object]:
    return {
        "authority_receipt_id": receipt.authority_receipt_id,
        "offline_run_id": receipt.offline_run_id,
        "runtime_id": receipt.runtime_id,
        "manifest_id": receipt.manifest_id,
        "authorization_envelope_id": receipt.authorization_envelope_id,
        "decision_session_id": receipt.decision_session_id,
        "decision_cutoff": receipt.decision_cutoff.isoformat().replace(
            "+00:00", "Z"
        ),
        "issued_at": receipt.issued_at.isoformat().replace("+00:00", "Z"),
        "clock_source_id": receipt.clock_source_id,
        "clock_source_kind": receipt.clock_source_kind.value,
        "clock_source_commit_receipt_digest": (
            receipt.clock_source_commit_receipt_digest
        ),
        "paper_action_authority": receipt.paper_action_authority,
        "live_action_authority": receipt.live_action_authority,
        "system_mode": receipt.system_mode,
        "external_execution_authority": receipt.external_execution_authority,
        "executable": receipt.executable,
    }


def build_e0_authority_receipt(
    *,
    authority_receipt_id: str,
    expectation: AuthorityExpectation,
    decision_cutoff: datetime,
    issued_at: datetime,
    trusted_time: TrustedTimestampInput,
) -> E0AuthorityReceipt:
    """Create a digest-bound E0 receipt from explicit caller-supplied values."""

    receipt = E0AuthorityReceipt(
        authority_receipt_id=authority_receipt_id,
        offline_run_id=expectation.offline_run_id,
        runtime_id=expectation.runtime_id,
        manifest_id=expectation.manifest_id,
        authorization_envelope_id=expectation.authorization_envelope_id,
        decision_session_id=expectation.decision_session_id,
        decision_cutoff=decision_cutoff,
        issued_at=issued_at,
        clock_source_id=trusted_time.source_id,
        clock_source_kind=trusted_time.source_kind,
        clock_source_commit_receipt_digest=(
            trusted_time.source_commit_receipt_digest
        ),
        paper_action_authority="NONE",
        live_action_authority="NONE",
        system_mode=SYSTEM_MODE,
        external_execution_authority=EXTERNAL_EXECUTION_AUTHORITY,
        executable=False,
        receipt_digest="0" * 64,
    )
    return replace(receipt, receipt_digest=canonical_digest(_receipt_payload(receipt)))


@dataclass(frozen=True, slots=True)
class ValidatedE0Authority:
    authority_receipt_id: str
    decision_cutoff: datetime
    offline_run_id: str
    runtime_id: str
    manifest_id: str
    authorization_envelope_id: str
    decision_session_id: str
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False


class E0AuthorityAdapter:
    """Validate one authority receipt against one explicit trusted clock."""

    def validate(
        self,
        *,
        expectation: AuthorityExpectation,
        receipt: E0AuthorityReceipt,
        trusted_time: TrustedTimestampInput,
    ) -> ValidatedE0Authority:
        expected_values = (
            expectation.offline_run_id,
            expectation.runtime_id,
            expectation.manifest_id,
            expectation.authorization_envelope_id,
            expectation.decision_session_id,
        )
        supplied_values = (
            receipt.offline_run_id,
            receipt.runtime_id,
            receipt.manifest_id,
            receipt.authorization_envelope_id,
            receipt.decision_session_id,
        )
        if supplied_values != expected_values:
            raise AuthorityAdapterError("AUTHORITY_STATUS_MISMATCH")
        if (
            receipt.system_mode != SYSTEM_MODE
            or receipt.external_execution_authority
            != EXTERNAL_EXECUTION_AUTHORITY
            or receipt.executable
            or receipt.paper_action_authority != "NONE"
            or receipt.live_action_authority != "NONE"
        ):
            raise AuthorityAdapterError("E0_ACTION_AUTHORITY_NONE")
        if canonical_digest(_receipt_payload(receipt)) != receipt.receipt_digest:
            raise AuthorityAdapterError("AUTHORITY_STATUS_MISMATCH")
        if (
            not trusted_time.authoritative
            or not trusted_time.source_commit_receipt_valid
            or trusted_time.source_id != receipt.clock_source_id
            or trusted_time.source_kind is not receipt.clock_source_kind
            or trusted_time.source_commit_receipt_digest
            != receipt.clock_source_commit_receipt_digest
            or trusted_time.timestamp != receipt.decision_cutoff
            or trusted_time.source_available_at
            > trusted_time.source_committed_at
            or trusted_time.source_available_at > receipt.decision_cutoff
            or trusted_time.source_committed_at > receipt.decision_cutoff
            or receipt.issued_at > receipt.decision_cutoff
        ):
            raise AuthorityAdapterError("CLOCK_UNTRUSTED")
        return ValidatedE0Authority(
            authority_receipt_id=receipt.authority_receipt_id,
            decision_cutoff=receipt.decision_cutoff,
            offline_run_id=receipt.offline_run_id,
            runtime_id=receipt.runtime_id,
            manifest_id=receipt.manifest_id,
            authorization_envelope_id=receipt.authorization_envelope_id,
            decision_session_id=receipt.decision_session_id,
        )


class E0ExternalExecutionDenyAdapter:
    """Explicitly deny every paper or live dispatch in E0."""

    @staticmethod
    def submit_paper(_: object) -> None:
        raise AuthorityAdapterError("EXTERNAL_EXECUTION_FORBIDDEN_E0")

    @staticmethod
    def submit_live(_: object) -> None:
        raise AuthorityAdapterError("EXTERNAL_EXECUTION_FORBIDDEN_E0")
