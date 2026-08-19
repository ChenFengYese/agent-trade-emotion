from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.action_discrimination_experiment import (
    evaluate_completed_action_experiment,
    role_packet,
)
from trade_system.theory_paper_v2.domain.action_discrimination.evaluation import (
    evaluate_case_actions,
)
from trade_system.theory_paper_v2.domain.action_discrimination.model import (
    OUTPUT_SPECS,
    PATH_SLOTS,
    SAMPLE_INDICES,
    SELECTION_AXES,
    ActionDiscriminationError,
    profile_for_index,
)
from trade_system.theory_paper_v2.domain.action_discrimination.validation import (
    validate_semantic_output,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    verify_self_digest,
)
from trade_system.theory_paper_v2.infrastructure.action_discrimination_store import (
    EXPECTED_ROLE_KEYS,
    ActionExperimentStoreError,
    FrozenActionDatasetAdapter,
    FrozenOutcomeDatasetAdapter,
    prepare_action_experiment,
    record_action_case,
    verify_action_experiment,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = (
    ROOT
    / ".runtime"
    / "theory-paper-v2"
    / "formal-e0-batches"
    / "formal-e0-btcusdt-20260731T103131Z"
)
CONFIG = ROOT / "config" / "theory_agent_v2.action_discrimination_e0a.v1.json"
CONFIG_V11 = (
    ROOT / "config" / "theory_agent_v2.action_discrimination_e0a.v1_1.json"
)
DESIGN = ROOT / "archive/experiments/THEORY_AGENT_V2_ACTION_DISCRIMINATION_EXPERIMENT_v0_1.md"
TRANSPORT_ADDENDUM = (
    ROOT
    / "archive/experiments/THEORY_AGENT_V2_ACTION_DISCRIMINATION_TRANSPORT_ADDENDUM_v0_1.md"
)


def _semantic(role_key: str, context: dict, *, selected_offset: int = 0) -> dict:
    choice = context["candidate_calculations"]["selector_choice_set"]
    evidence = context["allowed_evidence_ids"]
    path_ids = (
        "NORMAL_REBOUND_TO_T1",
        "FAILURE_TO_STOP",
        "EXHAUSTION_T1_THEN_RETURN",
        "UNKNOWN",
    )
    paths = []
    for slot, path_id in zip(PATH_SLOTS, path_ids, strict=True):
        paths.append(
            {
                "slot": slot,
                "path_id": path_id,
                "summary": f"Frozen decision-time {slot} path.",
                "evidence_ids": evidence[:2] if slot != "OTHER_OR_UNKNOWN" else [],
                "hard_falsifier_refs": [],
                "unknowns": (
                    ["path_probabilities"] if slot == "OTHER_OR_UNKNOWN" else []
                ),
            }
        )
    selector = OUTPUT_SPECS[role_key] == "SELECTION"
    ranking = choice[selected_offset:] + choice[:selected_offset]
    return {
        "schema_id": "action_discrimination_semantic_output",
        "schema_version": "1.0.0",
        "output_kind": OUTPUT_SPECS[role_key],
        "context_digest": context["context_digest"],
        "state_digest": context["state"]["state_digest"],
        "paths": paths,
        "action_assessments": [
            {
                "action_id": action_id,
                "ordinal": "PREFERRED" if action_id == ranking[0] else "VIABLE",
                "rationale": "Compared under the frozen risk and path matrix.",
                "evidence_ids": evidence[:2],
            }
            for action_id in choice
        ],
        "challenge_claims": [
            {
                "category": "OPPORTUNITY_COST_OMISSION",
                "materiality": "MATERIAL",
                "claim": "No-action and exposure-changing candidates require symmetric review.",
                "evidence_ids": evidence[:2],
                "affected_action_ids": choice,
            }
        ],
        "selected_action": ranking[0] if selector else None,
        "ranked_action_ids": ranking if selector else [],
        "selection_axes": [
            {
                "axis": axis,
                "status": "APPLIED",
                "rationale": "Applied to the frozen context only.",
            }
            for axis in SELECTION_AXES
        ],
        "numeric_probability_status": "NOT_CLAIMED",
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }


def _invocation_receipts(context: dict) -> dict[str, dict]:
    return {
        role_key: {
            "role_key": role_key,
            "agent_task_id": f"test-{role_key}",
            "delivery_protocol": "INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1",
            "fork_turns": "none",
            "packet_digest": "a" * 64,
            "packet_byte_length": 100,
            "context_digest": context["context_digest"],
            "tool_use_status": "NO_TOOL_CALL_OBSERVED",
            "external_data_status": "NO_EXTERNAL_DATA_OBSERVED",
            "served_model_attestation": "UNATTESTED",
            "token_budget_attestation": "UNATTESTED",
            "formal_role_call": True,
            "response_json_only": True,
        }
        for role_key in EXPECTED_ROLE_KEYS
    }


@unittest.skipUnless(SOURCE_RUN.exists(), "frozen E0 authority is required")
class ActionDiscriminationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temp.name)
        self.run_root = prepare_action_experiment(
            runtime_root=self.runtime,
            run_id="action-e0a-test",
            source_run_root=SOURCE_RUN,
            config_path=CONFIG,
            design_path=DESIGN,
            frozen_at="2026-08-01T07:00:00Z",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_config_and_profile_mapping_are_frozen(self) -> None:
        config = load_json_strict(CONFIG)
        verify_self_digest(config, "config_digest")
        profiles = [profile_for_index(index)[0].profile_id.value for index in SAMPLE_INDICES]
        self.assertEqual(len(set(profiles)), 8)
        self.assertTrue(all(profiles.count(value) == 4 for value in set(profiles)))

    def test_prepare_has_all_actions_and_no_role_outputs(self) -> None:
        manifest = load_json_strict(self.run_root / "frozen" / "manifest.json")
        self.assertEqual(len(manifest["registered_action_ids"]), 11)
        self.assertEqual(len(manifest["choice_set_action_ids"]), 11)
        self.assertFalse((self.run_root / "outputs").exists())
        status = verify_action_experiment(self.run_root)
        self.assertEqual(status["completed_count"], 0)
        self.assertEqual(status["next_sample_index"], 128)
        pressure = load_json_strict(
            self.run_root / "frozen" / "contexts" / "sample-134.json"
        )
        normal_rows = {
            row["action_id"]: row["net_account_change"]
            for row in pressure["path_payoff_matrix"]["rows"]
            if row["path_id"] == "NORMAL_REBOUND_TO_T1"
        }
        self.assertNotEqual(
            normal_rows["REDUCE_TACTICAL"],
            normal_rows["PARTIAL_TAKE_PROFIT"],
        )

    def test_decision_adapter_denies_outcome_without_terminal_authorization(self) -> None:
        adapter = FrozenActionDatasetAdapter(SOURCE_RUN)
        context = adapter.decision_context(128)
        self.assertEqual(context["sample_index"], 128)
        self.assertFalse(hasattr(adapter, "outcome_bars"))
        with self.assertRaises(ActionExperimentStoreError):
            FrozenOutcomeDatasetAdapter(SOURCE_RUN, self.run_root)

    def test_role_packets_preserve_blindness(self) -> None:
        proposal = role_packet(
            run_root=self.run_root,
            sample_index=128,
            role="cluster-proposal",
        )
        challenge = role_packet(
            run_root=self.run_root,
            sample_index=128,
            role="cluster-challenge",
        )
        self.assertEqual(proposal["upstream_outputs"], {})
        self.assertEqual(challenge["upstream_outputs"], {})
        with self.assertRaises(ActionDiscriminationError):
            role_packet(
                run_root=self.run_root,
                sample_index=128,
                role="cluster-selection",
            )

    def test_semantic_validator_rejects_role_overreach(self) -> None:
        context = load_json_strict(
            self.run_root / "frozen" / "contexts" / "sample-128.json"
        )
        valid = _semantic("cluster-proposal", context)
        validation = validate_semantic_output(
            role_key="cluster-proposal", output=valid, context=context
        )
        self.assertGreater(validation.quality_score, 0)
        invalid = dict(valid)
        invalid["selected_action"] = context["candidate_calculations"][
            "selector_choice_set"
        ][0]
        with self.assertRaises(ActionDiscriminationError):
            validate_semantic_output(
                role_key="cluster-proposal", output=invalid, context=context
            )

    def test_one_case_records_atomically_and_advances_checkpoint(self) -> None:
        context = load_json_strict(
            self.run_root / "frozen" / "contexts" / "sample-128.json"
        )
        outputs = {key: _semantic(key, context) for key in EXPECTED_ROLE_KEYS}
        event = record_action_case(
            run_root=self.run_root,
            sample_index=128,
            semantic_outputs=outputs,
        )
        self.assertFalse(event["future_outcome_used"])
        status = verify_action_experiment(self.run_root)
        self.assertEqual(status["completed_count"], 1)
        self.assertEqual(status["role_output_count"], 6)
        self.assertEqual(status["next_sample_index"], 129)
        with self.assertRaises(ActionExperimentStoreError):
            record_action_case(
                run_root=self.run_root,
                sample_index=128,
                semantic_outputs=outputs,
            )

    def test_v11_direct_inline_successor_binds_same_contexts_and_receipts(self) -> None:
        successor = prepare_action_experiment(
            runtime_root=self.runtime,
            run_id="action-e0a-v11-test",
            source_run_root=SOURCE_RUN,
            config_path=CONFIG_V11,
            design_path=TRANSPORT_ADDENDUM,
            frozen_at="2026-08-01T08:00:00Z",
        )
        old_manifest = load_json_strict(
            self.run_root / "frozen" / "manifest.json"
        )
        new_manifest = load_json_strict(successor / "frozen" / "manifest.json")
        self.assertEqual(
            [row["context_digest"] for row in old_manifest["context_rows"]],
            [row["context_digest"] for row in new_manifest["context_rows"]],
        )
        self.assertEqual(
            new_manifest["role_transport"]["delivery_protocol"],
            "INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1",
        )
        context = load_json_strict(
            successor / "frozen" / "contexts" / "sample-128.json"
        )
        outputs = {key: _semantic(key, context) for key in EXPECTED_ROLE_KEYS}
        with self.assertRaises(ActionExperimentStoreError):
            record_action_case(
                run_root=successor,
                sample_index=128,
                semantic_outputs=outputs,
            )
        record_action_case(
            run_root=successor,
            sample_index=128,
            semantic_outputs=outputs,
            invocation_receipts=_invocation_receipts(context),
        )
        self.assertEqual(
            verify_action_experiment(successor)["completed_count"], 1
        )

    def test_outcome_evaluation_is_blocked_before_all_outputs(self) -> None:
        with self.assertRaises(ActionDiscriminationError):
            evaluate_completed_action_experiment(
                run_root=self.run_root,
                source_run_root=SOURCE_RUN,
            )

    def test_multi_horizon_ledger_separates_cost_and_opportunity_loss(self) -> None:
        adapter = FrozenActionDatasetAdapter(SOURCE_RUN)
        context = adapter.decision_context(128)
        # Unit-test the ledger against source-frozen rows. Application tests
        # separately prove that runtime outcome access requires a terminal chain.
        outcome = adapter._dataset.bars[129:153]
        choices = context["candidate_calculations"]["selector_choice_set"]
        diagnostic = evaluate_case_actions(
            context=context,
            single_action_id=choices[0],
            cluster_action_id=choices[1],
            outcome_bars=outcome,
        )
        self.assertEqual(
            [row["horizon_hours"] for row in diagnostic["horizons"]],
            [1, 4, 8, 24],
        )
        for row in diagnostic["horizons"]:
            for arm in ("single", "cluster"):
                ledger = row["arms"][arm]
                self.assertIn("transaction_cost", ledger)
                self.assertTrue(ledger["opportunity_loss_not_actual_loss"])

    def test_full_fixture_chain_reaches_descriptive_terminal_result(self) -> None:
        for sample_index in SAMPLE_INDICES:
            context = load_json_strict(
                self.run_root
                / "frozen"
                / "contexts"
                / f"sample-{sample_index:03d}.json"
            )
            outputs = {
                key: _semantic(
                    key,
                    context,
                    selected_offset=(
                        1
                        if key == "cluster-selection"
                        and len(
                            context["candidate_calculations"][
                                "selector_choice_set"
                            ]
                        )
                        > 1
                        else 0
                    ),
                )
                for key in EXPECTED_ROLE_KEYS
            }
            record_action_case(
                run_root=self.run_root,
                sample_index=sample_index,
                semantic_outputs=outputs,
            )
        status = verify_action_experiment(self.run_root)
        self.assertTrue(status["terminal"])
        self.assertEqual(status["role_output_count"], 192)
        result = evaluate_completed_action_experiment(
            run_root=self.run_root,
            source_run_root=SOURCE_RUN,
        )
        self.assertIn(
            result["terminal_verdict"],
            {
                "INCONCLUSIVE_ACTION_TRADEOFF",
                "PRACTICAL_CLUSTER_ACTION_BENEFIT",
                "PRACTICAL_SINGLE_ACTION_BENEFIT",
            },
        )
        self.assertFalse(result["claims"]["profitability_proven"])


if __name__ == "__main__":
    unittest.main()
