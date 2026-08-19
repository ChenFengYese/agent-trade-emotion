from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from inspect import signature
from pathlib import Path

from tests.test_theory_paper_v2_v31_cycle import DECISION_AT, full_inputs
from trade_system.theory_paper_v2.application.v31_durable_bundle import (
    ASSEMBLY_BUNDLE_DIRECTORY,
    V31DurableBundleError,
    assembly_bundle_relative_ref,
    rebuild_v31_documents_from_bundle,
    seal_v31_durable_assembly_bundle,
)
from trade_system.theory_paper_v2.application.v31_durable_cycle import (
    V31DurableCycleError,
    recover_persisted_v31_cycle,
)
from trade_system.theory_paper_v2.application.v31_research_cycle import (
    assemble_v31_cycle_evaluation,
    complete_v31_research_cycle,
    select_v31_cycle_action,
)
from trade_system.theory_paper_v2.domain.behavior_planning import (
    seal_action_selection,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    self_digest,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
    V31ResearchStoreError,
)


EVENT_ORDER = (
    "INPUTS_ADMITTED",
    "PROPOSAL_SEALED",
    "EVALUATION_SEALED",
    "SELECTION_SEALED",
    "STATE_ACCEPTED",
    "COMPLETION_SEALED",
)


def completed_cycle_fixture():
    inputs = full_inputs()
    preselection = assemble_v31_cycle_evaluation(**inputs)
    evaluation = inputs["action_evaluation"]
    selected_candidate_id = "candidate:WAIT"
    alternatives = {
        row["candidate_id"]: "less robust under the admitted uncertainty"
        for row in evaluation["candidates"]
        if row["candidate_id"] != selected_candidate_id
    }
    failures = ("new evidence invalidates the wait thesis",)
    selection = seal_action_selection(
        evaluation=evaluation,
        selected_candidate_id=selected_candidate_id,
        reason="WAIT preserves reversibility in the fixture.",
        alternative_explanations=alternatives,
        failure_conditions=failures,
        next_review_at="2026-08-06T11:00:00Z",
        selected_at="2026-08-06T10:00:01Z",
    )
    accepted = select_v31_cycle_action(
        preselection=preselection,
        action_evaluation=evaluation,
        selected_candidate_id=selected_candidate_id,
        alternative_explanations=alternatives,
        selection_rationale="WAIT preserves reversibility in the fixture.",
        failure_conditions=failures,
        next_review_at="2026-08-06T11:00:00Z",
        selected_at="2026-08-06T10:00:01Z",
    )
    completion = complete_v31_research_cycle(
        accepted_state=accepted,
        completed_at="2026-08-06T10:00:02Z",
    )
    documents = {
        "INPUTS_ADMITTED": inputs["inputs_receipt"],
        "PROPOSAL_SEALED": inputs["agent_proposal"],
        "EVALUATION_SEALED": preselection,
        "SELECTION_SEALED": selection,
        "STATE_ACCEPTED": accepted,
        "COMPLETION_SEALED": completion,
    }
    event_times = {
        event_type: f"2026-08-06T10:00:{index + 2:02d}Z"
        for index, event_type in enumerate(EVENT_ORDER)
    }
    return inputs, documents, event_times


class V31DurableBundleTests(unittest.TestCase):
    def test_strict_typed_bundle_rebuilds_all_six_artifacts(self) -> None:
        inputs, documents, event_times = completed_cycle_fixture()
        bundle = seal_v31_durable_assembly_bundle(
            assembly_inputs=inputs,
            documents=documents,
            recorded_at_by_event=event_times,
        )

        rebuilt_inputs, rebuilt_documents, rebuilt_times = (
            rebuild_v31_documents_from_bundle(bundle)
        )

        expected_inputs = signature(assemble_v31_cycle_evaluation).bind(**inputs)
        expected_inputs.apply_defaults()
        self.assertEqual(dict(expected_inputs.arguments), rebuilt_inputs)
        self.assertEqual(documents, rebuilt_documents)
        self.assertEqual(event_times, rebuilt_times)

        drifted = dict(bundle)
        drifted["unknown_schema_field"] = "must fail closed"
        drifted.pop("assembly_bundle_digest")
        drifted = self_digest(drifted, "assembly_bundle_digest")
        with self.assertRaisesRegex(V31DurableBundleError, "V31_BUNDLE_SCHEMA_INVALID"):
            rebuild_v31_documents_from_bundle(drifted)

        signature_drift = dict(bundle)
        signature_drift["assembly_parameter_names"] = [
            *signature_drift["assembly_parameter_names"],
            "removed_or_unknown_parameter",
        ]
        signature_drift["assembly_signature_digest"] = canonical_digest(
            signature_drift["assembly_parameter_names"]
        )
        signature_drift.pop("assembly_bundle_digest")
        signature_drift = self_digest(
            signature_drift, "assembly_bundle_digest"
        )
        with self.assertRaisesRegex(
            V31DurableBundleError, "V31_BUNDLE_BOUNDARY_OR_SCHEMA_DRIFT"
        ):
            rebuild_v31_documents_from_bundle(signature_drift)

        execution_drift = {
            **inputs,
            "inputs_receipt": {
                **inputs["inputs_receipt"],
                "executable": True,
            },
        }
        with self.assertRaisesRegex(
            V31DurableBundleError, "V31_BUNDLE_EXECUTABLE_INPUT_FORBIDDEN"
        ):
            seal_v31_durable_assembly_bundle(
                assembly_inputs=execution_drift,
                documents=documents,
                recorded_at_by_event=event_times,
            )

    def test_fresh_store_recovers_from_only_content_addressed_bundle(self) -> None:
        inputs, documents, event_times = completed_cycle_fixture()
        bundle = seal_v31_durable_assembly_bundle(
            assembly_inputs=inputs,
            documents=documents,
            recorded_at_by_event=event_times,
        )
        relative_ref = assembly_bundle_relative_ref(
            cycle_index=1,
            bundle_digest=bundle["assembly_bundle_digest"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_process = LocalV31ResearchStore(root)
            first_process.write_document(
                relative_ref=relative_ref,
                document=bundle,
                digest_field="assembly_bundle_digest",
            )

            # Start a genuinely fresh interpreter: it receives only the durable
            # root path and immutable run identity, never any typed input object,
            # chronology document, selection plan, or semantic-admission state.
            project_root = Path(__file__).resolve().parents[1]
            recovery_script = """
import json
import sys
from pathlib import Path

from trade_system.theory_paper_v2.application.v31_durable_cycle import recover_persisted_v31_cycle
from trade_system.theory_paper_v2.infrastructure.v31_research_store import LocalV31ResearchStore

checkpoint = recover_persisted_v31_cycle(
    store=LocalV31ResearchStore(Path(sys.argv[1])),
    run_id="run:v31",
    cycle_index=1,
    total_cycles=1,
    created_at=sys.argv[2],
)
print(json.dumps(checkpoint, sort_keys=True, separators=(",", ":")))
"""
            recovered = subprocess.run(
                [sys.executable, "-c", recovery_script, str(root), DECISION_AT],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            )
            checkpoint = json.loads(recovered.stdout)

            self.assertEqual("TERMINAL", checkpoint["status"])
            self.assertEqual(
                [
                    {
                        "cycle_index": 1,
                        "relative_ref": relative_ref,
                        "semantic_digest": bundle["assembly_bundle_digest"],
                    }
                ],
                checkpoint["assembly_bundle_bindings"],
            )
            third_process = LocalV31ResearchStore(root)
            self.assertEqual(
                checkpoint["checkpoint_digest"],
                third_process.load_checkpoint(run_id="run:v31")[
                    "checkpoint_digest"
                ],
            )

    def test_missing_ambiguous_and_resigned_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                V31DurableCycleError, "V31_DURABLE_RECOVERY_FAILED_CLOSED"
            ):
                recover_persisted_v31_cycle(
                    store=LocalV31ResearchStore(Path(directory)),
                    run_id="run:v31",
                    cycle_index=1,
                    total_cycles=1,
                    created_at=DECISION_AT,
                )

        inputs, documents, event_times = completed_cycle_fixture()
        bundle = seal_v31_durable_assembly_bundle(
            assembly_inputs=inputs,
            documents=documents,
            recorded_at_by_event=event_times,
        )
        relative_ref = assembly_bundle_relative_ref(
            cycle_index=1,
            bundle_digest=bundle["assembly_bundle_digest"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalV31ResearchStore(root)
            store.write_document(
                relative_ref=relative_ref,
                document=bundle,
                digest_field="assembly_bundle_digest",
            )
            tampered = dict(bundle)
            tampered["selection_plan"] = {
                **tampered["selection_plan"],
                "reason": "re-signed replacement",
            }
            tampered.pop("assembly_bundle_digest")
            tampered = self_digest(tampered, "assembly_bundle_digest")
            (root / relative_ref).write_bytes(canonical_bytes(tampered) + b"\n")
            with self.assertRaisesRegex(
                V31DurableCycleError, "V31_DURABLE_RECOVERY_FAILED_CLOSED"
            ):
                recover_persisted_v31_cycle(
                    store=LocalV31ResearchStore(root),
                    run_id="run:v31",
                    cycle_index=1,
                    total_cycles=1,
                    created_at=DECISION_AT,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalV31ResearchStore(root)
            store.write_document(
                relative_ref=relative_ref,
                document=bundle,
                digest_field="assembly_bundle_digest",
            )
            extra = root / "cycles/0001" / ASSEMBLY_BUNDLE_DIRECTORY / ("f" * 64 + ".json")
            extra.write_bytes(canonical_bytes(bundle) + b"\n")
            with self.assertRaisesRegex(
                V31ResearchStoreError,
                "V31_CONTENT_ADDRESSED_DIRECTORY_AMBIGUOUS",
            ):
                store.discover_content_addressed_document(
                    relative_dir=f"cycles/0001/{ASSEMBLY_BUNDLE_DIRECTORY}",
                    digest_field="assembly_bundle_digest",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
