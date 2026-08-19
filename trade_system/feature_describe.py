"""Pre-freeze descriptive summaries for sealed forward feature evidence."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .collection_inventory import inventory_collections
from .event_store import EventStore
from .pipeline import FeaturePipeline


class FeatureDescribeError(ValueError):
    pass


def _nearest_rank(values: List[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        raise FeatureDescribeError("cannot calculate percentile of empty feature series")
    index = max(0, min(len(values) - 1, int((Decimal(len(values)) * percentile).to_integral_value(rounding="ROUND_CEILING")) - 1))
    return values[index]


def describe_sealed_features(roots: Iterable[Path]) -> Dict[str, Any]:
    """Summarize feature distributions from currently sealed collections only.

    This is intentionally a pre-registration aid, not a model fit: it does
    not consume labels, action outcomes, costs, forecasts, or holdouts, and it
    never writes a research artifact or recommends a threshold.
    """
    inventory = inventory_collections(tuple(Path(item) for item in roots))
    selected = [row for row in inventory["collections"] if row.get("status") == "SEALED_CURRENT"]
    if not selected:
        raise FeatureDescribeError("no SEALED_CURRENT collections were found")
    values: Dict[str, List[Decimal]] = {}
    quality_flags: Dict[str, int] = {}
    feature_rows = 0
    collection_rows = []
    for collection in selected:
        store = EventStore(Path(collection["data_dir"]), create=False)
        count = 0
        for feature in FeaturePipeline().replay_collection(store, collection["collection_id"]):
            count += 1
            feature_rows += 1
            for flag in feature.quality_flags:
                quality_flags[flag] = quality_flags.get(flag, 0) + 1
            for name, raw in feature.values.items():
                try:
                    values.setdefault(name, []).append(Decimal(str(raw)))
                except Exception as exc:
                    raise FeatureDescribeError("non-numeric feature %s" % name) from exc
        collection_rows.append({
            "collection_id": collection["collection_id"],
            "data_dir": collection["data_dir"],
            "feature_rows": count,
            "duration_seconds": collection.get("duration_seconds"),
            "current_audit_digest": collection["current_audit_digest"],
            "current_replay_digest": collection["current_replay_digest"],
        })
    distributions = {}
    for name, series in sorted(values.items()):
        series.sort()
        distributions[name] = {
            "observations": len(series),
            "min": str(series[0]),
            "p01": str(_nearest_rank(series, Decimal("0.01"))),
            "p05": str(_nearest_rank(series, Decimal("0.05"))),
            "p50": str(_nearest_rank(series, Decimal("0.50"))),
            "p95": str(_nearest_rank(series, Decimal("0.95"))),
            "p99": str(_nearest_rank(series, Decimal("0.99"))),
            "max": str(series[-1]),
        }
    return {
        "record_type": "pre_freeze_feature_description",
        "collections": collection_rows,
        "feature_rows": feature_rows,
        "feature_distributions": distributions,
        "quality_flag_counts": dict(sorted(quality_flags.items())),
        "limitation": "Descriptive pre-freeze evidence only. It does not deduplicate overlapping windows, inspect outcomes or labels, fit a model, choose thresholds, establish G1/G2/G3, or authorize trading.",
    }
