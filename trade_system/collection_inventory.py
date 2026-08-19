"""Read-only inventory of terminal public collection evidence stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .event_store import EventStore
from .replay import DeterministicReplay
from .types import iso_utc, utc_now


def _manifest_paths(roots: Iterable[Path]) -> List[Path]:
    selected = set()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            continue
        for path in root.rglob("manifests/collection/*.json"):
            selected.add(path.resolve())
    return sorted(selected)


def inventory_collections(roots: Iterable[Path]) -> Dict[str, Any]:
    """Inspect existing collection manifests without creating or changing data.

    A collection is reported as ``SEALED_CURRENT`` only when the current store
    audit and replay digests still match the terminal manifest.  The command
    deliberately reports raw duration totals as descriptive only: it neither
    merges overlapping windows nor applies any G1 policy.
    """
    manifests = _manifest_paths(tuple(Path(item) for item in roots))
    store_cache: Dict[Path, Dict[str, Any]] = {}
    rows: List[Dict[str, Any]] = []
    for manifest_path in manifests:
        store_root = manifest_path.parents[2]
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"manifest_path": str(manifest_path), "status": "INVALID_MANIFEST", "issues": [str(exc)]})
            continue
        collection_id = manifest.get("collection_id")
        if not isinstance(manifest, dict) or manifest.get("record_type") != "collection_manifest" or not isinstance(collection_id, str) or not collection_id:
            rows.append({"manifest_path": str(manifest_path), "status": "INVALID_MANIFEST", "issues": ["not a terminal collection manifest"]})
            continue
        if store_root not in store_cache:
            try:
                store = EventStore(store_root, create=False)
                audit_valid, audit_issues, audit_digest, all_raws, all_availability = store.audit_with_records()
                store_cache[store_root] = {
                    "store": store,
                    "audit_valid": audit_valid,
                    "audit_issues": audit_issues,
                    "audit_digest": audit_digest,
                    "replay_digest": DeterministicReplay.digest_from_records(all_raws, all_availability),
                    "raws": all_raws,
                    "availability": all_availability,
                }
            except Exception as exc:
                store_cache[store_root] = {"error": "%s: %s" % (type(exc).__name__, exc)}
        cached = store_cache[store_root]
        if "error" in cached:
            rows.append({"manifest_path": str(manifest_path), "collection_id": collection_id, "status": "STORE_UNREADABLE", "issues": [cached["error"]]})
            continue
        store = cached["store"]
        raws = [raw for raw in cached["raws"] if raw.connection_id.startswith(collection_id + "-")]
        raw_ids = {raw.event_id for raw in raws}
        availability = [item for item in cached["availability"] if item.event_id in raw_ids]
        segments = sorted({Path(raw.raw_segment).stem for raw in raws})
        sealed_segments = {item.stem for item in store.manifest_root.glob("*.json")}
        all_sealed = bool(segments) and all(segment in sealed_segments for segment in segments)
        audit_matches = cached["audit_digest"] == manifest.get("audit_digest")
        replay_matches = cached["replay_digest"] == manifest.get("replay_digest")
        issues = []
        if not raws:
            issues.append("collection has no current raw records")
        if not all_sealed:
            issues.append("collection raw segments are not all sealed")
        if not cached["audit_valid"]:
            issues.extend(cached["audit_issues"])
        if not audit_matches:
            issues.append("current audit digest differs from terminal manifest")
        if not replay_matches:
            issues.append("current replay digest differs from terminal manifest")
        result = manifest.get("collection_result")
        if result != "QUALIFIED_SMOKE":
            status = "UNQUALIFIED"
        elif cached["audit_valid"] and all_sealed and audit_matches and replay_matches:
            status = "SEALED_CURRENT"
        else:
            status = "QUALIFIED_BUT_NOT_CURRENT"
        rows.append({
            "collection_id": collection_id,
            "data_dir": str(store_root),
            "manifest_path": str(manifest_path),
            "status": status,
            "collection_result": result,
            "duration_seconds": manifest.get("duration_seconds"),
            "raw_records": len(raws),
            "availability_records": len(availability),
            "segments": segments,
            "all_segments_sealed": all_sealed,
            "current_audit_valid": cached["audit_valid"],
            "current_audit_digest": cached["audit_digest"],
            "current_replay_digest": cached["replay_digest"],
            "source_registry": manifest.get("source_registry"),
            "capture_plan": manifest.get("capture_plan"),
            "episode_policy": manifest.get("episode_policy"),
            "issues": issues,
        })
    rows.sort(key=lambda item: (str(item.get("data_dir", "")), str(item.get("collection_id", ""))))
    sealed_current = [row for row in rows if row.get("status") == "SEALED_CURRENT"]
    durations = [row.get("duration_seconds") for row in sealed_current]
    descriptive_duration = sum(float(item) for item in durations if isinstance(item, (int, float)))
    return {
        "record_type": "collection_inventory",
        "inspected_at": iso_utc(utc_now()),
        "roots": [str(Path(item)) for item in roots],
        "collections": rows,
        "summary": {
            "terminal_manifests": len(rows),
            "sealed_current_collections": len(sealed_current),
            "descriptive_duration_seconds": descriptive_duration,
            "distinct_evidence_stores": len({row.get("data_dir") for row in rows if row.get("data_dir")}),
        },
        "limitation": "Inventory is read-only and descriptive. It does not deduplicate overlapping time windows, infer market-state coverage, freeze thresholds, or grant G1/G2/G3 eligibility.",
    }
