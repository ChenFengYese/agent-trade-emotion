"""Write-once, non-authoritative first-round reports."""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from ..application.round1_run import FrozenRound1RunResult
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    self_digest,
    write_once_json,
)


class PresentationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MaterializedRound1Report:
    run_root: Path
    artifact_index_path: Path
    markdown_path: Path
    artifact_index_digest: str


def _artifact(
    artifact_type: str,
    value: Mapping[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_type": artifact_type,
        "artifact_version": "1.0.0",
        "value": dict(value),
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    payload["artifact_digest"] = canonical_digest(payload)
    return payload


def _generic_record(
    *,
    schema_id: str,
    record_id: str,
    value_refs: tuple[str, ...],
) -> dict[str, object]:
    return self_digest(
        {
            "schema_id": schema_id,
            "schema_version": "1.0.0",
            "record_id": record_id,
            "revision": 1,
            "value_refs": list(value_refs),
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "record_digest",
    )


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def build_round1_markdown_zh(result: FrozenRound1RunResult) -> str:
    evaluation = result.evaluation
    accounting = evaluation.a_observed
    lines = [
        "# Theory Agent V2 第一轮冻结回测报告",
        "",
        "## 结论",
        "",
        (
            f"- 终局：`{evaluation.terminal_status}`；"
            f"第二轮授权：`{str(result.round2_authorized).lower()}`。"
        ),
        (
            f"- 工程功能闸门：`{evaluation.hard_functional_gate_status}`；"
            f"行为与经济闸门：`{evaluation.behavior_economic_gate_status}`。"
        ),
        (
            f"- 规范场景：{result.scenario_report.pass_count}/32 PASS，"
            f"{result.scenario_report.fail_count} FAIL，"
            f"{result.scenario_report.unknown_count} UNKNOWN。"
        ),
        (
            "- Agent 拓扑："
            f"`{result.topology_evaluation.selection_status}`，"
            f"运行拓扑回退为 `{result.topology_evaluation.selected_topology_id}`；"
            "没有把集群形式本身当作能力提升证据。"
        ),
        (
            "- A 组历史账本与动作/成交可精确复算；B–I 所需的持久战略"
            "状态、CORE/TACTICAL 角色、重入合同、动态几何和完整候选"
            "提案流在 V1 中不存在，因此不得用事后构造填补。"
        ),
        "",
        "## 权限与证据边界",
        "",
        "- 模式：`E0_OFFLINE_COUNTERFACTUAL`。",
        "- 外部执行权：`NONE_E0`；`executable=false`。",
        (
            "- V1 源树运行前后摘要相同："
            f"`{result.source_tree_digest_before}`。"
        ),
        "- 本报告未修改 V1、理论、阈值、仓位、历史输出或 automation-2。",
        "",
        "## A 组已识别收益账本",
        "",
        "| 项目 | 数值 |",
        "|---|---:|",
        f"| 初始权益 | {_cell(accounting.initial_equity)} USDT |",
        f"| 期末现金 | {_cell(accounting.cash_balance)} USDT |",
        f"| 已实现毛盈亏 | {_cell(accounting.realized_pnl_gross)} USDT |",
        f"| 手续费 | {_cell(accounting.fees)} USDT |",
        f"| 已实现净盈亏 | {_cell(accounting.net_realized_pnl)} USDT |",
        f"| 未实现盈亏 | {_cell(accounting.unrealized_pnl)} USDT |",
        f"| 总净盈亏 | {_cell(accounting.total_net_pnl)} USDT |",
        f"| 最大回撤比例 | {_cell(accounting.max_drawdown_fraction)} |",
        f"| 成交数 | {accounting.fill_count} |",
        f"| 资金费 | {_cell(accounting.funding_status)} |",
        "",
        "## A–I 消融识别结果",
        "",
        "| Arm | 功能状态 | 经济状态 | 已识别缺口 |",
        "|---|---|---|---|",
    ]
    for arm in evaluation.arms:
        lines.append(
            f"| {arm.arm_id} | {_cell(arm.functional_status)} | "
            f"{_cell(arm.economic_status)} | "
            f"{_cell(', '.join(arm.unknown_fields) or '无')} |"
        )
    lines.extend(
        [
            "",
            "九个 arm 使用同一 point-in-time bundle、同一成本政策和同一"
            "事件时间顺序。由于完整候选提案流不可识别，B–I 没有被另行"
            "生成有利提案。",
            "",
            "## 三条冻结反事实",
            "",
            "| 政策 | 可识别性 | 结果状态 | 期末标记净盈亏 | 假设退出净盈亏 |",
            "|---|---|---|---:|---:|",
        ]
    )
    for item in evaluation.counterfactuals:
        lines.append(
            f"| {_cell(item.policy_id)} | {_cell(item.identifiability)} | "
            f"{_cell(item.result_status)} | "
            f"{_cell(item.terminal_mark_net_pnl)} | "
            f"{_cell(item.hypothetical_exit_net_pnl)} |"
        )
    lines.extend(
        [
            "",
            "SNDK 战略持有路径只是敏感性分析，不是 V1 当时已冻结的规则；"
            "TACTICAL_REDUCTION_ONLY 的战术比例 alpha 未注册，因此只能"
            "保留参数式区间。机会差额不计入实际现金亏损。",
            "",
            "## 单 Agent 与三角色集群",
            "",
            (
                f"- 完整配对会话："
                f"{result.topology_evaluation.observed_complete_paired_sessions}/"
                f"{result.topology_evaluation.minimum_paired_sessions}。"
            ),
            (
                f"- 等输入、模型和预算核验："
                f"`{str(result.topology_evaluation.equal_input_model_budget_verified).lower()}`。"
            ),
            (
                f"- 选择状态：`{result.topology_evaluation.selection_status}`；"
                f"当前使用：`{result.topology_evaluation.selected_topology_id}`。"
            ),
            (
                "- 当前没有 32 组真实、等预算、成对 Agent 输出，因此按冻结"
                "政策回退强单 Agent；这不证明集群更差。"
            ),
            "",
            "## 32 个规范场景证据索引",
            "",
            "| 场景 | 队列 | 谓词 | 观察结果 | 结果码 | 状态 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in result.scenario_report.results:
        lines.append(
            f"| {_cell(item.scenario_id)} {_cell(item.title)} | "
            f"{_cell(item.cohort_id)} | {_cell(item.predicate_id)} | "
            f"{_cell(item.observed_outcome)} | {_cell(item.observed_code)} | "
            f"{_cell(item.status)} |"
        )
    lines.extend(
        [
            "",
            "## 未通过第二轮的原因",
            "",
        ]
    )
    lines.extend(
        f"- `{code}`" for code in evaluation.terminal_reason_codes
    )
    lines.extend(
        [
            "",
            "## 裁决边界",
            "",
            "- 32/32 场景通过仅证明当前实现满足这些合成状态与风险不变量。",
            "- 第一轮只确认 A 组历史行为可复算，不能确认 B–I 的经济改进。",
            "- 不能据此声称预测有效、概率已校准、正期望、稳定盈利、"
            "paper-ready、live-ready 或获得自动交易权限。",
            "- 因经济闸门不可识别，第二轮独立纸面实验和 101% 外生初始"
            "成本设置均未创建。",
            "",
            f"运行结果摘要：`{result.run_result_digest}`",
            f"场景报告摘要：`{result.scenario_report.report_digest}`",
            f"第一轮评估摘要：`{evaluation.result_digest}`",
            "",
        ]
    )
    return "\n".join(lines)


def _write_once_text(path: Path, text: str) -> None:
    payload = text.encode("utf-8")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or target.read_bytes() != payload:
            raise PresentationError(f"WRITE_ONCE_CONFLICT:{target}")
        return
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        if target.is_file() and target.read_bytes() == payload:
            return
        raise PresentationError(f"WRITE_ONCE_RACE:{target}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def materialize_round1_report(
    *,
    runtime_root: Path,
    offline_run_id: str,
    result: FrozenRound1RunResult,
) -> MaterializedRound1Report:
    if offline_run_id in {"current", "latest"}:
        raise PresentationError("EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED")
    run_root = Path(runtime_root).resolve() / offline_run_id
    manifest = load_json_strict(run_root / "manifest.json")
    if (
        manifest.get("manifest_id") != offline_run_id
        or manifest.get("system_mode") != "E0_OFFLINE_COUNTERFACTUAL"
        or manifest.get("external_execution_authority") != "NONE_E0"
        or manifest.get("executable") is not False
    ):
        raise PresentationError("RUNTIME_MANIFEST_MISMATCH")

    artifacts = run_root / "artifacts"
    reports = run_root / "reports" / "zh"
    run_payload = _artifact("FROZEN_ROUND1_RUN_RESULT", asdict(result))
    scenario_payload = _artifact(
        "CANONICAL_SCENARIO_REPORT",
        asdict(result.scenario_report),
    )
    evaluation_payload = _artifact(
        "ROUND1_A_I_EVALUATION",
        asdict(result.evaluation),
    )
    topology_payload = _artifact(
        "AGENT_TOPOLOGY_EVALUATION",
        asdict(result.topology_evaluation),
    )
    hard_gate = _generic_record(
        schema_id="hard_gate_result",
        record_id=f"{offline_run_id}:hard-gate",
        value_refs=(
            (
                "functional-status:"
                f"{result.evaluation.hard_functional_gate_status}"
            ),
            (
                "behavior-economic-status:"
                f"{result.evaluation.behavior_economic_gate_status}"
            ),
            f"terminal-status:{result.evaluation.terminal_status}",
            f"round2-authorized:{str(result.round2_authorized).lower()}",
            *(
                f"reason-code:{code}"
                for code in result.evaluation.terminal_reason_codes
            ),
        ),
    )
    ablation = _generic_record(
        schema_id="ablation_result",
        record_id=f"{offline_run_id}:ablation",
        value_refs=tuple(
            (
                f"arm:{arm.arm_id}:functional={arm.functional_status}:"
                f"economic={arm.economic_status}"
            )
            for arm in result.evaluation.arms
        ),
    )
    gap = _generic_record(
        schema_id="evaluation_snapshot",
        record_id=f"{offline_run_id}:gap-report",
        value_refs=(
            "gap:complete_candidate_proposal_stream:UNKNOWN",
            "gap:strategic_episode_state:UNKNOWN",
            "gap:core_tactical_lot_role:UNKNOWN",
            "gap:reentry_contract:UNKNOWN",
            "gap:geometry_lifecycle:UNKNOWN",
        ),
    )
    compatibility = _generic_record(
        schema_id="evaluation_snapshot",
        record_id=f"{offline_run_id}:compatibility-report",
        value_refs=(
            (
                "legacy-source-tree-unchanged:"
                f"{str(result.source_tree_unchanged).lower()}"
            ),
            (
                "a-accounting-replay-match:"
                f"{str(result.evaluation.a_replayed_accounting_match).lower()}"
            ),
            (
                "a-action-fill-identity-match:"
                f"{str(result.evaluation.a_replayed_action_fill_identity_match).lower()}"
            ),
            (
                "scenario-report-digest:"
                f"{result.scenario_report.report_digest}"
            ),
        ),
    )
    residual = _generic_record(
        schema_id="evaluation_snapshot",
        record_id=f"{offline_run_id}:residual-risk-report",
        value_refs=(
            "residual:probability-calibration:NOT_ESTABLISHED",
            "residual:predictive-validity:NOT_ESTABLISHED",
            "residual:profitability:NOT_ESTABLISHED",
            "residual:paper-readiness:NOT_AUTHORIZED",
            "residual:live-readiness:NOT_AUTHORIZED",
            "residual:historical-b-i-economics:NOT_IDENTIFIABLE",
        ),
    )
    json_artifacts = {
        artifacts / "round1-run-result.json": run_payload,
        artifacts / "canonical-scenario-report.json": scenario_payload,
        artifacts / "round1-evaluation.json": evaluation_payload,
        artifacts / "topology-evaluation.json": topology_payload,
        artifacts / "hard-gate-result.json": hard_gate,
        artifacts / "ablation-result.json": ablation,
        artifacts / "gap-report.json": gap,
        artifacts / "compatibility-report.json": compatibility,
        artifacts / "residual-risk-report.json": residual,
    }
    for path, payload in json_artifacts.items():
        write_once_json(path, payload)

    markdown_path = reports / "round1-frozen-evaluation.md"
    _write_once_text(markdown_path, build_round1_markdown_zh(result))

    index_path = run_root / "artifact-index.json"
    indexed_paths = tuple(
        sorted(
            (
                path
                for path in run_root.rglob("*")
                if path.is_file() and path != index_path
            ),
            key=lambda item: item.relative_to(run_root).as_posix(),
        )
    )
    entries = []
    for path in indexed_paths:
        payload = path.read_bytes()
        entries.append(
            {
                "relative_path": path.relative_to(run_root).as_posix(),
                "byte_length": len(payload),
                "physical_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    index = self_digest(
        {
            "index_id": f"{offline_run_id}:artifact-index",
            "index_version": "1.0.0",
            "entries": entries,
            "round1_run_result_digest": result.run_result_digest,
            "round2_authorized": result.round2_authorized,
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "artifact_index_digest",
    )
    write_once_json(index_path, index)
    # Re-read the exact canonical bytes to ensure no presentation mutation.
    if canonical_bytes(index) + b"\n" != index_path.read_bytes():
        raise PresentationError("ARTIFACT_INDEX_BYTES_MISMATCH")
    return MaterializedRound1Report(
        run_root=run_root,
        artifact_index_path=index_path,
        markdown_path=markdown_path,
        artifact_index_digest=str(index["artifact_index_digest"]),
    )
