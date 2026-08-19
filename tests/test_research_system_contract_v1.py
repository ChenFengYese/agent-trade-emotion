from __future__ import annotations

import copy
import hashlib
import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from trade_system.research_system_contract_v1 import validate_research_system_bundle


ROOT = Path(__file__).resolve().parents[1]
OBJECT_PATH = "config/research_system.object_dictionary.v1.json"
HYPOTHESIS_PATH = "config/research_system.hypothesis_validation_queue.v1.json"
MEASUREMENT_PATH = "config/research_system.measurement_contract.v1.json"
PARAMETER_PATH = "config/research_system.parameter_registry.v1.json"
SOURCE_PATH = "config/research_system.source_authority_registry.v1.json"
DISPUTE_PATH = "config/research_system.dispute_registry.v1.json"
STAGE_PATH = "config/research_system.stage_contract.v1.json"
PATHS = (
    OBJECT_PATH,
    HYPOTHESIS_PATH,
    MEASUREMENT_PATH,
    PARAMETER_PATH,
    SOURCE_PATH,
    DISPUTE_PATH,
    STAGE_PATH,
)
DIGEST_FIELDS = {
    OBJECT_PATH: "registry_sha256",
    HYPOTHESIS_PATH: "registry_sha256",
    MEASUREMENT_PATH: "registry_sha256",
    PARAMETER_PATH: "registry_sha256",
    SOURCE_PATH: "registry_sha256",
    DISPUTE_PATH: "registry_sha256",
    STAGE_PATH: "contract_sha256",
}


def read_actual_raw_bundle() -> dict[str, str]:
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in PATHS}


def parse_actual_document(bundle: dict[str, str], path: str) -> dict[str, Any]:
    return json.loads(bundle[path])


def independently_resign(document: dict[str, Any], path: str) -> str:
    digest_field = DIGEST_FIELDS[path]
    unsigned = copy.deepcopy(document)
    unsigned.pop(digest_field, None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    canonicalization = document["canonicalization"]
    domain = canonicalization["domain_prefix_utf8"].encode("utf-8")
    separator = bytes.fromhex(canonicalization["domain_separator_hex"])
    document[digest_field] = hashlib.sha256(domain + separator + canonical).hexdigest()
    return json.dumps(document, ensure_ascii=True, indent=2) + "\n"


class ExplodingMapping(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise RuntimeError("caller mapping exploded")

    def __iter__(self):
        raise RuntimeError("caller mapping exploded")

    def __len__(self) -> int:
        raise RuntimeError("caller mapping exploded")


class ResearchSystemContractV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = read_actual_raw_bundle()

    def replace_resigned(self, path: str, document: dict[str, Any]) -> None:
        self.bundle[path] = independently_resign(document, path)

    def assert_rejected(self, reason_code: str) -> dict[str, Any]:
        result = validate_research_system_bundle(self.bundle)
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual(reason_code, result["reason_code"])
        self.assertIsNone(result["bundle_digest"])
        self.assertEqual(
            {"status", "reason_code", "details", "bundle_digest"}, set(result)
        )
        return result

    def test_001_actual_bundle_is_accepted(self) -> None:
        result = validate_research_system_bundle(self.bundle)
        self.assertEqual("ACCEPTED", result["status"])
        self.assertEqual("OK", result["reason_code"])
        self.assertRegex(result["bundle_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(7, result["details"]["document_count"])

    def test_002_bundle_digest_is_mapping_order_independent(self) -> None:
        first = validate_research_system_bundle(self.bundle)
        reversed_bundle = dict(reversed(list(self.bundle.items())))
        second = validate_research_system_bundle(reversed_bundle)
        self.assertEqual("ACCEPTED", second["status"])
        self.assertEqual(first["bundle_digest"], second["bundle_digest"])

    def test_003_missing_file_is_rejected(self) -> None:
        self.bundle.pop(OBJECT_PATH)
        self.assert_rejected("E_FILE_SET")

    def test_004_extra_file_is_rejected(self) -> None:
        self.bundle["config/research_system.extra.v1.json"] = "{}"
        self.assert_rejected("E_FILE_SET")

    def test_005_non_string_raw_value_is_rejected(self) -> None:
        self.bundle[OBJECT_PATH] = b"{}"  # type: ignore[assignment]
        self.assert_rejected("E_RAW_TYPE")

    def test_006_none_input_is_total_and_rejected(self) -> None:
        result = validate_research_system_bundle(None)  # type: ignore[arg-type]
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INPUT_TYPE", result["reason_code"])

    def test_007_list_input_is_total_and_rejected(self) -> None:
        result = validate_research_system_bundle([])  # type: ignore[arg-type]
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INPUT_TYPE", result["reason_code"])

    def test_008_exploding_mapping_is_total_and_fail_closed(self) -> None:
        result = validate_research_system_bundle(ExplodingMapping())
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INTERNAL_TOTALITY", result["reason_code"])
        self.assertEqual({"error_type": "RuntimeError"}, result["details"])

    def test_009_malformed_json_is_rejected(self) -> None:
        self.bundle[OBJECT_PATH] = "{"
        self.assert_rejected("E_JSON_MALFORMED")

    def test_010_top_level_array_is_rejected(self) -> None:
        self.bundle[OBJECT_PATH] = "[]"
        self.assert_rejected("E_TOP_LEVEL_TYPE")

    def test_011_duplicate_top_level_key_is_rejected(self) -> None:
        raw = self.bundle[OBJECT_PATH]
        replacement = '"registry_id": "DUPLICATE",\n  "registry_id": '
        self.bundle[OBJECT_PATH] = raw.replace('"registry_id": ', replacement, 1)
        self.assert_rejected("E_JSON_DUPLICATE_KEY")

    def test_012_duplicate_nested_key_is_rejected(self) -> None:
        raw = self.bundle[OBJECT_PATH]
        replacement = '"decision_id": "DUPLICATE",\n    "decision_id": '
        self.bundle[OBJECT_PATH] = raw.replace('"decision_id": ', replacement, 1)
        self.assert_rejected("E_JSON_DUPLICATE_KEY")

    def test_013_nan_is_rejected(self) -> None:
        raw = self.bundle[HYPOTHESIS_PATH]
        self.bundle[HYPOTHESIS_PATH] = raw.replace('"leading_max": 1', '"leading_max": NaN', 1)
        self.assert_rejected("E_JSON_NONFINITE")

    def test_014_infinity_is_rejected(self) -> None:
        raw = self.bundle[HYPOTHESIS_PATH]
        self.bundle[HYPOTHESIS_PATH] = raw.replace(
            '"leading_max": 1', '"leading_max": Infinity', 1
        )
        self.assert_rejected("E_JSON_NONFINITE")

    def test_015_finite_float_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["active_path_policy"]["leading_max"] = 1.5
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_FIELD_TYPE")

    def test_016_unknown_top_level_field_is_rejected_after_resign(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["candidate_grant"] = "ALLOW"
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_UNKNOWN_FIELD")

    def test_017_unknown_nested_field_is_rejected_after_resign(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"][0]["candidate_grant"] = "ALLOW"
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_UNKNOWN_FIELD")

    def test_018_bool_cannot_replace_integer(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["active_path_policy"]["leading_max"] = True
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_FIELD_TYPE")

    def test_019_integer_cannot_replace_bool(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["permission_matrix"]["backtest"] = 0
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_FIELD_TYPE")

    def test_020_string_cannot_replace_bool(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["object_types"][0]["can_authorize_order"] = "false"
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_FIELD_TYPE")

    def test_021_empty_hypothesis_collection_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"] = []
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_FIELD_EMPTY")

    def test_022_empty_source_collection_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"] = []
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_FIELD_EMPTY")

    def test_023_empty_measurement_observables_are_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["contracts"][0]["observables"] = []
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_FIELD_EMPTY")

    def test_024_empty_object_outputs_are_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["object_types"][0]["required_outputs"] = []
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_FIELD_EMPTY")

    def test_025_non_utc_created_at_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["created_at"] = "2026-07-27T12:00:00+08:00"
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_CLOCK")

    def test_026_invalid_utc_calendar_date_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["accessed_at"] = "2026-02-31T12:00:00Z"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_CLOCK")

    def test_027_bad_digest_sha_syntax_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["registry_sha256"] = "g" * 64
        self.bundle[OBJECT_PATH] = json.dumps(doc)
        self.assert_rejected("E_SHA256")

    def test_028_semantically_stale_self_digest_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["scope_injection"] = "candidate"
        self.bundle[OBJECT_PATH] = json.dumps(doc)
        self.assert_rejected("E_UNKNOWN_FIELD")
        doc.pop("scope_injection")
        doc["created_at"] = "2026-07-27T12:00:00Z"
        self.bundle[OBJECT_PATH] = json.dumps(doc)
        self.assert_rejected("E_SELF_DIGEST")

    def test_029_canonical_domain_mutation_is_rejected_even_if_resigned(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["canonicalization"]["domain"] = "candidate/domain"
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_CANONICALIZATION")

    def test_030_canonical_formula_mutation_is_rejected_even_if_resigned(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["canonicalization"]["formula"] = "SHA256(canonical_json_utf8)"
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_CANONICALIZATION")

    def test_031_canonical_separator_mutation_is_rejected_even_if_resigned(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["canonicalization"]["domain_separator_hex"] = "01"
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_CANONICALIZATION")

    def test_032_common_authority_cannot_self_authorize(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["authority_binding"]["decision_id"] = "CANDIDATE_DECISION"
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_033_authority_hash_cannot_be_candidate_rebound(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["authority_binding"]["decision_physical_sha256"] = "0" * 64
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_034_authorized_head_is_externally_fixed(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["authority_binding"]["head"] = "f" * 40
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_035_stage_decision_state_cannot_self_authorize(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["authority_binding"]["decision_state"] = "CANDIDATE_AUTHORIZED_ALL"
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_STAGE_AUTHORITY")

    def test_036_immutable_baseline_hash_is_externally_fixed(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["immutable_baseline"][0]["physical_sha256"] = "0" * 64
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_IMMUTABLE_BASELINE")

    def test_037_immutable_baseline_order_is_not_authority(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["immutable_baseline"].reverse()
        self.replace_resigned(STAGE_PATH, doc)
        result = validate_research_system_bundle(self.bundle)
        self.assertEqual("ACCEPTED", result["status"])

    def test_038_historical_p1a_baseline_path_is_legal(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        paths = {item["path"] for item in doc["immutable_baseline"]}
        self.assertIn(
            "config/sol_decision.p1a-authority-chain-block.v1.json", paths
        )
        self.assertEqual(
            "ACCEPTED", validate_research_system_bundle(self.bundle)["status"]
        )

    def test_039_data_permission_escalation_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["permission_matrix"]["historical_data_acquisition"] = True
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_PERMISSION_MATRIX")

    def test_040_backtest_permission_escalation_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["permission_matrix"]["backtest"] = True
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_PERMISSION_MATRIX")

    def test_041_paper_permission_escalation_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["permission_matrix"]["paper_or_testnet"] = True
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_PERMISSION_MATRIX")

    def test_042_live_permission_escalation_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["permission_matrix"]["live_or_trading"] = True
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_PERMISSION_MATRIX")

    def test_043_future_gate_opening_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        gate = next(item for item in doc["gates"] if item["gate_id"] == "E2")
        gate["status"] = "OPEN"
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")

    def test_044_missing_future_gate_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["gates"] = [item for item in doc["gates"] if item["gate_id"] != "D2"]
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")

    def test_045_role_cannot_accept_own_candidate(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["dynamic_roles"][0]["can_accept_own_candidate"] = True
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_STAGE_AUTHORITY")

    def test_046_claim_boundary_cannot_authorize_backtest(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["claim_boundary"]["backtest"] = "AUTHORIZED"
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_PERMISSION_MATRIX")

    def test_047_other_path_cannot_be_removed(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["active_path_policy"]["required_residual_paths"] = ["UNKNOWN_PATH"]
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_RESIDUAL_PATH_POLICY")

    def test_048_abstain_cannot_be_registered_as_path(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["active_path_policy"]["required_residual_paths"] = [
            "OTHER_PATH",
            "UNKNOWN_PATH",
            "ABSTAIN",
        ]
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_RESIDUAL_PATH_POLICY")

    def test_049_abstain_action_semantics_cannot_be_reversed(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["active_path_policy"]["abstain_is_action_not_path"] = False
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_RESIDUAL_PATH_POLICY")

    def test_050_active_g1_alias_in_candidate_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["source_id"] = "SRC-CANDIDATE-ACTIVE_G1"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_ALIAS")

    def test_051_repeated_percent_decoded_p1a_alias_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["source_id"] = "SRC-%2550%2531%2541-CANDIDATE"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_ALIAS")

    def test_052_unicode_application_support_alias_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["source_id"] = "ＳＲＣ-Ａｐｐｌｉｃａｔｉｏｎ　Ｓｕｐｐｏｒｔ"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_ALIAS")

    def test_053_unknown_hypothesis_claim_reference_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"][0]["source_claim_ids"][0] = "CLM-NOT-DECLARED"
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_CROSS_CLAIM")

    def test_054_unknown_source_claim_reference_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["claim_ids_supported"][0] = "CLM-NOT-DECLARED"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_CROSS_CLAIM")

    def test_055_unknown_dispute_claim_reference_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, DISPUTE_PATH)
        doc["disputes"][0]["affected_claim_ids"][0] = "CLM-NOT-DECLARED"
        self.replace_resigned(DISPUTE_PATH, doc)
        self.assert_rejected("E_CROSS_CLAIM")

    def test_056_unknown_dispute_hypothesis_reference_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, DISPUTE_PATH)
        doc["disputes"][0]["affected_hypothesis_ids"][0] = "H-NOT-DECLARED"
        self.replace_resigned(DISPUTE_PATH, doc)
        self.assert_rejected("E_CROSS_HYPOTHESIS")

    def test_057_missing_measurement_contract_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["contracts"].pop()
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_MEASUREMENT_BINDING")

    def test_058_unknown_measurement_hypothesis_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["contracts"][0]["hypothesis_id"] = "H-NOT-DECLARED"
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_MEASUREMENT_BINDING")

    def test_059_wrong_hypothesis_measurement_binding_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"][0]["measurement_contract_id"] = "MC-NOT-DECLARED"
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_MEASUREMENT_BINDING")

    def test_060_unknown_parameter_reference_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["contracts"][0]["sensitivity_parameter_ids"].append("PAR-NOT-DECLARED")
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_PARAMETER_REF")

    def test_061_duplicate_claim_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, OBJECT_PATH)
        doc["claims"][1]["claim_id"] = doc["claims"][0]["claim_id"]
        self.replace_resigned(OBJECT_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_062_duplicate_hypothesis_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"][1]["hypothesis_id"] = doc["hypotheses"][0]["hypothesis_id"]
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_063_duplicate_measurement_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["contracts"][1]["measurement_contract_id"] = doc["contracts"][0][
            "measurement_contract_id"
        ]
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_064_duplicate_parameter_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, PARAMETER_PATH)
        doc["parameters"][1]["parameter_id"] = doc["parameters"][0]["parameter_id"]
        self.replace_resigned(PARAMETER_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_065_duplicate_source_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][1]["source_id"] = doc["sources"][0]["source_id"]
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_066_duplicate_dispute_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, DISPUTE_PATH)
        doc["disputes"][1]["dispute_id"] = doc["disputes"][0]["dispute_id"]
        self.replace_resigned(DISPUTE_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_067_invalid_hypothesis_lifecycle_state_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"][0]["current_state"] = "CANDIDATE_AUTHORIZED"
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_LIFECYCLE")

    def test_068_lifecycle_declaration_cannot_be_narrowed(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        doc["lifecycle_states"].remove("ARCHIVED")
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_LIFECYCLE")

    def test_069_invalid_measurement_status_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["contracts"][0]["status"] = "EXECUTABLE"
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_STATUS")

    def test_070_invalid_parameter_status_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, PARAMETER_PATH)
        doc["parameters"][0]["current_status"] = "CALIBRATED"
        self.replace_resigned(PARAMETER_PATH, doc)
        self.assert_rejected("E_STATUS")

    def test_071_undeclared_parameter_source_type_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, PARAMETER_PATH)
        doc["parameters"][0]["source_type"] = "CANDIDATE_SOURCE"
        self.replace_resigned(PARAMETER_PATH, doc)
        self.assert_rejected("E_STATUS")

    def test_072_parameter_enum_declaration_cannot_drop_theory_constraint(self) -> None:
        doc = parse_actual_document(self.bundle, PARAMETER_PATH)
        doc["source_types"].remove("THEORY_CONSTRAINT")
        self.replace_resigned(PARAMETER_PATH, doc)
        self.assert_rejected("E_STATUS")

    def test_073_invalid_source_status_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["pit_status"] = "LOOKAHEAD_ALLOWED"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_STATUS")

    def test_074_invalid_dispute_status_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, DISPUTE_PATH)
        doc["disputes"][0]["status"] = "CANDIDATE_RESOLVED"
        self.replace_resigned(DISPUTE_PATH, doc)
        self.assert_rejected("E_STATUS")

    def test_075_archived_hypothesis_cannot_erase_result_history(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        hypothesis = next(
            item for item in doc["hypotheses"] if item["current_state"] == "ARCHIVED"
        )
        hypothesis["result_history"] = []
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_RESULT_HISTORY")

    def test_076_result_history_must_remain_immutable(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        hypothesis = next(item for item in doc["hypotheses"] if item["result_history"])
        hypothesis["result_history"][0]["immutable"] = False
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_RESULT_HISTORY")

    def test_077_result_history_unknown_field_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        hypothesis = next(item for item in doc["hypotheses"] if item["result_history"])
        hypothesis["result_history"][0]["candidate_note"] = "rewrite"
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_UNKNOWN_FIELD")

    def test_078_duplicate_result_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, HYPOTHESIS_PATH)
        history_rows = [
            row
            for hypothesis in doc["hypotheses"]
            for row in hypothesis["result_history"]
        ]
        self.assertGreaterEqual(len(history_rows), 2)
        history_rows[1]["result_id"] = history_rows[0]["result_id"]
        self.replace_resigned(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_079_bad_optional_local_content_digest_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["content_digest_if_locally_preserved"] = "not-a-sha"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_SHA256")

    def test_080_duplicate_dynamic_role_id_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["dynamic_roles"][1]["role_id"] = doc["dynamic_roles"][0]["role_id"]
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_ID_DUPLICATE")

    def test_081_parameter_reference_in_rule_text_must_exist(self) -> None:
        doc = parse_actual_document(self.bundle, MEASUREMENT_PATH)
        doc["global_rules"]["ordinal_aggregation"] += " PAR-NOT-DECLARED"
        self.replace_resigned(MEASUREMENT_PATH, doc)
        self.assert_rejected("E_PARAMETER_REF")

    def test_082_nine_layer_percent_encoded_alias_is_rejected(self) -> None:
        encoded = "%50%31%41"
        for _ in range(8):
            encoded = encoded.replace("%", "%25")
        doc = parse_actual_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["source_id"] = f"SRC-{encoded}-CANDIDATE"
        self.replace_resigned(SOURCE_PATH, doc)
        self.assert_rejected("E_ALIAS")

    def test_083_gate_prerequisite_rewrite_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        gate = next(item for item in doc["gates"] if item["gate_id"] == "D0")
        gate["prerequisites"][0] = "CANDIDATE_REWRITTEN_PREREQUISITE"
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")

    def test_084_gate_deliverable_rewrite_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        gate = next(item for item in doc["gates"] if item["gate_id"] == "D1")
        gate["deliverables"][0] = "CANDIDATE_REWRITTEN_DELIVERABLE"
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")

    def test_085_gate_prerequisite_order_is_fixed(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        gate = next(item for item in doc["gates"] if item["gate_id"] == "D2")
        gate["prerequisites"][0], gate["prerequisites"][1] = (
            gate["prerequisites"][1],
            gate["prerequisites"][0],
        )
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")

    def test_086_gate_deliverable_order_is_fixed(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        gate = next(item for item in doc["gates"] if item["gate_id"] == "RSR-P0")
        gate["deliverables"][0], gate["deliverables"][1] = (
            gate["deliverables"][1],
            gate["deliverables"][0],
        )
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")

    def test_087_gate_self_cycle_is_rejected(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        gate = next(item for item in doc["gates"] if item["gate_id"] == "D3")
        gate["prerequisites"].append("D3")
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")

    def test_088_gate_list_order_is_fixed(self) -> None:
        doc = parse_actual_document(self.bundle, STAGE_PATH)
        doc["gates"][1], doc["gates"][2] = doc["gates"][2], doc["gates"][1]
        self.replace_resigned(STAGE_PATH, doc)
        self.assert_rejected("E_GATE_STATUS")


if __name__ == "__main__":
    unittest.main()
