"""Pure V3.2 replayable shadow-decision and outcome contracts.

Six pre-registered comparison arms share one point-in-time information and
opportunity set.  Every arm carries a frozen policy identity and a typed
derivation receipt.  A baseline that has not actually been recomputed is kept
as ``UNKNOWN_NOT_COMPUTED``; a caller cannot replace that fact with an
arbitrary action label.

Outcome evaluation is deterministic.  One terminal public mark can establish
only terminal directional alignment.  It cannot establish an intrahorizon
path, MFE, MAE, fill, position, PnL, probability, or expected value, so those
fields remain ``UNKNOWN`` unless a later, separately frozen path contract is
provided.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    canonical_bytes,
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .v32_outcome_tick import (
    OUTCOME_RECEIPT_DIGEST_FIELD,
    OUTCOME_RECEIPT_SCHEMA_ID,
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
    V32OutcomeTickError,
    verify_v32_outcome_schedule_set,
)


class V32ShadowEvaluationError(ValueError):
    """A V3.2 shadow comparison invariant failed closed."""


SCHEMA_VERSION = "1.0.0"
SHADOW_DECISION_BUNDLE_SCHEMA_ID = "theory_paper_v32_shadow_decision_bundle_v1"
SHADOW_DECISION_BUNDLE_DIGEST_FIELD = "shadow_decision_bundle_digest"
SHADOW_OUTCOME_EVALUATION_SCHEMA_ID = (
    "theory_paper_v32_shadow_outcome_evaluation_v1"
)
SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD = "shadow_outcome_evaluation_digest"

PIT_REGISTRY_SCHEMA_ID = "theory_paper_v32_verified_pit_evidence_registry_v1"
PIT_REGISTRY_DIGEST_FIELD = "pit_evidence_registry_digest"
MARKET_ANALYSIS_SCHEMA_ID = "theory_paper_v32_public_market_analysis_bundle_v1"
MARKET_ANALYSIS_DIGEST_FIELD = "public_market_analysis_bundle_digest"
OPPORTUNITY_SET_SCHEMA_ID = "theory_paper_v32_dynamic_action_evaluation_v1"
OPPORTUNITY_SET_DIGEST_FIELD = "action_evaluation_digest"
SELECTED_PLAN_SCHEMA_ID = "theory_paper_v32_dynamic_action_plan_v1"
SELECTED_PLAN_DIGEST_FIELD = "dynamic_action_plan_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

SHADOW_ARM_IDS = (
    "V32_SELECTED_PLAN",
    "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE",
    "WAIT_ONLY",
    "SIMPLE_15M_TREND",
    "NO_RSI_REFERENCE",
    "ALWAYS_LONG_PUBLIC_MARK_REFERENCE",
)

POLICY_VERSION = "1.0.0"
POLICY_DESCRIPTORS = {
    "V32_SELECTED_PLAN": {
        "policy_id": "V32_SELECTED_PLAN_EXACT_SEALED_OUTPUT",
        "rule": "COPY_EXACT_SELECTED_ACTION_AND_DIRECTION_FROM_SEALED_V32_PLAN",
    },
    "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE": {
        "policy_id": "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE",
        "rule": "UNKNOWN_UNTIL_A_FROZEN_V31_POLICY_IS_REPLAYED_ON_IDENTICAL_PIT_INPUT",
    },
    "WAIT_ONLY": {
        "policy_id": "WAIT_ONLY_CONSTANT",
        "rule": "WAIT_WITH_NO_DIRECTION_FOR_EVERY_DECISION",
    },
    "SIMPLE_15M_TREND": {
        "policy_id": "SIMPLE_15M_LAST_TWO_CLOSED_BAR_TREND",
        "rule": "LONG_IF_LATEST_CLOSE_GT_PREVIOUS_SHORT_IF_LT_WAIT_IF_EQUAL",
    },
    "NO_RSI_REFERENCE": {
        "policy_id": "NO_RSI_REFERENCE",
        "rule": "UNKNOWN_UNTIL_A_FROZEN_NO_RSI_POLICY_IS_REPLAYED_ON_IDENTICAL_PIT_INPUT",
    },
    "ALWAYS_LONG_PUBLIC_MARK_REFERENCE": {
        "policy_id": "ALWAYS_LONG_PUBLIC_MARK_REFERENCE",
        "rule": "HOLD_LONG_PUBLIC_MARK_DIRECTION_WITHOUT_FILL_OR_POSITION_CLAIM",
    },
}
POLICY_DIGESTS = {
    arm_id: canonical_digest(
        {"policy_version": POLICY_VERSION, **descriptor}
    )
    for arm_id, descriptor in POLICY_DESCRIPTORS.items()
}

ACTION_LABELS = (
    "OPEN_PROBE",
    "ADD",
    "HOLD",
    "REDUCE",
    "CLOSE",
    "REENTER",
    "REVERSE",
    "WAIT",
    "UNKNOWN",
)
DIRECTION_LABELS = ("LONG", "SHORT", "NONE", "UNKNOWN")
SHADOW_ARM_ORDINAL_BANDS = (
    "VERY_LOW",
    "LOW",
    "MEDIUM",
    "HIGH",
    "VERY_HIGH",
    "UNKNOWN",
)
ALIGNMENT_LABELS = ("ALIGNED", "OPPOSED", "NON_DIRECTIONAL", "UNKNOWN")
PATH_LABELS = ("CONSISTENT", "PARTIAL", "INCONSISTENT", "UNKNOWN")
ORDINAL_MAGNITUDE_BANDS = ("NONE", "LOW", "MEDIUM", "HIGH", "UNKNOWN")
OPPORTUNITY_MISS_BANDS = (
    "NONE",
    "LOW",
    "MEDIUM",
    "HIGH",
    "AVOIDED_ADVERSE_MOVE",
    "UNKNOWN",
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_COMMON_ARM_FIELDS = frozenset(
    {
        "arm_id",
        "run_id",
        "cycle_index",
        "as_of",
        "pit_registry_binding",
        "market_analysis_binding",
        "opportunity_set_binding",
        "selected_plan_binding",
        "policy_id",
        "policy_version",
        "policy_digest",
        "derivation_status",
        "derivation_inputs",
        "derivation_input_refs",
        "derivation_receipt_digest",
        "action_label",
        "direction_label",
        "shadow_arm_ordinal_band",
        "ordinal_band_semantics",
        "ordinal_rationale",
        "evidence_refs",
        "research_role",
        "outcome_fields_present",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "probability_claim",
        "expected_value_allowed",
        "executable",
    }
)
_DECISION_BUNDLE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "bundle_id",
        "run_id",
        "decision_id",
        "cycle_index",
        "as_of",
        "created_at",
        "pit_registry_binding",
        "market_analysis_binding",
        "opportunity_set_binding",
        "selected_plan_binding",
        "decision_mark_snapshot",
        "arm_ids",
        "arms",
        "arm_set_policy",
        "policy_replay_requirement",
        "comparison_context_policy",
        "outcome_values_present",
        "probability_claim",
        "expected_value_allowed",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "source_scope",
        "external_execution_authority",
        "executable",
        SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    }
)
_OUTCOME_RESULT_FIELDS = frozenset(
    {
        "arm_id",
        "action_label",
        "direction_label",
        "outcome_schedule_id",
        "outcome_schedule_digest",
        "outcome_receipt_digest",
        "directional_alignment",
        "path_alignment",
        "mfe_band",
        "mae_band",
        "turnover_intent_band",
        "opportunity_miss_band",
        "unknown_fields",
        "descriptive_rationale",
        "comparison_evidence_refs",
        "comparison_status",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "probability_claim",
        "expected_value_allowed",
        "executable",
    }
)
_OUTCOME_EVALUATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "evaluation_id",
        "run_id",
        "decision_id",
        "cycle_index",
        "decision_as_of",
        "evaluated_at",
        "horizon",
        "shadow_decision_bundle_binding",
        "outcome_schedule_set_binding",
        "outcome_schedule_id",
        "outcome_schedule_digest",
        "outcome_not_before",
        "outcome_receipt_binding",
        "outcome_resolution_status",
        "arm_ids",
        "arm_results",
        "comparison_policy",
        "mfe_mae_semantics",
        "numeric_market_values_copied_into_arm_results",
        "probability_claim",
        "expected_value_allowed",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "source_scope",
        "external_execution_authority",
        "executable",
        SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD,
    }
)

# Frozen receipt surface copied from the V3.2 outcome contract so this module
# can reject a self-signed object with omitted or injected execution semantics.
_OUTCOME_RECEIPT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "schedule_id",
        "schedule_digest",
        "schedule_set_digest",
        "decision_id",
        "cycle_index",
        "horizon",
        "outcome_not_before",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
        "resolved_at",
        "resolution_status",
        "coverage_loss_reason",
        "observable_ref",
        "value",
        "provider_as_of",
        "available_at",
        "quality",
        "missingness",
        "terminal",
        "attempt_count",
        "retry_allowed",
        "shared_tick_request",
        "observation_scope",
        "stop_trigger_semantics",
        "trigger_is_fill",
        "fill_claim",
        "position_claim",
        "pnl_claim",
        "source_scope",
        "external_execution_authority",
        "executable",
        OUTCOME_RECEIPT_DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ShadowEvaluationError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ShadowEvaluationError(code) from exc
    if parsed.tzinfo is None:
        raise V32ShadowEvaluationError(code)
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text:
        raise V32ShadowEvaluationError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _cycle(value: Any, code: str = "V32_SHADOW_CYCLE_INVALID") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16:
        raise V32ShadowEvaluationError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32ShadowEvaluationError(code)
    return value


def _relative_ref(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V32ShadowEvaluationError(code)
    return text


def _binding(
    value: Any,
    *,
    schema_id: str,
    digest_field: str,
    code: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32ShadowEvaluationError(code)
    if value.get("schema_id") != schema_id or value.get("digest_field") != digest_field:
        raise V32ShadowEvaluationError(code)
    return {
        "relative_ref": _relative_ref(value.get("relative_ref"), code),
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def _physical_sha(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _embedded_binding(
    document: Mapping[str, Any],
    value: Any,
    *,
    schema_id: str,
    digest_field: str,
    code: str,
) -> dict[str, str]:
    binding = _binding(
        value, schema_id=schema_id, digest_field=digest_field, code=code
    )
    try:
        semantic = verify_self_digest(document, digest_field)
    except (TypeError, ValueError) as exc:
        raise V32ShadowEvaluationError(code) from exc
    if (
        document.get("schema_id") != schema_id
        or binding["semantic_digest"] != semantic
        or binding["physical_sha256"] != _physical_sha(document)
    ):
        raise V32ShadowEvaluationError(code)
    return binding


def _digest_refs(value: Any, code: str, *, allow_empty: bool) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32ShadowEvaluationError(code)
    result = [_digest(item, code) for item in value]
    if (not allow_empty and not result) or result != sorted(set(result)):
        raise V32ShadowEvaluationError(code)
    return result


def _positive_decimal(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise V32ShadowEvaluationError(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise V32ShadowEvaluationError(code) from exc
    if not parsed.is_finite() or parsed <= 0 or canonical_decimal(parsed) != value:
        raise V32ShadowEvaluationError(code)
    return value


def _decision_mark_snapshot(
    value: Any, *, decision_as_of: str, created_at: str
) -> dict[str, str]:
    code = "V32_SHADOW_DECISION_MARK_INVALID"
    fields = {"value", "datum_digest", "observed_at", "available_at"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise V32ShadowEvaluationError(code)
    observed = _time(value.get("observed_at"), code)
    available = _time(value.get("available_at"), code)
    if (
        _moment(observed, code) > _moment(available, code)
        or _moment(available, code) > _moment(decision_as_of, code)
        or _moment(decision_as_of, code) > _moment(created_at, code)
    ):
        raise V32ShadowEvaluationError(code)
    return {
        "value": _positive_decimal(value.get("value"), code),
        "datum_digest": _digest(value.get("datum_digest"), code),
        "observed_at": observed,
        "available_at": available,
    }


def _policy_derivation(
    *,
    arm_id: str,
    value: Mapping[str, Any],
    selected_plan_digest: str,
) -> tuple[str, dict[str, Any], list[str], str, str, str]:
    """Validate one frozen arm and deterministically derive its output."""

    code = "V32_SHADOW_ARM_POLICY_DERIVATION_INVALID"
    status = _text(value.get("derivation_status"), code)
    inputs = value.get("derivation_inputs")
    if not isinstance(inputs, Mapping):
        raise V32ShadowEvaluationError(code)
    input_refs = _digest_refs(
        value.get("derivation_input_refs"), code, allow_empty=True
    )
    if arm_id == "V32_SELECTED_PLAN":
        if status != "COMPUTED_FROM_SELECTED_PLAN" or set(inputs) != {
            "selected_candidate_id",
            "action_label",
            "direction_label",
        }:
            raise V32ShadowEvaluationError(code)
        action = _text(inputs.get("action_label"), code)
        direction = _text(inputs.get("direction_label"), code)
        _text(inputs.get("selected_candidate_id"), code)
        if (
            input_refs != [selected_plan_digest]
            or action == "UNKNOWN"
            or direction == "UNKNOWN"
        ):
            raise V32ShadowEvaluationError(code)
    elif arm_id in {
        "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE",
        "NO_RSI_REFERENCE",
    }:
        if status != "UNKNOWN_NOT_COMPUTED" or inputs or input_refs:
            raise V32ShadowEvaluationError(code)
        action, direction = "UNKNOWN", "UNKNOWN"
    elif arm_id == "WAIT_ONLY":
        if status != "COMPUTED_CONSTANT" or inputs or input_refs:
            raise V32ShadowEvaluationError(code)
        action, direction = "WAIT", "NONE"
    elif arm_id == "ALWAYS_LONG_PUBLIC_MARK_REFERENCE":
        if status != "COMPUTED_CONSTANT" or inputs or input_refs:
            raise V32ShadowEvaluationError(code)
        action, direction = "HOLD", "LONG"
    elif arm_id == "SIMPLE_15M_TREND":
        required = {
            "previous_close",
            "latest_close",
            "previous_close_datum_digest",
            "latest_close_datum_digest",
        }
        if status != "COMPUTED_FROM_TWO_CLOSED_15M_BARS" or set(inputs) != required:
            raise V32ShadowEvaluationError(code)
        previous = Decimal(_positive_decimal(inputs.get("previous_close"), code))
        latest = Decimal(_positive_decimal(inputs.get("latest_close"), code))
        prior_digest = _digest(inputs.get("previous_close_datum_digest"), code)
        latest_digest = _digest(inputs.get("latest_close_datum_digest"), code)
        if prior_digest == latest_digest or input_refs != sorted(
            [prior_digest, latest_digest]
        ):
            raise V32ShadowEvaluationError(code)
        if latest > previous:
            action, direction = "HOLD", "LONG"
        elif latest < previous:
            action, direction = "HOLD", "SHORT"
        else:
            action, direction = "WAIT", "NONE"
    else:  # pragma: no cover - guarded by the frozen arm set
        raise V32ShadowEvaluationError(code)
    if action not in ACTION_LABELS or direction not in DIRECTION_LABELS:
        raise V32ShadowEvaluationError(code)
    if (action == "WAIT") != (direction == "NONE"):
        raise V32ShadowEvaluationError(code)
    if action == "UNKNOWN" and direction != "UNKNOWN":
        raise V32ShadowEvaluationError(code)
    if direction == "UNKNOWN" and action != "UNKNOWN":
        raise V32ShadowEvaluationError(code)
    receipt_digest = canonical_digest(
        {
            "arm_id": arm_id,
            "policy_digest": POLICY_DIGESTS[arm_id],
            "derivation_status": status,
            "derivation_inputs": dict(inputs),
            "derivation_input_refs": input_refs,
            "action_label": action,
            "direction_label": direction,
        }
    )
    return status, dict(inputs), input_refs, action, direction, receipt_digest


def _common_bindings(
    *,
    pit_registry_binding: Mapping[str, Any],
    market_analysis_binding: Mapping[str, Any],
    opportunity_set_binding: Mapping[str, Any],
    selected_plan_binding: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    return {
        "pit_registry_binding": _binding(
            pit_registry_binding,
            schema_id=PIT_REGISTRY_SCHEMA_ID,
            digest_field=PIT_REGISTRY_DIGEST_FIELD,
            code="V32_SHADOW_PIT_BINDING_INVALID",
        ),
        "market_analysis_binding": _binding(
            market_analysis_binding,
            schema_id=MARKET_ANALYSIS_SCHEMA_ID,
            digest_field=MARKET_ANALYSIS_DIGEST_FIELD,
            code="V32_SHADOW_MARKET_ANALYSIS_BINDING_INVALID",
        ),
        "opportunity_set_binding": _binding(
            opportunity_set_binding,
            schema_id=OPPORTUNITY_SET_SCHEMA_ID,
            digest_field=OPPORTUNITY_SET_DIGEST_FIELD,
            code="V32_SHADOW_OPPORTUNITY_SET_BINDING_INVALID",
        ),
        "selected_plan_binding": _binding(
            selected_plan_binding,
            schema_id=SELECTED_PLAN_SCHEMA_ID,
            digest_field=SELECTED_PLAN_DIGEST_FIELD,
            code="V32_SHADOW_SELECTED_PLAN_BINDING_INVALID",
        ),
    }


def _decision_arm(
    value: Any,
    *,
    run_id: str,
    cycle_index: int,
    as_of: str,
    common_bindings: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    code = "V32_SHADOW_ARM_INVALID"
    if not isinstance(value, Mapping) or set(value) != _COMMON_ARM_FIELDS:
        raise V32ShadowEvaluationError(code)
    arm_id = _text(value.get("arm_id"), code)
    band = _text(value.get("shadow_arm_ordinal_band"), code)
    if (
        arm_id not in SHADOW_ARM_IDS
        or band not in SHADOW_ARM_ORDINAL_BANDS
        or value.get("ordinal_band_semantics")
        != "SHADOW_ARM_COMPARISON_ONLY_NOT_SUBJECTIVE_PLAUSIBILITY_TIER"
        or value.get("run_id") != run_id
        or value.get("cycle_index") != cycle_index
        or value.get("as_of") != as_of
        or any(value.get(name) != common_bindings[name] for name in common_bindings)
    ):
        raise V32ShadowEvaluationError(code)
    descriptor = POLICY_DESCRIPTORS[arm_id]
    if (
        value.get("policy_id") != descriptor["policy_id"]
        or value.get("policy_version") != POLICY_VERSION
        or value.get("policy_digest") != POLICY_DIGESTS[arm_id]
    ):
        raise V32ShadowEvaluationError("V32_SHADOW_ARM_POLICY_IDENTITY_INVALID")
    (
        derivation_status,
        derivation_inputs,
        derivation_input_refs,
        action,
        direction,
        derivation_receipt_digest,
    ) = _policy_derivation(
        arm_id=arm_id,
        value=value,
        selected_plan_digest=common_bindings["selected_plan_binding"][
            "semantic_digest"
        ],
    )
    if (
        value.get("action_label") != action
        or value.get("direction_label") != direction
        or value.get("derivation_receipt_digest") != derivation_receipt_digest
    ):
        raise V32ShadowEvaluationError(
            "V32_SHADOW_ARM_POLICY_OUTPUT_MISMATCH"
        )
    evidence = _digest_refs(
        value.get("evidence_refs"), code, allow_empty=True
    )
    if arm_id == "SIMPLE_15M_TREND" and not evidence:
        raise V32ShadowEvaluationError("V32_SHADOW_ARM_EVIDENCE_REQUIRED")
    if arm_id == "SIMPLE_15M_TREND" and evidence != derivation_input_refs:
        raise V32ShadowEvaluationError("V32_SHADOW_ARM_EVIDENCE_INVALID")
    if arm_id not in {"V32_SELECTED_PLAN", "SIMPLE_15M_TREND"} and evidence:
        raise V32ShadowEvaluationError("V32_SHADOW_ARM_EVIDENCE_INVALID")
    if derivation_status == "UNKNOWN_NOT_COMPUTED" and band != "UNKNOWN":
        raise V32ShadowEvaluationError("V32_SHADOW_UNKNOWN_BASELINE_OVERCLAIM")
    expected_role = (
        "SELECTED_NON_EXECUTABLE_RESEARCH_LABEL"
        if arm_id == "V32_SELECTED_PLAN"
        else "SHADOW_COUNTERFACTUAL_RESEARCH_LABEL"
    )
    if (
        value.get("research_role") != expected_role
        or value.get("outcome_fields_present") is not False
        or value.get("fill_claim") is not False
        or value.get("position_claim") is not False
        or value.get("pnl_claim") is not False
        or value.get("probability_claim")
        != "NONE_ORDINAL_RATIONALE_NOT_PROBABILITY"
        or value.get("expected_value_allowed") is not False
        or value.get("executable") is not False
    ):
        raise V32ShadowEvaluationError("V32_SHADOW_ARM_CLAIM_BOUNDARY_INVALID")
    return {
        "arm_id": arm_id,
        "run_id": run_id,
        "cycle_index": cycle_index,
        "as_of": as_of,
        **{name: dict(common_bindings[name]) for name in common_bindings},
        "policy_id": descriptor["policy_id"],
        "policy_version": POLICY_VERSION,
        "policy_digest": POLICY_DIGESTS[arm_id],
        "derivation_status": derivation_status,
        "derivation_inputs": derivation_inputs,
        "derivation_input_refs": derivation_input_refs,
        "derivation_receipt_digest": derivation_receipt_digest,
        "action_label": action,
        "direction_label": direction,
        "shadow_arm_ordinal_band": band,
        "ordinal_band_semantics": (
            "SHADOW_ARM_COMPARISON_ONLY_NOT_SUBJECTIVE_PLAUSIBILITY_TIER"
        ),
        "ordinal_rationale": _text(value.get("ordinal_rationale"), code),
        "evidence_refs": evidence,
        "research_role": expected_role,
        "outcome_fields_present": False,
        "fill_claim": False,
        "position_claim": False,
        "pnl_claim": False,
        "probability_claim": "NONE_ORDINAL_RATIONALE_NOT_PROBABILITY",
        "expected_value_allowed": False,
        "executable": False,
    }


def build_v32_shadow_decision_bundle_v1(
    *,
    bundle_id: str,
    run_id: str,
    decision_id: str,
    cycle_index: int,
    as_of: str,
    created_at: str,
    pit_registry_binding: Mapping[str, Any],
    market_analysis_binding: Mapping[str, Any],
    opportunity_set_binding: Mapping[str, Any],
    selected_plan_binding: Mapping[str, Any],
    decision_mark_snapshot: Mapping[str, Any],
    arms: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal six replayable shadow arms before any future outcome is available."""

    run = _text(run_id, "V32_SHADOW_RUN_INVALID")
    cycle = _cycle(cycle_index)
    decision = _text(decision_id, "V32_SHADOW_DECISION_ID_INVALID")
    observed = _time(as_of, "V32_SHADOW_AS_OF_INVALID")
    created = _time(created_at, "V32_SHADOW_CREATED_AT_INVALID")
    if _moment(created, "V32_SHADOW_CREATED_AT_INVALID") < _moment(
        observed, "V32_SHADOW_AS_OF_INVALID"
    ):
        raise V32ShadowEvaluationError("V32_SHADOW_TIME_ORDER_INVALID")
    common = _common_bindings(
        pit_registry_binding=pit_registry_binding,
        market_analysis_binding=market_analysis_binding,
        opportunity_set_binding=opportunity_set_binding,
        selected_plan_binding=selected_plan_binding,
    )
    decision_mark = _decision_mark_snapshot(
        decision_mark_snapshot,
        decision_as_of=observed,
        created_at=created,
    )
    if isinstance(arms, (str, bytes)) or not isinstance(arms, Sequence):
        raise V32ShadowEvaluationError("V32_SHADOW_ARM_SET_INVALID")
    normalized = [
        _decision_arm(
            row,
            run_id=run,
            cycle_index=cycle,
            as_of=observed,
            common_bindings=common,
        )
        for row in arms
    ]
    by_id = {row["arm_id"]: row for row in normalized}
    if len(normalized) != len(SHADOW_ARM_IDS) or set(by_id) != set(SHADOW_ARM_IDS):
        raise V32ShadowEvaluationError("V32_SHADOW_ARM_SET_INVALID")
    document = {
        "schema_id": SHADOW_DECISION_BUNDLE_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "bundle_id": _text(bundle_id, "V32_SHADOW_BUNDLE_ID_INVALID"),
        "run_id": run,
        "decision_id": decision,
        "cycle_index": cycle,
        "as_of": observed,
        "created_at": created,
        **common,
        "decision_mark_snapshot": decision_mark,
        "arm_ids": list(SHADOW_ARM_IDS),
        "arms": [by_id[arm_id] for arm_id in SHADOW_ARM_IDS],
        "arm_set_policy": "EXACT_SIX_FROZEN_ARMS_NO_ADDITION_OR_OMISSION",
        "policy_replay_requirement": (
            "COMPUTED_ARMS_REQUIRE_FROZEN_POLICY_INPUT_OUTPUT_RECEIPT_"
            "UNAVAILABLE_POLICY_REMAINS_UNKNOWN_NOT_COMPUTED"
        ),
        "comparison_context_policy": (
            "SAME_CYCLE_AS_OF_PIT_MARKET_ANALYSIS_OPPORTUNITY_SET_AND_SELECTED_PLAN"
        ),
        "outcome_values_present": False,
        "probability_claim": "NONE_ORDINAL_RATIONALE_NOT_PROBABILITY",
        "expected_value_allowed": False,
        "fill_claim": False,
        "position_claim": False,
        "pnl_claim": False,
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
    }
    return self_digest(document, SHADOW_DECISION_BUNDLE_DIGEST_FIELD)


def verify_v32_shadow_decision_bundle_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _DECISION_BUNDLE_FIELDS:
        raise V32ShadowEvaluationError("V32_SHADOW_BUNDLE_INVALID")
    try:
        supplied = verify_self_digest(document, SHADOW_DECISION_BUNDLE_DIGEST_FIELD)
        rebuilt = build_v32_shadow_decision_bundle_v1(
            bundle_id=document["bundle_id"],
            run_id=document["run_id"],
            decision_id=document["decision_id"],
            cycle_index=document["cycle_index"],
            as_of=document["as_of"],
            created_at=document["created_at"],
            pit_registry_binding=document["pit_registry_binding"],
            market_analysis_binding=document["market_analysis_binding"],
            opportunity_set_binding=document["opportunity_set_binding"],
            selected_plan_binding=document["selected_plan_binding"],
            decision_mark_snapshot=document["decision_mark_snapshot"],
            arms=document["arms"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ShadowEvaluationError):
            raise
        raise V32ShadowEvaluationError("V32_SHADOW_BUNDLE_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[SHADOW_DECISION_BUNDLE_DIGEST_FIELD]:
        raise V32ShadowEvaluationError("V32_SHADOW_BUNDLE_RECONSTRUCTION_MISMATCH")
    return supplied


def _verify_outcome_receipt_intrinsic(document: Mapping[str, Any]) -> str:
    code = "V32_SHADOW_OUTCOME_RECEIPT_INVALID"
    if not isinstance(document, Mapping) or set(document) != _OUTCOME_RECEIPT_FIELDS:
        raise V32ShadowEvaluationError(code)
    try:
        digest = verify_self_digest(document, OUTCOME_RECEIPT_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V32ShadowEvaluationError(code) from exc
    if (
        document.get("schema_id") != OUTCOME_RECEIPT_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("resolution_status")
        not in {"OBSERVED_PUBLIC_MARK", "UNKNOWN_COVERAGE_LOSS"}
        or document.get("terminal") is not True
        or document.get("attempt_count") != 1
        or document.get("retry_allowed") is not False
        or document.get("shared_tick_request") is not True
        or document.get("observation_scope")
        != "PUBLIC_MARKET_PATH_ONLY_NO_EXECUTION_STATE"
        or document.get("stop_trigger_semantics")
        != "PUBLIC_PRICE_CONDITION_ONLY_NOT_ORDER_NOT_FILL"
        or document.get("trigger_is_fill") is not False
        or document.get("fill_claim") is not False
        or document.get("position_claim") is not False
        or document.get("pnl_claim") is not False
        or document.get("source_scope") != SOURCE_SCOPE
        or document.get("external_execution_authority")
        != EXTERNAL_EXECUTION_AUTHORITY
        or document.get("executable") is not False
    ):
        raise V32ShadowEvaluationError(code)
    for field in (
        "schedule_digest",
        "schedule_set_digest",
        "batch_intent_digest",
        "observation_tick_digest",
        "raw_evidence_digest",
    ):
        _digest(document.get(field), code)
    _text(document.get("run_id"), code)
    _text(document.get("schedule_id"), code)
    _text(document.get("decision_id"), code)
    _cycle(document.get("cycle_index"), code)
    _time(document.get("outcome_not_before"), code)
    _time(document.get("resolved_at"), code)
    _time(document.get("available_at"), code)
    if document["resolution_status"] == "UNKNOWN_COVERAGE_LOSS":
        if (
            document.get("value") is not None
            or document.get("provider_as_of") is not None
            or document.get("quality") != "UNKNOWN"
            or document.get("missingness") != "UNKNOWN"
            or not isinstance(document.get("coverage_loss_reason"), str)
            or not document["coverage_loss_reason"]
        ):
            raise V32ShadowEvaluationError(code)
    else:
        if (
            document.get("coverage_loss_reason") is not None
            or document.get("quality") not in {"HIGH", "MEDIUM"}
            or document.get("missingness") != "OBSERVED"
        ):
            raise V32ShadowEvaluationError(code)
        value = document.get("value")
        if not isinstance(value, str):
            raise V32ShadowEvaluationError(code)
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise V32ShadowEvaluationError(code) from exc
        if not parsed.is_finite() or parsed <= 0 or canonical_decimal(parsed) != value:
            raise V32ShadowEvaluationError(code)
        _time(document.get("provider_as_of"), code)
    return digest


def _turnover_band(action_label: str) -> str:
    return {
        "WAIT": "NONE",
        "HOLD": "NONE",
        "OPEN_PROBE": "LOW",
        "ADD": "MEDIUM",
        "REDUCE": "MEDIUM",
        "CLOSE": "MEDIUM",
        "REENTER": "MEDIUM",
        "REVERSE": "HIGH",
        "UNKNOWN": "UNKNOWN",
    }[action_label]


def _outcome_result(
    *,
    arm: Mapping[str, Any],
    schedule: Mapping[str, Any],
    receipt_digest: str,
    outcome_missing: bool,
    decision_mark: Decimal,
    outcome_mark: Decimal | None,
) -> dict[str, Any]:
    if not arm:
        raise V32ShadowEvaluationError("V32_SHADOW_OUTCOME_ARM_RESULT_INVALID")
    policy_unknown = arm["derivation_status"] == "UNKNOWN_NOT_COMPUTED"
    if outcome_missing or policy_unknown:
        alignment = "UNKNOWN"
    elif arm["direction_label"] == "NONE":
        alignment = "NON_DIRECTIONAL"
    else:
        assert outcome_mark is not None
        delta = outcome_mark - decision_mark
        if delta == 0:
            alignment = "NON_DIRECTIONAL"
        elif (delta > 0 and arm["direction_label"] == "LONG") or (
            delta < 0 and arm["direction_label"] == "SHORT"
        ):
            alignment = "ALIGNED"
        else:
            alignment = "OPPOSED"
    # A single terminal mark contains no intrahorizon excursion or path.
    path = "UNKNOWN"
    mfe = "UNKNOWN"
    mae = "UNKNOWN"
    miss = "UNKNOWN"
    turnover = _turnover_band(arm["action_label"])
    outcome_fields = {
        "DIRECTIONAL_ALIGNMENT": alignment,
        "PATH_ALIGNMENT": path,
        "MFE": mfe,
        "MAE": mae,
        "OPPORTUNITY_MISS": miss,
    }
    unknown_fields = sorted(
        name for name, label in outcome_fields.items() if label == "UNKNOWN"
    )
    expected_status = (
        "UNKNOWN_COVERAGE_LOSS"
        if outcome_missing
        else "UNKNOWN_BASELINE_NOT_COMPUTED"
        if policy_unknown
        else "TERMINAL_MARK_DIRECTION_ONLY_PATH_UNKNOWN"
    )
    return {
        "arm_id": arm["arm_id"],
        "action_label": arm["action_label"],
        "direction_label": arm["direction_label"],
        "outcome_schedule_id": schedule["schedule_id"],
        "outcome_schedule_digest": schedule["schedule_digest"],
        "outcome_receipt_digest": receipt_digest,
        "directional_alignment": alignment,
        "path_alignment": path,
        "mfe_band": mfe,
        "mae_band": mae,
        "turnover_intent_band": turnover,
        "opportunity_miss_band": miss,
        "unknown_fields": unknown_fields,
        "descriptive_rationale": (
            "Public outcome coverage was unavailable; every outcome field remains unknown."
            if outcome_missing
            else "The frozen baseline policy was not computed; no outcome comparison is claimed."
            if policy_unknown
            else "Only terminal public-mark direction is derivable; intrahorizon path, MFE, MAE, and opportunity cost remain unknown."
        ),
        "comparison_evidence_refs": sorted(
            [schedule["schedule_digest"], receipt_digest]
        ),
        "comparison_status": expected_status,
        "fill_claim": False,
        "position_claim": False,
        "pnl_claim": False,
        "probability_claim": "NONE_ORDINAL_DESCRIPTION_NOT_PROBABILITY",
        "expected_value_allowed": False,
        "executable": False,
    }


def build_v32_shadow_outcome_evaluation_v1(
    *,
    evaluation_id: str,
    shadow_decision_bundle: Mapping[str, Any],
    shadow_decision_bundle_binding: Mapping[str, Any],
    outcome_schedule_set: Mapping[str, Any],
    outcome_schedule_set_binding: Mapping[str, Any],
    outcome_receipt: Mapping[str, Any],
    outcome_receipt_binding: Mapping[str, Any],
    horizon: str,
    evaluated_at: str,
) -> dict[str, Any]:
    """Deterministically bind six policy arms to one terminal public mark."""

    bundle_digest = verify_v32_shadow_decision_bundle_v1(shadow_decision_bundle)
    bundle_binding = _embedded_binding(
        shadow_decision_bundle,
        shadow_decision_bundle_binding,
        schema_id=SHADOW_DECISION_BUNDLE_SCHEMA_ID,
        digest_field=SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
        code="V32_SHADOW_BUNDLE_BINDING_INVALID",
    )
    try:
        schedule_set_digest = verify_v32_outcome_schedule_set(outcome_schedule_set)
    except V32OutcomeTickError as exc:
        raise V32ShadowEvaluationError("V32_SHADOW_SCHEDULE_SET_INVALID") from exc
    schedule_set_binding = _embedded_binding(
        outcome_schedule_set,
        outcome_schedule_set_binding,
        schema_id=SCHEDULE_SET_SCHEMA_ID,
        digest_field=SCHEDULE_SET_DIGEST_FIELD,
        code="V32_SHADOW_SCHEDULE_SET_BINDING_INVALID",
    )
    receipt_digest = _verify_outcome_receipt_intrinsic(outcome_receipt)
    receipt_binding = _embedded_binding(
        outcome_receipt,
        outcome_receipt_binding,
        schema_id=OUTCOME_RECEIPT_SCHEMA_ID,
        digest_field=OUTCOME_RECEIPT_DIGEST_FIELD,
        code="V32_SHADOW_OUTCOME_RECEIPT_BINDING_INVALID",
    )
    matching = [
        row for row in outcome_schedule_set["schedules"] if row["horizon"] == horizon
    ]
    if len(matching) != 1:
        raise V32ShadowEvaluationError("V32_SHADOW_SCHEDULE_HORIZON_INVALID")
    schedule = matching[0]
    if (
        outcome_schedule_set.get("run_id") != shadow_decision_bundle["run_id"]
        or outcome_schedule_set.get("decision_id")
        != shadow_decision_bundle["decision_id"]
        or outcome_schedule_set.get("cycle_index")
        != shadow_decision_bundle["cycle_index"]
        or outcome_schedule_set.get("decision_time") != shadow_decision_bundle["as_of"]
        or outcome_schedule_set.get("sealed_decision_digest")
        != shadow_decision_bundle["selected_plan_binding"]["semantic_digest"]
        or outcome_receipt.get("run_id") != schedule["run_id"]
        or outcome_receipt.get("decision_id") != schedule["decision_id"]
        or outcome_receipt.get("cycle_index") != schedule["cycle_index"]
        or outcome_receipt.get("schedule_id") != schedule["schedule_id"]
        or outcome_receipt.get("schedule_digest") != schedule["schedule_digest"]
        or outcome_receipt.get("schedule_set_digest") != schedule_set_digest
        or outcome_receipt.get("horizon") != horizon
        or outcome_receipt.get("outcome_not_before") != schedule["outcome_not_before"]
    ):
        raise V32ShadowEvaluationError("V32_SHADOW_OUTCOME_CROSS_BINDING_INVALID")
    receipt_not_before = _moment(
        outcome_receipt["outcome_not_before"], "V32_SHADOW_OUTCOME_NOT_DUE"
    )
    receipt_available = _moment(
        outcome_receipt["available_at"], "V32_SHADOW_OUTCOME_NOT_DUE"
    )
    receipt_resolved = _moment(
        outcome_receipt["resolved_at"], "V32_SHADOW_OUTCOME_NOT_DUE"
    )
    if receipt_available < receipt_not_before or receipt_resolved < receipt_available:
        raise V32ShadowEvaluationError("V32_SHADOW_OUTCOME_NOT_DUE")
    if outcome_receipt["provider_as_of"] is not None and _moment(
        outcome_receipt["provider_as_of"], "V32_SHADOW_OUTCOME_NOT_DUE"
    ) > receipt_available:
        raise V32ShadowEvaluationError("V32_SHADOW_OUTCOME_TIME_ORDER_INVALID")
    evaluated = _time(evaluated_at, "V32_SHADOW_EVALUATED_AT_INVALID")
    evaluated_moment = _moment(evaluated, "V32_SHADOW_EVALUATED_AT_INVALID")
    if (
        evaluated_moment
        < _moment(schedule["outcome_not_before"], "V32_SHADOW_OUTCOME_NOT_DUE")
        or evaluated_moment
        < _moment(outcome_receipt["resolved_at"], "V32_SHADOW_OUTCOME_NOT_DUE")
        or _moment(
            shadow_decision_bundle["created_at"], "V32_SHADOW_BUNDLE_TIME_INVALID"
        )
        >= _moment(schedule["outcome_not_before"], "V32_SHADOW_OUTCOME_NOT_DUE")
    ):
        raise V32ShadowEvaluationError("V32_SHADOW_OUTCOME_NOT_DUE")
    outcome_missing = outcome_receipt["resolution_status"] == "UNKNOWN_COVERAGE_LOSS"
    arms = {row["arm_id"]: row for row in shadow_decision_bundle["arms"]}
    decision_mark = Decimal(shadow_decision_bundle["decision_mark_snapshot"]["value"])
    outcome_mark = (
        None if outcome_missing else Decimal(str(outcome_receipt["value"]))
    )
    normalized = [
        _outcome_result(
            arm=arms[arm_id],
            schedule=schedule,
            receipt_digest=receipt_digest,
            outcome_missing=outcome_missing,
            decision_mark=decision_mark,
            outcome_mark=outcome_mark,
        )
        for arm_id in SHADOW_ARM_IDS
    ]
    by_id = {row["arm_id"]: row for row in normalized}
    if (
        len(normalized) != len(SHADOW_ARM_IDS)
        or set(by_id) != set(SHADOW_ARM_IDS)
    ):
        raise V32ShadowEvaluationError("V32_SHADOW_OUTCOME_RESULT_SET_INVALID")
    document = {
        "schema_id": SHADOW_OUTCOME_EVALUATION_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": _text(
            evaluation_id, "V32_SHADOW_OUTCOME_EVALUATION_ID_INVALID"
        ),
        "run_id": shadow_decision_bundle["run_id"],
        "decision_id": shadow_decision_bundle["decision_id"],
        "cycle_index": shadow_decision_bundle["cycle_index"],
        "decision_as_of": shadow_decision_bundle["as_of"],
        "evaluated_at": evaluated,
        "horizon": horizon,
        "shadow_decision_bundle_binding": bundle_binding,
        "outcome_schedule_set_binding": schedule_set_binding,
        "outcome_schedule_id": schedule["schedule_id"],
        "outcome_schedule_digest": schedule["schedule_digest"],
        "outcome_not_before": schedule["outcome_not_before"],
        "outcome_receipt_binding": receipt_binding,
        "outcome_resolution_status": outcome_receipt["resolution_status"],
        "arm_ids": list(SHADOW_ARM_IDS),
        "arm_results": [by_id[arm_id] for arm_id in SHADOW_ARM_IDS],
        "comparison_policy": (
            "SAME_SEALED_DECISION_CONTEXT_FROZEN_POLICY_RECEIPTS_AND_SAME_"
            "TERMINAL_SCHEDULE_RECEIPT_FOR_ALL_ARMS_NO_CALLER_OUTCOME_LABELS"
        ),
        "mfe_mae_semantics": (
            "UNKNOWN_TERMINAL_MARK_CANNOT_IDENTIFY_INTRAHORIZON_PATH_OR_EXCURSION"
        ),
        "numeric_market_values_copied_into_arm_results": False,
        "probability_claim": "NONE_ORDINAL_DESCRIPTION_NOT_PROBABILITY",
        "expected_value_allowed": False,
        "fill_claim": False,
        "position_claim": False,
        "pnl_claim": False,
        "source_scope": SOURCE_SCOPE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
    }
    return self_digest(document, SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD)


def verify_v32_shadow_outcome_evaluation_v1(
    document: Mapping[str, Any],
    *,
    shadow_decision_bundle: Mapping[str, Any],
    outcome_schedule_set: Mapping[str, Any],
    outcome_receipt: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _OUTCOME_EVALUATION_FIELDS:
        raise V32ShadowEvaluationError("V32_SHADOW_OUTCOME_EVALUATION_INVALID")
    try:
        supplied = verify_self_digest(
            document, SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD
        )
        rebuilt = build_v32_shadow_outcome_evaluation_v1(
            evaluation_id=document["evaluation_id"],
            shadow_decision_bundle=shadow_decision_bundle,
            shadow_decision_bundle_binding=document["shadow_decision_bundle_binding"],
            outcome_schedule_set=outcome_schedule_set,
            outcome_schedule_set_binding=document["outcome_schedule_set_binding"],
            outcome_receipt=outcome_receipt,
            outcome_receipt_binding=document["outcome_receipt_binding"],
            horizon=document["horizon"],
            evaluated_at=document["evaluated_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ShadowEvaluationError):
            raise
        raise V32ShadowEvaluationError(
            "V32_SHADOW_OUTCOME_EVALUATION_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD]
    ):
        raise V32ShadowEvaluationError(
            "V32_SHADOW_OUTCOME_EVALUATION_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "ACTION_LABELS",
    "MARKET_ANALYSIS_DIGEST_FIELD",
    "MARKET_ANALYSIS_SCHEMA_ID",
    "OPPORTUNITY_SET_DIGEST_FIELD",
    "OPPORTUNITY_SET_SCHEMA_ID",
    "PIT_REGISTRY_DIGEST_FIELD",
    "PIT_REGISTRY_SCHEMA_ID",
    "POLICY_DESCRIPTORS",
    "POLICY_DIGESTS",
    "POLICY_VERSION",
    "SELECTED_PLAN_DIGEST_FIELD",
    "SELECTED_PLAN_SCHEMA_ID",
    "SHADOW_ARM_IDS",
    "SHADOW_DECISION_BUNDLE_DIGEST_FIELD",
    "SHADOW_DECISION_BUNDLE_SCHEMA_ID",
    "SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD",
    "SHADOW_OUTCOME_EVALUATION_SCHEMA_ID",
    "V32ShadowEvaluationError",
    "build_v32_shadow_decision_bundle_v1",
    "build_v32_shadow_outcome_evaluation_v1",
    "verify_v32_shadow_decision_bundle_v1",
    "verify_v32_shadow_outcome_evaluation_v1",
]
