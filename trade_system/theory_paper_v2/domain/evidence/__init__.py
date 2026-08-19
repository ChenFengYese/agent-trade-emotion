"""Point-in-time evidence admission and cross-timescale promotion."""

from .model import (
    AdmittedEvidence,
    EvidenceQuality,
    EvidenceRecord,
    EvidenceScope,
    PhysicalExistence,
    SignalClass,
)
from .service import PromotionRequest, admit_evidence, qualify_promotion

__all__ = [
    "AdmittedEvidence",
    "EvidenceQuality",
    "EvidenceRecord",
    "EvidenceScope",
    "PhysicalExistence",
    "PromotionRequest",
    "SignalClass",
    "admit_evidence",
    "qualify_promotion",
]

