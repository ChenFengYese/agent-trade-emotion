"""Pure bounded V3.2 Agent market-view contract.

This Domain module knows only the sealed view shape and byte budget.  It does
not import Application or Infrastructure and cannot collect or reconstruct
market data.  Full upstream replay belongs to the Application composition.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
    verify_self_digest,
)


class V32AgentMarketGraphViewError(ValueError):
    """The bounded Agent market view violated its pure contract."""


SCHEMA_ID = "theory_paper_v32_agent_market_graph_view_v1"
DIGEST_FIELD = "agent_market_graph_view_digest"
SCHEMA_VERSION = "1.1.0"

# The inline view remains hard-capped at 256 KiB.  Large decision-irrelevant
# closure lists remain in the verified owning graph registry; the Agent view
# carries their exact semantic digest and counts plus every dependency group.
# Full Application replay rebuilds the index from that registry.  The complete
# packet still uses lossless shards if its independent ceiling is exceeded.
MAX_CANONICAL_BYTES = 256 * 1024

VIEW_POLICY = {
    "closed_bars": "EXACT_ALL_ADMITTED_NO_TRUNCATION",
    "non_bar_datums": "EXACT_ALL_CURRENT_NO_TRUNCATION",
    "claim_ceilings": "ALL_CURRENT_SOURCE_EVENTS_AND_AXES",
    "evidence_closure": (
        "ALL_AGENT_CITABLE_EVIDENCE_DIGESTS_AVAILABILITY_STATUS_FULL_"
        "DEPENDENCY_GROUPS_EXACT_CLOSURE_DIGEST_AND_COUNTS"
    ),
    "owning_closure_lists": (
        "FULL_EVIDENCE_REFS_NODE_IDS_AND_ASSOCIATION_IDS_RETAINED_IN_"
        "VERIFIED_GRAPH_REGISTRY_AND_EXACTLY_REBUILT_BY_OWNING_VERIFIER"
    ),
    "bar_citation": (
        "EXACT_BARS_CITE_THEIR_OFFICIAL_CANDLE_RESPONSE_EVENT_NOT_PER_FIELD_NODES"
    ),
    "history": "CURRENT_GRAPH_DELTA_ONLY_NO_REPEATED_CUMULATIVE_NODE_HISTORY",
    "overflow": "FAIL_CLOSED_NO_TRUNCATION_OR_OBJECT_DROPPING",
}

_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "available_at",
        "instrument",
        "upstream_digests",
        "closed_bar_series",
        "closed_bar_evidence",
        "current_non_bar_datums",
        "source_event_claim_ceilings",
        "axis_source_evidence",
        "citable_evidence_records",
        "evidence_dependency_policy",
        "graph_delta_summary",
        "content_counts",
        "unknown_retained",
        "other_retained",
        "causal_claim",
        "view_policy",
        "canonical_payload_bytes",
        "max_canonical_payload_bytes",
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_data_accessed",
        "order_data_accessed",
        DIGEST_FIELD,
    }
)
_EVIDENCE_RECORD_FIELDS = frozenset(
    {
        "evidence_digest",
        "available_at",
        "closure_status",
        "dependency_group_ids",
        "evidence_ref_count",
        "node_id_count",
        "association_id_count",
        "dependency_group_id_count",
        "exact_closure_digest",
    }
)
_EXPANDED_EVIDENCE_RECORD_FIELDS = frozenset(
    {
        "evidence_digest",
        "available_at",
        "closure_status",
        "evidence_refs",
        "node_ids",
        "association_ids",
        "dependency_group_ids",
    }
)
_SOURCE_CLAIM_FIELDS = frozenset(
    {
        "event_id",
        "component_id",
        "status",
        "available_at",
        "claim_ceiling",
        "public_source_event_digest",
    }
)
_GRAPH_DELTA_SUMMARY_FIELDS = frozenset(
    {
        "graph_delta_digest",
        "base_graph_revision",
        "base_graph_digest",
        "revision",
        "occurred_at",
        "available_at",
        "node_revision_count",
        "association_revision_count",
        "dependency_group_ids",
    }
)
_UPSTREAM_DIGEST_FIELDS = frozenset(
    {
        "public_market_analysis_bundle_digest",
        "public_market_graph_projection_digest",
        "graph_dependency_registry_digest",
        "pit_evidence_availability_registry_digest",
    }
)


def project_v32_agent_market_graph_closure_record_v1(
    expanded_record: Mapping[str, Any],
    *,
    exact_closure_digest: str | None = None,
) -> dict[str, Any]:
    """Project one full owning closure into a bounded, tamper-evident index."""

    if not isinstance(expanded_record, Mapping) or set(expanded_record) != (
        _EXPANDED_EVIDENCE_RECORD_FIELDS
    ):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_CLOSURE_INVALID"
        )
    row = dict(expanded_record)
    for field in (
        "evidence_refs",
        "node_ids",
        "association_ids",
        "dependency_group_ids",
    ):
        value = row[field]
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise V32AgentMarketGraphViewError(
                "V32_AGENT_MARKET_GRAPH_VIEW_CLOSURE_INVALID"
            )
    digest = (
        canonical_digest(row)
        if exact_closure_digest is None
        else exact_closure_digest
    )
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or set(digest) - set("0123456789abcdef")
    ):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_CLOSURE_INVALID"
        )
    return {
        "evidence_digest": row["evidence_digest"],
        "available_at": row["available_at"],
        "closure_status": row["closure_status"],
        "dependency_group_ids": list(row["dependency_group_ids"]),
        "evidence_ref_count": len(row["evidence_refs"]),
        "node_id_count": len(row["node_ids"]),
        "association_id_count": len(row["association_ids"]),
        "dependency_group_id_count": len(row["dependency_group_ids"]),
        "exact_closure_digest": digest,
    }


def _valid_closure_index_record(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != _EVIDENCE_RECORD_FIELDS:
        return False
    groups = value.get("dependency_group_ids")
    counts = (
        value.get("evidence_ref_count"),
        value.get("node_id_count"),
        value.get("association_id_count"),
        value.get("dependency_group_id_count"),
    )
    digests = (value.get("evidence_digest"), value.get("exact_closure_digest"))
    return bool(
        isinstance(value.get("available_at"), str)
        and value["available_at"]
        and value.get("closure_status")
        in {"VERIFIED_COMPLETE_GRAPH_CLOSURE", "BUNDLE_ROOT_NO_GRAPH_NODE"}
        and isinstance(groups, list)
        and all(isinstance(group, str) and group for group in groups)
        and all(
            not isinstance(count, bool)
            and isinstance(count, int)
            and count >= 0
            for count in counts
        )
        and value.get("dependency_group_id_count") == len(groups)
        and all(
            isinstance(digest, str)
            and len(digest) == 64
            and set(digest) <= set("0123456789abcdef")
            for digest in digests
        )
    )


def seal_v32_agent_market_graph_view_v1(
    payload_without_digest: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal one complete view and converge its exact canonical byte count."""

    if not isinstance(payload_without_digest, Mapping):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_SCHEMA_INVALID"
        )
    candidate = dict(payload_without_digest)
    candidate.pop(DIGEST_FIELD, None)
    candidate["canonical_payload_bytes"] = 0
    for _ in range(8):
        sealed = self_digest(candidate, DIGEST_FIELD)
        size = len(canonical_bytes(sealed))
        if candidate["canonical_payload_bytes"] == size:
            if size > MAX_CANONICAL_BYTES:
                raise V32AgentMarketGraphViewError(
                    "V32_AGENT_MARKET_GRAPH_VIEW_PAYLOAD_TOO_LARGE"
                )
            verify_v32_agent_market_graph_view_intrinsic_v1(sealed)
            return sealed
        candidate["canonical_payload_bytes"] = size
    raise V32AgentMarketGraphViewError(
        "V32_AGENT_MARKET_GRAPH_VIEW_SIZE_DID_NOT_CONVERGE"
    )


def verify_v32_agent_market_graph_view_intrinsic_v1(
    document: Mapping[str, Any],
) -> str:
    """Verify the bounded shape before full upstream replay at acceptance."""

    if not isinstance(document, Mapping) or set(document) != _FIELDS:
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_SCHEMA_INVALID"
        )
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
    except (KeyError, TypeError, ValueError) as exc:
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_INVALID"
        ) from exc
    if (
        document.get("schema_id") != SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("max_canonical_payload_bytes") != MAX_CANONICAL_BYTES
        or document.get("canonical_payload_bytes")
        != len(canonical_bytes(dict(document)))
        or isinstance(document.get("canonical_payload_bytes"), bool)
        or not isinstance(document.get("canonical_payload_bytes"), int)
        or document["canonical_payload_bytes"] > MAX_CANONICAL_BYTES
        or any(
            not _valid_closure_index_record(row)
            for row in document.get("citable_evidence_records", ())
        )
        or any(
            not isinstance(row, Mapping) or set(row) != _SOURCE_CLAIM_FIELDS
            for row in document.get("source_event_claim_ceilings", ())
        )
        or not isinstance(document.get("graph_delta_summary"), Mapping)
        or set(document["graph_delta_summary"]) != _GRAPH_DELTA_SUMMARY_FIELDS
        or not isinstance(document.get("upstream_digests"), Mapping)
        or set(document["upstream_digests"]) != _UPSTREAM_DIGEST_FIELDS
        or document.get("view_policy") != VIEW_POLICY
        or document.get("source_scope") != "PUBLIC_NON_ACCOUNT_ONLY"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("account_data_accessed") is not False
        or document.get("order_data_accessed") is not False
    ):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_INVALID"
        )
    return supplied


__all__ = [
    "DIGEST_FIELD",
    "MAX_CANONICAL_BYTES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "VIEW_POLICY",
    "V32AgentMarketGraphViewError",
    "project_v32_agent_market_graph_closure_record_v1",
    "seal_v32_agent_market_graph_view_v1",
    "verify_v32_agent_market_graph_view_intrinsic_v1",
]
