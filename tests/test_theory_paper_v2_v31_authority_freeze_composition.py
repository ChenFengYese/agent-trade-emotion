from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_theory_paper_v2_v31_authorization import (
    _Q6_QUALIFICATION_ID,
    _Q6_ROOT_REF,
    _Q7_ROOT_REF,
    _RUN_ID as _AUTHORIZATION_FIXTURE_RUN_ID,
    _create_no_network_q7_fixture,
)
from trade_system.theory_paper_v2.application.v31_external_qualification import (
    build_q6_receipt_from_durable_qualification,
    build_q7_receipt_from_completed_authoring_transport,
)
from trade_system.theory_paper_v2.application.v31_authority_freeze import (
    GATE_IDS,
    V31_PRODUCTION_RUNTIME_PATHS,
)
from trade_system.theory_paper_v2.domain.governance.v31_authorization import (
    V31AuthorizationError,
)
from trade_system.theory_paper_v2.domain.governance.v31_experiment_qualification import (
    TYPED_QUALIFICATION_GATE_IDS,
    build_typed_qualification_receipt,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    load_v31_active_authorization_chain,
)
from trade_system.theory_paper_v2.presentation.v31_authority_freeze_composition import (
    ACTIVE_AUTHORITY_PATH,
    PREDECESSOR_AUTHORITY_PATH,
    THEORY_APPROVAL_PATH,
    V31AuthorityFreezeCompositionError,
    finalize_v31_active_authority,
    freeze_v31_qualification_subject,
    initialize_v31_run_genesis_from_active_authority,
    verify_external_qualification_physical_replay,
    v31_authority_freeze_paths,
)


_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_RUN_ID = _AUTHORIZATION_FIXTURE_RUN_ID


def _copy_file(source_root: Path, project: Path, relative_path: str) -> None:
    target = project / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / relative_path, target)


def _project_fixture(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    for relative_path in V31_PRODUCTION_RUNTIME_PATHS:
        _copy_file(_SOURCE_ROOT, project, relative_path)
    for relative_path in (THEORY_APPROVAL_PATH, PREDECESSOR_AUTHORITY_PATH):
        _copy_file(_SOURCE_ROOT, project, relative_path)
    _copy_file(
        _SOURCE_ROOT,
        project,
        "theory/history/RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md",
    )
    return project


def _freeze(project: Path) -> dict[str, object]:
    return freeze_v31_qualification_subject(
        project_root=project,
        run_id=_RUN_ID,
        contract_id="v31-minimal-experiment-contract-20260806t180000z",
        manifest_id="v31-frozen-manifest-20260806t180100z",
        contract_frozen_at="2026-08-06T18:00:00Z",
        subject_created_at="2026-08-06T18:01:00Z",
    )


def _qualification_receipts(
    project: Path, phase_a: dict[str, object]
) -> dict[str, dict[str, object]]:
    """Build Q0-Q8 from real no-network Q6/Q7 durable evidence."""

    contract = phase_a["experiment_contract"]
    manifest = phase_a["manifest_subject"]
    approval = phase_a["theory_approval"]
    assert isinstance(contract, dict)
    assert isinstance(manifest, dict)
    assert isinstance(approval, dict)
    _create_no_network_q7_fixture(
        project,
        experiment_contract=contract,
        theory_approval=approval,
    )

    receipts: dict[str, dict[str, object]] = {}
    for index, gate_id in enumerate(GATE_IDS):
        evaluated_at = f"2026-08-06T18:{10 + index:02d}:00Z"
        if gate_id in TYPED_QUALIFICATION_GATE_IDS:
            receipt = build_typed_qualification_receipt(
                gate_id=gate_id,
                evaluated_at=evaluated_at,
                experiment_contract=contract,
                manifest=manifest,
                theory_approval=approval,
            )
        elif gate_id == "Q6":
            receipt = build_q6_receipt_from_durable_qualification(
                project_root=project,
                qualification_root_ref=_Q6_ROOT_REF,
                qualification_id=_Q6_QUALIFICATION_ID,
                evaluated_at=evaluated_at,
                experiment_contract=contract,
                manifest=manifest,
            )
        else:
            receipt = build_q7_receipt_from_completed_authoring_transport(
                project_root=project,
                qualification_root_ref=_Q7_ROOT_REF,
                subject_run_id=_RUN_ID,
                evaluated_at=evaluated_at,
                experiment_contract=contract,
                manifest=manifest,
            )
        receipts[gate_id] = receipt
    return receipts


class V31AuthorityFreezeCompositionTests(unittest.TestCase):
    def test_runtime_freeze_covers_full_formal_cycle_and_no_artifacts_or_docs(self) -> None:
        required = {
            "tests/test_theory_paper_v2_v31_agent_transport.py",
            "tests/test_theory_paper_v2_v31_cycle_source_admission.py",
            "tests/test_theory_paper_v2_v31_durable_bundle.py",
            "tests/test_theory_paper_v2_v31_formal_cycle_composition.py",
            "tests/test_theory_paper_v2_v31_public_outcome_adapter.py",
            "tests/test_theory_paper_v2_v31_research_store.py",
            "tests/test_theory_paper_v2_v31_semantic_compiler.py",
            "trade_system/theory_paper_v2/application/v31_agent_transport.py",
            "trade_system/theory_paper_v2/application/v31_cycle_source_admission.py",
            "trade_system/theory_paper_v2/application/v31_durable_bundle.py",
            "trade_system/theory_paper_v2/application/v31_durable_cycle.py",
            "trade_system/theory_paper_v2/application/v31_formal_cycle.py",
            "trade_system/theory_paper_v2/application/v31_research_cycle.py",
            "trade_system/theory_paper_v2/infrastructure/v31_agent_transport_store.py",
            "trade_system/theory_paper_v2/infrastructure/v31_public_outcome_adapter.py",
            "trade_system/theory_paper_v2/infrastructure/v31_research_store.py",
            "trade_system/theory_paper_v2/infrastructure/v31_semantic_compiler.py",
            "trade_system/theory_paper_v2/presentation/v31_formal_cycle_composition.py",
        }
        self.assertEqual(
            len(V31_PRODUCTION_RUNTIME_PATHS),
            len(set(V31_PRODUCTION_RUNTIME_PATHS)),
        )
        self.assertTrue(required.issubset(V31_PRODUCTION_RUNTIME_PATHS))
        self.assertTrue(
            all(
                path.startswith(("tests/", "trade_system/theory_paper_v2/"))
                and not path.endswith((".json", ".md"))
                and "/experiments/" not in path
                for path in V31_PRODUCTION_RUNTIME_PATHS
            )
        )

    def test_phase_a_freezes_exact_subject_without_authority_or_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project_fixture(Path(directory))
            result = _freeze(project)
            paths = v31_authority_freeze_paths(_RUN_ID)

            self.assertEqual(
                "QUALIFICATION_SUBJECT_FROZEN_AUTHORITY_NOT_CREATED",
                result["status"],
            )
            self.assertTrue((project / paths["experiment_contract"]).is_file())
            self.assertTrue((project / paths["qualification_subject"]).is_file())
            self.assertFalse((project / paths["final_manifest"]).exists())
            self.assertFalse((project / paths["authorization_receipt"]).exists())
            self.assertFalse((project / ACTIVE_AUTHORITY_PATH).exists())
            self.assertFalse((project / "checkpoint.json").exists())
            self.assertEqual(
                V31_PRODUCTION_RUNTIME_PATHS,
                tuple(result["manifest_subject"]["implementation_bindings"]),
            )
            self.assertEqual({}, result["manifest_subject"]["qualification_gates"])
            self.assertFalse(result["subject_freeze"]["executable"])

            # Exact re-entry is idempotent and returns the same frozen subject.
            second = _freeze(project)
            self.assertEqual(result["subject_freeze"], second["subject_freeze"])

    def test_phase_a_fails_before_write_when_one_runtime_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project_fixture(Path(directory))
            missing = V31_PRODUCTION_RUNTIME_PATHS[-1]
            (project / missing).unlink()
            paths = v31_authority_freeze_paths(_RUN_ID)

            with self.assertRaises(V31AuthorityFreezeCompositionError):
                _freeze(project)
            self.assertFalse((project / paths["experiment_contract"]).exists())
            self.assertFalse((project / paths["qualification_subject"]).exists())
            self.assertFalse((project / ACTIVE_AUTHORITY_PATH).exists())

    def test_every_runtime_byte_drift_blocks_phase_b_before_any_receipt_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project_fixture(Path(directory))
            _freeze(project)
            paths = v31_authority_freeze_paths(_RUN_ID)

            for relative_path in V31_PRODUCTION_RUNTIME_PATHS:
                drifted = project / relative_path
                original = drifted.read_bytes()
                drifted.write_bytes(original + b"\n# drift\n")
                with self.subTest(
                    relative_path=relative_path
                ), self.assertRaisesRegex(
                    V31AuthorityFreezeCompositionError,
                    "V31_FREEZE_PHASE_B_FAILED",
                ):
                    finalize_v31_active_authority(
                        project_root=project,
                        run_id=_RUN_ID,
                        qualification_receipts={},
                        authorization_id="v31-authorization-20260806t183000z",
                        authority_id="v31-authority-20260806t183000z",
                        issued_at="2026-08-06T18:30:00Z",
                        recorded_at="2026-08-06T18:31:00Z",
                    )
                drifted.write_bytes(original)
            self.assertTrue(
                all(
                    not (project / path).exists()
                    for path in paths["qualification_receipts"].values()
                )
            )
            self.assertFalse((project / paths["final_manifest"]).exists())
            self.assertFalse((project / ACTIVE_AUTHORITY_PATH).exists())

    def test_real_q6_q7_phase_b_loader_active_and_genesis_chain_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _project_fixture(root)
            phase_a = _freeze(project)
            receipts = _qualification_receipts(project, phase_a)
            for gate_id in ("Q6", "Q7"):
                self.assertEqual(
                    "theory_paper_v31_typed_qualification_gate_receipt",
                    receipts[gate_id]["schema_id"],
                )
                self.assertEqual("PASS", receipts[gate_id]["verdict"])

            finalized = finalize_v31_active_authority(
                project_root=project,
                run_id=_RUN_ID,
                qualification_receipts=receipts,
                authorization_id="v31-authorization-20260806t183000z",
                authority_id="v31-authority-20260806t183000z",
                issued_at="2026-08-06T18:30:00Z",
                recorded_at="2026-08-06T18:31:00Z",
            )

            self.assertEqual(
                "ACTIVE_FROZEN_RESEARCH_NOT_YET_GENESIS_INITIALIZED",
                finalized["status"],
            )
            loaded = load_v31_active_authorization_chain(project)
            self.assertEqual(_RUN_ID, loaded["authority"]["authorized_run_id"])
            self.assertEqual(set(GATE_IDS), set(loaded["qualification_receipts"]))
            self.assertFalse(loaded["authority"]["executable"])

            genesis = initialize_v31_run_genesis_from_active_authority(
                project_root=project,
                run_root=root / "formal-run",
                created_at="2026-08-06T18:32:00Z",
            )
            self.assertEqual("READY_FOR_CYCLE", genesis["checkpoint"]["status"])
            self.assertEqual(0, genesis["checkpoint"]["revision"])
            self.assertFalse(genesis["run_genesis"]["executable"])

            # Both external typed receipts were physically replayed before
            # publication and by the final loader.  Either retained-byte drift
            # makes the ACTIVE chain unusable, never silently accepted.
            for relative_path in (
                (
                    f"{_Q6_ROOT_REF}/cycles/0001/market/raw/"
                    "okx-native-ticker.body"
                ),
                (
                    f"{_Q7_ROOT_REF}/cycles/0001/agent-transport/"
                    "compilation/compiled-assembly-bundle.json"
                ),
            ):
                artifact = project / relative_path
                original = artifact.read_bytes()
                artifact.write_bytes(original + b" ")
                with self.subTest(relative_path=relative_path), self.assertRaises(
                    V31AuthorizationError
                ):
                    load_v31_active_authorization_chain(project)
                artifact.write_bytes(original)

    def test_q7_missing_physical_replay_hook_is_explicitly_fail_closed(self) -> None:
        receipts = {gate_id: {"gate_id": gate_id} for gate_id in GATE_IDS}
        target = (
            "trade_system.theory_paper_v2.application.v31_external_qualification."
            "verify_q7_receipt_durable_artifacts"
        )
        with tempfile.TemporaryDirectory() as directory, patch(
            "trade_system.theory_paper_v2.presentation."
            "v31_authority_freeze_composition."
            "verify_q6_receipt_durable_artifacts",
            return_value=None,
        ), patch(target, None, create=True):
            with self.assertRaisesRegex(
                V31AuthorityFreezeCompositionError,
                "V31_FREEZE_Q7_DURABLE_REPLAY_NOT_AVAILABLE",
            ):
                verify_external_qualification_physical_replay(
                    project_root=Path(directory), receipts=receipts
                )

    def test_second_run_subject_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = _project_fixture(Path(directory))
            _freeze(project)
            with self.assertRaisesRegex(
                V31AuthorityFreezeCompositionError,
                "V31_FREEZE_ANOTHER_RUN_ALREADY_FROZEN",
            ):
                freeze_v31_qualification_subject(
                    project_root=project,
                    run_id="v31-prospective-btcusdt-20260806t190000z",
                    contract_id="v31-minimal-experiment-contract-20260806t190000z",
                    manifest_id="v31-frozen-manifest-20260806t190100z",
                    contract_frozen_at="2026-08-06T19:00:00Z",
                    subject_created_at="2026-08-06T19:01:00Z",
                )


if __name__ == "__main__":
    unittest.main()
