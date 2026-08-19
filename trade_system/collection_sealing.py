"""Collection-level sealing for terminal append-only evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .event_store import EventStore


def seal_collection(store: EventStore, collection_id: str) -> Dict[str, Any]:
    """Seal every raw date segment belonging to one terminal collection.

    Raw segments are date-scoped rather than collection-scoped. A segment is
    refused when another writer cannot be tied to a terminal manifest, which
    prevents a UTC-midnight boundary from sealing an active collector.
    """
    manifest_path = store.collection_manifest_root / (collection_id + ".json")
    try:
        terminal = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("terminal collection manifest is required before sealing") from exc
    if terminal.get("record_type") != "collection_manifest" or terminal.get("collection_id") != collection_id:
        raise ValueError("collection manifest identity is invalid")
    raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(collection_id + "-")]
    if not raws:
        raise ValueError("no raw records found for collection prefix: %s" % collection_id)
    segments = sorted({Path(raw.raw_segment).stem for raw in raws})
    terminal_ids = {path.stem for path in store.collection_manifest_root.glob("*.json")}
    unknown_connections = sorted({
        raw.connection_id
        for raw in store.iter_raw()
        if Path(raw.raw_segment).stem in segments
        and not raw.connection_id.startswith(collection_id + "-")
        and not any(raw.connection_id.startswith(terminal_id + "-") for terminal_id in terminal_ids)
    })
    if unknown_connections:
        raise ValueError("refusing to seal segment with unknown or active writers: %s" % ",".join(unknown_connections))
    sealed, already_sealed = [], []
    for segment in segments:
        raw_manifest = store.manifest_root / (segment + ".json")
        if raw_manifest.exists():
            already_sealed.append(str(raw_manifest))
        else:
            sealed.append(str(store.seal_raw_segment(segment)))
    return {
        "collection_id": collection_id,
        "segments": segments,
        "sealed_manifests": sealed,
        "already_sealed_manifests": already_sealed,
    }
