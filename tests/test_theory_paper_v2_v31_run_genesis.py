from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.test_theory_paper_v2_v31_authorization import _make_chain
from trade_system.theory_paper_v2.application.v31_run_genesis import (
    V31RunGenesisInitializationError,
    initialize_v31_run_genesis,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v31_run_genesis import (
    GENESIS_SOURCE_SPECS,
    RUN_GENESIS_REF,
    checkpoint_genesis_bindings,
    verify_v31_run_genesis_receipt,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    V31_CURRENT_RESEARCH_AUTHORITY_PATH,
    load_v31_active_authorization_chain,
)
from trade_system.theory_paper_v2.infrastructure.v31_research_store import (
    LocalV31ResearchStore,
)


_CREATED_AT = "2026-08-06T16:20:00Z"


def _binding_for_current_authority(
    project: Path, authority: dict[str, Any]
) -> dict[str, Any]:
    path = V31_CURRENT_RESEARCH_AUTHORITY_PATH.as_posix()
    raw = (project / path).read_bytes()
    return {
        "path": path,
        "schema_id": authority["schema_id"],
        "digest_field": "authority_digest",
        "semantic_digest": authority["authority_digest"],
        "physical_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _inputs(project: Path) -> dict[str, Any]:
    _make_chain(project)
    loaded = load_v31_active_authorization_chain(project)
    documents = {
        "theory_approval": loaded["theory_approval"],
        "experiment_contract": loaded["experiment_contract"],
        "experiment_manifest": loaded["manifest"],
        "experiment_authorization": loaded["authorization_receipt"],
        "current_authority": loaded["authority"],
    }
    authority = loaded["authority"]
    global_bindings = {
        "theory_approval": authority["theory_approval_binding"],
        "experiment_contract": authority["experiment_contract_binding"],
        "experiment_manifest": authority["manifest_binding"],
        "experiment_authorization": authority[
            "authorization_receipt_binding"
        ],
        "current_authority": _binding_for_current_authority(
            project, loaded["authority"]
        ),
    }
    global_raw_bytes = {
        role: (project / binding["path"]).read_bytes()
        for role, binding in global_bindings.items()
    }
    return {
        "documents": documents,
        "global_bindings": global_bindings,
        "global_raw_bytes": global_raw_bytes,
    }


def _resign_current_authority(
    inputs: dict[str, Any], changes: dict[str, Any]
) -> None:
    authority = {
        key: value
        for key, value in copy.deepcopy(
            inputs["documents"]["current_authority"]
        ).items()
        if key != "authority_digest"
    }
    authority.update(changes)
    authority = self_digest(authority, "authority_digest")
    raw = canonical_bytes(authority) + b"\n"
    inputs["documents"]["current_authority"] = authority
    inputs["global_raw_bytes"]["current_authority"] = raw
    inputs["global_bindings"]["current_authority"] = {
        **inputs["global_bindings"]["current_authority"],
        "semantic_digest": authority["authority_digest"],
        "physical_sha256": hashlib.sha256(raw).hexdigest(),
    }


class V31RunGenesisTests(unittest.TestCase):
    def test_exact_bytes_receipt_and_checkpoint_bindings_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            run_root = root / "run"
            project.mkdir()
            inputs = _inputs(project)
            store = LocalV31ResearchStore(run_root)

            result = initialize_v31_run_genesis(
                store=store, created_at=_CREATED_AT, **inputs
            )

            receipt = result["run_genesis"]
            checkpoint = result["checkpoint"]
            self.assertEqual("theory_paper_v31_run_genesis", receipt["schema_id"])
            self.assertEqual("RUN_V31_PROSPECTIVE", receipt["operation"])
            self.assertEqual("BTC-USDT-SWAP", receipt["instrument"]["instrument_id"])
            self.assertEqual(8, receipt["cycle_protocol"]["accepted_cycle_count"])
            self.assertEqual(3600, receipt["cycle_protocol"]["cadence_seconds"])
            self.assertEqual(
                "STATIC_COUNTERFACTUAL_FLAT_SHADOW", receipt["portfolio_mode"]
            )
            self.assertFalse(receipt["legacy_runs_resumable"])
            self.assertFalse(receipt["executable"])
            self.assertEqual(
                receipt["genesis_artifacts"][1],
                receipt["experiment_contract_binding"],
            )
            self.assertEqual(
                "experiment_contract",
                receipt["experiment_contract_binding"]["source_role"],
            )
            verify_v31_run_genesis_receipt(
                receipt,
                documents=inputs["documents"],
                global_bindings=inputs["global_bindings"],
            )
            for spec in GENESIS_SOURCE_SPECS:
                self.assertEqual(
                    inputs["global_raw_bytes"][spec.role],
                    (run_root / spec.local_ref).read_bytes(),
                )
            expected = checkpoint_genesis_bindings(
                receipt,
                documents=inputs["documents"],
                global_bindings=inputs["global_bindings"],
            )
            self.assertEqual("1.2.0", checkpoint["schema_version"])
            self.assertEqual("READY_FOR_CYCLE", checkpoint["status"])
            self.assertEqual(0, checkpoint["revision"])
            self.assertTrue(checkpoint["resume_allowed"])
            for field, value in expected.items():
                self.assertEqual(value, checkpoint[field])

    def test_receipt_to_checkpoint_direction_has_no_digest_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            inputs = _inputs(project)
            result = initialize_v31_run_genesis(
                store=LocalV31ResearchStore(root / "run"),
                created_at=_CREATED_AT,
                **inputs,
            )
            receipt = result["run_genesis"]
            serialized = canonical_bytes(receipt)

            self.assertNotIn(b'"checkpoint_digest"', serialized)
            self.assertEqual(
                "FORBIDDEN",
                receipt["checkpoint_initialization_contract"][
                    "back_reference_policy"
                ],
            )
            self.assertEqual(
                receipt["run_genesis_digest"],
                result["checkpoint"]["run_genesis_digest"],
            )
            self.assertEqual(RUN_GENESIS_REF, result["checkpoint"]["run_genesis_ref"])

    def test_exact_reentry_is_idempotent_but_genesis_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            inputs = _inputs(project)
            store = LocalV31ResearchStore(root / "run")
            first = initialize_v31_run_genesis(
                store=store, created_at=_CREATED_AT, **inputs
            )
            second = initialize_v31_run_genesis(
                store=store, created_at=_CREATED_AT, **inputs
            )
            self.assertEqual(first, second)

            with self.assertRaises(V31RunGenesisInitializationError):
                initialize_v31_run_genesis(
                    store=store,
                    created_at="2026-08-06T16:21:00Z",
                    **inputs,
                )
            self.assertEqual(
                first["checkpoint"], store.load_checkpoint(run_id=first["checkpoint"]["run_id"])
            )

    def test_wrong_run_product_or_permission_fails_before_any_write(self) -> None:
        cases = (
            {"authorized_run_id": "wrong-run"},
            {
                "instrument": {
                    "venue": "OKX",
                    "instrument_id": "BTC-USDT",
                    "market_type": "SPOT",
                    "underlying_symbol": "BTC-USDT",
                }
            },
            {"paper_trading": True},
        )
        for changes in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = root / "project"
                run_root = root / "run"
                project.mkdir()
                inputs = _inputs(project)
                _resign_current_authority(inputs, changes)

                with self.assertRaises(V31RunGenesisInitializationError):
                    initialize_v31_run_genesis(
                        store=LocalV31ResearchStore(run_root),
                        created_at=_CREATED_AT,
                        **inputs,
                    )
                self.assertFalse((run_root / "checkpoint.json").exists())
                self.assertFalse((run_root / "genesis").exists())

    def test_global_byte_drift_and_missing_role_fail_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            inputs = _inputs(project)
            inputs["global_raw_bytes"]["theory_approval"] += b" "
            run_root = root / "run"
            with self.assertRaisesRegex(
                V31RunGenesisInitializationError,
                "V31_RUN_GENESIS_SOURCE_BYTES_DRIFT",
            ):
                initialize_v31_run_genesis(
                    store=LocalV31ResearchStore(run_root),
                    created_at=_CREATED_AT,
                    **inputs,
                )
            self.assertFalse((run_root / "checkpoint.json").exists())
            self.assertFalse((run_root / "genesis").exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            inputs = _inputs(project)
            inputs["global_raw_bytes"].pop("experiment_contract")
            run_root = root / "run"
            with self.assertRaisesRegex(
                V31RunGenesisInitializationError,
                "V31_RUN_GENESIS_SOURCE_BYTE_SET_INVALID",
            ):
                initialize_v31_run_genesis(
                    store=LocalV31ResearchStore(run_root),
                    created_at=_CREATED_AT,
                    **inputs,
                )
            self.assertFalse((run_root / "checkpoint.json").exists())
            self.assertFalse((run_root / "genesis").exists())

    def test_partial_genesis_conflict_never_creates_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            run_root = root / "run"
            project.mkdir()
            inputs = _inputs(project)
            store = LocalV31ResearchStore(run_root)
            manifest_ref = next(
                spec.local_ref
                for spec in GENESIS_SOURCE_SPECS
                if spec.role == "experiment_manifest"
            )
            store.write_raw(relative_ref=manifest_ref, payload=b"wrong bytes\n")

            with self.assertRaises(V31RunGenesisInitializationError):
                initialize_v31_run_genesis(
                    store=store, created_at=_CREATED_AT, **inputs
                )

            self.assertTrue((run_root / "genesis/theory-approval.json").is_file())
            self.assertTrue((run_root / "genesis/experiment-contract.json").is_file())
            self.assertEqual(b"wrong bytes\n", (run_root / manifest_ref).read_bytes())
            self.assertFalse((run_root / RUN_GENESIS_REF).exists())
            self.assertFalse((run_root / "checkpoint.json").exists())


if __name__ == "__main__":
    unittest.main()
