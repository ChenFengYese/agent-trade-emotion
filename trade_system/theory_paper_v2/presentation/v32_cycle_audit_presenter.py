"""Display-only rendering of a verified typed CycleAuditNarrative bundle."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..domain.v32_cycle_audit_narrative import (
    verify_v32_cycle_audit_narrative_bundle_v1,
)


def render_v32_cycle_audit_narrative_markdown_v1(
    *, directory: Mapping[str, Any], shards: Sequence[Mapping[str, Any]]
) -> str:
    """Return Chinese Markdown; perform no writes and create no authority."""

    verify_v32_cycle_audit_narrative_bundle_v1(directory, shards)
    by_section: dict[str, list[Mapping[str, Any]]] = {}
    for shard in shards:
        by_section.setdefault(str(shard["section_id"]), []).append(shard)
    lines = [
        f"# V3.2 周期审计：{directory['run_id']} / {directory['cycle_index']}",
        "",
        f"- 边界：{directory['boundary_type']}",
        f"- 生成时间：{directory['generated_at']}",
        "- 性质：仅供人工审查；typed 工件仍是唯一权威。",
        "",
    ]
    for entry in directory["section_entries"]:
        parts = sorted(
            by_section[entry["section_id"]], key=lambda row: row["part_index"]
        )
        lines.extend(
            [
                f"## {entry['title_zh']}",
                "",
                "".join(str(part["content_part_zh"]) for part in parts),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_v32_cycle_audit_narrative_markdown_v1"]
