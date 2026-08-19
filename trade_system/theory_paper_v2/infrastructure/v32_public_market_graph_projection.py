"""Deterministic V3.2 public-market bundle to knowledge-graph projection.

The collector proves raw-first public evidence.  This module performs the next
local-only step: every admitted source event, point-in-time datum and twelve-
axis/OTHER evidence row becomes a typed graph node, while provenance links
become explicitly non-causal associations.  The resulting dependency registry
is the finite set the Agent may cite when it creates zones, modifiers and
hypotheses.

No network, clock, account, order, fill, PnL or execution capability exists in
this module.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
import threading
from typing import Any, Mapping, Sequence

from ..domain.association_model import build_association_revision
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.market_knowledge_graph import (
    build_graph_node_revision,
    create_market_knowledge_graph,
    verify_market_knowledge_graph,
)
from ..domain.v31_sentiment_native_projection_v2 import (
    V31_NATIVE_SENTIMENT_AXES,
    build_v31_native_sentiment_source_registry,
    verify_v31_native_sentiment_source_registry,
)
from .v32_incremental_market_graph import build_and_apply_v32_graph_delta
from .v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    ANALYSIS_BUNDLE_SCHEMA_ID,
    AXIS_EVIDENCE_DIGEST_FIELD,
    INFORMATION_EVENT_DIGEST_FIELD,
    PIT_DATUM_DIGEST_FIELD,
    verify_v32_public_market_analysis_bundle,
)



_OBSERVABLE_FAMILY_BY_COMPONENT = {
    "SERVER_TIME": "PROVIDER_METADATA",
    "INSTRUMENT": "CONTRACT_SPEC",
    "TICKER": "PRICE_ACTION",
    "MARK_PRICE": "PRICE_ACTION",
    "CLOSED_CANDLES_15M": "PRICE_ACTION",
    "CLOSED_CANDLES_1H": "PRICE_ACTION",
    "CLOSED_CANDLES_4H": "PRICE_ACTION",
    "CLOSED_CANDLES_1D": "PRICE_ACTION",
    "OPEN_INTEREST": "POSITIONING",
    "FUNDING_RATE": "FUNDING_CROWDING",
    "ORDER_BOOK": "ORDERBOOK_LIQUIDITY",
    "RECENT_TRADES": "TRADE_FLOW",
}


def _observable_family_dependency(component_id: str) -> str:
    """Return the material observable family for one frozen source request."""

    try:
        family = _OBSERVABLE_FAMILY_BY_COMPONENT[component_id]
    except KeyError as exc:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_OBSERVABLE_FAMILY_UNCLASSIFIED"
        ) from exc
    return f"OBSERVABLE_FAMILY:{family}"


class V32PublicMarketGraphProjectionError(ValueError):
    """The public-market graph projection failed closed."""


class _PublicGraphVerificationMemo:
    __slots__ = ("owner", "results")

    def __init__(self, owner: tuple[object, object | None]) -> None:
        self.owner = owner
        self.results: dict[tuple[str, bytes], tuple[str, str]] = {}


_PUBLIC_GRAPH_VERIFICATION_MEMO: ContextVar[
    _PublicGraphVerificationMemo | None
] = ContextVar("v32_public_graph_verification_memo", default=None)
_MEMO_MISSING = object()
_STRICT_SNAPSHOT_UNAVAILABLE = object()


def _execution_owner() -> tuple[object, object | None]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.current_thread(), task


def _strict_builtin_json_snapshot(value: Any) -> Any:
    """Copy only the canonical built-in JSON shapes accepted for memo use."""

    value_type = type(value)
    if value is None or value_type in {str, bool, int}:
        return value
    if value_type is list:
        snapshot: list[Any] = []
        try:
            for item in value:
                copied = _strict_builtin_json_snapshot(item)
                if copied is _STRICT_SNAPSHOT_UNAVAILABLE:
                    return _STRICT_SNAPSHOT_UNAVAILABLE
                snapshot.append(copied)
        except (KeyError, RuntimeError):
            return _STRICT_SNAPSHOT_UNAVAILABLE
        return snapshot
    if value_type is dict:
        snapshot_dict: dict[str, Any] = {}
        try:
            for key, item in value.items():
                if type(key) is not str:
                    return _STRICT_SNAPSHOT_UNAVAILABLE
                copied = _strict_builtin_json_snapshot(item)
                if copied is _STRICT_SNAPSHOT_UNAVAILABLE:
                    return _STRICT_SNAPSHOT_UNAVAILABLE
                snapshot_dict[key] = copied
        except (KeyError, RuntimeError):
            return _STRICT_SNAPSHOT_UNAVAILABLE
        return snapshot_dict
    return _STRICT_SNAPSHOT_UNAVAILABLE


@contextmanager
def v32_public_graph_verification_scope_v1():
    """Share successful exact graph verification inside one owning call.

    The key and verifier consume the same strict built-in snapshot.  Nested
    scopes owned by the same thread/task share results; copied ContextVars,
    custom Mapping objects, failures, and completed scopes never do.
    """

    owner = _execution_owner()
    active = _PUBLIC_GRAPH_VERIFICATION_MEMO.get()
    if active is not None and active.owner == owner:
        yield
        return
    created = _PublicGraphVerificationMemo(owner)
    token = _PUBLIC_GRAPH_VERIFICATION_MEMO.set(created)
    try:
        yield
    finally:
        created.results.clear()
        _PUBLIC_GRAPH_VERIFICATION_MEMO.reset(token)


SCHEMA_VERSION = "1.0.0"
GRAPH_PROJECTION_SCHEMA_ID = "theory_paper_v32_public_market_graph_projection_v1"
GRAPH_PROJECTION_DIGEST_FIELD = "public_market_graph_projection_digest"
GRAPH_REGISTRY_SCHEMA_ID = "theory_paper_v32_verified_graph_dependency_registry_v1"
GRAPH_REGISTRY_DIGEST_FIELD = "graph_dependency_registry_digest"
EVIDENCE_DEPENDENCY_CLOSURE_SCHEMA_ID = (
    "theory_paper_v32_evidence_dependency_closure_v1"
)
EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD = (
    "evidence_dependency_closure_digest"
)
PROJECTION_CLOSURE_DIGEST_FIELD = "projection_evidence_dependency_closure_digest"

SOURCE_SCOPE = "PUBLIC_NON_ACCOUNT_ONLY"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_LOCAL_SIMULATION"

_PROJECTION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "market_as_of",
        "available_at",
        "analysis_bundle_digest",
        "axis_source_registry_digest",
        "previous_graph_projection_digest",
        "graph_delta",
        "graph_delta_digest",
        "knowledge_graph",
        "knowledge_graph_digest",
        "knowledge_graph_revision",
        "source_event_node_ids",
        "datum_node_ids",
        "axis_node_ids",
        "provenance_association_ids",
        "dependency_group_ids",
        "evidence_dependency_closure",
        PROJECTION_CLOSURE_DIGEST_FIELD,
        "native_axis_ids",
        "proxy_axis_ids",
        "derived_axis_ids",
        "unknown_axis_ids",
        "twelve_axes_native",
        "unknown_retained",
        "other_retained",
        "causal_claim",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        GRAPH_PROJECTION_DIGEST_FIELD,
    }
)
_REGISTRY_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "members",
        "evidence_dependency_policy",
        "evidence_dependency_closure",
        "upstream_schema_id",
        "upstream_digest_field",
        "upstream_semantic_digest",
        "full_verification_receipt_digest",
        "source_scope",
        "external_execution_authority",
        "executable",
        GRAPH_REGISTRY_DIGEST_FIELD,
    }
)
_EVIDENCE_DEPENDENCY_CLOSURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "evidence_digest",
        "evidence_refs",
        "node_ids",
        "association_ids",
        "dependency_group_ids",
        EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD,
    }
)
_EVIDENCE_DEPENDENCY_POLICY = {
    "identity_key": "PAYLOAD_DIGEST",
    "node_scope": "LATEST_NODE_REVISIONS_ONLY",
    "association_scope": "ALL_LATEST_INCIDENT_ASSOCIATIONS",
    "dependency_operation": "UNION_NO_CALLER_SUBSETS",
    "same_digest_split_allowed": False,
}


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32PublicMarketGraphProjectionError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32PublicMarketGraphProjectionError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise V32PublicMarketGraphProjectionError(code)
    return parsed.astimezone(UTC)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32PublicMarketGraphProjectionError(code)
    return value


def _sorted_unique(values: Sequence[str], code: str) -> list[str]:
    result = list(values)
    if not result or any(not isinstance(row, str) or not row for row in result):
        raise V32PublicMarketGraphProjectionError(code)
    return sorted(set(result))


def _verified_axis_registry_digest() -> str:
    registry = build_v31_native_sentiment_source_registry()
    try:
        return verify_v31_native_sentiment_source_registry(registry)
    except ValueError as exc:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_AXIS_SOURCE_REGISTRY_INVALID"
        ) from exc


def _axis_coverage_sets(
    axes: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str], list[str], list[str]]:
    native: list[str] = []
    proxy: list[str] = []
    derived: list[str] = []
    unknown: list[str] = []
    for row in axes:
        axis_id = str(row["axis_id"])
        if axis_id == "OTHER":
            continue
        if row["admission_status"] != "ADMITTED":
            unknown.append(axis_id)
            continue
        assessments = [
            item
            for item in row["source_assessments"]
            if item["admission_status"] == "ADMITTED"
        ]
        roles = {item["evidence_role"] for item in assessments}
        if row["native_external_direct_admitted"] is True:
            native.append(axis_id)
        elif "PROXY" in roles:
            proxy.append(axis_id)
        elif "DERIVED" in roles:
            derived.append(axis_id)
        else:
            raise V32PublicMarketGraphProjectionError(
                "V32_GRAPH_AXIS_ADMISSION_WITHOUT_LEGAL_ROLE"
            )
    partition = {*native, *proxy, *derived, *unknown}
    if (
        partition != set(V31_NATIVE_SENTIMENT_AXES)
        or sum(map(len, (native, proxy, derived, unknown)))
        != len(V31_NATIVE_SENTIMENT_AXES)
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_AXIS_COVERAGE_PARTITION_INVALID"
        )
    return sorted(native), sorted(proxy), sorted(derived), sorted(unknown)


def _evidence_dependency_closure_from_heads(
    *,
    latest_nodes: Mapping[str, Mapping[str, Any]],
    latest_associations: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Close evidence over one already-selected set of current graph heads."""

    grouped: dict[str, dict[str, set[str]]] = {}
    node_to_digest: dict[str, str] = {}
    for node_id, node in latest_nodes.items():
        evidence_digest = str(node["payload_digest"])
        node_to_digest[node_id] = evidence_digest
        bucket = grouped.setdefault(
            evidence_digest,
            {
                "evidence_refs": set(),
                "node_ids": set(),
                "association_ids": set(),
                "dependency_group_ids": set(),
            },
        )
        bucket["evidence_refs"].add(str(node["payload_ref"]))
        bucket["node_ids"].add(node_id)
        bucket["dependency_group_ids"].update(node["dependency_group_ids"])
    for association_id, association in latest_associations.items():
        incident_digests = {
            node_to_digest[node_id]
            for node_id in (
                association["source_node_id"],
                association["target_node_id"],
            )
            if node_id in node_to_digest
        }
        for evidence_digest in incident_digests:
            bucket = grouped[evidence_digest]
            bucket["association_ids"].add(association_id)
            bucket["dependency_group_ids"].update(
                association["dependency_group_ids"]
            )
    rows: list[dict[str, Any]] = []
    for evidence_digest in sorted(grouped):
        bucket = grouped[evidence_digest]
        if not bucket["node_ids"] or not bucket["dependency_group_ids"]:
            raise V32PublicMarketGraphProjectionError(
                "V32_GRAPH_EVIDENCE_DEPENDENCY_CLOSURE_INVALID"
            )
        rows.append(
            self_digest(
                {
                    "schema_id": EVIDENCE_DEPENDENCY_CLOSURE_SCHEMA_ID,
                    "schema_version": SCHEMA_VERSION,
                    "evidence_digest": evidence_digest,
                    "evidence_refs": sorted(bucket["evidence_refs"]),
                    "node_ids": sorted(bucket["node_ids"]),
                    "association_ids": sorted(bucket["association_ids"]),
                    "dependency_group_ids": sorted(
                        bucket["dependency_group_ids"]
                    ),
                },
                EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD,
            )
        )
    if not rows or len({row["evidence_digest"] for row in rows}) != len(rows):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_EVIDENCE_DEPENDENCY_CLOSURE_INVALID"
        )
    return rows


def _build_evidence_dependency_closure(
    graph: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build the initial closure by scanning the complete revision-one graph."""

    latest_nodes = {
        row["node_id"]: row
        for row in graph["node_history"]
        if row["node_digest"]
        == graph["latest_node_digests"].get(row["node_id"])
    }
    latest_associations = {
        row["association_id"]: row
        for row in graph["association_history"]
        if row["association_digest"]
        == graph["latest_association_digests"].get(row["association_id"])
    }
    return _evidence_dependency_closure_from_heads(
        latest_nodes=latest_nodes,
        latest_associations=latest_associations,
    )


def _verify_evidence_dependency_closure_rows(
    rows: Any,
) -> str:
    """Verify one complete, canonically ordered closure snapshot."""

    if not isinstance(rows, list) or not rows:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_EVIDENCE_DEPENDENCY_CLOSURE_INVALID"
        )
    evidence_digests: list[str] = []
    try:
        for row in rows:
            if (
                not isinstance(row, Mapping)
                or set(row) != _EVIDENCE_DEPENDENCY_CLOSURE_FIELDS
                or row.get("schema_id")
                != EVIDENCE_DEPENDENCY_CLOSURE_SCHEMA_ID
                or row.get("schema_version") != SCHEMA_VERSION
                or not isinstance(row.get("evidence_digest"), str)
                or len(row["evidence_digest"]) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in row["evidence_digest"]
                )
            ):
                raise V32PublicMarketGraphProjectionError(
                    "V32_GRAPH_EVIDENCE_DEPENDENCY_CLOSURE_INVALID"
                )
            for field, allow_empty in (
                ("evidence_refs", False),
                ("node_ids", False),
                ("association_ids", True),
                ("dependency_group_ids", False),
            ):
                values = row.get(field)
                if (
                    not isinstance(values, list)
                    or (not allow_empty and not values)
                    or values != sorted(set(values))
                    or any(
                        not isinstance(value, str) or not value for value in values
                    )
                ):
                    raise V32PublicMarketGraphProjectionError(
                        "V32_GRAPH_EVIDENCE_DEPENDENCY_CLOSURE_INVALID"
                    )
            verify_self_digest(row, EVIDENCE_DEPENDENCY_CLOSURE_DIGEST_FIELD)
            evidence_digests.append(row["evidence_digest"])
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicMarketGraphProjectionError):
            raise
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_EVIDENCE_DEPENDENCY_CLOSURE_INVALID"
        ) from exc
    if evidence_digests != sorted(set(evidence_digests)):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_EVIDENCE_DEPENDENCY_CLOSURE_INVALID"
        )
    return canonical_digest(rows)


def _validated_delta_heads(
    *,
    graph: Mapping[str, Any],
    graph_delta: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    """Validate and return the heads explicitly revised by one graph delta."""

    node_rows = graph_delta.get("node_revisions")
    association_rows = graph_delta.get("association_revisions")
    if not isinstance(node_rows, list) or not isinstance(association_rows, list):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_INCREMENTAL_CLOSURE_DELTA_INVALID"
        )
    latest_nodes = {row.get("node_id"): row for row in node_rows}
    latest_associations = {
        row.get("association_id"): row for row in association_rows
    }
    if (
        len(latest_nodes) != len(node_rows)
        or len(latest_associations) != len(association_rows)
        or any(
            graph["latest_node_digests"].get(node_id) != row.get("node_digest")
            for node_id, row in latest_nodes.items()
        )
        or any(
            graph["latest_association_digests"].get(association_id)
            != row.get("association_digest")
            for association_id, row in latest_associations.items()
        )
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_INCREMENTAL_CLOSURE_DELTA_INVALID"
        )
    return latest_nodes, latest_associations


def _build_delta_evidence_dependency_closure(
    *,
    graph: Mapping[str, Any],
    graph_delta: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build a closure when one bounded delta contains every current head."""

    latest_nodes, latest_associations = _validated_delta_heads(
        graph=graph, graph_delta=graph_delta
    )
    if (
        set(latest_nodes) != set(graph.get("latest_node_digests", ()))
        or set(latest_associations)
        != set(graph.get("latest_association_digests", ()))
        or any(
            association.get("source_node_id") not in latest_nodes
            or association.get("target_node_id") not in latest_nodes
            for association in latest_associations.values()
        )
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_INCREMENTAL_CLOSURE_DELTA_HEAD_COVERAGE_INVALID"
        )
    return _evidence_dependency_closure_from_heads(
        latest_nodes=latest_nodes,
        latest_associations=latest_associations,
    )


def _latest_graph_rows_for_ids(
    *,
    graph: Mapping[str, Any],
    history_field: str,
    id_field: str,
    digest_field: str,
    head_field: str,
    required_ids: set[str],
) -> dict[str, Mapping[str, Any]]:
    """Read only the latest rows needed by one affected closure subgraph."""

    if not required_ids:
        return {}
    heads = graph.get(head_field)
    history = graph.get(history_field)
    if not isinstance(heads, Mapping) or not isinstance(history, list):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_INCREMENTAL_CLOSURE_HISTORY_INVALID"
        )
    missing = set(required_ids)
    result: dict[str, Mapping[str, Any]] = {}
    for row in reversed(history):
        identity = row.get(id_field)
        if (
            identity in missing
            and row.get(digest_field) == heads.get(identity)
        ):
            result[str(identity)] = row
            missing.remove(str(identity))
            if not missing:
                break
    if missing:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_INCREMENTAL_CLOSURE_HEAD_MISSING"
        )
    return result


def _verify_projection_evidence_dependency_closure_binding(
    projection: Mapping[str, Any],
) -> str:
    """Verify closure rows, digest and projection membership without graph rebuild."""

    supplied = projection.get(PROJECTION_CLOSURE_DIGEST_FIELD)
    rows = projection.get("evidence_dependency_closure")
    verified = _verify_evidence_dependency_closure_rows(rows)
    if not isinstance(supplied, str) or supplied != verified:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_PROJECTION_CLOSURE_DIGEST_INVALID"
        )
    closure_members = sorted(
        {
            dependency
            for row in rows
            for dependency in row["dependency_group_ids"]
        }
    )
    if closure_members != projection.get("dependency_group_ids"):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_PROJECTION_CLOSURE_INCOMPLETE"
        )
    return verified


def _verify_projection_evidence_dependency_closure(
    projection: Mapping[str, Any],
) -> str:
    """Verify one projection closure against one complete graph reconstruction."""

    verified = _verify_projection_evidence_dependency_closure_binding(
        projection
    )
    rows = projection["evidence_dependency_closure"]
    expected = _build_evidence_dependency_closure(
        projection["knowledge_graph"]
    )
    if rows != expected:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_PROJECTION_CLOSURE_RECONSTRUCTION_MISMATCH"
        )
    return verified


def _build_incremental_evidence_dependency_closure(
    *,
    previous_projection: Mapping[str, Any],
    graph: Mapping[str, Any],
    graph_delta: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Reuse the verified predecessor snapshot and replace affected evidence.

    Unaffected evidence rows are retained byte-for-byte.  Changed nodes and
    associations expand to their complete incident subgraph, and only missing
    current heads for that subgraph are located in history.  The function never
    rebuilds closure rows for the whole accumulated graph.
    """

    previous_rows = [
        dict(row) for row in previous_projection["evidence_dependency_closure"]
    ]
    previous_by_digest = {row["evidence_digest"]: row for row in previous_rows}
    previous_digest_by_node = {
        node_id: row["evidence_digest"]
        for row in previous_rows
        for node_id in row["node_ids"]
    }
    previous_digests_by_association: dict[str, set[str]] = {}
    for row in previous_rows:
        for association_id in row["association_ids"]:
            previous_digests_by_association.setdefault(
                association_id, set()
            ).add(row["evidence_digest"])

    delta_nodes, delta_associations = _validated_delta_heads(
        graph=graph, graph_delta=graph_delta
    )
    affected_digests = {
        previous_digest_by_node[node_id]
        for node_id in delta_nodes
        if node_id in previous_digest_by_node
    }
    affected_digests.update(
        node["payload_digest"]
        for node in delta_nodes.values()
        if node["payload_digest"] in previous_by_digest
    )
    for association_id in delta_associations:
        affected_digests.update(
            previous_digests_by_association.get(association_id, set())
        )

    affected_node_ids = set(delta_nodes)
    affected_association_ids = set(delta_associations)
    current_associations: dict[str, Mapping[str, Any]] = dict(
        delta_associations
    )
    while True:
        before = (
            len(affected_digests),
            len(affected_node_ids),
            len(affected_association_ids),
        )
        for evidence_digest in tuple(affected_digests):
            previous_row = previous_by_digest.get(evidence_digest)
            if previous_row is None:
                continue
            affected_node_ids.update(previous_row["node_ids"])
            affected_association_ids.update(previous_row["association_ids"])
        missing_association_ids = (
            affected_association_ids - set(current_associations)
        )
        current_associations.update(
            _latest_graph_rows_for_ids(
                graph=graph,
                history_field="association_history",
                id_field="association_id",
                digest_field="association_digest",
                head_field="latest_association_digests",
                required_ids=missing_association_ids,
            )
        )
        for association in current_associations.values():
            for node_id in (
                association["source_node_id"],
                association["target_node_id"],
            ):
                affected_node_ids.add(node_id)
                previous_digest = previous_digest_by_node.get(node_id)
                if previous_digest is not None:
                    affected_digests.add(previous_digest)
        after = (
            len(affected_digests),
            len(affected_node_ids),
            len(affected_association_ids),
        )
        if after == before:
            break

    current_nodes: dict[str, Mapping[str, Any]] = dict(delta_nodes)
    current_nodes.update(
        _latest_graph_rows_for_ids(
            graph=graph,
            history_field="node_history",
            id_field="node_id",
            digest_field="node_digest",
            head_field="latest_node_digests",
            required_ids=affected_node_ids - set(current_nodes),
        )
    )
    reused = [
        row
        for row in previous_rows
        if row["evidence_digest"] not in affected_digests
    ]
    recomputed = _evidence_dependency_closure_from_heads(
        latest_nodes=current_nodes,
        latest_associations=current_associations,
    )
    result = sorted(
        [*reused, *recomputed], key=lambda row: row["evidence_digest"]
    )
    _verify_evidence_dependency_closure_rows(result)
    if (
        {node_id for row in result for node_id in row["node_ids"]}
        != set(graph["latest_node_digests"])
        or {
            association_id
            for row in result
            for association_id in row["association_ids"]
        }
        != set(graph["latest_association_digests"])
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_INCREMENTAL_CLOSURE_COVERAGE_INVALID"
        )
    return result


def _node(
    *,
    node_id: str,
    node_type: str,
    label: str,
    description: str,
    payload_ref: str,
    payload_digest: str,
    observed_at: str,
    available_at: str,
    created_at: str,
    dependency_group_ids: Sequence[str],
    limitations: Sequence[str],
    prior_revision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    revision = 1 if prior_revision is None else int(prior_revision["revision"]) + 1
    predecessor = None if prior_revision is None else prior_revision["node_digest"]
    identity_created_at = (
        created_at if prior_revision is None else str(prior_revision["created_at"])
    )
    return build_graph_node_revision(
        {
            "schema_version": "V3_1_GRAPH_NODE_REVISION",
            "node_id": node_id,
            "revision": revision,
            "predecessor_digest": predecessor,
            "node_type": node_type,
            "label": label,
            "description": description,
            "payload_ref": payload_ref,
            "payload_digest": payload_digest,
            "observed_at": observed_at,
            "available_at": available_at,
            "validity": {"valid_from": observed_at, "valid_until": None},
            "status": "ACTIVE",
            "dependency_group_ids": _sorted_unique(
                dependency_group_ids, "V32_GRAPH_NODE_DEPENDENCY_INVALID"
            ),
            "provenance": [
                {
                    "source_ref": payload_ref,
                    "source_digest": payload_digest,
                    "observed_at": observed_at,
                    "available_at": available_at,
                    "revision_ref": "SOURCE_REVISION_1",
                }
            ],
            "created_at": identity_created_at,
            "limitations": _sorted_unique(
                limitations, "V32_GRAPH_NODE_LIMITATIONS_INVALID"
            ),
        },
        decision_at=available_at,
        prior_revision=prior_revision,
    )


def _association(
    *,
    association_id: str,
    source_node_id: str,
    target_node_id: str,
    relation: str,
    observed_at: str,
    available_at: str,
    created_at: str,
    dependency_group_ids: Sequence[str],
    analysis_bundle_digest: str,
    limitations: Sequence[str] = (),
    prior_revision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    revision = 1 if prior_revision is None else int(prior_revision["revision"]) + 1
    predecessor = (
        None if prior_revision is None else prior_revision["association_digest"]
    )
    identity_created_at = (
        created_at if prior_revision is None else str(prior_revision["created_at"])
    )
    return build_association_revision(
        {
            "schema_version": "V3_1_ASSOCIATION_REVISION",
            "association_id": association_id,
            "revision": revision,
            "predecessor_digest": predecessor,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "relation": relation,
            "association_type": "OBSERVED_ASSOCIATION",
            "method": "EXACT_TYPED_PROVENANCE_LINK",
            "interpretation_boundary": "ASSOCIATIONAL_NOT_CAUSAL",
            "estimate_interval": {
                "lower": None,
                "point": None,
                "upper": None,
                "scale": "NOT_ESTIMATED",
                "unit": "NONE",
                "interval_kind": "NOT_ESTIMATED",
            },
            "window": {
                "start_at": observed_at,
                "end_at": observed_at,
                "timeframe": "POINT_IN_TIME_PROVENANCE",
                "sample_count": 1,
            },
            "lag": {"value": 0, "unit": "SECONDS", "direction": "SYNCHRONOUS"},
            "regime": {"regime_ids": [], "condition_refs": []},
            "coverage": {"ratio": "1", "status": "COMPLETE", "limitations": []},
            "stability": {
                "assessment": "UNKNOWN",
                "evidence_window_count": 0,
                "break_refs": [],
            },
            "dependency_group_ids": _sorted_unique(
                dependency_group_ids, "V32_GRAPH_EDGE_DEPENDENCY_INVALID"
            ),
            "provenance": [
                {
                    "source_ref": "public-market-analysis-bundle",
                    "source_digest": analysis_bundle_digest,
                    "observed_at": observed_at,
                    "available_at": available_at,
                    "revision_ref": "ANALYSIS_BUNDLE_REVISION_1",
                }
            ],
            "validity": {"valid_from": observed_at, "valid_until": None},
            "identification_contract": None,
            "status": "ACTIVE",
            "created_at": identity_created_at,
            "available_at": available_at,
            "limitations": sorted(
                {
                    "PROVENANCE_LINK_ONLY",
                    "NOT_CAUSAL_NOT_PREDICTIVE_NOT_ACTOR_IDENTIFICATION",
                    *limitations,
                }
            ),
        },
        decision_at=available_at,
        prior_revision=prior_revision,
    )


def _projection_parts(
    analysis_bundle: Mapping[str, Any],
    previous_projection: Mapping[str, Any] | None,
    *,
    verify_previous_closure_fully: bool = True,
    verified_current_closure: list[dict[str, Any]] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    list[str],
    list[str],
    list[str],
    list[str],
    list[str],
]:
    analysis_digest = verify_v32_public_market_analysis_bundle(analysis_bundle)
    axis_registry_digest = _verified_axis_registry_digest()
    if analysis_bundle.get("axis_source_registry_digest") != axis_registry_digest:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_AXIS_SOURCE_REGISTRY_BINDING_INVALID"
        )
    run_id = _text(analysis_bundle.get("run_id"), "V32_GRAPH_RUN_INVALID")
    cycle_index = analysis_bundle.get("cycle_index")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 16
    ):
        raise V32PublicMarketGraphProjectionError("V32_GRAPH_CYCLE_INVALID")
    available_at = _text(
        analysis_bundle.get("available_at"), "V32_GRAPH_TIME_INVALID"
    )
    market_as_of = _text(
        analysis_bundle.get("as_of"), "V32_GRAPH_TIME_INVALID"
    )
    available = _moment(available_at, "V32_GRAPH_TIME_INVALID")
    if _moment(market_as_of, "V32_GRAPH_TIME_INVALID") > available:
        raise V32PublicMarketGraphProjectionError("V32_GRAPH_FUTURE_SOURCE_FORBIDDEN")
    requests = analysis_bundle["request_raw_bindings"]
    created_at = min(row["request_started_at"] for row in requests)
    if _moment(created_at, "V32_GRAPH_TIME_INVALID") >= available:
        raise V32PublicMarketGraphProjectionError("V32_GRAPH_TIME_ORDER_INVALID")

    if cycle_index == 1:
        if previous_projection is not None:
            raise V32PublicMarketGraphProjectionError(
                "V32_GRAPH_INITIAL_PREDECESSOR_FORBIDDEN"
            )
        graph = create_market_knowledge_graph(
            graph_id=f"v32-public-market:{run_id}", created_at=created_at
        )
    else:
        if (
            not isinstance(previous_projection, Mapping)
            or set(previous_projection) != _PROJECTION_FIELDS
        ):
            raise V32PublicMarketGraphProjectionError(
                "V32_GRAPH_PREVIOUS_PROJECTION_REQUIRED"
            )
        try:
            verify_self_digest(
                previous_projection, GRAPH_PROJECTION_DIGEST_FIELD
            )
            graph = dict(previous_projection["knowledge_graph"])
            verify_market_knowledge_graph(
                graph, decision_at=previous_projection["available_at"]
            )
            if verify_previous_closure_fully:
                _verify_projection_evidence_dependency_closure(
                    previous_projection
                )
            else:
                _verify_projection_evidence_dependency_closure_binding(
                    previous_projection
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise V32PublicMarketGraphProjectionError(
                "V32_GRAPH_PREVIOUS_PROJECTION_INVALID"
            ) from exc
        if (
            previous_projection.get("run_id") != run_id
            or previous_projection.get("cycle_index") != cycle_index - 1
            or previous_projection.get("knowledge_graph_digest")
            != graph.get("graph_digest")
            or graph.get("graph_id") != f"v32-public-market:{run_id}"
            or _moment(
                previous_projection.get("available_at"),
                "V32_GRAPH_PREVIOUS_TIME_INVALID",
            )
            >= available
        ):
            raise V32PublicMarketGraphProjectionError(
                "V32_GRAPH_PREVIOUS_PROJECTION_DISCONNECTED"
            )

    latest_nodes = {
        row["node_id"]: row
        for row in graph["node_history"]
        if row["node_digest"] == graph["latest_node_digests"].get(row["node_id"])
    }
    latest_associations = {
        row["association_id"]: row
        for row in graph["association_history"]
        if row["association_digest"]
        == graph["latest_association_digests"].get(row["association_id"])
    }

    events = analysis_bundle["information_events"]
    datums = analysis_bundle["datums"]
    axes = analysis_bundle["axis_source_evidence"]
    event_by_component = {row["component_id"]: row for row in events}
    nodes: list[dict[str, Any]] = []
    event_ids: list[str] = []
    datum_ids: list[str] = []
    axis_ids: list[str] = []

    for row in events:
        node_id = f"source-event:{row['event_id']}"
        event_ids.append(node_id)
        observable_family = _observable_family_dependency(row["component_id"])
        nodes.append(
            _node(
                node_id=node_id,
                node_type="INFORMATION_EVENT",
                label=f"OKX public {row['component_id']}",
                description=(
                    "Observed official public response"
                    if row["status"] == "OBSERVED"
                    else "Typed public-source coverage unknown"
                ),
                payload_ref=f"analysis:information-event:{row['event_id']}",
                payload_digest=row[INFORMATION_EVENT_DIGEST_FIELD],
                observed_at=row["request_started_at"],
                available_at=row["available_at"],
                created_at=created_at,
                dependency_group_ids=[
                    *row["dependency_group_ids"],
                    observable_family,
                ],
                limitations=[row["claim_ceiling"], "PUBLIC_SOURCE_ONLY"],
                prior_revision=latest_nodes.get(node_id),
            )
        )

    for row in datums:
        node_id = f"market-datum:{row['datum_id']}"
        datum_ids.append(node_id)
        observable_family = _observable_family_dependency(
            row["source_component_id"]
        )
        observed_at = row["observed_at"] or row["available_at"]
        node_type = "DERIVED_MEASURE" if row["status"] == "DERIVED" else "MARKET_FACT"
        limitations = [
            row["derivation"],
            "UNKNOWN_IS_NOT_ZERO" if row["status"] == "UNKNOWN" else "VALUE_NOT_CAUSAL",
        ]
        nodes.append(
            _node(
                node_id=node_id,
                node_type=node_type,
                label=f"{row['metric_kind']} ({row['datum_id']})",
                description=(
                    "Explicit unknown point-in-time datum"
                    if row["status"] == "UNKNOWN"
                    else "Point-in-time public market datum"
                ),
                payload_ref=f"analysis:datum:{row['datum_id']}",
                payload_digest=row[PIT_DATUM_DIGEST_FIELD],
                observed_at=observed_at,
                available_at=row["available_at"],
                created_at=created_at,
                dependency_group_ids=[
                    *row["dependency_group_ids"],
                    observable_family,
                ],
                limitations=limitations,
                prior_revision=latest_nodes.get(node_id),
            )
        )

    for row in axes:
        node_id = f"market-axis:{row['axis_id']}"
        axis_ids.append(node_id)
        observed_at = row["observed_at"] or row["available_at"]
        dependencies = ["VENUE:OKX", f"AXIS:{row['axis_id']}"]
        dependencies.extend(
            f"REQUEST:{component_id}" for component_id in row["source_component_ids"]
        )
        dependencies.extend(
            _observable_family_dependency(component_id)
            for component_id in row["source_component_ids"]
        )
        if row["axis_id"] == "OTHER":
            dependencies.append("RESIDUAL:OTHER")
        for assessment in row["source_assessments"]:
            dependencies.extend(
                [
                    f"SOURCE_KIND:{assessment['source_kind']}",
                    f"EVIDENCE_ROLE:{assessment['evidence_role']}",
                    f"ADMISSION:{assessment['admission_status']}",
                    (
                        "AXIS_SOURCE:"
                        f"{row['axis_id']}:"
                        f"{assessment['source_kind']}:"
                        f"{assessment['evidence_role']}:"
                        f"{assessment['admission_status']}"
                    ),
                ]
            )
        limitations = [
            row["claim_ceiling"],
            row["reason_code"] or "NO_REASON_CODE",
            f"AXIS_ADMISSION:{row['admission_status']}",
            "SOURCE_COVERAGE_NOT_DIRECTIONAL_STATE",
        ]
        limitations.extend(
            f"SOURCE_CLAIM_CEILING:{assessment['claim_ceiling']}"
            for assessment in row["source_assessments"]
        )
        limitations.extend(
            f"SOURCE_REASON:{assessment['reason_code']}"
            for assessment in row["source_assessments"]
            if assessment["reason_code"] is not None
        )
        nodes.append(
            _node(
                node_id=node_id,
                node_type="LATENT_STATE",
                label=f"Market analysis axis {row['axis_id']}",
                description=(
                    "Source coverage for an analysis axis; no direction precomputed"
                ),
                payload_ref=f"analysis:axis:{row['axis_id']}",
                payload_digest=row[AXIS_EVIDENCE_DIGEST_FIELD],
                observed_at=observed_at,
                available_at=row["available_at"],
                created_at=created_at,
                dependency_group_ids=dependencies,
                limitations=limitations,
                prior_revision=latest_nodes.get(node_id),
            )
        )

    associations: list[dict[str, Any]] = []
    for row in datums:
        observed_at = row["observed_at"] or row["available_at"]
        component = row["source_component_id"]
        associations.append(
            _association(
                association_id=f"provenance:event-to-datum:{row['datum_id']}",
                source_node_id=f"source-event:{event_by_component[component]['event_id']}",
                target_node_id=f"market-datum:{row['datum_id']}",
                relation="PRODUCES",
                observed_at=observed_at,
                available_at=available_at,
                created_at=created_at,
                dependency_group_ids=[
                    *row["dependency_group_ids"],
                    _observable_family_dependency(component),
                    "PROJECTION:EVENT_DATUM",
                ],
                analysis_bundle_digest=analysis_digest,
                prior_revision=latest_associations.get(
                    f"provenance:event-to-datum:{row['datum_id']}"
                ),
            )
        )
    for row in axes:
        observed_at = row["observed_at"] or row["available_at"]
        for component in row["source_component_ids"]:
            component_assessments = [
                assessment
                for assessment in row["source_assessments"]
                if component in assessment["source_component_ids"]
            ]
            assessment_dependencies = [
                value
                for assessment in component_assessments
                for value in (
                    f"SOURCE_KIND:{assessment['source_kind']}",
                    f"EVIDENCE_ROLE:{assessment['evidence_role']}",
                    f"ADMISSION:{assessment['admission_status']}",
                    (
                        "AXIS_SOURCE:"
                        f"{row['axis_id']}:"
                        f"{assessment['source_kind']}:"
                        f"{assessment['evidence_role']}:"
                        f"{assessment['admission_status']}"
                    ),
                )
            ]
            assessment_limitations = [
                value
                for assessment in component_assessments
                for value in (
                    f"SOURCE_CLAIM_CEILING:{assessment['claim_ceiling']}",
                    (
                        "SOURCE_ADMISSION:"
                        f"{assessment['admission_status']}"
                    ),
                )
            ]
            associations.append(
                _association(
                    association_id=f"provenance:event-to-axis:{component}:{row['axis_id']}",
                    source_node_id=f"source-event:{event_by_component[component]['event_id']}",
                    target_node_id=f"market-axis:{row['axis_id']}",
                    relation="DESCRIBES",
                    observed_at=observed_at,
                    available_at=available_at,
                    created_at=created_at,
                    dependency_group_ids=[
                        "VENUE:OKX",
                        f"REQUEST:{component}",
                        _observable_family_dependency(component),
                        f"AXIS:{row['axis_id']}",
                        "PROJECTION:EVENT_AXIS",
                        *assessment_dependencies,
                    ],
                    analysis_bundle_digest=analysis_digest,
                    limitations=[
                        f"AXIS_ADMISSION:{row['admission_status']}",
                        *assessment_limitations,
                    ],
                    prior_revision=latest_associations.get(
                        f"provenance:event-to-axis:{component}:{row['axis_id']}"
                    ),
                )
            )
    delta_dependencies = sorted(
        {
            dependency
            for item in [*nodes, *associations]
            for dependency in item["dependency_group_ids"]
        }
    )
    delta, projected = build_and_apply_v32_graph_delta(
        {
            "schema_version": "V3_1_GRAPH_DELTA",
            "delta_id": f"v32-public-market-cycle-{cycle_index:04d}",
            "graph_id": graph["graph_id"],
            "base_graph_revision": graph["revision"],
            "base_graph_digest": graph["graph_digest"],
            "revision": graph["revision"] + 1,
            "occurred_at": created_at,
            "available_at": available_at,
            "node_revisions": nodes,
            "association_revisions": associations,
            "dependency_group_ids": delta_dependencies,
            "reason": "PUBLIC_MARKET_ANALYSIS_BUNDLE_TYPED_PROJECTION",
        },
        decision_at=available_at,
        prior_graph=graph,
    )
    if verified_current_closure is not None:
        evidence_dependency_closure = [
            dict(row) for row in verified_current_closure
        ]
        _verify_evidence_dependency_closure_rows(
            evidence_dependency_closure
        )
    else:
        evidence_dependency_closure = (
            _build_evidence_dependency_closure(projected)
            if previous_projection is None
            else _build_incremental_evidence_dependency_closure(
                previous_projection=previous_projection,
                graph=projected,
                graph_delta=delta,
            )
        )
    cumulative_dependencies = sorted(projected["dependency_index"])
    return (
        projected,
        delta,
        evidence_dependency_closure,
        sorted(event_ids),
        sorted(datum_ids),
        sorted(axis_ids),
        sorted(row["association_id"] for row in associations),
        cumulative_dependencies,
    )


def _build_v32_public_market_graph_projection_v1(
    analysis_bundle: Mapping[str, Any],
    *,
    previous_projection: Mapping[str, Any] | None = None,
    verify_previous_closure_fully: bool = True,
    verified_current_closure: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    (
        graph,
        delta,
        evidence_dependency_closure,
        event_ids,
        datum_ids,
        axis_ids,
        association_ids,
        dependencies,
    ) = _projection_parts(
        analysis_bundle,
        previous_projection,
        verify_previous_closure_fully=verify_previous_closure_fully,
        verified_current_closure=verified_current_closure,
    )
    native_axes, proxy_axes, derived_axes, unknown_axes = _axis_coverage_sets(
        analysis_bundle["axis_source_evidence"]
    )
    axis_registry_digest = _verified_axis_registry_digest()
    return self_digest(
        {
            "schema_id": GRAPH_PROJECTION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": analysis_bundle["run_id"],
            "cycle_index": analysis_bundle["cycle_index"],
            "market_as_of": analysis_bundle["as_of"],
            "available_at": analysis_bundle["available_at"],
            "analysis_bundle_digest": analysis_bundle[ANALYSIS_BUNDLE_DIGEST_FIELD],
            "axis_source_registry_digest": axis_registry_digest,
            "previous_graph_projection_digest": (
                None
                if previous_projection is None
                else previous_projection[GRAPH_PROJECTION_DIGEST_FIELD]
            ),
            "graph_delta": delta,
            "graph_delta_digest": delta["graph_delta_digest"],
            "knowledge_graph": graph,
            "knowledge_graph_digest": graph["graph_digest"],
            "knowledge_graph_revision": graph["revision"],
            "source_event_node_ids": event_ids,
            "datum_node_ids": datum_ids,
            "axis_node_ids": axis_ids,
            "provenance_association_ids": association_ids,
            "dependency_group_ids": dependencies,
            "evidence_dependency_closure": evidence_dependency_closure,
            PROJECTION_CLOSURE_DIGEST_FIELD: canonical_digest(
                evidence_dependency_closure
            ),
            "native_axis_ids": native_axes,
            "proxy_axis_ids": proxy_axes,
            "derived_axis_ids": derived_axes,
            "unknown_axis_ids": unknown_axes,
            "twelve_axes_native": native_axes
            == sorted(V31_NATIVE_SENTIMENT_AXES),
            "unknown_retained": bool(unknown_axes),
            "other_retained": "market-axis:OTHER" in axis_ids,
            "causal_claim": "NONE_PROVENANCE_ASSOCIATIONS_ONLY",
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
            "account_data_accessed": False,
            "order_data_accessed": False,
        },
        GRAPH_PROJECTION_DIGEST_FIELD,
    )


def build_v32_public_market_graph_projection_v1(
    analysis_bundle: Mapping[str, Any],
    *,
    previous_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_v32_public_market_graph_projection_v1(
        analysis_bundle,
        previous_projection=previous_projection,
    )


def _verify_v32_public_market_graph_projection_once_uncached(
    document: Mapping[str, Any],
    *,
    analysis_bundle: Mapping[str, Any],
    previous_projection: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Verify one projection with exactly one full current-graph closure rebuild.

    The reconstructed closure is reused to rebuild the projection.  A cycle-2+
    predecessor is checked structurally and by its sealed digest here; its full
    closure was owned by the preceding projection scope.  The public projection
    builder keeps its stronger standalone predecessor check.
    """

    if not isinstance(document, Mapping) or set(document) != _PROJECTION_FIELDS:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_PROJECTION_SCHEMA_INVALID"
        )
    try:
        supplied = verify_self_digest(document, GRAPH_PROJECTION_DIGEST_FIELD)
        closure_digest = _verify_projection_evidence_dependency_closure_binding(
            document
        )
        expected_closure = _build_evidence_dependency_closure(
            document["knowledge_graph"]
        )
        if document["evidence_dependency_closure"] != expected_closure:
            raise V32PublicMarketGraphProjectionError(
                "V32_GRAPH_PROJECTION_CLOSURE_RECONSTRUCTION_MISMATCH"
            )
        rebuilt = _build_v32_public_market_graph_projection_v1(
            analysis_bundle,
            previous_projection=previous_projection,
            verify_previous_closure_fully=False,
            verified_current_closure=expected_closure,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicMarketGraphProjectionError):
            raise
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_PROJECTION_INVALID"
        ) from exc
    if (
        closure_digest != document[PROJECTION_CLOSURE_DIGEST_FIELD]
        or dict(document) != rebuilt
        or supplied != rebuilt[GRAPH_PROJECTION_DIGEST_FIELD]
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_PROJECTION_RECONSTRUCTION_MISMATCH"
        )
    return supplied, closure_digest


def _verify_v32_public_market_graph_projection_once(
    document: Mapping[str, Any],
    *,
    analysis_bundle: Mapping[str, Any],
    previous_projection: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Verify once, memoizing only exact successful strict snapshots."""

    memo = _PUBLIC_GRAPH_VERIFICATION_MEMO.get()
    if memo is None:
        return _verify_v32_public_market_graph_projection_once_uncached(
            document,
            analysis_bundle=analysis_bundle,
            previous_projection=previous_projection,
        )
    if memo.owner != _execution_owner():
        # asyncio tasks copy ContextVars.  A child task must never consume the
        # mutable verification authority created by its parent task.
        with v32_public_graph_verification_scope_v1():
            return _verify_v32_public_market_graph_projection_once(
                document,
                analysis_bundle=analysis_bundle,
                previous_projection=previous_projection,
            )

    document_snapshot = _strict_builtin_json_snapshot(document)
    analysis_snapshot = _strict_builtin_json_snapshot(analysis_bundle)
    previous_snapshot = _strict_builtin_json_snapshot(previous_projection)
    if any(
        snapshot is _STRICT_SNAPSHOT_UNAVAILABLE
        for snapshot in (
            document_snapshot,
            analysis_snapshot,
            previous_snapshot,
        )
    ):
        return _verify_v32_public_market_graph_projection_once_uncached(
            document,
            analysis_bundle=analysis_bundle,
            previous_projection=previous_projection,
        )

    key = (
        "PUBLIC_MARKET_GRAPH_PROJECTION_V1",
        canonical_bytes(
            {
                "document": document_snapshot,
                "analysis_bundle": analysis_snapshot,
                "previous_projection": previous_snapshot,
            }
        ),
    )
    cached = memo.results.get(key, _MEMO_MISSING)
    if cached is not _MEMO_MISSING:
        return cached
    result = _verify_v32_public_market_graph_projection_once_uncached(
        document_snapshot,
        analysis_bundle=analysis_snapshot,
        previous_projection=previous_snapshot,
    )
    memo.results[key] = result
    return result


def verify_v32_public_market_graph_projection_v1(
    document: Mapping[str, Any],
    *,
    analysis_bundle: Mapping[str, Any],
    previous_projection: Mapping[str, Any] | None = None,
) -> str:
    supplied, _ = _verify_v32_public_market_graph_projection_once(
        document,
        analysis_bundle=analysis_bundle,
        previous_projection=previous_projection,
    )
    return supplied


def build_v32_verified_graph_dependency_registry_v1(
    *,
    graph_projection: Mapping[str, Any],
    analysis_bundle: Mapping[str, Any],
    decision_time: str,
    previous_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    projection_digest, projection_closure_digest = (
        _verify_v32_public_market_graph_projection_once(
            graph_projection,
            analysis_bundle=analysis_bundle,
            previous_projection=previous_projection,
        )
    )
    decision = _moment(decision_time, "V32_GRAPH_REGISTRY_TIME_INVALID")
    if decision < _moment(
        graph_projection["available_at"], "V32_GRAPH_REGISTRY_TIME_INVALID"
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_REGISTRY_FUTURE_PROJECTION_FORBIDDEN"
        )
    evidence_dependency_closure = [
        dict(row) for row in graph_projection["evidence_dependency_closure"]
    ]
    if (
        projection_closure_digest
        != graph_projection[PROJECTION_CLOSURE_DIGEST_FIELD]
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_REGISTRY_PROJECTION_CLOSURE_BINDING_INVALID"
        )
    closure_members = sorted(
        {
            dependency
            for row in evidence_dependency_closure
            for dependency in row["dependency_group_ids"]
        }
    )
    if closure_members != graph_projection["dependency_group_ids"]:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_REGISTRY_EVIDENCE_CLOSURE_INCOMPLETE"
        )
    return self_digest(
        {
            "schema_id": GRAPH_REGISTRY_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "run_id": graph_projection["run_id"],
            "cycle_index": graph_projection["cycle_index"],
            "as_of": decision_time,
            "members": list(graph_projection["dependency_group_ids"]),
            "evidence_dependency_policy": dict(
                _EVIDENCE_DEPENDENCY_POLICY
            ),
            "evidence_dependency_closure": evidence_dependency_closure,
            "upstream_schema_id": GRAPH_PROJECTION_SCHEMA_ID,
            "upstream_digest_field": GRAPH_PROJECTION_DIGEST_FIELD,
            "upstream_semantic_digest": projection_digest,
            "full_verification_receipt_digest": projection_digest,
            "source_scope": SOURCE_SCOPE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
        },
        GRAPH_REGISTRY_DIGEST_FIELD,
    )


def verify_v32_verified_graph_dependency_registry_v1(
    document: Mapping[str, Any],
    *,
    graph_projection: Mapping[str, Any],
    analysis_bundle: Mapping[str, Any],
    previous_projection: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _REGISTRY_FIELDS:
        raise V32PublicMarketGraphProjectionError("V32_GRAPH_REGISTRY_SCHEMA_INVALID")
    closure = document.get("evidence_dependency_closure")
    if (
        document.get("evidence_dependency_policy")
        != _EVIDENCE_DEPENDENCY_POLICY
    ):
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_REGISTRY_EVIDENCE_CLOSURE_INVALID"
        )
    try:
        _verify_evidence_dependency_closure_rows(closure)
    except (KeyError, TypeError, ValueError, V32PublicMarketGraphProjectionError) as exc:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_REGISTRY_EVIDENCE_CLOSURE_INVALID"
        ) from exc
    try:
        supplied = verify_self_digest(document, GRAPH_REGISTRY_DIGEST_FIELD)
        rebuilt = build_v32_verified_graph_dependency_registry_v1(
            graph_projection=graph_projection,
            analysis_bundle=analysis_bundle,
            decision_time=document["as_of"],
            previous_projection=previous_projection,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PublicMarketGraphProjectionError):
            raise
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_REGISTRY_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[GRAPH_REGISTRY_DIGEST_FIELD]:
        raise V32PublicMarketGraphProjectionError(
            "V32_GRAPH_REGISTRY_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "GRAPH_PROJECTION_DIGEST_FIELD",
    "GRAPH_PROJECTION_SCHEMA_ID",
    "GRAPH_REGISTRY_DIGEST_FIELD",
    "GRAPH_REGISTRY_SCHEMA_ID",
    "PROJECTION_CLOSURE_DIGEST_FIELD",
    "V32PublicMarketGraphProjectionError",
    "build_v32_public_market_graph_projection_v1",
    "build_v32_verified_graph_dependency_registry_v1",
    "v32_public_graph_verification_scope_v1",
    "verify_v32_public_market_graph_projection_v1",
    "verify_v32_verified_graph_dependency_registry_v1",
]
