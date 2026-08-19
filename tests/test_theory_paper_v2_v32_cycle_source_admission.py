from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.application.v32_cycle_source_admission import (
    V32CycleSourceAdmissionWorkflowError,
    admit_fresh_v32_source_to_cycle,
    verify_durable_v32_cycle_source_admission,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    self_digest,
)
from trade_system.theory_paper_v2.domain.v32_cycle_source_admission import (
    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD,
    CAPTURE_DIGEST_FIELD,
    FULL_LOADER_DIGEST_FIELD,
    FULL_LOADER_SCHEMA_ID,
    GOVERNING_AUTHORITY_DIGEST_FIELD,
    QUALIFICATION_DIGEST_FIELD,
    SNAPSHOT_DIGEST_FIELD,
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_VERSION,
    V32CycleSourceAdmissionError,
    build_v32_active_authority_projection,
    build_v32_cycle_source_full_loader_receipt,
    build_v32_formal_source_qualification,
    build_v32_pit_evidence_registry,
    build_v32_public_market_snapshot,
    build_v32_public_source_capture,
    qualification_ref,
    seal_v32_cycle_source_admission,
    verify_v32_cycle_source_admission,
    verify_v32_cycle_source_full_loader_receipt,
)
from trade_system.theory_paper_v2.infrastructure.v32_cycle_source_admission_store import (
    LocalV32CycleSourceAdmissionStore,
    V32CycleSourceAdmissionStoreError,
)


RUN_ID = "run:v32:typed-source-admission"
CONTRACT_DIGEST = "c" * 64
BASE = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)


def ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def token(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def authority() -> dict:
    return build_v32_active_authority_projection(
        run_id=RUN_ID,
        recorded_at=ts(BASE),
        experiment_contract_digest=CONTRACT_DIGEST,
        governing_authority_binding={
            "relative_ref": "config/v32/governing-authority.json",
            "schema_id": "theory_paper_v32_current_research_authority_v1",
            "digest_field": "authority_digest",
            "semantic_digest": "a" * 64,
            "physical_sha256": "b" * 64,
        },
    )


def write_source_bundle(
    store: LocalV32CycleSourceAdmissionStore,
    *,
    cycle: int,
    decision: datetime,
    qid: str | None = None,
    stale: bool = False,
    pre_authority: bool = False,
    capture_boundary_mutations: dict[str, object] | None = None,
    capture_attempt_number: int = 1,
) -> tuple[str, str]:
    qid = qid or f"v32-source-q-{cycle:04d}"
    if stale:
        started = BASE + timedelta(minutes=1)
        capture_started = BASE + timedelta(minutes=2)
        received = BASE + timedelta(minutes=3)
        completed = BASE + timedelta(minutes=4)
    else:
        started = decision - timedelta(seconds=120)
        capture_started = decision - timedelta(seconds=100)
        received = decision - timedelta(seconds=90)
        completed = decision - timedelta(seconds=60)
    admitted = decision + timedelta(seconds=30)
    raw_ref = f"qualifications/{qid}/raw/public-market-bundle.body"
    raw = f"public BTC-USDT-SWAP cycle={cycle} q={qid}".encode()
    raw_sha = store.write_raw(relative_ref=raw_ref, payload=raw)["physical_sha256"]
    capture = build_v32_public_source_capture(
        qualification_id=qid,
        run_id=RUN_ID,
        cycle_index=cycle,
        attempt_id=f"attempt:{qid}",
        request_id=f"request:{qid}",
        request_started_at=ts(capture_started),
        response_received_at=ts(received),
        raw_response_binding={
            "relative_ref": raw_ref,
            "semantic_digest": raw_sha,
            "physical_sha256": raw_sha,
        },
    )
    if capture_boundary_mutations or capture_attempt_number != 1:
        capture = dict(capture)
        if capture_boundary_mutations:
            capture.update(capture_boundary_mutations)
        capture["attempt_number"] = capture_attempt_number
        capture = self_digest(capture, CAPTURE_DIGEST_FIELD)
    capture_ref = f"qualifications/{qid}/capture.json"
    capture_binding = store.write_document(
        relative_ref=capture_ref,
        document=capture,
        digest_field=CAPTURE_DIGEST_FIELD,
    )
    # Keep the fixture internally PIT-valid even when the whole transaction is
    # intentionally stale relative to the decision clock.  The workflow must
    # reject that case at its freshness gate, not while constructing evidence.
    closed = (
        received - timedelta(minutes=15)
        if stale
        else decision - timedelta(minutes=15)
    )
    snapshot = build_v32_public_market_snapshot(
        qualification_id=qid,
        run_id=RUN_ID,
        cycle_index=cycle,
        capture_attempt_digest=capture[CAPTURE_DIGEST_FIELD],
        as_of=ts(received - timedelta(seconds=1)),
        available_at=ts(received),
        closed_bar_as_of=ts(closed),
        open_interest_datum_digest=token(f"oi:{cycle}:{qid}"),
        open_interest_status="OBSERVED" if cycle % 2 else "UNKNOWN",
    )
    snapshot_ref = f"qualifications/{qid}/snapshot.json"
    snapshot_binding = store.write_document(
        relative_ref=snapshot_ref,
        document=snapshot,
        digest_field=SNAPSHOT_DIGEST_FIELD,
    )
    pit = build_v32_pit_evidence_registry(
        run_id=RUN_ID,
        cycle_index=cycle,
        as_of=ts(received),
        members=sorted(
            [snapshot["open_interest_datum_digest"], token(f"mark:{cycle}:{qid}")]
        ),
        upstream_snapshot_digest=snapshot[SNAPSHOT_DIGEST_FIELD],
        capture_digest=capture[CAPTURE_DIGEST_FIELD],
    )
    pit_ref = f"qualifications/{qid}/pit-registry.json"
    pit_binding = store.write_document(
        relative_ref=pit_ref,
        document=pit,
        digest_field="pit_evidence_registry_digest",
    )
    qualification = build_v32_formal_source_qualification(
        qualification_id=qid,
        run_id=RUN_ID,
        cycle_index=cycle,
        started_at=ts(started),
        completed_at=ts(completed),
        decision_time=ts(decision),
        active_authority_projection_digest=authority()[
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
        ],
        governing_authority_digest=authority()[
            GOVERNING_AUTHORITY_DIGEST_FIELD
        ],
        active_authority_recorded_at=authority()["recorded_at"],
        experiment_contract_digest=CONTRACT_DIGEST,
        capture_binding=capture_binding,
        snapshot_binding=snapshot_binding,
        pit_registry_binding=pit_binding,
    )
    if pre_authority:
        qualification = dict(qualification)
        qualification["started_at"] = ts(BASE - timedelta(seconds=1))
        qualification = self_digest(qualification, QUALIFICATION_DIGEST_FIELD)
    store.write_document(
        relative_ref=qualification_ref(qid),
        document=qualification,
        digest_field=QUALIFICATION_DIGEST_FIELD,
    )
    return qid, ts(admitted)


def prior_kwargs(result: dict) -> dict:
    return {
        "previous_cycle_source_admission_binding": result[
            "cycle_source_admission_binding"
        ],
        "prior_snapshot_binding": result["current_snapshot_binding"],
        "prior_open_interest_datum_digest": result[
            "current_open_interest_datum_digest"
        ],
        "prior_open_interest_status": result["current_open_interest_status"],
        "prior_open_interest_zero_imputed": False,
    }


def rewrite_cycle_one_as_legacy_v1(
    *, root: Path, result: dict
) -> tuple[dict, dict]:
    """Replace a generated cycle-one head with an exact historical v1 pair."""

    full_v2 = result["full_loader_receipt"]
    cutoff = datetime.fromisoformat(
        full_v2["source_cutoff_at"].replace("Z", "+00:00")
    )
    legacy_admitted_at = ts(cutoff - timedelta(seconds=30))
    full_v1 = build_v32_cycle_source_full_loader_receipt(
        run_id=full_v2["run_id"],
        cycle_index=full_v2["cycle_index"],
        admitted_at=legacy_admitted_at,
        decision_time=full_v2["decision_time"],
        active_authority_projection_digest=full_v2[
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
        ],
        governing_authority_digest=full_v2[GOVERNING_AUTHORITY_DIGEST_FIELD],
        active_authority_recorded_at=full_v2["active_authority_recorded_at"],
        experiment_contract_digest=full_v2["experiment_contract_digest"],
        qualification_binding=full_v2["qualification_binding"],
        capture_binding=full_v2["capture_binding"],
        current_snapshot_binding=full_v2["current_snapshot_binding"],
        pit_registry_binding=full_v2["pit_registry_binding"],
        qualification_started_at=full_v2["qualification_started_at"],
        qualification_completed_at=full_v2["qualification_completed_at"],
        earliest_capture_started_at=full_v2["earliest_capture_started_at"],
        latest_capture_received_at=full_v2["latest_capture_received_at"],
        closed_bar_as_of=full_v2["closed_bar_as_of"],
        current_open_interest_datum_digest=full_v2[
            "current_open_interest_datum_digest"
        ],
        current_open_interest_status=full_v2["current_open_interest_status"],
        previous_source_context=full_v2["previous_source_context"],
        artifact_copies=full_v2["artifact_copies"],
    )
    full_payload = canonical_bytes(full_v1) + b"\n"
    full_binding = dict(result["full_loader_receipt_binding"])
    full_binding.update(
        {
            "schema_id": FULL_LOADER_SCHEMA_ID,
            "semantic_digest": full_v1[FULL_LOADER_DIGEST_FIELD],
            "physical_sha256": hashlib.sha256(full_payload).hexdigest(),
        }
    )
    (root / full_binding["relative_ref"]).write_bytes(full_payload)

    admission_v2 = result["cycle_source_admission"]
    admission_v1 = seal_v32_cycle_source_admission(
        run_id=admission_v2["run_id"],
        cycle_index=admission_v2["cycle_index"],
        decision_time=admission_v2["decision_time"],
        admitted_at=legacy_admitted_at,
        current_snapshot_binding=admission_v2["current_snapshot_binding"],
        pit_registry_binding=admission_v2["pit_registry_binding"],
        previous_source_context=admission_v2["previous_source_context"],
        full_loader_receipt_binding=full_binding,
        active_authority_projection_digest=admission_v2[
            ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
        ],
        governing_authority_digest=admission_v2[
            GOVERNING_AUTHORITY_DIGEST_FIELD
        ],
        experiment_contract_digest=admission_v2["experiment_contract_digest"],
        qualification_binding=admission_v2["qualification_binding"],
        capture_binding=admission_v2["capture_binding"],
        current_open_interest_datum_digest=admission_v2[
            "current_open_interest_datum_digest"
        ],
        current_open_interest_status=admission_v2[
            "current_open_interest_status"
        ],
    )
    admission_payload = canonical_bytes(admission_v1) + b"\n"
    admission_ref = result["cycle_source_admission_binding"]["relative_ref"]
    (root / admission_ref).write_bytes(admission_payload)
    return full_v1, admission_v1


class V32CycleSourceAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source_root = root / "source"
        self.run_root = root / "run"
        self.source_store = LocalV32CycleSourceAdmissionStore(self.source_root)
        self.run_store = LocalV32CycleSourceAdmissionStore(self.run_root)
        self.authority = authority()

    def admit(self, cycle: int, previous: dict | None = None) -> dict:
        decision = BASE + timedelta(minutes=15 * cycle)
        qid, admitted = write_source_bundle(
            self.source_store, cycle=cycle, decision=decision
        )
        return admit_fresh_v32_source_to_cycle(
            source_store=self.source_store,
            run_store=self.run_store,
            active_authority=self.authority,
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=cycle,
            decision_time=ts(decision),
            admitted_at=admitted,
            **({} if previous is None else prior_kwargs(previous)),
        )

    def test_cycle_one_is_typed_exact_byte_and_full_loader_replayable(self) -> None:
        result = self.admit(1)
        admission = result["cycle_source_admission"]
        self.assertEqual("theory_paper_v32_cycle_source_admission_v1", admission["schema_id"])
        self.assertEqual(SOURCE_ADMISSION_SCHEMA_VERSION, admission["schema_version"])
        self.assertEqual(admission["decision_time"], admission["source_cutoff_at"])
        self.assertLess(admission["source_cutoff_at"], admission["admitted_at"])
        self.assertEqual(
            admission[SOURCE_ADMISSION_DIGEST_FIELD],
            verify_v32_cycle_source_admission(admission),
        )
        self.assertEqual(1, result["source_collection_transactions"])
        self.assertFalse(result["cycle_started"])
        full = result["full_loader_receipt"]
        self.assertEqual(SOURCE_ADMISSION_SCHEMA_VERSION, full["schema_version"])
        self.assertEqual(admission["source_cutoff_at"], full["source_cutoff_at"])
        self.assertEqual(admission["admitted_at"], full["admitted_at"])
        self.assertTrue(full["single_source_collection_transaction"])
        self.assertEqual(1, full["attempt_count"])
        self.assertFalse(full["retry_allowed"])
        self.assertTrue(full["exact_bytes_copied_and_read_back"])
        self.assertEqual(5, len(full["artifact_copies"]))
        replay = verify_durable_v32_cycle_source_admission(
            run_store=self.run_store,
            run_id=RUN_ID,
            cycle_index=1,
            expected_authority_projection_digest=self.authority[
                ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
            ],
            expected_governing_authority_digest=self.authority[
                GOVERNING_AUTHORITY_DIGEST_FIELD
            ],
            expected_experiment_contract_digest=CONTRACT_DIGEST,
        )
        self.assertEqual(result["cycle_source_admission_binding"], replay["cycle_source_admission_binding"])

    def test_cycle_two_requires_exact_previous_admission_snapshot_and_oi_triplet(self) -> None:
        first = self.admit(1)
        decision = BASE + timedelta(minutes=30)
        qid, admitted = write_source_bundle(
            self.source_store, cycle=2, decision=decision
        )
        wrong = prior_kwargs(first)
        wrong["prior_open_interest_datum_digest"] = "0" * 64
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "PREVIOUS_TRIPLET_MISMATCH"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=self.run_store,
                active_authority=self.authority,
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=2,
                decision_time=ts(decision),
                admitted_at=admitted,
                **wrong,
            )
        early_decision = BASE + timedelta(minutes=15)
        early_qid, early_admitted = write_source_bundle(
            self.source_store,
            cycle=2,
            decision=early_decision,
            qid="cycle-two-before-previous-head",
        )
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "NOT_AFTER_PREVIOUS_CYCLE"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=self.run_store,
                active_authority=self.authority,
                qualification_id=early_qid,
                run_id=RUN_ID,
                cycle_index=2,
                decision_time=ts(early_decision),
                admitted_at=early_admitted,
                **prior_kwargs(first),
            )
        second = admit_fresh_v32_source_to_cycle(
            source_store=self.source_store,
            run_store=self.run_store,
            active_authority=self.authority,
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=2,
            decision_time=ts(decision),
            admitted_at=admitted,
            **prior_kwargs(first),
        )
        context = second["cycle_source_admission"]["previous_source_context"]
        self.assertEqual(first["cycle_source_admission_binding"], context["previous_cycle_source_admission_binding"])
        self.assertFalse(context["prior_open_interest_zero_imputed"])

    def test_v1_durable_head_replays_and_can_precede_a_new_v2_cycle(self) -> None:
        generated = self.admit(1)
        full_v1, admission_v1 = rewrite_cycle_one_as_legacy_v1(
            root=self.run_root, result=generated
        )
        self.assertEqual("1.0.0", full_v1["schema_version"])
        self.assertEqual("1.0.0", admission_v1["schema_version"])
        self.assertNotIn("source_cutoff_at", full_v1)
        self.assertNotIn("source_cutoff_at", admission_v1)
        verify_v32_cycle_source_full_loader_receipt(full_v1)
        verify_v32_cycle_source_admission(admission_v1)
        previous = verify_durable_v32_cycle_source_admission(
            run_store=self.run_store,
            run_id=RUN_ID,
            cycle_index=1,
            expected_authority_projection_digest=self.authority[
                ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
            ],
            expected_governing_authority_digest=self.authority[
                GOVERNING_AUTHORITY_DIGEST_FIELD
            ],
            expected_experiment_contract_digest=CONTRACT_DIGEST,
        )
        second = self.admit(2, previous)
        self.assertEqual(
            SOURCE_ADMISSION_SCHEMA_VERSION,
            second["cycle_source_admission"]["schema_version"],
        )
        self.assertEqual(
            previous["cycle_source_admission_binding"],
            second["cycle_source_admission"]["previous_source_context"][
                "previous_cycle_source_admission_binding"
            ],
        )

    def test_v2_cutoff_alias_and_admission_order_fail_closed(self) -> None:
        decision = BASE + timedelta(minutes=15)
        qid, _ = write_source_bundle(
            self.source_store,
            cycle=1,
            decision=decision,
            qid="bad-v2-cutoff-order",
        )
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError,
            "CHRONOLOGY_OR_FRESHNESS_INVALID",
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=self.run_store,
                active_authority=self.authority,
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                decision_time=ts(decision),
                admitted_at=ts(decision - timedelta(seconds=1)),
            )

        other_store = LocalV32CycleSourceAdmissionStore(
            Path(self.temp.name) / "alias-run"
        )
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "CUTOFF_ALIAS_INVALID"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=other_store,
                active_authority=self.authority,
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                decision_time=ts(decision + timedelta(seconds=1)),
                admitted_at=ts(decision + timedelta(seconds=30)),
            )

    def test_schema_version_dispatch_rejects_unknown_or_malformed_v2(self) -> None:
        result = self.admit(1)
        for mutation in ("unknown", "missing-cutoff", "wrong-alias"):
            admission = dict(result["cycle_source_admission"])
            if mutation == "unknown":
                admission["schema_version"] = "3.0.0"
            elif mutation == "missing-cutoff":
                admission.pop("source_cutoff_at")
            else:
                admission["source_cutoff_at"] = ts(
                    BASE + timedelta(minutes=15, seconds=1)
                )
            admission = self_digest(admission, SOURCE_ADMISSION_DIGEST_FIELD)
            with self.assertRaises(V32CycleSourceAdmissionError):
                verify_v32_cycle_source_admission(admission)

            full = dict(result["full_loader_receipt"])
            if mutation == "unknown":
                full["schema_version"] = "3.0.0"
            elif mutation == "missing-cutoff":
                full.pop("source_cutoff_at")
            else:
                full["source_cutoff_at"] = ts(
                    BASE + timedelta(minutes=15, seconds=1)
                )
            full = self_digest(full, FULL_LOADER_DIGEST_FIELD)
            with self.assertRaises(V32CycleSourceAdmissionError):
                verify_v32_cycle_source_full_loader_receipt(full)

    def test_cycle_sixteen_allowed_cycle_seventeen_rejected(self) -> None:
        previous = None
        for cycle in range(1, 17):
            previous = self.admit(cycle, previous)
        self.assertEqual(16, previous["cycle_source_admission"]["cycle_index"])
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "OUTSIDE_FROZEN_CONTRACT"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=self.run_store,
                active_authority=self.authority,
                qualification_id="unused-cycle-17",
                run_id=RUN_ID,
                cycle_index=17,
                decision_time=ts(BASE + timedelta(minutes=255)),
                admitted_at=ts(BASE + timedelta(minutes=254)),
            )

    def test_pre_authority_and_stale_qualification_are_rejected(self) -> None:
        decision = BASE + timedelta(minutes=30)
        pre_qid, pre_admitted = write_source_bundle(
            self.source_store,
            cycle=1,
            decision=decision,
            qid="pre-authority",
            pre_authority=True,
        )
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "QUALIFIED_BUNDLE_INVALID"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=self.run_store,
                active_authority=self.authority,
                qualification_id=pre_qid,
                run_id=RUN_ID,
                cycle_index=1,
                decision_time=ts(decision),
                admitted_at=pre_admitted,
            )
        stale_qid, stale_admitted = write_source_bundle(
            self.source_store,
            cycle=1,
            decision=decision,
            qid="stale-source",
            stale=True,
        )
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "FRESHNESS_INVALID"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=self.run_store,
                active_authority=self.authority,
                qualification_id=stale_qid,
                run_id=RUN_ID,
                cycle_index=1,
                decision_time=ts(decision),
                admitted_at=stale_admitted,
            )

    def test_byte_tamper_and_expanded_permission_or_second_attempt_fail_closed(self) -> None:
        decision = BASE + timedelta(minutes=15)
        qid, admitted = write_source_bundle(
            self.source_store, cycle=1, decision=decision, qid="byte-tamper"
        )
        snapshot_path = self.source_root / f"qualifications/{qid}/snapshot.json"
        snapshot_path.write_bytes(snapshot_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "QUALIFIED_BUNDLE_INVALID"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=self.run_store,
                active_authority=self.authority,
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                decision_time=ts(decision),
                admitted_at=admitted,
            )
        for qid, boundary_mutations, attempt_number in (
            ("account-expanded", {"account_access": True}, 1),
            ("order-expanded", {"order_submission": True}, 1),
            ("credential-expanded", {"credential_access": True}, 1),
            ("permission-expanded", {"external_execution_authority": "PAPER"}, 1),
            ("second-attempt", None, 2),
        ):
            bad_qid, bad_admitted = write_source_bundle(
                self.source_store,
                cycle=1,
                decision=decision,
                qid=qid,
                capture_boundary_mutations=boundary_mutations,
                capture_attempt_number=attempt_number,
            )
            with self.assertRaisesRegex(
                V32CycleSourceAdmissionWorkflowError, "QUALIFIED_BUNDLE_INVALID"
            ):
                admit_fresh_v32_source_to_cycle(
                    source_store=self.source_store,
                    run_store=self.run_store,
                    active_authority=self.authority,
                    qualification_id=bad_qid,
                    run_id=RUN_ID,
                    cycle_index=1,
                    decision_time=ts(decision),
                    admitted_at=bad_admitted,
                )

    def test_partial_copy_recovery_idempotent_replay_and_conflict(self) -> None:
        decision = BASE + timedelta(minutes=15)
        qid, admitted = write_source_bundle(
            self.source_store, cycle=1, decision=decision, qid="partial-replay"
        )
        source_capture = self.source_store.read_raw(
            relative_ref=f"qualifications/{qid}/capture.json"
        )
        target = "cycles/0001/market/v32-source-admission/qualified/source-capture.json"
        self.run_store.write_raw(relative_ref=target, payload=source_capture)
        result = admit_fresh_v32_source_to_cycle(
            source_store=self.source_store,
            run_store=self.run_store,
            active_authority=self.authority,
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=1,
            decision_time=ts(decision),
            admitted_at=admitted,
        )
        replay = admit_fresh_v32_source_to_cycle(
            source_store=self.source_store,
            run_store=self.run_store,
            active_authority=self.authority,
            qualification_id=qid,
            run_id=RUN_ID,
            cycle_index=1,
            decision_time=ts(decision),
            admitted_at=admitted,
        )
        self.assertEqual(result["cycle_source_admission_binding"], replay["cycle_source_admission_binding"])

        other_root = Path(self.temp.name) / "conflict-run"
        conflict_store = LocalV32CycleSourceAdmissionStore(other_root)
        conflict_store.write_raw(relative_ref=target, payload=b"conflicting partial bytes")
        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "WRITE_ONCE_CONFLICT"
        ):
            admit_fresh_v32_source_to_cycle(
                source_store=self.source_store,
                run_store=conflict_store,
                active_authority=self.authority,
                qualification_id=qid,
                run_id=RUN_ID,
                cycle_index=1,
                decision_time=ts(decision),
                admitted_at=admitted,
            )

    def test_durable_replay_rejects_cross_document_forgery(self) -> None:
        result = self.admit(1)
        full = dict(result["full_loader_receipt"])
        admission = dict(result["cycle_source_admission"])
        qualification_row = next(
            row
            for row in full["artifact_copies"]
            if row["artifact_role"] == "SOURCE_QUALIFICATION"
        )
        qualification_path = self.run_root / qualification_row["target_relative_ref"]
        qualification = self.run_store.read_document(
            relative_ref=qualification_row["target_relative_ref"],
            digest_field=QUALIFICATION_DIGEST_FIELD,
        )
        qualification = dict(qualification)
        qualification["snapshot_binding"] = dict(
            qualification["snapshot_binding"]
        )
        qualification["snapshot_binding"]["semantic_digest"] = "f" * 64
        qualification = self_digest(qualification, QUALIFICATION_DIGEST_FIELD)
        qualification_payload = canonical_bytes(qualification) + b"\n"
        qualification_sha = hashlib.sha256(qualification_payload).hexdigest()
        qualification_path.write_bytes(qualification_payload)

        full["artifact_copies"] = [dict(row) for row in full["artifact_copies"]]
        qualification_row = next(
            row
            for row in full["artifact_copies"]
            if row["artifact_role"] == "SOURCE_QUALIFICATION"
        )
        qualification_row["semantic_digest"] = qualification[
            QUALIFICATION_DIGEST_FIELD
        ]
        qualification_row["source_physical_sha256"] = qualification_sha
        qualification_row["target_physical_sha256"] = qualification_sha
        full["qualification_binding"] = dict(full["qualification_binding"])
        full["qualification_binding"]["semantic_digest"] = qualification[
            QUALIFICATION_DIGEST_FIELD
        ]
        full["qualification_binding"]["physical_sha256"] = qualification_sha
        full = self_digest(full, FULL_LOADER_DIGEST_FIELD)
        full_payload = canonical_bytes(full) + b"\n"
        full_sha = hashlib.sha256(full_payload).hexdigest()
        (self.run_root / result["full_loader_receipt_binding"]["relative_ref"]).write_bytes(
            full_payload
        )

        admission["qualification_binding"] = dict(full["qualification_binding"])
        admission["full_loader_receipt_binding"] = dict(
            admission["full_loader_receipt_binding"]
        )
        admission["full_loader_receipt_binding"]["semantic_digest"] = full[
            FULL_LOADER_DIGEST_FIELD
        ]
        admission["full_loader_receipt_binding"]["physical_sha256"] = full_sha
        admission = self_digest(admission, SOURCE_ADMISSION_DIGEST_FIELD)
        admission_payload = canonical_bytes(admission) + b"\n"
        (
            self.run_root
            / result["cycle_source_admission_binding"]["relative_ref"]
        ).write_bytes(admission_payload)

        with self.assertRaisesRegex(
            V32CycleSourceAdmissionWorkflowError, "DURABLE_REPLAY_FAILED"
        ):
            verify_durable_v32_cycle_source_admission(
                run_store=self.run_store,
                run_id=RUN_ID,
                cycle_index=1,
                expected_authority_projection_digest=self.authority[
                    ACTIVE_AUTHORITY_PROJECTION_DIGEST_FIELD
                ],
                expected_governing_authority_digest=self.authority[
                    GOVERNING_AUTHORITY_DIGEST_FIELD
                ],
                expected_experiment_contract_digest=CONTRACT_DIGEST,
            )

    def test_path_symlink_and_v31_schema_impersonation_are_rejected(self) -> None:
        with self.assertRaisesRegex(V32CycleSourceAdmissionStoreError, "PATH_INVALID"):
            self.run_store.write_raw(relative_ref="../escape", payload=b"x")
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        symlink = self.run_root / "linked"
        os.symlink(outside, symlink)
        with self.assertRaisesRegex(V32CycleSourceAdmissionStoreError, "SYMLINK"):
            self.run_store.write_raw(relative_ref="linked/escape", payload=b"x")
        v31 = self_digest(
            {
                "schema_id": "theory_paper_v31_cycle_source_admission",
                "schema_version": "1.0.0",
                "run_id": RUN_ID,
                "cycle_index": 1,
            },
            SOURCE_ADMISSION_DIGEST_FIELD,
        )
        with self.assertRaises(V32CycleSourceAdmissionError):
            verify_v32_cycle_source_admission(v31)


if __name__ == "__main__":
    unittest.main()
