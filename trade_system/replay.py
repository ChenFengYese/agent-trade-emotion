"""Deterministic, point-in-time replay over append-only evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Iterator, List, Optional, Set

from .event_store import EventStore
from .types import AvailabilityKind, AvailabilityRecord, RawCapture


@dataclass(frozen=True)
class ReplayEvent:
    raw: RawCapture
    availability: AvailabilityRecord


class ReplayError(RuntimeError):
    pass


class DeterministicReplay:
    """Release only the frozen derived record available at virtual time."""

    def __init__(self, store: EventStore, allow_reconstructed: bool = False) -> None:
        self.store = store
        self.allow_reconstructed = allow_reconstructed

    @staticmethod
    def events_from_records(
        raws: Iterable[RawCapture],
        records: Iterable[AvailabilityRecord],
        *,
        allow_reconstructed: bool = False,
        until: Optional[datetime] = None,
    ) -> Iterator[ReplayEvent]:
        raw_by_id: Dict[str, RawCapture] = {raw.event_id: raw for raw in raws}
        available: List[AvailabilityRecord] = []
        for record in records:
            if record.availability_kind == AvailabilityKind.RECONSTRUCTED and not allow_reconstructed:
                continue
            if until is not None and record.available_at > until:
                continue
            available.append(record)
        available.sort(
            key=lambda item: (
                item.available_at,
                raw_by_id[item.event_id].capture_seq if item.event_id in raw_by_id else -1,
                item.event_id,
                item.schema_version,
            )
        )
        emitted: Set[tuple] = set()
        for record in available:
            raw = raw_by_id.get(record.event_id)
            if raw is None:
                raise ReplayError("availability record references missing raw %s" % record.event_id)
            key = (record.event_id, record.schema_version, record.derived_at)
            if key in emitted:
                raise ReplayError("duplicate frozen availability version %r" % (key,))
            emitted.add(key)
            yield ReplayEvent(raw=raw, availability=record)

    def events(self, until: Optional[datetime] = None) -> Iterator[ReplayEvent]:
        return self.events_from_records(
            self.store.iter_raw(),
            self.store.iter_availability(),
            allow_reconstructed=self.allow_reconstructed,
            until=until,
        )

    @staticmethod
    def _digest_events(events: Iterable[ReplayEvent]) -> str:
        digest = hashlib.sha256()
        for event in events:
            payload = {
                "capture_seq": event.raw.capture_seq,
                "event_id": event.raw.event_id,
                "available_at": event.availability.available_at.isoformat(),
                "availability_kind": event.availability.availability_kind.value,
                "schema_version": event.availability.schema_version,
                "normalized": event.availability.normalized,
                "quality_flags": event.availability.quality_flags,
            }
            digest.update(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
        return digest.hexdigest()

    @classmethod
    def digest_from_records(
        cls,
        raws: Iterable[RawCapture],
        records: Iterable[AvailabilityRecord],
        *,
        allow_reconstructed: bool = False,
        until: Optional[datetime] = None,
    ) -> str:
        return cls._digest_events(cls.events_from_records(raws, records, allow_reconstructed=allow_reconstructed, until=until))

    def digest(self, until: Optional[datetime] = None) -> str:
        return self._digest_events(self.events(until=until))
