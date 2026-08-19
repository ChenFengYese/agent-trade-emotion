"""Deterministic bounded Agent view of the full V3.2 public market graph.

The durable store and cycle acceptance retain and replay every full upstream
artifact.  The Agent receives this non-lossy *decision-facing* projection
instead of the cumulative multi-megabyte graph: exact closed bars, every
current non-bar datum, source and axis claim ceilings, and every citable
evidence digest with first availability, full dependency groups, exact owning
closure digest and counts.  Full closure lists remain in the verified registry
and are rebuilt by this owning Application verifier.  A view that cannot fit
the frozen byte budget fails closed.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..domain.v32_agent_market_graph_view import (
    DIGEST_FIELD,
    MAX_CANONICAL_BYTES,
    SCHEMA_ID,
    SCHEMA_VERSION,
    VIEW_POLICY,
    V32AgentMarketGraphViewError,
    project_v32_agent_market_graph_closure_record_v1,
    seal_v32_agent_market_graph_view_v1,
    verify_v32_agent_market_graph_view_intrinsic_v1,
)
from ..domain.v32_cycle_source_admission import verify_v32_pit_evidence_registry
from .v32_public_evidence_port import V32PublicEvidenceVerifierPort
from .v32_dynamic_state_continuity import (
    verify_v32_verified_pit_evidence_availability_registry_v1,
)


def build_v32_agent_market_graph_view_v1(
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    public_market_analysis_bundle: Mapping[str, Any],
    public_market_graph_projection: Mapping[str, Any],
    pit_evidence_registry: Mapping[str, Any],
    graph_dependency_registry: Mapping[str, Any],
    pit_evidence_availability_registry: Mapping[str, Any],
    previous_public_market_graph_projection: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Rebuild the complete bounded Agent-facing current-market projection."""

    try:
        bundle_digest = public_evidence_verifier.verify_public_market_analysis_bundle(
            public_market_analysis_bundle
        )
        projection_digest = public_evidence_verifier.verify_public_market_graph_projection(
            public_market_graph_projection,
            analysis_bundle=public_market_analysis_bundle,
            previous_projection=previous_public_market_graph_projection,
        )
        pit_digest = verify_v32_pit_evidence_registry(pit_evidence_registry)
        graph_digest = public_evidence_verifier.verify_graph_dependency_registry(
            graph_dependency_registry,
            graph_projection=public_market_graph_projection,
            analysis_bundle=public_market_analysis_bundle,
            previous_projection=previous_public_market_graph_projection,
        )
        availability_digest = (
            verify_v32_verified_pit_evidence_availability_registry_v1(
                pit_evidence_availability_registry,
                public_evidence_verifier=public_evidence_verifier,
                public_market_analysis_bundle=public_market_analysis_bundle,
                pit_evidence_registry=pit_evidence_registry,
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentMarketGraphViewError):
            raise
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_UPSTREAM_INVALID"
        ) from exc

    run_id = public_market_analysis_bundle.get("run_id")
    cycle_index = public_market_analysis_bundle.get("cycle_index")
    if (
        not isinstance(run_id, str)
        or not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 16
        or pit_evidence_registry.get("run_id") != run_id
        or pit_evidence_registry.get("cycle_index") != cycle_index
        or public_market_graph_projection.get("run_id") != run_id
        or public_market_graph_projection.get("cycle_index") != cycle_index
        or graph_dependency_registry.get("run_id") != run_id
        or graph_dependency_registry.get("cycle_index") != cycle_index
        or pit_evidence_availability_registry.get("run_id") != run_id
        or pit_evidence_availability_registry.get("cycle_index") != cycle_index
        or pit_evidence_availability_registry.get("pit_evidence_registry_digest")
        != pit_digest
    ):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_IDENTITY_INVALID"
        )

    availability = {
        row["evidence_ref"]: row["available_at"]
        for row in pit_evidence_availability_registry["entries"]
    }
    closure_by_digest = {
        row["evidence_digest"]: row
        for row in graph_dependency_registry["evidence_dependency_closure"]
    }
    if set(availability) != set(pit_evidence_registry["members"]):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_AVAILABILITY_COVERAGE_INVALID"
        )
    non_bar_datums = [
        dict(row)
        for row in public_market_analysis_bundle["datums"]
        if not row["datum_id"].startswith("bar-")
    ]
    source_claims = [
        {
            "event_id": row["event_id"],
            "component_id": row["component_id"],
            "status": row["status"],
            "available_at": row["available_at"],
            "claim_ceiling": row["claim_ceiling"],
            "public_source_event_digest": row["public_source_event_digest"],
        }
        for row in public_market_analysis_bundle["information_events"]
    ]
    citable_digests = {
        bundle_digest,
        *[row["pit_datum_digest"] for row in non_bar_datums],
        *[row["public_source_event_digest"] for row in source_claims],
        *[
            row["axis_source_evidence_digest"]
            for row in public_market_analysis_bundle["axis_source_evidence"]
        ],
    }
    if not citable_digests.issubset(availability):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_CITABLE_AVAILABILITY_MISSING"
        )
    evidence_records: list[dict[str, Any]] = []
    for evidence_digest in sorted(citable_digests):
        closure = closure_by_digest.get(evidence_digest)
        if closure is None:
            if evidence_digest != bundle_digest:
                raise V32AgentMarketGraphViewError(
                    "V32_AGENT_MARKET_GRAPH_VIEW_CLOSURE_MISSING"
                )
            expanded = {
                "evidence_digest": evidence_digest,
                "available_at": availability[evidence_digest],
                "closure_status": "BUNDLE_ROOT_NO_GRAPH_NODE",
                "evidence_refs": ["analysis:public-market-bundle"],
                "node_ids": [],
                "association_ids": [],
                "dependency_group_ids": [],
            }
            evidence_records.append(
                project_v32_agent_market_graph_closure_record_v1(expanded)
            )
            continue
        expanded = {
            "evidence_digest": evidence_digest,
            "available_at": availability[evidence_digest],
            "closure_status": "VERIFIED_COMPLETE_GRAPH_CLOSURE",
            "evidence_refs": list(closure["evidence_refs"]),
            "node_ids": list(closure["node_ids"]),
            "association_ids": list(closure["association_ids"]),
            "dependency_group_ids": list(closure["dependency_group_ids"]),
        }
        evidence_records.append(
            project_v32_agent_market_graph_closure_record_v1(
                expanded,
                exact_closure_digest=closure[
                    "evidence_dependency_closure_digest"
                ],
            )
        )

    events_by_component = {
        row["component_id"]: row
        for row in public_market_analysis_bundle["information_events"]
    }
    closed_bar_evidence = {
        timeframe: {
            "source_component_id": f"CLOSED_CANDLES_{timeframe}",
            "public_source_event_digest": events_by_component[
                f"CLOSED_CANDLES_{timeframe}"
            ]["public_source_event_digest"],
            "available_at": events_by_component[
                f"CLOSED_CANDLES_{timeframe}"
            ]["available_at"],
        }
        for timeframe in public_market_analysis_bundle["closed_bar_series"]
    }
    graph_delta = public_market_graph_projection["graph_delta"]
    graph_delta_summary = {
        "graph_delta_digest": graph_delta["graph_delta_digest"],
        "base_graph_revision": graph_delta["base_graph_revision"],
        "base_graph_digest": graph_delta["base_graph_digest"],
        "revision": graph_delta["revision"],
        "occurred_at": graph_delta["occurred_at"],
        "available_at": graph_delta["available_at"],
        "node_revision_count": len(graph_delta["node_revisions"]),
        "association_revision_count": len(graph_delta["association_revisions"]),
        "dependency_group_ids": list(graph_delta["dependency_group_ids"]),
    }
    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle_index,
        "as_of": graph_dependency_registry["as_of"],
        "available_at": public_market_graph_projection["available_at"],
        "instrument": dict(public_market_analysis_bundle["instrument"]),
        "upstream_digests": {
            "public_market_analysis_bundle_digest": bundle_digest,
            "public_market_graph_projection_digest": projection_digest,
            "graph_dependency_registry_digest": graph_digest,
            "pit_evidence_availability_registry_digest": availability_digest,
        },
        "closed_bar_series": {
            timeframe: [dict(row) for row in rows]
            for timeframe, rows in public_market_analysis_bundle[
                "closed_bar_series"
            ].items()
        },
        "closed_bar_evidence": closed_bar_evidence,
        "current_non_bar_datums": non_bar_datums,
        "source_event_claim_ceilings": source_claims,
        "axis_source_evidence": [
            dict(row)
            for row in public_market_analysis_bundle["axis_source_evidence"]
        ],
        "citable_evidence_records": evidence_records,
        "evidence_dependency_policy": dict(
            graph_dependency_registry["evidence_dependency_policy"]
        ),
        "graph_delta_summary": graph_delta_summary,
        "content_counts": {
            "closed_bar_count": sum(
                len(rows)
                for rows in public_market_analysis_bundle[
                    "closed_bar_series"
                ].values()
            ),
            "current_non_bar_datum_count": len(non_bar_datums),
            "source_event_count": len(source_claims),
            "axis_evidence_count": len(
                public_market_analysis_bundle["axis_source_evidence"]
            ),
            "citable_evidence_count": len(evidence_records),
            "durable_pit_member_count": len(pit_evidence_registry["members"]),
        },
        "unknown_retained": bool(
            public_market_graph_projection["unknown_retained"]
        ),
        "other_retained": bool(public_market_graph_projection["other_retained"]),
        "causal_claim": "NONE_PROVENANCE_ASSOCIATIONS_ONLY",
        "view_policy": dict(VIEW_POLICY),
        "canonical_payload_bytes": 0,
        "max_canonical_payload_bytes": MAX_CANONICAL_BYTES,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_data_accessed": False,
        "order_data_accessed": False,
    }
    return seal_v32_agent_market_graph_view_v1(document)


def verify_v32_agent_market_graph_view_v1(
    document: Mapping[str, Any],
    *,
    public_evidence_verifier: V32PublicEvidenceVerifierPort,
    public_market_analysis_bundle: Mapping[str, Any],
    public_market_graph_projection: Mapping[str, Any],
    pit_evidence_registry: Mapping[str, Any],
    graph_dependency_registry: Mapping[str, Any],
    pit_evidence_availability_registry: Mapping[str, Any],
    previous_public_market_graph_projection: Mapping[str, Any] | None,
) -> str:
    supplied = verify_v32_agent_market_graph_view_intrinsic_v1(document)
    try:
        rebuilt = build_v32_agent_market_graph_view_v1(
            public_evidence_verifier=public_evidence_verifier,
            public_market_analysis_bundle=public_market_analysis_bundle,
            public_market_graph_projection=public_market_graph_projection,
            pit_evidence_registry=pit_evidence_registry,
            graph_dependency_registry=graph_dependency_registry,
            pit_evidence_availability_registry=(
                pit_evidence_availability_registry
            ),
            previous_public_market_graph_projection=(
                previous_public_market_graph_projection
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AgentMarketGraphViewError):
            raise
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[DIGEST_FIELD]
    ):
        raise V32AgentMarketGraphViewError(
            "V32_AGENT_MARKET_GRAPH_VIEW_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "DIGEST_FIELD",
    "MAX_CANONICAL_BYTES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "VIEW_POLICY",
    "V32AgentMarketGraphViewError",
    "build_v32_agent_market_graph_view_v1",
    "verify_v32_agent_market_graph_view_intrinsic_v1",
    "verify_v32_agent_market_graph_view_v1",
]
