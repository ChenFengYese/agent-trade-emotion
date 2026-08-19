"""Mechanical, outcome-free checks for the v0.3.0 theory challenger registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = (
    PROJECT_ROOT
    / "config"
    / "rsi_mtf_drl_pm.theory_challenger.v0_3_0.hypothesis_registry.json"
)
DOCUMENT_PATH = PROJECT_ROOT / "theory/history/RSI_MTF_DRL_PM_THEORY_CHALLENGER_v0_3_0.md"

CHAMPION_FILES = {
    "semantic_source_sha256": "archive/authority/RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md",
    "authority_spec_sha256": "archive/authority/RSI_MTF_DRL_PM_AUTHORITY_BUNDLE_SPEC_v0_2_2.md",
    "route_decision_sha256": "config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json",
    "strategy_contract_sha256": "config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json",
}

P0_ORDER = (
    "V3-H01-TREND_VETO",
    "V3-H02-OFI_INCREMENT",
    "V3-H03-IMPACT_RESILIENCE",
    "V3-H04-LEVEL_RESPONSE",
    "V3-H05-VOL_LIQ_GEOMETRY",
    "V3-H06-REMAINING_EV_EXIT",
)

LAYER_ORDER = ("V3-L0", "V3-L1", "V3-L2", "V3-L3", "V3-L4", "V3-L5", "V3-L6")

ALLOWED_RESULTS = {
    "NOT_RUN",
    "WAIT_DATA",
    "INCONCLUSIVE_COVERAGE",
    "SUPPORTED_DEVELOPMENT_ONLY",
    "REJECTED_DEVELOPMENT",
    "CALIBRATION_PASS",
    "REJECTED_CALIBRATION",
    "HOLDOUT_PASS_BOUNDED",
    "REJECTED_HOLDOUT",
    "STOP_DATA_INVALID",
}


def _read_registry() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


class TheoryChallengerV030Tests(unittest.TestCase):
    def test_champion_bytes_match_registry(self) -> None:
        registry = _read_registry()
        champion = registry["champion"]

        self.assertFalse(champion["mutation_allowed"])
        for field, relative_path in CHAMPION_FILES.items():
            actual = hashlib.sha256(
                (PROJECT_ROOT / relative_path).read_bytes()
            ).hexdigest()
            self.assertEqual(champion[field], actual, relative_path)

    def test_exact_p0_ids_and_order(self) -> None:
        registry = _read_registry()
        hypotheses = registry["hypotheses"]

        self.assertEqual(tuple(registry["trial_order"]), P0_ORDER)
        self.assertEqual(tuple(item["hypothesis_id"] for item in hypotheses), P0_ORDER)
        self.assertTrue(all(item["priority"] == "P0" for item in hypotheses))

    def test_each_hypothesis_has_complete_traceable_definition(self) -> None:
        registry = _read_registry()
        source_ids = set(registry["source_registry"])
        required_scalar_fields = (
            "source_claim",
            "mechanism",
            "champion_control",
            "primary_outcome",
            "primary_metric",
            "falsification_condition",
        )

        for hypothesis in registry["hypotheses"]:
            with self.subTest(hypothesis_id=hypothesis["hypothesis_id"]):
                for field in required_scalar_fields:
                    self.assertIsInstance(hypothesis[field], str, field)
                    self.assertTrue(hypothesis[field].strip(), field)
                self.assertIsInstance(hypothesis["required_raw_fields"], list)
                self.assertTrue(hypothesis["required_raw_fields"])
                self.assertTrue(hypothesis["source_ids"])
                self.assertTrue(set(hypothesis["source_ids"]).issubset(source_ids))

    def test_b4_data_feasibility_and_development_gate_are_distinct(self) -> None:
        registry = _read_registry()
        capabilities = registry["capabilities"]
        gates = registry["authorization_gates"]

        self.assertEqual(
            capabilities["historical_source_adapter"],
            "FORBIDDEN_UNLESS_EXPLICIT_AUTHORITY_B4_DATA_FEASIBILITY_AUTHORIZATION_AND_INDEPENDENT_SOURCE_ADAPTER_CONTRACT",
        )
        self.assertEqual(
            capabilities["historical_outcome_access"],
            "FORBIDDEN_UNTIL_POST_B4_INDEPENDENT_DEVELOPMENT_AUTHORIZATION",
        )
        self.assertEqual(
            capabilities["backtest"],
            "FORBIDDEN_UNTIL_POST_B4_INDEPENDENT_DEVELOPMENT_AUTHORIZATION",
        )
        self.assertEqual(capabilities["paper"], "FORBIDDEN")
        self.assertEqual(capabilities["live"], "FORBIDDEN")
        self.assertEqual(
            capabilities["synthetic_schema_design"],
            "FORBIDDEN_UNTIL_SOL_V3_B_GATE_PASS",
        )
        self.assertEqual(
            gates["AUTHORITY_B4_DATA_FEASIBILITY"]["historical_outcome_access"],
            "NOT_GRANTED",
        )
        self.assertEqual(
            gates["AUTHORITY_B4_DATA_FEASIBILITY"]["backtest"], "NOT_GRANTED"
        )
        self.assertEqual(
            gates["INDEPENDENT_DEVELOPMENT_GATE"]["status"],
            "REQUIRES_SEPARATE_POST_B4_SOL_AUTHORIZATION",
        )

    def test_only_next_p0_is_the_independent_sol_v3_b_gate(self) -> None:
        next_p0 = _read_registry()["next_p0"]

        self.assertEqual(next_p0["action"], "SOL_V3_B_GATE")
        self.assertEqual(
            next_p0["v3_c_start"], "FORBIDDEN_UNTIL_SOL_V3_B_GATE_PASS"
        )
        self.assertEqual(
            next_p0["b4_data_feasibility_application"],
            "FORBIDDEN_UNTIL_POST_V3_C_GATE",
        )

    def test_result_statuses_are_registered_and_currently_outcome_free(self) -> None:
        registry = _read_registry()
        self.assertEqual(set(registry["common_protocol"]["allowed_results"]), ALLOWED_RESULTS)
        for hypothesis in registry["hypotheses"]:
            self.assertIn(hypothesis["result_status"], {"NOT_RUN", "WAIT_DATA"})
            self.assertIn(hypothesis["result_status"], ALLOWED_RESULTS)

    def test_comparison_graph_has_one_independent_edge_per_layer(self) -> None:
        registry = _read_registry()
        graph = registry["comparison_graph"]
        edges = graph["edges"]
        hypotheses = {item["hypothesis_id"]: item for item in registry["hypotheses"]}
        comparators = {item["comparator_id"] for item in graph["comparators"]}

        self.assertEqual(graph["mode"], "INDEPENDENT_SINGLE_LAYER_ONLY")
        self.assertEqual(graph["post_hoc_comparator_switching"], "FORBIDDEN")
        self.assertEqual(graph["cumulative_layering"], "FORBIDDEN")
        self.assertEqual(tuple(edge["layer_id"] for edge in edges), LAYER_ORDER)
        self.assertIsNone(edges[0]["hypothesis_id"])
        self.assertIsNone(edges[0]["comparator_id"])
        self.assertEqual(tuple(edge["hypothesis_id"] for edge in edges[1:]), P0_ORDER)
        self.assertTrue(all(edge["comparator_id"] in comparators for edge in edges[1:]))
        for edge in edges[1:]:
            self.assertEqual(
                hypotheses[edge["hypothesis_id"]]["comparison_edge_id"], edge["layer_id"]
            )
            self.assertEqual(
                hypotheses[edge["hypothesis_id"]]["champion_control"],
                edge["comparator_id"],
            )

    def test_h03_h04_require_disposition_not_predecessor_pass(self) -> None:
        hypotheses = {
            item["hypothesis_id"]: item for item in _read_registry()["hypotheses"]
        }
        self.assertEqual(
            hypotheses["V3-H03-IMPACT_RESILIENCE"]["depends_on"],
            ["V3-H02-OFI_INCREMENT_DISPOSITION_RECORDED"],
        )
        self.assertEqual(
            hypotheses["V3-H04-LEVEL_RESPONSE"]["depends_on"],
            ["V3-H03-IMPACT_RESILIENCE_DISPOSITION_RECORDED"],
        )
        for hypothesis_id in ("V3-H03-IMPACT_RESILIENCE", "V3-H04-LEVEL_RESPONSE"):
            self.assertNotIn("SUPPORT_CHALLENGER", hypotheses[hypothesis_id]["depends_on"])

    def test_measurement_contracts_are_pending_v3_c_not_frozen(self) -> None:
        for hypothesis in _read_registry()["hypotheses"]:
            with self.subTest(hypothesis_id=hypothesis["hypothesis_id"]):
                self.assertEqual(
                    hypothesis["measurement_contract_id"],
                    "V3-C-MEASUREMENT-CONTRACT-REQUIRED",
                )
                self.assertEqual(
                    hypothesis["measurement_contract_status"],
                    "NOT_FROZEN_REQUIRES_V3_C_SYNTHETIC",
                )
                self.assertTrue(hypothesis["measurement_definition_candidate"])
                self.assertNotIn("measurement_function", hypothesis)

    def test_h05_cites_pro_and_counter_volatility_evidence(self) -> None:
        registry = _read_registry()
        sources = registry["source_registry"]
        h05 = next(
            item
            for item in registry["hypotheses"]
            if item["hypothesis_id"] == "V3-H05-VOL_LIQ_GEOMETRY"
        )

        self.assertIn("SRC_VOL_2017", sources)
        self.assertIn("SRC_VOL_COUNTEREVIDENCE_2020", sources)
        self.assertIn("SRC_VOL_2017", h05["source_ids"])
        self.assertIn("SRC_VOL_COUNTEREVIDENCE_2020", h05["source_ids"])

    def test_document_has_all_ids_and_explicit_e0_no_trade_boundary(self) -> None:
        document = DOCUMENT_PATH.read_text(encoding="utf-8")

        for hypothesis_id in P0_ORDER:
            self.assertIn(hypothesis_id, document)
        self.assertIn("E0 / LITERATURE_SYNTHESIS / THEORY_CHALLENGER_ONLY", document)
        self.assertIn("不改变当前任何交易权限", document)
        self.assertIn("禁止声明：市场有效、预测有效、成本后盈利、paper 可用、实盘可用或可自动晋级。", document)
        self.assertIn("AUTHORITY_B4_DATA_FEASIBILITY", document)
        self.assertIn("INDEPENDENT_DEVELOPMENT_GATE", document)
        self.assertIn(
            "B1_CANDIDATE awaiting independent Sol gate; B2 unauthorized", document
        )
        self.assertIn("V3-L0 = frozen champion reference", document)
        self.assertNotIn("B0 = RSI + existing risk geometry", document)
        self.assertNotIn("DATA_INVALID` / `STOP_DATA_INVALID", document)

    def test_registry_does_not_grant_historical_outcome_access(self) -> None:
        registry = _read_registry()
        capabilities = registry["capabilities"]

        self.assertEqual(
            registry["status"],
            "OUTCOME_FREE_REPAIR_COMPLETE_AWAITING_SOL_V3_B_GATE",
        )
        self.assertEqual(
            capabilities["historical_outcome_access"],
            "FORBIDDEN_UNTIL_POST_B4_INDEPENDENT_DEVELOPMENT_AUTHORIZATION",
        )
        self.assertEqual(registry["common_protocol"]["role_dates"], "REQUIRED_BEFORE_ANY_NEW_OUTCOME_ACCESS")


if __name__ == "__main__":
    unittest.main()
