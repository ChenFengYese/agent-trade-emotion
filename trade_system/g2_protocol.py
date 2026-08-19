"""Protocol-v2 bound, development-only G2 evaluation entry point."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

from .g2_evaluator import AblationPair, FeatureTerm, G2EvaluationError, G2EvaluatorPolicy, evaluate_g2
from .feature_bundle import load_verified_feature_bundle_manifest
from .evidence_archive import EvidenceArchiveError, load_verified_evidence_archive_receipt, verify_evidence_archive
from .protocol import ProtocolError, ResearchProtocol, V2_SCHEMA_VERSION
from .research_evidence_admission import ResearchEvidenceAdmissionError, load_verified_research_evidence_admission
from .research_report import sha256_file
from .state_classifier import StateClassifier
from .state_label_bundle import load_verified_state_label_bundle_manifest
from .types import iso_utc, parse_utc, utc_now


class G2ProtocolError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _policy(protocol: ResearchProtocol, *, as_of: str) -> G2EvaluatorPolicy:
    if protocol.raw.get("schema_version") != V2_SCHEMA_VERSION:
        raise G2ProtocolError("formal G2 requires protocol v2")
    raw = protocol.raw.get("g2_evaluator")
    if not isinstance(raw, dict):
        raise G2ProtocolError("protocol is missing machine-readable g2_evaluator")
    try:
        groups = {
            name: tuple(FeatureTerm(str(term["name"]), str(term.get("transform", "IDENTITY")), tuple(term.get("sources", ()))) for term in terms)
            for name, terms in raw["feature_groups"].items()
        }
        pairs = {
            key: AblationPair(key, str(value["candidate_group"]), str(value["control_group"]))
            for key, value in raw["ablation_pairs"].items()
        }
        costs = raw["cost_scenarios"]
        return G2EvaluatorPolicy(
            as_of=parse_utc(as_of), folds=int(raw["folds"]), embargo_seconds=int(raw["embargo_seconds"]),
            feature_groups=groups, ablation_pairs=pairs, utility_feature_group=str(raw["utility_feature_group"]),
            calibration_fraction=float(raw["calibration_fraction"]), min_effective_episodes=int(raw["min_effective_episodes"]),
            min_effective_episodes_per_state=int(raw["min_effective_episodes_per_state"]),
            required_states=tuple(raw["required_state_ids"]), min_utc_days=int(raw["bootstrap"]["min_utc_days"]),
            bootstrap_iterations=int(raw["bootstrap"]["iterations"]), bootstrap_seed=int(raw["bootstrap"]["seed"]),
            base_round_trip_cost_bps=float(costs["base"]["round_trip_bps"]), stress_round_trip_cost_bps=float(costs["stress"]["round_trip_bps"]),
            tp_gross_return_bps=float(raw["payoff_proxy_bps"]["TP"]), sl_gross_return_bps=float(raw["payoff_proxy_bps"]["SL"]),
            relative_logloss_improvement_min=float(raw["relative_logloss_improvement_min"]),
            min_successful_folds=int(raw["min_successful_folds"]),
            max_day_concentration=float(raw["concentration_limits"]["utc_day"]), max_state_concentration=float(raw["concentration_limits"]["state"]), max_direction_concentration=float(raw["concentration_limits"]["direction"]),
            required_sides=tuple(raw["required_sides"]), min_effective_episodes_per_side=int(raw["min_effective_episodes_per_side"]),
            min_effective_episodes_per_state_per_side=int(raw["min_effective_episodes_per_state_per_side"]), separate_models=raw["modeling_policy"] == "SEPARATE_MODELS",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise G2ProtocolError("protocol g2_evaluator is malformed") from exc


def _load_json(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise G2ProtocolError("cannot load %s" % label) from exc
    if not isinstance(value, dict):
        raise G2ProtocolError("%s must be an object" % label)
    return value


def _verify_context_evidence(*, feature_manifest: Dict[str, Any], required: Dict[str, Any]) -> Dict[str, Any]:
    context = feature_manifest.get("context_binding")
    if not isinstance(context, dict) or context.get("policy_id") != required["policy"]["id"] or context.get("policy_sha256") != required["policy"]["sha256"] or context.get("artifact_sha256") != required["artifact"]["sha256"] or context.get("context_manifest_sha256") != required["artifact"]["manifest_sha256"] or context.get("role_window") != required["role_window"]:
        raise G2ProtocolError("feature context binding does not match frozen protocol")
    artifact_path, manifest_path = context.get("artifact"), context.get("context_manifest")
    if not isinstance(artifact_path, str) or not isinstance(manifest_path, str):
        raise G2ProtocolError("context artifact paths are missing")
    if sha256_file(Path(artifact_path)) != context["artifact_sha256"]:
        raise G2ProtocolError("context artifact digest drifted")
    manifest = _load_json(Path(manifest_path), "context manifest")
    body = dict(manifest); declared = body.pop("manifest_sha256", None)
    if declared != _sha(body) or declared != context["context_manifest_sha256"]:
        raise G2ProtocolError("context manifest digest drifted")
    if manifest.get("context_artifact_sha256") != context["artifact_sha256"] or manifest.get("feature_artifact_sha256") != feature_manifest.get("feature_artifact_sha256"):
        raise G2ProtocolError("context manifest artifact binding drifted")
    if manifest.get("context_policy") != {"id": context["policy_id"], "sha256": context["policy_sha256"]} or manifest.get("role_window") != context["role_window"]:
        raise G2ProtocolError("context manifest policy/window binding drifted")
    feature_collections = feature_manifest.get("collections")
    context_collections = manifest.get("collections")
    if not isinstance(feature_collections, list) or not isinstance(context_collections, list) or len(feature_collections) != len(context_collections):
        raise G2ProtocolError("context collection receipt set is incomplete")
    seen = set(); rendered = []
    by_evidence = {item.get("evidence_id"): item for item in context_collections if isinstance(item, dict)}
    for collection in feature_collections:
        if not isinstance(collection, dict) or collection.get("evidence_id") in seen:
            raise G2ProtocolError("feature collections are invalid or repeated")
        seen.add(collection["evidence_id"])
        linked = by_evidence.get(collection["evidence_id"])
        binding = collection.get("archive_receipt")
        if not isinstance(linked, dict) or linked.get("collection_id") != collection.get("collection_id") or linked.get("archive_receipt") != binding or not isinstance(binding, dict):
            raise G2ProtocolError("context receipt does not match feature collection")
        path = binding.get("receipt_path")
        if not isinstance(path, str):
            raise G2ProtocolError("archive receipt path is missing")
        try:
            receipt = load_verified_evidence_archive_receipt(Path(path)); cold = verify_evidence_archive(Path(path))
        except EvidenceArchiveError as exc:
            raise G2ProtocolError(str(exc)) from exc
        if receipt.get("receipt_sha256") != binding.get("receipt_sha256") or receipt.get("archive_id") != binding.get("archive_id") or receipt.get("collection_id") != collection.get("collection_id") or str(Path(receipt.get("source_evidence_root", "")).resolve()) != str(Path(collection.get("data_dir", "")).resolve()) or not cold.get("valid"):
            raise G2ProtocolError("archive receipt does not prove the feature collection")
        rendered.append({"archive_id": receipt["archive_id"], "receipt_sha256": receipt["receipt_sha256"], "collection_id": receipt["collection_id"]})
    return {"context_binding": context, "archive_receipts": rendered}


def evaluate_protocol_g2(*, protocol_path: Path, evidence_admission_path: Path, state_labels_path: Path, state_manifest_path: Path, classifier_path: Path, feature_path: Path, feature_manifest_path: Path, output_path: Path, as_of: str) -> Dict[str, Any]:
    try:
        protocol = ResearchProtocol.load(protocol_path)
        protocol.assert_frozen_for_research()
    except ProtocolError as exc:
        raise G2ProtocolError(str(exc)) from exc
    if protocol.raw.get("schema_version") != V2_SCHEMA_VERSION:
        raise G2ProtocolError("formal G2 requires frozen protocol v2")
    classifier = StateClassifier.load(classifier_path)
    state_manifest = load_verified_state_label_bundle_manifest(state_manifest_path, labels_path=state_labels_path, classifier=classifier)
    try:
        admission = load_verified_research_evidence_admission(
            evidence_admission_path, state_labels_path=state_labels_path, protocol=protocol, role="DEVELOPMENT",
            state_label_manifest_sha256=state_manifest["manifest_sha256"],
        )
    except ResearchEvidenceAdmissionError as exc:
        raise G2ProtocolError(str(exc)) from exc
    feature_manifest = load_verified_feature_bundle_manifest(feature_manifest_path, feature_path=feature_path)
    if feature_manifest.get("manifest_sha256") != admission.get("feature_bundle_manifest_sha256"):
        raise G2ProtocolError("development admission does not bind supplied feature manifest")
    required_context = protocol.raw["context_evidence"]
    verified_context = _verify_context_evidence(feature_manifest=feature_manifest, required=required_context)
    state_policy = protocol.raw["state_coverage_policy"]
    if classifier.classifier_id != state_policy["classifier_id"] or classifier.digest != state_policy["classifier_digest"]:
        raise G2ProtocolError("state classifier does not match frozen protocol")
    try:
        rows = [json.loads(line) for line in Path(state_labels_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise G2ProtocolError("cannot load state-label artifact") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise G2ProtocolError("state-label artifact contains non-object row")
    try:
        # State-label artifacts deliberately do not repeat an availability
        # field.  DEVELOPMENT admission has just re-audited the entire chain
        # as ACTUAL_ONLY, so this is a checked transport annotation, not an
        # inferred market value or an execution claim.
        result = evaluate_g2((dict(row, availability_kind="ACTUAL") for row in rows), policy=_policy(protocol, as_of=as_of))
    except G2EvaluationError as exc:
        raise G2ProtocolError(str(exc)) from exc
    value = dict(result)
    value.update({
        "record_type": "g2_protocol_evaluation.v1", "research_status": value["overall_status"],
        "meaning": "DEVELOPMENT-only counterfactual market-path utility after declared costs; not execution PnL, trading performance, or trading authorization.",
        "written_at": iso_utc(utc_now()), "protocol": {"id": protocol.protocol_id, "sha256": protocol.digest},
        "development_evidence_admission_sha256": admission["manifest_sha256"],
        "state_labels_artifact_sha256": sha256_file(state_labels_path), "state_label_manifest_sha256": state_manifest["manifest_sha256"],
        "state_classifier": {"id": classifier.classifier_id, "sha256": classifier.digest},
        "feature_bundle_manifest_sha256": feature_manifest["manifest_sha256"], **verified_context,
    })
    target = Path(output_path)
    if target.exists():
        raise G2ProtocolError("G2 output already exists")
    value["report_sha256"] = _sha(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(value) + "\n"); handle.flush(); os.fsync(handle.fileno())
    except OSError as exc:
        raise G2ProtocolError("cannot write G2 report") from exc
    return value
