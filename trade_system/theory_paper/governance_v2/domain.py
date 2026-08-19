"""Pure successor-v2 multi-timescale decision-governance domain.

This module owns no filesystem, account, portfolio, order, or network
capability.  It has two deliberately separate responsibilities:

* audit immutable legacy v1 cycles without inventing missing intent; and
* fail closed on a future governance card before a successor paper action is
  allowed to reach a portfolio adapter.

The historical audit is diagnostic.  A legacy violation is preserved as
evidence and never repaired by rewriting the source cycle.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

FRAMEWORK_ID = "THEORY_PAPER_MULTI_TIMESCALE_DECISION_GOVERNANCE.v2"
FRAMEWORK_SCHEMA = "theory-paper-decision-governance-framework.v2"
SIDECAR_SCHEMA = "theory-paper-decision-governance-sidecar.v2"
CARD_SCHEMA = "theory-paper-decision-governance-card.v2"
HISTORICAL_MODE = "HISTORICAL_SHADOW_AUDIT"
UNKNOWN = "UNKNOWN"
LEGACY_UNKNOWN_STATE = "UNKNOWN_LEGACY_UNDECLARED"

DECISION_LAYERS = (
    "STRATEGIC_HYPOTHESIS",
    "STRUCTURAL_EVIDENCE",
    "RISK_CONTROL",
    "TACTICAL_EXECUTION",
    "REVIEW_UPDATE",
)
STRATEGIC_STATES = (
    "A_VALID",
    "B_TACTICAL_DISTURBANCE",
    "C_CHALLENGED",
    "D_INVALIDATED",
)
SIGNAL_CLASSES = frozenset(
    {"STRUCTURAL", "CONFIRMATORY", "TACTICAL", "NOISE", "RISK_ONLY"}
)
ACTION_INTENTS = frozenset(
    {
        "STRATEGIC_ENTRY",
        "STRATEGIC_ADD",
        "RISK_REDUCTION",
        "RISK_EXIT",
        "TACTICAL_EXIT",
        "STRATEGIC_INVALIDATION_EXIT",
        "PROTECTION_UPDATE",
        "EXECUTION_ONLY",
        "HOLD",
    }
)
NEW_RISK_ACTIONS = frozenset(
    {"OPEN_LONG", "OPEN_SHORT", "ADD_LONG", "ADD_SHORT"}
)
EXIT_OR_REDUCE_ACTIONS = frozenset({"REDUCE", "EXIT"})
LOWER_TIMEFRAMES = frozenset({"realtime", "15m", "1h"})
STRUCTURAL_TIMEFRAMES = frozenset({"4h", "1d"})
ACTION_DIRECTIONS = {
    "OPEN_LONG": "LONG",
    "ADD_LONG": "LONG",
    "OPEN_SHORT": "SHORT",
    "ADD_SHORT": "SHORT",
}
EXPECTED_PHI_DIRECTIONS = {
    "PHI_UPWARD_CONTINUATION": "LONG",
    "PHI_DOWNWARD_CONTINUATION": "SHORT",
    "PHI_ABSORPTION_REVERSAL": "CONDITIONAL",
    "PHI_BREAKOUT": "CONDITIONAL",
    "PHI_RANGE": "NEUTRAL",
    "PHI_OTHER_UNKNOWN": "UNKNOWN",
}
FORBIDDEN_CAUSE_CLASSES = frozenset(
    {"PURE_LIQUIDITY", "RANDOM_COMPATIBLE", "UNKNOWN"}
)
REENTRY_REQUIRED_INTENTS = frozenset(
    {"RISK_REDUCTION", "RISK_EXIT", "TACTICAL_EXIT"}
)
SCHEDULED_REVIEW_TRIGGERS = frozenset(
    {
        "SCHEDULED_4H_CLOSE",
        "SCHEDULED_1D_CLOSE",
        "HYPOTHESIS_EXPIRY",
    }
)
ALL_REVIEW_TRIGGERS = SCHEDULED_REVIEW_TRIGGERS | frozenset(
    {"QUALIFIED_MAJOR_EVENT", "TACTICAL_UPDATE", "NO_CHANGE"}
)
_CYCLE_ID_RE = re.compile(r"^cycle-(\d{4})$")
HORIZON_POLICIES = {
    "TACTICAL": {
        "evaluation_timeframes": frozenset({"15m", "1h"}),
        "minimum_complete_windows": 1,
    },
    "OPERATIONAL": {
        "evaluation_timeframes": frozenset({"1h", "4h"}),
        "minimum_complete_windows": 2,
    },
    "STRATEGIC": {
        "evaluation_timeframes": frozenset({"4h", "1d"}),
        "minimum_complete_windows": 2,
    },
}
TIMEFRAME_SECONDS = {
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}
ACTION_ALLOWED_INTENTS = {
    "OPEN_LONG": frozenset({"STRATEGIC_ENTRY"}),
    "OPEN_SHORT": frozenset({"STRATEGIC_ENTRY"}),
    "ADD_LONG": frozenset({"STRATEGIC_ADD"}),
    "ADD_SHORT": frozenset({"STRATEGIC_ADD"}),
    "REDUCE": frozenset({"RISK_REDUCTION"}),
    "EXIT": frozenset(
        {"RISK_EXIT", "TACTICAL_EXIT", "STRATEGIC_INVALIDATION_EXIT"}
    ),
    "MODIFY_ORDERS": frozenset({"PROTECTION_UPDATE", "EXECUTION_ONLY"}),
    "CANCEL_ORDER": frozenset({"PROTECTION_UPDATE", "EXECUTION_ONLY"}),
    "KEEP": frozenset({"HOLD"}),
    "ABSTAIN": frozenset({"HOLD"}),
}


class GovernanceV2Error(ValueError):
    """Stable fail-closed domain error."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GovernanceV2Error("NON_CANONICAL_JSON") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GovernanceV2Error("TIMESTAMP_NOT_CANONICAL_UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GovernanceV2Error("TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise GovernanceV2Error("TIMESTAMP_NOT_AWARE")
    return parsed.astimezone(timezone.utc)


def _cycle_number(value: Any) -> int:
    if not isinstance(value, str):
        raise GovernanceV2Error("CYCLE_ID_INVALID")
    match = _CYCLE_ID_RE.fullmatch(value)
    if match is None:
        raise GovernanceV2Error("CYCLE_ID_INVALID")
    return int(match.group(1))


def _mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GovernanceV2Error(reason)
    return value


def _list(value: Any, reason: str) -> list[Any]:
    if not isinstance(value, list):
        raise GovernanceV2Error(reason)
    return value


def _strings(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        return None
    return list(value)


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    errors: list[str],
    prefix: str,
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        errors.append(f"{prefix}:MISSING_FIELDS:" + ",".join(missing))
    if unknown:
        errors.append(f"{prefix}:UNKNOWN_FIELDS:" + ",".join(unknown))


def validate_framework_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if config.get("framework_id") != FRAMEWORK_ID:
        raise GovernanceV2Error("FRAMEWORK_ID_MISMATCH")
    if config.get("schema_version") != FRAMEWORK_SCHEMA:
        raise GovernanceV2Error("FRAMEWORK_SCHEMA_MISMATCH")
    if (
        config.get("status") != "SHADOW_CANDIDATE_NOT_ACTIVATED"
        or config.get("execution_scope")
        != "PUBLIC_DATA_LOCAL_PAPER_GOVERNANCE_ONLY"
    ):
        raise GovernanceV2Error("FRAMEWORK_AUTHORITY_BOUNDARY_MISMATCH")
    if tuple(config.get("decision_layers", [])) != DECISION_LAYERS:
        raise GovernanceV2Error("FRAMEWORK_DECISION_LAYERS_MISMATCH")
    if set(config.get("signal_class_registry", [])) != SIGNAL_CLASSES:
        raise GovernanceV2Error("FRAMEWORK_SIGNAL_CLASSES_MISMATCH")
    if set(config.get("action_intent_registry", [])) != ACTION_INTENTS:
        raise GovernanceV2Error("FRAMEWORK_ACTION_INTENTS_MISMATCH")
    if config.get("phi_direction_registry") != EXPECTED_PHI_DIRECTIONS:
        raise GovernanceV2Error("FRAMEWORK_PHI_DIRECTIONS_MISMATCH")

    profile = _mapping(
        config.get("timeframe_role_profile"), "FRAMEWORK_ROLE_PROFILE_MISSING"
    )
    roles = _list(profile.get("roles"), "FRAMEWORK_ROLE_REGISTRY_MISSING")
    timeframes = [row.get("timeframe") for row in roles if isinstance(row, Mapping)]
    if timeframes != ["1w", "1d", "4h", "1h", "15m"]:
        raise GovernanceV2Error("FRAMEWORK_ROLE_ORDER_MISMATCH")
    if (
        profile.get("strategic_context_timeframe") != "1d"
        or profile.get("strategic_operational_owner_timeframe") != "4h"
        or profile.get("timeframe_voting") != "FORBIDDEN"
    ):
        raise GovernanceV2Error("FRAMEWORK_ROLE_AUTHORITY_MISMATCH")

    promotion = _mapping(
        config.get("promotion_contract"), "FRAMEWORK_PROMOTION_CONTRACT_MISSING"
    )
    if (
        promotion.get("minimum_distinct_observation_windows") != 2
        or promotion.get("minimum_independent_confirmation_groups") != 2
        or promotion.get("promotion_is_automatic_state_transition") is not False
        or promotion.get("missing_condition_disposition") != "REJECT_PROMOTION"
    ):
        raise GovernanceV2Error("FRAMEWORK_PROMOTION_INVARIANT_MISMATCH")

    machine = _mapping(
        config.get("strategic_state_machine"), "FRAMEWORK_STATE_MACHINE_MISSING"
    )
    if tuple(machine.get("state_registry", [])) != STRATEGIC_STATES:
        raise GovernanceV2Error("FRAMEWORK_STATE_REGISTRY_MISMATCH")
    if (
        machine.get("initial_state") != "A_VALID"
        or machine.get("terminal_state") != "D_INVALIDATED"
        or machine.get("same_hypothesis_may_leave_terminal_state") is not False
        or machine.get("tactical_state_may_change_strategic_direction") is not False
    ):
        raise GovernanceV2Error("FRAMEWORK_STATE_INVARIANT_MISMATCH")
    legal = _mapping(
        machine.get("legal_transitions"), "FRAMEWORK_TRANSITIONS_MISSING"
    )
    if set(legal) != set(STRATEGIC_STATES):
        raise GovernanceV2Error("FRAMEWORK_TRANSITION_SOURCE_MISMATCH")
    for source, destinations in legal.items():
        if not isinstance(destinations, list) or any(
            destination not in STRATEGIC_STATES for destination in destinations
        ):
            raise GovernanceV2Error(
                f"FRAMEWORK_TRANSITION_DESTINATION_INVALID:{source}"
            )
    if legal.get("D_INVALIDATED") != ["D_INVALIDATED"]:
        raise GovernanceV2Error("FRAMEWORK_TERMINAL_STATE_NOT_TERMINAL")

    action_contract = _mapping(
        config.get("action_contract"), "FRAMEWORK_ACTION_CONTRACT_MISSING"
    )
    if (
        action_contract.get("risk_or_tactical_action_changes_hypothesis_state")
        is not False
        or action_contract.get("new_risk_allowed_states") != ["A_VALID"]
        or action_contract.get("strategic_invalidation_exit_requires_state")
        != "D_INVALIDATED"
        or action_contract.get("unknown_action_intent_disposition") != "REJECT"
    ):
        raise GovernanceV2Error("FRAMEWORK_ACTION_INVARIANT_MISMATCH")
    if set(
        action_contract.get(
            "reentry_required_intents_when_hypothesis_not_invalidated", []
        )
    ) != REENTRY_REQUIRED_INTENTS:
        raise GovernanceV2Error("FRAMEWORK_REENTRY_INTENTS_MISMATCH")

    reentry = _mapping(
        config.get("reentry_contract"), "FRAMEWORK_REENTRY_CONTRACT_MISSING"
    )
    if (
        reentry.get("default_policy")
        != "SEEK_REENTRY_WHILE_HYPOTHESIS_REMAINS_NOT_INVALIDATED"
        or reentry.get("cancel_on_state") != "D_INVALIDATED"
        or reentry.get("missing_contract_disposition") != "REJECT_ACTION"
    ):
        raise GovernanceV2Error("FRAMEWORK_REENTRY_INVARIANT_MISMATCH")
    if reentry.get("restoration_stages") != [
        "MINIMUM_VERIFICATION_POSITION",
        "STRUCTURAL_RECONFIRMATION_POSITION",
        "PLANNED_POSITION_COMPLETION",
    ]:
        raise GovernanceV2Error("FRAMEWORK_REENTRY_STAGES_MISMATCH")

    evaluation = _mapping(
        config.get("evaluation_contract"), "FRAMEWORK_EVALUATION_CONTRACT_MISSING"
    )
    if (
        evaluation.get("horizon_classes")
        != ["TACTICAL", "OPERATIONAL", "STRATEGIC"]
        or
        evaluation.get("before_horizon_end_status")
        != "INTERIM_PATH_OBSERVATION_NOT_CORRECTNESS"
        or evaluation.get("short_horizon_result_may_validate_long_horizon_decision")
        is not False
        or evaluation.get("pnl_may_validate_strategy_hypothesis") is not False
        or evaluation.get("evaluate_against_frozen_rules") is not True
    ):
        raise GovernanceV2Error("FRAMEWORK_EVALUATION_INVARIANT_MISMATCH")

    review_clock = _mapping(
        config.get("review_clock_contract"),
        "FRAMEWORK_REVIEW_CLOCK_CONTRACT_MISSING",
    )
    if (
        set(review_clock.get("strategic_review_triggers", []))
        != {
            "SCHEDULED_4H_CLOSE",
            "SCHEDULED_1D_CLOSE",
            "HYPOTHESIS_EXPIRY",
            "QUALIFIED_MAJOR_EVENT",
        }
        or review_clock.get("tactical_review_may_rewrite_strategy") is not False
        or review_clock.get("risk_review_may_rewrite_strategy") is not False
        or review_clock.get("qualified_event_requires_typed_evidence") is not True
        or review_clock.get("free_text_event_exception") != "FORBIDDEN"
    ):
        raise GovernanceV2Error("FRAMEWORK_REVIEW_CLOCK_INVARIANT_MISMATCH")

    if set(config.get("direct_strategic_transition_forbidden_inputs", [])) != {
        "CURRENT_PNL",
        "UNREALIZED_PNL",
        "RECENT_ACTION_OUTCOME",
        "EMOTIONAL_PRESSURE",
        "SALIENCE",
        "SINGLE_LOWER_TIMEFRAME_BAR",
        "UNCONFIRMED_HEADLINE",
        "FREE_TEXT_NARRATIVE_ONLY",
    }:
        raise GovernanceV2Error("FRAMEWORK_FORBIDDEN_INPUTS_MISMATCH")

    invariants = _mapping(
        config.get("invariants"), "FRAMEWORK_INVARIANTS_MISSING"
    )
    required_invariants = {
        "available_at_not_after_decision_at": True,
        "low_timeframe_direct_strategic_override": "FORBIDDEN",
        "risk_action_implies_thesis_invalidation": False,
        "short_result_implies_long_decision_correct": False,
        "tactical_exit_without_reentry_contract": "FORBIDDEN",
        "same_invalidated_hypothesis_reactivation": "FORBIDDEN",
        "numeric_probability_or_unvalidated_weight": "FORBIDDEN",
        "participant_psychology_inference_as_fact": "FORBIDDEN",
        "paper_action_authority": "NONE_SHADOW_ONLY",
        "v1_artifact_mutation": "FORBIDDEN",
    }
    for field, expected in required_invariants.items():
        if invariants.get(field) != expected:
            raise GovernanceV2Error(f"FRAMEWORK_INVARIANT_MISMATCH:{field}")

    legacy = _mapping(
        config.get("legacy_audit"), "FRAMEWORK_LEGACY_AUDIT_MISSING"
    )
    if (
        legacy.get("mode") != HISTORICAL_MODE
        or legacy.get("undeclared_strategic_state") != LEGACY_UNKNOWN_STATE
        or legacy.get("do_not_invent_missing_intent_or_reentry_contract")
        is not True
        or legacy.get("legacy_violation_does_not_rewrite_source") is not True
    ):
        raise GovernanceV2Error("FRAMEWORK_LEGACY_AUDIT_INVARIANT_MISMATCH")

    return {
        "valid": True,
        "framework_id": FRAMEWORK_ID,
        "config_digest": canonical_digest(config),
    }


def _symbol_map(rows: Any, reason: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in _list(rows, reason):
        item = _mapping(row, reason)
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol in result:
            raise GovernanceV2Error(reason)
        result[symbol] = item
    if not result:
        raise GovernanceV2Error(reason)
    return result


def _source_parts(
    source: Mapping[str, Any],
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    dict[str, Mapping[str, Any]],
    dict[str, Mapping[str, Any]],
]:
    if source.get("mode") != HISTORICAL_MODE:
        raise GovernanceV2Error("SOURCE_MODE_NOT_HISTORICAL_AUDIT")
    analysis = _mapping(source.get("analysis"), "SOURCE_ANALYSIS_MISSING")
    decision_receipt = _mapping(source.get("decision"), "SOURCE_DECISION_MISSING")
    validated = _mapping(
        decision_receipt.get("validated_decision"),
        "SOURCE_VALIDATED_DECISION_MISSING",
    )
    cycle_id = source.get("cycle_id")
    if analysis.get("cycle_id") != cycle_id or validated.get("cycle_id") != cycle_id:
        raise GovernanceV2Error("SOURCE_CYCLE_BINDING_MISMATCH")
    decision_at = analysis.get("decision_at")
    if validated.get("decision_at") != decision_at:
        raise GovernanceV2Error("SOURCE_DECISION_TIME_BINDING_MISMATCH")
    parse_utc(decision_at)
    analysis_symbols = _symbol_map(
        analysis.get("symbols"), "SOURCE_ANALYSIS_SYMBOLS_INVALID"
    )
    decision_symbols = _symbol_map(
        validated.get("symbol_decisions"), "SOURCE_DECISION_SYMBOLS_INVALID"
    )
    if list(analysis_symbols) != list(decision_symbols):
        raise GovernanceV2Error("SOURCE_SYMBOL_ORDER_MISMATCH")
    return analysis, decision_receipt, validated, analysis_symbols, decision_symbols


def _timeframe_roles(symbol_analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    multiscale = _mapping(
        symbol_analysis.get("multi_scale_state_belief"),
        "SOURCE_MULTISCALE_STATE_MISSING",
    )
    rows: list[dict[str, Any]] = []
    for raw in _list(
        multiscale.get("role_states"), "SOURCE_TIMEFRAME_ROLES_MISSING"
    ):
        row = _mapping(raw, "SOURCE_TIMEFRAME_ROLE_INVALID")
        rows.append(
            {
                "timeframe": row.get("timeframe"),
                "role": row.get("role"),
                "direction_state": row.get("direction_state"),
                "source_status": row.get("state_status"),
            }
        )
    return rows


def _operational_direction(symbol_analysis: Mapping[str, Any]) -> str:
    state = _mapping(
        symbol_analysis.get("multi_scale_state_belief"),
        "SOURCE_MULTISCALE_STATE_MISSING",
    ).get("operational_bias")
    return str(state) if state in {"UP", "DOWN", "RANGE", "TRANSITION"} else UNKNOWN


def _action_effect(action: str) -> str:
    if action in NEW_RISK_ACTIONS:
        return "NEW_RISK"
    if action in EXIT_OR_REDUCE_ACTIONS:
        return "EXIT_OR_REDUCTION"
    if action in {"MODIFY_ORDERS", "CANCEL_ORDER"}:
        return "EXECUTION_OR_PROTECTION"
    if action in {"KEEP", "ABSTAIN"}:
        return "NO_DIRECT_PORTFOLIO_CHANGE"
    return "UNKNOWN_EFFECT"


def _prior_symbol_rows(
    previous_sidecar: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if previous_sidecar is None:
        return {}
    return _symbol_map(
        previous_sidecar.get("symbols"), "PRIOR_SIDECAR_SYMBOLS_INVALID"
    )


def _violation(
    destination: list[dict[str, Any]],
    code: str,
    *,
    severity: str,
    symbol: str,
    evidence_refs: Sequence[str],
    consequence: str,
) -> None:
    payload = {
        "code": code,
        "severity": severity,
        "symbol": symbol,
        "evidence_refs": sorted(set(str(item) for item in evidence_refs if item)),
        "consequence": consequence,
    }
    payload["violation_id"] = "GV-" + canonical_digest(payload)[:20]
    destination.append(payload)


def build_legacy_audit_sidecar(
    source: Mapping[str, Any],
    config: Mapping[str, Any],
    previous_sidecar: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit one immutable v1 cycle and preserve undeclared fields as unknown."""

    config_verdict = validate_framework_config(config)
    (
        analysis,
        decision_receipt,
        validated,
        analysis_symbols,
        decision_symbols,
    ) = _source_parts(source)
    decision_at = str(analysis["decision_at"])
    previous_rows = _prior_symbol_rows(previous_sidecar)
    observable_registry = _mapping(
        config.get("observable_permission_registry"),
        "FRAMEWORK_OBSERVABLE_REGISTRY_MISSING",
    )
    phi_registry = _mapping(
        config.get("phi_direction_registry"),
        "FRAMEWORK_PHI_DIRECTION_REGISTRY_MISSING",
    )
    symbol_rows: list[dict[str, Any]] = []
    all_violations: list[dict[str, Any]] = []

    for symbol, symbol_analysis in analysis_symbols.items():
        decision = decision_symbols[symbol]
        action = str(decision.get("action") or "")
        selected_phi = str(decision.get("selected_phi_id") or "")
        operational = _operational_direction(symbol_analysis)
        action_direction = ACTION_DIRECTIONS.get(action, UNKNOWN)
        declared_phi_direction = str(phi_registry.get(selected_phi, UNKNOWN))
        source_refs = [
            str(analysis.get("analysis_digest") or ""),
            str(decision_receipt.get("decision_receipt_digest") or ""),
        ]
        violations: list[dict[str, Any]] = []

        _violation(
            violations,
            "STRATEGIC_HYPOTHESIS_INSTANCE_MISSING",
            severity="BLOCKING",
            symbol=symbol,
            evidence_refs=source_refs,
            consequence=(
                "The per-cycle selected PHI cannot prove continuity of one strategic "
                "hypothesis across cycles."
            ),
        )
        _violation(
            violations,
            "STRATEGIC_STATE_MISSING",
            severity="BLOCKING",
            symbol=symbol,
            evidence_refs=source_refs,
            consequence=(
                "A/B/C/D state and a typed transition receipt cannot be reconstructed."
            ),
        )
        _violation(
            violations,
            "STRATEGIC_REVIEW_CLOCK_MISSING",
            severity="BLOCKING",
            symbol=symbol,
            evidence_refs=source_refs,
            consequence=(
                "expiry_at is a hypothesis deadline, not an exclusive strategic review clock."
            ),
        )
        _violation(
            violations,
            "SIGNAL_PERMISSION_LEDGER_MISSING",
            severity="BLOCKING",
            symbol=symbol,
            evidence_refs=source_refs,
            consequence=(
                "The source has timeframe observations but no signal class, permission, "
                "or promotion receipt."
            ),
        )
        _violation(
            violations,
            "EVALUATION_HORIZON_CLASS_MISSING",
            severity="BLOCKING",
            symbol=symbol,
            evidence_refs=source_refs,
            consequence=(
                "The source cannot distinguish a local path observation from strategic correctness."
            ),
        )

        effect = _action_effect(action)
        _violation(
            violations,
            "ACTION_INTENT_MISSING",
            severity=(
                "WARNING"
                if effect == "NO_DIRECT_PORTFOLIO_CHANGE"
                else "BLOCKING"
            ),
            symbol=symbol,
            evidence_refs=source_refs,
            consequence=(
                "Portfolio effect is present, but strategic, risk, tactical, and "
                "execution intent are not typed independently."
            ),
        )
        if effect == "NEW_RISK":
            _violation(
                violations,
                "NEW_RISK_WITHOUT_GOVERNANCE_PERMISSION",
                severity="BLOCKING",
                symbol=symbol,
                evidence_refs=source_refs,
                consequence=(
                    "Geometry and portfolio risk approval do not prove strategic authority."
                ),
            )
            expected_parent = (
                "LONG"
                if operational == "UP"
                else "SHORT"
                if operational == "DOWN"
                else UNKNOWN
            )
            if expected_parent == UNKNOWN or action_direction != expected_parent:
                _violation(
                    violations,
                    "LOWER_LAYER_PARENT_OVERRIDE_UNGUARDED",
                    severity="BLOCKING",
                    symbol=symbol,
                    evidence_refs=source_refs,
                    consequence=(
                        "New risk is opposite to, or unsupported by, the 4H parent and "
                        "there is no promotion receipt."
                    ),
                )
            if declared_phi_direction in {"LONG", "SHORT"} and (
                declared_phi_direction != action_direction
            ):
                _violation(
                    violations,
                    "PHI_ACTION_DIRECTION_UNBOUND",
                    severity="BLOCKING",
                    symbol=symbol,
                    evidence_refs=source_refs,
                    consequence=(
                        "The selected hypothesis direction and the action direction are not bound."
                    ),
                )
        if effect == "EXIT_OR_REDUCTION":
            _violation(
                violations,
                "EXIT_OR_REDUCTION_INTENT_UNDECLARED",
                severity="BLOCKING",
                symbol=symbol,
                evidence_refs=source_refs,
                consequence=(
                    "The source cannot distinguish risk control, tactical exit, or "
                    "strategic invalidation."
                ),
            )
            _violation(
                violations,
                "REENTRY_CONTRACT_UNREPRESENTABLE_IN_V1",
                severity="BLOCKING",
                symbol=symbol,
                evidence_refs=source_refs,
                consequence=(
                    "The v1 action schema has no typed re-entry contract and cannot "
                    "fail closed when it is absent."
                ),
            )

        support = _mapping(
            decision.get("support_predicate"),
            "SOURCE_SUPPORT_PREDICATE_MISSING",
        )
        observable_id = str(support.get("observable_id") or "")
        permission = _mapping(
            observable_registry.get(observable_id),
            "FRAMEWORK_OBSERVABLE_PERMISSION_MISSING",
        )
        if permission.get("maximum_permission") != "STRUCTURAL_EVIDENCE":
            _violation(
                violations,
                "SHORT_HORIZON_SUPPORT_CAN_UPGRADE_HYPOTHESIS",
                severity="BLOCKING",
                symbol=symbol,
                evidence_refs=source_refs,
                consequence=(
                    "A tactical or confirmatory predicate can produce SUPPORTED_ACTIVE "
                    "without horizon-compatible strategic evaluation."
                ),
            )

        prior_row = previous_rows.get(symbol)
        prior_phi = (
            _mapping(prior_row.get("hypothesis_ledger"), "PRIOR_HYPOTHESIS_LEDGER_INVALID")
            .get("declared_phi_id")
            if isinstance(prior_row, Mapping)
            else None
        )
        if isinstance(prior_phi, str) and prior_phi != selected_phi:
            _violation(
                violations,
                "STRATEGIC_PATH_CHANGED_WITHOUT_STATE_TRANSITION",
                severity="BLOCKING",
                symbol=symbol,
                evidence_refs=source_refs,
                consequence=(
                    "The selected path changed between cycles without preserving a "
                    "strategic hypothesis instance or transition receipt."
                ),
            )

        timeframe_rows = _timeframe_roles(symbol_analysis)
        signal_rows = [
            {
                "signal_id": "LEGACY-"
                + canonical_digest(
                    {
                        "symbol": symbol,
                        "decision_at": decision_at,
                        "timeframe": row["timeframe"],
                        "direction_state": row["direction_state"],
                    }
                )[:20],
                "source_available_at": decision_at,
                "timeframe": row["timeframe"],
                "legacy_role": row["role"],
                "observed_value": row["direction_state"],
                "signal_class": "UNDECLARED_LEGACY",
                "decision_permission": "UNDECLARED_LEGACY",
                "promotion_receipt_id": None,
            }
            for row in timeframe_rows
        ]
        signal_rows.append(
            {
                "signal_id": "LEGACY-"
                + canonical_digest(
                    {
                        "symbol": symbol,
                        "decision_at": decision_at,
                        "predicate": support,
                    }
                )[:20],
                "source_available_at": decision_at,
                "timeframe": permission.get("default_timeframe"),
                "legacy_role": "SUPPORT_PREDICATE",
                "observed_value": copy.deepcopy(dict(support)),
                "signal_class": permission.get("default_signal_class"),
                "decision_permission": permission.get("maximum_permission"),
                "promotion_receipt_id": None,
            }
        )

        behavior = {
            "behavior_entry_id": "BEH-"
            + canonical_digest(
                {
                    "symbol": symbol,
                    "decision_at": decision_at,
                    "action": action,
                    "decision_digest": validated.get("decision_digest"),
                }
            )[:20],
            "v1_action": action,
            "mechanical_effect": effect,
            "declared_action_intent": "UNDECLARED_LEGACY",
            "changes_strategic_state": "UNKNOWN_LEGACY",
            "reentry_contract": None,
            "evaluation_horizon_class": "UNDECLARED_LEGACY",
            "source_refs": source_refs,
        }
        hypothesis = {
            "hypothesis_entry_id": "HYP-"
            + canonical_digest(
                {
                    "symbol": symbol,
                    "decision_at": decision_at,
                    "selected_phi_id": selected_phi,
                    "thesis": decision.get("thesis"),
                }
            )[:20],
            "hypothesis_instance_id": None,
            "declared_phi_id": selected_phi,
            "declared_thesis": decision.get("thesis"),
            "strategic_direction": declared_phi_direction,
            "strategic_state": LEGACY_UNKNOWN_STATE,
            "review_clock": None,
            "target_horizon": None,
            "source_expiry_at": decision.get("expiry_at"),
            "source_refs": source_refs,
        }
        symbol_row = {
            "symbol": symbol,
            "source_operational_4h_direction": operational,
            "hypothesis_ledger": hypothesis,
            "signal_ledger": signal_rows,
            "behavior_ledger": behavior,
            "violations": sorted(
                violations, key=lambda row: (row["code"], row["violation_id"])
            ),
            "governance_disposition": "BLOCKED_LEGACY_SCHEMA_INCOMPLETE",
        }
        symbol_rows.append(symbol_row)
        all_violations.extend(violations)

    counts = Counter(row["code"] for row in all_violations)
    sidecar: dict[str, Any] = {
        "schema_version": SIDECAR_SCHEMA,
        "framework_id": FRAMEWORK_ID,
        "framework_config_digest": config_verdict["config_digest"],
        "mode": HISTORICAL_MODE,
        "authority": {
            "paper_action_authority": "NONE_SHADOW_ONLY",
            "v1_artifact_mutation": "FORBIDDEN",
            "legacy_intent_reconstruction": "FORBIDDEN",
            "activation_status": "SHADOW_CANDIDATE_NOT_ACTIVATED",
        },
        "source": {
            "run_id": source.get("run_id"),
            "cycle_id": source.get("cycle_id"),
            "decision_at": decision_at,
            "source_envelope_digest": source.get("source_envelope_digest"),
            "source_artifacts": copy.deepcopy(source.get("source_artifacts")),
            "validated_decision_digest": validated.get("decision_digest"),
        },
        "previous_sidecar_digest": (
            previous_sidecar.get("sidecar_digest")
            if isinstance(previous_sidecar, Mapping)
            else None
        ),
        "symbols": symbol_rows,
        "summary": {
            "symbol_count": len(symbol_rows),
            "blocking_violation_count": sum(
                row["severity"] == "BLOCKING" for row in all_violations
            ),
            "warning_violation_count": sum(
                row["severity"] == "WARNING" for row in all_violations
            ),
            "violation_code_counts": dict(sorted(counts.items())),
            "runtime_enforced_governance": False,
            "historical_source_rewritten": False,
            "result": "LEGACY_GOVERNANCE_GAPS_CONFIRMED",
        },
    }
    sidecar["sidecar_digest"] = canonical_digest(sidecar)
    return sidecar


def validate_sidecar(
    sidecar: Mapping[str, Any],
    config: Mapping[str, Any],
    previous_sidecar: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    config_verdict = validate_framework_config(config)
    if sidecar.get("schema_version") != SIDECAR_SCHEMA:
        raise GovernanceV2Error("SIDECAR_SCHEMA_MISMATCH")
    if sidecar.get("framework_id") != FRAMEWORK_ID:
        raise GovernanceV2Error("SIDECAR_FRAMEWORK_MISMATCH")
    if sidecar.get("framework_config_digest") != config_verdict["config_digest"]:
        raise GovernanceV2Error("SIDECAR_CONFIG_DIGEST_MISMATCH")
    if sidecar.get("mode") != HISTORICAL_MODE:
        raise GovernanceV2Error("SIDECAR_MODE_MISMATCH")
    expected_prior = (
        previous_sidecar.get("sidecar_digest")
        if isinstance(previous_sidecar, Mapping)
        else None
    )
    if sidecar.get("previous_sidecar_digest") != expected_prior:
        raise GovernanceV2Error("SIDECAR_PRIOR_DIGEST_MISMATCH")
    symbols = _symbol_map(sidecar.get("symbols"), "SIDECAR_SYMBOLS_INVALID")
    for symbol, row in symbols.items():
        if (
            _mapping(
                row.get("hypothesis_ledger"), "SIDECAR_HYPOTHESIS_LEDGER_MISSING"
            ).get("strategic_state")
            != LEGACY_UNKNOWN_STATE
        ):
            raise GovernanceV2Error(f"SIDECAR_LEGACY_STATE_INVENTED:{symbol}")
        behavior = _mapping(
            row.get("behavior_ledger"), "SIDECAR_BEHAVIOR_LEDGER_MISSING"
        )
        if (
            behavior.get("declared_action_intent") != "UNDECLARED_LEGACY"
            or behavior.get("reentry_contract") is not None
        ):
            raise GovernanceV2Error(f"SIDECAR_LEGACY_INTENT_INVENTED:{symbol}")
        if row.get("governance_disposition") != "BLOCKED_LEGACY_SCHEMA_INCOMPLETE":
            raise GovernanceV2Error(f"SIDECAR_LEGACY_NOT_BLOCKED:{symbol}")
    summary = _mapping(sidecar.get("summary"), "SIDECAR_SUMMARY_MISSING")
    if (
        summary.get("runtime_enforced_governance") is not False
        or summary.get("historical_source_rewritten") is not False
        or summary.get("result") != "LEGACY_GOVERNANCE_GAPS_CONFIRMED"
    ):
        raise GovernanceV2Error("SIDECAR_BOUNDARY_MISMATCH")
    candidate = copy.deepcopy(dict(sidecar))
    claimed = candidate.pop("sidecar_digest", None)
    if claimed != canonical_digest(candidate):
        raise GovernanceV2Error("SIDECAR_DIGEST_MISMATCH")
    return {
        "valid": True,
        "cycle_id": _mapping(sidecar.get("source"), "SIDECAR_SOURCE_MISSING").get(
            "cycle_id"
        ),
        "symbol_count": len(symbols),
        "sidecar_digest": claimed,
    }


def _card_source(
    source: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Mapping[str, Any]]]:
    analysis = _mapping(source.get("analysis"), "CARD_SOURCE_ANALYSIS_MISSING")
    decision_receipt = _mapping(source.get("decision"), "CARD_SOURCE_DECISION_MISSING")
    validated = _mapping(
        decision_receipt.get("validated_decision"),
        "CARD_SOURCE_VALIDATED_DECISION_MISSING",
    )
    decisions = _symbol_map(
        validated.get("symbol_decisions"), "CARD_SOURCE_SYMBOLS_INVALID"
    )
    return analysis, validated, decisions


def _validate_reentry(
    reentry: Any,
    hypothesis_id: str,
    decision_at: str,
    config: Mapping[str, Any],
    errors: list[str],
    prefix: str,
) -> None:
    if not isinstance(reentry, Mapping):
        errors.append(f"{prefix}:REENTRY_CONTRACT_REQUIRED")
        return
    contract = _mapping(config.get("reentry_contract"), "FRAMEWORK_REENTRY_MISSING")
    required = set(contract.get("required_fields", []))
    _exact_keys(reentry, required, errors, f"{prefix}:REENTRY")
    if reentry.get("hypothesis_instance_id") != hypothesis_id:
        errors.append(f"{prefix}:REENTRY_HYPOTHESIS_MISMATCH")
    if reentry.get("default_policy") != contract.get("default_policy"):
        errors.append(f"{prefix}:REENTRY_DEFAULT_POLICY_MISMATCH")
    if reentry.get("restoration_stages") != contract.get("restoration_stages"):
        errors.append(f"{prefix}:REENTRY_STAGES_MISMATCH")
    if reentry.get("cancel_on_state") != "D_INVALIDATED":
        errors.append(f"{prefix}:REENTRY_CANCEL_STATE_MISMATCH")
    if not _strings(reentry.get("minimum_condition_ids")):
        errors.append(f"{prefix}:REENTRY_MINIMUM_CONDITIONS_REQUIRED")
    for field in ("price_condition", "time_condition"):
        if not isinstance(reentry.get(field), str) or not reentry.get(field):
            errors.append(f"{prefix}:REENTRY_{field.upper()}_REQUIRED")
    try:
        created = parse_utc(reentry.get("created_at"))
        review_by = parse_utc(reentry.get("review_by"))
        if created != parse_utc(decision_at) or review_by <= created:
            errors.append(f"{prefix}:REENTRY_TIME_INVALID")
    except GovernanceV2Error:
        errors.append(f"{prefix}:REENTRY_TIME_INVALID")
    errors.append(f"{prefix}:REENTRY_EXECUTION_AUTHORITY_NOT_CONNECTED")


def validate_governance_card(
    card: Mapping[str, Any],
    source: Mapping[str, Any],
    config: Mapping[str, Any],
    previous_card: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a future successor card without granting paper authority.

    The return value is a complete verdict.  Call :func:`require_valid_card`
    at an application boundary that must fail closed.  The application must
    load ``previous_card`` from an accepted write-once repository; byte-level
    self-consistency alone is not acceptance authority.
    """

    errors: list[str] = []
    validate_framework_config(config)
    analysis, validated, source_decisions = _card_source(source)
    expected_top = {
        "schema_version",
        "framework_id",
        "framework_config_digest",
        "run_id",
        "cycle_id",
        "decision_at",
        "source_analysis_digest",
        "source_decision_digest",
        "previous_card_digest",
        "symbols",
        "card_digest",
    }
    _exact_keys(card, expected_top, errors, "CARD")
    if card.get("schema_version") != CARD_SCHEMA:
        errors.append("CARD:SCHEMA_MISMATCH")
    if card.get("framework_id") != FRAMEWORK_ID:
        errors.append("CARD:FRAMEWORK_MISMATCH")
    if card.get("framework_config_digest") != canonical_digest(config):
        errors.append("CARD:CONFIG_DIGEST_MISMATCH")
    if card.get("run_id") != source.get("run_id"):
        errors.append("CARD:RUN_ID_MISMATCH")
    if card.get("cycle_id") != source.get("cycle_id"):
        errors.append("CARD:CYCLE_ID_MISMATCH")
    decision_at = str(analysis.get("decision_at"))
    if card.get("decision_at") != decision_at:
        errors.append("CARD:DECISION_AT_MISMATCH")
    if card.get("source_analysis_digest") != analysis.get("analysis_digest"):
        errors.append("CARD:ANALYSIS_DIGEST_MISMATCH")
    if card.get("source_decision_digest") != validated.get("decision_digest"):
        errors.append("CARD:DECISION_DIGEST_MISMATCH")
    try:
        current_cycle_number = _cycle_number(card.get("cycle_id"))
    except GovernanceV2Error:
        current_cycle_number = -1
        errors.append("CARD:CYCLE_ID_INVALID")
    if previous_card is None:
        if card.get("previous_card_digest") is not None:
            errors.append("CARD:UNEXPECTED_PREVIOUS_CARD_DIGEST")
        if current_cycle_number > 1:
            errors.append("CARD:PRIOR_CARD_REQUIRED")
    else:
        previous_candidate = copy.deepcopy(dict(previous_card))
        previous_claimed_digest = previous_candidate.pop("card_digest", None)
        if previous_claimed_digest != canonical_digest(previous_candidate):
            errors.append("PRIOR_CARD:DIGEST_MISMATCH")
        if card.get("previous_card_digest") != previous_claimed_digest:
            errors.append("CARD:PREVIOUS_CARD_DIGEST_MISMATCH")
        if previous_card.get("schema_version") != CARD_SCHEMA:
            errors.append("PRIOR_CARD:SCHEMA_MISMATCH")
        if previous_card.get("framework_id") != FRAMEWORK_ID:
            errors.append("PRIOR_CARD:FRAMEWORK_MISMATCH")
        if (
            previous_card.get("framework_config_digest")
            != card.get("framework_config_digest")
        ):
            errors.append("PRIOR_CARD:CONFIG_DIGEST_MISMATCH")
        if previous_card.get("run_id") != card.get("run_id"):
            errors.append("PRIOR_CARD:RUN_ID_MISMATCH")
        try:
            previous_cycle_number = _cycle_number(previous_card.get("cycle_id"))
            if previous_cycle_number + 1 != current_cycle_number:
                errors.append("PRIOR_CARD:CYCLE_NOT_CONTIGUOUS")
        except GovernanceV2Error:
            errors.append("PRIOR_CARD:CYCLE_ID_INVALID")
    try:
        decision_time = parse_utc(decision_at)
    except GovernanceV2Error:
        decision_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        errors.append("CARD:SOURCE_DECISION_TIME_INVALID")

    card_symbols: dict[str, Mapping[str, Any]] = {}
    try:
        card_symbols = _symbol_map(card.get("symbols"), "CARD:SYMBOLS_INVALID")
    except GovernanceV2Error as exc:
        errors.append(str(exc))
    if list(card_symbols) != list(source_decisions):
        errors.append("CARD:SYMBOL_ORDER_MISMATCH")
    prior_symbols: dict[str, Mapping[str, Any]] = {}
    if previous_card is not None:
        try:
            prior_symbols = _symbol_map(
                previous_card.get("symbols"), "PRIOR_CARD:SYMBOLS_INVALID"
            )
        except GovernanceV2Error as exc:
            errors.append(str(exc))

    machine = _mapping(
        config.get("strategic_state_machine"), "FRAMEWORK_STATE_MACHINE_MISSING"
    )
    legal = _mapping(machine.get("legal_transitions"), "FRAMEWORK_TRANSITIONS_MISSING")
    promotion_config = _mapping(
        config.get("promotion_contract"), "FRAMEWORK_PROMOTION_MISSING"
    )
    role_timeframes = {
        str(row.get("timeframe"))
        for row in _list(
            _mapping(
                config.get("timeframe_role_profile"),
                "FRAMEWORK_PROFILE_MISSING",
            ).get("roles"),
            "FRAMEWORK_ROLES_MISSING",
        )
        if isinstance(row, Mapping)
    }
    phi_directions = _mapping(
        config.get("phi_direction_registry"), "FRAMEWORK_PHI_REGISTRY_MISSING"
    )

    for symbol, source_decision in source_decisions.items():
        row = card_symbols.get(symbol)
        if not isinstance(row, Mapping):
            continue
        prefix = f"SYMBOL:{symbol}"
        _exact_keys(
            row,
            {
                "symbol",
                "hypothesis",
                "signals",
                "promotion_receipts",
                "state_transition",
                "behavior",
            },
            errors,
            prefix,
        )
        hypothesis = row.get("hypothesis")
        transition = row.get("state_transition")
        behavior = row.get("behavior")
        if not isinstance(hypothesis, Mapping):
            errors.append(f"{prefix}:HYPOTHESIS_REQUIRED")
            continue
        if not isinstance(transition, Mapping):
            errors.append(f"{prefix}:STATE_TRANSITION_REQUIRED")
            continue
        if not isinstance(behavior, Mapping):
            errors.append(f"{prefix}:BEHAVIOR_REQUIRED")
            continue

        _exact_keys(
            hypothesis,
            {
                "hypothesis_instance_id",
                "selected_phi_id",
                "strategic_direction",
                "state",
                "core_premise_ids",
                "hard_invalidator_ids",
                "review_clock",
                "target_horizon",
            },
            errors,
            f"{prefix}:HYPOTHESIS",
        )
        hypothesis_id = hypothesis.get("hypothesis_instance_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            errors.append(f"{prefix}:HYPOTHESIS_INSTANCE_ID_REQUIRED")
            hypothesis_id = ""
        prior = prior_symbols.get(symbol)
        prior_hypothesis = (
            _mapping(prior.get("hypothesis"), "PRIOR_CARD:HYPOTHESIS_INVALID")
            if isinstance(prior, Mapping)
            else {}
        )
        prior_hypothesis_id = prior_hypothesis.get("hypothesis_instance_id")
        same_hypothesis_instance = (
            isinstance(prior_hypothesis_id, str)
            and prior_hypothesis_id == hypothesis_id
        )
        if prior_hypothesis and not same_hypothesis_instance:
            errors.append(f"{prefix}:NEW_HYPOTHESIS_CREATION_RECEIPT_REQUIRED")
        state = hypothesis.get("state")
        if state not in STRATEGIC_STATES:
            errors.append(f"{prefix}:STRATEGIC_STATE_INVALID")
        selected_phi = source_decision.get("selected_phi_id")
        if hypothesis.get("selected_phi_id") != selected_phi:
            errors.append(f"{prefix}:SELECTED_PHI_BINDING_MISMATCH")
        strategic_direction = hypothesis.get("strategic_direction")
        if strategic_direction not in {"LONG", "SHORT", "NEUTRAL"}:
            errors.append(f"{prefix}:STRATEGIC_DIRECTION_INVALID")
        phi_direction = phi_directions.get(selected_phi)
        if phi_direction in {"LONG", "SHORT", "NEUTRAL"} and (
            strategic_direction != phi_direction
        ):
            errors.append(f"{prefix}:PHI_DIRECTION_MISMATCH")
        core_premises = _strings(hypothesis.get("core_premise_ids"))
        hard_invalidators = _strings(hypothesis.get("hard_invalidator_ids"))
        if not core_premises or len(core_premises) != len(set(core_premises)):
            errors.append(f"{prefix}:CORE_PREMISES_REQUIRED_UNIQUE")
            core_premises = []
        if not hard_invalidators or len(hard_invalidators) != len(
            set(hard_invalidators)
        ):
            errors.append(f"{prefix}:HARD_INVALIDATORS_REQUIRED_UNIQUE")
            hard_invalidators = []
        if same_hypothesis_instance:
            immutable_fields = (
                "selected_phi_id",
                "strategic_direction",
                "core_premise_ids",
                "hard_invalidator_ids",
                "target_horizon",
            )
            for field in immutable_fields:
                if hypothesis.get(field) != prior_hypothesis.get(field):
                    errors.append(
                        f"{prefix}:HYPOTHESIS_IMMUTABLE_FIELD_CHANGED:{field}"
                    )

        review_clock = hypothesis.get("review_clock")
        if not isinstance(review_clock, Mapping):
            errors.append(f"{prefix}:REVIEW_CLOCK_REQUIRED")
            review_clock = {}
        _exact_keys(
            review_clock,
            {
                "strategic_timeframe",
                "last_reviewed_at",
                "next_scheduled_review_at",
                "current_trigger",
                "qualified_event_evidence_ids",
            },
            errors,
            f"{prefix}:REVIEW_CLOCK",
        )
        if review_clock.get("strategic_timeframe") not in {"4h", "1d"}:
            errors.append(f"{prefix}:REVIEW_CLOCK_TIMEFRAME_INVALID")
        trigger = review_clock.get("current_trigger")
        if trigger not in ALL_REVIEW_TRIGGERS:
            errors.append(f"{prefix}:REVIEW_TRIGGER_INVALID")
        qualified_event_ids = _strings(
            review_clock.get("qualified_event_evidence_ids")
        )
        if qualified_event_ids is None:
            errors.append(f"{prefix}:QUALIFIED_EVENT_EVIDENCE_NOT_LIST")
            qualified_event_ids = []
        if trigger == "QUALIFIED_MAJOR_EVENT" and not qualified_event_ids:
            errors.append(f"{prefix}:QUALIFIED_EVENT_EVIDENCE_REQUIRED")
        if trigger != "QUALIFIED_MAJOR_EVENT" and qualified_event_ids:
            errors.append(f"{prefix}:UNEXPECTED_QUALIFIED_EVENT_EVIDENCE")
        try:
            last_reviewed = parse_utc(review_clock.get("last_reviewed_at"))
            next_review = parse_utc(review_clock.get("next_scheduled_review_at"))
            if next_review <= last_reviewed:
                errors.append(f"{prefix}:REVIEW_CLOCK_TIME_INVALID")
            if same_hypothesis_instance:
                prior_clock = _mapping(
                    prior_hypothesis.get("review_clock"),
                    "PRIOR_CARD:REVIEW_CLOCK_INVALID",
                )
                prior_last = parse_utc(prior_clock.get("last_reviewed_at"))
                prior_next = parse_utc(
                    prior_clock.get("next_scheduled_review_at")
                )
                if trigger in SCHEDULED_REVIEW_TRIGGERS | {
                    "QUALIFIED_MAJOR_EVENT"
                }:
                    if last_reviewed != decision_time:
                        errors.append(f"{prefix}:STRATEGIC_REVIEW_TIME_MISMATCH")
                    if (
                        trigger
                        in {"SCHEDULED_4H_CLOSE", "SCHEDULED_1D_CLOSE"}
                        and decision_time < prior_next
                    ):
                        errors.append(f"{prefix}:SCHEDULED_REVIEW_NOT_DUE")
                    if trigger == "HYPOTHESIS_EXPIRY":
                        try:
                            prior_horizon = _mapping(
                                prior_hypothesis.get("target_horizon"),
                                "PRIOR_CARD:HORIZON_INVALID",
                            )
                            if decision_time < parse_utc(
                                prior_horizon.get("ends_at")
                            ):
                                errors.append(
                                    f"{prefix}:HYPOTHESIS_EXPIRY_NOT_DUE"
                                )
                        except GovernanceV2Error:
                            errors.append(f"{prefix}:PRIOR_HORIZON_TIME_INVALID")
                    errors.append(
                        f"{prefix}:TRUSTED_REVIEW_TRIGGER_AUTHORITY_NOT_CONNECTED"
                    )
                else:
                    if last_reviewed != prior_last or next_review != prior_next:
                        errors.append(
                            f"{prefix}:NON_STRATEGIC_UPDATE_REWROTE_REVIEW_CLOCK"
                        )
                    if decision_time >= prior_next:
                        errors.append(f"{prefix}:STRATEGIC_REVIEW_OVERDUE")
            elif last_reviewed != decision_time:
                errors.append(f"{prefix}:GENESIS_REVIEW_TIME_MISMATCH")
        except GovernanceV2Error:
            errors.append(f"{prefix}:REVIEW_CLOCK_TIME_INVALID")

        horizon = hypothesis.get("target_horizon")
        if not isinstance(horizon, Mapping):
            errors.append(f"{prefix}:TARGET_HORIZON_REQUIRED")
            horizon = {}
        _exact_keys(
            horizon,
            {
                "horizon_class",
                "starts_at",
                "ends_at",
                "evaluation_timeframe",
                "minimum_complete_windows",
            },
            errors,
            f"{prefix}:HORIZON",
        )
        horizon_class = horizon.get("horizon_class")
        if horizon_class not in HORIZON_POLICIES:
            errors.append(f"{prefix}:HORIZON_CLASS_INVALID")
        evaluation_timeframe = horizon.get("evaluation_timeframe")
        if evaluation_timeframe not in role_timeframes:
            errors.append(f"{prefix}:HORIZON_TIMEFRAME_INVALID")
        minimum_windows = horizon.get("minimum_complete_windows")
        if (
            isinstance(minimum_windows, bool)
            or not isinstance(minimum_windows, int)
            or minimum_windows < 1
        ):
            errors.append(f"{prefix}:HORIZON_WINDOWS_INVALID")
        policy_for_class = HORIZON_POLICIES.get(str(horizon_class))
        if policy_for_class is not None:
            if (
                evaluation_timeframe
                not in policy_for_class["evaluation_timeframes"]
            ):
                errors.append(f"{prefix}:HORIZON_CLASS_TIMEFRAME_MISMATCH")
            if (
                isinstance(minimum_windows, int)
                and not isinstance(minimum_windows, bool)
                and minimum_windows
                < int(policy_for_class["minimum_complete_windows"])
            ):
                errors.append(f"{prefix}:HORIZON_CLASS_WINDOWS_INSUFFICIENT")
        try:
            starts = parse_utc(horizon.get("starts_at"))
            ends = parse_utc(horizon.get("ends_at"))
            expected_horizon_start = decision_time
            if same_hypothesis_instance:
                expected_horizon_start = parse_utc(
                    _mapping(
                        prior_hypothesis.get("target_horizon"),
                        "PRIOR_CARD:HORIZON_INVALID",
                    ).get("starts_at")
                )
            if starts != expected_horizon_start or ends <= starts:
                errors.append(f"{prefix}:HORIZON_TIME_INVALID")
            if (
                isinstance(minimum_windows, int)
                and not isinstance(minimum_windows, bool)
                and evaluation_timeframe in TIMEFRAME_SECONDS
                and (ends - starts).total_seconds()
                < TIMEFRAME_SECONDS[str(evaluation_timeframe)] * minimum_windows
            ):
                errors.append(f"{prefix}:HORIZON_DURATION_TOO_SHORT")
        except GovernanceV2Error:
            errors.append(f"{prefix}:HORIZON_TIME_INVALID")

        raw_signals = row.get("signals")
        signals: dict[str, Mapping[str, Any]] = {}
        if not isinstance(raw_signals, list) or not raw_signals:
            errors.append(f"{prefix}:SIGNALS_REQUIRED")
            raw_signals = []
        for index, raw_signal in enumerate(raw_signals):
            signal_prefix = f"{prefix}:SIGNAL:{index}"
            if not isinstance(raw_signal, Mapping):
                errors.append(f"{signal_prefix}:NOT_OBJECT")
                continue
            _exact_keys(
                raw_signal,
                {
                    "signal_id",
                    "available_at",
                    "timeframe",
                    "signal_class",
                    "affects",
                    "changed_core_premise_id",
                    "outside_normal_range",
                    "persistence_observation_ids",
                    "independent_confirmation_group_ids",
                    "cause_class",
                    "source_ref",
                },
                errors,
                signal_prefix,
            )
            signal_id = raw_signal.get("signal_id")
            if (
                not isinstance(signal_id, str)
                or not signal_id
                or signal_id in signals
            ):
                errors.append(f"{signal_prefix}:ID_INVALID_OR_DUPLICATE")
                continue
            signals[signal_id] = raw_signal
            if raw_signal.get("timeframe") not in role_timeframes | {"realtime", "8h"}:
                errors.append(f"{signal_prefix}:TIMEFRAME_INVALID")
            if raw_signal.get("signal_class") not in SIGNAL_CLASSES:
                errors.append(f"{signal_prefix}:CLASS_INVALID")
            if raw_signal.get("affects") not in {"DIRECTION", "RISK", "EXECUTION"}:
                errors.append(f"{signal_prefix}:AFFECTS_INVALID")
            if type(raw_signal.get("outside_normal_range")) is not bool:
                errors.append(f"{signal_prefix}:NORMAL_RANGE_FLAG_INVALID")
            for field in (
                "persistence_observation_ids",
                "independent_confirmation_group_ids",
            ):
                values = _strings(raw_signal.get(field))
                if values is None or len(values) != len(set(values)):
                    errors.append(f"{signal_prefix}:{field.upper()}_INVALID")
            if (
                raw_signal.get("changed_core_premise_id") is not None
                and raw_signal.get("changed_core_premise_id") not in core_premises
            ):
                errors.append(f"{signal_prefix}:CORE_PREMISE_UNKNOWN")
            try:
                if parse_utc(raw_signal.get("available_at")) > decision_time:
                    errors.append(f"{signal_prefix}:AVAILABLE_AFTER_DECISION")
            except GovernanceV2Error:
                errors.append(f"{signal_prefix}:AVAILABLE_AT_INVALID")

        raw_promotions = row.get("promotion_receipts")
        promotions: dict[str, Mapping[str, Any]] = {}
        if not isinstance(raw_promotions, list):
            errors.append(f"{prefix}:PROMOTION_RECEIPTS_NOT_LIST")
            raw_promotions = []
        for index, raw_promotion in enumerate(raw_promotions):
            promotion_prefix = f"{prefix}:PROMOTION:{index}"
            if not isinstance(raw_promotion, Mapping):
                errors.append(f"{promotion_prefix}:NOT_OBJECT")
                continue
            _exact_keys(
                raw_promotion,
                {
                    "promotion_receipt_id",
                    "signal_ids",
                    "changed_core_premise_id",
                    "issued_at",
                    "promoted_to",
                    "condition_attestations",
                },
                errors,
                promotion_prefix,
            )
            promotion_id = raw_promotion.get("promotion_receipt_id")
            if (
                not isinstance(promotion_id, str)
                or not promotion_id
                or promotion_id in promotions
            ):
                errors.append(f"{promotion_prefix}:ID_INVALID_OR_DUPLICATE")
                continue
            promotions[promotion_id] = raw_promotion
            errors.append(
                f"{promotion_prefix}:TRUSTED_EVIDENCE_AUTHORITY_NOT_CONNECTED"
            )
            signal_ids = _strings(raw_promotion.get("signal_ids"))
            if (
                not signal_ids
                or len(signal_ids) != len(set(signal_ids))
                or any(signal_id not in signals for signal_id in signal_ids)
            ):
                errors.append(f"{promotion_prefix}:SIGNAL_REFS_INVALID")
                signal_ids = []
            changed_premise = raw_promotion.get("changed_core_premise_id")
            if changed_premise not in core_premises:
                errors.append(f"{promotion_prefix}:CORE_PREMISE_INVALID")
            if raw_promotion.get("promoted_to") != "STRUCTURAL_EVIDENCE":
                errors.append(f"{promotion_prefix}:TARGET_INVALID")
            if set(raw_promotion.get("condition_attestations", [])) != set(
                promotion_config.get("all_conditions_required", [])
            ):
                errors.append(f"{promotion_prefix}:CONDITIONS_INCOMPLETE")
            try:
                if parse_utc(raw_promotion.get("issued_at")) != decision_time:
                    errors.append(f"{promotion_prefix}:ISSUED_AT_INVALID")
            except GovernanceV2Error:
                errors.append(f"{promotion_prefix}:ISSUED_AT_INVALID")
            linked = [signals[signal_id] for signal_id in signal_ids if signal_id in signals]
            windows = {
                item
                for signal in linked
                for item in signal.get("persistence_observation_ids", [])
            }
            groups = {
                item
                for signal in linked
                for item in signal.get("independent_confirmation_group_ids", [])
            }
            if len(windows) < int(
                promotion_config.get("minimum_distinct_observation_windows", 2)
            ):
                errors.append(f"{promotion_prefix}:PERSISTENCE_INSUFFICIENT")
            if len(groups) < int(
                promotion_config.get(
                    "minimum_independent_confirmation_groups", 2
                )
            ):
                errors.append(f"{promotion_prefix}:INDEPENDENCE_INSUFFICIENT")
            if any(
                signal.get("outside_normal_range") is not True for signal in linked
            ):
                errors.append(f"{promotion_prefix}:NORMAL_RANGE_NOT_EXCEEDED")
            if any(
                signal.get("cause_class") in FORBIDDEN_CAUSE_CLASSES
                for signal in linked
            ):
                errors.append(f"{promotion_prefix}:CAUSE_CLASS_INELIGIBLE")
            if any(
                signal.get("changed_core_premise_id") != changed_premise
                for signal in linked
            ):
                errors.append(f"{promotion_prefix}:PREMISE_BINDING_MISMATCH")
            if any(signal.get("affects") != "DIRECTION" for signal in linked):
                errors.append(f"{promotion_prefix}:NON_DIRECTION_SIGNAL_INELIGIBLE")

        promoted_signal_ids = {
            signal_id
            for promotion in promotions.values()
            for signal_id in promotion.get("signal_ids", [])
        }
        for signal_id, signal in signals.items():
            if (
                signal.get("timeframe") in LOWER_TIMEFRAMES
                and signal.get("affects") == "DIRECTION"
                and signal_id not in promoted_signal_ids
            ):
                errors.append(
                    f"{prefix}:SIGNAL:{signal_id}:LOWER_TIMEFRAME_DIRECTION_NOT_PROMOTED"
                )
            if (
                signal.get("signal_class") == "STRUCTURAL"
                and signal.get("timeframe") not in STRUCTURAL_TIMEFRAMES
                and signal_id not in promoted_signal_ids
            ):
                errors.append(
                    f"{prefix}:SIGNAL:{signal_id}:STRUCTURAL_CLASS_NOT_AUTHORIZED"
                )

        _exact_keys(
            transition,
            {
                "transition_id",
                "from_state",
                "to_state",
                "reviewed_at",
                "trigger",
                "evidence_signal_ids",
                "promotion_receipt_ids",
                "changed_core_premise_ids",
                "hard_invalidator_ids",
            },
            errors,
            f"{prefix}:TRANSITION",
        )
        if transition.get("to_state") != state:
            errors.append(f"{prefix}:TRANSITION_TARGET_STATE_MISMATCH")
        if transition.get("trigger") != trigger:
            errors.append(f"{prefix}:TRANSITION_TRIGGER_MISMATCH")
        try:
            if parse_utc(transition.get("reviewed_at")) != decision_time:
                errors.append(f"{prefix}:TRANSITION_REVIEW_TIME_INVALID")
        except GovernanceV2Error:
            errors.append(f"{prefix}:TRANSITION_REVIEW_TIME_INVALID")
        evidence_signal_ids = _strings(transition.get("evidence_signal_ids"))
        promotion_ids = _strings(transition.get("promotion_receipt_ids"))
        changed_premise_ids = _strings(transition.get("changed_core_premise_ids"))
        transition_hard_ids = _strings(transition.get("hard_invalidator_ids"))
        if evidence_signal_ids is None or any(
            signal_id not in signals for signal_id in evidence_signal_ids
        ):
            errors.append(f"{prefix}:TRANSITION_EVIDENCE_REFS_INVALID")
            evidence_signal_ids = []
        if promotion_ids is None or any(
            promotion_id not in promotions for promotion_id in promotion_ids
        ):
            errors.append(f"{prefix}:TRANSITION_PROMOTION_REFS_INVALID")
            promotion_ids = []
        if changed_premise_ids is None or any(
            premise not in core_premises for premise in changed_premise_ids
        ):
            errors.append(f"{prefix}:TRANSITION_PREMISE_REFS_INVALID")
            changed_premise_ids = []
        if transition_hard_ids is None or any(
            invalidator not in hard_invalidators
            for invalidator in transition_hard_ids
        ):
            errors.append(f"{prefix}:TRANSITION_INVALIDATOR_REFS_INVALID")
            transition_hard_ids = []

        if same_hypothesis_instance:
            expected_from = prior_hypothesis.get("state")
        else:
            expected_from = "A_VALID"
        from_state = transition.get("from_state")
        to_state = transition.get("to_state")
        if not prior_hypothesis and (
            state != "A_VALID"
            or from_state != "A_VALID"
            or to_state != "A_VALID"
            or trigger != "NO_CHANGE"
        ):
            errors.append(f"{prefix}:GENESIS_MUST_START_A_VALID_NO_CHANGE")
        if from_state != expected_from:
            errors.append(f"{prefix}:TRANSITION_SOURCE_STATE_MISMATCH")
        if (
            from_state not in STRATEGIC_STATES
            or to_state not in legal.get(str(from_state), [])
        ):
            errors.append(f"{prefix}:TRANSITION_ILLEGAL")
        if from_state == "D_INVALIDATED" and to_state != "D_INVALIDATED":
            errors.append(f"{prefix}:INVALIDATED_HYPOTHESIS_REACTIVATED")
        if to_state != from_state and not evidence_signal_ids:
            errors.append(f"{prefix}:STATE_CHANGE_EVIDENCE_REQUIRED")
        strategic_state_change = to_state != from_state and (
            to_state in {"C_CHALLENGED", "D_INVALIDATED"}
            or from_state == "C_CHALLENGED"
        )
        if strategic_state_change:
            if trigger not in SCHEDULED_REVIEW_TRIGGERS | {
                "QUALIFIED_MAJOR_EVENT"
            }:
                errors.append(f"{prefix}:STRATEGIC_TRANSITION_OUTSIDE_REVIEW_CLOCK")
            structural_evidence = any(
                signals[signal_id].get("timeframe") in STRUCTURAL_TIMEFRAMES
                and signals[signal_id].get("signal_class") == "STRUCTURAL"
                for signal_id in evidence_signal_ids
                if signal_id in signals
            )
            if not structural_evidence and not promotion_ids:
                errors.append(f"{prefix}:STRATEGIC_TRANSITION_EVIDENCE_INSUFFICIENT")
            if not changed_premise_ids and not transition_hard_ids:
                errors.append(f"{prefix}:STRATEGIC_TRANSITION_PREMISE_REQUIRED")
        if (
            from_state == "C_CHALLENGED"
            and to_state in {"A_VALID", "B_TACTICAL_DISTURBANCE"}
            and not changed_premise_ids
        ):
            errors.append(f"{prefix}:STRATEGIC_RECOVERY_PREMISE_REQUIRED")
        if to_state == "D_INVALIDATED" and to_state != from_state:
            if not transition_hard_ids:
                errors.append(f"{prefix}:INVALIDATION_HARD_PREDICATE_REQUIRED")

        _exact_keys(
            behavior,
            {
                "action_intent",
                "changes_strategic_state",
                "v1_action",
                "reentry_contract",
                "evaluation_policy",
            },
            errors,
            f"{prefix}:BEHAVIOR",
        )
        intent = behavior.get("action_intent")
        v1_action = source_decision.get("action")
        if intent not in ACTION_INTENTS:
            errors.append(f"{prefix}:ACTION_INTENT_INVALID")
        if behavior.get("v1_action") != v1_action:
            errors.append(f"{prefix}:V1_ACTION_BINDING_MISMATCH")
        allowed_intents = ACTION_ALLOWED_INTENTS.get(str(v1_action))
        if allowed_intents is None:
            errors.append(f"{prefix}:V1_ACTION_UNREGISTERED")
        elif intent not in allowed_intents:
            errors.append(f"{prefix}:ACTION_INTENT_V1_ACTION_MISMATCH")
        if behavior.get("changes_strategic_state") is not False:
            errors.append(f"{prefix}:BEHAVIOR_MAY_NOT_OWN_STRATEGIC_STATE")
        if v1_action in NEW_RISK_ACTIONS:
            if intent not in {"STRATEGIC_ENTRY", "STRATEGIC_ADD"}:
                errors.append(f"{prefix}:NEW_RISK_INTENT_MISMATCH")
            if state != "A_VALID":
                errors.append(f"{prefix}:NEW_RISK_STATE_NOT_VALID")
            action_direction = ACTION_DIRECTIONS.get(str(v1_action))
            if action_direction != strategic_direction:
                errors.append(f"{prefix}:NEW_RISK_DIRECTION_MISMATCH")
            analysis_symbol = _symbol_map(
                analysis.get("symbols"), "CARD_SOURCE_ANALYSIS_SYMBOLS_INVALID"
            ).get(symbol)
            parent = (
                _operational_direction(analysis_symbol)
                if isinstance(analysis_symbol, Mapping)
                else UNKNOWN
            )
            expected_parent = (
                "LONG"
                if parent == "UP"
                else "SHORT"
                if parent == "DOWN"
                else UNKNOWN
            )
            if action_direction != expected_parent and not promotion_ids:
                errors.append(f"{prefix}:PARENT_OVERRIDE_REQUIRES_PROMOTION")
        if intent == "STRATEGIC_INVALIDATION_EXIT" and state != "D_INVALIDATED":
            errors.append(f"{prefix}:INVALIDATION_EXIT_STATE_MISMATCH")
        if (
            v1_action in EXIT_OR_REDUCE_ACTIONS
            and state != "D_INVALIDATED"
        ):
            _validate_reentry(
                behavior.get("reentry_contract"),
                str(hypothesis_id),
                decision_at,
                config,
                errors,
                prefix,
            )
        elif behavior.get("reentry_contract") is not None:
            errors.append(f"{prefix}:UNEXPECTED_REENTRY_CONTRACT")

        policy = behavior.get("evaluation_policy")
        if not isinstance(policy, Mapping):
            errors.append(f"{prefix}:EVALUATION_POLICY_REQUIRED")
            policy = {}
        _exact_keys(
            policy,
            {
                "horizon_class",
                "correctness_eligible_at",
                "before_eligibility_status",
                "evaluate_against_frozen_rules",
                "pnl_is_strategy_validation",
            },
            errors,
            f"{prefix}:EVALUATION",
        )
        if policy.get("horizon_class") != horizon.get("horizon_class"):
            errors.append(f"{prefix}:EVALUATION_HORIZON_CLASS_MISMATCH")
        if policy.get("correctness_eligible_at") != horizon.get("ends_at"):
            errors.append(f"{prefix}:EVALUATION_ELIGIBILITY_TIME_MISMATCH")
        if (
            policy.get("before_eligibility_status")
            != "INTERIM_PATH_OBSERVATION_NOT_CORRECTNESS"
            or policy.get("evaluate_against_frozen_rules") is not True
            or policy.get("pnl_is_strategy_validation") is not False
        ):
            errors.append(f"{prefix}:EVALUATION_POLICY_INVARIANT_MISMATCH")

    candidate = copy.deepcopy(dict(card))
    claimed_digest = candidate.pop("card_digest", None)
    if claimed_digest != canonical_digest(candidate):
        errors.append("CARD:DIGEST_MISMATCH")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "card_digest": claimed_digest,
        "paper_action_authority": "NONE_VALIDATION_ONLY",
    }


def require_valid_card(
    card: Mapping[str, Any],
    source: Mapping[str, Any],
    config: Mapping[str, Any],
    previous_card: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = validate_governance_card(card, source, config, previous_card)
    if not verdict["valid"]:
        raise GovernanceV2Error(
            "GOVERNANCE_CARD_REJECTED:" + ";".join(verdict["errors"])
        )
    return verdict


def evaluate_horizon_status(
    *,
    reviewed_at: str,
    correctness_eligible_at: str,
    complete_windows: int,
    minimum_complete_windows: int,
    frozen_support_matched: bool | None,
    frozen_falsifier_matched: bool | None,
) -> str:
    """Return horizon logic for already trusted evaluator inputs.

    This pure function does not establish that window counts or predicate
    matches are authentic.  A future application boundary must supply them
    through a frozen-predicate/closed-window receipt before this result can be
    persisted or consumed.
    """

    review_time = parse_utc(reviewed_at)
    eligible_time = parse_utc(correctness_eligible_at)
    if (
        isinstance(complete_windows, bool)
        or not isinstance(complete_windows, int)
        or complete_windows < 0
        or isinstance(minimum_complete_windows, bool)
        or not isinstance(minimum_complete_windows, int)
        or minimum_complete_windows < 1
    ):
        raise GovernanceV2Error("HORIZON_WINDOW_COUNT_INVALID")
    if (
        review_time < eligible_time
        or complete_windows < minimum_complete_windows
    ):
        return "INTERIM_PATH_OBSERVATION_NOT_CORRECTNESS"
    if frozen_falsifier_matched is True:
        return "FALSIFIED_AT_DECLARED_HORIZON"
    if frozen_support_matched is True:
        return "SUPPORTED_AT_DECLARED_HORIZON"
    if frozen_support_matched is None or frozen_falsifier_matched is None:
        return "UNKNOWN_AT_DECLARED_HORIZON"
    return "EXPIRED_UNSUPPORTED_AT_DECLARED_HORIZON"
