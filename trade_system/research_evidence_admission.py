"""Fail-closed admission of one role-isolated research evidence chain."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict

from .action_bundle import load_verified_action_bundle_manifest
from .capture_plan import ForwardCapturePlan
from .data_acceptance import DataAcceptanceError, assert_equal_or_stricter_than_g1, load_verified_data_acceptance_report
from .event_store import EventStore
from .feature_bundle import load_verified_feature_bundle_manifest
from .g1_acceptance import G1AcceptancePolicy
from .g1_report import load_passed_g1_report
from .label_bundle import load_verified_label_bundle_manifest
from .protocol import ResearchProtocol, V2_SCHEMA_VERSION
from .research_report import sha256_file
from .state_classifier import StateClassifier
from .state_label_bundle import load_verified_state_label_bundle_manifest
from .types import parse_utc, iso_utc, utc_now


class ResearchEvidenceAdmissionError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load_rows(path: Path) -> list[Dict[str, Any]]:
    rows = []
    try:
        handle = Path(path).open("r", encoding="utf-8")
    except OSError as exc:
        raise ResearchEvidenceAdmissionError("cannot read artifact") from exc
    with handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                raise ResearchEvidenceAdmissionError("artifact contains blank line %d" % number)
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ResearchEvidenceAdmissionError("artifact row is invalid JSON") from exc
            if not isinstance(row, dict):
                raise ResearchEvidenceAdmissionError("artifact row is not an object")
            rows.append(row)
    return rows


def _role_contract(protocol: ResearchProtocol, role: str) -> Dict[str, Any]:
    if role not in {"DEVELOPMENT", "HOLDOUT"}:
        raise ResearchEvidenceAdmissionError("role must be DEVELOPMENT or HOLDOUT")
    if protocol.raw.get("schema_version") != V2_SCHEMA_VERSION:
        raise ResearchEvidenceAdmissionError("research evidence admission requires protocol v2")
    contract = next((item for item in protocol.raw["data_eligibility"]["admitted_collection_roles"] if item.get("role") == role), None)
    if not isinstance(contract, dict):
        raise ResearchEvidenceAdmissionError("requested role is not in the frozen protocol")
    return contract


def _verify_collection(collection: Dict[str, Any], *, plan: ForwardCapturePlan) -> Dict[str, Any]:
    store = EventStore(Path(collection["data_dir"]), create=False)
    valid, issues, audit_digest = store.audit()
    if not valid:
        raise ResearchEvidenceAdmissionError("accepted event-store audit failed: %s" % "; ".join(issues))
    path = store.collection_manifest_root / (collection["collection_id"] + ".json")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchEvidenceAdmissionError("accepted collection manifest is unavailable") from exc
    if not isinstance(manifest, dict) or manifest.get("record_type") != "collection_manifest" or manifest.get("collection_result") != "QUALIFIED_SMOKE":
        raise ResearchEvidenceAdmissionError("accepted collection is not terminal qualified evidence")
    if manifest.get("audit_digest") != collection["collection_audit_digest"] or manifest.get("replay_digest") != collection["collection_replay_digest"]:
        raise ResearchEvidenceAdmissionError("accepted collection audit/replay binding drifted")
    capture = manifest.get("capture_plan")
    if not isinstance(capture, dict) or capture.get("plan_id") != plan.plan_id or capture.get("plan_sha256") != plan.digest or not isinstance(capture.get("slot_id"), str):
        raise ResearchEvidenceAdmissionError("accepted collection plan or slot binding drifted")
    if not any(slot.slot_id == capture["slot_id"] for slot in plan.slots):
        raise ResearchEvidenceAdmissionError("accepted collection refers to an undeclared capture slot")
    raws = [raw for raw in store.iter_raw() if raw.connection_id.startswith(collection["collection_id"] + "-")]
    seals = {item.stem for item in store.manifest_root.glob("*.json")}
    if not raws or any(Path(raw.raw_segment).stem not in seals for raw in raws):
        raise ResearchEvidenceAdmissionError("accepted collection raw evidence is not sealed")
    raw_ids = {raw.event_id for raw in raws}
    if any(record.availability_kind.value != "ACTUAL" for record in store.iter_availability() if record.event_id in raw_ids):
        raise ResearchEvidenceAdmissionError("accepted collection includes non-ACTUAL availability")
    return {"data_dir": str(store.root.resolve()), "collection_id": collection["collection_id"], "collection_manifest_sha256": _sha(manifest), "collection_audit_digest": manifest["audit_digest"], "collection_replay_digest": manifest["replay_digest"], "event_store_audit_sha256": audit_digest, "sealed_raw_segments": sorted({Path(raw.raw_segment).stem for raw in raws}), "capture_slot_id": capture["slot_id"]}


def _assert_manifest_chain(*, feature: Dict[str, Any], action: Dict[str, Any], label: Dict[str, Any], state: Dict[str, Any], labels_path: Path) -> None:
    """Ensure every downstream manifest names the exact upstream artifact."""
    if action.get("feature_bundle_manifest_sha256") != feature.get("manifest_sha256"):
        raise ResearchEvidenceAdmissionError("action bundle does not bind the loaded feature bundle")
    if label.get("feature_bundle_manifest_sha256") != feature.get("manifest_sha256"):
        raise ResearchEvidenceAdmissionError("label bundle does not bind the loaded feature bundle")
    if label.get("action_bundle_manifest_sha256") != action.get("manifest_sha256"):
        raise ResearchEvidenceAdmissionError("label bundle does not bind the loaded action bundle")
    if state.get("label_bundle_manifest_sha256") != label.get("manifest_sha256"):
        raise ResearchEvidenceAdmissionError("state-label bundle does not bind the loaded label bundle")
    if state.get("feature_bundle_manifest_sha256") != feature.get("manifest_sha256"):
        raise ResearchEvidenceAdmissionError("state-label bundle does not bind the loaded feature bundle")
    if state.get("labels_artifact_sha256") != sha256_file(Path(labels_path)):
        raise ResearchEvidenceAdmissionError("state-label bundle does not bind the loaded labels artifact")


def admit_research_evidence(
    *,
    protocol_path: Path,
    role: str,
    capture_plan_path: Path,
    acceptance_policy_path: Path,
    acceptance_report_path: Path,
    baseline_g1_policy_path: Path,
    g1_report_path: Path,
    feature_path: Path,
    feature_manifest_path: Path,
    actions_path: Path,
    action_manifest_path: Path,
    labels_path: Path,
    label_manifest_path: Path,
    state_labels_path: Path,
    state_manifest_path: Path,
    classifier_path: Path,
    output_path: Path,
    admission_id: str,
) -> Dict[str, Any]:
    if not isinstance(admission_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", admission_id):
        raise ResearchEvidenceAdmissionError("admission_id must be a safe non-empty identifier")
    protocol = ResearchProtocol.load(Path(protocol_path)); protocol.assert_frozen_for_research()
    contract = _role_contract(protocol, role)
    plan = ForwardCapturePlan.load(Path(capture_plan_path))
    policy, baseline = G1AcceptancePolicy.load(Path(acceptance_policy_path)), G1AcceptancePolicy.load(Path(baseline_g1_policy_path))
    if contract["capture_plan"] != {"id": plan.plan_id, "sha256": plan.digest} or contract["acceptance_policy"] != {"id": policy.policy_id, "sha256": policy.digest}:
        raise ResearchEvidenceAdmissionError("role plan or acceptance policy does not match frozen protocol")
    try:
        assert_equal_or_stricter_than_g1(policy, baseline)
        accepted = load_verified_data_acceptance_report(acceptance_report_path, role=role, policy=policy, plan=plan)
    except DataAcceptanceError as exc:
        raise ResearchEvidenceAdmissionError(str(exc)) from exc
    qualification = protocol.g1_qualification
    load_passed_g1_report(Path(g1_report_path), policy_id=qualification["required_g1_policy_id"], expected_sha256=qualification["required_g1_report_sha256"], expected_policy_sha256=qualification.get("required_g1_policy_sha256", ""))
    classifier = StateClassifier.load(Path(classifier_path))
    feature = load_verified_feature_bundle_manifest(feature_manifest_path, feature_path=feature_path)
    action = load_verified_action_bundle_manifest(action_manifest_path, actions_path=actions_path, feature_manifest_sha256=feature["manifest_sha256"])
    label = load_verified_label_bundle_manifest(label_manifest_path, labels_path=labels_path)
    state = load_verified_state_label_bundle_manifest(state_manifest_path, labels_path=state_labels_path, classifier=classifier)
    # Evidence-binding equality alone is not enough: a copied manifest could
    # retain the same binding while pointing at a different upstream artifact.
    _assert_manifest_chain(feature=feature, action=action, label=label, state=state, labels_path=Path(labels_path))
    binding = feature.get("evidence_binding")
    expected_binding = {"protocol": {"id": protocol.protocol_id, "sha256": protocol.digest}, "role": role, "capture_plan": {"id": plan.plan_id, "sha256": plan.digest}, "acceptance_policy": {"id": policy.policy_id, "sha256": policy.digest}, "acceptance_report": {"id": accepted["report_id"], "sha256": accepted["report_sha256"]}, "allowed_availability": "ACTUAL_ONLY"}
    if binding != expected_binding or action.get("evidence_binding") != binding or label.get("evidence_binding") != binding or state.get("evidence_binding") != binding:
        raise ResearchEvidenceAdmissionError("artifact manifests do not preserve one exact role evidence_binding")
    collections = [_verify_collection(item, plan=plan) for item in accepted["qualified_collections"]]
    by_evidence = {item["evidence_id"]: item for item in feature["collections"]}
    if set(by_evidence) != {item["evidence_id"] for item in feature["collections"]} or len(by_evidence) != len(collections):
        raise ResearchEvidenceAdmissionError("feature bundle collection count is inconsistent")
    accepted_keys = {(str(Path(item["data_dir"]).resolve()), item["collection_id"], item["collection_audit_digest"], item["collection_replay_digest"]) for item in accepted["qualified_collections"]}
    feature_keys = {(str(Path(str(item.get("data_dir", ""))).resolve()), item.get("collection_id"), item.get("collection_audit_digest"), item.get("collection_replay_digest")) for item in feature["collections"]}
    if feature_keys != accepted_keys:
        raise ResearchEvidenceAdmissionError("feature bundle does not contain exactly accepted role collections")
    feature_rows = _load_rows(feature_path)
    if any(row.get("availability_kind") != "ACTUAL" for row in feature_rows):
        raise ResearchEvidenceAdmissionError("feature artifact contains non-ACTUAL row")
    labels = _load_rows(state_labels_path)
    window = contract["time_window"]
    start, end, horizon = parse_utc(window["decision_start"]), parse_utc(window["decision_end"]), float(window["label_horizon_seconds"])
    evidence_ids = set(by_evidence)
    for row in labels:
        if row.get("evidence_id") not in evidence_ids:
            raise ResearchEvidenceAdmissionError("state label references evidence outside admitted role")
        decision = parse_utc(row["decision_at"])
        if not start <= decision < end:
            raise ResearchEvidenceAdmissionError("state label decision is outside admitted role window")
        if row.get("label_end_at") is not None:
            label_end = parse_utc(row["label_end_at"])
            if label_end < decision or label_end > decision + timedelta(seconds=horizon) or label_end > end + timedelta(seconds=horizon):
                raise ResearchEvidenceAdmissionError("state label crosses admitted role horizon/window")
    target = Path(output_path)
    if target.exists():
        raise ResearchEvidenceAdmissionError("research evidence admission output already exists")
    value = {"record_type": "research_evidence_admission", "schema_version": "research_evidence_admission.v1", "admission_id": admission_id, "status": "ADMITTED", "admitted_at": iso_utc(utc_now()), "protocol": expected_binding["protocol"], "role": role, "evidence_binding": binding, "state_labels_artifact_sha256": sha256_file(Path(state_labels_path)), "state_label_manifest_sha256": state["manifest_sha256"], "feature_bundle_manifest_sha256": feature["manifest_sha256"], "action_bundle_manifest_sha256": action["manifest_sha256"], "label_bundle_manifest_sha256": label["manifest_sha256"], "collections": collections, "state_label_rows": len(labels)}
    value["manifest_sha256"] = _sha(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        handle.write(_canonical(value) + "\n"); handle.flush(); os.fsync(handle.fileno())
    return value


def load_verified_research_evidence_admission(path: Path, *, state_labels_path: Path, protocol: ResearchProtocol, role: str, state_label_manifest_sha256: str = "") -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchEvidenceAdmissionError("cannot load research evidence admission") from exc
    if not isinstance(value, dict) or value.get("record_type") != "research_evidence_admission" or value.get("schema_version") != "research_evidence_admission.v1":
        raise ResearchEvidenceAdmissionError("invalid research evidence admission type")
    body = dict(value); digest = body.pop("manifest_sha256", None)
    if not isinstance(digest, str) or digest != _sha(body):
        raise ResearchEvidenceAdmissionError("research evidence admission digest does not match content")
    if value.get("status") != "ADMITTED" or value.get("role") != role:
        raise ResearchEvidenceAdmissionError("research evidence admission role is invalid")
    if value.get("protocol") != {"id": protocol.protocol_id, "sha256": protocol.digest}:
        raise ResearchEvidenceAdmissionError("research evidence admission protocol does not match")
    if value.get("state_labels_artifact_sha256") != sha256_file(Path(state_labels_path)):
        raise ResearchEvidenceAdmissionError("research evidence admission state-label artifact does not match")
    if state_label_manifest_sha256 and value.get("state_label_manifest_sha256") != state_label_manifest_sha256:
        raise ResearchEvidenceAdmissionError("research evidence admission state-label manifest does not match the consumer")
    return value
