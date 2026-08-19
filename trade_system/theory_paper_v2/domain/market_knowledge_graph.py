"""Append-only V3.1 typed market-knowledge graph contracts.

The graph records public, inspectable research state from information through
outcomes.  A ``GraphDelta`` may only append a contiguous node or association
revision.  Retirement and supersession are explicit terminal revisions; no
node, edge, or earlier revision is overwritten or physically deleted.

This module is pure Domain code and performs no IO or graph estimation.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .association_model import (
    AssociationModelError,
    build_association_revision,
    verify_association_revision,
)
from .contracts.canonical import self_digest, verify_self_digest


class MarketKnowledgeGraphError(ValueError):
    """A typed graph, revision, or delta contract failed closed."""


NODE_TYPES = frozenset(
    {
        "SOURCE_ARTIFACT",
        "INFORMATION_ACTOR",
        "INFORMATION_EVENT",
        "OBSERVABLE_ACTION",
        "AUDIENCE_SEGMENT",
        "MARKET_FACT",
        "DERIVED_MEASURE",
        "LATENT_STATE",
        "REGIME_STATE",
        "MECHANISM_HYPOTHESIS",
        "PATH_HYPOTHESIS",
        "EXPECTATION",
        "SCENARIO_PATH",
        "ACTION_CANDIDATE",
        "OUTCOME",
    }
)

# Useful for presentation and audit; inference is not allowed to skip a layer
# merely because the integer order exists.
NODE_STAGE_ORDER = {
    "SOURCE_ARTIFACT": 0,
    "INFORMATION_ACTOR": 0,
    "INFORMATION_EVENT": 1,
    "OBSERVABLE_ACTION": 1,
    "AUDIENCE_SEGMENT": 1,
    "MARKET_FACT": 2,
    "DERIVED_MEASURE": 3,
    "LATENT_STATE": 4,
    "REGIME_STATE": 4,
    "MECHANISM_HYPOTHESIS": 5,
    "PATH_HYPOTHESIS": 5,
    "EXPECTATION": 6,
    "SCENARIO_PATH": 7,
    "ACTION_CANDIDATE": 8,
    "OUTCOME": 9,
}

NODE_STATUSES = frozenset({"ACTIVE", "SUPERSEDED", "RETIRED"})
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_NODE_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "revision",
        "predecessor_digest",
        "node_type",
        "label",
        "description",
        "payload_ref",
        "payload_digest",
        "observed_at",
        "available_at",
        "validity",
        "status",
        "dependency_group_ids",
        "provenance",
        "created_at",
        "limitations",
        "node_digest",
    }
)
_VALIDITY_FIELDS = frozenset({"valid_from", "valid_until"})
_PROVENANCE_FIELDS = frozenset(
    {"source_ref", "source_digest", "observed_at", "available_at", "revision_ref"}
)
_DELTA_FIELDS = frozenset(
    {
        "schema_version",
        "delta_id",
        "graph_id",
        "base_graph_revision",
        "base_graph_digest",
        "revision",
        "occurred_at",
        "available_at",
        "node_revisions",
        "association_revisions",
        "dependency_group_ids",
        "reason",
        "graph_delta_digest",
    }
)
_GRAPH_FIELDS = frozenset(
    {
        "schema_version",
        "graph_id",
        "revision",
        "created_at",
        "updated_at",
        "previous_graph_digest",
        "applied_delta_ids",
        "node_history",
        "association_history",
        "latest_node_digests",
        "latest_association_digests",
        "active_node_ids",
        "active_association_ids",
        "dependency_index",
        "graph_digest",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketKnowledgeGraphError(code)
    return value.strip()


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise MarketKnowledgeGraphError(code)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketKnowledgeGraphError(code) from exc
    if result.tzinfo is None:
        raise MarketKnowledgeGraphError(code)
    return result.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _integer(value: Any, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MarketKnowledgeGraphError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise MarketKnowledgeGraphError(code)
    return value


def _strings(value: Any, code: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise MarketKnowledgeGraphError(code)
    result = list(value)
    if (
        (not allow_empty and not result)
        or any(not isinstance(item, str) or not item.strip() for item in result)
        or len(result) != len(set(result))
    ):
        raise MarketKnowledgeGraphError(code)
    return sorted(item.strip() for item in result)


def _mapping(value: Any, fields: frozenset[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MarketKnowledgeGraphError(code)
    return value


def _normalize_validity(value: Any, *, available_at: datetime) -> dict[str, Any]:
    raw = _mapping(value, _VALIDITY_FIELDS, "GRAPH_NODE_VALIDITY_SCHEMA_INVALID")
    valid_from = _timestamp(raw.get("valid_from"), "GRAPH_NODE_VALID_FROM_INVALID")
    valid_until = (
        None
        if raw.get("valid_until") is None
        else _timestamp(raw.get("valid_until"), "GRAPH_NODE_VALID_UNTIL_INVALID")
    )
    # `valid_from` is event/market time, while `available_at` is knowledge time.
    # A late-arriving or revised record may legitimately describe an earlier
    # validity interval; point-in-time safety is enforced solely by available_at.
    if valid_until is not None and valid_until < valid_from:
        raise MarketKnowledgeGraphError("GRAPH_NODE_VALIDITY_INTERVAL_INVALID")
    return {
        "valid_from": _time_text(valid_from),
        "valid_until": None if valid_until is None else _time_text(valid_until),
    }


def _normalize_provenance(value: Any, *, available_at: datetime) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or not value:
        raise MarketKnowledgeGraphError("GRAPH_NODE_PROVENANCE_INVALID")
    result: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for item in value:
        raw = _mapping(item, _PROVENANCE_FIELDS, "GRAPH_NODE_PROVENANCE_SCHEMA_INVALID")
        observed_at = _timestamp(
            raw.get("observed_at"), "GRAPH_NODE_PROVENANCE_OBSERVED_INVALID"
        )
        source_available = _timestamp(
            raw.get("available_at"), "GRAPH_NODE_PROVENANCE_AVAILABLE_INVALID"
        )
        if observed_at > source_available or source_available > available_at:
            raise MarketKnowledgeGraphError("GRAPH_NODE_PROVENANCE_NOT_PIT")
        source_ref = _text(
            raw.get("source_ref"), "GRAPH_NODE_PROVENANCE_SOURCE_INVALID"
        )
        source_digest = _digest(
            raw.get("source_digest"), "GRAPH_NODE_PROVENANCE_DIGEST_INVALID"
        )
        identity = (source_ref, source_digest)
        if identity in identities:
            raise MarketKnowledgeGraphError("GRAPH_NODE_PROVENANCE_DUPLICATE")
        identities.add(identity)
        result.append(
            {
                "source_ref": source_ref,
                "source_digest": source_digest,
                "observed_at": _time_text(observed_at),
                "available_at": _time_text(source_available),
                "revision_ref": _text(
                    raw.get("revision_ref"),
                    "GRAPH_NODE_PROVENANCE_REVISION_INVALID",
                ),
            }
        )
    return sorted(result, key=lambda row: (row["available_at"], row["source_ref"]))


def build_graph_node_revision(
    candidate: Mapping[str, Any],
    *,
    decision_at: str,
    prior_revision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit one point-in-time append-only node revision."""

    if not isinstance(candidate, Mapping) or set(candidate) not in {
        _NODE_FIELDS,
        _NODE_FIELDS - {"node_digest"},
    }:
        raise MarketKnowledgeGraphError("GRAPH_NODE_SCHEMA_INVALID")
    if candidate.get("schema_version") != "V3_1_GRAPH_NODE_REVISION":
        raise MarketKnowledgeGraphError("GRAPH_NODE_SCHEMA_VERSION_INVALID")
    cutoff = _timestamp(decision_at, "GRAPH_NODE_DECISION_TIME_INVALID")
    observed_at = _timestamp(
        candidate.get("observed_at"), "GRAPH_NODE_OBSERVED_AT_INVALID"
    )
    available_at = _timestamp(
        candidate.get("available_at"), "GRAPH_NODE_AVAILABLE_AT_INVALID"
    )
    created_at = _timestamp(candidate.get("created_at"), "GRAPH_NODE_CREATED_AT_INVALID")
    if observed_at > available_at or created_at > available_at or available_at > cutoff:
        raise MarketKnowledgeGraphError("GRAPH_NODE_NOT_POINT_IN_TIME")
    node_type = str(candidate.get("node_type") or "")
    if node_type not in NODE_TYPES:
        raise MarketKnowledgeGraphError("GRAPH_NODE_TYPE_INVALID")
    status = str(candidate.get("status") or "")
    if status not in NODE_STATUSES:
        raise MarketKnowledgeGraphError("GRAPH_NODE_STATUS_INVALID")
    revision = _integer(candidate.get("revision"), "GRAPH_NODE_REVISION_INVALID", minimum=1)
    predecessor_digest = candidate.get("predecessor_digest")
    immutable = ("node_id", "node_type", "created_at")
    if prior_revision is None:
        if revision != 1 or predecessor_digest is not None:
            raise MarketKnowledgeGraphError("GRAPH_NODE_INITIAL_REVISION_INVALID")
    else:
        try:
            prior_digest = verify_self_digest(prior_revision, "node_digest")
        except ValueError as exc:
            raise MarketKnowledgeGraphError("GRAPH_NODE_PRIOR_DIGEST_INVALID") from exc
        if revision != prior_revision.get("revision", 0) + 1:
            raise MarketKnowledgeGraphError("GRAPH_NODE_REVISION_NOT_CONTIGUOUS")
        if predecessor_digest != prior_digest:
            raise MarketKnowledgeGraphError("GRAPH_NODE_PREDECESSOR_INVALID")
        if any(candidate.get(field) != prior_revision.get(field) for field in immutable):
            raise MarketKnowledgeGraphError("GRAPH_NODE_IDENTITY_REWRITE_FORBIDDEN")
        if available_at <= _timestamp(
            prior_revision.get("available_at"), "GRAPH_NODE_PRIOR_TIME_INVALID"
        ):
            raise MarketKnowledgeGraphError("GRAPH_NODE_REVISION_TIME_NOT_MONOTONIC")
        if prior_revision.get("status") in {"SUPERSEDED", "RETIRED"}:
            raise MarketKnowledgeGraphError("GRAPH_NODE_TERMINAL_REVISION_FORBIDDEN")
    normalized = {
        "schema_version": "V3_1_GRAPH_NODE_REVISION",
        "node_id": _text(candidate.get("node_id"), "GRAPH_NODE_ID_INVALID"),
        "revision": revision,
        "predecessor_digest": (
            None
            if predecessor_digest is None
            else _digest(predecessor_digest, "GRAPH_NODE_PREDECESSOR_INVALID")
        ),
        "node_type": node_type,
        "label": _text(candidate.get("label"), "GRAPH_NODE_LABEL_INVALID"),
        "description": _text(
            candidate.get("description"), "GRAPH_NODE_DESCRIPTION_INVALID"
        ),
        "payload_ref": _text(
            candidate.get("payload_ref"), "GRAPH_NODE_PAYLOAD_REF_INVALID"
        ),
        "payload_digest": _digest(
            candidate.get("payload_digest"), "GRAPH_NODE_PAYLOAD_DIGEST_INVALID"
        ),
        "observed_at": _time_text(observed_at),
        "available_at": _time_text(available_at),
        "validity": _normalize_validity(
            candidate.get("validity"), available_at=available_at
        ),
        "status": status,
        "dependency_group_ids": _strings(
            candidate.get("dependency_group_ids"),
            "GRAPH_NODE_DEPENDENCY_GROUPS_INVALID",
        ),
        "provenance": _normalize_provenance(
            candidate.get("provenance"), available_at=available_at
        ),
        "created_at": _time_text(created_at),
        "limitations": _strings(
            candidate.get("limitations"), "GRAPH_NODE_LIMITATIONS_INVALID"
        ),
    }
    result = self_digest(normalized, "node_digest")
    supplied = candidate.get("node_digest")
    if supplied is not None and supplied != result["node_digest"]:
        raise MarketKnowledgeGraphError("GRAPH_NODE_DIGEST_MISMATCH")
    return result


def verify_graph_node_revision(
    document: Mapping[str, Any],
    *,
    decision_at: str,
    prior_revision: Mapping[str, Any] | None = None,
) -> str:
    normalized = build_graph_node_revision(
        document, decision_at=decision_at, prior_revision=prior_revision
    )
    try:
        supplied = verify_self_digest(document, "node_digest")
    except ValueError as exc:
        raise MarketKnowledgeGraphError("GRAPH_NODE_DIGEST_INVALID") from exc
    if supplied != normalized["node_digest"]:
        raise MarketKnowledgeGraphError("GRAPH_NODE_CANONICAL_FORM_INVALID")
    return supplied


def create_market_knowledge_graph(*, graph_id: str, created_at: str) -> dict[str, Any]:
    """Create an empty, digest-bound revision-zero graph."""

    timestamp = _timestamp(created_at, "GRAPH_CREATED_AT_INVALID")
    document = {
        "schema_version": "V3_1_MARKET_KNOWLEDGE_GRAPH",
        "graph_id": _text(graph_id, "GRAPH_ID_INVALID"),
        "revision": 0,
        "created_at": _time_text(timestamp),
        "updated_at": _time_text(timestamp),
        "previous_graph_digest": None,
        "applied_delta_ids": [],
        "node_history": [],
        "association_history": [],
        "latest_node_digests": {},
        "latest_association_digests": {},
        "active_node_ids": [],
        "active_association_ids": [],
        "dependency_index": {},
    }
    return self_digest(document, "graph_digest")


def _latest_by_id(history: Sequence[Mapping[str, Any]], id_field: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in history:
        identity = str(row[id_field])
        if identity not in result or int(row["revision"]) > int(result[identity]["revision"]):
            result[identity] = dict(row)
    return result


def _dependency_index(
    node_history: Sequence[Mapping[str, Any]],
    association_history: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    index: dict[str, dict[str, list[str]]] = {}
    for row, kind, id_field in (
        *((item, "node_revision_refs", "node_id") for item in node_history),
        *((item, "association_revision_refs", "association_id") for item in association_history),
    ):
        revision_ref = f"{row[id_field]}@{row['revision']}"
        for group_id in row["dependency_group_ids"]:
            bucket = index.setdefault(
                group_id,
                {"node_revision_refs": [], "association_revision_refs": []},
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


def _history_prior(
    history: Sequence[Mapping[str, Any]], id_field: str, identity: str
) -> Mapping[str, Any] | None:
    rows = [row for row in history if row.get(id_field) == identity]
    return max(rows, key=lambda row: int(row["revision"])) if rows else None


def _verify_graph_shape(graph: Mapping[str, Any], *, decision_at: str) -> str:
    if not isinstance(graph, Mapping) or set(graph) != _GRAPH_FIELDS:
        raise MarketKnowledgeGraphError("GRAPH_SCHEMA_INVALID")
    if graph.get("schema_version") != "V3_1_MARKET_KNOWLEDGE_GRAPH":
        raise MarketKnowledgeGraphError("GRAPH_SCHEMA_VERSION_INVALID")
    try:
        supplied_digest = verify_self_digest(graph, "graph_digest")
    except ValueError as exc:
        raise MarketKnowledgeGraphError("GRAPH_DIGEST_INVALID") from exc
    cutoff = _timestamp(decision_at, "GRAPH_DECISION_TIME_INVALID")
    created_at = _timestamp(graph.get("created_at"), "GRAPH_CREATED_AT_INVALID")
    updated_at = _timestamp(graph.get("updated_at"), "GRAPH_UPDATED_AT_INVALID")
    if created_at > updated_at or updated_at > cutoff:
        raise MarketKnowledgeGraphError("GRAPH_NOT_POINT_IN_TIME")
    revision = _integer(graph.get("revision"), "GRAPH_REVISION_INVALID")
    delta_ids = _strings(
        graph.get("applied_delta_ids"), "GRAPH_DELTA_IDS_INVALID", allow_empty=True
    )
    if revision != len(delta_ids):
        raise MarketKnowledgeGraphError("GRAPH_REVISION_DELTA_COUNT_MISMATCH")
    previous_digest = graph.get("previous_graph_digest")
    if revision == 0:
        if previous_digest is not None:
            raise MarketKnowledgeGraphError("EMPTY_GRAPH_PREDECESSOR_FORBIDDEN")
    else:
        _digest(previous_digest, "GRAPH_PREDECESSOR_DIGEST_INVALID")
    if not isinstance(graph.get("node_history"), list) or not isinstance(
        graph.get("association_history"), list
    ):
        raise MarketKnowledgeGraphError("GRAPH_HISTORY_INVALID")
    return supplied_digest


def verify_market_knowledge_graph(graph: Mapping[str, Any], *, decision_at: str) -> str:
    """Validate canonical digest, PIT histories, heads, endpoints, and dependencies."""

    supplied_digest = _verify_graph_shape(graph, decision_at=decision_at)
    node_latest: dict[str, dict[str, Any]] = {}
    seen_node_revisions: set[tuple[str, int]] = set()
    for row in graph["node_history"]:
        node_id = str(row.get("node_id") or "")
        revision = row.get("revision")
        key = (node_id, revision)
        if key in seen_node_revisions:
            raise MarketKnowledgeGraphError("GRAPH_NODE_HISTORY_DUPLICATE")
        prior = node_latest.get(node_id)
        verify_graph_node_revision(row, decision_at=row["available_at"], prior_revision=prior)
        node_latest[node_id] = dict(row)
        seen_node_revisions.add(key)
    association_latest: dict[str, dict[str, Any]] = {}
    seen_association_revisions: set[tuple[str, int]] = set()
    for row in graph["association_history"]:
        association_id = str(row.get("association_id") or "")
        revision = row.get("revision")
        key = (association_id, revision)
        if key in seen_association_revisions:
            raise MarketKnowledgeGraphError("GRAPH_ASSOCIATION_HISTORY_DUPLICATE")
        prior = association_latest.get(association_id)
        try:
            verify_association_revision(
                row, decision_at=row["available_at"], prior_revision=prior
            )
        except AssociationModelError as exc:
            raise MarketKnowledgeGraphError(f"GRAPH_ASSOCIATION_INVALID:{exc}") from exc
        association_latest[association_id] = dict(row)
        seen_association_revisions.add(key)
    expected_node_digests = {
        identity: row["node_digest"] for identity, row in sorted(node_latest.items())
    }
    expected_association_digests = {
        identity: row["association_digest"]
        for identity, row in sorted(association_latest.items())
    }
    if graph.get("latest_node_digests") != expected_node_digests:
        raise MarketKnowledgeGraphError("GRAPH_NODE_HEADS_INVALID")
    if graph.get("latest_association_digests") != expected_association_digests:
        raise MarketKnowledgeGraphError("GRAPH_ASSOCIATION_HEADS_INVALID")
    active_nodes = sorted(
        identity for identity, row in node_latest.items() if row["status"] == "ACTIVE"
    )
    active_associations = sorted(
        identity
        for identity, row in association_latest.items()
        if row["status"] == "ACTIVE"
    )
    if graph.get("active_node_ids") != active_nodes:
        raise MarketKnowledgeGraphError("GRAPH_ACTIVE_NODES_INVALID")
    if graph.get("active_association_ids") != active_associations:
        raise MarketKnowledgeGraphError("GRAPH_ACTIVE_ASSOCIATIONS_INVALID")
    for association_id in active_associations:
        row = association_latest[association_id]
        if row["source_node_id"] not in active_nodes or row["target_node_id"] not in active_nodes:
            raise MarketKnowledgeGraphError("GRAPH_ACTIVE_EDGE_ENDPOINT_INVALID")
    expected_index = _dependency_index(
        graph["node_history"], graph["association_history"]
    )
    if graph.get("dependency_index") != expected_index:
        raise MarketKnowledgeGraphError("GRAPH_DEPENDENCY_INDEX_INVALID")
    return supplied_digest


def build_graph_delta(
    candidate: Mapping[str, Any],
    *,
    decision_at: str,
    prior_graph: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize a delta against the exact previous graph revision."""

    if not isinstance(candidate, Mapping) or set(candidate) not in {
        _DELTA_FIELDS,
        _DELTA_FIELDS - {"graph_delta_digest"},
    }:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_SCHEMA_INVALID")
    if candidate.get("schema_version") != "V3_1_GRAPH_DELTA":
        raise MarketKnowledgeGraphError("GRAPH_DELTA_SCHEMA_VERSION_INVALID")
    prior_digest = verify_market_knowledge_graph(prior_graph, decision_at=decision_at)
    if candidate.get("graph_id") != prior_graph.get("graph_id"):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_GRAPH_ID_INVALID")
    base_revision = _integer(
        candidate.get("base_graph_revision"), "GRAPH_DELTA_BASE_REVISION_INVALID"
    )
    revision = _integer(candidate.get("revision"), "GRAPH_DELTA_REVISION_INVALID", minimum=1)
    if base_revision != prior_graph["revision"] or revision != base_revision + 1:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_REVISION_NOT_CONTIGUOUS")
    if candidate.get("base_graph_digest") != prior_digest:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_BASE_DIGEST_INVALID")
    delta_id = _text(candidate.get("delta_id"), "GRAPH_DELTA_ID_INVALID")
    if delta_id in prior_graph["applied_delta_ids"]:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_ALREADY_APPLIED")
    cutoff = _timestamp(decision_at, "GRAPH_DELTA_DECISION_TIME_INVALID")
    occurred_at = _timestamp(
        candidate.get("occurred_at"), "GRAPH_DELTA_OCCURRED_AT_INVALID"
    )
    available_at = _timestamp(
        candidate.get("available_at"), "GRAPH_DELTA_AVAILABLE_AT_INVALID"
    )
    prior_updated = _timestamp(prior_graph["updated_at"], "GRAPH_PRIOR_UPDATED_AT_INVALID")
    if occurred_at > available_at or available_at > cutoff or available_at <= prior_updated:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_NOT_POINT_IN_TIME_OR_MONOTONIC")
    raw_nodes = candidate.get("node_revisions")
    raw_associations = candidate.get("association_revisions")
    if not isinstance(raw_nodes, (list, tuple)) or not isinstance(
        raw_associations, (list, tuple)
    ):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_REVISIONS_INVALID")
    if not raw_nodes and not raw_associations:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_EMPTY")
    node_ids = [str(row.get("node_id") or "") for row in raw_nodes if isinstance(row, Mapping)]
    association_ids = [
        str(row.get("association_id") or "")
        for row in raw_associations
        if isinstance(row, Mapping)
    ]
    if len(node_ids) != len(raw_nodes) or len(node_ids) != len(set(node_ids)):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_NODE_DUPLICATE")
    if len(association_ids) != len(raw_associations) or len(association_ids) != len(
        set(association_ids)
    ):
        raise MarketKnowledgeGraphError("GRAPH_DELTA_ASSOCIATION_DUPLICATE")
    nodes: list[dict[str, Any]] = []
    for row in raw_nodes:
        prior = _history_prior(prior_graph["node_history"], "node_id", row["node_id"])
        node = build_graph_node_revision(
            row, decision_at=_time_text(available_at), prior_revision=prior
        )
        if _timestamp(node["available_at"], "GRAPH_NODE_AVAILABLE_AT_INVALID") > available_at:
            raise MarketKnowledgeGraphError("GRAPH_DELTA_CONTAINS_FUTURE_NODE")
        nodes.append(node)
    associations: list[dict[str, Any]] = []
    for row in raw_associations:
        prior = _history_prior(
            prior_graph["association_history"], "association_id", row["association_id"]
        )
        try:
            association = build_association_revision(
                row, decision_at=_time_text(available_at), prior_revision=prior
            )
        except AssociationModelError as exc:
            raise MarketKnowledgeGraphError(f"GRAPH_DELTA_ASSOCIATION_INVALID:{exc}") from exc
        if _timestamp(
            association["available_at"], "GRAPH_ASSOCIATION_AVAILABLE_AT_INVALID"
        ) > available_at:
            raise MarketKnowledgeGraphError("GRAPH_DELTA_CONTAINS_FUTURE_ASSOCIATION")
        associations.append(association)
    dependency_groups = sorted(
        {
            group_id
            for row in [*nodes, *associations]
            for group_id in row["dependency_group_ids"]
        }
    )
    if _strings(
        candidate.get("dependency_group_ids"),
        "GRAPH_DELTA_DEPENDENCY_GROUPS_INVALID",
    ) != dependency_groups:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_DEPENDENCY_GROUPS_INCOMPLETE")
    normalized = {
        "schema_version": "V3_1_GRAPH_DELTA",
        "delta_id": delta_id,
        "graph_id": prior_graph["graph_id"],
        "base_graph_revision": base_revision,
        "base_graph_digest": prior_digest,
        "revision": revision,
        "occurred_at": _time_text(occurred_at),
        "available_at": _time_text(available_at),
        "node_revisions": sorted(nodes, key=lambda row: (row["node_id"], row["revision"])),
        "association_revisions": sorted(
            associations, key=lambda row: (row["association_id"], row["revision"])
        ),
        "dependency_group_ids": dependency_groups,
        "reason": _text(candidate.get("reason"), "GRAPH_DELTA_REASON_INVALID"),
    }
    result = self_digest(normalized, "graph_delta_digest")
    supplied = candidate.get("graph_delta_digest")
    if supplied is not None and supplied != result["graph_delta_digest"]:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_DIGEST_MISMATCH")
    return result


def apply_graph_delta(
    prior_graph: Mapping[str, Any],
    delta: Mapping[str, Any],
    *,
    decision_at: str,
) -> dict[str, Any]:
    """Append one verified delta and derive the new graph heads and indexes."""

    prior_digest = verify_market_knowledge_graph(prior_graph, decision_at=decision_at)
    normalized_delta = build_graph_delta(
        delta, decision_at=decision_at, prior_graph=prior_graph
    )
    try:
        supplied_delta_digest = verify_self_digest(delta, "graph_delta_digest")
    except ValueError as exc:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_DIGEST_INVALID") from exc
    if supplied_delta_digest != normalized_delta["graph_delta_digest"]:
        raise MarketKnowledgeGraphError("GRAPH_DELTA_CANONICAL_FORM_INVALID")
    node_history = [dict(row) for row in prior_graph["node_history"]]
    association_history = [dict(row) for row in prior_graph["association_history"]]
    node_history.extend(dict(row) for row in normalized_delta["node_revisions"])
    association_history.extend(
        dict(row) for row in normalized_delta["association_revisions"]
    )
    node_latest = _latest_by_id(node_history, "node_id")
    association_latest = _latest_by_id(association_history, "association_id")
    for row in association_latest.values():
        if row["source_node_id"] not in node_latest or row["target_node_id"] not in node_latest:
            raise MarketKnowledgeGraphError("GRAPH_EDGE_ENDPOINT_MISSING")
        if row["status"] == "ACTIVE" and (
            node_latest[row["source_node_id"]]["status"] != "ACTIVE"
            or node_latest[row["target_node_id"]]["status"] != "ACTIVE"
        ):
            raise MarketKnowledgeGraphError("GRAPH_ACTIVE_EDGE_ENDPOINT_TERMINAL")
    result = {
        "schema_version": "V3_1_MARKET_KNOWLEDGE_GRAPH",
        "graph_id": prior_graph["graph_id"],
        "revision": normalized_delta["revision"],
        "created_at": prior_graph["created_at"],
        "updated_at": normalized_delta["available_at"],
        "previous_graph_digest": prior_digest,
        "applied_delta_ids": [*prior_graph["applied_delta_ids"], normalized_delta["delta_id"]],
        "node_history": node_history,
        "association_history": association_history,
        "latest_node_digests": {
            identity: row["node_digest"] for identity, row in sorted(node_latest.items())
        },
        "latest_association_digests": {
            identity: row["association_digest"]
            for identity, row in sorted(association_latest.items())
        },
        "active_node_ids": sorted(
            identity for identity, row in node_latest.items() if row["status"] == "ACTIVE"
        ),
        "active_association_ids": sorted(
            identity
            for identity, row in association_latest.items()
            if row["status"] == "ACTIVE"
        ),
        "dependency_index": _dependency_index(node_history, association_history),
    }
    graph = self_digest(result, "graph_digest")
    verify_market_knowledge_graph(graph, decision_at=decision_at)
    return graph


def node_history(graph: Mapping[str, Any], node_id: str) -> tuple[dict[str, Any], ...]:
    """Return the immutable history of one node in revision order."""

    identity = _text(node_id, "GRAPH_NODE_ID_INVALID")
    return tuple(
        dict(row)
        for row in graph.get("node_history", [])
        if row.get("node_id") == identity
    )


def association_history(
    graph: Mapping[str, Any], association_id: str
) -> tuple[dict[str, Any], ...]:
    """Return the immutable history of one association in revision order."""

    identity = _text(association_id, "ASSOCIATION_ID_INVALID")
    return tuple(
        dict(row)
        for row in graph.get("association_history", [])
        if row.get("association_id") == identity
    )


def dependency_members(
    graph: Mapping[str, Any], dependency_group_id: str
) -> dict[str, list[str]]:
    """Expose revisions sharing one evidence dependency group."""

    group_id = _text(dependency_group_id, "GRAPH_DEPENDENCY_GROUP_ID_INVALID")
    bucket = graph.get("dependency_index", {}).get(group_id)
    if bucket is None:
        return {"node_revision_refs": [], "association_revision_refs": []}
    return {
        "node_revision_refs": list(bucket["node_revision_refs"]),
        "association_revision_refs": list(bucket["association_revision_refs"]),
    }
