from __future__ import annotations

import copy
import hashlib
import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from trade_system.research_system_contract_v1_1 import (
    validate_research_system_bundle_v1_1,
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
PATHS = (
    OBJECT_PATH,
    HYPOTHESIS_PATH,
    MEASUREMENT_PATH,
    PARAMETER_PATH,
    SOURCE_PATH,
    DISPUTE_PATH,
    STAGE_PATH,
    OVERLAY_PATH,
)
V1_DIGEST_FIELDS = {
    OBJECT_PATH: "registry_sha256",
    HYPOTHESIS_PATH: "registry_sha256",
    MEASUREMENT_PATH: "registry_sha256",
    PARAMETER_PATH: "registry_sha256",
    SOURCE_PATH: "registry_sha256",
    DISPUTE_PATH: "registry_sha256",
    STAGE_PATH: "contract_sha256",
}


def read_actual_successor_bundle() -> dict[str, str]:
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in PATHS}


def parse_document(bundle: dict[str, str], path: str) -> dict[str, Any]:
    return json.loads(bundle[path])


def independently_resign_v1_document(document: dict[str, Any], path: str) -> str:
    digest_field = V1_DIGEST_FIELDS[path]
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


def independently_resign_overlay(document: dict[str, Any]) -> str:
    unsigned = copy.deepcopy(document)
    unsigned.pop("overlay_sha256", None)
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
    document["overlay_sha256"] = hashlib.sha256(
        domain + separator + canonical
    ).hexdigest()
    return json.dumps(document, ensure_ascii=True, indent=2) + "\n"


class ExplodingMapping(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise RuntimeError("mapping exploded")

    def __iter__(self):
        raise RuntimeError("mapping exploded")

    def __len__(self) -> int:
        raise RuntimeError("mapping exploded")


class ResearchSystemContractV11Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = read_actual_successor_bundle()

    def replace_resigned_v1(self, path: str, document: dict[str, Any]) -> None:
        self.bundle[path] = independently_resign_v1_document(document, path)

    def replace_resigned_overlay(self, document: dict[str, Any]) -> None:
        self.bundle[OVERLAY_PATH] = independently_resign_overlay(document)

    def assert_rejected(self, reason_code: str) -> dict[str, Any]:
        result = validate_research_system_bundle_v1_1(self.bundle)
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual(reason_code, result["reason_code"])
        self.assertIsNone(result["bundle_digest"])
        self.assertEqual(
            {"status", "reason_code", "details", "bundle_digest"}, set(result)
        )
        return result

    def test_001_clean_successor_is_accepted(self) -> None:
        result = validate_research_system_bundle_v1_1(self.bundle)
        self.assertEqual("ACCEPTED", result["status"])
        self.assertEqual("OK", result["reason_code"])
        self.assertEqual(8, result["details"]["document_count"])
        self.assertRegex(result["bundle_digest"], r"^[0-9a-f]{64}$")

    def test_002_clean_successor_digest_is_mapping_order_independent(self) -> None:
        first = validate_research_system_bundle_v1_1(self.bundle)
        second = validate_research_system_bundle_v1_1(
            dict(reversed(list(self.bundle.items())))
        )
        self.assertEqual("ACCEPTED", second["status"])
        self.assertEqual(first["bundle_digest"], second["bundle_digest"])

    def test_003_sol_a01_hypothesis_e5_is_rejected(self) -> None:
        doc = parse_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"][0]["evidence_level"] = "E5_LIVE_VALIDATED"
        self.replace_resigned_v1(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_004_sol_a02_claim_e5_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OBJECT_PATH)
        doc["claims"][0]["evidence_status"] = "E5_MARKET_CONFIRMED"
        self.replace_resigned_v1(OBJECT_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_005_sol_a03_source_verified_is_rejected(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        source = doc["sources"][0]
        source["integrity_status"] = "VERIFIED"
        source["coverage_status"] = "VERIFIED_COMPLETE"
        source["revision_status"] = "VERIFIED_VERSIONED"
        source["pit_status"] = "VERIFIED_AVAILABLE_AT"
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_006_sol_a04_live_source_usage_is_rejected(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["replacement_or_usage_status"] = (
            "ADMITTED_FOR_LIVE_TRADING"
        )
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_007_case_variant_is_rejected_with_stable_boundary_code(self) -> None:
        doc = parse_document(self.bundle, OBJECT_PATH)
        doc["claims"][0]["evidence_status"] = "confirmed_constraint"
        self.replace_resigned_v1(OBJECT_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_008_unicode_variant_is_rejected_with_stable_boundary_code(self) -> None:
        doc = parse_document(self.bundle, HYPOTHESIS_PATH)
        doc["hypotheses"][0]["evidence_level"] = "Ｅ０＿ＵＮＴＥＳＴＥＤ"
        self.replace_resigned_v1(HYPOTHESIS_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_009_separator_variant_is_rejected_with_stable_boundary_code(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["replacement_or_usage_status"] = (
            "DISCOVERED-NOT-ACQUIRED-NOT-ADMITTED"
        )
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_010_wording_equivalent_is_rejected_with_stable_boundary_code(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["replacement_or_usage_status"] = (
            "DISCOVERED AND NOT ACQUIRED AND NOT ADMITTED"
        )
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_011_lowercase_source_integrity_maps_to_boundary_code(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["integrity_status"] = "document_identity_discovered"
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_012_other_valid_v1_coverage_is_still_too_strong(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["coverage_status"] = "VERIFIED_PARTIAL"
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_013_other_valid_v1_revision_is_still_too_strong(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["revision_status"] = "VERIFIED_NON_REVISING"
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_014_other_valid_v1_pit_is_still_too_strong(self) -> None:
        doc = parse_document(self.bundle, SOURCE_PATH)
        doc["sources"][0]["pit_status"] = "VERIFIED_AVAILABLE_AT"
        self.replace_resigned_v1(SOURCE_PATH, doc)
        self.assert_rejected("E_NESTED_CLAIM_BOUNDARY")

    def test_015_overlay_duplicate_top_key_is_rejected(self) -> None:
        raw = self.bundle[OVERLAY_PATH]
        replacement = '"overlay_id": "DUPLICATE",\n  "overlay_id": '
        self.bundle[OVERLAY_PATH] = raw.replace('"overlay_id": ', replacement, 1)
        self.assert_rejected("E_JSON_DUPLICATE_KEY")

    def test_016_overlay_duplicate_nested_key_is_rejected(self) -> None:
        raw = self.bundle[OVERLAY_PATH]
        replacement = '"decision_id": "DUPLICATE",\n      "decision_id": '
        self.bundle[OVERLAY_PATH] = raw.replace('"decision_id": ', replacement, 1)
        self.assert_rejected("E_JSON_DUPLICATE_KEY")

    def test_017_overlay_nan_is_rejected(self) -> None:
        raw = self.bundle[OVERLAY_PATH]
        self.bundle[OVERLAY_PATH] = raw.replace(
            '"artifact_count": 21', '"artifact_count": NaN', 1
        )
        self.assert_rejected("E_JSON_NONFINITE")

    def test_018_overlay_infinity_is_rejected(self) -> None:
        raw = self.bundle[OVERLAY_PATH]
        self.bundle[OVERLAY_PATH] = raw.replace(
            '"artifact_count": 21', '"artifact_count": Infinity', 1
        )
        self.assert_rejected("E_JSON_NONFINITE")

    def test_019_overlay_unknown_top_field_is_rejected_after_resign(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["candidate_authorization"] = "ALLOW"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_UNKNOWN_FIELD")

    def test_020_overlay_unknown_nested_field_is_rejected_after_resign(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["failed_p0_gate_decision"]["candidate"] = "ALLOW"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_UNKNOWN_FIELD")

    def test_021_overlay_digest_syntax_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["overlay_sha256"] = "g" * 64
        self.bundle[OVERLAY_PATH] = json.dumps(doc)
        self.assert_rejected("E_SHA256")

    def test_022_overlay_stale_digest_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["created_at"] = "2026-07-27T09:17:44Z"
        self.bundle[OVERLAY_PATH] = json.dumps(doc)
        self.assert_rejected("E_SELF_DIGEST")

    def test_023_initial_sol_physical_hash_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["initial_sol_decision"]["physical_sha256"] = "0" * 64
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_024_initial_sol_canonical_hash_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["initial_sol_decision"]["canonical_sha256"] = "0" * 64
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_025_failed_gate_physical_hash_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["failed_p0_gate_decision"]["physical_sha256"] = "0" * 64
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_026_failed_gate_canonical_hash_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["failed_p0_gate_decision"]["canonical_sha256"] = "0" * 64
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_027_failed_gate_state_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["failed_p0_gate_decision"]["decision_state"] = "PASS"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_028_inventory_physical_hash_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["frozen_p0_inventory"]["physical_sha256"] = "0" * 64
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_029_inventory_canonical_hash_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["frozen_p0_inventory"]["canonical_sha256"] = "0" * 64
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_030_inventory_artifact_count_bool_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["frozen_p0_inventory"]["artifact_count"] = True
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_FIELD_TYPE")

    def test_031_predecessor_bundle_self_rebind_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["authority_binding"]["predecessor_bundle"]["bundle_digest"] = "0" * 64
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_032_candidate_cannot_broaden_trusted_vocab(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["trusted_semantic_ceilings"]["hypothesis_evidence_level"].append(
            "E5_LIVE_VALIDATED"
        )
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_033_candidate_cannot_reorder_trusted_vocab(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        values = doc["trusted_semantic_ceilings"]["source_coverage_status"]
        values[0], values[1] = values[1], values[0]
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_AUTHORITY_BINDING")

    def test_034_d0_denial_is_fixed(self) -> None:
        self._assert_stage_denial_fixed("D0")

    def test_035_d1_denial_is_fixed(self) -> None:
        self._assert_stage_denial_fixed("D1")

    def test_036_d2_denial_is_fixed(self) -> None:
        self._assert_stage_denial_fixed("D2")

    def test_037_d3_denial_is_fixed(self) -> None:
        self._assert_stage_denial_fixed("D3")

    def test_038_e2_denial_is_fixed(self) -> None:
        self._assert_stage_denial_fixed("E2")

    def test_039_e3_denial_is_fixed(self) -> None:
        self._assert_stage_denial_fixed("E3")

    def _assert_stage_denial_fixed(self, gate_id: str) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["stage_denials"][gate_id] = "AUTHORIZED"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_STAGE_DENIAL")

    def test_040_clean_result_reports_all_denials_unchanged(self) -> None:
        result = validate_research_system_bundle_v1_1(self.bundle)
        self.assertEqual(
            {
                "D0": "DENIED",
                "D1": "DENIED",
                "D2": "DENIED",
                "D3": "DENIED",
                "E2": "DENIED",
                "E3": "DENIED",
            },
            result["details"]["stage_denials"],
        )

    def test_041_backtest_claim_boundary_cannot_be_authorized(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["claim_boundary"]["backtest"] = "AUTHORIZED"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_STAGE_DENIAL")

    def test_042_trading_claim_boundary_cannot_be_authorized(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["claim_boundary"]["trading"] = "AUTHORIZED"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_STAGE_DENIAL")

    def test_043_overlay_non_utc_clock_is_rejected(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["created_at"] = "2026-07-27T17:17:43+08:00"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_CLOCK")

    def test_044_overlay_canonical_formula_is_fixed(self) -> None:
        doc = parse_document(self.bundle, OVERLAY_PATH)
        doc["canonicalization"]["formula"] = "SHA256(canonical_json_utf8)"
        self.replace_resigned_overlay(doc)
        self.assert_rejected("E_CANONICALIZATION")

    def test_045_missing_overlay_is_rejected(self) -> None:
        self.bundle.pop(OVERLAY_PATH)
        self.assert_rejected("E_FILE_SET")

    def test_046_extra_file_is_rejected(self) -> None:
        self.bundle["config/research_system.successor_extra.json"] = "{}"
        self.assert_rejected("E_FILE_SET")

    def test_047_non_string_overlay_is_rejected(self) -> None:
        self.bundle[OVERLAY_PATH] = b"{}"  # type: ignore[assignment]
        self.assert_rejected("E_RAW_TYPE")

    def test_048_malformed_predecessor_is_v1_base_rejection(self) -> None:
        self.bundle[OBJECT_PATH] = "{"
        self.assert_rejected("E_V1_BASE_CONTRACT")

    def test_049_clean_semantics_but_changed_predecessor_bytes_are_rejected(self) -> None:
        self.bundle[OBJECT_PATH] = self.bundle[OBJECT_PATH] + "\n"
        self.assert_rejected("E_PREDECESSOR_BYTES")

    def test_050_none_input_is_total(self) -> None:
        result = validate_research_system_bundle_v1_1(None)  # type: ignore[arg-type]
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INPUT_TYPE", result["reason_code"])

    def test_051_list_input_is_total(self) -> None:
        result = validate_research_system_bundle_v1_1([])  # type: ignore[arg-type]
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INPUT_TYPE", result["reason_code"])

    def test_052_exploding_mapping_is_total_and_fail_closed(self) -> None:
        result = validate_research_system_bundle_v1_1(ExplodingMapping())
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual("E_INTERNAL_TOTALITY", result["reason_code"])
        self.assertEqual({"error_type": "RuntimeError"}, result["details"])


if __name__ == "__main__":
    unittest.main()
