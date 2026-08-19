"""Chinese reader report for one completed formal E0 experiment."""

from __future__ import annotations

from ..application.formal_experiment import FormalExperimentResult


def _entry_value(
    entries: object,
    prefix: str,
    *,
    fallback: str = "UNKNOWN",
) -> str:
    if not isinstance(entries, list):
        return fallback
    for item in entries:
        if isinstance(item, str) and item.startswith(prefix):
            return item[len(prefix) :]
    return fallback


def build_formal_experiment_markdown_zh(
    result: FormalExperimentResult,
) -> str:
    """Render conclusions without upgrading E0 evidence or authority."""

    topology = result.topology_evaluation
    behavior = result.behavior_metrics
    risk = result.risk_metrics
    profit = result.profit_metrics
    manifest_entries = result.experiment_manifest.get("entry_refs")
    requested_model = _entry_value(
        manifest_entries,
        "requested-model:",
    )
    served_model = _entry_value(
        manifest_entries,
        "served-model-attestation:",
        fallback="UNKNOWN_NOT_EXPOSED",
    )
    served_model_status = _entry_value(
        manifest_entries,
        "served-model-attestation-status:",
        fallback="UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT",
    )
    model_call_cost_status = _entry_value(
        manifest_entries,
        "model-call-monetary-cost:",
        fallback="UNKNOWN_NOT_EXPOSED",
    )
    reasons = (
        "\n".join(f"- `{item}`" for item in result.terminal_reason_codes)
        if result.terminal_reason_codes
        else "- 无"
    )
    lines = [
        "# Theory Agent V2 正式 E0 实验报告",
        "",
        "## 结论",
        "",
        f"- 终局：`{result.terminal_status}`。",
        (
            "- 三个冻结窗口按顺序独立使用：拓扑选择 96–127、"
            "政策资格 128–159、正式度量 160–191。正式窗口没有反向"
            "修改拓扑或政策。"
        ),
        (
            f"- 选定拓扑：`{topology.selected_topology_id}`；"
            f"选择状态：`{topology.selection_status}`。"
        ),
        (
            f"- 行为闸门：`{behavior.gate_status}`；"
            f"风险闸门：`{risk.gate_status}`；"
            f"经济闸门：`{profit.gate_status}`。"
        ),
        (
            f"- 第二轮前置状态：`{result.round2_precondition_status}`；"
            "本次运行没有创建 101% 第二轮实例。"
        ),
        "",
        "## 当前状态与权限边界",
        "",
        "- 模式：`E0_OFFLINE_COUNTERFACTUAL`。",
        "- 外部执行权：`NONE_E0`；`executable=false`。",
        "- 本报告不构成 paper、live、自动下单或盈利能力授权。",
        (
            f"- 冻结数据集：`{result.dataset_manifest_ref.dataset_id}`；"
            f"质量：`{result.dataset_manifest_ref.quality_verdict}`。"
        ),
        (
            "- 角色输入 transport："
            f"`{result.dataset_manifest_ref.transport_contract_verdict}`；"
            "schema digest："
            f"`{result.dataset_manifest_ref.transport_schema_digest}`。"
        ),
        f"- 请求模型绑定：`{requested_model}`。",
        (
            "- 服务端实际模型证明："
            f"`{served_model}`；状态：`{served_model_status}`。未暴露时"
            "保持 UNKNOWN，不用请求模型名称替代证明。"
        ),
        (
            "- 模型调用货币成本："
            f"`{model_call_cost_status}`；冻结合同未把该值设为拓扑"
            "选择门，因此不以 0 填补，也不据此阻断。"
        ),
        "",
        "## 冻结样本与拓扑选择",
        "",
        "| 项目 | 数值 |",
        "|---|---:|",
        f"| 输入收据总数 | {result.receipt_count} |",
        (
            "| 拓扑选择完整配对会话 | "
            f"{result.topology_selection_session_count} |"
        ),
        (
            "| 政策资格会话 | "
            f"{result.policy_qualification_session_count} |"
        ),
        (
            "| 正式实验会话 | "
            f"{result.formal_experiment_session_count} |"
        ),
        (
            "| 等输入、请求模型与预算 | "
            f"{str(topology.equal_input_model_budget_verified).lower()} |"
        ),
        "",
        "## 行为指标",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 正式决策数 | {behavior.decision_count} |",
        (
            "| 动态候选路径覆盖均值 | "
            f"{behavior.mean_dynamic_candidate_coverage} |"
        ),
        (
            "| 独立缺陷发现均值 | "
            f"{behavior.mean_independent_defect_discovery} |"
        ),
        f"| 动作质量均值 | {behavior.mean_action_quality_score} |",
        f"| 硬约束错误 | {behavior.hard_constraint_error_count} |",
        f"| 状态连续性错误 | {behavior.state_continuity_error_count} |",
        (
            "| 重复评估差异 | "
            f"{behavior.reproducibility_difference_count} |"
        ),
        "",
        "## 风险与收益指标",
        "",
        "| 指标 | 当前拓扑 | 冻结基准 | 差额 |",
        "|---|---:|---:|---:|",
        (
            f"| 最大回撤 | {risk.max_drawdown_fraction} | "
            f"{risk.frozen_baseline_max_drawdown_fraction} | "
            f"{risk.drawdown_degradation_fraction} |"
        ),
        (
            f"| 扣成本净收益 | {profit.net_pnl_after_cost} | "
            f"{profit.frozen_baseline_net_pnl_after_cost} | "
            f"{profit.relative_frozen_baseline_pnl} |"
        ),
        (
            f"| 主路径捕获 | {profit.mean_primary_path_capture} | "
            f"{profit.frozen_baseline_mean_primary_path_capture} | — |"
        ),
        f"| 交易成本 | {profit.transaction_cost} | — | — |",
        "",
        "## 两次确定性评估",
        "",
        (
            f"- 第一次摘要：`{result.first_evaluation_summary_digest}`"
        ),
        (
            f"- 第二次摘要：`{result.second_evaluation_summary_digest}`"
        ),
        (
            "- 完全一致："
            f"`{str(result.deterministic_repeat_match).lower()}`。"
        ),
        "",
        "## 终局原因码",
        "",
        reasons,
        "",
        "## 裁决边界",
        "",
        (
            "- 拓扑选择窗口只选择拓扑；政策资格窗口只决定该拓扑是否"
            "可进入正式窗口；收益和行为结论只来自正式窗口。"
        ),
        (
            "- 选择与资格窗口中未识别的经济字段保留为 null/UNKNOWN，"
            "没有用零值填补。"
        ),
        (
            "- 即使三个闸门通过，本结果也只表示可以提交独立的 101% "
            "第二轮前置审查，不会自动创建第二轮。"
        ),
        "",
        f"正式结果摘要：`{result.result_digest}`",
        "",
    ]
    return "\n".join(lines)


__all__ = ["build_formal_experiment_markdown_zh"]
