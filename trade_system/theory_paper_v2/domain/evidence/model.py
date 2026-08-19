"""Evidence objects with explicit point-in-time lineage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EvidenceScope(StrEnum):
    DECISION_CONTEMPORANEOUS = "DECISION_CONTEMPORANEOUS"
    COUNTERFACTUAL_MARKET_REPLAY = "COUNTERFACTUAL_MARKET_REPLAY"
    EVALUATION_ONLY = "EVALUATION_ONLY"


class PhysicalExistence(StrEnum):
    PROVEN = "PROVEN"
    NOT_CLAIMED = "NOT_CLAIMED"
    DISPROVEN = "DISPROVEN"


class EvidenceQuality(StrEnum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    PROXY = "PROXY"
    MISSING = "MISSING"
    CONFLICTED = "CONFLICTED"
    STALE = "STALE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SignalClass(StrEnum):
    STRATEGIC = "STRATEGIC"
    STRUCTURAL = "STRUCTURAL"
    RISK = "RISK"
    TACTICAL = "TACTICAL"
    NOISE = "NOISE"


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    source_id: str
    available_at: datetime
    ingested_at: datetime
    source_committed_at: datetime
    source_commit_receipt_valid: bool
    physical_existence: PhysicalExistence
    usage_scope: EvidenceScope
    quality: EvidenceQuality
    signal_class: SignalClass
    timeframe_seconds: int
    premise_ids: tuple[str, ...] = ()
    independent_source_ids: tuple[str, ...] = ()
    observation_count: int = 1


@dataclass(frozen=True, slots=True)
class AdmittedEvidence:
    record: EvidenceRecord
    decision_cutoff: datetime
    strategic_authority: bool
    promotion_required: bool

