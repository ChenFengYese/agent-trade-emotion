"""Compose and persist run-local twelve-axis projection support.

The use case reconstructs the current information revision registry from the
information-event records copied by the cycle source admission.  For cycle
two and later it consumes only the exact accepted previous registry/dataset
and the previous source admission bound by the current receipt.  It then calls
the successor PIT-to-axis adapter, writes every immutable material, and returns
the five-field bindings required by successor commit support.

No axis state is accepted as input here.  Consequently this composition can
make qualified source evidence available, but can never upgrade UNKNOWN into
an ordinal direction.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping, Protocol, Sequence

from .v31_sentiment_native_projection_adapter_v2 import (
    V31SentimentProjectionAdapterV2Error,
    build_v31_sentiment_native_projection_receipt_v2,
    verify_v31_sentiment_native_projection_receipt_v2,
)
from ..domain.information_model import (
    InformationEvent,
    InformationModelError,
    admit_information_event,
    build_information_event_revision_registry,
    information_event_digest,
    information_event_from_canonical_dict,
)
from ..domain.v31_cycle_source_admission import (
    SOURCE_ADMISSION_DIGEST_FIELD,
    SOURCE_ADMISSION_SCHEMA_ID,
    V31CycleSourceAdmissionError,
    cycle_source_admission_ref,
    verify_v31_cycle_source_admission,
)
from ..domain.v31_source_qualification import (
    V31SourceQualificationError,
    verify_v31_source_qualification_information_event_record,
)
from ..infrastructure.v31_sentiment_projection_store_v2 import (
    sentiment_material_ref_v2,
    sentiment_projection_receipt_ref_v2,
    sentiment_source_registry_ref_v2,
)


class V31SentimentProjectionCompositionV2Error(ValueError):
    """Run-local sentiment projection support failed closed."""


class V31SentimentProjectionRunReaderV2(Protocol):
    def load_checkpoint(self, *, run_id: str) -> Mapping[str, Any]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...


class V31SentimentProjectionOutputStoreV2(Protocol):
    def write_document(
        self,
        *,
        relative_ref: str,
        document: Mapping[str, Any],
        digest_field: str,
    ) -> Mapping[str, str]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def artifact_binding(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> Mapping[str, str]: ...


_TYPED_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31SentimentProjectionCompositionV2Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SentimentProjectionCompositionV2Error(code) from exc
    if parsed.tzinfo is None:
        raise V31SentimentProjectionCompositionV2Error(code)
    return parsed.astimezone(UTC)


def _typed_read(
    *,
    store: V31SentimentProjectionRunReaderV2,
    relative_ref: str,
    schema_id: str,
    digest_field: str,
    expected_semantic_digest: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        document = store.read_document(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
        raw_binding = store.artifact_binding(
            relative_ref=relative_ref,
            digest_field=digest_field,
            expected_semantic_digest=expected_semantic_digest,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_RUN_LOCAL_READ_FAILED"
        ) from exc
    if document.get("schema_id") != schema_id:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_SOURCE_SCHEMA_MISMATCH"
        )
    binding = {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": str(document[digest_field]),
        "physical_sha256": str(raw_binding.get("physical_sha256") or ""),
    }
    if (
        raw_binding.get("relative_ref") != relative_ref
        or raw_binding.get("semantic_digest") != document[digest_field]
        or raw_binding.get("schema_id", schema_id) != schema_id
        or raw_binding.get("digest_field", digest_field) != digest_field
        or _HEX_64.fullmatch(binding["physical_sha256"]) is None
    ):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_SOURCE_PHYSICAL_BINDING_INVALID"
        )
    return dict(document), binding


def _copied_rows(
    admission: Mapping[str, Any], *, artifact_role: str
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in admission["artifact_copies"]
        if row.get("artifact_role") == artifact_role
    ]


def _read_copied_document(
    *,
    store: V31SentimentProjectionRunReaderV2,
    row: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    if row.get("schema_id") is None or row.get("digest_field") is None:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_COPIED_DOCUMENT_INVALID"
        )
    document, binding = _typed_read(
        store=store,
        relative_ref=str(row["target_relative_ref"]),
        schema_id=str(row["schema_id"]),
        digest_field=str(row["digest_field"]),
        expected_semantic_digest=str(row["semantic_digest"]),
    )
    expected = {
        "relative_ref": row["target_relative_ref"],
        "schema_id": row["schema_id"],
        "digest_field": row["digest_field"],
        "semantic_digest": row["semantic_digest"],
        "physical_sha256": row["target_physical_sha256"],
    }
    if binding != expected:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_COPIED_DOCUMENT_PHYSICAL_DRIFT"
        )
    return document, binding


def _load_admission(
    *,
    store: V31SentimentProjectionRunReaderV2,
    run_id: str,
    cycle_index: int,
    expected_binding: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    ref = cycle_source_admission_ref(cycle_index)
    admission, binding = _typed_read(
        store=store,
        relative_ref=ref,
        schema_id=SOURCE_ADMISSION_SCHEMA_ID,
        digest_field=SOURCE_ADMISSION_DIGEST_FIELD,
        expected_semantic_digest=(
            None
            if expected_binding is None
            else str(expected_binding["semantic_digest"])
        ),
    )
    try:
        verify_v31_cycle_source_admission(admission)
    except V31CycleSourceAdmissionError as exc:
        raise V31SentimentProjectionCompositionV2Error(
            f"V31_SENTIMENT_COMPOSITION_SOURCE_ADMISSION_INVALID:{exc}"
        ) from exc
    if admission.get("run_id") != run_id or admission.get("cycle_index") != cycle_index:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_SOURCE_ADMISSION_IDENTITY_MISMATCH"
        )
    if expected_binding is not None and binding != dict(expected_binding):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_PREVIOUS_ADMISSION_BINDING_DRIFT"
        )
    return admission, binding


def _accepted_previous_inputs(
    *,
    store: V31SentimentProjectionRunReaderV2,
    run_id: str,
    cycle_index: int,
    checkpoint: Mapping[str, Any],
    current_admission: Mapping[str, Any],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, dict[str, str]],
]:
    completed = checkpoint.get("completed_cycles")
    if (
        completed != cycle_index - 1
        or checkpoint.get("next_cycle_index") != cycle_index
    ):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_CHECKPOINT_NOT_AT_CYCLE_BOUNDARY"
        )
    status = checkpoint.get("status")
    active = checkpoint.get("active_cycle_index")
    if not (
        (status == "READY_FOR_CYCLE" and active is None)
        or (status == "CYCLE_IN_PROGRESS" and active == cycle_index)
    ):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_CHECKPOINT_STATE_INVALID"
        )
    if cycle_index == 1:
        for field in (
            "accepted_pit_dataset_ref",
            "accepted_pit_dataset_digest",
            "accepted_information_revision_registry_ref",
            "accepted_information_revision_registry_digest",
        ):
            if checkpoint.get(field) is not None:
                raise V31SentimentProjectionCompositionV2Error(
                    "V31_SENTIMENT_COMPOSITION_GENESIS_ACCEPTED_HEAD_FORBIDDEN"
                )
        return None, None, None, {}

    context = current_admission["previous_source_context"]
    expected_previous_binding = context.get(
        "previous_cycle_source_admission_binding"
    )
    if not isinstance(expected_previous_binding, Mapping):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_PREVIOUS_ADMISSION_BINDING_MISSING"
        )
    previous_admission, previous_admission_binding = _load_admission(
        store=store,
        run_id=run_id,
        cycle_index=cycle_index - 1,
        expected_binding=expected_previous_binding,
    )
    previous_dataset, previous_dataset_binding = _typed_read(
        store=store,
        relative_ref=str(checkpoint["accepted_pit_dataset_ref"]),
        schema_id="theory_paper_v2_v31_point_in_time_dataset",
        digest_field="dataset_digest",
        expected_semantic_digest=str(
            checkpoint["accepted_pit_dataset_digest"]
        ),
    )
    previous_registry, previous_registry_binding = _typed_read(
        store=store,
        relative_ref=str(
            checkpoint["accepted_information_revision_registry_ref"]
        ),
        schema_id="theory_paper_v2_v31_information_revision_registry",
        digest_field="information_revision_registry_digest",
        expected_semantic_digest=str(
            checkpoint["accepted_information_revision_registry_digest"]
        ),
    )
    if (
        previous_admission.get("pit_dataset_digest")
        != previous_dataset.get("dataset_digest")
        or previous_admission.get("decision_at")
        != previous_dataset.get("decision_at")
        or previous_registry.get("run_id") != run_id
        or previous_registry.get("cycle_index") != cycle_index - 1
        or previous_registry.get("decision_at")
        != previous_admission.get("decision_at")
    ):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_PREVIOUS_ACCEPTED_HEAD_DRIFT"
        )
    return (
        previous_registry,
        previous_dataset,
        previous_admission,
        {
            "previous_cycle_source_admission": previous_admission_binding,
            "previous_pit_dataset": previous_dataset_binding,
            "previous_information_revision_registry": previous_registry_binding,
        },
    )


def _event_records(
    *,
    store: V31SentimentProjectionRunReaderV2,
    admission: Mapping[str, Any],
) -> tuple[list[InformationEvent], list[dict[str, str]]]:
    rows = _copied_rows(admission, artifact_role="INFORMATION_EVENT")
    if not rows:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_INFORMATION_EVENTS_MISSING"
        )
    events: list[InformationEvent] = []
    bindings: list[dict[str, str]] = []
    digests: list[str] = []
    for row in rows:
        record, binding = _read_copied_document(store=store, row=row)
        try:
            verify_v31_source_qualification_information_event_record(
                record,
                qualification_id=str(admission["source_qualification_id"]),
            )
            event = information_event_from_canonical_dict(
                record["event_document"]
            )
            digest = information_event_digest(event)
        except (InformationModelError, V31SourceQualificationError) as exc:
            raise V31SentimentProjectionCompositionV2Error(
                f"V31_SENTIMENT_COMPOSITION_INFORMATION_EVENT_INVALID:{exc}"
            ) from exc
        if record.get("information_event_digest") != digest:
            raise V31SentimentProjectionCompositionV2Error(
                "V31_SENTIMENT_COMPOSITION_INFORMATION_EVENT_DIGEST_DRIFT"
            )
        events.append(event)
        bindings.append(binding)
        digests.append(digest)
    if digests != list(admission["information_event_digests"]):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_INFORMATION_EVENT_SET_DRIFT"
        )
    return events, bindings


def _find_prior_event(
    *,
    store: V31SentimentProjectionRunReaderV2,
    run_id: str,
    before_cycle: int,
    event_id: str,
    event_digest_value: str,
) -> InformationEvent:
    for cycle in range(before_cycle, 0, -1):
        admission, _ = _load_admission(
            store=store, run_id=run_id, cycle_index=cycle
        )
        events, _ = _event_records(store=store, admission=admission)
        for event in events:
            if (
                event.event_id == event_id
                and information_event_digest(event) == event_digest_value
            ):
                return event
    raise V31SentimentProjectionCompositionV2Error(
        "V31_SENTIMENT_COMPOSITION_PRIOR_INFORMATION_REVISION_MISSING"
    )


def _current_information_registry(
    *,
    store: V31SentimentProjectionRunReaderV2,
    run_id: str,
    cycle_index: int,
    admission: Mapping[str, Any],
    previous_registry: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    events, bindings = _event_records(store=store, admission=admission)
    prior_latest = {
        str(row["event_id"]): dict(row)
        for row in (
            [] if previous_registry is None else previous_registry["latest_revisions"]
        )
    }
    decision = _time(
        admission["decision_at"],
        "V31_SENTIMENT_COMPOSITION_DECISION_TIME_INVALID",
    )
    admissions = []
    for event in events:
        prior_event = None
        if event.revision > 1:
            prior = prior_latest.get(event.event_id)
            if (
                prior is None
                or prior.get("event_digest") != event.previous_revision_digest
            ):
                raise V31SentimentProjectionCompositionV2Error(
                    "V31_SENTIMENT_COMPOSITION_INFORMATION_REVISION_CHAIN_INVALID"
                )
            prior_event = _find_prior_event(
                store=store,
                run_id=run_id,
                before_cycle=cycle_index - 1,
                event_id=event.event_id,
                event_digest_value=str(prior["event_digest"]),
            )
        try:
            admissions.append(
                admit_information_event(
                    event, decision_at=decision, prior_revision=prior_event
                )
            )
        except InformationModelError as exc:
            raise V31SentimentProjectionCompositionV2Error(
                f"V31_SENTIMENT_COMPOSITION_INFORMATION_ADMISSION_FAILED:{exc}"
            ) from exc
    try:
        registry = build_information_event_revision_registry(
            run_id=run_id,
            cycle_index=cycle_index,
            decision_at=decision,
            admissions=tuple(admissions),
            previous_registry=previous_registry,
        )
    except InformationModelError as exc:
        raise V31SentimentProjectionCompositionV2Error(
            f"V31_SENTIMENT_COMPOSITION_INFORMATION_REGISTRY_FAILED:{exc}"
        ) from exc
    return registry, bindings


def _write_materials(
    *,
    store: V31SentimentProjectionOutputStoreV2,
    cycle_index: int,
    values: Sequence[Mapping[str, Any]],
    material_kind: str,
) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    seen: set[str] = set()
    for wrapper in values:
        if not isinstance(wrapper, Mapping) or set(wrapper) != {
            "material_ref",
            "material_digest",
            "material",
        }:
            raise V31SentimentProjectionCompositionV2Error(
                "V31_SENTIMENT_COMPOSITION_MATERIAL_WRAPPER_INVALID"
            )
        material = wrapper["material"]
        digest = str(wrapper["material_digest"])
        if (
            not isinstance(material, Mapping)
            or material.get("material_digest") != digest
            or digest in seen
        ):
            raise V31SentimentProjectionCompositionV2Error(
                "V31_SENTIMENT_COMPOSITION_MATERIAL_BINDING_INVALID"
            )
        seen.add(digest)
        ref = sentiment_material_ref_v2(
            cycle_index,
            material_kind=material_kind,
            material_digest=digest,
        )
        binding = store.write_document(
            relative_ref=ref,
            document=material,
            digest_field="material_digest",
        )
        if set(binding) != _TYPED_BINDING_FIELDS:
            raise V31SentimentProjectionCompositionV2Error(
                "V31_SENTIMENT_COMPOSITION_OUTPUT_BINDING_INVALID"
            )
        bindings.append(dict(binding))
    return sorted(bindings, key=lambda row: row["relative_ref"])


def compose_and_persist_v31_sentiment_projection_v2(
    *,
    run_store: V31SentimentProjectionRunReaderV2,
    projection_store: V31SentimentProjectionOutputStoreV2,
    run_id: str,
    cycle_index: int,
) -> Mapping[str, Any]:
    """Build/recover one immutable cycle projection without changing a cursor."""

    if (
        not isinstance(run_id, str)
        or not run_id
        or isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_IDENTITY_INVALID"
        )
    try:
        checkpoint = run_store.load_checkpoint(run_id=run_id)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_CHECKPOINT_INVALID"
        ) from exc
    current_admission, current_admission_binding = _load_admission(
        store=run_store, run_id=run_id, cycle_index=cycle_index
    )
    (
        previous_registry,
        previous_dataset,
        previous_admission,
        previous_bindings,
    ) = _accepted_previous_inputs(
        store=run_store,
        run_id=run_id,
        cycle_index=cycle_index,
        checkpoint=checkpoint,
        current_admission=current_admission,
    )
    pit_rows = _copied_rows(current_admission, artifact_role="PIT_DATASET")
    if len(pit_rows) != 1:
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_CURRENT_DATASET_NOT_UNIQUE"
        )
    pit_dataset, pit_binding = _read_copied_document(
        store=run_store, row=pit_rows[0]
    )
    information_registry, event_bindings = _current_information_registry(
        store=run_store,
        run_id=run_id,
        cycle_index=cycle_index,
        admission=current_admission,
        previous_registry=previous_registry,
    )
    try:
        receipt = build_v31_sentiment_native_projection_receipt_v2(
            projection_id=(
                f"v31-native-sentiment:{run_id}:cycle:{cycle_index:04d}"
            ),
            pit_dataset=pit_dataset,
            information_revision_registry=information_registry,
            cycle_source_admission=current_admission,
            previous_pit_dataset=previous_dataset,
            previous_cycle_source_admission=previous_admission,
            axis_state_bindings=(),
        )
    except V31SentimentProjectionAdapterV2Error as exc:
        raise V31SentimentProjectionCompositionV2Error(
            f"V31_SENTIMENT_COMPOSITION_ADAPTER_FAILED:{exc}"
        ) from exc
    if receipt["projection"]["axis_state_bindings"] or any(
        row["ordinal_value"] is not None
        for row in receipt["projection"]["axis_projections"]
    ):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_UNKNOWN_UPGRADE_FORBIDDEN"
        )

    registry = receipt["native_source_registry"]
    registry_binding = projection_store.write_document(
        relative_ref=sentiment_source_registry_ref_v2(cycle_index),
        document=registry,
        digest_field="registry_digest",
    )
    information_material_bindings = _write_materials(
        store=projection_store,
        cycle_index=cycle_index,
        values=receipt["information_datum_binding_materials"],
        material_kind="information",
    )
    derived_material_bindings = _write_materials(
        store=projection_store,
        cycle_index=cycle_index,
        values=receipt["derived_evidence_materials"],
        material_kind="derived",
    )
    receipt_binding = projection_store.write_document(
        relative_ref=sentiment_projection_receipt_ref_v2(cycle_index),
        document=receipt,
        digest_field="projection_receipt_digest",
    )
    for binding in (registry_binding, receipt_binding):
        if set(binding) != _TYPED_BINDING_FIELDS:
            raise V31SentimentProjectionCompositionV2Error(
                "V31_SENTIMENT_COMPOSITION_OUTPUT_BINDING_INVALID"
            )
    durable_receipt = projection_store.read_document(
        relative_ref=receipt_binding["relative_ref"],
        digest_field=receipt_binding["digest_field"],
        expected_semantic_digest=receipt_binding["semantic_digest"],
    )
    try:
        verify_v31_sentiment_native_projection_receipt_v2(
            durable_receipt,
            pit_dataset=pit_dataset,
            information_revision_registry=information_registry,
            cycle_source_admission=current_admission,
            previous_pit_dataset=previous_dataset,
            previous_cycle_source_admission=previous_admission,
        )
    except V31SentimentProjectionAdapterV2Error as exc:
        raise V31SentimentProjectionCompositionV2Error(
            f"V31_SENTIMENT_COMPOSITION_DURABLE_REPLAY_FAILED:{exc}"
        ) from exc
    replayed_binding = projection_store.artifact_binding(
        relative_ref=receipt_binding["relative_ref"],
        digest_field=receipt_binding["digest_field"],
        expected_semantic_digest=receipt_binding["semantic_digest"],
    )
    if dict(replayed_binding) != dict(receipt_binding):
        raise V31SentimentProjectionCompositionV2Error(
            "V31_SENTIMENT_COMPOSITION_RECEIPT_PHYSICAL_DRIFT"
        )
    return {
        "run_id": run_id,
        "cycle_index": cycle_index,
        "support_bindings": {
            "sentiment_source_registry": dict(registry_binding),
            "sentiment_projection": dict(receipt_binding),
        },
        "material_bindings": (
            information_material_bindings + derived_material_bindings
        ),
        "source_input_bindings": {
            "cycle_source_admission": current_admission_binding,
            "pit_dataset": pit_binding,
            "information_event_records": event_bindings,
            **previous_bindings,
        },
        "information_revision_registry": information_registry,
        "projection_receipt": dict(durable_receipt),
    }


__all__ = [
    "V31SentimentProjectionCompositionV2Error",
    "V31SentimentProjectionOutputStoreV2",
    "V31SentimentProjectionRunReaderV2",
    "compose_and_persist_v31_sentiment_projection_v2",
]
