from __future__ import annotations

import copy
import unittest

from trade_system.theory_paper_v2.domain.association_model import (
    INTERPRETATION_BOUNDARIES,
    AssociationModelError,
    build_association_revision,
    build_identification_contract,
    verify_association_revision,
)
from trade_system.theory_paper_v2.domain.market_knowledge_graph import (
    NODE_STAGE_ORDER,
    NODE_TYPES,
    MarketKnowledgeGraphError,
    apply_graph_delta,
    association_history,
    build_graph_delta,
    build_graph_node_revision,
    create_market_knowledge_graph,
    dependency_members,
    node_history,
    verify_market_knowledge_graph,
)


def identification_contract() -> dict:
    return {
        "design": "NATURAL_EXPERIMENT",
        "estimand": "average effect of the registered policy shock on the target measure",
        "treatment_ref": "node:event",
        "outcome_ref": "node:fact",
        "assignment_or_instrument_ref": "registered discontinuous announcement timing",
        "assumptions": ["no concurrent unregistered intervention in the event window"],
        "diagnostics": ["pre-trend and placebo windows are recorded"],
        "scope": "synthetic fixture population and registered event window only",
        "limitations": ["identification remains conditional on stated assumptions"],
    }


def association_candidate(
    association_type: str = "OBSERVED_ASSOCIATION",
    *,
    association_id: str = "association:event-fact",
    revision: int = 1,
    predecessor_digest: str | None = None,
    available_at: str = "2026-08-06T00:02:00Z",
) -> dict:
    predictive = association_type == "PREDICTIVE_LEAD"
    causal = association_type == "IDENTIFIED_CAUSAL_EFFECT"
    return {
        "schema_version": "V3_1_ASSOCIATION_REVISION",
        "association_id": association_id,
        "revision": revision,
        "predecessor_digest": predecessor_digest,
        "source_node_id": "node:event",
        "target_node_id": "node:fact",
        "relation": "LEADS" if predictive else "TRANSMITS_TO",
        "association_type": association_type,
        "method": "registered Granger predictive test" if predictive else "registered event-window estimate",
        "interpretation_boundary": INTERPRETATION_BOUNDARIES[association_type],
        "estimate_interval": {
            "lower": "0.1",
            "point": "0.2",
            "upper": "0.3",
            "scale": "EFFECT_SIZE" if causal or predictive else "CORRELATION",
            "unit": "INDEX",
            "interval_kind": "IDENTIFICATION_INTERVAL" if causal else "ESTIMATION_INTERVAL",
        },
        "window": {
            "start_at": "2026-08-05T00:00:00Z",
            "end_at": "2026-08-06T00:00:00Z",
            "timeframe": "1h",
            "sample_count": 24,
        },
        "lag": {
            "value": 1 if predictive else 0,
            "unit": "HOUR",
            "direction": "SOURCE_LEADS_TARGET" if predictive else "SYNCHRONOUS",
        },
        "regime": {
            "regime_ids": ["regime:calm"],
            "condition_refs": ["condition:liquidity-normal"],
        },
        "coverage": {"ratio": "1", "status": "COMPLETE", "limitations": []},
        "stability": {
            "assessment": "STABLE_WITHIN_WINDOW",
            "evidence_window_count": 2,
            "break_refs": [],
        },
        "dependency_group_ids": ["dependency:shared"],
        "provenance": [
            {
                "source_ref": "fixture:source",
                "source_digest": "a" * 64,
                "observed_at": "2026-08-06T00:00:00Z",
                "available_at": "2026-08-06T00:01:00Z",
                "revision_ref": "fixture:source@1",
            }
        ],
        "validity": {"valid_from": available_at, "valid_until": None},
        "identification_contract": identification_contract() if causal else None,
        "status": "ACTIVE",
        "created_at": "2026-08-06T00:01:30Z",
        "available_at": available_at,
        "limitations": ["synthetic fixture does not establish external validity"],
    }


def node_candidate(
    node_id: str,
    node_type: str,
    *,
    revision: int = 1,
    predecessor_digest: str | None = None,
    available_at: str = "2026-08-06T00:01:00Z",
    status: str = "ACTIVE",
    payload_char: str = "b",
) -> dict:
    return {
        "schema_version": "V3_1_GRAPH_NODE_REVISION",
        "node_id": node_id,
        "revision": revision,
        "predecessor_digest": predecessor_digest,
        "node_type": node_type,
        "label": f"fixture {node_type}",
        "description": "public fixture node with explicit point-in-time provenance",
        "payload_ref": f"fixture:{node_id}",
        "payload_digest": payload_char * 64,
        "observed_at": "2026-08-06T00:00:00Z",
        "available_at": available_at,
        "validity": {"valid_from": available_at, "valid_until": None},
        "status": status,
        "dependency_group_ids": ["dependency:shared"],
        "provenance": [
            {
                "source_ref": "fixture:source",
                "source_digest": "a" * 64,
                "observed_at": "2026-08-06T00:00:00Z",
                "available_at": "2026-08-06T00:00:30Z",
                "revision_ref": "fixture:source@1",
            }
        ],
        "created_at": "2026-08-06T00:00:30Z",
        "limitations": ["synthetic fixture only"],
    }


def delta_candidate(
    graph: dict,
    *,
    delta_id: str,
    revision: int,
    available_at: str,
    nodes: list[dict],
    associations: list[dict],
) -> dict:
    return {
        "schema_version": "V3_1_GRAPH_DELTA",
        "delta_id": delta_id,
        "graph_id": graph["graph_id"],
        "base_graph_revision": graph["revision"],
        "base_graph_digest": graph["graph_digest"],
        "revision": revision,
        "occurred_at": available_at,
        "available_at": available_at,
        "node_revisions": nodes,
        "association_revisions": associations,
        "dependency_group_ids": ["dependency:shared"],
        "reason": "append admitted fixture research revisions",
    }


class AssociationModelV31Tests(unittest.TestCase):
    def test_five_types_are_distinct_and_granger_is_predictive_only(self) -> None:
        for association_type in (
            "OBSERVED_ASSOCIATION",
            "CONDITIONAL_DEPENDENCE",
            "PREDICTIVE_LEAD",
            "MECHANISM_HYPOTHESIS",
            "IDENTIFIED_CAUSAL_EFFECT",
        ):
            candidate = association_candidate(
                association_type, association_id=f"association:{association_type}"
            )
            admitted = build_association_revision(
                candidate, decision_at="2026-08-06T00:03:00Z"
            )
            self.assertEqual(association_type, admitted["association_type"])
            self.assertEqual(
                INTERPRETATION_BOUNDARIES[association_type],
                admitted["interpretation_boundary"],
            )
        predictive = build_association_revision(
            association_candidate("PREDICTIVE_LEAD"),
            decision_at="2026-08-06T00:03:00Z",
        )
        self.assertEqual(
            "PREDICTIVE_NOT_STRUCTURAL_CAUSAL",
            predictive["interpretation_boundary"],
        )
        bad = association_candidate("IDENTIFIED_CAUSAL_EFFECT")
        bad["method"] = "Granger causality"
        with self.assertRaisesRegex(
            AssociationModelError, "GRANGER_MUST_BE_PREDICTIVE_NOT_CAUSAL"
        ):
            build_association_revision(bad, decision_at="2026-08-06T00:03:00Z")

    def test_identified_causal_effect_requires_identification_contract(self) -> None:
        candidate = association_candidate("IDENTIFIED_CAUSAL_EFFECT")
        candidate["identification_contract"] = None
        with self.assertRaisesRegex(
            AssociationModelError, "IDENTIFIED_CAUSAL_CONTRACT_AND_ESTIMATE_REQUIRED"
        ):
            build_association_revision(candidate, decision_at="2026-08-06T00:03:00Z")
        contract = build_identification_contract(identification_contract())
        self.assertEqual(64, len(contract["identification_contract_digest"]))

    def test_association_type_upgrade_and_endpoint_rewrite_are_forbidden(self) -> None:
        first = build_association_revision(
            association_candidate(), decision_at="2026-08-06T00:03:00Z"
        )
        upgraded = association_candidate(
            "IDENTIFIED_CAUSAL_EFFECT",
            revision=2,
            predecessor_digest=first["association_digest"],
            available_at="2026-08-06T00:04:00Z",
        )
        with self.assertRaisesRegex(
            AssociationModelError, "IDENTITY_OR_TYPE_REWRITE_FORBIDDEN"
        ):
            build_association_revision(
                upgraded,
                decision_at="2026-08-06T00:05:00Z",
                prior_revision=first,
            )

    def test_invalid_estimate_interval_fails_closed(self) -> None:
        candidate = association_candidate()
        candidate["estimate_interval"].update(
            {"lower": "0.4", "point": "0.2", "upper": "0.3"}
        )
        with self.assertRaisesRegex(
            AssociationModelError, "ASSOCIATION_ESTIMATE_INTERVAL_INVALID"
        ):
            build_association_revision(candidate, decision_at="2026-08-06T00:03:00Z")

    def test_future_window_and_future_provenance_fail_pit(self) -> None:
        future_window = association_candidate()
        future_window["window"]["end_at"] = "2026-08-06T00:02:30Z"
        with self.assertRaisesRegex(AssociationModelError, "WINDOW_NOT_PIT"):
            build_association_revision(
                future_window, decision_at="2026-08-06T00:03:00Z"
            )
        future_source = association_candidate()
        future_source["provenance"][0]["available_at"] = "2026-08-06T00:02:30Z"
        with self.assertRaisesRegex(AssociationModelError, "PROVENANCE_NOT_PIT"):
            build_association_revision(
                future_source, decision_at="2026-08-06T00:03:00Z"
            )

    def test_canonical_digest_is_stable_and_verifiable(self) -> None:
        candidate = association_candidate()
        first = build_association_revision(
            candidate, decision_at="2026-08-06T00:03:00Z"
        )
        second = build_association_revision(
            copy.deepcopy(candidate), decision_at="2026-08-06T00:03:00Z"
        )
        self.assertEqual(first["association_digest"], second["association_digest"])
        self.assertEqual(
            first["association_digest"],
            verify_association_revision(
                first, decision_at="2026-08-06T00:03:00Z"
            ),
        )

    def test_retrospective_validity_is_distinct_from_knowledge_time(self) -> None:
        candidate = association_candidate()
        candidate["validity"]["valid_from"] = "2026-08-05T00:00:00Z"
        admitted = build_association_revision(
            candidate, decision_at="2026-08-06T00:03:00Z"
        )
        self.assertEqual("2026-08-05T00:00:00Z", admitted["validity"]["valid_from"])
        self.assertEqual("2026-08-06T00:02:00Z", admitted["available_at"])


class MarketKnowledgeGraphV31Tests(unittest.TestCase):
    def _first_graph(self) -> tuple[dict, dict, dict]:
        graph0 = create_market_knowledge_graph(
            graph_id="graph:fixture", created_at="2026-08-06T00:00:00Z"
        )
        event = build_graph_node_revision(
            node_candidate("node:event", "INFORMATION_EVENT"),
            decision_at="2026-08-06T00:01:00Z",
        )
        fact = build_graph_node_revision(
            node_candidate("node:fact", "MARKET_FACT", payload_char="c"),
            decision_at="2026-08-06T00:01:00Z",
        )
        association = build_association_revision(
            association_candidate(), decision_at="2026-08-06T00:02:00Z"
        )
        unsigned_delta = delta_candidate(
            graph0,
            delta_id="delta:1",
            revision=1,
            available_at="2026-08-06T00:03:00Z",
            nodes=[event, fact],
            associations=[association],
        )
        delta = build_graph_delta(
            unsigned_delta,
            decision_at="2026-08-06T00:03:00Z",
            prior_graph=graph0,
        )
        graph1 = apply_graph_delta(
            graph0, delta, decision_at="2026-08-06T00:03:00Z"
        )
        return graph0, graph1, delta

    def test_node_vocabulary_covers_information_to_outcome_chain(self) -> None:
        self.assertTrue(
            {
                "INFORMATION_ACTOR",
                "INFORMATION_EVENT",
                "MARKET_FACT",
                "DERIVED_MEASURE",
                "LATENT_STATE",
                "MECHANISM_HYPOTHESIS",
                "PATH_HYPOTHESIS",
                "EXPECTATION",
                "SCENARIO_PATH",
                "ACTION_CANDIDATE",
                "OUTCOME",
            }.issubset(NODE_TYPES)
        )

    def test_expectation_is_a_first_class_graph_node(self) -> None:
        expectation = build_graph_node_revision(
            node_candidate("node:expectation", "EXPECTATION", payload_char="e"),
            decision_at="2026-08-06T00:01:00Z",
        )
        self.assertEqual("EXPECTATION", expectation["node_type"])
        self.assertEqual(6, NODE_STAGE_ORDER["EXPECTATION"])

    def test_retrospective_node_validity_does_not_backdate_knowledge(self) -> None:
        candidate = node_candidate("node:retrospective", "MARKET_FACT")
        candidate["validity"]["valid_from"] = "2026-08-05T00:00:00Z"
        admitted = build_graph_node_revision(
            candidate, decision_at="2026-08-06T00:01:00Z"
        )
        self.assertEqual("2026-08-05T00:00:00Z", admitted["validity"]["valid_from"])
        self.assertEqual("2026-08-06T00:01:00Z", admitted["available_at"])

    def test_delta_apply_preserves_history_heads_and_dependencies(self) -> None:
        graph0, graph1, _ = self._first_graph()
        self.assertEqual(0, graph0["revision"])
        self.assertEqual(1, graph1["revision"])
        self.assertEqual(2, len(graph1["node_history"]))
        self.assertEqual(1, len(graph1["association_history"]))
        self.assertEqual((graph1["node_history"][0],), node_history(graph1, "node:event"))
        self.assertEqual(
            (graph1["association_history"][0],),
            association_history(graph1, "association:event-fact"),
        )
        members = dependency_members(graph1, "dependency:shared")
        self.assertEqual(
            ["node:event@1", "node:fact@1"], members["node_revision_refs"]
        )
        self.assertEqual(
            ["association:event-fact@1"], members["association_revision_refs"]
        )
        self.assertEqual(
            graph1["graph_digest"],
            verify_market_knowledge_graph(
                graph1, decision_at="2026-08-06T00:03:00Z"
            ),
        )

    def test_second_delta_appends_revisions_without_overwrite_or_delete(self) -> None:
        _, graph1, _ = self._first_graph()
        first_node = next(
            row for row in graph1["node_history"] if row["node_id"] == "node:fact"
        )
        first_association = graph1["association_history"][0]
        revised_node_candidate = node_candidate(
            "node:fact",
            "MARKET_FACT",
            revision=2,
            predecessor_digest=first_node["node_digest"],
            available_at="2026-08-06T00:04:00Z",
            payload_char="d",
        )
        revised_node = build_graph_node_revision(
            revised_node_candidate,
            decision_at="2026-08-06T00:04:00Z",
            prior_revision=first_node,
        )
        revised_association_candidate = association_candidate(
            revision=2,
            predecessor_digest=first_association["association_digest"],
            available_at="2026-08-06T00:04:00Z",
        )
        revised_association_candidate["estimate_interval"].update(
            {"lower": "0.15", "point": "0.25", "upper": "0.35"}
        )
        revised_association = build_association_revision(
            revised_association_candidate,
            decision_at="2026-08-06T00:04:00Z",
            prior_revision=first_association,
        )
        unsigned_delta = delta_candidate(
            graph1,
            delta_id="delta:2",
            revision=2,
            available_at="2026-08-06T00:05:00Z",
            nodes=[revised_node],
            associations=[revised_association],
        )
        delta = build_graph_delta(
            unsigned_delta,
            decision_at="2026-08-06T00:05:00Z",
            prior_graph=graph1,
        )
        graph2 = apply_graph_delta(
            graph1, delta, decision_at="2026-08-06T00:05:00Z"
        )
        self.assertEqual(graph1["node_history"], graph2["node_history"][:2])
        self.assertEqual(
            graph1["association_history"], graph2["association_history"][:1]
        )
        self.assertEqual([1, 2], [row["revision"] for row in node_history(graph2, "node:fact")])
        self.assertEqual(
            [1, 2],
            [row["revision"] for row in association_history(graph2, "association:event-fact")],
        )
        self.assertEqual(first_node["node_digest"], graph2["node_history"][1]["node_digest"])
        self.assertEqual(2, graph2["revision"])

    def test_delta_base_mismatch_and_history_tampering_fail_closed(self) -> None:
        graph0, graph1, delta = self._first_graph()
        wrong_base = copy.deepcopy(delta)
        wrong_base.pop("graph_delta_digest")
        wrong_base["base_graph_digest"] = "f" * 64
        with self.assertRaisesRegex(
            MarketKnowledgeGraphError, "GRAPH_DELTA_BASE_DIGEST_INVALID"
        ):
            build_graph_delta(
                wrong_base,
                decision_at="2026-08-06T00:03:00Z",
                prior_graph=graph0,
            )
        tampered = copy.deepcopy(graph1)
        tampered["node_history"].clear()
        with self.assertRaisesRegex(MarketKnowledgeGraphError, "GRAPH_DIGEST_INVALID"):
            verify_market_knowledge_graph(
                tampered, decision_at="2026-08-06T00:03:00Z"
            )

    def test_node_future_availability_fails_pit(self) -> None:
        candidate = node_candidate(
            "node:future", "MARKET_FACT", available_at="2026-08-06T00:04:00Z"
        )
        with self.assertRaisesRegex(MarketKnowledgeGraphError, "NOT_POINT_IN_TIME"):
            build_graph_node_revision(
                candidate, decision_at="2026-08-06T00:03:00Z"
            )


if __name__ == "__main__":
    unittest.main()
