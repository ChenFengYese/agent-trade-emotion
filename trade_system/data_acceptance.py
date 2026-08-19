"""Write-once role acceptance reports and machine-checkable quality equivalence."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from .capture_plan import ForwardCapturePlan
from .event_store import EventStore, EventStoreError
from .g1_acceptance import G1AcceptancePolicy, G1PolicyError, validate_g1_stores
from .types import iso_utc, utc_now


class DataAcceptanceError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _binding(policy: G1AcceptancePolicy, plan: ForwardCapturePlan) -> Dict[str, str]:
    return {
        "policy_id": policy.policy_id,
        "policy_sha256": policy.digest,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.digest,
    }


def assert_equal_or_stricter_than_g1(candidate: G1AcceptancePolicy, baseline: G1AcceptancePolicy) -> None:
    """Prove the role policy never weakens the frozen G1 quality contract.

    Plan identity is intentionally excluded: development and holdout have their
    own predeclared plans.  Every quality-relevant value has a directional
    comparison instead of relying on a prose equivalence claim.
    """
    failures = []
    if candidate.instrument != baseline.instrument:
        failures.append("instrument")
    if candidate.required_source_registry_id != baseline.required_source_registry_id or candidate.required_source_registry_sha256 != baseline.required_source_registry_sha256:
        failures.append("source_registry")
    if not set(candidate.required_streams).issuperset(baseline.required_streams):
        failures.append("required_streams")
    if not set(candidate.required_configured_streams).issuperset(baseline.required_configured_streams):
        failures.append("required_configured_streams")
    for field in ("require_actual_only", "require_sealed_raw_segments", "require_exchange_info_trading"):
        if getattr(baseline, field) and not getattr(candidate, field):
            failures.append(field)
    if candidate.allow_reconnects and not baseline.allow_reconnects:
        failures.append("allow_reconnects")
    for field in ("max_parse_errors", "max_book_gaps", "max_exchange_info_gap_seconds"):
        if getattr(candidate, field) > getattr(baseline, field):
            failures.append(field)
    for field in ("min_total_observed_seconds", "min_qualified_collections", "min_distinct_utc_days", "min_distinct_utc_hour_buckets", "min_exchange_info_observations"):
        if getattr(candidate, field) < getattr(baseline, field):
            failures.append(field)
    candidate_min = dict(candidate.min_stream_observations)
    baseline_min = dict(baseline.min_stream_observations)
    for stream, threshold in baseline_min.items():
        if candidate_min.get(stream, -1) < threshold:
            failures.append("min_stream_observations.%s" % stream)
    candidate_gap = dict(candidate.max_stream_gap_seconds)
    baseline_gap = dict(baseline.max_stream_gap_seconds)
    for stream, threshold in baseline_gap.items():
        if stream not in candidate_gap or candidate_gap[stream] > threshold:
            failures.append("max_stream_gap_seconds.%s" % stream)
    if failures:
        raise DataAcceptanceError("role acceptance policy is weaker than G1: %s" % ", ".join(sorted(set(failures))))


def write_data_acceptance_report(
    path: Path,
    *,
    report_id: str,
    role: str,
    policy: G1AcceptancePolicy,
    plan: ForwardCapturePlan,
    data_dirs: tuple[Path, ...],
) -> Dict[str, Any]:
    """Persist a role-specific PASS without calling it G1.

    The acceptance result is recalculated from the exact supplied event stores.
    A caller-provided JSON "PASS" is deliberately not an input: that would
    make the report forgeable without raw evidence.
    """
    if role not in {"DEVELOPMENT", "HOLDOUT"}:
        raise DataAcceptanceError("role must be DEVELOPMENT or HOLDOUT")
    if not isinstance(report_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", report_id):
        raise DataAcceptanceError("report_id must be a safe non-empty identifier")
    if not policy.is_frozen:
        raise DataAcceptanceError("data acceptance report requires a frozen acceptance policy")
    if policy.required_capture_plan_id != plan.plan_id or policy.required_capture_plan_sha256 != plan.digest:
        raise DataAcceptanceError("acceptance policy does not bind the supplied capture plan")
    roots = tuple(Path(item).resolve() for item in data_dirs)
    if not roots or len(set(roots)) != len(roots):
        raise DataAcceptanceError("data acceptance report requires distinct exact data directories")
    try:
        stores = tuple(EventStore(root, create=False) for root in roots)
        validation = validate_g1_stores(stores, policy)
    except (G1PolicyError, EventStoreError, OSError, ValueError) as exc:
        raise DataAcceptanceError("cannot revalidate supplied event stores") from exc
    if validation.get("passed") is not True or validation.get("status") != "PASS":
        raise DataAcceptanceError("revalidated stores do not satisfy the frozen acceptance policy")
    if validation.get("policy_id") != policy.policy_id or validation.get("policy_sha256") != policy.digest:
        raise DataAcceptanceError("revalidated result does not match the supplied acceptance policy")
    qualified = []
    for row in validation.get("collections", []):
        if not isinstance(row, dict) or not row.get("qualified"):
            continue
        capture = row.get("capture_plan")
        if not isinstance(capture, dict) or capture.get("plan_id") != plan.plan_id or capture.get("plan_sha256") != plan.digest:
            raise DataAcceptanceError("qualified collection does not bind the supplied capture plan")
        required = ("data_dir", "collection_id", "collection_audit_digest", "collection_replay_digest")
        if any(not isinstance(row.get(field), str) or not row[field] for field in required):
            raise DataAcceptanceError("qualified collection is missing immutable provenance")
        qualified.append({field: row[field] for field in required} | {"capture_plan": capture})
    if not qualified:
        raise DataAcceptanceError("PASS validation has no qualified collections for this plan")
    value = {
        "record_type": "data_acceptance_report",
        "schema_version": "data_acceptance_report.v1",
        "report_id": report_id,
        "role": role,
        "status": "PASS",
        "written_at": iso_utc(utc_now()),
        "acceptance_policy": {"id": policy.policy_id, "sha256": policy.digest},
        "capture_plan": {"id": plan.plan_id, "sha256": plan.digest},
        "qualified_collections": qualified,
        "revalidation_sha256": _sha(dict(validation)),
    }
    value["report_sha256"] = _sha(value)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise DataAcceptanceError("data acceptance report already exists")
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise DataAcceptanceError("cannot write data acceptance report") from exc
    return value


def load_verified_data_acceptance_report(path: Path, *, role: str = "", policy: G1AcceptancePolicy | None = None, plan: ForwardCapturePlan | None = None) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataAcceptanceError("cannot load data acceptance report") from exc
    if not isinstance(value, dict) or value.get("record_type") != "data_acceptance_report" or value.get("schema_version") != "data_acceptance_report.v1":
        raise DataAcceptanceError("invalid data acceptance report type")
    body = dict(value)
    digest = body.pop("report_sha256", None)
    if not isinstance(digest, str) or digest != _sha(body):
        raise DataAcceptanceError("data acceptance report digest does not match content")
    if value.get("status") != "PASS" or value.get("role") not in {"DEVELOPMENT", "HOLDOUT"}:
        raise DataAcceptanceError("data acceptance report is not a role PASS")
    if role and value["role"] != role:
        raise DataAcceptanceError("data acceptance report role does not match")
    for field in ("acceptance_policy", "capture_plan"):
        binding = value.get(field)
        if not isinstance(binding, dict) or not isinstance(binding.get("id"), str) or not re.fullmatch(r"[0-9a-f]{64}", str(binding.get("sha256", ""))):
            raise DataAcceptanceError("data acceptance report %s binding is invalid" % field)
    qualified = value.get("qualified_collections")
    if not isinstance(qualified, list) or not qualified:
        raise DataAcceptanceError("data acceptance report has no qualified collections")
    if policy is not None and value["acceptance_policy"] != {"id": policy.policy_id, "sha256": policy.digest}:
        raise DataAcceptanceError("data acceptance report policy does not match")
    if plan is not None and value["capture_plan"] != {"id": plan.plan_id, "sha256": plan.digest}:
        raise DataAcceptanceError("data acceptance report plan does not match")
    return value
