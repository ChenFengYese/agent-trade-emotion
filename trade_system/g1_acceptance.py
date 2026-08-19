"""Frozen-policy validation for forward-market data readiness (G1/E1)."""

from __future__ import annotations

import json
import re
import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .event_store import EventStore
from .types import AvailabilityKind


FROZEN_G1_STATUS = "FROZEN_G1_DATA_ACCEPTANCE"


class G1PolicyError(ValueError):
    pass


def _positive_number(value: Any, name: str, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise G1PolicyError("%s must be numeric" % name) from exc
    if number < 0 or (number == 0 and not allow_zero):
        raise G1PolicyError("%s must be %s" % (name, "non-negative" if allow_zero else "positive"))
    return number


def _positive_integer(value: Any, name: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise G1PolicyError("%s must be an integer" % name)
    number = _positive_number(value, name, allow_zero=allow_zero)
    if number != int(number):
        raise G1PolicyError("%s must be an integer" % name)
    return int(number)


def _stream_thresholds(raw: Any, name: str) -> Tuple[Tuple[str, float], ...]:
    """Load a stream-to-threshold map without silently accepting malformed keys."""
    if raw is None:
        return ()
    if not isinstance(raw, dict) or not raw:
        raise G1PolicyError("%s must be a non-empty object" % name)
    values = []
    for stream, value in raw.items():
        if not isinstance(stream, str) or not stream:
            raise G1PolicyError("%s stream names must be non-empty strings" % name)
        values.append((stream, _positive_number(value, "%s.%s" % (name, stream), allow_zero=True)))
    return tuple(sorted(values))


@dataclass(frozen=True)
class G1AcceptancePolicy:
    policy_id: str
    status: str
    instrument: str
    required_streams: Tuple[str, ...]
    required_configured_streams: Tuple[str, ...] = ()
    required_source_registry_id: str = ""
    required_source_registry_sha256: str = ""
    required_capture_plan_id: str = ""
    required_capture_plan_sha256: str = ""
    min_total_observed_seconds: float = 0.0
    min_qualified_collections: int = 0
    min_distinct_utc_days: int = 0
    min_distinct_utc_hour_buckets: int = 0
    min_exchange_info_observations: int = 0
    max_exchange_info_gap_seconds: float = 0.0
    min_stream_observations: Tuple[Tuple[str, float], ...] = ()
    max_stream_gap_seconds: Tuple[Tuple[str, float], ...] = ()
    require_exchange_info_trading: bool = True
    max_parse_errors: int = 0
    max_book_gaps: int = 0
    require_actual_only: bool = True
    require_sealed_raw_segments: bool = True
    allow_reconnects: bool = False
    digest: str = ""

    @classmethod
    def load(cls, path: Path) -> "G1AcceptancePolicy":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise G1PolicyError("cannot load G1 acceptance policy") from exc
        if not isinstance(raw, dict) or not raw.get("policy_id") or not raw.get("status"):
            raise G1PolicyError("policy_id and status are required")
        required_streams = raw.get("required_streams", [])
        if not isinstance(required_streams, list) or not all(isinstance(item, str) and item for item in required_streams):
            raise G1PolicyError("required_streams must be a list of non-empty strings")
        required_configured_streams = raw.get("required_configured_streams", [])
        if not isinstance(required_configured_streams, list) or not all(isinstance(item, str) and item for item in required_configured_streams):
            raise G1PolicyError("required_configured_streams must be a list of non-empty strings")
        policy = cls(
            policy_id=str(raw["policy_id"]),
            status=str(raw["status"]),
            instrument=str(raw.get("instrument", "")),
            required_streams=tuple(required_streams),
            required_configured_streams=tuple(required_configured_streams),
            required_source_registry_id=str(raw.get("required_source_registry_id", "")),
            required_source_registry_sha256=str(raw.get("required_source_registry_sha256", "")),
            required_capture_plan_id=str(raw.get("required_capture_plan_id", "")),
            required_capture_plan_sha256=str(raw.get("required_capture_plan_sha256", "")),
            min_total_observed_seconds=float(raw.get("min_total_observed_seconds", 0)),
            min_qualified_collections=_positive_integer(raw.get("min_qualified_collections", 0), "min_qualified_collections", allow_zero=True),
            min_distinct_utc_days=_positive_integer(raw.get("min_distinct_utc_days", 0), "min_distinct_utc_days", allow_zero=True),
            min_distinct_utc_hour_buckets=_positive_integer(raw.get("min_distinct_utc_hour_buckets", 0), "min_distinct_utc_hour_buckets", allow_zero=True),
            min_exchange_info_observations=int(raw.get("min_exchange_info_observations", 0)),
            max_exchange_info_gap_seconds=float(raw.get("max_exchange_info_gap_seconds", 0)),
            min_stream_observations=_stream_thresholds(raw.get("min_stream_observations"), "min_stream_observations"),
            max_stream_gap_seconds=_stream_thresholds(raw.get("max_stream_gap_seconds"), "max_stream_gap_seconds"),
            require_exchange_info_trading=bool(raw.get("require_exchange_info_trading", True)),
            max_parse_errors=int(raw.get("max_parse_errors", 0)),
            max_book_gaps=int(raw.get("max_book_gaps", 0)),
            require_actual_only=bool(raw.get("require_actual_only", True)),
            require_sealed_raw_segments=bool(raw.get("require_sealed_raw_segments", True)),
            allow_reconnects=bool(raw.get("allow_reconnects", False)),
            digest=hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        )
        if policy.status == FROZEN_G1_STATUS:
            policy._validate_frozen(raw)
        return policy

    @property
    def is_frozen(self) -> bool:
        return self.status == FROZEN_G1_STATUS

    def _validate_frozen(self, raw: Dict[str, Any]) -> None:
        if not self.instrument:
            raise G1PolicyError("frozen policy requires instrument")
        if not self.required_streams:
            raise G1PolicyError("frozen policy requires required_streams")
        if "exchangeInfo" not in self.required_streams:
            raise G1PolicyError("frozen policy requires exchangeInfo stream")
        if "btcusdt@forceOrder" not in self.required_configured_streams:
            raise G1PolicyError("frozen policy requires configured btcusdt@forceOrder stream")
        if "required_configured_streams" in raw and (not isinstance(raw["required_configured_streams"], list) or not all(isinstance(item, str) and item for item in raw["required_configured_streams"])):
            raise G1PolicyError("required_configured_streams must be a list of non-empty strings")
        if not isinstance(raw.get("required_source_registry_id"), str) or not raw["required_source_registry_id"]:
            raise G1PolicyError("frozen policy requires required_source_registry_id")
        if not isinstance(raw.get("required_source_registry_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", raw["required_source_registry_sha256"]):
            raise G1PolicyError("frozen policy requires a lowercase SHA-256 required_source_registry_sha256")
        plan_id = raw.get("required_capture_plan_id", "")
        plan_sha = raw.get("required_capture_plan_sha256", "")
        if bool(plan_id) != bool(plan_sha):
            raise G1PolicyError("required capture plan ID and SHA-256 must be supplied together")
        if plan_id and (not isinstance(plan_id, str) or not isinstance(plan_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_sha)):
            raise G1PolicyError("required capture plan requires an ID and lowercase SHA-256")
        _positive_number(raw.get("min_total_observed_seconds"), "min_total_observed_seconds")
        _positive_integer(raw.get("min_qualified_collections"), "min_qualified_collections")
        _positive_integer(raw.get("min_distinct_utc_days"), "min_distinct_utc_days")
        hour_buckets = _positive_integer(raw.get("min_distinct_utc_hour_buckets"), "min_distinct_utc_hour_buckets")
        if hour_buckets > 24:
            raise G1PolicyError("min_distinct_utc_hour_buckets cannot exceed 24")
        _positive_number(raw.get("min_exchange_info_observations"), "min_exchange_info_observations")
        _positive_number(raw.get("max_exchange_info_gap_seconds"), "max_exchange_info_gap_seconds")
        expected_min_streams = set(self.required_streams) - {"exchangeInfo"}
        expected_gap_streams = expected_min_streams - {"snapshot"}
        actual_min_streams = {stream for stream, _ in self.min_stream_observations}
        actual_gap_streams = {stream for stream, _ in self.max_stream_gap_seconds}
        if actual_min_streams != expected_min_streams:
            raise G1PolicyError("frozen policy min_stream_observations must cover exactly every required non-exchangeInfo stream")
        if actual_gap_streams != expected_gap_streams:
            raise G1PolicyError("frozen policy max_stream_gap_seconds must cover exactly every continuously observed stream")
        for stream, value in self.min_stream_observations:
            _positive_number(value, "min_stream_observations.%s" % stream)
            if value != int(value):
                raise G1PolicyError("min_stream_observations.%s must be an integer" % stream)
        for stream, value in self.max_stream_gap_seconds:
            _positive_number(value, "max_stream_gap_seconds.%s" % stream)
        _positive_number(raw.get("max_parse_errors"), "max_parse_errors", allow_zero=True)
        _positive_number(raw.get("max_book_gaps"), "max_book_gaps", allow_zero=True)
        for field in ("require_actual_only", "require_sealed_raw_segments", "allow_reconnects", "require_exchange_info_trading"):
            if field not in raw or not isinstance(raw[field], bool):
                raise G1PolicyError("frozen policy requires boolean %s" % field)


@dataclass(frozen=True)
class CollectionEvidence:
    data_dir: str
    collection_id: str
    manifest: Dict[str, Any]
    streams: Tuple[str, ...]
    raw_records: int
    availability_records: int
    reconstructed_records: int
    start: datetime | None
    end: datetime | None
    raw_segments: Tuple[str, ...]
    sealed_segments: Tuple[str, ...]
    exchange_info_times: Tuple[datetime, ...]
    exchange_info_statuses: Tuple[str, ...]
    stream_times: Tuple[Tuple[str, Tuple[datetime, ...]], ...]
    utc_dates: Tuple[str, ...]
    utc_hour_buckets: Tuple[int, ...]

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds()) if self.start and self.end else 0.0

    @property
    def exchange_info_max_gap_seconds(self) -> float:
        return self.max_gap_seconds(self.exchange_info_times)

    def stream_observations(self, stream: str) -> int:
        return len(dict(self.stream_times).get(stream, ()))

    def stream_max_gap_seconds(self, stream: str) -> float:
        return self.max_gap_seconds(dict(self.stream_times).get(stream, ()))

    def max_gap_seconds(self, observations: Sequence[datetime]) -> float:
        if not observations or not self.start or not self.end:
            return float("inf")
        points = (self.start,) + tuple(observations) + (self.end,)
        return max((right - left).total_seconds() for left, right in zip(points, points[1:]))


def _load_manifests(store: EventStore) -> List[Tuple[str, Dict[str, Any]]]:
    result = []
    for path in sorted(store.collection_manifest_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("record_type") != "collection_manifest" or value.get("collection_id") != path.stem:
                raise ValueError("invalid collection manifest identity")
            result.append((path.stem, value))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise G1PolicyError("invalid collection manifest: %s" % path.name) from exc
    return result


def _collection_evidence(store: EventStore, collection_id: str, manifest: Dict[str, Any]) -> CollectionEvidence:
    raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(collection_id + "-")]
    raw_ids = {raw.event_id for raw in raws}
    availability = [record for record in store.iter_availability() if record.event_id in raw_ids]
    exchange_info = sorted(
        (record.available_at, str(record.normalized.get("status", "")))
        for record in availability
        if record.normalized.get("kind") == "exchange_info"
    )
    stream_times: Dict[str, List[datetime]] = {}
    for raw in raws:
        stream_times.setdefault(raw.stream, []).append(raw.receive_time)
    return CollectionEvidence(
        data_dir=str(store.root),
        collection_id=collection_id,
        manifest=manifest,
        streams=tuple(sorted({raw.stream for raw in raws})),
        raw_records=len(raws),
        availability_records=len(availability),
        reconstructed_records=sum(record.availability_kind == AvailabilityKind.RECONSTRUCTED for record in availability),
        start=min((raw.receive_time for raw in raws), default=None),
        end=max((raw.receive_time for raw in raws), default=None),
        raw_segments=tuple(sorted({Path(raw.raw_segment).stem for raw in raws})),
        sealed_segments=tuple(sorted(path.stem for path in store.manifest_root.glob("*.json"))),
        exchange_info_times=tuple(item[0] for item in exchange_info),
        exchange_info_statuses=tuple(item[1] for item in exchange_info),
        stream_times=tuple((stream, tuple(sorted(times))) for stream, times in sorted(stream_times.items())),
        utc_dates=tuple(sorted({raw.receive_time.date().isoformat() for raw in raws})),
        utc_hour_buckets=tuple(sorted({raw.receive_time.hour for raw in raws})),
    )


def _union_duration(intervals: Iterable[Tuple[datetime, datetime]]) -> float:
    ordered = sorted(intervals)
    merged: List[Tuple[datetime, datetime]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return sum((end - start).total_seconds() for start, end in merged)


def validate_g1_stores(stores: Sequence[EventStore], policy: G1AcceptancePolicy) -> Dict[str, Any]:
    if not stores:
        raise G1PolicyError("at least one event store is required")
    roots = [str(store.root.resolve()) for store in stores]
    if len(set(roots)) != len(roots):
        raise G1PolicyError("the same evidence store cannot appear more than once in a G1 bundle")
    audits = [(str(store.root),) + store.audit() for store in stores]
    audit_valid = all(item[1] for item in audits)
    if len(audits) == 1:
        audit_issues = audits[0][2]
        audit_digest = audits[0][3]
    else:
        audit_issues = [{"data_dir": path, "issues": issues} for path, _valid, issues, _digest in audits if issues]
        digest_payload = json.dumps([(path, digest) for path, _valid, _issues, digest in audits], sort_keys=True, separators=(",", ":"))
        audit_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
    evidence = [
        _collection_evidence(store, collection_id, manifest)
        for store in stores
        for collection_id, manifest in _load_manifests(store)
    ]
    reasons: List[str] = []
    fingerprints = [
        (item.collection_id, str(item.manifest.get("audit_digest", "")), str(item.manifest.get("replay_digest", "")))
        for item in evidence
    ]
    if len(set(fingerprints)) != len(fingerprints):
        reasons.append("duplicate collection evidence is not eligible for a G1 bundle")
    if not policy.is_frozen:
        reasons.append("policy is not frozen")
    if not audit_valid:
        reasons.append("event-store audit failed")
    qualified = []
    intervals = []
    rows = []
    for item in evidence:
        item_reasons = []
        manifest = item.manifest
        if manifest.get("collection_result") != "QUALIFIED_SMOKE":
            item_reasons.append("collection manifest is not qualified")
        if policy.instrument and manifest.get("instrument") != policy.instrument:
            item_reasons.append("instrument mismatch")
        missing_streams = sorted(set(policy.required_streams) - set(item.streams))
        if missing_streams:
            item_reasons.append("missing streams: %s" % ",".join(missing_streams))
        configured = manifest.get("configured_streams", [])
        missing_configured = sorted(set(policy.required_configured_streams) - set(configured))
        if missing_configured:
            item_reasons.append("missing configured streams: %s" % ",".join(missing_configured))
        source_registry = manifest.get("source_registry", {})
        if policy.is_frozen and not isinstance(source_registry, dict):
            item_reasons.append("collection source registry binding is invalid")
        elif policy.is_frozen and policy.required_source_registry_id and source_registry.get("registry_id") != policy.required_source_registry_id:
            item_reasons.append("source registry id mismatch")
        elif policy.is_frozen and policy.required_source_registry_sha256 and source_registry.get("sha256") != policy.required_source_registry_sha256:
            item_reasons.append("source registry digest mismatch")
        capture_plan = manifest.get("capture_plan")
        if policy.required_capture_plan_id:
            if not isinstance(capture_plan, dict):
                item_reasons.append("required capture plan binding is missing")
            elif capture_plan.get("plan_id") != policy.required_capture_plan_id:
                item_reasons.append("capture plan id mismatch")
            elif capture_plan.get("plan_sha256") != policy.required_capture_plan_sha256:
                item_reasons.append("capture plan digest mismatch")
        if item.raw_records != int(manifest.get("raw_captured", -1)):
            item_reasons.append("raw record count does not match manifest")
        if item.availability_records != int(manifest.get("availability_written", -1)):
            item_reasons.append("availability count does not match manifest")
        if int(manifest.get("parse_errors", 0)) > policy.max_parse_errors:
            item_reasons.append("parse errors exceed policy")
        if int(manifest.get("book_gaps", 0)) > policy.max_book_gaps:
            item_reasons.append("book gaps exceed policy")
        if manifest.get("errors"):
            item_reasons.append("collection recorded runtime errors")
        if not policy.allow_reconnects and manifest.get("reconnects"):
            item_reasons.append("reconnects are disallowed by policy")
        if policy.require_actual_only and item.reconstructed_records:
            item_reasons.append("reconstructed records present")
        if policy.require_sealed_raw_segments and (not item.raw_segments or any(segment not in item.sealed_segments for segment in item.raw_segments)):
            item_reasons.append("raw segment is not sealed")
        if policy.min_exchange_info_observations and len(item.exchange_info_times) < policy.min_exchange_info_observations:
            item_reasons.append("exchangeInfo observation count below policy")
        if policy.max_exchange_info_gap_seconds and item.exchange_info_max_gap_seconds > policy.max_exchange_info_gap_seconds:
            item_reasons.append("exchangeInfo observation gap exceeds policy")
        if policy.min_exchange_info_observations and policy.require_exchange_info_trading and any(status != "TRADING" for status in item.exchange_info_statuses):
            item_reasons.append("exchangeInfo observed non-TRADING status")
        for stream, threshold in policy.min_stream_observations:
            if threshold and item.stream_observations(stream) < threshold:
                item_reasons.append("%s observation count below policy" % stream)
        for stream, threshold in policy.max_stream_gap_seconds:
            if threshold and item.stream_max_gap_seconds(stream) > threshold:
                item_reasons.append("%s observation gap exceeds policy" % stream)
        collection_ok = not item_reasons
        if collection_ok:
            qualified.append(item)
            if item.start and item.end:
                intervals.append((item.start, item.end))
        rows.append({
            "data_dir": item.data_dir,
            "collection_id": item.collection_id,
            "qualified": collection_ok,
            "reasons": item_reasons,
            "raw_records": item.raw_records,
            "availability_records": item.availability_records,
            "observed_duration_seconds": item.duration_seconds,
            "streams": item.streams,
            "raw_segments": item.raw_segments,
            "source_registry": manifest.get("source_registry"),
            "capture_plan": capture_plan,
            "collection_audit_digest": manifest.get("audit_digest"),
            "collection_replay_digest": manifest.get("replay_digest"),
            "exchange_info_observations": len(item.exchange_info_times),
            "exchange_info_statuses": item.exchange_info_statuses,
            "exchange_info_max_gap_seconds": item.exchange_info_max_gap_seconds,
            "stream_observations": {stream: item.stream_observations(stream) for stream, _ in policy.min_stream_observations},
            "stream_max_gap_seconds": {stream: item.stream_max_gap_seconds(stream) for stream, _ in policy.max_stream_gap_seconds},
        })
    observed_seconds = _union_duration(intervals)
    utc_dates = sorted({date for item in qualified for date in item.utc_dates})
    utc_hour_buckets = sorted({hour for item in qualified for hour in item.utc_hour_buckets})
    if len(qualified) < policy.min_qualified_collections:
        reasons.append("qualified collection count below policy")
    if observed_seconds < policy.min_total_observed_seconds:
        reasons.append("observed duration below policy")
    if len(utc_dates) < policy.min_distinct_utc_days:
        reasons.append("distinct UTC date coverage below policy")
    if len(utc_hour_buckets) < policy.min_distinct_utc_hour_buckets:
        reasons.append("distinct UTC hour-bucket coverage below policy")
    passed = policy.is_frozen and audit_valid and not reasons
    collection_failure_counts = Counter(
        reason
        for row in rows
        for reason in row["reasons"]
    )
    deficits = {
        "qualified_collections": max(0, policy.min_qualified_collections - len(qualified)),
        "observed_seconds": max(0.0, policy.min_total_observed_seconds - observed_seconds),
        "distinct_utc_days": max(0, policy.min_distinct_utc_days - len(utc_dates)),
        "distinct_utc_hour_buckets": max(0, policy.min_distinct_utc_hour_buckets - len(utc_hour_buckets)),
    }
    return {
        "passed": passed,
        "status": "PASS" if passed else ("DRAFT_POLICY" if not policy.is_frozen else "WAIT_DATA"),
        "policy_id": policy.policy_id,
        "policy_status": policy.status,
        "policy_sha256": policy.digest,
        "requirements": {
            "instrument": policy.instrument,
            "source_registry_id": policy.required_source_registry_id,
            "source_registry_sha256": policy.required_source_registry_sha256,
            "capture_plan_id": policy.required_capture_plan_id or None,
            "capture_plan_sha256": policy.required_capture_plan_sha256 or None,
            "min_qualified_collections": policy.min_qualified_collections,
            "min_total_observed_seconds": policy.min_total_observed_seconds,
            "min_distinct_utc_days": policy.min_distinct_utc_days,
            "min_distinct_utc_hour_buckets": policy.min_distinct_utc_hour_buckets,
        },
        "audit_valid": audit_valid,
        "audit_issues": audit_issues,
        "audit_digest": audit_digest,
        "qualified_collections": len(qualified),
        "total_collections": len(evidence),
        "total_observed_seconds": observed_seconds,
        "distinct_utc_dates": utc_dates,
        "distinct_utc_hour_buckets": utc_hour_buckets,
        "collections": rows,
        "deficits": deficits,
        "collection_failure_counts": dict(sorted(collection_failure_counts.items())),
        "reasons": reasons,
    }


def validate_g1_data(store: EventStore, policy: G1AcceptancePolicy) -> Dict[str, Any]:
    """Validate one evidence store; retained as the compatibility entry point."""
    return validate_g1_stores((store,), policy)
