from __future__ import annotations

import ast
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from tests.test_theory_paper_v2_v32_public_source_collector import (
    BASE,
    RUN_ID,
    BundleTransport,
    RecordingStore,
    SequenceClock,
    authority,
    component_final_url,
    raw_bundle,
    ts,
)
from trade_system.theory_paper_v2.application.v32_cycle_source_admission import (
    admit_fresh_v32_source_to_cycle,
)
from trade_system.theory_paper_v2.application.v32_durable_source_replay import (
    RECEIPT_DIGEST_FIELD,
    RECEIPT_SCHEMA_ID,
    SCHEMA_VERSION,
    V32DurableSourceReplayError,
    compose_and_persist_v32_durable_source_replay_receipt,
    durable_source_replay_receipt_ref,
    verify_durable_v32_source_replay_receipt,
    verify_v32_durable_source_replay_receipt,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_source_collector import (
    ANALYSIS_BUNDLE_DIGEST_FIELD,
    V32RawFirstOkxPublicBundleCollector,
)
from trade_system.theory_paper_v2.infrastructure.v32_public_evidence_verifier import (
    V32InfrastructurePublicEvidenceVerifier,
)


class ResponseFailureBundleTransport:
    """Fixture transport retaining one optional 503 response before UNKNOWN."""

    def __init__(self) -> None:
        self.calls = 0

    def fetch_once(self, *, instrument_id: str, raw_body_sink) -> bytes:
        self.calls += 1
        if instrument_id != "BTC-USDT-SWAP":
            raise AssertionError("instrument drift")
        bundle = deepcopy(raw_bundle())
        for component in bundle["components"]:
            payload = str(component["body_utf8"]).encode("utf-8")
            http_status = 200
            if component["component_id"] == "OPEN_INTEREST":
                payload = b'{"code":"500","msg":"provider unavailable"}'
                http_status = 503
                component["status"] = "UNKNOWN"
                component["http_status"] = 503
                component["body_utf8"] = None
                component["error_code"] = "PUBLIC_PROVIDER_UNAVAILABLE"
            binding = dict(
                raw_body_sink.seal_component_capture(
                    component_id=component["component_id"],
                    payload=payload,
                    method=component["method"],
                    path=component["path"],
                    query=component["query"],
                    http_status=http_status,
                    final_url=component_final_url(component),
                    request_started_at=component["request_started_at"],
                    response_received_at=component["response_received_at"],
                    capture_completed_at=component["response_received_at"],
                    route_policy_id=(
                        "V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_FIXED_HEADERS_NON_CREDENTIAL_NO_REDIRECT_V3"
                    ),
                )
            )
            component["raw_binding"] = binding
            component["failure_evidence_binding"] = (
                binding
                if component["component_id"] == "OPEN_INTEREST"
                else None
            )
        return canonical_bytes(bundle)


def timeout_bundle() -> dict:
    bundle = raw_bundle(unknown_optional=True)
    for component in bundle["components"]:
        if component["status"] == "UNKNOWN":
            component["error_code"] = "PUBLIC_TIMEOUT"
    return bundle


class V32DurableSourceReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public_evidence_verifier = V32InfrastructurePublicEvidenceVerifier()

    def collect(
        self,
        *,
        store: RecordingStore,
        qualification_id: str,
        transport=None,
    ):
        return V32RawFirstOkxPublicBundleCollector(
            transport=transport or BundleTransport(raw_bundle()),
            clock=SequenceClock(),
            store=store,
        ).collect_and_qualify(
            qualification_id=qualification_id,
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=authority(),
        )

    def admit(
        self,
        *,
        source_store: RecordingStore,
        run_store: LocalV32CycleSourceAdmissionStore,
        qualification_id: str,
        collected,
    ) -> dict:
        return admit_fresh_v32_source_to_cycle(
            source_store=source_store,
            run_store=run_store,
            active_authority=authority(),
            qualification_id=qualification_id,
            run_id=RUN_ID,
            cycle_index=1,
            decision_time=collected.formal_qualification["decision_time"],
            admitted_at=ts(
                BASE + timedelta(seconds=6, microseconds=500_000)
            ),
        )

    def prepare(
        self,
        *,
        qualification_id: str = "q-v32-replay",
        transport=None,
    ):
        source_store = RecordingStore(self.root / f"source-{qualification_id}")
        run_store = LocalV32CycleSourceAdmissionStore(
            self.root / f"run-{qualification_id}"
        )
        collected = self.collect(
            store=source_store,
            qualification_id=qualification_id,
            transport=transport,
        )
        admission = self.admit(
            source_store=source_store,
            run_store=run_store,
            qualification_id=qualification_id,
            collected=collected,
        )
        return source_store, run_store, collected, admission

    def compose(
        self,
        *,
        source_store: RecordingStore,
        run_store: LocalV32CycleSourceAdmissionStore,
        qualification_id: str,
    ) -> dict:
        return compose_and_persist_v32_durable_source_replay_receipt(
            public_evidence_verifier=self.public_evidence_verifier,
            source_store=source_store,
            run_store=run_store,
            active_authority=authority(),
            qualification_id=qualification_id,
            run_id=RUN_ID,
            cycle_index=1,
            replayed_at=ts(BASE + timedelta(seconds=7)),
        )

    def test_application_replay_has_no_infrastructure_reverse_dependency(self) -> None:
        module_path = (
            Path(__file__).parents[1]
            / "trade_system/theory_paper_v2/application/"
            "v32_durable_source_replay.py"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertFalse(
            any(
                module == "infrastructure"
                or module.startswith("infrastructure.")
                for module in imported_modules
            )
        )

    def test_composes_full_physical_and_semantic_replay_for_acceptance(self) -> None:
        source_store, run_store, collected, admission = self.prepare()
        result = self.compose(
            source_store=source_store,
            run_store=run_store,
            qualification_id="q-v32-replay",
        )
        receipt = result["durable_source_replay_receipt"]
        self.assertEqual("1.3.0", SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, receipt["schema_version"])

        self.assertEqual(RECEIPT_SCHEMA_ID, receipt["schema_id"])
        self.assertEqual(
            receipt[RECEIPT_DIGEST_FIELD],
            verify_v32_durable_source_replay_receipt(receipt),
        )
        self.assertEqual(12, len(receipt["request_replays"]))
        self.assertEqual(
            12,
            len({row["request_id"] for row in receipt["request_replays"]}),
        )
        self.assertTrue(
            all(
                row["attempt_number"] == 1
                and row["retry_allowed"] is False
                for row in receipt["request_replays"]
            )
        )
        self.assertEqual(
            collected.public_market_analysis_bundle_binding,
            receipt["market_analysis_bundle_binding"],
        )
        self.assertIn(
            receipt["market_analysis_bundle_binding"]["semantic_digest"],
            collected.pit_registry["members"],
        )
        self.assertEqual(
            admission["cycle_source_admission_binding"],
            receipt["cycle_source_admission_binding"],
        )
        self.assertEqual(
            "EXACT_RAW_RECONSTRUCTION_AND_DERIVED_BYTE_MATCH",
            receipt["raw_before_derived_proof"]["method"],
        )
        self.assertEqual(
            13,
            len(receipt["raw_before_derived_proof"]["sealed_raw_bindings"]),
        )
        self.assertTrue(
            all(
                row["source_binding"]["physical_sha256"]
                == row["target_binding"]["physical_sha256"]
                for row in receipt["run_copy_replays"]
            )
        )
        self.assertEqual(
            {
                "durable_source_replay_receipt_binding",
                "public_market_analysis_bundle_binding",
                "cycle_source_admission_binding",
                "pit_registry_binding",
            },
            set(result["acceptance_inputs"]),
        )
        for binding in result["acceptance_inputs"].values():
            self.assertRegex(binding["semantic_digest"], r"^[0-9a-f]{64}$")
            self.assertRegex(binding["physical_sha256"], r"^[0-9a-f]{64}$")

        replayed = verify_durable_v32_source_replay_receipt(
            public_evidence_verifier=self.public_evidence_verifier,
            source_store=source_store,
            run_store=run_store,
            active_authority=authority(),
            qualification_id="q-v32-replay",
            run_id=RUN_ID,
            cycle_index=1,
        )
        self.assertEqual(result["acceptance_inputs"], replayed["acceptance_inputs"])

    def test_tampered_per_request_raw_fails_closed(self) -> None:
        source_store, run_store, _, _ = self.prepare(
            qualification_id="q-v32-tamper"
        )
        target = (
            source_store.root
            / "qualifications/q-v32-tamper/raw/requests/mark-price.body"
        )
        target.write_bytes(b"{}")
        with self.assertRaises(V32DurableSourceReplayError):
            self.compose(
                source_store=source_store,
                run_store=run_store,
                qualification_id="q-v32-tamper",
            )

    def test_timeout_unknown_requests_bind_typed_failure_receipts(self) -> None:
        qualification_id = "q-v32-replay-unknown"
        source_store = RecordingStore(self.root / "source-unknown")
        run_store = LocalV32CycleSourceAdmissionStore(self.root / "run-unknown")
        transport = BundleTransport(timeout_bundle())
        collected = V32RawFirstOkxPublicBundleCollector(
            transport=transport,
            clock=SequenceClock(),
            store=source_store,
        ).collect_and_qualify(
            qualification_id=qualification_id,
            run_id=RUN_ID,
            cycle_index=1,
            active_authority=authority(),
        )
        self.admit(
            source_store=source_store,
            run_store=run_store,
            qualification_id=qualification_id,
            collected=collected,
        )
        result = self.compose(
            source_store=source_store,
            run_store=run_store,
            qualification_id=qualification_id,
        )
        receipt = result["durable_source_replay_receipt"]
        self.assertEqual(1, transport.calls)
        unknown = [
            row for row in receipt["request_replays"]
            if row["status"] == "UNKNOWN"
        ]
        self.assertEqual(4, len(unknown))
        self.assertTrue(
            all(
                row["raw_binding"] is None
                and row["http_status"] is None
                and row["error_code"] == "PUBLIC_TIMEOUT"
                and "/component-failures/"
                in row["failure_evidence_binding"]["relative_ref"]
                for row in unknown
            )
        )
        self.assertEqual(
            9,
            len(receipt["raw_before_derived_proof"]["sealed_raw_bindings"]),
        )
        self.assertEqual(
            [row["failure_evidence_binding"] for row in unknown],
            receipt["raw_before_derived_proof"][
                "verified_no_response_failure_bindings"
            ],
        )
        verify_durable_v32_source_replay_receipt(
            public_evidence_verifier=self.public_evidence_verifier,
            source_store=source_store,
            run_store=run_store,
            active_authority=authority(),
            qualification_id=qualification_id,
            run_id=RUN_ID,
            cycle_index=1,
        )
        self.assertEqual(1, transport.calls)

    def test_503_unknown_replays_its_sealed_raw_and_capture(self) -> None:
        qualification_id = "q-v32-replay-503"
        transport = ResponseFailureBundleTransport()
        source_store, run_store, _, _ = self.prepare(
            qualification_id=qualification_id,
            transport=transport,
        )

        result = self.compose(
            source_store=source_store,
            run_store=run_store,
            qualification_id=qualification_id,
        )
        receipt = result["durable_source_replay_receipt"]
        row = receipt["request_replays"][8]

        self.assertEqual("OPEN_INTEREST", row["component_id"])
        self.assertEqual("UNKNOWN", row["status"])
        self.assertEqual(503, row["http_status"])
        self.assertEqual(row["raw_binding"], row["failure_evidence_binding"])
        self.assertIn(
            row["raw_binding"],
            receipt["raw_before_derived_proof"]["sealed_raw_bindings"],
        )
        self.assertEqual(
            [],
            receipt["raw_before_derived_proof"][
                "verified_no_response_failure_bindings"
            ],
        )
        verify_durable_v32_source_replay_receipt(
            public_evidence_verifier=self.public_evidence_verifier,
            source_store=source_store,
            run_store=run_store,
            active_authority=authority(),
            qualification_id=qualification_id,
            run_id=RUN_ID,
            cycle_index=1,
        )
        self.assertEqual(1, transport.calls)

    def test_503_raw_or_capture_missing_tampered_or_swapped_fails_offline(self) -> None:
        for mutation in ("missing", "tampered", "swapped"):
            with self.subTest(mutation=mutation):
                qualification_id = f"q-v32-replay-503-{mutation}"
                transport = ResponseFailureBundleTransport()
                source_store, run_store, _, _ = self.prepare(
                    qualification_id=qualification_id,
                    transport=transport,
                )
                base = source_store.root / f"qualifications/{qualification_id}"
                raw = base / "raw/requests/open-interest.body"
                capture = base / "component-captures/open-interest.json"
                other_capture = base / "component-captures/funding-rate.json"
                if mutation == "missing":
                    capture.unlink()
                elif mutation == "tampered":
                    raw.write_bytes(raw.read_bytes() + b" ")
                else:
                    capture_bytes = capture.read_bytes()
                    other_bytes = other_capture.read_bytes()
                    capture.write_bytes(other_bytes)
                    other_capture.write_bytes(capture_bytes)
                with self.assertRaises(V32DurableSourceReplayError):
                    self.compose(
                        source_store=source_store,
                        run_store=run_store,
                        qualification_id=qualification_id,
                    )
                self.assertEqual(1, transport.calls)

    def test_timeout_receipt_missing_tampered_or_swapped_fails_offline(self) -> None:
        for mutation in ("missing", "tampered", "swapped"):
            with self.subTest(mutation=mutation):
                qualification_id = f"q-v32-replay-timeout-{mutation}"
                transport = BundleTransport(timeout_bundle())
                source_store, run_store, _, _ = self.prepare(
                    qualification_id=qualification_id,
                    transport=transport,
                )
                base = source_store.root / f"qualifications/{qualification_id}"
                receipt = base / "component-failures/open-interest.json"
                other_receipt = base / "component-failures/funding-rate.json"
                if mutation == "missing":
                    receipt.unlink()
                elif mutation == "tampered":
                    receipt.write_bytes(receipt.read_bytes() + b"\n")
                else:
                    receipt_bytes = receipt.read_bytes()
                    other_bytes = other_receipt.read_bytes()
                    receipt.write_bytes(other_bytes)
                    other_receipt.write_bytes(receipt_bytes)
                with self.assertRaises(V32DurableSourceReplayError):
                    self.compose(
                        source_store=source_store,
                        run_store=run_store,
                        qualification_id=qualification_id,
                    )
                self.assertEqual(1, transport.calls)

    def test_missing_per_request_raw_fails_closed(self) -> None:
        source_store, run_store, _, _ = self.prepare(
            qualification_id="q-v32-missing"
        )
        target = (
            source_store.root
            / "qualifications/q-v32-missing/raw/requests/mark-price.body"
        )
        target.unlink()
        with self.assertRaises(V32DurableSourceReplayError):
            self.compose(
                source_store=source_store,
                run_store=run_store,
                qualification_id="q-v32-missing",
            )

    def test_semantically_equivalent_nonidentical_raw_fails_closed(self) -> None:
        source_store, run_store, _, _ = self.prepare(
            qualification_id="q-v32-equivalent"
        )
        target = (
            source_store.root
            / "qualifications/q-v32-equivalent/raw/requests/mark-price.body"
        )
        target.write_bytes(target.read_bytes() + b" ")
        with self.assertRaises(V32DurableSourceReplayError):
            self.compose(
                source_store=source_store,
                run_store=run_store,
                qualification_id="q-v32-equivalent",
            )

    def test_self_resigned_duplicate_request_receipt_is_rejected(self) -> None:
        source_store, run_store, _, _ = self.prepare(
            qualification_id="q-v32-duplicate"
        )
        result = self.compose(
            source_store=source_store,
            run_store=run_store,
            qualification_id="q-v32-duplicate",
        )
        forged = deepcopy(result["durable_source_replay_receipt"])
        forged["request_replays"][1]["request_id"] = forged[
            "request_replays"
        ][0]["request_id"]
        forged["transaction_proof"]["request_ids"] = [
            row["request_id"] for row in forged["request_replays"]
        ]
        forged = self_digest(forged, RECEIPT_DIGEST_FIELD)
        with self.assertRaises(V32DurableSourceReplayError):
            verify_v32_durable_source_replay_receipt(forged)

    def test_legacy_replay_schema_is_rejected_at_explicit_boundary(self) -> None:
        source_store, run_store, _, _ = self.prepare(
            qualification_id="q-v32-legacy-replay-schema"
        )
        receipt = deepcopy(
            self.compose(
                source_store=source_store,
                run_store=run_store,
                qualification_id="q-v32-legacy-replay-schema",
            )["durable_source_replay_receipt"]
        )
        receipt["schema_version"] = "1.0.0"
        receipt = self_digest(receipt, RECEIPT_DIGEST_FIELD)

        with self.assertRaisesRegex(
            V32DurableSourceReplayError,
            "V32_DURABLE_SOURCE_REPLAY_SCHEMA_VERSION_UNSUPPORTED",
        ):
            verify_v32_durable_source_replay_receipt(receipt)

    def test_wrong_source_transaction_cannot_replay_admitted_transaction(self) -> None:
        source_store = RecordingStore(self.root / "source-wrong-transaction")
        source_a = self.collect(
            store=source_store, qualification_id="q-v32-transaction-a"
        )
        source_b = self.collect(
            store=source_store, qualification_id="q-v32-transaction-b"
        )
        run_store = LocalV32CycleSourceAdmissionStore(
            self.root / "run-wrong-transaction"
        )
        self.admit(
            source_store=source_store,
            run_store=run_store,
            qualification_id="q-v32-transaction-b",
            collected=source_b,
        )
        self.assertNotEqual(
            source_a.formal_qualification_binding,
            source_b.formal_qualification_binding,
        )
        with self.assertRaises(V32DurableSourceReplayError):
            self.compose(
                source_store=source_store,
                run_store=run_store,
                qualification_id="q-v32-transaction-a",
            )

    def test_noncanonical_receipt_bytes_are_rejected_on_durable_replay(self) -> None:
        source_store, run_store, _, _ = self.prepare(
            qualification_id="q-v32-receipt-equivalent"
        )
        self.compose(
            source_store=source_store,
            run_store=run_store,
            qualification_id="q-v32-receipt-equivalent",
        )
        receipt_path = run_store.root / durable_source_replay_receipt_ref(1)
        receipt_path.write_bytes(receipt_path.read_bytes() + b"\n")
        with self.assertRaises(V32DurableSourceReplayError):
            verify_durable_v32_source_replay_receipt(
                public_evidence_verifier=self.public_evidence_verifier,
                source_store=source_store,
                run_store=run_store,
                active_authority=authority(),
                qualification_id="q-v32-receipt-equivalent",
                run_id=RUN_ID,
                cycle_index=1,
            )

    def test_duplicate_request_in_source_analysis_fails_reconstruction(self) -> None:
        source_store, run_store, collected, _ = self.prepare(
            qualification_id="q-v32-source-duplicate"
        )
        forged = deepcopy(collected.public_market_analysis_bundle)
        forged["request_raw_bindings"][1]["request_id"] = forged[
            "request_raw_bindings"
        ][0]["request_id"]
        forged = self_digest(forged, ANALYSIS_BUNDLE_DIGEST_FIELD)
        target = (
            source_store.root
            / "qualifications/q-v32-source-duplicate/"
            "public-market-analysis-bundle.json"
        )
        target.write_bytes(canonical_bytes(forged) + b"\n")
        with self.assertRaises(V32DurableSourceReplayError):
            self.compose(
                source_store=source_store,
                run_store=run_store,
                qualification_id="q-v32-source-duplicate",
            )


if __name__ == "__main__":
    unittest.main()
