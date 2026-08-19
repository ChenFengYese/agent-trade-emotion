from __future__ import annotations

import copy
import hashlib
import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from trade_system.research_system_contract_v1_2 import (
    validate_research_system_bundle_v1_2,
)


ROOT = Path(__file__).resolve().parents[1]
OBJECT_PATH = "config/research_system.object_dictionary.v1.json"
HYPOTHESIS_PATH = "config/research_system.hypothesis_validation_queue.v1.json"
MEASUREMENT_PATH = "config/research_system.measurement_contract.v1.json"
PARAMETER_PATH = "config/research_system.parameter_registry.v1.json"
SOURCE_PATH = "config/research_system.source_authority_registry.v1.json"
DISPUTE_PATH = "config/research_system.dispute_registry.v1.json"
STAGE_PATH = "config/research_system.stage_contract.v1.json"
OVERLAY_PATH = "config/research_system.semantic_claim_boundary.v1_1.json"
PREDECESSOR_PATHS = (
    OBJECT_PATH,
    HYPOTHESIS_PATH,
    MEASUREMENT_PATH,
    PARAMETER_PATH,
    SOURCE_PATH,
    DISPUTE_PATH,
    STAGE_PATH,
    OVERLAY_PATH,
)
GRAPH_PATH = "config/research_system.runtime_hypothesis_graph_contract.v1_2.json"
REGISTRY_PATH = (
    "config/research_system.runtime_hypothesis_template_registry.v1_2.json"
)
EVIDENCE_PATH = (
    "config/research_system.runtime_evidence_evaluation_contract.v1_2.json"
)
CONTRACT_PATHS = (GRAPH_PATH, REGISTRY_PATH, EVIDENCE_PATH)
PATHS = PREDECESSOR_PATHS + CONTRACT_PATHS
DIGEST_FIELDS = {
    GRAPH_PATH: "contract_sha256",
    REGISTRY_PATH: "registry_sha256",
    EVIDENCE_PATH: "contract_sha256",
}
EXPECTED_DIGESTS = {
    GRAPH_PATH: "ecffaef260232b2e16eac8f2d80e49c44f97006a8cf8a1ca948a588f3ca1672b",
    REGISTRY_PATH: "11b9f1e85cbc7d0e8a1c4ad4b8cc90b8878eb335bd26d098503bbc1b44b02f6c",
    EVIDENCE_PATH: "7005944011f19ebde8f60f3fe481e7922890eb167c1eb3a062c0ebdf747a1932",
}
EXPECTED_PREDECESSOR_BUNDLE_DIGEST = (
    "8a607d9d472f5a26d05e4e74ddca27876621a52ec102a6088f723687c52950fe"
)
PATH_IDENTITY_FIELDS = (
    "activation_predicate_ids",
    "required_partial_order_edges",
    "optional_partial_order_edges",
    "repeatable_milestones",
    "skippable_milestones",
    "terminal_cell_id",
    "terminal_matcher_predicate_ids",
    "horizon_bars",
    "clock_profile",
    "hard_invalidation_predicate_ids",
    "expiry_predicate_ids",
)


def read_bundle() -> dict[str, str]:
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in PATHS}


def canonical_digest(document: dict[str, Any], path: str) -> str:
    unsigned = copy.deepcopy(document)
    unsigned.pop(DIGEST_FIELDS[path], None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    domain = document["canonicalization"]["domain"].encode("utf-8")
    separator = bytes.fromhex(document["canonicalization"]["domain_separator_hex"])
    return hashlib.sha256(domain + separator + canonical).hexdigest()


def resign(document: dict[str, Any], path: str) -> str:
    document[DIGEST_FIELDS[path]] = canonical_digest(document, path)
    return json.dumps(document, ensure_ascii=True, indent=2) + "\n"


def resign_path_identity(path_template: dict[str, Any]) -> None:
    identity = {field: path_template[field] for field in PATH_IDENTITY_FIELDS}
    canonical = json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    path_template["path_identity_digest"] = hashlib.sha256(
        b"msta-hed/runtime-path-semantic-identity/v1_2\0" + canonical
    ).hexdigest()


class ExplodingMapping(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise RuntimeError("mapping exploded")

    def __iter__(self):
        raise RuntimeError("mapping exploded")

    def __len__(self) -> int:
        raise RuntimeError("mapping exploded")


class ResearchSystemContractV12Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = read_bundle()

    def mutate(
        self, path: str, operation: Callable[[dict[str, Any]], None]
    ) -> dict[str, Any]:
        document = json.loads(self.bundle[path])
        operation(document)
        self.bundle[path] = resign(document, path)
        return document

    def result(self) -> dict[str, Any]:
        return validate_research_system_bundle_v1_2(self.bundle)

    def assert_rejected(self, reason_code: str) -> dict[str, Any]:
        result = self.result()
        self.assertEqual("REJECTED", result["status"], result)
        self.assertEqual(reason_code, result["reason_code"], result)
        self.assertIsNone(result["bundle_digest"])
        self.assertEqual(
            {"status", "reason_code", "details", "bundle_digest"}, set(result)
        )
        return result

    def assert_frozen_predecessor_byte_drift(
        self, path: str, *, rejected_by_v1_1: bool
    ) -> None:
        self.bundle[path] += "\n"
        if rejected_by_v1_1:
            result = self.assert_rejected("E_V1_1_PREDECESSOR")
            self.assertEqual(
                "E_PREDECESSOR_BYTES",
                result["details"]["v1_1_reason_code"],
            )
            self.assertEqual(path, result["details"]["v1_1_path"])
        else:
            result = self.assert_rejected("E_V1_1_PREDECESSOR_BYTES")
            self.assertEqual(path, result["details"]["path"])

    def test_001_clean_bundle_is_accepted(self) -> None:
        result = self.result()
        self.assertEqual("ACCEPTED", result["status"])
        self.assertEqual("OK", result["reason_code"])
        self.assertEqual(11, result["details"]["document_count"])
        self.assertEqual(8, result["details"]["predecessor_document_count"])
        self.assertEqual(3, result["details"]["v1_2_contract_document_count"])
        self.assertEqual(
            EXPECTED_PREDECESSOR_BUNDLE_DIGEST,
            result["details"]["predecessor_bundle_digest"],
        )
        self.assertEqual(
            "f730d9f712001ec603a33e26977efaadf8db1a7492cba2e4d24acaee7ba10625",
            result["bundle_digest"],
        )

    def test_002_mapping_order_does_not_change_identity(self) -> None:
        first = self.result()
        self.bundle = dict(reversed(list(self.bundle.items())))
        second = self.result()
        self.assertEqual("ACCEPTED", second["status"])
        self.assertEqual(first["bundle_digest"], second["bundle_digest"])

    def test_003_repeated_validation_is_deterministic(self) -> None:
        self.assertEqual(self.result(), self.result())

    def test_004_each_canonical_digest_is_independently_recomputable(self) -> None:
        for path in CONTRACT_PATHS:
            document = json.loads(self.bundle[path])
            self.assertEqual(EXPECTED_DIGESTS[path], canonical_digest(document, path))
            self.assertEqual(EXPECTED_DIGESTS[path], document[DIGEST_FIELDS[path]])

    def test_005_non_mapping_input_is_total(self) -> None:
        result = validate_research_system_bundle_v1_2(None)  # type: ignore[arg-type]
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INPUT_TYPE", result["reason_code"])

    def test_006_exploding_mapping_is_total(self) -> None:
        result = validate_research_system_bundle_v1_2(ExplodingMapping())
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INTERNAL_TOTALITY", result["reason_code"])

    def test_007_missing_document_is_rejected(self) -> None:
        self.bundle.pop(EVIDENCE_PATH)
        self.assert_rejected("E_FILE_SET")

    def test_008_extra_document_is_rejected(self) -> None:
        self.bundle["config/not-authorized.json"] = "{}"
        self.assert_rejected("E_FILE_SET")

    def test_009_non_string_raw_document_is_rejected(self) -> None:
        self.bundle[GRAPH_PATH] = b"{}"  # type: ignore[assignment]
        self.assert_rejected("E_RAW_TYPE")

    def test_010_malformed_json_is_rejected(self) -> None:
        self.bundle[GRAPH_PATH] = "{"
        self.assert_rejected("E_JSON_MALFORMED")

    def test_011_non_object_top_level_is_rejected(self) -> None:
        self.bundle[EVIDENCE_PATH] = "[]"
        self.assert_rejected("E_TOP_LEVEL_TYPE")

    def test_012_duplicate_json_key_is_rejected(self) -> None:
        self.bundle[GRAPH_PATH] = self.bundle[GRAPH_PATH].replace(
            '  "contract_id":',
            '  "contract_id": "DUPLICATE",\n  "contract_id":',
            1,
        )
        self.assert_rejected("E_JSON_DUPLICATE_KEY")

    def test_013_nonfinite_number_is_rejected(self) -> None:
        self.bundle[REGISTRY_PATH] = self.bundle[REGISTRY_PATH].replace(
            '"value": 2.0', '"value": NaN', 1
        )
        self.assert_rejected("E_JSON_NONFINITE")

    def test_014_unknown_top_level_field_is_rejected(self) -> None:
        self.mutate(GRAPH_PATH, lambda document: document.update({"authority": True}))
        self.assert_rejected("E_UNKNOWN_FIELD")

    def test_015_bad_self_digest_is_rejected(self) -> None:
        document = json.loads(self.bundle[EVIDENCE_PATH])
        document["contract_sha256"] = "0" * 64
        self.bundle[EVIDENCE_PATH] = json.dumps(document)
        self.assert_rejected("E_SELF_DIGEST")

    def test_016_candidate_cannot_change_canonicalization(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["canonicalization"].update(
                {"domain": "candidate/authority"}
            ),
        )
        self.assert_rejected("E_CANONICALIZATION")

    def test_017_candidate_cannot_replace_route_authority(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["authority_binding"]["route_decision"].update(
                {"decision_id": "SELF_AUTHORIZED"}
            ),
        )
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_018_candidate_cannot_accept_itself(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document.update({"status": "ACCEPT_P0_1"}),
        )
        self.assert_rejected("E_METADATA")

    def test_019_stage_d0_cannot_be_enabled(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["stage_denials"].update({"D0": "ALLOWED"}),
        )
        self.assert_rejected("E_STAGE_DENIAL")

    def test_020_backtest_cannot_be_authorized(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["claim_boundary"].update(
                {"backtest": "AUTHORIZED"}
            ),
        )
        self.assert_rejected("E_CLAIM_BOUNDARY")

    def test_021_research_plane_cannot_authorize_action(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["plane_contract"].update(
                {"research_plane_authorizes_action": True}
            ),
        )
        self.assert_rejected("E_GRAPH_SEMANTICS")

    def test_022_trade_parent_cardinality_cannot_be_many(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["graph_semantics"].update(
                {"trade_parent_path_cardinality": "ONE_OR_MORE"}
            ),
        )
        self.assert_rejected("E_GRAPH_SEMANTICS")

    def test_023_runtime_template_creation_is_forbidden(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["generation_contract"].update(
                {"runtime_template_creation": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_GENERATOR_POLICY")

    def test_024_llm_story_injection_is_forbidden(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["generation_contract"].update(
                {"llm_story_injection": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_GENERATOR_POLICY")

    def test_025_outcome_conditioned_generation_is_forbidden(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["generation_contract"].update(
                {"outcome_conditioned_generation": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_GENERATOR_POLICY")

    def test_026_prior_revision_rewrite_is_forbidden(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["generation_contract"].update(
                {"prior_revision_rewrite": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_GENERATOR_POLICY")

    def test_027_graph_backdating_is_forbidden(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["generation_contract"].update(
                {"backdating": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_GENERATOR_POLICY")

    def test_028_pool_overflow_cannot_silently_prune(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["generation_contract"]["capacity_policy"].update(
                {"silent_pruning": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_GENERATOR_POLICY")

    def test_029_pool_overflow_must_return_unknown_and_abstain(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["generation_contract"]["capacity_policy"].update(
                {"overflow_disposition": "KEEP_TOP_SCORE"}
            ),
        )
        self.assert_rejected("E_GENERATOR_POLICY")

    def test_030_path_identity_cannot_include_trade_side(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["path_identity_contract"][
                "semantic_identity_fields"
            ].append("default_trade_side"),
        )
        self.assert_rejected("E_PATH_IDENTITY")

    def test_031_same_side_paths_cannot_be_merged(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["path_identity_contract"].update(
                {"same_side_merge": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_PATH_IDENTITY")

    def test_032_unknown_path_cannot_become_outcome(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["direction_and_residual_contract"][
                "UNKNOWN_PATH"
            ].update({"is_outcome": True}),
        )
        self.assert_rejected("E_RESIDUAL_SEMANTICS")

    def test_033_other_path_must_remain_future_probability_eligible(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["direction_and_residual_contract"][
                "OTHER_PATH"
            ].update({"is_probability_eligible_in_future": False}),
        )
        self.assert_rejected("E_RESIDUAL_SEMANTICS")

    def test_034_abstain_cannot_become_market_path(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["direction_and_residual_contract"][
                "ABSTAIN"
            ].update({"is_outcome": True}),
        )
        self.assert_rejected("E_RESIDUAL_SEMANTICS")

    def test_035_trade_schema_must_keep_parent_path_instance(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["object_schemas"][
                "TradeHypothesisInstance"
            ].remove("parent_path_instance_id"),
        )
        self.assert_rejected("E_SCHEMA")

    def test_036_frozen_registry_rejects_injected_predicate(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            injected = copy.deepcopy(document["machine_predicates"][0])
            injected["predicate_id"] = "PRED-LLM-STORY-INJECTED-01"
            document["machine_predicates"].append(injected)

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_TEMPLATE_INJECTION")

    def test_037_predicate_shape_is_exact(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["machine_predicates"][0].pop(
                "minimum_persistence"
            ),
        )
        self.assert_rejected("E_FIELD_EMPTY")

    def test_038_predicate_clock_must_be_point_in_time(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["machine_predicates"][0]["clock"].update(
                {"available_relation": "AVAILABLE_AFTER_DECISION"}
            ),
        )
        self.assert_rejected("E_CLOCK")

    def test_039_hard_invalidation_precedence_is_zero(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            predicate = next(
                item
                for item in document["machine_predicates"]
                if item["terminal_reason"] == "HARD_INVALIDATION"
            )
            predicate["precedence"] = 9

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_PREDICATE_TERMINAL")

    def test_040_hard_invalidation_reference_must_be_terminal_typed(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["mechanism_templates"][0].update(
                {
                    "hard_invalidation_predicate_ids": [
                        "PRED-LOW-DOWNSIDE-EFFICIENCY-01"
                    ]
                }
            ),
        )
        self.assert_rejected("E_PREDICATE_TERMINAL")

    def test_041_exact_duplicate_path_semantics_are_rejected(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            source = document["path_templates"][1]
            target = document["path_templates"][3]
            for field in PATH_IDENTITY_FIELDS:
                target[field] = copy.deepcopy(source[field])
            target["path_identity_digest"] = source["path_identity_digest"]

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_DUPLICATE_PATH")

    def test_042_registry_path_identity_cannot_include_side(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            path = document["path_templates"][0]
            path["identity_fields"].append("default_trade_side")

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_PATH_IDENTITY")

    def test_043_terminal_direction_and_side_must_cohere(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["path_templates"][0].update(
                {"default_trade_side": "SHORT"}
            ),
        )
        self.assert_rejected("E_DIRECTION_COVERAGE")

    def test_044_opposing_direction_cannot_be_pruned(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["path_templates"].pop(2),
        )
        self.assert_rejected("E_TEMPLATE_INJECTION")

    def test_045_finite_pool_cannot_hide_an_extra_path(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            injected = copy.deepcopy(document["path_templates"][0])
            injected["path_template_id"] = "PHT-INJECTED-FIFTH-PATH-01"
            document["path_templates"].append(injected)

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_TEMPLATE_INJECTION")

    def test_046_mechanism_score_cannot_transfer_to_path(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            edge = next(
                item
                for item in document["topology_edges"]
                if item["edge_type"] == "MECHANISM_TO_PATH"
            )
            edge["transfer_mode"] = "TRANSFER_SCORE"

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_MECHANISM_TRANSFER")

    def test_047_trade_cannot_have_multiple_parent_paths(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            edge = copy.deepcopy(
                next(
                    item
                    for item in document["topology_edges"]
                    if item["edge_type"] == "PATH_TO_TRADE"
                )
            )
            edge["edge_template_id"] = "EDGE-PT-SECOND-PARENT"
            edge["from_template_id"] = "PHT-SHOCK-BALANCE-01"
            document["topology_edges"].append(edge)

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_TRADE_PARENT")

    def test_048_trade_cannot_have_zero_parent_paths(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            document["topology_edges"] = [
                edge
                for edge in document["topology_edges"]
                if not (
                    edge["edge_type"] == "PATH_TO_TRADE"
                    and edge["to_template_id"]
                    == "THT-ABSORPTION-RECLAIM-LONG-01"
                )
            ]

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_TRADE_PARENT")

    def test_049_trade_permission_cannot_be_enabled(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["trade_templates"][0].update(
                {"permission_state": "AUTHORIZED"}
            ),
        )
        self.assert_rejected("E_PERMISSION_ESCALATION")

    def test_050_trade_max_risk_must_remain_zero(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["trade_templates"][0].update(
                {"max_risk": 0.01}
            ),
        )
        self.assert_rejected("E_PERMISSION_ESCALATION")

    def test_051_mechanism_context_cannot_strengthen_trade(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document["trade_templates"][0].update(
                {"mechanism_context_effect": "INCREASE_SCORE_AND_SIZE"}
            ),
        )
        self.assert_rejected("E_MECHANISM_TRANSFER")

    def test_052_fixture_binding_cannot_be_swapped(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            first = document["fixture_bindings"][0]
            second = document["fixture_bindings"][1]
            first["fixture_set_id"], second["fixture_set_id"] = (
                second["fixture_set_id"],
                first["fixture_set_id"],
            )

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_FIXTURE_BINDING")

    def test_053_terminal_cells_must_be_disjoint(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            source = document["path_templates"][0]
            target = document["path_templates"][1]
            target["terminal_cell_id"] = source["terminal_cell_id"]
            resign_path_identity(target)

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_TERMINAL_PARTITION")

    def test_054_registry_change_cannot_keep_stale_cross_document_authority(self) -> None:
        self.mutate(
            REGISTRY_PATH,
            lambda document: document.update({"created_at": "2026-07-27T11:00:00Z"}),
        )
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_055_evidence_aliases_cannot_count_as_independent_support(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["evidence_semantics"].update(
                {"copied_alias_independent_support": True}
            ),
        )
        self.assert_rejected("E_EVIDENCE_SEMANTICS")

    def test_056_one_lineage_can_contribute_only_once_per_target_update(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["evidence_semantics"].update(
                {"one_lineage_per_target_update": False}
            ),
        )
        self.assert_rejected("E_EVIDENCE_SEMANTICS")

    def test_057_hard_invalidation_must_dominate_ordinal_score(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["evidence_semantics"].update(
                {"hard_invalidation_dominates_ordinal": False}
            ),
        )
        self.assert_rejected("E_EVIDENCE_SEMANTICS")

    def test_058_terminal_instance_cannot_be_revived(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["evidence_semantics"].update(
                {"terminal_revival": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_EVIDENCE_SEMANTICS")

    def test_059_equal_opposing_evidence_cannot_use_identifier_tie_break(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["conflict_contract"].update(
                {"identifier_tie_break_as_semantic_winner": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_CONFLICT_SEMANTICS")

    def test_060_mechanism_cannot_be_promoted_to_unique_causal_truth(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["mechanism_identifiability_classes"][0].update(
                {"unique_causal_choice": "ALLOWED", "truth_label": "TRUE"}
            ),
        )
        self.assert_rejected("E_IDENTIFIABILITY")

    def test_061_every_named_path_pair_needs_discrimination(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["path_discrimination_contracts"].pop(),
        )
        self.assert_rejected("E_PATH_DISCRIMINATION")

    def test_062_same_side_paths_must_be_decision_identifiable(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            contract = next(
                item
                for item in document["path_discrimination_contracts"]
                if item["next_observation_plan_id"]
                == "NOP-SAME-DOWNSIDE-SHORT-01"
            )
            contract["decision_identifiable"] = False

        self.mutate(EVIDENCE_PATH, operation)
        self.assert_rejected("E_PATH_DISCRIMINATION")

    def test_063_uncalibrated_numeric_information_gain_is_forbidden(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["next_observation_plans"][0].update(
                {"numeric_information_gain": 0.42}
            ),
        )
        self.assert_rejected("E_NEXT_OBSERVATION")

    def test_064_next_observation_must_arrive_before_expiry(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["next_observation_plans"][0].update(
                {"deadline_rule": "AFTER_PATH_EXPIRY"}
            ),
        )
        self.assert_rejected("E_NEXT_OBSERVATION")

    def test_065_ordinal_support_cannot_become_numeric_probability(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["probability_contract"]["modes"][0].update(
                {"numeric_probability_fields": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_PROBABILITY_ESCALATION")

    def test_066_softmax_of_ordinal_support_cannot_be_allowed(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["probability_contract"][
                "forbidden_transformations"
            ].remove("SOFTMAX_ORDINAL"),
        )
        self.assert_rejected("E_PROBABILITY_ESCALATION")

    def test_067_unknown_path_cannot_enter_future_probability_simplex(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["probability_contract"].update(
                {"unknown_path_in_probability_simplex": True}
            ),
        )
        self.assert_rejected("E_PROBABILITY_ESCALATION")

    def test_068_scenario_aggregation_must_keep_source_path_provenance(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document[
                "terminal_scenario_aggregation_contract"
            ].update({"source_path_provenance_required": False}),
        )
        self.assert_rejected("E_AGGREGATION")

    def test_069_unknown_opportunities_cannot_be_dropped(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["denominator_contract"].update(
                {"unknown_opportunities_reported": False}
            ),
        )
        self.assert_rejected("E_DENOMINATOR")

    def test_070_same_side_paths_cannot_be_pooled_for_acceptance(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["denominator_contract"].update(
                {"same_side_path_results_pooled_for_acceptance": True}
            ),
        )
        self.assert_rejected("E_DENOMINATOR")

    def test_071_dynamic_order_semantics_remain_unset_in_p0_1(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["future_oos_gate"].update(
                {
                    "dynamic_order_and_position_management_contract": (
                        "EVENT_DRIVEN_TRAILING_STOP_v1"
                    )
                }
            ),
        )
        self.assert_rejected("E_FUTURE_GATE")

    def test_072_future_evaluation_semantics_cannot_be_frozen_in_p0_1(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["future_oos_gate"].update(
                {"evaluation_semantics": "FROZEN_STATIC_ENTRY_EXIT"}
            ),
        )
        self.assert_rejected("E_FUTURE_GATE")

    def test_073_boundary_fixture_is_executed_not_merely_present(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            fixture_set = document["synthetic_fixture_sets"][0]
            boundary = next(
                case for case in fixture_set["cases"] if case["case_kind"] == "BOUNDARY"
            )
            boundary["predicate_inputs"][0]["observed_value"] = 0.36

        self.mutate(EVIDENCE_PATH, operation)
        self.assert_rejected("E_FIXTURE_PREDICATE")

    def test_074_clock_fixture_is_executed_not_merely_present(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            fixture_set = document["synthetic_fixture_sets"][0]
            clock = next(
                case for case in fixture_set["cases"] if case["case_kind"] == "CLOCK"
            )
            clock["predicate_inputs"][0]["available_at"] = "2026-01-01T03:00:00Z"

        self.mutate(EVIDENCE_PATH, operation)
        self.assert_rejected("E_FIXTURE_PREDICATE")

    def test_075_gap_fixture_is_executed_not_merely_present(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            fixture_set = document["synthetic_fixture_sets"][0]
            gap = next(
                case for case in fixture_set["cases"] if case["case_kind"] == "GAP"
            )
            gap["predicate_inputs"][0]["has_gap"] = False

        self.mutate(EVIDENCE_PATH, operation)
        self.assert_rejected("E_FIXTURE_PREDICATE")

    def test_076_hard_invalidation_fixture_disposition_is_required(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            fixture_set = document["synthetic_fixture_sets"][0]
            hard = next(
                case
                for case in fixture_set["cases"]
                if case["case_kind"] == "HARD_INVALIDATION"
            )
            hard["expected_template_disposition"] = "ACTIVE_OR_SUPPORTED"

        self.mutate(EVIDENCE_PATH, operation)
        self.assert_rejected("E_FIXTURE_CASE")

    def test_077_expiry_fixture_disposition_is_required(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            fixture_set = document["synthetic_fixture_sets"][0]
            expiry = next(
                case for case in fixture_set["cases"] if case["case_kind"] == "EXPIRY"
            )
            expiry["expected_template_disposition"] = "ACTIVE_OR_SUPPORTED"

        self.mutate(EVIDENCE_PATH, operation)
        self.assert_rejected("E_FIXTURE_CASE")

    def test_078_all_active_templates_require_fixture_sets(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["synthetic_fixture_sets"].pop(),
        )
        self.assert_rejected("E_FIXTURE_BINDING")

    def test_079_fixture_set_cannot_be_rebound_to_another_template(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["synthetic_fixture_sets"][0].update(
                {"template_id": "MHT-SQUEEZE-CONTINUATION-01"}
            ),
        )
        self.assert_rejected("E_FIXTURE_BINDING")

    def test_080_target_effect_schema_cannot_add_utility_or_permission(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["target_effect_schema"].append(
                "permission_delta"
            ),
        )
        self.assert_rejected("E_SCHEMA")

    def test_081_graph_change_cannot_keep_stale_registry_authority(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document.update({"created_at": "2026-07-27T11:00:00Z"}),
        )
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_082_e2_cannot_be_enabled(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["stage_denials"].update({"E2": "ALLOWED"}),
        )
        self.assert_rejected("E_STAGE_DENIAL")

    def test_083_paper_trading_cannot_be_authorized(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["claim_boundary"].update(
                {"paper": "AUTHORIZED"}
            ),
        )
        self.assert_rejected("E_CLAIM_BOUNDARY")

    def test_084_raw_resolution_predicates_are_not_a_partition_proof(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            path = document["path_templates"][1]
            path["terminal_matcher_predicate_ids"] = [
                "PRED-DOWNSIDE-RESUMPTION-RESOLVE-01"
            ]
            resign_path_identity(path)

        self.mutate(REGISTRY_PATH, operation)
        self.assert_rejected("E_TERMINAL_PARTITION")

    def test_085_simultaneous_terminal_matches_cannot_use_identifier_tie_break(
        self,
    ) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["terminal_partition_contract"].update(
                {
                    "simultaneous_candidate_match_count_gt_one": (
                        "CHOOSE_LEXICOGRAPHIC_PATH_ID"
                    )
                }
            ),
        )
        self.assert_rejected("E_TERMINAL_PARTITION")

    def test_086_policy_event_order_is_exact_and_deterministic(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"].update(
                {
                    "policy_event_order": [
                        "available_at_ASC",
                        "event_id_ASC",
                        "source_sequence_ASC",
                    ]
                }
            ),
        )
        self.assert_rejected("E_DYNAMIC_POLICY")

    def test_087_duplicate_policy_event_cannot_apply_twice(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"].update(
                {"duplicate_event_idempotent_no_second_state_change_or_receipt": False}
            ),
        )
        self.assert_rejected("E_DYNAMIC_POLICY")

    def test_088_real_counterfactual_lane_permission_remains_denied(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"].update(
                {"real_permission_state": "AUTHORIZED", "real_max_risk": 1}
            ),
        )
        self.assert_rejected("E_PERMISSION_ESCALATION")

    def test_089_position_management_cannot_add_position(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"]["action_classes"][
                "POSITION_MANAGEMENT"
            ].append("ADD"),
        )
        self.assert_rejected("E_DYNAMIC_POLICY")

    def test_090_graph_revision_cannot_rewrite_position_lock(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "position_lock_contract"
            ].update({"graph_or_path_revision_rewrites_lock": "ALLOWED"}),
        )
        self.assert_rejected("E_POSITION_LOCK")

    def test_091_path_switch_cannot_auto_reverse(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "path_switch_contract"
            ].update({"leading_path_change_auto_reverses_position": True}),
        )
        self.assert_rejected("E_PATH_SWITCH")

    def test_092_path_switch_cannot_auto_add_or_rescue(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "path_switch_contract"
            ].update({"leading_path_change_auto_adds_or_rescues_position": True}),
        )
        self.assert_rejected("E_PATH_SWITCH")

    def test_093_path_switch_cannot_auto_reenter(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "path_switch_contract"
            ].update({"leading_path_change_auto_reenters_after_exit": True}),
        )
        self.assert_rejected("E_PATH_SWITCH")

    def test_094_stop_cannot_be_relaxed(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "position_management_risk_contract"
            ].update({"widen_invalidation_or_stop": "ALLOWED"}),
        )
        self.assert_rejected("E_RISK_MONOTONICITY")

    def test_095_horizon_cannot_be_extended(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "position_management_risk_contract"
            ].update({"horizon_end_may_extend": True}),
        )
        self.assert_rejected("E_RISK_MONOTONICITY")

    def test_096_target_cannot_move_outward(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "position_management_risk_contract"
            ].update({"move_target_outward": "ALLOWED"}),
        )
        self.assert_rejected("E_RISK_MONOTONICITY")

    def test_097_total_risk_cannot_omit_pending_fees_or_tail(self) -> None:
        def operation(document: dict[str, Any]) -> None:
            components = document["dynamic_policy_contract"][
                "position_management_risk_contract"
            ]["total_risk_components"]
            components.remove("PENDING_ORDER_WORST_CASE_LOSS")
            components.remove("FEES_RESERVE")
            components.remove("TAIL_RESERVE")

        self.mutate(GRAPH_PATH, operation)
        self.assert_rejected("E_RISK_MONOTONICITY")

    def test_098_gap_cannot_be_labeled_normal_enter_or_keep(self) -> None:
        self.mutate(
            GRAPH_PATH,
            lambda document: document["dynamic_policy_contract"][
                "gap_contract"
            ].update({"gap_event_may_be_labeled_normal_ENTER_or_KEEP": True}),
        )
        self.assert_rejected("E_REPLAY_CONTRACT")

    def test_099_full_bar_backfill_is_forbidden(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["event_driven_pit_replay_contract"].update(
                {"full_bar_backfill_into_earlier_decision": "ALLOWED"}
            ),
        )
        self.assert_rejected("E_REPLAY_CONTRACT")

    def test_100_future_high_low_mfe_mae_are_not_policy_inputs(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["event_driven_pit_replay_contract"].update(
                {
                    "future_high_low_close_mfe_or_mae_in_policy_information_set": (
                        "ALLOWED"
                    )
                }
            ),
        )
        self.assert_rejected("E_REPLAY_CONTRACT")

    def test_101_favorable_first_same_bar_assumption_is_forbidden(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["event_driven_pit_replay_contract"].update(
                {
                    "same_bar_or_same_timestamp_barrier_order_unknown": (
                        "ASSUME_FAVORABLE_FIRST"
                    )
                }
            ),
        )
        self.assert_rejected("E_REPLAY_CONTRACT")

    def test_102_late_revision_cannot_overwrite_prior_receipt(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["event_driven_pit_replay_contract"].update(
                {"late_source_revision": "OVERWRITE_PRIOR_EVENT"}
            ),
        )
        self.assert_rejected("E_REPLAY_CONTRACT")

    def test_103_unclosed_higher_timeframe_bar_is_not_closed_bar_evidence(
        self,
    ) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["event_driven_pit_replay_contract"].update(
                {"unclosed_higher_timeframe_bar": "ADMIT_AS_CLOSED_BAR"}
            ),
        )
        self.assert_rejected("E_REPLAY_CONTRACT")

    def test_104_baselines_cannot_receive_unequal_information(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["policy_trajectory_evaluation_contract"][
                "comparison_fairness"
            ].update({"same_point_in_time_information": False}),
        )
        self.assert_rejected("E_POLICY_EVALUATION")

    def test_105_no_trade_baseline_is_required(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["policy_trajectory_evaluation_contract"][
                "required_baselines"
            ].pop(),
        )
        self.assert_rejected("E_POLICY_EVALUATION")

    def test_106_dynamic_metric_thresholds_remain_unset(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["policy_trajectory_evaluation_contract"][
                "metric_thresholds"
            ].update({"latency": 0.25}),
        )
        self.assert_rejected("E_POLICY_EVALUATION")

    def test_107_policy_event_denominator_cannot_be_deleted(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["denominator_contract"].update(
                {"all_admitted_events_retained_in_trajectory": False}
            ),
        )
        self.assert_rejected("E_DENOMINATOR")

    def test_108_endpoint_pnl_cannot_hide_risk_breach(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["policy_trajectory_evaluation_contract"].update(
                {"endpoint_pnl_may_rescue_intratrajectory_risk_breach": True}
            ),
        )
        self.assert_rejected("E_POLICY_EVALUATION")

    def test_109_e2_proxy_cannot_be_called_execution_proof(self) -> None:
        self.mutate(
            EVIDENCE_PATH,
            lambda document: document["event_driven_pit_replay_contract"].update(
                {"e2_proxy_or_synthetic_result_is_execution_proof": True}
            ),
        )
        self.assert_rejected("E_REPLAY_CONTRACT")

    def test_110_object_dictionary_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            OBJECT_PATH, rejected_by_v1_1=True
        )

    def test_111_hypothesis_queue_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            HYPOTHESIS_PATH, rejected_by_v1_1=True
        )

    def test_112_measurement_contract_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            MEASUREMENT_PATH, rejected_by_v1_1=True
        )

    def test_113_parameter_registry_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            PARAMETER_PATH, rejected_by_v1_1=True
        )

    def test_114_source_registry_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            SOURCE_PATH, rejected_by_v1_1=True
        )

    def test_115_dispute_registry_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            DISPUTE_PATH, rejected_by_v1_1=True
        )

    def test_116_stage_contract_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            STAGE_PATH, rejected_by_v1_1=True
        )

    def test_117_v1_1_overlay_byte_drift_is_rejected(self) -> None:
        self.assert_frozen_predecessor_byte_drift(
            OVERLAY_PATH, rejected_by_v1_1=False
        )

    def test_118_missing_predecessor_document_is_outer_file_set_error(self) -> None:
        self.bundle.pop(OBJECT_PATH)
        result = self.assert_rejected("E_FILE_SET")
        self.assertEqual(OBJECT_PATH, result["details"]["missing"])

    def test_119_extra_document_is_outer_file_set_error(self) -> None:
        extra_path = (
            "config/sol_decision."
            "research-system-dynamic-hypothesis-graph-p0_1-route.v1.json"
        )
        self.bundle[extra_path] = "{}"
        result = self.assert_rejected("E_FILE_SET")
        self.assertEqual(extra_path, result["details"]["extra"])

    def test_120_v1_1_reason_and_nested_v1_reason_are_wrapped(self) -> None:
        self.bundle[OBJECT_PATH] = "{"
        result = self.assert_rejected("E_V1_1_PREDECESSOR")
        self.assertEqual("REJECTED", result["details"]["v1_1_status"])
        self.assertEqual(
            "E_V1_BASE_CONTRACT",
            result["details"]["v1_1_reason_code"],
        )
        self.assertEqual(
            "E_JSON_MALFORMED",
            result["details"]["v1_1_v1_reason_code"],
        )

    def test_121_v1_1_accepted_result_must_have_exact_bundle_digest(self) -> None:
        forged_result = {
            "status": "ACCEPTED",
            "reason_code": "OK",
            "details": {"document_count": 8},
            "bundle_digest": "0" * 64,
        }
        with patch(
            "trade_system.research_system_contract_v1_2._validate_v1_1_bundle",
            return_value=forged_result,
        ):
            result = self.assert_rejected("E_V1_1_BUNDLE")
        self.assertEqual(
            EXPECTED_PREDECESSOR_BUNDLE_DIGEST,
            result["details"]["expected_bundle_digest"],
        )
        self.assertEqual("0" * 64, result["details"]["observed_bundle_digest"])

    def test_122_predecessor_validation_precedes_v1_2_contract_parse(self) -> None:
        self.bundle[OBJECT_PATH] += "\n"
        self.bundle[GRAPH_PATH] = "{"
        result = self.assert_rejected("E_V1_1_PREDECESSOR")
        self.assertEqual(
            "E_PREDECESSOR_BYTES",
            result["details"]["v1_1_reason_code"],
        )


if __name__ == "__main__":
    unittest.main()
