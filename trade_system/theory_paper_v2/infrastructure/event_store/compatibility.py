"""Deterministic full replay and immutable-event compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from ...domain.contracts.canonical import canonical_digest
from .store import FileUnitOfWork


class EventCompatibilityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UpcasterEntry:
    event_schema_id: str
    from_event_schema_version: str
    to_event_schema_version: str
    input_event_schema_ref: str
    output_event_schema_ref: str
    upcaster_code_digest: str
    interpretation_only: bool = True


@dataclass(frozen=True, slots=True)
class ProjectionCursorEntry:
    consumer_id: str
    last_processed_event_ref: str
    lag_status: str


@dataclass(frozen=True, slots=True)
class EventReplayCompatibilityManifest:
    manifest_id: str
    manifest_version: str
    genesis_contract_ref: str
    genesis_state_digest: str
    first_event_sequence: int
    last_event_sequence: int
    expected_event_chain_head_digest: str
    event_schema_version_refs: tuple[str, ...]
    reducer_version_refs: tuple[str, ...]
    upcaster_chain: tuple[UpcasterEntry, ...]
    projection_cursor_set: tuple[ProjectionCursorEntry, ...]
    full_replay_expected_digest: str
    compatibility_test_refs: tuple[str, ...]
    manifest_digest: str
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False


def build_event_replay_compatibility_manifest(
    *,
    manifest_id: str,
    genesis_contract_ref: str,
    genesis_state_digest: str,
    first_event_sequence: int,
    last_event_sequence: int,
    expected_event_chain_head_digest: str,
    event_schema_version_refs: tuple[str, ...],
    reducer_version_refs: tuple[str, ...],
    full_replay_expected_digest: str,
    compatibility_test_refs: tuple[str, ...],
    upcaster_chain: tuple[UpcasterEntry, ...] = (),
    projection_cursor_set: tuple[ProjectionCursorEntry, ...] = (),
) -> EventReplayCompatibilityManifest:
    if (
        not manifest_id
        or not genesis_contract_ref
        or first_event_sequence < 0
        or last_event_sequence < first_event_sequence
        or not event_schema_version_refs
        or not reducer_version_refs
        or not compatibility_test_refs
        or any(not entry.interpretation_only for entry in upcaster_chain)
    ):
        raise EventCompatibilityError(
            "EVENT_REPLAY_COMPATIBILITY_MANIFEST_INVALID"
        )
    payload = {
        "manifest_id": manifest_id,
        "manifest_version": "1.0.0",
        "genesis_contract_ref": genesis_contract_ref,
        "genesis_state_digest": genesis_state_digest,
        "first_event_sequence": first_event_sequence,
        "last_event_sequence": last_event_sequence,
        "expected_event_chain_head_digest": (
            expected_event_chain_head_digest
        ),
        "event_schema_version_refs": event_schema_version_refs,
        "reducer_version_refs": reducer_version_refs,
        "upcaster_chain": tuple(
            (
                entry.event_schema_id,
                entry.from_event_schema_version,
                entry.to_event_schema_version,
                entry.input_event_schema_ref,
                entry.output_event_schema_ref,
                entry.upcaster_code_digest,
                entry.interpretation_only,
            )
            for entry in upcaster_chain
        ),
        "projection_cursor_set": tuple(
            (
                entry.consumer_id,
                entry.last_processed_event_ref,
                entry.lag_status,
            )
            for entry in projection_cursor_set
        ),
        "full_replay_expected_digest": full_replay_expected_digest,
        "compatibility_test_refs": compatibility_test_refs,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return EventReplayCompatibilityManifest(
        manifest_id=manifest_id,
        manifest_version="1.0.0",
        genesis_contract_ref=genesis_contract_ref,
        genesis_state_digest=genesis_state_digest,
        first_event_sequence=first_event_sequence,
        last_event_sequence=last_event_sequence,
        expected_event_chain_head_digest=(
            expected_event_chain_head_digest
        ),
        event_schema_version_refs=event_schema_version_refs,
        reducer_version_refs=reducer_version_refs,
        upcaster_chain=upcaster_chain,
        projection_cursor_set=projection_cursor_set,
        full_replay_expected_digest=full_replay_expected_digest,
        compatibility_test_refs=compatibility_test_refs,
        manifest_digest=canonical_digest(payload),
    )


def verify_event_replay_compatibility(
    *,
    manifest: EventReplayCompatibilityManifest,
    store: FileUnitOfWork,
    genesis_state: Mapping[str, object],
    reducer: Callable[
        [Mapping[str, object], Mapping[str, object]], Mapping[str, object]
    ],
    registered_upcaster_digests: Mapping[
        tuple[str, str, str], str
    ] | None = None,
) -> str:
    """Replay accepted immutable events without treating projections as heads."""

    if (
        manifest.system_mode != "E0_OFFLINE_COUNTERFACTUAL"
        or manifest.external_execution_authority != "NONE_E0"
        or manifest.executable
        or canonical_digest(genesis_state) != manifest.genesis_state_digest
    ):
        raise EventCompatibilityError(
            "EVENT_REPLAY_GENESIS_MISMATCH"
        )
    upcasters = registered_upcaster_digests or {}
    for entry in manifest.upcaster_chain:
        key = (
            entry.event_schema_id,
            entry.from_event_schema_version,
            entry.to_event_schema_version,
        )
        if (
            not entry.interpretation_only
            or upcasters.get(key) != entry.upcaster_code_digest
        ):
            raise EventCompatibilityError(
                "EVENT_REPLAY_UPCASTER_UNAVAILABLE"
            )
    recovered = store.recover()
    events = tuple(
        event
        for transaction in recovered["commits"]
        for event in transaction["stored_events"]
    )
    if (
        not events
        or events[0]["event_sequence"] != manifest.first_event_sequence
        or events[-1]["event_sequence"] != manifest.last_event_sequence
        or events[-1]["event_digest"]
        != manifest.expected_event_chain_head_digest
    ):
        raise EventCompatibilityError(
            "EVENT_REPLAY_CHAIN_MISMATCH"
        )
    registered_schemas = {
        ref.rsplit(":", 1)[0]
        for ref in manifest.event_schema_version_refs
        if ":" in ref
    }
    state: Mapping[str, object] = dict(genesis_state)
    for event in events:
        if event["payload_schema_id"] not in registered_schemas:
            raise EventCompatibilityError(
                "EVENT_REPLAY_SCHEMA_UNREGISTERED"
            )
        state = reducer(state, event)
        if not isinstance(state, Mapping):
            raise EventCompatibilityError(
                "EVENT_REPLAY_REDUCER_INVALID"
            )
    digest = canonical_digest(state)
    if digest != manifest.full_replay_expected_digest:
        raise EventCompatibilityError(
            "EVENT_REPLAY_STATE_DIGEST_MISMATCH"
        )
    return digest


def require_authoritative_command_head(
    *,
    head_kind: str,
    aggregate_revision: int | None,
    aggregate_state_digest: str | None,
) -> None:
    if (
        head_kind != "AGGREGATE_HEAD_RECEIPT"
        or aggregate_revision is None
        or aggregate_revision < 0
        or aggregate_state_digest is None
    ):
        raise EventCompatibilityError(
            "PROJECTION_NOT_COMMAND_HEAD"
        )
