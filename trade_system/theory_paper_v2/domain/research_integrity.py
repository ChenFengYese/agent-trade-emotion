"""Pure contracts for continuous single-Strategy-Agent research.

This module is intentionally narrow.  It owns the two decisions that the
prospective v1.4 loop left implicit: replayable path-belief updates and an
action evaluation set that exists before an Agent may select an action.  It
does not collect data, call a model, write files, or grant execution authority.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_decimal, self_digest, verify_self_digest
from .portfolio_truth import (
    PortfolioTruthError,
    build_lot_position_truth,
    candidate_lot_scope,
)


class ResearchIntegrityError(ValueError):
    """A deterministic research-integrity contract was violated."""


SUPPORT_LEVELS = (
    "UNKNOWN",
    "WEAK",
    "PLAUSIBLE",
    "SUPPORTED",
    "DOMINANT",
    "INVALIDATED",
)
BELIEF_EVENT_OPERATIONS = frozenset(
    {"ADD", "SUPERSEDE", "EXPIRE", "SOFT_CONTRADICTION", "HARD_FALSIFIER"}
)
BELIEF_DIRECTIONS = frozenset(
    {"SUPPORT", "SOFT_CONTRADICTION", "HARD_FALSIFIER"}
)
ACTION_CLASSES = frozenset(
    {
        "HOLD",
        "OPEN",
        "ADD",
        "REDUCE",
        "PARTIAL_TAKE_PROFIT",
        "EXIT",
        "REENTER",
        "WAIT",
    }
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BELIEF_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "operation",
        "path_id",
        "evidence_id",
        "lineage_key",
        "direction",
        "strength",
        "available_at",
        "source_ref",
        "premise_ref",
        "supersedes_evidence_id",
    }
)
_CANDIDATE_FIELDS = frozenset(
    {
        "candidate_id",
        "source_cycle_index",
        "action_class",
        "sizing_id",
        "quantity_delta",
        "stop_price_after",
        "thesis_path_id",
        "evidence_refs",
        "rationale",
        "path_outcomes",
        "wait_until",
        "wait_for_observations",
        "target_lot_ids",
        "target_lot_role",
    }
)
_OUTCOME_FIELDS = frozenset(
    {
        "path_id",
        "source_cycle_index",
        "position_truth_digest",
        "process_id",
        "distinguishing_evidence_refs",
        "failure_trigger_refs",
        "position_consequence",
        "compatibility",
        "market_process",
        "failure_process",
        "opportunity_cost",
        "cost_risk_tradeoff",
    }
)
_REDUCTION_SIZE_CONTRACTS = {
    "REDUCE_25": ("REDUCE", Decimal("0.25")),
    "REDUCE_50": ("REDUCE", Decimal("0.50")),
    "REDUCE_75": ("REDUCE", Decimal("0.75")),
    "PARTIAL_25": ("PARTIAL_TAKE_PROFIT", Decimal("0.25")),
    "EXIT_100": ("EXIT", Decimal("1")),
}
_RISK_POLICY_FIELDS = frozenset(
    {
        "fee_rate",
        "slippage_rate",
        "initial_margin_rate",
        "max_gross_leverage",
        "portfolio_risk_cap_usdt",
        "symbol_risk_cap_usdt",
        "gross_notional_cap_usdt",
        "symbol_notional_cap_usdt",
    }
)


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ResearchIntegrityError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ResearchIntegrityError(code) from exc
    if not result.is_finite():
        raise ResearchIntegrityError(code)
    return result


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ResearchIntegrityError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchIntegrityError(code) from exc
    if parsed.tzinfo is None:
        raise ResearchIntegrityError(code)
    return parsed.astimezone(UTC)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise ResearchIntegrityError(code)
    return value


def _string_tuple(value: Any, code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ResearchIntegrityError(code)
    result = tuple(value)
    if (
        (not allow_empty and not result)
        or any(not isinstance(item, str) or not item for item in result)
        or len(result) != len(set(result))
    ):
        raise ResearchIntegrityError(code)
    return result


def _support_level(*, score: int, hard_falsified: bool, evidence_count: int) -> str:
    """Map an auditable ordinal balance to a label; never to a probability."""

    if hard_falsified:
        return "INVALIDATED"
    if evidence_count == 0:
        return "UNKNOWN"
    if score >= 5:
        return "DOMINANT"
    if score >= 3:
        return "SUPPORTED"
    if score >= 1:
        return "PLAUSIBLE"
    return "WEAK"


def _path_support_snapshot(
    active: Mapping[str, Mapping[str, Any]], path_id: str
) -> dict[str, Any]:
    rows = sorted(
        (row for row in active.values() if row["path_id"] == path_id),
        key=lambda row: (row["lineage_key"], row["evidence_id"]),
    )
    score = sum(
        row["strength"]
        if row["direction"] == "SUPPORT"
        else -row["strength"]
        for row in rows
        if row["direction"] != "HARD_FALSIFIER"
    )
    hard_ids = [
        row["evidence_id"]
        for row in rows
        if row["direction"] == "HARD_FALSIFIER"
    ]
    return {
        "support_level": _support_level(
            score=score, hard_falsified=bool(hard_ids), evidence_count=len(rows)
        ),
        "ordinal_balance": score,
        "active_evidence_ids": [row["evidence_id"] for row in rows],
        "active_hard_falsifier_ids": hard_ids,
    }


def reduce_path_beliefs(
    *,
    previous_state: Mapping[str, Any] | None,
    belief_events: Sequence[Mapping[str, Any]],
    path_ids: Sequence[str],
    decision_at: str,
) -> dict[str, Any]:
    """Reduce explicit evidence lifecycle events into the next path state.

    Active evidence persists until a SUPERSEDE or EXPIRE event names it.
    Therefore missing data and Agent silence cannot silently lower support.
    """

    cutoff = _timestamp(decision_at, "BELIEF_DECISION_TIME_INVALID")
    paths = tuple(path_ids)
    if not paths or len(paths) != len(set(paths)) or any(not item for item in paths):
        raise ResearchIntegrityError("BELIEF_PATH_SET_INVALID")
    active: dict[str, dict[str, Any]] = {}
    known_evidence_ids: set[str] = set()
    known_event_ids: set[str] = set()
    previous_digest: str | None = None
    revision = 1
    prior_levels = {path_id: "UNKNOWN" for path_id in paths}
    if previous_state is not None:
        try:
            previous_digest = verify_self_digest(previous_state, "belief_state_digest")
        except ValueError as exc:
            raise ResearchIntegrityError("BELIEF_PRIOR_DIGEST_INVALID") from exc
        prior_path_ids = set(previous_state.get("path_beliefs", {}))
        if not prior_path_ids or not prior_path_ids.issubset(set(paths)):
            raise ResearchIntegrityError("BELIEF_PATH_CONTINUITY_INVALID")
        revision = int(previous_state.get("revision", 0)) + 1
        for row in previous_state.get("active_evidence", []):
            if not isinstance(row, Mapping):
                raise ResearchIntegrityError("BELIEF_PRIOR_ACTIVE_EVIDENCE_INVALID")
            evidence_id = str(row.get("evidence_id") or "")
            if (
                not evidence_id
                or evidence_id in active
                or row.get("path_id") not in paths
                or not row.get("lineage_key")
            ):
                raise ResearchIntegrityError("BELIEF_PRIOR_ACTIVE_EVIDENCE_INVALID")
            active[evidence_id] = dict(row)
        known_evidence_ids = set(
            previous_state.get("known_evidence_ids", tuple(active))
        )
        known_event_ids = set(previous_state.get("known_event_ids", ()))
        if (
            any(not isinstance(item, str) or not item for item in known_evidence_ids)
            or any(not isinstance(item, str) or not item for item in known_event_ids)
            or not set(active).issubset(known_evidence_ids)
            or len(
                {
                    (row["path_id"], row["lineage_key"])
                    for row in active.values()
                }
            )
            != len(active)
        ):
            raise ResearchIntegrityError("BELIEF_PRIOR_ACTIVE_EVIDENCE_INVALID")
        prior_levels = {
            path_id: (
                str(previous_state["path_beliefs"][path_id]["support_level"])
                if path_id in prior_path_ids
                else "UNKNOWN"
            )
            for path_id in paths
        }

    transition_receipts: list[dict[str, Any]] = []
    for raw_event in belief_events:
        if not isinstance(raw_event, Mapping) or set(raw_event) != _BELIEF_EVENT_FIELDS:
            raise ResearchIntegrityError("BELIEF_EVENT_SCHEMA_INVALID")
        event = dict(raw_event)
        event_id = str(event.get("event_id") or "")
        operation = str(event.get("operation") or "")
        path_id = str(event.get("path_id") or "")
        evidence_id = str(event.get("evidence_id") or "")
        lineage_key = str(event.get("lineage_key") or "")
        available_at = _timestamp(
            event.get("available_at"), "BELIEF_EVENT_AVAILABLE_AT_INVALID"
        )
        if (
            not event_id
            or event_id in known_event_ids
            or operation not in BELIEF_EVENT_OPERATIONS
            or path_id not in paths
            or not evidence_id
            or available_at > cutoff
        ):
            raise ResearchIntegrityError("BELIEF_EVENT_INVALID")
        before_snapshot = _path_support_snapshot(active, path_id)
        if operation == "EXPIRE":
            existing = active.get(evidence_id)
            if existing is None or existing["path_id"] != path_id:
                raise ResearchIntegrityError("BELIEF_EXPIRE_TARGET_INVALID")
            if any(
                event.get(field) is not None
                for field in (
                    "direction",
                    "strength",
                    "source_ref",
                    "premise_ref",
                    "supersedes_evidence_id",
                )
            ) or (lineage_key and lineage_key != existing["lineage_key"]):
                raise ResearchIntegrityError("BELIEF_EXPIRE_FIELDS_INVALID")
            del active[evidence_id]
        else:
            direction = str(event.get("direction") or "")
            strength = event.get("strength")
            source_ref = str(event.get("source_ref") or "")
            premise_ref = str(event.get("premise_ref") or "")
            supersedes = event.get("supersedes_evidence_id")
            if (
                not lineage_key
                or direction not in BELIEF_DIRECTIONS
                or not source_ref
                or not premise_ref
                or isinstance(strength, bool)
                or not isinstance(strength, int)
                or not 1 <= strength <= 3
            ):
                raise ResearchIntegrityError("BELIEF_CONTRIBUTION_INVALID")
            expected_direction = {
                "ADD": "SUPPORT",
                "SOFT_CONTRADICTION": "SOFT_CONTRADICTION",
                "HARD_FALSIFIER": "HARD_FALSIFIER",
            }.get(operation)
            if expected_direction is not None and direction != expected_direction:
                raise ResearchIntegrityError("BELIEF_EVENT_DIRECTION_INVALID")
            if operation == "SUPERSEDE":
                if not isinstance(supersedes, str) or supersedes not in active:
                    raise ResearchIntegrityError("BELIEF_SUPERSEDE_TARGET_INVALID")
                prior = active[supersedes]
                if prior["path_id"] != path_id or prior["lineage_key"] != lineage_key:
                    raise ResearchIntegrityError("BELIEF_SUPERSEDE_LINEAGE_INVALID")
                if available_at < _timestamp(
                    prior["available_at"], "BELIEF_SUPERSEDE_TIME_INVALID"
                ):
                    raise ResearchIntegrityError("BELIEF_SUPERSEDE_TIME_INVALID")
                del active[supersedes]
            elif supersedes is not None:
                raise ResearchIntegrityError("BELIEF_SUPERSEDE_TARGET_INVALID")
            if evidence_id in known_evidence_ids:
                raise ResearchIntegrityError("BELIEF_EVIDENCE_REUSE_INVALID")
            if any(
                row["path_id"] == path_id and row["lineage_key"] == lineage_key
                for row in active.values()
            ):
                raise ResearchIntegrityError("BELIEF_LINEAGE_REQUIRES_SUPERSEDE")
            active[evidence_id] = {
                "evidence_id": evidence_id,
                "path_id": path_id,
                "lineage_key": lineage_key,
                "direction": direction,
                "strength": strength,
                "available_at": event["available_at"],
                "source_ref": source_ref,
                "premise_ref": premise_ref,
                "origin_event_id": event_id,
            }
            known_evidence_ids.add(evidence_id)
        after_snapshot = _path_support_snapshot(active, path_id)
        transition_receipts.append(
            self_digest(
                {
                    "schema_id": "path_belief_event_receipt",
                    "schema_version": "1.0.0",
                    "event_id": event_id,
                    "operation": operation,
                    "path_id": path_id,
                    "before": before_snapshot,
                    "after": after_snapshot,
                },
                "transition_digest",
            )
        )
        known_event_ids.add(event_id)

    path_beliefs: dict[str, dict[str, Any]] = {}
    for path_id in paths:
        snapshot = _path_support_snapshot(active, path_id)
        path_beliefs[path_id] = {
            **snapshot,
            "previous_support_level": prior_levels[path_id],
            "transition_reason": (
                "ACTIVE_HARD_FALSIFIER"
                if snapshot["active_hard_falsifier_ids"]
                else "PERSISTED_ACTIVE_EVIDENCE_BALANCE"
                if not belief_events
                else "EXPLICIT_EVIDENCE_LIFECYCLE_EVENTS"
            ),
        }
    state = {
        "schema_id": "persistent_path_belief_state",
        "schema_version": "1.1.0",
        "revision": revision,
        "decision_at": decision_at,
        "previous_belief_state_digest": previous_digest,
        "support_semantics": "ORDINAL_ACTIVE_EVIDENCE_BALANCE_NOT_PROBABILITY",
        "support_mapping": {
            "UNKNOWN": "NO_ACTIVE_EVIDENCE",
            "WEAK": "BALANCE_LESS_THAN_ONE",
            "PLAUSIBLE": "BALANCE_ONE_TO_TWO",
            "SUPPORTED": "BALANCE_THREE_TO_FOUR",
            "DOMINANT": "BALANCE_AT_LEAST_FIVE",
            "INVALIDATED": "ACTIVE_HARD_FALSIFIER",
        },
        "path_beliefs": path_beliefs,
        "active_evidence": sorted(
            active.values(), key=lambda row: (row["path_id"], row["lineage_key"])
        ),
        "known_evidence_ids": sorted(known_evidence_ids),
        "known_event_ids": sorted(known_event_ids),
        "applied_event_ids": [receipt["event_id"] for receipt in transition_receipts],
        "transition_receipts": transition_receipts,
    }
    return self_digest(state, "belief_state_digest")


def _class_applicability(
    action_class: str,
    current_quantity: Decimal,
    target_quantity: Decimal,
    target_quantity_after: Decimal,
    delta: Decimal,
    *, reentry_contract_active: bool,
) -> tuple[str, ...]:
    vetoes: list[str] = []
    has_exposure = current_quantity > 0
    if action_class in {"HOLD", "WAIT"} and delta != 0:
        vetoes.append("ZERO_DELTA_REQUIRED")
    elif action_class == "OPEN" and (has_exposure or delta <= 0):
        vetoes.append("OPEN_REQUIRES_FLAT_AND_POSITIVE_DELTA")
    elif action_class == "ADD" and (
        not has_exposure or target_quantity <= 0 or delta <= 0
    ):
        vetoes.append("ADD_REQUIRES_TARGET_EXPOSURE_AND_POSITIVE_DELTA")
    elif action_class in {"REDUCE", "PARTIAL_TAKE_PROFIT"} and (
        target_quantity <= 0 or delta >= 0 or target_quantity_after <= 0
    ):
        vetoes.append("PARTIAL_REDUCTION_REQUIRES_REMAINING_TARGET_EXPOSURE")
    elif action_class == "EXIT" and (
        target_quantity <= 0
        or delta != -target_quantity
        or target_quantity_after != 0
    ):
        vetoes.append("EXIT_REQUIRES_FULL_TARGET_LOT_REDUCTION")
    elif action_class == "REENTER" and (
        has_exposure or delta <= 0 or not reentry_contract_active
    ):
        vetoes.append("REENTRY_CONTRACT_AND_FLAT_STATE_REQUIRED")
    return tuple(vetoes)


def build_action_evaluation_set(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    symbol: str,
    belief_state_digest: str,
    operational_lead_path_id: str,
    runner_up_path_id: str,
    residual_path_id: str,
    position_truth: Mapping[str, Any],
    risk_policy: Mapping[str, Any],
    valid_evidence_refs: Sequence[str],
    valid_failure_trigger_refs: Sequence[str],
    required_sizing_ids: Sequence[str],
    candidate_proposals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Calculate every candidate before any action-selection input exists."""

    if not run_id or not symbol or cycle_index < 1:
        raise ResearchIntegrityError("ACTION_EVALUATION_IDENTITY_INVALID")
    decision_time = _timestamp(decision_at, "ACTION_EVALUATION_TIME_INVALID")
    _digest(belief_state_digest, "ACTION_BELIEF_DIGEST_INVALID")
    path_ids = (
        operational_lead_path_id,
        runner_up_path_id,
        residual_path_id,
    )
    if any(not item for item in path_ids) or len(set(path_ids)) != 3:
        raise ResearchIntegrityError("ACTION_PATH_SET_INVALID")
    valid_evidence = set(_string_tuple(valid_evidence_refs, "ACTION_EVIDENCE_SET_INVALID"))
    valid_failure_triggers = set(
        _string_tuple(
            valid_failure_trigger_refs,
            "ACTION_FAILURE_TRIGGER_SET_INVALID",
        )
    )
    required_sizes = set(
        _string_tuple(required_sizing_ids, "ACTION_SIZING_SET_INVALID", allow_empty=True)
    )

    try:
        position_document = build_lot_position_truth(
            symbol=symbol, position_truth=position_truth
        )
    except PortfolioTruthError as exc:
        raise ResearchIntegrityError(str(exc)) from exc
    side = str(position_document["intended_side"])
    mark = _decimal(position_document["mark_price"], "ACTION_MARK_INVALID")
    multiplier = _decimal(
        position_document["contract_multiplier"], "ACTION_MULTIPLIER_INVALID"
    )
    target_truth = position_document["target_symbol"]
    account_truth = position_document["account"]
    current_quantity = _decimal(
        target_truth["current_quantity"], "ACTION_QUANTITY_INVALID"
    )
    current_symbol_pending_risk = _decimal(
        target_truth["pending_order_risk_usdt"], "ACTION_RISK_INVALID"
    )
    current_symbol_risk = _decimal(
        target_truth["open_risk_usdt"], "ACTION_RISK_INVALID"
    ) + current_symbol_pending_risk
    current_symbol_pending_notional = _decimal(
        target_truth["pending_open_notional_usdt"], "ACTION_NOTIONAL_INVALID"
    )
    current_symbol_notional = _decimal(
        target_truth["open_notional_usdt"], "ACTION_NOTIONAL_INVALID"
    ) + current_symbol_pending_notional
    current_portfolio_risk = _decimal(
        account_truth["committed_risk_usdt"], "ACTION_RISK_INVALID"
    )
    current_gross = _decimal(
        account_truth["committed_gross_notional_usdt"],
        "ACTION_NOTIONAL_INVALID",
    )
    account_equity = _decimal(
        account_truth["equity_usdt"], "ACTION_ACCOUNT_INVALID"
    )
    current_margin_used = _decimal(
        account_truth["margin_used_usdt"], "ACTION_ACCOUNT_INVALID"
    )
    account_leverage_cap = _decimal(
        account_truth["max_gross_leverage"], "ACTION_ACCOUNT_INVALID"
    )
    reentry_active = position_document["reentry_contract_active"] is True

    if not isinstance(risk_policy, Mapping) or set(risk_policy) != _RISK_POLICY_FIELDS:
        raise ResearchIntegrityError("ACTION_POLICY_INVALID")
    fee_rate = _decimal(risk_policy.get("fee_rate"), "ACTION_POLICY_INVALID")
    slippage_rate = _decimal(
        risk_policy.get("slippage_rate"), "ACTION_POLICY_INVALID"
    )
    initial_margin_rate = _decimal(
        risk_policy.get("initial_margin_rate"), "ACTION_POLICY_INVALID"
    )
    policy_leverage_cap = _decimal(
        risk_policy.get("max_gross_leverage"), "ACTION_POLICY_INVALID"
    )
    portfolio_cap = _decimal(
        risk_policy.get("portfolio_risk_cap_usdt"), "ACTION_POLICY_INVALID"
    )
    symbol_cap = _decimal(
        risk_policy.get("symbol_risk_cap_usdt"), "ACTION_POLICY_INVALID"
    )
    gross_cap = _decimal(
        risk_policy.get("gross_notional_cap_usdt"), "ACTION_POLICY_INVALID"
    )
    symbol_notional_cap = _decimal(
        risk_policy.get("symbol_notional_cap_usdt"), "ACTION_POLICY_INVALID"
    )
    if (
        min(fee_rate, slippage_rate, initial_margin_rate) < 0
        or fee_rate >= 1
        or slippage_rate >= 1
        or initial_margin_rate > 1
        or policy_leverage_cap <= 0
        or policy_leverage_cap > account_leverage_cap
        or min(portfolio_cap, symbol_cap, gross_cap, symbol_notional_cap) <= 0
    ):
        raise ResearchIntegrityError("ACTION_POLICY_INVALID")
    policy_document = self_digest(
        {
            "schema_id": "continuous_action_risk_policy",
            "schema_version": "1.1.0",
            "fee_rate": canonical_decimal(fee_rate),
            "slippage_rate": canonical_decimal(slippage_rate),
            "initial_margin_rate": canonical_decimal(initial_margin_rate),
            "max_gross_leverage": canonical_decimal(policy_leverage_cap),
            "portfolio_risk_cap_usdt": canonical_decimal(portfolio_cap),
            "symbol_risk_cap_usdt": canonical_decimal(symbol_cap),
            "gross_notional_cap_usdt": canonical_decimal(gross_cap),
            "symbol_notional_cap_usdt": canonical_decimal(symbol_notional_cap),
        },
        "risk_policy_digest",
    )

    if not candidate_proposals:
        raise ResearchIntegrityError("ACTION_CANDIDATES_MISSING")
    candidate_ids: set[str] = set()
    action_classes: set[str] = set()
    sizing_ids: set[str] = set()
    all_process_ids: set[str] = set()
    evaluations: list[dict[str, Any]] = []
    for raw in candidate_proposals:
        if not isinstance(raw, Mapping) or set(raw) != _CANDIDATE_FIELDS:
            raise ResearchIntegrityError("SELECTION_FIELD_FORBIDDEN_IN_EVALUATION_PHASE")
        candidate_id = str(raw.get("candidate_id") or "")
        source_cycle_index = raw.get("source_cycle_index")
        action_class = str(raw.get("action_class") or "")
        sizing_id = str(raw.get("sizing_id") or "")
        thesis_path_id = str(raw.get("thesis_path_id") or "")
        rationale = str(raw.get("rationale") or "").strip()
        if (
            not candidate_id
            or candidate_id in candidate_ids
            or isinstance(source_cycle_index, bool)
            or source_cycle_index != cycle_index
            or action_class not in ACTION_CLASSES
            or not sizing_id
            or thesis_path_id not in path_ids
            or not rationale
        ):
            raise ResearchIntegrityError("ACTION_CANDIDATE_INVALID")
        try:
            targets, target_role, target_quantity = candidate_lot_scope(
                position_truth=position_document,
                action_class=action_class,
                target_lot_ids=raw.get("target_lot_ids"),
                target_lot_role=raw.get("target_lot_role"),
            )
        except PortfolioTruthError as exc:
            raise ResearchIntegrityError(str(exc)) from exc
        target_rows = [
            row for row in position_document["lots"] if row["lot_id"] in targets
        ]
        target_open_risk = sum(
            (
                _decimal(row["open_risk_usdt"], "ACTION_TARGET_TRUTH_INVALID")
                for row in target_rows
            ),
            Decimal("0"),
        )
        target_open_notional = sum(
            (
                _decimal(row["notional_usdt"], "ACTION_TARGET_TRUTH_INVALID")
                for row in target_rows
            ),
            Decimal("0"),
        )
        target_margin_used = sum(
            (
                _decimal(row["margin_used_usdt"], "ACTION_TARGET_TRUTH_INVALID")
                for row in target_rows
            ),
            Decimal("0"),
        )
        evidence_refs = _string_tuple(
            raw.get("evidence_refs"), "ACTION_CANDIDATE_EVIDENCE_INVALID"
        )
        if not set(evidence_refs).issubset(valid_evidence):
            raise ResearchIntegrityError("ACTION_CANDIDATE_EVIDENCE_INVALID")
        wait_until = raw.get("wait_until")
        wait_for_observations = _string_tuple(
            raw.get("wait_for_observations"),
            "ACTION_WAIT_OBSERVATIONS_INVALID",
            allow_empty=True,
        )
        if action_class == "WAIT":
            if (
                wait_until is None
                or _timestamp(wait_until, "ACTION_WAIT_REVIEW_TIME_INVALID")
                <= decision_time
                or not wait_for_observations
            ):
                raise ResearchIntegrityError("ACTION_WAIT_OBLIGATION_INCOMPLETE")
        elif wait_until is not None or wait_for_observations:
            raise ResearchIntegrityError("ACTION_WAIT_FIELDS_FOR_NON_WAIT")
        outcomes = raw.get("path_outcomes")
        if not isinstance(outcomes, list) or len(outcomes) != 3:
            raise ResearchIntegrityError("ACTION_PATH_OUTCOMES_INVALID")
        normalized_outcomes: list[dict[str, Any]] = []
        outcome_path_ids: set[str] = set()
        process_ids: set[str] = set()
        for outcome in outcomes:
            if not isinstance(outcome, Mapping) or set(outcome) != _OUTCOME_FIELDS:
                raise ResearchIntegrityError("ACTION_PATH_OUTCOME_SCHEMA_INVALID")
            path_id = str(outcome.get("path_id") or "")
            outcome_cycle_index = outcome.get("source_cycle_index")
            position_truth_digest = str(
                outcome.get("position_truth_digest") or ""
            )
            process_id = str(outcome.get("process_id") or "")
            distinguishing = _string_tuple(
                outcome.get("distinguishing_evidence_refs"),
                "ACTION_PATH_DISTINCTION_INVALID",
            )
            triggers = _string_tuple(
                outcome.get("failure_trigger_refs"),
                "ACTION_PATH_FAILURE_TRIGGER_INVALID",
            )
            if (
                path_id not in path_ids
                or path_id in outcome_path_ids
                or isinstance(outcome_cycle_index, bool)
                or outcome_cycle_index != cycle_index
                or position_truth_digest
                != position_document["position_truth_digest"]
                or not process_id
                or process_id in process_ids
                or process_id in all_process_ids
                or not set(distinguishing).issubset(valid_evidence)
                or not set(triggers).issubset(valid_failure_triggers)
                or any(
                    not str(outcome.get(field) or "").strip()
                    for field in (
                        "position_consequence",
                        "compatibility",
                        "market_process",
                        "failure_process",
                        "opportunity_cost",
                        "cost_risk_tradeoff",
                    )
                )
            ):
                raise ResearchIntegrityError("ACTION_PATH_OUTCOME_INVALID")
            normalized_outcomes.append(
                {
                    "path_id": path_id,
                    "source_cycle_index": cycle_index,
                    "position_truth_digest": position_truth_digest,
                    "process_id": process_id,
                    "distinguishing_evidence_refs": list(distinguishing),
                    "failure_trigger_refs": list(triggers),
                    "position_consequence": str(outcome["position_consequence"]),
                    "compatibility": str(outcome["compatibility"]),
                    "market_process": str(outcome["market_process"]),
                    "failure_process": str(outcome["failure_process"]),
                    "opportunity_cost": str(outcome["opportunity_cost"]),
                    "cost_risk_tradeoff": str(outcome["cost_risk_tradeoff"]),
                }
            )
            outcome_path_ids.add(path_id)
            process_ids.add(process_id)
            all_process_ids.add(process_id)
        if outcome_path_ids != set(path_ids):
            raise ResearchIntegrityError("ACTION_PATH_OUTCOMES_INVALID")

        delta = _decimal(raw.get("quantity_delta"), "ACTION_DELTA_INVALID")
        size_contract = _REDUCTION_SIZE_CONTRACTS.get(sizing_id)
        if size_contract is not None:
            expected_class, fraction = size_contract
            if action_class != expected_class or delta != -(target_quantity * fraction):
                raise ResearchIntegrityError("ACTION_SIZING_QUANTITY_MISMATCH")
        quantity_after = current_quantity + delta
        target_quantity_after = target_quantity + delta
        vetoes = list(
            _class_applicability(
                action_class,
                current_quantity,
                target_quantity,
                target_quantity_after,
                delta,
                reentry_contract_active=reentry_active,
            )
        )
        if quantity_after < 0:
            vetoes.append("NEGATIVE_POST_ACTION_QUANTITY")
            quantity_after = Decimal("0")
        if target_quantity_after < 0:
            vetoes.append("NEGATIVE_POST_ACTION_TARGET_QUANTITY")
            target_quantity_after = Decimal("0")
        direction_factor = Decimal("1") if side == "LONG" else Decimal("-1")
        trade_factor = direction_factor if delta > 0 else -direction_factor
        fill_price = (
            mark
            if delta == 0
            else mark * (Decimal("1") + trade_factor * slippage_rate)
        )
        turnover = abs(delta) * fill_price * multiplier
        fee = turnover * fee_rate
        slippage_cost = abs(fill_price - mark) * abs(delta) * multiplier
        action_cost = fee + slippage_cost
        stop_raw = raw.get("stop_price_after")
        stop = None if stop_raw is None else _decimal(stop_raw, "ACTION_STOP_INVALID")
        if action_class in {"HOLD", "WAIT"}:
            if stop is not None:
                vetoes.append("UNCHANGED_ACTION_STOP_OVERRIDE_FORBIDDEN")
            target_risk_after = target_open_risk
            target_notional_after = target_open_notional
            target_margin_after = target_margin_used
        elif action_class == "EXIT":
            if stop is not None:
                vetoes.append("EXIT_STOP_MUST_BE_NULL")
            target_risk_after = Decimal("0")
            target_notional_after = Decimal("0")
            target_margin_after = Decimal("0")
        else:
            target_risk_after = Decimal("0")
            if stop is None:
                vetoes.append("PROTECTIVE_STOP_REQUIRED")
            elif (side == "LONG" and stop >= mark) or (
                side == "SHORT" and stop <= mark
            ):
                vetoes.append("PROTECTIVE_STOP_WRONG_SIDE")
            else:
                target_risk_after = (
                    target_quantity_after * abs(mark - stop) * multiplier
                )
            target_notional_after = target_quantity_after * mark * multiplier
            if action_class == "ADD":
                target_margin_after = target_margin_used + (
                    max(Decimal("0"), delta)
                    * mark
                    * multiplier
                    * initial_margin_rate
                )
            elif action_class in {"REDUCE", "PARTIAL_TAKE_PROFIT"}:
                target_margin_after = (
                    Decimal("0")
                    if target_quantity == 0
                    else target_margin_used
                    * target_quantity_after
                    / target_quantity
                )
            else:
                target_margin_after = (
                    target_notional_after * initial_margin_rate
                )
        symbol_risk_after = (
            current_symbol_risk - target_open_risk + target_risk_after
        )
        symbol_notional_after = (
            current_symbol_notional
            - target_open_notional
            + target_notional_after
        )
        portfolio_risk_after = (
            current_portfolio_risk - current_symbol_risk + symbol_risk_after
        )
        gross_after = current_gross - current_symbol_notional + symbol_notional_after
        margin_used_after = (
            current_margin_used - target_margin_used + target_margin_after
        )
        margin_available_after = account_equity - margin_used_after
        gross_leverage_after = gross_after / account_equity
        if symbol_risk_after > symbol_cap:
            vetoes.append("SYMBOL_RISK_CAP")
        if portfolio_risk_after > portfolio_cap:
            vetoes.append("PORTFOLIO_RISK_CAP")
        if symbol_notional_after > symbol_notional_cap:
            vetoes.append("SYMBOL_NOTIONAL_CAP")
        if gross_after > gross_cap:
            vetoes.append("GROSS_NOTIONAL_CAP")
        if margin_used_after < 0 or margin_available_after < 0:
            vetoes.append("MARGIN_CAPACITY_EXCEEDED")
        if gross_leverage_after > policy_leverage_cap:
            vetoes.append("GROSS_LEVERAGE_CAP")
        evaluation = {
            "candidate_id": candidate_id,
            "source_cycle_index": cycle_index,
            "position_truth_digest": position_document["position_truth_digest"],
            "action_class": action_class,
            "sizing_id": sizing_id,
            "thesis_path_id": thesis_path_id,
            "target_lot_ids": list(targets),
            "target_lot_role": target_role,
            "rationale": rationale,
            "evidence_refs": list(evidence_refs),
            "wait_until": wait_until,
            "wait_for_observations": list(wait_for_observations),
            "path_outcomes": sorted(
                normalized_outcomes, key=lambda row: path_ids.index(row["path_id"])
            ),
            "economics": {
                "quantity_before": canonical_decimal(current_quantity),
                "target_quantity_before": canonical_decimal(target_quantity),
                "quantity_delta": canonical_decimal(delta),
                "quantity_after": canonical_decimal(quantity_after),
                "target_quantity_after": canonical_decimal(target_quantity_after),
                "estimated_fill_price": canonical_decimal(fill_price),
                "turnover_notional_usdt": canonical_decimal(turnover),
                "estimated_fee_usdt": canonical_decimal(fee),
                "estimated_slippage_usdt": canonical_decimal(slippage_cost),
                "estimated_action_cost_usdt": canonical_decimal(action_cost),
                "symbol_notional_after_usdt": canonical_decimal(symbol_notional_after),
                "symbol_open_risk_after_usdt": canonical_decimal(symbol_risk_after),
                "symbol_committed_risk_after_usdt": canonical_decimal(
                    symbol_risk_after
                ),
                "portfolio_open_risk_after_usdt": canonical_decimal(
                    portfolio_risk_after
                ),
                "portfolio_committed_risk_after_usdt": canonical_decimal(
                    portfolio_risk_after
                ),
                "remaining_symbol_risk_budget_usdt": canonical_decimal(
                    symbol_cap - symbol_risk_after
                ),
                "remaining_portfolio_risk_budget_usdt": canonical_decimal(
                    portfolio_cap - portfolio_risk_after
                ),
                "gross_notional_after_usdt": canonical_decimal(gross_after),
                "margin_used_after_usdt": canonical_decimal(margin_used_after),
                "margin_available_after_usdt": canonical_decimal(
                    margin_available_after
                ),
                "gross_leverage_after": canonical_decimal(gross_leverage_after),
                "worst_case_symbol_loss_after_cost_usdt": canonical_decimal(
                    symbol_risk_after + action_cost
                ),
                "protective_stop_after": (
                    None if stop is None else canonical_decimal(stop)
                ),
            },
            "feasible": not vetoes,
            "hard_vetoes": sorted(set(vetoes)),
        }
        evaluations.append(self_digest(evaluation, "candidate_evaluation_digest"))
        candidate_ids.add(candidate_id)
        action_classes.add(action_class)
        sizing_ids.add(sizing_id)
    if action_classes != ACTION_CLASSES:
        raise ResearchIntegrityError("ACTION_CLASS_COVERAGE_INCOMPLETE")
    if not required_sizes.issubset(sizing_ids):
        raise ResearchIntegrityError("ACTION_SIZING_COMPARISON_INCOMPLETE")
    result = {
        "schema_id": "sealed_action_evaluation_set",
        "schema_version": "1.2.0",
        "run_id": run_id,
        "cycle_index": cycle_index,
        "decision_at": decision_at,
        "symbol": symbol,
        "belief_state_digest": belief_state_digest,
        "position_truth": position_document,
        "risk_policy": policy_document,
        "operational_lead_path_id": operational_lead_path_id,
        "runner_up_path_id": runner_up_path_id,
        "residual_path_id": residual_path_id,
        "required_sizing_ids": sorted(required_sizes),
        "valid_failure_trigger_refs": sorted(valid_failure_triggers),
        "selection_fields_admitted": False,
        "probability_status": "ORDINAL_ONLY_NO_NUMERIC_EV",
        "candidates": sorted(evaluations, key=lambda row: row["candidate_id"]),
    }
    return self_digest(result, "action_evaluation_digest")


def select_from_evaluation_set(
    *,
    evaluation_set: Mapping[str, Any],
    selected_candidate_id: str,
    ranked_alternative_ids: Sequence[str],
    why_not_selected: Mapping[str, str],
    selection_rationale: str,
    agent_proposal_digest: str,
) -> dict[str, Any]:
    """Select only after the complete evaluation set has been sealed."""

    try:
        evaluation_digest = verify_self_digest(
            evaluation_set, "action_evaluation_digest"
        )
    except ValueError as exc:
        raise ResearchIntegrityError("ACTION_EVALUATION_DIGEST_INVALID") from exc
    _digest(agent_proposal_digest, "AGENT_PROPOSAL_DIGEST_INVALID")
    candidates = {
        str(row["candidate_id"]): row
        for row in evaluation_set.get("candidates", [])
        if isinstance(row, Mapping) and row.get("candidate_id")
    }
    selected = candidates.get(selected_candidate_id)
    if selected is None or selected.get("feasible") is not True:
        raise ResearchIntegrityError("SELECTED_CANDIDATE_NOT_FEASIBLE")
    alternatives = tuple(ranked_alternative_ids)
    feasible_alternatives = {
        candidate_id
        for candidate_id, row in candidates.items()
        if row.get("feasible") is True and candidate_id != selected_candidate_id
    }
    if (
        len(alternatives) != len(set(alternatives))
        or set(alternatives) != feasible_alternatives
        or set(why_not_selected) != feasible_alternatives
        or any(not str(value).strip() for value in why_not_selected.values())
        or not selection_rationale.strip()
    ):
        raise ResearchIntegrityError("ACTION_SELECTION_ALTERNATIVES_INCOMPLETE")
    selection = {
        "schema_id": "sealed_action_selection",
        "schema_version": "1.0.0",
        "run_id": evaluation_set["run_id"],
        "cycle_index": evaluation_set["cycle_index"],
        "symbol": evaluation_set["symbol"],
        "agent_proposal_digest": agent_proposal_digest,
        "action_evaluation_digest": evaluation_digest,
        "selected_candidate_id": selected_candidate_id,
        "selected_candidate_evaluation_digest": selected[
            "candidate_evaluation_digest"
        ],
        "ranked_alternative_ids": list(alternatives),
        "why_not_selected": dict(sorted(why_not_selected.items())),
        "selection_rationale": selection_rationale.strip(),
        "selection_boundary": "AGENT_CHOICE_WITHIN_DETERMINISTIC_FEASIBLE_SET",
    }
    return self_digest(selection, "action_selection_digest")


def make_agent_invocation_receipt(
    *,
    run_id: str,
    cycle_index: int,
    attempt_id: str,
    input_context_digest: str,
    proposal_digest: str,
    started_at: str,
    ended_at: str,
    automation_id: str | None,
    thread_id: str | None,
    authoring_mode: str = "CODEX_SINGLE_STRATEGY_AGENT",
    platform_model_receipt: str | None = None,
    input_plan_digest: str | None = None,
    delivery_receipt_digest: str | None = None,
) -> dict[str, Any]:
    """Record practical Agent provenance without claiming unavailable attestation."""

    start = _timestamp(started_at, "AGENT_INVOCATION_TIME_INVALID")
    end = _timestamp(ended_at, "AGENT_INVOCATION_TIME_INVALID")
    if end < start or not run_id or cycle_index < 1 or not attempt_id:
        raise ResearchIntegrityError("AGENT_INVOCATION_INVALID")
    _digest(input_context_digest, "AGENT_INPUT_DIGEST_INVALID")
    _digest(proposal_digest, "AGENT_PROPOSAL_DIGEST_INVALID")
    if platform_model_receipt is not None:
        _digest(platform_model_receipt, "PLATFORM_MODEL_RECEIPT_DIGEST_INVALID")
    if input_plan_digest is not None:
        _digest(input_plan_digest, "AGENT_INPUT_PLAN_DIGEST_INVALID")
    if delivery_receipt_digest is not None:
        _digest(delivery_receipt_digest, "AGENT_DELIVERY_RECEIPT_DIGEST_INVALID")
    return self_digest(
        {
            "schema_id": "single_strategy_agent_invocation_receipt",
            "schema_version": "1.2.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "attempt_id": attempt_id,
            "authoring_mode": authoring_mode,
            "automation_id": automation_id,
            "thread_id": thread_id,
            "input_context_digest": input_context_digest,
            "input_plan_digest": input_plan_digest,
            "proposal_digest": proposal_digest,
            "delivery_receipt_digest": delivery_receipt_digest,
            "started_at": started_at,
            "ended_at": ended_at,
            "platform_model_receipt": platform_model_receipt,
            "model_identity_evidence": (
                "PLATFORM_RECEIPT_DIGEST_BOUND_IDENTITY_SCOPE_UNVERIFIED"
                if platform_model_receipt
                else "PRACTICAL_CODEX_PROVENANCE_NOT_MODEL_ATTESTED"
            ),
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "invocation_receipt_digest",
    )


_REVIEW_FIELDS = frozenset(
    {
        "cycle_index",
        "lead_path_id",
        "lead_prefix_status",
        "selected_candidate_id",
        "applied_candidate_id",
        "agent_net_pnl_usdt",
        "baseline_net_pnl_usdt",
        "available_favorable_move_usdt",
        "captured_favorable_move_usdt",
        "available_add_risk_usdt",
        "deployed_add_risk_usdt",
        "reentry_status",
        "eligible_reentry_at",
        "reentered_at",
        "fees_usdt",
        "funding_status",
        "funding_usdt",
        "equity_usdt",
        "peak_equity_usdt",
    }
)


def build_four_cycle_review(
    *, run_id: str, through_cycle: int, cycle_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Compute, rather than narratively assert, one four-cycle review."""

    expected = list(range(through_cycle - 3, through_cycle + 1))
    if through_cycle < 4 or through_cycle % 4 or len(cycle_rows) != 4:
        raise ResearchIntegrityError("FOUR_CYCLE_REVIEW_WINDOW_INVALID")
    normalized: list[dict[str, Any]] = []
    for expected_index, row in zip(expected, cycle_rows, strict=True):
        if not isinstance(row, Mapping) or set(row) != _REVIEW_FIELDS:
            raise ResearchIntegrityError("FOUR_CYCLE_REVIEW_FIELDS_INCOMPLETE")
        if row.get("cycle_index") != expected_index:
            raise ResearchIntegrityError("FOUR_CYCLE_REVIEW_ORDER_INVALID")
        if row.get("lead_prefix_status") not in {
            "SUPPORTED",
            "FAILED",
            "UNRESOLVED",
        }:
            raise ResearchIntegrityError("FOUR_CYCLE_PATH_STATUS_INVALID")
        if (
            not str(row.get("lead_path_id") or "")
            or not str(row.get("selected_candidate_id") or "")
            or not str(row.get("applied_candidate_id") or "")
        ):
            raise ResearchIntegrityError("FOUR_CYCLE_IDENTITY_INVALID")
        agent_pnl = _decimal(row["agent_net_pnl_usdt"], "FOUR_CYCLE_METRIC_INVALID")
        baseline_pnl = _decimal(
            row["baseline_net_pnl_usdt"], "FOUR_CYCLE_METRIC_INVALID"
        )
        available_move = _decimal(
            row["available_favorable_move_usdt"], "FOUR_CYCLE_METRIC_INVALID"
        )
        captured_move = _decimal(
            row["captured_favorable_move_usdt"], "FOUR_CYCLE_METRIC_INVALID"
        )
        available_add = _decimal(
            row["available_add_risk_usdt"], "FOUR_CYCLE_METRIC_INVALID"
        )
        deployed_add = _decimal(
            row["deployed_add_risk_usdt"], "FOUR_CYCLE_METRIC_INVALID"
        )
        fees = _decimal(row["fees_usdt"], "FOUR_CYCLE_METRIC_INVALID")
        equity = _decimal(row["equity_usdt"], "FOUR_CYCLE_METRIC_INVALID")
        peak = _decimal(row["peak_equity_usdt"], "FOUR_CYCLE_METRIC_INVALID")
        funding_status = str(row.get("funding_status") or "")
        funding_raw = row.get("funding_usdt")
        if funding_status not in {"OBSERVED", "MODELED", "UNKNOWN"}:
            raise ResearchIntegrityError("FOUR_CYCLE_FUNDING_STATUS_INVALID")
        if funding_status == "UNKNOWN":
            if funding_raw is not None:
                raise ResearchIntegrityError("FOUR_CYCLE_UNKNOWN_NOT_NULL")
            funding = None
        else:
            funding = _decimal(funding_raw, "FOUR_CYCLE_METRIC_INVALID")
        if min(available_move, captured_move, available_add, deployed_add, fees, equity, peak) < 0:
            raise ResearchIntegrityError("FOUR_CYCLE_METRIC_INVALID")
        if captured_move > available_move or deployed_add > available_add:
            raise ResearchIntegrityError("FOUR_CYCLE_METRIC_INVALID")
        capture = (
            None
            if available_move == 0
            else captured_move / available_move
        )
        add_utilization = (
            None
            if available_add == 0
            else deployed_add / available_add
        )
        drawdown = Decimal("0") if peak == 0 else max(Decimal("0"), (peak - equity) / peak)
        reentry_status = str(row.get("reentry_status") or "")
        if reentry_status not in {
            "NOT_APPLICABLE",
            "NOT_ELIGIBLE",
            "PENDING",
            "COMPLETED",
        }:
            raise ResearchIntegrityError("FOUR_CYCLE_REENTRY_STATUS_INVALID")
        eligible_at = row.get("eligible_reentry_at")
        reentered_at = row.get("reentered_at")
        delay_hours: Decimal | None = None
        if reentry_status == "COMPLETED":
            eligible = _timestamp(eligible_at, "FOUR_CYCLE_REENTRY_TIME_INVALID")
            reentered = _timestamp(reentered_at, "FOUR_CYCLE_REENTRY_TIME_INVALID")
            if reentered < eligible:
                raise ResearchIntegrityError("FOUR_CYCLE_REENTRY_TIME_INVALID")
            delay_hours = Decimal(str((reentered - eligible).total_seconds())) / Decimal("3600")
        elif reentry_status == "PENDING":
            _timestamp(eligible_at, "FOUR_CYCLE_REENTRY_TIME_INVALID")
            if reentered_at is not None:
                raise ResearchIntegrityError("FOUR_CYCLE_REENTRY_TIME_INVALID")
        elif eligible_at is not None or reentered_at is not None:
            raise ResearchIntegrityError("FOUR_CYCLE_REENTRY_TIME_INVALID")
        normalized.append(
            {
                "cycle_index": expected_index,
                "lead_path_id": str(row["lead_path_id"]),
                "lead_prefix_status": str(row["lead_prefix_status"]),
                "selected_candidate_id": str(row["selected_candidate_id"]),
                "applied_candidate_id": str(row["applied_candidate_id"]),
                "action_fidelity": row["selected_candidate_id"]
                == row["applied_candidate_id"],
                "opportunity_difference_usdt": canonical_decimal(
                    agent_pnl - baseline_pnl
                ),
                "path_capture_ratio": (
                    None if capture is None else canonical_decimal(capture)
                ),
                "add_utilization_ratio": (
                    None
                    if add_utilization is None
                    else canonical_decimal(add_utilization)
                ),
                "reentry_status": reentry_status,
                "reentry_delay_hours": (
                    None
                    if delay_hours is None
                    else canonical_decimal(delay_hours)
                ),
                "fees_usdt": canonical_decimal(fees),
                "funding_status": funding_status,
                "funding_usdt": (
                    None if funding is None else canonical_decimal(funding)
                ),
                "drawdown_fraction": canonical_decimal(drawdown),
            }
        )
    known_capture = [
        _decimal(row["path_capture_ratio"], "FOUR_CYCLE_METRIC_INVALID")
        for row in normalized
        if row["path_capture_ratio"] is not None
    ]
    review = {
        "schema_id": "structured_four_cycle_review",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "through_cycle": through_cycle,
        "cycle_indices": expected,
        "cycles": normalized,
        "summary": {
            "supported_lead_prefixes": sum(
                row["lead_prefix_status"] == "SUPPORTED" for row in normalized
            ),
            "failed_lead_prefixes": sum(
                row["lead_prefix_status"] == "FAILED" for row in normalized
            ),
            "unresolved_lead_prefixes": sum(
                row["lead_prefix_status"] == "UNRESOLVED" for row in normalized
            ),
            "action_fidelity_count": sum(row["action_fidelity"] for row in normalized),
            "ending_opportunity_difference_usdt": normalized[-1][
                "opportunity_difference_usdt"
            ],
            "mean_known_path_capture_ratio": (
                None
                if not known_capture
                else canonical_decimal(sum(known_capture, Decimal("0")) / len(known_capture))
            ),
            "maximum_drawdown_fraction": canonical_decimal(
                max(
                    _decimal(row["drawdown_fraction"], "FOUR_CYCLE_METRIC_INVALID")
                    for row in normalized
                )
            ),
            "pending_reentry_count": sum(
                row["reentry_status"] == "PENDING" for row in normalized
            ),
            "ending_fees_usdt": normalized[-1]["fees_usdt"],
            "ending_funding_status": normalized[-1]["funding_status"],
            "ending_funding_usdt": normalized[-1]["funding_usdt"],
        },
        "interpretation_boundary": "FOUR_CYCLE_PROCESS_EVIDENCE_NOT_PROFITABILITY_OR_PREDICTIVE_PROOF",
    }
    return self_digest(review, "review_digest")
