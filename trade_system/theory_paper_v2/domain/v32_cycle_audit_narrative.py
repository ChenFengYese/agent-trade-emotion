"""Typed, append-only Chinese audit narrative directory and deterministic shards."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_bytes, canonical_digest, self_digest, verify_self_digest
from .v32_authorized_revision_common import (
    SCHEMA_VERSION,
    V32AuthorizedRevisionContractError,
    binding,
    boundary,
    integer,
    text,
    time,
    verify_boundary,
)


DIRECTORY_SCHEMA_ID = "theory_paper_v32_cycle_audit_narrative_directory_v1"
DIRECTORY_DIGEST_FIELD = "cycle_audit_narrative_directory_digest"
SHARD_SCHEMA_ID = "theory_paper_v32_cycle_audit_narrative_shard_v1"
SHARD_DIGEST_FIELD = "cycle_audit_narrative_shard_digest"
POLICY_SCHEMA_ID = "theory_paper_v32_cycle_audit_policy_v1"
POLICY_DIGEST_FIELD = "cycle_audit_policy_digest"
MAX_SECTION_UTF8_BYTES = 262_144
DEFAULT_MAX_TEXT_PART_UTF8_BYTES = 8_192
DEFAULT_MAX_SHARD_CANONICAL_BYTES = 16_384
MAX_NARRATIVE_SHARDS = 512
BOUNDARY_TYPES = frozenset(
    {"QUALIFICATION", "ANALYSIS", "ACCEPTANCE", "OUTCOME", "RECOVERY"}
)
REQUIRED_SECTION_IDS = (
    "RUN_AND_CYCLE",
    "STAGE_CHRONOLOGY",
    "SOURCE_COVERAGE",
    "OBJECTIVE_UNKNOWNS",
    "SUBJECTIVE_ASSESSMENTS",
    "HYPOTHESIS_ZONE_MODIFIER_CHANGES",
    "LEGAL_ACTION_COMPARISON",
    "SELECTED_AND_RUNNER_UP",
    "RISK_ENVELOPE",
    "SHADOW_ARMS",
    "OUTCOME_SCHEDULE",
    "ALERTS_AND_RECOVERY",
    "DIGESTS_AND_LIMITATIONS",
)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class V32CycleAuditNarrativeError(ValueError):
    """A narrative omitted, reordered, forged, or exceeded a frozen bound."""


def build_v32_cycle_audit_policy_v1(
    *,
    policy_id: str,
    run_scope_id: str,
    frozen_at: str,
    max_text_part_utf8_bytes: int = DEFAULT_MAX_TEXT_PART_UTF8_BYTES,
    max_shard_canonical_bytes: int = DEFAULT_MAX_SHARD_CANONICAL_BYTES,
) -> dict[str, Any]:
    """Freeze human audit rendering after each corresponding typed boundary."""

    try:
        document = {
            "schema_id": POLICY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "policy_id": text(policy_id, "V32_AUDIT_POLICY_ID_INVALID"),
            "run_scope_id": text(
                run_scope_id, "V32_AUDIT_POLICY_RUN_SCOPE_INVALID"
            ),
            "frozen_at": time(frozen_at, "V32_AUDIT_POLICY_TIME_INVALID"),
            "language": "zh-CN",
            "required_section_ids": list(REQUIRED_SECTION_IDS),
            "boundary_types": sorted(BOUNDARY_TYPES),
            "max_section_utf8_bytes": MAX_SECTION_UTF8_BYTES,
            "max_text_part_utf8_bytes": integer(
                max_text_part_utf8_bytes,
                "V32_AUDIT_POLICY_PART_LIMIT_INVALID",
                minimum=256,
                maximum=65_536,
            ),
            "max_shard_canonical_bytes": integer(
                max_shard_canonical_bytes,
                "V32_AUDIT_POLICY_SHARD_LIMIT_INVALID",
                minimum=2048,
                maximum=131_072,
            ),
            "max_narrative_shards": MAX_NARRATIVE_SHARDS,
            "typed_source_bindings_required": True,
            "all_sections_required": True,
            "deterministic_sharding_required": True,
            "append_only_required": True,
            # Every narrative is derived only after its corresponding typed
            # boundary is sealed.  Acceptance narratives are a stricter
            # subset and remain post-acceptance; qualification, analysis,
            # outcome and recovery narratives must not be mislabeled as
            # post-acceptance artifacts.
            "typed_boundary_must_be_sealed_before_narrative": True,
            "acceptance_narrative_post_acceptance_only": True,
            "narrative_is_authority": False,
            "typed_artifacts_remain_authoritative": True,
            "private_chain_of_thought_recorded": False,
            "capacity_failure_status": "CONTEXT_CAPACITY_UNRESOLVED",
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        raise V32CycleAuditNarrativeError(
            "V32_AUDIT_POLICY_INPUT_INVALID"
        ) from exc
    return self_digest(document, POLICY_DIGEST_FIELD)


def verify_v32_cycle_audit_policy_v1(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, POLICY_DIGEST_FIELD)
        verify_boundary(document, "V32_AUDIT_POLICY_BOUNDARY_INVALID")
        rebuilt = build_v32_cycle_audit_policy_v1(
            policy_id=document["policy_id"],
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
            max_text_part_utf8_bytes=document["max_text_part_utf8_bytes"],
            max_shard_canonical_bytes=document["max_shard_canonical_bytes"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleAuditNarrativeError):
            raise
        raise V32CycleAuditNarrativeError("V32_AUDIT_POLICY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[POLICY_DIGEST_FIELD]:
        raise V32CycleAuditNarrativeError("V32_AUDIT_POLICY_REPLAY_MISMATCH")
    return supplied


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _chinese(value: Any, code: str) -> str:
    candidate = text(value, code)
    if _CJK.search(candidate) is None:
        raise V32CycleAuditNarrativeError(code)
    return candidate


def _split_utf8(value: str, maximum: int) -> list[str]:
    if len(value.encode("utf-8")) <= maximum:
        return [value]
    parts: list[str] = []
    current: list[str] = []
    current_bytes = 0
    for character in value:
        size = len(character.encode("utf-8"))
        if current and current_bytes + size > maximum:
            parts.append("".join(current))
            current = []
            current_bytes = 0
        current.append(character)
        current_bytes += size
    if current:
        parts.append("".join(current))
    return parts


def _sections(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_SET_INVALID")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "section_id",
            "title_zh",
            "content_zh",
            "source_bindings",
        }:
            raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_INVALID")
        source_bindings = item["source_bindings"]
        if (
            isinstance(source_bindings, (str, bytes))
            or not isinstance(source_bindings, Sequence)
            or not source_bindings
            or len(source_bindings) > 64
        ):
            raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_SOURCE_INVALID")
        normalized_bindings = [
            binding(row, "V32_AUDIT_SECTION_SOURCE_INVALID")
            for row in source_bindings
        ]
        normalized_bindings.sort(
            key=lambda row: (
                row["schema_id"], row["semantic_digest"], row["relative_ref"]
            )
        )
        if len(
            {
                (row["schema_id"], row["semantic_digest"], row["physical_sha256"])
                for row in normalized_bindings
            }
        ) != len(normalized_bindings):
            raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_SOURCE_DUPLICATE")
        content = _chinese(item["content_zh"], "V32_AUDIT_SECTION_CHINESE_REQUIRED")
        if len(content.encode("utf-8")) > MAX_SECTION_UTF8_BYTES:
            raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_TOO_LARGE")
        rows.append(
            {
                "section_id": text(item["section_id"], "V32_AUDIT_SECTION_INVALID"),
                "title_zh": _chinese(
                    item["title_zh"], "V32_AUDIT_SECTION_CHINESE_REQUIRED"
                ),
                "content_zh": content,
                "source_bindings": normalized_bindings,
            }
        )
    if [row["section_id"] for row in rows] != list(REQUIRED_SECTION_IDS):
        raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_COVERAGE_INVALID")
    return rows


def _shard(
    *,
    run_id: str,
    cycle_index: int,
    boundary_type: str,
    generated_at: str,
    section_id: str,
    source_bindings_digest: str,
    part_index: int,
    part_count: int,
    content_part_zh: str,
) -> dict[str, Any]:
    return self_digest(
        {
            "schema_id": SHARD_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "boundary_type": boundary_type,
            "generated_at": generated_at,
            "section_id": section_id,
            "part_index": part_index,
            "part_count": part_count,
            "source_bindings_digest": source_bindings_digest,
            "content_part_zh": content_part_zh,
            "content_part_utf8_bytes": len(content_part_zh.encode("utf-8")),
            "content_part_sha256": hashlib.sha256(
                content_part_zh.encode("utf-8")
            ).hexdigest(),
            "narrative_is_authority": False,
            "typed_artifacts_remain_authoritative": True,
            "private_chain_of_thought_recorded": False,
            **boundary(),
        },
        SHARD_DIGEST_FIELD,
    )


def build_v32_cycle_audit_narrative_bundle_v1(
    *,
    narrative_id: str,
    run_id: str,
    cycle_index: int,
    boundary_type: str,
    generated_at: str,
    sections: Sequence[Mapping[str, Any]],
    max_text_part_utf8_bytes: int = DEFAULT_MAX_TEXT_PART_UTF8_BYTES,
    max_shard_canonical_bytes: int = DEFAULT_MAX_SHARD_CANONICAL_BYTES,
) -> dict[str, Any]:
    try:
        run = text(run_id, "V32_AUDIT_RUN_INVALID")
        cycle = integer(
            cycle_index, "V32_AUDIT_CYCLE_INVALID", minimum=0, maximum=16
        )
        boundary_name = text(boundary_type, "V32_AUDIT_BOUNDARY_TYPE_INVALID")
        if boundary_name not in BOUNDARY_TYPES:
            raise V32CycleAuditNarrativeError("V32_AUDIT_BOUNDARY_TYPE_INVALID")
        generated = time(generated_at, "V32_AUDIT_TIME_INVALID")
        part_limit = integer(
            max_text_part_utf8_bytes,
            "V32_AUDIT_PART_LIMIT_INVALID",
            minimum=256,
            maximum=65_536,
        )
        shard_limit = integer(
            max_shard_canonical_bytes,
            "V32_AUDIT_SHARD_LIMIT_INVALID",
            minimum=2048,
            maximum=131_072,
        )
        normalized_sections = _sections(sections)
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        if isinstance(exc, V32CycleAuditNarrativeError):
            raise
        raise V32CycleAuditNarrativeError("V32_AUDIT_INPUT_INVALID") from exc

    shards: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    for section in normalized_sections:
        parts = _split_utf8(section["content_zh"], part_limit)
        source_digest = canonical_digest(section["source_bindings"])
        descriptors: list[dict[str, Any]] = []
        for part_index, part in enumerate(parts):
            shard = _shard(
                run_id=run,
                cycle_index=cycle,
                boundary_type=boundary_name,
                generated_at=generated,
                section_id=section["section_id"],
                source_bindings_digest=source_digest,
                part_index=part_index,
                part_count=len(parts),
                content_part_zh=part,
            )
            shard_bytes = len(canonical_bytes(shard))
            if shard_bytes > shard_limit:
                raise V32CycleAuditNarrativeError("CONTEXT_CAPACITY_UNRESOLVED")
            global_index = len(shards)
            shards.append(shard)
            descriptors.append(
                {
                    "relative_ref": (
                        "cycle-audit-narrative/shards/"
                        f"{global_index:04d}-{section['section_id'].lower()}-"
                        f"{part_index:04d}.json"
                    ),
                    "schema_id": SHARD_SCHEMA_ID,
                    "digest_field": SHARD_DIGEST_FIELD,
                    "semantic_digest": shard[SHARD_DIGEST_FIELD],
                    "physical_sha256": _physical(shard),
                    "part_index": part_index,
                    "canonical_bytes": shard_bytes,
                }
            )
        entries.append(
            {
                "section_id": section["section_id"],
                "title_zh": section["title_zh"],
                "source_bindings": section["source_bindings"],
                "source_bindings_digest": source_digest,
                "content_utf8_bytes": len(section["content_zh"].encode("utf-8")),
                "content_sha256": hashlib.sha256(
                    section["content_zh"].encode("utf-8")
                ).hexdigest(),
                "part_count": len(parts),
                "shard_descriptors": descriptors,
            }
        )
    if len(shards) > MAX_NARRATIVE_SHARDS:
        raise V32CycleAuditNarrativeError("CONTEXT_CAPACITY_UNRESOLVED")
    directory = self_digest(
        {
            "schema_id": DIRECTORY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "narrative_id": text(narrative_id, "V32_AUDIT_ID_INVALID"),
            "run_id": run,
            "cycle_index": cycle,
            "boundary_type": boundary_name,
            "generated_at": generated,
            "language": "zh-CN",
            "required_section_ids": list(REQUIRED_SECTION_IDS),
            "section_entries": entries,
            "section_count": len(entries),
            "shard_count": len(shards),
            "max_text_part_utf8_bytes": part_limit,
            "max_shard_canonical_bytes": shard_limit,
            "all_sections_present": True,
            "section_omission_allowed": False,
            "append_only_required": True,
            "narrative_is_authority": False,
            "typed_artifacts_remain_authoritative": True,
            "private_chain_of_thought_recorded": False,
            "limitations_required": True,
            **boundary(),
        },
        DIRECTORY_DIGEST_FIELD,
    )
    return {"directory": directory, "shards": shards}


def verify_v32_cycle_audit_narrative_bundle_v1(
    directory: Mapping[str, Any], shards: Sequence[Mapping[str, Any]]
) -> str:
    try:
        supplied = verify_self_digest(directory, DIRECTORY_DIGEST_FIELD)
        verify_boundary(directory, "V32_AUDIT_BOUNDARY_INVALID")
    except (TypeError, ValueError) as exc:
        raise V32CycleAuditNarrativeError("V32_AUDIT_DIRECTORY_INVALID") from exc
    if (
        directory.get("schema_id") != DIRECTORY_SCHEMA_ID
        or directory.get("schema_version") != SCHEMA_VERSION
        or directory.get("language") != "zh-CN"
        or directory.get("required_section_ids") != list(REQUIRED_SECTION_IDS)
        or directory.get("section_count") != len(REQUIRED_SECTION_IDS)
        or directory.get("all_sections_present") is not True
        or directory.get("section_omission_allowed") is not False
        or directory.get("append_only_required") is not True
        or directory.get("narrative_is_authority") is not False
        or directory.get("typed_artifacts_remain_authoritative") is not True
        or directory.get("private_chain_of_thought_recorded") is not False
        or directory.get("limitations_required") is not True
        or not isinstance(shards, Sequence)
        or isinstance(shards, (str, bytes))
        or len(shards) != directory.get("shard_count")
        or len(shards) > MAX_NARRATIVE_SHARDS
    ):
        raise V32CycleAuditNarrativeError("V32_AUDIT_DIRECTORY_INVALID")
    entries = directory.get("section_entries")
    if (
        not isinstance(entries, list)
        or [entry.get("section_id") for entry in entries]
        != list(REQUIRED_SECTION_IDS)
    ):
        raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_COVERAGE_INVALID")
    cursor = 0
    replay_sections: list[dict[str, Any]] = []
    for entry in entries:
        try:
            normalized_sources = [
                binding(row, "V32_AUDIT_SECTION_SOURCE_INVALID")
                for row in entry["source_bindings"]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise V32CycleAuditNarrativeError(
                "V32_AUDIT_SECTION_SOURCE_INVALID"
            ) from exc
        normalized_sources.sort(
            key=lambda row: (
                row["schema_id"], row["semantic_digest"], row["relative_ref"]
            )
        )
        if (
            normalized_sources != entry["source_bindings"]
            or canonical_digest(normalized_sources) != entry["source_bindings_digest"]
            or entry.get("part_count", 0) < 1
        ):
            raise V32CycleAuditNarrativeError("V32_AUDIT_SECTION_SOURCE_INVALID")
        parts: list[str] = []
        descriptors = entry.get("shard_descriptors")
        if not isinstance(descriptors, list) or len(descriptors) != entry["part_count"]:
            raise V32CycleAuditNarrativeError("V32_AUDIT_SHARD_DIRECTORY_INVALID")
        for local_index, descriptor in enumerate(descriptors):
            if cursor >= len(shards):
                raise V32CycleAuditNarrativeError("V32_AUDIT_SHARD_SET_INVALID")
            shard = shards[cursor]
            cursor += 1
            try:
                shard_digest = verify_self_digest(shard, SHARD_DIGEST_FIELD)
                verify_boundary(shard, "V32_AUDIT_SHARD_BOUNDARY_INVALID")
            except (TypeError, ValueError) as exc:
                raise V32CycleAuditNarrativeError("V32_AUDIT_SHARD_INVALID") from exc
            content = shard.get("content_part_zh")
            if (
                shard.get("schema_id") != SHARD_SCHEMA_ID
                or shard.get("schema_version") != SCHEMA_VERSION
                or shard.get("run_id") != directory["run_id"]
                or shard.get("cycle_index") != directory["cycle_index"]
                or shard.get("boundary_type") != directory["boundary_type"]
                or shard.get("generated_at") != directory["generated_at"]
                or shard.get("section_id") != entry["section_id"]
                or shard.get("part_index") != local_index
                or shard.get("part_count") != entry["part_count"]
                or shard.get("source_bindings_digest")
                != entry["source_bindings_digest"]
                or not isinstance(content, str)
                or shard.get("content_part_utf8_bytes")
                != len(content.encode("utf-8"))
                or shard.get("content_part_utf8_bytes")
                > directory["max_text_part_utf8_bytes"]
                or shard.get("content_part_sha256")
                != hashlib.sha256(content.encode("utf-8")).hexdigest()
                or len(canonical_bytes(shard))
                > directory["max_shard_canonical_bytes"]
                or shard.get("narrative_is_authority") is not False
                or shard.get("typed_artifacts_remain_authoritative") is not True
                or shard.get("private_chain_of_thought_recorded") is not False
            ):
                raise V32CycleAuditNarrativeError("V32_AUDIT_SHARD_INVALID")
            expected_descriptor = {
                "relative_ref": descriptor["relative_ref"],
                "schema_id": SHARD_SCHEMA_ID,
                "digest_field": SHARD_DIGEST_FIELD,
                "semantic_digest": shard_digest,
                "physical_sha256": _physical(shard),
                "part_index": local_index,
                "canonical_bytes": len(canonical_bytes(shard)),
            }
            if descriptor != expected_descriptor:
                raise V32CycleAuditNarrativeError("V32_AUDIT_SHARD_DIRECTORY_INVALID")
            parts.append(content)
        content_zh = "".join(parts)
        if (
            _CJK.search(content_zh) is None
            or len(content_zh.encode("utf-8")) != entry["content_utf8_bytes"]
            or hashlib.sha256(content_zh.encode("utf-8")).hexdigest()
            != entry["content_sha256"]
        ):
            raise V32CycleAuditNarrativeError("V32_AUDIT_CONTENT_REPLAY_MISMATCH")
        replay_sections.append(
            {
                "section_id": entry["section_id"],
                "title_zh": entry["title_zh"],
                "content_zh": content_zh,
                "source_bindings": normalized_sources,
            }
        )
    if cursor != len(shards):
        raise V32CycleAuditNarrativeError("V32_AUDIT_SHARD_SET_INVALID")
    rebuilt = build_v32_cycle_audit_narrative_bundle_v1(
        narrative_id=directory["narrative_id"],
        run_id=directory["run_id"],
        cycle_index=directory["cycle_index"],
        boundary_type=directory["boundary_type"],
        generated_at=directory["generated_at"],
        sections=replay_sections,
        max_text_part_utf8_bytes=directory["max_text_part_utf8_bytes"],
        max_shard_canonical_bytes=directory["max_shard_canonical_bytes"],
    )
    if dict(directory) != rebuilt["directory"] or list(shards) != rebuilt["shards"]:
        raise V32CycleAuditNarrativeError("V32_AUDIT_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "BOUNDARY_TYPES",
    "DEFAULT_MAX_SHARD_CANONICAL_BYTES",
    "DEFAULT_MAX_TEXT_PART_UTF8_BYTES",
    "DIRECTORY_DIGEST_FIELD",
    "DIRECTORY_SCHEMA_ID",
    "MAX_NARRATIVE_SHARDS",
    "MAX_SECTION_UTF8_BYTES",
    "POLICY_DIGEST_FIELD",
    "POLICY_SCHEMA_ID",
    "REQUIRED_SECTION_IDS",
    "SHARD_DIGEST_FIELD",
    "SHARD_SCHEMA_ID",
    "V32CycleAuditNarrativeError",
    "build_v32_cycle_audit_narrative_bundle_v1",
    "build_v32_cycle_audit_policy_v1",
    "verify_v32_cycle_audit_narrative_bundle_v1",
    "verify_v32_cycle_audit_policy_v1",
]
