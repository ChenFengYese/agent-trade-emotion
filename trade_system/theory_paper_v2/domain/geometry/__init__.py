"""Analytical-geometry and executable-protection domain rules."""

from .model import (
    AnalysisGeometry,
    AnalysisGeometryStatus,
    GeometryAggregate,
    PositionSide,
    ProbabilityStatus,
    ProtectionBarrier,
    ExecutionBarrierStatus,
)
from .reducer import (
    AnalysisGeometryTransition,
    ProtectionRevision,
    ProtectionStatusTransition,
    reduce_analysis_geometry,
    revise_protection,
    transition_protection_status,
)

__all__ = [
    "AnalysisGeometry",
    "AnalysisGeometryStatus",
    "AnalysisGeometryTransition",
    "ExecutionBarrierStatus",
    "GeometryAggregate",
    "PositionSide",
    "ProbabilityStatus",
    "ProtectionBarrier",
    "ProtectionRevision",
    "ProtectionStatusTransition",
    "reduce_analysis_geometry",
    "revise_protection",
    "transition_protection_status",
]
