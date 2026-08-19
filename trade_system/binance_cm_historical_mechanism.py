"""Isolated, fail-closed Binance COIN-M historical mechanism experiment.

This module deliberately does *not* feed G1/G2 evidence.  It is a small,
dependency-free experiment runner for a separately declared historical data
set.  Historical books are sampled, not a replay of the live capture path, so
all output is descriptive and denies trading authorization.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import json
import math
import os
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from . import research as research_module
from .research import LabeledObservation, MarketOutcome, RegularizedMultinomialLogistic, evaluate_predictions, purged_walk_forward


FROZEN_PLAN = "FROZEN_BINANCE_CM_HISTORICAL_MECHANISM_PLAN_V1"
FROZEN_SMOKE_PLAN = "FROZEN_BINANCE_CM_HISTORICAL_MECHANISM_SMOKE_PLAN_V1"
_HEADERS = {
    "aggTrades": ("agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"),
    "bookDepth": ("timestamp", "percentage", "depth", "notional"),
    "metrics": ("create_time", "symbol", "sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"),
}
_KINDS = tuple(_HEADERS)


class HistoricalMechanismError(ValueError):
    pass


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_day(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise HistoricalMechanismError("%s must be an ISO date" % field)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HistoricalMechanismError("%s must be an ISO date" % field) from exc


def _dt_text(value: str, field: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise HistoricalMechanismError("%s must be UTC YYYY-MM-DD HH:MM:SS" % field) from exc


def _number(value: Any, field: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalMechanismError("%s must be numeric" % field) from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise HistoricalMechanismError("%s is not a permitted finite value" % field)
    return result


@dataclass(frozen=True)
class HistoricalMechanismPlan:
    experiment_id: str
    status: str
    venue: str
    instrument: str
    dates: Tuple[date, ...]
    development_dates: Tuple[date, ...]
    evaluation_dates: Tuple[date, ...]
    min_rows_per_side: int
    state_thin_max_depth: float
    state_deep_min_depth: float
    digest: str

    @classmethod
    def load(cls, path: Path) -> "HistoricalMechanismPlan":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HistoricalMechanismError("cannot load historical mechanism plan") from exc
        if not isinstance(raw, dict):
            raise HistoricalMechanismError("historical mechanism plan must be an object")
        if raw.get("status") not in {FROZEN_PLAN, FROZEN_SMOKE_PLAN}:
            raise HistoricalMechanismError("historical mechanism plan is not frozen")
        if raw.get("venue") != "BINANCE_COINM" or raw.get("instrument") != "BTCUSD_PERP":
            raise HistoricalMechanismError("this experiment is restricted to Binance COIN-M BTCUSD_PERP")
        experiment_id = raw.get("experiment_id")
        if not isinstance(experiment_id, str) or not experiment_id:
            raise HistoricalMechanismError("experiment_id is required")
        declared = raw.get("dates")
        if not isinstance(declared, list) or not declared:
            raise HistoricalMechanismError("dates must be a non-empty list")
        dates = tuple(_parse_day(item, "dates") for item in declared)
        if len(set(dates)) != len(dates) or tuple(sorted(dates)) != dates:
            raise HistoricalMechanismError("dates must be strictly sorted and unique")
        development = tuple(_parse_day(item, "development_dates") for item in raw.get("development_dates", []))
        evaluation = tuple(_parse_day(item, "evaluation_dates") for item in raw.get("evaluation_dates", []))
        if raw["status"] == FROZEN_PLAN:
            expected = tuple(date(2025, 1, day) for day in range(1, 29))
            if dates != expected or development != expected[:21] or evaluation != expected[21:]:
                raise HistoricalMechanismError("v1 must be locked to 2025-01-01..28 with 01..21 development and 22..28 evaluation")
        elif development != dates or evaluation:
            raise HistoricalMechanismError("smoke plan may only use its declared dates as development and has no evaluation")
        if set(development) | set(evaluation) != set(dates) or set(development) & set(evaluation):
            raise HistoricalMechanismError("development/evaluation dates must partition dates")
        states = raw.get("liquidity_state_thresholds")
        if not isinstance(states, dict):
            raise HistoricalMechanismError("liquidity_state_thresholds is required")
        thin = _number(states.get("thin_max_depth"), "thin_max_depth", positive=True)
        deep = _number(states.get("deep_min_depth"), "deep_min_depth", positive=True)
        if thin >= deep:
            raise HistoricalMechanismError("liquidity state thresholds are invalid")
        min_rows = raw.get("min_rows_per_side", 30)
        if not isinstance(min_rows, int) or min_rows < 1:
            raise HistoricalMechanismError("min_rows_per_side must be positive")
        return cls(experiment_id, raw["status"], raw["venue"], raw["instrument"], dates, development, evaluation, min_rows, thin, deep, hashlib.sha256(_canonical(raw).encode("utf-8")).hexdigest())


@dataclass(frozen=True)
class _Trade:
    at: datetime
    trade_id: int
    price: float
    quantity: float
    buyer_maker: bool


@dataclass(frozen=True)
class _DayInput:
    day: date
    trades: Tuple[_Trade, ...]
    depths: Tuple[Tuple[datetime, float, float], ...]
    metrics: Tuple[Tuple[datetime, float], ...]
    audit: Dict[str, Any]


def _expected_name(instrument: str, kind: str, day: date) -> str:
    return "%s-%s-%s.zip" % (instrument, kind, day.isoformat())


def _official_url(instrument: str, kind: str, day: date) -> str:
    return "https://data.binance.vision/data/futures/cm/daily/%s/%s/%s" % (kind, instrument, _expected_name(instrument, kind, day))


def _software_bindings() -> Dict[str, Any]:
    experiment_path = Path(__file__).resolve()
    research_path = Path(research_module.__file__).resolve()
    return {
        "entrypoint": "trade_system.binance_cm_historical_mechanism.run_historical_mechanism_experiment",
        "experiment_module": {"path": str(experiment_path), "sha256": _sha256(experiment_path)},
        "model": {"class": "trade_system.research.RegularizedMultinomialLogistic", "module_path": str(research_path), "module_sha256": _sha256(research_path)},
    }


def _checksum(path: Path) -> str:
    if not path.is_file():
        raise HistoricalMechanismError("official checksum is missing: %s" % path)
    parts = path.read_text(encoding="utf-8").strip().split()
    if len(parts) != 2 or len(parts[0]) != 64 or parts[1].lstrip("*") != path.name[:-9]:
        raise HistoricalMechanismError("official checksum schema is invalid: %s" % path)
    return parts[0]


def _archive_csv(path: Path, kind: str) -> Iterable[Dict[str, str]]:
    if not path.is_file():
        raise HistoricalMechanismError("official archive is missing: %s" % path)
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if names != [path.name[:-4] + ".csv"]:
            raise HistoricalMechanismError("archive has an unexpected member: %s" % path)
        with archive.open(names[0], "r") as binary:
            reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8", newline=""))
            if tuple(reader.fieldnames or ()) != _HEADERS[kind]:
                raise HistoricalMechanismError("archive schema mismatch for %s" % path)
            yield from reader


def _load_day(plan: HistoricalMechanismPlan, input_root: Path, day: date) -> _DayInput:
    audits: Dict[str, Any] = {}
    raw: Dict[str, List[Dict[str, str]]] = {}
    for kind in _KINDS:
        archive = input_root / _expected_name(plan.instrument, kind, day)
        checksum = Path(str(archive) + ".CHECKSUM")
        expected = _checksum(checksum)
        observed = _sha256(archive) if archive.is_file() else ""
        if observed != expected:
            raise HistoricalMechanismError("official checksum mismatch for %s" % archive)
        rows = list(_archive_csv(archive, kind))
        if not rows:
            raise HistoricalMechanismError("archive is empty: %s" % archive)
        source_url = _official_url(plan.instrument, kind, day)
        audits[kind] = {
            "source_url": source_url,
            "checksum_source_url": source_url + ".CHECKSUM",
            "path": str(archive),
            "checksum_path": str(checksum),
            "archive_sha256": observed,
            "checksum_file_sha256": _sha256(checksum),
            "official_declared_archive_sha256": expected,
            "rows": len(rows),
        }
        raw[kind] = rows
    trades: List[_Trade] = []
    previous_key = None
    for row in raw["aggTrades"]:
        try:
            at = datetime.fromtimestamp(int(row["transact_time"]) / 1000, tz=timezone.utc)
            item = _Trade(at, int(row["agg_trade_id"]), _number(row["price"], "trade.price", positive=True), _number(row["quantity"], "trade.quantity", positive=True), str(row["is_buyer_maker"]).lower() == "true")
        except (OSError, ValueError) as exc:
            raise HistoricalMechanismError("invalid aggTrade row") from exc
        if item.at.date() != day or str(row["is_buyer_maker"]).lower() not in {"true", "false"}:
            raise HistoricalMechanismError("aggTrade date or maker value is invalid")
        key = (item.at, item.trade_id)
        if previous_key is not None and key <= previous_key:
            raise HistoricalMechanismError("aggTrades must be strictly ordered")
        previous_key = key
        trades.append(item)
    grouped: Dict[datetime, Dict[int, float]] = {}
    for row in raw["bookDepth"]:
        at = _dt_text(row["timestamp"], "bookDepth.timestamp")
        percentage = int(row["percentage"])
        depth = _number(row["depth"], "bookDepth.depth", positive=True)
        if at.date() != day or percentage not in {-1, 1}:
            continue
        if percentage in grouped.setdefault(at, {}):
            raise HistoricalMechanismError("bookDepth has duplicate 1 percent level")
        grouped[at][percentage] = depth
    depths = tuple(sorted((at, values[-1], values[1]) for at, values in grouped.items() if set(values) == {-1, 1}))
    if not depths:
        raise HistoricalMechanismError("bookDepth has no complete +/-1 percent snapshots")
    metrics: List[Tuple[datetime, float]] = []
    previous = None
    for row in raw["metrics"]:
        at = _dt_text(row["create_time"], "metrics.create_time")
        value = _number(row["sum_open_interest"], "metrics.sum_open_interest", positive=True)
        if at.date() != day or row["symbol"] != plan.instrument:
            raise HistoricalMechanismError("metrics date or symbol mismatch")
        if previous is not None and at <= previous:
            raise HistoricalMechanismError("metrics must be strictly ordered")
        previous = at
        metrics.append((at, value))
    return _DayInput(day, tuple(trades), depths, tuple(metrics), audits)


def _at_or_before(items: Sequence[Tuple[datetime, Any]], target: datetime) -> Any:
    positions = [item[0] for item in items]
    index = bisect.bisect_left(positions, target) - 1  # strict: target is not yet observable
    return items[index] if index >= 0 else None


def _state(total_depth: float, plan: HistoricalMechanismPlan) -> str:
    if total_depth <= plan.state_thin_max_depth:
        return "THIN_BOOK"
    if total_depth >= plan.state_deep_min_depth:
        return "DEEP_BOOK"
    return "NORMAL_BOOK"


def _label(trades: Sequence[_Trade], timestamps: Sequence[datetime], decision_at: datetime, side: str) -> Tuple[MarketOutcome, datetime, float] | None:
    begin = bisect.bisect_left(timestamps, decision_at + timedelta(milliseconds=250))
    if begin >= len(trades):
        return None
    entry = trades[begin]
    expiry = entry.at + timedelta(seconds=300)
    end = bisect.bisect_right(timestamps, expiry)
    if end <= begin:
        return None
    tp = entry.price * (1.002 if side == "BUY" else 0.998)
    sl = entry.price * (0.9988 if side == "BUY" else 1.0012)
    last = entry
    for item in trades[begin:end]:
        last = item
        if (side == "BUY" and item.price >= tp) or (side == "SELL" and item.price <= tp):
            return MarketOutcome.TP, item.at, 20.0
        if (side == "BUY" and item.price <= sl) or (side == "SELL" and item.price >= sl):
            return MarketOutcome.SL, item.at, -12.0
    gross = ((last.price / entry.price) - 1.0) * (10000.0 if side == "BUY" else -10000.0)
    return MarketOutcome.TIMEOUT, expiry, gross


def _rows_for_day(item: _DayInput, plan: HistoricalMechanismPlan) -> List[Dict[str, Any]]:
    trade_times = [trade.at for trade in item.trades]
    depth_items: Sequence[Tuple[datetime, Any]] = [(at, (bid, ask)) for at, bid, ask in item.depths]
    metric_items: Sequence[Tuple[datetime, Any]] = list(item.metrics)
    start = datetime.combine(item.day, datetime.min.time(), tzinfo=timezone.utc)
    current = start + timedelta(minutes=5)
    finish = start + timedelta(hours=23, minutes=50)
    rows: List[Dict[str, Any]] = []
    cooldown_until = start
    while current <= finish:
        current_depth = _at_or_before(depth_items, current)
        prior_depth = _at_or_before(depth_items, current - timedelta(minutes=5))
        current_oi = _at_or_before(metric_items, current)
        prior_oi = _at_or_before(metric_items, current - timedelta(minutes=5))
        left, right = bisect.bisect_left(trade_times, current - timedelta(minutes=5)), bisect.bisect_left(trade_times, current)
        preceding = bisect.bisect_left(trade_times, current - timedelta(minutes=5)) - 1
        if not current_depth or not prior_depth or not current_oi or not prior_oi or right <= left or preceding < 0:
            current += timedelta(minutes=5)
            continue
        signed = sum((-trade.quantity if trade.buyer_maker else trade.quantity) for trade in item.trades[left:right])
        bid, ask = current_depth[1]
        prior_bid, prior_ask = prior_depth[1]
        total = bid + ask
        # D is deliberately expressed in percentage points.  The frozen 1.5
        # threshold therefore means net five-minute aggressor flow reaches
        # 1.5 percent of contemporaneously observable +/-1% book depth.
        d = 100.0 * signed / total
        if abs(d) < 1.5 or current < cooldown_until:
            current += timedelta(minutes=5)
            continue
        price = item.trades[right - 1].price
        old_price = item.trades[preceding].price
        impact = math.log(price / old_price)
        pressure_side, now_depth, old_depth = ("BUY", ask, prior_ask) if d > 0 else ("SELL", bid, prior_bid)
        resilience = math.log(now_depth / old_depth) - abs(impact)
        oi = float(current_oi[1])
        old_oi = float(prior_oi[1])
        features = {
            "D": d, "impact": impact, "R": resilience, "L": math.log(oi / old_oi),
            "state_THIN": 1.0 if _state(total, plan) == "THIN_BOOK" else 0.0,
            "state_NORMAL": 1.0 if _state(total, plan) == "NORMAL_BOOK" else 0.0,
            "state_DEEP": 1.0 if _state(total, plan) == "DEEP_BOOK" else 0.0,
        }
        features.update({"D_x_L_THIN": d * features["L"] * features["state_THIN"], "D_x_L_NORMAL": d * features["L"] * features["state_NORMAL"], "D_x_L_DEEP": d * features["L"] * features["state_DEEP"]})
        label = _label(item.trades, trade_times, current, "SELL" if d > 0 else "BUY")
        if label is not None:
            outcome, ended, gross = label
            side = "SELL" if d > 0 else "BUY"
            rows.append({"episode_id": "%s-%s-%04d" % (item.day.isoformat(), side, len(rows)), "decision_at": current, "label_end_at": ended, "side": side, "state_id": _state(total, plan), "outcome": outcome, "gross_return_bps": gross, "features": features, "directional_depth_side": pressure_side})
            cooldown_until = ended + timedelta(seconds=30)
        current += timedelta(minutes=5)
    return rows


_GROUPS = {
    "H-001": (("D", "impact", "R"), ("D", "impact")),
    "H-002": (("D", "R"), ("D",)),
    "H-003": (("D", "L", "state_THIN", "state_NORMAL", "state_DEEP", "D_x_L_THIN", "D_x_L_NORMAL", "D_x_L_DEEP"), ("D", "L", "state_THIN", "state_NORMAL", "state_DEEP")),
}


def _observations(rows: Sequence[Dict[str, Any]]) -> Tuple[LabeledObservation, ...]:
    return tuple(LabeledObservation(row["episode_id"], row["decision_at"], row["label_end_at"], row["features"], row["outcome"], row["state_id"]) for row in rows)


def _metrics(rows: Sequence[LabeledObservation], names: Sequence[str]) -> Dict[str, Any]:
    if not rows:
        raise HistoricalMechanismError("cannot score empty historical rows")
    model = RegularizedMultinomialLogistic(names).fit(rows)
    result = evaluate_predictions((row.outcome, model.predict(row.features)) for row in rows)
    return {"observations": result.observations, "log_loss": result.log_loss, "multiclass_brier": result.multiclass_brier, "accuracy": result.accuracy}


def _walk_forward(rows: Sequence[Dict[str, Any]], names: Sequence[str], minimum: int) -> Dict[str, Any]:
    observations = _observations(rows)
    if len(observations) < minimum:
        return {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "insufficient development rows", "observations": len(observations)}
    try:
        folds = purged_walk_forward(observations, folds=5, embargo=timedelta(seconds=300))
    except ValueError as exc:
        return {"status": "INCONCLUSIVE/WAIT_DATA", "reason": str(exc), "observations": len(observations)}
    reports = []
    for fold in folds:
        if len(fold.train) < 2 or not fold.test:
            return {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "insufficient purged fold", "observations": len(observations)}
        model = RegularizedMultinomialLogistic(names).fit(fold.train)
        metrics = evaluate_predictions((row.outcome, model.predict(row.features)) for row in fold.test)
        reports.append({"train": len(fold.train), "test": metrics.observations, "log_loss": metrics.log_loss, "multiclass_brier": metrics.multiclass_brier, "accuracy": metrics.accuracy})
    return {"status": "DESCRIPTIVE", "observations": len(observations), "folds": reports, "mean_log_loss": sum(row["log_loss"] for row in reports) / len(reports), "mean_multiclass_brier": sum(row["multiclass_brier"] for row in reports) / len(reports)}


def _locked_eval(development: Sequence[Dict[str, Any]], evaluation: Sequence[Dict[str, Any]], names: Sequence[str], minimum: int) -> Dict[str, Any]:
    train, test = _observations(development), _observations(evaluation)
    if len(train) < minimum or not test:
        return {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "insufficient locked development/evaluation rows", "development_rows": len(train), "evaluation_rows": len(test)}
    model = RegularizedMultinomialLogistic(names).fit(train)
    metrics = evaluate_predictions((row.outcome, model.predict(row.features)) for row in test)
    return {"status": "DESCRIPTIVE", "development_rows": len(train), "evaluation_rows": metrics.observations, "log_loss": metrics.log_loss, "multiclass_brier": metrics.multiclass_brier, "accuracy": metrics.accuracy}


def _costs(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"status": "INCONCLUSIVE/WAIT_DATA", "reason": "no counterfactual probe paths"}
    gross = sum(row["gross_return_bps"] for row in rows) / len(rows)
    return {"status": "DESCRIPTIVE", "observations": len(rows), "mean_gross_return_bps": gross, "BASE_10BPS": gross - 10.0, "STRESS_20BPS": gross - 20.0}


def run_historical_mechanism_experiment(plan: HistoricalMechanismPlan, *, input_root: Path) -> Dict[str, Any]:
    """Audit all declared input before deriving any row; raises on any gap."""
    # Process one calendar day at a time.  The raw trade archives are large,
    # while the retained object is only a declared five-minute probe row.  This
    # keeps the experiment bounded without changing its point-in-time inputs.
    input_audit: Dict[str, Any] = {}
    rows: List[Dict[str, Any]] = []
    for day in plan.dates:
        item = _load_day(plan, Path(input_root), day)
        input_audit[day.isoformat()] = item.audit
        rows.extend(_rows_for_day(item, plan))
    development = [row for row in rows if row["decision_at"].date() in set(plan.development_dates)]
    evaluation = [row for row in rows if row["decision_at"].date() in set(plan.evaluation_dates)]
    report: Dict[str, Any] = {
        "record_type": "binance_coinm_historical_mechanism_experiment.v1", "experiment_id": plan.experiment_id,
        "plan_status": plan.status, "plan_sha256": plan.digest, "venue": plan.venue, "instrument": plan.instrument,
        "eligible_for_binance_g2": False, "trading_authorization": "DENIED",
        "software_bindings": _software_bindings(),
        "input_audit": input_audit, "input_manifest_sha256": hashlib.sha256(_canonical(input_audit).encode("utf-8")).hexdigest(),
        "date_coverage": {"declared": [day.isoformat() for day in plan.dates], "development": [day.isoformat() for day in plan.development_dates], "locked_evaluation": [day.isoformat() for day in plan.evaluation_dates]},
        "rows": {"all": len(rows), "development": len(development), "locked_evaluation": len(evaluation), "by_side": {side: sum(1 for row in rows if row["side"] == side) for side in ("BUY", "SELL")}, "by_state": {state: sum(1 for row in rows if row["state_id"] == state) for state in ("THIN_BOOK", "NORMAL_BOOK", "DEEP_BOOK")}},
        "counterfactual_path": {"signal": "abs(D)>=1.5 percentage points of +/-1% displayed depth", "direction": "contrarian PROBE", "latency_ms": 250, "tp_bps": 20, "sl_bps": 12, "max_holding_seconds": 300, "cooldown_seconds": 30, "ordering": "aggTrade transact_time then aggregate_trade_id"},
        "cost_descriptive": {"all": _costs(rows), "development": _costs(development), "locked_evaluation": _costs(evaluation)},
        "hypotheses": {},
        "limitation": "Historical COIN-M sampled-book mechanism evidence only. It is not Binance USD-M ACTUAL evidence, does not establish G1/G2/G3, does not prove archive completeness, execution cost, fillability or profitability, and never authorizes trading.",
    }
    for hypothesis, (candidate, control) in _GROUPS.items():
        entry: Dict[str, Any] = {"candidate_features": list(candidate), "control_features": list(control), "by_side": {}}
        for side in ("BUY", "SELL"):
            dev_side = [row for row in development if row["side"] == side]
            eval_side = [row for row in evaluation if row["side"] == side]
            entry["by_side"][side] = {"purged_walk_forward": {"candidate": _walk_forward(dev_side, candidate, plan.min_rows_per_side), "control": _walk_forward(dev_side, control, plan.min_rows_per_side)}, "locked_evaluation": {"candidate": _locked_eval(dev_side, eval_side, candidate, plan.min_rows_per_side), "control": _locked_eval(dev_side, eval_side, control, plan.min_rows_per_side)}}
        report["hypotheses"][hypothesis] = entry
    report["hypotheses"]["H-004"] = {"status": "UNTESTABLE_MISSING_LIQUIDATION", "reason": "frozen input contract deliberately excludes liquidation data; no proxy is substituted"}
    return report


def write_historical_mechanism_report(path: Path, report: Mapping[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(_canonical(dict(report)) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path
