from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from tests.test_theory_paper_v2_v32_dynamic_research import (
    EXPIRES,
    _cluster,
    _cycle_two_kwargs,
    _hypothesis,
    _kwargs,
    _row,
    _set_regime_features,
)
from trade_system.theory_paper_v2.application.v32_dynamic_state_continuity import (
    GRAPH_REGISTRY_DIGEST_FIELD,
    GRAPH_REGISTRY_SCHEMA_ID,
    PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_DIGEST_FIELD,
    PIT_REGISTRY_SCHEMA_ID,
    RECEIPT_DIGEST_FIELD,
    V32DynamicStateContinuityError,
    build_v32_verified_pit_evidence_availability_registry_v1,
    compose_v32_dynamic_state_continuity_v1,
    verify_v32_verified_pit_evidence_availability_registry_v1,
    verify_v32_dynamic_state_continuity_v1,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.v32_dynamic_research import (
    DIGEST_FIELD,
    build_v32_dynamic_research_state_v1,
)


class _TestPublicEvidenceVerifier:
    def verify_public_market_analysis_bundle(self, document: dict[str, object]) -> str:
        return str(document["public_market_analysis_bundle_digest"])


PUBLIC_EVIDENCE_VERIFIER = _TestPublicEvidenceVerifier()


def _registry(
    state: dict[str, object],
    *,
    kind: str,
    members: list[str],
    dependency_closure: dict[str, set[str]] | None = None,
) -> dict[str, object]:
    if kind == "pit":
        schema_id = PIT_REGISTRY_SCHEMA_ID
        digest_field = PIT_REGISTRY_DIGEST_FIELD
        upstream_schema = "test_verified_pit_dataset"
        upstream_field = "dataset_digest"
    else:
        schema_id = GRAPH_REGISTRY_SCHEMA_ID
        digest_field = GRAPH_REGISTRY_DIGEST_FIELD
        upstream_schema = "test_verified_market_graph"
        upstream_field = "graph_digest"
    document = {
        "schema_id": schema_id,
        "schema_version": "1.0.0",
        "run_id": state["run_id"],
        "cycle_index": state["cycle_index"],
        "as_of": state["as_of"],
        "members": sorted(members),
        "upstream_schema_id": upstream_schema,
        "upstream_digest_field": upstream_field,
        "upstream_semantic_digest": "a" * 64,
        "full_verification_receipt_digest": "b" * 64,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    if kind == "graph":
        closure_rows = []
        for evidence_ref, dependencies in sorted((dependency_closure or {}).items()):
            closure_rows.append(
                self_digest(
                    {
                        "schema_id": "theory_paper_v32_evidence_dependency_closure_v1",
                        "schema_version": "1.0.0",
                        "evidence_digest": canonical_digest(
                            {"synthetic_evidence_ref": evidence_ref}
                        ),
                        "evidence_refs": [evidence_ref],
                        "node_ids": [f"synthetic-node:{len(closure_rows):04d}"],
                        "association_ids": [],
                        "dependency_group_ids": sorted(dependencies),
                    },
                    "evidence_dependency_closure_digest",
                )
            )
        document["evidence_dependency_policy"] = {
            "identity_key": "PAYLOAD_DIGEST",
            "node_scope": "LATEST_NODE_REVISIONS_ONLY",
            "association_scope": "ALL_LATEST_INCIDENT_ASSOCIATIONS",
            "dependency_operation": "UNION_NO_CALLER_SUBSETS",
            "same_digest_split_allowed": False,
        }
        document["evidence_dependency_closure"] = sorted(
            closure_rows, key=lambda row: row["evidence_digest"]
        )
    return self_digest(document, digest_field)


def _registries(
    state: dict[str, object],
    *,
    regime_feature_family_overrides: dict[str, str] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    sources: set[str] = set()
    groups: set[str] = set()
    dependencies_by_source: dict[str, set[str]] = {}
    regime_feature_family_overrides = regime_feature_family_overrides or {}

    def bind(source_refs: list[str], dependency_groups: list[str]) -> None:
        for source_ref in source_refs:
            dependencies_by_source.setdefault(source_ref, set()).update(
                dependency_groups
            )

    def bind_independently(
        source_refs: list[str], dependency_groups: list[str]
    ) -> None:
        distinct_refs = list(dict.fromkeys(source_refs))
        material_groups = [
            group for group in dependency_groups if group.startswith("dep:")
        ]
        family_groups = [
            group
            for group in dependency_groups
            if group
            in {
                "OBSERVABLE_FAMILY:PRICE_ACTION",
                "OBSERVABLE_FAMILY:POSITIONING",
                "OBSERVABLE_FAMILY:FUNDING_CROWDING",
                "OBSERVABLE_FAMILY:ORDERBOOK_LIQUIDITY",
                "OBSERVABLE_FAMILY:TRADE_FLOW",
            }
        ]
        for index, source_ref in enumerate(distinct_refs):
            dependency = material_groups[index % len(material_groups)]
            request = f"REQUEST:FIXTURE:{dependency}"
            family = family_groups[index % len(family_groups)]
            dependencies_by_source.setdefault(source_ref, set()).update(
                {dependency, request, family}
            )
            groups.update({request, family})
    for row in state["unknowns"]:
        groups.update(row["dependency_refs"])
    for row in state["zones"]:
        for field in (
            "evidence_refs",
            "touch_refs",
            "reaction_refs",
            "volume_at_price_refs",
            "dwell_time_refs",
            "round_number_refs",
            "orderbook_flow_refs",
            "leverage_refs",
            "options_refs",
        ):
            sources.update(row[field])
        groups.update(row["dependency_groups"])
        bind(
            [
                item
                for field in (
                    "evidence_refs",
                    "touch_refs",
                    "reaction_refs",
                    "volume_at_price_refs",
                    "dwell_time_refs",
                    "round_number_refs",
                    "orderbook_flow_refs",
                    "leverage_refs",
                    "options_refs",
                )
                for item in row[field]
            ],
            row["dependency_groups"],
        )
    for row in state["hypotheses"]:
        for field in (
            "source_refs",
            "supporting_refs",
            "opposing_refs",
            "tier_update_refs",
            "renewal_evidence_refs",
        ):
            sources.update(row[field])
        groups.update(row["dependency_groups"])
        hypothesis_refs = [
            item
            for field in (
                "source_refs",
                "supporting_refs",
                "opposing_refs",
                "tier_update_refs",
                "renewal_evidence_refs",
            )
            for item in row[field]
        ]
        if any(
            group.startswith("OBSERVABLE_FAMILY:")
            for group in row["dependency_groups"]
        ):
            bind_independently(hypothesis_refs, row["dependency_groups"])
        else:
            bind(hypothesis_refs, row["dependency_groups"])
    for row in state["path_modifiers"]:
        sources.update(row["source_refs"])
        groups.update(row["dependency_groups"])
        bind(row["source_refs"], row["dependency_groups"])
    for row in state["dependency_clusters"]:
        groups.update(row["shared_dependency_groups"])
    for field in (
        "evidence_refs",
        "counter_evidence_refs",
        "transition_evidence_refs",
    ):
        sources.update(state["market_regime_state"][field])
    default_regime_feature_families = {
        "DIRECTIONAL_PERSISTENCE": "PRICE_ACTION",
        "REVERSAL_FREQUENCY": "PRICE_ACTION",
        "EXECUTION_CHURN_PRESSURE": "TRADE_FLOW",
        "REALIZED_VOLATILITY": "PRICE_ACTION",
        "DIRECTIONAL_IMBALANCE": "TRADE_FLOW",
    }
    for index, assessment in enumerate(
        state["market_regime_state"]["regime_feature_assessments"]
    ):
        feature_type = assessment["feature_type"]
        family = regime_feature_family_overrides.get(
            feature_type, default_regime_feature_families[feature_type]
        )
        dependency = f"dep:regime-feature:{feature_type.lower()}"
        request = f"REQUEST:FIXTURE:REGIME_FEATURE:{index}"
        family_group = f"OBSERVABLE_FAMILY:{family}"
        groups.update({dependency, request, family_group})
        for evidence_ref in assessment["evidence_refs"]:
            sources.add(evidence_ref)
            dependencies_by_source.setdefault(evidence_ref, set()).update(
                {dependency, request, family_group}
            )
    for index, evidence_ref in enumerate(
        state["market_regime_state"]["transition_evidence_refs"]
    ):
        dependency = f"dep:regime-transition:{index}"
        request = f"REQUEST:FIXTURE:REGIME:{index}"
        family = (
            "OBSERVABLE_FAMILY:PRICE_ACTION"
            if index == 0
            else "OBSERVABLE_FAMILY:TRADE_FLOW"
        )
        groups.update({dependency, request, family})
        dependencies_by_source.setdefault(evidence_ref, set()).update(
            {dependency, request, family}
        )
    covered_groups = set().union(*dependencies_by_source.values())
    registry_only_groups = groups - covered_groups
    if registry_only_groups:
        dependencies_by_source["synthetic:registry-only"] = registry_only_groups
    sources.add(_analysis_digest(state))
    return (
        _registry(state, kind="pit", members=sorted(sources)),
        _registry(
            state,
            kind="graph",
            members=sorted(groups),
            dependency_closure=dependencies_by_source,
        ),
    )


def _analysis_digest(state: dict[str, object]) -> str:
    return canonical_digest(
        {
            "synthetic_analysis": True,
            "run_id": state["run_id"],
            "cycle_index": state["cycle_index"],
            "as_of": state["as_of"],
        }
    )


def _analysis_bundle(
    state: dict[str, object],
    pit: dict[str, object],
    *,
    previous_availability: dict[str, str] | None = None,
    datum_status_overrides: dict[str, str] | None = None,
    event_refs: set[str] | None = None,
) -> dict[str, object]:
    digest = _analysis_digest(state)
    previous_availability = previous_availability or {}
    datum_status_overrides = datum_status_overrides or {}
    event_refs = event_refs or set()
    return {
        "schema_id": "theory_paper_v32_public_market_analysis_bundle_v1",
        "schema_version": "1.0.0",
        "run_id": state["run_id"],
        "cycle_index": state["cycle_index"],
        "as_of": state["as_of"],
        "available_at": state["as_of"],
        "information_events": [
            {
                "public_source_event_digest": member,
                "available_at": previous_availability.get(member, state["as_of"]),
            }
            for member in pit["members"]
            if member != digest and member in event_refs
        ],
        "datums": [
            {
                "pit_datum_digest": member,
                "available_at": previous_availability.get(member, state["as_of"]),
                "status": datum_status_overrides.get(member, "OBSERVED"),
            }
            for member in pit["members"]
            if member != digest and member not in event_refs
        ],
        "axis_source_evidence": [],
        "public_market_analysis_bundle_digest": digest,
    }


def _availability(
    analysis: dict[str, object], pit: dict[str, object]
) -> dict[str, object]:
    return build_v32_verified_pit_evidence_availability_registry_v1(
        public_evidence_verifier=PUBLIC_EVIDENCE_VERIFIER,
        public_market_analysis_bundle=analysis,
        pit_evidence_registry=pit,
    )


def _compose(
    state: dict[str, object],
    *,
    previous: dict[str, object] | None = None,
    previous_digest: str | None = None,
    pit: dict[str, object] | None = None,
    graph: dict[str, object] | None = None,
    pit_digest: str | None = None,
    graph_digest: str | None = None,
    availability_overrides: dict[str, str] | None = None,
    closed_bar_series: dict[str, list[dict[str, object]]] | None = None,
    datum_status_overrides: dict[str, str] | None = None,
    event_refs: set[str] | None = None,
) -> dict[str, object]:
    default_pit, default_graph = _registries(state)
    selected_pit = pit or default_pit
    selected_graph = graph or default_graph
    previous_availability = None
    previous_availability_map: dict[str, str] = {}
    if previous is not None:
        previous_pit, _ = _registries(previous)
        previous_analysis = _analysis_bundle(previous, previous_pit)
        previous_availability = _availability(previous_analysis, previous_pit)
        previous_availability_map = {
            row["evidence_ref"]: row["available_at"]
            for row in previous_availability["entries"]
        }
    analysis = _analysis_bundle(
        state,
        selected_pit,
        previous_availability={
            **previous_availability_map,
            **(availability_overrides or {}),
        },
        datum_status_overrides=datum_status_overrides,
        event_refs=event_refs,
    )
    if closed_bar_series is not None:
        analysis["closed_bar_series"] = closed_bar_series
    availability = _availability(analysis, selected_pit)
    return compose_v32_dynamic_state_continuity_v1(
            public_evidence_verifier=PUBLIC_EVIDENCE_VERIFIER,
            current_state=state,
            durable_previous_state=previous,
            durable_previous_state_digest=previous_digest,
            verified_pit_evidence_registry=selected_pit,
            verified_pit_evidence_registry_digest=(
                pit_digest or selected_pit[PIT_REGISTRY_DIGEST_FIELD]
            ),
            verified_public_market_analysis_bundle=analysis,
            verified_pit_evidence_availability_registry=availability,
            verified_pit_evidence_availability_registry_digest=availability[
                PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
            ],
            durable_previous_pit_evidence_availability_registry=(
                previous_availability
            ),
            durable_previous_pit_evidence_availability_registry_digest=(
                None
                if previous_availability is None
                else previous_availability[PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD]
            ),
            verified_graph_dependency_registry=selected_graph,
            verified_graph_dependency_registry_digest=(
                graph_digest or selected_graph[GRAPH_REGISTRY_DIGEST_FIELD]
            ),
        )


def _next_kwargs(
    previous: dict[str, object], *, as_of: str = "2026-08-07T00:15:00Z"
) -> dict[str, object]:
    hypotheses = deepcopy(previous["hypotheses"])
    for hypothesis in hypotheses:
        hypothesis["parent_revision_digest"] = previous[DIGEST_FIELD]
        hypothesis["previous_subjective_plausibility_tier"] = hypothesis[
            "subjective_plausibility_tier"
        ]
        hypothesis["previous_expires_at"] = hypothesis["expires_at"]
        hypothesis["tier_update_refs"] = []
        hypothesis["renewal_evidence_refs"] = []
    return {
        "run_id": previous["run_id"],
        "cycle_index": previous["cycle_index"] + 1,
        "as_of": as_of,
        "frame_mode": "DELTA_UPDATE",
        "previous_state_digest": previous[DIGEST_FIELD],
        "market_regime_state": {
            **deepcopy(previous["market_regime_state"]),
            "previous_regime": previous["market_regime_state"]["regime"],
            "transition_evidence_refs": [],
        },
        "unknowns": deepcopy(previous["unknowns"]),
        "zones": deepcopy(previous["zones"]),
        "hypotheses": hypotheses,
        "path_modifiers": deepcopy(previous["path_modifiers"]),
        "dependency_clusters": deepcopy(previous["dependency_clusters"]),
    }


def _expired_object_renewal_transition(
    *, fresh_hypothesis_evidence: bool = True
) -> tuple[dict[str, object], dict[str, object]]:
    first_values = _kwargs()
    _row(first_values["hypotheses"], "hypothesis_id", "attribution-neutral")[
        "expires_at"
    ] = "2026-08-07T00:10:00Z"
    first_values["zones"][0]["expires_at"] = "2026-08-07T00:10:00Z"
    _row(first_values["path_modifiers"], "modifier_id", "modifier-venue")[
        "expires_at"
    ] = "2026-08-07T00:10:00Z"
    previous = build_v32_dynamic_research_state_v1(**first_values)
    values = _next_kwargs(previous)

    old_hypothesis = _row(
        values["hypotheses"], "hypothesis_id", "attribution-neutral"
    )
    old_hypothesis["status"] = "EXPIRED"
    successor = deepcopy(old_hypothesis)
    old_hypothesis["subjective_plausibility_tier"] = "EXTREME_UNCERTAINTY"
    old_hypothesis["tier_update_refs"] = ["fresh-pit:attribution-expired"]
    successor["hypothesis_id"] = "attribution-neutral-v2"
    successor["lineage_id"] = old_hypothesis["lineage_id"]
    successor["lineage_revision"] = old_hypothesis["lineage_revision"] + 1
    successor["predecessor_id"] = old_hypothesis["hypothesis_id"]
    successor["predecessor_fingerprint"] = old_hypothesis[
        "semantic_fingerprint"
    ]
    successor["semantic_fingerprint"] = None
    successor["status"] = "ACTIVE"
    successor["expires_at"] = "2026-08-07T01:00:00Z"
    renewal_ref = (
        "fresh-pit:attribution-renewal"
        if fresh_hypothesis_evidence
        else "support:attribution-neutral"
    )
    if renewal_ref not in successor["supporting_refs"]:
        successor["supporting_refs"].append(renewal_ref)
    successor["renewal_evidence_refs"] = [renewal_ref]
    values["hypotheses"].append(successor)
    attribution_cluster = _row(
        values["dependency_clusters"], "cluster_id", "cluster-attribution"
    )
    attribution_cluster["member_hypothesis_ids"].append(
        "attribution-neutral-v2"
    )
    attribution_cluster["aggregate_tier"] = "LOW"

    successor_zone = deepcopy(values["zones"][0])
    successor_zone.update(
        {
            "zone_id": "resistance-1300-v2",
            "created_at": "2026-08-07T00:13:00Z",
            "available_at": "2026-08-07T00:14:00Z",
            "expires_at": "2026-08-07T01:00:00Z",
            "lineage_id": values["zones"][0]["lineage_id"],
            "lineage_revision": values["zones"][0]["lineage_revision"] + 1,
            "predecessor_id": values["zones"][0]["zone_id"],
            "predecessor_fingerprint": values["zones"][0][
                "semantic_fingerprint"
            ],
            "semantic_fingerprint": None,
        }
    )
    successor_zone["evidence_refs"].append("fresh-pit:zone-renewal")
    successor_zone["path_modifier_ids"] = []
    values["zones"].append(successor_zone)

    old_modifier = _row(
        values["path_modifiers"], "modifier_id", "modifier-venue"
    )
    old_modifier["status"] = "EXPIRED"
    successor_modifier = deepcopy(old_modifier)
    successor_modifier.update(
        {
            "modifier_id": "modifier-venue-v2",
            "created_at": "2026-08-07T00:13:00Z",
            "available_at": "2026-08-07T00:14:00Z",
            "expires_at": "2026-08-07T00:45:00Z",
            "status": "ACTIVE",
            "source_refs": ["fresh-pit:modifier-renewal"],
            "lineage_id": old_modifier["lineage_id"],
            "lineage_revision": old_modifier["lineage_revision"] + 1,
            "predecessor_id": old_modifier["modifier_id"],
            "predecessor_fingerprint": old_modifier[
                "semantic_fingerprint"
            ],
            "semantic_fingerprint": None,
        }
    )
    values["path_modifiers"].append(successor_modifier)
    _row(values["hypotheses"], "hypothesis_id", "state-long")[
        "path_modifier_ids"
    ].append("modifier-venue-v2")

    return previous, build_v32_dynamic_research_state_v1(**values)


class V32DynamicStateContinuityTests(unittest.TestCase):
    def test_receipt_requires_exact_reconstruction(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        analysis = _analysis_bundle(state, pit)
        availability = _availability(analysis, pit)
        receipt = _compose(state, pit=pit, graph=graph)
        verified = verify_v32_dynamic_state_continuity_v1(
            receipt,
            public_evidence_verifier=PUBLIC_EVIDENCE_VERIFIER,
            current_state=state,
            durable_previous_state=None,
            durable_previous_state_digest=None,
            verified_pit_evidence_registry=pit,
            verified_pit_evidence_registry_digest=pit[PIT_REGISTRY_DIGEST_FIELD],
            verified_public_market_analysis_bundle=analysis,
            verified_pit_evidence_availability_registry=availability,
            verified_pit_evidence_availability_registry_digest=availability[
                PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
            ],
            durable_previous_pit_evidence_availability_registry=None,
            durable_previous_pit_evidence_availability_registry_digest=None,
            verified_graph_dependency_registry=graph,
            verified_graph_dependency_registry_digest=graph[
                GRAPH_REGISTRY_DIGEST_FIELD
            ],
        )
        self.assertEqual(verified, receipt[RECEIPT_DIGEST_FIELD])

        forged = deepcopy(receipt)
        forged["new_hypothesis_ids"] = []
        forged = self_digest(forged, RECEIPT_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_RECEIPT_RECONSTRUCTION_MISMATCH",
        ):
            verify_v32_dynamic_state_continuity_v1(
                forged,
                public_evidence_verifier=PUBLIC_EVIDENCE_VERIFIER,
                current_state=state,
                durable_previous_state=None,
                durable_previous_state_digest=None,
                verified_pit_evidence_registry=pit,
                verified_pit_evidence_registry_digest=pit[
                    PIT_REGISTRY_DIGEST_FIELD
                ],
                verified_public_market_analysis_bundle=analysis,
                verified_pit_evidence_availability_registry=availability,
                verified_pit_evidence_availability_registry_digest=availability[
                    PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD
                ],
                durable_previous_pit_evidence_availability_registry=None,
                durable_previous_pit_evidence_availability_registry_digest=None,
                verified_graph_dependency_registry=graph,
                verified_graph_dependency_registry_digest=graph[
                    GRAPH_REGISTRY_DIGEST_FIELD
                ],
            )

    def test_genesis_and_cycle_two_bind_to_verified_durable_state(self) -> None:
        first = build_v32_dynamic_research_state_v1(**_kwargs())
        first_receipt = _compose(first)
        self.assertEqual(
            verify_self_digest(first_receipt, RECEIPT_DIGEST_FIELD),
            first_receipt[RECEIPT_DIGEST_FIELD],
        )
        self.assertIsNone(first_receipt["durable_previous_state_digest"])
        self.assertEqual(first_receipt["continued_hypothesis_ids"], [])
        self.assertEqual(
            first_receipt["new_hypothesis_ids"],
            sorted(row["hypothesis_id"] for row in first["hypotheses"]),
        )

        previous, values = _cycle_two_kwargs()
        second = build_v32_dynamic_research_state_v1(**values)
        second_receipt = _compose(
            second,
            previous=previous,
            previous_digest=previous[DIGEST_FIELD],
        )
        self.assertEqual(
            second_receipt["durable_previous_state_digest"],
            previous[DIGEST_FIELD],
        )
        self.assertEqual(second_receipt["new_hypothesis_ids"], [])
        self.assertEqual(
            second_receipt["continued_hypothesis_ids"],
            sorted(row["hypothesis_id"] for row in previous["hypotheses"]),
        )

    def test_high_tier_requires_fresh_nonoverlapping_graph_dependencies(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        collapsed_refs = {
            *next(
                row
                for row in state["hypotheses"]
                if row["hypothesis_id"] == "state-long"
            )["source_refs"],
            *next(
                row
                for row in state["hypotheses"]
                if row["hypothesis_id"] == "state-long"
            )["supporting_refs"],
        }
        closure = {
            evidence_ref: set(row["dependency_group_ids"])
            for row in graph["evidence_dependency_closure"]
            for evidence_ref in row["evidence_refs"]
        }
        for evidence_ref in collapsed_refs:
            closure[evidence_ref] = {"dep:state"}
        forged_graph = _registry(
            state,
            kind="graph",
            members=graph["members"],
            dependency_closure=closure,
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DUAL_FRESH_INDEPENDENT_EVIDENCE_REQUIRED",
        ):
            _compose(state, pit=pit, graph=forged_graph)

        previous, values = _cycle_two_kwargs()
        current = build_v32_dynamic_research_state_v1(**values)
        pit, graph = _registries(current)
        rejection = next(
            row
            for row in current["hypotheses"]
            if row["hypothesis_id"] == "forecast-rejection"
        )
        closure = {
            evidence_ref: set(row["dependency_group_ids"])
            for row in graph["evidence_dependency_closure"]
            for evidence_ref in row["evidence_refs"]
        }
        for evidence_ref in rejection["tier_update_refs"]:
            closure[evidence_ref] = {"dep:zone"}
        forged_graph = _registry(
            current,
            kind="graph",
            members=graph["members"],
            dependency_closure=closure,
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DUAL_FRESH_INDEPENDENT_EVIDENCE_REQUIRED",
        ):
            _compose(
                current,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
                pit=pit,
                graph=forged_graph,
            )

    def test_high_tier_ignores_only_shared_provenance_and_rejects_same_family(self) -> None:
        values = _kwargs()
        high_input = next(
            row
            for row in values["hypotheses"]
            if row["hypothesis_id"] == "state-long"
        )
        high_input["dependency_groups"] = sorted(
            {
                *high_input["dependency_groups"],
                "VENUE:OKX",
                "PROJECTION:EVENT_DATUM",
                "OBSERVABLE_FAMILY:PROVIDER_METADATA",
                "OBSERVABLE_FAMILY:CONTRACT_SPEC",
            }
        )
        state = build_v32_dynamic_research_state_v1(**values)
        pit, graph = _registries(state)
        high = next(
            row
            for row in state["hypotheses"]
            if row["hypothesis_id"] == "state-long"
        )
        high_refs = {
            *high["source_refs"],
            *high["supporting_refs"],
        }
        closure = {
            evidence_ref: set(row["dependency_group_ids"])
            for row in graph["evidence_dependency_closure"]
            for evidence_ref in row["evidence_refs"]
        }
        for evidence_ref in high_refs:
            closure[evidence_ref].update(
                {"VENUE:OKX", "PROJECTION:EVENT_DATUM"}
            )
        provenance_shared = _registry(
            state,
            kind="graph",
            members=sorted(set().union(*closure.values())),
            dependency_closure=closure,
        )
        _compose(state, pit=pit, graph=provenance_shared)

        for evidence_ref in high_refs:
            closure[evidence_ref] = {
                group
                for group in closure[evidence_ref]
                if not group.startswith("OBSERVABLE_FAMILY:")
            }
            closure[evidence_ref].add(
                "OBSERVABLE_FAMILY:POSITIONING"
            )
        same_family = _registry(
            state,
            kind="graph",
            members=sorted(set().union(*closure.values())),
            dependency_closure=closure,
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DUAL_FRESH_INDEPENDENT_EVIDENCE_REQUIRED",
        ):
            _compose(state, pit=pit, graph=same_family)

        for index, evidence_ref in enumerate(sorted(high_refs)):
            closure[evidence_ref] = {
                group
                for group in closure[evidence_ref]
                if not group.startswith("OBSERVABLE_FAMILY:")
            }
            closure[evidence_ref].add(
                "OBSERVABLE_FAMILY:PROVIDER_METADATA"
                if index % 2 == 0
                else "OBSERVABLE_FAMILY:CONTRACT_SPEC"
            )
        nondirectional_families = _registry(
            state,
            kind="graph",
            members=sorted(set().union(*closure.values())),
            dependency_closure=closure,
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DUAL_FRESH_INDEPENDENT_EVIDENCE_REQUIRED",
        ):
            _compose(state, pit=pit, graph=nondirectional_families)

    def test_high_tier_rejects_unknown_event_and_invalid_counter_evidence(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        high = next(
            row
            for row in state["hypotheses"]
            if row["hypothesis_id"] == "state-long"
        )
        support_refs = {
            *high["source_refs"],
            *high["supporting_refs"],
        }
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DUAL_FRESH_INDEPENDENT_EVIDENCE_REQUIRED",
        ):
            _compose(
                state,
                pit=pit,
                graph=graph,
                datum_status_overrides={ref: "UNKNOWN" for ref in support_refs},
            )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DUAL_FRESH_INDEPENDENT_EVIDENCE_REQUIRED",
        ):
            _compose(
                state,
                pit=pit,
                graph=graph,
                event_refs=support_refs,
            )

        values = _kwargs()
        high_input = next(
            row
            for row in values["hypotheses"]
            if row["hypothesis_id"] == "state-long"
        )
        high_input["dependency_groups"] = sorted(
            {
                *high_input["dependency_groups"],
                "OBSERVABLE_FAMILY:PROVIDER_METADATA",
            }
        )
        invalid_counter_state = build_v32_dynamic_research_state_v1(**values)
        pit, graph = _registries(invalid_counter_state)
        high = next(
            row
            for row in invalid_counter_state["hypotheses"]
            if row["hypothesis_id"] == "state-long"
        )
        opposing_ref = high["opposing_refs"][0]
        closure = {
            evidence_ref: set(row["dependency_group_ids"])
            for row in graph["evidence_dependency_closure"]
            for evidence_ref in row["evidence_refs"]
        }
        closure[opposing_ref] = {
            group
            for group in closure[opposing_ref]
            if not group.startswith("OBSERVABLE_FAMILY:")
        }
        closure[opposing_ref].add("OBSERVABLE_FAMILY:PROVIDER_METADATA")
        invalid_counter_graph = _registry(
            invalid_counter_state,
            kind="graph",
            members=sorted(set().union(*closure.values())),
            dependency_closure=closure,
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DIRECTIONAL_COUNTER_EVIDENCE_REQUIRED",
        ):
            _compose(
                invalid_counter_state,
                pit=pit,
                graph=invalid_counter_graph,
            )

    def test_high_tier_counter_identity_is_distinct_and_residual_high_is_not_directional(self) -> None:
        values = _kwargs()
        high = next(
            row
            for row in values["hypotheses"]
            if row["hypothesis_id"] == "state-long"
        )
        high["opposing_refs"] = [high["source_refs"][0]]
        duplicated_counter = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_HIGH_TIER_DIRECTIONAL_COUNTER_EVIDENCE_REQUIRED",
        ):
            _compose(duplicated_counter)

        residual_values = _kwargs()
        residual = next(
            row
            for row in residual_values["hypotheses"]
            if row["direction"] == "OTHER"
        )
        residual["subjective_plausibility_tier"] = "HIGH"
        residual_high = build_v32_dynamic_research_state_v1(**residual_values)
        _compose(residual_high)

    def test_nondirectional_regime_features_require_current_typed_pit_evidence(
        self,
    ) -> None:
        for regime in ("CHOPPY", "VOLATILITY_WITHOUT_DIRECTION"):
            with self.subTest(regime=regime):
                values = _kwargs()
                _set_regime_features(values, regime)
                state = build_v32_dynamic_research_state_v1(**values)
                _compose(state)

        values = _kwargs()
        _set_regime_features(values, "CHOPPY")
        state = build_v32_dynamic_research_state_v1(**values)
        pit, graph = _registries(
            state,
            regime_feature_family_overrides={
                "EXECUTION_CHURN_PRESSURE": "PRICE_ACTION"
            },
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_REGIME_FEATURE_OBSERVABLE_FAMILY_INVALID",
        ):
            _compose(state, pit=pit, graph=graph)

        pit, graph = _registries(state)
        missing_ref = "regime:trade-churn"
        pit_without_feature_ref = _registry(
            state,
            kind="pit",
            members=[item for item in pit["members"] if item != missing_ref],
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_STATE_EVIDENCE_NOT_CURRENT_PIT",
        ):
            _compose(state, pit=pit_without_feature_ref, graph=graph)

    def test_regime_transition_uses_asymmetric_evidence_gate(self) -> None:
        for initial_regime in (
            "NEUTRAL",
            "TRANSITION",
            "CHOPPY",
            "VOLATILITY_WITHOUT_DIRECTION",
        ):
            with self.subTest(initial_regime=initial_regime):
                initial = _kwargs()
                if initial_regime in {
                    "CHOPPY",
                    "VOLATILITY_WITHOUT_DIRECTION",
                }:
                    _set_regime_features(initial, initial_regime)
                else:
                    initial["market_regime_state"]["regime"] = initial_regime
                previous = build_v32_dynamic_research_state_v1(**initial)

                values = _next_kwargs(previous)
                values["market_regime_state"]["regime"] = "TREND_UP"
                values["market_regime_state"]["regime_feature_assessments"] = []
                values["market_regime_state"]["transition_evidence_refs"] = [
                    "fresh:regime-price"
                ]
                current = build_v32_dynamic_research_state_v1(**values)
                with self.assertRaisesRegex(
                    V32DynamicStateContinuityError,
                    "V32_CONTINUITY_NONDIRECTIONAL_TO_DIRECTIONAL_EVIDENCE_GATE_INVALID",
                ):
                    _compose(
                        current,
                        previous=previous,
                        previous_digest=previous[DIGEST_FIELD],
                    )

        initial = _kwargs()
        initial["market_regime_state"]["regime"] = "NEUTRAL"
        previous = build_v32_dynamic_research_state_v1(**initial)
        values = _next_kwargs(previous)
        values["market_regime_state"]["regime"] = "TREND_UP"

        values["market_regime_state"]["transition_evidence_refs"] = [
            "fresh:regime-price",
            "fresh:regime-flow",
        ]
        current = build_v32_dynamic_research_state_v1(**values)
        receipt = _compose(
            current,
            previous=previous,
            previous_digest=previous[DIGEST_FIELD],
        )
        self.assertIn("fresh:regime-price", receipt["fresh_lifecycle_evidence_refs"])

        directional = build_v32_dynamic_research_state_v1(**_kwargs())
        to_nondirectional = _next_kwargs(directional)
        to_nondirectional["market_regime_state"]["regime"] = "NEUTRAL"
        to_nondirectional["market_regime_state"]["transition_evidence_refs"] = [
            "fresh:hard-nondirectional"
        ]
        nondirectional = build_v32_dynamic_research_state_v1(**to_nondirectional)
        _compose(
            nondirectional,
            previous=directional,
            previous_digest=directional[DIGEST_FIELD],
        )

    def test_two_closed_15m_bars_are_machine_direction_alternative(self) -> None:
        initial = _kwargs()
        initial["market_regime_state"]["regime"] = "NEUTRAL"
        previous = build_v32_dynamic_research_state_v1(**initial)
        values = _next_kwargs(previous)
        values["market_regime_state"]["regime"] = "TREND_UP"
        values["market_regime_state"]["transition_evidence_refs"] = [
            "fresh:regime-price"
        ]
        current = build_v32_dynamic_research_state_v1(**values)
        bars = {
            "15M": [
                {
                    "open_time_ms": 0,
                    "close_time_ms": 900_000,
                    "open": "100",
                    "close": "101",
                    "confirmed_closed": True,
                },
                {
                    "open_time_ms": 900_000,
                    "close_time_ms": 1_800_000,
                    "open": "101",
                    "close": "102",
                    "confirmed_closed": True,
                },
            ]
        }
        _compose(
            current,
            previous=previous,
            previous_digest=previous[DIGEST_FIELD],
            closed_bar_series=bars,
        )

    def test_genesis_forbids_fabricated_previous_state(self) -> None:
        first = build_v32_dynamic_research_state_v1(**_kwargs())
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_GENESIS_PREVIOUS_STATE_FORBIDDEN",
        ):
            _compose(
                first,
                previous=first,
                previous_digest=first[DIGEST_FIELD],
            )

    def test_cycle_two_requires_external_durable_digest_and_full_prior_validation(
        self,
    ) -> None:
        previous, values = _cycle_two_kwargs()
        second = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_DURABLE_PREVIOUS_STATE_REQUIRED",
        ):
            _compose(second)

        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_PREVIOUS_DIGEST_BINDING_MISMATCH",
        ):
            _compose(second, previous=previous, previous_digest="c" * 64)

        tampered = deepcopy(previous)
        tampered["hypotheses"][0]["mechanism"] = "unsealed prior mutation"
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_DURABLE_PREVIOUS_STATE_INVALID",
        ):
            _compose(
                second,
                previous=tampered,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_current_cycle_cannot_self_report_a_different_previous_tier(self) -> None:
        previous, values = _cycle_two_kwargs()
        rejection = _row(
            values["hypotheses"], "hypothesis_id", "forecast-rejection"
        )
        # Internally consistent and accepted by the pure domain builder, but
        # false relative to the durable previous LOW tier.
        rejection["previous_subjective_plausibility_tier"] = "HIGH"
        rejection["subjective_plausibility_tier"] = "LOW"
        rejection["tier_update_refs"] = ["closed-15m-rejection-delta"]
        _row(
            values["dependency_clusters"],
            "cluster_id",
            "cluster-zone-short",
        )["aggregate_tier"] = "LOW"
        second = build_v32_dynamic_research_state_v1(**values)

        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_DURABLE_PRIOR_CLAIM_MISMATCH",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_current_cycle_cannot_self_report_a_different_previous_expiry(self) -> None:
        previous, values = _cycle_two_kwargs()
        _row(values["hypotheses"], "hypothesis_id", "state-long")[
            "previous_expires_at"
        ] = "2026-08-07T05:00:00Z"
        second = build_v32_dynamic_research_state_v1(**values)

        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_DURABLE_PRIOR_CLAIM_MISMATCH",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_in_place_expiry_extension_is_forbidden_for_all_object_types(self) -> None:
        previous, values = _cycle_two_kwargs()
        hypothesis = _row(values["hypotheses"], "hypothesis_id", "state-long")
        hypothesis["expires_at"] = "2026-08-07T05:00:00Z"
        hypothesis["supporting_refs"].append("fresh-pit:hypothesis-renewal")
        hypothesis["renewal_evidence_refs"] = ["fresh-pit:hypothesis-renewal"]
        second = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "HYPOTHESIS_IN_PLACE_RENEWAL_FORBIDDEN",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

        previous, values = _cycle_two_kwargs()
        values["zones"][0]["expires_at"] = "2026-08-07T05:00:00Z"
        second = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError, "ZONE_IN_PLACE_RENEWAL_FORBIDDEN"
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

        previous, values = _cycle_two_kwargs()
        _row(
            values["path_modifiers"], "modifier_id", "modifier-venue"
        )["expires_at"] = "2026-08-07T00:45:00Z"
        second = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "PATH_MODIFIER_IN_PLACE_RENEWAL_FORBIDDEN",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_due_objects_retire_and_new_versions_require_fresh_pit(self) -> None:
        previous, current = _expired_object_renewal_transition()
        receipt = _compose(
            current,
            previous=previous,
            previous_digest=previous[DIGEST_FIELD],
        )

        self.assertEqual(
            ["attribution-neutral-v2"], receipt["renewed_hypothesis_ids"]
        )
        self.assertEqual(
            ["attribution-neutral"], receipt["retired_hypothesis_ids"]
        )
        self.assertEqual(["resistance-1300"], receipt["retired_zone_ids"])
        self.assertEqual(["resistance-1300-v2"], receipt["renewed_zone_ids"])
        self.assertEqual(
            ["modifier-venue"], receipt["retired_path_modifier_ids"]
        )
        self.assertEqual(
            ["modifier-venue-v2"], receipt["renewed_path_modifier_ids"]
        )
        self.assertTrue(receipt["lifecycle_reanalysis_required"])
        self.assertEqual(
            {
                "HYPOTHESIS_EXPIRY_RETIREMENT",
                "PATH_MODIFIER_EXPIRY_RETIREMENT",
                "ZONE_EXPIRY_RETIREMENT",
            },
            set(receipt["lifecycle_reanalysis_reasons"]),
        )
        self.assertTrue(
            {
                "fresh-pit:attribution-renewal",
                "fresh-pit:modifier-renewal",
                "fresh-pit:zone-renewal",
            }.issubset(receipt["fresh_lifecycle_evidence_refs"])
        )

        previous, no_fresh = _expired_object_renewal_transition(
            fresh_hypothesis_evidence=False
        )
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "HYPOTHESIS_RENEWAL_FRESH_PIT_REQUIRED",
        ):
            _compose(
                no_fresh,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_zone_and_modifier_tombstones_cannot_silently_disappear(self) -> None:
        previous, values = _cycle_two_kwargs()
        values["zones"] = []
        values["path_modifiers"] = [
            row
            for row in values["path_modifiers"]
            if row["modifier_id"] != "modifier-stop-hunt"
        ]
        for hypothesis in values["hypotheses"]:
            hypothesis["path_modifier_ids"] = [
                item
                for item in hypothesis["path_modifier_ids"]
                if item != "modifier-stop-hunt"
            ]
        second = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError, "PREVIOUS_ZONE_DISAPPEARED"
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

        previous, values = _cycle_two_kwargs()
        values["path_modifiers"] = [
            row
            for row in values["path_modifiers"]
            if row["modifier_id"] != "modifier-venue"
        ]
        _row(values["hypotheses"], "hypothesis_id", "state-long")[
            "path_modifier_ids"
        ] = []
        second = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "PREVIOUS_PATH_MODIFIER_DISAPPEARED",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_old_hypothesis_must_not_silently_disappear(self) -> None:
        previous, values = _cycle_two_kwargs()
        values["hypotheses"] = [
            row
            for row in values["hypotheses"]
            if row["hypothesis_id"] != "attribution-neutral"
        ]
        _row(values["hypotheses"], "hypothesis_id", "hypothesis-unknown")[
            "alternative_ids"
        ] = []
        values["dependency_clusters"] = [
            row
            for row in values["dependency_clusters"]
            if row["cluster_id"] != "cluster-attribution"
        ]
        second = build_v32_dynamic_research_state_v1(**values)

        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_PREVIOUS_HYPOTHESIS_DISAPPEARED",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_falsified_hypothesis_id_cannot_be_revived(self) -> None:
        first_values = _kwargs()
        _row(first_values["hypotheses"], "hypothesis_id", "action-long")[
            "status"
        ] = "FALSIFIED"
        _row(first_values["hypotheses"], "hypothesis_id", "action-long")[
            "subjective_plausibility_tier"
        ] = "EXTREME_UNCERTAINTY"
        _row(
            first_values["dependency_clusters"],
            "cluster_id",
            "cluster-action-long",
        )["aggregate_tier"] = "EXTREME_UNCERTAINTY"
        previous = build_v32_dynamic_research_state_v1(**first_values)

        values = _kwargs()
        values.update(
            {
                "cycle_index": 2,
                "as_of": "2026-08-07T00:15:00Z",
                "frame_mode": "DELTA_UPDATE",
                "previous_state_digest": previous[DIGEST_FIELD],
            }
        )
        values["market_regime_state"]["previous_regime"] = "TREND_UP"
        for hypothesis in values["hypotheses"]:
            old = _row(
                previous["hypotheses"],
                "hypothesis_id",
                hypothesis["hypothesis_id"],
            )
            hypothesis["parent_revision_digest"] = previous[DIGEST_FIELD]
            hypothesis["previous_subjective_plausibility_tier"] = old[
                "subjective_plausibility_tier"
            ]
            hypothesis["previous_expires_at"] = old["expires_at"]
        revived = _row(values["hypotheses"], "hypothesis_id", "action-long")
        revived["subjective_plausibility_tier"] = "LOW"
        revived["tier_update_refs"] = ["fresh-pit:revival-attempt"]
        _row(
            values["dependency_clusters"],
            "cluster_id",
            "cluster-action-long",
        )["aggregate_tier"] = "LOW"
        second = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_FALSIFIED_HYPOTHESIS_REVIVAL_FORBIDDEN",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_new_hypothesis_cannot_claim_a_parent_it_never_had(self) -> None:
        previous, values = _cycle_two_kwargs()
        invented = _hypothesis(
            "invented-state",
            "STATE",
            "NEUTRAL",
            "LOW",
            "dep:invented",
        )
        invented["parent_revision_digest"] = previous[DIGEST_FIELD]
        invented["previous_subjective_plausibility_tier"] = "LOW"
        invented["previous_expires_at"] = EXPIRES
        values["hypotheses"].append(invented)
        values["dependency_clusters"].append(
            _cluster(
                "cluster-invented",
                ["invented-state"],
                "NEUTRAL",
                "dep:invented",
                "LOW",
            )
        )
        second = build_v32_dynamic_research_state_v1(**values)

        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_NEW_HYPOTHESIS_FALSE_PARENT",
        ):
            _compose(
                second,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_modifier_sources_and_dependencies_must_be_current_registry_members(
        self,
    ) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        pit["members"].remove("touch-2")
        pit = self_digest(pit, PIT_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_MODIFIER_SOURCE_NOT_CURRENT_PIT",
        ):
            _compose(state, pit=pit, graph=graph)

    def test_all_state_evidence_and_dependencies_require_current_registries(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        hypothesis_source = state["hypotheses"][0]["source_refs"][0]
        pit["members"].remove(hypothesis_source)
        pit = self_digest(pit, PIT_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_STATE_EVIDENCE_NOT_CURRENT_PIT",
        ):
            _compose(state, pit=pit, graph=graph)

        pit, graph = _registries(state)
        hypothesis_dependency = state["hypotheses"][0]["dependency_groups"][0]
        graph["members"].remove(hypothesis_dependency)
        graph = self_digest(graph, GRAPH_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_GRAPH_REGISTRY_EVIDENCE_CLOSURE_INVALID",
        ):
            _compose(state, pit=pit, graph=graph)

        pit, graph = _registries(state)
        graph["members"].remove("dep:zone")
        graph = self_digest(graph, GRAPH_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_GRAPH_REGISTRY_EVIDENCE_CLOSURE_INVALID",
        ):
            _compose(state, pit=pit, graph=graph)

    def test_registry_must_be_digest_valid_and_bound_to_current_cycle(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        tampered = deepcopy(pit)
        tampered["members"].append("unsealed-evidence")
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_AVAILABILITY_PIT_REGISTRY_DIGEST_INVALID",
        ):
            _compose(state, pit=tampered, graph=graph)

        wrong_cycle = deepcopy(graph)
        wrong_cycle["cycle_index"] = 2
        wrong_cycle = self_digest(wrong_cycle, GRAPH_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_GRAPH_REGISTRY_CURRENT_CYCLE_BINDING_INVALID",
        ):
            _compose(state, pit=pit, graph=wrong_cycle)

        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "V32_CONTINUITY_PIT_REGISTRY_DURABLE_BINDING_MISMATCH",
        ):
            _compose(state, pit=pit, graph=graph, pit_digest="c" * 64)

    def test_application_rechecks_bidirectional_modifier_edges(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        _row(state["hypotheses"], "hypothesis_id", "forecast-rejection")[
            "path_modifier_ids"
        ] = []
        pit, graph = _registries(state)
        module = (
            "trade_system.theory_paper_v2.application."
            "v32_dynamic_state_continuity.verify_v32_dynamic_research_state_v1"
        )
        # Isolate the application-level reverse-edge check from the domain's
        # identical defense so a future domain refactor cannot remove it.
        with patch(module, return_value="d" * 64):
            with self.assertRaisesRegex(
                V32DynamicStateContinuityError,
                "V32_CONTINUITY_MODIFIER_AFFECTED_IDS_NOT_BIDIRECTIONAL",
            ):
                _compose(state, pit=pit, graph=graph)

    def test_same_evidence_digest_cannot_be_split_across_dependency_subsets(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        forged = deepcopy(graph)
        index = next(
            index
            for index, row in enumerate(forged["evidence_dependency_closure"])
            if len(row["dependency_group_ids"]) >= 2
        )
        original = forged["evidence_dependency_closure"][index]
        midpoint = len(original["dependency_group_ids"]) // 2
        rows = []
        for dependencies in (
            original["dependency_group_ids"][:midpoint],
            original["dependency_group_ids"][midpoint:],
        ):
            split = deepcopy(original)
            split["dependency_group_ids"] = dependencies
            rows.append(self_digest(split, "evidence_dependency_closure_digest"))
        forged["evidence_dependency_closure"][index : index + 1] = rows
        forged = self_digest(forged, GRAPH_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "EVIDENCE_CLOSURE_SPLIT_FORBIDDEN",
        ):
            _compose(state, pit=pit, graph=forged)

    def test_object_must_declare_full_dependency_union_for_each_evidence(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, graph = _registries(state)
        forged = deepcopy(graph)
        row = next(
            item
            for item in forged["evidence_dependency_closure"]
            if item["evidence_refs"] != ["synthetic:registry-only"]
            and len(item["dependency_group_ids"]) == 1
        )
        extra = next(
            member
            for member in forged["members"]
            if member not in row["dependency_group_ids"]
        )
        row["dependency_group_ids"] = sorted([*row["dependency_group_ids"], extra])
        sealed = self_digest(row, "evidence_dependency_closure_digest")
        forged["evidence_dependency_closure"] = [
            sealed if item["evidence_digest"] == sealed["evidence_digest"] else item
            for item in forged["evidence_dependency_closure"]
        ]
        forged = self_digest(forged, GRAPH_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "EVIDENCE_DEPENDENCY_CLOSURE_INCOMPLETE",
        ):
            _compose(state, pit=pit, graph=forged)

    def test_new_id_cannot_identity_wash_an_expired_lineage(self) -> None:
        previous, values = _cycle_two_kwargs()
        source = _row(values["hypotheses"], "hypothesis_id", "attribution-neutral")
        washed = deepcopy(source)
        washed.update(
            {
                "hypothesis_id": "attribution-neutral-renamed",
                "mechanism": source["mechanism"] + " with renamed prose",
                "source_refs": ["fresh:identity-wash"],
                "supporting_refs": ["fresh:identity-wash"],
                "parent_revision_digest": None,
                "previous_subjective_plausibility_tier": None,
                "previous_expires_at": None,
                "tier_update_refs": [],
                "renewal_evidence_refs": [],
                "lineage_id": "attribution-neutral-renamed",
                "lineage_revision": 1,
                "predecessor_id": None,
                "predecessor_fingerprint": None,
                "semantic_fingerprint": None,
            }
        )
        values["hypotheses"].append(washed)
        cluster = _row(
            values["dependency_clusters"], "cluster_id", "cluster-attribution"
        )
        cluster["member_hypothesis_ids"].append("attribution-neutral-renamed")
        current = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "HYPOTHESIS_RENEWAL_IDENTITY_REQUIRED",
        ):
            _compose(
                current,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
            )

    def test_unseen_ref_is_not_fresh_when_availability_does_not_postdate_cutoff(self) -> None:
        previous, values = _cycle_two_kwargs()
        source = _row(values["hypotheses"], "hypothesis_id", "attribution-neutral")
        stale = deepcopy(source)
        stale.update(
            {
                "hypothesis_id": "attribution-new-but-stale",
                "next_observation": "a genuinely distinct next observation",
                "source_refs": ["stale:new-source"],
                "supporting_refs": ["stale:new-source"],
                "parent_revision_digest": None,
                "previous_subjective_plausibility_tier": None,
                "previous_expires_at": None,
                "tier_update_refs": [],
                "renewal_evidence_refs": [],
                "lineage_id": "attribution-new-but-stale",
                "lineage_revision": 1,
                "predecessor_id": None,
                "predecessor_fingerprint": None,
                "semantic_fingerprint": None,
            }
        )
        values["hypotheses"].append(stale)
        _row(values["dependency_clusters"], "cluster_id", "cluster-attribution")[
            "member_hypothesis_ids"
        ].append("attribution-new-but-stale")
        current = build_v32_dynamic_research_state_v1(**values)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "NEW_HYPOTHESIS_FRESH_PIT_REQUIRED",
        ):
            _compose(
                current,
                previous=previous,
                previous_digest=previous[DIGEST_FIELD],
                availability_overrides={
                    "stale:new-source": previous["as_of"]
                },
            )

    def test_availability_sidecar_rejects_self_reported_time_rewrite(self) -> None:
        state = build_v32_dynamic_research_state_v1(**_kwargs())
        pit, _ = _registries(state)
        analysis = _analysis_bundle(state, pit)
        availability = _availability(analysis, pit)
        forged = deepcopy(availability)
        forged["entries"][0]["available_at"] = "2026-08-06T23:59:59Z"
        forged = self_digest(forged, PIT_AVAILABILITY_REGISTRY_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32DynamicStateContinuityError,
            "AVAILABILITY_REGISTRY_RECONSTRUCTION_MISMATCH",
        ):
            verify_v32_verified_pit_evidence_availability_registry_v1(
                forged,
                public_evidence_verifier=PUBLIC_EVIDENCE_VERIFIER,
                public_market_analysis_bundle=analysis,
                pit_evidence_registry=pit,
            )


if __name__ == "__main__":
    unittest.main()
