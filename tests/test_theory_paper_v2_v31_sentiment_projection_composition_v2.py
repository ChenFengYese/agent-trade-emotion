from __future__ import annotations

import copy
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping
import unittest

from tests.test_theory_paper_v2_v31_sentiment_native_projection_adapter_v2 import (
    RAW_SHA,
    _dataset,
)
from trade_system.theory_paper_v2.application.v31_sentiment_projection_composition_v2 import (  # noqa: E501
    V31SentimentProjectionCompositionV2Error,
    compose_and_persist_v31_sentiment_projection_v2,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    verify_self_digest,
)
from trade_system.theory_paper_v2.domain.data_model import (
    point_in_time_datum_from_document,
)
from trade_system.theory_paper_v2.domain.information_model import (
    information_event_digest,
    information_event_from_canonical_dict,
    information_event_to_canonical_dict,
)
from trade_system.theory_paper_v2.domain.v31_cycle_source_admission import (
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    cycle_source_admission_ref,
    seal_v31_cycle_source_admission,
)
from trade_system.theory_paper_v2.domain.v31_source_qualification import (
    seal_v31_source_qualification_information_event_record,
)
from trade_system.theory_paper_v2.infrastructure.v31_sentiment_projection_store_v2 import (  # noqa: E501
    LocalV31SentimentProjectionStoreV2,
    V31SentimentProjectionStoreV2Error,
)


RUN_ID = "v31-prospective-btcusdt-20260806t183742z"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_RUN_ROOT = PROJECT_ROOT / "agent-cluster" / "experiments" / RUN_ID
TYPED_BINDING_FIELDS = {
    "relative_ref",
    "schema_id",
    "digest_field",
    "semantic_digest",
    "physical_sha256",
}


def _physical(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(document)) + b"\n").hexdigest()


def _load_fixture(relative_ref: str) -> dict[str, Any]:
    return dict(load_json_strict(FROZEN_RUN_ROOT / relative_ref))


def _genesis_checkpoint() -> dict[str, Any]:
    return {
        "status": "READY_FOR_CYCLE",
        "active_cycle_index": None,
        "completed_cycles": 0,
        "next_cycle_index": 1,
        "accepted_pit_dataset_ref": None,
        "accepted_pit_dataset_digest": None,
        "accepted_information_revision_registry_ref": None,
        "accepted_information_revision_registry_digest": None,
    }


class _FixtureReader:
    def __init__(
        self,
        checkpoint: Mapping[str, Any],
        *,
        physical_overrides: Mapping[str, str] | None = None,
    ) -> None:
        self.checkpoint = dict(checkpoint)
        self.physical_overrides = dict(physical_overrides or {})

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        if run_id != RUN_ID:
            raise ValueError("run mismatch")
        return copy.deepcopy(self.checkpoint)

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        document = _load_fixture(relative_ref)
        digest = verify_self_digest(document, digest_field)
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise ValueError("semantic mismatch")
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        physical = self.physical_overrides.get(
            relative_ref,
            hashlib.sha256((FROZEN_RUN_ROOT / relative_ref).read_bytes()).hexdigest(),
        )
        return {
            "relative_ref": relative_ref,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": physical,
        }


class _MemoryReader:
    def __init__(
        self,
        *,
        documents: Mapping[str, Mapping[str, Any]],
        checkpoint: Mapping[str, Any],
    ) -> None:
        self.documents = {
            relative_ref: copy.deepcopy(dict(document))
            for relative_ref, document in documents.items()
        }
        self.checkpoint = copy.deepcopy(dict(checkpoint))

    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]:
        if run_id != RUN_ID:
            raise ValueError("run mismatch")
        return copy.deepcopy(self.checkpoint)

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]:
        document = copy.deepcopy(self.documents[relative_ref])
        digest = verify_self_digest(document, digest_field)
        if expected_semantic_digest is not None and digest != expected_semantic_digest:
            raise ValueError("semantic mismatch")
        return document

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]:
        document = self.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        return {
            "relative_ref": relative_ref,
            "semantic_digest": str(document[digest_field]),
            "physical_sha256": _physical(document),
        }


def _document_row(
    *,
    role: str,
    artifact_id: str,
    target_ref: str,
    schema_id: str,
    digest_field: str,
    semantic_digest: str,
    physical_sha256: str,
) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "artifact_id": artifact_id,
        "source_relative_ref": f"qualification/{role.lower()}-{artifact_id}.json",
        "target_relative_ref": target_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": semantic_digest,
        "source_physical_sha256": physical_sha256,
        "target_physical_sha256": physical_sha256,
        "exact_bytes_copied": True,
    }


def _cycle_two_reader() -> _MemoryReader:
    previous_admission_ref = cycle_source_admission_ref(1)
    previous_admission = _load_fixture(previous_admission_ref)
    previous_dataset_ref = "cycles/0001/pit-dataset.json"
    previous_registry_ref = "cycles/0001/information-revision-registry.json"
    previous_dataset = _load_fixture(previous_dataset_ref)
    previous_registry = _load_fixture(previous_registry_ref)
    previous_information_ref = (
        "cycles/0001/market/source-admission/adapted/"
        "information-event-0001.json"
    )
    previous_information_record = _load_fixture(previous_information_ref)

    previous_oi = point_in_time_datum_from_document(
        next(
            row
            for row in previous_dataset["data"]
            if row["metric"] == "open-interest-btc"
        )
    )
    decision = datetime(2026, 8, 6, 19, 58, tzinfo=UTC)
    current_dataset, event_id, _ = _dataset(
        cycle=2,
        decision=decision,
        previous_oi=previous_oi,
    )
    prior_event = information_event_from_canonical_dict(
        previous_information_record["event_document"]
    )
    current_event = replace(prior_event, event_id=event_id)
    event_document = information_event_to_canonical_dict(current_event)
    qualification_id = "qualification:successor-composition:cycle-2"
    information_record = seal_v31_source_qualification_information_event_record(
        qualification_id=qualification_id,
        event_document=event_document,
    )

    dataset_ref = (
        "cycles/0002/market/source-admission/adapted/pit-dataset.json"
    )
    information_ref = (
        "cycles/0002/market/source-admission/adapted/"
        "information-event-0001.json"
    )
    plan_digest = canonical_digest({"plan": 2})
    reservation_digest = canonical_digest({"reservation": 2})
    checkpoint_digest = canonical_digest({"qualification-checkpoint": 2})
    completion_digest = canonical_digest({"completion": 2})
    snapshot_digest = canonical_digest({"snapshot": 2})
    placeholders = {
        "QUALIFICATION_PLAN": ("plan", plan_digest),
        "QUALIFICATION_RESERVATION": ("reservation", reservation_digest),
        "QUALIFICATION_CHECKPOINT": ("checkpoint", checkpoint_digest),
        "QUALIFICATION_COMPLETION": ("completion", completion_digest),
        "MARKET_SNAPSHOT": ("snapshot", snapshot_digest),
    }
    artifact_rows = []
    for role, (artifact_id, semantic_digest) in placeholders.items():
        artifact_rows.append(
            _document_row(
                role=role,
                artifact_id=artifact_id,
                target_ref=(
                    "cycles/0002/market/source-admission/qualification/"
                    f"{artifact_id}.json"
                ),
                schema_id=f"fixture:{artifact_id}",
                digest_field=f"{artifact_id}_digest",
                semantic_digest=semantic_digest,
                physical_sha256=canonical_digest({"physical": artifact_id}),
            )
        )
    artifact_rows.extend(
        [
            _document_row(
                role="PIT_DATASET",
                artifact_id="pit_dataset",
                target_ref=dataset_ref,
                schema_id=str(current_dataset["schema_id"]),
                digest_field="dataset_digest",
                semantic_digest=str(current_dataset["dataset_digest"]),
                physical_sha256=_physical(current_dataset),
            ),
            _document_row(
                role="INFORMATION_EVENT",
                artifact_id="0001",
                target_ref=information_ref,
                schema_id=str(information_record["schema_id"]),
                digest_field=(
                    "source_qualification_information_event_record_digest"
                ),
                semantic_digest=str(
                    information_record[
                        "source_qualification_information_event_record_digest"
                    ]
                ),
                physical_sha256=_physical(information_record),
            ),
            {
                "artifact_role": "RAW_RESPONSE",
                "artifact_id": "okx-test",
                "source_relative_ref": "qualification/raw/okx-test.body",
                "target_relative_ref": (
                    "cycles/0002/market/source-admission/raw/okx-test.body"
                ),
                "schema_id": None,
                "digest_field": None,
                "semantic_digest": RAW_SHA,
                "source_physical_sha256": RAW_SHA,
                "target_physical_sha256": RAW_SHA,
                "exact_bytes_copied": True,
            },
        ]
    )
    artifact_rows.sort(key=lambda row: (row["artifact_role"], row["artifact_id"]))

    previous_snapshot_row = next(
        row
        for row in previous_admission["artifact_copies"]
        if row["artifact_role"] == "MARKET_SNAPSHOT"
    )
    previous_context = {
        "status": "BOUND_TO_PREVIOUS_ACCEPTED_CYCLE",
        "previous_cycle_source_admission_binding": {
            "relative_ref": previous_admission_ref,
            "schema_id": SOURCE_ADMISSION_SCHEMA_ID,
            "digest_field": SOURCE_ADMISSION_DIGEST_FIELD,
            "semantic_digest": previous_admission[SOURCE_ADMISSION_DIGEST_FIELD],
            "physical_sha256": _physical(previous_admission),
        },
        "prior_snapshot_binding": {
            "relative_ref": previous_snapshot_row["target_relative_ref"],
            "schema_id": previous_snapshot_row["schema_id"],
            "digest_field": previous_snapshot_row["digest_field"],
            "semantic_digest": previous_snapshot_row["semantic_digest"],
            "physical_sha256": previous_snapshot_row["target_physical_sha256"],
        },
        "prior_open_interest_datum_digest": previous_oi.to_document()[
            "datum_digest"
        ],
        "prior_open_interest_status": "OBSERVED",
        "prior_open_interest_zero_imputed": False,
        "previous_decision_at": previous_admission["decision_at"],
        "previous_admitted_at": previous_admission["admitted_at"],
        "previous_closed_1h_as_of": previous_admission["closed_1h_as_of"],
    }
    current_admission = seal_v31_cycle_source_admission(
        run_id=RUN_ID,
        cycle_index=2,
        admitted_at="2026-08-06T19:58:01Z",
        decision_at="2026-08-06T19:58:00Z",
        closed_1h_as_of="2026-08-06T18:00:00Z",
        active_authority_digest="1" * 64,
        active_authority_recorded_at="2026-08-06T19:56:00Z",
        experiment_contract_digest="2" * 64,
        source_qualification_id=qualification_id,
        source_qualification_plan_digest=plan_digest,
        source_qualification_checkpoint_digest=checkpoint_digest,
        source_qualification_completion_digest=completion_digest,
        source_qualification_decision_at="2026-08-06T19:58:00Z",
        native_market_snapshot_digest=snapshot_digest,
        pit_dataset_digest=current_dataset["dataset_digest"],
        information_event_digests=[information_event_digest(current_event)],
        information_event_record_digests=[
            information_record[
                "source_qualification_information_event_record_digest"
            ]
        ],
        source_capture_record_digests={
            "okx-test": canonical_digest({"capture": 2})
        },
        raw_physical_sha256_by_request_id={"okx-test": RAW_SHA},
        earliest_capture_started_at="2026-08-06T19:57:00Z",
        latest_capture_received_at="2026-08-06T19:57:30Z",
        artifact_copies=artifact_rows,
        previous_source_context=previous_context,
    )
    current_admission_ref = cycle_source_admission_ref(2)
    documents = {
        previous_admission_ref: previous_admission,
        previous_dataset_ref: previous_dataset,
        previous_registry_ref: previous_registry,
        previous_information_ref: previous_information_record,
        current_admission_ref: current_admission,
        dataset_ref: current_dataset,
        information_ref: information_record,
    }
    checkpoint = {
        "status": "READY_FOR_CYCLE",
        "active_cycle_index": None,
        "completed_cycles": 1,
        "next_cycle_index": 2,
        "accepted_pit_dataset_ref": previous_dataset_ref,
        "accepted_pit_dataset_digest": previous_dataset["dataset_digest"],
        "accepted_information_revision_registry_ref": previous_registry_ref,
        "accepted_information_revision_registry_digest": previous_registry[
            "information_revision_registry_digest"
        ],
    }
    return _MemoryReader(documents=documents, checkpoint=checkpoint)


class V31SentimentProjectionCompositionV2Tests(unittest.TestCase):
    def test_cycle_one_is_idempotent_and_never_infers_direction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection_store = LocalV31SentimentProjectionStoreV2(
                Path(temporary)
            )
            reader = _FixtureReader(_genesis_checkpoint())
            first = compose_and_persist_v31_sentiment_projection_v2(
                run_store=reader,
                projection_store=projection_store,
                run_id=RUN_ID,
                cycle_index=1,
            )
            second = compose_and_persist_v31_sentiment_projection_v2(
                run_store=reader,
                projection_store=projection_store,
                run_id=RUN_ID,
                cycle_index=1,
            )

            self.assertEqual(first["support_bindings"], second["support_bindings"])
            self.assertEqual(
                first["projection_receipt"]["projection_receipt_digest"],
                second["projection_receipt"]["projection_receipt_digest"],
            )
            for binding in first["support_bindings"].values():
                self.assertEqual(TYPED_BINDING_FIELDS, set(binding))
            self.assertEqual(
                12,
                len(first["projection_receipt"]["projection"]["axis_projections"]),
            )
            self.assertTrue(
                all(
                    row["ordinal_value"] is None
                    for row in first["projection_receipt"]["projection"][
                        "axis_projections"
                    ]
                )
            )

    def test_cycle_two_consumes_exact_accepted_previous_heads(self) -> None:
        reader = _cycle_two_reader()
        with tempfile.TemporaryDirectory() as temporary:
            result = compose_and_persist_v31_sentiment_projection_v2(
                run_store=reader,
                projection_store=LocalV31SentimentProjectionStoreV2(
                    Path(temporary)
                ),
                run_id=RUN_ID,
                cycle_index=2,
            )

        source_bindings = result["source_input_bindings"]
        self.assertIn("previous_cycle_source_admission", source_bindings)
        self.assertIn("previous_pit_dataset", source_bindings)
        self.assertIn("previous_information_revision_registry", source_bindings)
        self.assertEqual(
            "VERIFIED_EXACT_PREVIOUS_OI_BINDING",
            result["projection_receipt"]["previous_context_verification"][
                "status"
            ],
        )
        self.assertEqual(
            2, result["information_revision_registry"]["cycle_index"]
        )
        self.assertEqual(
            2, len(result["information_revision_registry"]["known_event_ids"])
        )
        self.assertTrue(
            all(
                row["ordinal_value"] is None
                for row in result["projection_receipt"]["projection"][
                    "axis_projections"
                ]
            )
        )

    def test_copied_dataset_physical_drift_fails_before_output(self) -> None:
        admission = _load_fixture(cycle_source_admission_ref(1))
        dataset_ref = next(
            row["target_relative_ref"]
            for row in admission["artifact_copies"]
            if row["artifact_role"] == "PIT_DATASET"
        )
        reader = _FixtureReader(
            _genesis_checkpoint(),
            physical_overrides={dataset_ref: "0" * 64},
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                V31SentimentProjectionCompositionV2Error,
                "COPIED_DOCUMENT_PHYSICAL_DRIFT",
            ):
                compose_and_persist_v31_sentiment_projection_v2(
                    run_store=reader,
                    projection_store=LocalV31SentimentProjectionStoreV2(
                        Path(temporary)
                    ),
                    run_id=RUN_ID,
                    cycle_index=1,
                )

    def test_previous_accepted_registry_digest_drift_fails_closed(self) -> None:
        reader = _cycle_two_reader()
        reader.checkpoint["accepted_information_revision_registry_digest"] = (
            "0" * 64
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                V31SentimentProjectionCompositionV2Error,
                "RUN_LOCAL_READ_FAILED",
            ):
                compose_and_persist_v31_sentiment_projection_v2(
                    run_store=reader,
                    projection_store=LocalV31SentimentProjectionStoreV2(
                        Path(temporary)
                    ),
                    run_id=RUN_ID,
                    cycle_index=2,
                )

    def test_projection_store_rejects_escape_symlink_and_physical_drift(self) -> None:
        reader = _FixtureReader(_genesis_checkpoint())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projection_store = LocalV31SentimentProjectionStoreV2(root)
            with self.assertRaisesRegex(
                V31SentimentProjectionStoreV2Error,
                "REF_INVALID",
            ):
                projection_store.read_document(
                    relative_ref="../projection-receipt.json",
                    digest_field="projection_receipt_digest",
                )

            outside = root / "outside"
            outside.mkdir()
            cycles = root / "v31-sentiment-projection-v2" / "cycles"
            cycles.mkdir(parents=True)
            os.symlink(outside, cycles / "0002")
            with self.assertRaisesRegex(
                V31SentimentProjectionStoreV2Error,
                "SYMLINK_FORBIDDEN",
            ):
                projection_store.read_document(
                    relative_ref=(
                        "v31-sentiment-projection-v2/cycles/0002/"
                        "projection-receipt.json"
                    ),
                    digest_field="projection_receipt_digest",
                )

            result = compose_and_persist_v31_sentiment_projection_v2(
                run_store=reader,
                projection_store=projection_store,
                run_id=RUN_ID,
                cycle_index=1,
            )
            receipt_binding = result["support_bindings"]["sentiment_projection"]
            receipt_path = root / receipt_binding["relative_ref"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt_path.write_text(
                json.dumps(receipt, indent=2),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                V31SentimentProjectionStoreV2Error,
                "PHYSICAL_DRIFT",
            ):
                projection_store.read_document(
                    relative_ref=receipt_binding["relative_ref"],
                    digest_field=receipt_binding["digest_field"],
                    expected_semantic_digest=receipt_binding["semantic_digest"],
                )


if __name__ == "__main__":
    unittest.main()
