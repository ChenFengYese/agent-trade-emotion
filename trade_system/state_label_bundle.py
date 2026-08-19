"""State-classified label artifacts that preserve G1 provenance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

from .label_bundle import LabelBundleError, load_verified_label_bundle_manifest
from .research_report import sha256_file
from .state_classifier import StateClassifier


class StateLabelBundleError(ValueError):
    pass


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise StateLabelBundleError("%s must be a non-empty string" % field)
    return value


def load_verified_state_label_bundle_manifest(path: Path, *, labels_path: Path, classifier: StateClassifier) -> Dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateLabelBundleError("cannot load state-label bundle manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("record_type") != "state_label_bundle_manifest":
        raise StateLabelBundleError("invalid state-label bundle manifest record type")
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str):
        raise StateLabelBundleError("state-label bundle manifest digest is missing")
    body = dict(manifest)
    body.pop("manifest_sha256", None)
    if digest != _sha256(body):
        raise StateLabelBundleError("state-label bundle manifest digest does not match content")
    if manifest.get("state_labels_artifact_sha256") != sha256_file(Path(labels_path)):
        raise StateLabelBundleError("state-label artifact digest does not match manifest")
    if manifest.get("state_classifier_id") != classifier.classifier_id or manifest.get("state_classifier_sha256") != classifier.digest:
        raise StateLabelBundleError("state-label classifier does not match supplied classifier")
    _non_empty(manifest.get("label_bundle_manifest_sha256"), "label_bundle_manifest_sha256")
    if "evidence_binding" not in manifest:
        _non_empty(manifest.get("g1_policy_id"), "g1_policy_id")
        _non_empty(manifest.get("g1_report_sha256"), "g1_report_sha256")
    return manifest


def build_state_label_bundle(
    *,
    labels_path: Path,
    label_manifest_path: Path,
    classifier_path: Path,
    output_path: Path,
    manifest_path: Path,
    state_labels_id: str,
) -> Dict[str, Any]:
    _non_empty(state_labels_id, "state_labels_id")
    try:
        label_manifest = load_verified_label_bundle_manifest(label_manifest_path, labels_path=labels_path)
    except LabelBundleError as exc:
        raise StateLabelBundleError(str(exc)) from exc
    classifier = StateClassifier.load(classifier_path)
    output, manifest_output = Path(output_path), Path(manifest_path)
    if output.resolve() == manifest_output.resolve():
        raise StateLabelBundleError("state-label artifact and manifest must be different paths")
    if output.exists() or manifest_output.exists():
        raise StateLabelBundleError("state-label artifact and manifest paths must both be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: Dict[str, int] = {state_id: 0 for state_id in classifier.state_ids}
    count = 0
    try:
        with Path(labels_path).open("r", encoding="utf-8") as source, output.open("x", encoding="utf-8") as destination:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict) or not isinstance(row.get("features"), dict):
                        raise ValueError("label row needs a feature object")
                    features = {key: float(value) for key, value in row["features"].items()}
                    state_id = classifier.classify(features)
                    row["state_id"] = state_id
                    row["state_classifier_id"] = classifier.classifier_id
                    row["state_classifier_sha256"] = classifier.digest
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise StateLabelBundleError("invalid label row at line %d: %s" % (line_number, exc)) from exc
                destination.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                counts[state_id] = counts.get(state_id, 0) + 1
                count += 1
            destination.flush()
            os.fsync(destination.fileno())
    except OSError as exc:
        raise StateLabelBundleError("cannot write state-label artifact") from exc
    manifest = {
        "record_type": "state_label_bundle_manifest",
        "state_labels_id": state_labels_id,
        "state_labels_artifact": str(output),
        "state_labels_artifact_sha256": sha256_file(output),
        "state_labels_written": count,
        "label_bundle_manifest_sha256": label_manifest["manifest_sha256"],
        "labels_artifact_sha256": label_manifest["labels_artifact_sha256"],
        "feature_bundle_manifest_sha256": label_manifest["feature_bundle_manifest_sha256"],
        "state_classifier_id": classifier.classifier_id,
        "state_classifier_sha256": classifier.digest,
        "state_counts": counts,
    }
    if "evidence_binding" in label_manifest:
        manifest["evidence_binding"] = label_manifest["evidence_binding"]
    else:
        manifest["g1_policy_id"] = label_manifest["g1_policy_id"]
        manifest["g1_report_sha256"] = label_manifest["g1_report_sha256"]
    if "context_binding" in label_manifest:
        manifest["context_binding"] = label_manifest["context_binding"]
    manifest["manifest_sha256"] = _sha256(manifest)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with manifest_output.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(manifest) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise StateLabelBundleError("cannot write state-label bundle manifest") from exc
    return dict(manifest, manifest_path=str(manifest_output))
