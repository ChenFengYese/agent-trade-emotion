"""Build provenance-bound features from the qualified collections in a PASS G1 report."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .event_store import EventStore
from .episode_policy import EpisodePolicy
from .g1_report import load_verified_g1_report
from .g1_acceptance import G1AcceptancePolicy
from .capture_plan import ForwardCapturePlan
from .data_acceptance import DataAcceptanceError, assert_equal_or_stricter_than_g1, load_verified_data_acceptance_report
from .evidence_archive import (
    EvidenceArchiveError,
    load_verified_evidence_archive_receipt,
    verify_evidence_archive,
    verify_hot_cold_equivalence,
)
from .feature_context import FeatureContextError, FeatureContextPolicy
from .protocol import ResearchProtocol, V2_SCHEMA_VERSION
from .pipeline import FeaturePipeline
from .research_report import sha256_file
from .role_capture_window import RoleCaptureWindow, RoleCaptureWindowError


class FeatureBundleError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def load_verified_feature_bundle_manifest(path: Path, *, feature_path: Path) -> Dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FeatureBundleError("cannot load feature bundle manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("record_type") != "feature_bundle_manifest":
        raise FeatureBundleError("invalid feature bundle manifest record type")
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str):
        raise FeatureBundleError("feature bundle manifest digest is missing")
    body = dict(manifest)
    body.pop("manifest_sha256", None)
    if digest != _sha256(body):
        raise FeatureBundleError("feature bundle manifest digest does not match content")
    if manifest.get("feature_artifact_sha256") != sha256_file(Path(feature_path)):
        raise FeatureBundleError("feature artifact digest does not match manifest")
    _non_empty(manifest.get("episode_policy_id"), "feature bundle episode_policy_id")
    episode_digest = manifest.get("episode_policy_sha256")
    if not isinstance(episode_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", episode_digest):
        raise FeatureBundleError("feature bundle episode_policy_sha256 is invalid")
    collections = manifest.get("collections")
    if not isinstance(collections, list) or not collections:
        raise FeatureBundleError("feature bundle manifest has no collections")
    evidence_ids = []
    for item in collections:
        if not isinstance(item, dict):
            raise FeatureBundleError("feature bundle collection entry is invalid")
        evidence_ids.append(_non_empty(item.get("evidence_id"), "feature bundle evidence_id"))
    if len(set(evidence_ids)) != len(evidence_ids):
        raise FeatureBundleError("feature bundle manifest repeats evidence_id")
    binding = manifest.get("evidence_binding")
    if binding is not None:
        if not isinstance(binding, dict) or binding.get("role") not in {"DEVELOPMENT", "HOLDOUT"}:
            raise FeatureBundleError("role feature bundle evidence_binding is invalid")
        for field in ("protocol", "capture_plan", "acceptance_policy", "acceptance_report"):
            value = binding.get(field)
            if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"] or not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
                raise FeatureBundleError("role feature bundle %s binding is invalid" % field)
        if binding.get("allowed_availability") != "ACTUAL_ONLY":
            raise FeatureBundleError("role feature bundle must be ACTUAL_ONLY")
        context = manifest.get("context_binding")
        if context is not None:
            for field in ("policy_id", "policy_sha256", "artifact_sha256", "context_manifest_sha256"):
                value = context.get(field) if isinstance(context, dict) else None
                if not isinstance(value, str) or not value:
                    raise FeatureBundleError("role feature bundle context binding is invalid")
            if not re.fullmatch(r"[0-9a-f]{64}", context["policy_sha256"]) or not re.fullmatch(r"[0-9a-f]{64}", context["artifact_sha256"]) or not re.fullmatch(r"[0-9a-f]{64}", context["context_manifest_sha256"]):
                raise FeatureBundleError("role feature bundle context digest is invalid")
            window = context.get("role_window")
            if not isinstance(window, dict) or not isinstance(window.get("id"), str) or not window["id"] or not isinstance(window.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", window["sha256"]):
                raise FeatureBundleError("role feature bundle role-window binding is invalid")
    else:
        _non_empty(manifest.get("g1_policy_id"), "feature bundle g1_policy_id")
        _non_empty(manifest.get("g1_report_sha256"), "feature bundle g1_report_sha256")
    return manifest


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FeatureBundleError("%s must be a non-empty string" % field)
    return value


def _qualified_collections(report: Dict[str, Any]) -> Tuple[Dict[str, Any], ...]:
    values = report.get("collections")
    if not isinstance(values, list):
        raise FeatureBundleError("G1 report collections are invalid")
    selected = []
    for index, item in enumerate(values):
        if not isinstance(item, dict) or not item.get("qualified"):
            continue
        row = dict(item)
        for field in ("data_dir", "collection_id", "collection_audit_digest", "collection_replay_digest"):
            _non_empty(row.get(field), "G1 collections[%d].%s" % (index, field))
        selected.append(row)
    if not selected:
        raise FeatureBundleError("PASS G1 report has no qualified collection rows")
    identities = [(str(Path(item["data_dir"]).resolve()), item["collection_id"]) for item in selected]
    if len(set(identities)) != len(identities):
        raise FeatureBundleError("G1 report repeats a qualified collection")
    return tuple(sorted(selected, key=lambda item: (str(Path(item["data_dir"]).resolve()), item["collection_id"])))


def _collection_manifest(store: EventStore, collection_id: str) -> Dict[str, Any]:
    path = store.collection_manifest_root / (collection_id + ".json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FeatureBundleError("cannot load qualified collection manifest: %s" % collection_id) from exc
    if not isinstance(value, dict) or value.get("record_type") != "collection_manifest" or value.get("collection_id") != collection_id:
        raise FeatureBundleError("invalid qualified collection manifest: %s" % collection_id)
    return value


def _preflight(data_dirs: Iterable[Path], report: Dict[str, Any]) -> Tuple[Tuple[EventStore, Dict[str, Any], Dict[str, Any]], ...]:
    qualified = _qualified_collections(report)
    roots = [str(Path(path).resolve()) for path in data_dirs]
    if len(set(roots)) != len(roots):
        raise FeatureBundleError("the same evidence store cannot appear more than once")
    selected_roots = {str(Path(item["data_dir"]).resolve()) for item in qualified}
    if set(roots) != selected_roots:
        raise FeatureBundleError("data directories must match exactly the qualified G1 evidence roots")
    stores = {root: EventStore(Path(root), create=False) for root in roots}
    prepared = []
    for row in qualified:
        root = str(Path(row["data_dir"]).resolve())
        store = stores[root]
        audit_valid, audit_issues, _audit_digest = store.audit()
        if not audit_valid:
            raise FeatureBundleError("event-store audit failed for %s: %s" % (root, "; ".join(audit_issues)))
        manifest = _collection_manifest(store, row["collection_id"])
        if manifest.get("collection_result") != "QUALIFIED_SMOKE":
            raise FeatureBundleError("collection is no longer qualified: %s" % row["collection_id"])
        if manifest.get("audit_digest") != row["collection_audit_digest"] or manifest.get("replay_digest") != row["collection_replay_digest"]:
            raise FeatureBundleError("collection provenance no longer matches G1 report: %s" % row["collection_id"])
        raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(row["collection_id"] + "-")]
        segments = {Path(raw.raw_segment).stem for raw in raws}
        sealed = {path.stem for path in store.manifest_root.glob("*.json")}
        if not raws or any(segment not in sealed for segment in segments):
            raise FeatureBundleError("qualified collection is not fully sealed: %s" % row["collection_id"])
        prepared.append((store, row, manifest))
    return tuple(prepared)


def build_feature_bundle(
    *,
    data_dirs: Iterable[Path],
    g1_report_path: Path,
    output_path: Path,
    manifest_path: Path,
    bundle_id: str,
    episode_policy_path: Path,
) -> Dict[str, Any]:
    """Write a new feature artifact and immutable provenance manifest.

    Each collection starts a fresh FeaturePipeline: order-book and episode
    state never cross an independent evidence-store or collection boundary.
    """
    _non_empty(bundle_id, "bundle_id")
    report = load_verified_g1_report(Path(g1_report_path), require_pass=True)
    episode_policy = EpisodePolicy.load(Path(episode_policy_path))
    prepared = _preflight(tuple(data_dirs), report)
    output, manifest_output = Path(output_path), Path(manifest_path)
    if output.resolve() == manifest_output.resolve():
        raise FeatureBundleError("feature artifact and manifest must be different paths")
    if output.exists() or manifest_output.exists():
        raise FeatureBundleError("feature artifact and manifest paths must both be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    collection_rows: List[Dict[str, Any]] = []
    total_rows = 0
    try:
        with output.open("x", encoding="utf-8") as handle:
            for store, g1_row, collection_manifest in prepared:
                provenance = {
                    "data_dir": str(store.root.resolve()),
                    "collection_id": g1_row["collection_id"],
                    "collection_audit_digest": g1_row["collection_audit_digest"],
                    "collection_replay_digest": g1_row["collection_replay_digest"],
                }
                evidence_id = _sha256(provenance)
                count = 0
                for feature in FeaturePipeline(episode_policy).replay_collection(store, g1_row["collection_id"]):
                    row = feature.to_dict()
                    source_event_id = row["event_id"]
                    row["event_id"] = evidence_id + "/" + source_event_id
                    row["source_event_id"] = source_event_id
                    if row["episode_id"] is not None:
                        row["episode_id"] = evidence_id + "/" + row["episode_id"]
                    row["evidence"] = dict(provenance, evidence_id=evidence_id)
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    count += 1
                collection_rows.append(dict(provenance, evidence_id=evidence_id, feature_rows=count, collection_manifest_sha256=_sha256(collection_manifest)))
                total_rows += count
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise FeatureBundleError("cannot write feature bundle") from exc
    manifest = {
        "record_type": "feature_bundle_manifest",
        "bundle_id": bundle_id,
        "g1_policy_id": report["policy_id"],
        "g1_report_sha256": report["report_sha256"],
        "feature_artifact": str(output),
        "feature_artifact_sha256": sha256_file(output),
        "feature_rows": total_rows,
        "episode_policy_id": episode_policy.policy_id,
        "episode_policy_sha256": episode_policy.digest,
        "collections": collection_rows,
    }
    manifest["manifest_sha256"] = _sha256(manifest)
    try:
        with manifest_output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(manifest) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise FeatureBundleError("cannot write feature bundle manifest") from exc
    return dict(manifest, manifest_path=str(manifest_output))


def build_role_feature_bundle(
    *,
    protocol_path: Path,
    role: str,
    capture_plan_path: Path,
    acceptance_policy_path: Path,
    acceptance_report_path: Path,
    baseline_g1_policy_path: Path,
    data_dirs: Iterable[Path],
    output_path: Path,
    manifest_path: Path,
    bundle_id: str,
    episode_policy_path: Path,
    context_policy_path: Path | None = None,
    role_window_path: Path | None = None,
    context_output_path: Path | None = None,
    context_manifest_path: Path | None = None,
    archive_receipt_paths: Iterable[Path] = (),
) -> Dict[str, Any]:
    """Build a role-isolated feature bundle from post-capture accepted data."""
    if role not in {"DEVELOPMENT", "HOLDOUT"}:
        raise FeatureBundleError("role must be DEVELOPMENT or HOLDOUT")
    protocol = ResearchProtocol.load(Path(protocol_path))
    protocol.assert_frozen_for_research()
    if protocol.raw.get("schema_version") != V2_SCHEMA_VERSION:
        raise FeatureBundleError("role feature bundles require frozen protocol v2")
    role_contract = next((item for item in protocol.raw["data_eligibility"]["admitted_collection_roles"] if item.get("role") == role), None)
    if not isinstance(role_contract, dict):
        raise FeatureBundleError("protocol does not admit the requested role")
    plan = ForwardCapturePlan.load(Path(capture_plan_path))
    policy = G1AcceptancePolicy.load(Path(acceptance_policy_path))
    baseline = G1AcceptancePolicy.load(Path(baseline_g1_policy_path))
    if role_contract["capture_plan"] != {"id": plan.plan_id, "sha256": plan.digest}:
        raise FeatureBundleError("role capture plan does not match frozen protocol")
    if role_contract["acceptance_policy"] != {"id": policy.policy_id, "sha256": policy.digest}:
        raise FeatureBundleError("role acceptance policy does not match frozen protocol")
    try:
        assert_equal_or_stricter_than_g1(policy, baseline)
        report = load_verified_data_acceptance_report(acceptance_report_path, role=role, policy=policy, plan=plan)
    except DataAcceptanceError as exc:
        raise FeatureBundleError(str(exc)) from exc
    episode_policy = EpisodePolicy.load(Path(episode_policy_path))
    context_mode = any(value is not None for value in (context_policy_path, role_window_path, context_output_path, context_manifest_path)) or bool(tuple(archive_receipt_paths))
    context_policy = None
    role_window = None
    archive_receipts: Dict[Tuple[str, str], Dict[str, Any]] = {}
    context_output = context_manifest_output = None
    if context_mode:
        if not all(value is not None for value in (context_policy_path, role_window_path, context_output_path, context_manifest_path)):
            raise FeatureBundleError("future role context requires policy, role window, context artifact and context manifest")
        try:
            context_policy = FeatureContextPolicy.load(Path(context_policy_path))
            role_window = RoleCaptureWindow.load(Path(role_window_path))
            role_window.assert_matches(role=role, plan=plan, context_policy=context_policy)
        except (FeatureContextError, RoleCaptureWindowError) as exc:
            raise FeatureBundleError(str(exc)) from exc
        context_output, context_manifest_output = Path(context_output_path), Path(context_manifest_path)
        if context_output in {Path(output_path), Path(manifest_path), context_manifest_output} or context_manifest_output in {Path(output_path), Path(manifest_path)}:
            raise FeatureBundleError("context artifact, context manifest, feature artifact and feature manifest must be distinct")
        receipt_paths = tuple(Path(path) for path in archive_receipt_paths)
        if not receipt_paths:
            raise FeatureBundleError("future role context requires one verified evidence archive receipt per collection")
        try:
            for receipt_path in receipt_paths:
                receipt = load_verified_evidence_archive_receipt(receipt_path)
                key = (str(Path(receipt.get("source_evidence_root", "")).resolve()), str(receipt.get("collection_id", "")))
                if key in archive_receipts:
                    raise FeatureBundleError("archive receipts repeat a collection")
                verify_evidence_archive(receipt_path)
                archive_receipts[key] = dict(receipt, receipt_path=str(receipt_path))
        except EvidenceArchiveError as exc:
            raise FeatureBundleError(str(exc)) from exc
    qualified = report["qualified_collections"]
    expected_roots = {str(Path(row["data_dir"]).resolve()) for row in qualified}
    roots = {str(Path(path).resolve()) for path in data_dirs}
    if roots != expected_roots:
        raise FeatureBundleError("role data directories must match the accepted report exactly")
    output, manifest_output = Path(output_path), Path(manifest_path)
    required_new = [output, manifest_output] + ([context_output, context_manifest_output] if context_mode else [])
    if any(path is None or path.exists() for path in required_new) or len({path.resolve() for path in required_new if path is not None}) != len(required_new):
        raise FeatureBundleError("role feature output and manifest must be distinct new paths")
    stores = {str(Path(path).resolve()): EventStore(Path(path), create=False) for path in data_dirs}
    collections = []
    total_rows = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    if context_mode:
        assert context_output is not None
        context_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            context_handle = context_output.open("x", encoding="utf-8") if context_mode and context_output is not None else None
            for accepted in qualified:
                store = stores[str(Path(accepted["data_dir"]).resolve())]
                valid, issues, _digest = store.audit()
                if not valid:
                    raise FeatureBundleError("event-store audit failed: %s" % "; ".join(issues))
                collection_id = accepted["collection_id"]
                manifest = _collection_manifest(store, collection_id)
                if manifest.get("collection_result") != "QUALIFIED_SMOKE" or manifest.get("audit_digest") != accepted["collection_audit_digest"] or manifest.get("replay_digest") != accepted["collection_replay_digest"]:
                    raise FeatureBundleError("accepted collection terminal provenance drifted")
                if manifest.get("capture_plan", {}).get("plan_id") != plan.plan_id or manifest.get("capture_plan", {}).get("plan_sha256") != plan.digest:
                    raise FeatureBundleError("accepted collection capture-plan binding drifted")
                raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(collection_id + "-")]
                raw_ids = {raw.event_id for raw in raws}
                if not raws or any(Path(raw.raw_segment).stem not in {item.stem for item in store.manifest_root.glob("*.json")} for raw in raws):
                    raise FeatureBundleError("accepted collection is not fully sealed")
                collection_availability = [record for record in store.iter_availability() if record.event_id in raw_ids]
                if len(collection_availability) != len(raw_ids) or {record.event_id for record in collection_availability} != raw_ids:
                    raise FeatureBundleError("accepted collection is missing or repeats availability evidence")
                if any(record.availability_kind.value != "ACTUAL" for record in collection_availability):
                    raise FeatureBundleError("accepted collection contains non-ACTUAL availability")
                coverage = None
                receipt_binding = None
                if context_mode:
                    assert role_window is not None and context_policy is not None
                    try:
                        coverage = role_window.assert_collection_coverage(collection_availability)
                        receipt = archive_receipts.get((str(store.root.resolve()), collection_id))
                        if receipt is None:
                            raise FeatureBundleError("accepted collection has no matching verified evidence archive receipt")
                        verify_hot_cold_equivalence(store=store, collection_id=collection_id, receipt_path=Path(receipt["receipt_path"]))
                    except (RoleCaptureWindowError, EvidenceArchiveError) as exc:
                        raise FeatureBundleError(str(exc)) from exc
                    receipt_binding = {
                        "archive_id": receipt["archive_id"],
                        "receipt_sha256": receipt["receipt_sha256"],
                        "receipt_path": receipt["receipt_path"],
                    }
                provenance = {"data_dir": str(store.root.resolve()), "collection_id": collection_id, "collection_audit_digest": accepted["collection_audit_digest"], "collection_replay_digest": accepted["collection_replay_digest"]}
                evidence_id = _sha256(provenance)
                count = 0
                for feature in FeaturePipeline(episode_policy, context_policy).replay_collection(store, collection_id):
                    row = feature.to_dict()
                    row["event_id"], row["source_event_id"] = evidence_id + "/" + row["event_id"], row["event_id"]
                    if row["episode_id"] is not None:
                        row["episode_id"] = evidence_id + "/" + row["episode_id"]
                    row["evidence"] = dict(provenance, evidence_id=evidence_id)
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    if context_handle is not None:
                        context_handle.write(json.dumps({
                            "feature_event_id": row["event_id"],
                            "source_event_id": row["source_event_id"],
                            "available_at": row["available_at"],
                            "availability_kind": row["availability_kind"],
                            "episode_id": row["episode_id"],
                            "episode_decision_eligible": row.get("episode_decision_eligible"),
                            "context": row.get("context"),
                            "evidence": row["evidence"],
                        }, ensure_ascii=False, sort_keys=True) + "\n")
                    count += 1
                collections.append(dict(provenance, evidence_id=evidence_id, feature_rows=count, collection_manifest_sha256=_sha256(manifest), **({"role_window_coverage": coverage, "archive_receipt": receipt_binding} if context_mode else {})))
                total_rows += count
            handle.flush(); os.fsync(handle.fileno())
            if context_handle is not None:
                context_handle.flush(); os.fsync(context_handle.fileno()); context_handle.close()
    except OSError as exc:
        raise FeatureBundleError("cannot write role feature bundle") from exc
    binding = {"protocol": {"id": protocol.protocol_id, "sha256": protocol.digest}, "role": role, "capture_plan": {"id": plan.plan_id, "sha256": plan.digest}, "acceptance_policy": {"id": policy.policy_id, "sha256": policy.digest}, "acceptance_report": {"id": report["report_id"], "sha256": report["report_sha256"]}, "allowed_availability": "ACTUAL_ONLY"}
    value = {"record_type": "feature_bundle_manifest", "bundle_id": bundle_id, "feature_artifact": str(output), "feature_artifact_sha256": sha256_file(output), "feature_rows": total_rows, "episode_policy_id": episode_policy.policy_id, "episode_policy_sha256": episode_policy.digest, "collections": collections, "evidence_binding": binding}
    if context_mode:
        assert context_policy is not None and role_window is not None and context_output is not None and context_manifest_output is not None
        context_value = {
            "record_type": "feature_context_artifact_manifest",
            "context_artifact": str(context_output),
            "context_artifact_sha256": sha256_file(context_output),
            "feature_artifact_sha256": value["feature_artifact_sha256"],
            "context_policy": {"id": context_policy.context_policy_id, "sha256": context_policy.digest},
            "role_window": {"id": role_window.window_id, "sha256": role_window.digest},
            "role": role,
            "measurement_contract": {
                "clock": "closed_utc_second",
                "publish_rule": "first ACTUAL event after the measured second closes; output available_at is that real event time",
                "price_impact_1s": "log(end_of_bucket_mid_t/end_of_bucket_mid_t_minus_1)",
                "pressure_side": "end_of_bucket D_directional_pressure (existing rolling-10s point-in-time feature)",
                "R_directional": "log(pressure_side_visible_depth_t/pressure_side_visible_depth_t_minus_1)-abs(price_impact_1s)",
                "R_directional_improvement": "same pressure side, contiguous closed UTC seconds only; otherwise unavailable",
            },
            "collections": [{"evidence_id": row["evidence_id"], "collection_id": row["collection_id"], "role_window_coverage": row["role_window_coverage"], "archive_receipt": row["archive_receipt"]} for row in collections],
        }
        context_value["manifest_sha256"] = _sha256(context_value)
        context_manifest_output.parent.mkdir(parents=True, exist_ok=True)
        with context_manifest_output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(context_value) + "\n"); handle.flush(); os.fsync(handle.fileno())
        value["context_binding"] = {
            "policy_id": context_policy.context_policy_id,
            "policy_sha256": context_policy.digest,
            "artifact": str(context_output),
            "artifact_sha256": context_value["context_artifact_sha256"],
            "context_manifest": str(context_manifest_output),
            "context_manifest_sha256": context_value["manifest_sha256"],
            "role_window": {"id": role_window.window_id, "sha256": role_window.digest},
        }
    value["manifest_sha256"] = _sha256(value)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    with manifest_output.open("x", encoding="utf-8") as handle:
        handle.write(_canonical(value) + "\n"); handle.flush(); os.fsync(handle.fileno())
    return dict(value, manifest_path=str(manifest_output))
