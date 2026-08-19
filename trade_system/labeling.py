"""Generate auditable action-specific competing-risk labels from feature replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .decision import ActionContract, ExecutionOutcome, PathPoint, label_market_path
from .types import PositionStage, Side, parse_utc


@dataclass(frozen=True)
class ActionRecord:
    decision_id: str
    episode_id: str
    decision_at: datetime
    filled_at: datetime
    contract: ActionContract
    execution_outcome: Optional[ExecutionOutcome]
    fill_fraction: Optional[Decimal]
    features: Dict[str, float]
    state_id: str = "UNASSIGNED"
    structure_invalidated_at: Optional[datetime] = None
    operational_override_at: Optional[datetime] = None
    operational_override: Optional[str] = None
    evidence_id: Optional[str] = None
    action_schema_version: str = "research-action-v1"
    market_path_entry_assumption: Optional[str] = None
    execution_evidence: bool = True
    structure_exit_states: tuple[str, ...] = ()
    require_decision_eligible_for_structure_exit: bool = False
    feature_event_id: Optional[str] = None


@dataclass(frozen=True)
class EpisodePathContext:
    observed_at: datetime
    episode_id: Optional[str]
    episode_state: Optional[str]
    decision_eligible: Optional[bool]
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class V2LabelResult:
    outcome: Optional[str]
    observed_at: datetime
    operational_override: Optional[str]
    exit_price: Optional[Decimal]
    mfe_bps: Optional[Decimal]
    mae_bps: Optional[Decimal]


_DATA_FAILURE_FLAGS = frozenset({"book_invalid", "gap", "sequence_gap", "late_critical", "pipeline_normalization_error"})


def _as_decimal(value: Any, name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError("invalid decimal %s" % name) from exc


def load_actions(path: Path) -> List[ActionRecord]:
    actions: List[ActionRecord] = []
    ids = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                decision_id = str(raw["decision_id"])
                if decision_id in ids:
                    raise ValueError("duplicate decision_id")
                ids.add(decision_id)
                schema_version = raw.get("action_schema_version", "research-action-v1")
                if schema_version == "research-action-v2":
                    if raw.get("market_path_entry_assumption") != "COUNTERFACTUAL_ENTRY_FOR_LABEL_ONLY" or raw.get("execution_evidence") is not False:
                        raise ValueError("v2 action must be counterfactual and have no execution evidence")
                    if "execution_outcome" in raw or "fill_fraction" in raw or "filled_at" in raw or "structure_invalidated_at" in raw:
                        raise ValueError("v2 action must not contain execution or future structure fields")
                    execution = None
                    fill_fraction = None
                    filled_at = parse_utc(raw["market_path_entry_at"])
                    decision_at = parse_utc(raw["decision_at"])
                    if decision_at != filled_at:
                        raise ValueError("v2 decision_at must equal market_path_entry_at")
                    feature_event_id = raw.get("feature_event_id")
                    if not isinstance(feature_event_id, str) or not feature_event_id:
                        raise ValueError("v2 action requires feature_event_id")
                    structure_rule = raw.get("structure_exit_rule")
                    if not isinstance(structure_rule, dict) or tuple(structure_rule.get("episode_states", ())) != ("FAILED",) or structure_rule.get("require_decision_eligible") is not True or structure_rule.get("unknown_or_data_failure") != "OPERATIONAL_CENSOR":
                        raise ValueError("v2 action has invalid structure_exit_rule")
                elif schema_version == "research-action-v1":
                    execution = ExecutionOutcome(raw.get("execution_outcome", "FILLED"))
                    fill_fraction = _as_decimal(raw.get("fill_fraction", "1"), "fill_fraction")
                    if not Decimal("0") <= fill_fraction <= Decimal("1"):
                        raise ValueError("fill_fraction must be in [0, 1]")
                    filled_at = parse_utc(raw["filled_at"])
                    decision_at = parse_utc(raw["decision_at"])
                    feature_event_id = None
                    structure_rule = None
                else:
                    raise ValueError("unsupported action_schema_version")
                state_id = raw.get("state_id", "UNASSIGNED")
                if not isinstance(state_id, str) or not state_id:
                    raise ValueError("state_id must be a non-empty string")
                evidence_id = raw.get("evidence_id")
                if evidence_id is not None and (not isinstance(evidence_id, str) or not evidence_id):
                    raise ValueError("evidence_id must be a non-empty string when supplied")
                contract = ActionContract(
                    side=Side(raw["side"]),
                    stage=PositionStage(raw["stage"]),
                    entry_price=_as_decimal(raw["entry_price"], "entry_price"),
                    take_profit=_as_decimal(raw["take_profit"], "take_profit"),
                    stop_loss=_as_decimal(raw["stop_loss"], "stop_loss"),
                    horizon=timedelta(seconds=float(raw["horizon_seconds"])),
                    structure_exit_fraction=_as_decimal(raw.get("structure_exit_fraction", "0"), "structure_exit_fraction"),
                )
                actions.append(ActionRecord(
                    decision_id=decision_id,
                    episode_id=str(raw["episode_id"]),
                    decision_at=decision_at,
                    filled_at=filled_at,
                    contract=contract,
                    execution_outcome=execution,
                    fill_fraction=fill_fraction,
                    features={key: float(value) for key, value in raw["features"].items()},
                    state_id=state_id,
                    structure_invalidated_at=parse_utc(raw["structure_invalidated_at"]) if raw.get("structure_invalidated_at") else None,
                    operational_override_at=parse_utc(raw["operational_override_at"]) if raw.get("operational_override_at") else None,
                    operational_override=raw.get("operational_override"),
                    evidence_id=evidence_id,
                    action_schema_version=schema_version,
                    market_path_entry_assumption=raw.get("market_path_entry_assumption"),
                    execution_evidence=raw.get("execution_evidence", True),
                    structure_exit_states=tuple(structure_rule["episode_states"]) if structure_rule is not None else (),
                    require_decision_eligible_for_structure_exit=bool(structure_rule["require_decision_eligible"]) if structure_rule is not None else False,
                    feature_event_id=feature_event_id,
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("invalid action at %s:%d: %s" % (path, line_number, exc)) from exc
    return actions


def load_feature_prices(path: Path, *, allow_reconstructed: bool = False) -> List[PathPoint]:
    points: List[PathPoint] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if raw.get("availability_kind") == "RECONSTRUCTED" and not allow_reconstructed:
                    raise ValueError("RECONSTRUCTED feature row is not eligible")
                values = raw["values"]
                points.append(PathPoint(
                    observed_at=parse_utc(raw["available_at"]),
                    price=_as_decimal(values["mid_price"], "mid_price"),
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("invalid feature row at %s:%d: %s" % (path, line_number, exc)) from exc
    return sorted(points, key=lambda item: item.observed_at)


def _points_for_action(action: ActionRecord, points: Sequence[PathPoint]) -> Iterable[PathPoint]:
    deadline = action.filled_at + action.contract.horizon
    structure_applied = False
    override_applied = False
    for point in points:
        if point.observed_at < action.filled_at:
            continue
        if point.observed_at > deadline:
            break
        # Slow operational events are observed independently of the feature
        # clock. Apply each at the first eligible market observation, never
        # only when the two clocks happen to share an exact timestamp.
        structure_invalidated = (
            not structure_applied
            and action.structure_invalidated_at is not None
            and point.observed_at >= action.structure_invalidated_at
        )
        override = (
            action.operational_override
            if not override_applied
            and action.operational_override_at is not None
            and point.observed_at >= action.operational_override_at
            else None
        )
        structure_applied = structure_applied or structure_invalidated
        override_applied = override_applied or override is not None
        yield PathPoint(
            observed_at=point.observed_at,
            price=point.price,
            structure_invalidated=structure_invalidated,
            operational_override=override,
        )


def _v2_exit_event(action: ActionRecord, contexts: Sequence[EpisodePathContext]) -> tuple[Optional[datetime], Optional[datetime]]:
    """Return the first v2 structure or operational-censor event.

    Quality failure is evidence-wide: a broken book cannot safely label any
    episode sharing that evidence path.  UNKNOWN remains episode-specific.
    Grouping by timestamp keeps the result independent of input-file order and
    makes censoring dominate a concurrent FAILED transition.
    """
    deadline = action.filled_at + action.contract.horizon
    grouped: Dict[datetime, List[EpisodePathContext]] = {}
    for context in contexts:
        if action.filled_at <= context.observed_at <= deadline:
            grouped.setdefault(context.observed_at, []).append(context)
    for observed_at in sorted(grouped):
        same_time = grouped[observed_at]
        if any(_DATA_FAILURE_FLAGS.intersection(context.quality_flags) for context in same_time):
            return None, observed_at
        episode_contexts = [context for context in same_time if context.episode_id == action.episode_id]
        if any(context.episode_state == "UNKNOWN" for context in episode_contexts):
            return None, observed_at
        if any(
            context.episode_state in action.structure_exit_states
            and (not action.require_decision_eligible_for_structure_exit or context.decision_eligible is True)
            for context in episode_contexts
        ):
            return observed_at, None
    return None, None


def _return_bps(action: ActionRecord, price: Decimal) -> Decimal:
    if action.contract.side == Side.BUY:
        return (price / action.contract.entry_price - Decimal("1")) * Decimal("10000")
    # Binance USD-M is linear: one price point in a short has the same
    # percentage magnitude as one point in a long, rather than an inverse-
    # contract return.
    return (action.contract.entry_price - price) / action.contract.entry_price * Decimal("10000")


def _v2_path_extremes(action: ActionRecord, prices: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    returns = [_return_bps(action, price) for price in prices]
    return max(returns), min(returns)


def _v2_result(action: ActionRecord, outcome: str, observed_at: datetime, exit_price: Decimal, prices: Sequence[Decimal]) -> V2LabelResult:
    mfe_bps, mae_bps = _v2_path_extremes(action, prices)
    return V2LabelResult(outcome, observed_at, None, exit_price, mfe_bps, mae_bps)


def _label_v2_market_path(action: ActionRecord, points: Sequence[PathPoint], contexts: Sequence[EpisodePathContext]) -> V2LabelResult:
    deadline = action.filled_at + action.contract.horizon
    structure_at, override_at = _v2_exit_event(action, contexts)
    grouped: Dict[datetime, List[PathPoint]] = {}
    last_seen = action.filled_at
    path_prices: List[Decimal] = [action.contract.entry_price]
    coverage_observed = False
    for point in points:
        if point.observed_at < action.filled_at:
            continue
        if point.observed_at >= deadline:
            coverage_observed = True
        if point.observed_at > deadline:
            continue
        grouped.setdefault(point.observed_at, []).append(point)
        last_seen = point.observed_at
    for observed_at in sorted(grouped):
        if override_at is not None and observed_at >= override_at:
            return V2LabelResult(None, observed_at, "DATA_EXECUTION_HALT", None, None, None)
        prices = [point.price for point in grouped[observed_at]]
        if action.contract.side == Side.BUY:
            tp = any(price >= action.contract.take_profit for price in prices)
            sl = any(price <= action.contract.stop_loss for price in prices)
        else:
            tp = any(price <= action.contract.take_profit for price in prices)
            sl = any(price >= action.contract.stop_loss for price in prices)
        # A same-timestamp barrier conflict is deliberately pessimistic.
        if sl:
            return _v2_result(action, "SL", observed_at, action.contract.stop_loss, path_prices + [action.contract.stop_loss])
        if tp:
            return _v2_result(action, "TP", observed_at, action.contract.take_profit, path_prices + [action.contract.take_profit])
        if structure_at is not None and observed_at >= structure_at:
            exit_price = min(prices) if action.contract.side == Side.BUY else max(prices)
            return _v2_result(action, "STRUCTURE_EXIT", observed_at, exit_price, path_prices + [exit_price])
        path_prices.extend(prices)
    if not coverage_observed:
        return V2LabelResult(None, last_seen, "DATA_COVERAGE_GAP", None, None, None)
    return _v2_result(action, "TIMEOUT", deadline, path_prices[-1], path_prices)


def generate_labels(
    actions: Iterable[ActionRecord],
    points: Sequence[PathPoint],
    *,
    episode_contexts: Sequence[EpisodePathContext] = (),
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for action in actions:
        base = {
            "decision_id": action.decision_id,
            "episode_id": action.episode_id,
            "decision_at": action.decision_at.isoformat(),
            "side": action.contract.side.value,
            "stage": action.contract.stage.value,
            "entry_price": str(action.contract.entry_price),
            "take_profit": str(action.contract.take_profit),
            "stop_loss": str(action.contract.stop_loss),
            "horizon_seconds": action.contract.horizon.total_seconds(),
            "features": action.features,
            "state_id": action.state_id,
            "evidence_id": action.evidence_id,
            # Current P0 labels use replayed feature snapshots, not a claim of
            # tick-by-tick barrier ordering. The source is preserved so a
            # higher-resolution labeler cannot silently mix its results here.
            "market_path_source": "FEATURE_MID_PRICE",
            "label_version": "competing-risk-v2" if action.action_schema_version == "research-action-v2" else "competing-risk-v1",
        }
        if action.action_schema_version == "research-action-v2":
            base.update({
                "market_path_entry_at": action.filled_at.isoformat(),
                "market_path_entry_assumption": action.market_path_entry_assumption,
                "execution_evidence": False,
                "market_path_source": "FEATURE_MID_PRICE_AND_EPISODE_STATE",
            })
            result = _label_v2_market_path(action, points, episode_contexts)
            gross_return_bps = _return_bps(action, result.exit_price) if result.exit_price is not None else None
            rows.append(dict(
                base,
                market_outcome=result.outcome,
                outcome=result.outcome,
                label_end_at=result.observed_at.isoformat(),
                censored=result.operational_override is not None,
                operational_override=result.operational_override,
                exit_price=str(result.exit_price) if result.exit_price is not None else None,
                gross_return_bps=str(gross_return_bps) if gross_return_bps is not None else None,
                time_to_event_seconds=str(Decimal(str((result.observed_at - action.filled_at).total_seconds()))),
                mfe_bps=str(result.mfe_bps) if result.mfe_bps is not None else None,
                mae_bps=str(result.mae_bps) if result.mae_bps is not None else None,
            ))
            continue
        base.update({
            "filled_at": action.filled_at.isoformat(),
            "execution_outcome": action.execution_outcome.value,
            "fill_fraction": str(action.fill_fraction),
        })
        if action.execution_outcome == ExecutionOutcome.NO_FILL or action.fill_fraction == 0:
            rows.append(dict(base, market_outcome=None, outcome=None, label_end_at=None, censored=False, operational_override=None))
            continue
        result = label_market_path(action.contract, action.filled_at, _points_for_action(action, points))
        rows.append(dict(
            base,
            market_outcome=result.market_outcome.value if result.market_outcome else None,
            outcome=result.market_outcome.value if result.market_outcome else None,
            label_end_at=result.observed_at.isoformat(),
            censored=result.is_censored,
            operational_override=result.operational_override,
        ))
    return rows


def write_label_rows(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path = Path(path)
    if any(part in {"raw", "availability"} for part in path.parts):
        raise ValueError("labels must not overwrite raw or availability evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count
