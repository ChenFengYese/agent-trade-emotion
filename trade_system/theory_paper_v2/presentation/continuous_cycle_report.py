"""Required user-visible summary projection for one completed research cycle."""

from __future__ import annotations

from typing import Any, Mapping


class CycleReportError(ValueError):
    pass


REQUIRED_SUMMARY_FIELDS = (
    "conclusion",
    "current_status",
    "data_collection",
    "analysis_process",
    "theory_sources",
    "inference_chain",
    "path_updates",
    "action_comparison",
    "selected_actions",
    "positions_and_trades",
    "risk_cost_performance",
    "comparators",
    "known_problems",
    "next_step",
    "full_report_path",
    "completion_receipt_digest",
)


def render_cycle_user_summary(summary: Mapping[str, Any]) -> str:
    """Render enough information to audit a cycle without opening internal files."""

    if set(summary) != set(REQUIRED_SUMMARY_FIELDS):
        raise CycleReportError("CYCLE_USER_SUMMARY_INCOMPLETE")
    for field in REQUIRED_SUMMARY_FIELDS:
        value = summary[field]
        if value is None or value == "" or value == [] or value == {}:
            raise CycleReportError(f"CYCLE_USER_SUMMARY_EMPTY:{field}")

    def section(title: str, value: Any) -> str:
        if isinstance(value, Mapping):
            lines = [f"- {key}: {item}" for key, item in value.items()]
        elif isinstance(value, (list, tuple)):
            lines = [f"- {item}" for item in value]
        else:
            lines = [str(value)]
        return f"### {title}\n\n" + "\n".join(lines)

    sections = [
        section("结论", summary["conclusion"]),
        section("当前状态", summary["current_status"]),
        section("数据采集与质量", summary["data_collection"]),
        section("分析流程", summary["analysis_process"]),
        section("理论来源", summary["theory_sources"]),
        section("事实到政策推论链", summary["inference_chain"]),
        section("竞争路径与动态更新", summary["path_updates"]),
        section("八类动作与仓位尺度比较", summary["action_comparison"]),
        section("当期选择", summary["selected_actions"]),
        section("仓位与交易", summary["positions_and_trades"]),
        section("风险、成本与结果", summary["risk_cost_performance"]),
        section("同条件对照", summary["comparators"]),
        section("已知问题", summary["known_problems"]),
        section("下一步", summary["next_step"]),
        section(
            "完整证据",
            {
                "report": summary["full_report_path"],
                "completion_receipt": summary["completion_receipt_digest"],
            },
        ),
    ]
    return "\n\n".join(sections) + "\n"
