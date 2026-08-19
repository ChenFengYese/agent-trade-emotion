"""Typed, fail-closed contract for the COIN-M historical diagnostic v2.

The February plan remains intentionally unexecutable.  January uses the same
contract solely as *seen development* data; neither status is trading or G2
authorization.  The contract owns timing and label semantics so a later
receipt-bound application cannot silently change them.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple


FROZEN_BEFORE_DOWNLOAD = "FROZEN_BEFORE_DOWNLOAD"
FROZEN_SEEN_DEVELOPMENT = "FROZEN_SEEN_DEVELOPMENT"
_STATUSES = {FROZEN_BEFORE_DOWNLOAD, FROZEN_SEEN_DEVELOPMENT}
_OUTCOMES = ("TP", "SL", "TIMEOUT")


class HistoricalDiagnosticError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise HistoricalDiagnosticError("%s must be a timezone-aware datetime" % field)
    return value.astimezone(timezone.utc)


def _iso(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise HistoricalDiagnosticError("%s must be an ISO UTC timestamp" % field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalDiagnosticError("%s is not an ISO timestamp" % field) from exc
    return _utc(parsed, field)


def _integer(mapping: Mapping[str, Any], field: str, expected: int) -> int:
    value = mapping.get(field)
    if type(value) is not int or value != expected:
        raise HistoricalDiagnosticError("%s must be fixed at %s" % (field, expected))
    return value


def _number(mapping: Mapping[str, Any], field: str, expected: float) -> float:
    value = mapping.get(field)
    if type(value) not in {int, float} or not math.isfinite(float(value)) or float(value) != expected:
        raise HistoricalDiagnosticError("%s must be fixed at %s" % (field, expected))
    return float(value)


@dataclass(frozen=True)
class HistoricalDiagnosticPlan:
    diagnostic_id: str
    status: str
    venue: str
    instrument: str
    dates: Tuple[str, ...]
    max_book_age_seconds: int
    max_book_gap_seconds: int
    max_oi_age_seconds: int
    max_oi_gap_seconds: int
    min_response_snapshots: int
    pressure_threshold: float
    raw: Dict[str, Any]
    canonical_digest: str

    @property
    def timing_policy(self) -> Mapping[str, Any]:
        return self.raw["timing_policy"]

    @property
    def evaluation_policy(self) -> Mapping[str, Any]:
        return self.raw["evaluation_policy"]

    @property
    def gate_policy(self) -> Mapping[str, Any]:
        return self.raw["gate_policy"]

    @classmethod
    def load(cls, path: Path) -> "HistoricalDiagnosticPlan":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HistoricalDiagnosticError("cannot load diagnostic plan") from exc
        if not isinstance(raw, dict) or raw.get("status") not in _STATUSES:
            raise HistoricalDiagnosticError("diagnostic plan status is invalid")
        status = raw["status"]
        if raw.get("venue") != "BINANCE_COINM" or raw.get("instrument") != "BTCUSD_PERP":
            raise HistoricalDiagnosticError("v2 diagnostic is restricted to Binance COIN-M BTCUSD_PERP")
        expected_dates = tuple("2025-%02d-%02d" % ((2 if status == FROZEN_BEFORE_DOWNLOAD else 1), day) for day in range(1, (29 if status == FROZEN_BEFORE_DOWNLOAD else 29)))
        if tuple(raw.get("dates", ())) != expected_dates:
            raise HistoricalDiagnosticError("diagnostic dates must be the exact frozen monthly set")
        identifier = raw.get("diagnostic_id")
        if not isinstance(identifier, str) or not identifier:
            raise HistoricalDiagnosticError("diagnostic_id is required")
        contract = raw.get("input_contract")
        if not isinstance(contract, dict) or tuple(contract.get("required_daily_kinds", ())) != ("aggTrades", "bookDepth", "metrics") or not isinstance(contract.get("source_url_template"), str):
            raise HistoricalDiagnosticError("input_contract is incomplete")
        if status == FROZEN_BEFORE_DOWNLOAD and (contract.get("authorization") != "REQUIRED_AFTER_EXPLICIT_AUTHORIZATION" or contract.get("fresh_mode") != "FRESH_SCORE_ONLY"):
            raise HistoricalDiagnosticError("before-download plan has wrong authorization state")
        if status == FROZEN_SEEN_DEVELOPMENT and (contract.get("authorization") != "SEEN_DEVELOPMENT_ONLY" or not isinstance(raw.get("evidence_ledger"), str)):
            raise HistoricalDiagnosticError("January development plan must bind the v1 evidence ledger")
        timing = raw.get("timing_policy")
        if not isinstance(timing, dict):
            raise HistoricalDiagnosticError("timing_policy is required")
        for field, value in (("pressure_window_seconds", 300), ("response_window_seconds", 60), ("decision_delay_after_response_seconds", 1), ("entry_latency_ms", 250), ("max_entry_wait_seconds", 60), ("path_horizon_seconds", 300), ("max_path_trade_age_seconds", 60), ("max_path_trade_gap_seconds", 60), ("max_book_age_seconds", 30), ("max_book_gap_seconds", 60), ("max_oi_age_seconds", 300), ("max_oi_gap_seconds", 300), ("min_response_snapshots", 2)):
            _integer(timing, field, value)
        signal = raw.get("signal_policy")
        if not isinstance(signal, dict) or _number(signal, "pressure_threshold", 1.5) != 1.5 or signal.get("extreme_stage") != "WATCH" or signal.get("candidate_requires") != "POST_PRESSURE_RESPONSE" or signal.get("cohort") != "ALL_EXTREMES_SHARED":
            raise HistoricalDiagnosticError("signal_policy is not the frozen outcome-free policy")
        features = raw.get("feature_proxies")
        required_features = {"D", "R", "L", "state"}
        if not isinstance(features, dict) or not required_features.issubset(features) or any(not isinstance(features[key], str) for key in required_features):
            raise HistoricalDiagnosticError("feature_proxies is incomplete")
        if status in _STATUSES:
            _number(features, "thin_max_depth", 1200000.0); _number(features, "deep_min_depth", 1600000.0)
            if features.get("response_persistence") != "all post-pressure directional-side snapshots are at least the pressure-end depth" or features.get("price_deceleration") != "signed post-pressure log return is <= 0":
                raise HistoricalDiagnosticError("January response predicates are not frozen")
        label = raw.get("label_policy")
        if not isinstance(label, dict) or label.get("entry") != "first eligible aggregate trade after 250ms" or label.get("same_timestamp_rule") != "CONSERVATIVE_SL" or label.get("gaps") != "CENSOR" or tuple(label.get("required_timestamps", ())) != ("pressure_end", "response_start", "response_end", "decision_at", "entry_at", "path_end_at", "valuation_event_at", "label_available_at"):
            raise HistoricalDiagnosticError("label_policy is incomplete")
        barriers = label.get("barriers")
        if not isinstance(barriers, dict) or _integer(barriers, "tp_bps", 20) != 20 or _integer(barriers, "sl_bps", 12) != 12 or _integer(barriers, "horizon_seconds", 300) != 300:
            raise HistoricalDiagnosticError("barrier policy differs from v2")
        split = raw.get("split_policy")
        if status == FROZEN_SEEN_DEVELOPMENT:
            if not isinstance(split, dict) or split.get("calibration") != "IDENTITY_TEMPERATURE_1":
                raise HistoricalDiagnosticError("January split_policy is incomplete")
            fit, calibration, end = (_iso(split.get(key), "split_policy." + key) for key in ("fit_end", "calibration_end", "development_test_end"))
            if not fit < calibration < end:
                raise HistoricalDiagnosticError("split boundaries are invalid")
        elif split is not None or raw.get("model_binding") != {"source":"JANUARY_RECEIPT_BOUND_MODEL_ONLY","receipt_required":True}:
            raise HistoricalDiagnosticError("fresh February plan must be score-only and receipt-bound to January model")
        evaluation = raw.get("evaluation_policy")
        if not isinstance(evaluation, dict) or tuple(evaluation.get("outcomes", ())) != _OUTCOMES or evaluation.get("timeout_payoff") != "LAST_OBSERVED_AGGTRADE_BEFORE_HORIZON_BPS" or evaluation.get("candidate") != "D+post-pressure-R+persistence+deceleration" or evaluation.get("control") != "D-only extreme" or evaluation.get("selection") != "FROZEN_POSITIVE_BASE_EV_ONLY":
            raise HistoricalDiagnosticError("evaluation policy is not fixed three-class candidate/control")
        _integer(evaluation, "base_cost_bps", 10); _integer(evaluation, "stress_cost_bps", 20)
        gates = raw.get("gate_policy")
        if not isinstance(gates, dict):
            raise HistoricalDiagnosticError("gate_policy is required")
        for field, value in (("min_effective_episodes", 600), ("min_effective_per_side", 300), ("min_utc_days", 7), ("min_effective_per_state", 100), ("bootstrap_iterations", 400), ("bootstrap_seed", 20260723)):
            _integer(gates, field, value)
        for field, value in (("relative_logloss_improvement_min", .02), ("max_utc_day_concentration", .40), ("max_state_concentration", .40), ("max_direction_concentration", .70), ("candidate_base_lower95_gt", 0.0), ("incremental_lower95_gt", 0.0), ("stress_mean_gte", 0.0)):
            _number(gates, field, value)
        expected_precedence = ("STOP_DATA_INVALID", "WAIT_DATA_COVERAGE", "STOP_PREDICTIVE", "STOP_ECONOMIC", "NOT_ADJUDICATED_DEVELOPMENT") if status == FROZEN_SEEN_DEVELOPMENT else ("STOP_DATA_INVALID", "WAIT_DATA_COVERAGE", "STOP_PREDICTIVE", "STOP_ECONOMIC", "WAIT_DATA_NOT_SCORED")
        if gates.get("brier_nonworsening") is not True or tuple(gates.get("precedence", ())) != expected_precedence or raw.get("g2_eligibility") is not False or raw.get("trading_authorization") != "DENIED":
            raise HistoricalDiagnosticError("gate/safety boundary differs from frozen contract")
        return cls(identifier, status, raw["venue"], raw["instrument"], expected_dates, timing["max_book_age_seconds"], timing["max_book_gap_seconds"], timing["max_oi_age_seconds"], timing["max_oi_gap_seconds"], timing["min_response_snapshots"], float(signal["pressure_threshold"]), raw, canonical_sha256(raw))


@dataclass(frozen=True)
class DiagnosticTiming:
    pressure_end: datetime; response_start: datetime; response_end: datetime; decision_at: datetime; entry_at: datetime; path_end_at: datetime; valuation_event_at: datetime; label_available_at: datetime
    def validate(self) -> None:
        p, rs, re, d, e, pe, ve, la = (_utc(value, name) for value, name in ((self.pressure_end,"pressure_end"),(self.response_start,"response_start"),(self.response_end,"response_end"),(self.decision_at,"decision_at"),(self.entry_at,"entry_at"),(self.path_end_at,"path_end_at"),(self.valuation_event_at,"valuation_event_at"),(self.label_available_at,"label_available_at")))
        if not (p == rs < re < d < e <= pe and e <= ve <= pe and pe <= la):
            raise HistoricalDiagnosticError("diagnostic timing violates exact pressure/response/decision/entry/path order")


@dataclass(frozen=True)
class FeatureWindow:
    start: datetime; end: datetime; observed_at: datetime; age_seconds: float; gap_seconds: float
    def validate(self, *, maximum_age: int, maximum_gap: int, name: str) -> None:
        start, end, observed = _utc(self.start, name+".start"), _utc(self.end, name+".end"), _utc(self.observed_at, name+".observed_at")
        calculated_age = (end-observed).total_seconds()
        if start >= end or observed > end or self.age_seconds < 0 or self.gap_seconds < 0 or abs(self.age_seconds-calculated_age) > 1e-6:
            raise HistoricalDiagnosticError("%s has invalid actual timestamp timing" % name)
        if self.age_seconds > maximum_age or self.gap_seconds > maximum_gap:
            raise HistoricalDiagnosticError("%s is stale or gapped" % name)


@dataclass(frozen=True)
class BarrierTrade:
    at: datetime; aggregate_trade_id: int; price: float


def label_barrier_path(*, side: str, entry_price: float, tp_bps: float, sl_bps: float, horizon_end: datetime, trades: Iterable[BarrierTrade]) -> Dict[str, Any]:
    if side not in {"BUY", "SELL"} or entry_price <= 0 or tp_bps <= 0 or sl_bps <= 0:
        raise HistoricalDiagnosticError("barrier specification is invalid")
    horizon = _utc(horizon_end, "horizon_end")
    ordered = sorted((_utc(x.at,"trade.at"), x.aggregate_trade_id, float(x.price)) for x in trades)
    if not ordered: return {"outcome":"CENSORED","reason":"NO_PATH_TRADE","path_end_at":horizon.isoformat()}
    tp, sl = entry_price*(1+(tp_bps/10000 if side=="BUY" else -tp_bps/10000)), entry_price*(1-(sl_bps/10000 if side=="BUY" else -sl_bps/10000))
    by_time: Dict[datetime, list[float]] = {}
    for at, _, price in ordered:
        if at > horizon: break
        by_time.setdefault(at, []).append(price)
    last_at = last_price = None
    for at, prices in by_time.items():
        hit_tp = any(p >= tp for p in prices) if side == "BUY" else any(p <= tp for p in prices)
        hit_sl = any(p <= sl for p in prices) if side == "BUY" else any(p >= sl for p in prices)
        if hit_sl: return {"outcome":"SL","path_end_at":at.isoformat(),"valuation_event_at":at.isoformat(),"same_timestamp_conservative_sl":hit_tp}
        if hit_tp: return {"outcome":"TP","path_end_at":at.isoformat(),"valuation_event_at":at.isoformat(),"same_timestamp_conservative_sl":False}
        last_at, last_price = at, prices[-1]
    if last_at is None: return {"outcome":"CENSORED","reason":"PATH_GAP","path_end_at":horizon.isoformat()}
    return {"outcome":"TIMEOUT","path_end_at":horizon.isoformat(),"valuation_event_at":last_at.isoformat(),"valuation_price":last_price,"valuation_kind":"LAST_OBSERVED_TRADE_BEFORE_HORIZON"}


def build_extreme_diagnostic_row(*, plan: HistoricalDiagnosticPlan, d_pressure_proxy: float, r_response_proxy: float, l_oi_proxy: float, state_id: str, pressure_window: FeatureWindow, response_window: FeatureWindow, oi_window: FeatureWindow, timing: DiagnosticTiming, response_snapshot_count: int, side: str) -> Dict[str, Any]:
    if side not in {"BUY","SELL"} or state_id not in {"THIN_BOOK","NORMAL_BOOK","DEEP_BOOK"}: raise HistoricalDiagnosticError("unknown diagnostic side or state")
    for name, window, age, gap in (("pressure",pressure_window,plan.max_book_age_seconds,plan.max_book_gap_seconds),("response",response_window,plan.max_book_age_seconds,plan.max_book_gap_seconds),("oi",oi_window,plan.max_oi_age_seconds,plan.max_oi_gap_seconds)):
        window.validate(maximum_age=age, maximum_gap=gap, name=name)
    timing.validate()
    if not (pressure_window.end == response_window.start and response_window.end < timing.decision_at and oi_window.start == pressure_window.start and oi_window.end == pressure_window.end): raise HistoricalDiagnosticError("D/R/L windows are not aligned")
    row={"stage":"WATCH","cohort":"ALL_EXTREMES_SHARED","decision_at":timing.decision_at.isoformat(),"side":side,"state_id":state_id,"proxies":{"D_pressure_5m_proxy":d_pressure_proxy,"R_post_pressure_60s_proxy":r_response_proxy,"L_oi_pressure_window_proxy":l_oi_proxy}}
    if abs(d_pressure_proxy)<plan.pressure_threshold: row.update(status="ABSTAIN",reason="NOT_EXTREME")
    elif response_snapshot_count<plan.min_response_snapshots: row.update(status="ABSTAIN",reason="INSUFFICIENT_POST_PRESSURE_BOOK_SNAPSHOTS")
    else: row.update(status="ELIGIBLE_DIAGNOSTIC_ONLY",candidate_features=["D_pressure_5m_proxy","R_post_pressure_60s_proxy","response_persistent","price_decelerates"],control_features=["D_pressure_5m_proxy"],selection_policy="FROZEN_POSITIVE_BASE_EV_ONLY")
    return row


def select_positive_ev(*, probabilities: Mapping[str, float], base_cost_bps: float, tp_bps: float, sl_bps: float, timeout_payoff_bps: float) -> Dict[str, Any]:
    if set(probabilities) != set(_OUTCOMES) or any(not math.isfinite(float(v)) or float(v)<0 for v in probabilities.values()) or abs(sum(float(v) for v in probabilities.values())-1)>1e-9 or not math.isfinite(timeout_payoff_bps):
        raise HistoricalDiagnosticError("probabilities must be a normalized three-outcome distribution")
    gross=probabilities["TP"]*tp_bps-probabilities["SL"]*sl_bps+probabilities["TIMEOUT"]*timeout_payoff_bps; net=gross-base_cost_bps
    return {"selected":net>0,"expected_gross_bps":gross,"expected_base_net_bps":net,"policy":"FROZEN_POSITIVE_BASE_EV_ONLY"}


def execute_frozen_before_download(plan: HistoricalDiagnosticPlan) -> None:
    if plan.status != FROZEN_BEFORE_DOWNLOAD: raise HistoricalDiagnosticError("only a pre-download plan must use this refusal endpoint")
    raise HistoricalDiagnosticError("v2 diagnostic execution refused: plan is FROZEN_BEFORE_DOWNLOAD and no authorized, receipt-bound input set exists")
