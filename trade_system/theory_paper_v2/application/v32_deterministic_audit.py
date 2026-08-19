"""Deterministic Chinese audit rendering from sealed V3.2 typed artifacts.

The renderer accepts no caller-authored narrative text.  It verifies every
source self-digest and physical binding, extracts a stable bounded audit view,
and delegates deterministic sharding to the Domain contract.  Large arrays or
objects are represented by exact count and canonical digest; the bound typed
artifact remains authoritative and fully replayable.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    verify_self_digest,
)
from ..domain.v32_cycle_audit_narrative import (
    BOUNDARY_TYPES,
    DEFAULT_MAX_SHARD_CANONICAL_BYTES,
    DEFAULT_MAX_TEXT_PART_UTF8_BYTES,
    REQUIRED_SECTION_IDS,
    build_v32_cycle_audit_narrative_bundle_v1,
)


class V32DeterministicAuditError(ValueError):
    """A source was not sealed, bound, chronological, or safe to render."""


_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_SOURCE_FIELDS = frozenset({"role", "document", "binding"})
_PRIVATE_KEYS = frozenset(
    {
        "chain_of_thought",
        "private_chain_of_thought",
        "private_reasoning",
        "reasoning_trace",
        "hidden_reasoning",
    }
)
_SECTION_TITLES = {
    "RUN_AND_CYCLE": "运行与周期",
    "STAGE_CHRONOLOGY": "阶段时序",
    "SOURCE_COVERAGE": "来源覆盖与数据质量",
    "OBJECTIVE_UNKNOWNS": "客观未知",
    "SUBJECTIVE_ASSESSMENTS": "有依据的主观评估",
    "HYPOTHESIS_ZONE_MODIFIER_CHANGES": "假说、磁区与外在路径变化",
    "LEGAL_ACTION_COMPARISON": "全部合法动作比较",
    "SELECTED_AND_RUNNER_UP": "选定方案与次优方案",
    "RISK_ENVELOPE": "风险包络与动态管理",
    "SHADOW_ARMS": "影子对照臂",
    "OUTCOME_SCHEDULE": "结果观察计划",
    "ALERTS_AND_RECOVERY": "告警与恢复",
    "DIGESTS_AND_LIMITATIONS": "摘要绑定、权限与限制",
}
_SECTION_KEYWORDS = {
    "RUN_AND_CYCLE": (
        "run_id",
        "cycle_index",
        "boundary",
        "instrument",
        "venue",
        "status",
    ),
    "STAGE_CHRONOLOGY": (
        "_at",
        "_time",
        "timestamp",
        "stage",
        "attempt",
        "revision",
        "checkpoint",
    ),
    "SOURCE_COVERAGE": (
        "source",
        "coverage",
        "request",
        "datum",
        "available",
        "quality",
        "axis",
        "raw",
        "capture",
    ),
    "OBJECTIVE_UNKNOWNS": (
        "unknown",
        "missing",
        "unavailable",
        "coverage_loss",
        "data_gap",
        "claim_ceiling",
    ),
    "SUBJECTIVE_ASSESSMENTS": (
        "subjective",
        "plausibility",
        "rationale",
        "counter",
        "falsifier",
        "expires",
        "expiry",
    ),
    "HYPOTHESIS_ZONE_MODIFIER_CHANGES": (
        "hypothesis",
        "zone",
        "modifier",
        "regime",
        "graph",
        "association",
        "correlation",
        "dependency",
    ),
    "LEGAL_ACTION_COMPARISON": (
        "legal_action",
        "action_evaluation",
        "candidate_action",
        "alternative",
        "feasible",
        "dominance",
        "veto",
        "opportunity_cost",
    ),
    "SELECTED_AND_RUNNER_UP": (
        "selected",
        "runner_up",
        "lead",
        "final_action",
        "selection",
    ),
    "RISK_ENVELOPE": (
        "risk",
        "budget",
        "loss",
        "tranche",
        "stop",
        "target",
        "size",
        "reentry",
    ),
    "SHADOW_ARMS": ("shadow", "arm", "baseline", "counterfactual"),
    "OUTCOME_SCHEDULE": (
        "schedule",
        "horizon",
        "due_at",
        "outcome",
        "observation",
    ),
    "ALERTS_AND_RECOVERY": (
        "alert",
        "recovery",
        "failure",
        "error",
        "retry",
        "supervisor",
    ),
    "DIGESTS_AND_LIMITATIONS": (
        "digest",
        "schema",
        "claim",
        "authority",
        "executable",
        "account",
        "order",
        "fill",
        "pnl",
        "limitation",
    ),
}
_MAX_INLINE_CANONICAL_BYTES = 4096
_MAX_INLINE_STRING_BYTES = 1024
_MAX_SOURCES = 64


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32DeterministicAuditError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32DeterministicAuditError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32DeterministicAuditError(code)
    return parsed.astimezone(UTC)


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _contains_private_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            (isinstance(key, str) and key.casefold() in _PRIVATE_KEYS)
            or _contains_private_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_private_key(item) for item in value)
    return False


def _aggregate(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            "类型": "对象",
            "字段数": len(value),
            "字段": sorted(str(key) for key in value),
            "规范摘要": canonical_digest(value),
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {
            "类型": "序列",
            "成员数": len(value),
            "规范摘要": canonical_digest(value),
        }
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return {
            "类型": "长文本",
            "字节数": len(encoded),
            "文本摘要": hashlib.sha256(encoded).hexdigest(),
        }
    return {"类型": type(value).__name__, "规范摘要": canonical_digest(value)}


def _flatten(value: Any, *, path: str = "", depth: int = 0) -> list[tuple[str, Any]]:
    """Produce a stable bounded scalar view without caller-selected top-k."""

    if isinstance(value, str) and len(value.encode("utf-8")) > _MAX_INLINE_STRING_BYTES:
        return [(path or "$", _aggregate(value))]
    if isinstance(value, Mapping):
        if depth > 0 and len(canonical_bytes(value)) > _MAX_INLINE_CANONICAL_BYTES:
            rows: list[tuple[str, Any]] = [
                (path or "$", _aggregate(value))
            ]
            for key in sorted(value, key=lambda item: str(item)):
                child = value[key]
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(child, (Mapping, list, tuple)):
                    rows.append((child_path, _aggregate(child)))
                else:
                    rows.extend(_flatten(child, path=child_path, depth=depth + 1))
            return rows
        rows = []
        for key in sorted(value, key=lambda item: str(item)):
            child_path = f"{path}.{key}" if path else str(key)
            rows.extend(_flatten(value[key], path=child_path, depth=depth + 1))
        return rows
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(canonical_bytes(value)) > _MAX_INLINE_CANONICAL_BYTES:
            return [(path or "$", _aggregate(value))]
        rows = []
        for index, item in enumerate(value):
            rows.extend(_flatten(item, path=f"{path}[{index}]", depth=depth + 1))
        return rows
    return [(path or "$", value)]


def _normalized_sources(
    value: Any, *, run_id: str, cycle_index: int
) -> list[dict[str, Any]]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not value
        or len(value) > _MAX_SOURCES
    ):
        raise V32DeterministicAuditError("V32_AUDIT_SOURCE_SET_INVALID")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _SOURCE_FIELDS:
            raise V32DeterministicAuditError("V32_AUDIT_SOURCE_INVALID")
        role = item.get("role")
        document = item.get("document")
        binding = item.get("binding")
        if (
            not isinstance(role, str)
            or not role
            or role != role.strip()
            or not isinstance(document, Mapping)
            or not isinstance(binding, Mapping)
            or set(binding) != _BINDING_FIELDS
            or _contains_private_key(document)
        ):
            raise V32DeterministicAuditError("V32_AUDIT_SOURCE_INVALID")
        digest_field = binding.get("digest_field")
        try:
            semantic = verify_self_digest(document, digest_field)
        except (KeyError, TypeError, ValueError) as exc:
            raise V32DeterministicAuditError("V32_AUDIT_SOURCE_INVALID") from exc
        if (
            binding.get("schema_id") != document.get("schema_id")
            or binding.get("semantic_digest") != semantic
            or binding.get("physical_sha256") != _physical(document)
            or document.get("run_id", run_id) != run_id
            or document.get("cycle_index", cycle_index) != cycle_index
        ):
            raise V32DeterministicAuditError("V32_AUDIT_SOURCE_BINDING_INVALID")
        rows.append(
            {
                "role": role,
                "document": dict(document),
                "binding": dict(binding),
                "flat": _flatten(document),
            }
        )
    rows.sort(
        key=lambda row: (
            row["role"],
            row["binding"]["schema_id"],
            row["binding"]["semantic_digest"],
        )
    )
    if len({row["role"] for row in rows}) != len(rows):
        raise V32DeterministicAuditError("V32_AUDIT_SOURCE_ROLE_DUPLICATE")
    return rows


def _matches(path: str, keywords: Sequence[str]) -> bool:
    lowered = path.casefold()
    return any(keyword in lowered for keyword in keywords)


def _section_payload(
    *, section_id: str, sources: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    keywords = _SECTION_KEYWORDS[section_id]
    payload: list[dict[str, Any]] = []
    for source in sources:
        facts = [
            {"路径": path, "值": value}
            for path, value in source["flat"]
            if _matches(path, keywords)
        ]
        if section_id == "DIGESTS_AND_LIMITATIONS":
            facts = [
                {
                    "路径": "完整工件规范字节数",
                    "值": len(canonical_bytes(source["document"])),
                },
                {
                    "路径": "完整工件语义摘要",
                    "值": source["binding"]["semantic_digest"],
                },
                *facts,
            ]
        if facts:
            payload.append(
                {
                    "工件角色": source["role"],
                    "工件模式": source["binding"]["schema_id"],
                    "事实": facts,
                }
            )
    return payload


def compose_v32_deterministic_boundary_audit_v1(
    *,
    narrative_id: str,
    run_id: str,
    cycle_index: int,
    boundary_type: str,
    boundary_sealed_at: str,
    generated_at: str,
    sealed_sources: Sequence[Mapping[str, Any]],
    max_text_part_utf8_bytes: int = DEFAULT_MAX_TEXT_PART_UTF8_BYTES,
    max_shard_canonical_bytes: int = DEFAULT_MAX_SHARD_CANONICAL_BYTES,
) -> dict[str, Any]:
    """Build all thirteen sections only from verified sealed source bytes."""

    if boundary_type not in BOUNDARY_TYPES:
        raise V32DeterministicAuditError("V32_AUDIT_BOUNDARY_INVALID")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 0
        or (boundary_type == "QUALIFICATION" and cycle_index != 0)
        or (boundary_type != "QUALIFICATION" and not 1 <= cycle_index <= 16)
    ):
        raise V32DeterministicAuditError("V32_AUDIT_CYCLE_INVALID")
    if _time(generated_at, "V32_AUDIT_TIME_INVALID") < _time(
        boundary_sealed_at, "V32_AUDIT_TIME_INVALID"
    ):
        raise V32DeterministicAuditError("V32_AUDIT_BEFORE_BOUNDARY_FORBIDDEN")
    sources = _normalized_sources(
        sealed_sources, run_id=run_id, cycle_index=cycle_index
    )
    source_bindings = [source["binding"] for source in sources]
    sections = []
    for section_id in REQUIRED_SECTION_IDS:
        payload = _section_payload(section_id=section_id, sources=sources)
        if section_id == "RUN_AND_CYCLE":
            payload = [
                {
                    "工件角色": "audit_boundary_metadata",
                    "工件模式": "deterministic_renderer_input_v1",
                    "事实": [
                        {"路径": "run_id", "值": run_id},
                        {"路径": "cycle_index", "值": cycle_index},
                        {"路径": "boundary_type", "值": boundary_type},
                    ],
                },
                *payload,
            ]
        elif section_id == "STAGE_CHRONOLOGY":
            payload = [
                {
                    "工件角色": "audit_boundary_metadata",
                    "工件模式": "deterministic_renderer_input_v1",
                    "事实": [
                        {"路径": "boundary_sealed_at", "值": boundary_sealed_at},
                        {"路径": "narrative_generated_at", "值": generated_at},
                    ],
                },
                *payload,
            ]
        if payload:
            facts_text = canonical_bytes(payload).decode("utf-8")
        else:
            facts_text = (
                "该已封存边界没有可机械提取的本类字段；本节保持不适用或未知，"
                "未补值、未推测。"
            )
        sections.append(
            {
                "section_id": section_id,
                "title_zh": _SECTION_TITLES[section_id],
                "content_zh": (
                    "本节仅由已封存 typed 工件机械生成；完整原件仍是唯一权威。"
                    + facts_text
                ),
                "source_bindings": source_bindings,
            }
        )
    try:
        return build_v32_cycle_audit_narrative_bundle_v1(
            narrative_id=narrative_id,
            run_id=run_id,
            cycle_index=cycle_index,
            boundary_type=boundary_type,
            generated_at=generated_at,
            sections=sections,
            max_text_part_utf8_bytes=max_text_part_utf8_bytes,
            max_shard_canonical_bytes=max_shard_canonical_bytes,
        )
    except (TypeError, ValueError) as exc:
        raise V32DeterministicAuditError(
            "V32_AUDIT_DETERMINISTIC_RENDER_FAILED"
        ) from exc


__all__ = [
    "V32DeterministicAuditError",
    "compose_v32_deterministic_boundary_audit_v1",
]
