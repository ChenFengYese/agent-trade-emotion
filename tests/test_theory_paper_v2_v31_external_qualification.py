from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.test_theory_paper_v2_v31_authorization import _make_chain
from trade_system.theory_paper_v2.application.v31_external_qualification import (
    V31ExternalQualificationWorkflowError,
    build_q6_receipt_from_durable_qualification,
    verify_q6_receipt_durable_artifacts,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.governance.v31_external_qualification import (
    V31ExternalQualificationError,
    build_q7_agent_transport_receipt,
    required_external_gate_evidence_paths,
    verify_external_typed_qualification_receipt,
)


_FRESH_ID = "v31-source-qualification-semantic-compiler-fixture"
_HISTORICAL_NONE_E0_ID = "v31-source-qualification-20260806t161918z"
_FAILED_ID = "v31-source-qualification-20260806t161618z"
_SOURCE_PROJECT = Path(__file__).resolve().parents[1]


class V31ExternalQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.chain = _make_chain(self.project)
        self.manifest = copy.deepcopy(self.chain["manifest"])
        for path in required_external_gate_evidence_paths("Q6"):
            target = self.project / path
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = f"# exact Q6 evidence for {path}\n".encode("utf-8")
            target.write_bytes(payload)
            self.manifest["implementation_bindings"][path] = hashlib.sha256(
                payload
            ).hexdigest()

    def _copy_qualification(self, qualification_id: str) -> str:
        source = (
            _SOURCE_PROJECT
            / "agent-cluster/experiments/v31-qualifications"
            / qualification_id
        )
        relative = (
            "agent-cluster/experiments/v31-qualifications/"
            f"{qualification_id}"
        )
        target = self.project / relative
        if not target.exists():
            shutil.copytree(source, target)
        return relative

    def _build_success(self) -> dict[str, object]:
        relative = (
            "agent-cluster/experiments/v31-qualifications/" f"{_FRESH_ID}"
        )
        return build_q6_receipt_from_durable_qualification(
            project_root=self.project,
            qualification_root_ref=relative,
            qualification_id=_FRESH_ID,
            evaluated_at="2026-08-06T16:20:00Z",
            experiment_contract=self.chain["experiment_contract"],
            manifest=self.manifest,
        )

    def test_q6_receipt_requires_full_durable_replay_and_reconstructs(self) -> None:
        receipt = self._build_success()
        self.assertEqual("Q6", receipt["gate_id"])
        self.assertEqual("PASS", receipt["verdict"])
        self.assertEqual(5, len(receipt["checks"]))
        self.assertEqual(
            receipt["qualification_receipt_digest"],
            verify_external_typed_qualification_receipt(
                receipt,
                expected_gate_id="Q6",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            ),
        )
        evidence = receipt["qualification_evidence"]
        self.assertEqual("SEALED", evidence["checkpoint"]["status"])
        self.assertTrue(evidence["completion"]["required_requests_complete"])
        self.assertTrue(
            evidence["completion"]["raw_bytes_read_back_and_verified"]
        )
        self.assertFalse(evidence["completion"]["missing_is_zero"])
        self.assertFalse(evidence["completion"]["executable"])
        self.assertEqual(
            evidence["completion"]["source_qualification_completion_digest"],
            verify_q6_receipt_durable_artifacts(
                project_root=self.project, receipt=receipt
            ),
        )

    def test_q6_rejects_raw_byte_drift_before_receipt_construction(self) -> None:
        relative = (
            "agent-cluster/experiments/v31-qualifications/" f"{_FRESH_ID}"
        )
        raw = (
            self.project
            / relative
            / "cycles/0001/market/raw/okx-native-ticker.body"
        )
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            build_q6_receipt_from_durable_qualification(
                project_root=self.project,
                qualification_root_ref=relative,
                qualification_id=_FRESH_ID,
                evaluated_at="2026-08-06T16:20:00Z",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            )

    def test_q6_rejects_failed_closed_attempt_and_bare_digest_receipt(self) -> None:
        relative = self._copy_qualification(_FAILED_ID)
        with self.assertRaisesRegex(
            ValueError, "V31_SOURCE_QUALIFICATION_NOT_DURABLY_SEALED"
        ):
            build_q6_receipt_from_durable_qualification(
                project_root=self.project,
                qualification_root_ref=relative,
                qualification_id=_FAILED_ID,
                evaluated_at="2026-08-06T16:20:00Z",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            )

        generic = self_digest(
            {
                "schema_id": "theory_paper_v31_qualification_gate_receipt",
                "schema_version": "1.0.0",
                "gate_id": "Q6",
                "evaluated_at": "2026-08-06T16:20:00Z",
                "verdict": "PASS",
                "evidence_digests": ["a" * 64],
                "limitations": [],
                "external_execution_authority": "NONE_LOCAL_SIMULATION",
                "executable": False,
            },
            "qualification_receipt_digest",
        )
        with self.assertRaisesRegex(
            V31ExternalQualificationError,
            "EXTERNAL_QUALIFICATION_RECEIPT_INVALID",
        ):
            verify_external_typed_qualification_receipt(
                generic,
                expected_gate_id="Q6",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            )

    def test_q6_resigned_embedded_completion_drift_fails(self) -> None:
        receipt = copy.deepcopy(self._build_success())
        receipt.pop("qualification_receipt_digest")
        receipt["qualification_evidence"]["completion"][
            "required_requests_complete"
        ] = False
        receipt = self_digest(receipt, "qualification_receipt_digest")
        with self.assertRaisesRegex(
            V31ExternalQualificationError, "Q6_EVIDENCE_DOCUMENT_INVALID"
        ):
            verify_external_typed_qualification_receipt(
                receipt,
                expected_gate_id="Q6",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            )

    def test_q6_old_typed_receipt_schema_is_not_silently_accepted(self) -> None:
        receipt = copy.deepcopy(self._build_success())
        receipt.pop("qualification_receipt_digest")
        receipt["schema_version"] = "1.0.0"
        receipt = self_digest(receipt, "qualification_receipt_digest")
        with self.assertRaisesRegex(
            V31ExternalQualificationError,
            "EXTERNAL_QUALIFICATION_RECEIPT_INVALID",
        ):
            verify_external_typed_qualification_receipt(
                receipt,
                expected_gate_id="Q6",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            )

    def test_q6_root_must_be_contained_and_match_qualification_id(self) -> None:
        relative = (
            "agent-cluster/experiments/v31-qualifications/" f"{_FRESH_ID}"
        )
        with self.assertRaisesRegex(
            V31ExternalQualificationWorkflowError,
            "V31_Q6_QUALIFICATION_ROOT_IDENTITY_INVALID",
        ):
            build_q6_receipt_from_durable_qualification(
                project_root=self.project,
                qualification_root_ref=relative,
                qualification_id="v31-source-qualification-different",
                evaluated_at="2026-08-06T16:20:00Z",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            )

    def test_q6_rejects_historical_nested_none_e0_authority(self) -> None:
        relative = self._copy_qualification(_HISTORICAL_NONE_E0_ID)
        with self.assertRaisesRegex(
            V31ExternalQualificationError,
            "Q6_EVIDENCE_RETIRED_EXECUTION_AUTHORITY",
        ):
            build_q6_receipt_from_durable_qualification(
                project_root=self.project,
                qualification_root_ref=relative,
                qualification_id=_HISTORICAL_NONE_E0_ID,
                evaluated_at="2026-08-06T16:20:00Z",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
            )

    def test_opaque_or_legacy_shaped_transport_cannot_close_q7(self) -> None:
        with self.assertRaisesRegex(
            V31ExternalQualificationError,
            "Q7_EVIDENCE_SCHEMA_INVALID",
        ):
            build_q7_agent_transport_receipt(
                evaluated_at="2026-08-06T16:21:00Z",
                experiment_contract=self.chain["experiment_contract"],
                manifest=self.manifest,
                qualification_evidence={},
            )


if __name__ == "__main__":
    unittest.main()
