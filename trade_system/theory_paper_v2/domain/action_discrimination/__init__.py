"""Action-discrimination experiment domain.

The package is an E0-only research surface.  It owns counterfactual state
profiles, action semantics, deterministic candidate calculations, bounded
selection validation, and descriptive outcome replay.  It never calls a model
or grants execution authority.
"""

from .model import (
    ACTION_SPECS,
    CHALLENGE_CATEGORIES,
    E0A_FINANCIAL_CONTRACT,
    E0B_FINANCIAL_CONTRACT,
    E0B_SAMPLE_INDICES,
    OUTPUT_SPECS,
    PROFILE_ORDER,
    SAMPLE_INDICES,
    SELECTION_AXES,
    SEMANTIC_OUTPUT_SCHEMA,
    SUPERVISION_ORDER,
    ActionId,
    ActionSpec,
    ProfileId,
    ProfileSpec,
    SupervisionMode,
    profile_for_index,
    profile_for_window_index,
)

__all__ = [
    "ACTION_SPECS",
    "CHALLENGE_CATEGORIES",
    "E0A_FINANCIAL_CONTRACT",
    "E0B_FINANCIAL_CONTRACT",
    "E0B_SAMPLE_INDICES",
    "OUTPUT_SPECS",
    "PROFILE_ORDER",
    "SAMPLE_INDICES",
    "SELECTION_AXES",
    "SEMANTIC_OUTPUT_SCHEMA",
    "SUPERVISION_ORDER",
    "ActionId",
    "ActionSpec",
    "ProfileId",
    "ProfileSpec",
    "SupervisionMode",
    "profile_for_index",
    "profile_for_window_index",
]
