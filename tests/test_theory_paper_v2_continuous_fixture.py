from __future__ import annotations

import ast
import contextlib
import io
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    verify_self_digest,
    write_once_json,
)
from trade_system.theory_paper_v2.infrastructure.legacy_v1.read_only import (
    read_existing_evaluation,
)
from trade_system.theory_paper_v2.infrastructure.continuous_fixture import (
    SyntheticStrategyAgent,
)
from trade_system.theory_paper_v2.infrastructure.research_cycle_store import (
    REQUIRED_EVIDENCE_ARTIFACT_BINDINGS,
    ResearchCycleStore,
)
from trade_system.theory_paper_v2.infrastructure.research_review_repository import (
    ReceiptBoundFourCycleReviewRepository,
    ResearchReviewRepositoryError,
)
from trade_system.theory_paper_v2.presentation.continuous_fixture_composition import (
    run_continuous_fixture,
)
from trade_system.theory_paper_v2.presentation.single_agent_research_cli import main


class ContinuousFixtureIntegrationTests(unittest.TestCase):
    def test_real_cli_completes_four_source_bound_dynamic_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            output = io.StringIO()
            seen_context_digests: list[str] = []
            original_propose = SyntheticStrategyAgent.propose

            def inspected_propose(agent, *, context):
                seen_context_digests.append(
                    verify_self_digest(context, "agent_context_digest")
                )
                return original_propose(agent, context=context)

            with mock.patch.object(
                SyntheticStrategyAgent, "propose", new=inspected_propose
            ), contextlib.redirect_stdout(output):
                code = main(
                    [
                        "run-continuous-fixture",
                        "--runtime-root",
                        str(runtime_root),
                        "--run-id",
                        "fixture-cli-run",
                    ]
                )
            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            self.assertEqual("COMPLETED_LOCAL_SYNTHETIC_FIXTURE", result["status"])
            self.assertEqual(4, result["completed_cycles"])
            self.assertEqual(4, len(seen_context_digests))
            self.assertEqual(
                "hypothesis:event-liquidity-vacuum-reversal",
                result["novel_hypothesis_id"],
            )
            self.assertEqual("FULFILLED", result["closed_expectation_status"])
            self.assertEqual(
                3, result["novel_hypothesis_became_operational_lead_cycle"]
            )
            self.assertEqual(
                "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE",
                result["agent_context_payload_mode"],
            )
            self.assertTrue(result["cross_window_resume_verified"])
            self.assertFalse(result["chat_history_is_authority"])
            self.assertTrue(result["public_inference_trace_bound"])
            self.assertFalse(result["private_chain_of_thought_recorded"])
            self.assertFalse(result["network_access"])
            self.assertFalse(result["model_invocation"])
            self.assertFalse(result["order_sent"])

            run_root = runtime_root / "fixture-cli-run"
            checkpoint = load_json_strict(run_root / "checkpoint.json")
            self.assertEqual(4, checkpoint["completed_cycles"])
            self.assertEqual(5, checkpoint["next_cycle_index"])
            review = load_json_strict(run_root / "reviews/through-cycle-0004.json")
            verify_self_digest(review, "review_digest")
            self.assertEqual(4, len(review["source_evidence_receipt_digests"]))
            self.assertEqual(
                "FOUR_VERIFIED_CYCLE_EVIDENCE_RECEIPTS", review["source_binding"]
            )
            for cycle_index in range(1, 5):
                receipt = load_json_strict(
                    run_root / f"evidence-receipts/cycle-{cycle_index:04d}.json"
                )
                verify_self_digest(receipt, "cycle_evidence_receipt_digest")
                self.assertEqual(
                    REQUIRED_EVIDENCE_ARTIFACT_BINDINGS,
                    set(receipt["artifact_bindings"]),
                )
                for required in (
                    "market_information_snapshot_digest",
                    "sentiment_state_digest",
                    "hypothesis_registry_delta_digest",
                    "hypothesis_registry_digest",
                    "expectation_ledger_delta_digest",
                    "expectation_ledger_digest",
                    "public_inference_trace_digest",
                ):
                    self.assertIn(required, receipt["artifact_bindings"])
                events = ResearchCycleStore(
                    run_root,
                    run_id="fixture-cli-run",
                    cycle_index=cycle_index,
                ).read_events()
                self.assertEqual("CYCLE_COMPLETED", events[-1]["event_type"])

            cycle2_receipt = load_json_strict(
                run_root / "evidence-receipts/cycle-0002.json"
            )
            registry = load_json_strict(
                run_root
                / cycle2_receipt["artifact_refs"]["hypothesis_registry_digest"]
            )
            self.assertIn(
                "hypothesis:event-liquidity-vacuum-reversal",
                registry["known_hypothesis_ids"],
            )
            self.assertIsNone(registry["semantic_family_whitelist"])
            context = load_json_strict(
                run_root
                / cycle2_receipt["artifact_refs"]["agent_context_digest"]
            )
            verify_self_digest(context, "agent_context_digest")
            self.assertEqual(
                "BOUNDED_INLINE_WITH_CONTENT_ADDRESSED_PRIOR_STATE",
                context["context_payload_mode"],
            )
            self.assertEqual(
                cycle2_receipt["artifact_bindings"][
                    "market_information_snapshot_digest"
                ],
                context["market_information_snapshot"][
                    "market_information_snapshot_digest"
                ],
            )
            self.assertEqual(
                {
                    "HOLD",
                    "OPEN",
                    "ADD",
                    "REDUCE",
                    "PARTIAL_TAKE_PROFIT",
                    "EXIT",
                    "REENTER",
                    "WAIT",
                },
                set(context["legal_action_contract"]["action_classes"]),
            )
            self.assertIsNone(
                context["research_capability_contract"][
                    "semantic_family_whitelist"
                ]
            )
            trace = load_json_strict(
                run_root
                / cycle2_receipt["artifact_refs"][
                    "public_inference_trace_digest"
                ]
            )
            verify_self_digest(trace, "public_inference_trace_digest")
            self.assertFalse(trace["private_chain_of_thought_recorded"])
            self.assertFalse(trace["uncalibrated_probability_emitted"])
            self.assertGreater(
                trace["evidence_balance"]["distinct_supporting_fact_count"], 0
            )
            self.assertGreater(
                trace["evidence_balance"]["distinct_contradicting_fact_count"], 0
            )
            self.assertGreater(
                trace["evidence_balance"]["distinct_unknown_fact_count"], 0
            )
            cycle3_receipt = load_json_strict(
                run_root / "evidence-receipts/cycle-0003.json"
            )
            ledger = load_json_strict(
                run_root
                / cycle3_receipt["artifact_refs"]["expectation_ledger_digest"]
            )
            expectation_by_id = {
                row["expectation_id"]: row for row in ledger["expectations"]
            }
            self.assertEqual(
                "FULFILLED", expectation_by_id["expectation:base-sequence"]["status"]
            )
            accepted_state = load_json_strict(
                run_root
                / cycle3_receipt["artifact_refs"]["accepted_state_digest"]
            )
            self.assertEqual(
                "hypothesis:event-liquidity-vacuum-reversal",
                accepted_state["operational_lead_path_id"],
            )
            self.assertEqual(
                cycle3_receipt["artifact_bindings"][
                    "public_inference_trace_digest"
                ],
                accepted_state["public_inference_trace_digest"],
            )

    def test_review_source_physical_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(
                runtime_root=runtime_root, run_id="fixture-tamper-run"
            )
            run_root = runtime_root / "fixture-tamper-run"
            receipt = load_json_strict(
                run_root / "evidence-receipts/cycle-0002.json"
            )
            target = run_root / receipt["artifact_refs"]["cycle_review_source_digest"]
            target.write_bytes(target.read_bytes() + b" ")
            repository = ReceiptBoundFourCycleReviewRepository(run_root)
            with self.assertRaisesRegex(
                ResearchReviewRepositoryError,
                "PHYSICAL_DRIFT|SEMANTIC_DIGEST",
            ):
                repository.load_verified_cycle_rows(
                    run_id="fixture-tamper-run", through_cycle=4
                )

        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(
                runtime_root=runtime_root, run_id="fixture-inference-tamper-run"
            )
            run_root = runtime_root / "fixture-inference-tamper-run"
            receipt = load_json_strict(
                run_root / "evidence-receipts/cycle-0002.json"
            )
            target = run_root / receipt["artifact_refs"][
                "public_inference_trace_digest"
            ]
            target.write_bytes(target.read_bytes() + b" ")
            with self.assertRaisesRegex(
                ResearchReviewRepositoryError,
                "CYCLE_EVENT_PAYLOAD_PHYSICAL_DRIFT|REVIEW_ARTIFACT_PHYSICAL_DRIFT",
            ):
                ReceiptBoundFourCycleReviewRepository(
                    run_root
                ).load_verified_cycle_rows(
                    run_id="fixture-inference-tamper-run", through_cycle=4
                )

    def test_nested_raw_market_source_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            run_continuous_fixture(
                runtime_root=runtime_root, run_id="fixture-raw-tamper-run"
            )
            run_root = runtime_root / "fixture-raw-tamper-run"
            raw_source = (
                run_root / "raw/cycle-0002/price_and_returns.json"
            )
            raw_source.write_bytes(raw_source.read_bytes() + b" ")
            with self.assertRaisesRegex(
                ResearchReviewRepositoryError,
                "REVIEW_RAW_SOURCE_PHYSICAL_DRIFT",
            ):
                ReceiptBoundFourCycleReviewRepository(
                    run_root
                ).load_verified_cycle_rows(
                    run_id="fixture-raw-tamper-run", through_cycle=4
                )

    def test_legacy_mutation_is_denied_and_evaluation_read_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "prepare-prospective",
                        "--project-root",
                        str(root),
                        "--runtime-root",
                        str(root / "runtime"),
                        "--template",
                        str(root / "template.json"),
                        "--run-id",
                        "legacy-denied",
                    ]
                )
            self.assertEqual(2, code)
            denied = json.loads(output.getvalue())
            self.assertEqual(
                "LEGACY_MUTATION_DISABLED_USE_CONTINUOUS_FIXTURE", denied["error"]
            )
            self.assertFalse((root / "runtime").exists())

            legacy_root = root / "legacy"
            write_once_json(
                legacy_root / "checkpoint.json",
                {
                    "run_id": "legacy",
                    "evaluation_path": None,
                },
            )
            before = sorted(path.relative_to(legacy_root) for path in legacy_root.rglob("*"))
            result = read_existing_evaluation(run_root=legacy_root)
            after = sorted(path.relative_to(legacy_root) for path in legacy_root.rglob("*"))
            self.assertEqual("LEGACY_EVALUATION_NOT_MATERIALIZED", result["status"])
            self.assertEqual(before, after)

    def test_new_main_path_obeys_four_layer_dependency_boundary(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        targets = {
            "trade_system/theory_paper_v2/domain/dynamic_research.py": {
                "application",
                "infrastructure",
                "presentation",
            },
            "trade_system/theory_paper_v2/domain/portfolio_truth.py": {
                "application",
                "infrastructure",
                "presentation",
            },
            "trade_system/theory_paper_v2/domain/epistemic_inference.py": {
                "application",
                "infrastructure",
                "presentation",
            },
            "trade_system/theory_paper_v2/domain/window_reliability.py": {
                "application",
                "infrastructure",
                "presentation",
            },
            "trade_system/theory_paper_v2/application/continuous_cycle.py": {
                "infrastructure",
                "presentation",
            },
            "trade_system/theory_paper_v2/application/continuous_fixture.py": {
                "infrastructure",
                "presentation",
            },
        }
        for relative, forbidden_segments in targets.items():
            tree = ast.parse((project_root / relative).read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            for imported in imports:
                self.assertFalse(
                    any(segment in imported.split(".") for segment in forbidden_segments),
                    f"{relative} imports forbidden layer through {imported}",
                )


if __name__ == "__main__":
    unittest.main()
