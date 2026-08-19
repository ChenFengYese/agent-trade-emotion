"""Fail-closed validation and pre-outcome quality scoring for Agent outputs."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from ..contracts.canonical import canonical_digest
from .model import (
    CHALLENGE_CATEGORIES,
    E0B_FINANCIAL_CONTRACT,
    EXECUTION_AUTHORITY,
    NON_SELECTOR_KEYS,
    OUTPUT_SPECS,
    PATH_SLOTS,
    SELECTION_AXES,
    SYSTEM_MODE,
    ActionDiscriminationError,
)


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_OUTPUT_TOP_KEYS = frozenset(
    {
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
    }
)
_PATH_KEYS = frozenset(
    {
        "slot",
        "path_id",
        "summary",
        "evidence_ids",
        "hard_falsifier_refs",
        "unknowns",
    }
)
_ASSESSMENT_KEYS = frozenset(
    {"action_id", "ordinal", "rationale", "evidence_ids"}
)
_CLAIM_KEYS = frozenset(
    {
        "category",
        "materiality",
        "claim",
        "evidence_ids",
        "affected_action_ids",
    }
)
_AXIS_KEYS = frozenset({"axis", "status", "rationale"})
_PATH_IDS = frozenset(
    {
        "FAILURE_TO_STOP",
        "NORMAL_REBOUND_TO_T1",
        "TREND_CONTINUATION_T1_TO_T2",
        "EXHAUSTION_T1_THEN_RETURN",
        "OTHER",
        "UNKNOWN",
    }
)
_ORDINALS = frozenset({"PREFERRED", "VIABLE", "AVOID", "UNKNOWN"})
_ORDINAL_RANK = {
    "PREFERRED": 0,
    "VIABLE": 1,
    "UNKNOWN": 2,
    "AVOID": 3,
}
_AXIS_STATUSES = frozenset({"APPLIED", "UNKNOWN", "NOT_APPLICABLE"})


@dataclass(frozen=True, slots=True)
class SemanticValidation:
    role_key: str
    output_kind: str
    selected_action: str | None
    material_challenge_categories: tuple[str, ...]
    quality_components: Mapping[str, bool]
    quality_score: int
    semantic_digest: str

    def document(self) -> dict[str, Any]:
        return {
            "role_key": self.role_key,
            "output_kind": self.output_kind,
            "selected_action": self.selected_action,
            "material_challenge_categories": list(
                self.material_challenge_categories
            ),
            "quality_components": dict(self.quality_components),
            "quality_score": self.quality_score,
            "semantic_digest": self.semantic_digest,
        }


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], code: str) -> None:
    if frozenset(value) != expected:
        raise ActionDiscriminationError(code)


def _string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionDiscriminationError(code)
    return value


def _string_list(value: Any, code: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise ActionDiscriminationError(code)
    return value


def _refs(
    value: Any,
    allowed: frozenset[str],
    code: str,
) -> list[str]:
    refs = _string_list(value, code)
    if any(item not in allowed for item in refs):
        raise ActionDiscriminationError(code)
    return refs


def _role_key_valid(role_key: str) -> str:
    try:
        return OUTPUT_SPECS[role_key]
    except KeyError as exc:
        raise ActionDiscriminationError("ROLE_KEY_UNKNOWN") from exc


def validate_semantic_output(
    *,
    role_key: str,
    output: Mapping[str, Any],
    context: Mapping[str, Any],
) -> SemanticValidation:
    """Validate exact role boundaries and score only decision-time structure."""

    expected_kind = _role_key_valid(role_key)
    if not isinstance(output, Mapping):
        raise ActionDiscriminationError("SEMANTIC_OUTPUT_NOT_OBJECT")
    _exact_keys(output, _OUTPUT_TOP_KEYS, "SEMANTIC_TOP_KEYS_INVALID")
    if (
        output.get("schema_id") != "action_discrimination_semantic_output"
        or output.get("schema_version") != "1.0.0"
        or output.get("output_kind") != expected_kind
        or output.get("system_mode") != SYSTEM_MODE
        or output.get("external_execution_authority") != EXECUTION_AUTHORITY
        or output.get("executable") is not False
        or output.get("numeric_probability_status") != "NOT_CLAIMED"
    ):
        raise ActionDiscriminationError("SEMANTIC_ENVELOPE_INVALID")
    context_digest = context.get("context_digest")
    state_digest = context.get("state", {}).get("state_digest")
    if (
        not isinstance(context_digest, str)
        or _DIGEST.fullmatch(context_digest) is None
        or output.get("context_digest") != context_digest
        or not isinstance(state_digest, str)
        or _DIGEST.fullmatch(state_digest) is None
        or output.get("state_digest") != state_digest
    ):
        raise ActionDiscriminationError("SEMANTIC_CONTEXT_STATE_BINDING_INVALID")
    choice = context.get("candidate_calculations", {}).get("selector_choice_set")
    if not isinstance(choice, list) or not choice or any(
        not isinstance(item, str) for item in choice
    ):
        raise ActionDiscriminationError("CONTEXT_CHOICE_SET_INVALID")
    choice_set = frozenset(choice)
    e0b_contract = (
        context.get("financial_contract_version") == E0B_FINANCIAL_CONTRACT
    )
    allowed_evidence = frozenset(context.get("allowed_evidence_ids", []))
    if not allowed_evidence:
        raise ActionDiscriminationError("CONTEXT_EVIDENCE_SET_EMPTY")

    paths = output.get("paths")
    if not isinstance(paths, list) or len(paths) != len(PATH_SLOTS):
        raise ActionDiscriminationError("SEMANTIC_PATH_COUNT_INVALID")
    slots: list[str] = []
    path_ids: list[str] = []
    evidence_used: set[str] = set()
    unknown_preserved = False
    for row in paths:
        if not isinstance(row, Mapping):
            raise ActionDiscriminationError("SEMANTIC_PATH_INVALID")
        _exact_keys(row, _PATH_KEYS, "SEMANTIC_PATH_KEYS_INVALID")
        slot = row.get("slot")
        path_id = row.get("path_id")
        if slot not in PATH_SLOTS or path_id not in _PATH_IDS:
            raise ActionDiscriminationError("SEMANTIC_PATH_ENUM_INVALID")
        _string(row.get("summary"), "SEMANTIC_PATH_SUMMARY_INVALID")
        refs = _refs(
            row.get("evidence_ids"),
            allowed_evidence,
            "SEMANTIC_PATH_EVIDENCE_INVALID",
        )
        evidence_used.update(refs)
        if e0b_contract:
            allowed_hard_falsifiers = frozenset(
                _string_list(
                    context.get("state", {}).get(
                        "hard_invalidator_refs", []
                    ),
                    "CONTEXT_HARD_INVALIDATOR_REFS_INVALID",
                )
            )
            _refs(
                row.get("hard_falsifier_refs"),
                allowed_hard_falsifiers,
                "SEMANTIC_HARD_FALSIFIER_REFS_INVALID",
            )
        else:
            _string_list(
                row.get("hard_falsifier_refs"),
                "SEMANTIC_HARD_FALSIFIER_REFS_INVALID",
            )
        unknowns = _string_list(
            row.get("unknowns"), "SEMANTIC_UNKNOWNS_INVALID"
        )
        if slot == "OTHER_OR_UNKNOWN":
            if path_id not in {"OTHER", "UNKNOWN"} or not unknowns:
                raise ActionDiscriminationError(
                    "SEMANTIC_OTHER_UNKNOWN_NOT_PRESERVED"
                )
            unknown_preserved = True
        slots.append(str(slot))
        path_ids.append(str(path_id))
    if tuple(slots) != PATH_SLOTS:
        raise ActionDiscriminationError("SEMANTIC_PATH_SLOT_ORDER_INVALID")
    if e0b_contract and (
        len(set(path_ids[:3])) != 3
        or any(item in {"OTHER", "UNKNOWN"} for item in path_ids[:3])
    ):
        raise ActionDiscriminationError(
            "SEMANTIC_KNOWN_PATH_SLOTS_NOT_DISTINCT"
        )

    assessments = output.get("action_assessments")
    if not isinstance(assessments, list) or len(assessments) != len(choice):
        raise ActionDiscriminationError("SEMANTIC_ASSESSMENT_COUNT_INVALID")
    assessed: list[str] = []
    assessment_ordinals: dict[str, str] = {}
    for row in assessments:
        if not isinstance(row, Mapping):
            raise ActionDiscriminationError("SEMANTIC_ASSESSMENT_INVALID")
        _exact_keys(row, _ASSESSMENT_KEYS, "SEMANTIC_ASSESSMENT_KEYS_INVALID")
        action_id = row.get("action_id")
        if action_id not in choice_set or row.get("ordinal") not in _ORDINALS:
            raise ActionDiscriminationError("SEMANTIC_ASSESSMENT_ENUM_INVALID")
        _string(row.get("rationale"), "SEMANTIC_ASSESSMENT_RATIONALE_INVALID")
        refs = _refs(
            row.get("evidence_ids"),
            allowed_evidence,
            "SEMANTIC_ASSESSMENT_EVIDENCE_INVALID",
        )
        evidence_used.update(refs)
        assessed.append(str(action_id))
        assessment_ordinals[str(action_id)] = str(row["ordinal"])
    if len(assessed) != len(set(assessed)) or frozenset(assessed) != choice_set:
        raise ActionDiscriminationError("SEMANTIC_ASSESSMENT_COVERAGE_INVALID")

    claims = output.get("challenge_claims")
    if not isinstance(claims, list):
        raise ActionDiscriminationError("SEMANTIC_CHALLENGES_INVALID")
    material_categories: set[str] = set()
    for row in claims:
        if not isinstance(row, Mapping):
            raise ActionDiscriminationError("SEMANTIC_CHALLENGE_INVALID")
        _exact_keys(row, _CLAIM_KEYS, "SEMANTIC_CHALLENGE_KEYS_INVALID")
        category = row.get("category")
        materiality = row.get("materiality")
        if category not in CHALLENGE_CATEGORIES or materiality not in {
            "MATERIAL",
            "NON_MATERIAL",
        }:
            raise ActionDiscriminationError("SEMANTIC_CHALLENGE_ENUM_INVALID")
        _string(row.get("claim"), "SEMANTIC_CHALLENGE_CLAIM_INVALID")
        refs = _refs(
            row.get("evidence_ids"),
            allowed_evidence,
            "SEMANTIC_CHALLENGE_EVIDENCE_INVALID",
        )
        evidence_used.update(refs)
        affected = _string_list(
            row.get("affected_action_ids"),
            "SEMANTIC_CHALLENGE_ACTIONS_INVALID",
        )
        if any(item not in choice_set for item in affected):
            raise ActionDiscriminationError("SEMANTIC_CHALLENGE_ACTIONS_INVALID")
        if materiality == "MATERIAL":
            material_categories.add(str(category))

    axes = output.get("selection_axes")
    if not isinstance(axes, list) or len(axes) != len(SELECTION_AXES):
        raise ActionDiscriminationError("SEMANTIC_AXIS_COUNT_INVALID")
    axis_status: dict[str, str] = {}
    for row in axes:
        if not isinstance(row, Mapping):
            raise ActionDiscriminationError("SEMANTIC_AXIS_INVALID")
        _exact_keys(row, _AXIS_KEYS, "SEMANTIC_AXIS_KEYS_INVALID")
        axis = row.get("axis")
        if axis not in SELECTION_AXES or row.get("status") not in _AXIS_STATUSES:
            raise ActionDiscriminationError("SEMANTIC_AXIS_ENUM_INVALID")
        _string(row.get("rationale"), "SEMANTIC_AXIS_RATIONALE_INVALID")
        if axis in axis_status:
            raise ActionDiscriminationError("SEMANTIC_AXIS_DUPLICATE")
        axis_status[str(axis)] = str(row["status"])
    if tuple(axis_status) != SELECTION_AXES:
        raise ActionDiscriminationError("SEMANTIC_AXIS_ORDER_INVALID")

    selected = output.get("selected_action")
    ranking = output.get("ranked_action_ids")
    if role_key in NON_SELECTOR_KEYS:
        if selected is not None or ranking != []:
            raise ActionDiscriminationError("NON_SELECTOR_ROLE_OVERREACH")
    else:
        if selected not in choice_set:
            raise ActionDiscriminationError("SELECTOR_ACTION_OUTSIDE_CHOICE_SET")
        ranked = _string_list(ranking, "SELECTOR_RANKING_INVALID")
        if frozenset(ranked) != choice_set or ranked[0] != selected:
            raise ActionDiscriminationError("SELECTOR_RANKING_INVALID")
        if e0b_contract and (
            assessment_ordinals[str(selected)] != "PREFERRED"
            or any(
                _ORDINAL_RANK[assessment_ordinals[left]]
                > _ORDINAL_RANK[assessment_ordinals[right]]
                for left, right in zip(ranked, ranked[1:])
            )
        ):
            raise ActionDiscriminationError(
                "SELECTOR_RANKING_ORDINAL_INCONSISTENT"
            )

    exposure_choices = len(
        {
            row.get("marked_gross_fraction_after")
            for row in context["candidate_calculations"]["candidate_rows"]
            if row.get("action_id") in choice_set
        }
    ) > 1
    has_reentry_choice = any(
        item in choice_set
        for item in ("EXIT_WITH_REENTRY", "REENTER_CORE", "WAIT_WITH_REVIEW")
    )
    symmetric_review_contract = e0b_contract
    review_challenge_pass = (
        bool(material_categories)
        if expected_kind in {"SELF_REVIEW", "CHALLENGE_BLIND"}
        else True
    )
    quality = {
        "SCHEMA_AND_BINDING": True,
        "PATH_SET_COMPLETE": tuple(slots) == PATH_SLOTS,
        "UNKNOWN_PRESERVED": unknown_preserved,
        "ACTION_SET_COMPLETE": frozenset(assessed) == choice_set,
        "EVIDENCE_BOUND": len(evidence_used) >= 2,
        (
            "DEDICATED_REVIEW_MATERIAL_CHALLENGE"
            if symmetric_review_contract
            else "MATERIAL_SELF_CHALLENGE"
        ): (
            review_challenge_pass
            if symmetric_review_contract
            else bool(material_categories)
        ),
        "STRATEGIC_CONTINUITY_REVIEWED": axis_status["STRATEGIC_CONTINUITY"] != "NOT_APPLICABLE",
        "PATH_EVIDENCE_REVIEWED": axis_status["PATH_EVIDENCE"] != "NOT_APPLICABLE",
        "RISK_AND_RR_REVIEWED": axis_status["TOTAL_ACCOUNT_RISK"] != "NOT_APPLICABLE" and axis_status["MARGINAL_REWARD_RISK"] != "NOT_APPLICABLE",
        "OPPORTUNITY_COST_REVIEWED": (not exposure_choices) or axis_status["OPPORTUNITY_COST"] != "NOT_APPLICABLE",
        "SUPERVISION_REVIEWED": axis_status["SUPERVISION"] != "NOT_APPLICABLE",
        "REENTRY_REVIEWED": (not has_reentry_choice) or axis_status["REENTRY_SYMMETRY"] != "NOT_APPLICABLE",
        "EXECUTION_COST_REVIEWED": axis_status["EXECUTION_COST"] != "NOT_APPLICABLE",
        "ROLE_BOUNDARY": True,
    }
    return SemanticValidation(
        role_key=role_key,
        output_kind=expected_kind,
        selected_action=str(selected) if isinstance(selected, str) else None,
        material_challenge_categories=tuple(sorted(material_categories)),
        quality_components=quality,
        quality_score=sum(1 for passed in quality.values() if passed),
        semantic_digest=canonical_digest(output),
    )


def arm_preoutcome_score(
    *,
    arm: str,
    validations: Sequence[SemanticValidation],
) -> dict[str, Any]:
    expected = 3
    if len(validations) != expected:
        raise ActionDiscriminationError("ARM_OUTPUT_COUNT_INVALID")
    selectors = [item for item in validations if item.output_kind == "SELECTION"]
    if len(selectors) != 1:
        raise ActionDiscriminationError("ARM_SELECTOR_COUNT_INVALID")
    categories = sorted(
        {
            category
            for item in validations
            for category in item.material_challenge_categories
        }
    )
    component_passes: dict[str, bool] = {}
    for item in validations:
        for key, passed in item.quality_components.items():
            component_passes[f"{item.output_kind}:{key}"] = passed
    score = sum(1 for passed in component_passes.values() if passed)
    value = {
        "arm": arm,
        "selected_action": selectors[0].selected_action,
        "preoutcome_quality_score": score,
        "preoutcome_quality_maximum": len(component_passes),
        "component_passes": component_passes,
        "material_challenge_categories": categories,
        "semantic_output_digests": [item.semantic_digest for item in validations],
        "future_outcome_used": False,
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXECUTION_AUTHORITY,
        "executable": False,
    }
    value["score_digest"] = canonical_digest(value)
    return value


__all__ = [
    "SemanticValidation",
    "arm_preoutcome_score",
    "validate_semantic_output",
]
