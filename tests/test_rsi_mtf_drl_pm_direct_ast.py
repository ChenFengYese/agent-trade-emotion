from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trade_system.rsi_mtf_drl_pm_direct_ast import (
    ASTReject,
    LITERAL_REGISTRY,
    canonical_json,
    identity,
    load_slice,
    validate_authority_files,
    validate_slice_a,
)


def registry_node() -> dict:
    return {
        "node_version": "rsi-mtf-drl-pm.direct-node.v0.2.2",
        "node_id": LITERAL_REGISTRY,
        "node_kind": "CONST",
        "requires": [],
        "body": {"members": {"SYNTHETIC": {"type": "STRING", "value": "SYNTHETIC"}}},
    }


def type_node(node_id: str) -> dict:
    return {
        "node_version": "rsi-mtf-drl-pm.direct-node.v0.2.2",
        "node_id": node_id,
        "node_kind": "TYPE",
        "requires": [],
        "body": {"type_expr": ["T_PRIMITIVE", "STRING"]},
    }


class DirectASTConformanceTests(unittest.TestCase):
    def test_exact_profile_and_semantic_authority_bytes(self) -> None:
        validate_authority_files(Path(__file__).resolve().parents[1])

    def test_canonical_bytes_and_identity_are_deterministic(self) -> None:
        payload = {"a": [1, True], "b": "ASCII"}
        self.assertEqual(canonical_json(payload), b'{"a":[1,true],"b":"ASCII"}')
        self.assertEqual(identity("test/v1", payload), hashlib.sha256(b'test/v1\0{"a":[1,true],"b":"ASCII"}').hexdigest())

    def test_slice_positive_and_digest(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "type/Label": type_node("type/Label")}
        result = validate_slice_a(nodes, set(nodes))
        self.assertEqual(set(result), set(nodes))
        self.assertEqual(result["type/Label"]["outbound_refs"], [])

    def test_free_string_and_raw_id_are_rejected(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "type/Label": type_node("type/Label")}
        nodes[LITERAL_REGISTRY]["body"]["members"]["BAD"] = {"type": "STRING", "value": "schema/Free.v0.2.2"}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))
        nodes = {LITERAL_REGISTRY: registry_node(), "type/Label": type_node("type/Label")}
        nodes["type/Label"]["body"] = {"type_expr": ["T_CONSTRAINED", ["T_PRIMITIVE", "STRING"], [["ID", "forbidden", ["GET", "$self", []]]]]}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))

    def test_prefix_kind_placeholder_and_constref_are_rejected(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "type/Label": type_node("type/Label")}
        bad = copy.deepcopy(nodes)
        bad["type/Label"]["node_kind"] = "SCHEMA"
        with self.assertRaises(ASTReject):
            validate_slice_a(bad, set(bad))
        bad = copy.deepcopy(nodes)
        bad["type/Label"]["body"] = {"type_expr": ["T_PRIMITIVE", "STRING"], "source_pointer": "x"}
        with self.assertRaises(ASTReject):
            validate_slice_a(bad, set(bad))
        bad = copy.deepcopy(nodes)
        bad["type/Label"]["body"] = {"type_expr": ["T_CONST_REF", ["CONST_REF", LITERAL_REGISTRY, "MISSING"]]}
        bad["type/Label"]["requires"] = [LITERAL_REGISTRY]
        with self.assertRaises(ASTReject):
            validate_slice_a(bad, set(bad))

    def test_bytes_wire_and_schema_construction_rules_are_rejected(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "type/Label": type_node("type/Label")}
        bad = copy.deepcopy(nodes)
        bad["type/Label"]["body"] = {"type_expr": ["T_PRIMITIVE", "BYTES"]}
        with self.assertRaises(ASTReject):
            validate_slice_a(bad, set(bad))

    def test_new_decimal_and_market_union_grammar_is_enforced(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "type/DecimalString": type_node("type/DecimalString")}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))
        nodes = {LITERAL_REGISTRY: registry_node(), "schema/Bad": {
            "node_version": "rsi-mtf-drl-pm.direct-node.v0.2.2", "node_id": "schema/Bad", "node_kind": "SCHEMA", "requires": [],
            "body": {"exact_keys": ["value"], "properties": {"value": ["T_DECIMAL_VALUE", "PRICE"]}, "constraints": []},
        }}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))
        nodes = {LITERAL_REGISTRY: registry_node(), "type/MarketSourceObject": type_node("type/MarketSourceObject")}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))

    def test_new_decimal_and_match_narrow_shapes_are_rejected(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "type/Label": type_node("type/Label")}
        nodes["type/Label"]["body"] = {"type_expr": ["T_CONSTRAINED", ["T_PRIMITIVE", "STRING"], [["DECIMAL_PARSE", "WRONG", ["GET", "$self", []]]]]}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))
        nodes = {LITERAL_REGISTRY: registry_node(), "algorithm/Narrow": {
            "node_version": "rsi-mtf-drl-pm.direct-node.v0.2.2", "node_id": "algorithm/Narrow", "node_kind": "ALGORITHM", "requires": [],
            "body": {"parameters": {}, "returns": ["T_PRIMITIVE", "BOOLEAN"], "locals": {}, "preconditions": [], "statements": [["MATCH_NARROW", ["GET", "x", []], [{"bind": "x", "type": ["T_PRIMITIVE", "STRING"]}]]], "postconditions": []},
        }}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))
        bad = copy.deepcopy(nodes)
        bad["type/Label"] = {
            "node_version": "rsi-mtf-drl-pm.direct-node.v0.2.2",
            "node_id": "type/Label",
            "node_kind": "SCHEMA",
            "requires": [],
            "body": {"exact_keys": ["z"], "properties": {"a": ["T_PRIMITIVE", "STRING"]}, "constraints": []},
        }
        with self.assertRaises(ASTReject):
            validate_slice_a(bad, set(bad))

    def test_routing_path_requires_nonempty_discriminator(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "routing/Probe": {
            "node_version": "rsi-mtf-drl-pm.direct-node.v0.2.2",
            "node_id": "routing/Probe",
            "node_kind": "ROUTING",
            "requires": [LITERAL_REGISTRY, "schema/Payload"],
            "body": {"input_type": ["T_PRIMITIVE", "ANY_JSON"], "discriminator": [], "discriminator_type": ["T_ENUM", [["CONST_REF", LITERAL_REGISTRY, "SYNTHETIC"]]], "value_path": [["FIELD", "payload"]], "cases": [{"match": ["CONST_REF", LITERAL_REGISTRY, "SYNTHETIC"], "schema_node_id": "schema/Payload"}]},
        }}
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))

    def test_requires_cannot_hide_or_omit_reference(self) -> None:
        nodes = {LITERAL_REGISTRY: registry_node(), "type/Label": type_node("type/Label")}
        nodes["type/Label"]["body"] = {"type_expr": ["T_CONST_REF", ["CONST_REF", LITERAL_REGISTRY, "SYNTHETIC"]]}
        nodes["type/Label"]["requires"] = []
        with self.assertRaises(ASTReject):
            validate_slice_a(nodes, set(nodes))

    def test_load_slice_rejects_noncanonical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slice.json"
            path.write_text('{"nodes": {}}\n', encoding="utf-8")
            with self.assertRaises(ASTReject):
                load_slice(path)


if __name__ == "__main__":
    unittest.main()
