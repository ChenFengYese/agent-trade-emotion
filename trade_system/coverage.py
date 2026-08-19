"""Evidence coverage reporting without inventing unseen market messages."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from .event_store import EventStore
from .types import AvailabilityKind, iso_utc


def _ranges_missing(values: Iterable[int]) -> List[Tuple[int, int]]:
    ordered = sorted(set(values))
    if not ordered:
        return []
    missing = []
    expected = ordered[0]
    for value in ordered:
        if value > expected:
            missing.append((expected, value - 1))
        expected = value + 1
    return missing


def build_coverage_report(store: EventStore) -> Dict[str, Any]:
    """Summarize what the local store contains, including observable gaps only.

    `ingest_seq` is a local capture sequence. Its continuity proves only that
    this process did not omit a raw record between its own sequence values; it
    cannot prove that a venue did not omit a message on a non-sequenced stream.
    """
    raws = list(store.iter_raw())
    availability = list(store.iter_availability())
    available_ids = {record.event_id for record in availability}
    groups: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    connection_sequences: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    connection_streams: Dict[Tuple[str, str], set] = defaultdict(set)
    for raw in raws:
        key = (raw.source, raw.venue, raw.instrument, raw.stream)
        summary = groups.setdefault(key, {
            "source": raw.source,
            "venue": raw.venue,
            "instrument": raw.instrument,
            "stream": raw.stream,
            "raw_records": 0,
            "first_receive_time": raw.receive_time,
            "last_receive_time": raw.receive_time,
            "connection_ids": set(),
            "raw_without_availability": 0,
            "actual_availability": 0,
            "reconstructed_availability": 0,
        })
        summary["raw_records"] += 1
        summary["first_receive_time"] = min(summary["first_receive_time"], raw.receive_time)
        summary["last_receive_time"] = max(summary["last_receive_time"], raw.receive_time)
        summary["connection_ids"].add(raw.connection_id)
        if raw.event_id not in available_ids:
            summary["raw_without_availability"] += 1
        connection_key = (raw.source, raw.connection_id)
        connection_sequences[connection_key].append(raw.ingest_seq)
        connection_streams[connection_key].add(raw.stream)

    raw_index = {raw.event_id: raw for raw in raws}
    for record in availability:
        raw = raw_index.get(record.event_id)
        if raw is None:
            continue  # audit() separately reports the invalid reference.
        group = groups[(raw.source, raw.venue, raw.instrument, raw.stream)]
        if record.availability_kind == AvailabilityKind.ACTUAL:
            group["actual_availability"] += 1
        else:
            group["reconstructed_availability"] += 1

    per_stream = []
    for key in sorted(groups):
        item = groups[key]
        per_stream.append({
            "source": item["source"],
            "venue": item["venue"],
            "instrument": item["instrument"],
            "stream": item["stream"],
            "raw_records": item["raw_records"],
            "first_receive_time": iso_utc(item["first_receive_time"]),
            "last_receive_time": iso_utc(item["last_receive_time"]),
            "connection_ids": sorted(item["connection_ids"]),
            "raw_without_availability": item["raw_without_availability"],
            "actual_availability": item["actual_availability"],
            "reconstructed_availability": item["reconstructed_availability"],
        })

    connections = []
    for (source, connection_id), sequences in sorted(connection_sequences.items()):
        connections.append({
            "source": source,
            "connection_id": connection_id,
            "streams": sorted(connection_streams[(source, connection_id)]),
            "raw_records": len(sequences),
            "first_ingest_seq": min(sequences),
            "last_ingest_seq": max(sequences),
            "observable_ingest_seq_gaps": [[start, end] for start, end in _ranges_missing(sequences)],
        })

    sealed = sorted(path.stem for path in store.manifest_root.glob("*.json"))
    collection_manifests = sorted(path.name for path in store.collection_manifest_root.glob("*.json"))
    raw_segments = sorted(path.stem for path in store.raw_root.glob("*.ndjson"))
    valid, issues, digest = store.audit()
    return {
        "audit_valid": valid,
        "audit_issues": issues,
        "audit_digest": digest,
        "raw_records": len(raws),
        "availability_records": len(availability),
        "raw_segments": raw_segments,
        "sealed_raw_segments": sealed,
        "collection_manifests": collection_manifests,
        "unsealed_raw_segments": [segment for segment in raw_segments if segment not in set(sealed)],
        "connections": connections,
        "streams": per_stream,
        "limitation": "Coverage reflects locally captured evidence only. ingest_seq continuity is meaningful only at source+connection scope and cannot infer missed venue messages for streams without exchange sequence guarantees.",
    }
