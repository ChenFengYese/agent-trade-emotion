"""Closed registries for the E0 action-discrimination experiment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


SYSTEM_MODE = "E0_OFFLINE_COUNTERFACTUAL"
EXECUTION_AUTHORITY = "NONE_E0"
EVIDENCE_CLASS = "PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT"
SAMPLE_INDICES = tuple(range(128, 160))
E0B_SAMPLE_INDICES = tuple(range(160, 192))
E0A_FINANCIAL_CONTRACT = "ACTION_E0A_FINANCIAL_CONTRACT_V1"
E0B_FINANCIAL_CONTRACT = "ACTION_E0B_FINANCIAL_CONTRACT_V2"
SUPPORTED_FINANCIAL_CONTRACTS = frozenset(
    {E0A_FINANCIAL_CONTRACT, E0B_FINANCIAL_CONTRACT}
)


class ActionDiscriminationError(ValueError):
    """A closed experiment-contract violation."""


class ProfileId(StrEnum):
    FLAT_ACTIVE = "FLAT_ACTIVE"
    CORE_ACTIVE = "CORE_ACTIVE"
    CORE_CONFIRMATION_ELIGIBLE = "CORE_CONFIRMATION_ELIGIBLE"
    CORE_PLUS_TACTICAL = "CORE_PLUS_TACTICAL"
    TARGET_REVIEW_ACTIVE = "TARGET_REVIEW_ACTIVE"
    REENTRY_PENDING = "REENTRY_PENDING"
    RISK_BUDGET_PRESSURE = "RISK_BUDGET_PRESSURE"
    HARD_INVALIDATED_CONTROL = "HARD_INVALIDATED_CONTROL"


class SupervisionMode(StrEnum):
    ATTENDED = "ATTENDED"
    UNATTENDED_PROTECTED = "UNATTENDED_PROTECTED"
    UNATTENDED_NO_NEW_RISK = "UNATTENDED_NO_NEW_RISK"


class ActionId(StrEnum):
    WAIT_WITH_REVIEW = "WAIT_WITH_REVIEW"
    HOLD_CORE = "HOLD_CORE"
    HOLD_CORE_TRAIL = "HOLD_CORE_TRAIL"
    OPEN_CORE = "OPEN_CORE"
    ADD_CONFIRMATION = "ADD_CONFIRMATION"
    ADD_TREND = "ADD_TREND"
    REDUCE_TACTICAL = "REDUCE_TACTICAL"
    PARTIAL_TAKE_PROFIT = "PARTIAL_TAKE_PROFIT"
    EXIT_WITH_REENTRY = "EXIT_WITH_REENTRY"
    REENTER_CORE = "REENTER_CORE"
    INVALIDATE_AND_EXIT = "INVALIDATE_AND_EXIT"


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_id: ActionId
    description: str
    introduces_new_risk: bool
    position_effect: str
    thesis_effect: str
    reentry_effect: str
    required_position_role: str | None = None

    def document(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id.value,
            "description": self.description,
            "introduces_new_risk": self.introduces_new_risk,
            "position_effect": self.position_effect,
            "thesis_effect": self.thesis_effect,
            "reentry_effect": self.reentry_effect,
            "required_position_role": self.required_position_role,
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXECUTION_AUTHORITY,
            "executable": False,
        }


ACTION_SPECS = (
    ActionSpec(
        ActionId.WAIT_WITH_REVIEW,
        "Remain flat and preserve an exact next-review obligation.",
        False,
        "NO_POSITION_CHANGE",
        "PRESERVE",
        "PRESERVE",
    ),
    ActionSpec(
        ActionId.HOLD_CORE,
        "Preserve the complete admitted position state, including CORE and any admitted TACTICAL lot.",
        False,
        "KEEP_STATE",
        "PRESERVE",
        "NONE",
        "CORE",
    ),
    ActionSpec(
        ActionId.HOLD_CORE_TRAIL,
        "Preserve CORE exposure and activate one-way trailing protection.",
        False,
        "KEEP_CORE_TRAIL",
        "PRESERVE",
        "NONE",
        "CORE",
    ),
    ActionSpec(
        ActionId.OPEN_CORE,
        "Open the registered 6.25 percent CORE research tranche.",
        True,
        "OPEN_CORE_6_25",
        "PRESERVE",
        "NONE",
    ),
    ActionSpec(
        ActionId.ADD_CONFIRMATION,
        "Activate the registered 3.125 percent confirmation tranche.",
        True,
        "ADD_CONFIRMATION_3_125",
        "PRESERVE",
        "NONE",
    ),
    ActionSpec(
        ActionId.ADD_TREND,
        "Activate the registered 3.125 percent trend tranche.",
        True,
        "ADD_TREND_3_125",
        "PRESERVE",
        "NONE",
    ),
    ActionSpec(
        ActionId.REDUCE_TACTICAL,
        "Close one TACTICAL tranche while preserving CORE and thesis.",
        False,
        "CLOSE_TACTICAL_3_125",
        "PRESERVE",
        "NONE",
        "TACTICAL",
    ),
    ActionSpec(
        ActionId.PARTIAL_TAKE_PROFIT,
        "Realize a bounded partial gain while retaining positive CORE exposure.",
        False,
        "PARTIAL_CLOSE_RETAIN_CORE",
        "PRESERVE",
        "NONE",
        "CORE",
    ),
    ActionSpec(
        ActionId.EXIT_WITH_REENTRY,
        "Exit all exposure while the thesis survives and atomically open reentry.",
        False,
        "EXIT_ALL",
        "PRESERVE",
        "OPEN",
    ),
    ActionSpec(
        ActionId.REENTER_CORE,
        "Fulfil the existing reentry contract with the registered CORE tranche.",
        True,
        "REENTER_CORE_6_25",
        "PRESERVE",
        "FULFILLED",
    ),
    ActionSpec(
        ActionId.INVALIDATE_AND_EXIT,
        "Apply a typed hard invalidator and close all remaining exposure.",
        False,
        "EXIT_ALL",
        "INVALIDATED",
        "CLOSED",
    ),
)
ACTION_BY_ID = {item.action_id: item for item in ACTION_SPECS}


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    profile_id: ProfileId
    thesis_status: str
    position_template: str
    reentry_status: str
    registered_action_ids: tuple[ActionId, ...]
    control_kind: str
    required_action_id: ActionId | None = None

    def __post_init__(self) -> None:
        if (
            not self.registered_action_ids
            or len(self.registered_action_ids)
            != len(set(self.registered_action_ids))
            or any(action not in ACTION_BY_ID for action in self.registered_action_ids)
            or self.control_kind not in {"MARKET_DISCRETION", "POLICY_CONTROL"}
            or (
                self.required_action_id is not None
                and self.required_action_id not in self.registered_action_ids
            )
        ):
            raise ActionDiscriminationError("PROFILE_SPEC_INVALID")

    def document(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id.value,
            "thesis_status": self.thesis_status,
            "position_template": self.position_template,
            "reentry_status": self.reentry_status,
            "registered_action_ids": tuple(
                action.value for action in self.registered_action_ids
            ),
            "control_kind": self.control_kind,
            "required_action_id": (
                self.required_action_id.value
                if self.required_action_id is not None
                else None
            ),
        }


PROFILE_SPECS = (
    ProfileSpec(
        ProfileId.FLAT_ACTIVE,
        "ACTIVE",
        "FLAT",
        "NONE",
        (ActionId.WAIT_WITH_REVIEW, ActionId.OPEN_CORE),
        "MARKET_DISCRETION",
    ),
    ProfileSpec(
        ProfileId.CORE_ACTIVE,
        "ACTIVE",
        "CORE_6_25",
        "NONE",
        (
            ActionId.HOLD_CORE,
            ActionId.HOLD_CORE_TRAIL,
            ActionId.ADD_CONFIRMATION,
            ActionId.EXIT_WITH_REENTRY,
        ),
        "MARKET_DISCRETION",
    ),
    ProfileSpec(
        ProfileId.CORE_CONFIRMATION_ELIGIBLE,
        "ACTIVE",
        "CORE_6_25",
        "NONE",
        (
            ActionId.HOLD_CORE,
            ActionId.ADD_CONFIRMATION,
            ActionId.EXIT_WITH_REENTRY,
        ),
        "MARKET_DISCRETION",
    ),
    ProfileSpec(
        ProfileId.CORE_PLUS_TACTICAL,
        "ACTIVE",
        "CORE_6_25_TACTICAL_3_125",
        "NONE",
        (
            ActionId.HOLD_CORE,
            ActionId.HOLD_CORE_TRAIL,
            ActionId.ADD_TREND,
            ActionId.REDUCE_TACTICAL,
            ActionId.PARTIAL_TAKE_PROFIT,
            ActionId.EXIT_WITH_REENTRY,
        ),
        "MARKET_DISCRETION",
    ),
    ProfileSpec(
        ProfileId.TARGET_REVIEW_ACTIVE,
        "ACTIVE",
        "CORE_6_25_TARGET_REACHED",
        "NONE",
        (
            ActionId.HOLD_CORE,
            ActionId.HOLD_CORE_TRAIL,
            ActionId.PARTIAL_TAKE_PROFIT,
            ActionId.EXIT_WITH_REENTRY,
        ),
        "MARKET_DISCRETION",
    ),
    ProfileSpec(
        ProfileId.REENTRY_PENDING,
        "ACTIVE",
        "FLAT",
        "OPEN",
        (ActionId.WAIT_WITH_REVIEW, ActionId.REENTER_CORE),
        "MARKET_DISCRETION",
    ),
    ProfileSpec(
        ProfileId.RISK_BUDGET_PRESSURE,
        "ACTIVE",
        "CORE_6_25_TACTICAL_6_25_PRESSURED",
        "NONE",
        (
            ActionId.REDUCE_TACTICAL,
            ActionId.PARTIAL_TAKE_PROFIT,
            ActionId.EXIT_WITH_REENTRY,
        ),
        "POLICY_CONTROL",
    ),
    ProfileSpec(
        ProfileId.HARD_INVALIDATED_CONTROL,
        "ACTIVE",
        "CORE_6_25_HARD_INVALIDATOR_PRESENT",
        "NONE",
        (ActionId.INVALIDATE_AND_EXIT,),
        "POLICY_CONTROL",
        required_action_id=ActionId.INVALIDATE_AND_EXIT,
    ),
)
PROFILE_BY_ID = {item.profile_id: item for item in PROFILE_SPECS}
PROFILE_ORDER = tuple(item.profile_id for item in PROFILE_SPECS)
SUPERVISION_ORDER = (
    SupervisionMode.ATTENDED,
    SupervisionMode.UNATTENDED_PROTECTED,
    SupervisionMode.UNATTENDED_NO_NEW_RISK,
    SupervisionMode.ATTENDED,
)


def profile_for_index(
    sample_index: int,
) -> tuple[ProfileSpec, SupervisionMode]:
    return profile_for_window_index(sample_index, SAMPLE_INDICES)


def profile_for_window_index(
    sample_index: int,
    sample_indices: tuple[int, ...],
) -> tuple[ProfileSpec, SupervisionMode]:
    if (
        type(sample_index) is not int
        or len(sample_indices) != 32
        or sample_indices != tuple(range(sample_indices[0], sample_indices[0] + 32))
        or sample_index not in sample_indices
    ):
        raise ActionDiscriminationError("SAMPLE_INDEX_OUTSIDE_ACTION_WINDOW")
    offset = sample_index - sample_indices[0]
    return (
        PROFILE_BY_ID[PROFILE_ORDER[offset % len(PROFILE_ORDER)]],
        SUPERVISION_ORDER[offset // len(PROFILE_ORDER)],
    )


CHALLENGE_CATEGORIES = (
    "STATE_CONTINUITY",
    "TIME_SCALE_OVERREACH",
    "EXIT_REENTRY_ASYMMETRY",
    "UNKNOWN_COERCION",
    "ACTION_SPACE_COLLAPSE",
    "ROLE_OVERREACH",
    "PATH_PAYOFF_MISMATCH",
    "RISK_BUDGET_OMISSION",
    "SUPERVISION_MISMATCH",
    "CORE_TACTICAL_CONFLATION",
    "UNREGISTERED_ADD",
    "OPPORTUNITY_COST_OMISSION",
)
SELECTION_AXES = (
    "STRATEGIC_CONTINUITY",
    "PATH_EVIDENCE",
    "MARGINAL_REWARD_RISK",
    "TOTAL_ACCOUNT_RISK",
    "OPPORTUNITY_COST",
    "SUPERVISION",
    "REENTRY_SYMMETRY",
    "EXECUTION_COST",
)
PATH_SLOTS = (
    "PRIMARY",
    "ALTERNATIVE",
    "NULL",
    "OTHER_OR_UNKNOWN",
)
OUTPUT_SPECS = {
    "single-proposal": "PROPOSAL",
    "single-self-review": "SELF_REVIEW",
    "single-selection": "SELECTION",
    "cluster-proposal": "PROPOSAL",
    "cluster-challenge": "CHALLENGE_BLIND",
    "cluster-selection": "SELECTION",
}
NON_SELECTOR_KEYS = frozenset(
    {
        "single-proposal",
        "single-self-review",
        "cluster-proposal",
        "cluster-challenge",
    }
)


SEMANTIC_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:theory-agent-v2:action-semantic-output:1.0.0",
    "type": "object",
    "required": [
        "schema_id",
        "schema_version",
        "output_kind",
        "context_digest",
        "state_digest",
        "paths",
        "action_assessments",
        "challenge_claims",
        "selected_action",
        "ranked_action_ids",
        "selection_axes",
        "numeric_probability_status",
        "system_mode",
        "external_execution_authority",
        "executable",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_id": {"const": "action_discrimination_semantic_output"},
        "schema_version": {"const": "1.0.0"},
        "output_kind": {
            "enum": ["PROPOSAL", "SELF_REVIEW", "CHALLENGE_BLIND", "SELECTION"]
        },
        "context_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "state_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "paths": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {
                "type": "object",
                "required": [
                    "slot",
                    "path_id",
                    "summary",
                    "evidence_ids",
                    "hard_falsifier_refs",
                    "unknowns",
                ],
                "additionalProperties": False,
                "properties": {
                    "slot": {"enum": list(PATH_SLOTS)},
                    "path_id": {
                        "enum": [
                            "FAILURE_TO_STOP",
                            "NORMAL_REBOUND_TO_T1",
                            "TREND_CONTINUATION_T1_TO_T2",
                            "EXHAUSTION_T1_THEN_RETURN",
                            "OTHER",
                            "UNKNOWN",
                        ]
                    },
                    "summary": {"type": "string", "minLength": 1},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "hard_falsifier_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "unknowns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                },
            },
        },
        "action_assessments": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["action_id", "ordinal", "rationale", "evidence_ids"],
                "additionalProperties": False,
                "properties": {
                    "action_id": {"type": "string"},
                    "ordinal": {
                        "enum": ["PREFERRED", "VIABLE", "AVOID", "UNKNOWN"]
                    },
                    "rationale": {"type": "string", "minLength": 1},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                },
            },
        },
        "challenge_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "category",
                    "materiality",
                    "claim",
                    "evidence_ids",
                    "affected_action_ids",
                ],
                "additionalProperties": False,
                "properties": {
                    "category": {"enum": list(CHALLENGE_CATEGORIES)},
                    "materiality": {"enum": ["MATERIAL", "NON_MATERIAL"]},
                    "claim": {"type": "string", "minLength": 1},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "affected_action_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                },
            },
        },
        "selected_action": {"type": ["string", "null"]},
        "ranked_action_ids": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
        },
        "selection_axes": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["axis", "status", "rationale"],
                "additionalProperties": False,
                "properties": {
                    "axis": {"enum": list(SELECTION_AXES)},
                    "status": {
                        "enum": ["APPLIED", "UNKNOWN", "NOT_APPLICABLE"]
                    },
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
        "numeric_probability_status": {"const": "NOT_CLAIMED"},
        "system_mode": {"const": SYSTEM_MODE},
        "external_execution_authority": {"const": EXECUTION_AUTHORITY},
        "executable": {"const": False},
    },
}


__all__ = [
    "ACTION_BY_ID",
    "ACTION_SPECS",
    "CHALLENGE_CATEGORIES",
    "E0A_FINANCIAL_CONTRACT",
    "E0B_FINANCIAL_CONTRACT",
    "E0B_SAMPLE_INDICES",
    "EVIDENCE_CLASS",
    "EXECUTION_AUTHORITY",
    "NON_SELECTOR_KEYS",
    "OUTPUT_SPECS",
    "PATH_SLOTS",
    "PROFILE_BY_ID",
    "PROFILE_ORDER",
    "PROFILE_SPECS",
    "SAMPLE_INDICES",
    "SELECTION_AXES",
    "SEMANTIC_OUTPUT_SCHEMA",
    "SUPERVISION_ORDER",
    "SUPPORTED_FINANCIAL_CONTRACTS",
    "SYSTEM_MODE",
    "ActionDiscriminationError",
    "ActionId",
    "ActionSpec",
    "ProfileId",
    "ProfileSpec",
    "SupervisionMode",
    "profile_for_index",
    "profile_for_window_index",
]
