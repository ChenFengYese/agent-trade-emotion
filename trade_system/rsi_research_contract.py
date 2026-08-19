"""Static validator for the outcome-free RSI-MTF-DRL-PM v0.2 research contract.

This module deliberately has no CLI, data reader, backtest, collector, order or
filesystem-writing capability.  It only loads one JSON contract and verifies its
two review-tooling source bindings.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .protocol import canonical_json, canonical_sha256
from .research_report import sha256_file
from .types import parse_utc


SCHEMA_VERSION = "rsi-mtf-drl-pm.research-contract.v0.2"
CONTRACT_ID = "rsi-mtf-drl-pm-v0-2-outcome-free-contract"
REVIEW_READY = "REVIEW_READY"
EVIDENCE_LEVEL = "E0"
FORBIDDEN = "FORBIDDEN"
REJECT_FREEZE = "REJECT_FREEZE"
CONTROL_IDS = ("C0", "C1", "C2", "C3", "C4", "Cmu", "C5")
HYPOTHESIS_MAPPING = {
    "H-010": "C2-C1",
    "H-011": "C3-C2",
    "H-012": "C4-C3",
    "H-013": "C5-C4",
    "H-014": "C4-Cmu",
}
PINNED_SEMANTIC_SHA256 = "99ed1ff1b5520180c02f84afa01474f930c155ead26b6030898fec25ddf5ccaf"
CONTROL_TABLE: tuple[dict[str, Any], ...] = (
    {
        "control_id": "C0",
        "required_gates": [],
        "forbidden_gates": ["RSI", "4H_RSI", "K", "RESPONDING", "D", "R", "L"],
        "lane_roles": ["DEVELOPMENT", "CALIBRATION", "HOLDOUT"],
        "anchor_source": "GATE_NEUTRAL_U_ANCHOR",
        "action_clock": "NO_ACTION",
        "ttl_source": "NO_TTL",
        "entry_policy": "NO_ENTRY",
        "exit_policy": "NO_EXIT",
        "inherits_submission_fill_from": "NONE",
        "action_kind": "NO_ACTION",
    },
    {
        "control_id": "C1",
        "required_gates": ["RSI", "COMMON_QUALITY", "COMMON_EXECUTION", "COMMON_GEOMETRY", "COMMON_EV", "COMMON_RISK"],
        "forbidden_gates": ["4H_RSI", "K", "RESPONDING", "D", "R", "L"],
        "lane_roles": ["DEVELOPMENT", "CALIBRATION", "HOLDOUT"],
        "anchor_source": "GATE_NEUTRAL_U_ANCHOR",
        "action_clock": "FIRST_LANE_AWARE_GATE_PASS",
        "ttl_source": "ENTRY_TTL_SECONDS",
        "entry_policy": "CONTROL_INDEXED_ENTRYZONE",
        "exit_policy": "FIXED_EXIT",
        "inherits_submission_fill_from": "NONE",
        "action_kind": "CONTROL_ACTION",
    },
    {
        "control_id": "C2",
        "required_gates": ["RSI", "4H_RSI", "COMMON_QUALITY", "COMMON_EXECUTION", "COMMON_GEOMETRY", "COMMON_EV", "COMMON_RISK"],
        "forbidden_gates": ["K", "REGIME", "RESPONDING", "D", "R", "L"],
        "lane_roles": ["DEVELOPMENT", "CALIBRATION", "HOLDOUT"],
        "anchor_source": "GATE_NEUTRAL_U_ANCHOR",
        "action_clock": "FIRST_LANE_AWARE_GATE_PASS",
        "ttl_source": "C2_OPPORTUNITY_OBSERVATION_TTL",
        "entry_policy": "CONTROL_INDEXED_ENTRYZONE",
        "exit_policy": "FIXED_EXIT",
        "inherits_submission_fill_from": "NONE",
        "action_kind": "CONTROL_ACTION",
    },
    {
        "control_id": "C3",
        "required_gates": ["RSI", "4H_RSI", "K", "COMMON_QUALITY", "COMMON_EXECUTION", "COMMON_GEOMETRY", "COMMON_EV", "COMMON_RISK"],
        "forbidden_gates": ["RESPONDING", "D", "R", "L"],
        "lane_roles": ["DEVELOPMENT", "CALIBRATION", "HOLDOUT"],
        "anchor_source": "C2_U_ANCHOR",
        "action_clock": "FIRST_LANE_AWARE_GATE_PASS",
        "ttl_source": "C2_OPPORTUNITY_OBSERVATION_TTL",
        "entry_policy": "CONTROL_INDEXED_ENTRYZONE",
        "exit_policy": "FIXED_EXIT",
        "inherits_submission_fill_from": "NONE",
        "action_kind": "CONTROL_ACTION",
    },
    {
        "control_id": "C4",
        "required_gates": ["RSI", "4H_RSI", "K", "RESPONDING", "D", "R", "L", "COMMON_QUALITY", "COMMON_EXECUTION", "COMMON_GEOMETRY", "COMMON_EV", "COMMON_RISK"],
        "forbidden_gates": [],
        "lane_roles": ["DEVELOPMENT", "CALIBRATION", "HOLDOUT"],
        "anchor_source": "C2_U_ANCHOR",
        "action_clock": "FIRST_LANE_AWARE_GATE_PASS",
        "ttl_source": "C2_OPPORTUNITY_OBSERVATION_TTL",
        "entry_policy": "CONTROL_INDEXED_ENTRYZONE",
        "exit_policy": "FIXED_EXIT",
        "inherits_submission_fill_from": "NONE",
        "action_kind": "RESEARCH_ACTION_ONLY",
    },
    {
        "control_id": "Cmu",
        "required_gates": ["K", "RESPONDING", "D", "R", "L", "COMMON_QUALITY", "COMMON_EXECUTION", "COMMON_GEOMETRY", "COMMON_EV", "COMMON_RISK"],
        "forbidden_gates": ["RSI", "4H_RSI"],
        "lane_roles": ["DEVELOPMENT", "CALIBRATION", "HOLDOUT"],
        "anchor_source": "GATE_NEUTRAL_U_ANCHOR",
        "action_clock": "FIRST_LANE_AWARE_GATE_PASS",
        "ttl_source": "ENTRY_TTL_SECONDS",
        "entry_policy": "CONTROL_INDEXED_ENTRYZONE_WITHOUT_RSI",
        "exit_policy": "FIXED_EXIT",
        "inherits_submission_fill_from": "NONE",
        "action_kind": "RESEARCH_ACTION_ONLY",
    },
    {
        "control_id": "C5",
        "required_gates": ["EXACT_C4_SUBMISSION", "EXACT_C4_FILL"],
        "forbidden_gates": [],
        "lane_roles": ["DEVELOPMENT", "CALIBRATION", "HOLDOUT"],
        "anchor_source": "EXACT_C4_ANCHOR",
        "action_clock": "EXACT_C4_SUBMISSION_AND_FILL_CLOCK",
        "ttl_source": "EXACT_C4_TTL",
        "entry_policy": "INHERIT_EXACT_C4_SUBMISSION_FILL",
        "exit_policy": "DYNAMIC_EXIT_ONLY",
        "inherits_submission_fill_from": "C4",
        "action_kind": "INHERITED_C4_RESEARCH_ACTION",
    },
)
LEDGER_REQUIRED_FIELDS = [
    "EVENT_ID", "PARENT_ID", "EPISODE_ID", "OPPORTUNITY_ID", "THEORY_CONTRACT_POLICY_CODE_DIGEST",
    "SIDE", "STATE_BEFORE_AFTER", "DECISION_AVAILABLE_EVALUATED_TIME", "ANCHOR_ZONE", "P_PE_I0_G0_S_T_H",
    "Q_AUTH_POSITION_PROTECTION_PENDING_RISK", "REQUEST_ACK_FILL_CANCEL_REDUCE_ONLY_ORDER_IDS", "FEE_FUNDING",
    "BARRIER_AUTHORITY", "RECONCILE_SNAPSHOT_HASH", "REASON_PRIORITY", "NO_CHANGE", "OPERATOR_ID",
    "PREVIOUS_HASH", "WRITTEN_AT",
]
PROTECTION_POLICY = {
    "pending_caps": {
        "FIRST_FILL_PENDING": {"max_seconds": 2, "max_quantity_fraction": "1", "fraction_denominator": "Q_AUTH", "max_risk_equivalent_usdt": "5", "all_caps_must_hold": True},
        "EXCESS_FILL_PENDING": {"max_seconds": 2, "max_quantity_fraction": "0.1", "fraction_denominator": "Q_AUTH", "max_risk_equivalent_usdt": "5", "all_caps_must_hold": True},
    },
    "pending_cap_feasibility": {"formula_id": "NONZERO_Q_AUTH_TIMES_CAP_FRACTION_IS_POSITIVE", "requirement": "NONZERO_Q_AUTH_MUST_HAVE_NONZERO_FEASIBLE_PENDING_CAP"},
    "sequence": ["FIRST_FILL", "CANCEL_REMAINDER", "STOP_PROTECT_REQUEST", "STOP_PRICE_QTY_ORDER_ID_REDUCE_ONLY_ACK", "OPEN_PROTECTED"],
    "failure_action": "REDUCE_ONLY_EXIT_AND_HALT_RECONCILE",
    "valid_stop_ack_invariant": {"formula_id": "EFFECTIVE_PROTECTED_QTY_GTE_ABS_RECONCILED_POSITION_QTY", "effective_protected_qty": "ACKED_REDUCE_ONLY_STOP_QTY", "reconciled_position_qty": "RECONCILED_POSITION_QTY", "enforcement": "SUFFICIENT_STOP_ACK_OPEN_PROTECTED_ONLY"},
    "transient_window": {"start": "FIRST_FILL_OR_ANY_RECONCILED_POSITION_INCREASE_ABOVE_EFFECTIVE_PROTECTED_QTY", "end": "SUFFICIENT_STOP_ACK_OR_REDUCE_ONLY_EXIT_AND_HALT_RECONCILE"},
    "risk_equivalent_formula_id": "ABS_UNPROTECTED_QTY_TIMES_WORST_CASE_EXIT_DISTANCE_PLUS_FEES_SLIPPAGE_TAIL",
    "barrier_authority": "OLD_ACKED_BARRIER_UNTIL_NEW_ACK",
    "after_q_auth": "QUANTITY_ONLY_DECREASES_NO_ADD",
    "fill_transitions": [
        {"event": "FIRST_FILL", "pending_cap": "FIRST_FILL_PENDING", "pe_update": "FREEZE_FROM_FIRST_AUTHORITATIVE_CUMULATIVE_NONZERO_FILL", "q_auth_update": "FREEZE_FROM_FIRST_AUTHORITATIVE_CUMULATIVE_NONZERO_FILL", "protected_update": "PENDING_STOP_ACK", "pending_update": "STOP_PROTECT_REQUEST_PENDING", "next_action": "CANCEL_REMAINDER_THEN_STOP_PROTECT"},
        {"event": "SUBSEQUENT_FILL_SAME_IOC", "pending_cap": "EXCESS_FILL_PENDING", "pe_update": "UNCHANGED_FROZEN_AT_FIRST_AUTHORITATIVE_NONZERO_FILL", "q_auth_update": "UNCHANGED_FROZEN_AT_FIRST_AUTHORITATIVE_NONZERO_FILL", "protected_update": "ENTER_PROTECTION_PENDING_EXTEND_STOP_TO_RECONCILED_POSITION", "pending_update": "RECORD_EXCESS_FILL_REDUCE_ONLY_TO_Q_AUTH_AND_RECONCILE", "next_action": "OLD_ACKED_BARRIER_REMAINS_AUTHORITY"},
        {"event": "CANCEL_PENDING_FILL", "pending_cap": "EXCESS_FILL_PENDING", "pe_update": "UNCHANGED_FROZEN_AT_FIRST_AUTHORITATIVE_NONZERO_FILL", "q_auth_update": "UNCHANGED_FROZEN_AT_FIRST_AUTHORITATIVE_NONZERO_FILL", "protected_update": "ENTER_PROTECTION_PENDING_EXTEND_STOP_TO_RECONCILED_POSITION", "pending_update": "RECORD_EXCESS_FILL_REDUCE_ONLY_TO_Q_AUTH_AND_RECONCILE", "next_action": "OLD_ACKED_BARRIER_REMAINS_AUTHORITY"},
        {"event": "LATE_FILL_AFTER_CANCEL", "pending_cap": "EXCESS_FILL_PENDING", "pe_update": "UNCHANGED_FROZEN_AT_FIRST_AUTHORITATIVE_NONZERO_FILL", "q_auth_update": "UNCHANGED_FROZEN_AT_FIRST_AUTHORITATIVE_NONZERO_FILL", "protected_update": "ENTER_PROTECTION_PENDING_EXTEND_STOP_TO_RECONCILED_POSITION", "pending_update": "RECORD_EXCESS_FILL_REDUCE_ONLY_TO_Q_AUTH_AND_HALT_RECONCILE", "next_action": "PROTECT_THEN_REDUCE_ONLY_AND_HALT_RECONCILE"},
    ],
}
MANAGEMENT_POLICY = {
    "pivot": {"serialization": {"window_seconds": 300, "exit_side_field": "LONG_BID_SHORT_ASK", "eligible_predicate": "LANE_QUALITY_VALID", "extreme": "LONG_MIN_SHORT_MAX", "tie_break": ["lane_clock", "capture_seq", "event_id"], "buffer": {"max_ticks": 2, "min_bps": "1"}, "rounding": "ROUND_OUT", "staleness_seconds": 2}, "missing_action": "NO_CHANGE_OR_FROZEN_HEALTH_EXIT_HALT"},
    "stop": {"candidate_set": ["S_ACK", "S_STRUCT", "S_BE_IF_QUALITY_DATA_ACK_HEALTHY_AND_NONCROSSING"], "s_struct_formula_id": "ROUND_OUT_PIVOT_MINUS_SIGNED_BUFFER", "s_be_formula_id": "ROUND_PROTECTIVE_PE_PLUS_SIGNED_EXCLUSIVE_COST_OVER_Q", "s_be_cost_components": ["C_INCURRED", "C_EXIT_WORST", "TAIL"], "s_be_quantity_denominator": "OPEN_Q", "monotonic_rule": "SIGNED_STOP_NONDECREASING_AFTER_ACK", "locked_net_condition": "ACK_AND_LOCKED_NET_NONNEGATIVE", "crossing_action": "REDUCE_ONLY_EXIT", "ack_required": True, "rounding": "ROUND_PROTECTIVE", "old_barrier_authority": "OLD_ACKED_BARRIER_UNTIL_NEW_ACK"},
    "locked_net": {"formula_id": "GROSS_REALIZED_PLUS_Q_TIMES_SIGNED_STOP_MINUS_INCURRED_MINUS_EXIT_WORST_MINUS_TAIL", "exclusive_cost_accounting": True, "cost_scope": "INCURRED_PLUS_FUTURE_EXIT_WORST_PLUS_TAIL_EXACTLY_ONCE"},
    "target": {"boundary": {"window_seconds": 300, "max_extension_r_multiple": "0.5", "t_cap_r_multiple": "3", "lane_aware": True, "stable_id_required": True, "as_of_required": True, "rounding": "ROUND_TOWARD_ENTRY"}, "absolute_ev_rule": "LCB_EV_HOLD_GT_ZERO", "relative_ev_rule": "LCB_EV_HOLD_MINUS_EV_EXIT_NOW_GTE_EPSILON_HOLD_0_05R", "epsilon_hold_r_multiple": "0.05", "tie_break": ["max_lcb_relative_ev", "min_extension", "min_priority_rank", "lex_stable_id"], "crossing_action": "REDUCE_ONLY_EXIT", "ack_required": True, "ack_identity": "PRICE_QTY_ORDER_ID_REDUCE_ONLY_ACK", "old_barrier_authority": "OLD_ACKED_BARRIER_UNTIL_NEW_ACK"},
    "horizon_extension": "FORBIDDEN",
    "management_cadence_seconds": 1,
    "same_timestamp_rule": "STOP_FIRST",
    "target_ack_required": True,
    "priority": ["KILL_ACCOUNT_MISMATCH", "STOP_HIT", "PROTECTION_REPAIR", "STRUCTURE_EXIT", "TARGET_HIT", "TIMEOUT", "BARRIER_UPDATE", "NO_CHANGE"],
}
LABEL_POLICY_BODY = {
    "policy_definition": {"market_path": "DISPATCH_LABEL_POLICY_BY_CONTROL", "submission": "NO_FILL_SEPARATE_FROM_MARKET_PATH", "execution": "PARTIAL_FILL_AND_OPERATIONAL_OVERRIDE_SEPARATE", "late_partial_fill": "KEEP_FROZEN_PE_Q_AUTH_RECORD_EXCESS_PROTECT_REDUCE_RECONCILE"},
    "market_path_labels": ["TP", "SL", "STRUCTURE_EXIT", "TIMEOUT"],
    "submission_label": "NO_FILL",
    "execution_labels": ["PARTIAL_FILL", "OPERATIONAL_OVERRIDE"],
    "path_selection": "LABEL_POLICY_BY_CONTROL_IS_SOLE_AUTHORITY",
    "same_timestamp_rule": "STOP_FIRST",
    "horizon": {"h0_seconds": 3600, "label_tail_source": "CHRONOLOGY_ROLE_LABEL_TAIL_SECONDS", "extension": "FORBIDDEN"},
    "late_partial_fill_semantics": "FROZEN_PE_Q_AUTH_RECORD_EXCESS_PROTECT_REDUCE_RECONCILE",
    "label_policy_by_control": {"C0": "NO_MARKET_PATH", "C1": "FIRST_HIT_FIXED_S0_T0_H0", "C2": "FIRST_HIT_FIXED_S0_T0_H0", "C3": "FIRST_HIT_FIXED_S0_T0_H0", "C4": "FIRST_HIT_FIXED_S0_T0_H0", "Cmu": "FIRST_HIT_FIXED_S0_T0_H0", "C5": "FIRST_HIT_DYNAMIC_PI_EXIT_EXACT_C4_FILL"},
}
HOLDOUT_RECEIPT_SCHEMA = {
    "required_binding_names": ["contract_digest", "candidate_digest", "code_digest", "data_digest", "labels_digest", "chronology_digest", "registry_digest"],
    "binding_value_rule": "UNPOPULATED_UNTIL_FUTURE_AUTHORIZATION",
    "digest_rule": "LOWERCASE_SHA256_ONLY_WHEN_OPENED",
}
TOP_LEVEL_FIELDS = {
    "schema_version", "contract_id", "status", "evidence_level", "scope",
    "authorization", "freeze_eligibility", "market_data_policy", "outcome_policy",
    "execution_policy", "strategy_implementation_binding", "review_tooling_binding",
    "role_lane_policy", "chronology", "controls", "signal_contract", "entry_contract",
    "risk_execution_contract", "management_contract", "ledger_contract",
    "experiment_contract", "error_attribution", "acceptance_contract", "holdout_receipt", "label_contract",
}
PLACEHOLDER_RE = re.compile(r"\b(TBD|REQUIRED|PENDING|UNRESOLVED)\b", re.IGNORECASE)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
DECIMAL_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d*[1-9])?")


class RsiResearchContractError(ValueError):
    pass


def _decimal(value: Any, name: str, *, minimum: str | None = None, maximum: str | None = None) -> Decimal:
    """Accept only canonical non-exponent Decimal strings; JSON floats fail closed."""
    if not isinstance(value, str) or DECIMAL_RE.fullmatch(value) is None:
        raise RsiResearchContractError(f"{name} must be a canonical Decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RsiResearchContractError(f"{name} must be a finite Decimal") from exc
    if parsed == 0 and value.startswith("-"):
        raise RsiResearchContractError(f"{name} must not use negative zero")
    if not parsed.is_finite() or (minimum is not None and parsed < Decimal(minimum)) or (maximum is not None and parsed > Decimal(maximum)):
        raise RsiResearchContractError(f"{name} is outside its frozen range")
    return parsed


def _expect_mapping(value: Any, name: str, fields: tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RsiResearchContractError(f"{name} must be an object")
    missing = [field for field in fields if field not in value]
    if missing:
        raise RsiResearchContractError(f"{name} missing fields: {', '.join(missing)}")
    return value


def _expect_list(value: Any, name: str, *, non_empty: bool = True) -> list[Any]:
    if not isinstance(value, list) or (non_empty and not value):
        raise RsiResearchContractError(f"{name} must be a {'non-empty ' if non_empty else ''}array")
    return value


def _expect_exact_keys(value: Mapping[str, Any], name: str, expected: set[str]) -> None:
    keys = set(value)
    if keys != expected:
        raise RsiResearchContractError(f"{name} keys must be exactly {sorted(expected)}")


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RsiResearchContractError(f"{name} must be a non-empty UTC Z timestamp")
    try:
        return parse_utc(value)
    except (TypeError, ValueError) as exc:
        raise RsiResearchContractError(f"{name} must be a valid UTC timestamp") from exc


def _check_no_placeholders(value: Any, path: str = "contract") -> None:
    if isinstance(value, str):
        if not value.strip() or PLACEHOLDER_RE.search(value):
            raise RsiResearchContractError(f"{path} contains an empty or placeholder string")
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise RsiResearchContractError(f"{path} contains an invalid key")
            if key in {"outcome", "outcomes", "result", "results", "evidence_payload", "input_artifacts"}:
                raise RsiResearchContractError(f"{path}.{key} is forbidden in an outcome-free contract")
            _check_no_placeholders(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_no_placeholders(child, f"{path}[{index}]")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _relative_file(root: Path, value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise RsiResearchContractError(f"{name}.path must be a non-empty relative path")
    resolved_root = root.resolve()
    target = (resolved_root / value).resolve()
    if resolved_root not in target.parents or not target.is_file():
        raise RsiResearchContractError(f"{name}.path must resolve to a workspace file")
    return target


def _validate_review_tooling(binding: Any, root: Path) -> dict[str, dict[str, str]]:
    raw = _expect_mapping(binding, "review_tooling_binding", ("bindings",))
    if set(raw) != {"bindings"}:
        raise RsiResearchContractError("review_tooling_binding may contain only bindings")
    items = _expect_list(raw["bindings"], "review_tooling_binding.bindings")
    expected_paths = {"archive/authority/CORE_TRADING_THEORY_v2_1.md", "trade_system/rsi_research_contract.py"}
    observed: dict[str, dict[str, str]] = {}
    for index, item in enumerate(items):
        entry = _expect_mapping(item, f"review_tooling_binding.bindings[{index}]", ("id", "path", "sha256"))
        if set(entry) != {"id", "path", "sha256"} or not isinstance(entry["id"], str) or not entry["id"] or not _is_sha256(entry["sha256"]):
            raise RsiResearchContractError("review tooling binding must have id, relative path and lowercase SHA-256")
        path = str(entry["path"])
        if path in observed:
            raise RsiResearchContractError("review tooling bindings must not repeat a path")
        target = _relative_file(root, path, "review tooling binding")
        if sha256_file(target) != entry["sha256"]:
            raise RsiResearchContractError(f"review tooling SHA-256 drift: {path}")
        observed[path] = {"id": entry["id"], "sha256": entry["sha256"]}
    if set(observed) != expected_paths:
        raise RsiResearchContractError("review tooling bindings must bind only CORE theory and this validator")
    return observed


def _validate_chronology(value: Any) -> None:
    raw = _expect_mapping(value, "chronology", ("windows", "pre_access_seen_registry"))
    _expect_exact_keys(raw, "chronology", {"windows", "pre_access_seen_registry"})
    windows = _expect_list(raw["windows"], "chronology.windows")
    if len(windows) != 3:
        raise RsiResearchContractError("chronology requires exactly DEVELOPMENT, CALIBRATION and HOLDOUT")
    expected_roles = ("DEVELOPMENT", "CALIBRATION", "HOLDOUT")
    previous: tuple[datetime, dict[str, Any]] | None = None
    for index, role in enumerate(expected_roles):
        item = _expect_mapping(windows[index], f"chronology.windows[{index}]", ("role", "start", "end", "warmup_seconds", "embargo_seconds", "label_tail_seconds"))
        if item.get("role") != role or set(item) != {"role", "start", "end", "warmup_seconds", "embargo_seconds", "label_tail_seconds"}:
            raise RsiResearchContractError("chronology roles and fields must be fixed in DEVELOPMENT/CALIBRATION/HOLDOUT order")
        start, end = _utc(item["start"], f"chronology.{role}.start"), _utc(item["end"], f"chronology.{role}.end")
        if start >= end or (previous is not None and start <= previous[0]):
            raise RsiResearchContractError("chronology windows must be ordered, non-overlapping UTC intervals")
        if any(not isinstance(item[field], int) or item[field] <= 0 for field in ("warmup_seconds", "embargo_seconds", "label_tail_seconds")):
            raise RsiResearchContractError("chronology warmup, embargo and label tail must be positive integers")
        if previous is not None:
            previous_end, previous_item = previous
            required_gap_end = previous_end.timestamp() + previous_item["label_tail_seconds"] + item["embargo_seconds"]
            next_eligible_start = start.timestamp() - item["warmup_seconds"]
            if required_gap_end > next_eligible_start:
                raise RsiResearchContractError("chronology warmup/embargo/label-tail buffers overlap across roles")
        previous = (end, item)
    seen = _expect_mapping(raw["pre_access_seen_registry"], "chronology.pre_access_seen_registry", ("status", "conflict_action"))
    if seen != {"status": "UNREAD_CANDIDATE_ONLY", "conflict_action": "REJECT"}:
        raise RsiResearchContractError("chronology must reject a pre-access seen-registry conflict")


def _validate_controls(value: Any) -> None:
    controls = _expect_list(value, "controls")
    if len(controls) != len(CONTROL_TABLE):
        raise RsiResearchContractError("controls must contain exactly seven canonical control dictionaries")
    for index, expected in enumerate(CONTROL_TABLE):
        row = _expect_mapping(controls[index], f"controls[{index}]")
        _expect_exact_keys(row, f"controls[{index}]", set(expected))
        if row != expected:
            raise RsiResearchContractError(f"controls[{index}] must exactly match canonical control {expected['control_id']}")


def _validate_contract_blocks(raw: Mapping[str, Any]) -> None:
    signal = _expect_mapping(raw["signal_contract"], "signal_contract", ("rsi", "lane_clock", "drl", "regime", "u_lifecycle"))
    _expect_exact_keys(signal, "signal_contract", {"rsi", "lane_clock", "drl", "regime", "u_lifecycle"})
    rsi = _expect_mapping(signal["rsi"], "signal_contract.rsi", ("period", "long", "short", "c1_c2_event_ledger"))
    if rsi["period"] != 14 or rsi["long"] != {"threshold": 30, "operator": "LTE"} or rsi["short"] != {"threshold": 70, "operator": "GTE"}:
        raise RsiResearchContractError("RSI must be the independent 14/30/70 baseline")
    drl = _expect_mapping(signal["drl"], "signal_contract.drl", ("tuple", "new_factor_or_score", "long", "short", "staleness_seconds", "missing_action"))
    _expect_exact_keys(drl, "signal_contract.drl", {"tuple", "new_factor_or_score", "long", "short", "staleness_seconds", "missing_action"})
    drl_fields = {"d_formula_id", "d_source", "d_window_seconds", "d_threshold", "r_formula_id", "r_source", "r_window_seconds", "r_threshold", "l_formula_id", "l_source", "l_window_seconds", "l_threshold", "responding_formula_id", "responding_source", "responding_window_seconds", "responding_threshold", "staleness_seconds", "zero_denominator_action", "missing_action", "production_authorization"}
    for side in ("long", "short"):
        item = _expect_mapping(drl[side], f"signal_contract.drl.{side}")
        _expect_exact_keys(item, f"signal_contract.drl.{side}", drl_fields)
        if any(type(item[field]) is not int or item[field] <= 0 for field in ("d_window_seconds", "r_window_seconds", "l_window_seconds", "responding_window_seconds", "staleness_seconds")) or item["zero_denominator_action"] != "UNKNOWN_ABSTAIN" or item["missing_action"] != "UNKNOWN_ABSTAIN" or item["production_authorization"] != FORBIDDEN:
            raise RsiResearchContractError("DRL side definition must be explicit, bounded and non-production")
        d_threshold = _decimal(item["d_threshold"], f"signal_contract.drl.{side}.d_threshold", minimum="-1", maximum="1")
        r_threshold = _decimal(item["r_threshold"], f"signal_contract.drl.{side}.r_threshold", minimum="0", maximum="1")
        l_threshold = _decimal(item["l_threshold"], f"signal_contract.drl.{side}.l_threshold", minimum="-1", maximum="1")
        responding_threshold = _decimal(item["responding_threshold"], f"signal_contract.drl.{side}.responding_threshold", minimum="0", maximum="10000")
        if r_threshold == 0 or responding_threshold == 0 or l_threshold >= 0 or (side == "long" and d_threshold <= 0) or (side == "short" and d_threshold >= 0):
            raise RsiResearchContractError("DRL threshold signs and ranges must remain explicit")
    regime = _expect_mapping(signal["regime"], "signal_contract.regime", ("k_gate_window_seconds", "formula_id", "source", "long_threshold", "short_threshold", "staleness_seconds", "missing_action", "zero_denominator_action", "production_authorization"))
    _expect_exact_keys(regime, "signal_contract.regime", {"k_gate_window_seconds", "formula_id", "source", "long_threshold", "short_threshold", "staleness_seconds", "missing_action", "zero_denominator_action", "production_authorization"})
    if regime["k_gate_window_seconds"] != 14400 or type(regime["staleness_seconds"]) is not int or regime["staleness_seconds"] != 900 or regime["missing_action"] != "UNKNOWN_ABSTAIN" or regime["zero_denominator_action"] != "USE_1E_MINUS_8_FLOOR" or regime["production_authorization"] != FORBIDDEN:
        raise RsiResearchContractError("regime/K definition must use explicit E0 hypothesis values")
    long_regime = _decimal(regime["long_threshold"], "signal_contract.regime.long_threshold", minimum="0", maximum="100")
    short_regime = _decimal(regime["short_threshold"], "signal_contract.regime.short_threshold", minimum="0", maximum="100")
    if long_regime == 0 or short_regime == 0:
        raise RsiResearchContractError("regime thresholds must be positive")
    lane = _expect_mapping(signal["lane_clock"], "signal_contract.lane_clock", ("actual_only", "reconstructed_causal_development"))
    if lane["actual_only"] != {"availability_kind": "ACTUAL", "as_of_field": "available_at"}:
        raise RsiResearchContractError("ACTUAL lane clock is invalid")
    reconstructed = _expect_mapping(lane["reconstructed_causal_development"], "reconstructed lane", ("availability_kind", "as_of_field", "pure_function_inputs", "forbidden_clock_inputs", "authorization"))
    if reconstructed["availability_kind"] != "RECONSTRUCTED" or reconstructed["as_of_field"] != "reconstructed_available_at" or reconstructed["pure_function_inputs"] != ["raw_exchange_time", "source_sequence_or_frozen_import_key", "schema_version", "fixed_release_lag"] or reconstructed["forbidden_clock_inputs"] != ["replay_wall_clock", "mtime", "later_capture_time"] or reconstructed["authorization"] != "SEPARATE_FUTURE_AUTHORIZATION_REQUIRED":
        raise RsiResearchContractError("reconstructed causal lane is invalid")
    lifecycle = _expect_mapping(signal["u_lifecycle"], "signal_contract.u_lifecycle", ("generation", "c2_opportunity", "control_specific_lifecycle"))
    if lifecycle["generation"] != "GATE_NEUTRAL_CANDIDATE_NEUTRAL_COOLDOWN_DEDUP" or lifecycle["control_specific_lifecycle"] is not True:
        raise RsiResearchContractError("U lifecycle must remain gate-neutral and control-specific")
    c2 = _expect_mapping(lifecycle["c2_opportunity"], "signal_contract.u_lifecycle.c2_opportunity", ("observation_ttl_seconds", "overlap_rule", "terminal_priority"))
    if not isinstance(c2["observation_ttl_seconds"], int) or c2["observation_ttl_seconds"] <= 0 or c2["overlap_rule"] != "SAME_OPPORTUNITY_ID_BY_CANDIDATE_NEUTRAL_DEDUP" or not isinstance(c2["terminal_priority"], list) or not c2["terminal_priority"]:
        raise RsiResearchContractError("C2 opportunity lifecycle is incomplete")
    entry = _expect_mapping(raw["entry_contract"], "entry_contract")
    _expect_exact_keys(entry, "entry_contract", {"z_regime_control_indexed", "c1_c2_read_k", "p_tau", "entryzone_sets", "ttl_seconds", "z_liq", "ev", "candidate_tie_break", "i0_path", "g0_selection", "rounding", "geometry"})
    if entry.get("z_regime_control_indexed") is not True or entry.get("c1_c2_read_k") is not False or entry.get("candidate_tie_break") != ["max_lcb_ev_submit", "min_worst_risk", "long_lower_short_higher_price", "canonical_tick_index"]:
        raise RsiResearchContractError("entry contract must preserve control-indexed no-K EntryZone semantics")
    if entry["entryzone_sets"] != ["Z_ANCHOR", "Z_REGIME", "Z_LIQ", "Z_GEOM", "Z_EV"] or not isinstance(entry["ttl_seconds"], int) or entry["ttl_seconds"] <= 0 or entry["rounding"] != {"round_out": "LONG_FLOOR_SHORT_CEIL", "round_toward_entry": "LONG_FLOOR_SHORT_CEIL", "round_protective": "LONG_CEIL_SHORT_FLOOR"}:
        raise RsiResearchContractError("entry contract must contain explicit EntryZone, TTL and rounding semantics")
    p_tau = _expect_mapping(entry["p_tau"], "entry_contract.p_tau")
    _expect_exact_keys(p_tau, "entry_contract.p_tau", {"long_lower_bps_from_anchor", "long_upper_bps_from_anchor", "short_lower_bps_from_anchor", "short_upper_bps_from_anchor", "tick_size", "tick_source", "production_authorization"})
    long_lower = _decimal(p_tau["long_lower_bps_from_anchor"], "entry_contract.p_tau.long_lower_bps_from_anchor", minimum="-10000", maximum="10000")
    long_upper = _decimal(p_tau["long_upper_bps_from_anchor"], "entry_contract.p_tau.long_upper_bps_from_anchor", minimum="-10000", maximum="10000")
    short_lower = _decimal(p_tau["short_lower_bps_from_anchor"], "entry_contract.p_tau.short_lower_bps_from_anchor", minimum="-10000", maximum="10000")
    short_upper = _decimal(p_tau["short_upper_bps_from_anchor"], "entry_contract.p_tau.short_upper_bps_from_anchor", minimum="-10000", maximum="10000")
    tick_size = _decimal(p_tau["tick_size"], "entry_contract.p_tau.tick_size", minimum="0", maximum="1000000")
    if long_lower > long_upper or short_lower > short_upper or tick_size == 0 or p_tau["tick_source"] != "FROZEN_INSTRUMENT_RULE_PROXY" or p_tau["production_authorization"] != FORBIDDEN:
        raise RsiResearchContractError("entry price bounds and tick size must be canonical and ordered")
    z_liq = _expect_mapping(entry["z_liq"], "entry_contract.z_liq")
    _expect_exact_keys(z_liq, "entry_contract.z_liq", {"max_spread_bps", "max_slippage_bps", "min_capacity_multiple_of_q", "quote_freshness_seconds"})
    if any(_decimal(z_liq[field], f"entry_contract.z_liq.{field}", minimum="0", maximum="100000") == 0 for field in ("max_spread_bps", "max_slippage_bps", "min_capacity_multiple_of_q")) or type(z_liq["quote_freshness_seconds"]) is not int or z_liq["quote_freshness_seconds"] <= 0:
        raise RsiResearchContractError("liquidity bounds must use positive canonical decimals and integer freshness")
    ev = _expect_mapping(entry["ev"], "entry_contract.ev")
    _expect_exact_keys(ev, "entry_contract.ev", {"epsilon_ev_r_multiple", "lcb_confidence"})
    epsilon_ev = _decimal(ev["epsilon_ev_r_multiple"], "entry_contract.ev.epsilon_ev_r_multiple", minimum="0", maximum="100")
    lcb_confidence = _decimal(ev["lcb_confidence"], "entry_contract.ev.lcb_confidence", minimum="0", maximum="1")
    if epsilon_ev == 0 or lcb_confidence == 0:
        raise RsiResearchContractError("EV thresholds must be positive")
    g0 = _expect_mapping(entry["g0_selection"], "entry_contract.g0_selection")
    _expect_exact_keys(g0, "entry_contract.g0_selection", {"structure_window_seconds", "minimum_favorable_bps", "tie_break"})
    if type(g0["structure_window_seconds"]) is not int or g0["structure_window_seconds"] <= 0 or _decimal(g0["minimum_favorable_bps"], "entry_contract.g0_selection.minimum_favorable_bps", minimum="0", maximum="100000") == 0:
        raise RsiResearchContractError("G0 selection must use integer time and positive canonical bps")
    geometry = _expect_mapping(entry["geometry"], "entry_contract.geometry")
    _expect_exact_keys(geometry, "entry_contract.geometry", {"b0", "r_min", "r_cap", "h0_seconds", "t_cap_r_multiple", "revalidate_after_round", "missing_action"})
    b0 = _expect_mapping(geometry["b0"], "entry_contract.geometry.b0")
    _expect_exact_keys(b0, "entry_contract.geometry.b0", {"max_ticks", "min_bps"})
    r_min = _decimal(geometry["r_min"], "entry_contract.geometry.r_min", minimum="0", maximum="10000")
    r_cap = _decimal(geometry["r_cap"], "entry_contract.geometry.r_cap", minimum="0", maximum="10000")
    t_cap = _decimal(geometry["t_cap_r_multiple"], "entry_contract.geometry.t_cap_r_multiple", minimum="0", maximum="10000")
    if type(b0["max_ticks"]) is not int or b0["max_ticks"] <= 0 or _decimal(b0["min_bps"], "entry_contract.geometry.b0.min_bps", minimum="0", maximum="100000") == 0 or type(geometry["h0_seconds"]) is not int or geometry["h0_seconds"] <= 0 or r_min <= 0 or r_cap < r_min or t_cap < r_min or geometry["revalidate_after_round"] is not True or geometry["missing_action"] != "ABSTAIN":
        raise RsiResearchContractError("geometry must use canonical decimals and ordered reward/risk bounds")
    risk = _expect_mapping(raw["risk_execution_contract"], "risk_execution_contract")
    _expect_exact_keys(risk, "risk_execution_contract", {"initial_levels", "sizing_inputs", "rsi_in_sizing", "first_fill", "protection", "late_fill"})
    protection = _expect_mapping(risk["protection"], "risk_execution_contract.protection")
    _expect_exact_keys(protection, "risk_execution_contract.protection", set(PROTECTION_POLICY))
    if risk["initial_levels"] != ["I0", "G0", "S0", "T0", "H0", "T_CAP"] or risk["rsi_in_sizing"] != FORBIDDEN or risk["first_fill"] != "AUTHORITATIVE_CUMULATIVE_Q_AUTH_VWAP_AND_FIXED_LEVELS" or risk["late_fill"] != "PROTECT_THEN_REDUCE_ONLY_TO_Q_AUTH_THEN_RECONCILE" or protection != PROTECTION_POLICY:
        raise RsiResearchContractError("risk/execution contract must contain fixed sizing and protection semantics")
    sizing = _expect_mapping(risk["sizing_inputs"], "risk_execution_contract.sizing_inputs")
    sizing_decimal_fields = {"reference_equity_usdt", "episode_risk_budget_bps", "max_notional_usdt", "max_leverage", "fee_bps_per_side", "base_slippage_bps_per_side", "stress_slippage_bps_per_side", "funding_buffer_bps", "tail_bps", "lot_step", "min_notional_usdt", "initial_margin_rate", "max_venue_qty"}
    _expect_exact_keys(sizing, "risk_execution_contract.sizing_inputs", sizing_decimal_fields | {"formula_id", "source", "missing_action", "production_authorization"})
    sizing_values = {field: _decimal(sizing[field], f"risk_execution_contract.sizing_inputs.{field}", minimum="0", maximum="1000000000000") for field in sizing_decimal_fields}
    if any(value == 0 for value in sizing_values.values()) or sizing_values["initial_margin_rate"] > 1 or sizing_values["max_notional_usdt"] > sizing_values["reference_equity_usdt"] or sizing["source"] != "DETERMINISTIC_RESEARCH_PROXY" or sizing["missing_action"] != "ABSTAIN" or sizing["production_authorization"] != FORBIDDEN:
        raise RsiResearchContractError("sizing inputs must be positive, bounded canonical decimals")
    pending_caps = _expect_mapping(protection["pending_caps"], "risk_execution_contract.protection.pending_caps")
    _expect_exact_keys(pending_caps, "risk_execution_contract.protection.pending_caps", {"FIRST_FILL_PENDING", "EXCESS_FILL_PENDING"})
    for cause, cap in pending_caps.items():
        _expect_exact_keys(_expect_mapping(cap, f"risk_execution_contract.protection.pending_caps.{cause}"), f"risk_execution_contract.protection.pending_caps.{cause}", {"max_seconds", "max_quantity_fraction", "fraction_denominator", "max_risk_equivalent_usdt", "all_caps_must_hold"})
        fraction = _decimal(cap["max_quantity_fraction"], f"risk_execution_contract.protection.pending_caps.{cause}.max_quantity_fraction", minimum="0", maximum="1")
        risk_cap = _decimal(cap["max_risk_equivalent_usdt"], f"risk_execution_contract.protection.pending_caps.{cause}.max_risk_equivalent_usdt", minimum="0", maximum="1000000000000")
        if type(cap["max_seconds"]) is not int or cap["max_seconds"] <= 0 or fraction == 0 or risk_cap == 0 or cap["fraction_denominator"] != "Q_AUTH" or cap["all_caps_must_hold"] is not True:
            raise RsiResearchContractError("cause-specific pending exposure caps must be feasible and explicit")
    management = _expect_mapping(raw["management_contract"], "management_contract")
    _expect_exact_keys(management, "management_contract", set(MANAGEMENT_POLICY))
    pivot = _expect_mapping(management["pivot"], "management_contract.pivot", ("serialization", "missing_action"))
    stop = _expect_mapping(management["stop"], "management_contract.stop", ("candidate_set", "crossing_action", "ack_required"))
    target = _expect_mapping(management["target"], "management_contract.target", ("boundary", "absolute_ev_rule", "relative_ev_rule", "tie_break", "ack_required"))
    _expect_exact_keys(pivot, "management_contract.pivot", {"serialization", "missing_action"})
    _expect_exact_keys(stop, "management_contract.stop", set(MANAGEMENT_POLICY["stop"]))
    _expect_exact_keys(target, "management_contract.target", set(MANAGEMENT_POLICY["target"]))
    if management != MANAGEMENT_POLICY:
        raise RsiResearchContractError("management contract must retain Pivot, stop and target fail-closed semantics")
    pivot_serialization = _expect_mapping(pivot["serialization"], "management_contract.pivot.serialization")
    _expect_exact_keys(pivot_serialization, "management_contract.pivot.serialization", {"window_seconds", "exit_side_field", "eligible_predicate", "extreme", "tie_break", "buffer", "rounding", "staleness_seconds"})
    pivot_buffer = _expect_mapping(pivot_serialization["buffer"], "management_contract.pivot.serialization.buffer")
    _expect_exact_keys(pivot_buffer, "management_contract.pivot.serialization.buffer", {"max_ticks", "min_bps"})
    if any(type(pivot_serialization[field]) is not int or pivot_serialization[field] <= 0 for field in ("window_seconds", "staleness_seconds")) or type(pivot_buffer["max_ticks"]) is not int or pivot_buffer["max_ticks"] <= 0 or _decimal(pivot_buffer["min_bps"], "management_contract.pivot.serialization.buffer.min_bps", minimum="0", maximum="100000") == 0:
        raise RsiResearchContractError("pivot serialization must use integer time and canonical decimal bps")
    target_boundary = _expect_mapping(target["boundary"], "management_contract.target.boundary")
    _expect_exact_keys(target_boundary, "management_contract.target.boundary", set(MANAGEMENT_POLICY["target"]["boundary"]))
    max_extension = _decimal(target_boundary["max_extension_r_multiple"], "management_contract.target.boundary.max_extension_r_multiple", minimum="0", maximum="10000")
    target_cap = _decimal(target_boundary["t_cap_r_multiple"], "management_contract.target.boundary.t_cap_r_multiple", minimum="0", maximum="10000")
    epsilon_hold = _decimal(target["epsilon_hold_r_multiple"], "management_contract.target.epsilon_hold_r_multiple", minimum="0", maximum="10000")
    if type(target_boundary["window_seconds"]) is not int or target_boundary["window_seconds"] <= 0 or max_extension == 0 or target_cap == 0 or epsilon_hold == 0 or target_boundary["lane_aware"] is not True or target_boundary["stable_id_required"] is not True or target_boundary["as_of_required"] is not True:
        raise RsiResearchContractError("target management must use positive canonical decimal bounds")
    ledger = _expect_mapping(raw["ledger_contract"], "ledger_contract", ("write_mode", "required_fields"))
    _expect_exact_keys(ledger, "ledger_contract", {"write_mode", "required_fields"})
    if ledger["write_mode"] != "IMMUTABLE_HASH_CHAIN" or ledger["required_fields"] != LEDGER_REQUIRED_FIELDS:
        raise RsiResearchContractError("ledger contract is incomplete")
    hypotheses = _expect_mapping(raw["experiment_contract"], "experiment_contract", ("hypothesis_mapping", "comparison_scope", "one_candidate_only", "error_attribution_rule"))
    _expect_exact_keys(hypotheses, "experiment_contract", {"hypothesis_mapping", "comparison_scope", "one_candidate_only", "error_attribution_rule"})
    if hypotheses["hypothesis_mapping"] != HYPOTHESIS_MAPPING or hypotheses["comparison_scope"] != {"H-013": "EXIT_ONLY_EXACT_C4_SUBMISSION_FILL"} or hypotheses["one_candidate_only"] is not True or hypotheses["error_attribution_rule"] != "ONE_LAYER_PER_NEW_VERSION":
        raise RsiResearchContractError("experiment hypothesis mapping is invalid")
    attribution = _expect_mapping(raw["error_attribution"], "error_attribution", ("layers", "same_seen_window_reuse", "cross_layer_delta", "backtest_risk_cost_rewrite"))
    _expect_exact_keys(attribution, "error_attribution", {"layers", "same_seen_window_reuse", "cross_layer_delta", "backtest_risk_cost_rewrite"})
    if attribution["layers"] != ["DATA_AVAILABILITY", "RSI", "REGIME", "DRL", "ENTRY", "EXIT", "COST", "TAIL", "COVERAGE"] or attribution["same_seen_window_reuse"] != FORBIDDEN or attribution["cross_layer_delta"] != FORBIDDEN or attribution["backtest_risk_cost_rewrite"] != FORBIDDEN:
        raise RsiResearchContractError("error attribution contract is incomplete")
    acceptance = _expect_mapping(raw["acceptance_contract"], "acceptance_contract", ("contract_review", "synthetic_fixture_policy", "market_validity_claim", "strategy_execution_claim"))
    _expect_exact_keys(acceptance, "acceptance_contract", {"contract_review", "synthetic_fixture_policy", "market_validity_claim", "strategy_execution_claim", "metrics"})
    if acceptance["contract_review"] != "STATIC_VALIDATOR_AND_CANONICAL_SHA256_ONLY" or acceptance["synthetic_fixture_policy"] != "PURE_SYNTHETIC_NO_OUTCOME" or acceptance["market_validity_claim"] != FORBIDDEN or acceptance["strategy_execution_claim"] != FORBIDDEN:
        raise RsiResearchContractError("acceptance contract is incomplete")
    metrics = _expect_mapping(acceptance["metrics"], "acceptance_contract.metrics", ("primary", "minimum_effective_episodes", "minimum_per_direction", "folds", "minimum_fold_passes", "confidence_level", "one_candidate_only", "hypothesis_status"))
    _expect_exact_keys(metrics, "acceptance_contract.metrics", {"primary", "minimum_effective_episodes", "minimum_per_direction", "folds", "minimum_fold_passes", "confidence_level", "one_candidate_only", "hypothesis_status"})
    confidence = _decimal(metrics["confidence_level"], "acceptance_contract.metrics.confidence_level", minimum="0", maximum="1")
    if metrics["primary"] != ["LOG_LOSS", "BRIER", "LCB_EV"] or metrics["minimum_effective_episodes"] != 600 or metrics["minimum_per_direction"] != 100 or metrics["folds"] != 5 or metrics["minimum_fold_passes"] != 4 or confidence == 0 or metrics["one_candidate_only"] is not True or metrics["minimum_fold_passes"] > metrics["folds"] or metrics["minimum_effective_episodes"] < metrics["minimum_per_direction"] * metrics["folds"]:
        raise RsiResearchContractError("acceptance metrics must use the frozen E0 hypothesis thresholds")
    labels = _expect_mapping(raw["label_contract"], "label_contract")
    _expect_exact_keys(labels, "label_contract", set(LABEL_POLICY_BODY) | {"policy_sha256"})
    if labels["policy_definition"]["market_path"] in {"FIRST_HIT_DYNAMIC_BARRIER", "FIRST_HIT_FIXED_S0_T0_H0", "CONTROL_INDEXED_FIRST_HIT"} or labels["path_selection"] != "LABEL_POLICY_BY_CONTROL_IS_SOLE_AUTHORITY" or set(labels["label_policy_by_control"]) != set(CONTROL_IDS) or labels.get("policy_sha256") != canonical_sha256({key: value for key, value in labels.items() if key != "policy_sha256"}) or {key: value for key, value in labels.items() if key != "policy_sha256"} != LABEL_POLICY_BODY:
        raise RsiResearchContractError("label contract must separate market, submission and execution paths")


def validate_rsi_research_contract(raw: Any, *, workspace_root: Path) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        raise RsiResearchContractError("research contract must be an object")
    _expect_exact_keys(raw, "research contract", TOP_LEVEL_FIELDS)
    _check_no_placeholders(raw)
    if raw["schema_version"] != SCHEMA_VERSION or raw["contract_id"] != CONTRACT_ID or raw["status"] != REVIEW_READY or raw["evidence_level"] != EVIDENCE_LEVEL:
        raise RsiResearchContractError("research contract identity/status/evidence level are invalid")
    if raw["scope"] != "OUTCOME_FREE_RESEARCH_CONTRACT_ONLY" or raw["authorization"] != {"strategy_primitives": FORBIDDEN, "market_data": FORBIDDEN, "historical_data": FORBIDDEN, "backtest": FORBIDDEN, "calibration": FORBIDDEN, "holdout": FORBIDDEN, "paper": FORBIDDEN, "trading": FORBIDDEN} or raw["market_data_policy"] != FORBIDDEN or raw["outcome_policy"] != FORBIDDEN or raw["execution_policy"] != FORBIDDEN or raw["freeze_eligibility"] != REJECT_FREEZE:
        raise RsiResearchContractError("research contract must stay outcome-free and non-freezable")
    if raw["strategy_implementation_binding"] != {"authorization_status": "NOT_AUTHORIZED", "implementation_status": "ABSENT_BY_DESIGN", "bindings": [], "freeze_eligibility": REJECT_FREEZE}:
        raise RsiResearchContractError("strategy implementation binding must remain absent by design")
    lanes = _expect_mapping(raw["role_lane_policy"], "role_lane_policy")
    _expect_exact_keys(lanes, "role_lane_policy", {"DEVELOPMENT", "CALIBRATION", "HOLDOUT"})
    release_fields = {"policy_id", "sha256", "authorization", "purpose", "source_schema_rules"}
    source_rule_fields = {"source_id", "schema_version", "lag_seconds", "formula_id", "ordering_key", "missing_action"}
    development_source_rules = [
        {"source_id": "MARK_PRICE_15M", "schema_version": "mark-price-v1", "lag_seconds": 60, "formula_id": "FIXED_RELEASE_LAG_V1", "ordering_key": "SOURCE_SEQUENCE_OR_FROZEN_IMPORT_KEY", "missing_action": "UNKNOWN_ABSTAIN"},
        {"source_id": "MARK_PRICE_4H", "schema_version": "mark-price-v1", "lag_seconds": 60, "formula_id": "FIXED_RELEASE_LAG_V1", "ordering_key": "SOURCE_SEQUENCE_OR_FROZEN_IMPORT_KEY", "missing_action": "UNKNOWN_ABSTAIN"},
        {"source_id": "AGG_TRADE", "schema_version": "agg-trade-v1", "lag_seconds": 60, "formula_id": "FIXED_RELEASE_LAG_V1", "ordering_key": "SOURCE_SEQUENCE_OR_FROZEN_IMPORT_KEY", "missing_action": "UNKNOWN_ABSTAIN"},
        {"source_id": "BOOK_DEPTH", "schema_version": "book-depth-v1", "lag_seconds": 60, "formula_id": "FIXED_RELEASE_LAG_V1", "ordering_key": "SOURCE_SEQUENCE_OR_FROZEN_IMPORT_KEY", "missing_action": "UNKNOWN_ABSTAIN"},
        {"source_id": "OPEN_INTEREST", "schema_version": "open-interest-v1", "lag_seconds": 60, "formula_id": "FIXED_RELEASE_LAG_V1", "ordering_key": "SOURCE_SEQUENCE_OR_FROZEN_IMPORT_KEY", "missing_action": "UNKNOWN_ABSTAIN"},
    ]
    for role, window in zip(("DEVELOPMENT", "CALIBRATION", "HOLDOUT"), raw["chronology"]["windows"]):
        if window["role"] != role:
            raise RsiResearchContractError("role lane policy must bind exact chronology roles")
        lane = _expect_mapping(lanes[role], f"role_lane_policy.{role}")
        _expect_exact_keys(lane, f"role_lane_policy.{role}", {"lane", "availability_kind", "as_of_field", "authorization", "purpose", "release_policy"})
        release = _expect_mapping(lane["release_policy"], f"role_lane_policy.{role}.release_policy")
        _expect_exact_keys(release, f"role_lane_policy.{role}.release_policy", release_fields)
        if not _is_sha256(release["sha256"]) or release["sha256"] != canonical_sha256({key: value for key, value in release.items() if key != "sha256"}):
            raise RsiResearchContractError("role release policy SHA-256 must match its complete canonical body")
        source_rules = _expect_list(release["source_schema_rules"], f"role_lane_policy.{role}.release_policy.source_schema_rules", non_empty=False)
        for index, source_rule in enumerate(source_rules):
            _expect_exact_keys(_expect_mapping(source_rule, f"role_lane_policy.{role}.release_policy.source_schema_rules[{index}]"), f"role_lane_policy.{role}.release_policy.source_schema_rules[{index}]", source_rule_fields)
            if type(source_rule["lag_seconds"]) is not int or source_rule["lag_seconds"] < 0:
                raise RsiResearchContractError("role source release rules require non-negative integer lag")
    if lanes["DEVELOPMENT"]["lane"] != "RECONSTRUCTED_CAUSAL_DEVELOPMENT" or lanes["DEVELOPMENT"]["availability_kind"] != "RECONSTRUCTED" or lanes["DEVELOPMENT"]["as_of_field"] != "reconstructed_available_at" or lanes["DEVELOPMENT"]["authorization"] != "NOT_AUTHORIZED" or lanes["DEVELOPMENT"]["purpose"] != "CANDIDATE_ONLY" or lanes["DEVELOPMENT"]["release_policy"] != {**lanes["DEVELOPMENT"]["release_policy"], "policy_id": "rsi-reconstructed-causal-release.v0.2", "authorization": "NOT_AUTHORIZED", "purpose": "CANDIDATE_ONLY", "source_schema_rules": development_source_rules}:
        raise RsiResearchContractError("development lane must remain a not-authorized reconstructed candidate")
    for role in ("CALIBRATION", "HOLDOUT"):
        release = lanes[role]["release_policy"]
        if lanes[role]["lane"] != "NONE" or lanes[role]["availability_kind"] != "NONE" or lanes[role]["as_of_field"] != "NONE" or lanes[role]["authorization"] != "NOT_AUTHORIZED" or lanes[role]["purpose"] != "NO_ACCESS" or release["policy_id"] != "NO_RELEASE_POLICY" or release["authorization"] != "NOT_AUTHORIZED" or release["purpose"] != "NO_ACCESS" or release["source_schema_rules"] != []:
            raise RsiResearchContractError("calibration and holdout must reject reconstructed access")
    if lanes["CALIBRATION"]["release_policy"] != lanes["HOLDOUT"]["release_policy"]:
        raise RsiResearchContractError("calibration and holdout must use the same no-access release policy")
    _validate_chronology(raw["chronology"])
    _validate_controls(raw["controls"])
    _validate_contract_blocks(raw)
    receipt = _expect_mapping(raw["holdout_receipt"], "holdout_receipt")
    _expect_exact_keys(receipt, "holdout_receipt", {"status", "reuse_policy", "opened", "issuance", "future_receipt_schema", "state_machine", "transitions"})
    if receipt["status"] != "UNOPENED" or receipt["reuse_policy"] != "ONE_TIME_ONLY" or receipt["opened"] is not False or receipt["issuance"] != "NOT_AUTHORIZED" or receipt["future_receipt_schema"] != HOLDOUT_RECEIPT_SCHEMA or receipt["state_machine"] != ["UNOPENED", "OPENED_ONCE", "CONSUMED_ONCE"] or receipt["transitions"] != [{"from": "UNOPENED", "to": "OPENED_ONCE", "rule": "FUTURE_AUTHORIZED_ISSUANCE_ONLY"}, {"from": "OPENED_ONCE", "to": "CONSUMED_ONCE", "rule": "ONE_TIME_EVALUATION_ONLY"}]:
        raise RsiResearchContractError("holdout receipt must remain unopened and one-time-only")
    if canonical_sha256({key: value for key, value in raw.items() if key != "review_tooling_binding"}) != PINNED_SEMANTIC_SHA256:
        raise RsiResearchContractError("same schema_version and contract_id require the exact pinned semantic template")
    return _validate_review_tooling(raw["review_tooling_binding"], Path(workspace_root))


@dataclass(frozen=True)
class RsiResearchContract:
    contract_id: str
    raw: dict[str, Any]
    digest: str
    tooling_bindings: dict[str, dict[str, str]]

    @classmethod
    def load(cls, path: Path, *, workspace_root: Path | None = None) -> "RsiResearchContract":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RsiResearchContractError("cannot load RSI research contract") from exc
        root = Path(workspace_root).resolve() if workspace_root is not None else Path(path).resolve().parent.parent
        bindings = validate_rsi_research_contract(raw, workspace_root=root)
        return cls(contract_id=raw["contract_id"], raw=raw, digest=canonical_sha256(raw), tooling_bindings=bindings)

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.raw).encode("utf-8")

    def summary(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "schema_version": self.raw["schema_version"],
            "status": self.raw["status"],
            "evidence_level": self.raw["evidence_level"],
            "sha256": self.digest,
            "freeze_eligibility": self.raw["freeze_eligibility"],
            "market_data_or_execution_authorized": False,
            "review_tooling_binding_ids": {path: item["id"] for path, item in self.tooling_bindings.items()},
        }
