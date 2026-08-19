import json
import shutil
import tempfile
import unittest
from pathlib import Path

from trade_system.protocol import canonical_sha256
from trade_system.rsi_research_contract import (
    CONTROL_IDS,
    RsiResearchContract,
    RsiResearchContractError,
    _decimal,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "rsi_mtf_drl_pm.research_contract.v0_2.json"
ARCHIVED_CORE = ROOT / "archive/authority/CORE_TRADING_THEORY_v2_0.rsi-v0_2_2.md"


class RsiResearchContractTests(unittest.TestCase):
    def _raw(self):
        return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def _load_raw(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            core = workspace / "archive/authority/CORE_TRADING_THEORY_v2_1.md"
            validator = workspace / "trade_system/rsi_research_contract.py"
            validator.parent.mkdir(parents=True)
            shutil.copyfile(ARCHIVED_CORE, core)
            shutil.copyfile(ROOT / "trade_system/rsi_research_contract.py", validator)
            path = workspace / "config/contract.json"
            path.parent.mkdir()
            path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            return RsiResearchContract.load(path, workspace_root=workspace)

    def _assert_invalid(self, raw):
        with self.assertRaises(RsiResearchContractError):
            self._load_raw(raw)

    def _leaf_paths(self, value, prefix=()):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from self._leaf_paths(child, prefix + (key,))
        else:
            yield prefix

    def _drift(self, value):
        if isinstance(value, str):
            return f"{value}_DRIFT"
        if isinstance(value, bool):
            return not value
        if isinstance(value, int):
            return value + 1
        if isinstance(value, list):
            return value + ["DRIFT"]
        if isinstance(value, dict):
            return {**value, "DRIFT": "DRIFT"}
        raise AssertionError(f"unsupported test drift: {value!r}")

    def test_committed_artifact_is_valid_and_review_only(self):
        contract = self._load_raw(self._raw())
        self.assertEqual("REVIEW_READY", contract.raw["status"])
        self.assertEqual("E0", contract.raw["evidence_level"])
        self.assertEqual("REJECT_FREEZE", contract.raw["freeze_eligibility"])
        self.assertEqual(("C0", "C1", "C2", "C3", "C4", "Cmu", "C5"), CONTROL_IDS)
        self.assertEqual(list(CONTROL_IDS), [row["control_id"] for row in contract.raw["controls"]])
        self.assertFalse(contract.summary()["market_data_or_execution_authorized"])

    def test_canonical_bytes_and_digest_are_stable_across_key_order_and_whitespace(self):
        raw = self._raw()
        first = self._load_raw(raw)
        reordered = {key: raw[key] for key in reversed(list(raw))}
        second = self._load_raw(reordered)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.digest, second.digest)

    def test_same_identity_semantic_drift_is_rejected_but_changes_canonical_digest(self):
        raw = self._raw()
        baseline_digest = canonical_sha256(raw)
        mutations = (
            lambda value: value["entry_contract"].__setitem__("ttl_seconds", value["entry_contract"]["ttl_seconds"] + 1),
            lambda value: value["signal_contract"]["rsi"].__setitem__("c1_c2_event_ledger", "DIFFERENT_REARM"),
            lambda value: value["signal_contract"]["drl"]["long"].__setitem__("d_formula_id", "DIFFERENT_FORMULA"),
            lambda value: value["entry_contract"]["i0_path"]["tie_break"].__setitem__(0, "DIFFERENT_I0_TIE"),
            lambda value: value["entry_contract"]["geometry"].__setitem__("r_min", "1.3"),
            lambda value: value["risk_execution_contract"]["sizing_inputs"].__setitem__("formula_id", "DIFFERENT_SIZING_FORMULA"),
            lambda value: value["risk_execution_contract"]["sizing_inputs"].__setitem__("fee_bps_per_side", "6"),
            lambda value: value["chronology"]["windows"][0].__setitem__("start", "2024-03-02T00:00:00Z"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = self._raw()
                mutate(changed)
                self.assertNotEqual(baseline_digest, canonical_sha256(changed))
                self._assert_invalid(changed)

    def test_placeholders_and_unknown_top_level_fields_fail_closed(self):
        raw = self._raw()
        raw["signal_contract"]["regime"]["threshold"] = "TBD"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["unexpected"] = "value"
        self._assert_invalid(raw)

    def test_each_contract_block_rejects_a_missing_required_field(self):
        removals = {
            "signal_contract": "rsi",
            "entry_contract": "p_tau",
            "risk_execution_contract": "protection",
            "management_contract": "pivot",
            "ledger_contract": "required_fields",
            "experiment_contract": "hypothesis_mapping",
            "error_attribution": "layers",
            "acceptance_contract": "synthetic_fixture_policy",
        }
        for block, field in removals.items():
            with self.subTest(block=block, field=field):
                raw = self._raw()
                raw[block].pop(field)
                self._assert_invalid(raw)

    def test_chronology_requires_exact_order_non_overlap_and_role_buffers(self):
        raw = self._raw()
        raw["chronology"]["windows"].pop()
        self._assert_invalid(raw)
        raw = self._raw()
        raw["chronology"]["windows"][1]["role"] = "DEVELOPMENT"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["chronology"]["windows"][1]["start"] = "2024-06-01T00:00:00Z"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["chronology"]["windows"][1]["start"] = "2024-06-15T00:00:00Z"
        self._assert_invalid(raw)

    def test_holdout_must_remain_unopened_and_one_time_only(self):
        raw = self._raw()
        raw["holdout_receipt"]["opened"] = True
        self._assert_invalid(raw)
        raw = self._raw()
        raw["holdout_receipt"]["reuse_policy"] = "REUSABLE"
        self._assert_invalid(raw)

    def test_control_order_tie_breaks_and_hypothesis_mapping_are_frozen(self):
        raw = self._raw()
        raw["controls"][4], raw["controls"][5] = raw["controls"][5], raw["controls"][4]
        self._assert_invalid(raw)
        raw = self._raw()
        raw["entry_contract"]["candidate_tie_break"] = list(reversed(raw["entry_contract"]["candidate_tie_break"]))
        self._assert_invalid(raw)
        raw = self._raw()
        raw["experiment_contract"]["hypothesis_mapping"]["H-014"] = "Cmu-C4"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["experiment_contract"]["comparison_scope"]["H-013"] = "FULL_STRATEGY_COMPARISON"
        self._assert_invalid(raw)

    def test_every_control_dictionary_rejects_field_deletion_and_semantic_drift(self):
        structural_fields = (
            "required_gates", "forbidden_gates", "lane_roles", "anchor_source",
            "action_clock", "ttl_source", "entry_policy", "exit_policy",
            "inherits_submission_fill_from", "action_kind",
        )
        for index, control_id in enumerate(CONTROL_IDS):
            for field in structural_fields:
                with self.subTest(control_id=control_id, field=field, mutation="delete"):
                    raw = self._raw()
                    raw["controls"][index].pop(field)
                    self._assert_invalid(raw)
                with self.subTest(control_id=control_id, field=field, mutation="drift"):
                    raw = self._raw()
                    value = raw["controls"][index][field]
                    raw["controls"][index][field] = value + ["DRIFT"] if isinstance(value, list) else f"{value}_DRIFT"
                    self._assert_invalid(raw)

    def test_decimal_parser_rejects_noncanonical_or_json_float_values(self):
        self.assertEqual("-0.0005", str(_decimal("-0.0005", "test")))
        for invalid in ("-0", "0.10", "01", "1e-3", 0.1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(RsiResearchContractError):
                    _decimal(invalid, "test")
        raw = self._raw()
        raw["entry_contract"]["ev"]["lcb_confidence"] = 0.95
        self._assert_invalid(raw)

    def test_outcome_injection_and_strategy_authorization_fail_closed(self):
        raw = self._raw()
        raw["outcome"] = "TP"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["strategy_implementation_binding"]["bindings"] = [{"path": "trade_system/strategy.py", "sha256": "a" * 64}]
        self._assert_invalid(raw)
        raw = self._raw()
        raw["authorization"]["backtest"] = "ALLOWED"
        self._assert_invalid(raw)

    def test_review_tooling_hash_drift_fails_closed(self):
        raw = self._raw()
        raw["review_tooling_binding"]["bindings"][1]["sha256"] = "0" * 64
        self._assert_invalid(raw)

    def test_release_policy_recomputes_complete_body_digest_and_rejects_fake_values(self):
        raw = self._raw()
        raw["role_lane_policy"]["DEVELOPMENT"]["release_policy"]["sha256"] = "0" * 64
        self._assert_invalid(raw)
        raw = self._raw()
        raw["role_lane_policy"]["DEVELOPMENT"]["release_policy"]["source_schema_rules"][0]["lag_seconds"] += 1
        self._assert_invalid(raw)
        raw = self._raw()
        raw["role_lane_policy"]["HOLDOUT"]["release_policy"]["policy_id"] = "DIFFERENT_NO_ACCESS_POLICY"
        self._assert_invalid(raw)

    def test_protection_rejects_structural_deletion_and_transition_drift(self):
        for field in self._raw()["risk_execution_contract"]["protection"]:
            with self.subTest(field=field, mutation="delete"):
                raw = self._raw()
                raw["risk_execution_contract"]["protection"].pop(field)
                self._assert_invalid(raw)
            with self.subTest(field=field, mutation="drift"):
                raw = self._raw()
                value = raw["risk_execution_contract"]["protection"][field]
                raw["risk_execution_contract"]["protection"][field] = self._drift(value)
                self._assert_invalid(raw)
        for index, transition in enumerate(self._raw()["risk_execution_contract"]["protection"]["fill_transitions"]):
            for field in transition:
                with self.subTest(transition=index, field=field):
                    raw = self._raw()
                    raw["risk_execution_contract"]["protection"]["fill_transitions"][index][field] = self._drift(transition[field])
                    self._assert_invalid(raw)
        for index in (1, 2, 3):
            for field, forbidden_update in (("pe_update", "RECOMPUTE_CUMULATIVE_VWAP"), ("q_auth_update", "INCREASE_TO_CUMULATIVE_FILLED_QTY")):
                with self.subTest(transition=index, field=field, forbidden_update=forbidden_update):
                    raw = self._raw()
                    raw["risk_execution_contract"]["protection"]["fill_transitions"][index][field] = forbidden_update
                    self._assert_invalid(raw)
        raw = self._raw()
        raw["risk_execution_contract"]["protection"]["valid_stop_ack_invariant"]["enforcement"] = "VALID_STOP_ACK_ONLY"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["risk_execution_contract"]["protection"]["transient_window"]["start"] = "FIRST_FILL"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["risk_execution_contract"]["protection"]["pending_caps"]["FIRST_FILL_PENDING"]["max_quantity_fraction"] = "0"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["risk_execution_contract"]["protection"]["fill_transitions"][0]["pending_cap"] = "EXCESS_FILL_PENDING"
        self._assert_invalid(raw)

    def test_every_management_leaf_is_exact(self):
        template = self._raw()["management_contract"]
        for path in self._leaf_paths(template):
            with self.subTest(path=path):
                raw = self._raw()
                target = raw["management_contract"]
                for key in path[:-1]:
                    target = target[key]
                leaf = path[-1]
                target[leaf] = self._drift(target[leaf])
                self._assert_invalid(raw)

    def test_label_policy_subdigest_and_semantics_reject_drift(self):
        raw = self._raw()
        raw["label_contract"]["policy_sha256"] = "0" * 64
        self._assert_invalid(raw)
        for field in self._raw()["label_contract"]:
            if field == "policy_sha256":
                continue
            with self.subTest(field=field):
                raw = self._raw()
                raw["label_contract"][field] = self._drift(raw["label_contract"][field])
                self._assert_invalid(raw)
        for control_id in self._raw()["label_contract"]["label_policy_by_control"]:
            with self.subTest(control_id=control_id):
                raw = self._raw()
                raw["label_contract"]["label_policy_by_control"][control_id] = "DIFFERENT_LABEL_POLICY"
                self._assert_invalid(raw)
        raw = self._raw()
        raw["label_contract"]["policy_definition"]["market_path"] = "FIRST_HIT_DYNAMIC_BARRIER"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["label_contract"]["path_selection"] = "FIRST_HIT_FIXED_S0_T0_H0"
        self._assert_invalid(raw)
        raw = self._raw()
        raw["label_contract"]["label_policy_by_control"].pop("C5")
        self._assert_invalid(raw)

    def test_holdout_schema_and_unopened_state_machine_reject_drift(self):
        raw = self._raw()
        raw["holdout_receipt"]["future_receipt_schema"]["required_binding_names"].pop()
        self._assert_invalid(raw)
        raw = self._raw()
        raw["holdout_receipt"]["state_machine"] = ["UNOPENED", "CONSUMED_ONCE"]
        self._assert_invalid(raw)
        raw = self._raw()
        raw["holdout_receipt"]["transitions"][0]["rule"] = "IMMEDIATE_OPEN"
        self._assert_invalid(raw)

    def test_validator_has_no_data_reader_or_backtest_side_effects(self):
        source = (ROOT / "trade_system" / "rsi_research_contract.py").read_text(encoding="utf-8")
        self.assertNotIn("import requests", source)
        self.assertNotIn("from requests", source)
        self.assertNotIn("write_text", source)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
