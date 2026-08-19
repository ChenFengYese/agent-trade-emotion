from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import re
import shutil
import tempfile
import unittest
from collections import UserDict
from pathlib import Path
from types import MappingProxyType

from trade_system.rsi_mtf_drl_pm_v0_2_2 import __all__
from trade_system.rsi_mtf_drl_pm_v0_2_2.contract import (
    ContractValidationError,
    JSONValue,
    serialize_contract,
    validate_contract_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json"
DECISION = ROOT / "config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json"
SEMANTIC_SOURCE = ROOT / "archive/authority/RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md"
AUTHORITY_SPEC = ROOT / "archive/authority/RSI_MTF_DRL_PM_AUTHORITY_BUNDLE_SPEC_v0_2_2.md"
CONTRACT_MODULE = ROOT / "trade_system/rsi_mtf_drl_pm_v0_2_2/contract.py"
ARCHIVED_CORE = ROOT / "archive/authority/CORE_TRADING_THEORY_v2_0.rsi-v0_2_2.md"
ARCHIVED_LEGACY_TEST = ROOT / "archive/authority/tests/test_rsi_research_contract.v0_2.py"
ERROR = "E_KERNEL_CONTRACT_INVALID"

_EXPECTED_CONTRACT_IMPORTS = (
    ("from", "__future__", 0, (("annotations", None),)),
    ("import", None, 0, (("hashlib", None),)),
    ("import", None, 0, (("json", None),)),
    ("from", "collections.abc", 0, (("Mapping", None),)),
    ("from", "pathlib", 0, (("Path", None),)),
    ("from", "typing", 0, (("Any", None), ("TypeAlias", None))),
)

_EXPECTED_CONTRACT_CALL_FORMS = frozenset(
    {
        "(workspace_root / _DECISION_PATH).read_bytes",
        "(workspace_root / path).read_bytes",
        "AssertionError",
        "ContractValidationError",
        "_COMPOSITE_DOMAIN.encode",
        "_bad",
        "_canonical_json",
        "_materialize_json",
        "_read_frozen",
        "_require_exact_structure",
        "_sha256",
        "_validate_decision_and_sources",
        "_walk_json",
        "contract.get",
        "contract_bytes.decode",
        "contract_bytes.endswith",
        "contract_bytes.isascii",
        "decision.get",
        "decision.get('successor_route', {}).get",
        "decision_raw.decode",
        "decision_raw.endswith",
        "decision_without_digest.pop",
        "dict",
        "frozen.get",
        "frozen.items",
        "frozen_raw.get",
        "hashlib.sha256",
        "hashlib.sha256(raw).hexdigest",
        "isinstance",
        "item.get",
        "json.dumps",
        "json.dumps(_materialize_json(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode",
        "json.loads",
        "legacy.get",
        "legacy_raw.decode",
        "len",
        "raw.isascii",
        "row.get",
        "semantic.get",
        "serialize_contract",
        "set",
        "source.get",
        "source_authority.get",
        "source_map.items",
        "super",
        "super().__init__",
        "value.items",
    }
)


def _assert_frozen_contract_ast_allowlist(source: str) -> None:
    tree = ast.parse(source)
    imports: list[tuple[str, str | None, int, tuple[tuple[str, str | None], ...]]] = []
    import_nodes = sorted(
        (node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))),
        key=lambda node: (node.lineno, node.col_offset),
    )
    for node in import_nodes:
        if isinstance(node, ast.Import):
            imports.append(("import", None, 0, tuple((alias.name, alias.asname) for alias in node.names)))
        elif isinstance(node, ast.ImportFrom):
            imports.append(("from", node.module, node.level, tuple((alias.name, alias.asname) for alias in node.names)))
    if tuple(imports) != _EXPECTED_CONTRACT_IMPORTS:
        raise AssertionError("contract import allowlist mismatch")
    call_forms = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    if call_forms != _EXPECTED_CONTRACT_CALL_FORMS:
        raise AssertionError("contract call-form allowlist mismatch")


class StrategyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = CONTRACT.read_bytes()
        self.value = json.loads(self.raw)
        self.decision = json.loads(DECISION.read_bytes())

    def expect_reject(self, value: object) -> None:
        with self.assertRaises(ContractValidationError) as caught:
            serialize_contract(value)  # type: ignore[arg-type]
        self.assertEqual(caught.exception.error_code, ERROR)
        self.assertEqual(caught.exception.args, (ERROR,))
        self.assertIsNone(caught.exception.__cause__)

    def clone(self) -> dict[str, JSONValue]:
        return copy.deepcopy(self.value)

    def test_exact_bytes_container_and_public_surface(self) -> None:
        self.assertFalse(self.raw.endswith(b"\n"))
        self.assertTrue(self.raw.isascii())
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), "26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc")
        self.assertEqual(serialize_contract(self.value), self.raw)
        temp, workspace = self._copy_authority_workspace()
        self.addCleanup(temp.cleanup)
        validate_contract_bytes(self.raw, workspace)
        decision_raw = DECISION.read_bytes()
        self.assertFalse(decision_raw.endswith(b"\n"))
        self.assertTrue(decision_raw.isascii())
        self.assertEqual(
            json.dumps(
                self.decision,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8"),
            decision_raw,
        )
        decision_without_digest = copy.deepcopy(self.decision)
        decision_internal = decision_without_digest.pop("decision_sha256")
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    decision_without_digest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest(),
            decision_internal,
        )
        self.assertEqual(
            hashlib.sha256(decision_raw).hexdigest(),
            self.value["route_decision_raw_sha256"],
        )
        spec_raw = AUTHORITY_SPEC.read_bytes()
        spec_authority = self.value["source_authority"]
        spec_frozen = self.decision["frozen_inputs"]["authority_bundle_spec"]
        self.assertEqual(len(spec_raw), spec_authority["authority_bundle_spec_size_bytes"])
        self.assertEqual(len(spec_raw), spec_frozen["size_bytes"])
        self.assertEqual(
            hashlib.sha256(spec_raw).hexdigest(),
            spec_authority["authority_bundle_spec_raw_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(spec_raw).hexdigest(),
            spec_frozen["raw_sha256"],
        )
        self.assertEqual(
            self.decision["successor_route"]["composite_theory_id"],
            self.value["composite_theory_id"],
        )
        self.assertEqual(
            self.decision["reason_codes"][-2:],
            [
                "C05_PUBLIC_G0_SELECTION_BINDING_REQUIRED",
                "C09_BARRIER_EVENT_OWNER_MIGRATED_TO_BUNDLE_VALIDATOR",
            ],
        )
        delta = self.decision["semantic_route_delta"]
        self.assertEqual(
            delta["semantic_section_8_2_selector_bindings"],
            "ROUTE_EXTENDED_G0_SELECTION_BINDING_PROOF_ONLY_ECONOMIC_SEMANTICS_UNCHANGED",
        )
        self.assertEqual(
            delta["semantic_section_9_3_c09_validation_owner"],
            "SEMANTICS_RETAINED_ROUTE_OWNER_BUNDLE_VALIDATOR",
        )
        self.assertEqual(__all__.count("serialize_contract"), 1)
        signature = inspect.signature(serialize_contract)
        self.assertEqual(list(signature.parameters), ["contract"])
        self.assertIn("Mapping", str(signature.parameters["contract"].annotation))
        self.assertEqual(signature.return_annotation, "bytes")
        self.assertTrue(hasattr(JSONValue, "__args__"))

    def test_both_superseded_contract_container_ids_are_explicitly_rejected(self) -> None:
        for old_id in (
            "rsi-mtf-drl-pm-v0-2-outcome-free-contract",
            "rsi-mtf-drl-pm-v0-2-2-outcome-free-contract",
        ):
            with self.subTest(contract_id=old_id):
                candidate = self.clone()
                candidate["contract_id"] = old_id
                self.expect_reject(candidate)

    def test_all_ordinary_boundary_exceptions_use_the_exact_carrier_but_process_exits_propagate(self) -> None:
        class ExplodingIter(dict[str, object]):
            def __iter__(self):
                raise RuntimeError("iter")

        class ExplodingItems(dict[str, object]):
            def items(self):
                raise RuntimeError("items")

        class ExplodingBytes(bytes):
            def endswith(self, suffix, start=0, end=None):
                raise RuntimeError("endswith")

        for mapping in (ExplodingIter(self.value), ExplodingItems(self.value)):
            with self.assertRaises(ContractValidationError) as caught:
                serialize_contract(mapping)  # type: ignore[arg-type]
            self.assertEqual(caught.exception.error_code, ERROR)
            self.assertEqual(caught.exception.args, (ERROR,))
            self.assertIsNone(caught.exception.__cause__)
            self.assertTrue(caught.exception.__suppress_context__)
        with self.assertRaises(ContractValidationError) as caught:
            validate_contract_bytes(ExplodingBytes(self.raw), ROOT)
        self.assertEqual(caught.exception.error_code, ERROR)
        self.assertEqual(caught.exception.args, (ERROR,))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

        class InterruptItems(dict[str, object]):
            def items(self):
                raise KeyboardInterrupt()

        class ExitingBytes(bytes):
            def endswith(self, suffix, start=0, end=None):
                raise SystemExit(7)

        with self.assertRaises(KeyboardInterrupt):
            serialize_contract(InterruptItems(self.value))  # type: ignore[arg-type]
        with self.assertRaises(SystemExit) as caught_exit:
            validate_contract_bytes(ExitingBytes(self.raw), ROOT)
        self.assertEqual(caught_exit.exception.code, 7)

    def test_top_level_and_nested_exact_key_closure(self) -> None:
        for key in list(self.value):
            candidate = self.clone()
            del candidate[key]
            self.expect_reject(candidate)
        candidate = self.clone()
        candidate["unexpected"] = "x"
        self.expect_reject(candidate)
        for path in (("authorization",), ("runtime",), ("canonicalization",), ("chronology",), ("semantic_commitment",), ("synthetic_gate",), ("source_authority",)):
            for key in list(self.value[path[0]]):
                candidate = self.clone()
                del candidate[path[0]][key]
                if candidate != self.value:
                    self.expect_reject(candidate)
            candidate = self.clone()
            candidate[path[0]]["unknown"] = "x"
            self.expect_reject(candidate)

    def test_canonical_utf8_json_and_physical_ascii_constraints(self) -> None:
        reordered = {key: self.value[key] for key in reversed(list(self.value))}
        self.assertEqual(serialize_contract(reordered), self.raw)
        for invalid in (b"{\"x\":1.0}", self.raw + b"\n", self.raw.replace(b'"E0"', b'"E1"', 1), b'{"x":"\xc3\xa9"}'):
            with self.assertRaises(ContractValidationError):
                validate_contract_bytes(invalid, ROOT)
        for value in (1.0, 9007199254740992, -9007199254740992):
            candidate = self.clone()
            candidate["repeat_process_runs"] = value
            self.expect_reject(candidate)

    def test_any_validated_mapping_is_recursively_materialized_for_canonical_bytes(self) -> None:
        self.assertEqual(serialize_contract(MappingProxyType(self.value)), self.raw)
        self.assertEqual(serialize_contract(UserDict(self.value)), self.raw)
        nested = self.clone()
        nested["runtime"] = MappingProxyType(nested["runtime"])
        nested["support_type_registry"][0] = UserDict(nested["support_type_registry"][0])
        self.assertEqual(serialize_contract(MappingProxyType(nested)), self.raw)

    def test_recursive_inputs_fail_closed_with_the_exact_contract_carrier(self) -> None:
        with self.assertRaises(ContractValidationError) as caught:
            validate_contract_bytes(b"[" * 10000 + b"]" * 10000, ROOT)
        self.assertEqual(caught.exception.error_code, ERROR)
        self.assertEqual(caught.exception.args, (ERROR,))
        recursive: dict[str, object] = {}
        recursive["self"] = recursive
        with self.assertRaises(ContractValidationError) as caught:
            serialize_contract(recursive)  # type: ignore[arg-type]
        self.assertEqual(caught.exception.error_code, ERROR)
        self.assertEqual(caught.exception.args, (ERROR,))

    def test_support_type_registry_exact_members_fields_unions_and_codes(self) -> None:
        registry = self.value["support_type_registry"]
        self.assertEqual(len(registry), 11)
        self.assertEqual([row["type_id"] for row in registry], sorted(row["type_id"] for row in registry))
        outer_reordered = self.clone()
        outer_reordered["support_type_registry"].reverse()
        self.expect_reject(outer_reordered)
        for index, row in enumerate(registry):
            for mutation in ("missing", "extra", "duplicate", "field_reorder", "invariant"):
                candidate = self.clone()
                rows = candidate["support_type_registry"]
                if mutation == "missing":
                    del rows[index]
                elif mutation == "extra":
                    rows.append(copy.deepcopy(row))
                elif mutation == "duplicate":
                    rows[index]["type_id"] = rows[0]["type_id"]
                elif mutation == "field_reorder":
                    rows[index]["ordered_fields"] = list(reversed(rows[index]["ordered_fields"]))
                else:
                    rows[index]["invariants"][0] += "_MUTATED"
                if candidate != self.value:
                    self.expect_reject(candidate)
        carrier = next(row for row in registry if row["type_id"] == "AuthorityLineageFileSetCheckResultV0_2_2")
        self.assertEqual([field["name"] for field in carrier["ordered_fields"]], ["schema_version", "status", "closure_id"])
        self.assertEqual(carrier["invariants"], ["C21_MINIMAL_ACYCLIC_PASS", "NO_MANIFEST_GOLDEN_RECEIPT_DIGEST_OR_PROJECTION", "NO_PARTIAL_SUCCESS"])
        union = next(row for row in registry if row["type_id"] == "BundleValidationOutcomeV0_2_2")
        self.assertEqual(union["ordered_fields"], [])
        self.assertEqual(union["invariants"], ["EXACT_UNION_VALIDATED_BUNDLE_OR_BUNDLE_VALIDATION_FAILURE", "NO_OTHER_VARIANT"])
        codes = next(row for row in registry if row["type_id"] == "KernelErrorCodeV0_2_2")["invariants"]
        self.assertEqual(len(codes), 26)
        self.assertEqual(codes[:5], ["E_KERNEL_CONTRACT_INVALID", "E_KERNEL_ARGUMENT_INVALID", "E_KERNEL_SCHEMA_INVALID", "E_KERNEL_DIGEST_INVALID", "E_KERNEL_BINDING_INVALID"])
        self.assertEqual(codes[-1], "E_C21_AUTHORITY_LINEAGE_INVALID")
        self.assertEqual(len(set(codes)), 26)
        bundle_failure = next(row for row in registry if row["type_id"] == "BundleValidationFailureV0_2_2")
        self.assertEqual([field["name"] for field in bundle_failure["ordered_fields"]], ["status", "error_code"])
        candidate = self.clone()
        target = next(row for row in candidate["support_type_registry"] if row["type_id"] == "BundleValidationFailureV0_2_2")
        target["invariants"].remove("BUNDLE_ERROR_SUBSET_ONLY")
        self.expect_reject(candidate)
        bundle_success = next(row for row in registry if row["type_id"] == "ValidatedBundleV0_2_2")
        self.assertEqual([field["name"] for field in bundle_success["ordered_fields"]], ["status", "bundle", "bundle_sha256", "validated_as_of_us", "role"])
        candidate = self.clone()
        target = next(row for row in candidate["support_type_registry"] if row["type_id"] == "KernelErrorCodeV0_2_2")
        target["invariants"][0], target["invariants"][1] = target["invariants"][1], target["invariants"][0]
        self.expect_reject(candidate)
        for derived_field in ("manifest_sha256", "golden_suite_sha256", "receipt_sha256"):
            candidate = self.clone()
            target = next(row for row in candidate["support_type_registry"] if row["type_id"] == "AuthorityLineageFileSetCheckResultV0_2_2")
            target["ordered_fields"].append({"name": derived_field, "type_id": "Sha256"})
            self.expect_reject(candidate)

    def test_algorithm_registry_closed_and_authority_refs_are_real(self) -> None:
        registry = self.value["algorithm_interface_registry"]
        self.assertEqual(len(registry), 13)
        self.assertEqual([row["algorithm_id"] for row in registry], sorted(row["algorithm_id"] for row in registry))
        source_line_count = len(SEMANTIC_SOURCE.read_text(encoding="utf-8").splitlines())
        for index, row in enumerate(registry):
            self.assertEqual(set(row), {"algorithm_id", "parameters", "returns", "status_semantics", "owner_entrypoint_id", "authority_ref"})
            self.assertTrue(row["parameters"])
            self.assertTrue(row["authority_ref"])
            for ref in row["authority_ref"]:
                match = re.fullmatch(r"(RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2(?:_1|_2)?\.md):L(\d+)-L(\d+)", ref)
                self.assertIsNotNone(match)
                assert match is not None
                path = ROOT / match.group(1)
                self.assertTrue(path.is_file())
                self.assertGreaterEqual(int(match.group(2)), 1)
                self.assertGreaterEqual(int(match.group(3)), int(match.group(2)))
                self.assertLessEqual(int(match.group(3)), len(path.read_text(encoding="utf-8").splitlines()))
            for mutation in ("missing", "extra", "duplicate", "reorder", "parameter", "return", "status", "owner", "ref"):
                candidate = self.clone()
                rows = candidate["algorithm_interface_registry"]
                if mutation == "missing": del rows[index]
                elif mutation == "extra": rows.append(copy.deepcopy(row))
                elif mutation == "duplicate": rows[index]["algorithm_id"] = rows[0]["algorithm_id"]
                elif mutation == "reorder": rows.reverse()
                elif mutation == "parameter": rows[index]["parameters"].reverse()
                elif mutation == "return": rows[index]["returns"] = "Wrong"
                elif mutation == "status": rows[index]["status_semantics"] = "Wrong"
                elif mutation == "owner": rows[index]["owner_entrypoint_id"] = "Wrong"
                else: rows[index]["authority_ref"] = ["archive/authority/RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L0-L0"]
                if candidate != self.value:
                    self.expect_reject(candidate)
        self.assertGreater(source_line_count, 1033)

    def test_public_entrypoints_failure_order_and_all_exports_are_closed(self) -> None:
        entries = self.value["public_entrypoint_registry"]
        codes = next(row for row in self.value["support_type_registry"] if row["type_id"] == "KernelErrorCodeV0_2_2")["invariants"]
        self.assertEqual(len(entries), 6)
        self.assertEqual([row["entrypoint_id"] for row in entries], sorted(row["entrypoint_id"] for row in entries))
        seen_c_codes: dict[str, str] = {}
        for index, row in enumerate(entries):
            self.assertEqual(set(row), {"entrypoint_id", "python_symbol", "parameters", "returns", "failure_mode", "failure_code_order", "purity"})
            self.assertTrue(row["python_symbol"].startswith("trade_system.rsi_mtf_drl_pm_v0_2_2."))
            self.assertEqual(row["purity"], "PURE_STDLIB_NO_IO")
            self.assertTrue(all(code in codes for code in row["failure_code_order"]))
            for code in row["failure_code_order"]:
                if code.startswith("E_C"):
                    self.assertNotIn(code, seen_c_codes)
                    seen_c_codes[code] = row["entrypoint_id"]
            for mutation in ("missing", "extra", "duplicate", "reorder", "parameter", "return", "symbol", "failure_mode", "failure_order", "purity"):
                candidate = self.clone(); rows = candidate["public_entrypoint_registry"]
                if mutation == "missing": del rows[index]
                elif mutation == "extra": rows.append(copy.deepcopy(row))
                elif mutation == "duplicate": rows[index]["entrypoint_id"] = rows[0]["entrypoint_id"]
                elif mutation == "reorder": rows.reverse()
                elif mutation == "parameter": rows[index]["parameters"].reverse()
                elif mutation == "return": rows[index]["returns"] = "Wrong"
                elif mutation == "symbol": rows[index]["python_symbol"] = "x:y"
                elif mutation == "failure_mode": rows[index]["failure_mode"] = "Wrong"
                elif mutation == "failure_order": rows[index]["failure_code_order"].reverse()
                else: rows[index]["purity"] = "IMPURE"
                if candidate != self.value:
                    self.expect_reject(candidate)
        self.assertNotIn("E_C21_AUTHORITY_LINEAGE_INVALID", seen_c_codes)
        expected_c_codes = {
            row["negative_error_code"]
            for row in self.value["closure_case_registry"]
            if row["closure_id"] != "C21"
        }
        self.assertEqual(set(seen_c_codes), expected_c_codes)
        by_id = {row["entrypoint_id"]: row for row in entries}
        bundle_codes = by_id["bundle_validator"]["failure_code_order"]
        decision_codes = by_id["decision_calculator"]["failure_code_order"]
        self.assertEqual(
            [
                code
                for code in bundle_codes
                if code
                in (
                    "E_C08_EV_STATS_INCONSISTENT",
                    "E_C09_TARGET_EVIDENCE_INCOMPLETE",
                    "E_C10_TARGET_ARTIFACT_ID_INVALID",
                )
            ],
            [
                "E_C08_EV_STATS_INCONSISTENT",
                "E_C09_TARGET_EVIDENCE_INCOMPLETE",
                "E_C10_TARGET_ARTIFACT_ID_INVALID",
            ],
        )
        self.assertNotIn("E_C09_TARGET_EVIDENCE_INCOMPLETE", decision_codes)
        self.assertEqual(
            [code for code in decision_codes if code.startswith("E_C")],
            [
                "E_C05_BOOK_GRID_DEDUP_INVALID",
                "E_C06_VENUE_RULE_MAPPING_INVALID",
                "E_C07_ACCOUNT_ASOF_CONFLICT",
                "E_C11_OI_SEAL_INCOMPLETE",
                "E_C12_DECISION_PROOF_INVALID",
                "E_C20_SELECTOR_BINDING_MISMATCH",
            ],
        )

    def test_closure_rows_gate_arrays_error_routing_and_cases_are_exact(self) -> None:
        rows = self.value["closure_case_registry"]
        entries = {row["entrypoint_id"]: row for row in self.value["public_entrypoint_registry"]}
        self.assertEqual([row["closure_id"] for row in rows], [f"C{i:02d}" for i in range(1, 22)])
        self.assertEqual(len({row["positive_case_id"] for row in rows} | {row["negative_case_id"] for row in rows}), 42)
        c09 = next(row for row in rows if row["closure_id"] == "C09")
        self.assertEqual(c09["case_executor_id"], "bundle_validator")
        for index, row in enumerate(rows):
            if row["case_executor_id"] in entries:
                self.assertIn(row["negative_error_code"], entries[row["case_executor_id"]]["failure_code_order"])
            else:
                self.assertEqual(row["case_executor_id"], "authority_lineage_checker")
                self.assertEqual(row["negative_error_code"], "E_C21_AUTHORITY_LINEAGE_INVALID")
            for mutation in ("missing", "extra", "duplicate", "reorder", "executor", "case", "error"):
                candidate = self.clone(); registry = candidate["closure_case_registry"]
                if mutation == "missing": del registry[index]
                elif mutation == "extra": registry.append(copy.deepcopy(row))
                elif mutation == "duplicate": registry[index]["closure_id"] = registry[0]["closure_id"]
                elif mutation == "reorder": registry.reverse()
                elif mutation == "executor": registry[index]["case_executor_id"] = "bundle_validator"
                elif mutation == "case": registry[index]["positive_case_id"] = "Wrong"
                else: registry[index]["negative_error_code"] = "E_KERNEL_ARGUMENT_INVALID"
                if candidate != self.value:
                    self.expect_reject(candidate)
        gate = self.value["synthetic_gate"]
        self.assertEqual(gate["required_closure_ids"], [row["closure_id"] for row in rows])
        self.assertEqual(gate["required_positive_case_ids"], [row["positive_case_id"] for row in rows])
        self.assertEqual(gate["required_negative_case_ids"], [row["negative_case_id"] for row in rows])
        self.assertEqual(gate["repeat_process_runs"], 2)
        for key in gate:
            candidate = self.clone(); candidate["synthetic_gate"][key] = [] if isinstance(gate[key], list) else "Wrong"
            self.expect_reject(candidate)

    def test_semantic_chronology_authorization_and_forbidden_injection_are_closed(self) -> None:
        self.assertEqual(self.value["chronology"]["active_role"], "SYNTHETIC")
        self.assertTrue(all(value == "FORBIDDEN" for key, value in self.value["authorization"].items() if not key.startswith("synthetic_")))

        def leaf_paths(value: object, prefix: tuple[str, ...] = ()):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield from leaf_paths(child, prefix + (key,))
            else:
                yield prefix

        leaves = [
            (section, path)
            for section in ("semantic_commitment", "chronology", "authorization")
            for path in leaf_paths(self.value[section])
        ]
        self.assertEqual(len(leaves), 32)
        for section, path in leaves:
            with self.subTest(section=section, path="/".join(path)):
                candidate = self.clone()
                parent = candidate[section]
                for key in path[:-1]:
                    parent = parent[key]
                old = parent[path[-1]]
                parent[path[-1]] = "MUTATED" if old is None else f"{old}_MUTATED"
                self.expect_reject(candidate)
        forbidden = ("parameter", "policy", "schema", "formula", "status", "selector", "identity", "state", "risk", "outcome", "market_data", "historical_data", "adapter", "backtest", "paper", "oms", "live_trading", "capability")
        for key in forbidden:
            candidate = self.clone(); candidate[key] = {"injected": True}
            self.expect_reject(candidate)
        spec = AUTHORITY_SPEC.read_text(encoding="utf-8")
        self.assertIn("#### 2.3.1A C05 decision-proof observability overlay", spec)
        ordered_fields = (
            "`grid_times_us` | `array<UtcUs>`",
            "`selected_book_artifact_ids` | `array<StableId>`",
            "`coverage_seal_artifact_id` | `StableId`",
            "`coverage_seal_sha256` | `Sha256`",
            "`ranked_candidate_ids` | `array<StableId>`",
            "`winner_candidate_id` | `StableId|null`",
            "`binding_sha256` | `Sha256`",
        )
        positions = [spec.index(field) for field in ordered_fields]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('ID("g0-selection-binding/v0.2.2"', spec)
        self.assertIn("相同 price但不同 grid必须形成两个不同 candidate ID", spec)
        self.assertIn(
            'KernelValidationError("E_C05_BOOK_GRID_DEDUP_INVALID")',
            spec,
        )
        self.assertIn("该 registry仍恰为11项", spec)

    def test_validator_source_has_only_read_only_contract_review_capabilities(self) -> None:
        source = CONTRACT_MODULE.read_text(encoding="utf-8")
        _assert_frozen_contract_ast_allowlist(source)
        counterexamples = (
            "\ndef _forbidden_import():\n    import subprocess\n",
            "\ndef _forbidden_open(path):\n    path.open('w')\n",
            "\ndef _forbidden_touch(path):\n    path.touch()\n",
            "\ndef _forbidden_subscript(calls):\n    calls['__import__']('os')\n",
            "\ndef _forbidden_unknown():\n    unknown_callee()\n",
            "\ndef _forbidden_lambda():\n    (lambda: None)()\n",
        )
        for counterexample in counterexamples:
            with self.subTest(counterexample=counterexample.splitlines()[1]):
                with self.assertRaises(AssertionError):
                    _assert_frozen_contract_ast_allowlist(source + counterexample)

    def _copy_authority_workspace(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        target = Path(temp.name)
        historical_sources = {
            "core_theory": ARCHIVED_CORE,
            "legacy_v0_2_contract_test": ARCHIVED_LEGACY_TEST,
        }
        for name, item in self.decision["frozen_inputs"].items():
            source = historical_sources.get(name, ROOT / item["path"])
            destination = target / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        decision_target = target / _decision_relative_path()
        decision_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DECISION, decision_target)
        return temp, target

    def test_temp_workspace_decision_and_each_frozen_input_tamper_fail_closed(self) -> None:
        temp, workspace = self._copy_authority_workspace()
        self.addCleanup(temp.cleanup)
        decision_copy = workspace / _decision_relative_path()
        decision_copy.write_bytes(decision_copy.read_bytes()[:-1] + b" ")
        with self.assertRaises(ContractValidationError):
            validate_contract_bytes(self.raw, workspace)
        temp.cleanup()
        for name, item in self.decision["frozen_inputs"].items():
            with self.subTest(frozen_input=name):
                temp, workspace = self._copy_authority_workspace()
                self.addCleanup(temp.cleanup)
                path = workspace / item["path"]
                raw = path.read_bytes()
                path.write_bytes((b"X" if raw[:1] != b"X" else b"Y") + raw[1:])
                with self.assertRaises(ContractValidationError) as caught:
                    validate_contract_bytes(self.raw, workspace)
                self.assertEqual(caught.exception.error_code, ERROR)
                temp.cleanup()

    def test_legacy_canonical_and_composite_are_recomputed_not_copied(self) -> None:
        legacy = ROOT / self.decision["frozen_inputs"]["legacy_v0_2_contract"]["path"]
        raw = legacy.read_bytes()
        canonical = json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        source = self.value["source_authority"]
        self.assertEqual(len(canonical), source["legacy_v0_2_contract_canonical_size_bytes"])
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), source["legacy_v0_2_contract_canonical_sha256"])
        preimage = {
            "core_raw_sha256": source["core_theory_raw_sha256"],
            "v0_2_contract_canonical_sha256": source["legacy_v0_2_contract_canonical_sha256"],
            "v0_2_1_addendum_raw_sha256": source["v0_2_1_addendum_raw_sha256"],
            "v0_2_2_delta_raw_sha256": source["semantic_source_raw_sha256"],
        }
        composite = hashlib.sha256(b"rsi-mtf-drl-pm-composite-theory/v0.2.2\x00" + json.dumps(preimage, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(composite, self.value["composite_theory_id"])
        candidate = self.clone(); candidate["composite_theory_id"] = "0" * 64
        self.expect_reject(candidate)


def _decision_relative_path() -> Path:
    return Path("config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json")


if __name__ == "__main__":
    unittest.main()
