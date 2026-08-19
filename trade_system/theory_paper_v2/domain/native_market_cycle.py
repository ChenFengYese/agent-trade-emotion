"""Pure contracts and financial evaluation for the native Codex BTC pilot."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_decimal, self_digest
from .dynamic_research import SENTIMENT_AXES


SENTIMENT_DIMENSIONS = SENTIMENT_AXES
SENTIMENT_REQUIRED_DEPENDENCY_GROUPS = {
    "PRICE_DIRECTIONAL_PRESSURE": (
        "CANDLE_15M",
        "CANDLE_1H",
        "CANDLE_4H",
        "CANDLE_1D",
        "BOOK_SNAPSHOT",
        "TRADES_SNAPSHOT",
    ),
    "STRUCTURE_PERSISTENCE": (
        "CANDLE_15M",
        "CANDLE_1H",
        "CANDLE_4H",
        "CANDLE_1D",
    ),
    "PARTICIPATION_AND_FLOW": (
        "CANDLE_15M",
        "CANDLE_1H",
        "CANDLE_4H",
        "CANDLE_1D",
        "TRADES_SNAPSHOT",
    ),
    "CROWDING_DIRECTION": ("FUNDING_RATE", "POSITIONING_SOURCE"),
    "LEVERAGE_CHANGE": ("OPEN_INTEREST_CHANGE", "LIQUIDATION_SOURCE"),
    "LIQUIDITY_RESILIENCE": (
        "BOOK_SNAPSHOT",
        "BOOK_RESILIENCE_HISTORY",
        "SPREAD_HISTORY",
    ),
    "VOLATILITY_STRESS": (
        "CANDLE_15M",
        "CANDLE_1H",
        "CANDLE_4H",
        "CANDLE_1D",
        "VOLATILITY_BASELINE",
        "LIQUIDATION_SOURCE",
    ),
    "CROSS_MARKET_RISK_APPETITE": ("CROSS_MARKET_SOURCE",),
    "EVENT_REACTION": ("NEWS_SOURCE",),
    "TIMEFRAME_COHERENCE": (
        "CANDLE_15M",
        "CANDLE_1H",
        "CANDLE_4H",
        "CANDLE_1D",
    ),
}
MARKET_ACTIONS = frozenset({"WAIT", "OPEN_LONG", "OPEN_SHORT"})
_PROHIBITED_KEYS = frozenset(
    {
        "probability_pct",
        "probability",
        "expected_value",
        "ev",
        "entropy",
        "confidence_pct",
        "total_sentiment_score",
    }
)


class NativeMarketCycleError(ValueError):
    """A fail-closed market-pilot epistemic or financial violation."""


def _text(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NativeMarketCycleError(reason)
    return value


def _decimal(value: object, reason: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise NativeMarketCycleError(reason)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise NativeMarketCycleError(reason) from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise NativeMarketCycleError(reason)
    if canonical_decimal(parsed) != value:
        raise NativeMarketCycleError(reason)
    return parsed


def _string_list(value: object, reason: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise NativeMarketCycleError(reason)
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise NativeMarketCycleError(reason)
    return list(value)


def _reject_prohibited_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in _PROHIBITED_KEYS:
                raise NativeMarketCycleError(
                    "NATIVE_MARKET_UNCALIBRATED_NUMBER_FORBIDDEN"
                )
            _reject_prohibited_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_prohibited_keys(item)


def _is_candle_metric(fact_id: str, suffix: str) -> bool:
    return fact_id.startswith("candle-") and fact_id.endswith(suffix)


def _validate_sentiment_contributor_semantics(
    *, axis: str, fact_id: str, ordinal_value: int
) -> None:
    allowed = {
        "PRICE_DIRECTIONAL_PRESSURE": (
            _is_candle_metric(fact_id, "-return-pct")
            or fact_id in {"book-top5-imbalance", "recent-trade-side-imbalance"}
        ),
        "STRUCTURE_PERSISTENCE": _is_candle_metric(
            fact_id, "-return-pct"
        ),
        "PARTICIPATION_AND_FLOW": (
            _is_candle_metric(fact_id, "-volume-vs-20bar-median")
            or fact_id == "recent-trade-side-imbalance"
        ),
        "CROWDING_DIRECTION": fact_id
        in {"funding-rate", "crowding-positioning"},
        "LEVERAGE_CHANGE": fact_id
        in {"open-interest-change-pct", "liquidation-stress"},
        "LIQUIDITY_RESILIENCE": fact_id
        in {"book-top5-imbalance", "book-resilience-history", "spread-history"},
        "VOLATILITY_STRESS": (
            _is_candle_metric(fact_id, "-range-pct")
            or fact_id in {"volatility-baseline", "liquidation-stress"}
        ),
        "CROSS_MARKET_RISK_APPETITE": fact_id
        == "cross-market-risk-appetite",
        "EVENT_REACTION": fact_id == "news-cross-market",
        "TIMEFRAME_COHERENCE": _is_candle_metric(
            fact_id, "-return-pct"
        ),
    }.get(axis, False)
    if not allowed:
        raise NativeMarketCycleError(
            "NATIVE_MARKET_SENTIMENT_FACT_AXIS_MISMATCH"
        )
    if (
        axis == "PARTICIPATION_AND_FLOW"
        and _is_candle_metric(fact_id, "-volume-vs-20bar-median")
        and ordinal_value != 0
    ):
        raise NativeMarketCycleError(
            "NATIVE_MARKET_PARTICIPATION_VOLUME_DIRECTION_FORBIDDEN"
        )
    if (
        axis == "VOLATILITY_STRESS"
        and _is_candle_metric(fact_id, "-range-pct")
        and ordinal_value != 0
    ):
        raise NativeMarketCycleError(
            "NATIVE_MARKET_UNBASELINED_RANGE_DIRECTION_FORBIDDEN"
        )
    single_snapshot_facts = {
        "book-top5-imbalance",
        "recent-trade-side-imbalance",
        "funding-rate",
        "open-interest-change-pct",
    }
    if fact_id in single_snapshot_facts and abs(ordinal_value) > 1:
        raise NativeMarketCycleError(
            "NATIVE_MARKET_SINGLE_SNAPSHOT_STRONG_CONTRIBUTION_FORBIDDEN"
        )


def _common_payload_binding(
    *, request: Mapping[str, Any], payload: Mapping[str, Any], schema_id: str
) -> None:
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_id") != schema_id
        or payload.get("schema_version") != "1.0.0"
        or payload.get("run_id") != request.get("run_id")
        or payload.get("cycle_index") != request.get("cycle_index")
        or payload.get("input_digest")
        != request.get("input_binding", {}).get("semantic_digest")
        or payload.get("private_chain_of_thought_recorded") is not False
    ):
        raise NativeMarketCycleError("NATIVE_MARKET_PAYLOAD_BINDING_MISMATCH")
    _reject_prohibited_keys(payload)


def validate_native_market_proposal_payload(
    *, request: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    _common_payload_binding(
        request=request,
        payload=payload,
        schema_id="native_codex_market_proposal_payload",
    )
    market_snapshot_digest = _text(
        payload.get("market_snapshot_digest"),
        "NATIVE_MARKET_SNAPSHOT_DIGEST_INVALID",
    )
    if market_snapshot_digest != request.get("market_snapshot_digest"):
        raise NativeMarketCycleError("NATIVE_MARKET_SNAPSHOT_BINDING_MISMATCH")

    dimensions = payload.get("sentiment_dimension_inputs")
    if not isinstance(dimensions, list) or len(dimensions) != len(
        SENTIMENT_DIMENSIONS
    ):
        raise NativeMarketCycleError("NATIVE_MARKET_SENTIMENT_DIMENSIONS_INVALID")
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in dimensions:
        if not isinstance(row, Mapping):
            raise NativeMarketCycleError(
                "NATIVE_MARKET_SENTIMENT_DIMENSIONS_INVALID"
            )
        dimension_id = _text(
            row.get("axis"),
            "NATIVE_MARKET_SENTIMENT_DIMENSION_ID_INVALID",
        )
        if dimension_id in by_id:
            raise NativeMarketCycleError(
                "NATIVE_MARKET_SENTIMENT_DIMENSION_DUPLICATE"
            )
        required_groups = _string_list(
            row.get("required_dependency_groups"),
            "NATIVE_MARKET_SENTIMENT_REQUIRED_GROUPS_INVALID",
        )
        if required_groups != list(
            SENTIMENT_REQUIRED_DEPENDENCY_GROUPS.get(dimension_id, ())
        ):
            raise NativeMarketCycleError(
                "NATIVE_MARKET_SENTIMENT_REQUIRED_GROUPS_DRIFTED"
            )
        contributors = row.get("contributors")
        if not isinstance(contributors, list):
            raise NativeMarketCycleError("NATIVE_MARKET_SENTIMENT_CONTRIBUTORS_INVALID")
        for contributor in contributors:
            if not isinstance(contributor, Mapping):
                raise NativeMarketCycleError("NATIVE_MARKET_SENTIMENT_CONTRIBUTOR_INVALID")
            _text(contributor.get("fact_id"), "NATIVE_MARKET_SENTIMENT_EVIDENCE_INVALID")
            value = contributor.get("ordinal_contribution")
            if isinstance(value, bool) or not isinstance(value, int) or value not in {-2, -1, 0, 1, 2}:
                raise NativeMarketCycleError("NATIVE_MARKET_SENTIMENT_ORDINAL_INVALID")
            expected_direction = "NEGATIVE" if value < 0 else "POSITIVE" if value > 0 else "NEUTRAL"
            if contributor.get("direction") != expected_direction:
                raise NativeMarketCycleError("NATIVE_MARKET_SENTIMENT_DIRECTION_INVALID")
            _text(contributor.get("rule"), "NATIVE_MARKET_SENTIMENT_RULE_INVALID")
            _validate_sentiment_contributor_semantics(
                axis=dimension_id,
                fact_id=str(contributor["fact_id"]),
                ordinal_value=value,
            )
        timeframe_states = row.get("timeframe_states")
        if not isinstance(timeframe_states, Mapping) or any(
            not isinstance(key, str)
            or not key
            or (
                value is not None
                and (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value not in {-2, -1, 0, 1, 2}
                )
            )
            for key, value in timeframe_states.items()
        ):
            raise NativeMarketCycleError("NATIVE_MARKET_SENTIMENT_TIMEFRAME_INVALID")
        for field in (
            "agent_interpretation",
            "limitations",
            "next_discriminating_observation",
        ):
            _text(row.get(field), "NATIVE_MARKET_SENTIMENT_TEXT_INVALID")
        by_id[dimension_id] = row
    if set(by_id) != set(SENTIMENT_DIMENSIONS):
        raise NativeMarketCycleError("NATIVE_MARKET_SENTIMENT_DIMENSIONS_INVALID")
    _text(
        payload.get("operational_synthesis"),
        "NATIVE_MARKET_SENTIMENT_SYNTHESIS_INVALID",
    )

    inferences = payload.get("public_inference_claims")
    if not isinstance(inferences, list) or not inferences:
        raise NativeMarketCycleError("NATIVE_MARKET_INFERENCE_REQUIRED")
    inference_ids: set[str] = set()
    for row in inferences:
        if not isinstance(row, Mapping):
            raise NativeMarketCycleError("NATIVE_MARKET_INFERENCE_INVALID")
        claim_id = _text(row.get("claim_id"), "NATIVE_MARKET_CLAIM_ID_INVALID")
        if claim_id in inference_ids:
            raise NativeMarketCycleError("NATIVE_MARKET_CLAIM_ID_DUPLICATE")
        inference_ids.add(claim_id)
        for field in (
            "statement",
            "financial_mechanism",
            "hypothesis_impact",
            "action_implication",
            "falsifier",
            "limitations",
            "next_observation",
        ):
            _text(row.get(field), f"NATIVE_MARKET_INFERENCE_{field.upper()}_INVALID")
        _string_list(
            row.get("supporting_evidence_refs"),
            "NATIVE_MARKET_INFERENCE_SUPPORT_INVALID",
        )
        _string_list(
            row.get("counter_evidence_refs"),
            "NATIVE_MARKET_INFERENCE_COUNTER_INVALID",
        )

    hypothesis_updates = payload.get("hypothesis_updates")
    if not isinstance(hypothesis_updates, list) or not hypothesis_updates:
        raise NativeMarketCycleError("NATIVE_MARKET_HYPOTHESIS_UPDATE_REQUIRED")
    hypothesis_ids: set[str] = set()
    for row in hypothesis_updates:
        if not isinstance(row, Mapping):
            raise NativeMarketCycleError("NATIVE_MARKET_HYPOTHESIS_UPDATE_INVALID")
        hypothesis_id = _text(
            row.get("hypothesis_id"), "NATIVE_MARKET_HYPOTHESIS_ID_INVALID"
        )
        if hypothesis_id in hypothesis_ids:
            raise NativeMarketCycleError("NATIVE_MARKET_HYPOTHESIS_ID_DUPLICATE")
        hypothesis_ids.add(hypothesis_id)
        if row.get("operation") not in {"CREATE", "UPDATE", "CLOSE"}:
            raise NativeMarketCycleError("NATIVE_MARKET_HYPOTHESIS_OPERATION_INVALID")
        if row.get("status") not in {"CANDIDATE", "WATCH", "ACTIVE", "CLOSED"}:
            raise NativeMarketCycleError("NATIVE_MARKET_HYPOTHESIS_STATUS_INVALID")
        if (row.get("operation") == "CLOSE") != (row.get("status") == "CLOSED"):
            raise NativeMarketCycleError("NATIVE_MARKET_HYPOTHESIS_CLOSE_INVALID")
        for field in ("thesis", "falsifier", "expiry", "next_observation"):
            _text(
                row.get(field),
                f"NATIVE_MARKET_HYPOTHESIS_{field.upper()}_INVALID",
            )
        _string_list(
            row.get("evidence_refs"),
            "NATIVE_MARKET_HYPOTHESIS_EVIDENCE_INVALID",
        )

    expectation_updates = payload.get("expectation_updates")
    if not isinstance(expectation_updates, list) or not expectation_updates:
        raise NativeMarketCycleError("NATIVE_MARKET_EXPECTATION_UPDATE_REQUIRED")
    expectation_ids: set[str] = set()
    for row in expectation_updates:
        if not isinstance(row, Mapping):
            raise NativeMarketCycleError("NATIVE_MARKET_EXPECTATION_UPDATE_INVALID")
        expectation_id = _text(
            row.get("expectation_id"), "NATIVE_MARKET_EXPECTATION_ID_INVALID"
        )
        if expectation_id in expectation_ids:
            raise NativeMarketCycleError("NATIVE_MARKET_EXPECTATION_ID_DUPLICATE")
        expectation_ids.add(expectation_id)
        if row.get("operation") not in {"CREATE", "UPDATE", "CLOSE"}:
            raise NativeMarketCycleError("NATIVE_MARKET_EXPECTATION_OPERATION_INVALID")
        if row.get("status") not in {"OPEN", "FULFILLED", "FAILED", "EXPIRED", "CLOSED"}:
            raise NativeMarketCycleError("NATIVE_MARKET_EXPECTATION_STATUS_INVALID")
        for field in ("statement", "condition", "expiry", "next_observation"):
            _text(
                row.get(field),
                f"NATIVE_MARKET_EXPECTATION_{field.upper()}_INVALID",
            )
        _text(
            row.get("hypothesis_id"),
            "NATIVE_MARKET_EXPECTATION_HYPOTHESIS_INVALID",
        )
        _string_list(
            row.get("evidence_refs"),
            "NATIVE_MARKET_EXPECTATION_EVIDENCE_INVALID",
        )
        if row.get("operation") == "CLOSE" and row.get("status") != "CLOSED":
            raise NativeMarketCycleError("NATIVE_MARKET_EXPECTATION_CLOSE_INVALID")

    competition = payload.get("path_competition")
    if not isinstance(competition, Mapping):
        raise NativeMarketCycleError("NATIVE_MARKET_PATH_COMPETITION_INVALID")
    path_ids = []
    for field in ("lead_path_id", "runner_up_path_id", "other_path_id"):
        path_ids.append(
            _text(
                competition.get(field),
                f"NATIVE_MARKET_{field.upper()}_INVALID",
            )
        )
    if len(set(path_ids)) != 3:
        raise NativeMarketCycleError("NATIVE_MARKET_PATH_COMPETITION_DUPLICATE")
    _text(
        competition.get("ranking_basis"),
        "NATIVE_MARKET_PATH_RANKING_BASIS_INVALID",
    )
    _text(
        competition.get("switch_condition"),
        "NATIVE_MARKET_PATH_SWITCH_CONDITION_INVALID",
    )

    candidates = payload.get("candidate_proposals")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise NativeMarketCycleError("NATIVE_MARKET_CANDIDATES_INVALID")
    actions: set[str] = set()
    candidate_ids: set[str] = set()
    for row in candidates:
        if not isinstance(row, Mapping):
            raise NativeMarketCycleError("NATIVE_MARKET_CANDIDATE_INVALID")
        candidate_id = _text(
            row.get("candidate_id"), "NATIVE_MARKET_CANDIDATE_ID_INVALID"
        )
        action = _text(row.get("action_class"), "NATIVE_MARKET_ACTION_INVALID")
        if candidate_id in candidate_ids or action in actions or action not in MARKET_ACTIONS:
            raise NativeMarketCycleError("NATIVE_MARKET_CANDIDATE_SET_INVALID")
        candidate_ids.add(candidate_id)
        actions.add(action)
        _text(row.get("thesis"), "NATIVE_MARKET_CANDIDATE_THESIS_INVALID")
        _text(
            row.get("hypothesis_id"),
            "NATIVE_MARKET_CANDIDATE_HYPOTHESIS_INVALID",
        )
        _string_list(
            row.get("evidence_refs"),
            "NATIVE_MARKET_CANDIDATE_EVIDENCE_INVALID",
        )
        if action == "WAIT":
            for field in ("reason", "opportunity_cost", "next_review_condition"):
                _text(
                    row.get(field),
                    f"NATIVE_MARKET_WAIT_{field.upper()}_INVALID",
                )
            for field in (
                "entry_reference_price",
                "stop_price",
                "target_price",
                "notional_usdt",
            ):
                if row.get(field) is not None:
                    raise NativeMarketCycleError(
                        "NATIVE_MARKET_WAIT_GEOMETRY_FORBIDDEN"
                    )
        else:
            for field in (
                "entry_reference_price",
                "stop_price",
                "target_price",
                "notional_usdt",
            ):
                _decimal(
                    row.get(field),
                    f"NATIVE_MARKET_CANDIDATE_{field.upper()}_INVALID",
                    positive=True,
                )
    if actions != set(MARKET_ACTIONS):
        raise NativeMarketCycleError("NATIVE_MARKET_CANDIDATE_SET_INVALID")
    return dict(payload)


def validate_native_market_deliberation_payload(
    *, request: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    _common_payload_binding(
        request=request,
        payload=payload,
        schema_id="native_codex_market_deliberation_payload",
    )
    if payload.get("evaluation_digest") != request.get("evaluation_digest"):
        raise NativeMarketCycleError(
            "NATIVE_MARKET_DELIBERATION_EVALUATION_MISMATCH"
        )
    _text(
        payload.get("selected_candidate_id"),
        "NATIVE_MARKET_SELECTED_CANDIDATE_INVALID",
    )
    ranked = _string_list(
        payload.get("ranked_alternative_ids"),
        "NATIVE_MARKET_RANKED_ALTERNATIVES_INVALID",
    )
    if len(set(ranked)) != len(ranked):
        raise NativeMarketCycleError("NATIVE_MARKET_RANKED_ALTERNATIVES_DUPLICATE")
    why_not = payload.get("why_not_selected")
    if not isinstance(why_not, Mapping) or set(why_not) != set(ranked):
        raise NativeMarketCycleError("NATIVE_MARKET_WHY_NOT_SELECTED_INVALID")
    for value in why_not.values():
        _text(value, "NATIVE_MARKET_WHY_NOT_SELECTED_INVALID")
    for field in ("selection_rationale", "next_review_condition"):
        _text(
            payload.get(field),
            f"NATIVE_MARKET_DELIBERATION_{field.upper()}_INVALID",
        )
    return dict(payload)


def validate_native_market_payload(
    *, request: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    expected = request.get("expected_output_schema_id")
    if expected == "native_codex_market_proposal_payload":
        return validate_native_market_proposal_payload(
            request=request, payload=payload
        )
    if expected == "native_codex_market_deliberation_payload":
        return validate_native_market_deliberation_payload(
            request=request, payload=payload
        )
    raise NativeMarketCycleError("NATIVE_MARKET_OUTPUT_SCHEMA_INVALID")


def build_shadow_action_evaluation(
    *,
    run_id: str,
    cycle_index: int,
    market_snapshot_digest: str,
    mark_price: str,
    valid_evidence_refs: Sequence[str],
    candidate_proposals: Sequence[Mapping[str, Any]],
    notional_usdt: str,
    fee_rate: str,
    slippage_rate: str,
    max_probe_risk_usdt: str,
    min_net_rr: str,
) -> dict[str, Any]:
    mark = _decimal(mark_price, "NATIVE_MARKET_MARK_INVALID", positive=True)
    fixed_notional = _decimal(
        notional_usdt, "NATIVE_MARKET_NOTIONAL_INVALID", positive=True
    )
    fee = _decimal(fee_rate, "NATIVE_MARKET_FEE_INVALID")
    slippage = _decimal(slippage_rate, "NATIVE_MARKET_SLIPPAGE_INVALID")
    risk_cap = _decimal(
        max_probe_risk_usdt, "NATIVE_MARKET_RISK_CAP_INVALID", positive=True
    )
    rr_floor = _decimal(min_net_rr, "NATIVE_MARKET_RR_FLOOR_INVALID", positive=True)
    if fee < 0 or slippage < 0 or fee >= 1 or slippage >= 1:
        raise NativeMarketCycleError("NATIVE_MARKET_COST_POLICY_INVALID")
    valid_refs = set(valid_evidence_refs)
    if not valid_refs:
        raise NativeMarketCycleError("NATIVE_MARKET_EVIDENCE_SET_EMPTY")
    rows: list[dict[str, Any]] = []
    for candidate in candidate_proposals:
        action = candidate["action_class"]
        hard_vetoes: list[str] = []
        if not set(candidate["evidence_refs"]).issubset(valid_refs):
            hard_vetoes.append("EVIDENCE_REF_NOT_CURRENT_CYCLE")
        row: dict[str, Any] = {
            "candidate_id": candidate["candidate_id"],
            "action_class": action,
            "hypothesis_id": candidate["hypothesis_id"],
            "source_cycle_index": cycle_index,
            "market_snapshot_digest": market_snapshot_digest,
            "hard_vetoes": hard_vetoes,
        }
        if action == "WAIT":
            row.update(
                {
                    "feasible": not hard_vetoes,
                    "entry_execution_price": None,
                    "stop_execution_price": None,
                    "target_execution_price": None,
                    "quantity_btc": None,
                    "net_risk_usdt": None,
                    "net_reward_usdt": None,
                    "net_rr": None,
                    "opportunity_cost": candidate["opportunity_cost"],
                    "next_review_condition": candidate[
                        "next_review_condition"
                    ],
                }
            )
        else:
            entry_reference = _decimal(
                candidate["entry_reference_price"],
                "NATIVE_MARKET_ENTRY_INVALID",
                positive=True,
            )
            stop = _decimal(
                candidate["stop_price"],
                "NATIVE_MARKET_STOP_INVALID",
                positive=True,
            )
            target = _decimal(
                candidate["target_price"],
                "NATIVE_MARKET_TARGET_INVALID",
                positive=True,
            )
            candidate_notional = _decimal(
                candidate["notional_usdt"],
                "NATIVE_MARKET_NOTIONAL_INVALID",
                positive=True,
            )
            if entry_reference != mark:
                hard_vetoes.append("ENTRY_REFERENCE_NOT_CURRENT_MARK")
            if candidate_notional != fixed_notional:
                hard_vetoes.append("NOTIONAL_NOT_FROZEN_PROBE_SIZE")
            if action == "OPEN_LONG":
                if not stop < mark < target:
                    hard_vetoes.append("LONG_GEOMETRY_INVALID")
                entry_execution = mark * (Decimal("1") + slippage)
                stop_execution = stop * (Decimal("1") - slippage)
                target_execution = target * (Decimal("1") - slippage)
                quantity = fixed_notional / entry_execution
                gross_risk = quantity * (entry_execution - stop_execution)
                gross_reward = quantity * (target_execution - entry_execution)
            else:
                if not target < mark < stop:
                    hard_vetoes.append("SHORT_GEOMETRY_INVALID")
                entry_execution = mark * (Decimal("1") - slippage)
                stop_execution = stop * (Decimal("1") + slippage)
                target_execution = target * (Decimal("1") + slippage)
                quantity = fixed_notional / entry_execution
                gross_risk = quantity * (stop_execution - entry_execution)
                gross_reward = quantity * (entry_execution - target_execution)
            entry_fee = fixed_notional * fee
            stop_fee = quantity * stop_execution * fee
            target_fee = quantity * target_execution * fee
            net_risk = gross_risk + entry_fee + stop_fee
            net_reward = gross_reward - entry_fee - target_fee
            net_rr = (
                net_reward / net_risk if net_risk > 0 else Decimal("-1")
            )
            if net_risk <= 0 or net_risk > risk_cap:
                hard_vetoes.append("PROBE_RISK_CAP_FAILED")
            if net_reward <= 0 or net_rr < rr_floor:
                hard_vetoes.append("MIN_NET_RR_FAILED")
            row.update(
                {
                    "feasible": not hard_vetoes,
                    "entry_execution_price": canonical_decimal(entry_execution),
                    "stop_execution_price": canonical_decimal(stop_execution),
                    "target_execution_price": canonical_decimal(target_execution),
                    "quantity_btc": canonical_decimal(
                        quantity.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
                    ),
                    "net_risk_usdt": canonical_decimal(net_risk),
                    "net_reward_usdt": canonical_decimal(net_reward),
                    "net_rr": canonical_decimal(net_rr),
                    "opportunity_cost": None,
                    "next_review_condition": None,
                }
            )
        rows.append(
            self_digest(row, "native_shadow_candidate_evaluation_digest")
        )
    if {row["action_class"] for row in rows} != set(MARKET_ACTIONS):
        raise NativeMarketCycleError("NATIVE_MARKET_CANDIDATE_SET_INVALID")
    return self_digest(
        {
            "schema_id": "native_btc_shadow_action_evaluation",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cycle_index": cycle_index,
            "market_snapshot_digest": market_snapshot_digest,
            "mark_price": mark_price,
            "notional_usdt": notional_usdt,
            "fee_rate": fee_rate,
            "slippage_rate": slippage_rate,
            "max_probe_risk_usdt": max_probe_risk_usdt,
            "min_net_rr": min_net_rr,
            "candidates": rows,
            "shadow_only": True,
            "order_sent": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
        },
        "native_shadow_action_evaluation_digest",
    )


__all__ = [
    "MARKET_ACTIONS",
    "SENTIMENT_DIMENSIONS",
    "SENTIMENT_REQUIRED_DEPENDENCY_GROUPS",
    "NativeMarketCycleError",
    "build_shadow_action_evaluation",
    "validate_native_market_deliberation_payload",
    "validate_native_market_payload",
    "validate_native_market_proposal_payload",
]
