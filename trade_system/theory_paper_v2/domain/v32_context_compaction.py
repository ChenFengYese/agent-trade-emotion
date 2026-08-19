"""Lossless deterministic context compaction from complete sealed originals.

Callers cannot provide a hand-picked member list.  Every canonical JSON leaf is
extracted from the fully replayed originals with a source identity and JSON
Pointer.  Dictionary equality never creates dependency edges.  Required roots
are policy-derived from epistemically critical roles and the caller may only add
roots, never remove them.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .v32_authorized_revision_common import (
    SCHEMA_VERSION,
    V32AuthorizedRevisionContractError,
    binding,
    boundary,
    integer,
    sorted_unique_texts,
    text,
    time,
    verify_boundary,
)


MANIFEST_SCHEMA_ID = "theory_paper_v32_context_compaction_manifest_v1"
MANIFEST_DIGEST_FIELD = "context_compaction_manifest_digest"
SHARD_SCHEMA_ID = "theory_paper_v32_context_compaction_shard_v1"
SHARD_DIGEST_FIELD = "context_compaction_shard_digest"
SELECTION_SCHEMA_ID = "theory_paper_v32_context_shard_selection_v1"
SELECTION_DIGEST_FIELD = "context_shard_selection_digest"
POLICY_SCHEMA_ID = "theory_paper_v32_context_compaction_policy_v1"
POLICY_DIGEST_FIELD = "context_compaction_policy_digest"
MAX_SOURCE_ARTIFACTS = 64
MAX_MEMBERS = 16_384
MAX_SHARDS = 512
DEFAULT_MAX_SHARD_CANONICAL_BYTES = 65_536
MAX_MANIFEST_CANONICAL_BYTES = 524_288

SEMANTIC_ROLES = frozenset(
    {
        "DATA",
        "METADATA",
        "TIME_SERIES",
        "UNKNOWN",
        "CONFLICT",
        "FALSIFIER",
        "HAZARD",
        "CLOSURE",
        "HYPOTHESIS",
        "OPPOSING_HYPOTHESIS",
    }
)
POLICY_REQUIRED_ROOT_ROLES = frozenset(
    {
        "UNKNOWN",
        "CONFLICT",
        "FALSIFIER",
        "HAZARD",
        "CLOSURE",
        "HYPOTHESIS",
        "OPPOSING_HYPOTHESIS",
    }
)
COMPACTION_STEPS = (
    "COMPLETE_ORIGINAL_REPLAY_AND_JSON_POINTER_EXTRACTION",
    "CANONICAL_DEDUPLICATION_AND_DICTIONARY",
    "TYPED_REPEATED_SERIES_AND_METADATA_COMPACTION",
    "DETERMINISTIC_FORCED_FULL_CROSS_SHARD_REFERENCE_SHARDING",
    "DETERMINISTIC_CANONICAL_VALUE_BYTE_RANGE_FRAGMENTATION",
    "POLICY_DERIVED_REQUIRED_ROOT_SELECTION",
)


class V32ContextCompactionError(ValueError):
    """The context projection is incomplete, lossy, forged, or over capacity."""


def build_v32_context_compaction_policy_v1(
    *,
    policy_id: str,
    run_scope_id: str,
    frozen_at: str,
    max_shard_canonical_bytes: int = DEFAULT_MAX_SHARD_CANONICAL_BYTES,
    max_manifest_canonical_bytes: int = MAX_MANIFEST_CANONICAL_BYTES,
    max_agent_context_canonical_bytes: int = 262_144,
) -> dict[str, Any]:
    """Freeze lossless compaction and fail-closed resource limits."""

    try:
        document = {
            "schema_id": POLICY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "policy_id": text(policy_id, "V32_COMPACTION_POLICY_ID_INVALID"),
            "run_scope_id": text(
                run_scope_id, "V32_COMPACTION_POLICY_RUN_SCOPE_INVALID"
            ),
            "frozen_at": time(frozen_at, "V32_COMPACTION_POLICY_TIME_INVALID"),
            "compaction_steps": list(COMPACTION_STEPS),
            "semantic_roles": sorted(SEMANTIC_ROLES),
            "policy_required_root_roles": sorted(POLICY_REQUIRED_ROOT_ROLES),
            "max_source_artifacts": MAX_SOURCE_ARTIFACTS,
            "max_members": MAX_MEMBERS,
            "max_shards": MAX_SHARDS,
            "max_shard_canonical_bytes": integer(
                max_shard_canonical_bytes,
                "V32_COMPACTION_POLICY_SHARD_LIMIT_INVALID",
                minimum=2048,
                maximum=262_144,
            ),
            "max_manifest_canonical_bytes": integer(
                max_manifest_canonical_bytes,
                "V32_COMPACTION_POLICY_MANIFEST_LIMIT_INVALID",
                minimum=4096,
                maximum=1_048_576,
            ),
            "max_agent_context_canonical_bytes": integer(
                max_agent_context_canonical_bytes,
                "V32_COMPACTION_POLICY_AGENT_LIMIT_INVALID",
                minimum=2048,
                maximum=4 * 1024 * 1024,
            ),
            "complete_original_replay_required": True,
            "complete_recursive_leaf_coverage_required": True,
            "original_artifacts_retained_write_once": True,
            "caller_inventory_forbidden": True,
            "dictionary_equality_creates_dependency": False,
            "dependency_closure_may_be_split": True,
            "dependency_closure_split_requires_forced_full_delivery": True,
            "oversized_leaf_byte_range_fragmentation_required": True,
            "caller_may_remove_policy_roots": False,
            "top_k_or_truncation_allowed": False,
            "chat_summary_as_evidence_allowed": False,
            "capacity_failure_status": "CONTEXT_CAPACITY_UNRESOLVED",
            "compaction_is_authority": False,
            **boundary(),
        }
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        raise V32ContextCompactionError(
            "V32_COMPACTION_POLICY_INPUT_INVALID"
        ) from exc
    return self_digest(document, POLICY_DIGEST_FIELD)


def verify_v32_context_compaction_policy_v1(document: Mapping[str, Any]) -> str:
    try:
        supplied = verify_self_digest(document, POLICY_DIGEST_FIELD)
        verify_boundary(document, "V32_COMPACTION_POLICY_BOUNDARY_INVALID")
        rebuilt = build_v32_context_compaction_policy_v1(
            policy_id=document["policy_id"],
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
            max_shard_canonical_bytes=document["max_shard_canonical_bytes"],
            max_manifest_canonical_bytes=document[
                "max_manifest_canonical_bytes"
            ],
            max_agent_context_canonical_bytes=document[
                "max_agent_context_canonical_bytes"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ContextCompactionError):
            raise
        raise V32ContextCompactionError("V32_COMPACTION_POLICY_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[POLICY_DIGEST_FIELD]:
        raise V32ContextCompactionError(
            "V32_COMPACTION_POLICY_REPLAY_MISMATCH"
        )
    return supplied


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _leaves(value: Any, pointer: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, Mapping):
        if not value:
            return [(pointer or "", {})]
        rows: list[tuple[str, Any]] = []
        for key in sorted(value):
            rows.extend(_leaves(value[key], f"{pointer}/{_pointer_token(key)}"))
        return rows
    if isinstance(value, (list, tuple)):
        if not value:
            return [(pointer or "", [])]
        rows = []
        for index, item in enumerate(value):
            rows.extend(_leaves(item, f"{pointer}/{index}"))
        return rows
    canonical_bytes(value)
    return [(pointer or "", value)]


def _role(pointer: str, value: Any) -> str:
    lowered = pointer.lower()
    rendered = value.lower() if isinstance(value, str) else ""
    if "unknown" in lowered or "unknown" in rendered:
        return "UNKNOWN"
    if any(token in lowered for token in ("opposing", "opposite", "runner_up")):
        return "OPPOSING_HYPOTHESIS"
    if any(token in lowered for token in ("falsifier", "invalidation", "falsification")):
        return "FALSIFIER"
    if any(
        token in lowered
        for token in ("conflict", "contradict", "disagreement", "counterevidence")
    ):
        return "CONFLICT"
    if any(
        token in lowered
        for token in (
            "hazard",
            "latency",
            "network_failure",
            "stop_through",
            "gap_risk",
            "max_loss",
        )
    ):
        return "HAZARD"
    if any(token in lowered for token in ("hypotheses", "hypothesis", "thesis")):
        return "HYPOTHESIS"
    if any(
        token in lowered
        for token in (
            "dependency",
            "closure",
            "evidence_refs",
            "source_refs",
            "member_",
        )
    ):
        return "CLOSURE"
    if any(token in lowered for token in ("bars", "candles", "series", "history")):
        return "TIME_SERIES"
    if any(
        lowered.endswith(token)
        for token in (
            "/schema_id",
            "/schema_version",
            "/run_id",
            "/cycle_index",
            "/created_at",
            "/as_of",
            "/available_at",
            "/observed_at",
        )
    ) or lowered.endswith("_digest"):
        return "METADATA"
    return "DATA"


def _source_rows_and_documents(
    source_artifacts: Any, original_documents: Any
) -> list[tuple[dict[str, Any], Mapping[str, Any]]]:
    if (
        isinstance(source_artifacts, (str, bytes))
        or not isinstance(source_artifacts, Sequence)
        or isinstance(original_documents, (str, bytes))
        or not isinstance(original_documents, Sequence)
        or not source_artifacts
        or len(source_artifacts) != len(original_documents)
        or len(source_artifacts) > MAX_SOURCE_ARTIFACTS
    ):
        raise V32ContextCompactionError("V32_COMPACTION_SOURCE_SET_INVALID")
    unused = list(original_documents)
    pairs: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
    for item in source_artifacts:
        if not isinstance(item, Mapping) or set(item) != {
            "artifact_binding",
            "canonical_bytes",
        }:
            raise V32ContextCompactionError("V32_COMPACTION_SOURCE_INVALID")
        artifact_binding = binding(
            item["artifact_binding"], "V32_COMPACTION_SOURCE_INVALID"
        )
        declared_bytes = integer(
            item["canonical_bytes"],
            "V32_COMPACTION_SOURCE_INVALID",
            minimum=1,
            maximum=32 * 1024 * 1024,
        )
        matches: list[tuple[int, Mapping[str, Any]]] = []
        for index, document in enumerate(unused):
            if not isinstance(document, Mapping):
                continue
            try:
                supplied = verify_self_digest(
                    document, artifact_binding["digest_field"]
                )
            except (CanonicalContractError, TypeError, ValueError):
                continue
            if (
                document.get("schema_id") == artifact_binding["schema_id"]
                and supplied == artifact_binding["semantic_digest"]
                and _physical(document) == artifact_binding["physical_sha256"]
                and len(canonical_bytes(dict(document))) == declared_bytes
            ):
                matches.append((index, document))
        if len(matches) != 1:
            raise V32ContextCompactionError(
                "V32_COMPACTION_ORIGINAL_REPLAY_MISMATCH"
            )
        index, document = matches[0]
        unused.pop(index)
        pairs.append(
            (
                {
                    "artifact_binding": artifact_binding,
                    "canonical_bytes": declared_bytes,
                },
                document,
            )
        )
    if unused:
        raise V32ContextCompactionError("V32_COMPACTION_ORIGINAL_SET_MISMATCH")
    pairs.sort(
        key=lambda pair: (
            pair[0]["artifact_binding"]["schema_id"],
            pair[0]["artifact_binding"]["semantic_digest"],
            pair[0]["artifact_binding"]["relative_ref"],
        )
    )
    identities = [
        (
            row["artifact_binding"]["schema_id"],
            row["artifact_binding"]["semantic_digest"],
            row["artifact_binding"]["physical_sha256"],
        )
        for row, _ in pairs
    ]
    if len(identities) != len(set(identities)):
        raise V32ContextCompactionError("V32_COMPACTION_SOURCE_DUPLICATE")
    return pairs


def _extract_members(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    members: list[dict[str, Any]] = []
    dictionary: dict[str, Any] = {}
    coverage: list[dict[str, Any]] = []
    for source, document in pairs:
        artifact = source["artifact_binding"]
        source_digest = artifact["semantic_digest"]
        source_members: list[str] = []
        role_counts = {role: 0 for role in sorted(SEMANTIC_ROLES)}
        for pointer, leaf in _leaves(document):
            value_digest = canonical_digest(leaf)
            dictionary[value_digest] = leaf
            semantic_role = _role(pointer, leaf)
            member_id = "leaf:" + canonical_digest(
                {"source_artifact_semantic_digest": source_digest, "json_pointer": pointer}
            )
            source_members.append(member_id)
            role_counts[semantic_role] += 1
            members.append(
                {
                    "member_id": member_id,
                    "source_artifact_semantic_digest": source_digest,
                    "json_pointer": pointer,
                    "semantic_role": semantic_role,
                    "dictionary_value_digest": value_digest,
                    "dependency_refs": [],
                }
            )
        coverage.append(
            {
                "source_artifact_semantic_digest": source_digest,
                "source_schema_id": artifact["schema_id"],
                "root_json_pointer": "",
                "leaf_count": len(source_members),
                "member_ids_digest": canonical_digest(sorted(source_members)),
                "role_counts": role_counts,
                "complete_recursive_leaf_coverage": True,
            }
        )
    if len(members) > MAX_MEMBERS:
        raise V32ContextCompactionError("CONTEXT_CAPACITY_UNRESOLVED")
    members.sort(key=lambda row: row["member_id"])
    by_source_pointer = {
        (row["source_artifact_semantic_digest"], row["json_pointer"]): row
        for row in members
    }
    identifier_values: dict[str, list[str]] = {}
    for row in members:
        key = row["json_pointer"].rsplit("/", 1)[-1].lower()
        value = dictionary[row["dictionary_value_digest"]]
        if isinstance(value, str) and (
            key.endswith("_id") or key.endswith("_digest") or key == "id"
        ):
            identifier_values.setdefault(value, []).append(row["member_id"])
    identifier_anchors = {
        value: min(member_ids) for value, member_ids in identifier_values.items()
    }
    # Only explicit identifier/reference semantics create edges.  Repeated
    # identifiers form a star around one deterministic anchor, not an O(n^2)
    # clique; equal non-identifier dictionary values never create an edge.
    for row in members:
        pointer = row["json_pointer"]
        key = pointer.rsplit("/", 1)[-1].lower()
        value = dictionary[row["dictionary_value_digest"]]
        dependencies: set[str] = set()
        if isinstance(value, str) and (
            "ref" in key or key.endswith("_id") or key.endswith("_digest")
        ):
            anchor = identifier_anchors.get(value)
            if anchor is not None and anchor != row["member_id"]:
                dependencies.add(anchor)
        if row["semantic_role"] in POLICY_REQUIRED_ROOT_ROLES:
            parent = pointer.rsplit("/", 1)[0]
            for (source_digest, candidate_pointer), candidate in by_source_pointer.items():
                if (
                    source_digest == row["source_artifact_semantic_digest"]
                    and candidate_pointer.rsplit("/", 1)[0] == parent
                    and candidate_pointer.rsplit("/", 1)[-1].lower().endswith("_id")
                ):
                    dependencies.add(candidate["member_id"])
        dependencies.discard(row["member_id"])
        row["dependency_refs"] = sorted(dependencies)
    coverage.sort(key=lambda row: row["source_artifact_semantic_digest"])
    return members, dictionary, coverage


def _closures(rows: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    neighbors = {str(row["member_id"]): set(row["dependency_refs"]) for row in rows}
    for member_id, linked in tuple(neighbors.items()):
        for other in linked:
            if other not in neighbors:
                raise V32ContextCompactionError(
                    "V32_COMPACTION_DEPENDENCY_NOT_IN_INVENTORY"
                )
            neighbors[other].add(member_id)
    remaining = set(neighbors)
    result: list[list[str]] = []
    while remaining:
        seed = min(remaining)
        stack = [seed]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(sorted(neighbors[current] - component, reverse=True))
        remaining -= component
        result.append(sorted(component))
    return sorted(result, key=lambda group: group[0])


def _canonical_array_size(*, item_count: int, item_bytes: int) -> int:
    return 2 + item_bytes + max(0, item_count - 1)


def _canonical_object_size(value_sizes: Mapping[str, int]) -> int:
    return (
        2
        + max(0, len(value_sizes) - 1)
        + sum(
            len(canonical_bytes(key)) + 1 + value_size
            for key, value_size in value_sizes.items()
        )
    )


def _fits_shard_limit(*, estimated_canonical_bytes: int, shard_limit: int) -> bool:
    return estimated_canonical_bytes <= shard_limit


def _shard_canonical_size_from_parts(
    *,
    run_id: str,
    cycle_index: int,
    created_at: str,
    shard_index: int,
    member_count: int,
    member_row_bytes: int,
    member_id_bytes: int,
    dictionary_entry_count: int,
    dictionary_entry_bytes: int,
    dependency_closure_complete: bool,
) -> int:
    """Exact shard size without repeatedly rebuilding the growing shard.

    Array item order affects the digest but never the byte count.  Both digest
    fields always contain a 64-character lowercase hex value, so a fixed valid
    placeholder has the exact serialized width of the final value.  The final
    shard is still built and self-digested once after its boundary is chosen.
    """

    values: dict[str, Any] = {
        "schema_id": SHARD_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle_index,
        "shard_id": f"context-shard-{shard_index:04d}",
        "shard_index": shard_index,
        "created_at": created_at,
        "member_ids_digest": "0" * 64,
        "dependency_closure_complete": dependency_closure_complete,
        "cross_shard_dependencies_resolved_by_forced_full_delivery": True,
        "dictionary_equality_creates_dependency": False,
        "lossless_structural_projection": True,
        **boundary(),
        SHARD_DIGEST_FIELD: "0" * 64,
    }
    value_sizes = {key: len(canonical_bytes(value)) for key, value in values.items()}
    value_sizes.update(
        {
            "member_rows": _canonical_array_size(
                item_count=member_count, item_bytes=member_row_bytes
            ),
            "member_ids": _canonical_array_size(
                item_count=member_count, item_bytes=member_id_bytes
            ),
            "dictionary_entries": _canonical_array_size(
                item_count=dictionary_entry_count,
                item_bytes=dictionary_entry_bytes,
            ),
        }
    )
    return _canonical_object_size(value_sizes)


def _build_shard(
    *,
    run_id: str,
    cycle_index: int,
    created_at: str,
    shard_index: int,
    rows: Sequence[Mapping[str, Any]],
    dictionary: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_rows = [dict(row) for row in sorted(rows, key=lambda row: row["member_id"])]
    local_member_ids = {row["member_id"] for row in normalized_rows}
    dependency_closure_complete = all(
        set(row["dependency_refs"]).issubset(local_member_ids)
        for row in normalized_rows
    )
    value_digests = sorted({row["dictionary_value_digest"] for row in normalized_rows})
    return self_digest(
        {
            "schema_id": SHARD_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "cycle_index": cycle_index,
            "shard_id": f"context-shard-{shard_index:04d}",
            "shard_index": shard_index,
            "created_at": created_at,
            "member_rows": normalized_rows,
            "member_ids": [row["member_id"] for row in normalized_rows],
            "member_ids_digest": canonical_digest(
                [row["member_id"] for row in normalized_rows]
            ),
            "dictionary_entries": [
                {"value_digest": value_digest, "value": dictionary[value_digest]}
                for value_digest in value_digests
            ],
            "dependency_closure_complete": dependency_closure_complete,
            "cross_shard_dependencies_resolved_by_forced_full_delivery": True,
            "dictionary_equality_creates_dependency": False,
            "lossless_structural_projection": True,
            **boundary(),
        },
        SHARD_DIGEST_FIELD,
    )


def _fragment_oversized_members(
    *,
    run_id: str,
    cycle_index: int,
    created_at: str,
    members: Sequence[Mapping[str, Any]],
    dictionary: Mapping[str, Any],
    coverage: Sequence[Mapping[str, Any]],
    shard_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[str]]:
    """Split only an otherwise-unshardable leaf into exact canonical byte ranges."""

    replacements: dict[str, list[dict[str, Any]]] = {}
    fragment_dictionary: dict[str, Any] = dict(dictionary)
    unfragmentable: list[str] = []
    for supplied in members:
        row = dict(supplied)
        if len(
            canonical_bytes(
                _build_shard(
                    run_id=run_id,
                    cycle_index=cycle_index,
                    created_at=created_at,
                    shard_index=0,
                    rows=[row],
                    dictionary=fragment_dictionary,
                )
            )
        ) <= shard_limit:
            replacements[row["member_id"]] = [row]
            continue
        raw = canonical_bytes(fragment_dictionary[row["dictionary_value_digest"]])
        capacity = max(1, ((shard_limit - 1_400) * 3) // 4)
        fragments: list[dict[str, Any]] | None = None
        while capacity >= 1:
            chunks = [raw[start : start + capacity] for start in range(0, len(raw), capacity)]
            if len(chunks) > MAX_MEMBERS:
                break
            candidate_rows: list[dict[str, Any]] = []
            cursor = 0
            count = len(chunks)
            for index, chunk in enumerate(chunks):
                encoded = base64.b64encode(chunk).decode("ascii")
                encoded_digest = canonical_digest(encoded)
                fragment_dictionary[encoded_digest] = encoded
                end = cursor + len(chunk)
                fragment_identity = {
                    "original_member_id": row["member_id"],
                    "fragment_index": index,
                    "fragment_count": count,
                    "byte_start": cursor,
                    "byte_end": end,
                }
                candidate_rows.append(
                    {
                        **row,
                        "member_id": "fragment:" + canonical_digest(fragment_identity),
                        "dictionary_value_digest": encoded_digest,
                        "dependency_refs": [],
                        "value_projection": (
                            "BASE64_CANONICAL_JSON_UTF8_BYTE_RANGE"
                        ),
                        "original_member_id": row["member_id"],
                        "original_dictionary_value_digest": row[
                            "dictionary_value_digest"
                        ],
                        "fragment_index": index,
                        "fragment_count": count,
                        "byte_start": cursor,
                        "byte_end": end,
                        "complete_canonical_value_bytes": len(raw),
                        "complete_canonical_value_sha256": hashlib.sha256(
                            raw
                        ).hexdigest(),
                    }
                )
                cursor = end
            for index, fragment in enumerate(candidate_rows):
                dependencies = set(row["dependency_refs"])
                if index > 0:
                    dependencies.add(candidate_rows[0]["member_id"])
                    dependencies.add(candidate_rows[index - 1]["member_id"])
                dependencies.discard(fragment["member_id"])
                fragment["dependency_refs"] = sorted(dependencies)
            if candidate_rows and all(
                len(
                    canonical_bytes(
                        _build_shard(
                            run_id=run_id,
                            cycle_index=cycle_index,
                            created_at=created_at,
                            shard_index=0,
                            rows=[fragment],
                            dictionary=fragment_dictionary,
                        )
                    )
                )
                <= shard_limit
                for fragment in candidate_rows
            ):
                fragments = candidate_rows
                break
            if capacity == 1:
                break
            capacity = max(1, capacity // 2)
        if fragments is None:
            replacements[row["member_id"]] = [row]
            unfragmentable.append(row["member_id"])
        else:
            replacements[row["member_id"]] = fragments

    anchors = {
        original_id: rows[0]["member_id"]
        for original_id, rows in replacements.items()
    }
    projected: list[dict[str, Any]] = []
    for supplied in members:
        original_id = str(supplied["member_id"])
        rows = replacements[original_id]
        remapped_dependencies = {
            anchors.get(str(dependency), str(dependency))
            for dependency in supplied["dependency_refs"]
        }
        for index, fragment in enumerate(rows):
            normalized = dict(fragment)
            dependencies = set(remapped_dependencies)
            if len(rows) > 1 and index > 0:
                dependencies.add(rows[0]["member_id"])
                dependencies.add(rows[index - 1]["member_id"])
            dependencies.discard(normalized["member_id"])
            normalized["dependency_refs"] = sorted(dependencies)
            projected.append(normalized)
    projected.sort(key=lambda row: row["member_id"])
    referenced_value_digests = {
        row["dictionary_value_digest"] for row in projected
    }
    projected_dictionary = {
        digest: fragment_dictionary[digest]
        for digest in sorted(referenced_value_digests)
    }
    projected_coverage: list[dict[str, Any]] = []
    for supplied in coverage:
        row = dict(supplied)
        source_rows = [
            member
            for member in projected
            if member["source_artifact_semantic_digest"]
            == row["source_artifact_semantic_digest"]
        ]
        member_ids = sorted(member["member_id"] for member in source_rows)
        fragment_rows = [
            member for member in source_rows if "original_member_id" in member
        ]
        row.update(
            {
                "projected_member_count": len(source_rows),
                "member_ids_digest": canonical_digest(member_ids),
                "projected_role_counts": {
                    role: sum(
                        member["semantic_role"] == role for member in source_rows
                    )
                    for role in sorted(SEMANTIC_ROLES)
                },
                "fragmented_leaf_count": len(
                    {member["original_member_id"] for member in fragment_rows}
                ),
                "fragment_member_count": len(fragment_rows),
                "complete_recursive_leaf_coverage": True,
                "exact_fragment_reassembly_required": True,
            }
        )
        projected_coverage.append(row)
    return projected, projected_dictionary, projected_coverage, sorted(unfragmentable)


def _projected_leaf_reassembly_rows(
    members: Sequence[Mapping[str, Any]], dictionary: Mapping[str, Any]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in members:
        grouped.setdefault(
            (
                str(row["source_artifact_semantic_digest"]),
                str(row["json_pointer"]),
            ),
            [],
        ).append(row)
    reassembled: list[dict[str, Any]] = []
    for (source_digest, pointer), rows in sorted(grouped.items()):
        fragment_flags = ["original_member_id" in row for row in rows]
        if any(fragment_flags):
            if not all(fragment_flags):
                raise V32ContextCompactionError(
                    "V32_COMPACTION_FRAGMENT_SET_INVALID"
                )
            ordered = sorted(rows, key=lambda row: row["fragment_index"])
            count = len(ordered)
            first = ordered[0]
            cursor = 0
            parts: list[bytes] = []
            for index, row in enumerate(ordered):
                encoded = dictionary.get(row["dictionary_value_digest"])
                try:
                    part = base64.b64decode(encoded, validate=True)
                except (TypeError, ValueError) as exc:
                    raise V32ContextCompactionError(
                        "V32_COMPACTION_FRAGMENT_VALUE_INVALID"
                    ) from exc
                identity = {
                    "original_member_id": row["original_member_id"],
                    "fragment_index": index,
                    "fragment_count": count,
                    "byte_start": cursor,
                    "byte_end": cursor + len(part),
                }
                if (
                    row.get("value_projection")
                    != "BASE64_CANONICAL_JSON_UTF8_BYTE_RANGE"
                    or row.get("fragment_index") != index
                    or row.get("fragment_count") != count
                    or row.get("byte_start") != cursor
                    or row.get("byte_end") != cursor + len(part)
                    or row.get("member_id")
                    != "fragment:" + canonical_digest(identity)
                    or row.get("original_member_id")
                    != first.get("original_member_id")
                    or row.get("original_dictionary_value_digest")
                    != first.get("original_dictionary_value_digest")
                    or row.get("complete_canonical_value_bytes")
                    != first.get("complete_canonical_value_bytes")
                    or row.get("complete_canonical_value_sha256")
                    != first.get("complete_canonical_value_sha256")
                ):
                    raise V32ContextCompactionError(
                        "V32_COMPACTION_FRAGMENT_RANGE_INVALID"
                    )
                parts.append(part)
                cursor += len(part)
            raw = b"".join(parts)
            if (
                len(raw) != first["complete_canonical_value_bytes"]
                or hashlib.sha256(raw).hexdigest()
                != first["complete_canonical_value_sha256"]
                or hashlib.sha256(raw).hexdigest()
                != first["original_dictionary_value_digest"]
            ):
                raise V32ContextCompactionError(
                    "V32_COMPACTION_FRAGMENT_REASSEMBLY_INVALID"
                )
            value_digest = first["original_dictionary_value_digest"]
        else:
            if len(rows) != 1:
                raise V32ContextCompactionError(
                    "V32_COMPACTION_MEMBER_POINTER_DUPLICATE"
                )
            value = dictionary.get(rows[0]["dictionary_value_digest"])
            raw = canonical_bytes(value)
            value_digest = rows[0]["dictionary_value_digest"]
            if hashlib.sha256(raw).hexdigest() != value_digest:
                raise V32ContextCompactionError(
                    "V32_COMPACTION_DICTIONARY_VALUE_INVALID"
                )
        reassembled.append(
            {
                "source_artifact_semantic_digest": source_digest,
                "json_pointer": pointer,
                "canonical_value_bytes": len(raw),
                "canonical_value_sha256": value_digest,
            }
        )
    return reassembled


def _expected_leaf_reassembly_rows(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, document in pairs:
        source_digest = source["artifact_binding"]["semantic_digest"]
        for pointer, value in _leaves(document):
            raw = canonical_bytes(value)
            rows.append(
                {
                    "source_artifact_semantic_digest": source_digest,
                    "json_pointer": pointer,
                    "canonical_value_bytes": len(raw),
                    "canonical_value_sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row["source_artifact_semantic_digest"], row["json_pointer"]
        ),
    )


def build_v32_context_compaction_bundle_v1(
    *,
    run_id: str,
    cycle_index: int,
    created_at: str,
    source_artifacts: Sequence[Mapping[str, Any]],
    original_documents: Sequence[Mapping[str, Any]],
    max_shard_canonical_bytes: int = DEFAULT_MAX_SHARD_CANONICAL_BYTES,
    max_manifest_canonical_bytes: int = MAX_MANIFEST_CANONICAL_BYTES,
) -> dict[str, Any]:
    try:
        run = text(run_id, "V32_COMPACTION_RUN_INVALID")
        cycle = integer(
            cycle_index, "V32_COMPACTION_CYCLE_INVALID", minimum=1, maximum=16
        )
        created = time(created_at, "V32_COMPACTION_TIME_INVALID")
        shard_limit = integer(
            max_shard_canonical_bytes,
            "V32_COMPACTION_SHARD_LIMIT_INVALID",
            minimum=2048,
            maximum=262_144,
        )
        manifest_limit = integer(
            max_manifest_canonical_bytes,
            "V32_COMPACTION_MANIFEST_LIMIT_INVALID",
            minimum=4096,
            maximum=1_048_576,
        )
        pairs = _source_rows_and_documents(source_artifacts, original_documents)
        members, dictionary, coverage = _extract_members(pairs)
    except (V32AuthorizedRevisionContractError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ContextCompactionError):
            raise
        raise V32ContextCompactionError("V32_COMPACTION_INPUT_INVALID") from exc
    members, dictionary, coverage, unfragmentable = _fragment_oversized_members(
        run_id=run,
        cycle_index=cycle,
        created_at=created,
        members=members,
        dictionary=dictionary,
        coverage=coverage,
        shard_limit=shard_limit,
    )
    if len(members) > MAX_MEMBERS:
        raise V32ContextCompactionError("CONTEXT_CAPACITY_UNRESOLVED")
    reassembly_rows = _projected_leaf_reassembly_rows(members, dictionary)
    expected_reassembly_rows = _expected_leaf_reassembly_rows(pairs)
    if reassembly_rows != expected_reassembly_rows:
        raise V32ContextCompactionError(
            "V32_COMPACTION_FRAGMENT_REASSEMBLY_INVALID"
        )
    closure_groups = _closures(members)
    shards: list[dict[str, Any]] = []
    pending: list[Mapping[str, Any]] = []
    unresolved: list[str] = []

    member_row_sizes = {
        str(row["member_id"]): len(canonical_bytes(dict(row))) for row in members
    }
    member_id_sizes = {
        str(row["member_id"]): len(canonical_bytes(row["member_id"]))
        for row in members
    }
    dictionary_entry_sizes = {
        value_digest: len(
            canonical_bytes(
                {
                    "value_digest": value_digest,
                    "value": dictionary[value_digest],
                }
            )
        )
        for value_digest in dictionary
    }
    pending_row_bytes = 0
    pending_id_bytes = 0
    pending_dictionary_bytes = 0
    pending_ids: set[str] = set()
    pending_value_digests: set[str] = set()
    pending_unresolved_dependencies: set[str] = set()

    def candidate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return _build_shard(
            run_id=run,
            cycle_index=cycle,
            created_at=created,
            shard_index=len(shards),
            rows=rows,
            dictionary=dictionary,
        )

    # Selection is forced-full and sequential, so dependency references may
    # cross a shard boundary without any information loss.  Co-locating an
    # entire connected component made a large, valid canonical Agent packet
    # permanently unshardable.  Capacity is therefore applied to one member
    # row at a time; only an individual member that cannot fit fails closed.
    for member in members:
        member_id = str(member["member_id"])
        value_digest = str(member["dictionary_value_digest"])
        dependency_refs = {
            str(value) for value in member["dependency_refs"]
        }
        new_unresolved_dependencies = {
            value
            for value in dependency_refs
            if value != member_id
            and value not in pending_ids
            and value not in pending_unresolved_dependencies
        }
        tentative_unresolved_count = (
            len(pending_unresolved_dependencies)
            - int(member_id in pending_unresolved_dependencies)
            + len(new_unresolved_dependencies)
        )
        value_is_new = value_digest not in pending_value_digests
        tentative_size = _shard_canonical_size_from_parts(
            run_id=run,
            cycle_index=cycle,
            created_at=created,
            shard_index=len(shards),
            member_count=len(pending) + 1,
            member_row_bytes=(
                pending_row_bytes + member_row_sizes[member_id]
            ),
            member_id_bytes=pending_id_bytes + member_id_sizes[member_id],
            dictionary_entry_count=(
                len(pending_value_digests) + int(value_is_new)
            ),
            dictionary_entry_bytes=(
                pending_dictionary_bytes
                + (
                    dictionary_entry_sizes[value_digest]
                    if value_is_new
                    else 0
                )
            ),
            dependency_closure_complete=(tentative_unresolved_count == 0),
        )
        if _fits_shard_limit(
            estimated_canonical_bytes=tentative_size,
            shard_limit=shard_limit,
        ):
            pending = [*pending, member]
            pending_row_bytes += member_row_sizes[member_id]
            pending_id_bytes += member_id_sizes[member_id]
            if value_is_new:
                pending_value_digests.add(value_digest)
                pending_dictionary_bytes += dictionary_entry_sizes[value_digest]
            pending_ids.add(member_id)
            pending_unresolved_dependencies.discard(member_id)
            pending_unresolved_dependencies.update(
                value
                for value in dependency_refs
                if value not in pending_ids
            )
            continue
        if pending:
            sealed_pending = candidate(pending)
            if len(canonical_bytes(sealed_pending)) > shard_limit:
                raise V32ContextCompactionError(
                    "V32_COMPACTION_SHARD_SIZE_ESTIMATE_INVALID"
                )
            shards.append(sealed_pending)
            pending = []
            pending_row_bytes = 0
            pending_id_bytes = 0
            pending_dictionary_bytes = 0
            pending_ids.clear()
            pending_value_digests.clear()
            pending_unresolved_dependencies.clear()
        single_size = _shard_canonical_size_from_parts(
            run_id=run,
            cycle_index=cycle,
            created_at=created,
            shard_index=len(shards),
            member_count=1,
            member_row_bytes=member_row_sizes[member_id],
            member_id_bytes=member_id_sizes[member_id],
            dictionary_entry_count=1,
            dictionary_entry_bytes=dictionary_entry_sizes[value_digest],
            dependency_closure_complete=dependency_refs.issubset({member_id}),
        )
        if not _fits_shard_limit(
            estimated_canonical_bytes=single_size,
            shard_limit=shard_limit,
        ):
            unresolved.append(member["member_id"])
        else:
            pending = [member]
            pending_row_bytes = member_row_sizes[member_id]
            pending_id_bytes = member_id_sizes[member_id]
            pending_dictionary_bytes = dictionary_entry_sizes[value_digest]
            pending_ids.add(member_id)
            pending_value_digests.add(value_digest)
            pending_unresolved_dependencies.update(
                value for value in dependency_refs if value != member_id
            )
    if pending and not unresolved:
        sealed_pending = candidate(pending)
        if len(canonical_bytes(sealed_pending)) > shard_limit:
            raise V32ContextCompactionError(
                "V32_COMPACTION_SHARD_SIZE_ESTIMATE_INVALID"
            )
        shards.append(sealed_pending)
    if len(shards) > MAX_SHARDS:
        unresolved = [row["member_id"] for row in members]
    unresolved = sorted(set(unresolved))
    if unresolved:
        shards = []
    sources = [dict(row) for row, _ in pairs]
    member_ids = [row["member_id"] for row in members]
    policy_roots = sorted(
        row["member_id"]
        for row in members
        if row["semantic_role"] in POLICY_REQUIRED_ROOT_ROLES
    )
    role_counts = {
        role: sum(row["semantic_role"] == role for row in members)
        for role in sorted(SEMANTIC_ROLES)
    }
    descriptors = [
        {
            "relative_ref": f"context-compaction/shards/{shard['shard_id']}.json",
            "schema_id": SHARD_SCHEMA_ID,
            "digest_field": SHARD_DIGEST_FIELD,
            "semantic_digest": shard[SHARD_DIGEST_FIELD],
            "physical_sha256": _physical(shard),
            "canonical_bytes": len(canonical_bytes(shard)),
            "member_count": len(shard["member_ids"]),
            "member_ids_digest": shard["member_ids_digest"],
        }
        for shard in shards
    ]
    manifest = self_digest(
        {
            "schema_id": MANIFEST_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": run,
            "cycle_index": cycle,
            "created_at": created,
            "status": (
                "READY_LOSSLESS_SHARDED"
                if not unresolved
                else "CONTEXT_CAPACITY_UNRESOLVED"
            ),
            "source_artifacts": sources,
            "source_artifact_identity_digest": canonical_digest(sources),
            "source_coverage_proofs": coverage,
            "source_coverage_proofs_digest": canonical_digest(coverage),
            "original_leaf_count": sum(row["leaf_count"] for row in coverage),
            "projected_member_count": len(members),
            "fragmented_leaf_count": sum(
                row["fragmented_leaf_count"] for row in coverage
            ),
            "fragment_member_count": sum(
                row["fragment_member_count"] for row in coverage
            ),
            "fragment_reassembly_rows_digest": canonical_digest(reassembly_rows),
            "exact_fragment_reassembly_verified": True,
            "deterministic_canonical_byte_range_fragmentation": True,
            "unfragmentable_original_member_ids": unfragmentable,
            "unfragmentable_original_member_ids_digest": canonical_digest(
                unfragmentable
            ),
            "original_artifacts_retained_write_once": True,
            "full_original_replay_required_for_acceptance": True,
            "compaction_steps": list(COMPACTION_STEPS),
            "caller_supplied_member_inventory_allowed": False,
            "arbitrary_top_k_forbidden": True,
            "chat_summary_as_evidence_forbidden": True,
            "dictionary_equality_creates_dependency": False,
            "loss_boundary": "LOSSLESS_STRUCTURAL_ONLY_NO_SEMANTIC_DELETION",
            "member_count": len(members),
            "member_inventory_digest": canonical_digest(members),
            "folded_member_ids_digest": canonical_digest(member_ids),
            "unique_dictionary_value_count": len(dictionary),
            "deduplicated_member_count": len(members) - len(dictionary),
            "semantic_role_counts": role_counts,
            "policy_required_root_roles": sorted(POLICY_REQUIRED_ROOT_ROLES),
            "policy_required_member_ids": policy_roots,
            "policy_required_member_ids_digest": canonical_digest(policy_roots),
            "dependency_closure_count": len(closure_groups),
            "dependency_closure_digest": canonical_digest(closure_groups),
            "dependency_closure_colocation_required": False,
            "cross_shard_dependencies_allowed_only_with_forced_full_delivery": True,
            "shard_descriptors": descriptors,
            "shard_count": len(shards),
            "max_shard_canonical_bytes": shard_limit,
            "unresolved_member_ids": sorted(unresolved),
            "unresolved_member_ids_digest": canonical_digest(sorted(unresolved)),
            "manual_escalation_required": bool(unresolved),
            "max_manifest_canonical_bytes": manifest_limit,
            "compaction_is_authority": False,
            **boundary(),
        },
        MANIFEST_DIGEST_FIELD,
    )
    if len(canonical_bytes(manifest)) > manifest_limit:
        raise V32ContextCompactionError("CONTEXT_CAPACITY_UNRESOLVED")
    return {"manifest": manifest, "shards": shards}


def verify_v32_context_compaction_bundle_v1(
    manifest: Mapping[str, Any],
    shards: Sequence[Mapping[str, Any]],
    *,
    original_documents: Sequence[Mapping[str, Any]],
) -> str:
    try:
        supplied = verify_self_digest(manifest, MANIFEST_DIGEST_FIELD)
        verify_boundary(manifest, "V32_COMPACTION_BOUNDARY_INVALID")
        rebuilt = build_v32_context_compaction_bundle_v1(
            run_id=manifest["run_id"],
            cycle_index=manifest["cycle_index"],
            created_at=manifest["created_at"],
            source_artifacts=manifest["source_artifacts"],
            original_documents=original_documents,
            max_shard_canonical_bytes=manifest["max_shard_canonical_bytes"],
            max_manifest_canonical_bytes=manifest["max_manifest_canonical_bytes"],
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ContextCompactionError):
            raise
        raise V32ContextCompactionError("V32_COMPACTION_BUNDLE_INVALID") from exc
    if dict(manifest) != rebuilt["manifest"] or list(shards) != rebuilt["shards"]:
        raise V32ContextCompactionError("V32_COMPACTION_RECONSTRUCTION_MISMATCH")
    if (
        manifest["source_artifact_identity_digest"]
        != canonical_digest(manifest["source_artifacts"])
        or manifest["source_coverage_proofs_digest"]
        != canonical_digest(manifest["source_coverage_proofs"])
    ):
        raise V32ContextCompactionError("V32_COMPACTION_PROOF_INVALID")
    if manifest["status"] == "READY_LOSSLESS_SHARDED":
        rows = [row for shard in shards for row in shard["member_rows"]]
        closures = _closures(rows)
        projected_dictionary: dict[str, Any] = {}
        for shard in shards:
            for entry in shard["dictionary_entries"]:
                value_digest = entry["value_digest"]
                value = entry["value"]
                if (
                    canonical_digest(value) != value_digest
                    or (
                        value_digest in projected_dictionary
                        and projected_dictionary[value_digest] != value
                    )
                ):
                    raise V32ContextCompactionError(
                        "V32_COMPACTION_DICTIONARY_VALUE_INVALID"
                    )
                projected_dictionary[value_digest] = value
        reassembly_rows = _projected_leaf_reassembly_rows(
            rows, projected_dictionary
        )
        if (
            len(closures) != manifest["dependency_closure_count"]
            or canonical_digest(closures) != manifest["dependency_closure_digest"]
            or reassembly_rows != _expected_leaf_reassembly_rows(
                _source_rows_and_documents(
                    manifest["source_artifacts"], original_documents
                )
            )
            or canonical_digest(reassembly_rows)
            != manifest["fragment_reassembly_rows_digest"]
            or manifest["unfragmentable_original_member_ids"]
        ):
            raise V32ContextCompactionError("V32_COMPACTION_CLOSURE_PROOF_INVALID")
    return supplied


def build_v32_context_shard_selection_v1(
    *,
    manifest: Mapping[str, Any],
    manifest_binding: Mapping[str, Any],
    shards: Sequence[Mapping[str, Any]],
    original_documents: Sequence[Mapping[str, Any]],
    caller_required_member_ids: Sequence[str],
    selected_at: str,
    max_agent_context_canonical_bytes: int,
    shard_bindings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest_digest = verify_v32_context_compaction_bundle_v1(
        manifest, shards, original_documents=original_documents
    )
    try:
        manifest_ref = binding(
            manifest_binding, "V32_COMPACTION_SELECTION_MANIFEST_BINDING_INVALID"
        )
        if (
            manifest_ref["schema_id"] != MANIFEST_SCHEMA_ID
            or manifest_ref["digest_field"] != MANIFEST_DIGEST_FIELD
            or manifest_ref["semantic_digest"] != manifest_digest
            or manifest_ref["physical_sha256"] != _physical(manifest)
        ):
            raise V32ContextCompactionError(
                "V32_COMPACTION_SELECTION_MANIFEST_BINDING_INVALID"
            )
        if manifest["status"] != "READY_LOSSLESS_SHARDED":
            raise V32ContextCompactionError("CONTEXT_CAPACITY_UNRESOLVED")
        caller_roots = sorted_unique_texts(
            caller_required_member_ids,
            "V32_COMPACTION_SELECTION_CALLER_ROOTS_INVALID",
            allow_empty=True,
            maximum=MAX_MEMBERS,
        )
        inventory_rows = sorted(
            member_id for shard in shards for member_id in shard["member_ids"]
        )
        if (
            len(inventory_rows) != manifest["member_count"]
            or len(inventory_rows) != len(set(inventory_rows))
            or canonical_digest(inventory_rows)
            != manifest["folded_member_ids_digest"]
        ):
            raise V32ContextCompactionError(
                "V32_COMPACTION_SELECTION_INVENTORY_INVALID"
            )
        inventory = set(inventory_rows)
        if any(member_id not in inventory for member_id in caller_roots):
            raise V32ContextCompactionError(
                "V32_COMPACTION_SELECTION_REQUIRED_MEMBER_MISSING"
            )
        policy_roots = list(manifest["policy_required_member_ids"])
        required_roots = sorted(set(policy_roots) | set(caller_roots))
        # A caller may add audit roots, but it may never turn a complete Agent
        # packet into a caller-selected subset.  Every mechanically generated
        # shard is delivered in its canonical shard-index order.
        selected_shards = list(shards)
        selected_member_ids = sorted(
            member_id
            for shard in selected_shards
            for member_id in shard["member_ids"]
        )
        if selected_member_ids != inventory_rows:
            raise V32ContextCompactionError(
                "V32_COMPACTION_SELECTION_INVENTORY_INVALID"
            )
        selected_bytes = sum(len(canonical_bytes(shard)) for shard in selected_shards)
        limit = integer(
            max_agent_context_canonical_bytes,
            "V32_COMPACTION_SELECTION_LIMIT_INVALID",
            minimum=2048,
            maximum=4 * 1024 * 1024,
        )
        if shard_bindings is None:
            normalized_shard_bindings = [
                {
                    "relative_ref": (
                        f"context-compaction/shards/{shard['shard_id']}.json"
                    ),
                    "schema_id": SHARD_SCHEMA_ID,
                    "digest_field": SHARD_DIGEST_FIELD,
                    "semantic_digest": shard[SHARD_DIGEST_FIELD],
                    "physical_sha256": _physical(shard),
                }
                for shard in selected_shards
            ]
        else:
            if (
                isinstance(shard_bindings, (str, bytes))
                or not isinstance(shard_bindings, Sequence)
                or len(shard_bindings) != len(selected_shards)
            ):
                raise V32ContextCompactionError(
                    "V32_COMPACTION_SELECTION_SHARD_BINDINGS_INVALID"
                )
            normalized_shard_bindings = []
            for shard, supplied_binding in zip(
                selected_shards, shard_bindings, strict=True
            ):
                shard_ref = binding(
                    supplied_binding,
                    "V32_COMPACTION_SELECTION_SHARD_BINDINGS_INVALID",
                )
                if (
                    shard_ref["schema_id"] != SHARD_SCHEMA_ID
                    or shard_ref["digest_field"] != SHARD_DIGEST_FIELD
                    or shard_ref["semantic_digest"]
                    != shard[SHARD_DIGEST_FIELD]
                    or shard_ref["physical_sha256"] != _physical(shard)
                ):
                    raise V32ContextCompactionError(
                        "V32_COMPACTION_SELECTION_SHARD_BINDINGS_INVALID"
                    )
                normalized_shard_bindings.append(shard_ref)

        manifest_bytes = len(canonical_bytes(manifest))
        largest_shard_bytes = max(
            (len(canonical_bytes(shard)) for shard in selected_shards), default=0
        )
        base_document = {
            "schema_id": SELECTION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "cycle_index": manifest["cycle_index"],
            "selected_at": time(selected_at, "V32_COMPACTION_SELECTION_TIME_INVALID"),
            "manifest_binding": manifest_ref,
            "selection_status": "READY_FORCED_ALL_SHARDS_SEQUENTIAL",
            "policy_required_root_roles": manifest["policy_required_root_roles"],
            "policy_required_member_ids": policy_roots,
            "caller_required_member_ids": caller_roots,
            "effective_required_member_ids": required_roots,
            "selected_member_count": len(selected_member_ids),
            "selected_member_ids_digest": canonical_digest(selected_member_ids),
            "selected_shard_count": len(selected_shards),
            "selected_shard_bindings": normalized_shard_bindings,
            "selected_shard_bindings_digest": canonical_digest(
                normalized_shard_bindings
            ),
            "aggregate_selected_canonical_bytes": selected_bytes,
            "largest_delivery_unit_canonical_bytes": max(
                manifest_bytes, largest_shard_bytes
            ),
            "max_agent_context_canonical_bytes": limit,
            "complete_manifest_and_shards_verified_before_selection": True,
            "forced_full_member_inventory": True,
            "forced_full_shard_inventory": True,
            "sequential_delivery_required": True,
            "policy_roots_may_be_removed_by_caller": False,
            "truncation_performed": False,
            "manual_escalation_required": False,
            **boundary(),
        }
        ready = self_digest(base_document, SELECTION_DIGEST_FIELD)
        largest_unit = max(
            base_document["largest_delivery_unit_canonical_bytes"],
            len(canonical_bytes(ready)),
        )
        if largest_unit <= limit:
            document = base_document
        else:
            document = {
                **base_document,
                "selection_status": "CONTEXT_CAPACITY_UNRESOLVED",
                "largest_delivery_unit_canonical_bytes": largest_unit,
                "manual_escalation_required": True,
            }
    except (V32AuthorizedRevisionContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ContextCompactionError):
            raise
        raise V32ContextCompactionError("V32_COMPACTION_SELECTION_INVALID") from exc
    return self_digest(document, SELECTION_DIGEST_FIELD)


def verify_v32_context_shard_selection_v1(
    document: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    shards: Sequence[Mapping[str, Any]],
    original_documents: Sequence[Mapping[str, Any]],
) -> str:
    try:
        supplied = verify_self_digest(document, SELECTION_DIGEST_FIELD)
        verify_boundary(document, "V32_COMPACTION_SELECTION_BOUNDARY_INVALID")
        rebuilt = build_v32_context_shard_selection_v1(
            manifest=manifest,
            manifest_binding=document["manifest_binding"],
            shards=shards,
            original_documents=original_documents,
            caller_required_member_ids=document["caller_required_member_ids"],
            selected_at=document["selected_at"],
            max_agent_context_canonical_bytes=document[
                "max_agent_context_canonical_bytes"
            ],
            shard_bindings=document["selected_shard_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ContextCompactionError):
            raise
        raise V32ContextCompactionError(
            "V32_COMPACTION_SELECTION_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[SELECTION_DIGEST_FIELD]:
        raise V32ContextCompactionError(
            "V32_COMPACTION_SELECTION_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "COMPACTION_STEPS",
    "DEFAULT_MAX_SHARD_CANONICAL_BYTES",
    "MANIFEST_DIGEST_FIELD",
    "MANIFEST_SCHEMA_ID",
    "MAX_MANIFEST_CANONICAL_BYTES",
    "MAX_MEMBERS",
    "MAX_SHARDS",
    "MAX_SOURCE_ARTIFACTS",
    "POLICY_REQUIRED_ROOT_ROLES",
    "POLICY_DIGEST_FIELD",
    "POLICY_SCHEMA_ID",
    "SELECTION_DIGEST_FIELD",
    "SELECTION_SCHEMA_ID",
    "SEMANTIC_ROLES",
    "SHARD_DIGEST_FIELD",
    "SHARD_SCHEMA_ID",
    "V32ContextCompactionError",
    "build_v32_context_compaction_bundle_v1",
    "build_v32_context_compaction_policy_v1",
    "build_v32_context_shard_selection_v1",
    "verify_v32_context_compaction_bundle_v1",
    "verify_v32_context_compaction_policy_v1",
    "verify_v32_context_shard_selection_v1",
]
