"""V3.2-only incremental construction for the frozen V3.1 graph contract.

The V3.1 domain module is a frozen runtime path and remains byte-identical.
This adapter first invokes its complete owning verifier on the predecessor,
then validates one delta against verified current heads and proves that the new
graph is exactly the predecessor plus that append.  Historical rows are never
discarded or accepted without the predecessor's complete verification.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..domain import market_knowledge_graph as v31_graph
from ..domain.association_model import (
    AssociationModelError,
    build_association_revision,
)
from ..domain.contracts.canonical import self_digest, verify_self_digest
from ..domain.market_knowledge_graph import (
    MarketKnowledgeGraphError,
    build_graph_node_revision,
)


def _extend_dependency_index(
    prior_index: Mapping[str, Mapping[str, Sequence[str]]],
    node_revisions: Sequence[Mapping[str, Any]],
    association_revisions: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    index = {
        group_id: {
            "node_revision_refs": list(bucket["node_revision_refs"]),
            "association_revision_refs": list(
                bucket["association_revision_refs"]
            ),
        }
        for group_id, bucket in prior_index.items()
    }
    for rows, kind, id_field in (
        (node_revisions, "node_revision_refs", "node_id"),
        (
            association_revisions,
            "association_revision_refs",
            "association_id",
        ),
    ):
        for row in rows:
            revision_ref = f"{row[id_field]}@{row['revision']}"
            for group_id in row["dependency_group_ids"]:
                bucket = index.setdefault(
                    group_id,
                    {
                        "node_revision_refs": [],
                        "association_revision_refs": [],
                    },
                )
                bucket[kind].append(revision_ref)
    return {
        group_id: {
            "node_revision_refs": sorted(set(bucket["node_revision_refs"])),
            "association_revision_refs": sorted(
                set(bucket["association_revision_refs"])
            ),
        }
        for group_id, bucket in sorted(index.items())
    }


def _latest_maps(
    graph: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    return (
        v31_graph._latest_by_id(graph["node_history"], "node_id"),
        v31_graph._latest_by_id(
            graph["association_history"], "association_id"
        ),
    )


def _normalize_delta_against_verified_prior(
    candidate: Mapping[str, Any],
    *,
    decision_at: str,
    prior_graph: Mapping[str, Any],
    prior_digest: str,
    prior_node_latest: Mapping[str, Mapping[str, Any]],
    prior_association_latest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(candidate, Mapping) or set(candidate) not in {
        v31_graph._DELTA_FIELDS,
        v31_graph._DELTA_FIELDS - {"graph_delta_digest"},
    }:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_SCHEMA_INVALID")
    if candidate.get("schema_version") != "V3_1_GRAPH_DELTA":
        raise MarketKnowledgeGraphError("GRAPH_DELTA_SCHEMA_VERSION_INVALID")
    if prior_digest != prior_graph.get("graph_digest"):
        raise MarketKnowledgeGraphError("GRAPH_VERIFIED_PRIOR_DIGEST_INVALID")
    if candidate.get("graph_id") != prior_graph.get("graph_id"):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_GRAPH_ID_INVALID")
    base_revision = v31_graph._integer(
        candidate.get("base_graph_revision"),
        "GRAPH_DELTA_BASE_REVISION_INVALID",
    )
    revision = v31_graph._integer(
        candidate.get("revision"),
        "GRAPH_DELTA_REVISION_INVALID",
        minimum=1,
    )
    if base_revision != prior_graph["revision"] or revision != base_revision + 1:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_REVISION_NOT_CONTIGUOUS")
    if candidate.get("base_graph_digest") != prior_digest:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_BASE_DIGEST_INVALID")
    delta_id = v31_graph._text(
        candidate.get("delta_id"), "GRAPH_DELTA_ID_INVALID"
    )
    if delta_id in prior_graph["applied_delta_ids"]:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_ALREADY_APPLIED")
    cutoff = v31_graph._timestamp(
        decision_at, "GRAPH_DELTA_DECISION_TIME_INVALID"
    )
    occurred_at = v31_graph._timestamp(
        candidate.get("occurred_at"), "GRAPH_DELTA_OCCURRED_AT_INVALID"
    )
    available_at = v31_graph._timestamp(
        candidate.get("available_at"), "GRAPH_DELTA_AVAILABLE_AT_INVALID"
    )
    prior_updated = v31_graph._timestamp(
        prior_graph["updated_at"], "GRAPH_PRIOR_UPDATED_AT_INVALID"
    )
    if (
        occurred_at > available_at
        or available_at > cutoff
        or available_at <= prior_updated
    ):
        raise MarketKnowledgeGraphError(
            "GRAPH_DELTA_NOT_POINT_IN_TIME_OR_MONOTONIC"
        )
    raw_nodes = candidate.get("node_revisions")
    raw_associations = candidate.get("association_revisions")
    if not isinstance(raw_nodes, (list, tuple)) or not isinstance(
        raw_associations, (list, tuple)
    ):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_REVISIONS_INVALID")
    if not raw_nodes and not raw_associations:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_EMPTY")
    node_ids = [
        str(row.get("node_id") or "")
        for row in raw_nodes
        if isinstance(row, Mapping)
    ]
    association_ids = [
        str(row.get("association_id") or "")
        for row in raw_associations
        if isinstance(row, Mapping)
    ]
    if len(node_ids) != len(raw_nodes) or len(node_ids) != len(set(node_ids)):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_NODE_DUPLICATE")
    if len(association_ids) != len(raw_associations) or len(
        association_ids
    ) != len(set(association_ids)):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_ASSOCIATION_DUPLICATE")

    nodes: list[dict[str, Any]] = []
    for row in raw_nodes:
        node = build_graph_node_revision(
            row,
            decision_at=v31_graph._time_text(available_at),
            prior_revision=prior_node_latest.get(row["node_id"]),
        )
        if (
            v31_graph._timestamp(
                node["available_at"], "GRAPH_NODE_AVAILABLE_AT_INVALID"
            )
            > available_at
        ):
            raise MarketKnowledgeGraphError("GRAPH_DELTA_CONTAINS_FUTURE_NODE")
        nodes.append(node)
    associations: list[dict[str, Any]] = []
    for row in raw_associations:
        try:
            association = build_association_revision(
                row,
                decision_at=v31_graph._time_text(available_at),
                prior_revision=prior_association_latest.get(
                    row["association_id"]
                ),
            )
        except AssociationModelError as exc:
            raise MarketKnowledgeGraphError(
                f"GRAPH_DELTA_ASSOCIATION_INVALID:{exc}"
            ) from exc
        if (
            v31_graph._timestamp(
                association["available_at"],
                "GRAPH_ASSOCIATION_AVAILABLE_AT_INVALID",
            )
            > available_at
        ):
            raise MarketKnowledgeGraphError(
                "GRAPH_DELTA_CONTAINS_FUTURE_ASSOCIATION"
            )
        associations.append(association)
    dependency_groups = sorted(
        {
            group_id
            for row in [*nodes, *associations]
            for group_id in row["dependency_group_ids"]
        }
    )
    if (
        v31_graph._strings(
            candidate.get("dependency_group_ids"),
            "GRAPH_DELTA_DEPENDENCY_GROUPS_INVALID",
        )
        != dependency_groups
    ):
        raise MarketKnowledgeGraphError(
            "GRAPH_DELTA_DEPENDENCY_GROUPS_INCOMPLETE"
        )
    normalized = {
        "schema_version": "V3_1_GRAPH_DELTA",
        "delta_id": delta_id,
        "graph_id": prior_graph["graph_id"],
        "base_graph_revision": base_revision,
        "base_graph_digest": prior_digest,
        "revision": revision,
        "occurred_at": v31_graph._time_text(occurred_at),
        "available_at": v31_graph._time_text(available_at),
        "node_revisions": sorted(
            nodes, key=lambda row: (row["node_id"], row["revision"])
        ),
        "association_revisions": sorted(
            associations,
            key=lambda row: (row["association_id"], row["revision"]),
        ),
        "dependency_group_ids": dependency_groups,
        "reason": v31_graph._text(
            candidate.get("reason"), "GRAPH_DELTA_REASON_INVALID"
        ),
    }
    result = self_digest(normalized, "graph_delta_digest")
    supplied = candidate.get("graph_delta_digest")
    if supplied is not None and supplied != result["graph_delta_digest"]:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_DIGEST_MISMATCH")
    return result


def _materialize_transition(
    prior_graph: Mapping[str, Any],
    *,
    prior_digest: str,
    delta: Mapping[str, Any],
    prior_node_latest: Mapping[str, Mapping[str, Any]],
    prior_association_latest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    node_history = [dict(row) for row in prior_graph["node_history"]]
    association_history = [dict(row) for row in prior_graph["association_history"]]
    node_history.extend(dict(row) for row in delta["node_revisions"])
    association_history.extend(
        dict(row) for row in delta["association_revisions"]
    )
    node_latest = {
        identity: dict(row) for identity, row in prior_node_latest.items()
    }
    node_latest.update(
        (row["node_id"], dict(row)) for row in delta["node_revisions"]
    )
    association_latest = {
        identity: dict(row)
        for identity, row in prior_association_latest.items()
    }
    association_latest.update(
        (row["association_id"], dict(row))
        for row in delta["association_revisions"]
    )
    for row in association_latest.values():
        if (
            row["source_node_id"] not in node_latest
            or row["target_node_id"] not in node_latest
        ):
            raise MarketKnowledgeGraphError("GRAPH_EDGE_ENDPOINT_MISSING")
        if row["status"] == "ACTIVE" and (
            node_latest[row["source_node_id"]]["status"] != "ACTIVE"
            or node_latest[row["target_node_id"]]["status"] != "ACTIVE"
        ):
            raise MarketKnowledgeGraphError(
                "GRAPH_ACTIVE_EDGE_ENDPOINT_TERMINAL"
            )
    return self_digest(
        {
            "schema_version": "V3_1_MARKET_KNOWLEDGE_GRAPH",
            "graph_id": prior_graph["graph_id"],
            "revision": delta["revision"],
            "created_at": prior_graph["created_at"],
            "updated_at": delta["available_at"],
            "previous_graph_digest": prior_digest,
            "applied_delta_ids": [
                *prior_graph["applied_delta_ids"],
                delta["delta_id"],
            ],
            "node_history": node_history,
            "association_history": association_history,
            "latest_node_digests": {
                identity: row["node_digest"]
                for identity, row in sorted(node_latest.items())
            },
            "latest_association_digests": {
                identity: row["association_digest"]
                for identity, row in sorted(association_latest.items())
            },
            "active_node_ids": sorted(
                identity
                for identity, row in node_latest.items()
                if row["status"] == "ACTIVE"
            ),
            "active_association_ids": sorted(
                identity
                for identity, row in association_latest.items()
                if row["status"] == "ACTIVE"
            ),
            "dependency_index": _extend_dependency_index(
                prior_graph["dependency_index"],
                delta["node_revisions"],
                delta["association_revisions"],
            ),
        },
        "graph_digest",
    )


def _verify_transition_after_verified_prior(
    prior_graph: Mapping[str, Any],
    delta: Mapping[str, Any],
    graph: Mapping[str, Any],
    *,
    decision_at: str,
    prior_digest: str,
    prior_node_latest: Mapping[str, Mapping[str, Any]],
    prior_association_latest: Mapping[str, Mapping[str, Any]],
) -> str:
    supplied_digest = v31_graph._verify_graph_shape(
        graph, decision_at=decision_at
    )
    if prior_digest != prior_graph.get("graph_digest"):
        raise MarketKnowledgeGraphError("GRAPH_VERIFIED_PRIOR_DIGEST_INVALID")
    try:
        verify_self_digest(delta, "graph_delta_digest")
    except ValueError as exc:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_DIGEST_INVALID") from exc
    expected_metadata = {
        "graph_id": prior_graph["graph_id"],
        "revision": delta["revision"],
        "created_at": prior_graph["created_at"],
        "updated_at": delta["available_at"],
        "previous_graph_digest": prior_digest,
        "applied_delta_ids": [
            *prior_graph["applied_delta_ids"],
            delta["delta_id"],
        ],
    }
    if any(graph.get(field) != value for field, value in expected_metadata.items()):
        raise MarketKnowledgeGraphError("GRAPH_TRANSITION_METADATA_INVALID")
    prior_node_count = len(prior_graph["node_history"])
    prior_association_count = len(prior_graph["association_history"])
    if (
        graph["node_history"][:prior_node_count] != prior_graph["node_history"]
        or graph["node_history"][prior_node_count:] != delta["node_revisions"]
    ):
        raise MarketKnowledgeGraphError("GRAPH_NODE_HISTORY_APPEND_INVALID")
    if (
        graph["association_history"][:prior_association_count]
        != prior_graph["association_history"]
        or graph["association_history"][prior_association_count:]
        != delta["association_revisions"]
    ):
        raise MarketKnowledgeGraphError(
            "GRAPH_ASSOCIATION_HISTORY_APPEND_INVALID"
        )
    expected = _materialize_transition(
        prior_graph,
        prior_digest=prior_digest,
        delta=delta,
        prior_node_latest=prior_node_latest,
        prior_association_latest=prior_association_latest,
    )
    for field in (
        "latest_node_digests",
        "latest_association_digests",
        "active_node_ids",
        "active_association_ids",
        "dependency_index",
    ):
        if graph.get(field) != expected[field]:
            raise MarketKnowledgeGraphError(
                f"GRAPH_TRANSITION_{field.upper()}_INVALID"
            )
    return supplied_digest


def build_and_apply_v32_graph_delta(
    candidate: Mapping[str, Any],
    *,
    decision_at: str,
    prior_graph: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one V3.2 delta and graph with one complete predecessor scan."""

    prior_digest = v31_graph.verify_market_knowledge_graph(
        prior_graph, decision_at=decision_at
    )
    prior_node_latest, prior_association_latest = _latest_maps(prior_graph)
    delta = _normalize_delta_against_verified_prior(
        candidate,
        decision_at=decision_at,
        prior_graph=prior_graph,
        prior_digest=prior_digest,
        prior_node_latest=prior_node_latest,
        prior_association_latest=prior_association_latest,
    )
    graph = _materialize_transition(
        prior_graph,
        prior_digest=prior_digest,
        delta=delta,
        prior_node_latest=prior_node_latest,
        prior_association_latest=prior_association_latest,
    )
    _verify_transition_after_verified_prior(
        prior_graph,
        delta,
        graph,
        decision_at=decision_at,
        prior_digest=prior_digest,
        prior_node_latest=prior_node_latest,
        prior_association_latest=prior_association_latest,
    )
    return delta, graph


def verify_v32_market_knowledge_graph_transition(
    prior_graph: Mapping[str, Any],
    delta: Mapping[str, Any],
    graph: Mapping[str, Any],
    *,
    decision_at: str,
) -> str:
    """Fail closed on a self-resigned rewrite of a V3.2 graph transition."""

    prior_digest = v31_graph.verify_market_knowledge_graph(
        prior_graph, decision_at=decision_at
    )
    prior_node_latest, prior_association_latest = _latest_maps(prior_graph)
    normalized_delta = _normalize_delta_against_verified_prior(
        delta,
        decision_at=decision_at,
        prior_graph=prior_graph,
        prior_digest=prior_digest,
        prior_node_latest=prior_node_latest,
        prior_association_latest=prior_association_latest,
    )
    try:
        supplied = verify_self_digest(delta, "graph_delta_digest")
    except ValueError as exc:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_DIGEST_INVALID") from exc
    if supplied != normalized_delta["graph_delta_digest"] or dict(
        delta
    ) != normalized_delta:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_CANONICAL_FORM_INVALID")
    return _verify_transition_after_verified_prior(
        prior_graph,
        normalized_delta,
        graph,
        decision_at=decision_at,
        prior_digest=prior_digest,
        prior_node_latest=prior_node_latest,
        prior_association_latest=prior_association_latest,
    )


__all__ = [
    "build_and_apply_v32_graph_delta",
    "verify_v32_market_knowledge_graph_transition",
]
