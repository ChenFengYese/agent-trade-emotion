"""Deterministic Chinese audit records for committed theory-paper cycles.

This sidecar does not participate in market analysis, portfolio decisions, or
the frozen experiment bindings.  It only renders already-committed artifacts
into a human-readable, write-once Markdown record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .common import TheoryPaperError, digest_json, read_json, verify_ledger


SHANGHAI = ZoneInfo("Asia/Shanghai")
CYCLE_PATTERN = re.compile(r"^cycle-(\d{4})$")
# Records through cycle 4 were already committed write-once with legacy labels
# for immutable entry-risk fields.  Preserve their exact bytes while making the
# same fields explicit for all later records.
LEGACY_EXECUTION_LABEL_CUTOFF = "2026-07-30T00:47:39.083611Z"
# Records through cycle 22 were already committed write-once with the label
# "strategy new-risk fills", even though the runtime counter includes any
# strategy-attributed fill (including exits). Preserve those bytes, then use
# the accurate counter name prospectively.
LEGACY_STRATEGY_FILL_LABEL_CUTOFF = "2026-07-30T20:09:17.927347Z"

THEORY_SOURCE_MAP = (
    (
        "点时事实、缺失与 UNKNOWN 边界",
        "`archive/authority/DATA_AUTHORITY_STANDARD_v1_0.md` §3–§5；"
        "`archive/authority/CORE_TRADING_THEORY_v2_1.md` §16.1–§16.2.1",
        "只使用决策时点前可得数据；缺失不能补零，单帧不能冒充连续韧性。",
    ),
    (
        "多尺度状态与父子周期职责",
        "`archive/authority/CORE_TRADING_THEORY_v2_1.md` §16.2、§16.7；"
        "`theory/history/GENERALIZED_COMPETING_PATH_THEORY_CHALLENGER_v0_5_0.md` §7",
        "周期按角色排序，不采用多数投票，低周期不得覆盖父级职责。",
    ),
    (
        "有限竞争路径、序数支持与证伪",
        "`archive/authority/CORE_TRADING_THEORY_v2_1.md` §16.3–§16.5；"
        "`theory/history/GENERALIZED_COMPETING_PATH_THEORY_CHALLENGER_v0_5_0.md` §3–§6",
        "同时保留 continuation、reversal、breakout、range 与 OTHER；"
        "支持度不是概率，hard falsifier 与 expiry 事前冻结。",
    ),
    (
        "动态假说、下一观测与版本纪律",
        "`theory/history/RESEARCH_SYSTEM_DYNAMIC_HYPOTHESIS_GRAPH_CHALLENGER_v1_2.md` "
        "§3–§14",
        "静态研究假说与运行时路径分离；原始 thesis 不因事后结果改写。",
    ),
    (
        "行动几何、成本后盈亏比与风险门",
        "`archive/authority/CORE_TRADING_THEORY_v2_1.md` §16.6；"
        "`archive/experiments/THEORY_PAPER_AGENT_GUIDE.md` §2、§5",
        "几何可行不等于执行许可；新增风险必须有触发、止损、目标、成本和风险预算。",
    ),
    (
        "纸面执行、事务链与版本绑定",
        "`archive/experiments/THEORY_PAPER_AGENT_GUIDE.md` §4、§8",
        "初始仓位不归因于理论；每次分析与决策以 prepare/commit、摘要和账本事件绑定。",
    ),
)

ACADEMIC_SOURCE_MAP = (
    (
        "Cont, Kukanov & Stoikov, The Price Impact of Order Book Events",
        "https://arxiv.org/abs/1011.6402",
        "支持研究订单流与价格冲击的关系，不证明本轮方向或盈利。",
    ),
    (
        "Hamilton (1989), DOI 10.2307/1912559",
        "https://doi.org/10.2307/1912559",
        "支持把不可直接观察的 regime 作为条件状态问题，不证明当前状态标签有效。",
    ),
    (
        "Fearnhead & Liu (2007), DOI 10.1111/j.1467-9868.2007.00601.x",
        "https://doi.org/10.1111/j.1467-9868.2007.00601.x",
        "支持在线变点与分段更新的研究方向，不证明变点可预测市场。",
    ),
    (
        "Naghshvar & Javidi (2013), DOI 10.1214/13-AOS1144",
        "https://doi.org/10.1214/13-AOS1144",
        "支持主动序贯区分观测的方向；本实验的下一观测仍是未校准计划。",
    ),
    (
        "Pearl (2009), DOI 10.1214/09-SS057",
        "https://doi.org/10.1214/09-SS057",
        "支持把观察相容性与因果识别分开，不能把行为代理写成主体意图。",
    ),
    (
        "Gneiting & Raftery (2007), DOI 10.1198/016214506000001437",
        "https://doi.org/10.1198/016214506000001437",
        "支持未来概率预测采用 proper scoring 与 calibration；当前序数支持无概率资格。",
    ),
)

AXIS_NAMES = {
    "D": "方向压力 D",
    "L": "杠杆与持仓 L",
    "C": "拥挤 C",
    "F": "强制去杠杆 F",
    "R": "流动性韧性 R",
}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise TheoryPaperError("record timestamp must be a string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TheoryPaperError(f"invalid record timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise TheoryPaperError(f"record timestamp is not timezone aware: {value}")
    return parsed.astimezone(timezone.utc)


def _time_pair(value: str) -> str:
    parsed = _parse_utc(value)
    utc_text = parsed.isoformat().replace("+00:00", "Z")
    local_text = parsed.astimezone(SHANGHAI).isoformat()
    return f"{local_text}（北京时间） / {utc_text}（UTC）"


def _filename_time(value: str) -> str:
    return _parse_utc(value).astimezone(SHANGHAI).strftime("%Y%m%dT%H%M%S%z")


def _fmt(value: Any) -> str:
    if value is None:
        return "未知"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.10g}"
    if isinstance(value, (list, tuple)):
        return "、".join(_fmt(item) for item in value) if value else "无"
    if isinstance(value, Mapping):
        return "；".join(f"{key}={_fmt(item)}" for key, item in value.items()) or "无"
    text = str(value)
    if text in {"UNKNOWN", "UNAVAILABLE", "NOT_AVAILABLE", ""}:
        return "未知"
    return text


def _cell(value: Any) -> str:
    return _fmt(value).replace("|", "\\|").replace("\n", "<br>")


def _json_block(value: Any) -> list[str]:
    return [
        "```json",
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round_number(value: float | None, digits: int = 8) -> float | None:
    return None if value is None else round(float(value), digits)


def _standard_position_snapshot(
    lot: Mapping[str, Any],
    *,
    mark_price: float | None,
    limits: Mapping[str, Any],
    snapshot_at: str,
) -> dict[str, Any]:
    quantity = _number(lot.get("quantity"))
    initial_quantity = _number(lot.get("initial_quantity"))
    entry_price = _number(lot.get("entry_price"))
    entry_notional = _number(lot.get("entry_notional_usdt"))
    side = str(lot.get("side"))
    direction = 1.0 if side == "LONG" else -1.0
    remaining_entry_fee = _number(lot.get("remaining_entry_fee_usdt")) or 0.0
    net_realized = _number(lot.get("net_realized_pnl_usdt")) or 0.0
    current_entry_notional = (
        None
        if quantity is None or entry_price is None
        else quantity * entry_price
    )
    current_notional = (
        None
        if quantity is None or mark_price is None
        else quantity * mark_price
    )
    unrealized = (
        None
        if quantity is None or entry_price is None or mark_price is None
        else direction * quantity * (mark_price - entry_price)
    )
    price_return_pct = (
        None
        if entry_price is None or entry_price <= 0 or mark_price is None
        else direction * (mark_price - entry_price) / entry_price * 100.0
    )
    cumulative_net_pnl = (
        None
        if unrealized is None
        else net_realized + unrealized - remaining_entry_fee
    )
    cumulative_net_return_pct = (
        None
        if cumulative_net_pnl is None
        or entry_notional is None
        or entry_notional <= 0
        else cumulative_net_pnl / entry_notional * 100.0
    )

    stop_price = _number(lot.get("stop_price"))
    target_price = _number(lot.get("target_price"))
    stop_slippage_bps = _number(limits.get("stop_slippage_bps")) or 0.0
    taker_fee_rate = _number(limits.get("taker_fee_rate")) or 0.0
    maker_fee_rate = _number(limits.get("maker_fee_rate")) or 0.0
    stop_fill_price = (
        None
        if stop_price is None
        else stop_price
        * (
            1.0 - stop_slippage_bps / 10000.0
            if side == "LONG"
            else 1.0 + stop_slippage_bps / 10000.0
        )
    )
    target_fill_price = target_price
    stop_quantity = quantity if stop_price is not None else None
    target_quantity = quantity if target_price is not None else None
    stop_notional = (
        None
        if stop_quantity is None or stop_price is None
        else stop_quantity * stop_price
    )
    target_notional = (
        None
        if target_quantity is None or target_price is None
        else target_quantity * target_price
    )
    stop_net_pnl_from_entry = (
        None
        if quantity is None or entry_price is None or stop_fill_price is None
        else (
            direction * quantity * (stop_fill_price - entry_price)
            - remaining_entry_fee
            - stop_fill_price * quantity * taker_fee_rate
        )
    )
    target_net_pnl_from_entry = (
        None
        if quantity is None or entry_price is None or target_fill_price is None
        else (
            direction * quantity * (target_fill_price - entry_price)
            - remaining_entry_fee
            - target_fill_price * quantity * maker_fee_rate
        )
    )
    forward_stop_risk = (
        None
        if quantity is None or mark_price is None or stop_fill_price is None
        else (
            max(
                0.0,
                direction * quantity * (mark_price - stop_fill_price),
            )
            + stop_fill_price * quantity * taker_fee_rate
        )
    )
    forward_target_reward = (
        None
        if quantity is None or mark_price is None or target_fill_price is None
        else (
            direction * quantity * (target_fill_price - mark_price)
            - target_fill_price * quantity * maker_fee_rate
        )
    )
    current_net_reward_risk = (
        None
        if forward_stop_risk is None
        or forward_stop_risk <= 0
        or forward_target_reward is None
        else forward_target_reward / forward_stop_risk
    )

    holding_seconds: float | None = None
    opened_at = lot.get("opened_at")
    end_at = lot.get("closed_at") or snapshot_at
    if isinstance(opened_at, str) and isinstance(end_at, str):
        holding_seconds = max(
            0.0,
            (_parse_utc(end_at) - _parse_utc(opened_at)).total_seconds(),
        )

    return {
        "lot_id": lot.get("lot_id"),
        "symbol": lot.get("symbol"),
        "side": lot.get("side"),
        "status": lot.get("status"),
        "origin": lot.get("origin"),
        "attribution": lot.get("attribution"),
        "hypothesis_id": lot.get("hypothesis_id"),
        "opened_at": lot.get("opened_at"),
        "closed_at": lot.get("closed_at"),
        "holding_seconds": _round_number(holding_seconds, 3),
        "entry_price": _round_number(entry_price),
        "mark_price": _round_number(mark_price),
        "initial_quantity_base": _round_number(initial_quantity, 12),
        "remaining_quantity_base": _round_number(quantity, 12),
        "entry_notional_usdt": _round_number(entry_notional),
        "remaining_entry_notional_usdt": _round_number(current_entry_notional),
        "current_position_value_usdt": _round_number(current_notional),
        "unrealized_price_pnl_usdt": _round_number(unrealized),
        "price_return_pct": _round_number(price_return_pct, 6),
        "gross_realized_pnl_usdt": _round_number(
            _number(lot.get("realized_pnl_usdt")) or 0.0
        ),
        "net_realized_pnl_usdt": _round_number(net_realized),
        "cumulative_net_pnl_usdt": _round_number(cumulative_net_pnl),
        "cumulative_net_return_pct": _round_number(
            cumulative_net_return_pct, 6
        ),
        "entry_fee_usdt": _round_number(
            _number(lot.get("entry_fee_usdt")) or 0.0
        ),
        "remaining_entry_fee_usdt": _round_number(remaining_entry_fee),
        "exit_fees_usdt": _round_number(
            _number(lot.get("exit_fees_usdt")) or 0.0
        ),
        "mfe_usdt": _round_number(_number(lot.get("mfe_usdt")) or 0.0),
        "mae_usdt": _round_number(_number(lot.get("mae_usdt")) or 0.0),
        "stop_trigger_price": _round_number(stop_price),
        "estimated_stop_fill_price": _round_number(stop_fill_price),
        "stop_protected_quantity_base": _round_number(stop_quantity, 12),
        "stop_protected_notional_usdt": _round_number(stop_notional),
        "stop_net_pnl_from_entry_usdt": _round_number(
            stop_net_pnl_from_entry
        ),
        "target_trigger_price": _round_number(target_price),
        "estimated_target_fill_price": _round_number(target_fill_price),
        "target_protected_quantity_base": _round_number(target_quantity, 12),
        "target_protected_notional_usdt": _round_number(target_notional),
        "target_net_pnl_from_entry_usdt": _round_number(
            target_net_pnl_from_entry
        ),
        "forward_open_risk_usdt": _round_number(forward_stop_risk),
        "forward_target_reward_usdt": _round_number(forward_target_reward),
        "current_net_reward_risk": _round_number(
            current_net_reward_risk, 6
        ),
        "initial_net_risk_usdt": _round_number(
            _number(lot.get("initial_net_risk_usdt"))
        ),
        "protection_activated_at": lot.get("protection_activated_at"),
        "risk_authorization": lot.get("risk_authorization"),
    }


def _read_ledger_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TheoryPaperError(f"cannot read ledger: {path}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TheoryPaperError(
                f"ledger line {line_number} is not valid JSON"
            ) from exc
        if not isinstance(item, dict):
            raise TheoryPaperError(f"ledger line {line_number} is not an object")
        events.append(item)
    return events


def _artifact_bundle(root: Path, cycle_id: str) -> dict[str, Any]:
    match = CYCLE_PATTERN.fullmatch(cycle_id)
    if match is None:
        raise TheoryPaperError(f"invalid cycle id: {cycle_id}")

    cycle_dir = root / "cycles" / cycle_id
    paths = {
        "manifest": root / "manifest.json",
        "config": root / "config.json",
        "analysis": cycle_dir / "analysis.json",
        "decision": cycle_dir / "decision.json",
        "market": cycle_dir / "market.json",
        "news": cycle_dir / "news.json",
        "market_execution": cycle_dir / "market-execution.json",
        "chaos_execution": cycle_dir / "chaos-execution.json",
        "analysis_commit": root / "transactions" / f"{cycle_id}-analysis.commit.json",
        "decision_prepare": root / "transactions" / f"{cycle_id}-decision.prepare.json",
        "decision_commit": root / "transactions" / f"{cycle_id}-decision.commit.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise TheoryPaperError(
            "cannot render an uncommitted or incomplete cycle: " + ", ".join(missing)
        )

    values = {name: read_json(path) for name, path in paths.items()}
    analysis = values["analysis"]
    decision = values["decision"]
    normalized = decision.get("validated_decision", {})
    if analysis.get("cycle_id") != cycle_id:
        raise TheoryPaperError("analysis cycle id mismatch")
    if decision.get("cycle_id") != cycle_id:
        raise TheoryPaperError("decision receipt cycle id mismatch")
    if not isinstance(normalized, dict) or normalized.get("cycle_id") != cycle_id:
        raise TheoryPaperError("normalized decision cycle id mismatch")

    for commit_name in ("analysis_commit", "decision_commit"):
        commit = values[commit_name]
        artifact_digests = commit.get("artifact_digests")
        if not isinstance(artifact_digests, dict):
            raise TheoryPaperError(f"{commit_name} has no artifact digest map")
        for relative_path, expected_digest in artifact_digests.items():
            artifact_path = root / relative_path
            if not artifact_path.is_file():
                raise TheoryPaperError(
                    f"committed artifact is missing: {relative_path}"
                )
            actual_digest = digest_json(read_json(artifact_path))
            if actual_digest != expected_digest:
                raise TheoryPaperError(
                    f"committed artifact digest mismatch: {relative_path}"
                )

    ledger_status = verify_ledger(root)
    if not ledger_status.get("valid"):
        raise TheoryPaperError("experiment ledger is invalid")
    ledger_events = _read_ledger_events(root / "ledger.ndjson")
    decision_events = [
        event
        for event in ledger_events
        if event.get("event_type") == "AGENT_DECISION_APPLIED"
        and event.get("payload", {}).get("cycle_id") == cycle_id
    ]
    if len(decision_events) != 1:
        raise TheoryPaperError(
            f"expected one committed decision ledger event for {cycle_id}"
        )

    values["paths"] = paths
    values["decision_event"] = decision_events[0]
    values["cycle_number"] = int(match.group(1))
    return values


def _render_theory_sources(manifest: Mapping[str, Any]) -> list[str]:
    lines = [
        "## 理论依据及来源",
        "",
        "### 本轮冻结的本地权威文件",
        "",
        "| 文件 | SHA-256 | 字节数 |",
        "|---|---|---:|",
    ]
    for binding in manifest.get("authority_bindings", []):
        lines.append(
            "| `{}` | `{}` | {} |".format(
                _cell(binding.get("path")),
                _cell(binding.get("sha256")),
                _cell(binding.get("size_bytes")),
            )
        )

    lines.extend(
        [
            "",
            "### 决策环节到理论章节的映射",
            "",
            "| 决策环节 | 本地来源 | 本轮使用边界 |",
            "|---|---|---|",
        ]
    )
    for step, source, boundary in THEORY_SOURCE_MAP:
        lines.append(
            f"| {_cell(step)} | {_cell(source)} | {_cell(boundary)} |"
        )

    lines.extend(
        [
            "",
            "### 公开学术与市场数据来源",
            "",
            "| 来源 | 本轮可支持的内容与限制 |",
            "|---|---|",
        ]
    )
    for title, url, boundary in ACADEMIC_SOURCE_MAP:
        lines.append(f"| [{_cell(title)}]({url}) | {_cell(boundary)} |")
    lines.extend(
        [
            "",
            "市场原始输入来自 Binance USDⓈ-M 公共市场接口；接口语义入口见 "
            "[Binance USDⓈ-M Futures Market Data API]"
            "(https://developers.binance.com/en/docs/catalog/"
            "core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/"
            "market-data)。新闻为冻结的公开发现元数据，除非另有一手核验，"
            "不作为方向因果真值。",
            "",
            "上述来源只支撑方法接口、测量语义和认识论边界；"
            "不证明本轮市场解释为真、策略具有正期望、或可用于真实交易。",
        ]
    )
    return lines


def _render_symbol(
    analysis_symbol: Mapping[str, Any],
    decision_symbol: Mapping[str, Any],
) -> list[str]:
    symbol = str(analysis_symbol.get("symbol", decision_symbol.get("symbol", "UNKNOWN")))
    measurement = analysis_symbol.get("measurement_snapshot", {})
    axes = measurement.get("axes", {})
    quality = measurement.get("data_quality", {})
    multiscale = analysis_symbol.get("multi_scale_state_belief", {})
    structure = analysis_symbol.get("structural_position", {})
    competition = analysis_symbol.get("phi_competition", {})
    news = analysis_symbol.get("news_context", {})

    lines = [
        f"## {symbol}：输入—规则—判断—动作",
        "",
        "### 1. 冻结事实与确定性测量",
        "",
        f"- 参考价格：`{_fmt(measurement.get('reference_price'))}`；"
        f"观测时间：{_time_pair(measurement.get('observed_at'))}。",
        f"- 数据覆盖率：`{_fmt(quality.get('coverage_ratio'))}`；"
        f"错误数：`{_fmt(quality.get('error_count'))}`；"
        f"严格流动性韧性可用：`{_fmt(quality.get('strict_resilience_available'))}`；"
        f"强平为零的确定性：`{_fmt(quality.get('liquidation_zero_certainty'))}`。",
        f"- 数据错误：{_fmt(quality.get('errors'))}。",
        f"- 原始来源摘要：`{_fmt(measurement.get('source_raw_digest'))}`；"
        f"测量对象：`{_fmt(measurement.get('measurement_snapshot_id'))}`。",
        "",
        "| 周期角色 | 方向 | 动量 | 参与度 | 波动 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    role_by_timeframe = {
        item.get("timeframe"): item for item in multiscale.get("role_states", [])
    }
    for timeframe in ("1w", "1d", "4h", "1h", "15m"):
        item = role_by_timeframe.get(timeframe, {})
        lines.append(
            "| {} / {} | {} | {} | {} | {} | {} |".format(
                timeframe,
                _cell(item.get("role")),
                _cell(item.get("direction_state")),
                _cell(item.get("momentum_state")),
                _cell(item.get("participation_state")),
                _cell(item.get("volatility_state")),
                _cell(item.get("state_status")),
            )
        )

    lines.extend(
        [
            "",
            "| 技术周期 | 全部冻结指标 |",
            "|---|---|",
        ]
    )
    timeframes = axes.get("K", {}).get("timeframes", {})
    for timeframe in ("1w", "1d", "4h", "1h", "15m"):
        item = timeframes.get(timeframe, {})
        lines.append(
            f"| {timeframe} / {_cell(item.get('status'))} | "
            f"{_cell(item.get('observations'))} |"
        )

    lines.extend(
        [
            "",
            "| 状态轴 | 状态 | 全部冻结观测 | 缺失字段 | 解释边界 |",
            "|---|---|---|---|---|",
        ]
    )
    for axis_id in ("D", "L", "C", "F", "R"):
        item = axes.get(axis_id, {})
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                AXIS_NAMES[axis_id],
                _cell(item.get("status")),
                _cell(item.get("observations")),
                _cell(item.get("missing_fields")),
                _cell(item.get("interpretation_boundary")),
            )
        )

    lines.extend(
        [
            "",
            "### 2. 结构位置与候选几何",
            "",
            f"- 结构对象：`{_fmt(structure.get('structural_position_id'))}`；"
            f"父级阶段：`{_fmt(structure.get('operational_phase'))}`；"
            f"位置阶段：`{_fmt(structure.get('location_stage'))}`；"
            f"扩张状态：`{_fmt(structure.get('expansion_state'))}`。",
            f"- 最近注册支撑：`{_fmt(structure.get('nearest_registered_support'))}`；"
            f"最近注册阻力：`{_fmt(structure.get('nearest_registered_resistance'))}`；"
            f"区间位置：`{_fmt(structure.get('normalized_range_location'))}`。",
            f"- 结构边界：{_fmt(structure.get('boundary'))}。",
            "",
            "| 几何 ID | 形态/方向 | 入场区 | 止损 | 止盈 | 成本后候选 RR | 状态 | 来源 |",
            "|---|---|---|---:|---:|---:|---|---|",
        ]
    )
    for candidate in analysis_symbol.get("action_geometry_candidates", []):
        zone = candidate.get("entry_zone", {})
        lines.append(
            "| `{}` | {} / {} | [{}, {}] | {} | {} | {} | {} | {} |".format(
                _cell(candidate.get("geometry_candidate_id")),
                _cell(candidate.get("setup_type")),
                _cell(candidate.get("side")),
                _cell(zone.get("low")),
                _cell(zone.get("high")),
                _cell(candidate.get("stop_loss")),
                _cell(candidate.get("take_profit")),
                _cell(candidate.get("reward_risk_at_entry_mid")),
                _cell(candidate.get("status")),
                _cell(candidate.get("geometry_source")),
            )
        )

    lines.extend(
        [
            "",
            "### 3. 完整竞争路径",
            "",
            f"- 竞争对象：`{_fmt(competition.get('phi_competition_id'))}`；"
            f"模式：`{_fmt(competition.get('competition_mode'))}`；"
            f"归一化规则：`{_fmt(competition.get('normalization_rule'))}`；"
            f"单一最高路径：`{_fmt(competition.get('single_top_path'))}`。",
            "",
            "| 路径 | 方向/序数支持 | 支持证据 | 冲突证据 | 未解决 | Hard falsifier | 到期 | 下一支持观测 |",
            "|---|---|---|---|---|---|---:|---|",
        ]
    )
    for hypothesis in competition.get("hypotheses", []):
        lines.append(
            "| `{}` {} | {} / {} | {} | {} | {} | {} | {}h | {} |".format(
                _cell(hypothesis.get("phi_id")),
                _cell(hypothesis.get("label")),
                _cell(hypothesis.get("direction")),
                _cell(hypothesis.get("support_ordinal")),
                _cell(hypothesis.get("evidence_for")),
                _cell(hypothesis.get("evidence_against")),
                _cell(hypothesis.get("unresolved")),
                _cell(hypothesis.get("hard_falsifiers")),
                _cell(hypothesis.get("expiry_hours")),
                _cell(hypothesis.get("next_observable_support")),
            )
        )

    lines.extend(
        [
            "",
            "### 4. Agent 可审计决策轨迹",
            "",
            f"- 市场解说：{_fmt(decision_symbol.get('analysis_narrative_zh'))}",
            f"- 行为假说及替代边界："
            f"{_fmt(decision_symbol.get('behavior_hypotheses_zh'))}",
            f"- 冻结 thesis：{_fmt(decision_symbol.get('thesis'))}",
            f"- 选择路径：`{_fmt(decision_symbol.get('selected_phi_id'))}`；"
            f"竞争路径：`{_fmt(decision_symbol.get('alternative_phi_ids'))}`。",
            f"- 支持谓词：`{_fmt(decision_symbol.get('support_predicate'))}`；"
            f"否证谓词：`{_fmt(decision_symbol.get('falsifier_predicate'))}`；"
            f"硬否证：{_fmt(decision_symbol.get('hard_falsifier'))}",
            f"- 未来力量路径：{_fmt(decision_symbol.get('future_force_path_zh'))}",
            f"- 下一观测：{_fmt(decision_symbol.get('next_observations'))}",
            f"- 到期：{_time_pair(decision_symbol.get('expiry_at'))}",
            f"- 行动：`{_fmt(decision_symbol.get('action'))}`；"
            f"执行意图：`{_fmt(decision_symbol.get('execution_intent'))}`；"
            f"可执行性：`{_fmt(decision_symbol.get('market_actionability'))}`；"
            f"不执行原因码：`{_fmt(decision_symbol.get('abstention_reason_code'))}`。",
            f"- 订单字段：`{_fmt(decision_symbol.get('order'))}`；"
            f"几何引用：`{_fmt(decision_symbol.get('geometry_candidate_id'))}`。",
            f"- 事实引用：`{_fmt(decision_symbol.get('fact_refs'))}`。",
            f"- 推断引用：`{_fmt(decision_symbol.get('inference_refs'))}`。",
            "",
            "### 5. 新闻与事件上下文",
            "",
            f"- 状态：`{_fmt(news.get('status'))}`；"
            f"边界：{_fmt(news.get('boundary'))}。",
        ]
    )
    headlines = news.get("headline_metadata", [])
    if headlines:
        lines.extend(
            [
                "",
                "| 标题 | 来源 | 发布时间 | 抓取时间 | 权威状态 |",
                "|---|---|---|---|---|",
            ]
        )
        for item in headlines:
            title = _cell(item.get("title"))
            url = item.get("url")
            title_cell = f"[{title}]({url})" if url else title
            lines.append(
                "| {} | {} | {} | {} | {} |".format(
                    title_cell,
                    _cell(item.get("source")),
                    _cell(item.get("published_at")),
                    _cell(item.get("retrieved_at")),
                    _cell(item.get("authority")),
                )
            )
    else:
        lines.extend(["", "本轮没有冻结到该标的的新闻发现项。"])
    return lines


def _render_standard_account(
    *,
    analysis: Mapping[str, Any],
    decision: Mapping[str, Any],
    decision_prepare: Mapping[str, Any],
) -> list[str]:
    portfolio = decision_prepare.get("post_state", {}).get("portfolio", {})
    if not isinstance(portfolio, Mapping):
        raise TheoryPaperError("decision transaction has no post-state portfolio")
    limits = portfolio.get("risk_limits", {})
    if not isinstance(limits, Mapping):
        raise TheoryPaperError("post-state portfolio has no risk limits")
    decided_at = decision.get("decided_at")
    if not isinstance(decided_at, str):
        raise TheoryPaperError("decision receipt has no decided_at timestamp")

    mark_prices: dict[str, float] = {}
    mark_times: dict[str, str] = {}
    for item in analysis.get("symbols", []):
        if not isinstance(item, Mapping):
            continue
        symbol = item.get("symbol")
        measurement = item.get("measurement_snapshot", {})
        if not isinstance(symbol, str) or not isinstance(measurement, Mapping):
            continue
        mark = _number(measurement.get("reference_price"))
        if mark is not None:
            mark_prices[symbol] = mark
        observed_at = measurement.get("observed_at")
        if isinstance(observed_at, str):
            mark_times[symbol] = observed_at

    lots = [
        item
        for item in portfolio.get("lots", [])
        if isinstance(item, Mapping)
    ]
    positions = [
        _standard_position_snapshot(
            lot,
            mark_price=mark_prices.get(str(lot.get("symbol"))),
            limits=limits,
            snapshot_at=decided_at,
        )
        for lot in lots
    ]
    open_positions = [
        item
        for item in positions
        if item.get("status") == "OPEN"
        and (_number(item.get("remaining_quantity_base")) or 0.0) > 0.0
    ]
    metrics = decision.get("portfolio_metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}
    initial_equity = _number(portfolio.get("initial_equity_usdt"))
    total_net_pnl = _number(metrics.get("total_net_pnl_usdt"))
    account_return_pct = (
        None
        if initial_equity is None
        or initial_equity <= 0
        or total_net_pnl is None
        else total_net_pnl / initial_equity * 100.0
    )
    calculated_unrealized_values = [
        _number(item.get("unrealized_price_pnl_usdt"))
        for item in open_positions
    ]
    calculated_unrealized = (
        None
        if any(value is None for value in calculated_unrealized_values)
        else sum(
            value
            for value in calculated_unrealized_values
            if value is not None
        )
    )
    metric_unrealized = _number(metrics.get("unrealized_pnl_usdt"))
    reconciliation_difference = (
        None
        if calculated_unrealized is None or metric_unrealized is None
        else calculated_unrealized - metric_unrealized
    )
    reconciliation_status = (
        "MATCH"
        if reconciliation_difference is not None
        and abs(reconciliation_difference) <= 1e-6
        else "UNKNOWN_OR_MISMATCH"
    )
    if (
        reconciliation_difference is not None
        and abs(reconciliation_difference) > 1e-6
    ):
        raise TheoryPaperError(
            "per-lot unrealized PnL does not reconcile to portfolio metrics"
        )

    lines = [
        "## 标准账户、当前持仓与历史交易信息（v2）",
        "",
        "### 账户总览",
        "",
        f"- 快照时间：{_time_pair(decided_at)}；账户模式："
        f"`{_fmt(portfolio.get('mode'))}`；纸面模式："
        f"`{_fmt(portfolio.get('paper_only'))}`。",
        f"- 名义口径：`{_fmt(portfolio.get('notional_interpretation'))}`；"
        "这是 1 倍 USDT 名义换算数量，不代表真实保证金或交易所杠杆。",
        "",
        "| 字段 | 数值 |",
        "|---|---:|",
        f"| 初始权益 | {_cell(initial_equity)} USDT |",
        f"| 当前权益 | {_cell(metrics.get('equity_usdt'))} USDT |",
        f"| 现金余额 | {_cell(metrics.get('cash_balance_usdt'))} USDT |",
        f"| 总净盈亏 | {_cell(total_net_pnl)} USDT |",
        f"| 账户累计收益率 | {_cell(_round_number(account_return_pct, 6))}% |",
        f"| 未实现价格盈亏 | {_cell(metrics.get('unrealized_pnl_usdt'))} USDT |",
        f"| 已实现毛盈亏 | {_cell(metrics.get('gross_realized_pnl_usdt'))} USDT |",
        f"| 已实现净盈亏 | {_cell(metrics.get('net_realized_pnl_usdt'))} USDT |",
        f"| 已付手续费 | {_cell(metrics.get('fees_paid_usdt'))} USDT |",
        f"| 当前持仓价值 | {_cell(metrics.get('gross_notional_usdt'))} USDT |",
        f"| 活跃挂单名义 | {_cell(metrics.get('pending_new_risk_notional_usdt'))} USDT |",
        f"| 总名义含挂单 | {_cell(metrics.get('gross_plus_pending_notional_usdt'))} USDT |",
        f"| 毛杠杆 | {_cell(metrics.get('gross_leverage'))}x |",
        f"| 当前回撤 | {_cell(_round_number((_number(metrics.get('drawdown_fraction')) or 0.0) * 100.0, 6))}% |",
        f"| 持仓开放风险 | {_cell(metrics.get('open_risk_usdt'))} USDT |",
        f"| 持仓加挂单开放风险 | {_cell(metrics.get('open_pending_risk_usdt'))} USDT |",
        f"| 成本价至止损损失口径 | {_cell(metrics.get('open_cost_to_stop_usdt'))} USDT |",
        f"| 资金费模拟状态 | {_cell(metrics.get('funding_accrual_status'))} |",
        "",
        "### 当前未平仓持仓",
        "",
    ]
    if open_positions:
        lines.extend(
            [
                "| Lot | 标的 | 方向 | 精确开仓时间 | 精确开仓价 | 标记价/时间 | 初始数量 | 剩余数量 | 入场名义 | 当前持仓价值 | 未实现盈亏 | 价格收益率 | 累计净盈亏/收益率 |",
                "|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for item in open_positions:
            symbol = str(item.get("symbol"))
            mark_time = mark_times.get(symbol)
            mark_display = (
                f"{_cell(item.get('mark_price'))} / {_cell(mark_time)}"
            )
            lines.append(
                "| `{}` | {} | {} | {} | {} | {} | {} | {} | {} USDT | {} USDT | {} USDT | {}% | {} USDT / {}% |".format(
                    _cell(item.get("lot_id")),
                    _cell(symbol),
                    _cell(item.get("side")),
                    _cell(item.get("opened_at")),
                    _cell(item.get("entry_price")),
                    mark_display,
                    _cell(item.get("initial_quantity_base")),
                    _cell(item.get("remaining_quantity_base")),
                    _cell(item.get("entry_notional_usdt")),
                    _cell(item.get("current_position_value_usdt")),
                    _cell(item.get("unrealized_price_pnl_usdt")),
                    _cell(item.get("price_return_pct")),
                    _cell(item.get("cumulative_net_pnl_usdt")),
                    _cell(item.get("cumulative_net_return_pct")),
                )
            )
    else:
        lines.append("当前没有未平仓持仓。")

    lines.extend(
        [
            "",
            "口径说明：未实现盈亏与运行时 `portfolio_metrics` 一致，"
            "按方向 × 剩余数量 ×（标记价−开仓价）计算，"
            "不预扣尚未发生的退出手续费；累计净盈亏另计入已实现净盈亏和"
            "尚未分摊的入场费。收益率不使用杠杆放大。",
            "",
            "### 止盈、止损与受保护数量",
            "",
        ]
    )
    protected_positions = [
        item
        for item in open_positions
        if item.get("stop_trigger_price") is not None
        or item.get("target_trigger_price") is not None
    ]
    if protected_positions:
        lines.extend(
            [
                "| Lot | 止损触发/预计成交 | 止损数量/触发名义 | 止损后预计净盈亏 | 止盈触发/预计成交 | 止盈数量/触发名义 | 止盈后预计净盈亏 | 当前开放风险/目标收益 | 当前净 RR |",
                "|---|---|---|---:|---|---|---:|---|---:|",
            ]
        )
        for item in protected_positions:
            lines.append(
                "| `{}` | {} / {} | {} / {} USDT | {} USDT | {} / {} | {} / {} USDT | {} USDT | {} / {} USDT | {} |".format(
                    _cell(item.get("lot_id")),
                    _cell(item.get("stop_trigger_price")),
                    _cell(item.get("estimated_stop_fill_price")),
                    _cell(item.get("stop_protected_quantity_base")),
                    _cell(item.get("stop_protected_notional_usdt")),
                    _cell(item.get("stop_net_pnl_from_entry_usdt")),
                    _cell(item.get("target_trigger_price")),
                    _cell(item.get("estimated_target_fill_price")),
                    _cell(item.get("target_protected_quantity_base")),
                    _cell(item.get("target_protected_notional_usdt")),
                    _cell(item.get("target_net_pnl_from_entry_usdt")),
                    _cell(item.get("forward_open_risk_usdt")),
                    _cell(item.get("forward_target_reward_usdt")),
                    _cell(item.get("current_net_reward_risk")),
                )
            )
        lines.extend(
            [
                "",
                "止盈/止损数量为该 lot 当前全部剩余基础资产数量；"
                "“触发名义”分别为数量 × 止盈或止损触发价。"
                "止损预计成交价计入冻结的止损滑点假设，"
                "止盈预计成交价按当前 maker 零滑点假设。",
            ]
        )
    else:
        lines.append("当前没有带止盈或止损的未平仓持仓。")

    lines.extend(
        [
            "",
            "### 持仓盈亏核对",
            "",
            f"- 逐 lot 重新计算的未实现盈亏："
            f"`{_fmt(_round_number(calculated_unrealized))}` USDT。",
            f"- 运行时组合未实现盈亏：`{_fmt(metric_unrealized)}` USDT。",
            f"- 差额：`{_fmt(_round_number(reconciliation_difference))}` USDT；"
            f"核对状态：`{reconciliation_status}`。",
            "",
            "### 完整 lot 历史",
            "",
            "| Lot | 标的/方向 | 状态 | 来源/归因/父假说 | 开仓/平仓时间 | 开仓价 | 初始/剩余数量 | 入场名义 | 毛/净已实现盈亏 | 手续费 | MFE/MAE | 持有秒数 |",
            "|---|---|---|---|---|---:|---|---:|---|---|---|---:|",
        ]
    )
    for item in positions:
        lines.append(
            "| `{}` | {} / {} | {} | {} / {} / {} | {} / {} | {} | {} / {} | {} USDT | {} / {} USDT | {} / {} / {} USDT | {} / {} USDT | {} |".format(
                _cell(item.get("lot_id")),
                _cell(item.get("symbol")),
                _cell(item.get("side")),
                _cell(item.get("status")),
                _cell(item.get("origin")),
                _cell(item.get("attribution")),
                _cell(item.get("hypothesis_id")),
                _cell(item.get("opened_at")),
                _cell(item.get("closed_at")),
                _cell(item.get("entry_price")),
                _cell(item.get("initial_quantity_base")),
                _cell(item.get("remaining_quantity_base")),
                _cell(item.get("entry_notional_usdt")),
                _cell(item.get("gross_realized_pnl_usdt")),
                _cell(item.get("net_realized_pnl_usdt")),
                _cell(item.get("entry_fee_usdt")),
                _cell(item.get("remaining_entry_fee_usdt")),
                _cell(item.get("exit_fees_usdt")),
                _cell(item.get("mfe_usdt")),
                _cell(item.get("mae_usdt")),
                _cell(item.get("holding_seconds")),
            )
        )

    orders = [
        item
        for item in portfolio.get("orders", [])
        if isinstance(item, Mapping)
    ]
    lines.extend(["", "### 完整订单历史", ""])
    if orders:
        lines.extend(
            [
                "| Order | 标的/方向/类型 | 状态 | 创建/激活/取消时间 | 限价 | 初始数量/剩余数量 | 初始名义/剩余名义 | Reduce-only | 止损/止盈 | 来源/归因/父假说 | 取消理由 |",
                "|---|---|---|---|---:|---|---|---|---|---|---|",
            ]
        )
        for order in orders:
            remaining_quantity = _number(order.get("remaining_quantity"))
            limit_price = _number(order.get("limit_price"))
            remaining_notional = (
                None
                if remaining_quantity is None or limit_price is None
                else remaining_quantity * limit_price
            )
            lines.append(
                "| `{}` | {} / {} / {} | {} | {} / {} / {} | {} | {} / {} | {} / {} USDT | {} | {} / {} | {} / {} / {} | {} |".format(
                    _cell(order.get("order_id")),
                    _cell(order.get("symbol")),
                    _cell(order.get("side")),
                    _cell(order.get("order_type")),
                    _cell(order.get("state")),
                    _cell(order.get("created_at")),
                    _cell(order.get("activated_at")),
                    _cell(order.get("canceled_at")),
                    _cell(order.get("limit_price")),
                    _cell(order.get("quantity")),
                    _cell(order.get("remaining_quantity")),
                    _cell(order.get("notional_usdt")),
                    _cell(_round_number(remaining_notional)),
                    _cell(order.get("reduce_only")),
                    _cell(order.get("stop_price")),
                    _cell(order.get("target_price")),
                    _cell(order.get("origin")),
                    _cell(order.get("attribution")),
                    _cell(order.get("hypothesis_id")),
                    _cell(order.get("cancel_reason")),
                )
            )
    else:
        lines.append("截至本轮提交时间，订单历史为空。")

    fills = [
        item
        for item in portfolio.get("fills", [])
        if isinstance(item, Mapping)
    ]
    lines.extend(["", "### 完整成交历史", ""])
    if fills:
        lines.extend(
            [
                "| Fill | 时间 | 标的/方向 | 数量/价格/名义 | 手续费 | 滑点假设/成本 | 原因 | 来源/归因/父假说 | 订单/新 lot | 平仓明细 | 歧义/拒绝超额 |",
                "|---|---|---|---|---:|---|---|---|---|---|---|",
            ]
        )
        for fill in fills:
            lines.append(
                "| `{}` | {} | {} / {} | {} / {} / {} USDT | {} USDT | {} bps / {} USDT | {} | {} / {} / {} | {} / {} | {} | {} / {} |".format(
                    _cell(fill.get("fill_id")),
                    _cell(fill.get("observed_at")),
                    _cell(fill.get("symbol")),
                    _cell(fill.get("side")),
                    _cell(fill.get("quantity")),
                    _cell(fill.get("price")),
                    _cell(fill.get("notional_usdt")),
                    _cell(fill.get("fee_usdt")),
                    _cell(fill.get("slippage_bps_assumption")),
                    _cell(fill.get("estimated_slippage_cost_usdt")),
                    _cell(fill.get("reason")),
                    _cell(fill.get("origin")),
                    _cell(fill.get("attribution")),
                    _cell(fill.get("hypothesis_id")),
                    _cell(fill.get("order_id")),
                    _cell(fill.get("opened_lot_id")),
                    _cell(fill.get("closed_lots")),
                    _cell(fill.get("ambiguous_same_bar")),
                    _cell(fill.get("rejected_excess_quantity")),
                )
            )
    else:
        lines.extend(
            [
                "截至本轮提交时间，`fills=[]`，没有由 Agent1 或纸面撮合产生的成交记录。",
                "五个仓位是用户提供的初始外生持仓，因此有精确开仓价和数量，"
                "但没有伪造对应的历史成交回执。",
            ]
        )

    lines.extend(
        [
            "",
            "### 原始账户对象附录",
            "",
            "以下对象来自本轮不可变的 decision prepare 后态，"
            "用于保留表格未展开的授权、归因和内部状态字段。",
            "",
            "#### Lots 原始对象",
            "",
        ]
    )
    lines.extend(_json_block(portfolio.get("lots", [])))
    lines.extend(["", "#### Orders 原始对象", ""])
    lines.extend(_json_block(portfolio.get("orders", [])))
    lines.extend(["", "#### Fills 原始对象", ""])
    lines.extend(_json_block(portfolio.get("fills", [])))
    return lines


def _render_execution(
    normalized: Mapping[str, Any],
    decision: Mapping[str, Any],
    decision_prepare: Mapping[str, Any],
    market_execution: Mapping[str, Any],
    chaos_execution: Mapping[str, Any],
    *,
    legacy_initial_metric_labels: bool,
    legacy_strategy_fill_label: bool,
) -> list[str]:
    actions = normalized.get("actions", [])
    results = decision.get("execution", {}).get("results", [])
    result_by_index = {
        item.get("index"): item for item in results if isinstance(item, dict)
    }
    portfolio = decision_prepare.get("post_state", {}).get("portfolio", {})
    lots = {item.get("lot_id"): item for item in portfolio.get("lots", [])}
    orders = {item.get("order_id"): item for item in portfolio.get("orders", [])}

    lines = [
        "## 具体执行记录",
        "",
        "### 盘中撮合与外生扰动",
        "",
        f"- 在本轮决策前由既有止损、止盈或已激活订单产生的成交："
        f"`{len(market_execution.get('fills', []))}` 笔。",
        f"- 盘中撮合跳过项：`{_fmt(market_execution.get('skipped'))}`。",
        f"- 自动/手工情绪扰动结果：`{_fmt(chaos_execution.get('results'))}`。",
        "",
        "### Agent 提交动作及回执",
        "",
        "| 序号 | 动作 | 对象 | 具体参数/原因 | 执行回执 |",
        "|---:|---|---|---|---|",
    ]
    for index, action in enumerate(actions):
        object_id = action.get("lot_id") or action.get("order_id") or action.get("symbol")
        detail = {
            key: value
            for key, value in action.items()
            if key not in {"type", "lot_id", "order_id", "symbol"}
        }
        receipt = result_by_index.get(index, {})
        lines.append(
            f"| {index + 1} | {_cell(action.get('type'))} | "
            f"`{_cell(object_id)}` | {_cell(detail)} | {_cell(receipt)} |"
        )

    protected_ids = [
        action.get("lot_id")
        for action in actions
        if action.get("type") == "UPDATE_PROTECTION"
    ]
    if protected_ids:
        metric_headers = (
            "成本后净 RR | 开放净风险"
            if legacy_initial_metric_labels
            else "初始成本后净 RR | 初始净风险"
        )
        lines.extend(
            [
                "",
                "### 保护后的持仓",
                "",
                "| Lot | 标的/方向 | 初始入场/名义 | 止损/止盈 | "
                f"{metric_headers} | 保护时间 | 来源归因 |",
                "|---|---|---|---|---:|---:|---|---|",
            ]
        )
        for lot_id in protected_ids:
            lot = lots.get(lot_id, {})
            lines.append(
                "| `{}` | {} / {} | {} / {} USDT | {} / {} | {} | {} USDT | {} | {} / {} |".format(
                    _cell(lot_id),
                    _cell(lot.get("symbol")),
                    _cell(lot.get("side")),
                    _cell(lot.get("entry_price")),
                    _cell(lot.get("entry_notional_usdt")),
                    _cell(lot.get("stop_price")),
                    _cell(lot.get("target_price")),
                    _cell(lot.get("entry_reward_risk_net")),
                    _cell(lot.get("initial_net_risk_usdt")),
                    _cell(lot.get("protection_activated_at")),
                    _cell(lot.get("origin")),
                    _cell(lot.get("attribution")),
                )
            )
        if not legacy_initial_metric_labels:
            lines.extend(
                [
                    "",
                    "此处净 RR 与净风险是 lot 入场时冻结的初始风险基准，"
                    "不会因后续止损更新而改写；当前标记价至止损的开放风险、"
                    "目标收益及当前净 RR 以上方“止盈、止损与受保护数量”表为准。",
                ]
            )

    canceled_ids = [
        action.get("order_id")
        for action in actions
        if action.get("type") == "CANCEL_ORDER"
    ]
    if canceled_ids:
        lines.extend(
            [
                "",
                "### 逐笔审查并取消的挂单",
                "",
                "| Order | 标的/方向 | 价格 | 名义 USDT | 状态/时间 | 取消理由 |",
                "|---|---|---:|---:|---|---|",
            ]
        )
        for order_id in canceled_ids:
            order = orders.get(order_id, {})
            lines.append(
                "| `{}` | {} / {} | {} | {} | {} / {} | {} |".format(
                    _cell(order_id),
                    _cell(order.get("symbol")),
                    _cell(order.get("side")),
                    _cell(order.get("limit_price")),
                    _cell(order.get("notional_usdt")),
                    _cell(order.get("state")),
                    _cell(order.get("canceled_at")),
                    _cell(order.get("cancel_reason")),
                )
            )

    strategy_fill_label = (
        "策略新开风险成交数"
        if legacy_strategy_fill_label
        else "策略成交数（含开仓、减仓和平仓）"
    )
    lines.extend(
        [
            "",
            "### 组合结果（提交后）",
            "",
            f"- {strategy_fill_label}：`"
            f"{_fmt(decision.get('execution', {}).get('strategy_fill_count'))}`。",
            f"- 执行结果总数：`{len(results)}`；"
            f"验证警告：`{_fmt(decision.get('validation_warnings'))}`。",
            "",
        ]
    )
    lines.extend(_json_block(decision.get("portfolio_metrics", {})))
    return lines


def render_cycle_record(root: Path, cycle_id: str) -> tuple[str, str]:
    bundle = _artifact_bundle(root, cycle_id)
    manifest = bundle["manifest"]
    analysis = bundle["analysis"]
    decision = bundle["decision"]
    normalized = decision["validated_decision"]
    decision_event = bundle["decision_event"]
    cycle_number = bundle["cycle_number"]
    decided_at = decision.get("decided_at")
    if not isinstance(decided_at, str):
        raise TheoryPaperError("decision receipt has no decided_at timestamp")

    lines = [
        f"# Agent{cycle_number} / 第 {cycle_number} 轮纸面交易完整执行、持仓与决策依据 v2",
        "",
        f"- 运行 ID：`{_fmt(manifest.get('run_id'))}`",
        f"- 周期 ID：`{cycle_id}`",
        "- 中文记录 schema：`theory-paper-zh-audit-record.v2`",
        f"- 分析冻结时间：{_time_pair(analysis.get('decision_at'))}",
        f"- 执行提交时间：{_time_pair(decided_at)}",
        f"- 执行范围：`{_fmt(normalized.get('execution_scope'))}`；"
        f"纸面模式：`{_fmt(decision.get('paper_only'))}`",
        f"- 决策 Agent：`{_fmt(normalized.get('agent_identity'))}`",
        f"- 账本序号：`{_fmt(decision_event.get('sequence'))}`；"
        f"事件摘要：`{_fmt(decision_event.get('event_digest'))}`",
        "",
        "> 本文记录的是可复核的决策轨迹：冻结输入、确定性测量、竞争假说、"
        "支持/否证条件、行动几何、风险门、实际动作和执行回执。"
        "它不包含也不伪造模型私有的逐 token 隐藏思维；"
        "未写入冻结工件的理由一律不视为可追溯依据。",
        "",
        "## 结论",
        "",
        _fmt(normalized.get("executive_summary_zh")),
        "",
        "## 组合决策理由",
        "",
        _fmt(normalized.get("portfolio_rationale_zh")),
        "",
        "## 决策规则链",
        "",
        "1. 冻结同一决策时点前可得的公共行情、闭合 K 线和新闻元数据。",
        "2. 将事实、确定性测量、行为推断与未知项分层；缺失不补零。",
        "3. 依次形成多尺度状态、结构位置、有限竞争路径及下一支持/否证观测。",
        "4. 将研究就绪几何与当前价格、触发条件、成本后 RR 和组合风险门逐项核对。",
        "5. 只有触发且全部风险条件通过才新增纸面风险；否则给出类型化不执行理由。",
        "6. 独立处理既有仓位、挂单和外生情绪单，记录实际回执及提交后组合状态。",
        "",
        f"- 编排门：`{_fmt(normalized.get('orchestration_gate'))}`。",
        f"- Agent 声明：`{_fmt(normalized.get('agent_attestation'))}`。",
        "",
        "## 方法执行观察",
        "",
    ]
    for item in normalized.get("method_observations", []):
        lines.append(f"- {_fmt(item)}")

    lines.extend([""])
    lines.extend(
        _render_standard_account(
            analysis=analysis,
            decision=decision,
            decision_prepare=bundle["decision_prepare"],
        )
    )
    lines.extend([""])
    lines.extend(_render_theory_sources(manifest))

    analysis_symbols = {
        item.get("symbol"): item for item in analysis.get("symbols", [])
    }
    decision_symbols = {
        item.get("symbol"): item for item in normalized.get("symbol_decisions", [])
    }
    symbol_order = manifest.get("symbols", list(analysis_symbols))
    for symbol in symbol_order:
        if symbol not in analysis_symbols or symbol not in decision_symbols:
            raise TheoryPaperError(f"incomplete symbol decision record: {symbol}")
        lines.extend([""])
        lines.extend(_render_symbol(analysis_symbols[symbol], decision_symbols[symbol]))

    lines.extend([""])
    lines.extend(
        _render_execution(
            normalized,
            decision,
            bundle["decision_prepare"],
            bundle["market_execution"],
            bundle["chaos_execution"],
            legacy_initial_metric_labels=(
                _parse_utc(decided_at)
                <= _parse_utc(LEGACY_EXECUTION_LABEL_CUTOFF)
            ),
            legacy_strategy_fill_label=(
                _parse_utc(decided_at)
                <= _parse_utc(LEGACY_STRATEGY_FILL_LABEL_CUTOFF)
            ),
        )
    )

    paths: Mapping[str, Path] = bundle["paths"]
    lines.extend(
        [
            "",
            "## 审计与原始工件",
            "",
            "| 工件 | 文件 SHA-256 | 事务绑定摘要 |",
            "|---|---|---|",
        ]
    )
    analysis_digests = bundle["analysis_commit"].get("artifact_digests", {})
    decision_digests = bundle["decision_commit"].get("artifact_digests", {})
    for name in (
        "manifest",
        "config",
        "market",
        "news",
        "market_execution",
        "chaos_execution",
        "analysis",
        "decision",
        "analysis_commit",
        "decision_prepare",
        "decision_commit",
    ):
        path = paths[name]
        relative = path.relative_to(root)
        committed = analysis_digests.get(str(relative)) or decision_digests.get(
            str(relative)
        )
        lines.append(
            f"| `{relative}` | `{_file_sha256(path)}` | "
            f"`{_fmt(committed)}` |"
        )

    lines.extend(
        [
            "",
            f"- 分析事务：`{_fmt(bundle['analysis_commit'])}`。",
            f"- 决策事务：`{_fmt(bundle['decision_commit'])}`。",
            f"- 决策账本事件：`{_fmt(decision_event)}`。",
            "",
            "完整原始行情与 K 线保留在上述 `market.json` 中；"
            "本文不复制约 1MB 的逐根原始数组，而以文件 SHA-256、"
            "事务绑定摘要和决策所用全部测量值建立可复核引用。",
            "",
            "## 使用边界",
            "",
            "- 本轮没有真实交易所订单、私有账户访问、API 密钥或资金操作。",
            "- 初始持仓属于外生条件，不能追溯归因于本理论；本轮只评价其后续风险管理。",
            "- 72 小时纸面结果只能作为描述性实践证据，不能证明因果、预测有效性或持续盈利。",
        ]
    )
    text = "\n".join(lines).rstrip() + "\n"
    filename = (
        f"{_filename_time(decided_at)}_{cycle_id}_agent{cycle_number}_zh_v2.md"
    )
    return filename, text


def write_cycle_record(
    root: Path,
    cycle_id: str,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    filename, text = render_cycle_record(root, cycle_id)
    directory = (
        Path(output_dir).resolve()
        if output_dir is not None
        else root / "reports" / "zh"
    )
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / filename
    payload = text.encode("utf-8")

    if target.exists():
        existing = target.read_bytes()
        if existing != payload:
            raise TheoryPaperError(
                f"write-once Chinese record differs from regenerated content: {target}"
            )
        status = "EXISTING_IDENTICAL"
    else:
        try:
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as exc:
            raise TheoryPaperError(
                f"Chinese record appeared concurrently: {target}"
            ) from exc
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        status = "CREATED"

    return {
        "cycle_id": cycle_id,
        "path": str(target),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "status": status,
    }


def committed_cycle_ids(root: Path) -> list[str]:
    cycles: list[str] = []
    for path in sorted((Path(root) / "cycles").glob("cycle-*/decision.json")):
        cycle_id = path.parent.name
        if CYCLE_PATTERN.fullmatch(cycle_id):
            commit = Path(root) / "transactions" / f"{cycle_id}-decision.commit.json"
            if commit.is_file():
                cycles.append(cycle_id)
    return cycles


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成已提交纸面交易周期的中文完整执行与决策依据文档"
    )
    parser.add_argument("--run-dir", required=True)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--cycle", help="例如 cycle-0001；省略时使用最新周期")
    selector.add_argument(
        "--all",
        action="store_true",
        help="补齐并校验全部已提交周期",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="默认写入 RUN_DIR/reports/zh",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = Path(args.run_dir).resolve()
    cycles = committed_cycle_ids(root)
    if args.all:
        selected = cycles
    elif args.cycle:
        selected = [args.cycle]
    elif cycles:
        selected = [cycles[-1]]
    else:
        raise TheoryPaperError("no committed decision cycles are available")
    if not selected:
        raise TheoryPaperError("no committed decision cycles are available")

    output_dir = Path(args.output_dir) if args.output_dir else None
    results = [
        write_cycle_record(root, cycle_id, output_dir=output_dir)
        for cycle_id in selected
    ]
    print(
        json.dumps(
            {
                "record_count": len(results),
                "records": results,
                "schema_version": "theory-paper-zh-audit-record.v2",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
