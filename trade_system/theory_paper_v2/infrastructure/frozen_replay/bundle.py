"""Digest-bound local/public replay bundles with strict PIT scope separation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlparse

from ...domain.common import EXTERNAL_EXECUTION_AUTHORITY, SYSTEM_MODE
from ...domain.contracts.canonical import canonical_digest
from ...domain.evidence.model import EvidenceScope


class FrozenReplayBundleError(ValueError):
    pass


class DatasetType(StrEnum):
    LEGACY_ACTUAL_INPUT = "LEGACY_ACTUAL_INPUT"
    HISTORICAL_COUNTERFACTUAL_REPLAY = "HISTORICAL_COUNTERFACTUAL_REPLAY"
    SYNTHETIC_CONTRACT_FIXTURE = "SYNTHETIC_CONTRACT_FIXTURE"
    INDEPENDENT_FROZEN_EVALUATION = "INDEPENDENT_FROZEN_EVALUATION"


class SourceKind(StrEnum):
    PUBLIC_OFFICIAL_API = "PUBLIC_OFFICIAL_API"
    PUBLIC_OFFICIAL_ARCHIVE = "PUBLIC_OFFICIAL_ARCHIVE"
    RECOGNIZED_CALENDAR = "RECOGNIZED_CALENDAR"
    LOCAL_IMMUTABLE_CAPTURE = "LOCAL_IMMUTABLE_CAPTURE"


class ReplayRecordKind(StrEnum):
    CLOSED_BAR = "CLOSED_BAR"
    CONTEMPORANEOUS_EVIDENCE = "CONTEMPORANEOUS_EVIDENCE"
    CALENDAR = "CALENDAR"
    POLICY = "POLICY"
    LEGACY_STATE = "LEGACY_STATE"
    EVALUATION_OUTCOME = "EVALUATION_OUTCOME"


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MUTABLE_ALIASES = {"current", "latest"}


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise FrozenReplayBundleError("CLOCK_TIME_INVALID")


def _timestamp(value: datetime) -> str:
    _require_utc(value)
    return value.isoformat().replace("+00:00", "Z")


def _explicit_id(value: str) -> None:
    if not value or value.casefold() in _MUTABLE_ALIASES:
        raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")


def _valid_public_locator(locator: str) -> bool:
    parsed = urlparse(locator)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _valid_local_locator(locator: str) -> bool:
    path = PurePosixPath(locator)
    return path.is_absolute() and ".." not in path.parts


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    source_id: str
    source_kind: SourceKind
    provider_id: str
    source_locator: str
    source_revision: str
    released_at: datetime
    captured_at: datetime
    committed_at: datetime
    immutable_capture: bool
    provider_release_time_proven: bool
    physical_existence_proven: bool
    source_commit_receipt_digest: str
    source_commit_receipt_valid: bool
    source_content_digest: str
    provenance_digest: str

    def __post_init__(self) -> None:
        for value in (self.released_at, self.captured_at, self.committed_at):
            _require_utc(value)
        for value in (self.source_id, self.provider_id, self.source_revision):
            _explicit_id(value)
        if (
            _SHA256.fullmatch(self.source_commit_receipt_digest) is None
            or _SHA256.fullmatch(self.source_content_digest) is None
            or _SHA256.fullmatch(self.provenance_digest) is None
        ):
            raise FrozenReplayBundleError("EVIDENCE_LINEAGE_INVALID")


def _source_payload(source: SourceProvenance) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_kind": source.source_kind.value,
        "provider_id": source.provider_id,
        "source_locator": source.source_locator,
        "source_revision": source.source_revision,
        "released_at": _timestamp(source.released_at),
        "captured_at": _timestamp(source.captured_at),
        "committed_at": _timestamp(source.committed_at),
        "immutable_capture": source.immutable_capture,
        "provider_release_time_proven": source.provider_release_time_proven,
        "physical_existence_proven": source.physical_existence_proven,
        "source_commit_receipt_digest": source.source_commit_receipt_digest,
        "source_commit_receipt_valid": source.source_commit_receipt_valid,
        "source_content_digest": source.source_content_digest,
    }


def build_source_provenance(
    *,
    source_id: str,
    source_kind: SourceKind,
    provider_id: str,
    source_locator: str,
    source_revision: str,
    released_at: datetime,
    captured_at: datetime,
    committed_at: datetime,
    source_commit_receipt_digest: str,
    source_content_digest: str,
    immutable_capture: bool = True,
    provider_release_time_proven: bool = True,
    physical_existence_proven: bool = True,
    source_commit_receipt_valid: bool = True,
) -> SourceProvenance:
    source = SourceProvenance(
        source_id=source_id,
        source_kind=source_kind,
        provider_id=provider_id,
        source_locator=source_locator,
        source_revision=source_revision,
        released_at=released_at,
        captured_at=captured_at,
        committed_at=committed_at,
        immutable_capture=immutable_capture,
        provider_release_time_proven=provider_release_time_proven,
        physical_existence_proven=physical_existence_proven,
        source_commit_receipt_digest=source_commit_receipt_digest,
        source_commit_receipt_valid=source_commit_receipt_valid,
        source_content_digest=source_content_digest,
        provenance_digest="0" * 64,
    )
    return replace(
        source, provenance_digest=canonical_digest(_source_payload(source))
    )


@dataclass(frozen=True, slots=True)
class FrozenReplayItem:
    item_id: str
    logical_key: str
    record_kind: ReplayRecordKind
    source_id: str
    source_revision: str
    payload_digest: str
    observed_at: datetime
    available_at: datetime
    ingested_at: datetime
    source_committed_at: datetime
    source_commit_receipt_digest: str
    source_commit_receipt_valid: bool
    physical_existence_proven: bool
    usage_scope: EvidenceScope
    decision_bearing: bool
    item_digest: str

    def __post_init__(self) -> None:
        for value in (
            self.observed_at,
            self.available_at,
            self.ingested_at,
            self.source_committed_at,
        ):
            _require_utc(value)
        for value in (
            self.item_id,
            self.logical_key,
            self.source_id,
            self.source_revision,
        ):
            _explicit_id(value)
        if any(
            _SHA256.fullmatch(value) is None
            for value in (
                self.payload_digest,
                self.source_commit_receipt_digest,
                self.item_digest,
            )
        ):
            raise FrozenReplayBundleError("EVIDENCE_LINEAGE_INVALID")


def _item_payload(item: FrozenReplayItem) -> dict[str, object]:
    return {
        "item_id": item.item_id,
        "logical_key": item.logical_key,
        "record_kind": item.record_kind.value,
        "source_id": item.source_id,
        "source_revision": item.source_revision,
        "payload_digest": item.payload_digest,
        "observed_at": _timestamp(item.observed_at),
        "available_at": _timestamp(item.available_at),
        "ingested_at": _timestamp(item.ingested_at),
        "source_committed_at": _timestamp(item.source_committed_at),
        "source_commit_receipt_digest": item.source_commit_receipt_digest,
        "source_commit_receipt_valid": item.source_commit_receipt_valid,
        "physical_existence_proven": item.physical_existence_proven,
        "usage_scope": item.usage_scope.value,
        "decision_bearing": item.decision_bearing,
    }


def build_frozen_replay_item(
    *,
    item_id: str,
    logical_key: str,
    record_kind: ReplayRecordKind,
    source: SourceProvenance,
    payload: bytes,
    observed_at: datetime,
    available_at: datetime,
    ingested_at: datetime,
    source_committed_at: datetime,
    usage_scope: EvidenceScope,
    decision_bearing: bool,
) -> FrozenReplayItem:
    item = FrozenReplayItem(
        item_id=item_id,
        logical_key=logical_key,
        record_kind=record_kind,
        source_id=source.source_id,
        source_revision=source.source_revision,
        payload_digest=hashlib.sha256(payload).hexdigest(),
        observed_at=observed_at,
        available_at=available_at,
        ingested_at=ingested_at,
        source_committed_at=source_committed_at,
        source_commit_receipt_digest=source.source_commit_receipt_digest,
        source_commit_receipt_valid=source.source_commit_receipt_valid,
        physical_existence_proven=source.physical_existence_proven,
        usage_scope=usage_scope,
        decision_bearing=decision_bearing,
        item_digest="0" * 64,
    )
    return replace(item, item_digest=canonical_digest(_item_payload(item)))


@dataclass(frozen=True, slots=True)
class FrozenReplayManifest:
    bundle_id: str
    manifest_version: str
    dataset_type: DatasetType
    source_cohort_id: str
    decision_cutoff: datetime
    frozen_at: datetime
    source_ids: tuple[str, ...]
    item_ids: tuple[str, ...]
    source_provenance_digests: tuple[str, ...]
    item_digests: tuple[str, ...]
    system_mode: str
    external_execution_authority: str
    executable: bool
    manifest_digest: str

    def __post_init__(self) -> None:
        _require_utc(self.decision_cutoff)
        _require_utc(self.frozen_at)
        for value in (
            self.bundle_id,
            self.manifest_version,
            self.source_cohort_id,
        ):
            _explicit_id(value)
        if (
            _SHA256.fullmatch(self.manifest_digest) is None
            or len(set(self.source_ids)) != len(self.source_ids)
            or len(set(self.item_ids)) != len(self.item_ids)
            or len(self.source_ids) != len(self.source_provenance_digests)
            or len(self.item_ids) != len(self.item_digests)
        ):
            raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")


def _manifest_payload(manifest: FrozenReplayManifest) -> dict[str, object]:
    return {
        "bundle_id": manifest.bundle_id,
        "manifest_version": manifest.manifest_version,
        "dataset_type": manifest.dataset_type.value,
        "source_cohort_id": manifest.source_cohort_id,
        "decision_cutoff": _timestamp(manifest.decision_cutoff),
        "frozen_at": _timestamp(manifest.frozen_at),
        "source_ids": list(manifest.source_ids),
        "item_ids": list(manifest.item_ids),
        "source_provenance_digests": list(
            manifest.source_provenance_digests
        ),
        "item_digests": list(manifest.item_digests),
        "system_mode": manifest.system_mode,
        "external_execution_authority": manifest.external_execution_authority,
        "executable": manifest.executable,
    }


def build_frozen_replay_manifest(
    *,
    bundle_id: str,
    dataset_type: DatasetType,
    source_cohort_id: str,
    decision_cutoff: datetime,
    frozen_at: datetime,
    sources: tuple[SourceProvenance, ...],
    items: tuple[FrozenReplayItem, ...],
) -> FrozenReplayManifest:
    ordered_sources = tuple(sorted(sources, key=lambda item: item.source_id))
    ordered_items = tuple(sorted(items, key=lambda item: item.item_id))
    manifest = FrozenReplayManifest(
        bundle_id=bundle_id,
        manifest_version="1.0.0",
        dataset_type=dataset_type,
        source_cohort_id=source_cohort_id,
        decision_cutoff=decision_cutoff,
        frozen_at=frozen_at,
        source_ids=tuple(item.source_id for item in ordered_sources),
        item_ids=tuple(item.item_id for item in ordered_items),
        source_provenance_digests=tuple(
            item.provenance_digest for item in ordered_sources
        ),
        item_digests=tuple(item.item_digest for item in ordered_items),
        system_mode=SYSTEM_MODE,
        external_execution_authority=EXTERNAL_EXECUTION_AUTHORITY,
        executable=False,
        manifest_digest="0" * 64,
    )
    return replace(
        manifest, manifest_digest=canonical_digest(_manifest_payload(manifest))
    )


@dataclass(frozen=True, slots=True)
class ValidatedFrozenReplayBundle:
    manifest: FrozenReplayManifest
    source_by_id: Mapping[str, SourceProvenance]
    item_by_id: Mapping[str, FrozenReplayItem]
    payload_by_item_id: Mapping[str, bytes]
    decision_item_ids: tuple[str, ...]
    market_replay_item_ids: tuple[str, ...]
    evaluation_only_item_ids: tuple[str, ...]
    system_mode: str = SYSTEM_MODE
    external_execution_authority: str = EXTERNAL_EXECUTION_AUTHORITY
    executable: bool = False


def _validate_source(source: SourceProvenance) -> None:
    if canonical_digest(_source_payload(source)) != source.provenance_digest:
        raise FrozenReplayBundleError("EVIDENCE_LINEAGE_INVALID")
    if source.source_kind is SourceKind.LOCAL_IMMUTABLE_CAPTURE:
        locator_valid = _valid_local_locator(source.source_locator)
    else:
        locator_valid = _valid_public_locator(source.source_locator)
    if (
        not locator_valid
        or not source.immutable_capture
        or not source.provider_release_time_proven
        or not source.physical_existence_proven
        or not source.source_commit_receipt_valid
        or source.released_at > source.captured_at
        or source.captured_at > source.committed_at
    ):
        raise FrozenReplayBundleError("EVIDENCE_LINEAGE_INVALID")


def _validate_item(
    *,
    item: FrozenReplayItem,
    source: SourceProvenance,
    payload: bytes,
    decision_cutoff: datetime,
    dataset_type: DatasetType,
) -> None:
    if canonical_digest(_item_payload(item)) != item.item_digest:
        raise FrozenReplayBundleError("EVIDENCE_LINEAGE_INVALID")
    if hashlib.sha256(payload).hexdigest() != item.payload_digest:
        raise FrozenReplayBundleError("EVIDENCE_LINEAGE_INVALID")
    if (
        item.source_revision != source.source_revision
        or item.source_commit_receipt_digest
        != source.source_commit_receipt_digest
        or item.source_committed_at != source.committed_at
        or not item.source_commit_receipt_valid
        or not item.physical_existence_proven
        or not (
            item.observed_at
            <= item.available_at
            <= item.ingested_at
            <= item.source_committed_at
        )
    ):
        raise FrozenReplayBundleError("EVIDENCE_LINEAGE_INVALID")
    if item.usage_scope is EvidenceScope.DECISION_CONTEMPORANEOUS:
        if not item.decision_bearing:
            raise FrozenReplayBundleError("PIT_MIXED_CUTOFF")
        if any(
            value > decision_cutoff
            for value in (
                item.available_at,
                item.ingested_at,
                item.source_committed_at,
            )
        ):
            raise FrozenReplayBundleError("PIT_FUTURE_AVAILABLE")
    elif item.usage_scope is EvidenceScope.COUNTERFACTUAL_MARKET_REPLAY:
        if (
            item.decision_bearing
            or item.record_kind is not ReplayRecordKind.CLOSED_BAR
            or dataset_type
            not in {
                DatasetType.HISTORICAL_COUNTERFACTUAL_REPLAY,
                DatasetType.SYNTHETIC_CONTRACT_FIXTURE,
                DatasetType.INDEPENDENT_FROZEN_EVALUATION,
            }
            or item.observed_at > decision_cutoff
            or item.available_at > decision_cutoff
            or source.released_at > decision_cutoff
        ):
            raise FrozenReplayBundleError("PIT_FUTURE_AVAILABLE")
    elif item.usage_scope is EvidenceScope.EVALUATION_ONLY:
        if item.decision_bearing:
            raise FrozenReplayBundleError("PIT_MIXED_CUTOFF")
    else:  # pragma: no cover - closed enum defensive branch
        raise FrozenReplayBundleError("PIT_MIXED_CUTOFF")


def validate_frozen_replay_bundle(
    *,
    manifest: FrozenReplayManifest,
    sources: tuple[SourceProvenance, ...],
    items: tuple[FrozenReplayItem, ...],
    payload_by_item_id: Mapping[str, bytes],
) -> ValidatedFrozenReplayBundle:
    """Validate exact membership, digests, provenance, and scope-aware PIT."""

    if (
        manifest.system_mode != SYSTEM_MODE
        or manifest.external_execution_authority
        != EXTERNAL_EXECUTION_AUTHORITY
        or manifest.executable
        or manifest.frozen_at < manifest.decision_cutoff
    ):
        raise FrozenReplayBundleError("AUTHORITY_STATUS_MISMATCH")
    if canonical_digest(_manifest_payload(manifest)) != manifest.manifest_digest:
        raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
    source_by_id = {item.source_id: item for item in sources}
    item_by_id = {item.item_id: item for item in items}
    if len(source_by_id) != len(sources) or len(item_by_id) != len(items):
        raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
    if (
        tuple(sorted(source_by_id)) != manifest.source_ids
        or tuple(sorted(item_by_id)) != manifest.item_ids
        or tuple(sorted(payload_by_item_id)) != manifest.item_ids
    ):
        raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
    ordered_sources = tuple(source_by_id[item] for item in manifest.source_ids)
    ordered_items = tuple(item_by_id[item] for item in manifest.item_ids)
    if (
        tuple(item.provenance_digest for item in ordered_sources)
        != manifest.source_provenance_digests
        or tuple(item.item_digest for item in ordered_items)
        != manifest.item_digests
    ):
        raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
    logical_keys = [item.logical_key for item in ordered_items]
    if len(set(logical_keys)) != len(logical_keys):
        raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
    for source in ordered_sources:
        _validate_source(source)
        if source.committed_at > manifest.frozen_at:
            raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
    for item in ordered_items:
        try:
            source = source_by_id[item.source_id]
        except KeyError as exc:
            raise FrozenReplayBundleError(
                "EVIDENCE_SOURCE_UNREGISTERED"
            ) from exc
        payload = payload_by_item_id[item.item_id]
        if not isinstance(payload, bytes):
            raise FrozenReplayBundleError("OFFLINE_REPLAY_FAILED_NO_COMMIT")
        _validate_item(
            item=item,
            source=source,
            payload=payload,
            decision_cutoff=manifest.decision_cutoff,
            dataset_type=manifest.dataset_type,
        )
    decision = tuple(
        item.item_id
        for item in ordered_items
        if item.usage_scope is EvidenceScope.DECISION_CONTEMPORANEOUS
    )
    replay = tuple(
        item.item_id
        for item in ordered_items
        if item.usage_scope is EvidenceScope.COUNTERFACTUAL_MARKET_REPLAY
    )
    evaluation = tuple(
        item.item_id
        for item in ordered_items
        if item.usage_scope is EvidenceScope.EVALUATION_ONLY
    )
    return ValidatedFrozenReplayBundle(
        manifest=manifest,
        source_by_id=MappingProxyType(dict(source_by_id)),
        item_by_id=MappingProxyType(dict(item_by_id)),
        payload_by_item_id=MappingProxyType(dict(payload_by_item_id)),
        decision_item_ids=decision,
        market_replay_item_ids=replay,
        evaluation_only_item_ids=evaluation,
    )
