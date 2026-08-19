"""Strict, owner-bound genesis for a new strategic episode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ..common import (
    EXTERNAL_EXECUTION_AUTHORITY,
    SYSTEM_MODE,
    DomainError,
    DomainResult,
    ReducerStatus,
)
from ..contracts.canonical import canonical_digest
from ..time_authority import ReviewClock
from .model import ExposureStatus, StrategicEpisode, StrategicStatus


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class TrustedReceiptAssertion:
    receipt_ref: str
    owner_module: str
    causal_cutoff: datetime
    verdict: str

    def __post_init__(self) -> None:
        if not self.receipt_ref or self.causal_cutoff.tzinfo is None:
            raise ValueError("GENESIS_RECEIPT_MISSING")


@dataclass(frozen=True, slots=True)
class OpenEpisodeCommand:
    request_id: str
    expected_head_digest: str | None
    episode_id: str
    instrument_id: str
    direction: str
    decision_cutoff: datetime
    strategic_timeframe_seconds: int
    hypothesis_set_id: str
    premise_ids: tuple[str, ...]
    hard_invalidator_ids: tuple[str, ...]
    review_clock: ReviewClock
    episode_risk_allocation_id: str
    new_hypothesis_receipt: TrustedReceiptAssertion
    time_authority_receipt: TrustedReceiptAssertion
    evidence_admission_receipts: tuple[TrustedReceiptAssertion, ...]
    timeframe_authority_profile_receipt: TrustedReceiptAssertion
    portfolio_snapshot_receipt: TrustedReceiptAssertion
    cooldown_receipt: TrustedReceiptAssertion
    episode_risk_allocation_receipt: TrustedReceiptAssertion
    expected_active_episode_ref: str | None = None
    prior_episode_status: StrategicStatus | None = None
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False


@dataclass(frozen=True, slots=True)
class StrategicEpisodeOpenedReceipt:
    receipt_id: str
    episode_ref: str
    state_digest: str
    causal_cutoff: datetime
    source_refs: tuple[str, ...]
    verdict: str
    receipt_digest: str
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False


@dataclass(frozen=True, slots=True)
class OpenedStrategicEpisode:
    state: StrategicEpisode
    opened_receipt: StrategicEpisodeOpenedReceipt


def _failure(code: str, message: str, *, unknown: bool = False):
    return DomainResult(
        status=ReducerStatus.UNKNOWN if unknown else ReducerStatus.REJECTED,
        error=DomainError(
            code=code,
            category="GENESIS",
            retryability="AFTER_INPUT_REPAIR" if unknown else "NEVER",
            message=message,
        ),
    )


def open_strategic_episode(
    command: OpenEpisodeCommand,
) -> DomainResult[OpenedStrategicEpisode]:
    """Validate strict genesis without minting any upstream receipt."""

    if (
        not command.request_id
        or not command.episode_id
        or not command.instrument_id
        or command.direction not in {"LONG", "SHORT"}
        or command.decision_cutoff.tzinfo is None
        or command.strategic_timeframe_seconds <= 0
        or not command.hypothesis_set_id
        or not command.premise_ids
        or not command.hard_invalidator_ids
        or not command.episode_risk_allocation_id
    ):
        return _failure("GENESIS_RECEIPT_MISSING", "genesis identity is incomplete")
    if (
        command.system_mode != SYSTEM_MODE
        or command.external_execution_authority
        != EXTERNAL_EXECUTION_AUTHORITY
        or command.executable
    ):
        return _failure(
            "E0_ACTION_AUTHORITY_NONE",
            "strict genesis cannot change E0 authority",
        )
    if (
        command.expected_active_episode_ref is not None
        or command.expected_head_digest is not None
    ):
        return _failure(
            "GENESIS_ACTIVE_EPISODE_EXISTS",
            "strict genesis requires no accepted active head",
        )
    if (
        command.prior_episode_status is not None
        and command.prior_episode_status is not StrategicStatus.CLOSED
    ):
        return _failure(
            "GENESIS_COOLDOWN_INCOMPLETE",
            "a prior episode must be CLOSED before new genesis",
        )
    required = (
        (
            command.new_hypothesis_receipt,
            "DOMAIN_HYPOTHESIS",
        ),
        (
            command.time_authority_receipt,
            "DOMAIN_TIME_AUTHORITY",
        ),
        *(
            (receipt, "DOMAIN_EVIDENCE")
            for receipt in command.evidence_admission_receipts
        ),
        (
            command.timeframe_authority_profile_receipt,
            "DOMAIN_POLICY",
        ),
        (
            command.portfolio_snapshot_receipt,
            "INFRASTRUCTURE_OFFLINE_PORTFOLIO",
        ),
        (
            command.cooldown_receipt,
            "DOMAIN_STRATEGIC",
        ),
        (
            command.episode_risk_allocation_receipt,
            "DOMAIN_POSITION",
        ),
    )
    if not command.evidence_admission_receipts:
        return _failure(
            "GENESIS_RECEIPT_MISSING",
            "at least one admitted evidence receipt is required",
            unknown=True,
        )
    for receipt, owner in required:
        if (
            receipt.owner_module != owner
            or receipt.verdict != "PASS"
            or receipt.causal_cutoff != command.decision_cutoff
        ):
            return _failure(
                "GENESIS_RECEIPT_MISSING",
                "receipt owner, verdict or causal cutoff is invalid",
                unknown=True,
            )
    if command.review_clock.next_review_at < command.decision_cutoff:
        return _failure(
            "CLOCK_TIME_INVALID",
            "initial review cannot precede genesis cutoff",
        )

    source_refs = tuple(receipt.receipt_ref for receipt, _ in required)
    state_digest = canonical_digest(
        {
            "episode_id": command.episode_id,
            "revision": 1,
            "strategic_status": StrategicStatus.ACTIVE.value,
            "exposure_status": ExposureStatus.FLAT.value,
            "strategic_timeframe_seconds": (
                command.strategic_timeframe_seconds
            ),
            "hypothesis_set_id": command.hypothesis_set_id,
            "premise_ids": command.premise_ids,
            "hard_invalidator_ids": command.hard_invalidator_ids,
            "review_clock": {
                "clock_id": command.review_clock.clock_id,
                "next_review_at": (
                    command.review_clock.next_review_at.isoformat()
                ),
                "mandatory_review_at": (
                    command.review_clock.mandatory_review_at.isoformat()
                ),
            },
            "episode_risk_allocation_id": (
                command.episode_risk_allocation_id
            ),
            "source_refs": source_refs,
        }
    )
    state = StrategicEpisode(
        episode_id=command.episode_id,
        revision=1,
        state_digest=state_digest,
        previous_state_digest=None,
        strategic_status=StrategicStatus.ACTIVE,
        exposure_status=ExposureStatus.FLAT,
        strategic_timeframe_seconds=command.strategic_timeframe_seconds,
        hypothesis_set_id=command.hypothesis_set_id,
        premise_ids=command.premise_ids,
        hard_invalidator_ids=command.hard_invalidator_ids,
        review_clock=command.review_clock,
        episode_risk_allocation_id=command.episode_risk_allocation_id,
    )
    receipt_payload = {
        "receipt_id": f"episode-opened:{command.episode_id}:1",
        "episode_ref": f"strategic-episode:{command.episode_id}:1",
        "state_digest": state_digest,
        "causal_cutoff": command.decision_cutoff.isoformat(),
        "source_refs": source_refs,
        "verdict": "PASS",
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
    }
    receipt_digest = canonical_digest(receipt_payload)
    receipt = StrategicEpisodeOpenedReceipt(
        receipt_id=receipt_payload["receipt_id"],
        episode_ref=receipt_payload["episode_ref"],
        state_digest=state_digest,
        causal_cutoff=command.decision_cutoff,
        source_refs=source_refs,
        verdict="PASS",
        receipt_digest=receipt_digest,
    )
    if _HEX64.fullmatch(state.state_digest) is None:
        return _failure("SCHEMA_INVALID", "state digest is malformed")
    return DomainResult(
        status=ReducerStatus.APPLIED,
        value=OpenedStrategicEpisode(state=state, opened_receipt=receipt),
        evaluated_event_id=f"EPISODE_OPENED:{command.episode_id}",
    )
