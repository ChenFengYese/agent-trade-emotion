from __future__ import annotations

import ast
from copy import deepcopy
import inspect
import tempfile
from pathlib import Path
import unittest

from trade_system.theory_paper_v2.application import (
    v32_shadow_outcome_composition as shadow_composition_module,
)
from tests.test_theory_paper_v2_v32_shadow_evaluation import (
    AS_OF,
    DECISION_ID,
    RUN_ID,
    _arms,
    _common_bindings,
    _decision_bundle,
    _embedded_binding,
    _receipt,
    _schedule_set,
)
from trade_system.theory_paper_v2.application.v32_shadow_outcome_composition import (
    V32ShadowOutcomeCompositionError,
    complete_v32_shadow_outcome_tail,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    load_json_strict,
    self_digest,
    write_once_json,
)
from trade_system.theory_paper_v2.domain.v32_outcome_tick import (
    BATCH_COMPLETION_DIGEST_FIELD,
    BATCH_COMPLETION_SCHEMA_ID,
    OUTCOME_RECEIPT_DIGEST_FIELD,
    OUTCOME_RECEIPT_SCHEMA_ID,
    SCHEDULE_SET_DIGEST_FIELD,
    SCHEDULE_SET_SCHEMA_ID,
)
from trade_system.theory_paper_v2.domain.v32_shadow_evaluation import (
    SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
    SHADOW_DECISION_BUNDLE_SCHEMA_ID,
    SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD,
    build_v32_shadow_decision_bundle_v1,
    build_v32_shadow_outcome_evaluation_v1,
)
from trade_system.theory_paper_v2.infrastructure.v32_shadow_evaluation_store import (
    CHECKPOINT_DIGEST_FIELD,
    LocalV32ShadowEvaluationStore,
    V32ShadowEvaluationStoreError,
)


def _completion(receipt: dict) -> dict:
    return self_digest(
        {
            "schema_id": BATCH_COMPLETION_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": receipt["run_id"],
            "batch_id": "outcome-batch:0001",
            "batch_intent_digest": receipt["batch_intent_digest"],
            "observation_tick_digest": receipt["observation_tick_digest"],
            "raw_evidence_digest": receipt["raw_evidence_digest"],
            "completed_at": "2026-08-07T00:15:03Z",
            "resolved_schedule_ids": [receipt["schedule_id"]],
            "outcome_receipt_digests": [
                receipt[OUTCOME_RECEIPT_DIGEST_FIELD]
            ],
            "network_requests_during_tail": 0,
            "all_due_schedules_terminal": True,
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        BATCH_COMPLETION_DIGEST_FIELD,
    )


class CrashAfterEvaluationWriteStore(LocalV32ShadowEvaluationStore):
    def __init__(self, run_root: Path) -> None:
        super().__init__(run_root)
        self.crash_once = True

    def _after_evaluation_write(self, binding: dict) -> None:
        if self.crash_once:
            self.crash_once = False
            raise RuntimeError("SIMULATED_CRASH_AFTER_EVALUATION_WRITE")


class V32ShadowOutcomeCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = LocalV32ShadowEvaluationStore(self.root)
        self._prepare_inputs()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _seal(self, binding: dict, document: dict) -> None:
        write_once_json(self.root / binding["relative_ref"], document)

    def _prepare_inputs(self, *, coverage_loss: bool = False) -> None:
        self.bundle = _decision_bundle()
        self.schedule_set = _schedule_set(self.bundle)
        self.receipt = _receipt(self.schedule_set, coverage_loss=coverage_loss)
        self.completion = _completion(self.receipt)
        self.bundle_binding = _embedded_binding(
            self.bundle,
            relative_ref="cycles/cycle-0001/shadow-decision-bundle.json",
            schema_id=SHADOW_DECISION_BUNDLE_SCHEMA_ID,
            digest_field=SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
        )
        self.schedule_binding = _embedded_binding(
            self.schedule_set,
            relative_ref="outcome-v32/schedules/cycle-0001.json",
            schema_id=SCHEDULE_SET_SCHEMA_ID,
            digest_field=SCHEDULE_SET_DIGEST_FIELD,
        )
        self.receipt_binding = _embedded_binding(
            self.receipt,
            relative_ref=(
                "outcome-v32/ticks/0001/receipts/"
                f"{self.receipt['schedule_id']}.json"
            ),
            schema_id=OUTCOME_RECEIPT_SCHEMA_ID,
            digest_field=OUTCOME_RECEIPT_DIGEST_FIELD,
        )
        self.completion_binding = _embedded_binding(
            self.completion,
            relative_ref="outcome-v32/ticks/0001/batch-completion.json",
            schema_id=BATCH_COMPLETION_SCHEMA_ID,
            digest_field=BATCH_COMPLETION_DIGEST_FIELD,
        )
        for document, binding in (
            (self.bundle, self.bundle_binding),
            (self.schedule_set, self.schedule_binding),
            (self.receipt, self.receipt_binding),
            (self.completion, self.completion_binding),
        ):
            self._seal(binding, document)

    def _tail(self, **overrides):
        arguments = {
            "store": self.store,
            "shadow_decision_bundle": self.bundle,
            "shadow_decision_bundle_binding": self.bundle_binding,
            "outcome_schedule_set": self.schedule_set,
            "outcome_schedule_set_binding": self.schedule_binding,
            "outcome_receipt": self.receipt,
            "outcome_receipt_binding": self.receipt_binding,
            "outcome_batch_completion": self.completion,
            "outcome_batch_completion_binding": self.completion_binding,
        }
        arguments.update(overrides)
        return complete_v32_shadow_outcome_tail(**arguments)

    def test_success_persists_only_terminal_direction_and_exact_binding(self) -> None:
        result = self._tail()
        self.assertEqual("COMMITTED", result["status"])
        self.assertTrue(result["directional_alignment_only"])
        self.assertFalse(result["path_metrics_evaluated"])
        self.assertEqual(0, result["network_requests"])
        self.assertEqual(0, result["agent_calls"])
        self.assertTrue(result["batch_completion_precedes_local_tail"])
        self.assertEqual(
            "2026-08-07T00:15:03.000001Z", result["shadow_evaluated_at"]
        )
        binding = result["evaluation_binding"]
        evaluation = load_json_strict(self.root / binding["relative_ref"])
        self.assertEqual(
            binding["semantic_digest"],
            evaluation[SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD],
        )
        for row in evaluation["arm_results"]:
            self.assertEqual("UNKNOWN", row["path_alignment"])
            self.assertEqual("UNKNOWN", row["mfe_band"])
            self.assertEqual("UNKNOWN", row["mae_band"])
            self.assertEqual("UNKNOWN", row["opportunity_miss_band"])
            self.assertFalse(row["fill_claim"])
            self.assertFalse(row["position_claim"])
            self.assertFalse(row["pnl_claim"])
            self.assertFalse(row["expected_value_allowed"])

    def test_coverage_loss_keeps_every_outcome_field_unknown(self) -> None:
        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = LocalV32ShadowEvaluationStore(self.root)
        self._prepare_inputs(coverage_loss=True)
        result = self._tail()
        evaluation = load_json_strict(
            self.root / result["evaluation_binding"]["relative_ref"]
        )
        self.assertEqual("UNKNOWN_COVERAGE_LOSS", result["outcome_resolution_status"])
        for row in evaluation["arm_results"]:
            self.assertEqual("UNKNOWN", row["directional_alignment"])
            self.assertEqual("UNKNOWN_COVERAGE_LOSS", row["comparison_status"])
            self.assertEqual(5, len(row["unknown_fields"]))

    def test_physical_binding_and_cross_decision_conflicts_fail_closed(self) -> None:
        bad_physical = dict(self.receipt_binding)
        bad_physical["physical_sha256"] = "0" * 64
        with self.assertRaises(V32ShadowOutcomeCompositionError):
            self._tail(outcome_receipt_binding=bad_physical)

        bindings = _common_bindings()
        other_bundle = build_v32_shadow_decision_bundle_v1(
            bundle_id="shadow-bundle:other-decision",
            run_id=RUN_ID,
            decision_id="decision:other",
            cycle_index=1,
            as_of=AS_OF,
            created_at=AS_OF,
            decision_mark_snapshot={
                "value": "64000",
                "datum_digest": "d" * 64,
                "observed_at": AS_OF,
                "available_at": AS_OF,
            },
            arms=_arms(bindings),
            **bindings,
        )
        other_binding = _embedded_binding(
            other_bundle,
            relative_ref="cycles/cycle-0001/other-shadow-bundle.json",
            schema_id=SHADOW_DECISION_BUNDLE_SCHEMA_ID,
            digest_field=SHADOW_DECISION_BUNDLE_DIGEST_FIELD,
        )
        self._seal(other_binding, other_bundle)
        with self.assertRaises(V32ShadowOutcomeCompositionError):
            self._tail(
                shadow_decision_bundle=other_bundle,
                shadow_decision_bundle_binding=other_binding,
            )

        forged_receipt = deepcopy(self.receipt)
        forged_receipt["decision_id"] = "decision:other"
        forged_receipt = self_digest(
            forged_receipt, OUTCOME_RECEIPT_DIGEST_FIELD
        )
        forged_binding = _embedded_binding(
            forged_receipt,
            relative_ref="outcome-v32/ticks/0001/receipts/forged.json",
            schema_id=OUTCOME_RECEIPT_SCHEMA_ID,
            digest_field=OUTCOME_RECEIPT_DIGEST_FIELD,
        )
        self._seal(forged_binding, forged_receipt)
        forged_completion = _completion(forged_receipt)
        forged_completion_binding = _embedded_binding(
            forged_completion,
            relative_ref="outcome-v32/ticks/0001/forged-completion.json",
            schema_id=BATCH_COMPLETION_SCHEMA_ID,
            digest_field=BATCH_COMPLETION_DIGEST_FIELD,
        )
        self._seal(forged_completion_binding, forged_completion)
        with self.assertRaises(V32ShadowOutcomeCompositionError):
            self._tail(
                outcome_receipt=forged_receipt,
                outcome_receipt_binding=forged_binding,
                outcome_batch_completion=forged_completion,
                outcome_batch_completion_binding=forged_completion_binding,
            )

    def test_caller_cannot_inject_or_self_sign_arm_results(self) -> None:
        with self.assertRaises(TypeError):
            self._tail(arm_results=[])

        checkpoint = self.store.initialize_checkpoint(
            run_id=RUN_ID, created_at=self.bundle["created_at"]
        )
        valid = build_v32_shadow_outcome_evaluation_v1(
            evaluation_id="shadow-outcome-evaluation:forgery-test",
            shadow_decision_bundle=self.bundle,
            shadow_decision_bundle_binding=self.bundle_binding,
            outcome_schedule_set=self.schedule_set,
            outcome_schedule_set_binding=self.schedule_binding,
            outcome_receipt=self.receipt,
            outcome_receipt_binding=self.receipt_binding,
            horizon="15M",
            evaluated_at="2026-08-07T00:15:03.000001Z",
        )
        forged = deepcopy(valid)
        forged["arm_results"][0]["directional_alignment"] = "OPPOSED"
        forged = self_digest(forged, SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32ShadowEvaluationStoreError, "EVALUATION_INVALID"
        ):
            self.store.commit_evaluation(
                evaluation=forged,
                shadow_decision_bundle=self.bundle,
                outcome_schedule_set=self.schedule_set,
                outcome_receipt=self.receipt,
                outcome_batch_completion=self.completion,
                outcome_batch_completion_binding=self.completion_binding,
                expected_checkpoint_digest=checkpoint[CHECKPOINT_DIGEST_FIELD],
            )

    def test_crash_after_write_recovers_idempotently_without_second_result(self) -> None:
        self.store = CrashAfterEvaluationWriteStore(self.root)
        initialized = self.store.initialize_checkpoint(
            run_id=RUN_ID, created_at=self.bundle["created_at"]
        )
        with self.assertRaisesRegex(RuntimeError, "SIMULATED_CRASH"):
            self._tail(
                expected_checkpoint_digest=initialized[CHECKPOINT_DIGEST_FIELD]
            )
        interrupted = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual([], interrupted["evaluation_bindings"])
        recovered = self._tail(
            expected_checkpoint_digest=initialized[CHECKPOINT_DIGEST_FIELD]
        )
        self.assertEqual("COMMITTED", recovered["status"])
        replay = self._tail(
            expected_checkpoint_digest=initialized[CHECKPOINT_DIGEST_FIELD]
        )
        self.assertEqual("IDEMPOTENT_REPLAY", replay["status"])
        self.assertEqual(
            recovered["evaluation_binding"], replay["evaluation_binding"]
        )
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(1, checkpoint["revision"])
        self.assertEqual(1, len(checkpoint["evaluation_bindings"]))

    def test_same_schedule_different_valid_evaluation_is_write_once_conflict(self) -> None:
        committed = self._tail()
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        different = build_v32_shadow_outcome_evaluation_v1(
            evaluation_id="shadow-outcome-evaluation:different-id",
            shadow_decision_bundle=self.bundle,
            shadow_decision_bundle_binding=self.bundle_binding,
            outcome_schedule_set=self.schedule_set,
            outcome_schedule_set_binding=self.schedule_binding,
            outcome_receipt=self.receipt,
            outcome_receipt_binding=self.receipt_binding,
            horizon="15M",
            evaluated_at="2026-08-07T00:15:03.000001Z",
        )
        self.assertNotEqual(
            committed["evaluation_binding"]["semantic_digest"],
            different[SHADOW_OUTCOME_EVALUATION_DIGEST_FIELD],
        )
        with self.assertRaisesRegex(
            V32ShadowEvaluationStoreError, "WRITE_ONCE_CONFLICT"
        ):
            self.store.commit_evaluation(
                evaluation=different,
                shadow_decision_bundle=self.bundle,
                outcome_schedule_set=self.schedule_set,
                outcome_receipt=self.receipt,
                outcome_batch_completion=self.completion,
                outcome_batch_completion_binding=self.completion_binding,
                expected_checkpoint_digest=checkpoint[CHECKPOINT_DIGEST_FIELD],
            )

    def test_wrong_cas_token_fails_before_evaluation_write(self) -> None:
        initialized = self.store.initialize_checkpoint(
            run_id=RUN_ID, created_at=self.bundle["created_at"]
        )
        self.assertNotEqual("f" * 64, initialized[CHECKPOINT_DIGEST_FIELD])
        with self.assertRaises(V32ShadowOutcomeCompositionError):
            self._tail(expected_checkpoint_digest="f" * 64)
        checkpoint = self.store.load_checkpoint(run_id=RUN_ID)
        self.assertEqual(0, checkpoint["revision"])
        self.assertEqual([], checkpoint["evaluation_bindings"])
        evaluation_root = self.root / "shadow-evaluation-v32/cycles"
        self.assertFalse(evaluation_root.exists())

    def test_application_composition_has_no_infrastructure_dependency(self) -> None:
        tree = ast.parse(inspect.getsource(shadow_composition_module))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertFalse(
            any("infrastructure" in module for module in imported_modules),
            imported_modules,
        )


if __name__ == "__main__":
    unittest.main()
